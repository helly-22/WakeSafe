"""Tests for compute_features, score_apnea and the full load_nights -> score flow (contract shapes)."""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))  # backend/, so `app` is importable

from app.models import ApneaScore, FeatureSet, NightRecord, ProfileInput
from app.services.screening.service import Z_FIELDS, compute_features, score_apnea
from app.services.whoop import load_nights, load_synthetic_profile

FORBIDDEN = re.compile(r"diagnos|you have|you've|probability|%", re.I)
DISCLAIMER_START = "WakeSafe is a screening aid, not a diagnosis"


def make_nights(n=24, spo2=96.0, source="synthetic", start=date(2026, 1, 1)):
    """Steady synthetic-looking nights with a little deterministic wobble."""
    out = []
    for i in range(n):
        wobble = (i % 5) - 2
        out.append(
            NightRecord(
                night_id=f"T-{i}", date=start + timedelta(days=i), source=source,
                resting_heart_rate_bpm=58.0 + wobble * 0.5, hrv_rmssd_ms=45.0 + wobble, spo2_pct=None if spo2 is None else spo2 + wobble * 0.2,
                respiratory_rate_rpm=14.5 + wobble * 0.1, disturbance_count=8 + wobble, sleep_efficiency_pct=90.0 + wobble * 0.5,
                sleep_duration_minutes=420.0, deep_sleep_minutes=60.0, rem_sleep_minutes=90.0,
            )
        )
    return out


def worsen(nights, last=7):
    """Demo-only change in the last nights: lower SpO2 and efficiency, faster breathing, more disturbances."""
    out = []
    for i, n in enumerate(nights):
        if i >= len(nights) - last:
            n = n.model_copy(update={
                "spo2_pct": n.spo2_pct - 3.0, "sleep_efficiency_pct": n.sleep_efficiency_pct - 6.0,
                "respiratory_rate_rpm": n.respiratory_rate_rpm + 1.5, "disturbance_count": n.disturbance_count + 8,
            })
        out.append(n)
    return out


def assert_safe_text(score: ApneaScore):
    for text in score.top_factors + [score.evidence_note]:
        assert not FORBIDDEN.search(text), text
        assert DISCLAIMER_START not in text  # the disclaimer is owned by the result and report layers
    for f in score.top_factors:
        assert re.search(r"\d", f), f


# compute_features


def test_features_shape_and_contents():
    nights = make_nights(24)
    f = compute_features(nights)
    FeatureSet.model_validate(f.model_dump())
    assert f.nights_available == 24 and f.nights_with_spo2 == 24
    assert set(f.baseline_z_scores) == set(Z_FIELDS) and all(isinstance(v, float) for v in f.baseline_z_scores.values())
    assert f.values["resting_heart_rate_bpm"] == pytest.approx(sum(n.resting_heart_rate_bpm for n in nights[-7:]) / 7)
    assert f.window_start == nights[-21].date and f.window_end == nights[-1].date
    assert f.data_quality_flags == ["synthetic_data"]
    assert FeatureSet.model_validate_json(f.model_dump_json()) == f


def test_z_score_is_recent_mean_minus_earlier_mean_over_earlier_sd():
    nights = worsen(make_nights(24))
    z = compute_features(nights).baseline_z_scores
    import numpy as np

    earlier = np.array([n.spo2_pct for n in nights[-21:-7]])
    recent = np.array([n.spo2_pct for n in nights[-7:]])
    assert z["spo2_pct"] == pytest.approx((recent.mean() - earlier.mean()) / earlier.std(ddof=1))
    assert z["spo2_pct"] < -1 and z["respiratory_rate_rpm"] > 1 and z["disturbance_count"] > 1 and z["sleep_efficiency_pct"] < -1


def test_baseline_nights_argument_changes_the_baseline_window():
    nights = make_nights(30)
    assert compute_features(nights, baseline_nights=14).window_start == nights[-21].date
    assert compute_features(nights, baseline_nights=21).window_start == nights[-28].date


def test_fewer_than_seven_nights_sets_a_flag_and_no_z_scores():
    f = compute_features(make_nights(6))
    assert "insufficient_nights" in f.data_quality_flags
    assert all(v is None for v in f.baseline_z_scores.values())
    assert f.nights_available == 6 and f.values["hrv_rmssd_ms"] is not None


def test_short_baseline_history_has_its_own_flag_and_no_z_scores():
    f = compute_features(make_nights(10))
    assert "short_baseline_history" in f.data_quality_flags and "insufficient_nights" not in f.data_quality_flags
    assert all(v is None for v in f.baseline_z_scores.values())


def test_no_nights_does_not_crash():
    f = compute_features([])
    FeatureSet.model_validate(f.model_dump())
    assert f.nights_available == 0 and "no_nights" in f.data_quality_flags and f.window_start is None


def test_missing_spo2_stays_missing_and_is_flagged():
    none = compute_features(make_nights(24, spo2=None))
    assert none.nights_with_spo2 == 0 and none.values["spo2_pct"] is None and none.baseline_z_scores["spo2_pct"] is None
    assert "spo2_unavailable" in none.data_quality_flags
    some = make_nights(24)
    some[3] = some[3].model_copy(update={"spo2_pct": None})
    f = compute_features(some)
    assert f.nights_with_spo2 == 23 and "spo2_partial" in f.data_quality_flags and f.baseline_z_scores["spo2_pct"] is not None


