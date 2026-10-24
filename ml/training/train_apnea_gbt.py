"""Train and honestly validate the apnea screening gradient-boosted tree.

Model: a SMALL gradient-boosted tree (sklearn HistGradientBoostingClassifier), chosen over a deep
net on purpose -- we have a handful of labelled nights, so a big model would memorise them. The
tree also handles missing features natively, which is what lets us POOL two cohorts whose raw
signals only partly overlap (Apnea-ECG has HR/HRV, UCD has SpO2/respiratory). If xgboost or
lightgbm were present they would be interchangeable here; sklearn's native GBT is used so the
pipeline runs with no extra dependency.

Validation is LEAVE-ONE-RECORD-OUT: every epoch of one recording is held out together, so no
recording ever appears in both train and test. Mixing epochs of one night across the split would
leak and inflate every number. We report, from the pooled held-out predictions:
  * sensitivity (recall on apnea epochs) and specificity (recall on normal epochs)
  * AUROC
  * the TRAIN-vs-TEST gap (resubstitution AUROC minus cross-validated AUROC) so overfitting is
    visible rather than hidden.

Trains only on ml/data/processed/apnea_epochs.csv (real recordings). Synthetic data is refused.

Outputs (added ALONGSIDE Dhev's runtime model, never overwriting it):
  * ml/models/apnea_gbt_v1.pkl        -- the fitted tree + feature list + metadata (gitignored)
  * ml/models/apnea_gbt_v1_metrics.json
  * ml/models/apnea_gbt_v1_metrics.md -- the human-readable metrics card with honest limits

Usage: python ml/training/train_apnea_gbt.py
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import Pipeline

from features_wearable import FEATURE_COLUMNS  # noqa: E402  (same-dir import when run as a script)

MODEL_VERSION = "apnea-gbt-v1"
DATA = Path("ml/data/processed/apnea_epochs.csv")
MODEL_PATH = Path("ml/models/apnea_gbt_v1.pkl")
METRICS_JSON = Path("ml/models/apnea_gbt_v1_metrics.json")
METRICS_MD = Path("ml/models/apnea_gbt_v1_metrics.md")
CUTOFF = 0.5  # fixed in advance; never tuned on the held-out predictions
SEED = 0

LIMITATIONS = [
    "Screening aid, not a diagnosis. WakeSafe flags a pattern worth discussing with a clinician; "
    "it never tells a user they have sleep apnea.",
    "Trained on raw clinical ECG and overnight oximetry (PhysioNet Apnea-ECG + UCD St Vincent's), "
    "NOT on WHOOP nightly summaries. It validates the screening LOGIC on wearable-mappable signals; "
    "accuracy on real WHOOP data is not claimed and has not been measured.",
    "Very small sample: a handful of overnight recordings. Leave-one-record-out validation is "
    "honest but the confidence intervals are wide and a single unusual night moves the numbers.",
    "Per-epoch labels: an epoch is positive if an apnea/hypopnea event overlaps it (Apnea-ECG "
    "minute annotations; UCD respiratory-event list). Epochs within one night are correlated, so "
    "effective sample size is far smaller than the epoch count.",
    "Pooled cohorts expose different raw signals, so many feature cells are missing by design; the "
    "tree splits on missingness, which helps here but would need re-checking on WHOOP's own fields.",
    "Output probability is NOT calibrated and must not be shown to a user as a percentage risk.",
]


def _make_model() -> Pipeline:
    # Deliberately small + regularised GBT: shallow trees, strong leaf floor, row subsampling.
    # GradientBoostingClassifier (not a deep net) is the overfit-resistant choice for few nights;
    # it needs no NaN support of its own, so a median imputer WITH missing-indicator columns feeds
    # it -- the indicators let the tree still split on whether a signal was present at all, which is
    # what makes pooling two cohorts with partly-disjoint signals work.
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            (
                "gbt",
                GradientBoostingClassifier(
                    max_depth=3,
                    learning_rate=0.05,
                    n_estimators=200,
                    subsample=0.8,
                    min_samples_leaf=30,
                    random_state=SEED,
                ),
            ),
        ]
    )


def _balanced_weights(y: np.ndarray) -> np.ndarray:
    """Per-sample weights that balance the two classes (GradientBoostingClassifier has no class_weight)."""
    w = np.ones(len(y), dtype=float)
    for c in (0, 1):
        n = (y == c).sum()
        if n:
            w[y == c] = len(y) / (2.0 * n)
    return w


def _fit(model: Pipeline, X: np.ndarray, y: np.ndarray) -> Pipeline:
    return model.fit(X, y, gbt__sample_weight=_balanced_weights(y))


def _assert_real(df: pd.DataFrame, path: Path) -> None:
    head = path.read_text().splitlines()[0].upper() if path.exists() else ""
    if "SYNTHETIC" in head or ("dataset" in df and df["dataset"].astype(str).str.contains("synthetic", case=False).any()):
        raise ValueError(f"{path} looks synthetic; this pipeline trains on real recordings only")


def _sens_spec(y: np.ndarray, pred: np.ndarray) -> tuple[float, float]:
    sens = float(pred[y == 1].mean()) if (y == 1).any() else float("nan")
    spec = float((~pred[y == 0]).mean()) if (y == 0).any() else float("nan")
    return sens, spec


def evaluate(df: pd.DataFrame) -> dict:
    X = df[FEATURE_COLUMNS].to_numpy(dtype=float)
    y = df["label"].astype(int).to_numpy()
    groups = df["record_id"].to_numpy()

    # Leave-one-record-out held-out predictions.
    oof = np.full(len(df), np.nan)
    logo = LeaveOneGroupOut()
    for train, test in logo.split(X, y, groups):
        if len(np.unique(y[train])) < 2:  # a fold whose training side is one class only cannot fit
            continue
        oof[test] = _fit(_make_model(), X[train], y[train]).predict_proba(X[test])[:, 1]
    scored = ~np.isnan(oof)

    cv_auroc = float(roc_auc_score(y[scored], oof[scored]))
    cv_sens, cv_spec = _sens_spec(y[scored], oof[scored] >= CUTOFF)

    # Resubstitution (train==test) AUROC, only to EXPOSE the overfitting gap -- never reported as skill.
    full = _fit(_make_model(), X, y)
    train_auroc = float(roc_auc_score(y, full.predict_proba(X)[:, 1]))

    # Per-record held-out sensitivity/specificity so no single night can hide behind the pool.
    per_record = {}
    for g in np.unique(groups):
        mask = (groups == g) & scored
        if not mask.any():
            continue
        s, sp = _sens_spec(y[mask], oof[mask] >= CUTOFF)
        per_record[g] = {"n": int(mask.sum()), "apnea": int(y[mask].sum()), "sensitivity": _r(s), "specificity": _r(sp)}

    return {
        "n_epochs": int(len(df)),
        "n_records": int(len(np.unique(groups))),
        "n_apnea_epochs": int((y == 1).sum()),
        "n_normal_epochs": int((y == 0).sum()),
        "validation": "leave-one-record-out (every epoch of a recording held out together)",
        "cutoff": CUTOFF,
        "cv_auroc": _r(cv_auroc),
        "cv_sensitivity": _r(cv_sens),
        "cv_specificity": _r(cv_spec),
        "train_auroc": _r(train_auroc),
        "train_minus_cv_auroc_gap": _r(train_auroc - cv_auroc),
        "per_record_heldout": per_record,
    }


def _r(x: float) -> float:
    return round(float(x), 3) if x == x else None  # NaN -> None


def permutation_importance(df: pd.DataFrame, model: Pipeline) -> dict:
    """Which WHOOP-mappable features the tree leans on (drop in AUROC when a column is shuffled)."""
    X = df[FEATURE_COLUMNS].to_numpy(dtype=float)
    y = df["label"].astype(int).to_numpy()
    base = roc_auc_score(y, model.predict_proba(X)[:, 1])
    rng = np.random.default_rng(SEED)
    out = {}
    for j, name in enumerate(FEATURE_COLUMNS):
        Xp = X.copy()
        Xp[:, j] = rng.permutation(Xp[:, j])
        out[name] = _r(base - roc_auc_score(y, model.predict_proba(Xp)[:, 1]))
    return dict(sorted(out.items(), key=lambda kv: (kv[1] is not None, kv[1] or 0), reverse=True))


def write_metrics_md(ev: dict, importance: dict, prov: dict) -> str:
    top = [f"- `{k}`: {v}" for k, v in list(importance.items())[:6] if v]
    pr = [f"| `{k}` | {v['n']} | {v['apnea']} | {v['sensitivity']} | {v['specificity']} |"
          for k, v in ev["per_record_heldout"].items()]
    lim = "\n".join(f"{i+1}. {t}" for i, t in enumerate(LIMITATIONS))
    return f"""# Apnea screening model -- metrics card ({MODEL_VERSION})

