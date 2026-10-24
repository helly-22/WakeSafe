import { Link } from 'react-router';
import { Card } from '../../components/Card';
import { CareIcon, IntakeIcon, ReportIcon } from '../../components/Icons';

const STEPS = [
  { to: '/intake', label: 'Health Intake', text: 'Review reported history and symptoms', Icon: IntakeIcon },
  { to: '/care', label: 'Find Care', text: 'Care options matched to this screening', Icon: CareIcon },
  { to: '/report', label: 'My Report', text: 'A clinician-ready summary to bring along', Icon: ReportIcon },
];

export function NextStepsCard({ urgent, className }: { urgent: boolean; className?: string }) {
  return (
    <Card eyebrow="Next steps" title="Where to go from here" className={className}>
      {urgent && (
        <p className="inline-alert" role="note">
          Call 911 first. These steps are for after the urgent concern is addressed.
        </p>
      )}
      <ul className="steps">
        {STEPS.map(({ to, label, text, Icon }) => (
          <li key={to}>
            <Link to={to} className="steps__link">
              <span className="steps__icon">
                <Icon />
              </span>
              <span className="steps__body">
                <span className="steps__label">{label}</span>
                <span className="steps__text">{text}</span>
              </span>
              <span className="steps__chevron" aria-hidden="true">
                ›
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
