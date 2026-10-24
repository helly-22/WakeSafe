#!/usr/bin/env python3
"""Validate SYNTHETIC WakeSafe data and print per-cohort summary statistics.

Synthetic data. Not clinical. Do not use to estimate model accuracy.

Run from the repository root after generating:

    python synthetic_data/validate_synthetic.py

Exits with status 1 if any check fails. Ground truth is joined here in memory only,
for validation. It is never merged into the files the app reads.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_synthetic_whoop as gen  # noqa: E402

# (feature, table, apnea direction): +1 means apnea is expected higher than healthy.
CORE_FEATURES: list[tuple[str, str, int]] = [
    ("spo2_percentage", "recovery", -1),
    ("respiratory_rate", "sleep", +1),
    ("disturbance_count", "sleep", +1),
    ("sleep_efficiency_percentage", "sleep", -1),
    ("resting_heart_rate", "recovery", +1),
    ("hrv_rmssd_milli", "recovery", -1),
]
EXTRA_FEATURES: list[tuple[str, str]] = [
    ("recovery_score", "recovery"),
    ("sleep_performance_percentage", "sleep"),
]
SHORT_NAMES = {
    "spo2_percentage": "spo2",
    "respiratory_rate": "resp",
    "disturbance_count": "disturb",
    "sleep_efficiency_percentage": "effic",
    "resting_heart_rate": "rhr",
    "hrv_rmssd_milli": "hrv",
    "recovery_score": "recov",
    "sleep_performance_percentage": "perf",
}
COHORT_ORDER = [
    "healthy", "hard_negative", "osa_mild", "osa_moderate", "osa_severe", "hard_positive",
    "cardiovascular_strain", "respiratory_flare", "acute_illness", "urgent",
]
STAGE_COLUMNS = [
    "total_awake_time_milli", "total_no_data_time_milli", "total_light_sleep_time_milli",
    "total_slow_wave_sleep_time_milli", "total_rem_sleep_time_milli",
]
ASLEEP_COLUMNS = STAGE_COLUMNS[2:]
GROUND_TRUTH_ONLY = {"true_condition", "simulated_ahi", "difficulty", "notes"}


@dataclass
class CheckResult:
    """Outcome of one validation check."""

    name: str
    passed: bool
    detail: str


@dataclass
class Dataset:
    """All output tables plus their header lines."""

    data_dir: Path
    tables: dict[str, pd.DataFrame]
    headers: dict[str, str]

    @property
    def profiles(self) -> pd.DataFrame:
        return self.tables["profiles.csv"]

    @property
    def recovery(self) -> pd.DataFrame:
        return self.tables["recovery.csv"]

    @property
    def sleep(self) -> pd.DataFrame:
        return self.tables["sleep.csv"]

    @property
    def ground_truth(self) -> pd.DataFrame:
        return self.tables["ground_truth.csv"]


# ---------------------------------------------------------------------------
# Loading and helpers
# ---------------------------------------------------------------------------


def load_dataset(data_dir: Path | str) -> Dataset:
    """Read every CSV with comment='#' and keep the first (comment) line of each."""
    data_dir = Path(data_dir)
    tables, headers = {}, {}
    for name in gen.OUTPUT_CSVS:
        path = data_dir / name
        with open(path, "r", encoding="utf-8") as handle:
            headers[name] = handle.readline().rstrip("\n")
        tables[name] = pd.read_csv(path, comment="#", keep_default_na=True)
    return Dataset(data_dir, tables, headers)


def cohort_labels(ground_truth: pd.DataFrame) -> pd.Series:
    """Map ground truth to display cohorts (hard cases get their own cohort)."""
    def label(row: pd.Series) -> str:
        cond, diff = row["true_condition"], row["difficulty"]
        if cond == "healthy":
            return "hard_negative" if diff == "hard" else "healthy"
        if str(cond).startswith("osa_") and diff == "hard":
            return "hard_positive"
        return str(cond)

    return ground_truth.set_index("person_id").apply(label, axis=1).rename("cohort")


def person_means(ds: Dataset) -> pd.DataFrame:
    """One row per person with the mean of each feature over that person's nights."""
    cols = {"recovery": [], "sleep": []}
    for feat, table, *_ in CORE_FEATURES + [(f, t) for f, t in EXTRA_FEATURES]:
        cols[table].append(feat)
    rec = ds.recovery.groupby("person_id")[cols["recovery"]].mean()
    slp = ds.sleep.groupby("person_id")[cols["sleep"]].mean()
    return rec.join(slp, how="outer")


