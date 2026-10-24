"""Targeted tests for the on-demand /nudges service and route.

Covered:
  * a MOCKED live Socrata response -> live nudges with an honest as-of stamp
  * a MOCKED fetch failure -> cached-CSV fallback, labelled ``cached``
  * tone guarantees: no fear words, exactly one positive action per nudge,
    and the set is rate-limited (small)
  * the GET /nudges route is wired and returns the contract shape
"""
from __future__ import annotations

import re
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import nudges as nudge_pkg
from app.services.nudges import service as nudge_service
from app.services.nudges.service import FEAR_WORDS, build_nudges, clear_cache

client = TestClient(app)


# --- fixtures: a fake live Socrata response ----------------------------------
_LIVE_RESP_ROWS = [
    {"week_end": "2026-10-17T00:00:00.000", "pathogen": "Influenza", "percent_test_positivity": "12.4"},
    {"week_end": "2026-10-17T00:00:00.000", "pathogen": "RSV", "percent_test_positivity": "6.1"},
    {"week_end": "2026-10-17T00:00:00.000", "pathogen": "COVID-19", "percent_test_positivity": "4.0"},
    # an older week, to prove we take the latest
    {"week_end": "2026-10-10T00:00:00.000", "pathogen": "Influenza", "percent_test_positivity": "9.0"},
]
_LIVE_FLU_ROWS = [
    {
        "week_ending": "2026-10-17T00:00:00.000",
        "season": "2026-2027",
        "state": "Massachusetts",
        "activity_level": "Level 6",
        "activity_level_label": "High",
    }
]


def _live_handler(request: httpx.Request) -> httpx.Response:
    """MockTransport handler: route by Socrata dataset id in the path."""
    if nudge_service.CDC_RESP_PATHOGENS_ID in request.url.path:
        return httpx.Response(200, json=_LIVE_RESP_ROWS)
    if nudge_service.CDC_FLUVIEW_ID in request.url.path:
        return httpx.Response(200, json=_LIVE_FLU_ROWS)
    return httpx.Response(404, json=[])


def _mock_live_client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(_live_handler))


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


def _fear_hits(text: str) -> list[str]:
    low = text.lower()
    return [w for w in FEAR_WORDS if re.search(rf"\b{re.escape(w)}\b", low)]


# --- live path ---------------------------------------------------------------
def test_live_fetch_builds_live_nudges_with_as_of():
    with _mock_live_client() as c:
        bundle = build_nudges(
            "Massachusetts", client=c, today=date(2026, 10, 24), use_cache=False
        )

    assert bundle.source == "live"
    assert bundle.as_of == "2026-10-17"  # honest stamp from the latest week
    assert bundle.nudges, "expected at least one nudge"
    assert all(n.source == "live" for n in bundle.nudges)

    topics = {n.topic for n in bundle.nudges}
    assert "respiratory" in topics
    assert "flu" in topics  # flu 12.4% + "High" label -> a flu nudge fires


# --- cached fallback path ----------------------------------------------------
def test_fetch_failure_falls_back_to_cached_labeled(tmp_path, monkeypatch):
    # The real cache lives in ml/data/raw/ (gitignored), so give the service a small one of its own.
    resp_csv = tmp_path / "resp.csv"
    resp_csv.write_text(
        "week_end,pathogen,percent_test_positivity\n"
        "2026-10-10T00:00:00.000,Influenza,3.0\n"
        "2026-10-17T00:00:00.000,Influenza,3.5\n"
        "2026-10-17T00:00:00.000,RSV,2.0\n"
    )
    flu_csv = tmp_path / "flu.csv"
    flu_csv.write_text(
        "week_ending,state,activity_level_label\n"
        "2026-10-17T00:00:00.000,Massachusetts,Minimal\n"
    )
    monkeypatch.setattr(nudge_service, "_RESP_CSV", resp_csv)
    monkeypatch.setattr(nudge_service, "_FLUVIEW_CSV", flu_csv)

    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated live outage")

    failing = httpx.Client(transport=httpx.MockTransport(_boom))
    with failing as c:
        bundle = build_nudges(
            "Massachusetts", client=c, today=date(2026, 10, 24), use_cache=False
        )

    assert bundle.source == "cached"
    assert bundle.nudges
    assert all(n.source == "cached" for n in bundle.nudges)
    # the fallback must say, honestly, that it is cached
    assert any("cached" in note.lower() for note in bundle.notes)
    # an honest as-of date still comes through from the cached CSV
    assert bundle.as_of == "2026-10-17"


# --- tone guarantees ---------------------------------------------------------
def test_nudges_have_no_fear_words_and_one_action():
    with _mock_live_client() as c:
        bundle = build_nudges(
            "Massachusetts", client=c, today=date(2026, 10, 24), use_cache=False
        )

    assert bundle.nudges
    for n in bundle.nudges:
        hits = _fear_hits(n.message) + _fear_hits(n.action)
        assert not hits, f"fear word(s) {hits} in nudge: {n.message!r} / {n.action!r}"
        # exactly one positive action: a single, non-empty action string with
        # no " and then " / numbered multi-step phrasing.
        assert n.action.strip()
        assert " then " not in n.action.lower()
        assert ";" not in n.action
        assert n.as_of  # every nudge is stamped


def test_nudges_are_rate_limited_small_set():
    with _mock_live_client() as c:
        bundle = build_nudges(
            "Massachusetts", client=c, today=date(2026, 10, 24), use_cache=False
        )
    # calm product: a small, most-relevant handful, never a flood
    assert 1 <= len(bundle.nudges) <= 3
    # at most one nudge per topic (no spamming the same topic)
    topics = [n.topic for n in bundle.nudges]
    assert len(topics) == len(set(topics))


def test_offseason_has_no_mosquito_nudge():
    with _mock_live_client() as c:
        bundle = build_nudges(
            "Massachusetts", client=c, today=date(2026, 1, 15), use_cache=False
        )
    assert "mosquito" not in {n.topic for n in bundle.nudges}


# --- route wiring ------------------------------------------------------------
def test_nudges_route_returns_calm_bundle():
    """The live route may reach the real API or fall back to cached -- either
    way it must return a valid, calm, stamped bundle and never 500."""
    resp = client.get("/nudges")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["region"] == "Massachusetts"
    assert body["source"] in {"live", "cached"}
    assert body["as_of"]
    assert 1 <= len(body["nudges"]) <= 3
    for n in body["nudges"]:
        assert n["topic"] in {"respiratory", "flu", "mosquito"}
        assert n["source"] in {"live", "cached"}
        assert n["as_of"]
        hits = _fear_hits(n["message"]) + _fear_hits(n["action"])
        assert not hits, f"fear word(s) {hits} in route nudge: {n}"


def test_nudges_route_accepts_region_param():
    resp = client.get("/nudges", params={"region": "Vermont"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["region"] == "Vermont"
