"""Nudge generation service.

Flow per ``build_nudges`` call:

1. Try the LIVE CDC Socrata API (short in-memory cache, ~15 min) for current
   national respiratory positivity (flu/RSV/COVID) and state ILI activity.
2. On any fetch failure / timeout, fall back to the cached CSVs downloaded under
   ``ml/data/raw/disease_feeds/`` -- and label every resulting nudge ``cached``
   with the cached data's own honest date.
3. Turn the signals into a small set of calm, one-positive-action, fear-word-free
   nudges, each stamped ``as of <date>``.

Nothing here raises to the caller for a data problem: a total failure degrades to
a single calm, generic seasonal nudge rather than crashing the endpoint.
"""
from __future__ import annotations

import csv
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

import httpx

# --- CDC Socrata datasets (same endpoints the MANIFEST identified) -----------
SOCRATA_HOST = "https://data.cdc.gov"
CDC_RESP_PATHOGENS_ID = "seuz-s2cv"  # % tests positive: COVID-19 / Influenza / RSV (national, current)
CDC_FLUVIEW_ID = "6svj-q4zv"  # ILINet outpatient activity level, by state

# --- cached CSV fallback (downloaded by the disease-feeds worker) ------------
# this file: backend/app/services/nudges/service.py -> repo root is parents[4]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_FEED_DIR = _REPO_ROOT / "ml" / "data" / "raw" / "disease_feeds"
_RESP_CSV = _FEED_DIR / "cdc_resp_pathogens_pct_positive.csv"
_FLUVIEW_CSV = _FEED_DIR / "cdc_fluview_outpatient_resp_illness.csv"

# Words a calm health nudge must never use. Checked (case-insensitive, word
# boundary) against every nudge message in tests and before returning.
FEAR_WORDS = frozenset(
    {
        "warning",
        "danger",
        "dangerous",
        "alarm",
        "alarming",
        "alert",
        "emergency",
        "crisis",
        "surge",
        "outbreak",
        "epidemic",
        "pandemic",
        "deadly",
        "fatal",
        "severe",
        "threat",
        "panic",
        "scary",
        "terrifying",
        "spike",
        "skyrocket",
        "rampant",
        "critical",
        "urgent",
    }
)

Source = Literal["live", "cached"]

# How long a live pull stays fresh in memory.
CACHE_TTL_SECONDS = 15 * 60
_HTTP_TIMEOUT_SECONDS = 6.0

# Respiratory positivity thresholds (demo values -- percent test positivity).
# Calm, three-band read: low / moderate / rising.
_RESP_RISING_PCT = 10.0
_RESP_MODERATE_PCT = 5.0


@dataclass(frozen=True)
class Nudge:
    """One calm, single-action public-health nudge."""

    topic: Literal["respiratory", "flu", "mosquito"]
    message: str
    action: str
    as_of: str  # ISO date the underlying data is current to
    source: Source  # "live" or "cached"


@dataclass
class NudgeBundle:
    """What the /nudges endpoint returns."""

    region: str
    as_of: str
    source: Source
    nudges: list[Nudge] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# --- tiny in-memory cache ----------------------------------------------------
# key -> (expires_at_epoch, payload)
_CACHE: dict[str, tuple[float, object]] = {}


def _cache_get(key: str) -> object | None:
    hit = _CACHE.get(key)
    if hit is None:
        return None
    expires_at, payload = hit
    if time.time() >= expires_at:
        _CACHE.pop(key, None)
        return None
    return payload


def _cache_put(key: str, payload: object, ttl: float = CACHE_TTL_SECONDS) -> None:
    _CACHE[key] = (time.time() + ttl, payload)


def clear_cache() -> None:
    """Drop all cached live pulls (used by tests)."""
    _CACHE.clear()


def _socrata_headers() -> dict[str, str]:
    """Optional Socrata app token from env -- works fine without one."""
    token = os.environ.get("SOCRATA_APP_TOKEN") or os.environ.get("CDC_APP_TOKEN")
    return {"X-App-Token": token} if token else {}


# --- live fetch --------------------------------------------------------------
def _fetch_resp_positivity(client: httpx.Client) -> list[dict]:
    """Most-recent respiratory positivity rows (COVID-19 / Influenza / RSV)."""
    url = f"{SOCRATA_HOST}/resource/{CDC_RESP_PATHOGENS_ID}.json"
    params = {"$order": "week_end DESC", "$limit": "30"}
    resp = client.get(url, params=params, headers=_socrata_headers())
    resp.raise_for_status()
    return resp.json()


