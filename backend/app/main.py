"""WakeSafe FastAPI application.

Exposes the existing, tested services over HTTP:

    GET  /health              liveness
    POST /screen              profile + nights -> RiskAssessment (+ ApneaScore, FeatureSet)
    POST /care                RiskAssessment + location -> CareRecommendations
                              (also at POST /api/care/recommendations, the
                              TEAM_CONTRACTS.md §4.3 name the frontend calls)
    POST /explain             ClinicianReportData (or pieces) -> Explanation
    POST /report              pieces -> ClinicianReportData (one-page brief)
    GET  /demo/{persona}      full chain for a synthetic persona, in one call

Run: uvicorn app.main:app --reload   (from the backend/ directory)
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.contract_routes import router as contract_router
from app.api.routes import router

app = FastAPI(
    title="WakeSafe API",
    version="0.1.0",
    description=(
        "Wellness screening aid (not a diagnosis). Exposes WakeSafe's risk, "
        "care-matching, apnea-screening and explanation services over HTTP."
    ),
)

# Permissive CORS for local dev — the frontend runs on a different port (Vite).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(contract_router)


@app.get("/")
def root() -> dict:
    return {
        "service": "WakeSafe API",
        "status": "ok",
        "docs": "/docs",
        "endpoints": [
            "/health",
            "/nudges",
            "/screen",
            "/care",
            "/api/care/recommendations",
            "/explain",
            "/report",
            "/demo/{persona}",
        ],
        "contract_endpoints": [
            "/api/health",
            "/api/demo/personas",
            "/api/screening/analyze",
            "/api/care/recommendations",
            "/api/reports/preview",
            "/api/reports/pdf",
        ],
    }
