import { ShellPage } from './ShellPage';

export function FindCarePage() {
  return (
    <ShellPage
      title="Find Care"
      subtitle="Care options matched to your screening. In an emergency, call 911."
      heading="Care recommendations are coming soon"
      items={[
        'Nearby facilities ranked by specialty fit, distance and capacity',
        'Capacity clearly labeled as static, simulated, live or unknown',
        'Emergency guidance shown first when warning signs are reported',
      ]}
    />
  );
}
