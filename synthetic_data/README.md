# WakeSafe synthetic WHOOP-style data

Synthetic data. Not clinical. Do not use to estimate model accuracy.

This folder generates fake nightly wearable data and fake medical-history profiles for WakeSafe demos, UI development, and tests. It is never used to train, tune, or score the screening model. The model uses real open sleep-study datasets with leave-one-person-out validation.

Every value is drawn from distributions in `persona_config.yaml`. Each one is an assumption chosen to look plausible. None is fitted to real data.

## Quick start

Run from the repository root:

```bash
python3 -m venv synthetic_data/.venv
synthetic_data/.venv/bin/pip install pandas==2.2.3 numpy==2.1.3 pyyaml==6.0.2 pytest==8.3.4

synthetic_data/.venv/bin/python synthetic_data/generate_synthetic_whoop.py --seed 42
synthetic_data/.venv/bin/python synthetic_data/validate_synthetic.py
synthetic_data/.venv/bin/python -m pytest synthetic_data/tests -q
```

Generator arguments (defaults in brackets): `--seed` [42], `--nights` [30], `--n-healthy` [25], `--n-osa` [20], `--n-hard-negative` [6], `--n-hard-positive` [6], `--n-other` [8], `--out` [synthetic_data/out], `--config` [synthetic_data/persona_config.yaml].

The same seed, cohort sizes, and config file always produce byte-identical files.

## Reading the files

Every CSV starts with one comment line that begins with `# SYNTHETIC DATA`. Read the files with `comment="#"`:

```python
import pandas as pd

sleep = pd.read_csv("synthetic_data/out/sleep.csv", comment="#")
```

No data value contains a `#`, so `comment="#"` only skips the header line. The header line also records the seed, cohort sizes, and a hash of the config. The validator uses these to regenerate the data and confirm it is unchanged.

Every CSV also has an `is_synthetic` column that is always true. Every JSON file has a top-level `"synthetic": true` field.

## Output files (`synthetic_data/out/`)

| File | Contents |
| --- | --- |
| `profiles.csv` | One row per person: age, sex, height, weight, BMI, neck circumference, conditions, self-reported symptoms, red flags |
| `recovery.csv` | One row per person per recorded night: recovery score, resting HR, HRV, SpO2, skin temperature, calibration flag |
| `sleep.csv` | One row per person per recorded night: sleep timing, stage durations, disturbances, respiratory rate, performance, consistency, efficiency |
| `ground_truth.csv` | One row per person: true condition, simulated AHI (apnea rows only), difficulty, notes |
| `whoop_api_mock/<person_id>.json` | The same rows shaped like WHOOP API v2 responses |

`ground_truth.csv` is kept separate on purpose. Never merge it into the data the app reads. Only `validate_synthetic.py` and the tests join it, and only in memory.

Person ids are `P001`, `P002`, and so on. Ids are shuffled, so their order does not reveal the cohort. The mock files use `Synthetic` and the person id as placeholder names, and `@example.invalid` emails.

### Conventions

- `date` is the wake-up date (ISO `YYYY-MM-DD`). The night of 2026-09-01 starts on the evening of 2026-08-31.
- `sleep_start` and `sleep_end` are ISO 8601 UTC timestamps with milliseconds, for example `2026-09-01T00:23:23.905Z`. Every persona is assumed to live in UTC, so local time equals UTC.
- All durations are integer milliseconds.
- `light + slow_wave + rem + awake + no_data = total_in_bed_time_milli` holds exactly on every night.
- `sleep_efficiency_percentage = 100 * (light + slow_wave + rem) / total_in_bed_time_milli`, rounded to 4 decimals.
- `spo2_percentage` and `skin_temp_celsius` are empty in CSV and `null` in JSON when missing.
- `conditions` and `red_flag_symptoms` are semicolon-separated and empty when there are none. Possible conditions: `hypertension`, `type2_diabetes`, `atrial_fibrillation`, `asthma`, `copd`. Possible red flags: `chest_pain`, `fainting`, `severe_shortness_of_breath`, `stroke_symptoms`.
- Red flags are self-reported profile fields. They never come from the wearable data.

### Field names compared with WHOOP API v2

The CSV field names follow the requested spec. They match the WHOOP v2 `score` fields, with these differences:

- WHOOP nests the fields. Recovery values (including `user_calibrating`) sit under `score`. Stage durations, `sleep_cycle_count`, and `disturbance_count` sit under `score.stage_summary`. The CSVs flatten them.
- WHOOP calls the sleep times `start` and `end`. The CSVs use `sleep_start` and `sleep_end`.
- `person_id`, `date`, and `is_synthetic` are not WHOOP fields. WHOOP identifies people by a numeric `user_id`.

