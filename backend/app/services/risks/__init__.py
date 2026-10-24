"""Rule-based multi-domain risk assessment for WakeSafe (Person B).

Public entry point:

    from app.services.risks import assess_risks
    assessment = assess_risks(profile, features, apnea)

Screening aid only. Imports types from the frozen contract (app.models.schemas);
it never changes them.
"""
from .rules import RULES_VERSION, assess_risks

__all__ = ["assess_risks", "RULES_VERSION"]
