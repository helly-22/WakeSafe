"""Synthetic demo provider (Person A). Reads synthetic_data/out/ only; never the answer key.

All people here are made up, for demos, UI work and tests. Nothing here trains or scores a model.
Fixture personas (for example the demo-only worsening person) come from the nightly CSV files
listed in DEMO_FIXTURE_FILES under fixtures/, when those files exist.
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import TypedDict

import pandas as pd

from app.models import NightRecord, ProfileInput

from .normalize import ProviderDataError, frame_to_nights

REPO_ROOT = Path(__file__).resolve().parents[4]
SYNTHETIC_DIR = REPO_ROOT / "synthetic_data" / "out"
FIXTURES_DIR = REPO_ROOT / "fixtures"
DEMO_FIXTURE_FILES = ("nights_worsening_sample.csv",)
# Demo-only people built from another synthetic person's nights reuse that person's intake answers.
DEMO_PROFILE_SOURCE = {"P901": "P019"}


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


# Made-up names for the demo people. They are random but fixed (a seeded shuffle), match the sex in
# each person's intake answers, and never depend on health condition. Every name carries "(synthetic)".
_FEMALE_NAMES = [
    "Priya", "Elena", "Grace", "Noor", "Camila", "Hannah", "Ingrid", "Leila", "Marta", "Nia", "Olivia",
    "Paloma", "Rhea", "Sofia", "Tara", "Uma", "Vera", "Wren", "Yuki", "Zoe", "Amara", "Beatrice", "Chloe",
    "Daria", "Esme", "Fatima", "Gwen", "Hana", "Isla", "Jana", "Keiko", "Lucia", "Mira", "Nadia", "Oona",
    "Petra", "Selma", "Talia",
]
_MALE_NAMES = [
    "Aarav", "Bruno", "Carlos", "Dmitri", "Elijah", "Felix", "Gabriel", "Hugo", "Ivan", "Jamal", "Kenji",
    "Liam", "Mateo", "Nikhil", "Omar", "Pavel", "Rafael", "Samuel", "Tomas", "Victor", "Wei", "Yusuf",
    "Zane", "Andre", "Benji", "Caleb", "Dev", "Emil", "Farid", "Gideon", "Hector", "Idris", "Jonas",
    "Kwame", "Lars", "Malik", "Nolan", "Oscar", "Pedro", "Quentin", "Ravi", "Stefan", "Theo", "Umar",
]
_SURNAMES = [
    "Okafor", "Lindqvist", "Moreau", "Tanaka", "Brennan", "Castillo", "Dubois", "Ellison", "Fontaine",
    "Gallagher", "Hartmann", "Ivanov", "Jensen", "Kowalski", "Lambert", "Marchetti", "Novak", "Ortega",
    "Petrov", "Quintero", "Reyes", "Santoro", "Thornton", "Underwood", "Vasquez", "Whitfield", "Xu",
    "Yamamoto", "Zielinski", "Abara", "Banerjee", "Carvalho", "Delgado", "Eriksen", "Fischer", "Grayson",
    "Holloway", "Iyer", "Jimenez", "Kaplan", "Larsen", "Mendoza", "Nakamura", "Oliveira", "Patel",
    "Quigley", "Rasmussen", "Sullivan", "Tremblay", "Ueda", "Vargas", "Walsh", "Yilmaz", "Zhang",
    "Adeyemi", "Bianchi", "Campos", "Donovan", "Esposito", "Farrell", "Gutierrez", "Haas", "Ibarra",
    "Joshi", "Kim", "Lopez", "Murphy", "Nguyen", "Park", "Ramos", "Silva", "Torres",
]


def _name_pools() -> tuple[list[str], list[str], list[str]]:
    rng = random.Random("wakesafe-demo-names")
    female, male, surnames = list(_FEMALE_NAMES), list(_MALE_NAMES), list(_SURNAMES)
    for pool in (female, male, surnames):
        rng.shuffle(pool)
    return female, male, surnames


def _display_names(ids: list[str], sex_by_id: dict[str, str]) -> dict[str, str]:
    female, male, surnames = _name_pools()
    if len(ids) > len(surnames):
        raise ValueError("More demo people than surnames; add surnames to synthetic.py.")
    counts = {"female": 0, "male": 0}
    names: dict[str, str] = {}
    for i, pid in enumerate(ids):
        sex = sex_by_id.get(pid) or ("female" if i % 2 == 0 else "male")  # unknown sex: alternate
        sex = "male" if sex.strip().lower() in {"male", "m", "man"} else "female"
        pool = male if sex == "male" else female
        first = pool[counts[sex] % len(pool)]
        counts[sex] += 1
        names[pid] = f"{first} {surnames[i]} (synthetic)"
    return names


def list_personas(*, synthetic_dir: Path = SYNTHETIC_DIR, fixtures_dir: Path = FIXTURES_DIR) -> list[PersonaInfo]:
    """Ids and made-up display names only. No cohort, label or ground truth."""
    profiles = _read("profiles.csv", synthetic_dir)
    ids = sorted(profiles["person_id"].astype(str).unique())
    ids += [p for p in sorted(_fixture_frames(fixtures_dir)) if p not in ids]
    sex_by_id = dict(zip(profiles["person_id"].astype(str), profiles["sex"].astype(str)))
    for pid, base in DEMO_PROFILE_SOURCE.items():  # demo-only people borrow their base person's sex
        if base in sex_by_id:
            sex_by_id.setdefault(pid, sex_by_id[base])
    names = _display_names(ids, sex_by_id)
    return [{"persona_id": p, "display_name": names[p]} for p in ids]


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
    row = profiles[profiles["person_id"].astype(str) == DEMO_PROFILE_SOURCE.get(persona_id, persona_id)]
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
