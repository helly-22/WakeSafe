import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppRoutes } from '../../App';
import type { NightRecord } from '../../lib/types';
import { MOCK_ANALYSES } from '../../services/mock/fixtures';
import { DemoLocalStore, memoryStorage } from '../../services/questionnaire/store';
import { QuestionnaireProvider } from '../questionnaire/QuestionnaireContext';
import { SessionProvider } from '../session/SessionContext';
import { SIGNALS, countSignal } from './signalCounts';

// Live mode: the screening service is "connected", so saving answers must call it again.
vi.mock('../../services/api', async () => {
  const fx = await import('../../services/mock/fixtures');
  return {
    USE_MOCKS: false,
    getPersonas: async () => structuredClone(fx.MOCK_PERSONAS),
    analyze: vi.fn(),
    ApiError: class extends Error {},
  };
});
import { analyze } from '../../services/api';

function night(i: number, spo2: number | null): NightRecord {
  return {
    night_id: `n${i}`,
    date: `2026-10-${String(10 + i).padStart(2, '0')}`,
    resting_heart_rate_bpm: 60,
    hrv_rmssd_ms: 40,
    spo2_pct: spo2,
    respiratory_rate_rpm: 15,
    skin_temperature_c: null,
    sleep_duration_minutes: 400,
    sleep_efficiency_pct: 85,
    deep_sleep_minutes: 70,
    rem_sleep_minutes: 90,
    disturbance_count: 10,
    sleep_consistency_pct: 80,
    source: 'synthetic',
  };
}

describe('countSignal', () => {
  const spo2Spec = SIGNALS.find((s) => s.key === 'spo2_pct')!;

  it('counts only recorded nights and never counts missing ones', () => {
    // recorded 94, 90, 96, 92 -> average 93; below average: 90 and 92 (2 of 4); one night missing.
    const nights = [night(0, 94), night(1, 90), night(2, null), night(3, 96), night(4, 92)];
    const c = countSignal(nights, spo2Spec);
    expect(c).toMatchObject({ hits: 2, recorded: 4, total: 5, average: 93, comparable: true });
    expect(c.marks.map((m) => m.state)).toEqual(['clear', 'hit', 'missing', 'clear', 'hit']);
  });

  it('does not compare when too few nights were recorded', () => {
    const c = countSignal([night(0, 94), night(1, null), night(2, 90)], spo2Spec);
    expect(c.comparable).toBe(false);
    expect(c.hits).toBe(0);
    expect(c.marks.map((m) => m.state)).toEqual(['unscored', 'missing', 'unscored']);
  });

  it('reports zero recorded nights without inventing an average', () => {
    const c = countSignal([night(0, null), night(1, null)], spo2Spec);
    expect(c).toMatchObject({ recorded: 0, average: null, comparable: false });
  });
});

const u = () => userEvent.setup();

async function choose(user: ReturnType<typeof userEvent.setup>, question: RegExp, option: string) {
  await user.click(within(screen.getByRole('group', { name: question })).getByLabelText(option));
}

async function fillAndSave(user: ReturnType<typeof userEvent.setup>) {
  await choose(user, /snore loudly/i, 'No');
  await choose(user, /tired, fatigued/i, 'Yes');
  await choose(user, /stop breathing/i, 'No');
  await choose(user, /high blood pressure\?/i, 'Yes');
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  await user.type(screen.getByLabelText(/^Age/), '47');
  await choose(user, /^Sex/, 'Female');
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  await user.click(screen.getByLabelText('None of these'));
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  for (const q of [/Chest pain/i, /Fainting/i, /Severe shortness of breath/i, /Stroke symptoms/i]) await choose(user, q, 'No');
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  await user.click(screen.getByRole('button', { name: 'Save answers' }));
  await screen.findByText('Answers saved.');
}

function renderApp(path: string) {
  return render(
    <QuestionnaireProvider store={new DemoLocalStore(memoryStorage())}>
      <SessionProvider>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </SessionProvider>
    </QuestionnaireProvider>,
  );
}

