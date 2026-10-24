import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppRoutes } from '../../App';
import { DemoLocalStore, memoryStorage, type QuestionnaireStore } from '../../services/questionnaire/store';
import { SessionProvider } from '../session/SessionContext';
import { QuestionnaireProvider } from './QuestionnaireContext';
import { emptyAnswers } from './model';

let store: QuestionnaireStore;

function renderApp(path: string, s: QuestionnaireStore = store) {
  return render(
    <QuestionnaireProvider store={s}>
      <SessionProvider>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </SessionProvider>
    </QuestionnaireProvider>,
  );
}

const user = () => userEvent.setup();

async function answerStopQuestions(u: ReturnType<typeof userEvent.setup>) {
  await choose(u, /snore loudly/i, 'Yes');
  await choose(u, /tired, fatigued/i, 'Yes');
  await choose(u, /stop breathing/i, 'No');
  await choose(u, /high blood pressure\?/i, 'Yes');
}

/** Choose an option inside the fieldset whose legend matches `question`. */
async function choose(u: ReturnType<typeof userEvent.setup>, question: RegExp, option: string) {
  const group = screen.getByRole('group', { name: question });
  await u.click(within(group).getByLabelText(option));
}

async function answerAll(u: ReturnType<typeof userEvent.setup>, { chestPain = 'No' } = {}) {
  await choose(u, /snore loudly/i, 'No');
  await choose(u, /tired, fatigued/i, 'Yes');
  await choose(u, /stop breathing/i, 'No');
  await choose(u, /high blood pressure\?/i, 'Yes');
  await u.click(screen.getByRole('button', { name: 'Continue' }));

  const age = screen.getByLabelText(/^Age/);
  await u.clear(age);
  await u.type(age, '47');
  await choose(u, /^Sex/, 'Female');
  await u.click(screen.getByRole('button', { name: 'Continue' }));

  const none = screen.getByLabelText('None of these');
  if (!(none as HTMLInputElement).checked) {
    for (const box of screen.getAllByRole('checkbox')) if ((box as HTMLInputElement).checked) await u.click(box);
    await u.click(none);
  }
  await u.click(screen.getByRole('button', { name: 'Continue' }));

  await choose(u, /Chest pain/i, chestPain);
  await choose(u, /Fainting/i, 'No');
  await choose(u, /Severe shortness of breath/i, 'No');
  await choose(u, /Stroke symptoms/i, 'No');
  await u.click(screen.getByRole('button', { name: 'Continue' }));
}

