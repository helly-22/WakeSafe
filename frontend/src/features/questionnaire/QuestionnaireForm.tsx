import { useMemo, useRef, useState } from 'react';
import { CheckboxGroup, ChoiceGroup, NumberField, YES_NO } from '../../components/form/fields';
import { EmergencyBanner } from '../../components/Safety';
import {
  CONDITION_OPTIONS,
  NUMERIC_FIELDS,
  RED_FLAG_OPTIONS,
  STEPS,
  missingOptional,
  positiveRedFlags,
  progress,
  validateAll,
  validateStep,
  type FieldErrors,
  type QuestionnaireAnswers,
  type Sex,
} from './model';

const SEX_OPTIONS = [
  { value: 'female', label: 'Female' },
  { value: 'male', label: 'Male' },
  { value: 'other', label: 'Another sex / prefer not to say' },
] as const;

interface Props {
  profileName: string;
  initial: QuestionnaireAnswers;
  onSave: (answers: QuestionnaireAnswers) => Promise<void>;
  onCancel: () => void;
  storeLabel: string;
}

type View = number | 'review';

const answerText = (v: string | null) => (v === null || v === '' ? 'Not answered' : v === 'yes' ? 'Yes' : v === 'no' ? 'No' : v);

/**
 * Step-by-step questionnaire. Answers live in local state across steps, so Back
 * and Continue never lose them. Nothing is scored here.
 */