def _fetch_fluview_state(client: httpx.Client, state: str) -> list[dict]:
    """Most-recent ILI activity rows for one state."""
    url = f"{SOCRATA_HOST}/resource/{CDC_FLUVIEW_ID}.json"
    params = {
        "$where": f"upper(state)='{state.upper()}'",
        "$order": "week_ending DESC",
        "$limit": "5",
    }
    resp = client.get(url, params=params, headers=_socrata_headers())
    resp.raise_for_status()
    return resp.json()


def _pull_live(region_state: str, client: httpx.Client | None) -> dict:
    """Return the raw signal dict from the live API, or raise on failure."""
    owns_client = client is None
    client = client or httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS)
    try:
        resp_rows = _fetch_resp_positivity(client)
        flu_rows = _fetch_fluview_state(client, region_state)
    finally:
        if owns_client:
            client.close()
    if not resp_rows:
        raise ValueError("live respiratory feed returned no rows")
    return {"resp": resp_rows, "flu": flu_rows}


# --- cached CSV fallback -----------------------------------------------------
def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _pull_cached(region_state: str) -> dict:
    """Load the same signals from the downloaded CSVs."""
    resp_rows = _read_csv(_RESP_CSV)
    flu_rows = [
        r
        for r in _read_csv(_FLUVIEW_CSV)
        if (r.get("state") or "").strip().lower() == region_state.strip().lower()
    ]
    # Normalise key names so downstream read is identical to the live JSON.
    resp_norm = [
        {
            "week_end": r.get("week_end"),
            "pathogen": r.get("pathogen"),
            "percent_test_positivity": r.get("percent_test_positivity"),
        }
        for r in resp_rows
    ]
    return {"resp": resp_norm, "flu": flu_rows}


# --- shaping signals into nudges ---------------------------------------------
def _to_date(raw: str | None) -> date | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "")).date()
    except ValueError:
        return None


def _latest_resp(resp_rows: list[dict]) -> tuple[date | None, dict[str, float]]:
    """Latest week's pathogen -> positivity %, and that week's date."""
    dated: list[tuple[date, str, float]] = []
    for r in resp_rows:
        d = _to_date(r.get("week_end"))
        pathogen = (r.get("pathogen") or "").strip()
        try:
            pct = float(r.get("percent_test_positivity"))
        except (TypeError, ValueError):
            continue
        if d and pathogen:
            dated.append((d, pathogen, pct))
    if not dated:
        return None, {}
    latest = max(d for d, _, _ in dated)
    by_pathogen = {p: pct for d, p, pct in dated if d == latest}
    return latest, by_pathogen


def _flu_label(flu_rows: list[dict]) -> tuple[date | None, str | None]:
    """Latest ILI activity label for the state, with its week date."""
    best_d: date | None = None
    best_label: str | None = None
    for r in flu_rows:
        d = _to_date(r.get("week_ending"))
        if d and (best_d is None or d > best_d):
            best_d = d
            best_label = (r.get("activity_level_label") or "").strip() or None
    return best_d, best_label


def _in_mosquito_season(today: date) -> bool:
    """West Nile season in the Northeast runs roughly June–October."""
    return 6 <= today.month <= 10


