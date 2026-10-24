"""Extract WakeSafe-style nightly summaries from the real Apnea-ECG recordings.

Input:  ml/data/raw/apnea-ecg/ (PhysioNet Apnea-ECG 1.0.0: learning set a01..c10 and test set x01..x35)
Output: ml/data/processed/apnea_ecg_nights.csv, one row per recording.

Only real recordings are read. Synthetic data is never used here.
Beat times come from the .qrs annotations when present, otherwise R peaks are
detected from the ECG in the .dat file. Minute-level apnea labels come from .apn
for a, b and c records. The x records have no .apn, so their apnea-minute total comes
from the dataset's own additional-information.txt table.

The class (a apnea, b borderline, c control) follows the dataset definition applied to
the apnea-minute total: at least 100 minutes is a, fewer than 5 is c, otherwise b.
Several recordings are repeat nights of one person, so subject_id groups recordings by
identical age, sex, height and weight from additional-information.txt.
See ml/training/FEATURES.md for every column.

Usage: python ml/training/extract_features.py [--raw DIR] [--out CSV]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
import wfdb
from scipy import signal

RR_MIN_S = 0.3  # 200 bpm
RR_MAX_S = 2.0  # 30 bpm
ARTIFACT_TOL = 0.2  # drop an interval that differs from its local median by more than 20%
ARTIFACT_WINDOW = 11  # beats
NOISE_SYMBOL = "|"  # .qrs symbol for an isolated QRS-like artifact
MIN_BEATS_PER_MINUTE = 10
RESTING_WINDOW_MIN = 5
RESTING_MIN_VALID = 4  # valid minutes needed inside a 5 minute window
GROUP_LABEL = {"a": 1, "c": 0}  # b (borderline) has no binary label
APNEA_MIN_A = 100  # apnea minutes needed for class a
APNEA_MAX_C_EXCL = 5  # class c has fewer than this many apnea minutes
INFO_FILE = "additional-information.txt"

RECORD_RE = re.compile(r"^([abcx])\d\d$")


def derive_class(apnea_minutes: float) -> str:
    """Apnea-ECG class from the dataset definition: a >= 100 min, c < 5 min, else b."""
    if apnea_minutes >= APNEA_MIN_A:
        return "a"
    if apnea_minutes < APNEA_MAX_C_EXCL:
        return "c"
    return "b"


def load_info(raw_dir: Path) -> pd.DataFrame:
    """Per-record table from additional-information.txt, indexed by record name, plus subject_id."""
    path = raw_dir / INFO_FILE
    if not path.exists():
        return pd.DataFrame()
    rows = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 12 and RECORD_RE.match(parts[0]):
            rows.append(
                {
                    "record": parts[0],
                    "length_min": int(parts[1]),
                    "apnea_min": int(parts[3]),
                    "age": int(parts[8]),
                    "sex": parts[9],
                    "height_cm": int(parts[10]),
                    "weight_kg": int(parts[11]),
                }
            )
    info = pd.DataFrame(rows).set_index("record")
    # Same age, sex, height and weight is treated as the same person.
    key = info[["age", "sex", "height_cm", "weight_kg"]].astype(str).agg("|".join, axis=1)
    ids = {k: f"S{i:02d}" for i, k in enumerate(dict.fromkeys(key), 1)}
    info["subject_id"] = key.map(ids)
    return info


def detect_r_peaks(ecg: np.ndarray, fs: float) -> np.ndarray:
    """Small Pan-Tompkins-style detector, used only when no .qrs file exists."""
    sos = signal.butter(2, [5, 15], btype="bandpass", fs=fs, output="sos")
    filt = signal.sosfiltfilt(sos, ecg - np.nanmean(ecg))
    energy = np.convolve(np.square(np.gradient(filt)), np.ones(int(0.15 * fs)) / int(0.15 * fs), "same")
    thresh = np.percentile(energy, 90) * 0.3
    cand, _ = signal.find_peaks(energy, height=thresh, distance=int(RR_MIN_S * fs))
    half = int(0.075 * fs)
    peaks = []
    for c in cand:  # snap to the local maximum of the filtered signal
        lo, hi = max(c - half, 0), min(c + half + 1, len(filt))
        peaks.append(lo + int(np.argmax(np.abs(filt[lo:hi]))))
    return np.unique(np.array(peaks, dtype=int))


def beat_samples(raw_dir: Path, name: str, fs: float) -> tuple[np.ndarray, np.ndarray, str]:
    """Return beat sample indices, a per-beat noisy flag, and the source."""
    if (raw_dir / f"{name}.qrs").exists():
        ann = wfdb.rdann(str(raw_dir / name), "qrs")
        noisy = np.array([s == NOISE_SYMBOL for s in ann.symbol])
        return np.asarray(ann.sample, dtype=int), noisy, "qrs"
    rec = wfdb.rdrecord(str(raw_dir / name), channels=[0])
    peaks = detect_r_peaks(rec.p_signal[:, 0], fs)
    return peaks, np.zeros(len(peaks), dtype=bool), "detected"


def valid_intervals(rr: np.ndarray, noisy_beat: np.ndarray) -> np.ndarray:
    """Mask of usable RR intervals: physiologic, not touching a noisy beat, near the local median."""
    ok = (rr >= RR_MIN_S) & (rr <= RR_MAX_S) & ~noisy_beat[1:] & ~noisy_beat[:-1]
    clean = pd.Series(np.where(ok, rr, np.nan))
    med = clean.rolling(ARTIFACT_WINDOW, center=True, min_periods=3).median().to_numpy()
    with np.errstate(invalid="ignore"):
        return ok & (np.abs(rr - med) <= ARTIFACT_TOL * med)


def extract_record(raw_dir: Path, name: str, info: pd.DataFrame | None = None) -> dict:
    if info is None:
        info = load_info(raw_dir)
    row = info.loc[name] if name in info.index else None
    hdr = wfdb.rdheader(str(raw_dir / name))
    fs = float(hdr.fs)
    if (raw_dir / f"{name}.apn").exists():
        apn = wfdb.rdann(str(raw_dir / name), "apn")
        labels = np.array([s == "A" for s in apn.symbol])
        n_min = len(labels)
        apnea_minutes, label_source = int(labels.sum()), "apn"
    elif row is not None:
        n_min = int(row["length_min"])
        apnea_minutes, label_source = int(row["apnea_min"]), "info_table"
    else:
        raise FileNotFoundError(f"{name}: no .apn file and no entry in {INFO_FILE}")

    samples, noisy, source = beat_samples(raw_dir, name, fs)
    keep = samples < n_min * 60 * fs
    samples, noisy = samples[keep], noisy[keep]
    t = samples / fs
    rr = np.diff(t)
    rr_t = t[1:]  # each interval is stamped with the time of its closing beat
    valid = valid_intervals(rr, noisy)

    rr_v, minute_v = rr[valid], (rr_t[valid] // 60).astype(int)
    hr_minute = np.full(n_min, np.nan)
    for m in range(n_min):
        r = rr_v[minute_v == m]
        if len(r) >= MIN_BEATS_PER_MINUTE:
            hr_minute[m] = 60.0 / r.mean()

    # RMSSD uses only successive pairs where both intervals are valid.
    pair_ok = valid[1:] & valid[:-1]
    d = np.diff(rr)[pair_ok]
    rmssd_ms = float(np.sqrt(np.mean(d**2)) * 1000) if len(d) else np.nan

    hr_roll = pd.Series(hr_minute).rolling(RESTING_WINDOW_MIN, min_periods=RESTING_MIN_VALID).mean()
    group = derive_class(apnea_minutes)

    return {
        "person_id": name,
        "subject_id": row["subject_id"] if row is not None else name,
        "record_set": "test" if name.startswith("x") else "learning",
        "group": group,
        "label": GROUP_LABEL.get(group, np.nan),
        "recording_hours": round(n_min / 60.0, 3),
        "n_minutes": n_min,
        "n_beats": int(len(samples)),
        "valid_rr_fraction": float(valid.mean()) if len(valid) else np.nan,
        "mean_hr_bpm": float(60.0 / rr_v.mean()) if len(rr_v) else np.nan,
        "resting_hr_bpm": float(hr_roll.min()) if hr_roll.notna().any() else np.nan,
        "hrv_rmssd_ms": rmssd_ms,
        "sdnn_ms": float(rr_v.std(ddof=1) * 1000) if len(rr_v) > 1 else np.nan,
        "hr_minute_sd_bpm": float(np.nanstd(hr_minute, ddof=1)) if np.isfinite(hr_minute).sum() > 1 else np.nan,
        "apnea_minutes": apnea_minutes,
        "apnea_minute_fraction": float(apnea_minutes / n_min) if n_min else np.nan,
        "label_source": label_source,
        "beat_source": source,
    }


def list_records(raw_dir: Path) -> list[str]:
    """Records with a header, beat times (.qrs or .dat) and a label source (.apn or the info table)."""
    info = load_info(raw_dir)
    names = sorted({p.stem for p in raw_dir.glob("*.hea") if RECORD_RE.match(p.stem)})
    return [
        n
        for n in names
        if ((raw_dir / f"{n}.qrs").exists() or (raw_dir / f"{n}.dat").exists())
        and ((raw_dir / f"{n}.apn").exists() or n in info.index)
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="ml/data/raw/apnea-ecg")
    ap.add_argument("--out", default="ml/data/processed/apnea_ecg_nights.csv")
    args = ap.parse_args()

    raw_dir = Path(args.raw)
    info = load_info(raw_dir)
    rows = [extract_record(raw_dir, n, info) for n in list_records(raw_dir)]
    df = pd.DataFrame(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)

    counts = df["group"].value_counts().to_dict()
    print(f"wrote {len(df)} recordings from {df['subject_id'].nunique()} subjects to {args.out}: {counts}")
    print(f"excluded from training (class b, borderline): {int((df['group'] == 'b').sum())}")

    # The derived class must reproduce the dataset's own letters for a, b and c records.
    letters = df["person_id"].str[0]
    labeled = df[letters.isin(["a", "b", "c"])]
    mism = labeled[labeled["group"] != labeled["person_id"].str[0]]["person_id"].tolist()
    print(f"class definition reproduces a/b/c letters: {not mism}" + (f" (mismatches: {mism})" if mism else ""))


if __name__ == "__main__":
    main()
