import { useRef } from 'react';
import { useElementWidth } from '../../hooks/useElementWidth';
import { useSlotHover } from '../../hooks/useSlotHover';
import { formatNumber, formatShortDate, formatTooltipDate } from '../../lib/format';
import { BaselineNote } from '../Badges';
import { labelIndices } from '../TrendChart';

export interface SignalRowData {
  key: string;
  label: string;
  unit: string;
  digits: number;
  color: string;
  values: Array<number | null>;
  /** Window average from the FeatureSet; drawn as a dashed reference line. */
  mean: number | null;
  /** Personal-baseline z-score from the FeatureSet, if available. */
  z: number | null | undefined;
}

interface SignalStackProps {
  rows: SignalRowData[];
  dates: string[];
  nightsAvailable: number;
  baselineNights: number;
}

const PLOT_H = 72;
const PAD_Y = 12;
const PAD_L = 30;
const PAD_R = 10;
const AXIS_H = 26;

/**
 * Small multiples sharing one time axis and one hover position. Hover or arrow-key
 * to a night and every row shows that night's value. Each row has its own y scale
 * (no cross-signal comparison is implied); the dashed line is the window average.
 */
export function SignalStack({ rows, dates, nightsAvailable, baselineNights }: SignalStackProps) {
  const [plotRef, W] = useElementWidth<HTMLDivElement>(560);
  const wrapRef = useRef<HTMLDivElement>(null);
  const { active, slot, handlers } = useSlotHover(dates.length, W, PAD_L, PAD_R, plotRef);
  const cx = (i: number) => PAD_L + slot * i + slot / 2;
  const xLabels = labelIndices(dates.length, Math.max(2, Math.floor((W - PAD_L - PAD_R) / 84)));
  const activeDate = active === null ? null : (dates[active] ?? null);
  const guideLeft = active === null ? 0 : (plotRef.current?.offsetLeft ?? 0) + cx(active);

  return (
    <div
      className="signals"
      ref={wrapRef}
      tabIndex={0}
      role="group"
      aria-label="Overnight signals by night. Use the left and right arrow keys to inspect a night."
      {...handlers}
    >
      <div className="signals__grid">
        {rows.map((row, r) => {
          const present = row.values.filter((v): v is number => v !== null);
          const recorded = present.length;
          const total = row.values.length;
          const hovered = active === null ? undefined : row.values[active];
          const shown = active === null ? row.mean : (hovered ?? null);
          const hasData = recorded > 0;

          let lo = 0;
          let hi = 1;
          if (hasData) {
            const extent = row.mean === null ? present : [...present, row.mean];
            const min = Math.min(...extent);
            const max = Math.max(...extent);
            const pad = (max - min || Math.abs(max) * 0.05 || 1) * 0.18;
            lo = min - pad;
            hi = max + pad;
          }
          const y = (v: number) => PAD_Y + (1 - (v - lo) / (hi - lo)) * (PLOT_H - PAD_Y * 2);

          const runs: string[][] = [[]];
          row.values.forEach((v, i) => {
            if (v === null) {
              if (runs[runs.length - 1]?.length) runs.push([]);
            } else {
              runs[runs.length - 1]?.push(`${cx(i).toFixed(1)},${y(v).toFixed(1)}`);
            }
          });

          return (
            <div key={row.key} className={`signals__row${r > 0 ? ' signals__row--sep' : ''}`}>
              <div className="signals__meta">
                <span className="signals__label">{row.label}</span>
                {hasData ? (
                  <BaselineNote z={row.z} nightsAvailable={nightsAvailable} baselineNights={baselineNights} />
                ) : (
                  <span className="baseline baseline--none">Not recorded on any night</span>
                )}
                {hasData && recorded < total && (
                  <span className="signals__coverage">
                    Recorded {recorded} of {total} nights
                  </span>
                )}
              </div>

              <div className="signals__value">
                <span className={`signals__num${shown === null ? ' signals__num--missing' : ''}`}>
                  {shown === null ? (active !== null ? 'No data' : '—') : formatNumber(shown, row.digits)}
                  {shown !== null && <span className="signals__unit">{row.unit}</span>}
                </span>
                <span className="signals__sub">{activeDate ? formatShortDate(activeDate) : 'window avg'}</span>
              </div>

              <div className="signals__plot" ref={r === 0 ? plotRef : undefined}>
                <svg width={W} height={PLOT_H} viewBox={`0 0 ${W} ${PLOT_H}`} aria-hidden="true">
                  {!hasData ? (
                    <line x1={PAD_L} x2={W - PAD_R} y1={PLOT_H / 2} y2={PLOT_H / 2} className="signals__empty-line" />
                  ) : (
                    <>
                      {row.values.map((v, i) =>
                        v === null ? (
                          <g key={`m-${dates[i] ?? i}`}>
                            <rect x={PAD_L + slot * i} y={0} width={slot} height={PLOT_H} className="trend__missing-band" />
                            <circle cx={cx(i)} cy={PLOT_H - 9} r={3} className="trend__missing-dot" />
                          </g>
                        ) : null,
                      )}
                      {row.mean !== null && (
                        <line x1={PAD_L} x2={W - PAD_R} y1={y(row.mean)} y2={y(row.mean)} className="trend__ref" />
                      )}
                      {runs
                        .filter((run) => run.length > 1)
                        .map((run) => (
                          <polyline key={run[0]} points={run.join(' ')} fill="none" stroke={row.color} className="trend__line" />
                        ))}
                      {row.values.map((v, i) =>
                        v === null ? null : (
                          <circle key={dates[i] ?? i} cx={cx(i)} cy={y(v)} r={active === i ? 4.5 : 2.2} fill={row.color} className="trend__dot" />
                        ),
                      )}
                      <text x={PAD_L - 8} y={y(Math.max(...present)) + 3.5} className="trend__axis trend__axis--sm" textAnchor="end">
                        {formatNumber(Math.max(...present), row.digits)}
                      </text>
                      {Math.min(...present) !== Math.max(...present) && (
                        <text x={PAD_L - 8} y={y(Math.min(...present)) + 3.5} className="trend__axis trend__axis--sm" textAnchor="end">
                          {formatNumber(Math.min(...present), row.digits)}
                        </text>
                      )}
                    </>
                  )}
                </svg>
              </div>
            </div>
          );
        })}

        <div className="signals__row signals__row--axis">
          <div className="signals__meta" />
          <div className="signals__value" />
          <div className="signals__plot">
            <svg width={W} height={AXIS_H} viewBox={`0 0 ${W} ${AXIS_H}`} aria-hidden="true">
              {dates.map((d, i) =>
                xLabels.has(i) ? (
                  <text key={d} x={cx(i)} y={17} className="trend__axis" textAnchor="middle">
                    {formatShortDate(d)}
                  </text>
                ) : null,
              )}
            </svg>
          </div>
        </div>
      </div>

      {active !== null && <div className="signals__guide" style={{ left: guideLeft }} aria-hidden="true" />}

      <p className="visually-hidden" aria-live="polite">
        {activeDate
          ? `${formatTooltipDate(activeDate)}: ${rows
              .map((row) => {
                const v = row.values[active ?? 0];
                return `${row.label} ${v === null || v === undefined ? 'no data' : `${formatNumber(v, row.digits)} ${row.unit}`}`;
              })
              .join(', ')}`
          : ''}
      </p>

      <div className="visually-hidden">
        <table>
        <caption>Overnight signals by night</caption>
        <thead>
          <tr>
            <th scope="col">Night</th>
            {rows.map((row) => (
              <th key={row.key} scope="col">
                {row.label} ({row.unit})
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {dates.map((d, i) => (
            <tr key={d}>
              <td>{formatTooltipDate(d)}</td>
              {rows.map((row) => {
                const v = row.values[i];
                return <td key={row.key}>{v === null || v === undefined ? 'No data recorded' : formatNumber(v, row.digits)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}
