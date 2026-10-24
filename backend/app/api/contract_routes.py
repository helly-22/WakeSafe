"""Routes named in TEAM_CONTRACTS.md section 4.3 (the names the frontend calls).

Thin adapters over the existing services, like routes.py. The older short routes
(/health, /screen, /care, /explain, /report, /demo/{persona}) stay as they are.

    GET  /api/health
    GET  /api/demo/personas            demo people with their made-up intake answers
    POST /api/screening/analyze        profile + data source -> features, apnea score,
                                       risk assessment, explanation, provenance (+ nights)
    POST /api/care/recommendations     risk assessment + location -> ranked facilities
    POST /api/reports/preview          the structured clinician report data
    POST /api/reports/pdf              not built yet (501)

Data sources for analyze: "synthetic" (a persona id from /api/demo/personas), "csv" (the
file's text in `csv_text`), "whoop" (not configured, 501).
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models import (
    ApneaScore,
    CareRecommendations,
    ClinicianReportData,
    Explanation,
    FeatureSet,
    NightRecord,
    ProfileInput,
    RiskAssessment,
)
from app.services.care import recommend_care
from app.services.whoop import ProviderDataError, list_personas, load_nights, load_synthetic_profile

from .demo import PERSONA_FILES, load_demo
from .pipeline import build_report, explain_report, run_screen

router = APIRouter(prefix="/api")

# Same central Massachusetts point the /demo route uses when no location is given.
DEFAULT_LAT, DEFAULT_LON = 42.3601, -71.0589


class DemoPersona(BaseModel):
    persona_id: str
    display_name: str
    description: str
    profile: ProfileInput


class AnalyzeRequest(BaseModel):
    data_source: Literal["synthetic", "csv", "whoop"] = "synthetic"
    persona_id: str | None = None
    profile: ProfileInput = Field(default_factory=ProfileInput)
    csv_text: str | None = None  # the uploaded CSV file's text, for data_source "csv"


class AnalyzeResponse(BaseModel):
    features: FeatureSet
    apnea_score: ApneaScore | None
    risk_assessment: RiskAssessment
    explanation: Explanation | None
    data_provenance: list[str]
    nights: list[NightRecord] = Field(default_factory=list)


class CareRecommendationsRequest(BaseModel):
    assessment: RiskAssessment
    latitude: float | None = None
    longitude: float | None = None
    limit: int = 5


class ReportPreviewRequest(AnalyzeRequest):
    pass


def _helly_persona_ids() -> set[str]:
    return {f"SYN-{key}" for key in PERSONA_FILES}


def _load_helly_persona(
    persona_id: str,
) -> tuple[ProfileInput, list[NightRecord], list[str]] | None:
    key = persona_id.strip().upper()
    if key not in _helly_persona_ids():
        return None
    try:
        _, profile, nights, flags = load_demo(key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Demo fixture missing on server: {exc}")
    return profile, nights, flags


def _nights_and_profile(
    body: AnalyzeRequest,
) -> tuple[ProfileInput, list[NightRecord], list[str]]:
    profile = body.profile
    intake_given = bool(profile.model_fields_set)
    try:
        if body.data_source == "synthetic":
            helly = _load_helly_persona(body.persona_id) if body.persona_id else None
            if helly is not None:
                return (profile if intake_given else helly[0]), helly[1], helly[2]
            nights = load_nights("synthetic", persona_id=body.persona_id)
            if not intake_given:
                pid = body.persona_id or list_personas()[0]["persona_id"]
                profile = load_synthetic_profile(pid)
            return profile, nights, []
        if body.data_source == "csv":
            return profile, load_nights("csv", csv_file=body.csv_text), []
        return profile, load_nights("whoop"), []
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except ProviderDataError as exc:
        status = 404 if str(exc).startswith("Unknown demo person") else 422
        raise HTTPException(status_code=status, detail=str(exc))


def _device_label(nights: list[NightRecord]) -> str:
    sources = {n.source for n in nights}
    if sources == {"synthetic"}:
        return "WHOOP (synthetic demo data)"
    if sources == {"csv"}:
        return "WHOOP-format CSV upload"
    return "WHOOP"


@router.get("/health")
def api_health() -> dict:
    return {"status": "ok"}


@router.get("/demo/personas", response_model=list[DemoPersona])
def demo_personas() -> list[DemoPersona]:
    out = []
    for p in list_personas():
        pid = p["persona_id"]
        nights = load_nights("synthetic", persona_id=pid)
        out.append(
            DemoPersona(
                persona_id=pid,
                display_name=p["display_name"],
                description=f"Made-up person with {len(nights)} synthetic nights and made-up intake answers.",
                profile=load_synthetic_profile(pid),
            )
        )
    for key in sorted(PERSONA_FILES):
        loaded = _load_helly_persona(f"SYN-{key}") if (_fixture_exists(key)) else None
        if loaded is None:
            continue
        profile, nights, _flags = loaded
        out.append(
            DemoPersona(
                persona_id=f"SYN-{key}",
                display_name=_helly_display_name(key),
                description=f"Demo scenario with {len(nights)} synthetic nights; intake answers unknown.",
                profile=profile,
            )
        )
    return out


def _fixture_exists(key: str) -> bool:
    from .demo import FIXTURES_DIR

    return (FIXTURES_DIR / PERSONA_FILES[key]).exists()


def _helly_display_name(key: str) -> str:
    import json

    from .demo import FIXTURES_DIR

    data = json.loads((FIXTURES_DIR / PERSONA_FILES[key]).read_text(encoding="utf-8"))
    return str(data.get("display_name", key.title()))


@router.post("/screening/analyze", response_model=AnalyzeResponse)
def analyze(body: AnalyzeRequest) -> AnalyzeResponse:
    profile, nights, flags = _nights_and_profile(body)
    features, apnea, assessment = run_screen(profile, nights, flags)
    report = build_report(profile, nights, features, apnea, assessment, device_label=_device_label(nights))
    explanation = explain_report(report)
    return AnalyzeResponse(
        features=features,
        apnea_score=apnea,
        risk_assessment=assessment,
        explanation=explanation,
        data_provenance=report.data_provenance,
        nights=nights,
    )


@router.post("/care/recommendations", response_model=CareRecommendations)
def care_recommendations(body: CareRecommendationsRequest) -> CareRecommendations:
    return recommend_care(
        body.assessment,
        user_lat=DEFAULT_LAT if body.latitude is None else body.latitude,
        user_lon=DEFAULT_LON if body.longitude is None else body.longitude,
        max_results=body.limit,
    )


@router.post("/reports/preview", response_model=ClinicianReportData)
def report_preview(body: ReportPreviewRequest) -> ClinicianReportData:
    profile, nights, flags = _nights_and_profile(body)
    features, apnea, assessment = run_screen(profile, nights, flags)
    report = build_report(profile, nights, features, apnea, assessment, device_label=_device_label(nights))
    return report.model_copy(update={"explanations": explain_report(report)})


@router.post("/reports/pdf")
def report_pdf() -> None:
    raise HTTPException(status_code=501, detail="PDF rendering is not built yet. Use /api/reports/preview for the report data.")
