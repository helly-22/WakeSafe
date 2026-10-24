"""WakeSafe HTTP routes.

Each route is a thin adapter: validate the body against a contract/transport
model, call the owners' service(s), return a contract model. No domain logic.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models import CareRecommendations, ClinicianReportData, Explanation
from app.services.care import recommend_care
from app.services.care.matcher import SCREENING_DISCLAIMER
from app.services.care.routing import build_care_map
from app.services.nudges import build_nudges
from app.services.risks import care_warranted_outside_travel

from .demo import available_personas, load_demo
from .models import (
    CareRequest,
    DemoResponse,
    ExplainRequest,
    NudgeResponse,
    ReportRequest,
    ScreenRequest,
    ScreenResponse,
)
from .pipeline import build_report, explain_report, run_screen

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/nudges", response_model=NudgeResponse)
def nudges(region: str = "Massachusetts") -> NudgeResponse:
    """Calm, rate-limited public-health nudges from FRESH CDC Socrata data.

    Pulls current flu / respiratory (+ West Nile in season) signals live on each
    hit (cached ~15 min in memory). When the live API is unreachable it falls
    back to the downloaded cached CSVs and labels every nudge ``cached`` with the
    cached data's honest date. Never crashes on a data problem.
    """
    bundle = build_nudges(region)
    return NudgeResponse(
        region=bundle.region,
        as_of=bundle.as_of,
        source=bundle.source,
        nudges=[
            {
                "topic": n.topic,
                "message": n.message,
                "action": n.action,
                "as_of": n.as_of,
                "source": n.source,
            }
            for n in bundle.nudges
        ],
        notes=bundle.notes,
    )


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


# NOTE: no response_model here. The frozen CareRecommendations contract has no
# field for a route polyline or a live-vs-estimated source flag, and schemas.py
# must not change. So this endpoint returns a plain dict carrying BOTH the
# unchanged recommendations (map pins ride their existing lat/lon) AND a separate
# "map" block with the OSRM route to the top pick. Free stack only: MapLibre +
# OpenStreetMap tiles + OSRM public server, no API key anywhere.
@router.post("/care/map")
@router.post("/api/care/map")
def care_map(body: CareRequest) -> dict:
    """A risk assessment + current location -> ranked facilities + map data.

    Same inputs as /care. The response is::

        {"care": <CareRecommendations>, "map": {user, pins, route_to_top, tiles}}

    where ``map.route_to_top.source`` is "live-osrm" when the OSRM public server
    answered, or "estimated-haversine" when it was unreachable and the route fell
    back to a labelled straight-line estimate (the call never 500s on routing).
    """
    care_recs = recommend_care(
        body.assessment,
        user_lat=body.user_lat,
        user_lon=body.user_lon,
        max_results=body.max_results,
    )
    map_block = build_care_map(care_recs, body.user_lat, body.user_lon)
    return {
        "care": care_recs.model_dump(mode="json"),
        "map": map_block,
    }


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
        canonical, profile, nights, quality_flags = load_demo(persona)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown persona '{persona}'. Try one of: {', '.join(available_personas())}.",
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500, detail=f"Demo fixture missing on server: {exc}"
        )

    features, apnea, assessment = run_screen(profile, nights, quality_flags)
    # Use the persona's own location when the profile carries one, else a central
    # Massachusetts point so the care demo returns realistic drive times.
    user_lat = profile.location_lat if profile.location_lat is not None else 42.3601
    user_lon = profile.location_lon if profile.location_lon is not None else -71.0589

    # Track-only while travelling: keep the nights and the risk assessment, but
    # do NOT rank care recommendations on a travel window alone. When care is not
    # warranted by non-travel data, pause recommendations (empty, with a note)
    # rather than ranking facilities off the trip's data.
    if not care_warranted_outside_travel(assessment):
        care_recs = CareRecommendations(
            recommendations=[],
            care_tier="Routine",
            disclaimer=(
                SCREENING_DISCLAIMER
                + " You appear to be travelling: your nights are still tracked, "
                "but care recommendations based only on the travel window are "
                "paused until a pattern persists back home."
            ),
        )
    else:
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
