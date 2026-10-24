/** Minimal stroke icons, decorative only (always paired with visible text). */
const base = {
  width: 20,
  height: 20,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
};

export const OverviewIcon = () => (
  <svg {...base}>
    <circle cx="12" cy="12" r="8" />
    <path d="M12 4a8 8 0 0 1 8 8" strokeWidth={3} />
  </svg>
);
export const TrendsIcon = () => (
  <svg {...base}>
    <path d="M4 19V5M4 19h16M8 15l3-4 3 2 5-6" />
  </svg>
);
export const IntakeIcon = () => (
  <svg {...base}>
    <rect x="5" y="4" width="14" height="17" rx="2" />
    <path d="M9 4h6v3H9zM9 12h6M9 16h4" />
  </svg>
);
export const CareIcon = () => (
  <svg {...base}>
    <path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" />
    <path d="M12 7v5M9.5 9.5h5" />
  </svg>
);
export const ReportIcon = () => (
  <svg {...base}>
    <path d="M7 3h7l5 5v13H7z" />
    <path d="M14 3v5h5M10 13h6M10 17h6" />
  </svg>
);
export const MoonLogo = () => (
  <svg width={26} height={26} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="12" cy="12" r="10.5" stroke="var(--teal)" strokeWidth={1.6} />
    <path d="M15.5 7.2a5.6 5.6 0 1 0 1.3 9.3 4.6 4.6 0 0 1-1.3-9.3z" fill="var(--teal)" />
  </svg>
);
