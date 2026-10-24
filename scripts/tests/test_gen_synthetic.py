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


def test_set_covers_all_five_cohorts(personas):
    ids = {p.persona_id for p in personas}
    assert ids == {
        "SYN-NORMAL",
        "SYN-APNEA",
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


def test_apnea_shows_demonstrable_frequency(personas):
    p = _by_id(personas, "SYN-APNEA")
    # "N of 7 nights" must be demonstrable: several nights desaturate.
    desat = [n for n in p.nights if n.spo2_pct is not None and n.spo2_pct < 92]
    assert len(p.nights) == 7
    assert len(desat) >= 3  # 4 of 7 by construction
    # those nights also run high RR and many disturbances
    for n in desat:
        assert n.respiratory_rate_rpm is not None and n.respiratory_rate_rpm > 16
        assert n.disturbance_count is not None and n.disturbance_count > 15


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
    assert len(json_files) == 5
    for path in json_files:
        nights, travel = gs.load_persona(path)
        assert nights
        # reloading proves the written JSON validates against NightRecord
        for n in nights:
            assert isinstance(n, NightRecord)
            assert n.source == "synthetic"
        # any travel flag follows the data_quality_flags travel:* convention
        for flags in travel.values():
            for f in flags:
                assert f.startswith("travel:")


def test_travel_flags_only_on_altitude_and_jetlag(personas):
    flagged = {p.persona_id for p in personas if p.travel_context}
    assert flagged == {"SYN-ALTITUDE", "SYN-JETLAG"}
