import { SOURCE_LABEL_TEXT } from '../lib/format';
import { baselineDirection } from '../lib/metrics';
import type { SourceLabel } from '../lib/types';

export const DEMO_DISCLOSURE = 'Measurements and screening outputs are not verified clinical findings.';

const SOURCE_HELP: Record<SourceLabel, string> = {
  patient_reported: 'Answers entered in the health intake.',
  wearable_measured: 'Nightly summaries recorded by the wearable.',
  app_calculated: 'Derived by the app from other values, such as baseline comparisons.',
  model_estimated: 'Output of the screening model.',
  simulated: 'Estimated for the demo.',
};

/** Provenance marker: a colored dot and plain text, not a boxed pill. */
export function SourceTag({ source }: { source: SourceLabel }) {
  return (
    <span className={`src src--${source}`} title={SOURCE_HELP[source]}>
      <i className="src__dot" aria-hidden="true" />
      {SOURCE_LABEL_TEXT[source]}
    </span>
  );
}

export function SourceTags({ sources }: { sources: SourceLabel[] }) {
  return (
    <ul className="src-list" aria-label="Data sources">
      {sources.map((s) => (
        <li key={s}>
          <SourceTag source={s} />
        </li>
      ))}
    </ul>
  );
}

const DIRECTION_TEXT = { above: 'Above your baseline', below: 'Below your baseline', near: 'Near your baseline' } as const;

interface BaselineNoteProps {
  z: number | null | undefined;
  nightsAvailable: number;
  baselineNights: number;
  /** When true, renders nothing instead of the "needs more nights" message. */
  quietWhenUnavailable?: boolean;
}

/**
 * Where recent nights sit relative to the user's own baseline, as plain text.
 * Direction only: neutral styling on purpose, because above or below is not
 * good or bad.
 */
export function BaselineNote({ z, nightsAvailable, baselineNights, quietWhenUnavailable = false }: BaselineNoteProps) {
  const dir = baselineDirection(z);
  if (dir === null) {
    if (quietWhenUnavailable) return null;
    return (
      <span className="baseline baseline--none">
        {nightsAvailable < baselineNights ? `Baseline needs ${baselineNights} nights (${nightsAvailable} so far)` : 'No baseline comparison'}
      </span>
    );
  }
  const arrow = dir === 'above' ? '↑' : dir === 'below' ? '↓' : '→';
  return (
    <span className={`baseline baseline--${dir}`} title={`App-calculated deviation from personal baseline (z = ${z?.toFixed(1)})`}>
      <span aria-hidden="true">{arrow}</span> {DIRECTION_TEXT[dir]}
    </span>
  );
}
