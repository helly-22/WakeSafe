import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { USE_MOCKS, analyze, getPersonas } from '../../services/api';
import type { AnalyzeResponse, DemoPersona, ProfileInput } from '../../lib/types';
import { toProfileInput } from '../questionnaire/model';
import { useQuestionnaires } from '../questionnaire/QuestionnaireContext';

/**
 * How the screening on screen was produced:
 *  - 'live':      the screening service ran for the current answers and wearable data.
 *  - 'demo':      a built-in demo result, shown only while no answers are saved.
 *  - 'not_rerun': answers are saved but no screening service is connected, so the
 *                 built-in prediction was removed instead of shown as if it were current.
 */
export type ScreeningRun = 'live' | 'demo' | 'not_rerun';

/**
 * In-memory session state shared across pages. Nothing is persisted to storage
 * or the server; "Clear session" discards it (TEAM_CONTRACTS.md §4.3).
 */
export type AnalysisState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: AnalyzeResponse; screening: ScreeningRun }
  | { status: 'error'; message: string };

export interface SessionValue {
  personas: DemoPersona[];
  personaId: string | null;
  persona: DemoPersona | null;
  /** Profile sent with the analysis request: the saved questionnaire when one exists, else the persona's own sample profile. */
  profileSource: 'questionnaire' | 'persona';
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

/** Keep the wearable data, drop every prediction that was not produced from the current answers. */
function withoutPredictions(data: AnalyzeResponse): AnalyzeResponse {
  return {
    ...data,
    apnea_score: null,
    explanation: null,
    risk_assessment: {
      risks: [],
      urgent_override: false,
      urgent_reasons: [],
      rules_version: data.risk_assessment.rules_version,
      disclaimer: data.risk_assessment.disclaimer,
    },
  };
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

  // Saved answers (complete or partial) replace the persona's sample profile in the request.
  // Unanswered questions go out as null, never as "No".
  const q = useQuestionnaires();
  const qState = persona ? q.get(persona.persona_id) : undefined;
  const qRecord = qState?.status === 'ready' ? qState.record : null;
  const qSettled = qState?.status === 'ready' || qState?.status === 'error';
  useEffect(() => {
    if (persona && !qState) void q.load(persona.persona_id);
  }, [persona, qState, q]);

  const profileJson = useMemo(() => {
    if (!persona) return null;
    const profile: ProfileInput = qRecord ? toProfileInput(qRecord.answers, persona.profile) : persona.profile;
    return JSON.stringify(profile);
  }, [persona, qRecord]);
  const useAnswers = qRecord !== null;
  const profileSource: SessionValue['profileSource'] = useAnswers ? 'questionnaire' : 'persona';

  // Re-run whenever the profile that would be screened changes, e.g. after the questionnaire is saved or edited.
  // Wait for the saved answers to load first so a stale built-in result never flashes up.
  useEffect(() => {
    if (!persona || profileJson === null || !qSettled) return;
    let cancelled = false;
    setAnalysis({ status: 'loading' });
    analyze({ data_source: 'synthetic', persona_id: persona.persona_id, profile: JSON.parse(profileJson) as ProfileInput })
      .then((data) => {
        if (cancelled) return;
        if (!USE_MOCKS) setAnalysis({ status: 'ready', data, screening: 'live' });
        else if (useAnswers) setAnalysis({ status: 'ready', data: withoutPredictions(data), screening: 'not_rerun' });
        else setAnalysis({ status: 'ready', data, screening: 'demo' });
      })
      .catch((err: unknown) => {
        if (!cancelled) setAnalysis({ status: 'error', message: err instanceof Error ? err.message : 'Analysis failed.' });
      });
    return () => {
      cancelled = true;
    };
  }, [persona, profileJson, useAnswers, qSettled]);

  const selectPersona = useCallback((id: string) => setPersonaId(id), []);
  const { clearAll } = q;
  const clearSession = useCallback(() => {
    setPersonaId(null);
    setAnalysis({ status: 'idle' });
    // Also discard questionnaire answers saved on this device.
    void clearAll();
  }, [clearAll]);

  const value = useMemo<SessionValue>(
    () => ({ personas, personaId, persona, profileSource, analysis, selectPersona, clearSession }),
    [personas, personaId, persona, profileSource, analysis, selectPersona, clearSession],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