beforeEach(() => {
  store = new DemoLocalStore(memoryStorage());
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('profile hub', () => {
  it('lists all three demo profiles with simulated-data labels and "Not started"', async () => {
    renderApp('/intake');
    expect(await screen.findByRole('heading', { name: 'Maya' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Jordan' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Riley' })).toBeInTheDocument();
    expect(screen.getAllByText('Demo')).toHaveLength(3);
    expect(screen.getAllByText('0 of 11 questions answered')).toHaveLength(3);
    await waitFor(() => expect(screen.getAllByText('Not started')).toHaveLength(3));
    expect(screen.getByRole('button', { name: 'Proceed to screening' })).toBeDisabled();
  });
});

describe('questionnaire', () => {
  it('blocks Continue on unanswered required questions and explains why', async () => {
    const u = user();
    renderApp('/intake?edit=jordan_demo');
    await screen.findByRole('heading', { name: 'Sleep and symptoms' });
    // Nothing is prefilled, so every required question starts unanswered.
    await u.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getAllByText(/Answer the breathing pauses question/).length).toBeGreaterThan(0);
    expect(screen.getByRole('heading', { name: 'Sleep and symptoms' })).toBeInTheDocument();
  });

  it('shows a numeric validation error', async () => {
    const u = user();
    renderApp('/intake?edit=maya_demo');
    await screen.findByRole('heading', { name: 'Sleep and symptoms' });
    await answerStopQuestions(u);
    await u.click(screen.getByRole('button', { name: 'Continue' }));
    const age = await screen.findByLabelText(/^Age/);
    await u.clear(age);
    await u.type(age, '200');
    await u.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getAllByText('Age must be between 18 and 110 years.').length).toBeGreaterThan(0);
  });

  it('preserves answers when going Back and Continue', async () => {
    const u = user();
    renderApp('/intake?edit=maya_demo');
    await screen.findByRole('heading', { name: 'Sleep and symptoms' });
    await answerStopQuestions(u);
    await choose(u, /snore loudly/i, 'No');
    await u.click(screen.getByRole('button', { name: 'Continue' }));
    await u.click(screen.getByRole('button', { name: 'Back' }));
    const group = screen.getByRole('group', { name: /snore loudly/i });
    expect(within(group).getByLabelText('No')).toBeChecked();
  });

  it('saves, then reopening loads the same profile answers and status is Complete', async () => {
    const u = user();
    const { unmount } = renderApp('/intake?edit=maya_demo');
    await screen.findByRole('heading', { name: 'Sleep and symptoms' });
    await answerAll(u);
    await u.click(screen.getByRole('button', { name: 'Save answers' }));
    expect(await screen.findByText('Answers saved.')).toBeInTheDocument();
    unmount();

    const rec = await store.load('maya_demo');
    expect(rec?.complete).toBe(true);
    expect(rec?.answers.age).toBe('47');

    renderApp('/intake?edit=maya_demo');
    await screen.findByRole('heading', { name: 'Sleep and symptoms' });
    expect(within(screen.getByRole('group', { name: /snore loudly/i })).getByLabelText('No')).toBeChecked();
    await u.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByLabelText(/^Age/)).toHaveValue(47);
  });

  it('editing one profile never overwrites another', async () => {
    const u = user();
    renderApp('/intake?edit=maya_demo');
    await screen.findByRole('heading', { name: 'Sleep and symptoms' });
    await answerAll(u);
    await u.click(screen.getByRole('button', { name: 'Save answers' }));
    await screen.findByText('Answers saved.');

    expect(await store.load('jordan_demo')).toBeNull();
    expect(await store.load('riley_demo')).toBeNull();
    expect((await store.load('maya_demo'))?.answers.age).toBe('47');
  });

  it('Save draft stores an incomplete questionnaire as In progress', async () => {
    const u = user();
    renderApp('/intake?edit=jordan_demo');
    await screen.findByRole('heading', { name: 'Sleep and symptoms' });
    await u.click(screen.getByRole('button', { name: 'Save draft' }));
    expect(await screen.findByText(/Draft saved/)).toBeInTheDocument();
    expect((await store.load('jordan_demo'))?.complete).toBe(false);
    await u.click(screen.getByRole('button', { name: 'Cancel' }));
    await screen.findByRole('heading', { name: 'Jordan' });
    await waitFor(() => expect(screen.getByText('In progress')).toBeInTheDocument());
  });

  it('a warning sign answered Yes shows call-911 guidance immediately', async () => {
    const u = user();
    renderApp('/intake?edit=maya_demo');
    await screen.findByRole('heading', { name: 'Sleep and symptoms' });
    await answerAll(u, { chestPain: 'Yes' });
    const alert = screen.getByRole('alert', { name: /Call 911 now/ });
    expect(alert).toHaveTextContent(/Chest pain/);
    expect(alert).toHaveTextContent(/not a diagnosis/);
  });

  it('keeps unanswered questions unanswered (never silently No)', async () => {
    renderApp('/intake?edit=jordan_demo');
    await screen.findByRole('heading', { name: 'Sleep and symptoms' });
    const pauses = screen.getByRole('group', { name: /stop breathing/i });
    expect(within(pauses).getByLabelText('Yes')).not.toBeChecked();
    expect(within(pauses).getByLabelText('No')).not.toBeChecked();
  });

  it('shows a clear error when saving fails', async () => {
    const u = user();
    const failing: QuestionnaireStore = {
      kind: 'demo-local',
      label: 'test',
      load: async () => null,
      save: async () => {
        throw new Error('Could not save on this device (storage is full or blocked).');
      },
      remove: async () => {},
      clearAll: async () => {},
    };
    renderApp('/intake?edit=maya_demo', failing);
    await screen.findByRole('heading', { name: 'Sleep and symptoms' });
    await u.click(screen.getByRole('button', { name: 'Save draft' }));
    expect(await screen.findByText(/storage is full or blocked/)).toBeInTheDocument();
  });
});

