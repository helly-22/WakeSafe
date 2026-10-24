"""WakeSafe HTTP routes.

Each route is a thin adapter: validate the body against a contract/transport
model, call the owners' service(s), return a contract model. No domain logic.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models import CareRecommendations, ClinicianReportData, Explanation
from app.services.care import recommend_care

from .demo import available_personas, load_demo
from .models import (
    CareRequest,
    DemoResponse,
    ExplainRequest,
    ReportRequest,
    ScreenRequest,
    ScreenResponse,
)
from .pipeline import build_report, explain_report, run_screen

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/screen", response_model=ScreenResponse)
def screen(body: ScreenRequest) -> ScreenResponse:
    """Nightly records + profile -> features -> apnea score -> risk assessment."""
    features, apnea, assessment = run_screen(body.profile, body.nights)
    return ScreenResponse(
        risk_assessment=assessment, apnea_score=apnea, features=features
    )


@router.post("/care", response_model=CareRecommendations)
def care(body: CareRequest) -> CareRecommendations:
    """A risk assessment + current location -> ranked facilities."""
    return recommend_care(
        body.assessment,
        user_lat=body.user_lat,
        user_lon=body.user_lon,
        max_results=body.max_results,
    )


@router.post("/explain", response_model=Explanation)
def explain_route(body: ExplainRequest) -> Explanation:
    """A ClinicianReportData (or the pieces to build one) -> Explanation."""
    report = body.report
    if report is None:
        missing = [
            name
            for name, val in (
                ("profile", body.profile),
                ("features", body.features),
                ("apnea_score", body.apnea_score),
                ("risk_assessment", body.risk_assessment),
            )
            if val is None
        ]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Provide either 'report' or all of: profile, features, "
                    f"apnea_score, risk_assessment. Missing: {', '.join(missing)}."
                ),
            )
        report = build_report(
            body.profile,  # type: ignore[arg-type]
            body.nights,
            body.features,  # type: ignore[arg-type]
            body.apnea_score,  # type: ignore[arg-type]
            body.risk_assessment,  # type: ignore[arg-type]
            device_label=body.device_label,
        )
    return explain_report(report)


@router.post("/report", response_model=ClinicianReportData)
def report_route(body: ReportRequest) -> ClinicianReportData:
    """Assemble the one-page clinician brief (with explanations filled in)."""
    report = build_report(
        body.profile,
        body.nights,
        body.features,
        body.apnea_score,
        body.risk_assessment,
        device_label=body.device_label,
        generated_at=body.generated_at,
    )
    explanation = explain_report(report)
    return report.model_copy(update={"explanations": explanation})


@router.get("/demo/{persona}", response_model=DemoResponse)
def demo(persona: str) -> DemoResponse:
    """One-call full chain for a synthetic demo persona.

    persona in {NORMAL, APNEA, MENOPAUSE, CARDIO, ALTITUDE, JETLAG}.
    """
    try:
        canonical, profile, nights = load_demo(persona)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown persona '{persona}'. Try one of: {', '.join(available_personas())}.",
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500, detail=f"Demo fixture missing on server: {exc}"
        )

    features, apnea, assessment = run_screen(profile, nights)
    # Use the persona's own location when the profile carries one, else a central
    # Massachusetts point so the care demo returns realistic drive times.
    user_lat = profile.location_lat if profile.location_lat is not None else 42.3601
    user_lon = profile.location_lon if profile.location_lon is not None else -71.0589
    care_recs = recommend_care(assessment, user_lat=user_lat, user_lon=user_lon)

    report = build_report(profile, nights, features, apnea, assessment)
    explanation = explain_report(report)
    report = report.model_copy(update={"explanations": explanation})

    return DemoResponse(
        persona=canonical,
        profile=profile,
        features=features,
        apnea_score=apnea,
        risk_assessment=assessment,
        care=care_recs,
        explanation=explanation,
        report=report,
    )
