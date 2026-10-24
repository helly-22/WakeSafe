"""Tests for scripts/gen_synthetic.py.

Every generated record must validate against the frozen contract NightRecord, and
the set must cover normal + apnea + cardiovascular + altitude + jet-lag, with the
travel nights carrying the data_quality_flags travel:* convention.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make scripts/ and backend/ importable.
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_DIR.parent
BACKEND = REPO_ROOT / "backend"
for p in (SCRIPTS_DIR, BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import gen_synthetic as gs  # noqa: E402
from app.models.schemas import NightRecord  # noqa: E402


@pytest.fixture(scope="module")
def personas():
    return gs.build_all()


def test_every_record_is_a_valid_nightrecord(personas):
    total = 0
    for p in personas:
        for n in p.nights:
            # build_all returns NightRecord instances already; re-validate the
            # JSON-serialised form to prove it loads cleanly against the contract.
            NightRecord.model_validate(n.model_dump(mode="json"))
            assert n.source == "synthetic"
            total += 1
    assert total > 0


def test_set_covers_all_cohorts(personas):
    ids = {p.persona_id for p in personas}
    assert ids == {
        "SYN-NORMAL",
        "SYN-APNEA",
        "SYN-MENOPAUSE",
        "SYN-CARDIO",
        "SYN-ALTITUDE",
        "SYN-JETLAG",
    }


def _by_id(personas, pid):
    return next(p for p in personas if p.persona_id == pid)


def test_normal_is_near_baseline(personas):
    p = _by_id(personas, "SYN-NORMAL")
    assert len(p.nights) >= 3
    # SpO2 healthy, no severe desaturation, no travel flags
    assert all(n.spo2_pct is not None and n.spo2_pct >= 95 for n in p.nights)
    assert p.travel_context == {}


def test_apnea_has_baseline_then_deviating_recent_window(personas):
    # The apnea persona is built as a near-normal baseline phase followed by a
    # recent apnea phase, so compute_features has earlier nights to compare the
    # recent window against (that is WHY the old 7-night persona produced empty
    # z-scores and never flagged).
    p = _by_id(personas, "SYN-APNEA")
    assert len(p.nights) >= 14  # >=7 baseline + >=7 recent
    assert p.travel_context == {}
    # The recent window desaturates, runs an elevated RR and fragmented sleep.
    recent = p.nights[7:]
    desat = [n for n in recent if n.spo2_pct is not None and n.spo2_pct < 95]
    assert len(desat) >= 3
    for n in recent:
        assert n.respiratory_rate_rpm is not None and n.respiratory_rate_rpm > 15.5
        assert n.disturbance_count is not None and n.disturbance_count > 10
    # Earlier baseline nights are near-normal (no desaturation).
    baseline = p.nights[:7]
    assert all(n.spo2_pct is not None and n.spo2_pct >= 95 for n in baseline)


def test_apnea_produces_nonempty_sizeable_z_scores(personas):
    # End-to-end proof of the BUG-1 fix: run the real feature engine and confirm
    # the deviating signals yield non-None, sizeable z-scores.
    import sys as _sys
    from pathlib import Path as _P

    _backend = _P(__file__).resolve().parents[2] / "backend"
    if str(_backend) not in _sys.path:
        _sys.path.insert(0, str(_backend))
    from app.services.screening.service import compute_features  # noqa: E402

    p = _by_id(personas, "SYN-APNEA")
    f = compute_features(p.nights)
    z = f.baseline_z_scores
    assert z.get("spo2_pct") is not None and z["spo2_pct"] < -1.0
    assert z.get("respiratory_rate_rpm") is not None and z["respiratory_rate_rpm"] > 1.0
    assert z.get("disturbance_count") is not None and z["disturbance_count"] > 1.0


def test_menopause_baseline_then_warm_disturbed_recent(personas):
    p = _by_id(personas, "SYN-MENOPAUSE")
    assert len(p.nights) >= 14
    # The menopause persona carries cycle:* context on its recent nights, and never a travel:* flag.
    flags = [f for fl in p.travel_context.values() for f in fl]
    assert flags and all(f.startswith("cycle:") for f in flags)
    recent = p.nights[7:]
    # Warm/disturbed recent nights: skin temp up, efficiency down, no SpO2 dip.
    for n in recent:
        assert n.skin_temperature_c is not None and n.skin_temperature_c > 34.0
        assert n.sleep_efficiency_pct is not None and n.sleep_efficiency_pct < 88
        assert n.spo2_pct is not None and n.spo2_pct >= 95  # NOT an apnea desaturation


def test_cardiovascular_drift_direction(personas):
    p = _by_id(personas, "SYN-CARDIO")
    hr = [n.resting_heart_rate_bpm for n in p.nights]
    hrv = [n.hrv_rmssd_ms for n in p.nights]
    # resting HR rises, HRV falls across the window
    assert hr[-1] > hr[0] + 5
    assert hrv[-1] < hrv[0] - 10


def test_altitude_is_low_spo2_but_flagged_travel(personas):
    p = _by_id(personas, "SYN-ALTITUDE")
    assert p.travel_context, "altitude persona must carry travel sidecar flags"
    # every flagged night uses the altitude convention
    for nid, flags in p.travel_context.items():
        assert any(f.startswith("travel:altitude:") and f.endswith("m") for f in flags)
    # the flagged nights are exactly the low-SpO2 ones (the suppressible signal)
    flagged = set(p.travel_context)
    low = {n.night_id for n in p.nights if n.spo2_pct is not None and n.spo2_pct < 93}
    assert flagged == low


def test_jetlag_is_disrupted_timing_but_flagged_travel(personas):
    p = _by_id(personas, "SYN-JETLAG")
    assert p.travel_context, "jet-lag persona must carry travel sidecar flags"
    for nid, flags in p.travel_context.items():
        assert any(f.startswith("travel:jetlag:") and f.endswith("h") for f in flags)
    # flagged nights have poor efficiency/consistency (the suppressible signal)
    for nid in p.travel_context:
        n = next(x for x in p.nights if x.night_id == nid)
        assert n.sleep_efficiency_pct is not None and n.sleep_efficiency_pct < 85


def test_generation_is_deterministic(personas):
    again = gs.build_all()
    dump = lambda ps: [[n.model_dump(mode="json") for n in p.nights] for p in ps]
    assert dump(personas) == dump(again)


def test_fixtures_write_and_roundtrip_through_contract(tmp_path):
    paths = gs.write_fixtures(tmp_path)
    assert paths, "write_fixtures produced no files"
    json_files = [p for p in paths if p.suffix == ".json" and p.name != "index.json"]
    assert len(json_files) == 6
    for path in json_files:
        nights, travel = gs.load_persona(path)
        assert nights
        # reloading proves the written JSON validates against NightRecord
        for n in nights:
            assert isinstance(n, NightRecord)
            assert n.source == "synthetic"
        # every context flag follows the data_quality_flags travel:* or cycle:* convention
        for flags in travel.values():
            for f in flags:
                assert f.startswith(("travel:", "cycle:"))


def test_travel_flags_only_on_altitude_and_jetlag(personas):
    flagged = {p.persona_id for p in personas if any(f.startswith("travel:") for fl in p.travel_context.values() for f in fl)}
    assert flagged == {"SYN-ALTITUDE", "SYN-JETLAG"}
