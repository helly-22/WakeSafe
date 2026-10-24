import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { PageHeader } from '../components/PageHeader';
import { Disclaimer, UrgentBanner } from '../components/Safety';
import { useSession } from '../hooks/useSession';

interface ShellPageProps {
  title: string;
  subtitle: string;
  /** Headline of the empty state. */
  heading: string;
  /** What this screen will show once available. */
  items: string[];
  children?: ReactNode;
}

/**
 * Deliberate "not available yet" state for screens whose services are not connected.
 * It says plainly that nothing here is working, and never shows placeholder results.
 */
export function ShellPage({ title, subtitle, heading, items, children }: ShellPageProps) {
  const { analysis } = useSession();
  return (
    <>
      <PageHeader title={title} subtitle={subtitle} />
      {analysis.status === 'ready' && <UrgentBanner assessment={analysis.data.risk_assessment} />}
      {children}
      <section className="soon" aria-labelledby="soon-title">
        <h2 id="soon-title" className="soon__title">
          {heading}
        </h2>
        <p className="soon__lead">This screen isn’t connected yet. Here is what it will show:</p>
        <ul className="soon__list">
          {items.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
        <Link className="btn btn--soft" to="/">
          Back to Overview
        </Link>
      </section>
      <Disclaimer />
    </>
  );
}
