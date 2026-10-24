"""Explanation engine for WakeSafe clinician reports.

Public API:
    explain(report) -> Explanation                 # template path, no LLM (default)
    explain_with_llm(report, polish=None)           # optional wording polish, template fallback
    build_evidence(report, risk) -> RiskEvidence    # structured per-risk evidence
    parse_evidence(text) -> dict | None             # read the [EVIDENCE] block back out

The default path is template-based (no LLM). The optional LLM wrapper only
polishes wording and always falls back to the template, so the demo never
depends on a live model.
"""
from .engine import explain, parse_evidence
from .evidence import build_evidence, MetricSeries, RiskEvidence
from .llm import explain_with_llm

__all__ = [
    "explain",
    "explain_with_llm",
    "build_evidence",
    "parse_evidence",
    "MetricSeries",
    "RiskEvidence",
]