def test_unsorted_input_is_handled_and_not_mutated():
    nights = make_nights(24)
    shuffled = list(reversed(nights))
    before = [n.model_dump() for n in shuffled]
    assert compute_features(shuffled) == compute_features(nights)
    assert [n.model_dump() for n in shuffled] == before


def test_synthetic_flag_only_when_every_night_is_synthetic():
    assert "synthetic_data" not in compute_features(make_nights(24, source="csv")).data_quality_flags


# score_apnea


def low_profile(**kw):
    base = dict(age=40, sex="female", height_cm=165, weight_kg=60, neck_circumference_cm=33, snoring=False,
                daytime_tiredness=False, witnessed_breathing_pauses=False, hypertension=False)
    base.update(kw)
    return ProfileInput(**base)


def test_score_shape_and_contract_values():
    s = score_apnea(low_profile(), compute_features(make_nights(24)))
    ApneaScore.model_validate(s.model_dump())
    assert s.tier == "Low" and s.probability is None and s.stop_bang_score == 0
    assert s.model_version.startswith("apnea-hr-rmssd-v1+") and s.top_factors
    assert "Synthetic demonstration data" in s.evidence_note
    assert_safe_text(s)


def test_csv_source_is_not_labeled_synthetic():
    s = score_apnea(low_profile(), compute_features(make_nights(24, source="csv")))
    assert "Synthetic" not in s.evidence_note


def test_too_little_wearable_data_uses_the_questionnaire_and_says_why():
    p = low_profile(snoring=True, daytime_tiredness=True, hypertension=True)
    s = score_apnea(p, compute_features(make_nights(4)))
    assert s.tier == "Moderate" and s.probability is None and s.stop_bang_score == 3
    assert "Wearable data was not used because only 4 nights were available and at least 7 are needed" in s.evidence_note
    assert_safe_text(s)
    empty = score_apnea(p, compute_features([]))
    assert empty.tier == "Moderate" and "only 0 nights" in empty.evidence_note


def test_two_wearable_changes_raise_one_level_with_reasons():
    s = score_apnea(low_profile(), compute_features(worsen(make_nights(24))))
    assert s.tier == "Moderate"  # Low base raised by one level only, although four signals fired
    assert s.top_factors[0].startswith("Raised from Low to Moderate: 4 wearable signals agree")
    assert any("SpO2 7-night average is" in f and "below your earlier nights" in f for f in s.top_factors)
    assert_safe_text(s)


def test_hypertension_in_conditions_and_sex_mapping():
    s = score_apnea(low_profile(hypertension=None, conditions=["Hypertension"]), compute_features(make_nights(24)))
    assert s.stop_bang_score == 1 and any("counted from the reported conditions" in f for f in s.top_factors)
    male = score_apnea(low_profile(sex="Male"), compute_features(make_nights(24)))
    assert male.stop_bang_score == 1
    odd = score_apnea(low_profile(sex="nonbinary"), compute_features(make_nights(24)))
    assert odd.stop_bang_score == 0 and any("sex" in f and "unknown" in f for f in odd.top_factors)


def test_empty_profile_still_scores():
    s = score_apnea(ProfileInput(), compute_features(make_nights(24)))
    assert s.tier == "Low" and s.stop_bang_score == 0
    assert any("answers unknown and counted as no" in f for f in s.top_factors)


# end to end


@pytest.mark.parametrize("pid", ["P001", "P002"])
def test_end_to_end_two_demo_people(pid):
    profile = load_synthetic_profile(pid)
    nights = load_nights("synthetic", persona_id=pid)
    features = compute_features(nights)
    score = score_apnea(profile, features)
    for model, obj in ((NightRecord, nights[0]), (FeatureSet, features), (ApneaScore, score)):
        model.model_validate(obj.model_dump())
    assert features.nights_available == len(nights) >= 15 and "synthetic_data" in features.data_quality_flags
    assert score.tier in ("Low", "Moderate", "High") and score.probability is None
    assert score.stop_bang_score == 4  # both demo people answer four STOP-Bang items yes
    assert_safe_text(score)


def test_end_to_end_worsening_person_through_the_csv_path(tmp_path):
    # A made-up demo person whose last week gets worse, passed through the CSV provider.
    import pandas as pd

    rows = [
        {
            "date": n.date.isoformat(), "resting_heart_rate": n.resting_heart_rate_bpm, "hrv_rmssd_milli": n.hrv_rmssd_ms,
            "spo2_percentage": n.spo2_pct, "respiratory_rate": n.respiratory_rate_rpm, "disturbance_count": n.disturbance_count,
            "sleep_efficiency_percentage": n.sleep_efficiency_pct,
        }
        for n in worsen(make_nights(24))
    ]
    path = tmp_path / "worsening.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    nights = load_nights("csv", csv_file=str(path))
    features = compute_features(nights)
    score = score_apnea(low_profile(), features)
    assert features.baseline_z_scores["spo2_pct"] < -1 and "synthetic_data" not in features.data_quality_flags
    assert score.tier == "Moderate" and score.top_factors[0].startswith("Raised from Low to Moderate")
    assert_safe_text(score)
