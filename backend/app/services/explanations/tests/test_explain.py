"""Tests for the WakeSafe explanation engine (template-first, evidence-first).

Run from the backend/ directory:
    pytest app/services/explanations/tests -q
or target the module folder directly:
    pytest backend/app/services/explanations/ -q
"""
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

# backend/ on the path so ``app`` imports (mirrors backend/tests/test_schemas.py).
_BACKEND = Path(__file__).resolve().parents[4]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.models import (
    ApneaScore,
    ClinicianReportData,
    Explanation,
    FeatureSet,
    NightRecord,
    RiskAssessment,
    RiskItem,
)
from app.services.explanations import (
    build_evidence,
    explain,
    explain_with_llm,
    parse_evidence,
)

# Words that would make the output read as a diagnosis rather than a screen.
DIAGNOSIS_WORDS = [
    "you have",
    "diagnosed",
    "diagnosis of",
    "you suffer",
    "confirms you have",
]


def _high_apnea_report() -> ClinicianReportData:
    """A High-tier sleep-apnea report: SpO2 dips below 90 on several nights,
    respiratory rate elevated, disturbances up."""
    spo2 = [96.0, 91.0, 88.0, 89.0, 87.0, 90.0, 86.0]  # min 86, <90 on 4 nights
    rr = [15.0, 16.0, 19.0, 20.0, 21.0, 18.0, 22.0]
    dist = [3, 5, 9, 11, 8, 7, 12]
    nights = [
        NightRecord(
            night_id=f"P001-2026-09-0{i+1}",
            date=date(2026, 9, i + 1),
            spo2_pct=spo2[i],
            respiratory_rate_rpm=rr[i],
            disturbance_count=dist[i],
            resting_heart_rate_bpm=58.0 + i,
            hrv_rmssd_ms=70.0 - 2 * i,
            source="synthetic",
        )
        for i in range(7)
    ]
    risks = [
        RiskItem(
            risk_id="apnea",
            display_name="Sleep-disordered breathing",
            tier="High",
            reasons=[
                "SpO2 repeatedly dipped below 90% overnight",
                "Respiratory rate elevated versus baseline",
            ],
            evidence_rating="Moderate",
            suggested_specialty="Sleep medicine",
            source_labels=["wearable_measured", "app_calculated"],
        )
    ]
    return ClinicianReportData(
        generated_at=datetime(2026, 9, 8, 9, 0),
        window_start=date(2026, 9, 1),
        window_end=date(2026, 9, 7),
        profile_summary={"age": 54, "sex": "M"},
        apnea_score=ApneaScore(
            tier="High", probability=0.78, model_version="apnea-v1",
            evidence_note="SpO2 desaturation pattern",
        ),
        risk_assessment=RiskAssessment(
            risks=risks, urgent_override=False,
            rules_version="rules-v1", disclaimer="Screening only.",
        ),
        features=FeatureSet(
            values={"spo2_pct": 86.0, "respiratory_rate_rpm": 22.0},
            baseline_z_scores={"spo2_pct": -2.1, "respiratory_rate_rpm": 1.8},
            nights_available=7, nights_with_spo2=7,
            window_start=date(2026, 9, 1), window_end=date(2026, 9, 7),
        ),
        nights=nights,
        device_label="WHOOP (synthetic)",
        data_provenance=["synthetic"],
        model_version="apnea-v1",
        rules_version="rules-v1",
    )


# --- core acceptance ---------------------------------------------------------

def test_template_path_is_default_and_llm_free():
    out = explain(_high_apnea_report())
    assert isinstance(out, Explanation)
    assert out.generated_by == "template"
    assert out.summary and out.risk_explanations and out.limitations


def test_output_names_the_driving_numbers():
    out = explain(_high_apnea_report())
    text = out.risk_explanations["apnea"]
    # The exact logged numbers must appear, not just prose.
    assert "88" in text or "86" in text, "min SpO2 not named"
    assert "4 of 7" in text, "frequency statement missing"


def test_no_diagnosis_words_anywhere():
    out = explain(_high_apnea_report())
    blob = " ".join(
        [out.summary, *out.risk_explanations.values(), *out.limitations]
    ).lower()
    for w in DIAGNOSIS_WORDS:
        assert w not in blob, f"diagnosis phrasing present: {w!r}"