**Model:** small gradient-boosted tree (sklearn `GradientBoostingClassifier`, depth 3,
200 estimators, learning rate 0.05, row subsample 0.8, min 30 samples/leaf, class-balanced
sample weights). Missing features are median-imputed with added missing-indicator columns, so the
tree can still split on whether a signal was present. Not a deep net -- by design.

**Data (open access, real recordings only):**
- Apnea-ECG: {prov.get('apnea_ecg')}
- UCD St Vincent's: {prov.get('ucddb')}
- UCD skipped (truncated / unreadable download): {prov.get('ucddb_skipped')}
- OSV oximetry set: NOT used for training -- it has no apnea event labels, so using it as a
  training label would be dishonest. It remains available for feature-extraction checks.

**Task:** per-epoch apnea/hypopnoea vs normal breathing. Epoch = {60}s.
{ev['n_epochs']} epochs from {ev['n_records']} recordings
({ev['n_apnea_epochs']} apnea / {ev['n_normal_epochs']} normal).

## Cross-validated performance (leave-one-record-out)

| metric | value |
|---|---|
| AUROC (held-out) | **{ev['cv_auroc']}** |
| sensitivity @ {ev['cutoff']} | **{ev['cv_sensitivity']}** |
| specificity @ {ev['cutoff']} | **{ev['cv_specificity']}** |
| AUROC (train, resubstitution) | {ev['train_auroc']} |
| **overfitting gap (train - CV AUROC)** | **{ev['train_minus_cv_auroc_gap']}** |

