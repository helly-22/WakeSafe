"""Synthetic labeling, ground-truth separation, safety wording, and cohort structure."""

from __future__ import annotations

import json
import re
from pathlib import Path

import generate_synthetic_whoop as gen
import validate_synthetic as val

FORBIDDEN = re.compile(r"diagnos|you have", re.IGNORECASE)


def test_csv_header_comment_and_flag(default_dir: Path, dataset: val.Dataset) -> None:
    for name in gen.OUTPUT_CSVS:
        first = (default_dir / name).read_text(encoding="utf-8").splitlines()[0]
        assert first.startswith("# SYNTHETIC DATA"), name
        assert dataset.tables[name]["is_synthetic"].astype(bool).all(), name


def test_json_files_flagged(default_dir: Path, dataset: val.Dataset) -> None:
    files = sorted((default_dir / gen.MOCK_DIR).glob("*.json"))
    assert len(files) == len(dataset.profiles)
    for path in files:
        assert json.loads(path.read_text(encoding="utf-8"))["synthetic"] is True


def test_ground_truth_is_separate(dataset: val.Dataset) -> None:
    for name in ("profiles.csv", "recovery.csv", "sleep.csv"):
        assert not val.GROUND_TRUTH_ONLY & set(dataset.tables[name].columns), name


def test_ids_are_placeholders_and_shuffled(dataset: val.Dataset) -> None:
    ids = dataset.profiles["person_id"]
    assert ids.str.fullmatch(r"P\d{3}").all()
    assert list(ids) == [f"P{i:03d}" for i in range(1, len(ids) + 1)]
    first_conditions = dataset.ground_truth["true_condition"].head(25)
    assert first_conditions.nunique() > 1  # ids do not reveal cohort order


def test_notes_use_screening_language(dataset: val.Dataset) -> None:
    for note in dataset.ground_truth["notes"]:
        assert not FORBIDDEN.search(str(note)), note


def test_cohort_counts(dataset: val.Dataset) -> None:
    cohorts = val.cohort_labels(dataset.ground_truth).value_counts()
    assert cohorts["healthy"] == 25
    assert cohorts["hard_negative"] == 6
    assert cohorts["hard_positive"] == 6
    assert cohorts[["osa_mild", "osa_moderate", "osa_severe"]].sum() == 20
    assert cohorts[["cardiovascular_strain", "respiratory_flare", "acute_illness", "urgent"]].sum() == 8


def test_ahi_matches_severity(dataset: val.Dataset) -> None:
    gt = dataset.ground_truth
    osa = gt[gt["true_condition"].str.startswith("osa_")]
    assert osa["simulated_ahi"].notna().all()
    assert gt.loc[~gt.index.isin(osa.index), "simulated_ahi"].isna().all()
    bounds = {"osa_mild": (5, 14), "osa_moderate": (15, 29.99), "osa_severe": (30, 200)}
    for cond, (lo, hi) in bounds.items():
        assert osa.loc[osa["true_condition"] == cond, "simulated_ahi"].between(lo, hi).all(), cond


def test_hard_positives_profile(dataset: val.Dataset) -> None:
    cohorts = val.cohort_labels(dataset.ground_truth)
    hp = dataset.profiles.set_index("person_id").loc[cohorts.index[cohorts == "hard_positive"]]
    assert not hp["snoring"].any()
    assert not hp["witnessed_breathing_pauses"].any()
    assert (hp["bmi"] < 34).all()


def test_red_flags_only_for_urgent(dataset: val.Dataset) -> None:
    cohorts = val.cohort_labels(dataset.ground_truth)
    flags = dataset.profiles.set_index("person_id")["red_flag_symptoms"].fillna("")
    allowed = {"chest_pain", "fainting", "severe_shortness_of_breath", "stroke_symptoms"}
    for pid, value in flags.items():
        if cohorts[pid] == "urgent":
            assert value and set(value.split(";")) <= allowed, pid
        else:
            assert value == "", pid


def test_condition_histories(dataset: val.Dataset) -> None:
    cohorts = val.cohort_labels(dataset.ground_truth)
    cond = dataset.profiles.set_index("person_id")["conditions"].fillna("")
    for pid in cohorts.index[cohorts == "cardiovascular_strain"]:
        assert {"hypertension", "atrial_fibrillation"} & set(cond[pid].split(";")), pid
    for pid in cohorts.index[cohorts == "respiratory_flare"]:
        assert {"asthma", "copd"} & set(cond[pid].split(";")), pid


def test_osa_profiles_skew_as_intended(dataset: val.Dataset) -> None:
    cohorts = val.cohort_labels(dataset.ground_truth)
    p = dataset.profiles.set_index("person_id")
    healthy = p.loc[cohorts.index[cohorts == "healthy"]]
    osa = p.loc[cohorts.index[cohorts.isin(["osa_mild", "osa_moderate", "osa_severe"])]]
    assert osa["bmi"].mean() > healthy["bmi"].mean()
    assert osa["neck_circumference_cm"].mean() > healthy["neck_circumference_cm"].mean()
    assert osa["snoring"].mean() > healthy["snoring"].mean()
    assert not osa["snoring"].all()  # correlated, never guaranteed
