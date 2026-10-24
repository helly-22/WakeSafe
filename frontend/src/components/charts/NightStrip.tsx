import { formatMinutes, formatShortDate, formatTooltipDate } from '../../lib/format';
import type { NightRecord } from '../../lib/types';

/**
 * A compact row of nightly sleep-duration bars, scaled from zero to the longest
 * night. Missing nights are hollow dashed stubs, never zero-height bars. Values
 * are available on hover (title) and in the accessible list.
 */
export function NightStrip({ nights }: { nights: NightRecord[] }) {
  const max = Math.max(0, ...nights.map((n) => n.sleep_duration_minutes ?? 0));
  const first = nights[0];
  const last = nights[nights.length - 1];
  if (max === 0 || !first || !last) return null;

  return (
    <div className="strip">
      <div className="strip__head">
        <h4 className="legend-head">Nightly sleep duration</h4>
        <span className="muted-note">longest night {formatMinutes(max)}</span>
      </div>
      <ul className="strip__bars" style={{ gridTemplateColumns: `repeat(${nights.length}, minmax(0, 1fr))` }}>
        {nights.map((n) => {
          const v = n.sleep_duration_minutes;
          const label = `${formatTooltipDate(n.date)}: ${v === null ? 'no data recorded' : formatMinutes(v)}`;
          return (
            <li key={n.night_id} title={label} aria-label={label}>
              {v === null ? (
                <span className="strip__bar strip__bar--missing" />
              ) : (
                <span className="strip__bar" style={{ height: `${Math.max((v / max) * 100, 4)}%` }} />
              )}
            </li>
          );
        })}
      </ul>
      <div className="strip__dates" aria-hidden="true">
        <span>{formatShortDate(first.date)}</span>
        <span>{formatShortDate(last.date)}</span>
      </div>
    </div>
  );
}
