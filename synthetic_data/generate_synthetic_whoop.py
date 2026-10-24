#!/usr/bin/env python3
"""Generate SYNTHETIC WHOOP-style nightly data for WakeSafe demos, UI work, and tests.

Synthetic data. Not clinical. Do not use to estimate model accuracy.

Run from the repository root:

    python synthetic_data/generate_synthetic_whoop.py --seed 42

All distributions and effect sizes come from synthetic_data/persona_config.yaml.
Output is fully deterministic for a given seed, cohort sizes, and config file.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = HERE / "persona_config.yaml"
DEFAULT_OUT = Path("synthetic_data") / "out"
GENERATOR_NAME = "synthetic_data/generate_synthetic_whoop.py"
NOTICE = "Synthetic data. Not clinical. Do not use to estimate model accuracy."
HEADER_PREFIX = "# SYNTHETIC DATA"
MOCK_DIR = "whoop_api_mock"
UUID_NAMESPACE = uuid.UUID("6f1d3c2a-9b7e-4c55-8a41-3e2f0d9b7a10")

PROFILE_COLUMNS = [
    "person_id", "age", "sex", "height_m", "weight_kg", "bmi", "neck_circumference_cm",
    "conditions", "snoring", "daytime_tiredness", "witnessed_breathing_pauses",
    "hypertension", "red_flag_symptoms", "is_synthetic",
]
RECOVERY_COLUMNS = [
    "person_id", "date", "user_calibrating", "recovery_score", "resting_heart_rate",
    "hrv_rmssd_milli", "spo2_percentage", "skin_temp_celsius", "is_synthetic",
]
SLEEP_COLUMNS = [
    "person_id", "date", "sleep_start", "sleep_end", "nap", "total_in_bed_time_milli",
    "total_awake_time_milli", "total_no_data_time_milli", "total_light_sleep_time_milli",
    "total_slow_wave_sleep_time_milli", "total_rem_sleep_time_milli", "sleep_cycle_count",
    "disturbance_count", "respiratory_rate", "sleep_performance_percentage",
    "sleep_consistency_percentage", "sleep_efficiency_percentage", "is_synthetic",
]
GROUND_TRUTH_COLUMNS = [
    "person_id", "true_condition", "simulated_ahi", "difficulty", "notes", "is_synthetic",
]
OUTPUT_CSVS = ("profiles.csv", "recovery.csv", "sleep.csv", "ground_truth.csv")

# Internal effect scales. Percent effects are stored as log multipliers so they compose.
EFFECT_KEYS = (
    "resting_hr_bpm", "hrv_log", "spo2_pts", "respiratory_rate_brpm", "disturbance_log",
    "efficiency_pts", "sws_log", "rem_log", "skin_temp_c",
)
_PCT_KEYS = {
    "hrv_pct": "hrv_log",
    "disturbance_pct": "disturbance_log",
    "sws_share_rel_pct": "sws_log",
    "rem_share_rel_pct": "rem_log",
}
_NON_EFFECT_KEYS = {
    "spo2_sd_mult", "respiratory_rate_sd_mult", "spo2_dip_night_prob", "spo2_dip_pts",
}
CONDITION_ORDER = ("hypertension", "type2_diabetes", "atrial_fibrillation", "asthma", "copd")
MS_PER_HOUR = 3_600_000


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Counts:
    """Cohort sizes."""

    n_healthy: int = 25
    n_osa: int = 20
    n_hard_negative: int = 6
    n_hard_positive: int = 6
    n_other: int = 8

    def total(self) -> int:
        """Total number of people."""
        return self.n_healthy + self.n_osa + self.n_hard_negative + self.n_hard_positive + self.n_other


@dataclass(frozen=True)
class PersonSpec:
    """Cohort assignment for one person before any randomness is applied."""

    true_condition: str
    difficulty: str
    cohort: str  # healthy, osa, hard_negative, hard_positive, other
    severity: str | None = None
    subtype: str | None = None


@dataclass
class Plan:
    """Resolved persona plan: which profile model and which physiological effects apply."""

    spec: PersonSpec
    profile_kind: str
    osa_severity: str | None = None
    osa_scale: float = 0.0
    ahi: float | None = None
    hn_subtype: str | None = None
    episodes: list[str] = field(default_factory=list)
    drift: bool = False
    red_flags: list[str] = field(default_factory=list)
    underlying: str | None = None


@dataclass
class PersonResult:
    """All generated rows for one person."""

    person_id: str
    number: int
    profile: dict[str, Any]
    ground_truth: dict[str, Any]
    recovery: list[dict[str, Any]]
    sleep: list[dict[str, Any]]
    extras: list[dict[str, Any]]  # per-night fields only used by the WHOOP mock


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load the persona YAML config."""
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def config_hash(path: Path | str = DEFAULT_CONFIG_PATH) -> str:
    """Short SHA-256 of the config file bytes, recorded in every output header."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def to_effect(spec: dict[str, Any] | None, scale: float = 1.0) -> dict[str, float]:
    """Convert config effect entries into additive effects on the internal scales."""
    out: dict[str, float] = {}
    for key, value in (spec or {}).items():
        if key in _NON_EFFECT_KEYS:
            continue
        if key in _PCT_KEYS:
            out[_PCT_KEYS[key]] = scale * math.log1p(float(value) / 100.0)
        elif key in EFFECT_KEYS:
            out[key] = scale * float(value)
        else:
            raise KeyError(f"unknown effect key in config: {key}")
    return out


def split_counts(n: int, mix: dict[str, float]) -> list[str]:
    """Split n into categories by proportion using the largest remainder method."""
    keys = list(mix)
    raw = [n * float(mix[k]) for k in keys]
    base = [int(math.floor(r)) for r in raw]
    remainder = n - sum(base)
    order = sorted(range(len(keys)), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[:remainder]:
        base[i] += 1
    result: list[str] = []
    for key, count in zip(keys, base):
        result.extend([key] * count)
    return result


def _clip(value: float, lo: float, hi: float) -> float:
    return float(min(max(value, lo), hi))


def _normal(rng: np.random.Generator, d: dict[str, Any], mean_key: str = "mean") -> float:
    """Draw from N(mean, sd) clipped to [min, max] when given."""
    value = float(rng.normal(d[mean_key], d["sd"]))
    if "min" in d and "max" in d:
        value = _clip(value, d["min"], d["max"])
    return value


# ---------------------------------------------------------------------------
# Cohorts and plans
# ---------------------------------------------------------------------------


def build_specs(cfg: dict[str, Any], counts: Counts) -> list[PersonSpec]:
    """Build the ordered list of cohort assignments (ids are shuffled later)."""
    specs: list[PersonSpec] = []
    specs += [PersonSpec("healthy", "easy", "healthy") for _ in range(counts.n_healthy)]
    for sev in split_counts(counts.n_osa, cfg["osa"]["severity_mix"]):
        specs.append(PersonSpec(f"osa_{sev}", "easy", "osa", severity=sev))
    subtypes = cfg["hard_negative"]["subtypes"]
    for i in range(counts.n_hard_negative):
        specs.append(PersonSpec("healthy", "hard", "hard_negative", subtype=subtypes[i % len(subtypes)]))
    hp_sev = cfg["hard_positive"]["severity"]
    specs += [
        PersonSpec(f"osa_{hp_sev}", "hard", "hard_positive", severity=hp_sev)
        for _ in range(counts.n_hard_positive)
    ]
    personas = cfg["other"]["personas"]
    for i in range(counts.n_other):
        persona = personas[i % len(personas)]
        specs.append(PersonSpec(persona, "easy", "other", subtype=persona))
    return specs


def _osa_scale(rng: np.random.Generator, cfg: dict[str, Any]) -> float:
    return _normal(rng, cfg["osa"]["individual_effect_scale"])


def _apply_other_persona(plan: Plan, persona: str, rng: np.random.Generator, cfg: dict[str, Any]) -> None:
    """Fill a plan for a non-apnea risk persona (also used for urgent underlying patterns)."""
    if persona == "healthy":
        plan.profile_kind = "other_healthy"
    elif persona == "osa_moderate":
        plan.profile_kind = "osa"
        plan.osa_severity = "moderate"
        plan.osa_scale = _osa_scale(rng, cfg)
    elif persona == "cardiovascular_strain":
        plan.profile_kind = "cardiovascular_strain"
        plan.drift = True
    elif persona in ("respiratory_flare", "acute_illness"):
        plan.profile_kind = persona
        plan.episodes = [persona]
    else:
        raise ValueError(f"unknown persona: {persona}")


def make_plan(rng: np.random.Generator, cfg: dict[str, Any], spec: PersonSpec) -> Plan:
    """Resolve the random parts of a persona (effect scale, AHI, urgent pattern, red flags)."""
    plan = Plan(spec=spec, profile_kind=spec.cohort)
    if spec.cohort == "osa":
        plan.osa_severity = spec.severity
        plan.osa_scale = _osa_scale(rng, cfg)
        lo, hi = cfg["osa"]["simulated_ahi"][spec.severity]
        plan.ahi = round(float(rng.uniform(lo, hi)), 1)
    elif spec.cohort == "hard_positive":
        hp = cfg["hard_positive"]
        plan.osa_severity = spec.severity
        individual = min(_osa_scale(rng, cfg), float(hp.get("individual_scale_max", 10.0)))
        plan.osa_scale = float(hp["effect_scale"]) * individual
        lo, hi = hp["simulated_ahi"]
        plan.ahi = round(float(rng.uniform(lo, hi)), 1)
    elif spec.cohort == "hard_negative":
        plan.hn_subtype = spec.subtype
        if spec.subtype == "cold":
            plan.episodes = ["cold"]
    elif spec.cohort == "other":
        if spec.subtype == "urgent":
            urgent = cfg["other"]["urgent"]
            underlying = str(urgent["underlying"][int(rng.integers(len(urgent["underlying"])))])
            n_flags = 2 if rng.random() < urgent["two_flags_prob"] else 1
            picks = sorted(rng.choice(len(urgent["red_flags"]), size=n_flags, replace=False))
            plan.red_flags = [str(urgent["red_flags"][i]) for i in picks]
            plan.underlying = underlying
            _apply_other_persona(plan, underlying, rng, cfg)
        else:
            _apply_other_persona(plan, str(spec.subtype), rng, cfg)
    return plan


# ---------------------------------------------------------------------------
# Profiles and baselines
# ---------------------------------------------------------------------------


def _healthy_bmi(rng: np.random.Generator, cfg: dict[str, Any]) -> float:
    return _normal(rng, cfg["healthy"]["bmi"])


def draw_profile(rng: np.random.Generator, cfg: dict[str, Any], plan: Plan) -> dict[str, Any]:
    """Draw age, sex, body size, self-reported history, and red flags."""
    h = cfg["healthy"]
    kind = plan.profile_kind
    osa_p = cfg["osa"]["profile"]
    hp = cfg["hard_positive"]
    other = cfg["other"]
    other_kinds = ("other_healthy", "cardiovascular_strain", "respiratory_flare", "acute_illness")

    # Age
    if kind in ("healthy", "hard_negative"):
        age = int(rng.integers(h["age"][0], h["age"][1] + 1))
    elif kind == "osa":
        a = dict(osa_p["age"])
        a["mean"] = a["mean"] + osa_p["age_shift"][plan.osa_severity]
        age = int(round(_normal(rng, a)))
    elif kind == "hard_positive":
        age = int(round(_normal(rng, hp["age"])))
    else:
        age = int(round(_normal(rng, other["age"])))

    # Sex and height
    male_prob = osa_p["male_prob"] if kind == "osa" else hp["male_prob"] if kind == "hard_positive" else h["male_prob"]
    sex = "male" if rng.random() < male_prob else "female"
    height = round(_clip(_normal(rng, h["height_m"][sex]), 1.45, 2.05), 2)

    # BMI
    if kind == "osa":
        if rng.random() < osa_p["normal_bmi_prob"]:
            bmi_raw = _healthy_bmi(rng, cfg)
        else:
            bmi_raw = _clip(_normal(rng, osa_p["bmi"][plan.osa_severity]), osa_p["bmi"]["min"], osa_p["bmi"]["max"])
    elif kind == "hard_positive" and not hp.get("use_healthy_bmi", True):
        bmi_raw = _clip(_normal(rng, osa_p["bmi"][plan.osa_severity]), osa_p["bmi"]["min"], osa_p["bmi"]["max"])
    elif kind == "hard_negative" and plan.hn_subtype == "high_bmi":
        lo, hi = cfg["hard_negative"]["high_bmi"]["bmi"]
        bmi_raw = float(rng.uniform(lo, hi))
    elif kind in other_kinds:
        bmi_raw = _healthy_bmi(rng, cfg) + float(other["bmi_shift"])
    else:
        bmi_raw = _healthy_bmi(rng, cfg)
    weight = round(bmi_raw * height**2, 1)
    bmi = round(weight / height**2, 1)

    # Neck circumference
    n = h["neck_cm"][sex]
    neck = n["base"] + n["per_bmi"] * (bmi - 24.0) + float(rng.normal(0.0, n["sd"]))
    if kind == "osa":
        neck += float(osa_p["extra_neck_cm"])
    neck = round(neck, 1)

    # Self-reported history probabilities
    probs: dict[str, float] = dict(h["profile_probs"])
    if kind == "osa":
        probs.update(osa_p["probs"][plan.osa_severity])
    elif kind == "hard_positive":
        probs.update(hp["probs"])
    elif kind == "hard_negative" and plan.hn_subtype == "high_bmi":
        probs.update(cfg["hard_negative"]["high_bmi"]["probs"])

    snoring = bool(rng.random() < probs.get("snoring", 0.0))
    tired = bool(rng.random() < probs.get("daytime_tiredness", 0.0))
    pauses = bool(rng.random() < probs.get("witnessed_breathing_pauses", 0.0))
    conditions = {c for c in CONDITION_ORDER if rng.random() < probs.get(c, 0.0)}

    if kind == "cardiovascular_strain":
        cv = other["cardiovascular_strain"]
        if rng.random() < cv["hypertension_prob"]:
            conditions.add("hypertension")
            if rng.random() < cv["afib_also_prob"]:
                conditions.add("atrial_fibrillation")
        else:
            conditions.add("atrial_fibrillation")
    elif kind == "respiratory_flare":
        rf = other["respiratory_flare"]
        conditions.add("asthma" if rng.random() < rf["asthma_prob"] else "copd")

    ordered = [c for c in CONDITION_ORDER if c in conditions]
    return {
        "age": age,
        "sex": sex,
        "height_m": height,
        "weight_kg": weight,
        "bmi": bmi,
        "neck_circumference_cm": neck,
        "conditions": ";".join(ordered),
        "snoring": snoring,
        "daytime_tiredness": tired,
        "witnessed_breathing_pauses": pauses,
        "hypertension": "hypertension" in conditions,
        "red_flag_symptoms": ";".join(plan.red_flags),
        "is_synthetic": True,
    }


def draw_baselines(rng: np.random.Generator, cfg: dict[str, Any], profile: dict[str, Any], plan: Plan) -> dict[str, Any]:
    """Draw each person's own healthy-style physiological baseline."""
    b = cfg["healthy"]["baselines"]
    hn = cfg["hard_negative"]
    age, bmi = profile["age"], profile["bmi"]

    r = b["resting_hr_bpm"]
    rhr = _clip(float(rng.normal(r["mean"], r["sd"])) + r["per_bmi"] * (bmi - 24.0), r["min"], r["max"])
    hv = b["hrv_ms"]
    log_hrv = math.log(hv["at_age_20"]) + hv["log_per_year"] * (age - 20) + float(rng.normal(0.0, hv["log_sd"]))
    hrv = _clip(math.exp(log_hrv), hv["min"], hv["max"])
    spo2 = _normal(rng, b["spo2_pts"])
    rr_cfg = b["respiratory_rate_brpm"]
    rr = _clip(float(rng.normal(rr_cfg["mean"], rr_cfg["sd"])) + rr_cfg["per_bmi"] * (bmi - 24.0), rr_cfg["min"], rr_cfg["max"])
    skin = _normal(rng, b["skin_temp_c"])
    in_bed = _normal(rng, b["in_bed_h"])
    start = _normal(rng, b["sleep_start_h"])
    eff = _normal(rng, b["efficiency_pts"])
    sw = b["sws_share"]
    sws = _clip(float(rng.normal(sw["mean_at_20"] + sw["per_year"] * (age - 20), sw["sd"])), sw["min"], sw["max"])
    rem = _normal(rng, b["rem_share"])
    db = b["disturbances"]
    dist = _clip(float(db["median"]) * math.exp(float(rng.normal(0.0, db["log_sd"]))), db["min"], db["max"])
    need = _normal(rng, b["sleep_need_h"])
    cycle_len = float(rng.uniform(*b["cycle_length_h"]))

    if plan.hn_subtype == "short_sleeper":
        sb = hn["short_sleeper"]["in_bed_h"]
        in_bed = _clip(float(rng.normal(sb["mean"], sb["sd"])), 5.0, 6.8)
    elif plan.hn_subtype == "endurance_trainer":
        et = hn["endurance_trainer"]
        rhr = _clip(float(rng.normal(et["resting_hr_bpm"]["mean"], et["resting_hr_bpm"]["sd"])), 38.0, 60.0)
        hrv = _clip(hrv * float(et["hrv_mult"]), hv["min"], hv["max"])
        need += float(et["extra_sleep_need_h"])

    wk = cfg["weekend"]
    has_weekend = bool(rng.random() < wk["person_prob"])
    weekend_shift = float(rng.uniform(*wk["start_shift_h"])) if has_weekend else 0.0
    weekend_extra = float(rng.uniform(*wk["extra_in_bed_h"])) if has_weekend else 0.0
    miss = cfg["missing"]
    spo2_sparse = bool(rng.random() < miss["spo2_sparse_person_prob"])
    calib = int(rng.integers(miss["calibrating_nights"][0], miss["calibrating_nights"][1] + 1))

    return {
        "rhr": rhr, "hrv": hrv, "spo2": spo2, "rr": rr, "skin": skin, "in_bed_h": in_bed,
        "start_h": start, "eff": eff, "sws": sws, "rem": rem, "dist": dist, "need_h": need,
        "cycle_len_h": cycle_len, "weekend_shift_h": weekend_shift, "weekend_extra_h": weekend_extra,
        "spo2_sparse": spo2_sparse, "calibrating_nights": calib,
    }


