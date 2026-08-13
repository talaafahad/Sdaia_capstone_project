"""Guardrails for the Municipal & Location service (implementation plan §2.3)."""

import pytest

from app.allowlist import CITABLE_DOMAINS, entity_for, is_citable, registered_domain
from app.competitor_lookup import AI_ESTIMATE_LABEL, CompetitorResult
from app.prompts import MANDATORY_APPROVAL_LINE, build_system_prompt


class TestNarrowAllowlist:
    def test_only_municipal_domains_are_citable(self):
        assert CITABLE_DOMAINS == {"balady.gov.sa", "momah.gov.sa"}

    def test_zatca_is_not_citable_here(self):
        """The service boundary is the guardrail: this node cannot cite VAT."""
        assert is_citable("https://zatca.gov.sa/en/vat") is False

    def test_balady_subdomain_is_citable(self):
        assert registered_domain("https://new.balady.gov.sa/en/services/x") == "balady.gov.sa"

    def test_suffix_confusion_rejected(self):
        assert is_citable("https://evilbalady.gov.sa/x") is False

    def test_credential_spoof_rejected(self):
        assert is_citable("https://balady.gov.sa@evil.com/") is False

    def test_entity_names(self):
        assert entity_for("https://balady.gov.sa/x") == "Balady"


class TestPrompts:
    def test_municipal_prompt_carries_the_mandatory_line(self):
        prompt = build_system_prompt("municipal_requirements", city="Riyadh")
        assert "Municipal approval status: NOT VERIFIED" in prompt
        assert "NEVER" in prompt

    def test_municipal_prompt_lists_only_its_own_domains(self):
        prompt = build_system_prompt("municipal_requirements")
        assert "balady.gov.sa" in prompt
        assert "zatca.gov.sa" not in prompt

    def test_competitor_prompt_forbids_judgment(self):
        prompt = build_system_prompt("competitor_lookup")
        assert AI_ESTIMATE_LABEL in prompt
        assert "FORBIDDEN" in prompt
        assert "saturation assessment" in prompt

    def test_competitor_prompt_has_no_web_citation_rules(self):
        prompt = build_system_prompt("competitor_lookup")
        assert "You may ONLY cite pages from these domains" not in prompt

    def test_missing_fields_degrade(self):
        assert "(not provided)" in build_system_prompt("municipal_requirements")

    def test_unknown_node_raises(self):
        with pytest.raises(KeyError):
            build_system_prompt("no_such_node")


class TestCompetitorResultShape:
    def test_label_is_attached_by_default(self):
        result = CompetitorResult(ok=True, count=3, radius_m=500, source="OSM")
        assert result.label == AI_ESTIMATE_LABEL

    def test_failure_reports_no_count(self):
        result = CompetitorResult(
            ok=False, count=None, radius_m=500, source="OSM", reason="district_not_geocoded"
        )
        assert result.count is None
        assert result.ok is False

    def test_approval_line_is_a_constant_not_model_output(self):
        """Appended by code so it is present regardless of what a model returns."""
        assert MANDATORY_APPROVAL_LINE.startswith("Municipal approval status: NOT VERIFIED")
