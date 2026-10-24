"""Care matcher for WakeSafe (Person B).

Public entry point: :func:`recommend_care`. It turns a RiskAssessment plus the
user's CURRENT location (lat/lon) into a ranked CareRecommendations object.

Route-where-you-are: the caller passes the user's *current* coordinates, so the
same code serves someone at home or travelling -- facilities are ranked by
proximity to whatever point is supplied, never a home default.

Contract: imports types only from ``app.models`` (frozen schemas). Facility data
is read at runtime from ``hospitals.csv`` (owned by a sibling worker) via
:data:`HOSPITALS_CSV`; when that file is absent the module falls back to a small
inline fixture so tests and demos still run.

Ranking: ``rank_score = 0.5*specialty_fit + 0.3*capacity + 0.2*proximity`` with
distance via the Haversine formula.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

from app.models import (
    CareRecommendations,
    FacilityRecommendation,
    RiskAssessment,
)

try:  # sibling worker owns capacity.py; import it when present.
    from app.services.care.capacity import get_capacity_score  # type: ignore
    _HAS_CAPACITY_PROVIDER = True
except Exception:  # pragma: no cover - exercised only when capacity.py is absent
    get_capacity_score = None  # type: ignore[assignment]
    _HAS_CAPACITY_PROVIDER = False


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

#: Runtime location of the facility catalogue (owned by the sibling worker).
HOSPITALS_CSV = Path(__file__).resolve().parents[2] / "data" / "hospitals.csv"

SCREENING_DISCLAIMER = (
    "WakeSafe is a wellness screening aid, not a medical device, and does not "
    "diagnose. These facility suggestions are informational. In an emergency "
    "call 911. For non-urgent concerns, talk with a licensed clinician."
)

CALL_911_NOTE = "If you have emergency symptoms, call 911 now - do not drive yourself."

# Ranking weights (must sum to 1.0).
W_SPECIALTY = 0.5
W_CAPACITY = 0.3
W_PROXIMITY = 0.2

# Proximity falls off linearly to zero at this distance (minutes).
PROXIMITY_FULL_FALLOFF_MIN = 60.0

# Rough average drive speed used to turn km into an estimated drive time.
AVG_DRIVE_KMH = 50.0

EARTH_RADIUS_KM = 6371.0


# --------------------------------------------------------------------------- #
# Specialty mapping
# --------------------------------------------------------------------------- #

# Each entry: keywords found in a risk_id/specialty/name -> canonical specialty.
_SPECIALTY_RULES: list[tuple[tuple[str, ...], str]] = [
    (("apnea", "sleep", "sleep-disordered", "disordered breathing"), "sleep medicine"),
    (("cardio", "cardiac", "heart", "hypertension", "arrhythmia"), "cardiology"),
    (("metabolic", "diabet", "glucose", "thyroid", "endocrin"), "endocrinology"),
    (("respirat", "pulmon", "lung", "copd", "asthma"), "pulmonology"),
]


def specialty_for_risk(risk_id: str, suggested_specialty: str = "") -> str:
    """Map a risk to the specialty that treats it.

    Looks at the ``risk_id`` first, then the contract's ``suggested_specialty``
    as a fallback, then returns ``primary care`` when nothing matches.
    """
    haystack = f"{risk_id} {suggested_specialty}".lower()
    for keywords, specialty in _SPECIALTY_RULES:
        if any(k in haystack for k in keywords):
            return specialty
    if suggested_specialty.strip():
        return suggested_specialty.strip().lower()
    return "primary care"


def needed_specialties(assessment: RiskAssessment) -> list[str]:
    """Distinct specialties implied by the assessment, highest-tier risks first."""
    order = {"Urgent": 0, "High": 1, "Moderate": 2, "Low": 3}
    ranked = sorted(assessment.risks, key=lambda r: order.get(r.tier, 9))
    out: list[str] = []
    for risk in ranked:
        spec = specialty_for_risk(risk.risk_id, risk.suggested_specialty)
        if spec not in out:
            out.append(spec)
    if not out:
        out = ["primary care"]
    return out


# --------------------------------------------------------------------------- #
# Care tier
# --------------------------------------------------------------------------- #

def derive_care_tier(assessment: RiskAssessment) -> str:
    """Derive the overall care tier from the assessment.

    urgent_override -> Urgent; any High risk -> Elevated; any Moderate ->
    Elevated; otherwise Routine. (Contract allows only Routine/Elevated/Urgent.)
    """
    if assessment.urgent_override:
        return "Urgent"
    tiers = {r.tier for r in assessment.risks}
    if "Urgent" in tiers:
        return "Urgent"
    if "High" in tiers or "Moderate" in tiers:
        return "Elevated"
    return "Routine"


# --------------------------------------------------------------------------- #
# Geo + capacity
# --------------------------------------------------------------------------- #

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two lat/lon points."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def estimate_drive_minutes(distance_km: float) -> float:
    """Rough drive-time estimate from straight-line distance."""
    return round((distance_km / AVG_DRIVE_KMH) * 60.0, 1)


def _proximity_score(drive_minutes: float) -> float:
    """1.0 next door, decaying linearly to 0.0 at PROXIMITY_FULL_FALLOFF_MIN."""
    score = 1.0 - (drive_minutes / PROXIMITY_FULL_FALLOFF_MIN)
    return max(0.0, min(1.0, score))


def _capacity_score(facility: dict) -> tuple[float, str]:
    """Return (capacity_score in 0..1, capacity_source).

    Prefers the sibling's capacity provider when available; otherwise uses a
    ``capacity_score`` column from the CSV/fixture, else a neutral default.
    """
    if _HAS_CAPACITY_PROVIDER and get_capacity_score is not None:
        try:
            score = float(get_capacity_score(facility.get("facility_id", "")))
            return max(0.0, min(1.0, score)), "live"
        except Exception:
            pass  # fall through to static
    raw = facility.get("capacity_score")
    if raw not in (None, ""):
        try:
            return max(0.0, min(1.0, float(raw))), "static"
        except (TypeError, ValueError):
            pass
    return 0.5, "unknown"


# --------------------------------------------------------------------------- #
# Facility loading
# --------------------------------------------------------------------------- #

# Small inline fixture used when hospitals.csv is not present yet. Coordinates
# are around Massachusetts so Haversine distances are realistic in tests.
_INLINE_FIXTURE: list[dict] = [
    {
        "facility_id": "fx-mgh",
        "name": "Fixture General Hospital",
        "address": "55 Fruit St, Boston, MA",
        "latitude": "42.3626",
        "longitude": "-71.0690",
        "specialties": "cardiology;sleep medicine;emergency;pulmonology",
        "has_ed": "true",
        "capacity_score": "0.6",
    },
    {
        "facility_id": "fx-sleep",
        "name": "Fixture Sleep & Lung Clinic",
        "address": "10 Clinic Way, Worcester, MA",
        "latitude": "42.2626",
        "longitude": "-71.8023",
        "specialties": "sleep medicine;pulmonology",
        "has_ed": "false",
        "capacity_score": "0.9",
    },
    {
        "facility_id": "fx-endo",
        "name": "Fixture Endocrine Center",
        "address": "200 Metabolic Rd, Springfield, MA",
        "latitude": "42.1015",
        "longitude": "-72.5898",
        "specialties": "endocrinology;primary care",
        "has_ed": "false",
        "capacity_score": "0.7",
    },
    {
        "facility_id": "fx-cape",
        "name": "Fixture Cape Regional ED",
        "address": "1 Shore Rd, Hyannis, MA",
        "latitude": "41.6529",
        "longitude": "-70.2869",
        "specialties": "emergency;cardiology;primary care",
        "has_ed": "true",
        "capacity_score": "0.5",
    },
]


def _parse_bool(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "t"}


def _parse_specialties(value) -> list[str]:
    if not value:
        return []
    text = str(value)
    sep = ";" if ";" in text else ","
    return [s.strip().lower() for s in text.split(sep) if s.strip()]


# --------------------------------------------------------------------------- #
# Unit-flag -> care-specialty mapping
# --------------------------------------------------------------------------- #
#
# The real hospitals.csv lists hospital UNIT flags (emergency, icu, ccu_cardiac,
# stroke, trauma, med_surg, ...), NOT outpatient care specialties like "sleep
# medicine". To route an apnea/pulmonary case to a plausible facility without
# fabricating a dedicated sleep clinic, we DERIVE care specialties from the unit
# flags a facility actually reports, and tag them inferred so the "why" note is
# honest ("pulmonology/sleep inferred from med/surg + ICU capability").
#
# Each rule: a unit flag present -> the care specialties it plausibly supports.
_UNIT_TO_SPECIALTY: dict[str, tuple[str, ...]] = {
    "ccu_cardiac": ("cardiology",),
    "stroke": ("cardiology",),
    "icu": ("pulmonology", "sleep medicine"),
    "med_surg": ("pulmonology", "sleep medicine", "primary care"),
    "maternity": ("gynecology",),
    "nicu": ("gynecology",),
    "psychiatric": ("psychiatry",),
    "rehabilitation": ("primary care",),
    "pediatric": ("primary care",),
}

# Specialties that are genuine CARE specialties already (not unit flags). When a
# facility lists one of these directly it is a reported capability, not inferred.
_DIRECT_CARE_SPECIALTIES = {
    "sleep medicine",
    "pulmonology",
    "cardiology",
    "endocrinology",
    "gynecology",
    "primary care",
    "psychiatry",
}


def enrich_specialties(raw_specialties: list[str]) -> tuple[list[str], list[str]]:
    """Return (all_specialties, inferred_specialties) for a facility.

    ``all_specialties`` keeps every raw flag (so Urgent still sees "emergency")
    and adds any care specialties derived from unit flags. ``inferred`` lists the
    care specialties that came ONLY from a unit-flag derivation (not reported
    directly), so the caller can say so in the note instead of fabricating a
    capability. Nothing is invented: a derived specialty is only added when a
    supporting unit flag is actually present.
    """
    out = list(raw_specialties)
    inferred: list[str] = []
    for flag in raw_specialties:
        for derived in _UNIT_TO_SPECIALTY.get(flag, ()):  # noqa: B007
            if derived not in out:
                out.append(derived)
                if derived not in raw_specialties:
                    inferred.append(derived)
    return out, inferred


def _lat_lon(fac: dict) -> tuple[float | None, float | None]:
    """Read latitude/longitude, tolerating both the inline-fixture column names
    (latitude/longitude) and the real hospitals.csv names (lat/lon)."""
    lat = _float_or_none(fac.get("latitude"))
    if lat is None:
        lat = _float_or_none(fac.get("lat"))
    lon = _float_or_none(fac.get("longitude"))
    if lon is None:
        lon = _float_or_none(fac.get("lon"))
    return lat, lon


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_facilities(csv_path: Path | None = None) -> list[dict]:
    """Load raw facility dicts from hospitals.csv, or the inline fixture.

    The returned dicts keep raw string-ish values; callers normalise them. This
    never writes hospitals.csv -- a missing file simply yields the fixture.
    """
    path = csv_path or HOSPITALS_CSV
    if not path.exists():
        return [dict(f) for f in _INLINE_FIXTURE]
    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader((line for line in handle if not line.startswith("#")))
        for row in reader:
            rows.append({k: (v if v is not None else "") for k, v in row.items()})
    return rows or [dict(f) for f in _INLINE_FIXTURE]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def _specialty_fit(facility_specialties: list[str], wanted: list[str], care_tier: str) -> float:
    """1.0 when a facility covers the top-needed specialty, scaled by coverage.

    For an Urgent tier, emergency capability dominates the fit so EDs rank top.
    """
    if care_tier == "Urgent":
        return 1.0 if "emergency" in facility_specialties else 0.2
    if not wanted:
        return 0.5
    covered = [s for s in wanted if s in facility_specialties]
    if not covered:
        return 0.0
    # Reward covering the top-priority specialty (0.6) plus breadth across the
    # rest (up to 0.4). A facility covering the top need and all others -> 1.0.
    top_bonus = 0.6 if wanted[0] in facility_specialties else 0.0
    breadth = 0.4 * (len(covered) / len(wanted))
    return min(1.0, top_bonus + breadth)


def recommend_care(
    assessment: RiskAssessment,
    user_lat: float,
    user_lon: float,
    csv_path: Path | None = None,
    max_results: int = 5,
) -> CareRecommendations:
    """Rank nearby facilities for a user at (user_lat, user_lon).

    ``user_lat``/``user_lon`` are the user's CURRENT location, so passing trip
    coordinates routes them to facilities near that point (route-where-you-are).
    """
    care_tier = derive_care_tier(assessment)
    wanted = needed_specialties(assessment)
    raw_facilities = load_facilities(csv_path)

    recs: list[FacilityRecommendation] = []
    for fac in raw_facilities:
        lat, lon = _lat_lon(fac)
        raw_specialties = _parse_specialties(fac.get("specialties"))
        specialties, inferred = enrich_specialties(raw_specialties)
        has_ed = _parse_bool(fac.get("has_ed")) or "emergency" in specialties

        if lat is not None and lon is not None:
            dist_km = haversine_km(user_lat, user_lon, lat, lon)
            drive_minutes = estimate_drive_minutes(dist_km)
            proximity = _proximity_score(drive_minutes)
        else:
            drive_minutes = None
            proximity = 0.0

        cap_score, cap_source = _capacity_score(fac)
        fit = _specialty_fit(specialties, wanted, care_tier)

        rank_score = round(
            W_SPECIALTY * fit + W_CAPACITY * cap_score + W_PROXIMITY * proximity, 4
        )

        # One-line "why this one".
        if care_tier == "Urgent":
            why = "Emergency department" if has_ed else "No ED - not ideal for an urgent need"
        else:
            matched = [s for s in wanted if s in specialties]
            why = (
                f"Covers {', '.join(matched)}" if matched else "General / primary care option"
            )
            # Be honest when a matched specialty was inferred from unit flags
            # (the facility does not list a dedicated clinic for it).
            inferred_matched = [s for s in matched if s in inferred]
            if inferred_matched:
                why += (
                    f" ({', '.join(inferred_matched)} inferred from the hospital's"
                    " units, not a listed clinic)"
                )
        if drive_minutes is not None:
            why += f"; ~{drive_minutes:.0f} min drive"

        notes = [why]
        if care_tier == "Urgent" and has_ed:
            notes.append(CALL_911_NOTE)

        recs.append(
            FacilityRecommendation(
                facility_id=str(fac.get("facility_id", "")),
                name=str(fac.get("name", "")),
                address=str(fac.get("address", "")),
                latitude=lat,
                longitude=lon,
                specialties=specialties,
                drive_minutes=drive_minutes,
                capacity_score=round(cap_score, 4),
                capacity_source=cap_source,  # type: ignore[arg-type]
                rank_score=rank_score,
                notes=notes,
            )
        )

    recs.sort(key=lambda r: r.rank_score, reverse=True)
    recs = recs[:max_results]

    return CareRecommendations(
        recommendations=recs,
        care_tier=care_tier,  # type: ignore[arg-type]
        disclaimer=SCREENING_DISCLAIMER,
    )
