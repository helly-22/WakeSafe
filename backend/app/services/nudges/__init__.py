"""Public-health nudge service for WakeSafe.

Pulls FRESH flu / respiratory (+ West Nile in season) signals from the CDC
Socrata open-data API on demand, caches them briefly in memory, and falls back
to the already-downloaded cached CSVs when the live API is unreachable -- always
labelling which source a nudge came from.

Tone is a hard requirement (this is a health product): every nudge is calm,
carries exactly ONE positive action, uses NO fear words, and the set is
rate-limited to a small, most-relevant handful. Each nudge carries an honest
``as of <date>`` stamp taken from the data itself.
"""
from __future__ import annotations

from .service import (
    Nudge,
    NudgeBundle,
    build_nudges,
    FEAR_WORDS,
    CDC_RESP_PATHOGENS_ID,
    CDC_FLUVIEW_ID,
)

__all__ = [
    "Nudge",
    "NudgeBundle",
    "build_nudges",
    "FEAR_WORDS",
    "CDC_RESP_PATHOGENS_ID",
    "CDC_FLUVIEW_ID",
]
