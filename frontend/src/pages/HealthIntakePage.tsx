import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { PageHeader } from '../components/PageHeader';
import { Disclaimer } from '../components/Safety';
import { ProfileCard } from '../features/questionnaire/ProfileCard';
import { useQuestionnaires } from '../features/questionnaire/QuestionnaireContext';
import { QuestionnaireForm } from '../features/questionnaire/QuestionnaireForm';
import { emptyAnswers } from '../features/questionnaire/model';
import { useSession } from '../hooks/useSession';

const COLLAPSED_COUNT = 6;

/**
 * Profile hub: each demo profile with its questionnaire status, and the
 * questionnaire itself (?edit=<profile id>). Questionnaires always start blank;
 * answers are stored per profile id and only appear once the user enters them.
 */
export function HealthIntakePage() {
  const { personas, personaId, analysis, selectPersona } = useSession();
  const q = useQuestionnaires();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const editId = params.get('edit');
  const editing = personas.find((p) => p.persona_id === editId) ?? null;
  const [savedNote, setSavedNote] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  const editState = editing ? q.get(editing.persona_id) : undefined;
  useEffect(() => {
    if (editing && !editState) void q.load(editing.persona_id);
  }, [editing, editState, q]);

  const openEditor = (id: string) => {
    setSavedNote(null);
    setParams({ edit: id });
  };
  const closeEditor = () => setParams({});

  if (editing) {
    if (!editState || editState.status === 'loading') {
      return (
        <>
          <PageHeader title="Health Intake" showPersonaPicker={false} />
          <p className="state state--loading" role="status">
            Loading your answers…
          </p>
        </>
      );
    }
    if (editState.status === 'error') {
      return (
        <>
          <PageHeader title="Health Intake" showPersonaPicker={false} />
          <div className="state state--error" role="alert">
            <p>{editState.message}</p>
            <button type="button" className="btn btn--ghost" onClick={closeEditor}>
              Back to profiles
            </button>
          </div>
        </>
      );
    }
    // Saved answers only. Nothing is prefilled from the profile's sample data.
    const initial = editState.record?.answers ?? emptyAnswers();
    return (
      <>
        <PageHeader title="Health Intake" subtitle="Your answers are saved for this profile only." showPersonaPicker={false} />
        <QuestionnaireForm
          key={editing.persona_id}
          profileName={editing.display_name}
          initial={initial}
          storeLabel={q.storeLabel}
          onCancel={closeEditor}
          onSave={async (answers) => {
            const rec = await q.save(editing.persona_id, answers);
            setSavedNote(rec.complete ? `${editing.display_name}: questionnaire complete.` : `${editing.display_name}: draft saved.`);
          }}
        />
        {savedNote && (
          <p className="fineprint">
            {savedNote}{' '}
            <button type="button" className="linkish" onClick={closeEditor}>
              Back to profiles
            </button>
          </p>
        )}
        <Disclaimer />
      </>
    );
  }

  const activeAnalysis = analysis.status === 'ready' ? analysis.data : null;
  // A long list starts collapsed to the first few profiles (and the selected one).
  const collapsed = !showAll && personas.length > COLLAPSED_COUNT;
  const shown = collapsed ? personas.filter((p, i) => i < COLLAPSED_COUNT || p.persona_id === personaId) : personas;
  return (
    <>
      <PageHeader title="Health Intake" subtitle="Choose a profile, answer a few questions, then continue to your screening." showPersonaPicker={false} />
      {personas.length === 0 ? (
        <p className={`state${analysis.status === 'error' ? ' state--error' : ' state--loading'}`} role={analysis.status === 'error' ? 'alert' : 'status'}>
          {analysis.status === 'error' ? analysis.message : 'Loading profiles…'}
        </p>
      ) : (
        <div className="profiles">
          {shown.map((p) => (
            <ProfileCard
              key={p.persona_id}
              persona={p}
              active={p.persona_id === personaId}
              analysis={p.persona_id === personaId ? activeAnalysis : null}
              onSelect={() => selectPersona(p.persona_id)}
              onEdit={() => openEditor(p.persona_id)}
              onProceed={() => {
                selectPersona(p.persona_id);
                navigate('/');
              }}
            />
          ))}
        </div>
      )}
      {collapsed && (
        <button type="button" className="btn btn--soft" onClick={() => setShowAll(true)}>
          Show all {personas.length} profiles
        </button>
      )}
      <Disclaimer />
    </>
  );
}
