"""Evidence extraction: turn logged nightly data + features into structured,
UI-consumable evidence for each flagged risk.

Design intent: the clinician view shows the REAL LOGGED EVIDENCE first -- exact
numbers, a frequency, and a short numeric series a UI can draw as a graph -- and
only then a couple of plain-language lines. So this module produces a structured
``RiskEvidence`` object, and the engine serialises it ahead of any prose.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Make ``app`` importable whether run from backend/ or elsewhere.
_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.models import ClinicianReportData, NightRecord, RiskItem  # noqa: E402


# --- Which nightly metric(s) drive which risk --------------------------------
# Maps a substring found in a risk_id / display_name to the NightRecord
# attribute(s) whose logged series is the evidence a clinician would want to see.
# Order within a tuple is "most telling first".
_RISK_METRICS: dict[str, tuple[str, ...]] = {
    "apnea": ("spo2_pct", "respiratory_rate_rpm", "disturbance_count"),
    "sdb": ("spo2_pct", "respiratory_rate_rpm", "disturbance_count"),
    "breathing": ("spo2_pct", "respiratory_rate_rpm"),
    "spo2": ("spo2_pct",),
    "oxygen": ("spo2_pct",),
    "recovery": ("hrv_rmssd_ms", "resting_heart_rate_bpm"),
    "under_recovery": ("hrv_rmssd_ms", "resting_heart_rate_bpm"),
    "illness": ("skin_temperature_c", "resting_heart_rate_bpm", "respiratory_rate_rpm"),
    "infection": ("skin_temperature_c", "resting_heart_rate_bpm"),
    "menopause": ("skin_temperature_c", "resting_heart_rate_bpm", "sleep_efficiency_pct"),
    "perimenopause": ("skin_temperature_c", "resting_heart_rate_bpm", "sleep_efficiency_pct"),
    "menstrual": ("skin_temperature_c", "resting_heart_rate_bpm"),
    "cycle": ("skin_temperature_c", "resting_heart_rate_bpm"),
    "cardio": ("resting_heart_rate_bpm", "hrv_rmssd_ms"),
    "heart": ("resting_heart_rate_bpm", "hrv_rmssd_ms"),
}

# Human-facing metric labels + units, and the direction + threshold that counts
# as a "notable" night for a simple frequency statement. ``low`` means values
# BELOW threshold are notable (e.g. SpO2 < 90); ``high`` means ABOVE.
_METRIC_META: dict[str, dict] = {
    "spo2_pct":              {"label": "SpO2", "unit": "%",   "threshold": 90.0, "direction": "low"},
    "respiratory_rate_rpm":  {"label": "Respiratory rate", "unit": " rpm", "threshold": 18.0, "direction": "high"},
    "resting_heart_rate_bpm": {"label": "Resting heart rate", "unit": " bpm", "threshold": None, "direction": "high"},
    "hrv_rmssd_ms":          {"label": "HRV (RMSSD)", "unit": " ms", "threshold": None, "direction": "low"},
    "skin_temperature_c":    {"label": "Skin temperature", "unit": " C", "threshold": None, "direction": "high"},
    "sleep_efficiency_pct":  {"label": "Sleep efficiency", "unit": "%", "threshold": 85.0, "direction": "low"},
    "disturbance_count":     {"label": "Sleep disturbances", "unit": "", "threshold": None, "direction": "high"},
}

_DEFAULT_METRICS = ("spo2_pct", "resting_heart_rate_bpm", "hrv_rmssd_ms")


@dataclass
class MetricSeries:
    """One nightly metric over the window: the series a UI graphs, plus the
    headline numbers computed from it."""
    metric: str
    label: str
    unit: str
    dates: list[str]
    values: list[float | None]
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    latest: float | None = None
    baseline_z: float | None = None
    # Frequency statement, e.g. "below 90% on 4 of 7 nights".
    notable_count: int | None = None
    nights_counted: int | None = None
    notable_text: str | None = None


@dataclass
class RiskEvidence:
    """All logged evidence for one flagged risk, evidence-first."""
    risk_id: str
    display_name: str
    tier: str
    series: list[MetricSeries] = field(default_factory=list)
    # One-line headline numbers a UI can show without parsing the series.
    headline_numbers: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    travel_suppressed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _metrics_for_risk(risk: RiskItem) -> tuple[str, ...]:
    key = f"{risk.risk_id} {risk.display_name}".lower()
    for needle, metrics in _RISK_METRICS.items():
        if needle in key:
            return metrics
    return _DEFAULT_METRICS


def _is_travel_suppressed(risk: RiskItem) -> bool:
    """A risk the rules engine down-weighted because context (e.g. altitude)
    explains it. Detected from source_labels or the risk's own reasons."""
    text = " ".join(risk.reasons).lower()
    return (
        "travel" in text
        or "altitude" in text
        or "where you are" in text
        or "context" in text and "suppress" in text
    )


