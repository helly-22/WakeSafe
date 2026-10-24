"""Free, key-less drive-time routing for WakeSafe (map + live routing feature).

Public entry point: :func:`route_between`. Given two lat/lon points it asks the
OSRM PUBLIC demo server for a real driving route and returns the drive-time,
distance and a GeoJSON line the frontend can draw. When OSRM is unreachable,
errors, or times out, it falls back to the module's own Haversine estimate and
LABELS the result ``estimated-haversine`` so the caller can say so in the UI.

No API key. No paid service. No new dependency: the HTTP call uses the standard
library (``urllib``), and the geometry fallback reuses the Haversine distance the
care matcher already computes. The routing service is:

    https://router.project-osrm.org/route/v1/driving/{lon},{lat};{lon},{lat}
        ?overview=full&geometries=geojson

which is OpenStreetMap-based, open, and needs no credential.

Why a separate helper and not a schema field: ``app.models.schemas`` is FROZEN.
``FacilityRecommendation`` already carries ``latitude``/``longitude`` (map pins)
and ``drive_minutes``, but there is no field for a route polyline or a source
flag. So the route geometry and the ``live-osrm`` vs ``estimated-haversine`` flag
ride in a plain dict that the route handler adds to its JSON response, never in
the contract model.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from app.services.care.matcher import (
    AVG_DRIVE_KMH,
    estimate_drive_minutes,
    haversine_km,
)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

#: OSRM public demo server. OpenStreetMap-based, open, no key. Fair-use only, so
#: this is a demo convenience — not a production SLA.
OSRM_BASE_URL = "https://router.project-osrm.org/route/v1/driving"

#: Keep the UI responsive: if OSRM is slow we fall back rather than hang /care.
OSRM_TIMEOUT_S = 4.0

#: Source flags surfaced to the frontend so a route is never silently faked.
SOURCE_LIVE = "live-osrm"
SOURCE_ESTIMATED = "estimated-haversine"


# --------------------------------------------------------------------------- #
# OSRM URL
# --------------------------------------------------------------------------- #

def build_osrm_url(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> str:
    """Build the OSRM driving-route URL. Note OSRM takes lon,lat order."""
    coords = f"{from_lon},{from_lat};{to_lon},{to_lat}"
    return f"{OSRM_BASE_URL}/{coords}?overview=full&geometries=geojson"


# --------------------------------------------------------------------------- #
# Fallback geometry
# --------------------------------------------------------------------------- #

def _straight_line_geometry(
    from_lat: float, from_lon: float, to_lat: float, to_lon: float
) -> dict[str, Any]:
    """A two-point GeoJSON LineString (lon,lat order) for the Haversine fallback.

    It is a straight line, not a real road path — honest for a drawn "estimate".
    """
    return {
        "type": "LineString",
        "coordinates": [[from_lon, from_lat], [to_lon, to_lat]],
    }


def haversine_route(
    from_lat: float, from_lon: float, to_lat: float, to_lon: float
) -> dict[str, Any]:
    """Build the labelled Haversine-estimate route result (no network call)."""
    distance_km = haversine_km(from_lat, from_lon, to_lat, to_lon)
    return {
        "source": SOURCE_ESTIMATED,
        "drive_minutes": estimate_drive_minutes(distance_km),
        "distance_km": round(distance_km, 2),
        "geometry": _straight_line_geometry(from_lat, from_lon, to_lat, to_lon),
        "estimated": True,
        "note": (
            "Straight-line estimate: live routing was unavailable, so drive time "
            f"assumes ~{AVG_DRIVE_KMH:.0f} km/h over the great-circle distance."
        ),
    }


# --------------------------------------------------------------------------- #
# OSRM response parsing
# --------------------------------------------------------------------------- #

def _parse_osrm_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Turn an OSRM JSON payload into our labelled live-route result.

    Raises ValueError when the payload is not a usable route, so the caller can
    fall back cleanly.
    """
    if payload.get("code") != "Ok":
        raise ValueError(f"OSRM code != Ok: {payload.get('code')!r}")
    routes = payload.get("routes") or []
    if not routes:
        raise ValueError("OSRM returned no routes")
    route = routes[0]
    duration_s = route.get("duration")
    distance_m = route.get("distance")
    geometry = route.get("geometry")
    if duration_s is None or distance_m is None or not geometry:
        raise ValueError("OSRM route missing duration/distance/geometry")
    return {
        "source": SOURCE_LIVE,
        "drive_minutes": round(float(duration_s) / 60.0, 1),
        "distance_km": round(float(distance_m) / 1000.0, 2),
        "geometry": geometry,  # GeoJSON LineString (lon,lat order)
        "estimated": False,
        "note": "Live driving route from the OSRM public server (OpenStreetMap).",
    }


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