def _shape_nudges(signals: dict, region: str, source: Source, today: date) -> NudgeBundle:
    notes: list[str] = []
    resp_date, by_pathogen = _latest_resp(signals.get("resp", []))
    flu_date, flu_label = _flu_label(signals.get("flu", []))

    as_of_date = max([d for d in (resp_date, flu_date) if d], default=None)
    as_of = as_of_date.isoformat() if as_of_date else "unknown"

    nudges: list[Nudge] = []

    # --- respiratory (national positivity trend) ---
    if by_pathogen:
        flu_pct = by_pathogen.get("Influenza", 0.0)
        rsv_pct = by_pathogen.get("RSV", 0.0)
        covid_pct = by_pathogen.get("COVID-19", 0.0)
        top = max(flu_pct, rsv_pct, covid_pct)
        resp_asof = (resp_date or as_of_date or today).isoformat()
        if top >= _RESP_RISING_PCT:
            nudges.append(
                Nudge(
                    topic="respiratory",
                    message=(
                        "Respiratory illnesses are more common in your area this week. "
                        "A good week to rest well and wash hands often."
                    ),
                    action="Wash your hands often and get a little extra rest this week.",
                    as_of=resp_asof,
                    source=source,
                )
            )
        elif top >= _RESP_MODERATE_PCT:
            nudges.append(
                Nudge(
                    topic="respiratory",
                    message=(
                        "Respiratory bugs are picking up a little as the season turns. "
                        "A good time to keep up healthy habits."
                    ),
                    action="Keep washing your hands and getting good sleep.",
                    as_of=resp_asof,
                    source=source,
                )
            )
        else:
            nudges.append(
                Nudge(
                    topic="respiratory",
                    message=(
                        "Respiratory illness levels are low right now. "
                        "A calm week to stay in your healthy routine."
                    ),
                    action="Keep up your regular sleep and hand-washing habits.",
                    as_of=resp_asof,
                    source=source,
                )
            )

        # --- flu (one gentle, timing-oriented action) ---
        flu_asof = (flu_date or resp_date or today).isoformat()
        if flu_pct >= _RESP_MODERATE_PCT or (flu_label and flu_label.lower() not in {"minimal", "low"}):
            nudges.append(
                Nudge(
                    topic="flu",
                    message=(
                        "Flu is active this season. If you have not had this year's "
                        "flu shot yet, now is a nice time to plan one."
                    ),
                    action="Book your flu shot when it suits you this week.",
                    as_of=flu_asof,
                    source=source,
                )
            )

    # --- mosquito (West Nile) -- only in season, calm prevention ---
    if _in_mosquito_season(today):
        nudges.append(
            Nudge(
                topic="mosquito",
                message=(
                    "Mosquitoes are still around this time of year. "
                    "A little prevention keeps evenings outside pleasant."
                ),
                action="Use repellent and empty standing water near your home.",
                as_of=(as_of_date or today).isoformat(),
                source=source,
            )
        )

    if not nudges:
        # Degrade to one calm generic nudge rather than returning nothing.
        nudges.append(
            Nudge(
                topic="respiratory",
                message=(
                    "A calm reminder to keep up your healthy routine this week."
                ),
                action="Get good sleep and wash your hands often.",
                as_of=as_of,
                source=source,
            )
        )
        notes.append("No specific signal available; showing a general wellness reminder.")

    # Rate limit: keep a small, most-relevant handful (respiratory, flu, mosquito
    # are already at most one each, but cap defensively).
    nudges = nudges[:3]

    return NudgeBundle(region=region, as_of=as_of, source=source, nudges=nudges, notes=notes)


# --- public entry point ------------------------------------------------------
def build_nudges(
    region: str = "Massachusetts",
    *,
    client: httpx.Client | None = None,
    today: date | None = None,
    use_cache: bool = True,
) -> NudgeBundle:
    """Build the calm nudge bundle for ``region``.

    Tries the live CDC Socrata API first (cached ~15 min); on any failure falls
    back to the cached CSVs, labelling nudges ``cached``. Never raises for a data
    problem.
    """
    today = today or datetime.now(timezone.utc).date()
    cache_key = f"signals:{region.lower()}"

    signals: dict | None = None
    source: Source = "live"
    extra_notes: list[str] = []

    if use_cache:
        cached_live = _cache_get(cache_key)
        if cached_live is not None:
            signals = cached_live  # type: ignore[assignment]

    if signals is None:
        try:
            signals = _pull_live(region, client)
            source = "live"
            if use_cache:
                _cache_put(cache_key, signals)
        except Exception as exc:  # noqa: BLE001 -- any live failure -> fallback
            signals = _pull_cached(region)
            source = "cached"
            extra_notes.append(
                f"Live CDC data was unreachable ({type(exc).__name__}); showing cached data."
            )

    bundle = _shape_nudges(signals or {}, region, source, today)
    bundle.notes = extra_notes + bundle.notes
    return bundle


__all__ = [
    "Nudge",
    "NudgeBundle",
    "build_nudges",
    "clear_cache",
    "FEAR_WORDS",
    "CACHE_TTL_SECONDS",
    "CDC_RESP_PATHOGENS_ID",
    "CDC_FLUVIEW_ID",
]