def screening_groups(ds: Dataset) -> tuple[pd.Index, pd.Index]:
    """Healthy group (easy healthy plus hard negatives) and apnea group (all osa rows)."""
    gt = ds.ground_truth.set_index("person_id")
    healthy = gt.index[gt["true_condition"] == "healthy"]
    apnea = gt.index[gt["true_condition"].astype(str).str.startswith("osa_")]
    return healthy, apnea


def auroc(positive: np.ndarray, negative: np.ndarray) -> float:
    """Mann-Whitney AUROC: probability a positive scores higher than a negative (ties count half)."""
    pos = np.asarray(positive, dtype=float)
    neg = np.asarray(negative, dtype=float)
    pos, neg = pos[~np.isnan(pos)], neg[~np.isnan(neg)]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    ranks = pd.Series(np.concatenate([pos, neg])).rank(method="average").to_numpy()
    rank_sum = ranks[: len(pos)].sum()
    return float((rank_sum - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg)))


def feature_aurocs(ds: Dataset) -> dict[str, float]:
    """AUROC per core feature on per-person means, oriented so apnea-like is positive."""
    means = person_means(ds)
    healthy, apnea = screening_groups(ds)
    out = {}
    for feat, _, direction in CORE_FEATURES:
        out[feat] = auroc(direction * means.loc[apnea, feat].to_numpy(), direction * means.loc[healthy, feat].to_numpy())
    return out


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_labels(ds: Dataset) -> CheckResult:
    """Every CSV starts with '# SYNTHETIC DATA' and has is_synthetic true; JSON has synthetic true."""
    problems = []
    for name, df in ds.tables.items():
        if not ds.headers[name].startswith(gen.HEADER_PREFIX):
            problems.append(f"{name}: first line does not start with '{gen.HEADER_PREFIX}'")
        if "is_synthetic" not in df.columns or not df["is_synthetic"].astype(bool).all():
            problems.append(f"{name}: is_synthetic missing or not always true")
        if name != "ground_truth.csv" and GROUND_TRUTH_ONLY & set(df.columns):
            problems.append(f"{name}: contains ground-truth columns {sorted(GROUND_TRUTH_ONLY & set(df.columns))}")
    mock_files = sorted((ds.data_dir / gen.MOCK_DIR).glob("*.json"))
    if len(mock_files) != len(ds.profiles):
        problems.append(f"expected {len(ds.profiles)} mock JSON files, found {len(mock_files)}")
    for path in mock_files:
        if json.loads(path.read_text(encoding="utf-8")).get("synthetic") is not True:
            problems.append(f"{path.name}: top-level synthetic is not true")
    ids_ok = ds.profiles["person_id"].astype(str).str.fullmatch(r"P\d{3,}").all()
    if not ids_ok:
        problems.append("person_id values must look like P001")
    return CheckResult("synthetic labels", not problems, "; ".join(problems) or "all CSV headers, columns, and JSON flags present")


