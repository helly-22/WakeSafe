"""Tests for hospitals.csv and the capacity providers (Person B).

Covers the task acceptance checks:
  - hospitals.csv loads, row count 12-20, all columns present, lat/lon non-null
  - simulated provider labels its output simulated (and is never presented as live)
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))  # backend/, so `app` is importable

from app.models import FacilityRecommendation
from app.services.care.capacity import (
    HOSPITALS_CSV,
    LiveFeed,
    SimulatedOccupancy,
    StaticLicensedBeds,
    get_provider,
)

REQUIRED_COLUMNS = [
    "facility_id", "name", "address", "lat", "lon",
    "specialties", "licensed_beds", "staffed_beds",
]


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    with HOSPITALS_CSV.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ---- hospitals.csv -----------------------------------------------------------

def test_hospitals_csv_exists_and_loads(rows):
    assert HOSPITALS_CSV.exists(), f"missing {HOSPITALS_CSV}"
    assert rows, "hospitals.csv has no data rows"


def test_row_count_is_12_to_20(rows):
    assert 12 <= len(rows) <= 20, f"expected 12-20 facilities, got {len(rows)}"


def test_all_required_columns_present(rows):
    for row in rows:
        assert list(row.keys()) == REQUIRED_COLUMNS
        assert set(row.keys()) == set(REQUIRED_COLUMNS)


def test_lat_lon_non_null_and_in_massachusetts(rows):
    for row in rows:
        assert row["lat"].strip() != "" and row["lon"].strip() != "", f"{row['facility_id']} missing coords"
        lat, lon = float(row["lat"]), float(row["lon"])
        # MA bounding box sanity (keeps a bad join from landing in the ocean)
        assert 41.0 <= lat <= 43.0, f"{row['facility_id']} lat {lat} outside MA"
        assert -74.0 <= lon <= -69.0, f"{row['facility_id']} lon {lon} outside MA"


def test_core_fields_are_populated(rows):
    ids = set()
    for row in rows:
        assert row["facility_id"].strip() and row["name"].strip() and row["address"].strip()
        assert row["specialties"].strip(), f"{row['facility_id']} has no specialties"
        assert int(row["licensed_beds"]) > 0, f"{row['facility_id']} has no licensed beds"
        ids.add(row["facility_id"])
    assert len(ids) == len(rows), "facility_id values are not unique"


def test_specialties_use_only_known_source_backed_tokens(rows):
    # every token must be one we derive from a real MassGIS column -- no free text
    allowed = {
        "emergency", "icu", "ccu_cardiac", "maternity", "nicu", "pediatric",
        "psychiatric", "burn", "rehabilitation", "med_surg", "stroke", "trauma",
    }
    for row in rows:
        for tok in row["specialties"].split(";"):
            assert tok in allowed, f"{row['facility_id']} has unknown specialty '{tok}'"


# ---- capacity providers ------------------------------------------------------

def test_static_provider_reads_real_licensed_beds():
    p = StaticLicensedBeds()
    assert p.source == "static"
    first = next(iter(_facility_ids()))
    snap = p.capacity_for(first)
    assert snap.source == "static"
    assert snap.capacity_score is None or 0.0 <= snap.capacity_score <= 1.0


def test_static_provider_returns_unknown_for_missing_facility():
    snap = StaticLicensedBeds().capacity_for("ma-does-not-exist")
    assert snap.source == "unknown" and snap.capacity_score is None


def test_simulated_provider_labels_its_output_simulated():
    p = SimulatedOccupancy()
    assert p.source == "simulated"
    snap = p.capacity_for("ma-2168")
    assert snap.source == "simulated"
    assert 0.0 <= snap.capacity_score <= 1.0
    assert any("simulated" in n.lower() for n in snap.notes)
    # must NEVER claim to be live
    assert snap.source != "live"
    assert all("live" not in n.lower() or "not" in n.lower() or "present as live" in n.lower() for n in snap.notes)


def test_simulated_provider_is_deterministic():
    a = SimulatedOccupancy(seed="x").capacity_for("ma-2168")
    b = SimulatedOccupancy(seed="x").capacity_for("ma-2168")
    assert a.capacity_score == b.capacity_score


def test_live_provider_is_a_stub_that_refuses():
    p = LiveFeed()
    assert p.source == "live"
    with pytest.raises(NotImplementedError, match="not configured"):
        p.capacity_for("ma-2168")


def test_factory_builds_each_provider_by_source_name():
    assert get_provider("static").source == "static"
    assert get_provider("simulated").source == "simulated"
    assert get_provider("live").source == "live"
    with pytest.raises(ValueError):
        get_provider("bogus")  # type: ignore[arg-type]


def test_snapshot_source_is_a_valid_contract_capacity_source():
    # the three concrete sources must all be valid FacilityRecommendation values
    for src in ("static", "simulated"):
        snap = get_provider(src).capacity_for("ma-2168")
        rec = FacilityRecommendation(
            facility_id=snap.facility_id, name="x", address="y",
            specialties=["icu"], capacity_source=snap.source, rank_score=1.0,
        )
        assert rec.capacity_source == src


def test_capacity_score_out_of_range_is_rejected():
    from app.services.care.capacity import CapacitySnapshot

    with pytest.raises(ValueError):
        CapacitySnapshot("f", 1.5, "simulated")


def _facility_ids() -> list[str]:
    with HOSPITALS_CSV.open(newline="", encoding="utf-8") as fh:
        return [r["facility_id"] for r in csv.DictReader(fh)]
