"""Tests for Person A modules. They build their own in-memory data and do not read synthetic_data."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/, so `app` is importable

from app.services.screening.features import baseline_zscores
from app.services.screening.model import score_stopbang

NO = dict(
    snoring=False,
    tired=False,
    observed_apnea=False,
    hypertension=False,
    bmi=25.0,
    age=40,
    neck_cm=35.0,
    male=False,
)


def stopbang(**overrides):
    return score_stopbang(**{**NO, **overrides})


def make_nights(n: int = 30, calibrating: int = 3, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=n, freq="D"),
            "spo2_percentage": rng.normal(96.0, 0.5, n),
            "respiratory_rate": rng.normal(14.5, 0.4, n),
            "resting_heart_rate": rng.normal(58.0, 1.5, n),
            "hrv_rmssd_milli": rng.normal(55.0, 6.0, n),
            "disturbance_count": rng.normal(8.0, 2.0, n),
            "sleep_efficiency_percentage": rng.normal(90.0, 2.0, n),
        }
    )
    df["user_calibrating"] = False
    df.loc[: calibrating - 1, "user_calibrating"] = True
    return df


# STOP-Bang


def test_all_no_is_low():
    r = stopbang()
    assert r.score == 0
    assert r.tier == "Low"
    assert not r.upgraded


def test_all_yes_is_high():
    r = stopbang(
        snoring=True,
        tired=True,
        observed_apnea=True,
        hypertension=True,
        bmi=40.0,
        age=60,
        neck_cm=45.0,
        male=True,
    )
    assert r.score == 8
    assert r.tier == "High"
    assert r.stop_items == 4


def test_bands():
    low = stopbang(snoring=True, hypertension=True)
    assert (low.score, low.tier) == (2, "Low")
    three = stopbang(snoring=True, hypertension=True, age=60)
    assert (three.score, three.tier) == (3, "Moderate")
    four = stopbang(snoring=True, tired=True, hypertension=True, age=60)
    assert (four.score, four.tier) == (4, "Moderate")
    assert not four.upgraded


def test_combination_rule_upgrades_moderate():
    r = stopbang(snoring=True, tired=True, male=True)
    assert r.score == 3
    assert r.tier == "High"
    assert r.upgraded is True


def test_age_is_not_an_override_item():
    r = stopbang(snoring=True, tired=True, age=60)
    assert r.score == 3
    assert r.tier == "Moderate"
    assert r.upgraded is False


def test_cutoffs_are_strictly_greater():
    assert stopbang(bmi=35.0).items["bmi_over_35"] is False
    assert stopbang(bmi=35.1).items["bmi_over_35"] is True
    assert stopbang(age=50).items["age_over_50"] is False
    assert stopbang(age=51).items["age_over_50"] is True
    assert stopbang(neck_cm=40.0).items["neck_over_40cm"] is False
    assert stopbang(neck_cm=40.5).items["neck_over_40cm"] is True


def test_unknown_bmi_and_neck_are_missing_and_count_as_no():
    r = stopbang(bmi=None, neck_cm=None)
    assert r.missing == ["bmi", "neck_cm"]
    assert r.items["bmi_over_35"] is False
    assert r.items["neck_over_40cm"] is False
    assert r.score == 0


# Personal baseline


def test_spo2_drop_gives_strongly_negative_z():
    df = make_nights()
    df.loc[df.index[-7:], "spo2_percentage"] -= 2.0
    z = baseline_zscores(df)["spo2_percentage"]["z"]
    assert z is not None and z < -3


def test_flat_series_gives_small_z():
    z = baseline_zscores(make_nights())["spo2_percentage"]["z"]
    assert z is not None and abs(z) < 2.5


def test_calibrating_nights_are_ignored():
    df = make_nights()
    df.loc[df["user_calibrating"], "spo2_percentage"] = 50.0
    entry = baseline_zscores(df)["spo2_percentage"]
    assert entry["baseline_mean"] > 90
    assert entry["z"] is not None and abs(entry["z"]) < 2.5


def test_all_nan_spo2_gives_no_z():
    df = make_nights()
    df["spo2_percentage"] = np.nan
    entry = baseline_zscores(df)["spo2_percentage"]
    assert entry["z"] is None
    assert entry["n_recent"] == 0
    assert entry["n_baseline"] == 0


def test_too_few_nights_gives_no_z():
    df = make_nights(n=8, calibrating=0)
    assert baseline_zscores(df)["spo2_percentage"]["z"] is None
