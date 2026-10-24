import { AnalysisGate } from '../components/AnalysisGate';
import { Card } from '../components/Card';
import { StageChart } from '../components/charts/StageChart';
import { PageHeader } from '../components/PageHeader';
import { Disclaimer, UrgentBanner } from '../components/Safety';
import { DataCoverageCard } from '../features/overview/DataCoverageCard';
import { ScreeningSignals } from '../features/overview/ScreeningSignals';
import { SignalsPanel } from '../features/overview/SignalsPanel';
import { TrendExplorer } from '../features/overview/TrendExplorer';
import { formatWindow } from '../lib/format';
import { TREND_PAGE_SERIES } from '../lib/series';

/** All the detail: every nightly series, sleep stages, shared-hover signals, signal counts and data coverage. */
export function SleepTrendsPage() {
  return (
    <>
      <PageHeader title="Sleep Trends" subtitle="Nightly values across your data window." />
      <AnalysisGate>
        {(data) => (
          <>
            <UrgentBanner assessment={data.risk_assessment} />

            <div className="dash dash--trends">
              <TrendExplorer data={data} series={TREND_PAGE_SERIES} eyebrow="Explore" height={280} className="dash__full" />

              <Card
                eyebrow="Sleep stages"
                title="How each night divided"
                className="dash__wide"
                action={<span className="muted-note">{formatWindow(data.features.window_start, data.features.window_end)}</span>}
              >
                {data.nights && data.nights.length > 0 ? (
                  <StageChart nights={data.nights} />
                ) : (
                  <p className="empty-note">Nightly records were not included in this response.</p>
                )}
              </Card>

              <DataCoverageCard data={data} className="dash__narrow" />
              <SignalsPanel data={data} className="dash__full" />

              <Card eyebrow="Screening" title="Signals behind your result" className="dash__full">
                <ScreeningSignals data={data} detail />
              </Card>
            </div>

            <Disclaimer />
          </>
        )}
      </AnalysisGate>
    </>
  );
}