describe('screening hand-off', () => {
  it('Proceed to screening is enabled once complete and goes to the Overview with an honest note', async () => {
    const u = user();
    renderApp('/intake?edit=maya_demo');
    await screen.findByRole('heading', { name: 'Sleep and symptoms' });
    await answerAll(u);
    await u.click(screen.getByRole('button', { name: 'Save answers' }));
    await screen.findByText('Answers saved.');
    await u.click(screen.getByRole('button', { name: 'Back to profiles' }));

    const proceed = await screen.findByRole('button', { name: 'Proceed to screening' });
    await waitFor(() => expect(proceed).toBeEnabled());
    await u.click(proceed);
    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument();
    expect((await screen.findAllByText(/couldn’t update/)).length).toBeGreaterThan(0);
    expect(document.querySelector('.tier__value')).toBeNull();
  });

  it('shows missing SpO2 honestly for a profile with no SpO2 nights', async () => {
    const u = user();
    renderApp('/intake');
    await screen.findByRole('heading', { name: 'Jordan' });
    const jordanCard = screen.getByRole('article', { name: 'Jordan' });
    await u.click(within(jordanCard).getByRole('button', { name: 'Select profile' }));
    expect(await screen.findByText(/No SpO₂ was recorded/)).toBeInTheDocument();
  });
});

describe('fresh start and profile isolation', () => {
  it('every profile opens with no answers selected, even for profiles whose sample data states answers', async () => {
    for (const id of ['maya_demo', 'jordan_demo', 'riley_demo']) {
      const { unmount } = renderApp(`/intake?edit=${id}`);
      await screen.findByRole('heading', { name: 'Sleep and symptoms' });
      expect(screen.getByText('0 of 11 required answered')).toBeInTheDocument();
      expect(screen.queryAllByRole('radio', { checked: true })).toHaveLength(0);
      unmount();
    }
  });

  it('answers saved for one profile never appear in another', async () => {
    const u = user();
    const first = renderApp('/intake?edit=maya_demo');
    await screen.findByRole('heading', { name: 'Sleep and symptoms' });
    await answerAll(u, { chestPain: 'Yes' });
    await u.click(screen.getByRole('button', { name: 'Save answers' }));
    await screen.findByText('Answers saved.');
    first.unmount();

    for (const id of ['jordan_demo', 'riley_demo']) {
      window.history.replaceState({}, '', `/?persona=${id}`);
      const { unmount } = renderApp(`/intake?edit=${id}`);
      await screen.findByRole('heading', { name: 'Sleep and symptoms' });
      expect(screen.getByText('0 of 11 required answered')).toBeInTheDocument();
      expect(screen.queryAllByRole('radio', { checked: true })).toHaveLength(0);
      expect(screen.queryByRole('alert', { name: /Call 911 now/ })).not.toBeInTheDocument();
      unmount();
    }
  });

  it('ignores answers left by an older build (schema v1)', async () => {
    const backing = memoryStorage();
    const old = emptyAnswers();
    old.snoring = 'yes';
    backing.setItem(
      'wakesafe.demo.questionnaire.v1:maya_demo',
      JSON.stringify({ profileId: 'maya_demo', answers: old, complete: false, schemaVersion: 1, createdAt: 'x', updatedAt: 'x' }),
    );
    const fresh = new DemoLocalStore(backing);
    expect(await fresh.load('maya_demo')).toBeNull();
  });

  it('profile cards show Not started and 0 answered on a clean device, and no "synthetic" or "illustrative" wording', async () => {
    renderApp('/intake');
    await screen.findByRole('heading', { name: 'Maya' });
    await waitFor(() => expect(screen.getAllByText('Not started')).toHaveLength(3));
    expect(screen.getAllByText('0 of 11 questions answered')).toHaveLength(3);
    expect(document.body.textContent ?? '').not.toMatch(/synthetic|illustrative/i);
  });

  it('no page shows "synthetic" or "illustrative" wording', async () => {
    for (const path of ['/', '/sleep', '/care', '/report', '/intake?edit=riley_demo']) {
      const { unmount } = renderApp(path);
      await screen.findByRole('heading', { level: 1 });
      await waitFor(() => expect(document.body.textContent ?? '').not.toMatch(/Loading/));
      expect(document.body.textContent ?? '', path).not.toMatch(/synthetic|illustrative|demo results/i);
      unmount();
    }
  });
});