def check_ranges(ds: Dataset, ranges: dict[str, list[float]]) -> CheckResult:
    """All values inside the plausible ranges listed in the config."""
    problems = []
    for col, (lo, hi) in ranges.items():
        for name, df in ds.tables.items():
            if col not in df.columns:
                continue
            values = pd.to_numeric(df[col], errors="coerce").dropna()
            bad = values[(values < lo) | (values > hi)]
            if len(bad):
                problems.append(f"{name}.{col}: {len(bad)} values outside [{lo}, {hi}] (e.g. {bad.iloc[0]})")
    for col in ("total_in_bed_time_milli", *STAGE_COLUMNS):
        if (ds.sleep[col] < 0).any() or not pd.api.types.is_integer_dtype(ds.sleep[col]):
            problems.append(f"sleep.csv.{col}: must be non-negative integer milliseconds")
    return CheckResult("plausible ranges", not problems, "; ".join(problems) or f"{len(ranges)} ranges respected")


def check_reconciliation(ds: Dataset) -> CheckResult:
    """Stage times reconcile to in-bed time, efficiency is recomputable, timestamps agree."""
    s = ds.sleep
    problems = []
    total = s[STAGE_COLUMNS].sum(axis=1)
    bad = int((total != s["total_in_bed_time_milli"]).sum())
    if bad:
        problems.append(f"{bad} nights where stages + awake + no-data != in-bed time")
    asleep = s[ASLEEP_COLUMNS].sum(axis=1)
    expected_eff = 100.0 * asleep / s["total_in_bed_time_milli"]
    bad_eff = int(((expected_eff - s["sleep_efficiency_percentage"]).abs() > 1e-3).sum())
    if bad_eff:
        problems.append(f"{bad_eff} nights where efficiency != 100 * asleep / in-bed")
    start = pd.to_datetime(s["sleep_start"], utc=True)
    end = pd.to_datetime(s["sleep_end"], utc=True)
    span_ms = ((end - start).dt.total_seconds() * 1000).round().astype("int64")
    bad_span = int((span_ms != s["total_in_bed_time_milli"]).sum())
    if bad_span:
        problems.append(f"{bad_span} nights where sleep_end - sleep_start != in-bed time")
    if s["nap"].astype(bool).any():
        problems.append("nap must be false for every row")
    for name in ("sleep.csv", "recovery.csv"):
        dates = ds.tables[name]["date"].astype(str)
        if not dates.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
            problems.append(f"{name}: date must be an ISO date string")
    keys_s = set(zip(s["person_id"], s["date"]))
    keys_r = set(zip(ds.recovery["person_id"], ds.recovery["date"]))
    if keys_s != keys_r:
        problems.append("sleep and recovery rows do not cover the same person-nights")
    return CheckResult("stage reconciliation", not problems, "; ".join(problems) or f"{len(s)} nights reconcile exactly")


def check_profiles(ds: Dataset) -> CheckResult:
    """BMI matches height and weight; hypertension flag matches conditions."""
    p = ds.profiles
    problems = []
    bmi = p["weight_kg"] / p["height_m"] ** 2
    if ((bmi - p["bmi"]).abs() > 0.06).any():
        problems.append("bmi does not match weight_kg / height_m^2")
    has_htn = p["conditions"].fillna("").str.split(";").apply(lambda xs: "hypertension" in xs)
    if (has_htn != p["hypertension"].astype(bool)).any():
        problems.append("hypertension flag disagrees with conditions")
    if not p["sex"].isin(["male", "female"]).all():
        problems.append("sex must be male or female")
    if not set(p["person_id"]) == set(ds.ground_truth["person_id"]):
        problems.append("profiles and ground_truth person ids differ")
    return CheckResult("profile consistency", not problems, "; ".join(problems) or f"{len(p)} profiles consistent")


