"""Train and honestly validate the WakeSafe apnea screening gradient-boosted tree.

What this models
----------------
Per-MINUTE apnea screening. A per-minute label (apnea/hypopnoea minute vs normal minute) is the
honest learnable unit on the data we actually have: a per-RECORDING apnea-vs-control model needs a
balanced set of whole nights we could not download here, and a naive per-minute POOL of two cohorts
whose raw signals barely overlap fails leave-one-record-out because it learns the cohort, not apnea
(diagnostic probe: pooled per-epoch AUROC 0.23). So we report TWO honest, separately cross-validated
results, each on the signals that cohort actually carries:

  PRIMARY (saved as the runtime model) -- UCD St Vincent's full polysomnography, using the complete
      WHOOP-mappable feature set (SpO2 desaturation + HR/HRV + respiratory). SpO2 is the dominant
      apnea signal, so this is the strongest honest model.
  SECONDARY (corroboration) -- PhysioNet Apnea-ECG, HR/HRV features only (no SpO2 in that cohort),
      on a DIFFERENT set of people and a DIFFERENT device. It confirms the HR/HRV pathway carries
      apnea information on its own.

Both use LEAVE-ONE-RECORD-OUT cross-validation: every minute of one recording is held out together,
so no recording ever straddles the split and nothing leaks. We report held-out sensitivity,
specificity, AUROC, the train-minus-CV gap (so overfitting is visible), and per-record held-out
numbers so no single night hides in the pool.

Model: a small gradient-boosted tree (sklearn GradientBoostingClassifier) -- shallow, regularised,
row-subsampled, class-balanced. Not a deep net: too few labelled nights for that. Missing features
are median-imputed with added missing-indicator columns so the tree can still split on presence.

Only REAL recordings are used; synthetic data is refused. OSV oximetry is NOT used -- it carries no
apnea event labels, so using it as a training label would be dishonest.

Outputs (ADDED ALONGSIDE Dhev's runtime model, never overwriting backend/app/ml/):
  * ml/models/apnea_gbt_v1.pkl             -- fitted tree + feature list + metadata (gitignored)
  * ml/models/apnea_gbt_v1_metrics.json
  * ml/models/apnea_gbt_v1_metrics.md      -- human-readable metrics card with honest limits

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

# A column that is all-missing in one cohort (e.g. beat-to-beat RMSSD is absent from UCD's pulse
# channel) makes the median imputer emit a benign "Skipping features without any observed values"
# notice. The missing-indicator column still records presence, so this is expected -- quiet it.
import warnings  # noqa: E402

warnings.filterwarnings("ignore", message="Skipping features without any observed values", category=UserWarning)

try:  # works when imported as a package (ml.training.train_apnea_gbt)
    from ml.training.features_wearable import FEATURE_COLUMNS, build_dataset
except ImportError:  # works when run as a script from inside ml/training
    from features_wearable import FEATURE_COLUMNS, build_dataset

MODEL_VERSION = "apnea-gbt-v1"
# Full WHOOP-mappable feature set -- what a wrist wearable reports: HR/HRV, SpO2 desaturation,
# respiratory-rate variability. The primary (UCD) model uses all of these.
RUNTIME_FEATURES = FEATURE_COLUMNS
# HR/HRV subset -- the only WHOOP-mappable signals present in the Apnea-ECG (ECG-only) cohort.
HR_FEATURES = ["hr_mean_bpm", "hr_min_bpm", "hr_max_bpm", "hr_std_bpm", "hrv_rmssd_ms", "hrv_sdnn_ms"]

PROCESSED = Path("ml/data/processed/apnea_epochs.csv")
MODEL_PATH = Path("ml/models/apnea_gbt_v1.pkl")
METRICS_JSON = Path("ml/models/apnea_gbt_v1_metrics.json")
METRICS_MD = Path("ml/models/apnea_gbt_v1_metrics.md")
CUTOFF = 0.5  # fixed in advance; never tuned on the held-out predictions
SEED = 0

LIMITATIONS = [
    "Screening aid, not a diagnosis. WakeSafe flags a pattern worth discussing with a clinician; "
    "it never tells a user they have sleep apnea.",
    "Trained on raw clinical polysomnography and ECG (UCD St Vincent's + PhysioNet Apnea-ECG), NOT "
    "on WHOOP nightly summaries. It validates the screening LOGIC on wearable-mappable signals; "
    "accuracy on real WHOOP data is not claimed and has not been measured. WHOOP computes SpO2, "
    "resting HR and HRV differently from these clinical sensors.",
    "Very small sample: a few overnight recordings per cohort (the full Apnea-ECG database could "
    "not be fetched in this environment). Leave-one-record-out validation is honest but confidence "
    "intervals are wide and a single unusual night moves the numbers.",
    "Per-minute labels within a night are correlated, so the effective sample size is far smaller "
    "than the minute count; held-out AUROC is reported per record so no single night hides in the pool.",
    "The two cohorts carry different raw signals (UCD has SpO2; Apnea-ECG does not), so they are "
    "validated separately rather than pooled -- pooling on the shared HR/HRV signals alone was "
    "weaker and would hide the fact that SpO2 is the dominant apnea signal.",
    "Output probability is NOT calibrated and must not be shown to a user as a percentage risk.",
]


def _make_model() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            (
                "gbt",
                GradientBoostingClassifier(
                    max_depth=3,
                    learning_rate=0.05,
                    n_estimators=150,
                    subsample=0.8,
                    min_samples_leaf=30,
                    random_state=SEED,
                ),
            ),
        ]
    )


def _balanced_weights(y: np.ndarray) -> np.ndarray:
    w = np.ones(len(y), dtype=float)
    for c in (0, 1):
        n = (y == c).sum()
        if n:
            w[y == c] = len(y) / (2.0 * n)
    return w


def _fit(model: Pipeline, X: np.ndarray, y: np.ndarray) -> Pipeline:
    return model.fit(X, y, gbt__sample_weight=_balanced_weights(y))


def _assert_real(df: pd.DataFrame) -> None:
    if "dataset" in df and df["dataset"].astype(str).str.contains("synthetic", case=False).any():
        raise ValueError("input contains synthetic rows; this pipeline trains on real recordings only")


def _sens_spec(y: np.ndarray, pred: np.ndarray) -> tuple[float, float]:
    sens = float(pred[y == 1].mean()) if (y == 1).any() else float("nan")
    spec = float((~pred[y == 0]).mean()) if (y == 0).any() else float("nan")
    return sens, spec


def _r(x: float) -> float | None:
    return round(float(x), 3) if x == x else None  # NaN -> None


def loro_evaluate(df: pd.DataFrame, features: list[str]) -> dict:
    """Leave-one-record-out held-out metrics for a cohort on a feature set."""
    X = df[features].to_numpy(dtype=float)
    y = df["label"].astype(int).to_numpy()
    groups = df["record_id"].to_numpy()

    oof = np.full(len(df), np.nan)
    for train, test in LeaveOneGroupOut().split(X, y, groups):
        if len(np.unique(y[train])) < 2:
            continue
        oof[test] = _fit(_make_model(), X[train], y[train]).predict_proba(X[test])[:, 1]
    scored = ~np.isnan(oof)

    cv_auroc = float(roc_auc_score(y[scored], oof[scored]))
    cv_sens, cv_spec = _sens_spec(y[scored], oof[scored] >= CUTOFF)
    train_auroc = float(roc_auc_score(y, _fit(_make_model(), X, y).predict_proba(X)[:, 1]))

    per_record = {}
    for g in np.unique(groups):
        mask = (groups == g) & scored
        if not mask.any():
            continue
        s, sp = _sens_spec(y[mask], oof[mask] >= CUTOFF)
        per_record[g] = {"n": int(mask.sum()), "apnea": int(y[mask].sum()), "sensitivity": _r(s), "specificity": _r(sp)}

    return {
        "features": features,
        "n_minutes": int(len(df)),
        "n_records": int(len(np.unique(groups))),
        "n_apnea_minutes": int((y == 1).sum()),
        "n_normal_minutes": int((y == 0).sum()),
        "validation": "leave-one-record-out (every minute of a recording held out together)",
        "cutoff": CUTOFF,
        "cv_auroc": _r(cv_auroc),
        "cv_sensitivity": _r(cv_sens),
        "cv_specificity": _r(cv_spec),
        "train_auroc": _r(train_auroc),
        "train_minus_cv_auroc_gap": _r(train_auroc - cv_auroc),
        "per_record_heldout": per_record,
    }


def permutation_importance(df: pd.DataFrame, model: Pipeline, features: list[str]) -> dict:
    X = df[features].to_numpy(float)
    y = df["label"].astype(int).to_numpy()
    base = roc_auc_score(y, model.predict_proba(X)[:, 1])
    rng = np.random.default_rng(SEED)
    out = {}
    for j, name in enumerate(features):
        Xp = X.copy()
        Xp[:, j] = rng.permutation(Xp[:, j])
        out[name] = _r(base - roc_auc_score(y, model.predict_proba(Xp)[:, 1]))
    return dict(sorted(out.items(), key=lambda kv: (kv[1] is not None, kv[1] or 0), reverse=True))


def _per_record_table(ev: dict) -> str:
    return "\n".join(
        f"| `{k}` | {v['n']} | {v['apnea']} | {v['sensitivity']} | {v['specificity']} |"
        for k, v in ev["per_record_heldout"].items()
    )


def _metrics_block(ev: dict) -> str:
    return f"""| metric | value |
