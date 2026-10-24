import { Link } from 'react-router';
import { SourceTag } from '../../components/Badges';
import { Card } from '../../components/Card';
import { Disclaimer } from '../../components/Safety';
import type { AnalyzeResponse, ScreeningTier, SourceLabel } from '../../lib/types';
import { primaryScreeningRisk } from './primaryRisk';

const TIERS: ScreeningTier[] = ['Low', 'Moderate', 'High'];
// Provenance is per risk (RiskItem.source_labels), not per factor: ApneaScore.top_factors is plain
// text. Tagging each factor would need a contract change (PROPOSED, not made here).
const ALL_SOURCES: SourceLabel[] = ['patient_reported', 'wearable_measured', 'app_calculated', 'model_estimated'];

/**
 * The screening result. A qualitative three-step tier, deliberately not a ring or a
 * percentage: it must never read as a probability or a performance score. The
 * explanation text leads, then the factors, then provenance.
 */
export function ScreeningOverview({ data, className }: { data: AnalyzeResponse; className?: string }) {
  const { apnea_score: score, risk_assessment: assessment, explanation } = data;
  const risk = primaryScreeningRisk(assessment);
  const tier = score?.tier ?? null;
  const sources = risk?.source_labels ?? [];

  return (
    <Card eyebrow="Screening" title="Sleep-breathing screening" className={`hero-screening ${className ?? ''}`}>
      {assessment.urgent_override && (
        <p className="inline-alert" role="note">
          Urgent symptoms were reported. Follow the emergency guidance above first.
        </p>
      )}

      {tier === null ? (
        <p className="muted">No screening result is available for this data.</p>
      ) : (
        <>
          <div className="tier" role="img" aria-label={`Screening tier: ${tier}, on a scale of Low, Moderate, High. Not a probability.`}>
            <div className="tier__head">
              <p className={`tier__value tier__value--${tier.toLowerCase()}`}>{tier}</p>
              <p className="tier__caption">
                screening tier
                <br />
                <span>not a probability</span>
              </p>
            </div>
            <ol className="tier__scale" aria-hidden="true">
              {TIERS.map((t) => (
                <li key={t} className={`tier__step tier__step--${t.toLowerCase()}${t === tier ? ' tier__step--active' : ''}`}>
                  <span className="tier__bar" />
                  <span className="tier__step-label">{t}</span>
                </li>
              ))}
            </ol>
          </div>

          {explanation && <p className="screening-lead">{explanation.summary}</p>}

          {score && score.top_factors.length > 0 && (
            <section aria-label="Top factors" className="factors">
              <h4 className="legend-head">Top factors</h4>
              <ol className="factors__list">
                {score.top_factors.map((f, i) => (
                  <li key={f}>
                    <span className="factors__n" aria-hidden="true">
                      {i + 1}
                    </span>
                    {f}
                  </li>
                ))}
              </ol>
            </section>
          )}

          <section aria-label="Where this comes from" className="provenance">
            <h4 className="legend-head">Built from</h4>
            <ul className="src-list">
              {ALL_SOURCES.map((s) => (
                <li key={s} className={sources.includes(s) ? '' : 'src-list__off'}>
                  <SourceTag source={s} />
                </li>
              ))}
            </ul>
            <p className="fineprint">
              {risk ? `Evidence: ${risk.evidence_rating}. ` : ''}
              Dimmed sources were not used for this result.
            </p>
          </section>
        </>
      )}

      <div className="next">
        {assessment.urgent_override ? (
          <a className="btn btn--urgent" href="tel:911">
            Call 911
          </a>
        ) : (
          <>
            <p className="next__text">
              Next step: consider discussing these results with a clinician
              {risk ? ` (${risk.suggested_specialty.toLowerCase()})` : ''}.
            </p>
            <Link className="btn" to="/care">
              Find care
            </Link>
          </>
        )}
      </div>

      <Disclaimer text={assessment.disclaimer} />
      {score && <p className="fineprint">{score.evidence_note}</p>}
    </Card>
  );
}
