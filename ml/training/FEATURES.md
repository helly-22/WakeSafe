# Apnea-ECG nightly features

Produced by `ml/training/extract_features.py` into `ml/data/processed/apnea_ecg_nights.csv`, one row per
real recording from PhysioNet Apnea-ECG 1.0.0 (learning set: a01 to a20, b01 to b05, c01 to c10, 35 recordings).
No synthetic data is used. WakeSafe is a screening aid, not a diagnosis.

## Source files per record

- `.hea` header: sampling rate (100 Hz) and recording length.
- `.apn` minute-level labels: one symbol per minute, `A` = apnea during that minute, `N` = none.
- `.qrs` machine QRS annotations: R-peak sample indices. If a record has no `.qrs`, R peaks are
  detected from the ECG in `.dat` with a small band-pass and energy-threshold detector (`beat_source = detected`).
  All 35 current records use `.qrs`.

## Interval cleaning (applies to every RR-based column)

RR interval = time between consecutive beats, in seconds. An interval is used only if all hold:

1. It is between 0.3 s and 2.0 s (30 to 200 bpm).
2. Neither bounding beat is annotated `|` (isolated QRS-like artifact).
3. It is within 20 percent of the median of the surrounding 11 beats (removes ectopic or missed beats).

Only beats inside the annotated minutes are used.

## Columns

| Column | Units | How it is computed |
| --- | --- | --- |
| `person_id` | text | Record name, for example `a01`. Used as the group in leave-one-person-out validation. |
| `group` | a, b, or c | First letter of the record name: a = apnea, b = borderline, c = control. |
| `label` | 1, 0, or empty | a = 1, c = 0. Group b is left empty and excluded from training (5 recordings). |
| `recording_hours` | hours | `n_minutes / 60`. |
| `n_minutes` | minutes | Number of `.apn` minute labels. |
| `n_beats` | count | Beats annotated inside the labeled minutes. |
| `valid_rr_fraction` | 0 to 1 | Share of RR intervals that pass the cleaning rules. A quality indicator. |
| `mean_hr_bpm` | beats per minute | `60 / mean(valid RR)` over the night. |
| `resting_hr_bpm` | beats per minute | Lowest 5 minute average of per-minute heart rate. Per-minute heart rate is `60 / mean(valid RR in that minute)`, needing at least 10 valid intervals. A window needs at least 4 valid minutes of 5. |
| `hrv_rmssd_ms` | milliseconds | RMSSD: root mean square of successive RR differences, using only pairs where both intervals are valid. |
| `sdnn_ms` | milliseconds | Standard deviation of valid RR intervals over the night. |
| `hr_minute_sd_bpm` | beats per minute | Standard deviation of the per-minute heart rate across the night. Captures overall heart-rate swing, which is larger when heart rate cycles with breathing pauses. |
| `apnea_minute_fraction` | 0 to 1 | Fraction of labeled minutes marked `A`. **Ground-truth summary, not a model input.** It is derived from the same labels as `label`, so using it as a feature would leak the answer. Kept for analysis only. |
| `beat_source` | `qrs` or `detected` | Where the beat times came from. |

## Model inputs

Training uses only the wearable-style columns: `mean_hr_bpm`, `resting_hr_bpm`, `hrv_rmssd_ms`,
`sdnn_ms`, `hr_minute_sd_bpm`. Never `apnea_minute_fraction`, `label`, `group`, or `person_id`.

## Limits

These come from clinical ECG, not from a wrist device. See `backend/app/ml/metrics.json` for the domain-shift statement.
