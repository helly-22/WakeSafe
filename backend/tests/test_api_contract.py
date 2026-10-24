"""Tests for the TEAM_CONTRACTS.md section 4.3 routes (/api/...), with the real services behind them."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))  # backend/, so `app` is importable

from app.api.demo import FIXTURES_DIR, PERSONA_FILES
from app.main import app
from app.models import CareRecommendations, ClinicianReportData, FeatureSet, RiskAssessment

client = TestClient(app)
BAD = re.compile(r"diagnos(?!is\.)|diagnosed|you have|you've", re.I)


def analyze(**body):
    return client.post("/api/screening/analyze", json={"data_source": "synthetic", **body})


def test_demo_fixture_files_are_in_the_repo():
    for name in PERSONA_FILES.values():
        assert (FIXTURES_DIR / name).is_file(), f"{name} must be committed; the demo routes read it"


def test_health_and_old_routes_still_work():
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/demo/APNEA").status_code == 200
    assert "/api/screening/analyze" in client.get("/").json()["contract_endpoints"]


def test_personas_list_has_our_people_and_the_demo_scenarios():
    r = client.get("/api/demo/personas")
    assert r.status_code == 200
    people = r.json()
    ids = [p["persona_id"] for p in people]
    assert len(ids) == len(set(ids)) >= 72
    assert {"P001", "P065", "P901", "SYN-APNEA", "SYN-NORMAL"} <= set(ids)
    for p in people:
        assert set(p) == {"persona_id", "display_name", "description", "profile"}
    text = " ".join(p["description"].lower() for p in people if p["persona_id"].startswith("P"))
    for word in ("osa", "apnea", "healthy", "severe", "ground", "cohort"):
        assert word not in text
    p001 = next(p for p in people if p["persona_id"] == "P001")
    assert p001["profile"]["age"] == 60 and p001["profile"]["sex"] == "male"


def test_analyze_one_id_runs_a_full_demo_with_the_personas_intake_answers():
    r = analyze(persona_id="P001")
    assert r.status_code == 200
    d = r.json()
    assert set(d) == {"features", "apnea_score", "risk_assessment", "explanation", "data_provenance", "nights"}
    FeatureSet.model_validate(d["features"])
    RiskAssessment.model_validate(d["risk_assessment"])
    assert d["apnea_score"]["stop_bang_score"] == 4 and d["apnea_score"]["probability"] is None
    assert d["data_provenance"] == ["synthetic"] and "synthetic_data" in d["features"]["data_quality_flags"]
    assert len(d["nights"]) == d["features"]["nights_available"] > 15
    assert d["explanation"]["generated_by"] == "template"
    texts = d["apnea_score"]["top_factors"] + [d["explanation"]["summary"]] + list(d["explanation"]["risk_explanations"].values())
    assert not any(BAD.search(t) for t in texts)


def test_sending_the_personas_own_profile_gives_the_same_result():
    people = {p["persona_id"]: p for p in client.get("/api/demo/personas").json()}
    omitted = analyze(persona_id="P002").json()
    sent = analyze(persona_id="P002", profile=people["P002"]["profile"]).json()
    assert omitted["apnea_score"] == sent["apnea_score"] and omitted["risk_assessment"] == sent["risk_assessment"]


def test_red_flag_in_the_profile_forces_the_urgent_path():
    d = analyze(persona_id="P003", profile={"red_flag_symptoms": ["chest_pain"], "age": 40}).json()
    assert d["risk_assessment"]["urgent_override"] is True
    care = client.post("/api/care/recommendations", json={"assessment": d["risk_assessment"]}).json()
    assert care["care_tier"] == "Urgent" and "911" in str(care)


def test_demo_scenario_persona_and_the_worsening_person():
    assert analyze(persona_id="SYN-APNEA").status_code == 200
    d = analyze(persona_id="P901").json()
    assert d["features"]["baseline_z_scores"]["sleep_efficiency_pct"] < -1


def test_unknown_persona_is_404_and_whoop_is_501():
    r = analyze(persona_id="X999")
    assert r.status_code == 404 and "Unknown demo person" in r.json()["detail"]
    assert client.post("/api/screening/analyze", json={"data_source": "whoop"}).status_code == 501


def test_csv_text_upload_and_bad_csv():
    text = (REPO / "fixtures" / "nights_sample_P001.csv").read_text()
    r = client.post("/api/screening/analyze", json={"data_source": "csv", "csv_text": text, "profile": {"age": 45}})
    assert r.status_code == 200
    d = r.json()
    assert d["data_provenance"] == ["csv"] and "synthetic_data" not in d["features"]["data_quality_flags"]
    assert len(d["nights"]) == 14
    bad = client.post("/api/screening/analyze", json={"data_source": "csv", "csv_text": "date,resting_heart_rate\n2026-01-01,SECRETVALUE\n"})
    assert bad.status_code == 422 and "SECRETVALUE" not in bad.text and "must be a number" in bad.json()["detail"]
    assert client.post("/api/screening/analyze", json={"data_source": "csv"}).status_code == 422


def test_care_recommendations_follow_the_location_and_have_a_default():
    assessment = analyze(persona_id="P001").json()["risk_assessment"]
    boston = client.post("/api/care/recommendations", json={"assessment": assessment, "latitude": 42.36, "longitude": -71.06, "limit": 3})
    west = client.post("/api/care/recommendations", json={"assessment": assessment, "latitude": 42.10, "longitude": -72.59, "limit": 3})
    default = client.post("/api/care/recommendations", json={"assessment": assessment})
    for r in (boston, west, default):
        assert r.status_code == 200
        CareRecommendations.model_validate(r.json())
    assert len(boston.json()["recommendations"]) == 3
    assert [x["facility_id"] for x in boston.json()["recommendations"]] != [x["facility_id"] for x in west.json()["recommendations"]]


def test_report_preview_and_pdf_not_built():
    r = client.post("/api/reports/preview", json={"data_source": "synthetic", "persona_id": "P002"})
    assert r.status_code == 200
    report = ClinicianReportData.model_validate(r.json())
    assert report.explanations is not None and report.data_provenance == ["synthetic"] and len(report.nights) > 15
    assert client.post("/api/reports/pdf").status_code == 501
