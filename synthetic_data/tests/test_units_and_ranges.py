"""Units, ranges, reconciliation, and schema of the generated tables."""

from __future__ import annotations

import pandas as pd

import generate_synthetic_whoop as gen
import validate_synthetic as val

DURATION_COLUMNS = ["total_in_bed_time_milli", *val.STAGE_COLUMNS]


def test_exact_column_names(dataset: val.Dataset) -> None:
    assert list(dataset.profiles.columns) == gen.PROFILE_COLUMNS
    assert list(dataset.recovery.columns) == gen.RECOVERY_COLUMNS
    assert list(dataset.sleep.columns) == gen.SLEEP_COLUMNS
    assert list(dataset.ground_truth.columns) == gen.GROUND_TRUTH_COLUMNS


def test_durations_are_integer_milliseconds(dataset: val.Dataset) -> None:
    s = dataset.sleep
    for col in DURATION_COLUMNS:
        assert pd.api.types.is_integer_dtype(s[col]), col
        assert (s[col] >= 0).all(), col
    hours = s["total_in_bed_time_milli"] / 3_600_000
    assert hours.between(3, 12).all()  # milliseconds, not seconds or minutes
    assert 6.5 < hours.mean() < 8.5


def test_stages_reconcile_and_efficiency_recomputes(dataset: val.Dataset) -> None:
    s = dataset.sleep
    assert (s[val.STAGE_COLUMNS].sum(axis=1) == s["total_in_bed_time_milli"]).all()
    asleep = s[val.ASLEEP_COLUMNS].sum(axis=1)
    eff = 100 * asleep / s["total_in_bed_time_milli"]
    assert ((eff - s["sleep_efficiency_percentage"]).abs() <= 1e-3).all()


def test_timestamps_and_dates_are_iso(dataset: val.Dataset) -> None:
    s = dataset.sleep
    start = pd.to_datetime(s["sleep_start"], format="%Y-%m-%dT%H:%M:%S.%fZ", utc=True)
    end = pd.to_datetime(s["sleep_end"], format="%Y-%m-%dT%H:%M:%S.%fZ", utc=True)
    span = ((end - start).dt.total_seconds() * 1000).round().astype("int64")
    assert (span == s["total_in_bed_time_milli"]).all()
    wake = pd.to_datetime(s["date"], format="%Y-%m-%d")
    assert (end.dt.tz_localize(None).dt.normalize() == wake).all()  # date is the wake-up date
    pd.to_datetime(dataset.recovery["date"], format="%Y-%m-%d")


def test_physiological_units(dataset: val.Dataset) -> None:
    r, s = dataset.recovery, dataset.sleep
    assert r["skin_temp_celsius"].dropna().between(30, 38).all()  # Celsius
    assert r["spo2_percentage"].dropna().between(85, 100).all()  # percent, not a fraction
    assert r["hrv_rmssd_milli"].between(5, 250).all()  # milliseconds, not seconds
    assert pd.api.types.is_integer_dtype(r["resting_heart_rate"])
    assert pd.api.types.is_integer_dtype(r["recovery_score"])
    assert s["respiratory_rate"].between(8, 30).all()
    assert pd.api.types.is_integer_dtype(s["sleep_performance_percentage"])
    assert pd.api.types.is_integer_dtype(s["sleep_consistency_percentage"])
    assert not s["nap"].astype(bool).any()


def test_profile_units(dataset: val.Dataset) -> None:
    p = dataset.profiles
    assert p["height_m"].between(1.4, 2.1).all()
    assert p["weight_kg"].between(35, 200).all()
    assert ((p["weight_kg"] / p["height_m"] ** 2 - p["bmi"]).abs() <= 0.06).all()
    assert p["sex"].isin(["male", "female"]).all()
    for col in ("snoring", "daytime_tiredness", "witnessed_breathing_pauses", "hypertension", "is_synthetic"):
        assert pd.api.types.is_bool_dtype(p[col]), col


def test_config_ranges_check_passes(dataset: val.Dataset, cfg: dict) -> None:
    assert val.check_ranges(dataset, cfg["validation"]["ranges"]).passed


def test_missing_data_pattern(dataset: val.Dataset, cfg: dict) -> None:
    r = dataset.recovery
    assert 0.02 < r["spo2_percentage"].isna().mean() < 0.20
    assert 0.01 < r["skin_temp_celsius"].isna().mean() < 0.12
    per_person = r.groupby("person_id")["spo2_percentage"].apply(lambda x: x.isna().mean())
    assert (per_person >= 0.2).any()  # some SpO2-sparse people
    expected_rows = len(dataset.profiles) * 30
    assert 0.9 * expected_rows < len(r) < expected_rows  # a few nights have no record at all
    assert val.check_missing(dataset, cfg).passed


def test_calibrating_first_three_or_four_nights(dataset: val.Dataset) -> None:
    r = dataset.recovery.copy()
    r["night"] = (pd.to_datetime(r["date"]) - pd.Timestamp("2026-09-01")).dt.days
    assert not r.loc[r["night"] >= 4, "user_calibrating"].any()
    assert r.loc[r["night"] < 3, "user_calibrating"].all()
