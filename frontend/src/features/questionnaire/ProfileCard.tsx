import { useEffect } from 'react';
import { formatWindow } from '../../lib/format';
import type { AnalyzeResponse, DemoPersona } from '../../lib/types';
import { completionOf, useQuestionnaires, type CompletionStatus } from './QuestionnaireContext';
import { emptyAnswers, positiveRedFlags, progress } from './model';

const STATUS_TEXT: Record<CompletionStatus, string> = {
  loading: 'Loading…',
  error: 'Could not load',
  not_started: 'Not started',
  in_progress: 'In progress',
  complete: 'Complete',
};

interface Props {
  persona: DemoPersona;
  active: boolean;
  /** The analysis for this persona, only when it is the selected one. */
  analysis: AnalyzeResponse | null;
  onEdit: () => void;
  onProceed: () => void;
  onSelect: () => void;
}

/** One profile: questionnaire status, wearable coverage, and the next actions. */
export function ProfileCard({ persona, active, analysis, onEdit, onProceed, onSelect }: Props) {
  const q = useQuestionnaires();
  const state = q.get(persona.persona_id);
  const status = completionOf(state);
  const record = state?.status === 'ready' ? state.record : null;
  // No saved record means nothing has been answered: show 0, never a prefilled count.
  const prog = progress(record ? record.answers : emptyAnswers());
  const flags = record ? positiveRedFlags(record.answers) : [];

  useEffect(() => {
    if (!state) void q.load(persona.persona_id);
  }, [state, q, persona.persona_id]);

  const f = analysis?.features;
  const hasNights = f ? f.nights_available > 0 : false;
  const canProceed = status === 'complete' && active && hasNights;

  return (
    <article className={`profile${active ? ' profile--active' : ''}`} aria-labelledby={`p-${persona.persona_id}`}>
      <header className="profile__head">
        <div>
          <h3 id={`p-${persona.persona_id}`} className="profile__name">
            {persona.display_name}
          </h3>
          {persona.description && <p className="profile__desc">{persona.description}</p>}
        </div>
        <span className={`qstatus qstatus--${status}`}>
          <i aria-hidden="true" />
          {STATUS_TEXT[status]}
        </span>
      </header>

      <div className="profile__progress">
        <div className="profile__bar" role="img" aria-label={`${prog.answered} of ${prog.required} questions answered`}>
          <span style={{ width: `${(prog.answered / prog.required) * 100}%` }} />
        </div>
        <p className="profile__count">
          {prog.answered} of {prog.required} questions answered
          {status === 'complete' && record ? ` · saved ${new Date(record.updatedAt).toLocaleDateString()}` : ''}
        </p>
        {status === 'error' && state?.status === 'error' && <p className="field__error">{state.message}</p>}
      </div>

      <section className="profile__wearable" aria-label="Wearable data">
        <p className="profile__wearable-title">
          Wearable data <span className="demo-flag demo-flag--inline">Demo</span>
        </p>
        {active && f ? (
          <dl className="profile__stats">
            <div>
              <dt>Window</dt>
              <dd>{formatWindow(f.window_start, f.window_end)}</dd>
            </div>
            <div>
              <dt>Nights</dt>
              <dd>{f.nights_available}</dd>
            </div>
            <div>
              <dt>SpO₂</dt>
              <dd className={f.nights_with_spo2 < f.nights_available ? 'is-partial' : undefined}>
                {f.nights_with_spo2} of {f.nights_available}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="fineprint">{active ? 'Loading wearable history…' : 'Select this profile to see its wearable history.'}</p>
        )}
        {active && f && f.nights_with_spo2 === 0 && <p className="profile__warn">No SpO₂ was recorded. It stays missing; nothing is estimated.</p>}
        {active && f && !hasNights && <p className="profile__warn">No wearable nights are available for this profile.</p>}
      </section>

      {flags.length > 0 && <p className="profile__urgent">Warning signs reported. Call 911.</p>}

      <div className="profile__actions">
        {!active && (
          <button type="button" className="btn btn--soft" onClick={onSelect}>
            Select profile
          </button>
        )}
        <button type="button" className={status === 'complete' ? 'btn btn--soft' : 'btn'} onClick={onEdit} disabled={status === 'loading'}>
          {status === 'not_started' ? 'Start questionnaire' : status === 'complete' ? 'Edit answers' : 'Continue questionnaire'}
        </button>
        {active && (
          <button type="button" className="btn" onClick={onProceed} disabled={!canProceed} aria-describedby={`pr-${persona.persona_id}`}>
            Proceed to screening
          </button>
        )}
      </div>
      {active && !canProceed && (
        <p id={`pr-${persona.persona_id}`} className="fineprint">
          {status !== 'complete' ? 'Complete the questionnaire to continue.' : !hasNights ? 'Wearable nights are needed to continue.' : ''}
        </p>
      )}
    </article>
  );
}
