/**
 * Hand-written ILLUSTRATIVE fixtures for UI development. Synthetic demo data only:
 * not real patients, not model output, not validation results. They stand in for
 * Dhev's score_apnea and Helly's assess_risks / explain until those exist, and
 * must never be used for training or evaluation (TEAM_CONTRACTS.md §1, §6.8).
 */
import type { AnalyzeResponse, DemoPersona } from '../../lib/types';
import { FIXTURE_FEATURES, FIXTURE_NIGHTS } from './generatedFixtures';

const FIXTURE_VERSION = 'fixture-v1';
const EVIDENCE_NOTE = 'Illustrative fixture output for the synthetic demo; not a clinical prediction.';
const DISCLAIMER = 'Screening aid only; not a diagnosis. Consider discussing results with a clinician.';

export const MOCK_PERSONAS: DemoPersona[] = [
  {
    persona_id: 'maya_demo',
    display_name: 'Maya (synthetic)',
    description: '52, snoring and daytime tiredness, 14 nights of data.',
    profile: {
      age: 52,
      sex: 'female',
      conditions: ['hypertension'],
      snoring: true,
      daytime_tiredness: true,
      witnessed_breathing_pauses: false,
      hypertension: true,
      red_flag_symptoms: [],
    },
  },
  {
    persona_id: 'jordan_demo',
    display_name: 'Jordan (synthetic)',
    description: '34, only 5 nights and no SpO₂: shows missing-data handling.',
    profile: {
      age: 34,
      sex: 'male',
      conditions: [],
      snoring: true,
      daytime_tiredness: false,
      witnessed_breathing_pauses: null,
      hypertension: false,
      red_flag_symptoms: [],
    },
  },
  {
    persona_id: 'riley_demo',
    display_name: 'Riley (synthetic)',
    description: '61, reports chest pain: shows the urgent-symptom screen.',
    profile: {
      age: 61,
      sex: 'female',
      conditions: [],
      snoring: true,
      daytime_tiredness: true,
      witnessed_breathing_pauses: true,
      hypertension: null,
      red_flag_symptoms: ['chest pain'],
    },
  },
];

function features(id: string) {
  const f = FIXTURE_FEATURES[id];
  if (!f) throw new Error(`Missing fixture features for ${id}`);
  return f;
}

