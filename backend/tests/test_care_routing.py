"""Targeted tests for the free map + live routing feature.

Covers the routing helper in isolation (OSRM success mocked, and the
fallback-to-Haversine path) and the /care/map endpoint wiring. No network call
is made: _fetch_osrm is monkeypatched. No API key is involved anywhere.
"""
from __future__ import annotations

import json
import urllib.error
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.care import routing

client = TestClient(app)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APNEA_FIXTURE = _REPO_ROOT / "scripts" / "fixtures" / "syn-apnea.json"

# Two Massachusetts points: Boston -> Worcester-ish.
FROM_LAT, FROM_LON = 42.3601, -71.0589
TO_LAT, TO_LON = 42.2626, -71.8023


def _apnea_nights() -> list[dict]:
    data = json.loads(_APNEA_FIXTURE.read_text(encoding="utf-8"))
    return data["nights"]


# --------------------------------------------------------------------------- #
# routing helper: OSRM success
# --------------------------------------------------------------------------- #

def test_build_osrm_url_uses_lon_lat_order():
    url = routing.build_osrm_url(FROM_LAT, FROM_LON, TO_LAT, TO_LON)
    # OSRM wants lon,lat;lon,lat -- longitude first.
    assert f"{FROM_LON},{FROM_LAT};{TO_LON},{TO_LAT}" in url
    assert "overview=full" in url and "geometries=geojson" in url
    assert url.startswith("https://router.project-osrm.org/route/v1/driving/")


def test_route_between_live_osrm_success(monkeypatch):
    fake_payload = {
        "code": "Ok",
        "routes": [
            {
                "duration": 3000.0,   # 3000 s -> 50.0 min
                "distance": 62000.0,  # 62 km
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[FROM_LON, FROM_LAT], [-71.4, 42.3], [TO_LON, TO_LAT]],
                },
            }
        ],
    }
    monkeypatch.setattr(routing, "_fetch_osrm", lambda url, timeout: fake_payload)

    result = routing.route_between(FROM_LAT, FROM_LON, TO_LAT, TO_LON)

    assert result["source"] == routing.SOURCE_LIVE
    assert result["estimated"] is False
    assert result["drive_minutes"] == 50.0
    assert result["distance_km"] == 62.0
    assert result["geometry"]["type"] == "LineString"
    # Live geometry keeps OSRM's multi-point path, not a 2-point straight line.
    assert len(result["geometry"]["coordinates"]) == 3


# --------------------------------------------------------------------------- #
# routing helper: fallback to Haversine
# --------------------------------------------------------------------------- #

def test_route_between_falls_back_on_network_error(monkeypatch):
    def boom(url, timeout):
        raise urllib.error.URLError("osrm unreachable")

    monkeypatch.setattr(routing, "_fetch_osrm", boom)

    result = routing.route_between(FROM_LAT, FROM_LON, TO_LAT, TO_LON)

    assert result["source"] == routing.SOURCE_ESTIMATED
    assert result["estimated"] is True
    assert result["drive_minutes"] > 0
    assert result["distance_km"] > 0
    # Fallback geometry is the 2-point straight line, in lon,lat order.
    coords = result["geometry"]["coordinates"]
    assert coords == [[FROM_LON, FROM_LAT], [TO_LON, TO_LAT]]


def test_route_between_falls_back_on_non_ok_payload(monkeypatch):
    # A syntactically valid body that is not a usable route must also fall back.
    monkeypatch.setattr(
        routing, "_fetch_osrm", lambda url, timeout: {"code": "NoRoute", "routes": []}
    )
    result = routing.route_between(FROM_LAT, FROM_LON, TO_LAT, TO_LON)
    assert result["source"] == routing.SOURCE_ESTIMATED
    assert result["estimated"] is True


def test_route_between_falls_back_on_timeout(monkeypatch):
    def slow(url, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(routing, "_fetch_osrm", slow)
    result = routing.route_between(FROM_LAT, FROM_LON, TO_LAT, TO_LON)
    assert result["source"] == routing.SOURCE_ESTIMATED


# --------------------------------------------------------------------------- #
# build_care_map
# --------------------------------------------------------------------------- #

def test_build_care_map_pins_and_route(monkeypatch):
    # Deterministic route so the assertion does not depend on the live server.
    monkeypatch.setattr(
        routing,
        "route_between",
        lambda *a, **k: {
            "source": routing.SOURCE_LIVE,
            "drive_minutes": 42.0,
            "distance_km": 50.0,
            "geometry": {"type": "LineString", "coordinates": [[FROM_LON, FROM_LAT], [TO_LON, TO_LAT]]},
            "estimated": False,
            "note": "live",
        },
    )
    screen = client.post("/screen", json={"profile": {}, "nights": _apnea_nights()})
    assessment = screen.json()["risk_assessment"]
    from app.services.care import recommend_care
    from app.models import RiskAssessment

    care = recommend_care(RiskAssessment(**assessment), user_lat=FROM_LAT, user_lon=FROM_LON)
    block = routing.build_care_map(care, FROM_LAT, FROM_LON)

    assert block["user"] == {"lat": FROM_LAT, "lon": FROM_LON}
    assert len(block["pins"]) >= 1
    assert all({"lat", "lon", "facility_id", "name", "is_top"} <= set(p) for p in block["pins"])
    assert sum(1 for p in block["pins"] if p["is_top"]) == 1  # exactly one top pin
    assert block["route_to_top"]["source"] == routing.SOURCE_LIVE
    assert "openstreetmap.org" in block["tiles"]["url"]  # free OSM tiles, no key


# --------------------------------------------------------------------------- #
# /care/map endpoint
# --------------------------------------------------------------------------- #

def test_care_map_endpoint_returns_pins_and_route(monkeypatch):
    # Force the labelled estimate so this test never touches the network.
    monkeypatch.setattr(routing, "_fetch_osrm", lambda url, timeout: (_ for _ in ()).throw(OSError("offline")))

    screen = client.post("/screen", json={"profile": {}, "nights": _apnea_nights()})
    assessment = screen.json()["risk_assessment"]

    resp = client.post(
        "/care/map",
        json={"assessment": assessment, "user_lat": FROM_LAT, "user_lon": FROM_LON},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Recommendations unchanged (still the frozen contract shape).
    assert len(body["care"]["recommendations"]) >= 1
    assert body["care"]["care_tier"] in {"Routine", "Elevated", "Urgent"}

    m = body["map"]
    assert len(m["pins"]) >= 1
    assert m["route_to_top"]["source"] == routing.SOURCE_ESTIMATED  # OSRM forced down
    assert m["route_to_top"]["estimated"] is True
    assert "openstreetmap.org" in m["tiles"]["url"]
