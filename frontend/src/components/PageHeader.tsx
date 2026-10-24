import type { ReactNode } from 'react';
import { useSession } from '../hooks/useSession';
import { formatToday } from '../lib/format';

interface PageHeaderProps {
  title: string;
  subtitle?: ReactNode;
  showPersonaPicker?: boolean;
}

/** Large iOS-style page title with a muted date above and supporting text below. */
export function PageHeader({ title, subtitle, showPersonaPicker = true }: PageHeaderProps) {
  const { personas, personaId, selectPersona } = useSession();

  return (
    <header className="page-header">
      <div className="page-header__text">
        <p className="page-header__date">{formatToday()}</p>
        <h1 className="page-header__title">{title}</h1>
        {subtitle && <p className="page-header__subtitle">{subtitle}</p>}
      </div>
      {showPersonaPicker && personas.length > 0 && (
        <label className="select">
          <span className="visually-hidden">Profile</span>
          <select value={personaId ?? ''} onChange={(e) => selectPersona(e.target.value)} aria-label="Profile">
            {personaId === null && (
              <option value="" disabled>
                Choose a profile
              </option>
            )}
            {personas.map((p) => (
              <option key={p.persona_id} value={p.persona_id}>
                {p.display_name}
              </option>
            ))}
          </select>
        </label>
      )}
    </header>
  );
}
