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

# Stable marker placed in a risk's reasons when its only worrying signals come
# from a travel window. The care layer keys off this to PAUSE recommendations
# ranked solely on that window (the data is still kept and tracked).
TRACK_ONLY_REASON = (
    "You appear to be travelling, so this period's data is kept and tracked, but "
    "care recommendations based only on the travel window are paused until the "
    "pattern persists back home."
)

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
    # Match both "jet_lag" and the generator's "jetlag" flag string. Jet-lag
    # disrupts sleep timing/efficiency AND fragments sleep, so it relaxes both.
    "jet_lag": ("sleep_efficiency_pct", "disturbance_count"),
    "jetlag": ("sleep_efficiency_pct", "disturbance_count"),
    # A generic travel marker relaxes the breathing + cardio signals AND the
    # sleep-timing ones, since any trip can plausibly explain all of them.
    "travel": (
        "spo2_pct",
        "respiratory_rate_rpm",
        "resting_heart_rate_bpm",
        "sleep_efficiency_pct",
        "disturbance_count",
    ),
    "vacation": (
        "spo2_pct",
        "respiratory_rate_rpm",
        "resting_heart_rate_bpm",
        "sleep_efficiency_pct",
        "disturbance_count",
    ),
}


# ---- helpers ----------------------------------------------------------------


@dataclass
class _GroupScore:
    points: float
    reasons: list[str]
    sources: set[SourceLabel]
    travel_softened: bool
    track_only: bool = False


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
    """Signals whose threshold a travel context relaxes.

    A flag like ``travel:altitude:2500m`` names a SPECIFIC context (altitude), so
    only that context's signals are relaxed -- the generic ``travel`` key is a
    fallback used only when the flag names no specific context (a bare
    ``travel`` / ``vacation`` flag). This stops a named-context flag from
    relaxing unrelated signals just because the string also contains "travel".
    """
    # Specific contexts take precedence over the generic travel/vacation set.
    generic_keys = {"travel", "vacation"}
    specific_keys = [k for k in TRAVEL_FLAG_SIGNALS if k not in generic_keys]

    out: set[str] = set()
    for flag in flags:
        f = flag.lower()
        matched_specific = False
        for key in specific_keys:
            if key in f:
                out.update(TRAVEL_FLAG_SIGNALS[key])
                matched_specific = True
        if not matched_specific:
            for key in generic_keys:
                if key in f:
                    out.update(TRAVEL_FLAG_SIGNALS[key])
    return out


# A data_quality_flags marker means the window is (at least partly) a travel
# window: either an explicit ``travel:*`` flag the generator/demo carries, or a
# context flag (altitude / jetlag / heat) whose signals the engine already
# relaxes. When a window is travel-flagged, that period is TRACK-ONLY: the nights
# and their features are kept, but no care recommendation is ranked solely on
# that window and travel alone must not push a group to High.
_TRAVEL_MARKERS: tuple[str, ...] = (
    "travel",
    "travelling",
    "traveling",
    "vacation",
    "vacationing",
    "altitude",
    "elevation",
    "jetlag",
    "jet_lag",
    "timezone",
    "heat",
)


def _is_travel_window(flags: list[str]) -> bool:
    """True when the data_quality_flags mark this window as a travel period."""
    for flag in flags:
        f = flag.lower()
        if any(m in f for m in _TRAVEL_MARKERS):
            return True
    return False


# --- transport mode inferred from location/speed (internal reasoning only) ----

EARTH_RADIUS_KM = 6371.0

# Speed (km/h) thresholds that bucket consecutive-night location change into a
# transport mode. INTERNAL ONLY: the mode shapes the reason text and the
# track-only decision; it never enters the schema or the user-facing output.
SPEED_MODE_KMH: tuple[tuple[float, str], ...] = (
    (5.0, "stationary"),
    (15.0, "walking"),
    (200.0, "driving"),
    (float("inf"), "flying"),
)
# At or above this inferred speed the window counts as "travelling" for the
# track-only rule (driving between cities / flying, not a walk around the block).
TRAVEL_SPEED_KMH = 40.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _speed_to_mode(speed_kmh: float) -> str:
    for ceiling, mode in SPEED_MODE_KMH:
        if speed_kmh < ceiling:
            return mode
    return "flying"


