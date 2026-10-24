"""Train and validate the heart-rate/HRV apnea screening model.

Two models are trained and validated the same way:
  * runtime model: resting heart rate and RMSSD only, the two signals a wrist wearable also reports.
    Saved as plain coefficients in JSON so the backend needs no scikit-learn.
  * ECG five-feature model: kept for comparison only, not applicable to wearable data.

Trains on ml/data/processed/apnea_ecg_nights.csv only (real Apnea-ECG recordings, learning
and test sets). Never reads or trains on synthetic data. Borderline (class b) recordings
are excluded.

Validation is leave-one-subject-out. The 70 Apnea-ECG recordings come from 32 people, so
all recordings of one person are held out together (subject_id, inferred from identical age,
sex, height and weight). AUROC comes from the pooled held-out predictions, with a bootstrap
95% confidence interval that resamples subjects, not recordings.

Usage: python ml/training/train_apnea_model.py
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ECG_FEATURES = ["mean_hr_bpm", "resting_hr_bpm", "hrv_rmssd_ms", "sdnn_ms", "hr_minute_sd_bpm"]
WEARABLE_FEATURES = ["resting_hr_bpm", "hrv_rmssd_ms"]
CUTOFF = 0.5  # fixed in advance (balanced class weights); never tuned on the validation predictions
RUNTIME_MODEL_VERSION = "apnea-hr-rmssd-v1"
DATA = Path("ml/data/processed/apnea_ecg_nights.csv")
ECG_MODEL_PATH = Path("ml/models/apnea_hr_hrv.joblib")  # gitignored, comparison only
RUNTIME_MODEL_PATH = Path("backend/app/ml/apnea_resting_hr_rmssd.json")
METRICS_PATH = Path("backend/app/ml/metrics.json")
N_BOOT = 2000
SEED = 0

RUNTIME_LIMITATIONS = (
    "1) Domain shift: trained on clinical ECG recordings from the PhysioNet Apnea-ECG database "
    "(32 people in a sleep lab) and applied to wrist-wearable nightly summaries. Accuracy on WHOOP "
    "data is not claimed and has not been measured; WHOOP's resting heart rate and HRV are not "
    "computed the same way as the ECG features used here. "
    "2) The labels contrast recordings with 100 or more apnea minutes against recordings with fewer "
    "than 5, and borderline recordings were excluded. That is easier than screening a general "
    "population, so these numbers are optimistic for real use. "
    "3) Subject grouping for validation was inferred from matching age, sex, height and weight, not "
    "from a published subject key. "
    "4) Output probabilities are not calibrated and must not be shown as a percentage. "
    "The sample is small and the confidence interval is wide. "
    "WakeSafe is a screening aid, not a diagnosis. Results come from wearable-style data and "
    "self-reported history, and must be confirmed by a clinician."
)

ECG_LIMITATIONS = (
    "Not applicable to wearable data: it needs ECG-derived features (mean heart rate, SDNN, "
    "minute-to-minute heart-rate spread) that a wrist device does not report. Kept only to show "
    "how much the two-feature runtime model gives up. The runtime limitations also apply."
)


def make_model() -> object:
    return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000))


def assert_real_data(df: pd.DataFrame, path: Path) -> None:
    """Refuse synthetic input: training and evaluation use real sleep-study recordings only."""
    first_line = path.read_text().splitlines()[0] if path.exists() else ""
    flagged = "is_synthetic" in df.columns and df["is_synthetic"].astype(bool).any()
    if flagged or "SYNTHETIC" in first_line.upper() or "synthetic" in df.get("source", pd.Series(dtype=str)).astype(str).values:
        raise ValueError(f"{path} looks synthetic; training and evaluation accept real recordings only")


def bootstrap_auroc_ci(
    y: np.ndarray, p: np.ndarray, groups: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED
) -> tuple[float, float]:
    """Percentile bootstrap that resamples whole groups (subjects) with replacement."""
    rng = np.random.default_rng(seed)
    members = {g: np.flatnonzero(groups == g) for g in np.unique(groups)}
    keys = list(members)
    stats = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(keys), len(keys))
        idx = np.concatenate([members[keys[i]] for i in pick])
        if len(np.unique(y[idx])) < 2:
            continue
        stats.append(roc_auc_score(y[idx], p[idx]))
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return float(lo), float(hi)


def evaluate(df: pd.DataFrame, group_col: str, features: list[str]) -> dict:
    """Leave-one-group-out validation; returns pooled held-out AUROC with a group bootstrap CI."""
    X, y, groups = df[features].to_numpy(), df["label"].astype(int).to_numpy(), df[group_col].to_numpy()
    oof = np.zeros(len(df))
    for train, test in LeaveOneGroupOut().split(X, y, groups):
        oof[test] = make_model().fit(X[train], y[train]).predict_proba(X[test])[:, 1]
    lo, hi = bootstrap_auroc_ci(y, oof, groups)
    pred = oof >= CUTOFF
    return {
        "n_recordings": int(len(df)),
        "n_groups": int(len(np.unique(groups))),
        "n_apnea": int((y == 1).sum()),
        "n_control": int((y == 0).sum()),
        "auroc": round(float(roc_auc_score(y, oof)), 3),
        "auroc_ci95": [round(lo, 3), round(hi, 3)],
        "cutoff": CUTOFF,
        "sensitivity_at_cutoff": round(float(pred[y == 1].mean()), 3),
        "specificity_at_cutoff": round(float((~pred[y == 0]).mean()), 3),
    }


def fit_full(df: pd.DataFrame, features: list[str]) -> object:
    return make_model().fit(df[features].to_numpy(), df["label"].astype(int).to_numpy())


def runtime_artifact(model: object, features: list[str], ev: dict) -> dict:
    """Plain-number description of the fitted pipeline: standardize, then logistic regression."""
    scaler, lr = model[0], model[-1]
    return {
        "model_version": RUNTIME_MODEL_VERSION,
        "kind": "standardize_then_logistic_regression",
        "features": features,
        "units": {"resting_hr_bpm": "beats per minute", "hrv_rmssd_ms": "milliseconds"},
        "scaler_mean": [float(v) for v in scaler.mean_],
        "scaler_scale": [float(v) for v in scaler.scale_],
        "coef": [float(v) for v in lr.coef_[0]],
        "intercept": float(lr.intercept_[0]),
        "cutoff": CUTOFF,
        "probability_calibrated": False,
        "trained_on": "PhysioNet Apnea-ECG 1.0.0 real recordings only",
        "n_recordings": ev["n_recordings"],
        "n_subjects": ev["n_groups"],
        "validation_auroc": ev["auroc"],
        "validation_auroc_ci95": ev["auroc_ci95"],
        "limitations": RUNTIME_LIMITATIONS,
    }


def summarize(ev: dict) -> dict:
    out = dict(ev)
    out["n_subjects"] = out.pop("n_groups")
    return out


def main() -> None:
    df = pd.read_csv(DATA)
    assert_real_data(df, DATA)
    n_excluded = int(df["label"].isna().sum())
    df = df.dropna(subset=["label"]).reset_index(drop=True)

    runtime_eval = evaluate(df, "subject_id", WEARABLE_FEATURES)
    ecg_eval = evaluate(df, "subject_id", ECG_FEATURES)

    runtime_model = fit_full(df, WEARABLE_FEATURES)
    ecg_model = fit_full(df, ECG_FEATURES)
    RUNTIME_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_MODEL_PATH.write_text(json.dumps(runtime_artifact(runtime_model, WEARABLE_FEATURES, runtime_eval), indent=2) + "\n")
    ECG_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": ecg_model, "features": ECG_FEATURES}, ECG_MODEL_PATH)

    def coefs(model: object, features: list[str]) -> dict:
        return {k: round(float(c), 3) for k, c in zip(features, model[-1].coef_[0])}

    metrics = {
        "model": "StandardScaler + LogisticRegression(C=1.0, class_weight=balanced), resting heart rate and RMSSD",
        "model_version": RUNTIME_MODEL_VERSION,
        "dataset": "PhysioNet Apnea-ECG 1.0.0, learning and test sets (real recordings only)",
        "validation": "leave-one-subject-out; all recordings of one person are held out together",
        "subject_grouping": "inferred from identical age, sex, height and weight in additional-information.txt",
        "class_definition": "apnea minutes >= 100 is apnea, < 5 is control, otherwise borderline (excluded)",
        **summarize(runtime_eval),
        "n_borderline_excluded": n_excluded,
        "ci_method": f"percentile bootstrap resampling subjects, {N_BOOT} resamples, seed {SEED}",
        "cutoff_note": "Cutoff 0.5 was fixed in advance, not tuned on the validation predictions.",
        "features": WEARABLE_FEATURES,
        "standardized_coefficients": coefs(runtime_model, WEARABLE_FEATURES),
        "runtime_artifact": "backend/app/ml/apnea_resting_hr_rmssd.json",
        "limitations": RUNTIME_LIMITATIONS,
        "ecg_five_feature_model": {
            "applicability": "not applicable to wearable data",
            **summarize(ecg_eval),
            "features": ECG_FEATURES,
            "standardized_coefficients": coefs(ecg_model, ECG_FEATURES),
            "limitations": ECG_LIMITATIONS,
        },
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps({k: v for k, v in metrics.items() if k != "limitations"}, indent=2))


if __name__ == "__main__":
    main()
