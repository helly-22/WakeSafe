"""Tests for the rule-based apnea tier. Pure inputs only; no schemas, no data files."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/, so `app` is importable

from app.services.screening.model import load_apnea_artifact
from app.services.screening.scoring import CONFIG, TIERS, bmi_from, screen_from_values, travel_suppressions

ART = load_apnea_artifact()
BENIGN_VALUES = {"resting_heart_rate_bpm": 50.0, "hrv_rmssd_ms": 70.0}  # model score below cutoff
RISKY_VALUES = {"resting_heart_rate_bpm": 76.0, "hrv_rmssd_ms": 20.0}  # model score above cutoff
CALM = {"spo2_pct": 0.0, "respiratory_rate_rpm": 0.0, "disturbance_count": 0.0, "sleep_efficiency_pct": 0.0}

# Questionnaire answers that give each base tier (not male, no BMI or neck data, so no combination upgrade).
BASE_ANSWERS = {
    "Low": dict(snoring=False, tired=False, observed_apnea=False, hypertension=False, age=40),
    "Moderate": dict(snoring=True, tired=False, observed_apnea=False, hypertension=True, age=60),
    "High": dict(snoring=True, tired=True, observed_apnea=True, hypertension=True, age=60),
}


MODEL_COUNTS = {**CONFIG, "model_counts_toward_raise": True}


def run(base="Low", values=None, z=None, nights=14, spo2_nights=14, synthetic=False, **overrides):
    overrides.setdefault("conditions", ())
    args = dict(
        male=False,
        height_cm=None,
        weight_kg=None,
        neck_cm=None,
        values=BENIGN_VALUES if values is None else values,
        z_scores={**CALM, **(z or {})},
        nights_available=nights,
        nights_with_spo2=spo2_nights,
        artifact=ART,
        synthetic=synthetic,
        **BASE_ANSWERS[base],
    )
    args.update(overrides)
    return screen_from_values(**args)


def test_base_answers_give_the_intended_tiers():
    assert [run(b).base_tier for b in TIERS] == list(TIERS)


@pytest.mark.parametrize("base", TIERS)
def test_calm_wearable_data_never_changes_or_lowers_the_tier(base):
    d = run(base)
    assert d.tier == base and not d.raised and d.signals_fired == []


@pytest.mark.parametrize("base", TIERS)
def test_protective_looking_trends_never_lower_the_tier(base):
    # SpO2 above baseline, calmer breathing, fewer disturbances, better efficiency
    d = run(base, z={"spo2_pct": 3.0, "respiratory_rate_rpm": -3.0, "disturbance_count": -3.0, "sleep_efficiency_pct": 3.0})
    assert TIERS.index(d.tier) >= TIERS.index(base) and d.tier == base


def test_one_signal_alone_does_not_raise():
    d = run("Low", z={"spo2_pct": -3.0})
    assert d.tier == "Low" and not d.raised and d.signals_fired == ["spo2_pct"]
    assert any("needed to raise" in f for f in d.top_factors)


def test_model_is_a_supporting_factor_by_default():
    assert CONFIG["model_counts_toward_raise"] is False
    d = run("Moderate", values=RISKY_VALUES, z={"spo2_pct": -3.0})
    assert d.model_score > CONFIG["model_cutoff"] and d.signals_fired == ["spo2_pct"] and d.tier == "Moderate"
    assert any("supporting information only" in f for f in d.top_factors)


def test_model_alone_does_not_raise_even_when_counted():
    d = run("Moderate", values=RISKY_VALUES, config=MODEL_COUNTS)
    assert d.signals_fired == ["model"] and d.tier == "Moderate"


def test_two_signals_raise_one_level_with_reasons_and_numbers():
    d = run("Low", z={"spo2_pct": -2.4, "respiratory_rate_rpm": 2.3})
    assert d.tier == "Moderate" and d.raised
    assert len(d.raise_reasons) == 1
    step = d.raise_reasons[0]
    assert "Low to Moderate" in step and "SpO2 -2.4 SD" in step and "Respiratory rate +2.3 SD" in step
    assert d.top_factors[0] == step


def test_model_plus_one_trend_raises_moderate_to_high_when_counted():
    d = run("Moderate", values=RISKY_VALUES, z={"respiratory_rate_rpm": 2.5}, config=MODEL_COUNTS)
    assert d.tier == "High" and d.raised
    assert set(d.signals_fired) == {"model", "respiratory_rate_rpm"}


def test_all_signals_raise_only_one_level():
    z = {"spo2_pct": -4.0, "respiratory_rate_rpm": 4.0, "disturbance_count": 4.0, "sleep_efficiency_pct": -4.0}
    d = run("Low", values=RISKY_VALUES, z=z, config=MODEL_COUNTS)
    assert len(d.signals_fired) == 5 and d.tier == "Moderate"
    assert len(run("Low", values=RISKY_VALUES, z=z).signals_fired) == 4


def test_high_stays_high_and_says_so():
    d = run("High", values=RISKY_VALUES, z={"spo2_pct": -3.0, "respiratory_rate_rpm": 3.0})
    assert d.tier == "High" and not d.raised
    assert any("already High" in f for f in d.top_factors)


def test_z_threshold_boundary_and_direction():
    zt = CONFIG["z_threshold"]
    assert zt == 1.0
    assert run("Low", z={"spo2_pct": -zt, "respiratory_rate_rpm": zt}).tier == "Moderate"
    assert run("Low", z={"spo2_pct": -(zt - 0.01), "respiratory_rate_rpm": zt - 0.01}).tier == "Low"
    # wrong direction does not count
    assert run("Low", z={"spo2_pct": 5.0, "respiratory_rate_rpm": -5.0}).signals_fired == []
    assert CONFIG["min_signals_to_raise"] == 2


def test_missing_wearable_data_uses_questionnaire_only():
    d = run("Moderate", values={}, z={k: None for k in CALM}, nights=14, spo2_nights=0)
    assert d.tier == "Moderate" and d.model_score is None and d.signals_fired == []
    assert "questionnaire only" in d.evidence_note
    assert any("SpO2 recorded on 0" in f for f in d.top_factors)


def test_fewer_than_minimum_nights_ignores_wearable_data():
    risky_z = {"spo2_pct": -3.0, "respiratory_rate_rpm": 3.0}
    d = run("Low", values=RISKY_VALUES, z=risky_z, nights=CONFIG["min_nights"] - 1)
    assert d.tier == "Low" and d.signals_fired == [] and d.model_score is None
    assert any("Only 6 nights" in f and "at least 7" in f for f in d.top_factors)
    assert "questionnaire only" in d.evidence_note
    assert run("Low", values=RISKY_VALUES, z=risky_z, nights=CONFIG["min_nights"]).tier == "Moderate"


def test_unknown_answers_count_as_no_and_are_listed():
    d = run("Low", snoring=None, tired=None, observed_apnea=None, hypertension=None, age=None, male=None)
    assert d.tier == "Low" and d.stop_bang_score == 0
    assert any("unknown and counted as no" in f and "snoring" in f and "sex" in f for f in d.top_factors)


def test_bmi_and_combination_rule_are_explained():
    d = run("Low", snoring=True, tired=True, male=True, height_cm=170, weight_kg=110)
    # snoring, tired, BMI 38.1, male = 4 -> Moderate -> combination rule -> High
    assert d.base_tier == "High" and d.stop_bang_score == 4
    assert any("BMI 38.1" in f for f in d.top_factors)
    assert any("combination rule" in f for f in d.top_factors)
    assert bmi_from(170, 110) == pytest.approx(38.06, abs=0.01)
    assert bmi_from(None, 80) is None and bmi_from(170, 0) is None


def test_every_factor_has_a_number_and_wording_is_safe():
    cases = [
        run("Low"),
        run("Moderate", values=RISKY_VALUES, z={"spo2_pct": -3.0, "respiratory_rate_rpm": 3.0}),
        run("High", values={}, z={k: None for k in CALM}, nights=2, spo2_nights=0, synthetic=True),
        run("Low", snoring=None, age=None, male=None),
    ]
    for d in cases:
        for text in d.top_factors + [d.evidence_note] + d.raise_reasons:
            assert "%" not in text
            assert not re.search(r"diagnos|you have|you've|probability", text, re.I), text
        for factor in d.top_factors:
            assert re.search(r"\d", factor), factor


def test_model_score_is_not_exposed_as_a_percentage():
    d = run("Low", values=RISKY_VALUES)
    assert 0.0 < d.model_score < 1.0
    assert any("not a percentage" in f for f in d.top_factors)


def test_synthetic_label_and_versions():
    d = run("Low", synthetic=True)
    assert "Synthetic demonstration data" in d.evidence_note
    assert d.model_version.startswith("apnea-hr-rmssd-v1+") and "rules" in d.model_version


def test_evidence_note_prints_thresholds_and_states_the_limits():
    note = run("Low").evidence_note
    assert "unreviewed by a clinician" in note
    assert "trained on clinical ECG data" in note and "not been validated on WHOOP data" in note
    assert f"{CONFIG['z_threshold']:g} SD" in note and f"{CONFIG['model_cutoff']:g}" in note
    assert f"{CONFIG['min_signals_to_raise']} signals" in note and f"{CONFIG['min_nights']} nights" in note


def test_config_cutoff_matches_the_trained_artifact():
    assert CONFIG["model_cutoff"] == ART["cutoff"] == 0.5
    assert CONFIG["min_nights"] == 7 and CONFIG["recent_nights"] == 7


def test_trend_factors_describe_a_recent_change_not_a_condition():
    z = {"spo2_pct": -1.3, "respiratory_rate_rpm": 1.4, "disturbance_count": 1.2, "sleep_efficiency_pct": -1.1}
    d = run("Low", z=z)
    trend = [f for f in d.top_factors if "-night average" in f]
    assert len(trend) == 4
    assert "SpO2 7-night average is 1.3 SD below your earlier nights" in trend
    assert "Respiratory rate 7-night average is 1.4 SD above your earlier nights" in trend
    banned = r"diagnos|apnea|apnoea|chronic|condition|disease|disorder|syndrome|sleep-disordered|you have|\bhas\b|suffer"
    for f in trend:
        assert not re.search(banned, f, re.I), f
        assert re.search(r"\d", f)


def test_hypertension_in_conditions_counts_and_is_listed():
    d = run("Low", hypertension=None, conditions=["Asthma", "HyperTension"])
    assert d.stop_bang_score == 1
    assert any("high blood pressure (counted from the reported conditions)" in f for f in d.top_factors)
    # explicit False is overridden by the conditions list, as specified
    assert run("Low", hypertension=False, conditions=["hypertension"]).stop_bang_score == 1
    # no double counting, and no "from conditions" note when the flag is already true
    d2 = run("Low", hypertension=True, conditions=["hypertension"])
    assert d2.stop_bang_score == 1 and not any("counted from the reported conditions" in f for f in d2.top_factors)
    # unrelated conditions change nothing
    assert run("Low", hypertension=None, conditions=["asthma"]).stop_bang_score == 0


def test_signals_that_are_not_about_breathing_cannot_raise_the_tier_alone():
    # Disturbances and low sleep efficiency also follow menopause, illness and travel.
    d = run("Low", z={"disturbance_count": 3.5, "sleep_efficiency_pct": -2.8})
    assert d.tier == "Low" and not d.raised
    assert set(d.signals_fired) == {"disturbance_count", "sleep_efficiency_pct"}
    assert any("none is a breathing signal" in f and "stays Low" in f for f in d.top_factors)


def test_one_breathing_signal_plus_one_other_still_raises():
    for breathing in ({"spo2_pct": -1.5}, {"respiratory_rate_rpm": 1.5}):
        d = run("Low", z={**breathing, "disturbance_count": 1.5})
        assert d.tier == "Moderate" and d.raised and len(d.signals_fired) == 2


def test_the_breathing_requirement_is_in_the_config_and_the_evidence_note():
    assert CONFIG["breathing_signals"] == ("spo2_pct", "respiratory_rate_rpm")
    assert "at least one breathing signal (SpO2 or respiratory rate)" in run("Low").evidence_note


def test_travel_flags_map_to_the_signals_they_explain():
    assert travel_suppressions(["synthetic_data"]) == {}
    alt = travel_suppressions(["travel:altitude:2500m"])
    assert set(alt) == {"spo2_pct", "respiratory_rate_rpm"} and alt["spo2_pct"] == "altitude 2500m"
    jet = travel_suppressions(["travel:jetlag:+8h", "synthetic_data"])
    assert set(jet) == {"disturbance_count", "sleep_efficiency_pct"} and jet["sleep_efficiency_pct"] == "jetlag +8h"
    assert set(travel_suppressions(["travel:altitude:2500m", "travel:jetlag:+8h"])) == set(alt) | set(jet)
    assert travel_suppressions(["travel:inferred:flight", "travel:altitude"]) == {}  # unknown mode or no detail


def test_an_altitude_trip_does_not_raise_the_apnea_tier():
    z = {"spo2_pct": -8.0, "respiratory_rate_rpm": 2.6}
    assert run("Low", z=z).tier == "Moderate"  # without the travel context it would raise
    d = run("Low", z=z, suppressed=travel_suppressions(["travel:altitude:2500m"]))
    assert d.tier == "Low" and not d.raised and d.signals_fired == []
    assert any("SpO2" in f and "not counted because of travel (altitude 2500m)" in f for f in d.top_factors)
    assert all(re.search(r"\d", f) for f in d.top_factors)


def test_travel_only_explains_its_own_signals():
    sup = travel_suppressions(["travel:altitude:2500m"])
    d = run("Low", z={"spo2_pct": -8.0, "respiratory_rate_rpm": 2.6, "disturbance_count": 3.0, "sleep_efficiency_pct": -3.0}, suppressed=sup)
    assert set(d.signals_fired) == {"disturbance_count", "sleep_efficiency_pct"} and d.tier == "Low"  # no breathing signal left
    d2 = run("Low", z={"spo2_pct": -8.0, "disturbance_count": 3.0}, suppressed=travel_suppressions(["travel:jetlag:+8h"]))
    # Jet lag explains the disturbance change but not the SpO2 drop, so exactly one signal is left.
    assert d2.signals_fired == ["spo2_pct"] and d2.tier == "Low"
