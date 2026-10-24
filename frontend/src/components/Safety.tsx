import type { RiskAssessment } from '../lib/types';

export const SCREENING_DISCLAIMER = 'Screening aid only, not a diagnosis. Consider discussing results with a clinician.';

export function Disclaimer({ text = SCREENING_DISCLAIMER }: { text?: string }) {
  return (
    <p className="disclaimer">
      <span aria-hidden="true">ⓘ</span> {text}
    </p>
  );
}

/**
 * Emergency guidance. Rendered before any routine content whenever
 * risk_assessment.urgent_override is true (TEAM_CONTRACTS.md §3.5). This is the
 * only element that uses urgent red styling.
 */
export function UrgentBanner({ assessment }: { assessment: RiskAssessment }) {
  if (!assessment.urgent_override) return null;
  return (
    <section className="urgent" role="alert" aria-labelledby="urgent-title">
      <div className="urgent__icon" aria-hidden="true">
        !
      </div>
      <div>
        <h2 id="urgent-title" className="urgent__title">
          Call 911 now
        </h2>
        <p className="urgent__text">
          You reported a symptom that can be a sign of a medical emergency. Call 911 or your local emergency number
          right away. Do not wait for sleep screening results.
        </p>
        {assessment.urgent_reasons.length > 0 && (
          <ul className="urgent__reasons">
            {assessment.urgent_reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        )}
        <a className="btn btn--urgent" href="tel:911">
          Call 911
        </a>
        <p className="urgent__fineprint">WakeSafe cannot contact emergency services for you.</p>
      </div>
    </section>
  );
}
