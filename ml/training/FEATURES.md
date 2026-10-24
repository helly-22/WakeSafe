# Apnea-ECG nightly features

Produced by `ml/training/extract_features.py` into `ml/data/processed/apnea_ecg_nights.csv`, one row per
real recording from PhysioNet Apnea-ECG 1.0.0: the learning set (a01 to c10, 35 recordings) and the test set (x01 to x35, 35 recordings),
70 in all, from 32 people. No synthetic data is used. Screening aid only.

## Source files per record

- `.hea` header: sampling rate (100 Hz) and recording length.
- `.apn` minute-level labels (a, b and c records only): one symbol per minute, `A` = apnea during that minute, `N` = none.
- `additional-information.txt` (dataset table, all 70 records): minutes of apnea per record, plus age, sex, height and weight.
  The x records have no `.apn`, so their apnea-minute total comes from this table.
- `.qrs` machine QRS annotations: R-peak sample indices. If a record has no `.qrs`, R peaks are
  detected from the ECG in `.dat` with a small band-pass and energy-threshold detector (`beat_source = detected`).
  All 70 current records use `.qrs`. The x records have no `.dat` downloaded, so R peaks are never detected for them.

## Class definition and subjects

- Class follows the dataset definition applied to the total apnea minutes: 100 or more is `a` (apnea), fewer than 5 is `c` (control), otherwise `b` (borderline).
  This reproduces the dataset's own a, b and c letters for all 35 learning-set records. On the x records it gives 20 a, 10 c and 5 b.
- The 70 recordings come from 32 people, with several repeat nights per person. `subject_id` groups recordings with identical age, sex, height
  and weight in `additional-information.txt`. This is an inference, not a published subject key. Validation holds out all recordings of a subject together.

## Interval cleaning (applies to every RR-based column)

RR interval = time between consecutive beats, in seconds. An interval is used only if all hold:

1. It is between 0.3 s and 2.0 s (30 to 200 bpm).
2. Neither bounding beat is annotated `|` (isolated QRS-like artifact).
3. It is within 20 percent of the median of the surrounding 11 beats (removes ectopic or missed beats).

Only beats inside the annotated minutes are used.

## Columns

| Column | Units | How it is computed |
| --- | --- | --- |
| `person_id` | text | Record name, for example `a01` or `x07`. One row per record. |
| `subject_id` | text | Inferred person, for example `S07`. The group used in leave-one-subject-out validation. |
| `record_set` | learning or test | `learning` for a, b, c records and `test` for x records. |
| `group` | a, b, or c | Class derived from `apnea_minutes` with the dataset definition above. |
| `label` | 1, 0, or empty | a = 1, c = 0. Class b is left empty and excluded from training (10 recordings). |
| `recording_hours` | hours | `n_minutes / 60`. |
| `n_minutes` | minutes | Number of `.apn` minute labels, or the dataset table length for x records. |
| `n_beats` | count | Beats annotated inside the labeled minutes. |
| `valid_rr_fraction` | 0 to 1 | Share of RR intervals that pass the cleaning rules. A quality indicator. |
| `mean_hr_bpm` | beats per minute | `60 / mean(valid RR)` over the night. |
| `resting_hr_bpm` | beats per minute | Lowest 5 minute average of per-minute heart rate. Per-minute heart rate is `60 / mean(valid RR in that minute)`, needing at least 10 valid intervals. A window needs at least 4 valid minutes of 5. |
| `hrv_rmssd_ms` | milliseconds | RMSSD: root mean square of successive RR differences, using only pairs where both intervals are valid. |
| `sdnn_ms` | milliseconds | Standard deviation of valid RR intervals over the night. |
| `hr_minute_sd_bpm` | beats per minute | Standard deviation of the per-minute heart rate across the night. Captures overall heart-rate swing, which is larger when heart rate cycles with breathing pauses. |
| `apnea_minutes` | minutes | Minutes marked apnea: counted from `.apn` when present, otherwise taken from `additional-information.txt`. **Ground-truth summary, not a model input.** |
| `apnea_minute_fraction` | 0 to 1 | `apnea_minutes / n_minutes`. **Ground-truth summary, not a model input.** It comes from the same labels as `label`, so using it as a feature would leak the answer. Kept for analysis only. |
| `label_source` | `apn` or `info_table` | Where `apnea_minutes` came from. |
| `beat_source` | `qrs` or `detected` | Where the beat times came from. |

## Model inputs

Two models are trained by `ml/training/train_apnea_model.py`, both on the 60 usable recordings (40 apnea, 20 control,
29 subjects), validated leave-one-subject-out with a subject-level bootstrap CI.

**Runtime model (used by the app): `resting_hr_bpm` and `hrv_rmssd_ms` only.** These are the two columns a wrist wearable also reports.
It is a standardized logistic regression stored as plain numbers in `backend/app/ml/apnea_resting_hr_rmssd.json`
(feature means and scales, coefficients, intercept, cutoff), so the backend needs no scikit-learn. The score is
`1 / (1 + exp(-(intercept + sum(coef * z))))` with `z = (value - mean) / scale`.
Cutoff 0.5 was fixed in advance and not tuned. The score is not a calibrated probability and must not be shown as a percentage.
Validation: AUROC 0.760 (95% CI 0.565 to 0.920), sensitivity 0.70 and specificity 0.75 at the cutoff.

**ECG five-feature model (comparison only, not applicable to wearable data):** `mean_hr_bpm`, `resting_hr_bpm`, `hrv_rmssd_ms`,
`sdnn_ms`, `hr_minute_sd_bpm`. AUROC 0.856 (95% CI 0.701 to 0.980). It shows what the two wearable-compatible features give up.
It is saved only as a gitignored local file.

Never a model input: `apnea_minutes`, `apnea_minute_fraction`, `label`, `group`, `person_id`, `subject_id`.

The resting heart rate here is the lowest 5 minute average over the recording. A wearable's resting heart rate and HRV are not
computed the same way, so applying the model to them is an assumption, not a validated result.

## Limits

These come from clinical ECG, not from a wrist device. See `backend/app/ml/metrics.json` for the domain-shift statement and the validation results.