def infer_travel_from_locations(
    locations: list[tuple[float, float, float]],
) -> tuple[bool, str, float]:
    """Infer whether a window is a travel period from a location/time series.

    ``locations`` is a list of ``(lat, lon, timestamp_seconds)`` across nights.
    Returns ``(is_travelling, mode, max_speed_kmh)`` where ``mode`` is the
    fastest inferred transport bucket (stationary / walking / driving / flying) --
    INTERNAL reasoning only, never emitted in the schema. A window is travelling
    when the fastest consecutive-night speed is at or past ``TRAVEL_SPEED_KMH``.
    """
    max_speed = 0.0
    fastest_mode = "stationary"
    for (lat1, lon1, t1), (lat2, lon2, t2) in zip(locations, locations[1:]):
        dt_h = abs(t2 - t1) / 3600.0
        if dt_h <= 0:
            continue
        km = _haversine_km(lat1, lon1, lat2, lon2)
        speed = km / dt_h
        if speed > max_speed:
            max_speed = speed
            fastest_mode = _speed_to_mode(speed)
    return (max_speed >= TRAVEL_SPEED_KMH, fastest_mode, round(max_speed, 1))


def _condition_matches(conditions: list[str], keywords: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for cond in conditions:
        c = cond.strip().lower()
        if any(k in c for k in keywords):
            hits.append(cond.strip())
    return hits


def _is_male(sex: str | None) -> bool:
    """True only when sex is CLEARLY male. female / unknown / None / other -> False.

    Menopause must never fire for a male; unknown must still be allowed (demo
    fixtures carry a neutral all-None profile), so this returns True only for an
    unambiguous male answer.
    """
    if sex is None:
        return False
    return sex.strip().lower() in {"male", "m", "man"}


# A cycle-disruption marker carried in FeatureSet.data_quality_flags, the same
# out-of-band convention travel uses (NightRecord/FeatureSet have no cycle field
# and schemas.py is frozen). Any flag mentioning one of these is a reported /
# marked menstrual-cycle irregularity -- the signal a menopause flag requires.
_CYCLE_DISRUPTION_MARKERS: tuple[str, ...] = (
    "cycle:",
    "cycle_irregular",
    "cycle-irregular",
    "irregular_cycle",
    "irregular_periods",
    "menstrual",
    "vasomotor",
    "hot_flash",
    "hot-flash",
    "night_sweat",
    "night-sweat",
)


def _has_cycle_disruption(flags: list[str]) -> bool:
    """True when data_quality_flags carry an explicit cycle-disruption marker."""
    for flag in flags:
        f = flag.lower()
        if any(m in f for m in _CYCLE_DISRUPTION_MARKERS):
            return True
    return False


def _score_group(
    group: str,
    profile: ProfileInput,
    z_scores: dict[str, float | None],
    travel_signals: set[str],
    apnea: ApneaScore,
    quality_flags: list[str],
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
    non_travel_signal = False
    is_travel_window = _is_travel_window(quality_flags)

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

    # --- Menopause gating (sex + required cycle-disruption signal) -----------
    # --- Menopause gating (required cycle-disruption signal) -----------------
    #
    #  SEX is handled UPSTREAM: assess_risks SKIPS the menopause group entirely
    #  for a clearly-male profile (it is excluded from the result, not scored as
    #  a Low row), so by the time this runs the profile is female or
    #  unknown/None. _is_male is still checked here as defensive depth for any
    #  direct caller of _score_group.
    #
    #  CYCLE DISRUPTION REQUIRED. A menopause flag needs a marked menstrual-cycle
    #  disruption present -- EITHER a reported peri/menopause condition (irregular
    #  periods / cycle irregularity / vasomotor / hot flashes / night sweats,
    #  matched above into cond_hits) OR an explicit cycle-disruption marker in
    #  data_quality_flags ("cycle:irregular", the same out-of-band convention
    #  travel uses, since NightRecord/FeatureSet have no cycle field and
    #  schemas.py is frozen). Without either, the warm/disturbed-night signals are
    #  NON-specific (apnea and acute illness fragment sleep too), so the group
    #  does NOT reach Moderate/High -- it scores none of its z-signals.
    if group == "menopause":
        if _is_male(profile.sex):
            # Should not be reached via assess_risks (suppressed there); kept as
            # a guard for direct callers. Scores nothing.
            return _GroupScore(
                points=0.0, reasons=reasons, sources=sources, travel_softened=False
            )
        has_cycle_signal = bool(cond_hits) or _has_cycle_disruption(quality_flags)
        if not has_cycle_signal:
            reasons.append(
                "No marked menstrual-cycle disruption is reported or recorded, so "
                "warm / disturbed-sleep signals are not attributed to menopause "
                "(they are non-specific on their own)."
            )
            return _GroupScore(
                points=points, reasons=reasons, sources=sources, travel_softened=False
            )

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
        else:
            non_travel_signal = True
        reasons.append(reason)
        sources.add("wearable_measured")

    # --- Travel track-only suppression --------------------------------------
    #
    # When the window is a travel period (altitude / jet-lag / an explicit
    # travel flag), that data is KEPT and still scored, but:
    #   * travel alone must not push a group to High, and
    #   * no care recommendation may be ranked solely on the travel window.
    # So if this group has worrying signals and NONE of them come from a
    # non-travel source, the group is TRACK-ONLY: its points are capped just
    # below the High band and ``track_only`` is set so care routing pauses
    # recommendations based only on this window. A reason states the data is
    # kept but recommendations are paused while travelling. A non-travel signal
    # present in the same group lifts the cap (the risk is not travel-only).
    track_only = False
    if (
        is_travel_window
        and group != "menopause"
        and sources
        and not non_travel_signal
        and not cond_hits
    ):
        high_floor = CONFIG["tier_bands"]["High"][0]
        if points >= high_floor:
            points = high_floor - 0.01  # keep it out of the High band
        track_only = True
        reasons.append(TRACK_ONLY_REASON)

    if not reasons:
        reasons.append("No worrying signals above threshold for this group.")

    return _GroupScore(
        points=points,
        reasons=reasons,
        sources=sources,
        travel_softened=travel_softened,
        track_only=track_only,
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
        # A male profile has no menopause question to answer: EXCLUDE the group
        # from the result entirely (not scored, not listed, not a zeroed row) --
        # a "Menopause: Low" row would wrongly imply the question was askable.
        # DELIBERATE PRODUCT CALL: unknown/None/unspecified sex still EVALUATES
        # the group (female and unknown => evaluate; only clearly-male => skip),
        # so a real case where sex was never recorded is not silently missed.
        if group == "menopause" and _is_male(profile.sex):
            continue

        gs = _score_group(group, profile, z_scores, travel_signals, apnea, quality_flags)
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


# ---- travel track-only introspection (for the care layer) -------------------


def travel_track_only_risk_ids(assessment: RiskAssessment) -> set[str]:
    """risk_ids whose only worrying signals came from a travel window.

    Keyed off the stable TRACK_ONLY_REASON marker the engine writes. The care
    layer uses this to pause recommendations ranked solely on the travel window.
    """
    return {
        r.risk_id
        for r in assessment.risks
        if any(TRACK_ONLY_REASON in reason for reason in r.reasons)
    }


def care_warranted_outside_travel(assessment: RiskAssessment) -> bool:
    """True when care is warranted by NON-travel data.

    Care is warranted when an urgent override is set, or any risk reaches
    Moderate/High/Urgent that is NOT a travel-track-only risk. When every
    elevated risk is travel-track-only, care based solely on the travel window
    is paused (the data is still tracked).
    """
    if assessment.urgent_override:
        return True
    track_only = travel_track_only_risk_ids(assessment)
    for r in assessment.risks:
        if r.tier in ("Moderate", "High", "Urgent") and r.risk_id not in track_only:
            return True
    return False
