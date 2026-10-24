import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { getQuestionnaireStore, type QuestionnaireRecord, type QuestionnaireStore } from '../../services/questionnaire/store';
import { validateAll, type QuestionnaireAnswers } from './model';

export type RecordState =
  | { status: 'loading' }
  | { status: 'ready'; record: QuestionnaireRecord | null }
  | { status: 'error'; message: string };

interface QuestionnaireValue {
  storeLabel: string;
  get: (profileId: string) => RecordState | undefined;
  load: (profileId: string) => Promise<void>;
  save: (profileId: string, answers: QuestionnaireAnswers) => Promise<QuestionnaireRecord>;
  clearAll: () => Promise<void>;
}

const Ctx = createContext<QuestionnaireValue | null>(null);

/** Per-profile questionnaire records, loaded and saved only through the store. */
export function QuestionnaireProvider({ children, store: injected }: { children: ReactNode; store?: QuestionnaireStore }) {
  const store = injected ?? getQuestionnaireStore();
  const [records, setRecords] = useState<Record<string, RecordState>>({});
  const inflight = useRef(new Set<string>());

  const load = useCallback(
    async (profileId: string) => {
      if (inflight.current.has(profileId)) return;
      inflight.current.add(profileId);
      setRecords((r) => ({ ...r, [profileId]: { status: 'loading' } }));
      try {
        const record = await store.load(profileId);
        setRecords((r) => ({ ...r, [profileId]: { status: 'ready', record } }));
      } catch (e) {
        setRecords((r) => ({ ...r, [profileId]: { status: 'error', message: e instanceof Error ? e.message : 'Could not load answers.' } }));
      } finally {
        inflight.current.delete(profileId);
      }
    },
    [store],
  );

  const save = useCallback(
    async (profileId: string, answers: QuestionnaireAnswers) => {
      const complete = Object.keys(validateAll(answers)).length === 0;
      const record = await store.save(profileId, answers, complete);
      setRecords((r) => ({ ...r, [profileId]: { status: 'ready', record } }));
      return record;
    },
    [store],
  );

  const clearAll = useCallback(async () => {
    await store.clearAll();
    setRecords({});
  }, [store]);

  const value = useMemo<QuestionnaireValue>(
    () => ({ storeLabel: store.label, get: (id) => records[id], load, save, clearAll }),
    [store.label, records, load, save, clearAll],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useQuestionnaires(): QuestionnaireValue {
  const v = useContext(Ctx);
  if (!v) throw new Error('useQuestionnaires must be used inside <QuestionnaireProvider>.');
  return v;
}

export type CompletionStatus = 'loading' | 'error' | 'not_started' | 'in_progress' | 'complete';

export function completionOf(state: RecordState | undefined): CompletionStatus {
  if (!state || state.status === 'loading') return 'loading';
  if (state.status === 'error') return 'error';
  if (!state.record) return 'not_started';
  return state.record.complete ? 'complete' : 'in_progress';
}
