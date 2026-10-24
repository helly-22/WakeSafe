"""Synthetic demo provider (Person A). Reads synthetic_data/out/ only; never the answer key.

All people here are made up, for demos, UI work and tests. Nothing here trains or scores a model.
Fixture personas (for example the demo-only worsening person) come from the nightly CSV files
listed in DEMO_FIXTURE_FILES under fixtures/, when those files exist.
"""
from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import pandas as pd

from app.models import NightRecord, ProfileInput

from .normalize import ProviderDataError, frame_to_nights

REPO_ROOT = Path(__file__).resolve().parents[4]
SYNTHETIC_DIR = REPO_ROOT / "synthetic_data" / "out"
FIXTURES_DIR = REPO_ROOT / "fixtures"
DEMO_FIXTURE_FILES = ("nights_worsening_sample.csv",)


class PersonaInfo(TypedDict):
    persona_id: str
    display_name: str


def _read(name: str, directory: Path) -> pd.DataFrame:
    return pd.read_csv(directory / name, comment="#")


def _fixture_frames(fixtures_dir: Path) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for name in DEMO_FIXTURE_FILES:
        path = fixtures_dir / name
        if not path.is_file():
            continue
        df = pd.read_csv(path, comment="#")
        if "person_id" in df.columns:
            for pid, rows in df.groupby("person_id"):
                frames[str(pid)] = rows.reset_index(drop=True)
    return frames


def _synthetic_frame(directory: Path) -> pd.DataFrame:
    sleep = _read("sleep.csv", directory)
    recovery = _read("recovery.csv", directory).drop(columns=["is_synthetic"], errors="ignore")
    return sleep.merge(recovery, on=["person_id", "date"], how="left")


def list_personas(*, synthetic_dir: Path = SYNTHETIC_DIR, fixtures_dir: Path = FIXTURES_DIR) -> list[PersonaInfo]:
    """Ids and neutral display names only. No cohort, label or ground truth."""
    ids = sorted(_read("profiles.csv", synthetic_dir)["person_id"].astype(str).unique())
    ids += [p for p in sorted(_fixture_frames(fixtures_dir)) if p not in ids]
    return [{"persona_id": p, "display_name": f"Demo person {p}"} for p in ids]


def load_synthetic_nights(
    persona_id: str | None = None, *, synthetic_dir: Path = SYNTHETIC_DIR, fixtures_dir: Path = FIXTURES_DIR
) -> list[NightRecord]:
    """Nights for one synthetic person, calibrating nights dropped. No persona_id means the first listed person."""
    personas = [p["persona_id"] for p in list_personas(synthetic_dir=synthetic_dir, fixtures_dir=fixtures_dir)]
    pid = persona_id or personas[0]
    if pid not in personas:
        raise ProviderDataError(f"Unknown demo person '{pid}'. Available ids: {', '.join(personas)}.")
    fixtures = _fixture_frames(fixtures_dir)
    if pid in fixtures:
        df = fixtures[pid]
    else:
        merged = _synthetic_frame(synthetic_dir)
        df = merged[merged["person_id"] == pid]
    return frame_to_nights(df, "synthetic")


def _split(value: object) -> list[str]:
    return [] if pd.isna(value) or not str(value).strip() else [p.strip() for p in str(value).split(";") if p.strip()]


def load_synthetic_profile(persona_id: str, *, synthetic_dir: Path = SYNTHETIC_DIR) -> ProfileInput:
    """The made-up intake answers for one demo person, so the UI can run a full demo from one id."""
    profiles = _read("profiles.csv", synthetic_dir)
    row = profiles[profiles["person_id"].astype(str) == persona_id]
    if row.empty:
        raise ProviderDataError(f"No demo profile for '{persona_id}'.")
    r = row.iloc[0]
    return ProfileInput(
        age=int(r["age"]),
        sex=str(r["sex"]),
        height_cm=round(float(r["height_m"]) * 100, 1),
        weight_kg=float(r["weight_kg"]),
        neck_circumference_cm=float(r["neck_circumference_cm"]),
        conditions=_split(r["conditions"]),
        snoring=bool(r["snoring"]),
        daytime_tiredness=bool(r["daytime_tiredness"]),
        witnessed_breathing_pauses=bool(r["witnessed_breathing_pauses"]),
        hypertension=bool(r["hypertension"]),
        red_flag_symptoms=_split(r["red_flag_symptoms"]),
    )
