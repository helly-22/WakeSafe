import { useState } from 'react';
import { BaselineNote } from '../../components/Badges';
import { Card } from '../../components/Card';
import { TrendChart } from '../../components/TrendChart';
import { formatNumber, formatWindow } from '../../lib/format';
import { BASELINE_NIGHTS } from '../../lib/metrics';
import { SERIES, formatSeriesValue, windowMean } from '../../lib/series';
import type { AnalyzeResponse, NightMetricKey } from '../../lib/types';

interface TrendExplorerProps {
  data: AnalyzeResponse;
  series: NightMetricKey[];
  initial?: NightMetricKey;
  eyebrow?: string;
  className?: string;
  height?: number;
}

/** One chart, many series. The headline is the window average; the dashed line repeats it on the chart. */
export function TrendExplorer({ data, series, initial, eyebrow = 'Sleep history', className, height = 240 }: TrendExplorerProps) {
  const [active, setActive] = useState<NightMetricKey>(initial ?? series[0] ?? 'sleep_duration_minutes');
  const { features, nights } = data;
  const def = SERIES[active];
  const mean = windowMean(features, active);
  const groups: Array<{ id: 'sleep' | 'recovery'; label: string }> = [
    { id: 'sleep', label: 'Sleep' },
    { id: 'recovery', label: 'Recovery' },
  ];

  return (
    <Card eyebrow={eyebrow} title={def.label} className={className}>
      <div className="explorer__top">
        <div className="explorer__headline">
          <p className="explorer__num">
            {mean === null ? (
              <span className="explorer__num--missing">Not recorded</span>
            ) : active.endsWith('_minutes') ? (
              formatSeriesValue(def, mean)
            ) : (
              <>
                {formatNumber(mean, def.digits)}
                <small>{def.unit}</small>
              </>
            )}
          </p>
          <p className="explorer__sub">
            Window average · {formatWindow(features.window_start, features.window_end)}
          </p>
          <BaselineNote z={features.baseline_z_scores[active]} nightsAvailable={features.nights_available} baselineNights={BASELINE_NIGHTS} />
        </div>

        <div className="chips" role="tablist" aria-label="Series">
          {groups.map((g) => {
            const keys = series.filter((k) => SERIES[k].group === g.id);
            if (keys.length === 0) return null;
            return (
              <div className="chips__group" key={g.id} role="presentation">
                <span className="chips__label">{g.label}</span>
                {keys.map((k) => (
                  <button
                    key={k}
                    type="button"
                    role="tab"
                    aria-selected={k === active}
                    className={`chip${k === active ? ' chip--active' : ''}`}
                    onClick={() => setActive(k)}
                  >
                    {SERIES[k].label.replace(' (RMSSD)', '').replace('Blood oxygen (SpO₂)', 'SpO₂').replace('Resting heart rate', 'Resting HR')}
                  </button>
                ))}
              </div>
            );
          })}
        </div>
      </div>

      {nights && nights.length > 0 ? (
        <TrendChart
          key={active}
          points={nights.map((n) => ({ date: n.date, value: n[active] }))}
          kind={def.kind}
          format={(v) => formatSeriesValue(def, v)}
          axisFormat={def.axisFormat}
          tickStep={def.tickStep}
          color={def.color}
          height={height}
          title={def.label}
          reference={mean === null ? null : { value: mean, label: `avg ${active.endsWith('_minutes') ? formatSeriesValue(def, mean) : formatNumber(mean, def.digits)}` }}
        />
      ) : (
        <p className="empty-note">Nightly records were not included in this response.</p>
      )}

      <p className="fineprint">
        <span className="src src--wearable_measured">
          <i className="src__dot" aria-hidden="true" />
          Wearable-measured
        </span>{' '}
        · Shaded nights have no data. Hover or use the arrow keys to read a night.
      </p>
    </Card>
  );
}
