"""Tests for the data providers in app.services.whoop (synthetic, CSV, live stub)."""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))  # backend/, so `app` is importable

from app.models import NightRecord, ProfileInput
from app.services.whoop import ProviderDataError, list_personas, load_nights, load_synthetic_profile
from app.services.whoop.csv_upload import MAX_CSV_BYTES
from app.services.whoop.normalize import MAX_NIGHTS
from app.services.whoop.synthetic import load_synthetic_nights

OUT = REPO / "synthetic_data" / "out"
SAMPLE = REPO / "fixtures" / "nights_sample.csv"


def raw_frame(person: str) -> pd.DataFrame:
    sleep = pd.read_csv(OUT / "sleep.csv", comment="#")
    recovery = pd.read_csv(OUT / "recovery.csv", comment="#").drop(columns=["is_synthetic"])
    merged = sleep.merge(recovery, on=["person_id", "date"])
    return merged[merged["person_id"] == person].reset_index(drop=True)


def write_csv(tmp_path: Path, df: pd.DataFrame, name: str = "nights.csv", header: str = "") -> str:
    path = tmp_path / name
    path.write_text(header + df.to_csv(index=False))
    return str(path)


# synthetic provider


@pytest.mark.parametrize("pid", ["P001", "P002"])
def test_synthetic_nights_are_valid_mapped_and_ordered(pid):
    nights = load_nights("synthetic", persona_id=pid)
    raw = raw_frame(pid)
    kept = raw[~raw["user_calibrating"]]
    assert len(nights) == len(kept) and 15 < len(nights) < 31
    for n in nights:
        NightRecord.model_validate(n.model_dump())
        assert n.source == "synthetic" and n.night_id.startswith(pid)
    assert [n.date for n in nights] == sorted(n.date for n in nights)
    assert len({n.night_id for n in nights}) == len(nights)
    first, row = nights[0], kept.iloc[0]
    assert first.resting_heart_rate_bpm == row["resting_heart_rate"]
    assert first.hrv_rmssd_ms == row["hrv_rmssd_milli"]
    assert first.respiratory_rate_rpm == row["respiratory_rate"]
    assert first.sleep_efficiency_pct == pytest.approx(row["sleep_efficiency_percentage"])
    stages = row["total_light_sleep_time_milli"] + row["total_slow_wave_sleep_time_milli"] + row["total_rem_sleep_time_milli"]
    assert first.sleep_duration_minutes == pytest.approx(stages / 60000)
    assert first.deep_sleep_minutes == pytest.approx(row["total_slow_wave_sleep_time_milli"] / 60000)
    assert 200 < first.sleep_duration_minutes < 700  # minutes, not milliseconds


def test_calibrating_nights_are_dropped_and_missing_spo2_stays_missing():
    total_missing = 0
    for pid in ("P001", "P005", "P010", "P020"):
        raw = raw_frame(pid)
        nights = load_nights("synthetic", persona_id=pid)
        assert len(nights) == int((~raw["user_calibrating"]).sum())
        expected_missing = int(raw[~raw["user_calibrating"]]["spo2_percentage"].isna().sum())
        assert sum(n.spo2_pct is None for n in nights) == expected_missing
        assert all(n.spo2_pct != 0 for n in nights)
        total_missing += expected_missing
    assert total_missing > 0  # at least one of these people has a night without SpO2


def test_default_call_works_offline_and_picks_first_person():
    nights = load_nights()
    assert nights and nights[0].night_id.startswith(list_personas()[0]["persona_id"])


def test_unknown_persona_and_unknown_source_give_clear_errors():
    with pytest.raises(ProviderDataError, match="Unknown demo person 'X999'"):
        load_nights("synthetic", persona_id="X999")
    with pytest.raises(ProviderDataError, match="Unknown data source"):
        load_nights("fitbit")  # type: ignore[arg-type]


def test_list_personas_exposes_only_ids_and_neutral_names():
    personas = list_personas()
    assert len(personas) == 65
    for p in personas:
        assert set(p) == {"persona_id", "display_name"}
        assert re.fullmatch(r"Demo person P\d{3}", p["display_name"])
    text = " ".join(map(str, personas)).lower()
    for word in ("osa", "apnea", "healthy", "severe", "condition", "cohort", "difficulty", "ahi"):
        assert word not in text


def test_synthetic_profile_builds_a_profile_input():
    prof = load_synthetic_profile("P001")
    assert isinstance(prof, ProfileInput)
    assert prof.age == 60 and prof.sex == "male" and prof.height_cm == 175.0
    assert prof.conditions == [] and prof.red_flag_symptoms == [] and prof.hypertension is False
    with_conditions = [load_synthetic_profile(p["persona_id"]) for p in list_personas()]
    assert any(p.conditions for p in with_conditions) and any(p.red_flag_symptoms for p in with_conditions)
    with pytest.raises(ProviderDataError):
        load_synthetic_profile("X999")


def test_fixture_persona_is_listed_and_loadable_from_a_fixtures_folder(tmp_path):
    sample = pd.read_csv(SAMPLE, comment="#")
    worsening = sample[sample["person_id"] == "P001"].copy()
    worsening["person_id"] = "W900"
    write_csv(tmp_path, worsening, "nights_worsening_sample.csv", header="# SYNTHETIC DATA\n")
    ids = [p["persona_id"] for p in list_personas(fixtures_dir=tmp_path)]
    assert ids[-1] == "W900" and len(ids) == 66
    nights = load_synthetic_nights("W900", fixtures_dir=tmp_path)
    assert len(nights) == 14 and all(n.source == "synthetic" for n in nights)


