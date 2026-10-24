"""One-off smoke test of the apnea tier logic on SYNTHETIC demo people. Not a validation.

Scores each synthetic person from synthetic_data/out/ through the runtime model signal and the
whole tier logic, then reports per cohort how often the model signal fires and how often the
tier is raised. Nothing here tunes a threshold, and the numbers say nothing about accuracy:
synthetic data is for demos and tests only and never trains, tunes or scores a model.

ground_truth.csv is read ONLY here, to split the output by cohort. App code never reads it.

Usage: python ml/training/smoke_test_synthetic.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.services.screening.features import baseline_zscores  # noqa: E402
from app.services.screening.model import load_apnea_artifact  # noqa: E402
from app.services.screening.scoring import CONFIG, TIERS, screen_from_values  # noqa: E402

OUT = REPO / "synthetic_data" / "out"
Z_KEYS = {
    "spo2_percentage": "spo2_pct",
    "respiratory_rate": "respiratory_rate_rpm",
    "disturbance_count": "disturbance_count",
    "sleep_efficiency_percentage": "sleep_efficiency_pct",
}
COHORT = {"healthy": "healthy", "osa_mild": "osa", "osa_moderate": "osa", "osa_severe": "osa"}


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(OUT / name, comment="#")


def score_person(profile: pd.Series, nights: pd.DataFrame, artifact: dict, config: dict):
    stats = baseline_zscores(
        nights,
        columns=("resting_heart_rate", "hrv_rmssd_milli", *Z_KEYS),
        recent_nights=7,
        baseline_nights=14,
    )
    usable = nights[~nights["user_calibrating"].astype(bool)]
    conditions = [] if pd.isna(profile["conditions"]) else str(profile["conditions"]).split(";")
    return screen_from_values(
        age=int(profile["age"]),
        male=profile["sex"] == "male",
        height_cm=float(profile["height_m"]) * 100,
        weight_kg=float(profile["weight_kg"]),
        neck_cm=float(profile["neck_circumference_cm"]),
        snoring=bool(profile["snoring"]),
        tired=bool(profile["daytime_tiredness"]),
        observed_apnea=bool(profile["witnessed_breathing_pauses"]),
        hypertension=bool(profile["hypertension"]),
        conditions=conditions,
        values={
            "resting_heart_rate_bpm": stats["resting_heart_rate"]["recent_mean"],
            "hrv_rmssd_ms": stats["hrv_rmssd_milli"]["recent_mean"],
        },
        z_scores={new: stats[old]["z"] for old, new in Z_KEYS.items()},
        nights_available=len(usable),
        nights_with_spo2=int(usable["spo2_percentage"].notna().sum()),
        artifact=artifact,
        synthetic=True,
        config=config,
    )


def run(config: dict) -> pd.DataFrame:
    profiles = read("profiles.csv").set_index("person_id")
    truth = read("ground_truth.csv").set_index("person_id")["true_condition"]
    nights = read("sleep.csv").merge(read("recovery.csv").drop(columns=["is_synthetic"]), on=["person_id", "date"], how="left")
    artifact = load_apnea_artifact()
    rows = []
    for pid, profile in profiles.iterrows():
        d = score_person(profile, nights[nights["person_id"] == pid], artifact, config)
        rows.append(
            {
                "person_id": pid,
                "cohort": COHORT.get(truth[pid], "other"),
                "model_score": d.model_score,
                "model_fired": d.model_score is not None and d.model_score >= config["model_cutoff"],
                "n_signals": len(d.signals_fired),
                "raised": d.raised,
                "base_tier": d.base_tier,
                "tier": d.tier,
                **{k: k in d.signals_fired for k in Z_KEYS.values()},
            }
        )
    return pd.DataFrame(rows)


def report(df: pd.DataFrame, title: str) -> None:
    print(f"\n=== {title} (SYNTHETIC people; smoke test only, not accuracy) ===")
    for cohort, g in df.groupby("cohort"):
        tiers = ", ".join(f"{t} {int((g['tier'] == t).sum())}" for t in TIERS)
        base = ", ".join(f"{t} {int((g['base_tier'] == t).sum())}" for t in TIERS)
        trend = ", ".join(f"{k} {int(g[k].sum())}" for k in Z_KEYS.values())
        print(
            f"{cohort:8s} n={len(g):2d} | model signal fires {int(g['model_fired'].sum()):2d}/{len(g)} "
            f"({g['model_fired'].mean():.0%}) | tier raised {int(g['raised'].sum()):2d}/{len(g)} ({g['raised'].mean():.0%})"
        )
        print(f"         base tiers: {base} | final tiers: {tiers}")
        print(f"         trend signals fired: {trend} | median model score {g['model_score'].median():.2f}")


def main() -> None:
    df = run(CONFIG)
    report(df, f"as configured (model_counts_toward_raise={CONFIG['model_counts_toward_raise']})")
    healthy = df[df["cohort"] == "healthy"]
    rate = healthy["model_fired"].mean()
    print(f"\nModel signal fires for {rate:.0%} of healthy synthetic people (rule: stop counting it above 50%).")
    if rate > 0.5 and CONFIG["model_counts_toward_raise"]:
        alt = run({**CONFIG, "model_counts_toward_raise": False})
        report(alt, "with the model kept as a supporting factor only")


if __name__ == "__main__":
    main()
