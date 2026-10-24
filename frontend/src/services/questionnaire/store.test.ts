import { describe, expect, it } from 'vitest';
import { emptyAnswers } from '../../features/questionnaire/model';
import { DemoLocalStore, StorageError, memoryStorage } from './store';
import { SupabaseStore } from './supabaseStore';

function clock(...isoTimes: string[]) {
  let i = 0;
  return () => new Date(isoTimes[Math.min(i++, isoTimes.length - 1)]!);
}

describe('DemoLocalStore', () => {
  it('saves, reloads and keeps profiles separate', async () => {
    const store = new DemoLocalStore(memoryStorage());
    const maya = emptyAnswers();
    maya.age = '52';
    const jordan = emptyAnswers();
    jordan.age = '34';
    await store.save('maya_demo', maya, false);
    await store.save('jordan_demo', jordan, false);
    expect((await store.load('maya_demo'))?.answers.age).toBe('52');
    expect((await store.load('jordan_demo'))?.answers.age).toBe('34');
    expect(await store.load('riley_demo')).toBeNull();
  });

  it('keeps createdAt and advances updatedAt on edit', async () => {
    const store = new DemoLocalStore(memoryStorage(), clock('2026-10-24T10:00:00Z', '2026-10-24T11:00:00Z'));
    const a = emptyAnswers();
    const first = await store.save('maya_demo', a, false);
    a.snoring = 'yes';
    const second = await store.save('maya_demo', a, true);
    expect(second.createdAt).toBe(first.createdAt);
    expect(second.updatedAt).toBe('2026-10-24T11:00:00.000Z');
    expect(second.complete).toBe(true);
    expect((await store.load('maya_demo'))?.answers.snoring).toBe('yes');
  });

  it('does not return a record filed under another profile id', async () => {
    const backing = memoryStorage();
    const store = new DemoLocalStore(backing);
    await store.save('maya_demo', emptyAnswers(), false);
    const raw = backing.getItem('wakesafe.demo.questionnaire.v1:maya_demo')!;
    backing.setItem('wakesafe.demo.questionnaire.v1:jordan_demo', raw);
    expect(await store.load('jordan_demo')).toBeNull();
  });

  it('refuses ids that are not synthetic demo profiles', async () => {
    const store = new DemoLocalStore(memoryStorage());
    await expect(store.save('real-patient-123', emptyAnswers(), false)).rejects.toBeInstanceOf(StorageError);
  });

  it('clearAll removes only questionnaire records', async () => {
    const backing = memoryStorage();
    backing.setItem('other-app-key', 'keep');
    const store = new DemoLocalStore(backing);
    await store.save('maya_demo', emptyAnswers(), false);
    await store.clearAll();
    expect(await store.load('maya_demo')).toBeNull();
    expect(backing.getItem('other-app-key')).toBe('keep');
  });

  it('reports a save failure instead of pretending it worked', async () => {
    const backing = memoryStorage();
    backing.setItem = () => {
      throw new Error('QuotaExceededError');
    };
    await expect(new DemoLocalStore(backing).save('maya_demo', emptyAnswers(), false)).rejects.toThrow(/Could not save/);
  });
});

describe('SupabaseStore', () => {
  it('refuses to run without a signed-in user', async () => {
    const store = new SupabaseStore({ url: 'https://example.supabase.co', anonKey: 'anon', getAccessToken: async () => null, fetchImpl: async () => new Response('[]') });
    await expect(store.load('maya_demo')).rejects.toThrow(/Sign in/);
  });

  it('rejects a service-role key', () => {
    expect(() => new SupabaseStore({ url: 'https://x.supabase.co', anonKey: 'eyJ...service_role...', getAccessToken: async () => 't' })).toThrow(/service-role/);
  });

  it('sends the user token and upserts on (user_id, profile_id)', async () => {
    const calls: Array<{ url: string; init: RequestInit }> = [];
    const row = { profile_id: 'maya_demo', answers: emptyAnswers(), complete: false, schema_version: 1, created_at: 'c', updated_at: 'u' };
    const store = new SupabaseStore({
      url: 'https://x.supabase.co/',
      anonKey: 'anon',
      getAccessToken: async () => 'user-jwt',
      fetchImpl: async (url, init) => {
        calls.push({ url: String(url), init: init ?? {} });
        return new Response(JSON.stringify([row]), { status: 200 });
      },
    });
    const rec = await store.save('maya_demo', emptyAnswers(), false);
    expect(rec.profileId).toBe('maya_demo');
    expect(calls[0]!.url).toBe('https://x.supabase.co/rest/v1/questionnaire_responses?on_conflict=user_id,profile_id');
    expect((calls[0]!.init.headers as Record<string, string>).Authorization).toBe('Bearer user-jwt');
    expect(JSON.parse(String(calls[0]!.init.body))).not.toHaveProperty('user_id');
  });
});
