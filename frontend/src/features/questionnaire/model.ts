/**
 * Health questionnaire: answer types, validation and the mapping to the shared
 * ProfileInput contract (TEAM_CONTRACTS.md §3.1, backend/app/models/schemas.py).
 *
 * Rules:
 *  - Unanswered is `null`, never `false` or `0`. "No" is an explicit answer.
 *  - Condition and red-flag strings are the exact lower-case phrases the
 *    backend risk rules match (backend/app/services/risks/rules.py).
 *  - No scoring here. The backend computes STOP-Bang and every risk tier.
 */
import type { ProfileInput } from '../../lib/types';

export type YesNo = 'yes' | 'no' | null;
export type Sex = 'male' | 'female' | 'other' | null;

export const CONDITION_OPTIONS = [
  { value: 'hypertension', label: 'High blood pressure (diagnosed)', group: 'Heart and circulation' },
  { value: 'coronary heart disease', label: 'Coronary heart disease', group: 'Heart and circulation' },
  { value: 'atrial fibrillation', label: 'Atrial fibrillation', group: 'Heart and circulation' },
  { value: 'heart failure', label: 'Heart failure', group: 'Heart and circulation' },
  { value: 'diabetes', label: 'Diabetes', group: 'Metabolic' },
  { value: 'prediabetes', label: 'Prediabetes', group: 'Metabolic' },
  { value: 'obesity', label: 'Obesity (diagnosed)', group: 'Metabolic' },
  { value: 'high cholesterol', label: 'High cholesterol', group: 'Metabolic' },
  { value: 'thyroid condition', label: 'Thyroid condition', group: 'Metabolic' },
  { value: 'asthma', label: 'Asthma', group: 'Lungs and breathing' },
  { value: 'copd', label: 'COPD', group: 'Lungs and breathing' },
  { value: 'sleep apnea', label: 'Previously diagnosed sleep apnea', group: 'Lungs and breathing' },
  { value: 'recent illness', label: 'Recent illness or infection (last 2 weeks)', group: 'Recent health' },
  { value: 'immunocompromised', label: 'Weakened immune system', group: 'Recent health' },
] as const;
export type ConditionValue = (typeof CONDITION_OPTIONS)[number]['value'];

export const RED_FLAG_OPTIONS = [
  { value: 'chest pain', label: 'Chest pain or pressure' },
  { value: 'fainting', label: 'Fainting or passing out' },
  { value: 'severe shortness of breath', label: 'Severe shortness of breath' },
  { value: 'stroke symptoms', label: 'Stroke symptoms (face drooping, arm weakness, slurred speech)' },
] as const;
export type RedFlagValue = (typeof RED_FLAG_OPTIONS)[number]['value'];

export interface QuestionnaireAnswers {
  // STOP-Bang
  snoring: YesNo;
  daytimeTiredness: YesNo;
  witnessedPauses: YesNo;
  highBloodPressure: YesNo;
  age: string;
  sex: Sex;
  heightCm: string;
  weightKg: string;
  neckCm: string;
  // History: null = not answered yet; [] = explicitly "none of these".
  conditions: ConditionValue[] | null;
  // Emergency signs: per symptom, never defaulted.
  redFlags: Record<RedFlagValue, YesNo>;
}

export function emptyAnswers(): QuestionnaireAnswers {
  return {
    snoring: null,
    daytimeTiredness: null,
    witnessedPauses: null,
    highBloodPressure: null,
    age: '',
    sex: null,
    heightCm: '',
    weightKg: '',
    neckCm: '',
    conditions: null,
    redFlags: { 'chest pain': null, fainting: null, 'severe shortness of breath': null, 'stroke symptoms': null },
  };
}

export type StepId = 'stopbang' | 'body' | 'history' | 'emergency';
export const STEPS: Array<{ id: StepId; title: string; blurb: string }> = [
  { id: 'stopbang', title: 'Sleep and symptoms', blurb: 'Four yes/no questions from the STOP-Bang screening.' },
  { id: 'body', title: 'About you', blurb: 'Age, sex and body measurements used by STOP-Bang.' },
  { id: 'history', title: 'Medical history', blurb: 'Conditions a clinician has told you about.' },
  { id: 'emergency', title: 'Warning signs', blurb: 'Symptoms that need emergency care, not screening.' },
];

export type FieldErrors = Partial<Record<string, string>>;

/** Numeric bounds: plausible adult ranges, to catch typos (e.g. height in metres). */
export const NUMERIC_FIELDS = {
  age: { label: 'Age', min: 18, max: 110, unit: 'years', integer: true, required: true },
  heightCm: { label: 'Height', min: 120, max: 230, unit: 'cm', integer: false, required: false },
  weightKg: { label: 'Weight', min: 30, max: 300, unit: 'kg', integer: false, required: false },
  neckCm: { label: 'Neck circumference', min: 25, max: 65, unit: 'cm', integer: false, required: false },
} as const;
type NumericKey = keyof typeof NUMERIC_FIELDS;

