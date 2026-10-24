"""Tests for the rule-based apnea tier. Pure inputs only; no schemas, no data files."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/, so `app` is importable

from app.services.screening.model import load_apnea_artifact
from app.services.screening.scoring import (
    MIN_SIGNALS_TO_RAISE,
    TIERS,
    Z_THRESHOLD,
    bmi_from,
    screen_from_values,
)

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


def run(base="Low", values=None, z=None, nights=14, spo2_nights=14, synthetic=False, **overrides):
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


def test_model_alone_does_not_raise():
    d = run("Moderate", values=RISKY_VALUES)
    assert d.signals_fired == ["model"] and d.tier == "Moderate"


def test_two_signals_raise_one_level_with_reasons_and_numbers():
    d = run("Low", z={"spo2_pct": -2.4, "respiratory_rate_rpm": 2.3})
    assert d.tier == "Moderate" and d.raised
    assert len(d.raise_reasons) == 1
    step = d.raise_reasons[0]
    assert "Low to Moderate" in step and "SpO2 -2.4 SD" in step and "Respiratory rate +2.3 SD" in step
    assert d.top_factors[0] == step


def test_model_plus_one_trend_raises_moderate_to_high():
    d = run("Moderate", values=RISKY_VALUES, z={"disturbance_count": 2.5})
    assert d.tier == "High" and d.raised
    assert set(d.signals_fired) == {"model", "disturbance_count"}


def test_all_signals_raise_only_one_level():
    z = {"spo2_pct": -4.0, "respiratory_rate_rpm": 4.0, "disturbance_count": 4.0, "sleep_efficiency_pct": -4.0}
    d = run("Low", values=RISKY_VALUES, z=z)
    assert len(d.signals_fired) == 5 and d.tier == "Moderate"


def test_high_stays_high_and_says_so():
    d = run("High", values=RISKY_VALUES, z={"spo2_pct": -3.0})
    assert d.tier == "High" and not d.raised
    assert any("already High" in f for f in d.top_factors)


def test_z_threshold_boundary_and_direction():
    assert run("Low", z={"spo2_pct": -Z_THRESHOLD, "respiratory_rate_rpm": Z_THRESHOLD}).tier == "Moderate"
    assert run("Low", z={"spo2_pct": -(Z_THRESHOLD - 0.01), "respiratory_rate_rpm": Z_THRESHOLD - 0.01}).tier == "Low"
    # wrong direction does not count
    assert run("Low", z={"spo2_pct": 5.0, "respiratory_rate_rpm": -5.0}).signals_fired == []
    assert MIN_SIGNALS_TO_RAISE == 2


def test_missing_wearable_data_uses_questionnaire_only():
    d = run("Moderate", values={}, z={k: None for k in CALM}, nights=3, spo2_nights=0)
    assert d.tier == "Moderate" and d.model_score is None and d.signals_fired == []
    assert "questionnaire only" in d.evidence_note
    assert any("3 available" in f or "3 nights" in f for f in d.top_factors)
    assert any("SpO2 recorded on 0" in f for f in d.top_factors)


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
    assert "WHOOP" in d.evidence_note and "not claimed" in d.evidence_note
