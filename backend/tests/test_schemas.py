"""Minimal import and validation tests for the shared schemas (TEAM_CONTRACTS.md section 3)."""
import sys
from datetime import date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/, so `app` is importable

from app.models import (
    ApneaScore,
    CareRecommendations,
    ClinicianReportData,
    Explanation,
    FacilityRecommendation,
    FeatureSet,
    NightRecord,
    ProfileInput,
    RiskAssessment,
    RiskItem,
)


def test_defaults_are_independent_and_optional():
    a, b = ProfileInput(), ProfileInput()
    a.conditions.append("asthma")
    assert b.conditions == [] and a.age is None and a.red_flag_symptoms == []


def test_night_record_keeps_missing_values_missing():
    n = NightRecord(night_id="P001-2026-09-01", date=date(2026, 9, 1))
    assert n.spo2_pct is None and n.source == "synthetic"
    with pytest.raises(ValidationError):
        NightRecord(night_id="x", date=date(2026, 9, 1), source="fitbit")


def test_apnea_score_tier_is_restricted():
    ok = ApneaScore(tier="Low", model_version="v", evidence_note="n")
    assert ok.probability is None and ok.top_factors == []
    with pytest.raises(ValidationError):
        ApneaScore(tier="Urgent", model_version="v", evidence_note="n")


def test_report_data_nests_and_round_trips_json():
    report = ClinicianReportData(
        generated_at=datetime(2026, 10, 24, 12, 0),
        profile_summary={"age": 52, "sex": None},
        risk_assessment=RiskAssessment(
            risks=[
                RiskItem(
                    risk_id="sdb", display_name="Sleep-disordered breathing", tier="Moderate", reasons=["r"],
                    evidence_rating="Weak to moderate", suggested_specialty="Sleep medicine", source_labels=["app_calculated"],
                )
            ],
            urgent_override=False, rules_version="v", disclaimer="d",
        ),
        features=FeatureSet(values={"a": None}, baseline_z_scores={}, nights_available=0, nights_with_spo2=0),
        nights=[],
        device_label="Synthetic",
        data_provenance=["synthetic"],
    )
    assert ClinicianReportData.model_validate_json(report.model_dump_json()) == report


def test_other_models_import_and_validate():
    FacilityRecommendation(facility_id="f", name="n", address="a", specialties=[], capacity_source="simulated", rank_score=1.0)
    CareRecommendations(recommendations=[], care_tier="Routine", disclaimer="d")
    Explanation(summary="s", risk_explanations={}, limitations=[], generated_by="template")
    with pytest.raises(ValidationError):
        CareRecommendations(recommendations=[], care_tier="Soon", disclaimer="d")
