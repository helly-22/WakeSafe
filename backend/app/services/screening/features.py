"""Nightly features and personal baselines for WakeSafe (Person A).

Screening aid only. Trends against a person's own earlier
nights are more trustworthy from a wrist device than absolute values.
"""
from __future__ import annotations

import math

import pandas as pd

DEFAULT_COLUMNS = (
    "spo2_percentage",
    "respiratory_rate",
    "resting_heart_rate",
    "hrv_rmssd_milli",
    "disturbance_count",
    "sleep_efficiency_percentage",
)


def baseline_zscores(
    nights: pd.DataFrame,
    columns: tuple[str, ...] = DEFAULT_COLUMNS,
    recent_nights: int = 7,
    baseline_nights: int = 30,
    min_baseline: int = 7,
    min_recent: int = 3,
) -> dict[str, dict]:
    """Compare a person's most recent nights with their own earlier nights.

    `nights` holds one person's nights with a `date` column and the feature columns.
    Nights flagged `user_calibrating` are ignored. For each feature the result has
    the recent mean, the baseline mean and standard deviation, the z-score of the
    recent mean (None when there is too little data or no spread), and how many
    nights were used. Missing values (for example SpO2) are skipped, never filled.
    """
    df = nights.copy()
    if "user_calibrating" in df.columns:
        df = df[~df["user_calibrating"].fillna(False).astype(bool)]
    df = df.sort_values("date").reset_index(drop=True)

    recent = df.tail(recent_nights)
    earlier = df.iloc[: max(len(df) - recent_nights, 0)].tail(baseline_nights)

    result: dict[str, dict] = {}
    for col in columns:
        if col not in df.columns:
            continue
        r = recent[col].dropna()
        b = earlier[col].dropna()
        entry: dict = {
            "recent_mean": float(r.mean()) if len(r) else None,
            "baseline_mean": float(b.mean()) if len(b) else None,
            "baseline_std": float(b.std(ddof=1)) if len(b) > 1 else None,
            "n_recent": int(len(r)),
            "n_baseline": int(len(b)),
            "z": None,
        }
        enough = len(b) >= min_baseline and len(r) >= min_recent
        std = entry["baseline_std"]
        if enough and std is not None and not math.isnan(std) and std > 0:
            entry["z"] = (entry["recent_mean"] - entry["baseline_mean"]) / std
        result[col] = entry
    return result
