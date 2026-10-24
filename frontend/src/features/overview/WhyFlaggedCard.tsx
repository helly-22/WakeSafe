import { SourceTags } from '../../components/Badges';
import { Card } from '../../components/Card';
import { stripEvidence } from '../../lib/format';
import type { AnalyzeResponse } from '../../lib/types';

/**
 * Text-led explanation per risk, then limitations. Shows the explanation layer's
 * text verbatim and adds no claims of its own. Limitations stay visible.
 */
export function WhyFlaggedCard({ data, className }: { data: AnalyzeResponse; className?: string }) {
  const { explanation, risk_assessment } = data;

  return (
    <Card eyebrow="Explanation" title="Why this was flagged" className={className}>
      {explanation ? (
        <>
          <ul className="risk-explanations">
            {risk_assessment.risks.map((risk) => (
              <li key={risk.risk_id} className="risk-explanations__item">
                <div className="risk-explanations__head">
                  <span className={`tier-mark tier-mark--${risk.tier.toLowerCase()}`}>{risk.tier}</span>
                  <h4 className="risk-explanations__name">{risk.display_name}</h4>
                </div>
                {stripEvidence(explanation.risk_explanations[risk.risk_id] ?? '') && (
                  <p className="lead">{stripEvidence(explanation.risk_explanations[risk.risk_id] ?? '')}</p>
                )}
                <ul className="reasons">
                  {risk.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
                <SourceTags sources={risk.source_labels} />
              </li>
            ))}
          </ul>

          {explanation.limitations.length > 0 && (
            <section className="limits" aria-label="Limitations">
              <h4 className="legend-head">Limitations</h4>
              <ul className="limits__list">
                {explanation.limitations.map((l) => (
                  <li key={l}>{l}</li>
                ))}
              </ul>
            </section>
          )}

          <p className="fineprint">
            {explanation.generated_by === 'template' ? 'Template explanation' : 'AI-assisted explanation'} · rules {risk_assessment.rules_version}
          </p>
        </>
      ) : (
        <p className="muted">No explanation is available for this result.</p>
      )}
    </Card>
  );
}
