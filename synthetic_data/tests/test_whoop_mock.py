"""WHOOP API v2 mock files mirror the CSVs and look like paginated collections."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import generate_synthetic_whoop as gen
import validate_synthetic as val


def _load(default_dir: Path, pid: str) -> dict:
    return json.loads((default_dir / gen.MOCK_DIR / f"{pid}.json").read_text(encoding="utf-8"))


def _records(payload: dict, endpoint: str) -> list[dict]:
    return [r for page in payload["endpoints"][endpoint]["pages"] for r in page["records"]]


def test_pagination_shape(default_dir: Path) -> None:
    payload = _load(default_dir, "P001")
    for endpoint in ("/v2/recovery", "/v2/activity/sleep"):
        pages = payload["endpoints"][endpoint]["pages"]
        assert len(pages) == 2  # about 29 records with a page size of 25
        assert all(set(page) == {"records", "next_token"} for page in pages)
        assert all(len(page["records"]) <= 25 for page in pages)
        assert isinstance(pages[0]["next_token"], str) and pages[-1]["next_token"] is None


def test_newest_first_and_matches_csv(default_dir: Path, dataset: val.Dataset) -> None:
    payload = _load(default_dir, "P001")
    sleeps = _records(payload, "/v2/activity/sleep")
    starts = [s["start"] for s in sleeps]
    assert starts == sorted(starts, reverse=True)
    csv = dataset.sleep[dataset.sleep["person_id"] == "P001"].sort_values("date", ascending=False)
    assert starts == list(csv["sleep_start"])
    stage = pd.DataFrame([s["score"]["stage_summary"] for s in sleeps])
    for col in stage.columns:
        assert list(stage[col]) == list(csv[col]), col


def test_v2_field_names(default_dir: Path) -> None:
    payload = _load(default_dir, "P002")
    sleep = _records(payload, "/v2/activity/sleep")[0]
    recovery = _records(payload, "/v2/recovery")[0]
    assert {"id", "cycle_id", "user_id", "start", "end", "timezone_offset", "nap", "score_state", "score"} <= set(sleep)
    assert set(sleep["score"]["stage_summary"]) == set(gen.SLEEP_COLUMNS[5:13])
    assert set(recovery["score"]) == set(gen.RECOVERY_COLUMNS[2:-1])
    assert recovery["sleep_id"] == sleep["id"]
    assert recovery["cycle_id"] == sleep["cycle_id"]


def test_null_spo2_is_json_null(default_dir: Path, dataset: val.Dataset) -> None:
    row = dataset.recovery[dataset.recovery["spo2_percentage"].isna()].iloc[0]
    payload = _load(default_dir, row["person_id"])
    match = [
        r for r, s in zip(_records(payload, "/v2/recovery"), _records(payload, "/v2/activity/sleep"))
        if s["end"].startswith(row["date"])
    ]
    assert match and match[0]["score"]["spo2_percentage"] is None


def test_profile_placeholders_have_no_real_identifiers(default_dir: Path) -> None:
    basic = _load(default_dir, "P003")["endpoints"]["/v2/user/profile/basic"]
    assert basic["email"].endswith("@example.invalid")
    assert basic["first_name"] == "Synthetic" and basic["last_name"] == "P003"
