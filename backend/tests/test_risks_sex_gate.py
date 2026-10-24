"""The menopause risk is not applied to a male profile."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))  # backend/, so `app` is importable

from app.api.pipeline import run_screen
from app.models import ProfileInput
from app.services.whoop import load_nights, load_synthetic_profile


def menopause_item(profile: ProfileInput, nights):
    _, _, assessment = run_screen(profile, nights)
    return next(r for r in assessment.risks if r.risk_id == "menopause")


@pytest.fixture(scope="module")
def worsening():
    # P901's nights make the menopause rule fire when nothing stops it (sleep efficiency far below baseline).
    return load_synthetic_profile("P901"), load_nights("synthetic", persona_id="P901")


def test_male_profile_gets_no_menopause_risk(worsening):
    profile, nights = worsening
    for sex in ("male", "Male", "M", " man "):
        item = menopause_item(profile.model_copy(update={"sex": sex}), nights)
        assert item.tier == "Low" and item.reasons == ["Not applicable: menopause screening is not applied to a male profile."]
        assert item.source_labels == ["patient_reported"]


def test_a_reported_menopause_condition_does_not_override_the_gate(worsening):
    profile, nights = worsening
    item = menopause_item(profile.model_copy(update={"sex": "male", "conditions": ["perimenopause"]}), nights)
    assert item.tier == "Low" and "Not applicable" in item.reasons[0]


@pytest.mark.parametrize("sex", ["female", "F", None, "nonbinary"])
def test_other_and_unknown_sex_answers_are_scored_as_before(worsening, sex):
    profile, nights = worsening
    item = menopause_item(profile.model_copy(update={"sex": sex}), nights)
    assert item.tier == "Moderate"  # the same result this person had before the gate was added
    assert not any("Not applicable" in r for r in item.reasons)


def test_other_risks_are_unchanged_by_the_gate(worsening):
    profile, nights = worsening
    male = run_screen(profile.model_copy(update={"sex": "male"}), nights)[2]
    female = run_screen(profile.model_copy(update={"sex": "female"}), nights)[2]
    keep = lambda a: [(r.risk_id, r.tier, r.reasons) for r in a.risks if r.risk_id != "menopause"]
    assert keep(male) == keep(female)


def test_the_menopause_demo_scenario_still_fires():
    from app.api.demo import load_demo

    _, profile, nights = load_demo("MENOPAUSE")
    assert profile.sex is None
    _, _, assessment = run_screen(profile, nights)
    assert next(r for r in assessment.risks if r.risk_id == "menopause").tier != "Low"
