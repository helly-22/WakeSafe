"""Data providers for WakeSafe (Person A): synthetic demo people, CSV upload, optional live WHOOP."""
from __future__ import annotations

from typing import Literal

from app.models import NightRecord, ProfileInput

from .csv_upload import load_csv_nights
from .normalize import ProviderDataError
from .synthetic import PersonaInfo, list_personas, load_synthetic_nights, load_synthetic_profile
from .whoop_live import load_whoop_nights


def load_nights(
    source: Literal["synthetic", "csv", "whoop"] = "synthetic",
    *,
    persona_id: str | None = None,
    csv_file: str | None = None,
    profile: ProfileInput | None = None,
) -> list[NightRecord]:
    """Contract signature (TEAM_CONTRACTS.md 4.1). `profile` is accepted for the contract and not used yet."""
    if source == "synthetic":
        return load_synthetic_nights(persona_id)
    if source == "csv":
        return load_csv_nights(csv_file)
    if source == "whoop":
        return load_whoop_nights()
    raise ProviderDataError(f"Unknown data source '{source}'. Use 'synthetic', 'csv' or 'whoop'.")


__all__ = [
    "PersonaInfo",
    "ProviderDataError",
    "list_personas",
    "load_nights",
    "load_synthetic_profile",
]
