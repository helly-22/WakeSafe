import type { ComponentType } from 'react';
import { NavLink, Outlet } from 'react-router';
import { useInstallPrompt } from '../hooks/useInstallPrompt';
import { useSession } from '../hooks/useSession';
import { USE_MOCKS } from '../services/api';
import { SyntheticBadge } from './Badges';
import { CareIcon, IntakeIcon, MoonLogo, OverviewIcon, ReportIcon, TrendsIcon } from './Icons';

interface NavItem {
  to: string;
  label: string;
  short: string;
  Icon: ComponentType;
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Overview', short: 'Overview', Icon: OverviewIcon },
  { to: '/sleep', label: 'Sleep Trends', short: 'Trends', Icon: TrendsIcon },
  { to: '/intake', label: 'Health Intake', short: 'Intake', Icon: IntakeIcon },
  { to: '/care', label: 'Find Care', short: 'Care', Icon: CareIcon },
  { to: '/report', label: 'My Report', short: 'Report', Icon: ReportIcon },
];

function navClass({ isActive }: { isActive: boolean }) {
  return isActive ? 'nav__link nav__link--active' : 'nav__link';
}

export function AppShell() {
  const { clearSession, personaId } = useSession();
  const { canInstall, install } = useInstallPrompt();

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <aside className="sidebar">
        <div className="brand">
          <MoonLogo />
          <span className="brand__name">WakeSafe</span>
        </div>
        <nav aria-label="Primary" className="nav">
          <ul>
            {NAV_ITEMS.map(({ to, label, Icon }) => (
              <li key={to}>
                <NavLink to={to} end={to === '/'} className={navClass}>
                  <Icon />
                  <span>{label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="sidebar__footer">
          {USE_MOCKS && <SyntheticBadge compact />}
          {canInstall && (
            <button type="button" className="btn btn--small" onClick={() => void install()}>
              Install app
            </button>
          )}
          <button type="button" className="btn btn--ghost btn--small" onClick={clearSession} disabled={personaId === null}>
            Clear session
          </button>
          <p className="sidebar__note">Screening aid only. Not a diagnosis. Not affiliated with WHOOP.</p>
        </div>
      </aside>

      <header className="mobile-bar">
        <div className="brand">
          <MoonLogo />
          <span className="brand__name">WakeSafe</span>
        </div>
        <div className="mobile-bar__actions">
          {canInstall && (
            <button type="button" className="btn btn--small" onClick={() => void install()}>
              Install
            </button>
          )}
          {USE_MOCKS && <SyntheticBadge compact />}
        </div>
      </header>

      <main id="main" className="main" tabIndex={-1}>
        <Outlet />
      </main>

      <nav aria-label="Primary (mobile)" className="tabbar">
        <ul>
          {NAV_ITEMS.map(({ to, short, Icon }) => (
            <li key={to}>
              <NavLink to={to} end={to === '/'} className={navClass}>
                <Icon />
                <span>{short}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
