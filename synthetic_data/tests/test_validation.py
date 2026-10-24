"""The validation checks pass on good data and fail on deliberately broken data."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

import generate_synthetic_whoop as gen
import validate_synthetic as val


def test_auroc_basics() -> None:
    assert val.auroc(np.array([3.0, 4.0]), np.array([1.0, 2.0])) == 1.0
    assert val.auroc(np.array([1.0, 2.0]), np.array([3.0, 4.0])) == 0.0
    assert val.auroc(np.array([1.0, 1.0]), np.array([1.0, 1.0])) == 0.5
    assert np.isnan(val.auroc(np.array([]), np.array([1.0])))


def test_all_checks_pass_on_default_data(default_dir: Path) -> None:
    _, results = val.run_checks(default_dir)
    failed = [f"{r.name}: {r.detail}" for r in results if not r.passed]
    assert not failed, failed
    assert len(results) == 10


def test_cli_exit_code_zero(default_dir: Path) -> None:
    assert val.main(["--data", str(default_dir)]) == 0


def test_aurocs_in_target_band(dataset: val.Dataset, cfg: dict) -> None:
    v = cfg["validation"]
    for feat, value in val.feature_aurocs(dataset).items():
        assert v["auroc_min"] < value < v["auroc_max"], (feat, value)


def test_reconciliation_detects_broken_stages(dataset: val.Dataset) -> None:
    dataset.sleep.loc[0, "total_light_sleep_time_milli"] += 1000
    assert not val.check_reconciliation(dataset).passed


def test_reconciliation_detects_wrong_efficiency(dataset: val.Dataset) -> None:
    dataset.sleep.loc[0, "sleep_efficiency_percentage"] += 1.0
    assert not val.check_reconciliation(dataset).passed


def test_ranges_detect_out_of_range(dataset: val.Dataset, cfg: dict) -> None:
    dataset.recovery.loc[0, "spo2_percentage"] = 0.95  # a fraction instead of a percent
    assert not val.check_ranges(dataset, cfg["validation"]["ranges"]).passed


def test_overlap_fails_when_data_is_separable(dataset: val.Dataset, cfg: dict) -> None:
    _, apnea = val.screening_groups(dataset)
    rows = dataset.recovery["person_id"].isin(apnea)
    dataset.recovery.loc[rows, "spo2_percentage"] = 88.0
    result = val.check_overlap(dataset, cfg)
    assert not result.passed
    assert "unrealistically easy" in result.detail


def test_overlap_fails_when_feature_carries_no_signal(dataset: val.Dataset, cfg: dict) -> None:
    dataset.sleep["respiratory_rate"] = 15.0
    assert not val.check_overlap(dataset, cfg).passed


def test_directions_fail_when_reversed(dataset: val.Dataset) -> None:
    _, apnea = val.screening_groups(dataset)
    rows = dataset.recovery["person_id"].isin(apnea)
    dataset.recovery.loc[rows, "resting_heart_rate"] = 40
    assert not val.check_directions(dataset).passed


def test_labels_fail_without_header_or_flag(dataset: val.Dataset) -> None:
    dataset.headers["sleep.csv"] = "person_id,date"
    assert not val.check_labels(dataset).passed


def test_labels_fail_when_ground_truth_is_merged(dataset: val.Dataset) -> None:
    gt = dataset.ground_truth[["person_id", "true_condition"]]
    dataset.tables["profiles.csv"] = dataset.profiles.merge(gt, on="person_id")
    assert not val.check_labels(dataset).passed


@pytest.fixture()
def copied_dir(default_dir: Path, tmp_path: Path) -> Path:
    target = tmp_path / "copy"
    shutil.copytree(default_dir, target)
    return target


def test_reproducibility_detects_edited_file(copied_dir: Path) -> None:
    path = copied_dir / "sleep.csv"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    lines[2] = lines[2].replace("False", "False ", 1)
    path.write_text("".join(lines), encoding="utf-8")
    ds = val.load_dataset(copied_dir)
    assert not val.check_reproducibility(ds, gen.DEFAULT_CONFIG_PATH).passed


def test_mock_check_detects_missing_records(copied_dir: Path, cfg: dict) -> None:
    path = copied_dir / gen.MOCK_DIR / "P001.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["endpoints"]["/v2/activity/sleep"]["pages"][0]["records"].pop()
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert not val.check_mock(val.load_dataset(copied_dir), cfg).passed


def test_summary_table_has_every_cohort(dataset: val.Dataset) -> None:
    table = val.summary_table(dataset)
    assert list(table.index) == val.COHORT_ORDER
    assert table["n"].sum() == len(dataset.profiles)