def test_real_worsening_fixture_is_listed_when_the_file_exists():
    path = REPO / "fixtures" / "nights_worsening_sample.csv"
    if not path.exists():
        pytest.skip("fixtures/nights_worsening_sample.csv has not been added yet")
    ids = {p["persona_id"] for p in list_personas()}
    assert set(pd.read_csv(path, comment="#")["person_id"].astype(str)) <= ids


# CSV provider


def test_csv_round_trip_matches_the_synthetic_provider(tmp_path):
    path = write_csv(tmp_path, raw_frame("P002"), header="# SYNTHETIC DATA. test header\n")
    from_csv = load_nights("csv", csv_file=path)
    from_synth = load_nights("synthetic", persona_id="P002")
    assert len(from_csv) == len(from_synth)
    assert all(n.source == "csv" for n in from_csv)
    for a, b in zip(from_csv, from_synth):
        assert a.model_dump(exclude={"source"}) == b.model_dump(exclude={"source"})


def test_csv_text_is_accepted_and_nothing_is_left_on_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    text = raw_frame("P002").to_csv(index=False)
    assert len(load_nights("csv", csv_file=text)) > 15
    assert list(tmp_path.iterdir()) == []


def test_minimal_csv_with_missing_values_stays_missing(tmp_path):
    path = tmp_path / "min.csv"
    path.write_text("date,spo2_percentage,resting_heart_rate\n2026-01-02,,58\n2026-01-01,96.5,\n")
    nights = load_nights("csv", csv_file=str(path))
    assert [n.date.isoformat() for n in nights] == ["2026-01-01", "2026-01-02"]
    assert nights[0].spo2_pct == 96.5 and nights[0].resting_heart_rate_bpm is None
    assert nights[1].spo2_pct is None and nights[1].hrv_rmssd_ms is None


@pytest.mark.parametrize(
    "content, fragment",
    [
        ("resting_heart_rate\n58\n", "needs a 'date' column"),
        ("date,notes\n2026-01-01,hello\n", "none of the sleep or recovery columns"),
        ("date,resting_heart_rate\n2026-01-01,58\nnot-a-date,59\n", "Row 2: 'date' is not a valid date"),
        ("date,resting_heart_rate\n2026-01-01,58\n2026-01-02,SECRETVALUE\n", "Row 2: 'resting_heart_rate' must be a number"),
        ("date,resting_heart_rate\n2026-01-01,-5\n", "cannot be negative"),
        ("date,spo2_percentage\n2026-01-01,101\n", "cannot be above 100"),
        ("date,resting_heart_rate\n2026-01-01,58\n2026-01-01,59\n", "more than one row for the same date"),
        ("date,person_id,resting_heart_rate\n2026-01-01,A,58\n2026-01-02,B,59\n", "2 different people"),
        ("date,resting_heart_rate\n", "no rows"),
    ],
)
def test_bad_csv_gives_clear_errors_without_echoing_values(tmp_path, caplog, content, fragment):
    path = tmp_path / "bad.csv"
    path.write_text(content)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ProviderDataError) as err:
            load_nights("csv", csv_file=str(path))
    assert fragment in str(err.value)
    assert "SECRETVALUE" not in str(err.value) and "SECRETVALUE" not in caplog.text


def test_missing_oversized_and_too_long_files_are_rejected(tmp_path):
    with pytest.raises(ProviderDataError, match="No CSV file"):
        load_nights("csv")
    with pytest.raises(ProviderDataError, match="could not be found"):
        load_nights("csv", csv_file=str(tmp_path / "nope.csv"))
    big = tmp_path / "big.csv"
    big.write_text("date,resting_heart_rate\n" + "2026-01-01,58\n" * (MAX_CSV_BYTES // 13 + 10))
    with pytest.raises(ProviderDataError, match="larger than"):
        load_nights("csv", csv_file=str(big))
    many = pd.DataFrame({"date": pd.date_range("2020-01-01", periods=MAX_NIGHTS + 1), "resting_heart_rate": 58})
    with pytest.raises(ProviderDataError, match="the limit is"):
        load_nights("csv", csv_file=write_csv(tmp_path, many, "many.csv"))


def test_csv_calibrating_and_nap_rows_are_dropped(tmp_path):
    path = tmp_path / "flags.csv"
    path.write_text(
        "date,resting_heart_rate,user_calibrating,nap\n2026-01-01,58,True,False\n2026-01-02,59,False,True\n2026-01-03,60,False,False\n"
    )
    nights = load_nights("csv", csv_file=str(path))
    assert [n.resting_heart_rate_bpm for n in nights] == [60.0]


# live WHOOP and ground truth


def test_live_whoop_fails_clearly_without_credentials():
    with pytest.raises(NotImplementedError, match="OAuth credentials"):
        load_nights("whoop")


def test_no_backend_code_reads_the_answer_key():
    offenders = [p for p in (BACKEND / "app").rglob("*.py") if "ground_truth" in p.read_text()]
    assert offenders == []
