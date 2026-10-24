import type { NightMetricKey } from './types';

/**
 * Display metadata for NightRecord fields. Labels and units only; no thresholds,
 * targets or scoring live here.
 */
export interface MetricMeta {
  key: NightMetricKey;
  label: string;
  unit: string;
  digits: number;
}

export const METRICS: Record<NightMetricKey, MetricMeta> = {
  sleep_duration_minutes: { key: 'sleep_duration_minutes', label: 'Sleep duration', unit: 'min', digits: 0 },
  sleep_efficiency_pct: { key: 'sleep_efficiency_pct', label: 'Sleep efficiency', unit: '%', digits: 0 },
  sleep_consistency_pct: { key: 'sleep_consistency_pct', label: 'Sleep consistency', unit: '%', digits: 0 },
  deep_sleep_minutes: { key: 'deep_sleep_minutes', label: 'Deep sleep', unit: 'min', digits: 0 },
  rem_sleep_minutes: { key: 'rem_sleep_minutes', label: 'REM sleep', unit: 'min', digits: 0 },
  disturbance_count: { key: 'disturbance_count', label: 'Disturbances', unit: '/night', digits: 0 },
  resting_heart_rate_bpm: { key: 'resting_heart_rate_bpm', label: 'Resting heart rate', unit: 'bpm', digits: 0 },
  hrv_rmssd_ms: { key: 'hrv_rmssd_ms', label: 'HRV (RMSSD)', unit: 'ms', digits: 0 },
  respiratory_rate_rpm: { key: 'respiratory_rate_rpm', label: 'Respiratory rate', unit: 'rpm', digits: 1 },
  spo2_pct: { key: 'spo2_pct', label: 'Blood oxygen (SpO₂)', unit: '%', digits: 1 },
  skin_temperature_c: { key: 'skin_temperature_c', label: 'Skin temperature', unit: '°C', digits: 1 },
};

/**
 * Nights needed before a personal baseline is shown. Mirrors the
 * compute_features(baseline_nights=14) default in TEAM_CONTRACTS.md §4.1; the
 * final minimum is still pending (§9). Used for wording only.
 */
export const BASELINE_NIGHTS = 14;

/**
 * Fixture feature key for a metric's window average. Placeholder naming
 * (`<field>_mean`) until Dhev's compute_features feature names are agreed.
 */
export function meanFeatureKey(key: NightMetricKey): string {
  return `${key}_mean`;
}

/**
 * Describes a personal-baseline z-score in words. Purely descriptive: it says
 * whether recent nights sit above or below the user's own average, not whether
 * that is good, bad or clinically meaningful. Returns null when no z-score exists.
 *
 * NEAR_BASELINE_Z is a display choice for wording only, not a clinical threshold.
 */
export const NEAR_BASELINE_Z = 0.5;

export type BaselineDirection = 'above' | 'below' | 'near';

export function baselineDirection(z: number | null | undefined): BaselineDirection | null {
  if (z === null || z === undefined) return null;
  if (Math.abs(z) < NEAR_BASELINE_Z) return 'near';
  return z > 0 ? 'above' : 'below';
}
