"""Focused tests for the two WakeSafe risk-engine fixes (Person B).

FIX 1 - Menopause gating: never fires for a male; requires a marked cycle
        disruption (reported peri/menopause condition OR a cycle:* marker).
FIX 2 - Travel: location/speed inference + TRACK-ONLY suppression. A travelling
        night is KEPT and tracked, but it cannot push a group to High on its own
        and no care recommendation is ranked solely on the travel window.

Plus the three live checks the acceptance names, via the FastAPI TestClient:
  * /demo/MENOPAUSE flags Menopause High
  * a male profile with the same signals does NOT flag menopause
  * a travelling-night persona (ALTITUDE / JETLAG) is tracked but yields no
    care recommendation ranked solely on the travel window.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/, so `app` imports

from app.api.demo import load_demo
from app.api.pipeline import run_screen
from app.main import app
from app.models.schemas import ApneaScore, FeatureSet, ProfileInput
from app.services.risks import (
    assess_risks,
    care_warranted_outside_travel,
    infer_travel_from_locations,
    travel_track_only_risk_ids,
)
from app.services.risks.rules import TRACK_ONLY_REASON

client = TestClient(app)


# ---- builders ---------------------------------------------------------------


def make_apnea(tier="Low") -> ApneaScore:
    return ApneaScore(
        tier=tier,
        probability=None,
        stop_bang_score=0,
        top_factors=[],
        model_version="apnea-hr-rmssd-v1+rules",
        evidence_note="Synthetic demonstration data; screening aid only.",
    )


CALM_Z = {
    "spo2_pct": 0.0,
    "respiratory_rate_rpm": 0.0,
    "disturbance_count": 0.0,
    "sleep_efficiency_pct": 0.0,
    "resting_heart_rate_bpm": 0.0,
    "hrv_rmssd_ms": 0.0,
    "skin_temperature_c": 0.0,
}


def make_features(z=None, flags=None) -> FeatureSet:
    return FeatureSet(
        values={},
        baseline_z_scores={**CALM_Z, **(z or {})},
        nights_available=14,
        nights_with_spo2=14,
        data_quality_flags=list(flags or []),
    )


def get_risk(assessment, risk_id):
    for r in assessment.risks:
        if r.risk_id == risk_id:
            return r
    raise AssertionError(f"no risk {risk_id}")


# ---- FIX 1: menopause sex + cycle gate --------------------------------------


def test_menopause_blocked_for_male_variants():
    for male in ("male", "M", "m", "Man"):
        a = assess_risks(
            ProfileInput(sex=male, conditions=["irregular periods"]),
            make_features(
                z={"sleep_efficiency_pct": -3.0, "disturbance_count": 3.5},
                flags=["cycle:irregular"],
            ),
            make_apnea("Low"),
        )
        # EXCLUDED entirely for a male -- not scored, not listed, not a zeroed row.
        risk_ids = {r.risk_id for r in a.risks}
        assert "menopause" not in risk_ids, (male, sorted(risk_ids))


def test_menopause_allowed_for_female_and_unknown():
    for sex in ("female", "F", None):
        a = assess_risks(
            ProfileInput(sex=sex),
            make_features(
                z={"sleep_efficiency_pct": -3.0, "disturbance_count": 3.5},
                flags=["cycle:irregular"],
            ),
            make_apnea("Low"),
        )
        assert get_risk(a, "menopause").tier in ("Moderate", "High"), sex


def test_menopause_requires_cycle_signal():
    # Female, warm/disturbed signals, but NO cycle marker and NO reported
    # condition -> must stay Low (the signals are non-specific on their own).
    a = assess_risks(
        ProfileInput(sex="female"),
        make_features(z={"sleep_efficiency_pct": -3.0, "disturbance_count": 3.5}),
        make_apnea("Low"),
    )
    meno = get_risk(a, "menopause")
    assert meno.tier == "Low", (meno.tier, meno.reasons)


def test_menopause_cycle_marker_is_enough_without_reported_condition():
    a = assess_risks(
        ProfileInput(sex="female"),
        make_features(
            z={"sleep_efficiency_pct": -3.0, "disturbance_count": 3.5},
            flags=["cycle:irregular"],
        ),
        make_apnea("Low"),
    )
    assert get_risk(a, "menopause").tier in ("Moderate", "High")


def test_menopause_reported_condition_is_enough_without_cycle_marker():
    a = assess_risks(
        ProfileInput(sex="female", conditions=["hot flashes"]),
        make_features(),
        make_apnea("Low"),
    )
    assert get_risk(a, "menopause").tier in ("Moderate", "High")


# ---- FIX 2: travel inference + track-only suppression -----------------------


def test_infer_travel_from_locations_flying():
    # ~5000 km apart, 24 h -> clearly flying/driving, well past the travel speed.
    locs = [(42.36, -71.06, 0.0), (37.77, -122.42, 24 * 3600.0)]
    travelling, mode, speed = infer_travel_from_locations(locs)
    assert travelling is True
    assert mode in ("driving", "flying")
    assert speed > 40.0


def test_infer_travel_from_locations_stationary():
    # Same spot across three nights -> not travelling.
    locs = [(42.36, -71.06, 0.0), (42.36, -71.06, 86400.0), (42.36, -71.06, 172800.0)]
    travelling, mode, speed = infer_travel_from_locations(locs)
    assert travelling is False
    assert mode == "stationary"


def test_travel_window_is_track_only_and_capped_below_high():
    # A big SpO2 dip under an altitude travel flag: the data is kept (reason
    # present) but the group is track-only and cannot reach High on its own.
    a = assess_risks(
        ProfileInput(),
        make_features(z={"spo2_pct": -6.0}, flags=["travel:altitude:2500m"]),
        make_apnea("Low"),
    )
    sdb = get_risk(a, "sleep_disordered_breathing")
    assert sdb.tier in ("Low", "Moderate")  # never High on a travel window alone
    assert "sleep_disordered_breathing" in travel_track_only_risk_ids(a)
    assert any(TRACK_ONLY_REASON in r for r in sdb.reasons)
    # Care based solely on the travel window is paused.
    assert care_warranted_outside_travel(a) is False


def test_non_travel_signal_lifts_the_track_only_cap():
    # A travel flag present, but a NON-travel signal (resting HR, not relaxed by
    # altitude) also fires -> care IS warranted from non-travel data.
    a = assess_risks(
        ProfileInput(),
        make_features(
            z={"spo2_pct": -6.0, "resting_heart_rate_bpm": 4.0},
            flags=["travel:altitude:2500m"],
        ),
        make_apnea("Low"),
    )
    assert get_risk(a, "cardiovascular").tier != "Low"
    assert care_warranted_outside_travel(a) is True


# ---- live demo checks (the three acceptance behaviours) ---------------------


def test_live_demo_menopause_flags_high():
    body = client.get("/demo/MENOPAUSE").json()
    meno = next(r for r in body["risk_assessment"]["risks"] if r["risk_id"] == "menopause")
    assert meno["tier"] == "High", meno


def test_live_male_profile_same_menopause_signals_does_not_flag():
    # Same nights + out-of-band flags the MENOPAUSE demo uses, but a male profile.
    _canon, _profile, nights, flags = load_demo("MENOPAUSE")
    _f, _a, assessment = run_screen(ProfileInput(sex="male"), nights, flags)
    # Excluded entirely for a male: no menopause row at all (not a Low row).
    assert "menopause" not in {r.risk_id for r in assessment.risks}


def test_live_demo_travel_personas_are_tracked_but_recs_paused():
    for persona in ("ALTITUDE", "JETLAG"):
        body = client.get("/demo/" + persona).json()
        # Nights are KEPT (still returned in the report).
        assert len(body["report"]["nights"]) >= 14, persona
        # No care recommendation ranked solely on the travel window.
        assert body["care"]["recommendations"] == [], persona
        assert "paused" in body["care"]["disclaimer"].lower(), persona
        # No risk reached High purely on the travel window.
        for r in body["risk_assessment"]["risks"]:
            assert r["tier"] != "High", (persona, r["risk_id"])
