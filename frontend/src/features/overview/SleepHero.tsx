import { BaselineNote } from '../../components/Badges';
import { NightStrip } from '../../components/charts/NightStrip';
import { SleepRings } from '../../components/charts/SleepRings';
import { Card } from '../../components/Card';
import { countPresent, formatMinutes, formatNumber, formatWindow } from '../../lib/format';
import { BASELINE_NIGHTS } from '../../lib/metrics';
import { windowMean } from '../../lib/series';
import type { AnalyzeResponse } from '../../lib/types';

/**
 * The sleep anchor: layered rings on the left, a legend that says exactly what each
 * ring means on the right. Efficiency and duration are shown separately, and no
 * target or performance score is implied.
 */
export function SleepHero({ data, className }: { data: AnalyzeResponse; className?: string }) {
  const { features, nights } = data;
  const efficiency = windowMean(features, 'sleep_efficiency_pct');
  const duration = windowMean(features, 'sleep_duration_minutes');
  const deep = windowMean(features, 'deep_sleep_minutes');
  const rem = windowMean(features, 'rem_sleep_minutes');
  const consistency = windowMean(features, 'sleep_consistency_pct');
  const disturbances = windowMean(features, 'disturbance_count');
  const other = duration !== null && deep !== null && rem !== null && duration - deep - rem >= 0 ? duration - deep - rem : null;
  const sleepNights = nights ? countPresent(nights, 'sleep_duration_minutes') : null;
  const z = features.baseline_z_scores;

  return (
    <Card
      eyebrow="Sleep"
      title="Average night"
      className={`hero-sleep ${className ?? ''}`}
      action={
        <span className="muted-note">
          {formatWindow(features.window_start, features.window_end)}
          {sleepNights !== null && ` · ${sleepNights} of ${features.nights_available} nights`}
        </span>
      }
    >
      <div className="hero-sleep__body">
        <div className="hero-sleep__rings">
          <SleepRings efficiency={efficiency} durationMinutes={duration} deepMinutes={deep} remMinutes={rem} />
          <BaselineNote z={z.sleep_duration_minutes} nightsAvailable={features.nights_available} baselineNights={BASELINE_NIGHTS} />
        </div>

        <div className="hero-sleep__legend">
          <section aria-label="Sleep efficiency">
            <h4 className="legend-head">
              <i className="swatch swatch--line" style={{ background: 'var(--c-efficiency)' }} />
              Efficiency · outer ring
            </h4>
            <p className="legend-stat">
              <span className="legend-stat__num">{efficiency === null ? '—' : formatNumber(efficiency, 0)}</span>
              <span className="legend-stat__unit">{efficiency === null ? 'Not recorded' : '% of time in bed asleep'}</span>
            </p>
            <BaselineNote z={z.sleep_efficiency_pct} nightsAvailable={features.nights_available} baselineNights={BASELINE_NIGHTS} quietWhenUnavailable />
          </section>

          <section aria-label="Where average sleep went">
            <h4 className="legend-head">Where average sleep went · inner ring</h4>
            <ul className="stage-list">
              <li>
                <i className="swatch" style={{ background: 'var(--c-deep)' }} />
                <span>Deep</span>
                <b>{formatMinutes(deep)}</b>
              </li>
              <li>
                <i className="swatch" style={{ background: 'var(--c-rem)' }} />
                <span>REM</span>
                <b>{formatMinutes(rem)}</b>
              </li>
              <li title="Average duration minus deep minus REM. Light sleep is not reported separately in this data.">
                <i className="swatch" style={{ background: 'var(--c-other)' }} />
                <span>Other</span>
                <b>{formatMinutes(other)}</b>
              </li>
            </ul>
            <p className="fineprint">Other = duration − deep − REM, calculated by the app.</p>
          </section>

          <dl className="mini-stats">
            <div>
              <dt>Consistency</dt>
              <dd>
                {consistency === null ? '—' : formatNumber(consistency, 0)}
                <small>{consistency === null ? '' : '%'}</small>
              </dd>
            </div>
            <div>
              <dt>Disturbances</dt>
              <dd>
                {disturbances === null ? '—' : formatNumber(disturbances, 0)}
                <small>{disturbances === null ? '' : '/night'}</small>
              </dd>
            </div>
          </dl>
        </div>
      </div>

      {nights && nights.length > 0 && <NightStrip nights={nights} />}
    </Card>
  );
}
