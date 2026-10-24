"""Shared Pydantic schemas, copied from TEAM_CONTRACTS.md section 3.

Do not change a field, name or type here without the contract-change procedure in
TEAM_CONTRACTS.md section 6. Schemas only: no behaviour and no database models.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


# 3.1 ProfileInput
class ProfileInput(BaseModel):
    age: int | None = None
    sex: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    neck_circumference_cm: float | None = None
    conditions: list[str] = Field(default_factory=list)
    snoring: bool | None = None
    daytime_tiredness: bool | None = None
    witnessed_breathing_pauses: bool | None = None
    hypertension: bool | None = None
    red_flag_symptoms: list[str] = Field(default_factory=list)
    location_lat: float | None = None
    location_lon: float | None = None


# 3.2 NightRecord
class NightRecord(BaseModel):
    night_id: str
    date: date
    resting_heart_rate_bpm: float | None = None
    hrv_rmssd_ms: float | None = None
    spo2_pct: float | None = None
    respiratory_rate_rpm: float | None = None
    skin_temperature_c: float | None = None
    sleep_duration_minutes: float | None = None
    sleep_efficiency_pct: float | None = None
    deep_sleep_minutes: float | None = None
    rem_sleep_minutes: float | None = None
    disturbance_count: int | None = None
    sleep_consistency_pct: float | None = None
    source: Literal["synthetic", "csv", "whoop"] = "synthetic"


# 3.3 FeatureSet
class FeatureSet(BaseModel):
    values: dict[str, float | None]
    baseline_z_scores: dict[str, float | None]
    nights_available: int
    nights_with_spo2: int
    data_quality_flags: list[str] = Field(default_factory=list)
    window_start: date | None = None
    window_end: date | None = None


# 3.4 ApneaScore
class ApneaScore(BaseModel):
    tier: Literal["Low", "Moderate", "High"]
    probability: float | None = None
    stop_bang_score: int | None = None
    top_factors: list[str] = Field(default_factory=list)
    model_version: str
    evidence_note: str


# 3.5 RiskItem and RiskAssessment
class RiskItem(BaseModel):
    risk_id: str
    display_name: str
    tier: Literal["Low", "Moderate", "High", "Urgent"]
    reasons: list[str]
    evidence_rating: Literal["Weak", "Weak to moderate", "Moderate", "Strong"]
    suggested_specialty: str
    source_labels: list[
        Literal[
            "patient_reported",
            "wearable_measured",
            "app_calculated",
            "model_estimated",
            "simulated",
        ]
    ]


class RiskAssessment(BaseModel):
    risks: list[RiskItem]
    urgent_override: bool
    urgent_reasons: list[str] = Field(default_factory=list)
    rules_version: str
    disclaimer: str


# 3.6 FacilityRecommendation
class FacilityRecommendation(BaseModel):
    facility_id: str
    name: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    specialties: list[str]
    drive_minutes: float | None = None
    capacity_score: float | None = None
    capacity_source: Literal["static", "simulated", "live", "unknown"]
    rank_score: float
    notes: list[str] = Field(default_factory=list)


# 3.7 CareRecommendations
class CareRecommendations(BaseModel):
    recommendations: list[FacilityRecommendation]
    care_tier: Literal["Routine", "Elevated", "Urgent"]
    disclaimer: str


# 3.8 Explanation
class Explanation(BaseModel):
    summary: str
    risk_explanations: dict[str, str]
    limitations: list[str]
    generated_by: Literal["template", "llm"]


# 3.9 ClinicianReportData
class ClinicianReportData(BaseModel):
    generated_at: datetime
    window_start: date | None = None
    window_end: date | None = None
    profile_summary: dict[str, str | int | float | bool | None]
    apnea_score: ApneaScore | None = None
    risk_assessment: RiskAssessment
    features: FeatureSet
    nights: list[NightRecord]
    explanations: Explanation | None = None
    device_label: str
    data_provenance: list[str]
    model_version: str | None = None
    rules_version: str | None = None