export function QuestionnaireForm({ profileName, initial, onSave, onCancel, storeLabel }: Props) {
  const [answers, setAnswers] = useState<QuestionnaireAnswers>(() => structuredClone(initial));
  const [view, setView] = useState<View>(0);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [saveError, setSaveError] = useState<string | null>(null);
  const initialJson = useRef(JSON.stringify(initial));
  const topRef = useRef<HTMLDivElement>(null);

  const dirty = JSON.stringify(answers) !== initialJson.current;
  const prog = progress(answers);
  const flags = positiveRedFlags(answers);
  const allErrors = useMemo(() => validateAll(answers), [answers]);
  const stepIndex = view === 'review' ? STEPS.length : view;
  const step = typeof view === 'number' ? STEPS[view] : undefined;

  const set = <K extends keyof QuestionnaireAnswers>(key: K, value: QuestionnaireAnswers[K]) => {
    setAnswers((a) => ({ ...a, [key]: value }));
    setErrors((e) => {
      const { [key as string]: _drop, ...rest } = e;
      return rest;
    });
    setSaving((s) => (s === 'saved' ? 'idle' : s));
  };
  const setFlag = (flag: (typeof RED_FLAG_OPTIONS)[number]['value'], v: 'yes' | 'no') => {
    setAnswers((a) => ({ ...a, redFlags: { ...a.redFlags, [flag]: v } }));
    setErrors((e) => {
      const { [`redFlag:${flag}`]: _drop, ...rest } = e;
      return rest;
    });
  };

  const go = (next: View) => {
    setView(next);
    setErrors({});
    topRef.current?.scrollIntoView?.({ block: 'start' });
    topRef.current?.focus();
  };

  const onContinue = () => {
    if (!step) return;
    const e = validateStep(step.id, answers);
    if (Object.keys(e).length) {
      setErrors(e);
      return;
    }
    go(typeof view === 'number' && view < STEPS.length - 1 ? view + 1 : 'review');
  };

  const persist = async () => {
    setSaving('saving');
    setSaveError(null);
    try {
      await onSave(answers);
      initialJson.current = JSON.stringify(answers);
      setSaving('saved');
    } catch (err) {
      setSaving('error');
      setSaveError(err instanceof Error ? err.message : 'Could not save your answers.');
    }
  };

  const onCancelClick = () => {
    if (dirty && !window.confirm('Discard unsaved changes to this questionnaire?')) return;
    onCancel();
  };

  const errorList = Object.values(errors).filter(Boolean) as string[];

  return (
    <div className="qnr" ref={topRef} tabIndex={-1} aria-label={`Health questionnaire for ${profileName}`}>
      <div className="qnr__top">
        <div>
          <p className="eyebrow">Health questionnaire · {profileName}</p>
          <h2 className="qnr__title">{step ? step.title : 'Review your answers'}</h2>
          <p className="qnr__blurb">{step ? step.blurb : 'Check each section, then save. You can edit any section.'}</p>
        </div>
        <p className="qnr__count" aria-live="polite">
          {prog.answered} of {prog.required} required answered
        </p>
      </div>

      <ol className="stepper" aria-label="Questionnaire progress">
        {[...STEPS, { id: 'review', title: 'Review' }].map((s, i) => {
          const state = i < stepIndex ? 'done' : i === stepIndex ? 'current' : 'todo';
          return (
            <li key={s.id} className={`stepper__item stepper__item--${state}`} aria-current={state === 'current' ? 'step' : undefined}>
              <span className="stepper__bar" />
              <span className="stepper__label">{s.title}</span>
            </li>
          );
        })}
      </ol>

      <p className="fineprint">
        <span className="field__req" aria-hidden="true">
          *
        </span>{' '}
        Required. Screening is not a diagnosis.
      </p>

      {errorList.length > 0 && (
        <div className="qnr__errors" role="alert">
          <p>Please fix {errorList.length === 1 ? 'this' : `these ${errorList.length}`} before continuing:</p>
          <ul>
            {errorList.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}

      {flags.length > 0 && (
        <EmergencyBanner
          reasons={flags.map((f) => `Reported: ${RED_FLAG_OPTIONS.find((o) => o.value === f)?.label ?? f}`)}
          intro="You reported a warning sign that can mean a medical emergency. Call 911 or your local emergency number now. This questionnaire cannot assess emergencies and is not a diagnosis."
        />
      )}

      <form
        className="qnr__body"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          if (view === 'review') void persist();
          else onContinue();
        }}
      >
        {step?.id === 'stopbang' && (
          <>
            <ChoiceGroup name="snoring" label="Do you snore loudly?" hint="Louder than talking, or loud enough to be heard through a closed door." required value={answers.snoring} options={YES_NO} onChange={(v) => set('snoring', v)} error={errors.snoring} />
            <ChoiceGroup name="tired" label="Do you often feel tired, fatigued or sleepy during the day?" required value={answers.daytimeTiredness} options={YES_NO} onChange={(v) => set('daytimeTiredness', v)} error={errors.daytimeTiredness} />
            <ChoiceGroup name="pauses" label="Has anyone observed you stop breathing, choke or gasp during sleep?" required value={answers.witnessedPauses} options={YES_NO} onChange={(v) => set('witnessedPauses', v)} error={errors.witnessedPauses} />
            <ChoiceGroup name="bp" label="Do you have, or are you being treated for, high blood pressure?" required value={answers.highBloodPressure} options={YES_NO} onChange={(v) => set('highBloodPressure', v)} error={errors.highBloodPressure} />
          </>
        )}

        {step?.id === 'body' && (
          <>
            <div className="qnr__grid">
              <NumberField label="Age" unit="years" required min={18} max={110} step="1" value={answers.age} onChange={(v) => set('age', v)} error={errors.age} />
              <NumberField label="Neck circumference" unit="cm" hint="Measured around the middle of the neck." min={25} max={65} value={answers.neckCm} onChange={(v) => set('neckCm', v)} error={errors.neckCm} />
              <NumberField label="Height" unit="cm" hint="Used with weight to calculate BMI." min={120} max={230} value={answers.heightCm} onChange={(v) => set('heightCm', v)} error={errors.heightCm} />
              <NumberField label="Weight" unit="kg" min={30} max={300} value={answers.weightKg} onChange={(v) => set('weightKg', v)} error={errors.weightKg} />
            </div>
            <ChoiceGroup<Exclude<Sex, null>> name="sex" label="Sex" hint="STOP-Bang uses male sex as one item. “Another sex” is recorded as unknown for that item." required value={answers.sex} options={SEX_OPTIONS} onChange={(v) => set('sex', v)} error={errors.sex} />
            {missingOptional(answers).length > 0 && (
              <p className="qnr__note">
                Left blank: {missingOptional(answers).join(', ')}. Blank answers are treated as unknown.
              </p>
            )}
          </>
        )}

        {step?.id === 'history' && (
          <CheckboxGroup
            label="Has a clinician told you that you have any of these?"
            hint="Select all that apply."
            required
            options={CONDITION_OPTIONS}
            value={answers.conditions}
            onChange={(v) => set('conditions', v)}
            noneLabel="None of these"
            error={errors.conditions}
          />
        )}

        {step?.id === 'emergency' && (
          <>
            <p className="qnr__note qnr__note--strong">
              Are you experiencing any of these <strong>right now or in the last few hours</strong>? If yes, stop and call 911.
            </p>
            {RED_FLAG_OPTIONS.map((o) => (
              <ChoiceGroup key={o.value} name={`flag-${o.value}`} label={o.label} required value={answers.redFlags[o.value]} options={YES_NO} onChange={(v) => setFlag(o.value, v)} error={errors[`redFlag:${o.value}`]} />
            ))}
          </>
        )}

        {view === 'review' && (
          <div className="review">
            {STEPS.map((s, i) => {
              const stepErrs = validateStep(s.id, answers);
              const rows: Array<[string, string]> =
                s.id === 'stopbang'
                  ? [
                      ['Loud snoring', answerText(answers.snoring)],
                      ['Daytime tiredness', answerText(answers.daytimeTiredness)],
                      ['Observed breathing pauses', answerText(answers.witnessedPauses)],
                      ['High blood pressure', answerText(answers.highBloodPressure)],
                    ]
                  : s.id === 'body'
                    ? [
                        ['Age', answers.age ? `${answers.age} years` : 'Not answered'],
                        ['Sex', answers.sex === 'other' ? 'Another sex / prefer not to say' : answerText(answers.sex)],
                        ...(Object.keys(NUMERIC_FIELDS) as Array<keyof typeof NUMERIC_FIELDS>)
                          .filter((k) => k !== 'age')
                          .map((k): [string, string] => [NUMERIC_FIELDS[k].label, answers[k] ? `${answers[k]} ${NUMERIC_FIELDS[k].unit}` : 'Not answered']),
                      ]
                    : s.id === 'history'
                      ? [
                          [
                            'Conditions',
                            answers.conditions === null
                              ? 'Not answered'
                              : answers.conditions.length === 0
                                ? 'None of these'
                                : answers.conditions.map((c) => CONDITION_OPTIONS.find((o) => o.value === c)?.label ?? c).join(', '),
                          ],
                        ]
                      : RED_FLAG_OPTIONS.map((o): [string, string] => [o.label, answerText(answers.redFlags[o.value])]);
              return (
                <section key={s.id} className="review__sec" aria-labelledby={`rev-${s.id}`}>
                  <div className="review__head">
                    <h3 id={`rev-${s.id}`} className="review__title">
                      {s.title}
                      {Object.keys(stepErrs).length > 0 && <span className="review__flag"> · incomplete</span>}
                    </h3>
                    <button type="button" className="btn btn--ghost btn--small" onClick={() => go(i)}>
                      Edit
                    </button>
                  </div>
                  <dl className="kv">
                    {rows.map(([k, v]) => (
                      <div key={k} className="kv__row">
                        <dt>{k}</dt>
                        <dd className={v === 'Not answered' ? 'muted' : undefined}>{v}</dd>
                      </div>
                    ))}
                  </dl>
                </section>
              );
            })}
          </div>
        )}

        <div className="qnr__actions">
          <button type="button" className="btn btn--ghost" onClick={onCancelClick}>
            Cancel
          </button>
          <span className="qnr__spacer" />
          {view !== 0 && (
            <button type="button" className="btn btn--ghost" onClick={() => go(view === 'review' ? STEPS.length - 1 : (view as number) - 1)}>
              Back
            </button>
          )}
          {view !== 'review' && (
            <button type="button" className="btn btn--ghost" onClick={() => void persist()} disabled={saving === 'saving'}>
              Save draft
            </button>
          )}
          <button type="submit" className="btn" disabled={saving === 'saving'}>
            {view === 'review'
              ? saving === 'saving'
                ? 'Saving…'
                : Object.keys(allErrors).length
                  ? 'Save (incomplete)'
                  : 'Save answers'
              : 'Continue'}
          </button>
        </div>

        <p className="qnr__status" role="status" aria-live="polite">
          {saving === 'saving' && 'Saving…'}
          {saving === 'saved' && (Object.keys(allErrors).length ? 'Draft saved. Some required questions are still unanswered.' : 'Answers saved.')}
          {saving === 'error' && <span className="field__error">{saveError}</span>}
          {saving === 'idle' && dirty && 'Unsaved changes'}
        </p>
        <p className="fineprint">{storeLabel}. No real personal health information should be entered in this demo.</p>
      </form>
    </div>
  );
}
