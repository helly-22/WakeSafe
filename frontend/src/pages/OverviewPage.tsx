import { AnalysisGate } from '../components/AnalysisGate';
import { Card } from '../components/Card';
import { PageHeader } from '../components/PageHeader';
import { UrgentBanner } from '../components/Safety';
import { ScreeningInputsNotice } from '../features/questionnaire/ScreeningInputsNotice';
import { ResultDetails } from '../features/overview/ResultDetails';
import { RiskSummary } from '../features/overview/RiskSummary';
import { ScreeningSignals } from '../features/overview/ScreeningSignals';
import { SleepSnapshot } from '../features/overview/SleepSnapshot';
import { useSession } from '../hooks/useSession';
import { formatWindow } from '../lib/format';

/** Overview: at-a-glance only. Charts, nightly signals and data coverage live on Sleep Trends. */
export function OverviewPage() {
  const { persona, analysis } = useSession();
  const subtitle =
    analysis.status === 'ready'
      ? `${persona?.display_name ?? 'Profile'} · ${formatWindow(analysis.data.features.window_start, analysis.data.features.window_end)} · ${analysis.data.features.nights_available} nights`
      : undefined;

  return (
    <>
      <PageHeader title="Overview" subtitle={subtitle} />
      <AnalysisGate>
        {(data) => (
          <>
            {/* Emergency guidance always comes before everything else. */}
            <UrgentBanner assessment={data.risk_assessment} />
            <RiskSummary data={data} />
            <ScreeningInputsNotice />
            <div className="dash">
              <SleepSnapshot data={data} className="dash__b" />
              <Card eyebrow="Key signals" title="What shaped this result" className="dash__e">
                <ScreeningSignals data={data} />
              </Card>
            </div>
            <ResultDetails data={data} />
          </>
        )}
      </AnalysisGate>
    </>
  );
}