The mock JSON uses WHOOP's nested v2 shape (sleep `id` as a UUID, `cycle_id`, `user_id`, `score_state`, `score.stage_summary`, `score.sleep_needed`, recovery `sleep_id`). It was checked against the public [WHOOP API reference](https://developer.whoop.com/api/).

### Mock JSON layout

```text
{
  "synthetic": true,
  "notice": "...",
  "person_id": "P001",
  "api_version": "v2",
  "generator": {"name": ..., "seed": 42, "config_sha256": ...},
  "endpoints": {
    "/v2/user/profile/basic": {...},
    "/v2/user/measurement/body": {...},
    "/v2/recovery": {"pages": [{"records": [...], "next_token": "..."}, ...]},
    "/v2/activity/sleep": {"pages": [{"records": [...], "next_token": null}]}
  }
}
```

Records are newest first, as WHOOP returns them. Pages hold at most 25 records, which is WHOOP's maximum `limit`. Page k+1 is the response to a request whose `nextToken` equals page k's `next_token`. The last page has `next_token: null`. `sleep_needed` holds the simulated nightly sleep need in `baseline_milli`, and the other need parts are 0.

## How the data is generated

1. Cohorts are built from the CLI counts. Ids are assigned by a seeded shuffle.
2. Each person gets a profile drawn from that cohort's distributions.
3. Each person gets a personal healthy-style baseline for every signal.
4. Chronic effects, episodes, and nightly events are added to that baseline.
5. Each night gets AR(1) noise, and then the derived scores are computed.
6. Missing data is applied. Burn-in nights are dropped.

Each person uses an independent random stream spawned from the seed, so one person's data does not depend on the order of the others.

### Healthy-style baseline (every persona starts here)

- Age is uniform from 20 to 70. Sex is 50/50 male and female. Height depends on sex.
- BMI ~ N(24.3, 2.9), clipped to 17.5 to 34, so it is mostly 19 to 29. Weight is computed from BMI and height.
- Neck circumference = sex-specific base + 0.45 to 0.55 cm per BMI unit above 24 + noise.
- Resting HR ~ N(61, 5) + 0.2 bpm per BMI unit above 24.
- HRV (RMSSD) is log-normal: 68 ms at age 20, declining about 1.7 percent per year, log SD 0.25.
- SpO2 ~ N(96.6, 0.95), clipped to 93.5 to 99.
- Respiratory rate ~ N(14.8, 1.0) + 0.05 per BMI unit.
- Skin temperature ~ N(33.9, 0.45) C.
- Time in bed ~ N(7.75, 0.45) h, clipped to 6.5 to 9.
- Sleep start is about 23:12 (SD 45 min).
- Efficiency ~ N(91, 3.5).
- Slow-wave share is about 21 percent at age 20 and declines with age. REM share is about 23 percent.
- Disturbances have a median of 9.5 per night (log SD 0.35).
- Sleep need ~ N(7.9, 0.4) h.

### Nightly process

- Noise: every signal gets its own stationary AR(1) series around the person's baseline, with phi = 0.5. Nightly SDs are in `noise.nightly_sd`.
- Weekend effect: 60 percent of people start sleep 0.5 to 1.5 h later on Friday and Saturday nights and stay in bed 0.1 to 0.6 h longer. This lowers their consistency.
- Shared confounder: every person has alcohol or minor-illness nights (5 percent of weekdays, 15 percent of weekend nights). On those nights HRV drops 15 percent, resting HR rises 3.5 bpm, and SpO2 drops 0.4 points. Disturbances, efficiency, and REM also get worse.
- Stages: asleep time = in-bed time x efficiency, capped by in-bed time minus no-data time. Slow-wave and REM are shares of asleep time. Light sleep is the remainder, so totals reconcile exactly.
- Disturbances are Poisson draws around the personal mean, scaled by time in bed and effects, and capped at 90.
- Sleep cycles = asleep hours / personal cycle length (1.4 to 1.7 h) + noise.
- `sleep_performance_percentage` = 100 x asleep hours / nightly sleep need, capped at 100.
- `sleep_consistency_percentage` = 100 - 40 x (mean of the SD of start time and the SD of end time, in hours, over the last 4 nights). Six hidden burn-in nights give the first output nights a history.
- `recovery_score` is a stand-in for WHOOP's proprietary score: 62 + 30 x ln(HRV / personal HRV baseline) - 1.2 x (resting HR - personal baseline) + 0.35 x (performance - 85) + noise (SD 7), clipped to 1 to 99. Any effect that lowers HRV, raises resting HR, or shortens sleep pulls recovery down.