def _fetch_osrm(url: str, timeout: float) -> dict[str, Any]:
    """GET the OSRM URL and decode the JSON body. Isolated so tests can mock it.

    Uses only the standard library; no API key, no custom headers needed.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "WakeSafe/0.1 (+hackathon)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https host)
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def route_between(
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    timeout: float = OSRM_TIMEOUT_S,
) -> dict[str, Any]:
    """Return a real OSRM driving route, or a labelled Haversine estimate.

    The returned dict always has the same shape::

        {
          "source": "live-osrm" | "estimated-haversine",
          "drive_minutes": float,
          "distance_km": float,
          "geometry": {GeoJSON LineString, lon,lat order},
          "estimated": bool,
          "note": str,
        }

    so the caller never has to branch on success vs fallback to render a map.
    Any OSRM failure (network error, timeout, non-OK body, bad JSON) degrades to
    the Haversine estimate instead of raising — /care must never 500 because the
    public routing server is down.
    """
    url = build_osrm_url(from_lat, from_lon, to_lat, to_lon)
    try:
        payload = _fetch_osrm(url, timeout)
        return _parse_osrm_payload(payload)
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        # URLError covers timeouts and DNS/connection failures; OSError is the
        # broader socket family; ValueError/JSONDecodeError cover a malformed or
        # non-route body. All degrade to the labelled estimate.
        return haversine_route(from_lat, from_lon, to_lat, to_lon)


# --------------------------------------------------------------------------- #
# Map assembly for the /care response
# --------------------------------------------------------------------------- #

def build_care_map(
    care: Any,
    user_lat: float,
    user_lon: float,
    timeout: float = OSRM_TIMEOUT_S,
) -> dict[str, Any]:
    """Turn a :class:`CareRecommendations` into a map-ready block.

    Returns a plain dict (NOT a contract model) so it can ride alongside the
    frozen ``CareRecommendations`` in the route handler's JSON without touching
    ``schemas.py``::

        {
          "user": {"lat": ..., "lon": ...},
          "pins": [ {facility_id, name, lat, lon, drive_minutes, rank_score,
                     is_top}, ... ],      # only facilities with coordinates
          "route_to_top": { ...route_between() result... } | None,
          "tiles": { attribution + the free OSM raster URL template for MapLibre }
        }

    ``route_to_top`` is the OSRM (or labelled Haversine) route from the user to
    the highest-ranked facility that has coordinates. When no facility has
    coordinates (e.g. care paused for a travel window) it is ``None`` and
    ``pins`` is empty — the frontend simply shows no route.
    """
    recs = list(getattr(care, "recommendations", []) or [])

    pins: list[dict[str, Any]] = []
    top_with_coords: Any = None
    for rec in recs:
        lat = getattr(rec, "latitude", None)
        lon = getattr(rec, "longitude", None)
        if lat is None or lon is None:
            continue
        if top_with_coords is None:
            top_with_coords = rec
        pins.append(
            {
                "facility_id": rec.facility_id,
                "name": rec.name,
                "lat": lat,
                "lon": lon,
                "drive_minutes": rec.drive_minutes,
                "rank_score": rec.rank_score,
                "is_top": rec is top_with_coords,
            }
        )

    route_to_top: dict[str, Any] | None = None
    if top_with_coords is not None:
        route_to_top = route_between(
            user_lat,
            user_lon,
            top_with_coords.latitude,
            top_with_coords.longitude,
            timeout=timeout,
        )
        route_to_top["to_facility_id"] = top_with_coords.facility_id
        route_to_top["to_name"] = top_with_coords.name

    return {
        "user": {"lat": user_lat, "lon": user_lon},
        "pins": pins,
        "route_to_top": route_to_top,
        "tiles": {
            # Free OpenStreetMap raster tiles, no key. Honour OSM's usage policy:
            # this demo volume is fine; a production app should self-host tiles.
            "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            "attribution": "\u00a9 OpenStreetMap contributors",
            "max_zoom": 19,
        },
    }
