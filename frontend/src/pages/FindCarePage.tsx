import { ShellPage } from './ShellPage';

export function FindCarePage() {
  return (
    <ShellPage
      title="Find Care"
      subtitle="Care options matched to the screening result. Not a substitute for calling 911 in an emergency."
      planned={[
        'Ranked facility list from POST /api/care/recommendations (Helly’s recommend_care)',
        'Map with verified facility locations',
        'Capacity labeled as static, simulated, live or unknown on every facility',
        'Emergency guidance instead of a routine list when urgent symptoms are reported',
      ]}
    />
  );
}
