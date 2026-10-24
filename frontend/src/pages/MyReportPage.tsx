import { ShellPage } from './ShellPage';

export function MyReportPage() {
  return (
    <ShellPage
      title="My Report"
      subtitle="A clinician-ready summary you can bring to an appointment."
      heading="Your report is coming soon"
      items={[
        'A preview of your flagged risks, reported history and wearable trends',
        'Data quality, limitations and the versions behind each result',
        'A PDF you can download and share with your clinician',
      ]}
    />
  );
}
