"""Tests for the deterministic Tax/Financial core (implementation plan §2.4).

Two things are locked in here beyond the arithmetic:

* the thresholds are still supported by the corpus, and
* the strict greater-than boundary still matches the source's wording ("exceed").

Both were established in Phase 0. A future change that breaks either should
fail loudly rather than silently produce a confident wrong number.
"""

import inspect

import pytest

from app.agents import tax_financial
from app.agents.tax_financial import (
    VAT_MANDATORY_THRESHOLD_SAR,
    VAT_VOLUNTARY_THRESHOLD_SAR,
    assess_vat,
    tax_financial_node,
    vat_evidence,
)
from app.config.allowlist import is_citable
from app.tools.corpus import load_corpus


class TestThresholdProvenance:
    def test_constants_match_the_plan(self):
        assert VAT_MANDATORY_THRESHOLD_SAR == 375_000
        assert VAT_VOLUNTARY_THRESHOLD_SAR == 187_500

    def test_corpus_still_states_both_thresholds(self):
        zatca = "\n".join(d.text for d in load_corpus() if d.domain == "zatca.gov.sa")
        assert f"{VAT_MANDATORY_THRESHOLD_SAR:,}" in zatca
        assert f"{VAT_VOLUNTARY_THRESHOLD_SAR:,}" in zatca

    def test_source_wording_justifies_strict_greater_than(self):
        """The boundary is `>` because the source says "exceed", not "at least".

        If ZATCA ever rewords this to "SAR 375,000 or more", the comparison in
        assess_vat becomes wrong by one riyal at the boundary and this test is
        what surfaces it.
        """
        zatca = "\n".join(d.text for d in load_corpus() if d.domain == "zatca.gov.sa")
        assert "exceed SAR 375,000" in zatca

    def test_cited_source_is_allowlisted_and_citable(self):
        assert is_citable(tax_financial.VAT_THRESHOLD_SOURCE_URL)

    def test_source_is_not_the_implementing_regulations(self):
        """Phase 0 finding: the regulations never state the number."""
        assert "Implmenting" not in tax_financial.VAT_THRESHOLD_SOURCE_URL
        assert "Implementing" not in tax_financial.VAT_THRESHOLD_SOURCE_URL


class TestNoLlmInTheDecisionPath:
    def test_module_imports_no_llm_client(self):
        source = inspect.getsource(tax_financial)
        for forbidden in ("openai", "langchain", "anthropic", "httpx", "requests"):
            assert forbidden not in source, f"{forbidden} must not reach the tax core"

    def test_assessment_is_pure(self):
        """Same input, same output, no hidden state."""
        first = assess_vat(450_000)
        second = assess_vat(450_000)
        assert first == second


class TestBoundaries:
    @pytest.mark.parametrize(
        "revenue,expected",
        [
            (450_000, "mandatory_registration_likely"),
            (375_000.01, "mandatory_registration_likely"),
            (375_000, "voluntary_registration_possible"),  # "exceed" — not crossed
            (374_999.99, "voluntary_registration_possible"),
            (187_500.01, "voluntary_registration_possible"),
            (187_500, "registration_not_required"),  # "exceed" — not crossed
            (100_000, "registration_not_required"),
            (0, "registration_not_required"),
        ],
    )
    def test_result_at_and_around_each_threshold(self, revenue, expected):
        assert assess_vat(revenue)["result"] == expected

    def test_exactly_mandatory_threshold_is_not_mandatory(self):
        """The single most likely off-by-one in the whole system."""
        assessment = assess_vat(VAT_MANDATORY_THRESHOLD_SAR)
        assert assessment["registration_required"] is False
        assert assessment["result"] == "voluntary_registration_possible"

    def test_one_riyal_above_is_mandatory(self):
        assert assess_vat(VAT_MANDATORY_THRESHOLD_SAR + 1)["registration_required"] is True


class TestMissingAndInvalidInput:
    def test_missing_revenue_is_unknown_not_zero(self):
        """Absent data is not a small business."""
        assessment = assess_vat(None)
        assert assessment["result"] == "unknown_revenue_not_provided"
        assert assessment["registration_required"] is None

    def test_nan_is_treated_as_missing(self):
        assert assess_vat(float("nan"))["result"] == "unknown_revenue_not_provided"

    def test_infinity_is_treated_as_missing(self):
        assert assess_vat(float("inf"))["result"] == "unknown_revenue_not_provided"

    def test_negative_revenue_raises(self):
        with pytest.raises(ValueError):
            assess_vat(-1)

    def test_integer_and_float_agree(self):
        assert assess_vat(450_000) == assess_vat(450_000.0)


class TestEvidence:
    def test_evidence_cites_zatca_with_an_explicit_url(self):
        evidence = vat_evidence(assess_vat(450_000))
        assert evidence["source_entity"] == "ZATCA"
        assert is_citable(evidence["source_url"])
        assert evidence["has_explicit_url"] is True
        assert evidence["confidence"] == "HIGH"

    def test_evidence_reproduces_thresholds_exactly(self):
        """§2.2 rule 5: never round or paraphrase a numeric threshold."""
        evidence = vat_evidence(assess_vat(450_000))
        assert "375,000" in evidence["claim"]
        assert "187,500" in evidence["claim"]

    def test_evidence_validates_as_an_Evidence_model(self):
        from app.state import Evidence

        model = Evidence.model_validate(vat_evidence(assess_vat(450_000)))
        assert model.confidence == "HIGH"

    def test_missing_revenue_evidence_says_so(self):
        evidence = vat_evidence(assess_vat(None))
        assert "not provided" in evidence["claim"]


class TestNode:
    def test_node_returns_a_partial_update_only(self):
        update = tax_financial_node({"expected_annual_revenue_sar": 450_000})
        assert set(update) == {
            "vat_registration_required",
            "requirements",
            "evidence_log",
            "decision_log",
        }

    def test_node_marks_registration_missing_when_mandatory(self):
        update = tax_financial_node({"expected_annual_revenue_sar": 450_000})
        assert update["vat_registration_required"] is True
        assert update["requirements"][0]["status"] == "missing"

    def test_node_marks_satisfied_when_below_threshold(self):
        update = tax_financial_node({"expected_annual_revenue_sar": 100_000})
        assert update["vat_registration_required"] is False
        assert update["requirements"][0]["status"] == "satisfied"

    def test_node_marks_unverified_when_revenue_absent(self):
        update = tax_financial_node({})
        assert update["vat_registration_required"] is None
        assert update["requirements"][0]["status"] == "unverified"

    def test_node_logs_that_it_is_deterministic(self):
        update = tax_financial_node({"expected_annual_revenue_sar": 450_000})
        assert "no LLM in the decision path" in update["decision_log"][0]

    def test_node_update_merges_into_case_state(self):
        from app.state import CaseState, merge_case_state

        state = CaseState(case_id="c1", goal="open a cafe")
        merged = merge_case_state(
            state, tax_financial_node({"expected_annual_revenue_sar": 450_000})
        )
        assert merged.vat_registration_required is True
        assert merged.requirements[0].name == "VAT registration (ZATCA)"
        assert len(merged.decision_log) == 1


def test_tax_wrapper_prompt_forbids_recomputation():
    from app.agents.prompts import TAX_EXPLANATION_WRAPPER

    assert "Do NOT recompute" in TAX_EXPLANATION_WRAPPER
    assert "Source: ZATCA." in TAX_EXPLANATION_WRAPPER
