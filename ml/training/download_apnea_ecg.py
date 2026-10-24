"""Fetch the PhysioNet Apnea-ECG 1.0.0 learning set (open access, no login, no agreement).

Resilient to broken connections: each file is downloaded on its own, verified against the
Content-Length header, and re-fetched up to a few times; a short/partial file is deleted so a
re-run completes it. Safe to re-run -- files already present at full size are skipped.

Usage: python ml/training/download_apnea_ecg.py
"""
from __future__ import annotations

import os
import time
import urllib.request
from pathlib import Path

BASE = "https://physionet.org/files/apnea-ecg/1.0.0/"
DEST = Path("ml/data/raw/apnea")
LEARNING = [f"a{i:02d}" for i in range(1, 21)] + [f"b{i:02d}" for i in range(1, 6)] + [f"c{i:02d}" for i in range(1, 11)]
EXTS = (".hea", ".dat", ".apn")
RETRIES = 5


def _remote_size(url: str) -> int | None:
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            cl = r.headers.get("Content-Length")
            return int(cl) if cl else None
    except Exception:
        return None


def _download(url: str, path: Path) -> bool:
    expected = _remote_size(url)
    for attempt in range(1, RETRIES + 1):
        if path.exists() and expected is not None and path.stat().st_size == expected:
            return True
        try:
            with urllib.request.urlopen(url, timeout=120) as r, open(path, "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
            if expected is None or path.stat().st_size == expected:
                return True
            print(f"  short ({path.stat().st_size}/{expected}), retry {attempt}")
        except Exception as e:  # noqa: BLE001
            print(f"  error {type(e).__name__} on {path.name}, retry {attempt}")
        if path.exists():
            path.unlink()  # drop the partial so the next attempt starts clean
        time.sleep(2 * attempt)
    return False


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    ok, failed = [], []
    for rec in LEARNING:
        got = True
        for ext in EXTS:
            name = rec + ext
            if not _download(BASE + name, DEST / name):
                got = False
                failed.append(name)
        if got:
            ok.append(rec)
    print(f"complete records: {len(ok)}/{len(LEARNING)}")
    if failed:
        print("failed files:", failed)
    # the supporting index files
    for aux in ("additional-information.txt", "RECORDS", "list", "ANNOTATORS"):
        _download(BASE + aux, DEST / aux)


if __name__ == "__main__":
    main()
