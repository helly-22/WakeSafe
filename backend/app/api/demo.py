"""Load demo personas from the synthetic fixtures under ``scripts/fixtures``.

The fixtures are nights-only JSON ({persona_id, display_name, nights,
travel_context}); they carry no intake profile, so the demo pairs them with a
neutral :class:`ProfileInput` (all-unknown) rather than inventing answers. The
services tolerate an all-None profile — the apnea/risk chain simply leans on the
nightly signals, which is the honest demo behaviour.

TRAVEL / CYCLE CONTEXT
----------------------
A fixture's ``travel_context`` sidecar (keyed by night_id) carries out-of-band
``travel:*`` and ``cycle:*`` flags, because the frozen NightRecord/FeatureSet
have no field for them. This module reads that sidecar and returns the flags so
the demo route can MERGE them into ``features.data_quality_flags`` before the
risk engine runs — otherwise travel suppression and the menopause cycle gate
never fire in the live demo. A fixture may also carry a per-night ``location``
([lat, lon, timestamp_seconds]) series; when present, travel is INFERRED from
the between-night speed and added as a ``travel:inferred:<mode>`` flag.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.models import NightRecord, ProfileInput
from app.services.risks import infer_travel_from_locations

# backend/app/api/demo.py -> repo root is parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = _REPO_ROOT / "scripts" / "fixtures"

# Friendly persona name (as used in the URL) -> fixture file stem.
PERSONA_FILES = {
    "NORMAL": "syn-normal.json",
    "APNEA": "syn-apnea.json",
    "MENOPAUSE": "syn-menopause.json",
    "CARDIO": "syn-cardio.json",
    "ALTITUDE": "syn-altitude.json",
    "JETLAG": "syn-jetlag.json",
}


def available_personas() -> list[str]:
    return sorted(PERSONA_FILES)


def _fixture_path(persona: str) -> Path | None:
    key = persona.strip().upper().replace("SYN-", "").replace("SYN_", "")
    name = PERSONA_FILES.get(key)
    if name is None:
        return None
    return FIXTURES_DIR / name


def _flags_from_travel_context(data: dict) -> list[str]:
    """Collect the distinct out-of-band flags from a fixture's travel_context.

    travel_context is a list of ``{"night_id": ..., "flags": [...]}``. We carry
    the flags themselves (travel:* / cycle:* strings) up to the demo route, which
    merges them into features.data_quality_flags for the engine.
    """
    flags: list[str] = []
    for entry in data.get("travel_context", []) or []:
        for flag in entry.get("flags", []) or []:
            if flag and flag not in flags:
                flags.append(flag)
    return flags


def _flags_from_locations(data: dict) -> list[str]:
    """Infer travel from a per-night location/time series, when the fixture has one.

    A fixture may carry ``locations``: a list of ``[lat, lon, timestamp_seconds]``
    across nights. We bucket the between-night speed into a transport mode and,
    when the window reads as travelling, add a ``travel:inferred:<mode>`` flag.
    The mode is internal-reasoning only; nothing enters the schema.
    """
    raw = data.get("locations")
    if not raw:
        return []
    series: list[tuple[float, float, float]] = []
    for pt in raw:
        try:
            if isinstance(pt, dict):
                series.append((float(pt["lat"]), float(pt["lon"]), float(pt["ts"])))
            else:
                series.append((float(pt[0]), float(pt[1]), float(pt[2])))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    if len(series) < 2:
        return []
    travelling, mode, _speed = infer_travel_from_locations(series)
    return [f"travel:inferred:{mode}"] if travelling else []


def load_demo(
    persona: str,
) -> tuple[str, ProfileInput, list[NightRecord], list[str]]:
    """Return (canonical_persona, profile, nights, quality_flags) for a persona.

    ``quality_flags`` are the out-of-band travel/cycle flags (from the fixture's
    travel_context sidecar and/or inferred from a location series) that the route
    merges into features.data_quality_flags before scoring.

    Raises ``KeyError`` for an unknown persona and ``FileNotFoundError`` when the
    fixture file is missing.
    """
    path = _fixture_path(persona)
    if path is None:
        raise KeyError(persona)
    if not path.exists():
        raise FileNotFoundError(str(path))

    data = json.loads(path.read_text(encoding="utf-8"))
    nights = [NightRecord(**n) for n in data.get("nights", [])]
    canonical = str(data.get("persona_id", persona)).upper()
    # A fixture may declare intake (e.g. the menopause persona is female); apply
    # it, else an all-None profile (nights-only fixture: intake unknown, not faked).
    profile_doc = data.get("profile")
    profile = ProfileInput(**profile_doc) if profile_doc else ProfileInput()

    quality_flags = _flags_from_travel_context(data)
    for flag in _flags_from_locations(data):
        if flag not in quality_flags:
            quality_flags.append(flag)
    return canonical, profile, nights, quality_flags
