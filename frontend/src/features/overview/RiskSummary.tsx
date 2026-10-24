import { Link } from 'react-router';
import { useSession } from '../../hooks/useSession';
import type { AnalyzeResponse, ScreeningTier } from '../../lib/types';
import { completionOf, useQuestionnaires } from '../questionnaire/QuestionnaireContext';
import { primaryScreeningRisk } from './primaryRisk';

const TIERS: ScreeningTier[] = ['Low', 'Moderate', 'High'];

/**
 * The estimated sleep apnea risk, first thing under the page title. A Low, Moderate
 * or High level, never a percentage. When no estimate exists for the current
 * answers it says so plainly instead of showing an old or invented one.
 */
export function RiskSummary({ data }: { data: AnalyzeResponse }) {
  const { analysis, persona } = useSession();
  const q = useQuestionnaires();
  const screening = analysis.status === 'ready' ? analysis.screening : 'demo';
  const { apnea_score: score, risk_assessment: assessment } = data;
  const risk = primaryScreeningRisk(assessment);
  const tier = score?.tier ?? null;
  const status = completionOf(persona ? q.get(persona.persona_id) : undefined);
  const edit = persona ? `/intake?edit=${persona.persona_id}` : '/intake';
  const why = risk?.reasons[0];

  return (
    <section className="panel risk" aria-labelledby="risk-title">
      <h2 id="risk-title" className="risk__label">
        Estimated sleep apnea risk
      </h2>

      {tier !== null ? (
        <>
          <div className="tier" role="img" aria-label={`Estimated sleep apnea risk: ${tier}, on a scale of Low, Moderate, High.`}>
            <div className="tier__head">
              <p className={`tier__value tier__value--${tier.toLowerCase()}`}>{tier}</p>
              <p className="tier__caption">Screening is not a diagnosis.</p>
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
          {why && <p className="risk__why">{why}</p>}
          <div className="next">
            {assessment.urgent_override ? (
              <a className="btn btn--urgent" href="tel:911">
                Call 911
              </a>
            ) : (
              <>
                <p className="next__text">
                  Next step: consider discussing this with a clinician{risk ? ` (${risk.suggested_specialty.toLowerCase()})` : ''}.
                </p>
                <Link className="btn" to="/care">
                  Find care
                </Link>
              </>
            )}
          </div>
        </>
      ) : (
        <div className="rerun" role="status">
          <p className="rerun__title">{screening === 'not_rerun' ? 'Risk estimate unavailable' : 'No risk estimate yet'}</p>
          <p>
            {screening === 'not_rerun'
              ? 'Your answers are saved, but we couldn’t update your estimate right now.'
              : status === 'complete'
                ? 'An estimate isn’t available for this profile right now.'
                : 'Complete the health questionnaire to get your estimate.'}
          </p>
          <Link to={edit}>{status === 'not_started' ? 'Start the questionnaire' : 'Edit your answers'}</Link>
          <p className="rerun__note">Screening is not a diagnosis.</p>
        </div>
      )}
    </section>
  );
}
