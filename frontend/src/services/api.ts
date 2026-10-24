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
  return request<DemoPersona[]>('/api/demo/personas');
}

export async function analyze(body: AnalyzeRequest): Promise<AnalyzeResponse> {
  if (USE_MOCKS) {
    const fixture = body.persona_id ? MOCK_ANALYSES[body.persona_id] : undefined;
    if (!fixture) throw new ApiError(`No synthetic fixture for persona "${body.persona_id ?? ''}".`, 404);
    return structuredClone(fixture);
  }
  return request<AnalyzeResponse>('/api/screening/analyze', { method: 'POST', body: JSON.stringify(body) });
}
