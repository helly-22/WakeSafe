import { Card } from '../../components/Card';
import { SignalStack, type SignalRowData } from '../../components/charts/SignalStack';
import { BASELINE_NIGHTS } from '../../lib/metrics';
import { SERIES, nightValues, windowMean } from '../../lib/series';
import type { AnalyzeResponse, NightMetricKey } from '../../lib/types';

const SIGNALS: NightMetricKey[] = ['resting_heart_rate_bpm', 'hrv_rmssd_ms', 'respiratory_rate_rpm', 'spo2_pct'];

/** Coordinated recovery signals: shared time axis, shared hover, window-average reference. */
export function SignalsPanel({ data, className }: { data: AnalyzeResponse; className?: string }) {
  const { features, nights } = data;

  return (
    <Card
      eyebrow="Recovery signals"
      title="Overnight signals"
      className={className}
      action={
        <p className="key-row">
          <span className="src src--wearable_measured">
            <i className="src__dot" aria-hidden="true" />
            Wearable-measured
          </span>
          <span className="key-row__item">
            <i className="key-dash" aria-hidden="true" /> window average
          </span>
        </p>
      }
    >
      {nights && nights.length > 0 ? (
        <>
          <SignalStack
            rows={SIGNALS.map<SignalRowData>((key) => {
              const def = SERIES[key];
              return {
                key,
                label: def.label,
                unit: def.unit,
                digits: def.digits,
                color: def.color,
                values: nightValues(nights, key),
                mean: windowMean(features, key),
                z: features.baseline_z_scores[key],
              };
            })}
            dates={nights.map((n) => n.date)}
            nightsAvailable={features.nights_available}
            baselineNights={BASELINE_NIGHTS}
          />
        </>
      ) : (
        <p className="empty-note">Nightly records were not included in this response.</p>
      )}
    </Card>
  );
}
