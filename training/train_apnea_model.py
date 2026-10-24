"""Train and validate the heart-rate/HRV apnea screening model.

Trains on data/processed/apnea_ecg_nights.csv only (real Apnea-ECG recordings).
Never reads or trains on synthetic data. Borderline (group b) recordings are excluded.

Validation is leave-one-person-out. Each recording is a different person, so this
is leave-one-out over recordings. AUROC comes from the pooled held-out predictions,
with a bootstrap 95% confidence interval over recordings.

Usage: python training/train_apnea_model.py
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
DATA = Path("data/processed/apnea_ecg_nights.csv")
MODEL_PATH = Path("models/apnea_hr_hrv.joblib")
METRICS_PATH = Path("models/metrics.json")
N_BOOT = 2000
SEED = 0

LIMITATIONS = (
    "Domain shift: this model was trained on clinical ECG recordings from the PhysioNet "
    "Apnea-ECG learning set (a small number of people in a sleep lab), and it is applied to "
    "wrist-wearable nightly summaries. Accuracy on WHOOP data is not claimed and has not been "
    "measured. The task validated here is separating apnea-group recordings from control-group "
    "recordings, not finding apnea in the general public. Borderline recordings were excluded. "
    "The sample is small, so the confidence interval is wide. WakeSafe is a screening aid, "
    "not a diagnosis."
)


def make_model() -> object:
    return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000))


def bootstrap_auroc_ci(y: np.ndarray, p: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if len(np.unique(y[idx])) < 2:
            continue
        stats.append(roc_auc_score(y[idx], p[idx]))
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return float(lo), float(hi)


def main() -> None:
    df = pd.read_csv(DATA)
    n_excluded = int(df["label"].isna().sum())
    df = df.dropna(subset=["label"]).reset_index(drop=True)
    X, y, groups = df[FEATURES].to_numpy(), df["label"].astype(int).to_numpy(), df["person_id"].to_numpy()

    oof = np.zeros(len(df))
    for train, test in LeaveOneGroupOut().split(X, y, groups):
        m = make_model().fit(X[train], y[train])
        oof[test] = m.predict_proba(X[test])[:, 1]

    auroc = float(roc_auc_score(y, oof))
    lo, hi = bootstrap_auroc_ci(y, oof)
    pred = oof >= 0.5
    sens = float(pred[y == 1].mean())
    spec = float((~pred[y == 0]).mean())

    model = make_model().fit(X, y)
    coefs = dict(zip(FEATURES, (float(c) for c in model[-1].coef_[0])))

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": FEATURES}, MODEL_PATH)

    metrics = {
        "model": "StandardScaler + LogisticRegression(C=1.0, class_weight=balanced)",
        "dataset": "PhysioNet Apnea-ECG 1.0.0 learning set (real recordings only)",
        "validation": "leave-one-person-out (one recording per person)",
        "n_recordings": int(len(df)),
        "n_apnea": int((y == 1).sum()),
        "n_control": int((y == 0).sum()),
        "n_borderline_excluded": n_excluded,
        "auroc": round(auroc, 3),
        "auroc_ci95": [round(lo, 3), round(hi, 3)],
        "ci_method": f"percentile bootstrap over recordings, {N_BOOT} resamples, seed {SEED}",
        "sensitivity_at_0.5": round(sens, 3),
        "specificity_at_0.5": round(spec, 3),
        "features": FEATURES,
        "standardized_coefficients": {k: round(v, 3) for k, v in coefs.items()},
        "limitations": LIMITATIONS,
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps({k: v for k, v in metrics.items() if k != "limitations"}, indent=2))


if __name__ == "__main__":
    main()
