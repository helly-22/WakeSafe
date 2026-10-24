import type { ReactNode } from 'react';
import { useSession } from '../hooks/useSession';
import type { AnalyzeResponse } from '../lib/types';

/** Renders children only once an analysis is ready; otherwise shows loading, error or empty states. */
export function AnalysisGate({ children }: { children: (data: AnalyzeResponse) => ReactNode }) {
  const { analysis, personas, selectPersona } = useSession();

  switch (analysis.status) {
    case 'ready':
      return <>{children(analysis.data)}</>;
    case 'loading':
      return (
        <p className="state" role="status">
          Loading synthetic screening data…
        </p>
      );
    case 'error':
      return (
        <p className="state state--error" role="alert">
          {analysis.message}
        </p>
      );
    case 'idle':
      return (
        <div className="state">
          <p>Session cleared. No data is loaded.</p>
          {personas[0] && (
            <button type="button" className="btn" onClick={() => selectPersona(personas[0]!.persona_id)}>
              Load a demo persona
            </button>
          )}
        </div>
      );
  }
}
