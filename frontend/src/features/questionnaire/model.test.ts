import { describe, expect, it } from 'vitest';
import {
  emptyAnswers,
  missingOptional,
  positiveRedFlags,
  progress,
  toProfileInput,
  validateAll,
  validateStep,
  type QuestionnaireAnswers,
} from './model';

function complete(): QuestionnaireAnswers {
  const a = emptyAnswers();
  a.snoring = 'yes';
  a.daytimeTiredness = 'no';
  a.witnessedPauses = 'no';
  a.highBloodPressure = 'yes';
  a.age = '52';
  a.sex = 'female';
  a.heightCm = '165';
  a.weightKg = '80';
  a.neckCm = '38';
  a.conditions = ['hypertension'];
  a.redFlags = { 'chest pain': 'no', fainting: 'no', 'severe shortness of breath': 'no', 'stroke symptoms': 'no' };
  return a;
}

describe('validation', () => {
  it('requires every yes/no question and says which one', () => {
    const e = validateStep('stopbang', emptyAnswers());
    expect(Object.keys(e)).toHaveLength(4);
    expect(e.snoring).toMatch(/snoring/i);
  });

  it('requires age and sex, but height, weight and neck are optional', () => {
    const a = emptyAnswers();
    a.age = '40';
    a.sex = 'male';
    expect(validateStep('body', a)).toEqual({});
  });

  it('rejects out-of-range and non-integer numbers with a clear message', () => {
    const a = complete();
    a.age = '5';
    a.heightCm = '1.7';
    a.neckCm = 'abc';
    const e = validateStep('body', a);
    expect(e.age).toMatch(/between 18 and 110/);
    expect(e.heightCm).toMatch(/between 120 and 230 cm/);
    expect(e.neckCm).toMatch(/must be a number/);
    a.age = '40.5';
    expect(validateStep('body', a).age).toMatch(/whole number/);
  });

  it('treats unanswered history as missing, but an explicit "none" as answered', () => {
    const a = complete();
    a.conditions = null;
    expect(validateStep('history', a).conditions).toBeDefined();
    a.conditions = [];
    expect(validateStep('history', a)).toEqual({});
  });

  it('requires an explicit answer for every warning sign', () => {
    const a = complete();
    a.redFlags.fainting = null;
    expect(Object.keys(validateStep('emergency', a))).toEqual(['redFlag:fainting']);
  });

  it('a fully answered questionnaire has no errors', () => {
    expect(validateAll(complete())).toEqual({});
    expect(progress(complete())).toEqual({ answered: 11, required: 11 });
  });
});

describe('mapping to ProfileInput', () => {
  it('keeps unanswered questions null, never false or 0', () => {
    const p = toProfileInput(emptyAnswers());
    expect(p.snoring).toBeNull();
    expect(p.hypertension).toBeNull();
    expect(p.age).toBeNull();
    expect(p.height_cm).toBeNull();
    expect(p.neck_circumference_cm).toBeNull();
    expect(p.sex).toBeNull();
    expect(p.red_flag_symptoms).toEqual([]);
  });

  it('maps explicit answers to the backend field names and condition strings', () => {
    const p = toProfileInput(complete());
    expect(p).toMatchObject({
      age: 52,
      sex: 'female',
      height_cm: 165,
      weight_kg: 80,
      neck_circumference_cm: 38,
      snoring: true,
      daytime_tiredness: false,
      witnessed_breathing_pauses: false,
      hypertension: true,
      conditions: ['hypertension'],
    });
  });

  it('sends "another sex" as unknown and blank measurements as missing', () => {
    const a = complete();
    a.sex = 'other';
    a.neckCm = '';
    expect(toProfileInput(a).sex).toBeNull();
    expect(toProfileInput(a).neck_circumference_cm).toBeNull();
    expect(missingOptional(a)).toEqual(['Neck circumference']);
  });

  it('only lists warning signs answered yes', () => {
    const a = complete();
    a.redFlags['chest pain'] = 'yes';
    expect(positiveRedFlags(a)).toEqual(['chest pain']);
    expect(toProfileInput(a).red_flag_symptoms).toEqual(['chest pain']);
  });
  it('a blank questionnaire has nothing answered and nothing prefilled', () => {
    const a = emptyAnswers();
    expect(progress(a)).toEqual({ answered: 0, required: 11 });
    expect(a.conditions).toBeNull();
    expect(Object.values(a.redFlags).every((v) => v === null)).toBe(true);
    expect(Object.keys(validateAll(a)).length).toBeGreaterThan(0);
  });
});
