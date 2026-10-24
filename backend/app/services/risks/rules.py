"""Rule-based multi-domain risk engine for WakeSafe (Person B).

`assess_risks` turns a profile, a feature set and the apnea screening tier into a
`RiskAssessment` (frozen contract, app.models.schemas). Six risk groups are scored:

  * sleep_disordered_breathing  (seeds off the apnea tier + SpO2/respiratory trends)
  * cardiovascular              (cardiac folds in here)
  * metabolic
  * respiratory
  * acute_illness
  * menopause                   (peri/menopause: skin-temp shift, warm/disturbed nights,
                                 reported cycle irregularity / hot flashes)

Scoring, per group:
  * a fixed BASELINE of points for each relevant reported condition
    (profile.conditions), each contribution CAPPED so one condition cannot
    dominate, and the condition total itself capped; plus
  * points from features.baseline_z_scores: a worrying deviation (|z| at or past
    CONFIG["z_threshold"] in the group's worrying direction) contributes points
    that rise with the deviation but are CAPPED per signal.
The capped total maps to a tier via CONFIG["tier_bands"] (Low / Moderate / High).

URGENT OVERRIDE: a non-empty profile.red_flag_symptoms is a 911 path. The group
most related to each red flag (cardiovascular by default) is set to tier "Urgent",
RiskAssessment.urgent_override is True and urgent_reasons names the symptoms.

TRAVEL: there is no contract field for travel. When features.data_quality_flags
mention altitude / heat / timezone context, the matching z-threshold for the
affected signal is RELAXED (a dip has to be larger to count) and, when a signal is
softened this way, the reason text says:
    "fits the altitude you're at; watching for persistence at home."
Nothing is added to the schema.

All thresholds live in CONFIG, are unreviewed by a clinician, and are demo values.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.models.schemas import (
    ApneaScore,
    FeatureSet,
    ProfileInput,
    RiskAssessment,
    RiskItem,
)

RULES_VERSION = "risk-rules-v1"

SourceLabel = Literal[
    "patient_reported",
    "wearable_measured",
    "app_calculated",
    "model_estimated",
    "simulated",
]

DISCLAIMER = (
    "This is a wellness screening aid, not a diagnosis. It flags patterns that may be "
    "worth discussing with a clinician and explains why; it does not identify or rule "
    "out any condition. Thresholds are unreviewed demo values. If you feel unwell, "
    "seek care regardless of what this shows."
)

CONFIG: dict = {
    # A deviation counts only at or past this many standard deviations from the
    # person's own baseline, in the group's worrying direction.
    "z_threshold": 1.0,
    # Points a single baseline-z signal can add, and how fast it grows with |z|.
    "points_per_z": 1.2,
    "max_points_per_signal": 3.0,
    # Points one reported condition can add, and the cap on all conditions together.
    "points_per_condition": 2.0,
    "max_points_from_conditions": 4.0,
    # Apnea tier seeds the sleep-disordered-breathing group only.
    "apnea_seed_points": {"Low": 0.0, "Moderate": 2.5, "High": 5.0},
    # total points -> tier. A band is (low_inclusive, high_exclusive).
    # High starts above max_points_per_signal (3.0) so one capped signal can never
    # reach High alone ("no single signal dominates"); Moderate starts low enough
    # that one clearly-worrying signal still registers.
    "tier_bands": {
        "Low": (0.0, 1.0),
        "Moderate": (1.0, 5.0),
        "High": (5.0, float("inf")),
    },
    # Travel: a flagged context relaxes the threshold for its signals by this much
    # (a dip must be larger to count) and softens the reason wording.
    "travel_threshold_relaxation": 1.5,
}

TRAVEL_REASON = "fits the altitude you're at; watching for persistence at home."

Tier = Literal["Low", "Moderate", "High", "Urgent"]

# ---- group definitions ------------------------------------------------------

# Each baseline-z signal: key in features.baseline_z_scores ->
#   (human label, worrying direction: -1 lower is worse, +1 higher is worse)
# Each group lists the signals that count toward it.
GROUP_SIGNALS: dict[str, dict[str, tuple[str, int]]] = {
    "sleep_disordered_breathing": {
        "spo2_pct": ("SpO2", -1),
        "respiratory_rate_rpm": ("respiratory rate", +1),
        "disturbance_count": ("sleep disturbances", +1),
    },
    "cardiovascular": {
        "resting_heart_rate_bpm": ("resting heart rate", +1),
        "hrv_rmssd_ms": ("heart-rate variability", -1),
    },
    "metabolic": {
        "resting_heart_rate_bpm": ("resting heart rate", +1),
        "sleep_efficiency_pct": ("sleep efficiency", -1),
    },
    "respiratory": {
        "respiratory_rate_rpm": ("respiratory rate", +1),
        "spo2_pct": ("SpO2", -1),
    },
    "acute_illness": {
        "skin_temperature_c": ("skin temperature", +1),
        "resting_heart_rate_bpm": ("resting heart rate", +1),
        "respiratory_rate_rpm": ("respiratory rate", +1),
    },
    "menopause": {
        "skin_temperature_c": ("skin temperature", +1),
        "sleep_efficiency_pct": ("sleep efficiency", -1),
        "disturbance_count": ("sleep disturbances", +1),
    },
}

# Reported conditions (lower-cased substring) that count toward each group.
GROUP_CONDITIONS: dict[str, tuple[str, ...]] = {
    "sleep_disordered_breathing": ("sleep apnea", "apnoea", "osa", "snoring"),
    "cardiovascular": (
        "hypertension",
        "high blood pressure",
        "heart disease",
        "coronary",
        "arrhythmia",
        "atrial fibrillation",
        "afib",
        "heart failure",
    ),
    "metabolic": (
        "diabetes",
        "prediabetes",
        "insulin resistance",
        "obesity",
        "metabolic syndrome",
        "thyroid",
        "high cholesterol",
    ),
    "respiratory": ("asthma", "copd", "bronchitis", "emphysema", "sleep apnea"),
    "acute_illness": ("immunocompromised", "recent illness", "recent infection"),
    "menopause": (
        "menopause",
        "perimenopause",
        "peri-menopause",
        "hot flashes",
        "hot flushes",
        "night sweats",
        "irregular periods",
        "irregular cycle",
        "cycle irregularity",
        "vasomotor",
    ),
}

GROUP_DISPLAY: dict[str, str] = {
    "sleep_disordered_breathing": "Sleep-disordered breathing",
    "cardiovascular": "Cardiovascular",
    "metabolic": "Metabolic",
    "respiratory": "Respiratory",
    "acute_illness": "Acute illness",
    "menopause": "Menopause / perimenopause",
}

GROUP_SPECIALTY: dict[str, str] = {
    "sleep_disordered_breathing": "Sleep medicine",
    "cardiovascular": "Cardiology",
    "metabolic": "Endocrinology / primary care",
    "respiratory": "Pulmonology",
    "acute_illness": "Primary care",
    "menopause": "Gynecology / endocrinology",
}

# Which group a red-flag symptom escalates. Default is cardiovascular (the 911
# chest-pain / stroke path), with a couple of respiratory cues routed to respiratory.
RED_FLAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "cardiovascular": (
        "chest pain",
        "chest pressure",
        "fainting",
        "faint",
        "syncope",
        "collapse",
        "stroke",
        "facial droop",
        "slurred speech",
        "weakness on one side",
        "palpitations",
    ),
    "respiratory": ("severe shortness of breath", "severe sob", "cannot breathe", "gasping"),
}

# Travel context flags -> the signals whose threshold they relax.
TRAVEL_FLAG_SIGNALS: dict[str, tuple[str, ...]] = {
    "altitude": ("spo2_pct", "respiratory_rate_rpm"),
    "high_altitude": ("spo2_pct", "respiratory_rate_rpm"),
    "elevation": ("spo2_pct", "respiratory_rate_rpm"),
    "heat": ("resting_heart_rate_bpm", "skin_temperature_c"),
    "high_heat": ("resting_heart_rate_bpm", "skin_temperature_c"),
    "timezone": ("sleep_efficiency_pct", "disturbance_count"),
    "jet_lag": ("sleep_efficiency_pct", "disturbance_count"),
    "travel": ("spo2_pct", "respiratory_rate_rpm", "resting_heart_rate_bpm"),
}


# ---- helpers ----------------------------------------------------------------


@dataclass
class _GroupScore:
    points: float
    reasons: list[str]
    sources: set[SourceLabel]
    travel_softened: bool


def _tier_for(points: float) -> Literal["Low", "Moderate", "High"]:
    for tier, (lo, hi) in CONFIG["tier_bands"].items():
        if lo <= points < hi:
            return tier  # type: ignore[return-value]
    return "High"


def _evidence_rating(points: float, n_wearable_signals: int) -> Literal[
    "Weak", "Weak to moderate", "Moderate", "Strong"
]:
    # More independent wearable signals -> stronger evidence; questionnaire-only is weak.
    if n_wearable_signals >= 2 and points >= CONFIG["tier_bands"]["High"][0]:
        return "Moderate"
    if n_wearable_signals >= 2:
        return "Weak to moderate"
    if n_wearable_signals == 1:
        return "Weak to moderate"
    return "Weak"


def _active_travel_signals(flags: list[str]) -> set[str]:
    out: set[str] = set()
    for flag in flags:
        f = flag.lower()
        for key, signals in TRAVEL_FLAG_SIGNALS.items():
            if key in f:
                out.update(signals)
    return out


_MALE_SEX = {"male", "m", "man"}


def _is_male(sex: str | None) -> bool:
    return sex is not None and sex.strip().lower() in _MALE_SEX


def _condition_matches(conditions: list[str], keywords: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for cond in conditions:
        c = cond.strip().lower()
        if any(k in c for k in keywords):
            hits.append(cond.strip())
    return hits


def _score_group(
    group: str,
    profile: ProfileInput,
    z_scores: dict[str, float | None],
    travel_signals: set[str],
    apnea: ApneaScore,
) -> _GroupScore:
    # Menopause does not apply to a male profile. Unknown or other sex answers still score, so a
    # profile with no intake answers (the demo scenarios) is unaffected.
    if group == "menopause" and _is_male(profile.sex):
        return _GroupScore(
            points=0.0,
            reasons=["Not applicable: menopause screening is not applied to a male profile."],
            sources={"patient_reported"},
            travel_softened=False,
        )

    reasons: list[str] = []
    sources: set[SourceLabel] = set()
    points = 0.0
    travel_softened = False
    n_wearable = 0

    # Apnea seed (sleep group only).
    if group == "sleep_disordered_breathing":
        seed = CONFIG["apnea_seed_points"].get(apnea.tier, 0.0)
        if seed > 0:
            points += seed
            reasons.append(
                f"Apnea screening tier is {apnea.tier}, which raises this group's baseline."
            )
            sources.add("model_estimated")

    # Reported conditions.
    cond_hits = _condition_matches(profile.conditions, GROUP_CONDITIONS.get(group, ()))
    if cond_hits:
        cond_points = min(
            len(cond_hits) * CONFIG["points_per_condition"],
            CONFIG["max_points_from_conditions"],
        )
        points += cond_points
        reasons.append(
            "Reported condition(s) relevant here: " + ", ".join(cond_hits) + "."
        )
        sources.add("patient_reported")

    # Baseline-z signals.
    #
    # Menopause gate: its warm/disturbed-night signals (sleep efficiency down,
    # disturbances up) are NON-specific -- apnea and acute illness fragment sleep
    # too. The feature engine does not emit a skin-temperature z-score (it is not
    # in its Z_FIELDS), so we cannot key the hallmark vasomotor temperature shift
    # off a z-score here. Instead we distinguish by what menopause is NOT: it does
    # not desaturate SpO2 and does not run an elevated respiratory rate (that is
    # the apnea signature). So the menopause group scores its sleep signals only
    # when there is NO apnea-type respiratory signature, OR a peri/menopause
    # condition was reported. Otherwise an apnea night would spuriously fire it.
    if group == "menopause" and not cond_hits:
        spo2_z = z_scores.get("spo2_pct")
        rr_z = z_scores.get("respiratory_rate_rpm")
        apnea_like = (
            (spo2_z is not None and -spo2_z >= CONFIG["z_threshold"])
            or (rr_z is not None and rr_z >= CONFIG["z_threshold"])
        )
        if apnea_like:
            reasons.append(
                "Disturbed-sleep signals here better fit a breathing pattern "
                "(SpO2 dip / raised respiratory rate), so they are attributed to "
                "sleep-disordered breathing, not menopause."
            )
            return _GroupScore(
                points=points, reasons=reasons, sources=sources, travel_softened=False
            )

    for key, (label, direction) in GROUP_SIGNALS.get(group, {}).items():
        z = z_scores.get(key)
        if z is None:
            continue
        signed = z * direction  # positive means "in the worrying direction"
        threshold = CONFIG["z_threshold"]
        softened_here = key in travel_signals
        if softened_here:
            threshold += CONFIG["travel_threshold_relaxation"]
        if signed < threshold:
            continue
        n_wearable += 1
        raw = (signed - CONFIG["z_threshold"]) * CONFIG["points_per_z"]
        capped = max(0.0, min(raw, CONFIG["max_points_per_signal"]))
        points += capped
        arrow = "below" if direction < 0 else "above"
        reason = (
            f"{label} is {abs(z):.1f} SD {arrow} your own baseline."
        )
        if softened_here:
            reason += " This " + TRAVEL_REASON
            travel_softened = True
        reasons.append(reason)
        sources.add("wearable_measured")

    if not reasons:
        reasons.append("No worrying signals above threshold for this group.")

    return _GroupScore(
        points=points,
        reasons=reasons,
        sources=sources,
        travel_softened=travel_softened,
    )


# ---- public entry point -----------------------------------------------------


def assess_risks(
    profile: ProfileInput,
    features: FeatureSet,
    apnea: ApneaScore,
) -> RiskAssessment:
    """Score five risk groups and return a RiskAssessment (frozen contract)."""
    z_scores = features.baseline_z_scores or {}
    quality_flags = list(features.data_quality_flags or [])
    travel_signals = _active_travel_signals(quality_flags)

    # Map each red flag to the group it escalates.
    red_flags = [s.strip() for s in (profile.red_flag_symptoms or []) if s.strip()]
    escalated_groups: dict[str, list[str]] = {}
    for symptom in red_flags:
        s = symptom.lower()
        matched_group = "cardiovascular"  # default 911 path
        for grp, keywords in RED_FLAG_KEYWORDS.items():
            if any(k in s for k in keywords):
                matched_group = grp
                break
        escalated_groups.setdefault(matched_group, []).append(symptom)

    risks: list[RiskItem] = []
    n_wearable_by_group: dict[str, int] = {}
    for group in GROUP_SIGNALS:
        gs = _score_group(group, profile, z_scores, travel_signals, apnea)
        n_wearable = sum(
            1 for s in gs.sources if s == "wearable_measured"
        )  # at most 1 by set; recompute below
        # recompute wearable count from reasons that cite SD
        n_wearable = sum(1 for r in gs.reasons if " SD " in r)
        n_wearable_by_group[group] = n_wearable

        tier: Tier = _tier_for(gs.points)
        reasons = list(gs.reasons)
        sources = set(gs.sources)

        if group in escalated_groups:
            tier = "Urgent"
            symptoms = escalated_groups[group]
            reasons.insert(
                0,
                "URGENT: reported red-flag symptom(s): "
                + ", ".join(symptoms)
                + ". This is a call-911 path, not a screening result.",
            )
            sources.add("patient_reported")

        if not sources:
            sources.add("app_calculated")

        risks.append(
            RiskItem(
                risk_id=group,
                display_name=GROUP_DISPLAY[group],
                tier=tier,
                reasons=reasons,
                evidence_rating=_evidence_rating(gs.points, n_wearable),
                suggested_specialty=GROUP_SPECIALTY[group],
                source_labels=sorted(sources),
            )
        )

    urgent_override = bool(escalated_groups)
    urgent_reasons: list[str] = []
    if urgent_override:
        urgent_reasons.append(
            "Red-flag symptoms reported: "
            + ", ".join(red_flags)
            + ". Call 911 or local emergency services now. Do not wait for screening."
        )

    return RiskAssessment(
        risks=risks,
        urgent_override=urgent_override,
        urgent_reasons=urgent_reasons,
        rules_version=RULES_VERSION,
        disclaimer=DISCLAIMER,
    )
