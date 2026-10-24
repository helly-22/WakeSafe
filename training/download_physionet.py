"""Download an open PhysioNet dataset using its SHA256SUMS.txt manifest.

Usage: python training/download_physionet.py apnea-ecg 1.0.0 data/raw/apnea-ecg

Resumable: files whose SHA-256 already matches are skipped, and each file is
verified after download. Used because wget and the aws CLI may be absent.
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

BASE = "https://physionet.org/files"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(name: str, version: str, dest: str) -> int:
    root = Path(dest)
    root.mkdir(parents=True, exist_ok=True)
    url_base = f"{BASE}/{name}/{version}"
    with urllib.request.urlopen(f"{url_base}/SHA256SUMS.txt", timeout=60) as r:
        lines = r.read().decode().splitlines()
    entries = [ln.split(None, 1) for ln in lines if ln.strip()]
    failed = 0
    for i, (digest, rel) in enumerate(entries, 1):
        rel = rel.strip()
        target = root / rel
        if target.exists() and sha256_of(target) == digest:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        try:
            urllib.request.urlretrieve(f"{url_base}/{rel}", part)
            if sha256_of(part) != digest:
                raise ValueError("checksum mismatch")
            part.replace(target)
            print(f"[{i}/{len(entries)}] ok {rel}", flush=True)
        except Exception as exc:  # keep going, report at the end
            failed += 1
            print(f"[{i}/{len(entries)}] FAILED {rel}: {exc}", flush=True)
    print(f"DONE failed={failed} total={len(entries)}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