def check_missing(ds: Dataset, cfg: dict[str, Any]) -> CheckResult:
    """Missingness and calibration flags look as configured."""
    problems = []
    r = ds.recovery
    spo2_rate = float(r["spo2_percentage"].isna().mean())
    skin_rate = float(r["skin_temp_celsius"].isna().mean())
    if not 0.02 <= spo2_rate <= 0.20:
        problems.append(f"SpO2 missing rate {spo2_rate:.3f} outside [0.02, 0.20]")
    if not 0.01 <= skin_rate <= 0.12:
        problems.append(f"skin temp missing rate {skin_rate:.3f} outside [0.01, 0.12]")
    start = pd.Timestamp(str(cfg["calendar"]["start_date"]))
    night = (pd.to_datetime(r["date"]) - start).dt.days
    lo, hi = cfg["missing"]["calibrating_nights"]
    calib = r["user_calibrating"].astype(bool)
    if (calib & (night >= hi)).any():
        problems.append(f"user_calibrating true after night {hi}")
    if (~calib & (night < lo)).any():
        problems.append(f"user_calibrating false before night {lo}")
    return CheckResult(
        "missing data", not problems,
        "; ".join(problems) or f"SpO2 missing {spo2_rate:.1%}, skin temp missing {skin_rate:.1%}, calibration flags ok",
    )


def check_directions(ds: Dataset) -> CheckResult:
    """Apnea group means move in the intended direction versus the healthy group."""
    means = person_means(ds)
    healthy, apnea = screening_groups(ds)
    problems, parts = [], []
    for feat, _, direction in CORE_FEATURES:
        diff = float(means.loc[apnea, feat].mean() - means.loc[healthy, feat].mean())
        parts.append(f"{SHORT_NAMES[feat]} {diff:+.2f}")
        if np.isnan(diff) or diff * direction <= 0:
            problems.append(f"{feat}: apnea minus healthy = {diff:+.3f}, expected sign {direction:+d}")
    return CheckResult("group directions", not problems, "; ".join(problems) or "apnea minus healthy: " + ", ".join(parts))


def check_overlap(ds: Dataset, cfg: dict[str, Any]) -> CheckResult:
    """Per-person AUROC is clearly above chance but not unrealistically high."""
    v = cfg["validation"]
    lo, hi, hard = float(v["auroc_min"]), float(v["auroc_max"]), float(v["auroc_hard_fail"])
    problems = []
    for feat, value in feature_aurocs(ds).items():
        if np.isnan(value) or value <= lo:
            problems.append(f"{feat}: AUROC {value:.3f} is not clearly above chance (<= {lo})")
        elif value >= hard:
            problems.append(f"{feat}: AUROC {value:.3f} >= {hard}, data is unrealistically easy")
        elif value >= hi:
            problems.append(f"{feat}: AUROC {value:.3f} >= target maximum {hi}")
    return CheckResult("overlap (AUROC)", not problems, "; ".join(problems) or f"every core feature in ({lo}, {hi})")


def worst_window(ds: Dataset, person_id: str, feature: str, table: str, direction: int, window: int) -> float:
    """Most apnea-like mean over `window` consecutive recorded nights for one person."""
    df = ds.tables[f"{table}.csv"]
    series = df.loc[df["person_id"] == person_id].sort_values("date")[feature]
    rolled = series.rolling(window, min_periods=max(1, window - 1)).mean().dropna()
    if rolled.empty:
        return float("nan")
    return float(rolled.max() if direction > 0 else rolled.min())