export const MOCK_ANALYSES: Record<string, AnalyzeResponse> = {
  maya_demo: {
    features: features('maya_demo'),
    nights: FIXTURE_NIGHTS.maya_demo,
    apnea_score: {
      tier: 'High',
      probability: null,
      stop_bang_score: null,
      top_factors: [
        'Reported loud snoring',
        'Reported daytime tiredness',
        'Reported high blood pressure',
        'Resting heart rate above personal baseline in recent nights',
      ],
      model_version: FIXTURE_VERSION,
      evidence_note: EVIDENCE_NOTE,
    },
    risk_assessment: {
      risks: [
        {
          risk_id: 'sleep_disordered_breathing',
          display_name: 'Sleep-disordered breathing',
          tier: 'High',
          reasons: [
            'Snoring and daytime tiredness were reported.',
            'High blood pressure was reported.',
            'Recent resting heart rate is above this person’s own baseline.',
          ],
          evidence_rating: 'Moderate',
          suggested_specialty: 'Sleep medicine',
          source_labels: ['patient_reported', 'wearable_measured', 'app_calculated', 'model_estimated'],
        },
      ],
      urgent_override: false,
      urgent_reasons: [],
      rules_version: FIXTURE_VERSION,
      disclaimer: DISCLAIMER,
    },
    explanation: {
      summary:
        'Several screening signals line up: reported snoring, daytime tiredness and high blood pressure, plus recent nights with a resting heart rate above this person’s own baseline.',
      risk_explanations: {
        sleep_disordered_breathing:
          'This screening combines reported symptoms with wearable trends. It is a risk signal, not a diagnosis. A sleep medicine clinician can decide whether a sleep study is appropriate.',
      },
      limitations: [
        'Synthetic demo data; illustrative only.',
        'Wearable summaries cannot measure breathing events directly.',
        'SpO₂ was missing on some nights.',
      ],
      generated_by: 'template',
    },
    data_provenance: ['synthetic'],
  },
  jordan_demo: {
    features: features('jordan_demo'),
    nights: FIXTURE_NIGHTS.jordan_demo,
    apnea_score: {
      tier: 'Moderate',
      probability: null,
      stop_bang_score: null,
      top_factors: ['Reported snoring', 'Limited history: only 5 nights available'],
      model_version: FIXTURE_VERSION,
      evidence_note: EVIDENCE_NOTE,
    },
    risk_assessment: {
      risks: [
        {
          risk_id: 'sleep_disordered_breathing',
          display_name: 'Sleep-disordered breathing',
          tier: 'Moderate',
          reasons: [
            'Snoring was reported.',
            'Only 5 nights are available, so no personal baseline exists yet.',
          ],
          evidence_rating: 'Weak to moderate',
          suggested_specialty: 'Primary care',
          source_labels: ['patient_reported', 'wearable_measured'],
        },
      ],
      urgent_override: false,
      urgent_reasons: [],
      rules_version: FIXTURE_VERSION,
      disclaimer: DISCLAIMER,
    },
    explanation: {
      summary:
        'Reported snoring is the main signal. There is not enough wearable history yet to compare against a personal baseline.',
      risk_explanations: {
        sleep_disordered_breathing:
          'With only a few nights of data, this screening relies mostly on reported symptoms. More nights would make trends easier to interpret.',
      },
      limitations: [
        'Synthetic demo data; illustrative only.',
        'SpO₂ was not recorded on any night.',
        'Fewer nights than needed for a personal baseline.',
      ],
      generated_by: 'template',
    },
    data_provenance: ['synthetic'],
  },
  riley_demo: {
    features: features('riley_demo'),
    nights: FIXTURE_NIGHTS.riley_demo,
    apnea_score: {
      tier: 'High',
      probability: null,
      stop_bang_score: null,
      top_factors: ['Reported snoring', 'Reported witnessed breathing pauses', 'Reported daytime tiredness'],
      model_version: FIXTURE_VERSION,
      evidence_note: EVIDENCE_NOTE,
    },
    risk_assessment: {
      risks: [
        {
          risk_id: 'urgent_symptoms',
          display_name: 'Urgent symptoms reported',
          tier: 'Urgent',
          reasons: ['Chest pain was reported.'],
          evidence_rating: 'Strong',
          suggested_specialty: 'Emergency services',
          source_labels: ['patient_reported'],
        },
        {
          risk_id: 'sleep_disordered_breathing',
          display_name: 'Sleep-disordered breathing',
          tier: 'High',
          reasons: ['Snoring, witnessed breathing pauses and daytime tiredness were reported.'],
          evidence_rating: 'Moderate',
          suggested_specialty: 'Sleep medicine',
          source_labels: ['patient_reported', 'model_estimated'],
        },
      ],
      urgent_override: true,
      urgent_reasons: ['Chest pain was reported.'],
      rules_version: FIXTURE_VERSION,
      disclaimer: DISCLAIMER,
    },
    explanation: {
      summary: 'Chest pain was reported. That needs emergency attention before any sleep screening follow-up.',
      risk_explanations: {
        urgent_symptoms: 'Chest pain can be a sign of a medical emergency. Call 911 now.',
        sleep_disordered_breathing:
          'Reported sleep symptoms are also a risk signal worth raising with a clinician once the urgent concern has been addressed.',
      },
      limitations: ['Synthetic demo data; illustrative only.', 'Only 10 nights available; no personal baseline yet.'],
      generated_by: 'template',
    },
    data_provenance: ['synthetic'],
  },
};
