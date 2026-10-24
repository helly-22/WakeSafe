import { Card } from '../../components/Card';
import { CoverageMatrix } from '../../components/charts/CoverageMatrix';
import { describeQualityFlag } from '../../lib/format';
import { BASELINE_NIGHTS } from '../../lib/metrics';
import type { AnalyzeResponse } from '../../lib/types';

/** What the screening rests on: a night-by-signal matrix, baseline progress and quality flags. */
export function DataCoverageCard({ data, className }: { data: AnalyzeResponse; className?: string }) {
  const { features, nights, data_provenance } = data;
  const total = features.nights_available;
  const baselineReady = total >= BASELINE_NIGHTS;
  const progress = Math.min(total / BASELINE_NIGHTS, 1);

  return (
    <Card eyebrow="Data coverage" title="What this is based on" className={className}>
      {nights && nights.length > 0 ? (
        <CoverageMatrix nights={nights} />
      ) : (
        <p className="muted small">
          SpO₂ on {features.nights_with_spo2} of {total} nights.
        </p>
      )}

      <div className="baseline-progress">
        <div className="baseline-progress__row">
          <span>Personal baseline</span>
          <b>
            {total} of {BASELINE_NIGHTS} nights
          </b>
        </div>
        <div className="baseline-progress__track" role="img" aria-label={`${total} of ${BASELINE_NIGHTS} nights toward a personal baseline`}>
          <span className={baselineReady ? 'is-ready' : ''} style={{ width: `${progress * 100}%` }} />
        </div>
        <p className="fineprint">{baselineReady ? 'Enough nights for baseline comparisons.' : 'Not enough nights yet for baseline comparisons.'}</p>
      </div>

      {features.data_quality_flags.length > 0 ? (
        <ul className="flags">
          {features.data_quality_flags.map((f) => (
            <li key={f} className="flags__item">
              <span aria-hidden="true" className="flags__mark" />
              {describeQualityFlag(f)}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted small">No data-quality warnings.</p>
      )}

      <p className="fineprint">
        Data source: {data_provenance.length ? data_provenance.join(', ') : 'unknown'}
        {data_provenance.includes('synthetic') && ' (illustrative, not real patient data)'}
      </p>
    </Card>
  );
}
