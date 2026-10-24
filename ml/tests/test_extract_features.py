"""Tests for the Apnea-ECG feature extraction (real data, skipped when not downloaded)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))  # repo root, so `ml.training` is importable

APNEA_RAW = REPO / "ml" / "data" / "raw" / "apnea-ecg"


@pytest.mark.skipif(
    not all((APNEA_RAW / f"a01.{ext}").exists() for ext in ("hea", "apn", "qrs")),
    reason="Apnea-ECG record a01 not downloaded",
)
def test_extract_features_on_one_record():
    from ml.training.extract_features import extract_record

    row = extract_record(APNEA_RAW, "a01")
    assert row["person_id"] == "a01"
    assert row["group"] == "a" and row["label"] == 1
    assert 5 <= row["recording_hours"] <= 12
    assert 40 < row["resting_hr_bpm"] <= row["mean_hr_bpm"] < 120
    assert 5 < row["hrv_rmssd_ms"] < 150
    assert 0.5 < row["valid_rr_fraction"] <= 1.0
    assert 0.0 <= row["apnea_minute_fraction"] <= 1.0
