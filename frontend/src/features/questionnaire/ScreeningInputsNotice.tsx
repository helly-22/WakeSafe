import { Link } from 'react-router';
import { DEMO_DISCLOSURE } from '../../components/Badges';
import { EmergencyBanner } from '../../components/Safety';
import { useSession } from '../../hooks/useSession';
import { completionOf, useQuestionnaires } from './QuestionnaireContext';
import { RED_FLAG_OPTIONS, positiveRedFlags } from './model';

/**
 * Call-911 guidance as soon as saved questionnaire answers report a warning sign,
 * on every page, even before the screening has been re-run. Skipped when the
 * current screening already returned urgent_override (its banner is shown instead).
 */
export function QuestionnaireEmergency() {
  const { persona, analysis } = useSession();
  const q = useQuestionnaires();
  if (!persona) return null;
  const state = q.get(persona.persona_id);
  const record = state?.status === 'ready' ? state.record : null;
  const flags = record ? positiveRedFlags(record.answers) : [];
  const backendUrgent = analysis.status === 'ready' && analysis.data.risk_assessment.urgent_override;
  if (flags.length === 0 || backendUrgent) return null;
  return (
    <EmergencyBanner reasons={flags.map((f) => `Reported in the questionnaire: ${RED_FLAG_OPTIONS.find((o) => o.value === f)?.label ?? f}`)} />
  );
}

/** One calm line on Overview saying exactly what the screening on screen was run on. */
export function ScreeningInputsNotice() {
  const { persona, analysis } = useSession();
  const q = useQuestionnaires();
  if (!persona) return null;
  const status = completionOf(q.get(persona.persona_id));
  if (status === 'loading' || analysis.status !== 'ready') return null;
  const edit = `/intake?edit=${persona.persona_id}`;
  const started = status === 'complete' || status === 'in_progress';

  let message: string;
  switch (analysis.screening) {
    case 'live':
      message = started
        ? `Screened with your ${status === 'in_progress' ? 'partly completed ' : ''}answers and your wearable data.`
        : 'Screened with this profile’s sample answers and its wearable data.';
      break;
    case 'not_rerun':
      message = 'Your answers are saved, but your risk estimate couldn’t be updated.';
      break;
    default:
      message = DEMO_DISCLOSURE;
  }

  return (
    <p className={`inputs-note${status === 'complete' ? '' : ' inputs-note--todo'}`} role="note">
      {message}{' '}
      {started ? (
        <Link to={edit}>{status === 'in_progress' ? 'Finish your answers' : 'Edit your answers'}</Link>
      ) : (
        <>
          You haven’t started the questionnaire. <Link to={edit}>Start it</Link> to personalize your screening.
        </>
      )}
    </p>
  );
}