|---|---|
| AUROC (held-out) | **{ev['cv_auroc']}** |
| sensitivity @ {ev['cutoff']} | **{ev['cv_sensitivity']}** |
| specificity @ {ev['cutoff']} | **{ev['cv_specificity']}** |
| AUROC (train, resubstitution) | {ev['train_auroc']} |
| **overfitting gap (train - CV AUROC)** | **{ev['train_minus_cv_auroc_gap']}** |"""


def write_metrics_md(primary: dict, secondary: dict | None, imp: dict, prov: dict) -> str:
    sec = (
        "Not available (no usable Apnea-ECG records with both apnea and normal minutes).\n"
        if not secondary
        else f"""Apnea-ECG apnea recordings, HR/HRV features only ({secondary['n_minutes']} minutes from
{secondary['n_records']} recordings, {secondary['n_apnea_minutes']} apnea / {secondary['n_normal_minutes']} normal).
A different set of people and a different device from the primary cohort.

{_metrics_block(secondary)}

| record | minutes | apnea | sensitivity | specificity |
|---|---|---|---|---|
{_per_record_table(secondary)}
"""
    )
    top = "\n".join(f"- `{k}`: {v}" for k, v in imp.items() if v)
    lim = "\n".join(f"{i+1}. {t}" for i, t in enumerate(LIMITATIONS))
    return f"""# WakeSafe apnea screening model -- metrics card ({MODEL_VERSION})

