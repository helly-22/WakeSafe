"""Live WHOOP provider (Person A): not implemented. Needs OAuth credentials and member consent."""
from __future__ import annotations

from app.models import NightRecord


def load_whoop_nights() -> list[NightRecord]:
    raise NotImplementedError(
        "Live WHOOP data needs OAuth credentials (a WHOOP client id and secret) and the member's consent, "
        "and none are configured. Use source='synthetic' for the demo or source='csv' to upload nights."
    )
