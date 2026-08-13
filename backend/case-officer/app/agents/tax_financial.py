"""Tax / Financial agent — deterministic core (implementation plan §2.4).

There is **no LLM in this decision path**, deliberately. This is the
architecture point worth making in the defense: agents where reasoning is
required, plain Python where certainty is required. A model that paraphrases
"exceeds SAR 375,000" into "around SAR 375,000" has produced a wrong answer to a
question with an exact answer.

A thin LLM wrapper turns the returned dict into a paragraph for the UI. It never
touches the numbers; its prompt lives in :mod:`app.agents.prompts`.

Threshold provenance
--------------------
Both constants were verified against zatca.gov.sa during Phase 0 and are backed
by a corpus document — see ``tests/test_tax_financial.py``, which fails if the
corpus stops supporting them.

The comparison is strictly greater-than because the source says *exceed*:
"Individuals whose annual revenues exceed SAR 375,000" and "optional for those
whose annual revenues exceed SAR 187,500 and less than SAR 375,000". Revenue
landing exactly on a threshold therefore does NOT cross it. That is a real
boundary decision taken from the source wording, not a coding convention.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional, TypedDict

VAT_MANDATORY_THRESHOLD_SAR = 375_000
VAT_VOLUNTARY_THRESHOLD_SAR = 187_500

#: The page that explicitly states both figures. NOT the Implementing
#: Regulations, which defer the number to the GCC Agreement and never state it.
VAT_THRESHOLD_SOURCE_URL = "https://zatca.gov.sa/en/eServices/Pages/eServices_002.aspx"
VAT_THRESHOLD_SOURCE_ENTITY = "ZATCA"

VatResult = Literal[
    "mandatory_registration_likely",
    "voluntary_registration_possible",
    "registration_not_required",
    "unknown_revenue_not_provided",
]


class VatAssessment(TypedDict):
    expected_revenue: Optional[float]
    mandatory_threshold: int
    voluntary_threshold: int
    result: VatResult
    registration_required: Optional[bool]
    source: str
    source_url: str
    confidence: str


def assess_vat(expected_annual_revenue_sar: float | None) -> VatAssessment:
    """Compare expected revenue against ZATCA's registration thresholds.

    Returns ``unknown_revenue_not_provided`` rather than assuming zero when the
    figure is missing — absent data is not the same as a small business, and
    quietly defaulting to "not required" would be a wrong answer presented
    confidently.
    """
    base: VatAssessment = {
        "expected_revenue": expected_annual_revenue_sar,
        "mandatory_threshold": VAT_MANDATORY_THRESHOLD_SAR,
        "voluntary_threshold": VAT_VOLUNTARY_THRESHOLD_SAR,
        "result": "unknown_revenue_not_provided",
        "registration_required": None,
        "source": VAT_THRESHOLD_SOURCE_ENTITY,
        "source_url": VAT_THRESHOLD_SOURCE_URL,
        "confidence": "HIGH",
    }

    if expected_annual_revenue_sar is None:
        return base

    revenue = float(expected_annual_revenue_sar)
    if revenue != revenue or revenue in (float("inf"), float("-inf")):  # NaN / inf
        return base
    if revenue < 0:
        raise ValueError("expected_annual_revenue_sar cannot be negative")

    if revenue > VAT_MANDATORY_THRESHOLD_SAR:
        base["result"] = "mandatory_registration_likely"
        base["registration_required"] = True
    elif revenue > VAT_VOLUNTARY_THRESHOLD_SAR:
        base["result"] = "voluntary_registration_possible"
        base["registration_required"] = False
    else:
        base["result"] = "registration_not_required"
        base["registration_required"] = False
    return base


def vat_evidence(assessment: VatAssessment) -> dict:
    """An Evidence-shaped record for the deterministic VAT finding.

    Built as a dict rather than an ``Evidence`` model so this module stays free
    of any import that could drag an LLM client into the decision path.
    """
    revenue = assessment["expected_revenue"]
    if revenue is None:
        claim = (
            "Expected annual revenue was not provided, so VAT registration status "
            "could not be determined. ZATCA's mandatory registration threshold is "
            f"SAR {VAT_MANDATORY_THRESHOLD_SAR:,}."
        )
    else:
        claim = (
            f"Expected annual revenue of SAR {revenue:,.0f} compared against ZATCA's "
            f"mandatory VAT registration threshold of SAR {VAT_MANDATORY_THRESHOLD_SAR:,} "
            f"and voluntary threshold of SAR {VAT_VOLUNTARY_THRESHOLD_SAR:,}. "
            f"Result: {assessment['result']}."
        )
    return {
        "claim": claim,
        "source_entity": assessment["source"],
        "source_url": assessment["source_url"],
        "retrieved_at": datetime.now(timezone.utc),
        "confidence": assessment["confidence"],
        # Computed by code from a cited source, so it is self-evidently backed.
        "has_explicit_url": True,
        "retrieval_path": "corpus_fallback",
    }


def tax_financial_node(state: dict) -> dict:
    """LangGraph node: partial CaseState update. No LLM, no network."""
    assessment = assess_vat(state.get("expected_annual_revenue_sar"))
    evidence = vat_evidence(assessment)

    if assessment["result"] == "unknown_revenue_not_provided":
        requirement_status = "unverified"
        note = "Expected annual revenue not provided — VAT status undetermined."
    elif assessment["registration_required"]:
        requirement_status = "missing"
        note = "Revenue exceeds the mandatory threshold; registration is required."
    else:
        requirement_status = "satisfied"
        note = "Revenue is below the mandatory threshold."

    return {
        "vat_registration_required": assessment["registration_required"],
        "requirements": [
            {
                "name": "VAT registration (ZATCA)",
                "status": requirement_status,
                "evidence": evidence,
                "note": note,
                "produced_by": "tax_financial",
            }
        ],
        "evidence_log": [evidence],
        "decision_log": [
            "Tax / Financial: deterministic assessment (no LLM in the decision path) — "
            f"{assessment['result']}."
        ],
    }
