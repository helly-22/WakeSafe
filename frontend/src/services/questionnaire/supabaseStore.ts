/**
 * Supabase adapter for questionnaire responses (NOT ACTIVE YET).
 *
 * Talks to the PostgREST endpoint of the `questionnaire_responses` table defined
 * in supabase/migrations/. It requires the SIGNED-IN user's access token: Row
 * Level Security restricts every row to auth.uid() = user_id, and the anon key
 * alone can read or write nothing. The service-role key must never be used here.
 *
 * Enabling it needs: a Supabase project, the migration applied, VITE_SUPABASE_URL
 * and VITE_SUPABASE_ANON_KEY set, and Supabase Auth wired into the app so
 * getAccessToken() returns a real session token. See supabase/README.md.
 */
import type { QuestionnaireAnswers } from '../../features/questionnaire/model';
import { QUESTIONNAIRE_SCHEMA_VERSION, StorageError, type QuestionnaireRecord, type QuestionnaireStore } from './store';

interface Row {
  profile_id: string;
  answers: QuestionnaireAnswers;
  complete: boolean;
  schema_version: number;
  created_at: string;
  updated_at: string;
}

export interface SupabaseStoreOptions {
  url: string;
  anonKey: string;
  /** Returns the signed-in user's JWT, or null when nobody is signed in. */
  getAccessToken: () => Promise<string | null>;
  fetchImpl?: typeof fetch;
}

const toRecord = (r: Row): QuestionnaireRecord => ({
  profileId: r.profile_id,
  answers: r.answers,
  complete: r.complete,
  schemaVersion: r.schema_version,
  createdAt: r.created_at,
  updatedAt: r.updated_at,
});

export class SupabaseStore implements QuestionnaireStore {
  readonly kind = 'supabase' as const;
  readonly label = 'Saved to your WakeSafe account';
  private readonly opts: SupabaseStoreOptions;
  private readonly fetchImpl: typeof fetch;

  constructor(opts: SupabaseStoreOptions) {
    if (/service_role/i.test(opts.anonKey)) {
      throw new StorageError('Refusing to use a service-role key in the browser.');
    }
    this.opts = opts;
    this.fetchImpl = opts.fetchImpl ?? fetch.bind(globalThis);
  }

  private async headers(): Promise<HeadersInit> {
    const token = await this.opts.getAccessToken();
    if (!token) throw new StorageError('Sign in to save answers to your account.');
    return {
      apikey: this.opts.anonKey,
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    };
  }

  private endpoint(query = ''): string {
    return `${this.opts.url.replace(/\/$/, '')}/rest/v1/questionnaire_responses${query}`;
  }

  private async call(url: string, init: RequestInit): Promise<Response> {
    let res: Response;
    try {
      res = await this.fetchImpl(url, init);
    } catch {
      throw new StorageError('Could not reach the database.');
    }
    if (!res.ok) throw new StorageError(`The database rejected the request (${res.status}).`);
    return res;
  }

  async load(profileId: string): Promise<QuestionnaireRecord | null> {
    const q = `?profile_id=eq.${encodeURIComponent(profileId)}&select=*`;
    const res = await this.call(this.endpoint(q), { headers: await this.headers() });
    const rows = (await res.json()) as Row[];
    return rows[0] ? toRecord(rows[0]) : null;
  }

  async save(profileId: string, answers: QuestionnaireAnswers, complete: boolean): Promise<QuestionnaireRecord> {
    // user_id defaults to auth.uid() in the database; created_at is kept on conflict.
    const res = await this.call(this.endpoint('?on_conflict=user_id,profile_id'), {
      method: 'POST',
      headers: { ...(await this.headers()), Prefer: 'resolution=merge-duplicates,return=representation' },
      body: JSON.stringify({ profile_id: profileId, answers, complete, schema_version: QUESTIONNAIRE_SCHEMA_VERSION }),
    });
    const rows = (await res.json()) as Row[];
    if (!rows[0]) throw new StorageError('The database did not return the saved answers.');
    return toRecord(rows[0]);
  }

  async remove(profileId: string): Promise<void> {
    await this.call(this.endpoint(`?profile_id=eq.${encodeURIComponent(profileId)}`), {
      method: 'DELETE',
      headers: await this.headers(),
    });
  }

  async clearAll(): Promise<void> {
    // RLS limits this to the signed-in user's own rows.
    await this.call(this.endpoint('?profile_id=not.is.null'), { method: 'DELETE', headers: await this.headers() });
  }
}
