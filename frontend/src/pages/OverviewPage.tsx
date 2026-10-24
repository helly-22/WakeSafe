import { AnalysisGate } from '../components/AnalysisGate';
import { PageHeader } from '../components/PageHeader';
import { Disclaimer, UrgentBanner } from '../components/Safety';
import { DataCoverageCard } from '../features/overview/DataCoverageCard';
import { NextStepsCard } from '../features/overview/NextStepsCard';
import { ScreeningOverview } from '../features/overview/ScreeningOverview';
import { SignalsPanel } from '../features/overview/SignalsPanel';
import { SleepHero } from '../features/overview/SleepHero';
import { TrendExplorer } from '../features/overview/TrendExplorer';
import { WhyFlaggedCard } from '../features/overview/WhyFlaggedCard';
import { useSession } from '../hooks/useSession';
import { formatWindow } from '../lib/format';
import { OVERVIEW_SERIES } from '../lib/series';

export function OverviewPage() {
  const { persona, analysis } = useSession();
  const subtitle =
    analysis.status === 'ready'
      ? `${persona?.display_name ?? 'Demo'} · ${formatWindow(analysis.data.features.window_start, analysis.data.features.window_end)} · ${analysis.data.features.nights_available} nights`
      : undefined;

  return (
    <>
      <PageHeader title="Overview" subtitle={subtitle} />
      <AnalysisGate>
        {(data) => (
          <>
            {/* Emergency guidance always comes before routine content. */}
            <UrgentBanner assessment={data.risk_assessment} />

            <div className="dash">
              <SleepHero data={data} className="dash__a" />
              <ScreeningOverview data={data} className="dash__b" />
              <SignalsPanel data={data} className="dash__full" />
              <TrendExplorer data={data} series={OVERVIEW_SERIES} className="dash__c" />
              <DataCoverageCard data={data} className="dash__d" />
              <WhyFlaggedCard data={data} className="dash__e" />
              <NextStepsCard urgent={data.risk_assessment.urgent_override} className="dash__f" />
            </div>

            <Disclaimer />
          </>
        )}
      </AnalysisGate>
    </>
  );
}
