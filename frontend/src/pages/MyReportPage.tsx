import { ShellPage } from './ShellPage';

export function MyReportPage() {
  return (
    <ShellPage
      title="My Report"
      subtitle="A clinician-ready summary built only from structured screening data."
      planned={[
        'Report preview from POST /api/reports/preview',
        'PDF download from POST /api/reports/pdf',
        'Provenance, generation time, model and rules versions, limitations',
        'Trend charts and a nightly-values appendix, readable in black and white',
      ]}
    />
  );
}
