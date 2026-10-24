"""Rule-based multi-domain risk assessment for WakeSafe (Person B).

Public entry point:

    from app.services.risks import assess_risks
    assessment = assess_risks(profile, features, apnea)

Screening aid only. Imports types from the frozen contract (app.models.schemas);
it never changes them.
"""
from .rules import (
    RULES_VERSION,
    assess_risks,
    care_warranted_outside_travel,
    infer_travel_from_locations,
    travel_track_only_risk_ids,
)

__all__ = [
    "assess_risks",
    "RULES_VERSION",
    "care_warranted_outside_travel",
    "infer_travel_from_locations",
    "travel_track_only_risk_ids",
]
