import { SourceTags } from '../../components/Badges';
import type { AnalyzeResponse } from '../../lib/types';
import { primaryScreeningRisk } from './primaryRisk';

/** Collapsed by default: what the result was based on, its reasons and its limits. */
export function ResultDetails({ data }: { data: AnalyzeResponse }) {
  const risk = primaryScreeningRisk(data.risk_assessment);
  const limits = data.explanation?.limitations ?? [];
  if (!data.apnea_score || (!risk && limits.length === 0)) return null;

  return (
    <details className="how how--panel">
      <summary>About this result</summary>
      {risk && (
        <div className="how__block">
          <div className="basis">
            <span className="basis__label">Based on</span>
            <SourceTags sources={risk.source_labels} />
            <span className="basis__evidence">Evidence: {risk.evidence_rating}</span>
          </div>
          {risk.reasons.length > 0 && (
            <ul className="reasons">
              {risk.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {limits.length > 0 && (
        <ul className="limits__list">
          {limits.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      )}
    </details>
  );
}
