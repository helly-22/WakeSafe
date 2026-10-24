import { useElementWidth } from '../hooks/useElementWidth';
import { useSlotHover } from '../hooks/useSlotHover';
import { formatNumber, formatShortDate, formatTooltipDate } from '../lib/format';

export interface TrendPoint {
  date: string;
  value: number | null;
}

export interface TrendReference {
  value: number;
  /** Short label drawn at the right end of the dashed line, e.g. "window avg 64". */
  label: string;
}

interface TrendChartProps {
  points: TrendPoint[];
  kind?: 'bar' | 'line';
  /** Formats values for the tooltip and screen-reader table. */
  format?: (v: number | null) => string;
  /** Formats y-axis tick labels; defaults to `format`. */
  axisFormat?: (v: number) => string;
  /** Fixed y-axis tick step (e.g. 120 minutes); otherwise a round step is chosen. */
  tickStep?: number;
  color?: string;
  height?: number;
  title: string;
  reference?: TrendReference | null;
}

const PAD = { top: 14, right: 64, bottom: 28, left: 48 };

/** Rounds a raw step to 1, 2, 2.5 or 5 x 10^k so axis labels land on readable values. */
export function niceStep(raw: number): number {
  if (raw <= 0) return 1;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const f = raw / pow;
  const nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
  return nice * pow;
}

/**
 * Evenly spaced date-label indices at a constant stride, anchored to the most
 * recent night so the latest date is always labeled.
 */
export function labelIndices(count: number, maxLabels: number): Set<number> {
  const out = new Set<number>();
  if (count === 0) return out;
  const stride = Math.max(1, Math.ceil(count / Math.max(1, maxLabels)));
  for (let i = count - 1; i >= 0; i -= stride) out.add(i);
  return out;
}

/**
 * Nightly chart with hover and keyboard inspection. Missing nights are shaded
 * and marked, never drawn as zero. A visually hidden table carries the same
 * data for screen readers.
 */
