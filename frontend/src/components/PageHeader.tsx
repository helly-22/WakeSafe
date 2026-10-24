import type { ReactNode } from 'react';
import { useSession } from '../hooks/useSession';
import { formatToday } from '../lib/format';
import { USE_MOCKS } from '../services/api';
import { SyntheticBadge } from './Badges';

interface PageHeaderProps {
  title: string;
  subtitle?: ReactNode;
  showPersonaPicker?: boolean;
}

export function PageHeader({ title, subtitle, showPersonaPicker = true }: PageHeaderProps) {
  const { personas, personaId, selectPersona } = useSession();

  return (
    <header className="page-header">
      <div className="page-header__text">
        <p className="eyebrow">{formatToday()}</p>
        <h1 className="page-header__title">{title}</h1>
        {subtitle && <p className="page-header__subtitle">{subtitle}</p>}
      </div>
      <div className="page-header__controls">
        {USE_MOCKS && <SyntheticBadge />}
        {showPersonaPicker && personas.length > 0 && (
          <label className="select">
            <span className="visually-hidden">Demo persona</span>
            <select value={personaId ?? ''} onChange={(e) => selectPersona(e.target.value)} aria-label="Demo persona">
              {personaId === null && (
                <option value="" disabled>
                  Choose a persona
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
      </div>
    </header>
  );
}
