"""Tests for the apnea screening gradient-boosted-tree pipeline (ml/training/train_apnea_gbt.py).

Real-data tests skip cleanly when the open datasets have not been downloaded; the artifact/metrics
tests skip until `python ml/training/train_apnea_gbt.py` has been run. In CI the training step runs
first, so all of them execute.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))  # repo root -> `ml.training....` importable
sys.path.insert(0, str(REPO / "ml" / "training"))  # also importable as bare modules

APNEA_RAW = REPO / "ml" / "data" / "raw" / "apnea"
UCD_RAW = REPO / "ml" / "data" / "raw" / "ucddb"
MODEL_PKL = REPO / "ml" / "models" / "apnea_gbt_v1.pkl"
METRICS_JSON = REPO / "ml" / "models" / "apnea_gbt_v1_metrics.json"
METRICS_MD = REPO / "ml" / "models" / "apnea_gbt_v1_metrics.md"

_HAS_APNEA = all((APNEA_RAW / f"a01.{e}").exists() for e in ("hea", "dat", "apn"))
_HAS_UCD = (UCD_RAW / "ucddb002.rec").exists() and (UCD_RAW / "ucddb002_respevt.txt").exists()


# ---- feature extraction runs on at least one real record ------------------------------------
@pytest.mark.skipif(not _HAS_APNEA, reason="Apnea-ECG record a01 not downloaded")
def test_feature_extraction_apnea_ecg_real_record():
    from ml.training.features_wearable import FEATURE_COLUMNS, extract_apnea_ecg_record

    df = extract_apnea_ecg_record(APNEA_RAW, "a01")
    assert len(df) > 100  # ~8h of minutes
    assert set(FEATURE_COLUMNS).issubset(df.columns)
    assert set(df["label"].unique()).issubset({0, 1})
    hr = df["hr_mean_bpm"].dropna()
    assert len(hr) > 50 and (hr.between(30, 160)).mean() > 0.9  # physiologic HR
    # a01 is a severe-apnea night: most minutes are apnea-labelled.
    assert df["label"].mean() > 0.5


@pytest.mark.skipif(not _HAS_UCD, reason="UCD record ucddb002 not downloaded")
def test_feature_extraction_ucd_real_record_has_spo2():
    from ml.training.features_wearable import extract_ucd_record

    df = extract_ucd_record(UCD_RAW, "ucddb002")
    assert len(df) > 100
    spo2 = df["spo2_mean_pct"].dropna()
    assert len(spo2) > 50 and (spo2.between(60, 100)).mean() > 0.9
    assert set(df["label"].unique()).issubset({0, 1})
    assert df["label"].sum() > 0  # has labelled apnea/hypopnoea minutes


def test_truncated_ucd_records_are_skipped_not_crashed():
    """available_ucd must silently drop an unreadable/truncated EDF instead of raising."""
    from ml.training.features_wearable import available_ucd

    if not UCD_RAW.exists():
        pytest.skip("UCD not downloaded")
    usable = available_ucd(UCD_RAW)
    assert isinstance(usable, list)
    for name in usable:  # every returned record must actually open
        import pyedflib

        f = pyedflib.EdfReader(str(UCD_RAW / f"{name}.rec"))
        f.close()


# ---- training refuses synthetic data --------------------------------------------------------
def test_training_rejects_synthetic_input():
    from ml.training.train_apnea_gbt import _assert_real

    _assert_real(pd.DataFrame({"dataset": ["apnea-ecg"], "label": [1]}))  # real: fine
    with pytest.raises(ValueError):
        _assert_real(pd.DataFrame({"dataset": ["synthetic"], "label": [1]}))


# ---- the model fits and predicts (small synthetic-shaped smoke, no real data needed) --------
def test_model_fits_and_predicts_probabilities():
    from ml.training.train_apnea_gbt import RUNTIME_FEATURES, _fit, _make_model

    rng = np.random.default_rng(0)
    n = 300
    X = rng.normal(size=(n, len(RUNTIME_FEATURES)))
    X[rng.random(X.shape) < 0.3] = np.nan  # missing cells, like the pooled cohorts
    y = (np.nan_to_num(X[:, 0]) + rng.normal(0, 0.5, n) > 0).astype(int)
    model = _fit(_make_model(), X, y)
    p = model.predict_proba(X)[:, 1]
    assert p.shape == (n,) and ((p >= 0) & (p <= 1)).all()


# ---- the trained artifact loads and predicts ------------------------------------------------
@pytest.mark.skipif(not MODEL_PKL.exists(), reason="run ml/training/train_apnea_gbt.py first")
def test_trained_artifact_loads_and_predicts():
    import joblib

    bundle = joblib.load(MODEL_PKL)
    assert bundle["model_version"] == "apnea-gbt-v1"
    assert bundle["probability_calibrated"] is False  # honesty: never shown as a calibrated %
    feats = bundle["features"]
    model = bundle["model"]
    row = np.full((1, len(feats)), np.nan)  # an all-missing night must still predict, not crash
    p = model.predict_proba(row)[0, 1]
    assert 0.0 <= p <= 1.0


# ---- the metrics card exists with cross-validated sens/spec/AUROC + the train/test gap -------
@pytest.mark.skipif(not METRICS_JSON.exists(), reason="run ml/training/train_apnea_gbt.py first")
def test_metrics_card_has_crossvalidated_sens_spec_auroc_and_gap():
    m = json.loads(METRICS_JSON.read_text())
    primary = m["primary_ucd_full_features"]
    for key in ("cv_auroc", "cv_sensitivity", "cv_specificity", "train_auroc", "train_minus_cv_auroc_gap"):
        assert key in primary and primary[key] is not None
    assert "leave-one-record-out" in primary["validation"]
    assert 0.0 <= primary["cv_sensitivity"] <= 1.0
    assert 0.0 <= primary["cv_specificity"] <= 1.0
    assert 0.0 <= primary["cv_auroc"] <= 1.0
    # the gap must equal train - CV (overfitting is reported, not hidden)
    assert primary["train_minus_cv_auroc_gap"] == pytest.approx(primary["train_auroc"] - primary["cv_auroc"], abs=1e-3)
    # per-record held-out breakdown present so no single night hides in the pool
    assert primary["per_record_heldout"]


@pytest.mark.skipif(not METRICS_MD.exists(), reason="run ml/training/train_apnea_gbt.py first")
def test_metrics_card_states_honest_limits():
    text = METRICS_MD.read_text().lower()
    for phrase in ("screening", "not a diagnosis", "whoop", "not calibrated", "leave-one-record-out"):
        assert phrase in text
    # must disclose it is NOT trained on WHOOP data and the sample is small
    assert "not" in text and "whoop" in text
    assert "small" in text or "wide" in text
