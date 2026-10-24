import { formatMinutes, formatNumber } from './format';
import type { FeatureSet, NightMetricKey, NightRecord } from './types';
import { meanFeatureKey } from './metrics';

/**
 * How each nightly series is drawn and labeled. Display metadata only: no
 * targets, thresholds or scoring live here.
 */
export interface SeriesDef {
  key: NightMetricKey;
  label: string;
  unit: string;
  digits: number;
  kind: 'bar' | 'line';
  color: string;
  group: 'sleep' | 'recovery';
  /** Y-axis tick step override (e.g. 120 minutes for hour ticks). */
  tickStep?: number;
  axisFormat?: (v: number) => string;
}

const HOURS = (v: number) => `${Math.round(v / 60)}h`;

export const SERIES: Record<NightMetricKey, SeriesDef> = {
  sleep_duration_minutes: { key: 'sleep_duration_minutes', label: 'Sleep duration', unit: 'min', digits: 0, kind: 'bar', color: 'var(--c-duration)', group: 'sleep', tickStep: 120, axisFormat: HOURS },
  sleep_efficiency_pct: { key: 'sleep_efficiency_pct', label: 'Sleep efficiency', unit: '%', digits: 0, kind: 'line', color: 'var(--c-efficiency)', group: 'sleep' },
  sleep_consistency_pct: { key: 'sleep_consistency_pct', label: 'Sleep consistency', unit: '%', digits: 0, kind: 'line', color: 'var(--teal)', group: 'sleep' },
  deep_sleep_minutes: { key: 'deep_sleep_minutes', label: 'Deep sleep', unit: 'min', digits: 0, kind: 'bar', color: 'var(--c-deep)', group: 'sleep' },
  rem_sleep_minutes: { key: 'rem_sleep_minutes', label: 'REM sleep', unit: 'min', digits: 0, kind: 'bar', color: 'var(--c-rem)', group: 'sleep' },
  disturbance_count: { key: 'disturbance_count', label: 'Disturbances', unit: '/night', digits: 0, kind: 'bar', color: 'var(--amber)', group: 'sleep' },
  resting_heart_rate_bpm: { key: 'resting_heart_rate_bpm', label: 'Resting heart rate', unit: 'bpm', digits: 0, kind: 'line', color: 'var(--c-hr)', group: 'recovery' },
  hrv_rmssd_ms: { key: 'hrv_rmssd_ms', label: 'HRV (RMSSD)', unit: 'ms', digits: 0, kind: 'line', color: 'var(--c-hrv)', group: 'recovery' },
  respiratory_rate_rpm: { key: 'respiratory_rate_rpm', label: 'Respiratory rate', unit: 'rpm', digits: 1, kind: 'line', color: 'var(--c-resp)', group: 'recovery' },
  spo2_pct: { key: 'spo2_pct', label: 'Blood oxygen (SpO₂)', unit: '%', digits: 1, kind: 'line', color: 'var(--c-spo2)', group: 'recovery' },
  skin_temperature_c: { key: 'skin_temperature_c', label: 'Skin temperature', unit: '°C', digits: 1, kind: 'line', color: 'var(--c-temp)', group: 'recovery' },
};

/** Series offered in the Overview trend explorer. */
export const OVERVIEW_SERIES: NightMetricKey[] = [
  'sleep_duration_minutes',
  'sleep_efficiency_pct',
  'resting_heart_rate_bpm',
  'hrv_rmssd_ms',
  'respiratory_rate_rpm',
  'spo2_pct',
];

/** Series offered on the Sleep Trends page. */
export const TREND_PAGE_SERIES: NightMetricKey[] = [
  ...OVERVIEW_SERIES,
  'sleep_consistency_pct',
  'disturbance_count',
  'skin_temperature_c',
];

/** Formats a value for tooltips and readouts, with unit. Missing stays an em dash. */
export function formatSeriesValue(def: SeriesDef, v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  if (def.key === 'sleep_duration_minutes' || def.key === 'deep_sleep_minutes' || def.key === 'rem_sleep_minutes') {
    return formatMinutes(v);
  }
  const n = formatNumber(v, def.digits);
  return def.unit === '%' || def.unit === '°C' ? `${n}${def.unit}` : `${n} ${def.unit}`;
}

/** Window average from the FeatureSet (placeholder `<field>_mean` naming, see metrics.ts). */
export function windowMean(features: FeatureSet, key: NightMetricKey): number | null {
  return features.values[meanFeatureKey(key)] ?? null;
}

export function nightValues(nights: NightRecord[], key: NightMetricKey): Array<number | null> {
  return nights.map((n) => n[key]);
}