The train-minus-CV gap is reported so overfitting is visible. A small gap means the tree is not
memorising; a large gap would be the warning sign.

### Held-out performance per recording
| record | epochs | apnea | sensitivity | specificity |
|---|---|---|---|---|
{chr(10).join(pr)}

## Features the model leans on (permutation importance, drop in AUROC)
{chr(10).join(top)}

## Honest limitations
{lim}

## How this plugs into the ApneaScore contract
`score_apnea(profile, features) -> ApneaScore` can load `ml/models/apnea_gbt_v1.pkl`, build the
{len(FEATURE_COLUMNS)}-feature row from a night's WHOOP-mappable summaries, and read
`predict_proba`. Map probability to `tier` (Low/Moderate/High) with documented cut-points, set
`probability` only as an uncalibrated score (or leave null per the contract), fill `top_factors`
from the permutation-importance order above, set `model_version="{MODEL_VERSION}"`, and put the
first limitation line in `evidence_note`. This model is ADDED alongside Dhev's runtime model; it
does not overwrite `backend/app/ml/`.
"""


def main() -> None:
    from features_wearable import build_dataset

    df = pd.read_csv(DATA)
    _assert_real(df, DATA)
    _, prov = build_dataset(Path("ml/data/raw"))  # provenance for the card

    ev = evaluate(df)

    X = df[FEATURE_COLUMNS].to_numpy(dtype=float)
    y = df["label"].astype(int).to_numpy()
    full = _fit(_make_model(), X, y)
    importance = permutation_importance(df, full)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": full,
            "features": FEATURE_COLUMNS,
            "model_version": MODEL_VERSION,
            "cutoff": CUTOFF,
            "probability_calibrated": False,
            "trained_on": "PhysioNet Apnea-ECG 1.0.0 + UCD St Vincent's (real recordings only)",
            "metrics": ev,
        },
        MODEL_PATH,
    )

    metrics = {"model_version": MODEL_VERSION, **ev, "permutation_importance": importance,
               "features": FEATURE_COLUMNS, "limitations": LIMITATIONS, "provenance": prov}
    METRICS_JSON.write_text(json.dumps(metrics, indent=2) + "\n")
    METRICS_MD.write_text(write_metrics_md(ev, importance, prov))

    print(json.dumps({k: ev[k] for k in
                      ["n_epochs", "n_records", "cv_auroc", "cv_sensitivity", "cv_specificity",
                       "train_auroc", "train_minus_cv_auroc_gap"]}, indent=2))
    print("wrote", MODEL_PATH, METRICS_JSON, METRICS_MD)


if __name__ == "__main__":
    main()