# ---------------------------------------------------------------------------
# Nightly simulation
# ---------------------------------------------------------------------------


def ar1(rng: np.random.Generator, n: int, phi: float, sd: float) -> np.ndarray:
    """Stationary AR(1) series with marginal standard deviation sd."""
    e = rng.standard_normal(n)
    x = np.empty(n)
    x[0] = e[0]
    k = math.sqrt(1.0 - phi**2)
    for t in range(1, n):
        x[t] = phi * x[t - 1] + k * e[t]
    return x * sd


def episode_weights(n_total: int, start: int, duration: int, tail: list[float]) -> np.ndarray:
    """Weights of 1 for the episode nights followed by a fading recovery tail."""
    w = np.zeros(n_total)
    w[start:start + duration] = 1.0
    for i, frac in enumerate(tail):
        j = start + duration + i
        if j < n_total:
            w[j] = float(frac)
    return w


def place_episode(rng: np.random.Generator, burn: int, nights: int, duration: int, tail_len: int) -> int:
    """Pick an episode start inside the output window, away from the edges when possible."""
    earliest = burn + min(4, max(0, nights - duration))
    latest = max(burn + max(0, nights - duration - tail_len), earliest)
    return int(rng.integers(earliest, latest + 1))


def sleep_consistency(start_h: np.ndarray, end_h: np.ndarray, window: int, pts_per_hour: float) -> np.ndarray:
    """Consistency from the spread of start and end times over a trailing window."""
    out = np.empty(len(start_h), dtype=int)
    for t in range(len(start_h)):
        lo = max(0, t - window + 1)
        spread = (float(np.std(start_h[lo:t + 1])) + float(np.std(end_h[lo:t + 1]))) / 2.0
        out[t] = int(round(_clip(100.0 - pts_per_hour * spread, 0.0, 100.0)))
    return out