def test_no_numeric_risk_score_verdict():
    out = explain(_high_apnea_report())
    blob = " ".join([out.summary, *out.risk_explanations.values()]).lower()
    # Probability from apnea_score must NOT be emitted as a verdict.
    assert "0.78" not in blob and "78%" not in blob
    assert "% risk" not in blob and "% probability" not in blob


def test_evidence_is_graph_ready():
    out = explain(_high_apnea_report())
    ev = parse_evidence(out.risk_explanations["apnea"])
    assert ev is not None, "no [EVIDENCE] block to parse"
    series = ev["series"]
    assert series, "no metric series exposed"
    spo2 = next(s for s in series if s["metric"] == "spo2_pct")
    # Aligned arrays the UI can plot directly.
    assert len(spo2["dates"]) == len(spo2["values"]) == 7
    assert spo2["min"] == 86.0 and spo2["max"] == 96.0
    assert spo2["notable_count"] == 4
    assert ev["headline_numbers"], "no headline numbers"


def test_evidence_comes_before_prose():
    out = explain(_high_apnea_report())
    text = out.risk_explanations["apnea"]
    assert text.index("[EVIDENCE]") < text.index("screening signal")


def test_limitations_are_honest():
    out = explain(_high_apnea_report())
    joined = " ".join(out.limitations).lower()
    assert "diagnosis" in joined  # "not a diagnosis"
    assert "ecg" in joined or "sleep study" in joined


# --- edge cases --------------------------------------------------------------

def test_no_risks_is_calm_and_safe():
    rpt = _high_apnea_report()
    rpt.risk_assessment.risks = []
    out = explain(rpt)
    assert out.risk_explanations == {}
    assert "diagnosis" in out.summary.lower()


def test_urgent_override_leads_summary():
    rpt = _high_apnea_report()
    rpt.risk_assessment.urgent_override = True
    rpt.risk_assessment.urgent_reasons = ["Chest pain reported"]
    out = explain(rpt)
    assert "prompt attention" in out.summary.lower()
    assert "Chest pain reported" in out.summary


def test_travel_suppressed_line_present():
    rpt = _high_apnea_report()
    rpt.risk_assessment.risks[0].reasons.append(
        "Likely explained by travel to altitude (context)"
    )
    out = explain(rpt)
    assert "fits where you are" in out.risk_explanations["apnea"].lower()


def test_short_window_limitation():
    rpt = _high_apnea_report()
    rpt.features.nights_available = 3
    out = explain(rpt)
    assert any("short window" in l.lower() for l in out.limitations)


# --- optional LLM wrapper ----------------------------------------------------

def test_llm_wrapper_with_no_polisher_matches_template():
    # No polisher means no model ran, so provenance stays honest: "template".
    rpt = _high_apnea_report()
    base = explain(rpt)
    llm = explain_with_llm(rpt, polish=None)
    assert llm.generated_by == "template"
    assert llm.risk_explanations == base.risk_explanations
    assert llm.summary == base.summary


def test_llm_polish_never_touches_evidence_block():
    rpt = _high_apnea_report()

    def shouter(prose: str) -> str:
        return prose.upper()

    out = explain_with_llm(rpt, polish=shouter)
    ev = parse_evidence(out.risk_explanations["apnea"])
    assert ev is not None and ev["series"], "evidence block corrupted by polish"
    # Prose was polished...
    assert "SCREENING SIGNAL" in out.risk_explanations["apnea"]


def test_llm_polish_falls_back_when_it_raises():
    rpt = _high_apnea_report()

    def broken(_prose: str) -> str:
        raise RuntimeError("model down")

    out = explain_with_llm(rpt, polish=broken)
    base = explain(rpt)
    assert out.risk_explanations == base.risk_explanations
    assert out.summary == base.summary


def test_llm_polish_rejects_diagnosis_leak():
    rpt = _high_apnea_report()

    def leaky(_prose: str) -> str:
        return "You have sleep apnea."

    out = explain_with_llm(rpt, polish=leaky)
    blob = " ".join([out.summary, *out.risk_explanations.values()]).lower()
    assert "you have sleep apnea" not in blob


# --- builder unit ------------------------------------------------------------

def test_build_evidence_direct():
    rpt = _high_apnea_report()
    ev = build_evidence(rpt, rpt.risk_assessment.risks[0])
    assert ev.risk_id == "apnea" and ev.tier == "High"
    metrics = {s.metric for s in ev.series}
    assert "spo2_pct" in metrics
