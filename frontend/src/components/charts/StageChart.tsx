import { useElementWidth } from '../../hooks/useElementWidth';
import { useSlotHover } from '../../hooks/useSlotHover';
import { formatMinutes, formatShortDate, formatTooltipDate } from '../../lib/format';
import type { NightRecord } from '../../lib/types';
import { labelIndices } from '../TrendChart';

const PAD = { top: 14, right: 16, bottom: 28, left: 48 };
const HEIGHT = 300;

interface Night {
  date: string;
  total: number | null;
  deep: number | null;
  rem: number | null;
  /** duration - deep - REM; null when the stage split is not recorded. */
  other: number | null;
}

function toNight(n: NightRecord): Night {
  const { sleep_duration_minutes: total, deep_sleep_minutes: deep, rem_sleep_minutes: rem } = n;
  const other = total !== null && deep !== null && rem !== null && total - deep - rem >= 0 ? total - deep - rem : null;
  return { date: n.date, total, deep, rem, other };
}

/**
 * Nightly sleep split into deep, REM and the remainder. "Other" is app-calculated
 * (duration minus deep minus REM); light sleep is not reported separately here.
 */
export function StageChart({ nights }: { nights: NightRecord[] }) {
  const data = nights.map(toNight);
  const [ref, W] = useElementWidth<HTMLElement>(640);
  const { active, slot, handlers } = useSlotHover(data.length, W, PAD.left, PAD.right);

  const max = Math.max(0, ...data.map((d) => d.total ?? 0));
  if (max === 0) return <p className="empty-note">No nightly sleep durations are available.</p>;

  const hi = Math.ceil(max / 120) * 120;
  const innerH = HEIGHT - PAD.top - PAD.bottom;
  const y = (v: number) => PAD.top + (1 - v / hi) * innerH;
  const baseY = y(0);
  const cx = (i: number) => PAD.left + slot * i + slot / 2;
  const barW = Math.max(Math.min(slot * 0.58, 30), 3);
  const xLabels = labelIndices(data.length, Math.max(2, Math.floor((W - PAD.left - PAD.right) / 84)));
  const ticks: number[] = [];
  for (let g = 0; g <= hi; g += 120) ticks.push(g);

  const activeNight = active === null ? null : (data[active] ?? null);
  const tipLeft = active === null ? 0 : Math.min(Math.max(cx(active), 84), W - 84);

  return (
    <figure className="trend" ref={ref}>
      <ul className="legend-row" aria-label="Legend">
        <li>
          <i className="swatch" style={{ background: 'var(--c-deep)' }} /> Deep
        </li>
        <li>
          <i className="swatch" style={{ background: 'var(--c-rem)' }} /> REM
        </li>
        <li>
          <i className="swatch" style={{ background: 'var(--c-other)' }} /> Other (duration − deep − REM)
        </li>
      </ul>

      <div className="trend__stage" tabIndex={0} role="group" aria-label="Sleep stages by night. Use the left and right arrow keys to inspect a night." {...handlers}>
        <svg viewBox={`0 0 ${W} ${HEIGHT}`} width={W} height={HEIGHT} className="trend__svg" aria-hidden="true">
          {ticks.map((g) => (
            <g key={g}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(g)} y2={y(g)} className="trend__grid" />
              <text x={PAD.left - 10} y={y(g) + 4} className="trend__axis" textAnchor="end">
                {g / 60}h
              </text>
            </g>
          ))}

          {data.map((d, i) => {
            const dim = active !== null && active !== i;
            const x = cx(i) - barW / 2;
            if (d.total === null) {
              return (
                <g key={d.date}>
                  <rect x={PAD.left + slot * i} y={PAD.top} width={slot} height={innerH} className="trend__missing-band" />
                  <circle cx={cx(i)} cy={baseY - 9} r={3.5} className="trend__missing-dot" />
                </g>
              );
            }
            const parts =
              d.other !== null && d.deep !== null && d.rem !== null
                ? [
                    { v: d.deep, c: 'var(--c-deep)' },
                    { v: d.rem, c: 'var(--c-rem)' },
                    { v: d.other, c: 'var(--c-other)' },
                  ]
                : [{ v: d.total, c: 'var(--c-other)' }];
            let acc = 0;
            return (
              <g key={d.date} opacity={dim ? 0.45 : 1}>
                {parts.map((p, k) => {
                  const top = y(acc + p.v);
                  const h = y(acc) - top;
                  acc += p.v;
                  return <rect key={k} x={x} y={top} width={barW} height={Math.max(h - 1, 0.5)} fill={p.c} rx={k === parts.length - 1 ? Math.min(4, barW / 2) : 0} />;
                })}
              </g>
            );
          })}

          {data.map((d, i) =>
            xLabels.has(i) ? (
              <text key={`x-${d.date}`} x={cx(i)} y={HEIGHT - 8} className="trend__axis" textAnchor="middle">
                {formatShortDate(d.date)}
              </text>
            ) : null,
          )}
        </svg>

        {activeNight && (
          <div className="tooltip tooltip--stack" style={{ left: tipLeft }} role="presentation">
            <span className="tooltip__date">{formatTooltipDate(activeNight.date)}</span>
            {activeNight.total === null ? (
              <span className="tooltip__value tooltip__value--missing">No data recorded</span>
            ) : (
              <>
                <span className="tooltip__value">{formatMinutes(activeNight.total)} total</span>
                {activeNight.other !== null ? (
                  <span className="tooltip__detail">
                    Deep {formatMinutes(activeNight.deep)} · REM {formatMinutes(activeNight.rem)} · Other {formatMinutes(activeNight.other)}
                  </span>
                ) : (
                  <span className="tooltip__detail">Stage split not recorded</span>
                )}
              </>
            )}
          </div>
        )}
      </div>

      <div className="visually-hidden">
        <table>
        <caption>Sleep stages by night</caption>
        <thead>
          <tr>
            <th scope="col">Night</th>
            <th scope="col">Total</th>
            <th scope="col">Deep</th>
            <th scope="col">REM</th>
            <th scope="col">Other</th>
          </tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.date}>
              <td>{formatTooltipDate(d.date)}</td>
              <td>{d.total === null ? 'No data recorded' : formatMinutes(d.total)}</td>
              <td>{d.deep === null ? '—' : formatMinutes(d.deep)}</td>
              <td>{d.rem === null ? '—' : formatMinutes(d.rem)}</td>
              <td>{d.other === null ? '—' : formatMinutes(d.other)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </figure>
  );
}
