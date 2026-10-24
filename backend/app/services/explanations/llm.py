"""Optional LLM wrapper: wording polish ONLY, same guardrails, template fallback.

The template path is always the source of truth. This wrapper, when a callable
polisher is supplied, rewrites the prose lines for readability WITHOUT touching
the ``[EVIDENCE]{...}[/EVIDENCE]`` block or the numbers inside it. If the
polisher is absent, raises, or returns anything that fails the no-diagnosis /
no-score guardrails, the untouched template output is returned.

The demo never depends on a live model: ``explain_with_llm`` with no ``polish``
argument is identical to ``explain``.
"""
from __future__ import annotations

from collections.abc import Callable

from app.models import ClinicianReportData, Explanation

from .engine import (
    EVIDENCE_CLOSE,
    EVIDENCE_OPEN,
    _assert_no_diagnosis,
    explain,
)

Polisher = Callable[[str], str]


def _split_evidence(text: str) -> tuple[str, str]:
    """Return (evidence_block_incl_markers, prose). Prose is everything after
    the closing marker."""
    start = text.find(EVIDENCE_OPEN)
    end = text.find(EVIDENCE_CLOSE)
    if start == -1 or end == -1:
        return "", text
    end += len(EVIDENCE_CLOSE)
    return text[start:end], text[end:].lstrip("\n")


def _safe_polish(prose: str, polish: Polisher) -> str:
    """Polish prose but reject anything unsafe; fall back to the original."""
    try:
        out = polish(prose)
    except Exception:
        return prose
    if not isinstance(out, str) or not out.strip():
        return prose
    try:
        _assert_no_diagnosis(out)
    except AssertionError:
        return prose
    # The polisher must not invent a numeric risk score verdict; if it added any
    # "%" probability-style verdict not present before, keep the original.
    if "% risk" in out.lower() or "% probability" in out.lower():
        return prose
    return out


def explain_with_llm(
    report: ClinicianReportData,
    polish: Polisher | None = None,
) -> Explanation:
    """Template-first, optionally LLM-polished. Evidence block is never altered."""
    base = explain(report)
    if polish is None:
        # No model ran -- keep honest provenance ("template").
        return base

    new_risk: dict[str, str] = {}
    for rid, text in base.risk_explanations.items():
        block, prose = _split_evidence(text)
        polished = _safe_polish(prose, polish) if prose else prose
        new_risk[rid] = f"{block}\n{polished}" if block else polished

    new_summary = _safe_polish(base.summary, polish)

    return Explanation(
        summary=new_summary,
        risk_explanations=new_risk,
        limitations=base.limitations,
        generated_by="llm",
    )
