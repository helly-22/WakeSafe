"""Synthetic WHOOP demo-data generator for WakeSafe (Person B, demo fixtures).

WHY THIS LIVES IN scripts/ (not backend/app/services/whoop/)
------------------------------------------------------------
backend/app/services/whoop/ already holds Dhev's live/synthetic WHOOP adapters
(whoop_live.py, synthetic.py, normalize.py, csv_upload.py). Dhev's synthetic.py
reads synthetic_data/out/ and the repo-root fixtures/ directory. To avoid any
collision this generator sits in scripts/ and writes to scripts/fixtures/ only.
It never writes to synthetic_data/, the repo-root fixtures/, or whoop/.

It imports the FROZEN contract NightRecord from app.models.schemas and NEVER
edits it. Every record it emits validates against NightRecord with source="synthetic".

TRAVEL CONTEXT CONVENTION (read this, risk engine)
--------------------------------------------------
The contract NightRecord has NO travel field, and it must not gain one. But a
travel night (altitude, jet-lag) should be SUPPRESSED by the risk engine rather
than flagged as apnea/under-recovery. We convey travel context out-of-band, using
the existing FeatureSet.data_quality_flags string convention:

    "travel:altitude:<meters>m"   e.g. "travel:altitude:2500m"
    "travel:jetlag:<hours>h"      e.g. "travel:jetlag:+8h"   (tz shift, signed)

Each generated persona file carries a parallel sidecar list `travel_context`:

    {"night_id": "<id>", "flags": ["travel:altitude:2500m"]}

one entry per affected night. The risk engine, when it builds a FeatureSet for a
window, looks up each night's sidecar flags and:
  1. copies them into FeatureSet.data_quality_flags, and
  2. for any night carrying a travel:* flag, SUPPRESSES the SpO2-dip /
     low-efficiency signals that would otherwise fire for that night (an oxygen
     dip at 2500 m is altitude, not apnea; disrupted timing after +8h is jet-lag,
     not under-recovery).

The flag strings are the only coupling; nights themselves stay pure NightRecord.

Run:
    python scripts/gen_synthetic.py            # writes scripts/fixtures/*.json
    python scripts/gen_synthetic.py --print     # also prints a one-line summary
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

# Make the backend app importable regardless of cwd, without touching sys.path
# permanently for anyone else: scripts/ -> repo root -> backend.
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.models.schemas import NightRecord  # noqa: E402  (after sys.path setup)

OUT_DIR = Path(__file__).resolve().parent / "fixtures"
START_DATE = date(2026, 9, 1)
SEED = 20261024  # deterministic output for reproducible demos


# --- healthy baselines (means), the reference every persona is perturbed from ---
BASELINE = {
    "resting_heart_rate_bpm": 56.0,
    "hrv_rmssd_ms": 72.0,
    "spo2_pct": 97.5,
    "respiratory_rate_rpm": 14.5,
    "skin_temperature_c": 33.4,
    "sleep_duration_minutes": 445.0,
    "sleep_efficiency_pct": 92.0,
    "deep_sleep_minutes": 95.0,
    "rem_sleep_minutes": 105.0,
    "disturbance_count": 6,
    "sleep_consistency_pct": 80.0,
}


@dataclass
class Persona:
    persona_id: str
    display_name: str
    nights: list[NightRecord]
    # sidecar: night_id -> list of data_quality_flags travel strings
    travel_context: dict[str, list[str]] = field(default_factory=dict)


def _jitter(rng: random.Random, mean: float, spread: float) -> float:
    """Small symmetric noise around a mean, rounded to 1 dp."""
    return round(mean + rng.uniform(-spread, spread), 1)


def _night(
    rng: random.Random,
    person: str,
    day: date,
    overrides: dict[str, float | int] | None = None,
) -> NightRecord:
    """Build one NightRecord from baseline + per-metric jitter + overrides."""
    overrides = overrides or {}
    vals: dict[str, float | int | None] = {}
    spreads = {
        "resting_heart_rate_bpm": 1.5,
        "hrv_rmssd_ms": 4.0,
        "spo2_pct": 0.4,
        "respiratory_rate_rpm": 0.4,
        "skin_temperature_c": 0.2,
        "sleep_duration_minutes": 20.0,
        "sleep_efficiency_pct": 2.0,
        "deep_sleep_minutes": 10.0,
        "rem_sleep_minutes": 12.0,
        "sleep_consistency_pct": 4.0,
    }
    for metric, mean in BASELINE.items():
        if metric in overrides:
            vals[metric] = overrides[metric]
        elif metric == "disturbance_count":
            vals[metric] = max(0, int(round(mean + rng.uniform(-2, 2))))
        else:
            vals[metric] = _jitter(rng, float(mean), spreads[metric])
    return NightRecord(
        night_id=f"{person}-{day.isoformat()}",
        date=day,
        source="synthetic",
        **vals,
    )


def _days(n: int) -> list[date]:
    return [START_DATE + timedelta(days=i) for i in range(n)]


def make_normal(rng: random.Random, nights: int = 7) -> Persona:
    """Healthy person, stable near baseline. Drives no risk -> Low tier."""
    pid = "SYN-NORMAL"
    recs = [_night(rng, pid, d) for d in _days(nights)]
    return Persona(pid, "Demo normal sleeper", recs)


def make_apnea(rng: random.Random, nights: int = 7) -> Persona:
    """Apnea pattern on 4 of 7 nights: SpO2 dips, raised RR, many disturbances,
    low efficiency. A frequency like '4 of 7 nights' is demonstrable."""
    pid = "SYN-APNEA"
    affected = {0, 2, 4, 6}  # 4 of 7
    recs: list[NightRecord] = []
    for i, d in enumerate(_days(nights)):
        if i in affected:
            ov = {
                "spo2_pct": _jitter(rng, 89.5, 1.0),           # clear desaturation
                "respiratory_rate_rpm": _jitter(rng, 17.8, 0.5),
                "disturbance_count": rng.randint(22, 34),
                "sleep_efficiency_pct": _jitter(rng, 74.0, 2.0),
                "deep_sleep_minutes": _jitter(rng, 48.0, 6.0),
            }
            recs.append(_night(rng, pid, d, ov))
        else:
            recs.append(_night(rng, pid, d))
    return Persona(pid, "Demo apnea pattern", recs)


def make_cardiovascular(rng: random.Random, nights: int = 10) -> Persona:
    """Cardiovascular drift over the window: resting HR rises, HRV falls."""
    pid = "SYN-CARDIO"
    recs: list[NightRecord] = []
    for i, d in enumerate(_days(nights)):
        frac = i / (nights - 1)
        ov = {
            "resting_heart_rate_bpm": _jitter(rng, 55.0 + 12.0 * frac, 0.8),  # 55 -> ~67
            "hrv_rmssd_ms": _jitter(rng, 78.0 - 34.0 * frac, 2.0),            # 78 -> ~44
            "respiratory_rate_rpm": _jitter(rng, 14.5 + 1.2 * frac, 0.3),
        }
        recs.append(_night(rng, pid, d, ov))
    return Persona(pid, "Demo cardiovascular drift", recs)


def make_altitude(rng: random.Random, nights: int = 5) -> Persona:
    """Altitude trip: SpO2 lower than usual on travel nights, but it is a travel
    FALSE ALARM. Sidecar marks those nights travel:altitude so the risk engine
    suppresses the SpO2 signal. Night 0 is a pre-trip home baseline."""
    pid = "SYN-ALTITUDE"
    recs: list[NightRecord] = []
    travel: dict[str, list[str]] = {}
    elevation_m = 2500
    for i, d in enumerate(_days(nights)):
        rec = _night(rng, pid, d)
        if i >= 1:  # nights 1..n are at altitude
            rec = _night(
                rng, pid, d,
                {
                    "spo2_pct": _jitter(rng, 90.5, 0.8),             # low, looks apnea-like
                    "respiratory_rate_rpm": _jitter(rng, 15.6, 0.3),  # mildly up at altitude
                },
            )
            travel[rec.night_id] = [f"travel:altitude:{elevation_m}m"]
        recs.append(rec)
    return Persona(pid, "Demo altitude trip (SpO2 suppressed)", recs, travel)


def make_jetlag(rng: random.Random, nights: int = 5) -> Persona:
    """Jet-lag trip: disrupted sleep timing/efficiency that looks like a flag but
    is travel-explained (+8h tz shift). Sidecar marks the nights travel:jetlag."""
    pid = "SYN-JETLAG"
    recs: list[NightRecord] = []
    travel: dict[str, list[str]] = {}
    tz_shift = "+8h"
    for i, d in enumerate(_days(nights)):
        rec = _night(rng, pid, d)
        if i >= 1:  # nights 1..n after the long-haul flight
            rec = _night(
                rng, pid, d,
                {
                    "sleep_efficiency_pct": _jitter(rng, 73.0, 3.0),     # poor efficiency
                    "sleep_consistency_pct": _jitter(rng, 42.0, 5.0),    # wrecked timing
                    "disturbance_count": rng.randint(18, 28),
                    "sleep_duration_minutes": _jitter(rng, 360.0, 25.0),
                },
            )
            travel[rec.night_id] = [f"travel:jetlag:{tz_shift}"]
        recs.append(rec)
    return Persona(pid, "Demo jet-lag trip (timing suppressed)", recs, travel)


def build_all(seed: int = SEED) -> list[Persona]:
    """Deterministic set covering normal + apnea + cardiovascular + altitude + jet-lag."""
    rng = random.Random(seed)
    return [
        make_normal(rng),
        make_apnea(rng),
        make_cardiovascular(rng),
        make_altitude(rng),
        make_jetlag(rng),
    ]


def persona_to_doc(p: Persona) -> dict:
    """Serialise a persona to a plain dict that reloads cleanly as NightRecords."""
    return {
        "persona_id": p.persona_id,
        "display_name": p.display_name,
        # nights are pure NightRecord dicts (JSON-mode so date serialises to str)
        "nights": [n.model_dump(mode="json") for n in p.nights],
        # out-of-band travel context, keyed by night_id (see module docstring)
        "travel_context": [
            {"night_id": nid, "flags": flags} for nid, flags in p.travel_context.items()
        ],
    }


def write_fixtures(out_dir: Path = OUT_DIR, seed: int = SEED) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for p in build_all(seed):
        path = out_dir / f"{p.persona_id.lower()}.json"
        path.write_text(json.dumps(persona_to_doc(p), indent=2), encoding="utf-8")
        written.append(path)
    # a small index so consumers can discover the set
    index = out_dir / "index.json"
    index.write_text(
        json.dumps(
            {
                "seed": seed,
                "travel_flag_convention": {
                    "altitude": "travel:altitude:<meters>m",
                    "jetlag": "travel:jetlag:<signed_hours>h",
                    "carrier": "FeatureSet.data_quality_flags (NightRecord has no travel field)",
                },
                "personas": [
                    {"persona_id": p.persona_id, "nights": len(p.nights),
                     "travel_nights": len(p.travel_context)}
                    for p in build_all(seed)
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    written.append(index)
    return written


def load_persona(path: Path) -> tuple[list[NightRecord], dict[str, list[str]]]:
    """Reload a fixture file back into NightRecords + its travel sidecar.

    Proves the JSON round-trips through the frozen contract."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    nights = [NightRecord.model_validate(n) for n in doc["nights"]]
    travel = {e["night_id"]: e["flags"] for e in doc.get("travel_context", [])}
    return nights, travel


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate synthetic WakeSafe demo NightRecord fixtures.")
    ap.add_argument("--out", type=Path, default=OUT_DIR, help="output directory (default scripts/fixtures)")
    ap.add_argument("--seed", type=int, default=SEED, help="RNG seed (default deterministic)")
    ap.add_argument("--print", dest="do_print", action="store_true", help="print a summary line per persona")
    args = ap.parse_args(argv)

    paths = write_fixtures(args.out, args.seed)
    if args.do_print:
        for p in build_all(args.seed):
            print(f"{p.persona_id}: {len(p.nights)} nights, {len(p.travel_context)} travel-flagged")
    print(f"wrote {len(paths)} files to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
