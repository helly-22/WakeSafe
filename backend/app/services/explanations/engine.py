"""Template-first explanation engine.

``explain(report)`` returns an :class:`Explanation`:

* ``summary``            - a few lines max, calm, screening-only.
* ``risk_explanations``  - {risk_id: text}. Each text is EVIDENCE FIRST: a
                           machine-readable ``[EVIDENCE]{...json...}[/EVIDENCE]``
                           block the UI parses for numbers and the graph series,
                           followed by at most a couple of plain-language lines.
* ``limitations``        - honest list (screening not diagnosis, derived nightly
                           summaries not raw ECG, few nights).
* ``generated_by``       - "template" (default) or "llm".

Guardrails (enforced, not just intended):
* never emit a numeric risk score / probability as a verdict;
* never use diagnosis phrasing ("you have X"): screening language only.

How the UI gets the graph series: parse the JSON in the ``[EVIDENCE]`` block of
each ``risk_explanations[risk_id]`` value. ``series[].dates`` and
``series[].values`` are aligned arrays ready to plot; ``headline_numbers`` and
``series[].min/max/mean/latest/notable_text`` are the numbers to show first.
"""
from __future__ import annotations

import json

from app.models import ClinicianReportData, Explanation, RiskItem

from .evidence import RiskEvidence, build_evidence

EVIDENCE_OPEN = "[EVIDENCE]"
EVIDENCE_CLOSE = "[/EVIDENCE]"

# Phrasing that would read as a diagnosis. The engine must never produce these.
_DIAGNOSIS_PHRASES = (
    "you have",
    "you suffer from",
    "diagnosed with",
    "this is a diagnosis",
    "confirms you have",
    "you are diagnosed",
)

_TIER_LEAD = {
    "Urgent": "These signs need prompt attention.",
    "High": "Several nights show a consistent pattern worth a clinician's look.",
    "Moderate": "A pattern is building across a few nights; worth watching.",
    "Low": "Mostly within your usual range.",
}

_TRAVEL_LINE = "Fits where you are; watching for persistence at home."


def _screening_line(ev: RiskEvidence) -> str:
    """Plain-language, screening-only prose for one risk. A couple of lines max,
    built from the logged numbers -- never a verdict, never a diagnosis."""
    lead = _TIER_LEAD.get(ev.tier, "")
    nums = "; ".join(ev.headline_numbers[:3]) if ev.headline_numbers else ""
    parts: list[str] = []
    if nums:
        parts.append(f"What was logged: {nums}.")
    if lead:
        parts.append(lead)
    parts.append(
        f"This is a screening signal for {ev.display_name.lower()}, not a diagnosis. "
        f"Sharing these numbers with a clinician can help decide next steps."
    )
    if ev.travel_suppressed:
        parts.append(_TRAVEL_LINE)
    return " ".join(parts)


def _evidence_block(ev: RiskEvidence) -> str:
    payload = ev.to_dict()
    return f"{EVIDENCE_OPEN}{json.dumps(payload, separators=(',', ':'))}{EVIDENCE_CLOSE}"


def _risk_text(ev: RiskEvidence) -> str:
    """Evidence first (machine-readable block), then minimal prose."""
    return f"{_evidence_block(ev)}\n{_screening_line(ev)}"


def parse_evidence(text: str) -> dict | None:
    """Read the ``[EVIDENCE]{...}[/EVIDENCE]`` JSON back out of a
    ``risk_explanations`` value. Returns the evidence dict, or None if absent.

    This is how the UI gets the graph series: ``result["series"][i]["dates"]``
    and ``["values"]`` are aligned arrays ready to plot."""
    start = text.find(EVIDENCE_OPEN)
    end = text.find(EVIDENCE_CLOSE)
    if start == -1 or end == -1:
        return None
    raw = text[start + len(EVIDENCE_OPEN):end]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _assert_no_diagnosis(text: str) -> None:
    low = text.lower()
    for phrase in _DIAGNOSIS_PHRASES:
        if phrase in low:
            raise AssertionError(f"diagnosis phrasing leaked into output: {phrase!r}")


def _build_summary(report: ClinicianReportData, evidences: list[RiskEvidence]) -> str:
    """A few lines max. Lists the flags by name + tier, no scores, calm tone."""
    ra = report.risk_assessment
    if ra.urgent_override:
        flags = "; ".join(ra.urgent_reasons) or "urgent signs noted"
        return (
            f"Some signs may need prompt attention: {flags}. "
            "This is a screening summary, not a diagnosis."
        )
    if not evidences:
        return (
            "Nothing stood out across the nights reviewed. "
            "This is a screening summary, not a diagnosis."
        )
    named = ", ".join(f"{e.display_name} ({e.tier})" for e in evidences)
    n = report.features.nights_available
    return (
        f"Across {n} night{'s' if n != 1 else ''} we flagged: {named}. "
        "Each flag below leads with the exact logged numbers. "
        "These are screening signals, not a diagnosis."
    )


def _limitations(report: ClinicianReportData) -> list[str]:
    n = report.features.nights_available
    lim = [
        "This is a wellness screening, not a medical diagnosis.",
        f"{report.device_label or 'The wearable'} reports derived nightly summaries, "
        "not raw ECG or a sleep study.",
    ]
    if n and n < 7:
        lim.append(f"Only {n} night{'s' if n != 1 else ''} of data -- a short window; trends firm up with more nights.")
    if report.features.nights_with_spo2 == 0:
        lim.append("No SpO2 was recorded in this window, so breathing-related signals are limited.")
    lim.append("Numbers can be affected by travel, illness, alcohol and wearable fit.")
    return lim


def explain(report: ClinicianReportData) -> Explanation:
    """Template path (default, no LLM). Builds an evidence-first Explanation."""
    risks: list[RiskItem] = list(report.risk_assessment.risks)

    evidences = [build_evidence(report, r) for r in risks]

    risk_explanations: dict[str, str] = {}
    for ev in evidences:
        text = _risk_text(ev)
        _assert_no_diagnosis(text)
        risk_explanations[ev.risk_id] = text

    summary = _build_summary(report, evidences)
    _assert_no_diagnosis(summary)

    return Explanation(
        summary=summary,
        risk_explanations=risk_explanations,
        limitations=_limitations(report),
        generated_by="template",
    )
