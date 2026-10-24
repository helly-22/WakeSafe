import { Card } from '../../components/Card';
import { formatMinutes, formatNumber, formatWindow } from '../../lib/format';
import { windowMean } from '../../lib/series';
import type { AnalyzeResponse } from '../../lib/types';

/** The four sleep numbers worth seeing at a glance. Missing stays an em dash. */
export function SleepSnapshot({ data, className }: { data: AnalyzeResponse; className?: string }) {
  const f = data.features;
  const duration = windowMean(f, 'sleep_duration_minutes');
  const efficiency = windowMean(f, 'sleep_efficiency_pct');
  const consistency = windowMean(f, 'sleep_consistency_pct');
  const disturbances = windowMean(f, 'disturbance_count');
  const pct = (v: number | null) => (v === null ? '—' : `${formatNumber(v, 0)}%`);

  return (
    <Card eyebrow="Sleep" title="Your average night" className={className} action={<span className="muted-note">{formatWindow(f.window_start, f.window_end)}</span>}>
      <dl className="snap">
        <div>
          <dt>Average sleep</dt>
          <dd>{formatMinutes(duration)}</dd>
        </div>
        <div>
          <dt>Efficiency</dt>
          <dd>{pct(efficiency)}</dd>
        </div>
        <div>
          <dt>Consistency</dt>
          <dd>{pct(consistency)}</dd>
        </div>
        <div>
          <dt>Disturbances</dt>
          <dd>
            {disturbances === null ? '—' : formatNumber(disturbances, 0)}
            {disturbances !== null && <small>/night</small>}
          </dd>
        </div>
      </dl>
    </Card>
  );
}
