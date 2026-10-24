"""FastAPI TestClient smoke test for the WakeSafe API.

Covers the wiring, not the service internals (those have their own suites):
  * /health is ok
  * /demo/APNEA runs the full chain and returns a valid RiskAssessment with risks
  * /screen with the same fixture nights returns a RiskAssessment + ApneaScore
  * /care returns ranked recommendations for the demo assessment
  * /explain returns an evidence-bearing Explanation
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APNEA_FIXTURE = _REPO_ROOT / "scripts" / "fixtures" / "syn-apnea.json"


def _apnea_nights() -> list[dict]:
    data = json.loads(_APNEA_FIXTURE.read_text(encoding="utf-8"))
    return data["nights"]


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_demo_apnea_full_chain():
    resp = client.get("/demo/APNEA")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Valid RiskAssessment with at least one risk.
    ra = body["risk_assessment"]
    assert isinstance(ra["risks"], list)
    assert len(ra["risks"]) >= 1
    assert ra["rules_version"]
    assert ra["disclaimer"]

    # Apnea score passed through (tier is a valid contract value).
    assert body["apnea_score"]["tier"] in {"Low", "Moderate", "High"}

    # Care recommendations present.
    assert len(body["care"]["recommendations"]) >= 1
    assert body["care"]["care_tier"] in {"Routine", "Elevated", "Urgent"}

    # Explanation present and evidence-bearing.
    expl = body["explanation"]
    assert expl["summary"]
    assert expl["generated_by"] in {"template", "llm"}


def test_screen_returns_assessment_and_apnea():
    resp = client.post(
        "/screen",
        json={"profile": {}, "nights": _apnea_nights()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["risk_assessment"]["risks"]) >= 1
    assert body["apnea_score"]["tier"] in {"Low", "Moderate", "High"}
    assert "nights_available" in body["features"]


def test_care_returns_recommendations():
    # Drive the assessment from /screen so we exercise real contract shapes.
    screen = client.post("/screen", json={"profile": {}, "nights": _apnea_nights()})
    assessment = screen.json()["risk_assessment"]

    resp = client.post(
        "/care",
        json={"assessment": assessment, "user_lat": 42.3601, "user_lon": -71.0589},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["recommendations"]) >= 1
    assert body["care_tier"] in {"Routine", "Elevated", "Urgent"}
    for rec in body["recommendations"]:
        assert "rank_score" in rec


def test_explain_from_pieces_has_evidence():
    screen = client.post("/screen", json={"profile": {}, "nights": _apnea_nights()})
    sb = screen.json()

    resp = client.post(
        "/explain",
        json={
            "profile": {},
            "nights": _apnea_nights(),
            "features": sb["features"],
            "apnea_score": sb["apnea_score"],
            "risk_assessment": sb["risk_assessment"],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"]
    assert isinstance(body["risk_explanations"], dict)
    # Evidence-first: at least one risk explanation carries an [EVIDENCE] block.
    assert any("[EVIDENCE]" in v for v in body["risk_explanations"].values())
    assert isinstance(body["limitations"], list) and body["limitations"]
