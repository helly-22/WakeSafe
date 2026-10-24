/**
 * Typed API client. The frontend never imports Python and never calculates risk
 * itself (TEAM_CONTRACTS.md §4.3). Route names follow §4.3 and are pending final
 * agreement (§9).
 *
 * Mock mode (default) serves typed synthetic fixtures so the UI works before the
 * backend and teammate modules exist.
 */
import type { AnalyzeRequest, AnalyzeResponse, DemoPersona } from '../lib/types';
import { MOCK_ANALYSES, MOCK_PERSONAS } from './mock/fixtures';

export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS !== 'false';
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

export class ApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...init?.headers },
    });
  } catch {
    throw new ApiError('Could not reach the WakeSafe API.');
  }
  if (!res.ok) throw new ApiError(`WakeSafe API returned ${res.status}.`, res.status);
  return (await res.json()) as T;
}

export async function getPersonas(): Promise<DemoPersona[]> {
  if (USE_MOCKS) return structuredClone(MOCK_PERSONAS);
  const list = await request<DemoPersona[]>('/api/demo/personas');
  const people = list.map((p) => ({ ...p, description: plainDescription(p.description) }));
  // The named scenarios (SYN-*) come first; the numbered people follow in the API's order.
  const scenario = (p: DemoPersona) => (p.persona_id.startsWith('SYN-') ? 0 : 1);
  return people.sort((a, b) => scenario(a) - scenario(b));
}

/** The API describes each profile in its own words; the app shows only the night count. */
function plainDescription(text: string): string {
  const nights = /(\d+)\s+(?:\w+\s+)?nights/.exec(text);
  return nights ? `${nights[1]} nights of wearable data.` : '';
}

export async function analyze(body: AnalyzeRequest): Promise<AnalyzeResponse> {
  if (USE_MOCKS) {
    const fixture = body.persona_id ? MOCK_ANALYSES[body.persona_id] : undefined;
    if (!fixture) throw new ApiError(`No demo data for profile "${body.persona_id ?? ''}".`, 404);
    return structuredClone(fixture);
  }
  return request<AnalyzeResponse>('/api/screening/analyze', { method: 'POST', body: JSON.stringify(body) });
}
