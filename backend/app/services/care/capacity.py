"""Capacity providers for WakeSafe care matching.

One interface, three implementations. Each returns a ``CapacitySnapshot`` whose
``capacity_source`` is one of the FROZEN contract values on
``FacilityRecommendation.capacity_source`` (schemas.py 3.6):
``"static" | "simulated" | "live" | "unknown"``.

Design rule (task PART B): **never present simulated capacity as live.** The
source label travels with every reading, and ``SimulatedOccupancy`` stamps
``"simulated"`` and adds a human-readable "(simulated)" note so a reading can
never be mistaken for real-time data. The live feed is a stub that raises
``NotImplementedError`` -- it cannot silently fall back to simulated numbers.

Providers read licensed bed counts from ``backend/app/data/hospitals.csv`` (built
by ``scripts/build_hospitals_csv.py``). ``capacity_score`` is a 0..1 float where 1
means the most open capacity; ``None`` means unknown.
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

CapacitySource = Literal["static", "simulated", "live", "unknown"]

# backend/app/data/hospitals.csv, resolved relative to this file
# (this file lives at backend/app/services/care/capacity.py).
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
HOSPITALS_CSV = DATA_DIR / "hospitals.csv"


@dataclass(frozen=True)
class CapacitySnapshot:
    """One capacity reading for one facility. ``source`` maps 1:1 onto
    ``FacilityRecommendation.capacity_source``."""

    facility_id: str
    capacity_score: float | None
    source: CapacitySource
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.capacity_score is not None and not (0.0 <= self.capacity_score <= 1.0):
            raise ValueError(f"capacity_score must be in [0,1] or None, got {self.capacity_score}")


@runtime_checkable
class CapacityProvider(Protocol):
    """The one interface care_matcher depends on."""

    #: the contract capacity_source value this provider stamps on its readings
    source: CapacitySource

    def capacity_for(self, facility_id: str) -> CapacitySnapshot: ...


def _load_beds(csv_path: Path = HOSPITALS_CSV) -> dict[str, dict[str, int | None]]:
    """facility_id -> {'licensed': int|None, 'staffed': int|None} from hospitals.csv."""
    if not csv_path.exists():
        raise FileNotFoundError(
            f"hospitals.csv not found at {csv_path}. Run scripts/build_hospitals_csv.py first."
        )
    out: dict[str, dict[str, int | None]] = {}
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[row["facility_id"]] = {
                "licensed": _as_int(row.get("licensed_beds")),
                "staffed": _as_int(row.get("staffed_beds")),
            }
    return out


def _as_int(v: str | None) -> int | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


class StaticLicensedBeds:
    """Capacity from the REAL licensed bed counts in hospitals.csv.

    This is not a live occupancy feed -- it reports a facility's static licensed
    size, normalized across the loaded set so a bigger hospital scores higher.
    ``capacity_source="static"``.
    """

    source: CapacitySource = "static"

    def __init__(self, csv_path: Path = HOSPITALS_CSV) -> None:
        self._beds = _load_beds(csv_path)
        licensed = [b["licensed"] for b in self._beds.values() if b["licensed"]]
        self._max_licensed = max(licensed) if licensed else 0

    def capacity_for(self, facility_id: str) -> CapacitySnapshot:
        rec = self._beds.get(facility_id)
        if rec is None or rec["licensed"] in (None, 0) or self._max_licensed == 0:
            return CapacitySnapshot(
                facility_id, None, "unknown",
                notes=["no licensed-bed data for this facility"],
            )
        score = rec["licensed"] / self._max_licensed
        return CapacitySnapshot(
            facility_id,
            round(score, 4),
            "static",
            notes=[f"static licensed beds: {rec['licensed']} (normalized against {self._max_licensed})"],
        )


class SimulatedOccupancy:
    """DEMO-ONLY synthetic occupancy. Clearly labeled simulated; NEVER live.

    Produces a deterministic pseudo-random free-capacity fraction per facility
    (seedable so a demo is reproducible). ``capacity_source="simulated"`` and
    every snapshot carries an explicit "(simulated)" note. This exists so the UI
    can show a varying capacity bar without pretending the number is real.
    """

    source: CapacitySource = "simulated"

    def __init__(self, seed: str = "wakesafe-demo") -> None:
        self._seed = seed

    def capacity_for(self, facility_id: str) -> CapacitySnapshot:
        # deterministic hash -> fraction in [0.05, 0.95]; no real-time meaning
        digest = hashlib.sha256(f"{self._seed}:{facility_id}".encode()).digest()
        frac = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
        score = round(0.05 + frac * 0.90, 4)
        return CapacitySnapshot(
            facility_id,
            score,
            "simulated",
            notes=["SIMULATED occupancy for demo only -- not real-time; do not present as live"],
        )


class LiveFeed:
    """Real-time bed-availability feed. Not implemented.

    A real implementation would call a hospital capacity API (e.g. a state HHS
    feed) and stamp ``capacity_source="live"``. Until credentials and a feed
    exist it raises ``NotImplementedError`` -- it must never silently return
    simulated numbers dressed up as live.
    """

    source: CapacitySource = "live"

    def capacity_for(self, facility_id: str) -> CapacitySnapshot:
        raise NotImplementedError(
            "Live capacity feed is not configured. It needs a real-time hospital "
            "bed-availability API endpoint and credentials, and none are set up. "
            "Use StaticLicensedBeds for real licensed sizes or SimulatedOccupancy "
            "for a clearly-labeled demo value."
        )


def get_provider(kind: CapacitySource = "static", **kwargs) -> CapacityProvider:
    """Factory: pick a provider by its capacity_source name."""
    if kind == "static":
        return StaticLicensedBeds(**kwargs)
    if kind == "simulated":
        return SimulatedOccupancy(**kwargs)
    if kind == "live":
        return LiveFeed()
    raise ValueError(f"Unknown capacity provider '{kind}'. Use static, simulated or live.")


__all__ = [
    "CapacityProvider",
    "CapacitySnapshot",
    "CapacitySource",
    "StaticLicensedBeds",
    "SimulatedOccupancy",
    "LiveFeed",
    "get_provider",
    "HOSPITALS_CSV",
]
