import type { NightMetricKey, NightRecord } from '../../lib/types';

/**
 * Plain counts of nights, from the nights the screening was given. Each recorded
 * night is compared with the person's own average over the same nights. This is a
 * descriptive count, not a clinical threshold and not a risk score; missing nights
 * are never counted and never estimated.
 */
export interface SignalSpec {
  key: NightMetricKey;
  label: string;
  side: 'above' | 'below';
}

export const SIGNALS: SignalSpec[] = [
  { key: 'resting_heart_rate_bpm', label: 'Resting heart rate above your average', side: 'above' },
  { key: 'hrv_rmssd_ms', label: 'HRV below your average', side: 'below' },
  { key: 'respiratory_rate_rpm', label: 'Respiratory rate above your average', side: 'above' },
  { key: 'spo2_pct', label: 'Blood oxygen (SpO₂) below your average', side: 'below' },
];

/** Fewest recorded nights needed before nights are compared with an average. */
export const MIN_NIGHTS_TO_COMPARE = 3;

export type NightState = 'hit' | 'clear' | 'missing' | 'unscored';

export interface NightMark {
  date: string;
  state: NightState;
  value: number | null;
}

export interface SignalCount {
  spec: SignalSpec;
  marks: NightMark[];
  hits: number;
  recorded: number;
  total: number;
  average: number | null;
  comparable: boolean;
}

export function countSignal(nights: NightRecord[], spec: SignalSpec): SignalCount {
  const values = nights.map((n) => n[spec.key]);
  const present = values.filter((v): v is number => v !== null);
  const average = present.length ? present.reduce((a, b) => a + b, 0) / present.length : null;
  const comparable = present.length >= MIN_NIGHTS_TO_COMPARE && average !== null;

  const marks = nights.map<NightMark>((n, i) => {
    const value = values[i] ?? null;
    if (value === null) return { date: n.date, state: 'missing', value };
    if (!comparable || average === null) return { date: n.date, state: 'unscored', value };
    const hit = spec.side === 'above' ? value > average : value < average;
    return { date: n.date, state: hit ? 'hit' : 'clear', value };
  });

  return {
    spec,
    marks,
    hits: marks.filter((m) => m.state === 'hit').length,
    recorded: present.length,
    total: nights.length,
    average,
    comparable,
  };
}
