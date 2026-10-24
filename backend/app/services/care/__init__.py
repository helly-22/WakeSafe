"""Care matching service (Person B).

Public API: :func:`recommend_care` -> CareRecommendations, ranked by
``0.5*specialty + 0.3*capacity + 0.2*proximity`` with Haversine distance.
"""
from .matcher import (
    HOSPITALS_CSV,
    SCREENING_DISCLAIMER,
    derive_care_tier,
    haversine_km,
    needed_specialties,
    recommend_care,
    specialty_for_risk,
)

__all__ = [
    "HOSPITALS_CSV",
    "SCREENING_DISCLAIMER",
    "derive_care_tier",
    "haversine_km",
    "needed_specialties",
    "recommend_care",
    "specialty_for_risk",
]
