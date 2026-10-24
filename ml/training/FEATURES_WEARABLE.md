# WakeSafe apnea features (WHOOP-mappable)

Every feature is a per-minute summary chosen to map onto a signal a wrist wearable (WHOOP) also
reports nightly, so a model trained on open clinical recordings describes the same quantities WHOOP
would feed it. Features are extracted by `ml/training/features_wearable.py`; missing values stay
`NaN` and are never imputed to a "normal" value before the model (the gradient-boosted tree handles
missingness itself).

## Heart rate / HRV -- maps to WHOOP resting heart rate and HRV (RMSSD)

| feature | unit | meaning | source |
|---|---|---|---|
| `hr_mean_bpm` | bpm | mean heart rate in the minute | Apnea-ECG: from ECG R-peaks (neurokit2, scipy fallback); UCD: pulse-oximeter HR channel |
| `hr_min_bpm` | bpm | minimum heart rate in the minute | same |
| `hr_max_bpm` | bpm | maximum heart rate in the minute | same |
| `hr_std_bpm` | bpm | within-minute heart-rate spread (apnea drives cyclical HR swings) | same |
| `hrv_rmssd_ms` | ms | RMSSD of successive RR intervals (beat-to-beat variability) | Apnea-ECG only (needs beat-to-beat ECG); NaN for UCD pulse HR |
| `hrv_sdnn_ms` | ms | SD of RR intervals | Apnea-ECG only |

RR intervals are kept only when physiologic (0.3-2.0 s). RMSSD/SDNN need true beat-to-beat timing,
so they come from the ECG cohort; the UCD pulse channel gives HR summaries but not RMSSD, which is
left missing by design.

## SpO2 desaturation -- maps to WHOOP nightly SpO2

| feature | unit | meaning | source |
|---|---|---|---|
| `spo2_mean_pct` | % | mean SpO2 in the minute | UCD SpO2 channel (8 Hz); NaN for Apnea-ECG (no usable oximetry) |
| `spo2_min_pct` | % | minimum SpO2 (deepest dip) | UCD |
| `spo2_drop_pct` | % | mean minus min within the minute (desaturation depth) | UCD |
| `spo2_time_below90_frac` | 0-1 | fraction of the minute spent below 90% SpO2 | UCD |
| `spo2_desat_count` | count | number of >=3% dips below a 120-s rolling baseline | UCD |

Oximeter dropout artefacts (values outside 50-100%) are clipped to `NaN` before these are computed.

## Respiratory-rate variability -- maps to WHOOP respiratory rate

| feature | unit | meaning | source |
|---|---|---|---|
| `resp_rate_rpm` | breaths/min | breathing rate from airflow zero-crossings | UCD Flow channel; NaN for Apnea-ECG |
| `resp_rate_std_rpm` | breaths/min | variability of breathing rate (apnea makes it irregular) | UCD |
| `flow_rms` | a.u. | airflow envelope energy; drops toward zero during an apnoea | UCD |

## Why features are missing across cohorts

The two open cohorts expose different raw signals: Apnea-ECG is ECG-only (HR/HRV, no SpO2), UCD is
full polysomnography (SpO2 + pulse HR + airflow). That is why the models are validated separately
per cohort rather than pooled on only the shared HR columns -- pooling on HR alone was weaker and
would have hidden that SpO2 is the dominant apnea signal. See
`ml/models/apnea_gbt_v1_metrics.md` for the cross-validated numbers.

## Labels

- Apnea-ECG: per-minute `.apn` annotation (`A` = apnea minute, `N` = normal).
- UCD: `_respevt.txt` event list; a minute is labelled apnea if an apnea/hypopnoea event overlaps it
  (event clock-times aligned to the EDF start time).
- OSV oximetry set: has **no** apnea event labels and is therefore **not** used for training.