export function TrendChart({
  points,
  kind = 'bar',
  format = (v) => formatNumber(v),
  axisFormat,
  tickStep,
  color = 'var(--teal)',
  height = 220,
  title,
  reference = null,
}: TrendChartProps) {
  const [figureRef, W] = useElementWidth<HTMLElement>(640);
  // Wide charts reserve a right margin for the average label; narrow ones show only the dashed line
  // (the headline above the chart already states the average).
  const wide = W >= 520;
  const pad = { ...PAD, right: wide ? 84 : 16 };
  const { active, slot, handlers } = useSlotHover(points.length, W, pad.left, pad.right);

  const present = points.map((p) => p.value).filter((v): v is number => v !== null);
  if (present.length === 0) {
    return <p className="empty-note">No nightly values available for {title.toLowerCase()}.</p>;
  }

  const domainValues = reference ? [...present, reference.value] : present;
  const rawMin = Math.min(...domainValues);
  const rawMax = Math.max(...domainValues);
  const floor = kind === 'bar' ? Math.min(0, rawMin) : rawMin;
  const step = tickStep ?? niceStep((rawMax - floor || Math.abs(rawMax) || 1) / 3);
  const lo = Math.floor(floor / step) * step;
  const hi = Math.max(Math.ceil(rawMax / step) * step, lo + step);
  const ticks: number[] = [];
  for (let g = lo; g <= hi + step / 2; g += step) ticks.push(+g.toFixed(6));
  const tickLabel = axisFormat ?? ((v: number) => format(v));

  const innerW = W - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const y = (v: number) => pad.top + (1 - (v - lo) / (hi - lo)) * innerH;
  const cx = (i: number) => pad.left + slot * i + slot / 2;
  const baseY = y(lo);
  const barW = Math.max(Math.min(slot * 0.58, 30), 3);
  const xLabels = labelIndices(points.length, Math.max(2, Math.floor(innerW / 84)));

  // Contiguous runs of present values so gaps stay visible in line charts.
  const runs: string[][] = [[]];
  points.forEach((p, i) => {
    if (p.value === null) {
      if (runs[runs.length - 1]?.length) runs.push([]);
    } else {
      runs[runs.length - 1]?.push(`${cx(i).toFixed(1)},${y(p.value).toFixed(1)}`);
    }
  });

  const activePoint = active === null ? null : (points[active] ?? null);
  const tipLeft = active === null ? 0 : Math.min(Math.max(cx(active), 64), W - 64);

  return (
    <figure className="trend" ref={figureRef}>
      <div
        className="trend__stage"
        tabIndex={0}
        role="group"
        aria-label={`${title} by night. Use the left and right arrow keys to inspect a night.`}
        {...handlers}
      >
        <svg viewBox={`0 0 ${W} ${height}`} width={W} height={height} className="trend__svg" aria-hidden="true">
          {ticks.map((g) => (
            <g key={g}>
              <line x1={pad.left} x2={W - pad.right} y1={y(g)} y2={y(g)} className="trend__grid" />
              <text x={pad.left - 10} y={y(g) + 4} className="trend__axis" textAnchor="end">
                {tickLabel(g)}
              </text>
            </g>
          ))}

          {points.map((p, i) =>
            p.value === null ? (
              <g key={`m-${p.date}`}>
                <rect x={pad.left + slot * i} y={pad.top} width={slot} height={innerH} className="trend__missing-band" />
                <circle cx={cx(i)} cy={baseY - 9} r={3.5} className="trend__missing-dot" />
              </g>
            ) : null,
          )}

          {reference && (
            <g>
              <line x1={pad.left} x2={W - pad.right + (wide ? 6 : 0)} y1={y(reference.value)} y2={y(reference.value)} className="trend__ref" />
              {wide && (
                <text x={W - pad.right + 12} y={y(reference.value) + 4} className="trend__ref-label">
                  {reference.label}
                </text>
              )}
            </g>
          )}

          {active !== null && <line x1={cx(active)} x2={cx(active)} y1={pad.top} y2={baseY} className="trend__guide" />}

          {kind === 'bar' &&
            points.map((p, i) => {
              if (p.value === null) return null;
              const top = y(p.value);
              const dim = active !== null && active !== i;
              return (
                <rect
                  key={p.date}
                  x={cx(i) - barW / 2}
                  y={top}
                  width={barW}
                  height={Math.max(baseY - top, 1)}
                  rx={Math.min(4, barW / 2)}
                  fill={color}
                  className="trend__bar"
                  opacity={dim ? 0.45 : 1}
                />
              );
            })}

          {kind === 'line' && (
            <>
              {runs
                .filter((run) => run.length > 1)
                .map((run) => (
                  <polyline key={run[0]} points={run.join(' ')} fill="none" stroke={color} className="trend__line" />
                ))}
              {points.map((p, i) =>
                p.value === null ? null : (
                  <circle key={p.date} cx={cx(i)} cy={y(p.value)} r={active === i ? 5 : 2.6} fill={color} className="trend__dot" />
                ),
              )}
            </>
          )}

          {points.map((p, i) =>
            xLabels.has(i) ? (
              <text key={`x-${p.date}`} x={cx(i)} y={height - 8} className="trend__axis" textAnchor="middle">
                {formatShortDate(p.date)}
              </text>
            ) : null,
          )}
        </svg>

        {activePoint && (
          <div className="tooltip" style={{ left: tipLeft }} role="presentation">
            <span className="tooltip__date">{formatTooltipDate(activePoint.date)}</span>
            <span className={`tooltip__value${activePoint.value === null ? ' tooltip__value--missing' : ''}`}>
              {activePoint.value === null ? 'No data recorded' : format(activePoint.value)}
            </span>
          </div>
        )}
      </div>

      <p className="visually-hidden" aria-live="polite">
        {activePoint
          ? `${formatTooltipDate(activePoint.date)}: ${activePoint.value === null ? 'no data recorded' : format(activePoint.value)}`
          : ''}
      </p>

      <div className="visually-hidden">
        <table>
        <caption>{title}</caption>
        <thead>
          <tr>
            <th scope="col">Night</th>
            <th scope="col">Value</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.date}>
              <td>{formatTooltipDate(p.date)}</td>
              <td>{p.value === null ? 'No data recorded' : format(p.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </figure>
  );
}
