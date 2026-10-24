import type { ReactNode } from 'react';
import { useSession } from '../hooks/useSession';
import type { AnalyzeResponse } from '../lib/types';

/** Renders children only once results are ready; otherwise shows deliberate loading, error or empty states. */
export function AnalysisGate({ children }: { children: (data: AnalyzeResponse) => ReactNode }) {
  const { analysis, personas, selectPersona } = useSession();

  switch (analysis.status) {
    case 'ready':
      return <>{children(analysis.data)}</>;
    case 'loading':
      return (
        <div className="state state--loading" role="status">
          <span className="state__pulse" aria-hidden="true" />
          <p>Loading your results…</p>
        </div>
      );
    case 'error':
      return (
        <div className="state state--error" role="alert">
          <h2 className="state__title">We couldn’t load your results</h2>
          <p>{analysis.message}</p>
          <button type="button" className="btn" onClick={() => window.location.reload()}>
            Try again
          </button>
        </div>
      );
    case 'idle':
      return (
        <div className="state">
          <h2 className="state__title">Session cleared</h2>
          <p>Your saved answers were removed from this device. Choose a profile to start again.</p>
          {personas[0] && (
            <button type="button" className="btn" onClick={() => selectPersona(personas[0]!.persona_id)}>
              Choose a profile
            </button>
          )}
        </div>
      );
  }
}
