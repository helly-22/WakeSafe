"""Tests for app.services.care.matcher (recommend_care).

These use the matcher's own inline fixture (by pointing csv_path at a file that
does not exist) so they are independent of the sibling-owned hospitals.csv.
Cases: a Routine assessment, an Urgent assessment (ED + 911), and an
away-from-home trip coordinate that must return facilities near THAT point.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))  # backend/, so `app` is importable

from app.models import CareRecommendations, RiskAssessment, RiskItem
from app.services.care import recommend_care
from app.services.care.matcher import haversine_km

# A path that does not exist -> load_facilities() uses the inline fixture.
NO_CSV = Path(__file__).resolve().parent / "_no_such_hospitals.csv"

# Reference coordinates.
BOSTON_LAT, BOSTON_LON = 42.3601, -71.0589      # near fixture Boston hospital
CAPE_LAT, CAPE_LON = 41.6529, -70.2869          # near fixture Cape ED (the trip)


def _risk(risk_id: str, display: str, tier: str, specialty: str) -> RiskItem:
    return RiskItem(
        risk_id=risk_id,
        display_name=display,
        tier=tier,
        reasons=["demo reason"],
        evidence_rating="Moderate",
        suggested_specialty=specialty,
        source_labels=["app_calculated"],
    )


def _assessment(risks, urgent=False, urgent_reasons=None) -> RiskAssessment:
    return RiskAssessment(
        risks=risks,
        urgent_override=urgent,
        urgent_reasons=urgent_reasons or [],
        rules_version="test-1",
        disclaimer="screening only, not a diagnosis",
    )


# --------------------------------------------------------------------------- #
# Routine
# --------------------------------------------------------------------------- #

def test_routine_low_risk_sleep():
    """A single Low sleep-apnea risk -> Routine tier, sleep-capable top pick."""
    assessment = _assessment(
        [_risk("apnea_pattern", "Sleep apnea pattern", "Low", "sleep medicine")]
    )
    result = recommend_care(assessment, BOSTON_LAT, BOSTON_LON, csv_path=NO_CSV)

    assert isinstance(result, CareRecommendations)
    assert result.care_tier == "Routine"
    assert result.recommendations, "expected at least one facility"
    # Ranked best-first.
    scores = [r.rank_score for r in result.recommendations]
    assert scores == sorted(scores, reverse=True)
    # Top pick should cover sleep medicine.
    assert "sleep medicine" in result.recommendations[0].specialties
    # Disclaimer present and no 911 note anywhere for a Routine tier.
    assert result.disclaimer
    assert all("911" not in n for r in result.recommendations for n in r.notes)


# --------------------------------------------------------------------------- #
# Urgent -> ED + 911
# --------------------------------------------------------------------------- #

def test_urgent_override_returns_ed_and_911_note():
    """urgent_override -> Urgent tier, top pick is an ED, carries a 911 note."""
    assessment = _assessment(
        [_risk("cardio_redflag", "Possible cardiac event", "Urgent", "cardiology")],
        urgent=True,
        urgent_reasons=["chest pain reported"],
    )
    result = recommend_care(assessment, BOSTON_LAT, BOSTON_LON, csv_path=NO_CSV)

    assert result.care_tier == "Urgent"
    top = result.recommendations[0]
    # Top recommendation must have emergency capability.
    assert "emergency" in top.specialties, "urgent tier should surface an ED first"
    # A 911 note must appear on the ED recommendation.
    all_notes = " ".join(n for r in result.recommendations for n in r.notes)
    assert "911" in all_notes
    assert any("911" in n for n in top.notes)


# --------------------------------------------------------------------------- #
# Away-from-home (route-where-you-are)
# --------------------------------------------------------------------------- #

def test_away_from_home_routes_to_local_facilities():
    """Trip coords (Cape Cod) -> nearest facility is the Cape one, not Boston."""
    assessment = _assessment(
        [_risk("apnea_pattern", "Sleep apnea pattern", "Moderate", "sleep medicine")]
    )

    home = recommend_care(assessment, BOSTON_LAT, BOSTON_LON, csv_path=NO_CSV)
    trip = recommend_care(assessment, CAPE_LAT, CAPE_LON, csv_path=NO_CSV)

    # Nearest facility by drive time must differ between the two locations.
    def nearest(res):
        drivable = [r for r in res.recommendations if r.drive_minutes is not None]
        return min(drivable, key=lambda r: r.drive_minutes)

    home_nearest = nearest(home)
    trip_nearest = nearest(trip)

    # From Cape coords, the Cape fixture facility is the closest.
    assert trip_nearest.facility_id == "fx-cape"
    # And it is genuinely closer from the trip point than from home.
    assert trip_nearest.drive_minutes < home_nearest.drive_minutes or \
        home_nearest.facility_id != "fx-cape"
    # Sanity: Haversine shrinks when we stand next to the facility.
    d_home = haversine_km(BOSTON_LAT, BOSTON_LON, 41.6529, -70.2869)
    d_trip = haversine_km(CAPE_LAT, CAPE_LON, 41.6529, -70.2869)
    assert d_trip < d_home


# --------------------------------------------------------------------------- #
# Contract-shape sanity
# --------------------------------------------------------------------------- #

def test_output_conforms_to_contract():
    assessment = _assessment(
        [_risk("metabolic_drift", "Metabolic drift", "Moderate", "endocrinology")]
    )
    result = recommend_care(assessment, BOSTON_LAT, BOSTON_LON, csv_path=NO_CSV)
    assert result.care_tier in {"Routine", "Elevated", "Urgent"}
    for rec in result.recommendations:
        assert rec.capacity_source in {"static", "simulated", "live", "unknown"}
        assert isinstance(rec.rank_score, float)
        assert rec.notes  # one-line "why this one"


# --------------------------------------------------------------------------- #
# BUG 3: specialty matching against the REAL hospitals.csv shape
# --------------------------------------------------------------------------- #
#
# The real catalogue uses `lat`/`lon` columns and lists hospital UNIT flags
# (emergency;icu;med_surg;stroke;...), never an outpatient "sleep medicine"
# value. The matcher must still route a non-urgent apnea case to a facility that
# plausibly offers sleep/pulmonology care, and say when that is inferred.

from app.services.care.matcher import enrich_specialties, _lat_lon  # noqa: E402

_REAL_SHAPE_CSV = """facility_id,name,address,lat,lon,specialties,licensed_beds,staffed_beds
ma-big,Giant Trauma ER,"1 Big St, Boston MA",42.3632,-71.0688,emergency;icu;ccu_cardiac;med_surg;stroke;trauma,1045,
ma-psych,Standalone Psych Hospital,"2 Calm Rd, Boston MA",42.3605,-71.0600,psychiatric,358,
ma-comm,Community Medical Center,"3 Main St, Boston MA",42.3610,-71.0595,emergency;icu;med_surg;stroke,250,
"""


def _write_real_shape_csv(tmp_path):
    p = tmp_path / "hospitals_real_shape.csv"
    p.write_text(_REAL_SHAPE_CSV, encoding="utf-8")
    return p


def test_unit_flags_map_to_sleep_pulmonology_and_are_marked_inferred():
    full, inferred = enrich_specialties(["emergency", "icu", "med_surg", "stroke"])
    # Derived care specialties appear...
    assert "sleep medicine" in full
    assert "pulmonology" in full
    assert "cardiology" in full  # from stroke/ccu
    # ...and are flagged as inferred (not reported directly).
    assert "sleep medicine" in inferred
    assert "pulmonology" in inferred


def test_lat_lon_alias_reads_real_csv_columns():
    assert _lat_lon({"lat": "42.5", "lon": "-71.1"}) == (42.5, -71.1)
    assert _lat_lon({"latitude": "42.5", "longitude": "-71.1"}) == (42.5, -71.1)
    assert _lat_lon({}) == (None, None)


def test_apnea_case_top_pick_covers_sleep_or_pulmonology(tmp_path):
    csv_path = _write_real_shape_csv(tmp_path)
    assessment = _assessment(
        [_risk("sleep_disordered_breathing", "Sleep-disordered breathing", "High", "Sleep medicine")]
    )
    result = recommend_care(assessment, BOSTON_LAT, BOSTON_LON, csv_path=csv_path)

    assert result.care_tier == "Elevated"  # High, not urgent
    top = result.recommendations[0]
    # The top pick genuinely covers sleep medicine or pulmonology (not chosen as a
    # generic ER while ignoring the specialty map).
    assert any(s in top.specialties for s in ("sleep medicine", "pulmonology"))
    # The psych-only hospital, which cannot offer sleep/pulmonology, ranks last.
    assert result.recommendations[-1].facility_id == "ma-psych"
    # The note is honest: it says the specialty is inferred from units.
    assert any("inferred" in n.lower() for n in top.notes)


def test_apnea_case_does_not_rank_specialtyless_facility_first(tmp_path):
    # A facility with NO sleep/pulmonology capability must not outrank one that
    # has it for an apnea case.
    csv_path = _write_real_shape_csv(tmp_path)
    assessment = _assessment(
        [_risk("sleep_disordered_breathing", "Sleep-disordered breathing", "Moderate", "Sleep medicine")]
    )
    result = recommend_care(assessment, BOSTON_LAT, BOSTON_LON, csv_path=csv_path)
    top = result.recommendations[0]
    assert top.facility_id != "ma-psych"
    assert any(s in top.specialties for s in ("sleep medicine", "pulmonology"))


def test_urgent_still_routes_to_ed_with_real_csv_shape(tmp_path):
    csv_path = _write_real_shape_csv(tmp_path)
    assessment = _assessment(
        [_risk("cardio_redflag", "Possible cardiac event", "Urgent", "cardiology")],
        urgent=True,
        urgent_reasons=["chest pain reported"],
    )
    result = recommend_care(assessment, BOSTON_LAT, BOSTON_LON, csv_path=csv_path)
    assert result.care_tier == "Urgent"
    top = result.recommendations[0]
    assert "emergency" in top.specialties
    assert any("911" in n for n in top.notes)
