"""Screening models for WakeSafe (Person A).

This is a screening aid, not a diagnosis. For now this file holds the STOP-Bang
questionnaire score. The apnea model and score_apnea are added later.
"""
from __future__ import annotations

from dataclasses import dataclass, field

STOP_ITEMS = ("snoring", "tired", "observed_apnea", "pressure")

# Original STOP-Bang neck cutoff. Some versions use 43 cm for men and 41 cm for women.
NECK_CM_CUTOFF = 40


@dataclass
class StopBangResult:
    score: int  # 0 to 8, one point per yes
    stop_items: int  # how many of the four STOP items are yes
    tier: str  # "Low", "Moderate", or "High" (STOP-Bang calls Moderate "intermediate")
    upgraded: bool  # True if the combination rule raised a Moderate score to High
    items: dict[str, bool]
    missing: list[str] = field(default_factory=list)  # inputs that were unknown


def score_stopbang(
    *,
    snoring: bool,
    tired: bool,
    observed_apnea: bool,
    hypertension: bool,
    bmi: float | None,
    age: int,
    neck_cm: float | None,
    male: bool,
) -> StopBangResult:
    """Score the eight STOP-Bang items.

    Bands: 0 to 2 Low, 3 to 4 Moderate, 5 to 8 High. A Moderate score becomes High
    when at least two STOP items are yes together with BMI over 35, a large neck,
    or male sex. An unknown BMI or neck size counts as "no" and is listed in
    `missing`, so the caller can say so.
    """
    missing: list[str] = []
    if bmi is None:
        missing.append("bmi")
    if neck_cm is None:
        missing.append("neck_cm")

    items = {
        "snoring": bool(snoring),
        "tired": bool(tired),
        "observed_apnea": bool(observed_apnea),
        "pressure": bool(hypertension),
        "bmi_over_35": bmi is not None and bmi > 35,
        "age_over_50": age > 50,
        "neck_over_40cm": neck_cm is not None and neck_cm > NECK_CM_CUTOFF,
        "male": bool(male),
    }
    score = sum(items.values())
    stop_items = sum(items[k] for k in STOP_ITEMS)

    if score >= 5:
        tier = "High"
    elif score >= 3:
        tier = "Moderate"
    else:
        tier = "Low"

    upgraded = False
    if tier == "Moderate" and stop_items >= 2 and (
        items["bmi_over_35"] or items["neck_over_40cm"] or items["male"]
    ):
        tier = "High"
        upgraded = True

    return StopBangResult(
        score=score,
        stop_items=stop_items,
        tier=tier,
        upgraded=upgraded,
        items=items,
        missing=missing,
    )
