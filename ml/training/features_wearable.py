"""WHOOP-mappable per-epoch feature extraction for apnea screening.

The point of WakeSafe's model is a SMALL, EXPLAINABLE screen on DIVERSE open data, not a deep
net that memorises a handful of nights. So we do feature extraction, never raw deep learning,
and every feature is chosen to map onto a signal a wrist wearable (WHOOP) also reports:

  * heart rate / HRV      -- WHOOP reports resting HR and HRV (RMSSD) nightly
  * SpO2 desaturation      -- WHOOP reports nightly SpO2
  * respiratory-rate var   -- WHOOP reports nightly respiratory rate

Two open sources are pooled, both read as REAL recordings only (never synthetic):

  Apnea-ECG (PhysioNet apnea-ecg 1.0.0): overnight single-lead ECG at 100 Hz with per-MINUTE
      apnea annotations (.apn). Yields HR/HRV features per minute. No SpO2 in the usable records
      (a01r's oximetry channel is a truncated partial download and is skipped).
  UCD St Vincent's (ucddb): full polysomnography EDF with SpO2, airflow, effort and pulse, plus a
      _respevt.txt list of apnea/hypopnea events. Yields SpO2-desaturation and respiratory
      features per epoch, labelled from the event list.

The two sources expose DIFFERENT raw signals, so a pooled row has missing features (an ECG minute
has no SpO2; a UCD epoch has no beat-to-beat RMSSD). That is intentional: the model is a
gradient-boosted tree that handles missing values natively, and pooling two cohorts with partly
disjoint signals is exactly what makes the screen generalise instead of memorise.

Every feature name, unit and source is documented in ml/training/FEATURES_WEARABLE.md.
Output: one row per epoch, written to ml/data/processed/apnea_epochs.csv.

Usage: python ml/training/features_wearable.py [--raw ml/data/raw] [--out CSV] [--epoch-s 60]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

# ---- WHOOP-mappable feature schema (stable column order) -------------------------------------
# Missing is encoded as NaN and never imputed to a "normal" value; the tree splits on NaN itself.
FEATURE_COLUMNS = [
    # Heart rate / HRV (ECG- or pulse-derived) -- maps to WHOOP resting HR + HRV
    "hr_mean_bpm",
    "hr_min_bpm",
    "hr_max_bpm",
    "hr_std_bpm",
    "hrv_rmssd_ms",
    "hrv_sdnn_ms",
    # SpO2 desaturation -- maps to WHOOP nightly SpO2
    "spo2_mean_pct",
    "spo2_min_pct",
    "spo2_drop_pct",          # mean - min within the epoch
    "spo2_time_below90_frac",
    "spo2_desat_count",       # >=3% dips below a rolling baseline
    # Respiratory-rate variability -- maps to WHOOP respiratory rate
    "resp_rate_rpm",
    "resp_rate_std_rpm",
    "flow_rms",               # airflow envelope energy (0 during an apnoea)
]

APNEA_EVENT_RE = re.compile(r"\s*(\d\d):(\d\d):(\d\d)\s+(APNEA|HYP)", re.IGNORECASE)
SPO2_VALID_LO, SPO2_VALID_HI = 50.0, 100.0  # clip oximeter dropout artefacts (e.g. 3.8%)
DESAT_DROP_PCT = 3.0
ROLL_BASELINE_S = 120


# ---- Apnea-ECG: HR/HRV per minute ------------------------------------------------------------
def _rpeaks(ecg: np.ndarray, fs: float) -> np.ndarray:
    """R-peak sample indices. neurokit2 when available, else a scipy bandpass detector."""
    try:
        import neurokit2 as nk

        cleaned = nk.ecg_clean(ecg, sampling_rate=fs)
        _, info = nk.ecg_peaks(cleaned, sampling_rate=fs)
        return np.asarray(info["ECG_R_Peaks"], dtype=int)
    except Exception:
        from scipy import signal

        sos = signal.butter(2, [5, 15], btype="bandpass", fs=fs, output="sos")
        filt = signal.sosfiltfilt(sos, ecg - np.nanmean(ecg))
        energy = np.convolve(np.square(np.gradient(filt)), np.ones(int(0.15 * fs)) / int(0.15 * fs), "same")
        peaks, _ = signal.find_peaks(energy, height=np.percentile(energy, 90) * 0.3, distance=int(0.3 * fs))
        return peaks


def _hrv_from_rr(rr_s: np.ndarray) -> dict:
    """HR and HRV summaries from physiologic RR intervals (0.3-2.0 s)."""
    rr = rr_s[(rr_s >= 0.3) & (rr_s <= 2.0)]
    if len(rr) < 5:
        return dict.fromkeys(["hr_mean_bpm", "hr_min_bpm", "hr_max_bpm", "hr_std_bpm", "hrv_rmssd_ms", "hrv_sdnn_ms"], np.nan)
    hr = 60.0 / rr
    return {
        "hr_mean_bpm": float(hr.mean()),
        "hr_min_bpm": float(hr.min()),
        "hr_max_bpm": float(hr.max()),
        "hr_std_bpm": float(hr.std(ddof=1)),
        "hrv_rmssd_ms": float(np.sqrt(np.mean(np.diff(rr) ** 2)) * 1000),
        "hrv_sdnn_ms": float(rr.std(ddof=1) * 1000),
    }


def extract_apnea_ecg_record(raw_apnea: Path, name: str, epoch_s: int = 60) -> pd.DataFrame:
    """One row per epoch for an Apnea-ECG record: HR/HRV features + minute apnea label."""
    import wfdb

    rec = wfdb.rdrecord(str(raw_apnea / name))
    fs = float(rec.fs)
    ecg = rec.p_signal[:, 0]
    ann = wfdb.rdann(str(raw_apnea / name), "apn")
    minute_labels = np.array([s == "A" for s in ann.symbol], dtype=int)

    peaks = _rpeaks(ecg, fs)
    peak_t = peaks / fs
    step = epoch_s
    rows = []
    for m, lab in enumerate(minute_labels):
        t0, t1 = m * step, (m + 1) * step
        in_epoch = peak_t[(peak_t >= t0) & (peak_t < t1)]
        feats = dict.fromkeys(FEATURE_COLUMNS, np.nan)
        feats.update(_hrv_from_rr(np.diff(in_epoch)))
        feats.update(
            record_id=f"apnea-ecg/{name}",
            dataset="apnea-ecg",
            epoch_index=m,
            label=int(lab),
        )
        rows.append(feats)
    return pd.DataFrame(rows)


# ---- UCD: SpO2 / respiratory per epoch -------------------------------------------------------
def _read_edf_signals(path: Path, wanted: dict[str, list[str]]) -> dict:
    """Return {canonical_name: (signal, fs)} for the first matching label of each wanted signal."""
    import pyedflib

    f = pyedflib.EdfReader(str(path))
    try:
        labels = [f.getLabel(i).strip() for i in range(f.signals_in_file)]
        out = {}
        for canon, aliases in wanted.items():
            idx = next((i for i, lb in enumerate(labels) if lb.lower() in [a.lower() for a in aliases]), None)
            if idx is not None:
                out[canon] = (f.readSignal(idx), float(f.getSampleFrequency(idx)))
        start = f.getStartdatetime()
        start_s = start.hour * 3600 + start.minute * 60 + start.second
        return out, start_s
    finally:
        f.close()


def _parse_respevt(path: Path, start_s: int, n_epochs: int, epoch_s: int) -> np.ndarray:
    """Per-epoch apnea/hypopnoea label (1 if any event overlaps the epoch) from a _respevt.txt."""
    labels = np.zeros(n_epochs, dtype=int)
    for ln in path.read_text(errors="ignore").splitlines():
        m = APNEA_EVENT_RE.match(ln)
        if not m:
            continue
        clock = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
        rel = clock - start_s
        if rel < 0:  # event clock rolled past midnight relative to recording start
            rel += 24 * 3600
        e = int(rel // epoch_s)
        if 0 <= e < n_epochs:
            labels[e] = 1
    return labels


def _spo2_features(spo2: np.ndarray, fs: float) -> dict:
    v = spo2.astype(float)
    v[(v < SPO2_VALID_LO) | (v > SPO2_VALID_HI)] = np.nan
    if np.isnan(v).all():
        return {k: np.nan for k in ["spo2_mean_pct", "spo2_min_pct", "spo2_drop_pct", "spo2_time_below90_frac", "spo2_desat_count"]}
    mean, mn = float(np.nanmean(v)), float(np.nanmin(v))
    base = pd.Series(v).rolling(int(ROLL_BASELINE_S * fs), min_periods=1, center=True).median().to_numpy()
    desat = (base - v) >= DESAT_DROP_PCT
    desat_count = int(np.sum(np.diff(desat.astype(int)) == 1))
    return {
        "spo2_mean_pct": mean,
        "spo2_min_pct": mn,
        "spo2_drop_pct": mean - mn,
        "spo2_time_below90_frac": float(np.nanmean(v < 90)),
        "spo2_desat_count": desat_count,
    }


def extract_ucd_record(raw_ucd: Path, name: str, epoch_s: int = 60) -> pd.DataFrame:
    """One row per epoch for a UCD record: SpO2/respiratory/pulse features + event label."""
    sigs, start_s = _read_edf_signals(
        raw_ucd / f"{name}.rec",
        {"spo2": ["SpO2"], "flow": ["Flow"], "pulse": ["Pulse"], "ribcage": ["ribcage"], "abdo": ["abdo"]},
    )
    if "spo2" not in sigs:
        raise ValueError(f"{name}: no SpO2 channel")
    spo2, spo2_fs = sigs["spo2"]
    dur_s = len(spo2) / spo2_fs
    n_epochs = int(dur_s // epoch_s)
    labels = _parse_respevt(raw_ucd / f"{name}_respevt.txt", start_s, n_epochs, epoch_s)

    rows = []
    for e in range(n_epochs):
        feats = dict.fromkeys(FEATURE_COLUMNS, np.nan)
        s0, s1 = int(e * epoch_s * spo2_fs), int((e + 1) * epoch_s * spo2_fs)
        feats.update(_spo2_features(spo2[s0:s1], spo2_fs))
        if "pulse" in sigs:  # pulse oximeter heart rate -> HR features (no beat-to-beat RMSSD)
            p, pfs = sigs["pulse"]
            seg = p[int(e * epoch_s * pfs):int((e + 1) * epoch_s * pfs)].astype(float)
            seg = seg[(seg > 25) & (seg < 220)]
            if len(seg) > 3:
                feats.update(hr_mean_bpm=float(seg.mean()), hr_min_bpm=float(seg.min()),
                             hr_max_bpm=float(seg.max()), hr_std_bpm=float(seg.std(ddof=1)))
        if "flow" in sigs:
            fl, ffs = sigs["flow"]
            seg = fl[int(e * epoch_s * ffs):int((e + 1) * epoch_s * ffs)].astype(float)
            if len(seg) > 1:
                feats["flow_rms"] = float(np.sqrt(np.mean((seg - seg.mean()) ** 2)))
                feats.update(_resp_rate(seg, ffs))
        feats.update(record_id=f"ucddb/{name}", dataset="ucddb", epoch_index=e, label=int(labels[e]))
        rows.append(feats)
    return pd.DataFrame(rows)


def _resp_rate(flow: np.ndarray, fs: float) -> dict:
    """Breathing rate and its variability from the airflow zero-crossings."""
    x = flow - np.mean(flow)
    if np.allclose(x, 0):
        return {"resp_rate_rpm": np.nan, "resp_rate_std_rpm": np.nan}
    crossings = np.where(np.diff(np.sign(x)) > 0)[0]  # positive-going zero crossings = breaths
    if len(crossings) < 3:
        return {"resp_rate_rpm": np.nan, "resp_rate_std_rpm": np.nan}
    periods_s = np.diff(crossings) / fs
    periods_s = periods_s[(periods_s > 1.0) & (periods_s < 12.0)]  # 5-60 breaths/min
    if len(periods_s) < 2:
        return {"resp_rate_rpm": np.nan, "resp_rate_std_rpm": np.nan}
    rates = 60.0 / periods_s
    return {"resp_rate_rpm": float(rates.mean()), "resp_rate_std_rpm": float(rates.std(ddof=1))}


# ---- discovery + driver ----------------------------------------------------------------------
APNEA_ECG_RE = re.compile(r"^[abc]\d\d$")


def available_apnea_ecg(raw_apnea: Path) -> list[str]:
    return sorted(
        p.stem
        for p in raw_apnea.glob("*.hea")
        if APNEA_ECG_RE.match(p.stem) and (raw_apnea / f"{p.stem}.dat").exists() and (raw_apnea / f"{p.stem}.apn").exists()
    )


def available_ucd(raw_ucd: Path) -> list[str]:
    """UCD records whose EDF opens AND whose event file is present (skip truncated downloads)."""
    import pyedflib

    names = []
    for rec in sorted(raw_ucd.glob("*.rec")):
        name = rec.stem
        if not (raw_ucd / f"{name}_respevt.txt").exists():
            continue
        try:
            f = pyedflib.EdfReader(str(rec))
            f.close()
            names.append(name)
        except Exception:
            continue  # truncated / unreadable EDF
    return names


def build_dataset(raw: Path, epoch_s: int = 60) -> tuple[pd.DataFrame, dict]:
    frames, provenance = [], {"apnea_ecg": [], "ucddb": [], "ucddb_skipped": []}
    raw_apnea, raw_ucd = raw / "apnea", raw / "ucddb"

    for name in available_apnea_ecg(raw_apnea):
        frames.append(extract_apnea_ecg_record(raw_apnea, name, epoch_s))
        provenance["apnea_ecg"].append(name)

    if raw_ucd.exists():
        usable = available_ucd(raw_ucd)
        for rec in sorted(raw_ucd.glob("*.rec")):
            if rec.stem not in usable:
                provenance["ucddb_skipped"].append(rec.stem)
        for name in usable:
            try:
                frames.append(extract_ucd_record(raw_ucd, name, epoch_s))
                provenance["ucddb"].append(name)
            except Exception as exc:  # noqa: BLE001
                provenance["ucddb_skipped"].append(f"{name} ({type(exc).__name__})")

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return df, provenance


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="ml/data/raw")
    ap.add_argument("--out", default="ml/data/processed/apnea_epochs.csv")
    ap.add_argument("--epoch-s", type=int, default=60)
    args = ap.parse_args()

    df, prov = build_dataset(Path(args.raw), args.epoch_s)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"wrote {len(df)} epochs from {df['record_id'].nunique()} records to {out}")
    print("provenance:", prov)
    print("label balance:", df["label"].value_counts().to_dict())
    print("per-record:", df.groupby("record_id")["label"].agg(["size", "sum"]).to_dict("index"))


if __name__ == "__main__":
    main()
