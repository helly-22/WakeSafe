import { formatShortDate, formatTooltipDate } from '../../lib/format';
import { SERIES } from '../../lib/series';
import type { NightMetricKey, NightRecord } from '../../lib/types';

const ROWS: Array<{ key: NightMetricKey; label: string }> = [
  { key: 'sleep_duration_minutes', label: 'Sleep summary' },
  { key: 'resting_heart_rate_bpm', label: 'Resting HR' },
  { key: 'hrv_rmssd_ms', label: 'HRV' },
  { key: 'respiratory_rate_rpm', label: 'Respiratory' },
  { key: 'spo2_pct', label: 'SpO₂' },
  { key: 'skin_temperature_c', label: 'Skin temp' },
];

/**
 * Which signals were recorded on which nights. One filled cell per recorded night,
 * a hollow cell per missing night. Shows at a glance what the screening rests on.
 */
export function CoverageMatrix({ nights }: { nights: NightRecord[] }) {
  const first = nights[0];
  const last = nights[nights.length - 1];

  return (
    <div className="cov" role="table" aria-label="Which signals were recorded on which nights">
      {ROWS.map(({ key, label }) => {
        const recorded = nights.filter((n) => n[key] !== null).length;
        const color = SERIES[key].color;
        return (
          <div className="cov__row" role="row" key={key}>
            <div className="cov__label" role="rowheader">
              <span>{label}</span>
              <span className={`cov__count${recorded < nights.length ? ' cov__count--partial' : ''}`}>
                {recorded}/{nights.length}
              </span>
            </div>
            <div className="cov__cells" style={{ gridTemplateColumns: `repeat(${nights.length}, minmax(0, 1fr))` }}>
              {nights.map((n) => {
                const on = n[key] !== null;
                return (
                  <span
                    key={n.night_id}
                    role="cell"
                    className={`cov__cell${on ? '' : ' cov__cell--off'}`}
                    style={on ? { background: color } : undefined}
                    title={`${formatTooltipDate(n.date)}: ${on ? 'recorded' : 'no data'}`}
                    aria-label={`${label}, ${formatTooltipDate(n.date)}: ${on ? 'recorded' : 'no data'}`}
                  />
                );
              })}
            </div>
          </div>
        );
      })}
      {first && last && (
        <div className="cov__dates" aria-hidden="true">
          <span>{formatShortDate(first.date)}</span>
          <span>{formatShortDate(last.date)}</span>
        </div>
      )}
    </div>
  );
}
