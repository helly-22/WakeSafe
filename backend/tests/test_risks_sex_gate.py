"""The menopause risk is not applied to a male profile.

CONTRACT (decided at the main-merge): a clearly-male profile has NO menopause
question to answer, so the menopause risk is EXCLUDED from the result entirely --
there is no `menopause` row at all (not a zeroed "Not applicable" Low row). This
matches the travel/menopause fixes (test_travel_menopause_fixes.py). Female and
unknown/None/other sex answers still EVALUATE the group (a row is present and is
scored by the cycle-disruption gate, exactly as before the sex gate was added).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))  # backend/, so `app` is importable

from app.api.pipeline import run_screen
from app.models import ProfileInput
from app.services.whoop import load_nights, load_synthetic_profile


def menopause_item(profile: ProfileInput, nights, flags=None):
    """Return the menopause risk row, or None when it is excluded."""
    _, _, assessment = run_screen(profile, nights, flags)
    return next((r for r in assessment.risks if r.risk_id == "menopause"), None)


@pytest.fixture(scope="module")
def worsening():
    # P901's nights make the menopause rule reach the engine (sleep efficiency far below baseline).
    return load_synthetic_profile("P901"), load_nights("synthetic", persona_id="P901")


def test_male_profile_gets_no_menopause_risk(worsening):
    profile, nights = worsening
    for sex in ("male", "Male", "M", " man "):
        assert menopause_item(profile.model_copy(update={"sex": sex}), nights) is None, sex


def test_a_reported_menopause_condition_does_not_override_the_gate(worsening):
    profile, nights = worsening
    item = menopause_item(
        profile.model_copy(update={"sex": "male", "conditions": ["perimenopause"]}), nights
    )
    assert item is None


@pytest.mark.parametrize("sex", ["female", "F", None, "nonbinary"])
def test_other_and_unknown_sex_answers_are_evaluated_not_excluded(worsening, sex):
    # Non-male answers EVALUATE the group: a menopause row is present (not excluded),
    # and it is scored by the cycle-disruption gate rather than suppressed by sex.
    profile, nights = worsening
    item = menopause_item(profile.model_copy(update={"sex": sex}), nights)
    assert item is not None, sex
    assert not any("not applied to a male profile" in r for r in item.reasons)


def test_other_risks_are_unchanged_by_the_gate(worsening):
    profile, nights = worsening
    male = run_screen(profile.model_copy(update={"sex": "male"}), nights)[2]
    female = run_screen(profile.model_copy(update={"sex": "female"}), nights)[2]
    # Sleep-disordered breathing is left out on purpose: STOP-Bang gives male sex a point, so it can differ.
    skip = {"menopause", "sleep_disordered_breathing"}
    keep = lambda a: [(r.risk_id, r.tier, r.reasons) for r in a.risks if r.risk_id not in skip]
    assert keep(male) == keep(female)


def test_the_menopause_demo_scenario_still_fires():
    from app.api.demo import load_demo

    # Our load_demo returns (canonical, profile, nights, quality_flags). The
    # MENOPAUSE demo carries a cycle-disruption flag and a female profile.
    _, profile, nights, flags = load_demo("MENOPAUSE")
    _, _, assessment = run_screen(profile, nights, flags)
    meno = next((r for r in assessment.risks if r.risk_id == "menopause"), None)
    assert meno is not None and meno.tier != "Low"


def test_a_female_profile_with_a_cycle_signal_fires():
    # The positive case for our contract: female + an explicit cycle-disruption
    # marker reaches Moderate/High on the worsening nights (sex gate lets it
    # through, cycle gate is satisfied).
    profile, nights = load_synthetic_profile("P901"), load_nights("synthetic", persona_id="P901")
    item = menopause_item(
        profile.model_copy(update={"sex": "female"}), nights, flags=["cycle:irregular"]
    )
    assert item is not None and item.tier in ("Moderate", "High"), item.tier
