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


def test_derive_class_matches_dataset_definition():
    from ml.training.extract_features import derive_class

    assert derive_class(100) == "a" and derive_class(470) == "a"
    assert derive_class(99) == "b" and derive_class(5) == "b"
    assert derive_class(4) == "c" and derive_class(0) == "c"


@pytest.mark.skipif(not (APNEA_RAW / "additional-information.txt").exists(), reason="Apnea-ECG info table not downloaded")
def test_info_table_reproduces_letters_and_groups_repeat_subjects():
    from ml.training.extract_features import derive_class, load_info

    info = load_info(APNEA_RAW)
    abc = info[info.index.str[0].isin(["a", "b", "c"])]
    assert len(abc) == 35
    assert all(derive_class(r.apnea_min) == name[0] for name, r in abc.iterrows())
    assert info.loc["a07", "subject_id"] == info.loc["a16", "subject_id"] == info.loc["x01", "subject_id"]
    assert info["subject_id"].nunique() == 32


@pytest.mark.skipif(
    not all((APNEA_RAW / f"x01.{ext}").exists() for ext in ("hea", "qrs")) or not (APNEA_RAW / "additional-information.txt").exists(),
    reason="Apnea-ECG record x01 not downloaded",
)
def test_x_record_uses_info_table_labels():
    from ml.training.extract_features import extract_record

    row = extract_record(APNEA_RAW, "x01")
    assert row["label_source"] == "info_table" and row["record_set"] == "test"
    assert row["group"] == "a" and row["label"] == 1
    assert row["apnea_minutes"] == 375


def test_training_rejects_synthetic_input(tmp_path):
    import pandas as pd

    from ml.training.train_apnea_model import assert_real_data

    path = tmp_path / "nights.csv"
    path.write_text("# SYNTHETIC DATA\nperson_id,is_synthetic\nP001,True\n")
    with pytest.raises(ValueError):
        assert_real_data(pd.read_csv(path, comment="#"), path)