### Missing data

- SpO2 and skin temperature are each missing at random on 5 percent of nights.
- 10 percent of people are SpO2-sparse, with SpO2 missing on 30 percent of nights.
- `user_calibrating` is true for each person's first 3 or 4 nights.
- 2 percent of nights have no record at all (no sleep row and no recovery row).
- 15 percent of nights have some no-data time (0.3 to 4 percent of time in bed).

## Cohorts and effect sizes

### Sleep apnea pattern (`osa_mild`, `osa_moderate`, `osa_severe`, difficulty easy)

The default 20 people split 35/35/30 into 7 mild, 7 moderate, and 6 severe. Effects are added to each person's own baseline. Each person also gets an individual effect scale ~ N(1, 0.35), clipped to 0.35 to 1.8, so severity groups overlap.

| Effect | Mild | Moderate | Severe |
| --- | --- | --- | --- |
| SpO2 mean (points) | -0.5 | -1.2 | -2.2 |
| SpO2 night-to-night SD multiplier | 1.3 | 1.6 | 2.0 |
| Nights with an extra SpO2 dip (probability, size in points) | 5%, 1.5 to 3 | 10%, 2 to 4 | 18%, 2.5 to 5 |
| Respiratory rate (breaths/min) | +0.3 | +0.7 | +1.2 |
| Respiratory rate SD multiplier | 1.15 | 1.3 | 1.5 |
| Disturbances | +25% | +60% | +110% |
| Sleep efficiency (points, so more awake time) | -2 | -5 | -9 |
| Slow-wave share (relative) | -10% | -20% | -30% |
| REM share (relative) | -5% | -10% | -15% |
| Resting HR (bpm) | +1.5 | +3 | +5 |
| HRV | -8% | -15% | -25% |
| Simulated AHI (events/h) | 5 to 14 | 15 to 29 | 30 to 60 |

Profile correlations make some traits more likely, but none is guaranteed:

- Age ~ N(50, 11), plus 3 years for moderate and 5 for severe.
- 68 percent are male.
- Mean BMI is 28.5, 30.5, and 33 for mild, moderate, and severe. 15 percent draw BMI from the healthy distribution.
- Neck circumference is 1 cm larger on top of the BMI effect.
- Snoring rates are 60, 75, and 85 percent. Witnessed pauses are 20, 35, and 55 percent. Daytime tiredness is 40, 55, and 70 percent. Hypertension is 30, 40, and 55 percent.
- Recovery score and sleep performance drop through the formulas above.

### Hard positives (`osa_mild`, difficulty hard)

Mild apnea at half the mild effect size. The individual scale is capped at 1, so the effect is at most 0.5 x mild. BMI is drawn from the healthy distribution. Nobody reports snoring or witnessed pauses. AHI is 5 to 12.

### Hard negatives (`healthy`, difficulty hard)

The subtypes are assigned in order and cycle when there are more people than subtypes:

- `short_sleeper`: about 6 h in bed, resting HR +2, HRV -10%.
- `endurance_trainer`: resting HR about 48 and HRV 1.5 times higher. Disturbances +20% and respiratory rate +0.4. On 35 percent of nights, hard training adds resting HR +5, HRV -22%, and more disturbances.
- `frequent_alcohol`: confounder nights on 30 percent of weekdays and 60 percent of weekends, at 1.5 times the usual effect.
- `cold`: one 3 to 4 night episode (respiratory rate +1.2, SpO2 -1.2, skin temperature +0.4, resting HR +4, HRV -20%) with a recovery tail.
- `high_bmi`: BMI 31 to 37, snoring 45 percent, resting HR +3, HRV -10%, SpO2 -0.5, respiratory rate +0.5.

### Other risk personas (difficulty easy)

- `cardiovascular_strain`: history of hypertension (70 percent, with atrial fibrillation also in 25 percent of those) or atrial fibrillation. Over the last 14 to 21 nights, resting HR drifts up to +6, HRV drifts down to -25%, and respiratory rate rises to +0.6.
- `respiratory_flare`: history of asthma (60 percent) or COPD. A 3 to 5 night flare: respiratory rate +2, skin temperature +0.4 C, SpO2 -2, HRV -15%, and resting HR +3.
- `acute_illness`: a 3 to 4 night episode: skin temperature +1.0 C, resting HR +7, respiratory rate +1.5, HRV -30%, and SpO2 -0.8.
- `urgent`: any pattern (healthy, moderate apnea, cardiovascular strain, or acute illness) plus 1 or 2 self-reported red flags.

