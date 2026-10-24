import { formatTooltipDate } from '../../lib/format';
import type { AnalyzeResponse } from '../../lib/types';
import { useSession } from '../../hooks/useSession';
import { useQuestionnaires } from '../questionnaire/QuestionnaireContext';
import type { QuestionnaireAnswers, YesNo } from '../questionnaire/model';
import { SIGNALS, countSignal } from './signalCounts';

const SYMPTOMS: Array<{ key: 'snoring' | 'daytimeTiredness' | 'witnessedPauses' | 'highBloodPressure'; label: string }> = [
  { key: 'snoring', label: 'Loud snoring' },
  { key: 'daytimeTiredness', label: 'Daytime tiredness' },
  { key: 'witnessedPauses', label: 'Observed breathing pauses' },
  { key: 'highBloodPressure', label: 'High blood pressure' },
];

const STATUS_TEXT: Record<'yes' | 'no' | 'none', string> = { yes: 'Reported', no: 'Not reported', none: 'Not answered' };
const statusOf = (v: YesNo): 'yes' | 'no' | 'none' => (v === null ? 'none' : v);

/** Counts of what you reported, straight from your saved answers. */
function ReportedSymptoms({ answers, detail }: { answers: QuestionnaireAnswers | null; detail: boolean }) {
  if (!answers) {
    return (
      <section className="viz" aria-label="Reported symptoms">
        <h4 className="legend-head">Reported symptoms</h4>
        <p className="viz__empty">Answer the questionnaire to see your reported symptoms here.</p>
      </section>
    );
  }
  const states = SYMPTOMS.map((s) => statusOf(answers[s.key]));
  const yes = states.filter((s) => s === 'yes').length;
  const none = states.filter((s) => s === 'none').length;
  return (
    <section className="viz" aria-label="Reported symptoms">
      <div className="viz__head">
        <h4 className="legend-head">Reported symptoms</h4>
        <p className="viz__total">
          <b>{yes}</b> of {SYMPTOMS.length} reported{none > 0 ? ` · ${none} not answered` : ''}
        </p>
      </div>
      {detail ? (
        <ul className="symp">
          {SYMPTOMS.map((s, i) => {
            const st = states[i]!;
            return (
              <li key={s.key} className={`symp__row symp__row--${st}`}>
                <span className="symp__seg" aria-hidden="true" />
                <span className="symp__label">{s.label}</span>
                <span className="symp__status">{STATUS_TEXT[st]}</span>
              </li>
            );
          })}
        </ul>
      ) : (
        yes > 0 && (
          <ul className="tags">
            {SYMPTOMS.filter((_, i) => states[i] === 'yes').map((s) => (
              <li key={s.key}>{s.label}</li>
            ))}
          </ul>
        )
      )}
    </section>
  );
}

/** Per-signal counts of nights; with `detail`, one dot per night. Gaps stay gaps. */
function WearableSignals({ nights, detail }: { nights: NonNullable<AnalyzeResponse['nights']>; detail: boolean }) {
  return (
    <section className="viz" aria-label="Wearable signals across nights">
      <div className="viz__head">
        <h4 className="legend-head">Wearable signals across {nights.length} nights</h4>
      </div>
      <ul className="sig">
        {SIGNALS.map((spec) => {
          const c = countSignal(nights, spec);
          const summary = c.comparable
            ? `${c.hits} of ${c.recorded} recorded nights`
            : c.recorded === 0
              ? 'No nights recorded'
              : `Only ${c.recorded} recorded, too few to compare`;
          return (
            <li key={spec.key} className="sig__row">
              <div className="sig__top">
                <span className="sig__label">{spec.label}</span>
                <span className="sig__count">{summary}</span>
              </div>
              {detail && (
                <div
                  className="sig__strip"
                  role="img"
                  aria-label={`${spec.label}: ${summary}${c.recorded < c.total ? `; ${c.total - c.recorded} nights have no data` : ''}`}
                  style={{ gridTemplateColumns: `repeat(${c.marks.length}, minmax(0, 1fr))` }}
                >
                  {c.marks.map((m) => (
                    <span
                      key={m.date}
                      className={`sig__cell sig__cell--${m.state}`}
                      title={`${formatTooltipDate(m.date)}: ${
                        m.state === 'missing' ? 'no data recorded' : m.state === 'hit' ? `${spec.side} your average` : m.state === 'clear' ? 'not ' + spec.side + ' your average' : 'recorded'
                      }`}
                    />
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** What the result rests on: your reported symptoms and counts of wearable nights. `detail` adds the per-night dots. */
export function ScreeningSignals({ data, detail = false }: { data: AnalyzeResponse; detail?: boolean }) {
  const { persona } = useSession();
  const q = useQuestionnaires();
  const state = persona ? q.get(persona.persona_id) : undefined;
  const answers = state?.status === 'ready' && state.record ? state.record.answers : null;

  return (
    <div className="vizs">
      <ReportedSymptoms answers={answers} detail={detail} />
      {data.nights && data.nights.length > 0 ? (
        <WearableSignals nights={data.nights} detail={detail} />
      ) : (
        <section className="viz" aria-label="Wearable signals across nights">
          <h4 className="legend-head">Wearable signals</h4>
          <p className="viz__empty">Nightly wearable records are not available.</p>
        </section>
      )}
    </div>
  );
}
