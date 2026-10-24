"""Tests for the multi-domain risk engine (Person B).

Personas drive assess_risks to Low / Moderate / High / Urgent, plus one
"altitude night" whose SpO2 dip would flag at home but is suppressed under a
travel context flag. Imports the public entry point and the frozen contract only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/, so `app` is importable

from app.models.schemas import ApneaScore, FeatureSet, ProfileInput, RiskAssessment, RiskItem
from app.services.risks import RULES_VERSION, assess_risks


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


def make_features(z=None, flags=None, nights=14, spo2_nights=14) -> FeatureSet:
    return FeatureSet(
        values={},
        baseline_z_scores={**CALM_Z, **(z or {})},
        nights_available=nights,
        nights_with_spo2=spo2_nights,
        data_quality_flags=list(flags or []),
    )


def make_profile(conditions=None, red_flags=None) -> ProfileInput:
    return ProfileInput(
        conditions=list(conditions or []),
        red_flag_symptoms=list(red_flags or []),
    )


def get_risk(assessment: RiskAssessment, risk_id: str) -> RiskItem:
    for r in assessment.risks:
        if r.risk_id == risk_id:
            return r
    raise AssertionError(f"no risk {risk_id} in {[r.risk_id for r in assessment.risks]}")


# ---- contract shape ---------------------------------------------------------


def test_returns_all_six_groups_and_stamps_version_and_disclaimer():
    a = assess_risks(make_profile(), make_features(), make_apnea("Low"))
    assert {r.risk_id for r in a.risks} == {
        "sleep_disordered_breathing",
        "cardiovascular",
        "metabolic",
        "respiratory",
        "acute_illness",
        "menopause",
    }
    assert a.rules_version == RULES_VERSION
    assert "screening" in a.disclaimer.lower() and "not a diagnosis" in a.disclaimer.lower()
    for r in a.risks:
        assert r.tier in ("Low", "Moderate", "High", "Urgent")
        assert r.reasons
        for label in r.source_labels:
            assert label in (
                "patient_reported",
                "wearable_measured",
                "app_calculated",
                "model_estimated",
                "simulated",
            )


# ---- Low --------------------------------------------------------------------


def test_low_persona_everything_calm():
    a = assess_risks(make_profile(), make_features(), make_apnea("Low"))
    assert a.urgent_override is False
    assert all(r.tier == "Low" for r in a.risks), [(r.risk_id, r.tier) for r in a.risks]


# ---- Moderate ---------------------------------------------------------------


def test_moderate_persona_one_group_in_the_moderate_band():
    # Apnea Moderate seeds 2.5 into the sleep group; one SpO2 dip adds a little more.
    a = assess_risks(
        make_profile(),
        make_features(z={"spo2_pct": -1.5}),
        make_apnea("Moderate"),
    )
    sdb = get_risk(a, "sleep_disordered_breathing")
    assert sdb.tier == "Moderate", [(r.risk_id, r.tier) for r in a.risks]
    assert any("SpO2" in reason for reason in sdb.reasons)
    assert "wearable_measured" in sdb.source_labels
    assert a.urgent_override is False


# ---- High -------------------------------------------------------------------


def test_high_persona_apnea_high_plus_strong_signals():
    a = assess_risks(
        make_profile(conditions=["Obstructive sleep apnea"]),
        make_features(z={"spo2_pct": -3.5, "respiratory_rate_rpm": 3.0, "disturbance_count": 3.0}),
        make_apnea("High"),
    )
    sdb = get_risk(a, "sleep_disordered_breathing")
    assert sdb.tier == "High", [(r.risk_id, r.tier) for r in a.risks]
    assert a.urgent_override is False


def test_no_single_signal_dominates_cap_is_enforced():
    # One absurd deviation must not alone push a group to High (per-signal cap).
    a = assess_risks(
        make_profile(),
        make_features(z={"resting_heart_rate_bpm": 50.0}),  # cardiovascular, huge
        make_apnea("Low"),
    )
    cv = get_risk(a, "cardiovascular")
    # capped: one signal maxes at max_points_per_signal (3.0) -> Moderate band, not High
    assert cv.tier == "Moderate", (cv.tier, cv.reasons)


# ---- Urgent -----------------------------------------------------------------


def test_urgent_persona_red_flag_sets_override_and_911():
    a = assess_risks(
        make_profile(red_flags=["chest pain", "fainting"]),
        make_features(),
        make_apnea("Low"),
    )
    assert a.urgent_override is True
    assert a.urgent_reasons and "911" in a.urgent_reasons[0]
    cv = get_risk(a, "cardiovascular")
    assert cv.tier == "Urgent"
    assert any("URGENT" in reason for reason in cv.reasons)


def test_urgent_respiratory_red_flag_routes_to_respiratory():
    a = assess_risks(
        make_profile(red_flags=["severe shortness of breath"]),
        make_features(),
        make_apnea("Low"),
    )
    assert a.urgent_override is True
    assert get_risk(a, "respiratory").tier == "Urgent"


# ---- Travel: altitude night suppressed --------------------------------------


def test_altitude_night_flags_at_home_but_is_suppressed_under_travel_context():
    # The SAME SpO2 dip: at home it raises the sleep group; under an altitude
    # context flag the relaxed threshold suppresses it and the reason says so.
    z = {"spo2_pct": -2.0}

    at_home = assess_risks(make_profile(), make_features(z=z), make_apnea("Low"))
    sdb_home = get_risk(at_home, "sleep_disordered_breathing")

    traveling = assess_risks(
        make_profile(),
        make_features(z=z, flags=["altitude"]),
        make_apnea("Low"),
    )
    sdb_travel = get_risk(traveling, "sleep_disordered_breathing")
    resp_travel = get_risk(traveling, "respiratory")

    # At home the dip counts (tier rises above Low).
    assert sdb_home.tier != "Low"
    assert any("SpO2" in r for r in sdb_home.reasons)

    # Traveling the dip is suppressed: sleep group falls back to Low.
    assert sdb_travel.tier == "Low", (sdb_travel.tier, sdb_travel.reasons)
    # and the SpO2 dip is not counted as a worrying reason in the travel case
    assert not any("SpO2 is" in r for r in sdb_travel.reasons)
    # travel wording appears somewhere the softened SpO2 signal would have been
    # (respiratory also watches SpO2); neither group should over-flag SpO2.
    assert resp_travel.tier == "Low"


def test_travel_only_relaxes_the_affected_signal_not_others():
    # A big resting-HR jump (cardiovascular) is NOT an altitude signal, so an
    # altitude flag must not suppress it.
    a = assess_risks(
        make_profile(),
        make_features(z={"resting_heart_rate_bpm": 3.0}, flags=["altitude"]),
        make_apnea("Low"),
    )
    assert get_risk(a, "cardiovascular").tier != "Low"


def test_large_dip_persists_even_when_traveling():
    # Travel relaxes the threshold, it does not switch the signal off: a dip far
    # past the relaxed threshold still counts, with the travel caveat in the text.
    a = assess_risks(
        make_profile(),
        make_features(z={"spo2_pct": -4.0}, flags=["altitude"]),
        make_apnea("Low"),
    )
    sdb = get_risk(a, "sleep_disordered_breathing")
    assert any("altitude you're at" in r for r in sdb.reasons)


# ---- Menopause / perimenopause (6th group) ----------------------------------


def test_menopause_fires_on_warm_disturbed_nights_with_cycle_marker():
    # Sleep efficiency down + disturbances up, NO SpO2 dip / NO raised RR, AND a
    # cycle-disruption marker present -> the warm/disturbed pattern is attributed
    # to menopause. (The marker is the signal the gate now requires.)
    a = assess_risks(
        make_profile(),
        make_features(
            z={"sleep_efficiency_pct": -3.0, "disturbance_count": 3.5},
            flags=["cycle:irregular"],
        ),
        make_apnea("Low"),
    )
    meno = get_risk(a, "menopause")
    assert meno.tier in ("Moderate", "High"), [(r.risk_id, r.tier) for r in a.risks]
    assert "gynecology" in meno.suggested_specialty.lower() or \
        "endocrin" in meno.suggested_specialty.lower()
    assert a.urgent_override is False


def test_menopause_does_not_fire_without_cycle_signal():
    # The SAME warm/disturbed signals but NO cycle marker and NO reported
    # peri/menopause condition -> non-specific, so menopause stays Low.
    a = assess_risks(
        make_profile(),
        make_features(z={"sleep_efficiency_pct": -3.0, "disturbance_count": 3.5}),
        make_apnea("Low"),
    )
    meno = get_risk(a, "menopause")
    assert meno.tier == "Low", (meno.tier, meno.reasons)
    assert any("cycle disruption" in r.lower() for r in meno.reasons)


def test_menopause_never_fires_for_male_even_with_cycle_marker_and_signals():
    # Male sex is an absolute gate: even with a cycle marker, reported conditions
    # and warm/disturbed signals, the menopause group is EXCLUDED from the result
    # entirely -- not scored, not listed, not a zeroed row (a "Menopause: Low"
    # row would wrongly imply the question was askable for a male).
    a = assess_risks(
        ProfileInput(
            sex="male",
            conditions=["hot flashes", "irregular periods"],
        ),
        make_features(
            z={"sleep_efficiency_pct": -3.0, "disturbance_count": 3.5},
            flags=["cycle:irregular"],
        ),
        make_apnea("Low"),
    )
    assert "menopause" not in {r.risk_id for r in a.risks}, [r.risk_id for r in a.risks]


def test_menopause_fires_for_unknown_sex_with_cycle_marker():
    # Unknown / None sex must still be ALLOWED (demo fixtures carry a neutral
    # all-None profile), so a cycle marker + signals still flags menopause.
    a = assess_risks(
        ProfileInput(sex=None),
        make_features(
            z={"sleep_efficiency_pct": -3.0, "disturbance_count": 3.5},
            flags=["cycle:irregular"],
        ),
        make_apnea("Low"),
    )
    assert get_risk(a, "menopause").tier in ("Moderate", "High")


def test_menopause_suppressed_when_signals_fit_apnea_breathing_pattern():
    # The SAME disturbed-sleep signals WITH a cycle marker (so the sex/cycle gate
    # passes), but now with an SpO2 dip -> the pattern better fits sleep-
    # disordered breathing, so menopause does NOT fire.
    a = assess_risks(
        make_profile(),
        make_features(
            z={"sleep_efficiency_pct": -3.0, "disturbance_count": 3.5, "spo2_pct": -3.0},
            flags=["cycle:irregular"],
        ),
        make_apnea("Moderate"),
    )
    meno = get_risk(a, "menopause")
    assert meno.tier == "Low", (meno.tier, meno.reasons)
    assert any("breathing pattern" in r for r in meno.reasons)
    # and the breathing group does register it
    assert get_risk(a, "sleep_disordered_breathing").tier in ("Moderate", "High")


def test_menopause_reported_condition_fires_even_without_temp_signal():
    # A reported peri/menopause symptom counts on its own, regardless of the
    # apnea-signature gate.
    a = assess_risks(
        make_profile(conditions=["hot flashes", "irregular periods"]),
        make_features(),
        make_apnea("Low"),
    )
    meno = get_risk(a, "menopause")
    assert meno.tier in ("Moderate", "High"), (meno.tier, meno.reasons)
    assert "patient_reported" in meno.source_labels


def test_menopause_condition_counts_even_with_apnea_signature():
    # Reported symptoms bypass the gate: even with an SpO2 dip present, a
    # reported hot-flashes history still attributes points to menopause.
    a = assess_risks(
        make_profile(conditions=["perimenopause"]),
        make_features(z={"spo2_pct": -3.0}),
        make_apnea("Moderate"),
    )
    meno = get_risk(a, "menopause")
    assert meno.tier in ("Moderate", "High"), (meno.tier, meno.reasons)


def test_menopause_calm_person_stays_low():
    a = assess_risks(make_profile(), make_features(), make_apnea("Low"))
    assert get_risk(a, "menopause").tier == "Low"
