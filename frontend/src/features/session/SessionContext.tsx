import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { analyze, getPersonas } from '../../services/api';
import type { AnalyzeResponse, DemoPersona } from '../../lib/types';

/**
 * In-memory session state shared across pages. Nothing is persisted to storage
 * or the server; "Clear session" discards it (TEAM_CONTRACTS.md §4.3).
 */
export type AnalysisState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: AnalyzeResponse }
  | { status: 'error'; message: string };

export interface SessionValue {
  personas: DemoPersona[];
  personaId: string | null;
  persona: DemoPersona | null;
  analysis: AnalysisState;
  selectPersona: (id: string) => void;
  clearSession: () => void;
}

export const SessionContext = createContext<SessionValue | null>(null);

const DEFAULT_PERSONA = 'maya_demo';

/** Optional `?persona=<id>` deep link for demos, e.g. `/?persona=riley_demo`. */
function personaFromUrl(): string | null {
  if (typeof window === 'undefined') return null;
  return new URLSearchParams(window.location.search).get('persona');
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [personas, setPersonas] = useState<DemoPersona[]>([]);
  const [personaId, setPersonaId] = useState<string | null>(null);
  // Start in 'loading' so first paint never claims the session was cleared; 'idle' only follows clearSession().
  const [analysis, setAnalysis] = useState<AnalysisState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    getPersonas()
      .then((list) => {
        if (cancelled) return;
        setPersonas(list);
        const requested = personaFromUrl();
        const initial =
          list.find((p) => p.persona_id === requested) ?? list.find((p) => p.persona_id === DEFAULT_PERSONA) ?? list[0];
        setPersonaId((current) => current ?? initial?.persona_id ?? null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setAnalysis({ status: 'error', message: err instanceof Error ? err.message : 'Could not load demo personas.' });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const persona = useMemo(() => personas.find((p) => p.persona_id === personaId) ?? null, [personas, personaId]);

  useEffect(() => {
    if (!persona) return;
    let cancelled = false;
    setAnalysis({ status: 'loading' });
    analyze({ data_source: 'synthetic', persona_id: persona.persona_id, profile: persona.profile })
      .then((data) => {
        if (!cancelled) setAnalysis({ status: 'ready', data });
      })
      .catch((err: unknown) => {
        if (!cancelled) setAnalysis({ status: 'error', message: err instanceof Error ? err.message : 'Analysis failed.' });
      });
    return () => {
      cancelled = true;
    };
  }, [persona]);

  const selectPersona = useCallback((id: string) => setPersonaId(id), []);
  const clearSession = useCallback(() => {
    setPersonaId(null);
    setAnalysis({ status: 'idle' });
  }, []);

  const value = useMemo<SessionValue>(
    () => ({ personas, personaId, persona, analysis, selectPersona, clearSession }),
    [personas, personaId, persona, analysis, selectPersona, clearSession],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
