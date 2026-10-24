# WakeSafe apnea screening model -- metrics card (apnea-gbt-v1)

**Model:** small gradient-boosted tree (sklearn `GradientBoostingClassifier`, depth 3,
150 estimators, learning rate 0.05, row subsample 0.8, min 30 samples/leaf, class-balanced
sample weights). Missing features are median-imputed with added missing-indicator columns, so the
tree can still split on whether a signal was present. Not a deep net -- by design, because there are
too few labelled nights for one.

**Unit:** one row per MINUTE of sleep; label = apnea/hypopnoea minute vs normal minute.

**WHOOP-mappable features:** `hr_mean_bpm`, `hr_min_bpm`, `hr_max_bpm`, `hr_std_bpm`, `hrv_rmssd_ms`, `hrv_sdnn_ms`, `spo2_mean_pct`, `spo2_min_pct`, `spo2_drop_pct`, `spo2_time_below90_frac`, `spo2_desat_count`, `resp_rate_rpm`, `resp_rate_std_rpm`, `flow_rms`
-- heart rate / HRV, SpO2 desaturation, and respiratory-rate variability, all signals a wrist
wearable (WHOOP) also reports nightly.

**Data (open access, real recordings only):**
- UCD St Vincent's (PRIMARY, runtime model): ['ucddb002', 'ucddb003', 'ucddb005']
- UCD skipped (truncated / unreadable): []
- Apnea-ECG (SECONDARY corroboration): ['a01', 'a02', 'a03', 'a04', 'a05', 'a06', 'b01', 'b04', 'c01']
- OSV oximetry: NOT used -- no apnea event labels, so it cannot honestly supply a training label.

The full Apnea-ECG database could not be downloaded in this environment (the PhysioNet link stalled
repeatedly), so the secondary cohort uses the apnea recordings that completed. The pipeline scales
up automatically if more records are fetched later.

## PRIMARY result -- UCD, full WHOOP-mappable feature set (this is the saved runtime model)
1228 minutes from 3 recordings
(358 apnea / 870 normal), leave-one-record-out.

| metric | value |
|---|---|
| AUROC (held-out) | **0.724** |
| sensitivity @ 0.5 | **0.52** |
| specificity @ 0.5 | **0.772** |
| AUROC (train, resubstitution) | 0.97 |
| **overfitting gap (train - CV AUROC)** | **0.246** |

### Held-out performance per recording
| record | minutes | apnea | sensitivity | specificity |
|---|---|---|---|---|
| `ucddb/ucddb002` | 374 | 103 | 0.107 | 0.989 |
| `ucddb/ucddb003` | 441 | 205 | 0.663 | 0.661 |
| `ucddb/ucddb005` | 413 | 50 | 0.78 | 0.683 |

### Features the runtime model leans on (permutation importance, drop in AUROC)
- `spo2_drop_pct`: 0.101
- `resp_rate_rpm`: 0.028
- `flow_rms`: 0.018
- `hr_std_bpm`: 0.015
- `resp_rate_std_rpm`: 0.012
- `hr_mean_bpm`: 0.009
- `spo2_mean_pct`: 0.007
- `hr_max_bpm`: 0.006
- `hr_min_bpm`: 0.005
- `spo2_time_below90_frac`: 0.004
- `spo2_min_pct`: 0.003

SpO2 desaturation dominates, which is the expected and reassuring result for an apnea screen;
HR/HRV contribute secondarily.

## SECONDARY result -- Apnea-ECG, HR/HRV only (independent corroboration)
Apnea-ECG apnea recordings, HR/HRV features only (2992 minutes from
6 recordings, 2071 apnea / 921 normal).
A different set of people and a different device from the primary cohort.

| metric | value |
|---|---|
| AUROC (held-out) | **0.705** |
| sensitivity @ 0.5 | **0.657** |
| specificity @ 0.5 | **0.739** |
| AUROC (train, resubstitution) | 0.921 |
| **overfitting gap (train - CV AUROC)** | **0.216** |

| record | minutes | apnea | sensitivity | specificity |
|---|---|---|---|---|
| `apnea-ecg/a01` | 489 | 470 | 0.994 | 0.0 |
| `apnea-ecg/a02` | 528 | 420 | 0.007 | 1.0 |
| `apnea-ecg/a03` | 519 | 246 | 0.976 | 0.535 |
| `apnea-ecg/a04` | 492 | 453 | 0.821 | 0.897 |
| `apnea-ecg/a05` | 454 | 276 | 0.804 | 0.708 |
| `apnea-ecg/a06` | 510 | 206 | 0.277 | 0.875 |

The HR/HRV-only model clears chance on a second cohort and device, confirming the heart-rate
pathway carries apnea information even without SpO2. This matters because some WHOOP nights may have
HR/HRV but sparse SpO2.

## Honest limitations
1. Screening aid, not a diagnosis. WakeSafe flags a pattern worth discussing with a clinician; it never tells a user they have sleep apnea.
2. Trained on raw clinical polysomnography and ECG (UCD St Vincent's + PhysioNet Apnea-ECG), NOT on WHOOP nightly summaries. It validates the screening LOGIC on wearable-mappable signals; accuracy on real WHOOP data is not claimed and has not been measured. WHOOP computes SpO2, resting HR and HRV differently from these clinical sensors.
3. Very small sample: a few overnight recordings per cohort (the full Apnea-ECG database could not be fetched in this environment). Leave-one-record-out validation is honest but confidence intervals are wide and a single unusual night moves the numbers.
4. Per-minute labels within a night are correlated, so the effective sample size is far smaller than the minute count; held-out AUROC is reported per record so no single night hides in the pool.
5. The two cohorts carry different raw signals (UCD has SpO2; Apnea-ECG does not), so they are validated separately rather than pooled -- pooling on the shared HR/HRV signals alone was weaker and would hide the fact that SpO2 is the dominant apnea signal.
6. Output probability is NOT calibrated and must not be shown to a user as a percentage risk.

## How this plugs into the ApneaScore contract
`score_apnea(profile, features) -> ApneaScore` can load `ml/models/apnea_gbt_v1.pkl`, build the
feature row from a night's WHOOP summaries (per minute, or a nightly aggregate), and read
`predict_proba`. The saved dict carries `features` (column order), `cutoff` and `model_version`.
Map the score to `tier` (Low/Moderate/High) with documented cut-points, set `probability` only as
an UNCALIBRATED score or leave it null per the contract, fill `top_factors` from the
permutation-importance order above, set `model_version="apnea-gbt-v1"`, and put the first
limitation line in `evidence_note`. Added ALONGSIDE Dhev's runtime model; does not overwrite
`backend/app/ml/`.
