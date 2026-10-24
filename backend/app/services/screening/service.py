"""compute_features and score_apnea with the TEAM_CONTRACTS.md signatures (Person A).

Thin layer between the shared schemas and the pure functions in features.py, model.py and
scoring.py. Feature names equal NightRecord field names.

FeatureSet contents
  values              recent-window means (the last 7 nights): resting_heart_rate_bpm (bpm),
                      hrv_rmssd_ms (ms), spo2_pct (%), respiratory_rate_rpm (breaths per minute),
                      skin_temperature_c (C), disturbance_count (count), sleep_efficiency_pct (%),
                      sleep_consistency_pct (%), sleep_duration_minutes, deep_sleep_minutes,
                      rem_sleep_minutes (minutes). None when no night in the window has the reading.
  baseline_z_scores   (recent 7-night mean - mean of up to `baseline_nights` earlier nights) divided by
                      the standard deviation of those earlier nights, for resting_heart_rate_bpm,
                      hrv_rmssd_ms, spo2_pct, respiratory_rate_rpm, disturbance_count and
                      sleep_efficiency_pct. None with fewer than 7 usable nights, fewer than 7 earlier
                      nights, fewer than 3 recent readings, or no spread. Missing readings are skipped.
  window_start/end    first and last date of the nights used (recent window plus baseline nights).
  data_quality_flags  stable ids: "no_nights", "insufficient_nights" (fewer than 7),
                      "short_baseline_history" (fewer than 7 earlier nights), "spo2_unavailable",
                      "spo2_partial", "synthetic_data" (every night has source "synthetic").
"""
from __future__ import annotations

import pandas as pd

from app.models import ApneaScore, FeatureSet, NightRecord, ProfileInput

from .features import baseline_zscores
from .model import load_apnea_artifact
from .scoring import CONFIG, screen_from_values, travel_suppressions

RECENT_NIGHTS = 7
MIN_BASELINE_NIGHTS = 7
Z_FIELDS = (
    "resting_heart_rate_bpm",
    "hrv_rmssd_ms",
    "spo2_pct",
    "respiratory_rate_rpm",
    "disturbance_count",
    "sleep_efficiency_pct",
)
MEAN_FIELDS = Z_FIELDS + (
    "skin_temperature_c",
    "sleep_consistency_pct",
    "sleep_duration_minutes",
    "deep_sleep_minutes",
    "rem_sleep_minutes",
)
_ARTIFACT: dict | None = None


def _artifact() -> dict:
    global _ARTIFACT
    if _ARTIFACT is None:
        _ARTIFACT = load_apnea_artifact()
    return _ARTIFACT


def compute_features(nights: list[NightRecord], *, baseline_nights: int = 14) -> FeatureSet:
    flags: list[str] = []
    if not nights:
        return FeatureSet(
            values={f: None for f in MEAN_FIELDS},
            baseline_z_scores={f: None for f in Z_FIELDS},
            nights_available=0,
            nights_with_spo2=0,
            data_quality_flags=["no_nights", "insufficient_nights", "spo2_unavailable"],
        )

    df = pd.DataFrame([n.model_dump() for n in nights]).sort_values("date").reset_index(drop=True)
    n_total = len(df)
    n_spo2 = int(df["spo2_pct"].notna().sum())

    recent = df.tail(RECENT_NIGHTS)
    earlier = df.iloc[: max(n_total - RECENT_NIGHTS, 0)].tail(baseline_nights)
    used = pd.concat([earlier, recent])

    if n_total < RECENT_NIGHTS:
        flags.append("insufficient_nights")
        z = {f: None for f in Z_FIELDS}
    else:
        if len(earlier) < MIN_BASELINE_NIGHTS:
            flags.append("short_baseline_history")
        stats = baseline_zscores(
            df,
            columns=Z_FIELDS,
            recent_nights=RECENT_NIGHTS,
            baseline_nights=baseline_nights,
            min_baseline=MIN_BASELINE_NIGHTS,
        )
        z = {f: stats[f]["z"] for f in Z_FIELDS}

    if n_spo2 == 0:
        flags.append("spo2_unavailable")
    elif n_spo2 < n_total:
        flags.append("spo2_partial")
    if all(n.source == "synthetic" for n in nights):
        flags.append("synthetic_data")

    def mean_or_none(col: str) -> float | None:
        m = recent[col].dropna()
        return float(m.mean()) if len(m) else None

    return FeatureSet(
        values={f: mean_or_none(f) for f in MEAN_FIELDS},
        baseline_z_scores=z,
        nights_available=n_total,
        nights_with_spo2=n_spo2,
        data_quality_flags=flags,
        window_start=used["date"].min(),
        window_end=used["date"].max(),
    )


def _male(sex: str | None) -> bool | None:
    if sex is None:
        return None
    s = sex.strip().lower()
    if s in {"male", "m", "man"}:
        return True
    if s in {"female", "f", "woman"}:
        return False
    return None  # other or unrecognized answers are treated as unknown


def score_apnea(profile: ProfileInput, features: FeatureSet) -> ApneaScore:
    d = screen_from_values(
        age=profile.age,
        male=_male(profile.sex),
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        neck_cm=profile.neck_circumference_cm,
        snoring=profile.snoring,
        tired=profile.daytime_tiredness,
        observed_apnea=profile.witnessed_breathing_pauses,
        hypertension=profile.hypertension,
        conditions=profile.conditions,
        values=features.values,
        z_scores=features.baseline_z_scores,
        nights_available=features.nights_available,
        nights_with_spo2=features.nights_with_spo2,
        artifact=_artifact(),
        synthetic="synthetic_data" in features.data_quality_flags,
        config=CONFIG,
        suppressed=travel_suppressions(features.data_quality_flags),
    )
    return ApneaScore(
        tier=d.tier,  # type: ignore[arg-type]
        probability=None,
        stop_bang_score=d.stop_bang_score,
        top_factors=d.top_factors,
        model_version=d.model_version,
        evidence_note=d.evidence_note,
    )