After each episode, effects fade over 2 nights at 50 percent and then 20 percent. Episode dates are in `ground_truth.csv` notes.

## Plausible ranges (checked by the validator)

| Field | Range |
| --- | --- |
| recovery_score | 0 to 100 |
| resting_heart_rate | 35 to 110 bpm |
| hrv_rmssd_milli | 5 to 250 ms |
| spo2_percentage | 85 to 100 % |
| skin_temp_celsius | 30 to 38 C |
| respiratory_rate | 8 to 30 breaths/min |
| total_in_bed_time_milli | 3 h to 12 h (10,800,000 to 43,200,000 ms) |
| sleep_efficiency_percentage | 50 to 100 |
| sleep_performance_percentage, sleep_consistency_percentage | 0 to 100 |
| disturbance_count | 0 to 100 |
| sleep_cycle_count | 0 to 10 |
| age | 18 to 90 |
| bmi | 15 to 60 |
| height_m | 1.40 to 2.10 |
| weight_kg | 35 to 200 |
| neck_circumference_cm | 25 to 55 |

All durations must also be non-negative integers.

## Validation (`validate_synthetic.py`)

The validator prints a per-cohort table: the mean (SD) of per-person means for SpO2, respiratory rate, disturbances, efficiency, resting HR, HRV, recovery, and performance. It also prints AUROCs, then runs these checks. It exits with status 1 if any check fails.

1. Synthetic labels: every CSV has the header comment and `is_synthetic`, every JSON has `"synthetic": true`, no ground-truth column appears outside `ground_truth.csv`, and ids look like `P001`.
2. Plausible ranges: values fall in the ranges above.
3. Stage reconciliation: stages + awake + no-data = in-bed time, efficiency can be recomputed, `sleep_end - sleep_start` = in-bed time, `nap` is false, dates are ISO, and sleep and recovery rows cover the same nights.
4. Profile consistency: BMI matches height and weight, and the hypertension flag matches conditions.
5. Missing data: missing rates are in a sensible band, and calibration flags cover only the first 3 to 4 nights.
6. Group directions: apnea vs healthy means move the intended way for SpO2 (lower), respiratory rate (higher), disturbances (higher), efficiency (lower), resting HR (higher), and HRV (lower).
7. Overlap: on per-person means, the AUROC separating healthy from apnea must be above 0.55 and below 0.90 for each of those six features. An AUROC of 0.95 or higher is reported as unrealistically easy.
8. Hard case overlap: each hard negative reaches the mild apnea range on at least one feature. Short episodes such as a cold count through the worst 4-night window. Each hard positive is no more apnea-like than the healthy 90th percentile on at least 3 of 6 features.
9. WHOOP mock: page records match the CSV rows, page sizes are 25 or fewer, and `next_token` chains correctly.
10. Reproducibility: the validator regenerates the data from the header parameters into a temp folder and checks every file is byte-identical. It fails if the config changed since generation.

For checks 6 to 8, "healthy" means easy healthy plus hard negatives, and "apnea" means all `osa_*` rows, including hard positives. The other risk personas are excluded.

Seed sensitivity: with about 26 apnea and 31 healthy people, AUROC has a sampling error of roughly 0.07. Seed 42 passes every check. In a sweep of seeds 1 to 30, 26 seeds passed every check. The failures were resting HR or HRV AUROC near 0.5 (seeds 5, 10, 30) and one hard positive (seed 24). This reflects how weak those signals are in small cohorts. If you change the seed, run the validator.

## Tests

`synthetic_data/tests/` covers:

- determinism (same seed gives byte-identical files, a different seed gives different files, and the CLI matches the library)
- units (milliseconds, Celsius, SpO2 as a percent)
- ranges and reconciliation
- missing data and calibration
- labels and ground-truth separation
- cohort structure and the WHOOP mock shape
- each validation check, which must pass on good data and fail on deliberately broken data

`synthetic_data/pytest.ini` keeps pytest's root inside this folder and turns off the cache.

## Limits

- This is a statistical sketch, not a physiological model. Effects are additive offsets with simple noise.
- The recovery formula, consistency formula, and sleep need are stand-ins. WHOOP's real algorithms are proprietary.
- Effect sizes are starting assumptions for tuning, not literature estimates.
- Synthetic data is for demos, UI work, and tests only. Never use it to train, tune, or score any model, and never report accuracy on it.