def _round(v: float | None, ndigits: int = 1) -> float | None:
    if v is None:
        return None
    try:
        return round(float(v), ndigits)
    except (TypeError, ValueError):
        return None


def _build_series(metric: str, nights: list[NightRecord], baseline_z: float | None) -> MetricSeries | None:
    meta = _METRIC_META.get(metric, {"label": metric, "unit": "", "threshold": None, "direction": "high"})
    dates: list[str] = []
    values: list[float | None] = []
    for n in nights:
        dates.append(n.date.isoformat())
        values.append(getattr(n, metric, None))

    present = [v for v in values if v is not None]
    if not present:
        return None

    nd = 0 if metric == "disturbance_count" else 1
    s = MetricSeries(
        metric=metric,
        label=meta["label"],
        unit=meta["unit"],
        dates=dates,
        values=[_round(v, nd) for v in values],
        min=_round(min(present), nd),
        max=_round(max(present), nd),
        mean=_round(sum(present) / len(present), nd),
        latest=_round(values[-1], nd) if values and values[-1] is not None else _round(present[-1], nd),
        baseline_z=_round(baseline_z, 2),
        nights_counted=len(present),
    )

    # Frequency statement against a fixed threshold, when one is defined.
    thr = meta["threshold"]
    if thr is not None:
        if meta["direction"] == "low":
            notable = sum(1 for v in present if v < thr)
            rel = "below"
        else:
            notable = sum(1 for v in present if v > thr)
            rel = "above"
        s.notable_count = notable
        if notable:
            s.notable_text = (
                f"{meta['label']} {rel} {thr:g}{meta['unit']} on "
                f"{notable} of {len(present)} nights"
            )
    return s


def _headline(series: MetricSeries) -> str | None:
    """A single most-telling number string for this metric."""
    meta = _METRIC_META.get(series.metric, {})
    direction = meta.get("direction", "high")
    if series.notable_text:
        return series.notable_text
    if direction == "low" and series.min is not None:
        return f"{series.label} low {series.min:g}{series.unit}"
    if series.max is not None:
        return f"{series.label} peak {series.max:g}{series.unit}"
    return None


def build_evidence(report: ClinicianReportData, risk: RiskItem) -> RiskEvidence:
    """Pull the logged evidence for one risk: the driving metric series, the
    headline numbers, and a frequency statement where meaningful."""
    nights = report.nights
    bz = report.features.baseline_z_scores or {}

    ev = RiskEvidence(
        risk_id=risk.risk_id,
        display_name=risk.display_name,
        tier=risk.tier,
        reasons=list(risk.reasons),
        travel_suppressed=_is_travel_suppressed(risk),
    )

    for metric in _metrics_for_risk(risk):
        series = _build_series(metric, nights, bz.get(metric))
        if series is None:
            # Fall back to the point value from features if no nightly series.
            fval = (report.features.values or {}).get(metric)
            if fval is None:
                continue
            meta = _METRIC_META.get(metric, {"label": metric, "unit": ""})
            series = MetricSeries(
                metric=metric, label=meta["label"], unit=meta.get("unit", ""),
                dates=[], values=[], latest=_round(fval),
                baseline_z=_round(bz.get(metric), 2), nights_counted=0,
            )
        ev.series.append(series)
        h = _headline(series)
        if h:
            ev.headline_numbers.append(h)

    return ev
