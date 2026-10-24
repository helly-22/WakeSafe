import type { NightMetricKey, NightRecord, SourceLabel } from './types';

/** Shown in place of any value that is missing. Never substitute zero. */
export const MISSING = '—';

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return MISSING;
  return value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** 412 -> "6h 52m". */
export function formatMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return MISSING;
  const total = Math.round(minutes);
  return `${Math.floor(total / 60)}h ${String(total % 60).padStart(2, '0')}m`;
}

const SHORT_DATE = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
const LONG_DATE = new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: 'numeric' });

/** Formats a YYYY-MM-DD date without shifting it across time zones. */
export function formatShortDate(isoDate: string | null | undefined): string {
  if (!isoDate) return MISSING;
  return SHORT_DATE.format(new Date(`${isoDate}T00:00:00Z`));
}

const TOOLTIP_DATE = new Intl.DateTimeFormat('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' });

/** "Thu, Oct 16" without time-zone shifting. */
export function formatTooltipDate(isoDate: string): string {
  return TOOLTIP_DATE.format(new Date(`${isoDate}T00:00:00Z`));
}

export function formatToday(now = new Date()): string {
  return LONG_DATE.format(now);
}

export function formatWindow(start: string | null, end: string | null): string {
  if (!start || !end) return 'Data window unavailable';
  return `${formatShortDate(start)} – ${formatShortDate(end)}`;
}

export const SOURCE_LABEL_TEXT: Record<SourceLabel, string> = {
  patient_reported: 'Patient-reported',
  wearable_measured: 'Wearable-measured',
  app_calculated: 'App-calculated',
  model_estimated: 'Model-estimated',
  simulated: 'Simulated',
};

/** Plain-language text for known FeatureSet.data_quality_flags; unknown flags are shown verbatim. */
const QUALITY_FLAG_TEXT: Record<string, string> = {
  insufficient_baseline_history: 'Not enough nights yet for a personal baseline.',
  spo2_unavailable: 'Blood oxygen (SpO₂) was not recorded on any night.',
  spo2_partially_missing: 'Blood oxygen (SpO₂) is missing on some nights.',
  skin_temperature_unavailable: 'Skin temperature was not recorded.',
  sleep_summary_missing_some_nights: 'Sleep summary is missing on some nights.',
};

export function describeQualityFlag(flag: string): string {
  return QUALITY_FLAG_TEXT[flag] ?? flag.replaceAll('_', ' ');
}

/** Pulls one metric across nights, keeping nulls so charts can show gaps. */
export function series(nights: NightRecord[], key: NightMetricKey): Array<number | null> {
  return nights.map((n) => n[key]);
}

export function countPresent(nights: NightRecord[], key: NightMetricKey): number {
  return nights.filter((n) => n[key] !== null).length;
}