beforeEach(() => {
  vi.mocked(analyze).mockReset();
  vi.mocked(analyze).mockImplementation(async (body) => {
    const base = structuredClone(MOCK_ANALYSES.maya_demo!);
    // A different tier for the new answers, so a stale result would be visible.
    if (body.profile.age === 47 && base.apnea_score) base.apnea_score.tier = 'Low';
    return base;
  });
});

describe('risk summary and signals', () => {
  it('shows the risk estimate under the title, with no summary paragraph or factor list', async () => {
    renderApp('/');
    expect(await screen.findByRole('heading', { name: 'Estimated sleep apnea risk' })).toBeInTheDocument();
    expect(document.querySelector('.tier__value')?.textContent).toMatch(/^(Low|Moderate|High)$/);
    expect(screen.getAllByText('Screening is not a diagnosis.').length).toBeGreaterThan(0);
    expect(screen.queryByText(/Several screening signals line up/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Each dot is a night/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Hover or use the arrow keys/)).not.toBeInTheDocument();
  });

  it('keeps per-night detail off the Overview and asks for the questionnaire instead of inventing symptoms', async () => {
    renderApp('/');
    await screen.findByRole('heading', { name: 'Estimated sleep apnea risk' });
    expect(screen.getByText('Wearable signals across 14 nights')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /Blood oxygen/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Answer the questionnaire to see your reported symptoms/)).toBeInTheDocument();
  });

  it('shows labeled per-night counts on Trends, with the gaps left as gaps', async () => {
    renderApp('/sleep');
    await screen.findByText('Wearable signals across 14 nights');
    expect(screen.getAllByText(/of \d+ recorded nights/).length).toBeGreaterThan(0);
    // Maya's SpO2 was recorded on 11 of 14 nights: the strip lists 3 nights with no data.
    const spo2 = screen.getByRole('img', { name: /Blood oxygen/ });
    expect(spo2.getAttribute('aria-label')).toMatch(/3 nights have no data/);
  });
});

describe('rerun after saving answers (screening service connected)', () => {
  it('re-runs with the saved answers and refreshes the tier, instead of keeping the earlier result', async () => {
    const user = u();
    renderApp('/intake?edit=maya_demo');
    await screen.findByRole('heading', { name: 'Sleep and symptoms' });
    await waitFor(() => expect(vi.mocked(analyze)).toHaveBeenCalledTimes(1));
    expect(vi.mocked(analyze).mock.calls[0]![0].profile.age).toBe(52); // sample profile, before any answers

    await fillAndSave(user);
    await waitFor(() => expect(vi.mocked(analyze)).toHaveBeenCalledTimes(2));
    const sent = vi.mocked(analyze).mock.calls[1]![0].profile;
    expect(sent).toMatchObject({ age: 47, sex: 'female', snoring: false, daytime_tiredness: true, hypertension: true, conditions: [], red_flag_symptoms: [] });
    expect(sent.height_cm).toBeNull(); // left blank: sent as unknown, not 0

    await user.click(screen.getByRole('button', { name: 'Back to profiles' }));
    await user.click(screen.getAllByRole('link', { name: 'Overview' })[0]!);
    await waitFor(() => expect(document.querySelector('.tier__value')?.textContent).toBe('Low'));
    expect(await screen.findByText(/Screened with your answers and your wearable data/)).toBeInTheDocument();
    expect(await screen.findByText('Reported symptoms')).toBeInTheDocument();
    expect(screen.getByText(/of 4 reported/)).toBeInTheDocument();
  });

  it('shows an error, not the earlier result, when the re-run fails', async () => {
    const user = u();
    renderApp('/intake?edit=maya_demo');
    await screen.findByRole('heading', { name: 'Sleep and symptoms' });
    await waitFor(() => expect(vi.mocked(analyze)).toHaveBeenCalledTimes(1));
    vi.mocked(analyze).mockRejectedValueOnce(new Error('Could not reach the WakeSafe API.'));
    await fillAndSave(user);
    await user.click(screen.getByRole('button', { name: 'Back to profiles' }));
    await user.click(screen.getAllByRole('link', { name: 'Overview' })[0]!);
    expect(await screen.findByText('We couldn’t load your results')).toBeInTheDocument();
    expect(document.querySelector('.tier__value')).toBeNull();
  });
});
