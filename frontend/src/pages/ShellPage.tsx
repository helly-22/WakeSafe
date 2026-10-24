import type { ReactNode } from 'react';
import { Card } from '../components/Card';
import { PageHeader } from '../components/PageHeader';
import { Disclaimer, UrgentBanner } from '../components/Safety';
import { useSession } from '../hooks/useSession';

interface ShellPageProps {
  title: string;
  subtitle: string;
  planned: string[];
  children?: ReactNode;
}

/** Layout for screens that are planned but not built in this milestone. Planned items are plainly labeled. */
export function ShellPage({ title, subtitle, planned, children }: ShellPageProps) {
  const { analysis } = useSession();
  return (
    <>
      <PageHeader title={title} subtitle={subtitle} />
      {analysis.status === 'ready' && <UrgentBanner assessment={analysis.data.risk_assessment} />}
      <div className="dash dash--shell">
        {children}
        <Card eyebrow="Coming next" title="Planned for this screen" className="dash__full roadmap">
          <ol className="roadmap__list">
            {planned.map((p, i) => (
              <li key={p}>
                <span className="roadmap__n" aria-hidden="true">
                  {String(i + 1).padStart(2, '0')}
                </span>
                {p}
              </li>
            ))}
          </ol>
          <p className="fineprint">Not built yet in this milestone. Nothing on this screen is a working feature.</p>
        </Card>
      </div>
      <Disclaimer />
    </>
  );
}
