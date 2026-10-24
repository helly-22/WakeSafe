"""Screening models for WakeSafe (Person A).

This is a screening aid, not a diagnosis. For now this file holds the STOP-Bang
questionnaire score and the runtime apnea model scorer. Tier logic is in scoring.py.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

STOP_ITEMS = ("snoring", "tired", "observed_apnea", "pressure")

# Original STOP-Bang neck cutoff. Some versions use 43 cm for men and 41 cm for women.
NECK_CM_CUTOFF = 40

# backend/app/ml/apnea_resting_hr_rmssd.json, written by ml/training/train_apnea_model.py
RUNTIME_ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "ml" / "apnea_resting_hr_rmssd.json"


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
    snoring: bool | None,
    tired: bool | None,
    observed_apnea: bool | None,
    hypertension: bool | None,
    bmi: float | None,
    age: int | None,
    neck_cm: float | None,
    male: bool | None,
) -> StopBangResult:
    """Score the eight STOP-Bang items.

    Bands: 0 to 2 Low, 3 to 4 Moderate, 5 to 8 High. A Moderate score becomes High
    when at least two STOP items are yes together with BMI over 35, a large neck,
    or male sex. Any unknown answer (None) counts as "no" and is listed in
    `missing`, so the caller can say so.
    """
    answers = {
        "snoring": snoring,
        "tired": tired,
        "observed_apnea": observed_apnea,
        "hypertension": hypertension,
        "bmi": bmi,
        "age": age,
        "neck_cm": neck_cm,
        "male": male,
    }
    missing = [name for name, value in answers.items() if value is None]

    items = {
        "snoring": bool(snoring),
        "tired": bool(tired),
        "observed_apnea": bool(observed_apnea),
        "pressure": bool(hypertension),
        "bmi_over_35": bmi is not None and bmi > 35,
        "age_over_50": age is not None and age > 50,
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


def apnea_model_score(artifact: dict, resting_hr_bpm: float, hrv_rmssd_ms: float) -> float:
    """Score from the runtime model (resting heart rate and RMSSD), read from its JSON artifact.

    The result is a number between 0 and 1 from a logistic function, but it is not a
    calibrated probability and must not be shown as a percentage. Compare it with
    `artifact["cutoff"]`. Inputs use the units in `artifact["units"]`.
    """
    values = {"resting_hr_bpm": resting_hr_bpm, "hrv_rmssd_ms": hrv_rmssd_ms}
    z = [
        (values[name] - mean) / scale
        for name, mean, scale in zip(artifact["features"], artifact["scaler_mean"], artifact["scaler_scale"])
    ]
    logit = artifact["intercept"] + sum(c * v for c, v in zip(artifact["coef"], z))
    return 1.0 / (1.0 + math.exp(-logit))


def load_apnea_artifact(path: str | Path = RUNTIME_ARTIFACT_PATH) -> dict:
    return json.loads(Path(path).read_text())
