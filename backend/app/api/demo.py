"""Load demo personas from the synthetic fixtures under ``scripts/fixtures``.

The fixtures are nights-only JSON ({persona_id, display_name, nights,
travel_context}); they carry no intake profile, so the demo pairs them with a
neutral :class:`ProfileInput` (all-unknown) rather than inventing answers. The
services tolerate an all-None profile — the apnea/risk chain simply leans on the
nightly signals, which is the honest demo behaviour.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.models import NightRecord, ProfileInput

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


def load_demo(persona: str) -> tuple[str, ProfileInput, list[NightRecord]]:
    """Return (canonical_persona, profile, nights) for a demo persona.

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
    profile = ProfileInput()  # nights-only fixture: intake unknown, not faked
    return canonical, profile, nights