def check_hard_cases(ds: Dataset, cfg: dict[str, Any]) -> CheckResult:
    """Hard negatives reach into the mild apnea range; hard positives look healthy on most features.

    A hard negative overlaps on a feature when its per-person mean, or its worst window of
    consecutive nights (for short episodes such as a cold), is on the apnea side of the easy
    healthy median and at least as apnea-like as the least apnea-like mild apnea person.
    A hard positive is healthy-like on a feature when it is not more apnea-like than the
    configured quantile of the easy healthy group.
    """
    v = cfg["validation"]
    window = int(v["hard_negative_window_nights"])
    q = float(v["hard_positive_healthy_quantile"])
    need = int(v["hard_positive_min_healthy_features"])
    means = person_means(ds)
    cohorts = cohort_labels(ds.ground_truth)
    healthy = means.loc[cohorts.index[cohorts == "healthy"]]
    mild = means.loc[cohorts.index[cohorts == "osa_mild"]]
    if len(healthy) < 3 or len(mild) < 2:
        return CheckResult("hard case overlap", True, "skipped: too few easy healthy or mild apnea people")
    problems = []
    for pid in cohorts.index[cohorts == "hard_negative"]:
        hits = []
        for feat, table, d in CORE_FEATURES:
            mild_edge = float((d * mild[feat]).min())
            median = float(d * healthy[feat].median())
            for value in (means.loc[pid, feat], worst_window(ds, pid, feat, table, d, window)):
                if not np.isnan(value) and d * value > median and d * value >= mild_edge:
                    hits.append(SHORT_NAMES[feat])
                    break
        if not hits:
            problems.append(f"hard negative {pid} does not reach the mild apnea range on any feature")
    for pid in cohorts.index[cohorts == "hard_positive"]:
        healthy_like = sum(
            d * means.loc[pid, feat] <= float((d * healthy[feat]).quantile(q)) for feat, _, d in CORE_FEATURES
        )
        if healthy_like < need:
            problems.append(f"hard positive {pid} is healthy-like on only {healthy_like} of {len(CORE_FEATURES)} features")
    return CheckResult("hard case overlap", not problems, "; ".join(problems) or "hard negatives and hard positives overlap as intended")


def check_mock(ds: Dataset, cfg: dict[str, Any]) -> CheckResult:
    """WHOOP mock pages hold the same rows as the CSVs, chain by next_token, respect page size."""
    size = int(cfg["whoop_mock"]["page_size"])
    problems = []
    rows_per_person = ds.sleep.groupby("person_id").size()
    for pid in ds.profiles["person_id"]:
        path = ds.data_dir / gen.MOCK_DIR / f"{pid}.json"
        if not path.exists():
            problems.append(f"{pid}: mock file missing")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for endpoint in ("/v2/recovery", "/v2/activity/sleep"):
            pages = payload["endpoints"][endpoint]["pages"]
            records = [rec for page in pages for rec in page["records"]]
            if len(records) != int(rows_per_person.get(pid, 0)):
                problems.append(f"{pid} {endpoint}: {len(records)} records, CSV has {rows_per_person.get(pid, 0)}")
            if any(len(page["records"]) > size for page in pages):
                problems.append(f"{pid} {endpoint}: page larger than {size}")
            tokens = [page["next_token"] for page in pages]
            if tokens[-1] is not None or any(t is None for t in tokens[:-1]) or len(set(tokens[:-1])) != len(tokens) - 1:
                problems.append(f"{pid} {endpoint}: next_token chain is broken")
        if len(problems) > 5:
            break
    return CheckResult("WHOOP v2 mock", not problems, "; ".join(problems[:5]) or "pages match CSV rows and chain correctly")


def check_reproducibility(ds: Dataset, config_path: Path) -> CheckResult:
    """Regenerate with the parameters in the header and compare every file byte for byte."""
    params = gen.parse_header(ds.headers["profiles.csv"])
    try:
        seed, nights = int(params["seed"]), int(params["nights"])
        counts = gen.Counts(*(int(params[k]) for k in ("n_healthy", "n_osa", "n_hard_negative", "n_hard_positive", "n_other")))
    except (KeyError, ValueError):
        return CheckResult("reproducibility", False, "header line is missing generator parameters")
    if params.get("config_sha256") != gen.config_hash(config_path):
        return CheckResult("reproducibility", False, "config changed since these files were generated; regenerate them")
    with tempfile.TemporaryDirectory(prefix="wakesafe_synth_") as tmp:
        gen.generate(tmp, seed, nights, counts, config_path)
        rel_files = sorted(
            [Path(n) for n in gen.OUTPUT_CSVS]
            + [Path(gen.MOCK_DIR) / p.name for p in (Path(tmp) / gen.MOCK_DIR).glob("*.json")]
        )
        existing = {Path(gen.MOCK_DIR) / p.name for p in (ds.data_dir / gen.MOCK_DIR).glob("*.json")} | {
            Path(n) for n in gen.OUTPUT_CSVS
        }
        diffs = [str(r) for r in rel_files if not (ds.data_dir / r).exists() or not filecmp.cmp(Path(tmp) / r, ds.data_dir / r, shallow=False)]
        extra = sorted(str(p) for p in existing - set(rel_files))
    if diffs or extra:
        return CheckResult("reproducibility", False, f"differs: {diffs[:5]} extra: {extra[:5]}")
    return CheckResult("reproducibility", True, f"seed {seed}: {len(rel_files)} files byte-identical on regeneration")


