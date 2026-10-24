"""Service wiring for the API layer.

One place that composes the existing services into the WakeSafe chain:

    nights --(whoop normalize already done)--> compute_features
          --> score_apnea --> assess_risks --> (recommend_care) --> explain

Every function here CALLS the owners' services; none reimplements them. The
owners' modules are imported, never edited.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.models import (
    ApneaScore,
    ClinicianReportData,
    Explanation,
    FeatureSet,
    NightRecord,
    ProfileInput,
    RiskAssessment,
)
from app.services.explanations import explain
from app.services.risks import assess_risks
from app.services.screening.service import compute_features, score_apnea


def run_screen(
    profile: ProfileInput,
    nights: list[NightRecord],
    extra_quality_flags: list[str] | None = None,
) -> tuple[FeatureSet, ApneaScore, RiskAssessment]:
    """features -> apnea score -> risk assessment, for a profile + nights.

    ``extra_quality_flags`` are out-of-band flags (travel:* / cycle:* markers
    carried in a fixture's ``travel_context`` sidecar, or travel inferred from a
    location/speed series) that the frozen NightRecord/FeatureSet cannot hold as
    fields. They are MERGED into ``features.data_quality_flags`` before the risk
    engine runs, which is the convention the engine reads travel / cycle context
    from. compute_features itself is Person A's and is not changed.
    """
    features = compute_features(nights)
    if extra_quality_flags:
        merged = list(features.data_quality_flags or [])
        for flag in extra_quality_flags:
            if flag and flag not in merged:
                merged.append(flag)
        features = features.model_copy(update={"data_quality_flags": merged})
    apnea = score_apnea(profile, features)
    assessment = assess_risks(profile, features, apnea)
    return features, apnea, assessment


def _profile_summary(profile: ProfileInput) -> dict:
    """A flat, display-only view of the profile for the clinician brief.

    Only scalar fields the ClinicianReportData.profile_summary contract allows
    (str/int/float/bool/None); list fields are joined to a string.
    """
    return {
        "age": profile.age,
        "sex": profile.sex,
        "height_cm": profile.height_cm,
        "weight_kg": profile.weight_kg,
        "neck_circumference_cm": profile.neck_circumference_cm,
        "conditions": ", ".join(profile.conditions) if profile.conditions else None,
        "snoring": profile.snoring,
        "daytime_tiredness": profile.daytime_tiredness,
        "witnessed_breathing_pauses": profile.witnessed_breathing_pauses,
        "hypertension": profile.hypertension,
        "red_flag_symptoms": (
            ", ".join(profile.red_flag_symptoms) if profile.red_flag_symptoms else None
        ),
    }


def build_report(
    profile: ProfileInput,
    nights: list[NightRecord],
    features: FeatureSet,
    apnea: ApneaScore,
    assessment: RiskAssessment,
    *,
    device_label: str = "WHOOP (synthetic demo data)",
    explanations: Explanation | None = None,
    generated_at: datetime | None = None,
) -> ClinicianReportData:
    """Assemble a ClinicianReportData (frozen contract) from the pieces."""
    provenance = ["synthetic"] if any(n.source == "synthetic" for n in nights) else []
    if any(n.source == "csv" for n in nights):
        provenance.append("csv")
    if any(n.source == "whoop" for n in nights):
        provenance.append("whoop")
    return ClinicianReportData(
        generated_at=generated_at or datetime.now(timezone.utc),
        window_start=features.window_start,
        window_end=features.window_end,
        profile_summary=_profile_summary(profile),
        apnea_score=apnea,
        risk_assessment=assessment,
        features=features,
        nights=nights,
        explanations=explanations,
        device_label=device_label,
        data_provenance=provenance or ["unknown"],
        model_version=apnea.model_version,
        rules_version=assessment.rules_version,
    )


def explain_report(report: ClinicianReportData) -> Explanation:
    """Run the explanation engine over an assembled report."""
    return explain(report)