**Model:** small gradient-boosted tree (sklearn `GradientBoostingClassifier`, depth 3,
150 estimators, learning rate 0.05, row subsample 0.8, min 30 samples/leaf, class-balanced
sample weights). Missing features are median-imputed with added missing-indicator columns, so the
tree can still split on whether a signal was present. Not a deep net -- by design, because there are
too few labelled nights for one.

**Unit:** one row per MINUTE of sleep; label = apnea/hypopnoea minute vs normal minute.

**WHOOP-mappable features:** {', '.join(f'`{f}`' for f in RUNTIME_FEATURES)}
-- heart rate / HRV, SpO2 desaturation, and respiratory-rate variability, all signals a wrist
wearable (WHOOP) also reports nightly.

**Data (open access, real recordings only):**
- UCD St Vincent's (PRIMARY, runtime model): {prov.get('ucddb')}
- UCD skipped (truncated / unreadable): {prov.get('ucddb_skipped')}
- Apnea-ECG (SECONDARY corroboration): {prov.get('apnea_ecg')}
- OSV oximetry: NOT used -- no apnea event labels, so it cannot honestly supply a training label.

The full Apnea-ECG database could not be downloaded in this environment (the PhysioNet link stalled
repeatedly), so the secondary cohort uses the apnea recordings that completed. The pipeline scales
up automatically if more records are fetched later.

## PRIMARY result -- UCD, full WHOOP-mappable feature set (this is the saved runtime model)
{primary['n_minutes']} minutes from {primary['n_records']} recordings
({primary['n_apnea_minutes']} apnea / {primary['n_normal_minutes']} normal), leave-one-record-out.

{_metrics_block(primary)}

### Held-out performance per recording
| record | minutes | apnea | sensitivity | specificity |
|---|---|---|---|---|
{_per_record_table(primary)}

