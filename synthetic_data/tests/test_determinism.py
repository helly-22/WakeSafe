"""Determinism: same seed gives byte-identical files; a different seed does not."""

from __future__ import annotations

import filecmp
from pathlib import Path

import generate_synthetic_whoop as gen

SMALL = gen.Counts(n_healthy=5, n_osa=4, n_hard_negative=2, n_hard_positive=2, n_other=4)


def _all_files(root: Path) -> list[Path]:
    return sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file())


def test_same_seed_byte_identical(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    gen.generate(a, seed=7, nights=14, counts=SMALL)
    gen.generate(b, seed=7, nights=14, counts=SMALL)
    files = _all_files(a)
    assert files == _all_files(b)
    assert len(files) == 4 + SMALL.total()
    for rel in files:
        assert filecmp.cmp(a / rel, b / rel, shallow=False), rel


def test_different_seed_differs(tmp_path: Path) -> None:
    gen.generate(tmp_path / "a", seed=7, nights=14, counts=SMALL)
    gen.generate(tmp_path / "b", seed=8, nights=14, counts=SMALL)
    assert (tmp_path / "a" / "sleep.csv").read_bytes() != (tmp_path / "b" / "sleep.csv").read_bytes()


def test_default_output_matches_fresh_run(default_dir: Path, tmp_path: Path) -> None:
    gen.generate(tmp_path)
    for rel in _all_files(default_dir):
        assert filecmp.cmp(default_dir / rel, tmp_path / rel, shallow=False), rel


def test_rerun_into_same_folder_removes_stale_mock_files(tmp_path: Path) -> None:
    gen.generate(tmp_path, seed=1, nights=7, counts=SMALL)
    smaller = gen.Counts(n_healthy=2, n_osa=1, n_hard_negative=1, n_hard_positive=1, n_other=1)
    gen.generate(tmp_path, seed=1, nights=7, counts=smaller)
    assert len(list((tmp_path / gen.MOCK_DIR).glob("*.json"))) == smaller.total()


def test_cli_matches_library(tmp_path: Path) -> None:
    gen.main(["--seed", "3", "--nights", "10", "--n-healthy", "3", "--n-osa", "3", "--n-hard-negative", "1",
              "--n-hard-positive", "1", "--n-other", "1", "--out", str(tmp_path / "cli")])
    gen.generate(tmp_path / "lib", seed=3, nights=10, counts=gen.Counts(3, 3, 1, 1, 1))
    for rel in _all_files(tmp_path / "cli"):
        assert filecmp.cmp(tmp_path / "cli" / rel, tmp_path / "lib" / rel, shallow=False), rel