def run_checks(data_dir: Path | str, config_path: Path | str = gen.DEFAULT_CONFIG_PATH, reproducibility: bool = True) -> tuple[Dataset, list[CheckResult]]:
    """Load the data and run every check."""
    cfg = gen.load_config(config_path)
    ds = load_dataset(data_dir)
    checks: list[Callable[[], CheckResult]] = [
        lambda: check_labels(ds),
        lambda: check_ranges(ds, cfg["validation"]["ranges"]),
        lambda: check_reconciliation(ds),
        lambda: check_profiles(ds),
        lambda: check_missing(ds, cfg),
        lambda: check_directions(ds),
        lambda: check_overlap(ds, cfg),
        lambda: check_hard_cases(ds, cfg),
        lambda: check_mock(ds, cfg),
    ]
    if reproducibility:
        checks.append(lambda: check_reproducibility(ds, Path(config_path)))
    return ds, [c() for c in checks]


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def summary_table(ds: Dataset) -> pd.DataFrame:
    """Mean and SD of per-person means for each cohort and feature."""
    means = person_means(ds).join(cohort_labels(ds.ground_truth))
    feats = [f for f, *_ in CORE_FEATURES] + [f for f, _ in EXTRA_FEATURES]
    rows = []
    present = [c for c in COHORT_ORDER if c in set(means["cohort"])]
    for cohort in present:
        sub = means[means["cohort"] == cohort]
        row: dict[str, Any] = {"cohort": cohort, "n": len(sub)}
        for f in feats:
            sd = sub[f].std(ddof=1) if len(sub) > 1 else 0.0
            row[SHORT_NAMES[f]] = f"{sub[f].mean():.2f} ({sd:.2f})"
        rows.append(row)
    return pd.DataFrame(rows).set_index("cohort")


def print_report(ds: Dataset, results: list[CheckResult]) -> None:
    """Print the summary table, AUROCs, and check results."""
    print(gen.NOTICE)
    print()
    print("Per-cohort summary: mean (SD) of per-person means over each person's nights")
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(summary_table(ds).to_string())
    print()
    healthy, apnea = screening_groups(ds)
    print(f"AUROC healthy (n={len(healthy)}, incl. hard negatives) vs apnea (n={len(apnea)}, incl. hard positives), per-person means:")
    for feat, value in feature_aurocs(ds).items():
        print(f"  {feat:<30} {value:.3f}")
    print()
    print("Checks:")
    for r in results:
        print(f"  [{'PASS' if r.passed else 'FAIL'}] {r.name}: {r.detail}")
    failed = sum(not r.passed for r in results)
    print()
    print(f"{len(results) - failed} passed, {failed} failed")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 1 if any check fails."""
    p = argparse.ArgumentParser(description=f"Validate SYNTHETIC WakeSafe data. {gen.NOTICE}")
    p.add_argument("--data", type=Path, default=gen.DEFAULT_OUT)
    p.add_argument("--config", type=Path, default=gen.DEFAULT_CONFIG_PATH)
    p.add_argument("--skip-reproducibility", action="store_true")
    args = p.parse_args(argv)
    ds, results = run_checks(args.data, args.config, reproducibility=not args.skip_reproducibility)
    print_report(ds, results)
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
