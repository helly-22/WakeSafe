"""Request-body wrappers for endpoints that take more than one contract object.

These are TRANSPORT shapes only (what the HTTP body looks like). They compose the
frozen contract models from ``app.models`` and add nothing to the domain — no
scoring, no defaults that change behaviour. The response models are always the
frozen contract types themselves.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

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


class ScreenRequest(BaseModel):
    """Body for POST /screen: a profile plus the person's nightly records."""

    profile: ProfileInput
    nights: list[NightRecord]


class ScreenResponse(BaseModel):
    """What /screen returns: the risk assessment plus the apnea score and the
    computed feature set (the UI needs all three to render)."""

    risk_assessment: RiskAssessment
    apnea_score: ApneaScore
    features: FeatureSet


class CareRequest(BaseModel):
    """Body for POST /care: a RiskAssessment plus the user's CURRENT location."""

    assessment: RiskAssessment
    user_lat: float = Field(ge=-90, le=90)
    user_lon: float = Field(ge=-180, le=180)
    max_results: int = Field(default=5, ge=1, le=20)


class ExplainRequest(BaseModel):
    """Body for POST /explain.

    Either pass a fully-assembled ClinicianReportData as ``report``, or pass the
    pieces and let the route assemble one. If both are given, ``report`` wins.
    """

    report: ClinicianReportData | None = None

    # Pieces, used only when ``report`` is absent.
    profile: ProfileInput | None = None
    nights: list[NightRecord] = Field(default_factory=list)
    features: FeatureSet | None = None
    apnea_score: ApneaScore | None = None
    risk_assessment: RiskAssessment | None = None
    device_label: str = "WHOOP (synthetic demo data)"


class ReportRequest(BaseModel):
    """Body for POST /report: the pieces needed to assemble a one-page clinician
    brief. The route runs the explanation engine to fill ``explanations``."""

    profile: ProfileInput
    nights: list[NightRecord]
    features: FeatureSet
    apnea_score: ApneaScore
    risk_assessment: RiskAssessment
    device_label: str = "WHOOP (synthetic demo data)"
    generated_at: datetime | None = None


class DemoResponse(BaseModel):
    """What GET /demo/{persona} returns: the full chain in one call."""

    persona: str
    profile: ProfileInput
    features: FeatureSet
    apnea_score: ApneaScore
    risk_assessment: RiskAssessment
    care: CareRecommendations
    explanation: Explanation
    report: ClinicianReportData


class NudgeItem(BaseModel):
    """One calm, single-action public-health nudge.

    Defined in the API layer because the frozen contract (schemas.py) has no
    nudge type. No domain logic -- it mirrors ``app.services.nudges.Nudge``.
    """

    topic: Literal["respiratory", "flu", "mosquito"]
    message: str
    action: str
    as_of: str = Field(description="ISO date the underlying data is current to")
    source: Literal["live", "cached"]


class NudgeResponse(BaseModel):
    """What GET /nudges returns: a small set of calm nudges plus an honest
    as-of stamp and a live/cached source flag."""

    region: str
    as_of: str
    source: Literal["live", "cached"]
    nudges: list[NudgeItem]
    notes: list[str] = Field(default_factory=list)
