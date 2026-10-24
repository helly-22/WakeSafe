"""Train and validate the heart-rate/HRV apnea screening model.

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

FEATURES = ["mean_hr_bpm", "resting_hr_bpm", "hrv_rmssd_ms", "sdnn_ms", "hr_minute_sd_bpm"]
DATA = Path("ml/data/processed/apnea_ecg_nights.csv")
MODEL_PATH = Path("ml/models/apnea_hr_hrv.joblib")
METRICS_PATH = Path("backend/app/ml/metrics.json")
N_BOOT = 2000
SEED = 0

LIMITATIONS = (
    "Domain shift: this model was trained on clinical ECG recordings from the PhysioNet "
    "Apnea-ECG database (32 people in a sleep lab), and it is applied to "
    "wrist-wearable nightly summaries. Accuracy on WHOOP data is not claimed and has not been "
    "measured. The task validated here is separating apnea-group recordings from control-group "
    "recordings, not finding apnea in the general public. Borderline recordings were excluded. "
    "The sample is small, so the confidence interval is wide. Subjects were inferred from "
    "matching age, sex, height and weight, which may not be exact. WakeSafe is a screening aid, "
    "not a diagnosis."
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


def evaluate(df: pd.DataFrame, group_col: str) -> dict:
    """Leave-one-group-out validation; returns pooled held-out AUROC with a group bootstrap CI."""
    X, y, groups = df[FEATURES].to_numpy(), df["label"].astype(int).to_numpy(), df[group_col].to_numpy()
    oof = np.zeros(len(df))
    for train, test in LeaveOneGroupOut().split(X, y, groups):
        oof[test] = make_model().fit(X[train], y[train]).predict_proba(X[test])[:, 1]
    lo, hi = bootstrap_auroc_ci(y, oof, groups)
    pred = oof >= 0.5
    return {
        "n_recordings": int(len(df)),
        "n_groups": int(len(np.unique(groups))),
        "n_apnea": int((y == 1).sum()),
        "n_control": int((y == 0).sum()),
        "auroc": round(float(roc_auc_score(y, oof)), 3),
        "auroc_ci95": [round(lo, 3), round(hi, 3)],
        "sensitivity_at_0.5": round(float(pred[y == 1].mean()), 3),
        "specificity_at_0.5": round(float((~pred[y == 0]).mean()), 3),
    }


def main() -> None:
    df = pd.read_csv(DATA)
    assert_real_data(df, DATA)
    n_excluded = int(df["label"].isna().sum())
    df = df.dropna(subset=["label"]).reset_index(drop=True)
    learning = df[df["record_set"] == "learning"].reset_index(drop=True)

    main_eval = evaluate(df, "subject_id")
    comparison = {
        "learning_set_by_recording_previous_method": evaluate(learning, "person_id"),
        "learning_set_by_subject": evaluate(learning, "subject_id"),
        "all_usable_by_recording": evaluate(df, "person_id"),
    }

    X, y = df[FEATURES].to_numpy(), df["label"].astype(int).to_numpy()
    model = make_model().fit(X, y)
    coefs = dict(zip(FEATURES, (float(c) for c in model[-1].coef_[0])))

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": FEATURES}, MODEL_PATH)

    metrics = {
        "model": "StandardScaler + LogisticRegression(C=1.0, class_weight=balanced)",
        "dataset": "PhysioNet Apnea-ECG 1.0.0, learning and test sets (real recordings only)",
        "validation": "leave-one-subject-out; all recordings of one person are held out together",
        "subject_grouping": "inferred from identical age, sex, height and weight in additional-information.txt",
        "class_definition": "apnea minutes >= 100 is apnea, < 5 is control, otherwise borderline (excluded)",
        **main_eval,
        "n_borderline_excluded": n_excluded,
        "ci_method": f"percentile bootstrap resampling subjects, {N_BOOT} resamples, seed {SEED}",
        "comparison": comparison,
        "features": FEATURES,
        "standardized_coefficients": {k: round(v, 3) for k, v in coefs.items()},
        "limitations": LIMITATIONS,
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps({k: v for k, v in metrics.items() if k != "limitations"}, indent=2))


if __name__ == "__main__":
    main()
