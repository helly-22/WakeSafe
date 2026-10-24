import type { RiskAssessment, RiskItem } from '../../lib/types';

/** The sleep-breathing risk item if present, otherwise the first non-urgent risk. Selection only, no scoring. */
export function primaryScreeningRisk(assessment: RiskAssessment): RiskItem | undefined {
  return (
    assessment.risks.find((r) => r.risk_id === 'sleep_disordered_breathing') ??
    assessment.risks.find((r) => r.tier !== 'Urgent')
  );
}
