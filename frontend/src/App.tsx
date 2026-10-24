import { BrowserRouter, Route, Routes } from 'react-router';
import { AppShell } from './components/AppShell';
import { SessionProvider } from './features/session/SessionContext';
import { FindCarePage } from './pages/FindCarePage';
import { HealthIntakePage } from './pages/HealthIntakePage';
import { MyReportPage } from './pages/MyReportPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { OverviewPage } from './pages/OverviewPage';
import { SleepTrendsPage } from './pages/SleepTrendsPage';

export function App() {
  return (
    <SessionProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="sleep" element={<SleepTrendsPage />} />
            <Route path="intake" element={<HealthIntakePage />} />
            <Route path="care" element={<FindCarePage />} />
            <Route path="report" element={<MyReportPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </SessionProvider>
  );
}