def iso_ms(dt: datetime) -> str:
    """ISO 8601 UTC timestamp with millisecond precision, WHOOP style."""
    return f"{dt:%Y-%m-%dT%H:%M:%S}.{dt.microsecond // 1000:03d}Z"


def simulate_nights(
    rng: np.random.Generator, cfg: dict[str, Any], plan: Plan, base: dict[str, Any], nights: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Simulate every night (plus hidden burn-in) and return output rows and event notes."""
    cal, noise, miss = cfg["calendar"], cfg["noise"], cfg["missing"]
    sd = noise["nightly_sd"]
    phi = float(noise["ar1_phi"])
    burn = int(cal["burn_in_nights"])
    n = burn + nights
    start_date = date.fromisoformat(str(cal["start_date"]))
    wake_dates = [start_date + timedelta(days=int(t - burn)) for t in range(n)]
    weekend = np.array([d.weekday() in (5, 6) for d in wake_dates])  # Fri and Sat nights
    ones = np.ones(n)
    eff = {k: np.zeros(n) for k in EFFECT_KEYS}
    events: dict[str, Any] = {}

    def add(vec: dict[str, float], weights: np.ndarray) -> None:
        for key, value in vec.items():
            eff[key] += value * weights

    # Chronic apnea pattern relative to the personal baseline
    spo2_mult = rr_mult = 1.0
    if plan.osa_severity:
        sev = cfg["osa"]["effects"][plan.osa_severity]
        s = plan.osa_scale
        add(to_effect(sev, s), ones)
        spo2_mult = 1.0 + (float(sev["spo2_sd_mult"]) - 1.0) * s
        rr_mult = 1.0 + (float(sev["respiratory_rate_sd_mult"]) - 1.0) * s
        dips = rng.random(n) < float(sev["spo2_dip_night_prob"])
        mags = rng.uniform(*sev["spo2_dip_pts"], size=n) * s
        eff["spo2_pts"] -= dips * mags

    # Hard negative chronic effects
    hn = cfg["hard_negative"]
    if plan.hn_subtype in ("short_sleeper", "endurance_trainer", "high_bmi"):
        add(to_effect(hn[plan.hn_subtype].get("chronic")), ones)

    # Shared confounder: alcohol or minor illness nights, for every person
    conf = cfg["confounder_nights"]
    p_wd, p_we, c_scale = float(conf["prob_weekday"]), float(conf["prob_weekend"]), 1.0
    if plan.hn_subtype == "frequent_alcohol":
        fa = hn["frequent_alcohol"]
        p_wd, p_we, c_scale = float(fa["prob_weekday"]), float(fa["prob_weekend"]), float(fa["effect_scale"])
    conf_mask = rng.random(n) < np.where(weekend, p_we, p_wd)
    add(to_effect(conf["effects"], c_scale), conf_mask.astype(float))

    if plan.hn_subtype == "endurance_trainer":
        et = hn["endurance_trainer"]
        train = rng.random(n) < float(et["hard_training_night_prob"])
        add(to_effect(et["hard_training_effects"]), train.astype(float))

    # Episodes (cold, respiratory flare, acute illness)
    tail = [float(x) for x in cfg["episode_tail"]]
    for name in plan.episodes:
        ep = hn["cold"] if name == "cold" else cfg["other"][name]
        lo, hi = ep["duration_nights"]
        duration = min(int(rng.integers(lo, hi + 1)), nights)
        start = place_episode(rng, burn, nights, duration, len(tail))
        add(to_effect(ep["effects"]), episode_weights(n, start, duration, tail))
        events[name] = (wake_dates[start].isoformat(), wake_dates[start + duration - 1].isoformat())

    # Cardiovascular drift that ends on the last night
    if plan.drift:
        cv = cfg["other"]["cardiovascular_strain"]
        lo, hi = cv["drift_nights"]
        d = min(int(rng.integers(lo, hi + 1)), nights)
        w = np.zeros(n)
        w[n - d:] = np.arange(1, d + 1) / d
        add(to_effect(cv["effects_at_end"]), w)
        events["drift"] = (wake_dates[n - d].isoformat(), wake_dates[n - 1].isoformat(), d)

    # AR(1) noise around the personal baseline
    n_start = ar1(rng, n, phi, sd["sleep_start_h"])
    n_inbed = ar1(rng, n, phi, sd["in_bed_h"])
    n_eff = ar1(rng, n, phi, sd["efficiency_pts"])
    n_sws = ar1(rng, n, phi, sd["sws_share"])
    n_rem = ar1(rng, n, phi, sd["rem_share"])
    n_rr = ar1(rng, n, phi, sd["respiratory_rate_brpm"])
    n_spo2 = ar1(rng, n, phi, sd["spo2_pts"])
    n_skin = ar1(rng, n, phi, sd["skin_temp_c"])
    n_rhr = ar1(rng, n, phi, sd["resting_hr_bpm"])
    n_hrv = ar1(rng, n, phi, sd["hrv_log"])
    n_dist = ar1(rng, n, phi, sd["disturbance_log"])
    n_need = ar1(rng, n, phi, sd["sleep_need_h"])

    # Timing, with the weekend effect on Fri and Sat nights
    start_h = base["start_h"] + n_start + weekend * base["weekend_shift_h"]
    in_bed_h = np.clip(base["in_bed_h"] + n_inbed + weekend * base["weekend_extra_h"], 3.5, 11.0)
    end_h = start_h + in_bed_h
    consistency = sleep_consistency(
        start_h, end_h, int(cfg["sleep_consistency"]["window_nights"]), float(cfg["sleep_consistency"]["pts_per_hour_sd"])
    )

    # Durations in milliseconds, reconciled exactly
    in_bed_ms = np.round(in_bed_h * MS_PER_HOUR).astype(np.int64)
    nd_mask = rng.random(n) < float(miss["no_data_night_prob"])
    nd_frac = rng.uniform(*miss["no_data_fraction"], size=n)
    no_data_ms = np.round(in_bed_ms * nd_frac * nd_mask).astype(np.int64)
    eff_pts = np.clip(base["eff"] + n_eff + eff["efficiency_pts"], 55.0, 99.0)
    asleep_ms = np.minimum(np.round(in_bed_ms * eff_pts / 100.0).astype(np.int64), in_bed_ms - no_data_ms)
    awake_ms = in_bed_ms - no_data_ms - asleep_ms
    sws_share = np.clip(base["sws"] * np.exp(eff["sws_log"]) + n_sws, 0.03, 0.40)
    rem_share = np.clip(base["rem"] * np.exp(eff["rem_log"]) + n_rem, 0.05, 0.40)
    sws_ms = np.round(asleep_ms * sws_share).astype(np.int64)
    rem_ms = np.round(asleep_ms * rem_share).astype(np.int64)
    light_ms = asleep_ms - sws_ms - rem_ms
    asleep_h = asleep_ms / MS_PER_HOUR

    cycles = np.clip(np.round(asleep_h / base["cycle_len_h"] + rng.normal(0.0, sd["cycle_count"], n)), 0, 10).astype(int)
    ref_in_bed = float(cfg["healthy"]["baselines"]["in_bed_h"]["mean"])
    lam = base["dist"] * np.exp(eff["disturbance_log"] + n_dist) * (in_bed_h / ref_in_bed)
    disturbances = np.minimum(rng.poisson(lam), int(cfg["healthy"]["baselines"]["disturbances"]["nightly_max"]))
    need_h = np.clip(base["need_h"] + n_need, 5.0, 11.0)
    performance = np.clip(np.round(100.0 * asleep_h / need_h), 0, 100).astype(int)

    # Physiology
    rr = np.clip(base["rr"] + eff["respiratory_rate_brpm"] + n_rr * rr_mult, 8.0, 30.0)
    spo2 = np.clip(base["spo2"] + eff["spo2_pts"] + n_spo2 * spo2_mult, 85.0, 100.0)
    skin = np.clip(base["skin"] + eff["skin_temp_c"] + n_skin, 30.0, 38.0)
    rhr = np.clip(np.round(base["rhr"] + eff["resting_hr_bpm"] + n_rhr), 35, 110).astype(int)
    hrv = np.clip(base["hrv"] * np.exp(eff["hrv_log"] + n_hrv), 5.0, 250.0)

    rf = cfg["recovery_formula"]
    recovery = (
        rf["intercept"]
        + rf["hrv_log_weight"] * (np.log(hrv) - math.log(base["hrv"]))
        + rf["rhr_weight"] * (rhr - base["rhr"])
        + rf["performance_weight"] * (performance - rf["performance_ref"])
        + rng.normal(0.0, sd["recovery_pts"], n)
    )
    recovery = np.clip(np.round(recovery), 1, 99).astype(int)

    # Missing data
    no_record = rng.random(n) < float(miss["no_record_night_prob"])
    p_spo2 = float(miss["spo2_sparse_night_prob"]) if base["spo2_sparse"] else float(miss["spo2_night_prob"])
    spo2_missing = rng.random(n) < p_spo2
    skin_missing = rng.random(n) < float(miss["skin_temp_night_prob"])

    rows: list[dict[str, Any]] = []
    for t in range(burn, n):
        if no_record[t]:
            continue
        wake = wake_dates[t]
        midnight = datetime(wake.year, wake.month, wake.day)
        start_dt = midnight + timedelta(milliseconds=int(round(start_h[t] * MS_PER_HOUR)))
        end_dt = start_dt + timedelta(milliseconds=int(in_bed_ms[t]))
        rows.append({
            "night_index": t - burn,
            "date": wake.isoformat(),
            "start_dt": start_dt,
            "end_dt": end_dt,
            "user_calibrating": bool(t - burn < base["calibrating_nights"]),
            "recovery_score": int(recovery[t]),
            "resting_heart_rate": int(rhr[t]),
            "hrv_rmssd_milli": round(float(hrv[t]), 2),
            "spo2_percentage": None if spo2_missing[t] else round(float(spo2[t]), 2),
            "skin_temp_celsius": None if skin_missing[t] else round(float(skin[t]), 2),
            "total_in_bed_time_milli": int(in_bed_ms[t]),
            "total_awake_time_milli": int(awake_ms[t]),
            "total_no_data_time_milli": int(no_data_ms[t]),
            "total_light_sleep_time_milli": int(light_ms[t]),
            "total_slow_wave_sleep_time_milli": int(sws_ms[t]),
            "total_rem_sleep_time_milli": int(rem_ms[t]),
            "sleep_cycle_count": int(cycles[t]),
            "disturbance_count": int(disturbances[t]),
            "respiratory_rate": round(float(rr[t]), 2),
            "sleep_performance_percentage": int(performance[t]),
            "sleep_consistency_percentage": int(consistency[t]),
            "sleep_efficiency_percentage": round(100.0 * int(asleep_ms[t]) / int(in_bed_ms[t]), 4),
            "sleep_need_milli": int(round(need_h[t] * MS_PER_HOUR)),
        })
    return rows, events


# ---------------------------------------------------------------------------
# Person assembly
# ---------------------------------------------------------------------------


def ground_truth_notes(plan: Plan, events: dict[str, Any], profile: dict[str, Any]) -> str:
    """Human-readable notes for ground_truth.csv (screening language only)."""
    def episode(name: str) -> str:
        a, b = events[name]
        return f"{a} to {b}"

    def pattern() -> str:
        if plan.osa_severity:
            return f"pattern consistent with {plan.osa_severity} sleep apnea, effect scale {plan.osa_scale:.2f}"
        if plan.drift:
            a, b, d = events["drift"]
            return f"resting HR drifts up and HRV drifts down over the last {d} nights ({a} to {b})"
        if "respiratory_flare" in plan.episodes:
            cond = "asthma" if "asthma" in profile["conditions"] else "copd"
            return f"{cond} flare pattern on nights {episode('respiratory_flare')}"
        if "acute_illness" in plan.episodes:
            return f"acute illness pattern on nights {episode('acute_illness')}, then recovery"
        return "healthy-style baseline"

    cohort = plan.spec.cohort
    if cohort == "hard_positive":
        return f"subtle {pattern()}; healthy BMI range; no reported snoring"
    if cohort == "hard_negative":
        sub = plan.hn_subtype
        text = {
            "short_sleeper": "healthy short sleeper; short time in bed and mild sleep debt",
            "endurance_trainer": "healthy endurance trainer; hard training nights raise resting HR and lower HRV",
            "frequent_alcohol": "healthy with frequent alcohol nights",
            "high_bmi": "healthy with higher BMI and no apnea pattern",
        }.get(str(sub))
        return text if text else f"healthy with a common cold on nights {episode('cold')}"
    if plan.spec.subtype == "urgent":
        flags = ", ".join(plan.red_flags)
        return f"user-reported red flag: {flags}; underlying wearable pattern: {pattern()}"
    return pattern()


def simulate_person(
    rng: np.random.Generator, cfg: dict[str, Any], spec: PersonSpec, person_id: str, number: int, nights: int
) -> PersonResult:
    """Generate profile, ground truth, and nightly rows for one person."""
    plan = make_plan(rng, cfg, spec)
    profile = draw_profile(rng, cfg, plan)
    base = draw_baselines(rng, cfg, profile, plan)
    nightly, events = simulate_nights(rng, cfg, plan, base, nights)

    recovery_rows, sleep_rows, extras = [], [], []
    for row in nightly:
        recovery_rows.append({"person_id": person_id, **{k: row[k] for k in RECOVERY_COLUMNS[1:-1]}, "is_synthetic": True})
        sleep = {
            "person_id": person_id,
            "date": row["date"],
            "sleep_start": iso_ms(row["start_dt"]),
            "sleep_end": iso_ms(row["end_dt"]),
            "nap": False,
        }
        sleep.update({k: row[k] for k in SLEEP_COLUMNS[5:-1]})
        sleep["is_synthetic"] = True
        sleep_rows.append(sleep)
        extras.append({
            "night_index": row["night_index"],
            "end_dt": row["end_dt"],
            "sleep_need_milli": row["sleep_need_milli"],
        })

    truth = {
        "person_id": person_id,
        "true_condition": spec.true_condition,
        "simulated_ahi": plan.ahi if spec.true_condition.startswith("osa_") else None,
        "difficulty": spec.difficulty,
        "notes": ground_truth_notes(plan, events, profile),
        "is_synthetic": True,
    }
    return PersonResult(person_id, number, {"person_id": person_id, **profile}, truth, recovery_rows, sleep_rows, extras)


# ---------------------------------------------------------------------------
# WHOOP API v2 mock
# ---------------------------------------------------------------------------


def _next_token(person_id: str, endpoint: str, page: int) -> str:
    raw = f"{person_id}:{endpoint}:{page}".encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _paginate(records: list[dict[str, Any]], page_size: int, person_id: str, endpoint: str) -> list[dict[str, Any]]:
    """Split records (newest first) into WHOOP-style pages linked by next_token."""
    chunks = [records[i:i + page_size] for i in range(0, len(records), page_size)] or [[]]
    pages = []
    for i, chunk in enumerate(chunks):
        token = _next_token(person_id, endpoint, i + 1) if i + 1 < len(chunks) else None
        pages.append({"records": chunk, "next_token": token})
    return pages


def build_whoop_mock(person: PersonResult, cfg: dict[str, Any], seed: int, cfg_hash: str) -> dict[str, Any]:
    """Shape one person's data like WHOOP API v2 responses."""
    mock_cfg = cfg["whoop_mock"]
    tz = str(cfg["calendar"]["timezone_offset"])
    user_id = int(mock_cfg["user_id_base"]) + person.number
    sleeps, recoveries = [], []
    for rec, slp, extra in zip(person.recovery, person.sleep, person.extras):
        sleep_id = str(uuid.uuid5(UUID_NAMESPACE, f"{person.person_id}/sleep/{slp['date']}"))
        cycle_id = user_id * 1000 + int(extra["night_index"])
        end_dt: datetime = extra["end_dt"]
        sleeps.append({
            "id": sleep_id,
            "cycle_id": cycle_id,
            "v1_id": None,
            "user_id": user_id,
            "created_at": iso_ms(end_dt + timedelta(minutes=20)),
            "updated_at": iso_ms(end_dt + timedelta(minutes=25)),
            "start": slp["sleep_start"],
            "end": slp["sleep_end"],
            "timezone_offset": tz,
            "nap": False,
            "score_state": "SCORED",
            "score": {
                "stage_summary": {k: slp[k] for k in SLEEP_COLUMNS[5:13]},
                "sleep_needed": {
                    "baseline_milli": extra["sleep_need_milli"],
                    "need_from_sleep_debt_milli": 0,
                    "need_from_recent_strain_milli": 0,
                    "need_from_recent_nap_milli": 0,
                },
                "respiratory_rate": slp["respiratory_rate"],
                "sleep_performance_percentage": slp["sleep_performance_percentage"],
                "sleep_consistency_percentage": slp["sleep_consistency_percentage"],
                "sleep_efficiency_percentage": slp["sleep_efficiency_percentage"],
            },
        })
        recoveries.append({
            "cycle_id": cycle_id,
            "sleep_id": sleep_id,
            "user_id": user_id,
            "created_at": iso_ms(end_dt + timedelta(minutes=30)),
            "updated_at": iso_ms(end_dt + timedelta(minutes=35)),
            "score_state": "SCORED",
            "score": {k: rec[k] for k in RECOVERY_COLUMNS[2:-1]},
        })
    # WHOOP collections are sorted by start time, newest first
    sleeps.reverse()
    recoveries.reverse()
    size = int(mock_cfg["page_size"])
    profile = person.profile
    return {
        "synthetic": True,
        "notice": NOTICE,
        "person_id": person.person_id,
        "api_version": "v2",
        "generator": {"name": GENERATOR_NAME, "seed": seed, "config_sha256": cfg_hash},
        "pagination": "Page k+1 is the response to a request whose nextToken equals page k's next_token.",
        "endpoints": {
            "/v2/user/profile/basic": {
                "user_id": user_id,
                "email": f"{person.person_id.lower()}@example.invalid",
                "first_name": "Synthetic",
                "last_name": person.person_id,
            },
            "/v2/user/measurement/body": {
                "height_meter": profile["height_m"],
                "weight_kilogram": profile["weight_kg"],
                "max_heart_rate": 220 - int(profile["age"]),
            },
            "/v2/recovery": {"pages": _paginate(recoveries, size, person.person_id, "recovery")},
            "/v2/activity/sleep": {"pages": _paginate(sleeps, size, person.person_id, "sleep")},
        },
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def header_line(file_name: str, seed: int, nights: int, counts: Counts, cfg_hash: str) -> str:
    """The single comment line written at the top of every CSV."""
    return (
        f"{HEADER_PREFIX}. Not clinical. Do not use to estimate model accuracy. "
        f"file={file_name} generator={GENERATOR_NAME} seed={seed} nights={nights} "
        f"n_healthy={counts.n_healthy} n_osa={counts.n_osa} n_hard_negative={counts.n_hard_negative} "
        f"n_hard_positive={counts.n_hard_positive} n_other={counts.n_other} config_sha256={cfg_hash}"
    )


def parse_header(line: str) -> dict[str, str]:
    """Parse key=value tokens from a CSV header comment line."""
    return dict(re.findall(r"(\w+)=(\S+)", line))


def write_csv(df: pd.DataFrame, path: Path, header: str) -> None:
    """Write a CSV with a leading comment line and Unix line endings."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(header + "\n")
        df.to_csv(handle, index=False, lineterminator="\n")


def generate(
    out_dir: Path | str = DEFAULT_OUT,
    seed: int = 42,
    nights: int = 30,
    counts: Counts = Counts(),
    config_path: Path | str = DEFAULT_CONFIG_PATH,
) -> dict[str, pd.DataFrame]:
    """Generate every output file and return the CSV tables."""
    if nights < 1:
        raise ValueError("nights must be at least 1")
    if min(counts.n_healthy, counts.n_osa, counts.n_hard_negative, counts.n_hard_positive, counts.n_other) < 0:
        raise ValueError("cohort sizes must be non-negative")
    cfg = load_config(config_path)
    cfg_hash = config_hash(config_path)
    specs = build_specs(cfg, counts)

    children = np.random.SeedSequence(seed).spawn(len(specs) + 1)
    order = np.random.default_rng(children[0]).permutation(len(specs))  # ids do not reveal cohort
    width = max(3, len(str(len(specs))))
    people: list[PersonResult] = []
    for i, spec in enumerate(specs):
        number = int(order[i]) + 1
        rng = np.random.default_rng(children[i + 1])
        people.append(simulate_person(rng, cfg, spec, f"P{number:0{width}d}", number, nights))
    people.sort(key=lambda p: p.number)

    tables = {
        "profiles.csv": pd.DataFrame([p.profile for p in people], columns=PROFILE_COLUMNS),
        "recovery.csv": pd.DataFrame([r for p in people for r in p.recovery], columns=RECOVERY_COLUMNS),
        "sleep.csv": pd.DataFrame([s for p in people for s in p.sleep], columns=SLEEP_COLUMNS),
        "ground_truth.csv": pd.DataFrame([p.ground_truth for p in people], columns=GROUND_TRUTH_COLUMNS),
    }

    out = Path(out_dir)
    mock_dir = out / MOCK_DIR
    mock_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        write_csv(df, out / name, header_line(name, seed, nights, counts, cfg_hash))
    for stale in mock_dir.glob("P*.json"):  # remove files from earlier runs with other cohort sizes
        if re.fullmatch(r"P\d+\.json", stale.name):
            stale.unlink()
    for person in people:
        payload = build_whoop_mock(person, cfg, seed, cfg_hash)
        text = json.dumps(payload, indent=2, allow_nan=False) + "\n"
        (mock_dir / f"{person.person_id}.json").write_text(text, encoding="utf-8")
    return tables


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Command-line arguments."""
    p = argparse.ArgumentParser(description=f"Generate SYNTHETIC WHOOP-style data for WakeSafe. {NOTICE}")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--nights", type=int, default=30)
    p.add_argument("--n-healthy", type=int, default=25)
    p.add_argument("--n-osa", type=int, default=20)
    p.add_argument("--n-hard-negative", type=int, default=6)
    p.add_argument("--n-hard-positive", type=int, default=6)
    p.add_argument("--n-other", type=int, default=8)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)
    counts = Counts(args.n_healthy, args.n_osa, args.n_hard_negative, args.n_hard_positive, args.n_other)
    tables = generate(args.out, args.seed, args.nights, counts, args.config)
    print(f"{NOTICE}")
    print(
        f"Wrote {len(tables['profiles.csv'])} people, {len(tables['sleep.csv'])} sleep rows, "
        f"{len(tables['recovery.csv'])} recovery rows to {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