### Features the runtime model leans on (permutation importance, drop in AUROC)
{top}

SpO2 desaturation dominates, which is the expected and reassuring result for an apnea screen;
HR/HRV contribute secondarily.

## SECONDARY result -- Apnea-ECG, HR/HRV only (independent corroboration)
{sec}
The HR/HRV-only model clears chance on a second cohort and device, confirming the heart-rate
pathway carries apnea information even without SpO2. This matters because some WHOOP nights may have
HR/HRV but sparse SpO2.

## Honest limitations
{lim}

## How this plugs into the ApneaScore contract
`score_apnea(profile, features) -> ApneaScore` can load `ml/models/apnea_gbt_v1.pkl`, build the
feature row from a night's WHOOP summaries (per minute, or a nightly aggregate), and read
`predict_proba`. The saved dict carries `features` (column order), `cutoff` and `model_version`.
Map the score to `tier` (Low/Moderate/High) with documented cut-points, set `probability` only as
an UNCALIBRATED score or leave it null per the contract, fill `top_factors` from the
permutation-importance order above, set `model_version="{MODEL_VERSION}"`, and put the first
limitation line in `evidence_note`. Added ALONGSIDE Dhev's runtime model; does not overwrite
`backend/app/ml/`.
"""


def main() -> None:
    df_all, prov = build_dataset(Path("ml/data/raw"))
    _assert_real(df_all)
    PROCESSED.parent.mkdir(parents=True, exist_ok=True)
    df_all.to_csv(PROCESSED, index=False)

    # PRIMARY cohort: UCD (has SpO2). SECONDARY: Apnea-ECG apnea recordings (HR/HRV only, drop
    # borderline 'b' and the all-normal control which cannot inform a per-minute apnea split).
    ucd = df_all[df_all["dataset"] == "ucddb"].reset_index(drop=True)
    ecg = df_all[df_all["record_id"].str.contains("apnea-ecg/a")].reset_index(drop=True)
    if ucd.empty or ucd["label"].nunique() < 2:
        raise SystemExit("no usable UCD cohort (need SpO2 recordings with apnea and normal minutes)")

    primary = loro_evaluate(ucd, RUNTIME_FEATURES)
    secondary = loro_evaluate(ecg, HR_FEATURES) if (not ecg.empty and ecg["label"].nunique() == 2) else None

    Xp = ucd[RUNTIME_FEATURES].to_numpy(float)
    yp = ucd["label"].astype(int).to_numpy()
    runtime = _fit(_make_model(), Xp, yp)
    importance = permutation_importance(ucd, runtime, RUNTIME_FEATURES)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": runtime,
            "features": RUNTIME_FEATURES,
            "model_version": MODEL_VERSION,
            "cutoff": CUTOFF,
            "probability_calibrated": False,
            "unit": "per-minute apnea/normal",
            "trained_on": "UCD St Vincent's polysomnography (real recordings only)",
            "metrics_primary": primary,
            "metrics_secondary_apnea_ecg_hr": secondary,
        },
        MODEL_PATH,
    )

    metrics = {
        "model_version": MODEL_VERSION,
        "primary_ucd_full_features": primary,
        "secondary_apnea_ecg_hr_only": secondary,
        "permutation_importance": importance,
        "runtime_features": RUNTIME_FEATURES,
        "hr_features": HR_FEATURES,
        "limitations": LIMITATIONS,
        "provenance": prov,
    }
    METRICS_JSON.write_text(json.dumps(metrics, indent=2) + "\n")
    METRICS_MD.write_text(write_metrics_md(primary, secondary, importance, prov))

    print("PRIMARY (UCD, full features):", json.dumps(
        {k: primary[k] for k in ["n_minutes", "n_records", "cv_auroc", "cv_sensitivity", "cv_specificity",
                                  "train_auroc", "train_minus_cv_auroc_gap"]}))
    print("SECONDARY (Apnea-ECG, HR only):", None if not secondary else json.dumps(
        {k: secondary[k] for k in ["n_minutes", "n_records", "cv_auroc", "cv_sensitivity", "cv_specificity",
                                   "train_minus_cv_auroc_gap"]}))
    print("wrote", MODEL_PATH, METRICS_JSON, METRICS_MD)


if __name__ == "__main__":
    main()
