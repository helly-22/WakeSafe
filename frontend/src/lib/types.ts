/**
 * TypeScript mirror of the shared data contracts in TEAM_CONTRACTS.md §3 and §5.
 *
 * The executable source of truth will be the shared Pydantic schemas in
 * `backend/app/models/` (not written yet). When they land, regenerate or re-check
 * these types against them. Do not change field names here unilaterally.
 *
 * Types marked PROPOSED are frontend needs that the contract does not define yet.
 * They require team approval before the backend implements them.
 */

export type DataSource = 'synthetic' | 'csv' | 'whoop';
export type IsoDate = string; // YYYY-MM-DD
export type IsoDateTime = string;

/** §3.1 */
export interface ProfileInput {
  age?: number | null;
  sex?: string | null;
  height_cm?: number | null;
  weight_kg?: number | null;
  neck_circumference_cm?: number | null;
  conditions: string[];
  snoring?: boolean | null;
  daytime_tiredness?: boolean | null;
  witnessed_breathing_pauses?: boolean | null;
  hypertension?: boolean | null;
  red_flag_symptoms: string[];
  location_lat?: number | null;
  location_lon?: number | null;
}

/** §3.2: one record per night. Missing readings stay null, never zero. */
export interface NightRecord {
  night_id: string;
  date: IsoDate;
  resting_heart_rate_bpm: number | null;
  hrv_rmssd_ms: number | null;
  spo2_pct: number | null;
  respiratory_rate_rpm: number | null;
  skin_temperature_c: number | null;
  sleep_duration_minutes: number | null;
  sleep_efficiency_pct: number | null;
  deep_sleep_minutes: number | null;
  rem_sleep_minutes: number | null;
  disturbance_count: number | null;
  sleep_consistency_pct: number | null;
  source: DataSource;
}

/** Numeric NightRecord fields that the UI charts. */
export type NightMetricKey = Exclude<keyof NightRecord, 'night_id' | 'date' | 'source'>;

/** §3.3 */
export interface FeatureSet {
  values: Record<string, number | null>;
  baseline_z_scores: Record<string, number | null>;
  nights_available: number;
  nights_with_spo2: number;
  data_quality_flags: string[];
  window_start: IsoDate | null;
  window_end: IsoDate | null;
}

export type ScreeningTier = 'Low' | 'Moderate' | 'High';
export type RiskTier = ScreeningTier | 'Urgent';

/** §3.4 */
export interface ApneaScore {
  tier: ScreeningTier;
  probability: number | null;
  stop_bang_score: number | null;
  top_factors: string[];
  model_version: string;
  evidence_note: string;
}

export type SourceLabel =
  | 'patient_reported'
  | 'wearable_measured'
  | 'app_calculated'
  | 'model_estimated'
  | 'simulated';

export type EvidenceRating = 'Weak' | 'Weak to moderate' | 'Moderate' | 'Strong';

/** §3.5 */
export interface RiskItem {
  risk_id: string;
  display_name: string;
  tier: RiskTier;
  reasons: string[];
  evidence_rating: EvidenceRating;
  suggested_specialty: string;
  source_labels: SourceLabel[];
}

/** §3.5 */
export interface RiskAssessment {
  risks: RiskItem[];
  urgent_override: boolean;
  urgent_reasons: string[];
  rules_version: string;
  disclaimer: string;
}

/** §3.6 */
export interface FacilityRecommendation {
  facility_id: string;
  name: string;
  address: string;
  latitude: number | null;
  longitude: number | null;
  specialties: string[];
  drive_minutes: number | null;
  capacity_score: number | null;
  capacity_source: 'static' | 'simulated' | 'live' | 'unknown';
  rank_score: number;
  notes: string[];
}

/** §3.7 */
export interface CareRecommendations {
  recommendations: FacilityRecommendation[];
  care_tier: 'Routine' | 'Elevated' | 'Urgent';
  disclaimer: string;
}

/** §3.8 */
export interface Explanation {
  summary: string;
  risk_explanations: Record<string, string>;
  limitations: string[];
  generated_by: 'template' | 'llm';
}

/** §5: analyze request. */
export interface AnalyzeRequest {
  data_source: DataSource;
  persona_id?: string | null;
  profile: ProfileInput;
}

/** §5: analyze response. */
export interface AnalyzeResponse {
  features: FeatureSet;
  apnea_score: ApneaScore | null;
  risk_assessment: RiskAssessment;
  explanation: Explanation | null;
  data_provenance: string[];
  /**
   * PROPOSED (not in §5): nightly records so the dashboard can draw trends.
   * Optional; the UI must work without it.
   */
  nights?: NightRecord[];
}

/**
 * PROPOSED: item shape for `GET /api/demo/personas` (§4.3 names the route but
 * not the payload).
 */
export interface DemoPersona {
  persona_id: string;
  display_name: string;
  description: string;
  /** Illustrative intake answers used when analyzing this persona. */
  profile: ProfileInput;
}