export function parseNumber(raw: string): number | null {
  const t = raw.trim();
  if (t === '') return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : NaN;
}

function checkNumber(key: NumericKey, raw: string): string | undefined {
  const spec = NUMERIC_FIELDS[key];
  const n = parseNumber(raw);
  if (n === null) return spec.required ? `${spec.label} is required.` : undefined;
  if (Number.isNaN(n)) return `${spec.label} must be a number.`;
  if (spec.integer && !Number.isInteger(n)) return `${spec.label} must be a whole number.`;
  if (n < spec.min || n > spec.max) return `${spec.label} must be between ${spec.min} and ${spec.max} ${spec.unit}.`;
  return undefined;
}

const YES_NO_LABELS: Record<string, string> = {
  snoring: 'snoring',
  daytimeTiredness: 'daytime tiredness',
  witnessedPauses: 'breathing pauses',
  highBloodPressure: 'high blood pressure',
};

/** Errors for one step. Required questions must be answered; optional ones only validated when filled. */
export function validateStep(step: StepId, a: QuestionnaireAnswers): FieldErrors {
  const e: FieldErrors = {};
  if (step === 'stopbang') {
    for (const k of ['snoring', 'daytimeTiredness', 'witnessedPauses', 'highBloodPressure'] as const) {
      if (a[k] === null) e[k] = `Answer the ${YES_NO_LABELS[k]} question (Yes or No).`;
    }
  }
  if (step === 'body') {
    for (const k of Object.keys(NUMERIC_FIELDS) as NumericKey[]) {
      const msg = checkNumber(k, a[k]);
      if (msg) e[k] = msg;
    }
    if (a.sex === null) e.sex = 'Choose an option for sex.';
  }
  if (step === 'history' && a.conditions === null) {
    e.conditions = 'Select any conditions that apply, or choose “None of these”.';
  }
  if (step === 'emergency') {
    for (const opt of RED_FLAG_OPTIONS) {
      if (a.redFlags[opt.value] === null) e[`redFlag:${opt.value}`] = `Answer Yes or No for “${opt.label}”.`;
    }
  }
  return e;
}

export function validateAll(a: QuestionnaireAnswers): FieldErrors {
  return STEPS.reduce<FieldErrors>((acc, s) => ({ ...acc, ...validateStep(s.id, a) }), {});
}

/** Count of required questions answered, for the progress indicator. */
export function progress(a: QuestionnaireAnswers): { answered: number; required: number } {
  const req = [
    a.snoring !== null,
    a.daytimeTiredness !== null,
    a.witnessedPauses !== null,
    a.highBloodPressure !== null,
    a.age.trim() !== '',
    a.sex !== null,
    a.conditions !== null,
    ...RED_FLAG_OPTIONS.map((o) => a.redFlags[o.value] !== null),
  ];
  return { answered: req.filter(Boolean).length, required: req.length };
}

export function positiveRedFlags(a: QuestionnaireAnswers): RedFlagValue[] {
  return RED_FLAG_OPTIONS.filter((o) => a.redFlags[o.value] === 'yes').map((o) => o.value);
}

/** Optional numeric fields left blank, so the UI can say they will be treated as unknown. */
export function missingOptional(a: QuestionnaireAnswers): string[] {
  return (['heightCm', 'weightKg', 'neckCm'] as const).filter((k) => a[k].trim() === '').map((k) => NUMERIC_FIELDS[k].label);
}

const yn = (v: YesNo): boolean | null => (v === null ? null : v === 'yes');
const num = (raw: string): number | null => {
  const n = parseNumber(raw);
  return n === null || Number.isNaN(n) ? null : n;
};

/**
 * Map answers to the shared ProfileInput. Unanswered stays null; the backend lists
 * unknown STOP-Bang items as missing instead of treating them as "no". Sex "other"
 * maps to null because the backend treats unrecognized values as unknown.
 */
export function toProfileInput(a: QuestionnaireAnswers, base?: Pick<ProfileInput, 'location_lat' | 'location_lon'>): ProfileInput {
  return {
    age: num(a.age),
    sex: a.sex === 'male' || a.sex === 'female' ? a.sex : null,
    height_cm: num(a.heightCm),
    weight_kg: num(a.weightKg),
    neck_circumference_cm: num(a.neckCm),
    conditions: a.conditions ? [...a.conditions] : [],
    snoring: yn(a.snoring),
    daytime_tiredness: yn(a.daytimeTiredness),
    witnessed_breathing_pauses: yn(a.witnessedPauses),
    hypertension: yn(a.highBloodPressure),
    red_flag_symptoms: positiveRedFlags(a),
    location_lat: base?.location_lat ?? null,
    location_lon: base?.location_lon ?? null,
  };
}
