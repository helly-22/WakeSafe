"""Turn nightly tables in our WHOOP-style format into NightRecord objects (Person A).

Input columns (our nightly format, see synthetic_data/ and fixtures/nights_sample.csv):
  date, person_id (optional), user_calibrating (optional), nap (optional),
  resting_heart_rate, hrv_rmssd_milli, spo2_percentage, respiratory_rate, skin_temp_celsius,
  disturbance_count, sleep_efficiency_percentage, sleep_consistency_percentage,
  total_light_sleep_time_milli, total_slow_wave_sleep_time_milli, total_rem_sleep_time_milli.

Output units follow TEAM_CONTRACTS.md section 3.2: durations in minutes, percentages in
percent, heart rate in bpm, HRV in milliseconds. Missing values stay None and are never filled.
Error messages name rows and columns but never print cell values.
"""
from __future__ import annotations

import math
from datetime import date as date_type
from typing import Literal

import pandas as pd

from app.models import NightRecord

MS_PER_MINUTE = 60_000.0
MAX_NIGHTS = 1000

# our column -> NightRecord field (no unit change)
DIRECT = {
    "resting_heart_rate": "resting_heart_rate_bpm",
    "hrv_rmssd_milli": "hrv_rmssd_ms",
    "spo2_percentage": "spo2_pct",
    "respiratory_rate": "respiratory_rate_rpm",
    "skin_temp_celsius": "skin_temperature_c",
    "disturbance_count": "disturbance_count",
    "sleep_efficiency_percentage": "sleep_efficiency_pct",
    "sleep_consistency_percentage": "sleep_consistency_pct",
}
STAGE_MS = {
    "light": "total_light_sleep_time_milli",
    "deep": "total_slow_wave_sleep_time_milli",
    "rem": "total_rem_sleep_time_milli",
}
PERCENT_COLUMNS = {"spo2_percentage", "sleep_efficiency_percentage", "sleep_consistency_percentage"}
MEASURE_COLUMNS = set(DIRECT) | set(STAGE_MS.values())


class ProviderDataError(ValueError):
    """The nightly data is unusable. The message is written for the person who supplied the file."""


def _clean(value: object) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
        return None
    return float(value)


def _to_bool(series: pd.Series) -> pd.Series:
    return series.map(lambda v: str(v).strip().lower() in {"true", "1", "yes"})


def frame_to_nights(df: pd.DataFrame, source: Literal["synthetic", "csv", "whoop"]) -> list[NightRecord]:
    """Validate a nightly table and convert it. Drops calibrating nights and naps."""
    if "date" not in df.columns:
        raise ProviderDataError("The file needs a 'date' column with one row per night (for example 2026-09-01).")
    if not (MEASURE_COLUMNS & set(df.columns)):
        raise ProviderDataError(
            "The file has a 'date' column but none of the sleep or recovery columns. Expected at least one of: "
            + ", ".join(sorted(DIRECT))
        )
    if len(df) > MAX_NIGHTS:
        raise ProviderDataError(f"The file has {len(df)} nights; the limit is {MAX_NIGHTS}.")
    if "person_id" in df.columns and df["person_id"].nunique() > 1:
        raise ProviderDataError(
            f"The file contains {df['person_id'].nunique()} different people; upload nights for one person at a time."
        )

    df = df.copy().reset_index(drop=True)
    df["_row"] = df.index + 1  # data row number, for error messages

    parsed = pd.to_datetime(df["date"], errors="coerce")
    bad = df.loc[parsed.isna(), "_row"].tolist()
    if bad:
        raise ProviderDataError(f"Row {bad[0]}: 'date' is not a valid date" + (f" (and {len(bad) - 1} more rows)." if len(bad) > 1 else "."))
    df["_date"] = parsed.dt.date
    dup = df[df["_date"].duplicated(keep=False)]
    if not dup.empty:
        raise ProviderDataError(f"Row {int(dup['_row'].iloc[1])}: more than one row for the same date; use one row per night.")

    numeric: dict[str, pd.Series] = {}
    for col in MEASURE_COLUMNS & set(df.columns):
        coerced = pd.to_numeric(df[col], errors="coerce")
        wrong = df.loc[coerced.isna() & df[col].notna() & (df[col].astype(str).str.strip() != ""), "_row"].tolist()
        if wrong:
            raise ProviderDataError(f"Row {wrong[0]}: '{col}' must be a number" + (f" (and {len(wrong) - 1} more rows)." if len(wrong) > 1 else "."))
        if (coerced < 0).any():
            raise ProviderDataError(f"Row {int(df.loc[coerced < 0, '_row'].iloc[0])}: '{col}' cannot be negative.")
        if col in PERCENT_COLUMNS and (coerced > 100).any():
            raise ProviderDataError(f"Row {int(df.loc[coerced > 100, '_row'].iloc[0])}: '{col}' is a percentage and cannot be above 100.")
        numeric[col] = coerced

    keep = pd.Series(True, index=df.index)
    if "user_calibrating" in df.columns:
        keep &= ~_to_bool(df["user_calibrating"])
    if "nap" in df.columns:
        keep &= ~_to_bool(df["nap"])
    person = str(df["person_id"].iloc[0]) if "person_id" in df.columns and len(df) else None

    nights: list[NightRecord] = []
    for i in df.index[keep]:
        d: date_type = df.at[i, "_date"]
        fields: dict[str, float | int | None] = {}
        for col, field in DIRECT.items():
            if col in numeric:
                v = _clean(numeric[col].at[i])
                fields[field] = None if v is None else (int(round(v)) if field == "disturbance_count" else v)
        stages = {k: _clean(numeric[c].at[i]) if c in numeric else None for k, c in STAGE_MS.items()}
        if all(v is not None for v in stages.values()):
            fields["sleep_duration_minutes"] = sum(stages.values()) / MS_PER_MINUTE  # type: ignore[arg-type]
        if stages["deep"] is not None:
            fields["deep_sleep_minutes"] = stages["deep"] / MS_PER_MINUTE
        if stages["rem"] is not None:
            fields["rem_sleep_minutes"] = stages["rem"] / MS_PER_MINUTE
        nights.append(
            NightRecord(night_id=f"{person}-{d.isoformat()}" if person else f"night-{d.isoformat()}", date=d, source=source, **fields)
        )
    nights.sort(key=lambda n: n.date)
    return nights
