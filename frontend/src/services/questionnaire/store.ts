/**
 * Questionnaire persistence. UI components never call storage directly; they use
 * a QuestionnaireStore picked by getQuestionnaireStore().
 *
 * Two adapters:
 *  - DemoLocalStore: browser localStorage, DEMO ONLY, for synthetic personas.
 *    Data stays on this device. Clearly labeled in the UI.
 *  - SupabaseStore: questionnaire_responses table with Row Level Security. Only
 *    enabled when VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are set AND a
 *    signed-in Supabase session exists. Not configured in this repo yet.
 */
import type { QuestionnaireAnswers } from '../../features/questionnaire/model';

// v2: questionnaires start blank. Records saved by v1 builds (which could be prefilled) are ignored on load.
export const QUESTIONNAIRE_SCHEMA_VERSION = 2;

export interface QuestionnaireRecord {
  profileId: string;
  answers: QuestionnaireAnswers;
  /** True only when every required question passed validation at save time. */
  complete: boolean;
  schemaVersion: number;
  createdAt: string;
  updatedAt: string;
}

export interface QuestionnaireStore {
  readonly kind: 'demo-local' | 'supabase';
  /** Human label shown in the UI so storage is never misrepresented. */
  readonly label: string;
  load(profileId: string): Promise<QuestionnaireRecord | null>;
  save(profileId: string, answers: QuestionnaireAnswers, complete: boolean): Promise<QuestionnaireRecord>;
  remove(profileId: string): Promise<void>;
  /** Removes every record this adapter owns (used by "Clear session"). */
  clearAll(): Promise<void>;
}

export class StorageError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'StorageError';
  }
}

const PREFIX = 'wakesafe.demo.questionnaire.v1:';

/**
 * Only the demo persona ids may use the local demo adapter: the built-in `*_demo` profiles and
 * the API's demo people (`P001`, `SYN-APNEA`, ...). Anything else, such as a real patient id, is refused.
 */
const DEMO_ID = /^(?:[a-z0-9_-]+_demo|P\d{3}|SYN-[A-Z0-9_]+)$/;

export function isDemoProfileId(profileId: string): boolean {
  return DEMO_ID.test(profileId);
}

/** Minimal Storage subset so tests can inject an in-memory implementation. */
export type KeyValueStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem' | 'key' | 'length'>;

export class DemoLocalStore implements QuestionnaireStore {
  readonly kind = 'demo-local' as const;
  readonly label = 'Saved on this device only';

  private readonly storage: KeyValueStorage;
  private readonly now: () => Date;

  constructor(storage: KeyValueStorage, now: () => Date = () => new Date()) {
    this.storage = storage;
    this.now = now;
  }

  private key(profileId: string): string {
    if (!isDemoProfileId(profileId)) {
      throw new StorageError(`This storage only accepts the built-in demo profiles, not "${profileId}".`);
    }
    return PREFIX + profileId;
  }

  async load(profileId: string): Promise<QuestionnaireRecord | null> {
    const raw = this.storage.getItem(this.key(profileId));
    if (raw === null) return null;
    try {
      const rec = JSON.parse(raw) as QuestionnaireRecord;
      // Defence in depth: never return a record filed under another profile.
      if (rec.profileId !== profileId || rec.schemaVersion !== QUESTIONNAIRE_SCHEMA_VERSION) return null;
      return rec;
    } catch {
      return null;
    }
  }

  async save(profileId: string, answers: QuestionnaireAnswers, complete: boolean): Promise<QuestionnaireRecord> {
    const key = this.key(profileId);
    const existing = await this.load(profileId);
    const stamp = this.now().toISOString();
    const rec: QuestionnaireRecord = {
      profileId,
      answers: structuredClone(answers),
      complete,
      schemaVersion: QUESTIONNAIRE_SCHEMA_VERSION,
      createdAt: existing?.createdAt ?? stamp,
      updatedAt: stamp,
    };
    try {
      this.storage.setItem(key, JSON.stringify(rec));
    } catch {
      throw new StorageError('Could not save on this device (storage is full or blocked).');
    }
    return rec;
  }

  async remove(profileId: string): Promise<void> {
    this.storage.removeItem(this.key(profileId));
  }

  async clearAll(): Promise<void> {
    const keys: string[] = [];
    for (let i = 0; i < this.storage.length; i++) {
      const k = this.storage.key(i);
      if (k?.startsWith(PREFIX)) keys.push(k);
    }
    keys.forEach((k) => this.storage.removeItem(k));
  }
}

/** In-memory fallback when localStorage is unavailable (private mode, tests). */
export function memoryStorage(): KeyValueStorage {
  const m = new Map<string, string>();
  return {
    getItem: (k) => m.get(k) ?? null,
    setItem: (k, v) => void m.set(k, v),
    removeItem: (k) => void m.delete(k),
    key: (i) => Array.from(m.keys())[i] ?? null,
    get length() {
      return m.size;
    },
  };
}

export const SUPABASE_CONFIGURED = Boolean(import.meta.env.VITE_SUPABASE_URL && import.meta.env.VITE_SUPABASE_ANON_KEY);

let store: QuestionnaireStore | null = null;

/**
 * The active store. Demo profiles always use DemoLocalStore. Cloud persistence
 * needs Supabase Auth (a signed-in user) before it can be enabled; see
 * supabase/README.md. Until then this never pretends to save to the cloud.
 */
export function getQuestionnaireStore(): QuestionnaireStore {
  if (store) return store;
  let backing: KeyValueStorage;
  try {
    backing = window.localStorage;
    backing.getItem('__probe__');
  } catch {
    backing = memoryStorage();
  }
  store = new DemoLocalStore(backing);
  return store;
}

/** Test hook. */
export function setQuestionnaireStore(next: QuestionnaireStore | null): void {
  store = next;
}
