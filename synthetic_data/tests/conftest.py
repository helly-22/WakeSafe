"""Shared fixtures. Synthetic data. Not clinical. Do not use to estimate model accuracy."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generate_synthetic_whoop as gen  # noqa: E402
import validate_synthetic as val  # noqa: E402


@pytest.fixture(scope="session")
def default_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Default CLI settings (seed 42, 30 nights, default cohort sizes) in a temp folder."""
    out = tmp_path_factory.mktemp("default")
    gen.generate(out)
    return out


@pytest.fixture()
def dataset(default_dir: Path) -> val.Dataset:
    """A fresh copy of the default tables so tests may mutate them."""
    return val.load_dataset(default_dir)


@pytest.fixture(scope="session")
def cfg() -> dict:
    """Parsed persona config."""
    return gen.load_config()
