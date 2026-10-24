import { useId, type ReactNode } from 'react';

interface FieldShellProps {
  label: string;
  required?: boolean;
  hint?: string;
  error?: string;
  children: (ids: { describedBy: string | undefined; invalid: boolean }) => ReactNode;
  as?: 'fieldset' | 'div';
  htmlFor?: string;
}

/** Label, required marker, hint and error, wired with aria-describedby. */
function FieldShell({ label, required, hint, error, children, as = 'fieldset', htmlFor }: FieldShellProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const describedBy = [hintId, errId].filter(Boolean).join(' ') || undefined;
  const labelBody = (
    <>
      {label}
      {required ? (
        <span className="field__req" aria-hidden="true">
          {' '}
          *
        </span>
      ) : (
        <span className="field__opt"> (optional)</span>
      )}
      {required && <span className="visually-hidden"> (required)</span>}
    </>
  );
  const body = (
    <>
      {hint && (
        <p id={hintId} className="field__hint">
          {hint}
        </p>
      )}
      {children({ describedBy, invalid: Boolean(error) })}
      {error && (
        <p id={errId} className="field__error" role="alert">
          {error}
        </p>
      )}
    </>
  );
  if (as === 'div') {
    return (
      <div className={`field${error ? ' field--invalid' : ''}`}>
        <label className="field__label" htmlFor={htmlFor}>
          {labelBody}
        </label>
        {body}
      </div>
    );
  }
  return (
    <fieldset className={`field${error ? ' field--invalid' : ''}`} aria-describedby={describedBy}>
      <legend className="field__label">{labelBody}</legend>
      {body}
    </fieldset>
  );
}

export interface ChoiceOption<T extends string> {
  value: T;
  label: string;
}

interface ChoiceGroupProps<T extends string> {
  name: string;
  label: string;
  value: T | null;
  options: ReadonlyArray<ChoiceOption<T>>;
  onChange: (v: T) => void;
  required?: boolean;
  hint?: string;
  error?: string;
}

/** Radio group rendered as segmented buttons. `null` means not answered yet. */
export function ChoiceGroup<T extends string>({ name, label, value, options, onChange, required, hint, error }: ChoiceGroupProps<T>) {
  const id = useId();
  return (
    <FieldShell label={label} required={required} hint={hint} error={error}>
      {({ invalid }) => (
        <div className="choice" role="radiogroup" aria-invalid={invalid || undefined}>
          {options.map((o) => (
            <label key={o.value} className={`choice__opt${value === o.value ? ' choice__opt--on' : ''}`}>
              <input type="radio" name={`${name}-${id}`} value={o.value} checked={value === o.value} onChange={() => onChange(o.value)} />
              <span>{o.label}</span>
            </label>
          ))}
        </div>
      )}
    </FieldShell>
  );
}

export const YES_NO: ReadonlyArray<ChoiceOption<'yes' | 'no'>> = [
  { value: 'yes', label: 'Yes' },
  { value: 'no', label: 'No' },
];

interface NumberFieldProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  unit: string;
  required?: boolean;
  hint?: string;
  error?: string;
  min?: number;
  max?: number;
  step?: string;
}

/** Numeric input kept as a string so "blank" never turns into 0. */
export function NumberField({ label, value, onChange, unit, required, hint, error, min, max, step = 'any' }: NumberFieldProps) {
  const id = useId();
  return (
    <FieldShell label={label} required={required} hint={hint} error={error} as="div" htmlFor={id}>
      {({ describedBy, invalid }) => (
        <div className="num">
          <input
            id={id}
            className="num__input"
            type="number"
            inputMode="decimal"
            value={value}
            min={min}
            max={max}
            step={step}
            aria-invalid={invalid || undefined}
            aria-describedby={describedBy}
            onChange={(e) => onChange(e.target.value)}
          />
          <span className="num__unit">{unit}</span>
        </div>
      )}
    </FieldShell>
  );
}

interface CheckboxGroupProps<T extends string> {
  label: string;
  options: ReadonlyArray<{ value: T; label: string; group?: string }>;
  /** null = not answered; [] = explicitly none. */
  value: T[] | null;
  onChange: (v: T[] | null) => void;
  noneLabel: string;
  required?: boolean;
  hint?: string;
  error?: string;
}

/** Multi-select with an exclusive "None of these" so an empty answer is explicit. */
export function CheckboxGroup<T extends string>({ label, options, value, onChange, noneLabel, required, hint, error }: CheckboxGroupProps<T>) {
  const selected = value ?? [];
  const groups = Array.from(new Set(options.map((o) => o.group ?? '')));
  const toggle = (v: T) => {
    const next = selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v];
    onChange(next.length ? next : null);
  };
  return (
    <FieldShell label={label} required={required} hint={hint} error={error}>
      {() => (
        <div className="checks">
          {groups.map((g) => (
            <div key={g || 'all'} className="checks__group">
              {g && <p className="checks__head">{g}</p>}
              {options
                .filter((o) => (o.group ?? '') === g)
                .map((o) => (
                  <label key={o.value} className={`check${selected.includes(o.value) ? ' check--on' : ''}`}>
                    <input type="checkbox" checked={selected.includes(o.value)} onChange={() => toggle(o.value)} />
                    <span>{o.label}</span>
                  </label>
                ))}
            </div>
          ))}
          <label className={`check check--none${value !== null && value.length === 0 ? ' check--on' : ''}`}>
            <input
              type="checkbox"
              checked={value !== null && value.length === 0}
              onChange={(e) => onChange(e.target.checked ? [] : null)}
            />
            <span>{noneLabel}</span>
          </label>
        </div>
      )}
    </FieldShell>
  );
}
