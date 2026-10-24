import { Card } from '../components/Card';
import { SourceTag } from '../components/Badges';
import { useSession } from '../hooks/useSession';
import { ShellPage } from './ShellPage';

function yesNo(v: boolean | null | undefined) {
  if (v === null || v === undefined) return 'Not answered';
  return v ? 'Yes' : 'No';
}

export function HealthIntakePage() {
  const { persona } = useSession();
  const p = persona?.profile;

  return (
    <ShellPage
      title="Health Intake"
      subtitle="Reported history and symptoms. Names and dates of birth are never required."
      planned={[
        'Editable STOP-Bang-style questions (field list pending team confirmation)',
        'Medical history and conditions',
        'Red-flag symptom check that routes straight to emergency guidance',
        'CSV upload as an alternative to demo personas',
      ]}
    >
      {p && persona && (
        <Card
          eyebrow="Reported answers"
          title={persona.display_name}
          className="dash__full"
          action={<SourceTag source="patient_reported" />}
        >
          <dl className="kv">
            <dt>Age</dt>
            <dd>{p.age ?? 'Not answered'}</dd>
            <dt>Snoring</dt>
            <dd>{yesNo(p.snoring)}</dd>
            <dt>Daytime tiredness</dt>
            <dd>{yesNo(p.daytime_tiredness)}</dd>
            <dt>Witnessed breathing pauses</dt>
            <dd>{yesNo(p.witnessed_breathing_pauses)}</dd>
            <dt>High blood pressure</dt>
            <dd>{yesNo(p.hypertension)}</dd>
            <dt>Red-flag symptoms</dt>
            <dd>{p.red_flag_symptoms.length ? p.red_flag_symptoms.join(', ') : 'None reported'}</dd>
          </dl>
          <p className="fineprint">Synthetic persona answers, shown for illustration. They are read-only in this milestone.</p>
        </Card>
      )}
    </ShellPage>
  );
}
