"""Tests for the per-node system prompts.

Prompt scoping is easy to get subtly wrong, so the invariants that matter are
asserted rather than eyeballed.
"""

import pytest

from app.agents.prompts import (
    HARD_RULES,
    NODES,
    UnknownNode,
    build_system_prompt,
    domains_for,
)
from app.config.allowlist import CITABLE_DOMAINS, SEARCHABLE_DOMAINS

REGULATION_ROUTER_NODES = [
    n for n, node in NODES.items() if node.service == "case-officer"
]


class TestNodeRegistry:
    def test_every_node_domain_is_allowlisted(self):
        for node_id, node in NODES.items():
            for domain in node.domains:
                assert domain in SEARCHABLE_DOMAINS, f"{node_id} -> unlisted {domain}"

    def test_regulation_router_does_not_own_balady(self):
        """Section 2.3: the Municipal A2A service owns every Balady requirement."""
        for node_id in REGULATION_ROUTER_NODES:
            assert "balady.gov.sa" not in domains_for(node_id), (
                f"{node_id} must not retrieve Balady — the municipal service owns it"
            )

    def test_municipal_node_does_own_balady(self):
        assert "balady.gov.sa" in domains_for("municipal_requirements")

    def test_node_domains_do_not_overlap_across_services(self):
        """No page should be retrievable by two different owners."""
        case_officer: set[str] = set()
        municipal: set[str] = set()
        for node in NODES.values():
            (case_officer if node.service == "case-officer" else municipal).update(node.domains)
        assert not (case_officer & municipal)

    def test_unknown_node_raises(self):
        with pytest.raises(UnknownNode):
            build_system_prompt("no_such_node")


class TestHardRules:
    @pytest.mark.parametrize(
        "node_id", [n for n, node in NODES.items() if node.uses_retrieval]
    )
    def test_retrieval_nodes_carry_every_hard_rule(self, node_id):
        prompt = build_system_prompt(node_id, city="Riyadh", business_category="cafe")
        # The rules that section 2.2 makes non-negotiable.
        assert "Do NOT answer from your own" in prompt
        assert "You may ONLY cite pages from these domains" in prompt
        assert "no allowlisted source found" in prompt
        assert "HIGH only when the passage text explicitly states" in prompt
        assert "Never HIGH from inference" in prompt
        assert "Do not average, round, convert, or paraphrase numeric values" in prompt
        assert "Copy retrieved_at from the passage's own metadata" in prompt

    @pytest.mark.parametrize(
        "node_id", [n for n, node in NODES.items() if node.uses_retrieval]
    )
    def test_allowed_domains_are_rendered_not_left_as_placeholder(self, node_id):
        prompt = build_system_prompt(node_id)
        assert "{allowed_domains}" not in prompt
        for domain in domains_for(node_id):
            assert domain in prompt

    @pytest.mark.parametrize(
        "node_id", [n for n, node in NODES.items() if node.uses_retrieval]
    )
    def test_no_unrendered_template_fields_remain(self, node_id):
        """A leftover {placeholder} would reach the model as literal text."""
        prompt = build_system_prompt(node_id)
        assert "{" not in prompt and "}" not in prompt

    def test_prompt_never_leaks_a_domain_outside_its_scope(self):
        """The VAT node must not mention Balady or GOSI in its allowed set."""
        prompt = build_system_prompt("vat_registration", expected_annual_revenue_sar=450000)
        allowed_line = [
            line for line in prompt.splitlines() if line.startswith("Allowed domains:")
        ]
        assert allowed_line and allowed_line[-1].strip() == "Allowed domains: zatca.gov.sa"


class TestScopeSpecifics:
    def test_vat_node_encodes_the_implementing_regulations_trap(self):
        """The Phase 0 finding must survive in the prompt, not just in a test."""
        prompt = build_system_prompt("vat_registration", expected_annual_revenue_sar=450000)
        assert "Mandatory Registration Threshold detailed in the Agreement" in prompt
        assert "not its value" in prompt

    def test_vat_node_disclaims_the_decision(self):
        """Section 2.4 keeps the registration decision out of LLM hands."""
        prompt = build_system_prompt("vat_registration")
        assert "You are NOT the decision-maker" in prompt

    def test_food_safety_node_warns_against_manufacture_analogy(self):
        prompt = build_system_prompt("food_safety", business_category="cafe", city="Riyadh")
        assert "MANUFACTURE" in prompt
        assert "by analogy" in prompt

    def test_municipal_node_carries_the_mandatory_approval_line(self):
        prompt = build_system_prompt("municipal_requirements", city="Riyadh")
        assert (
            "Municipal approval status: NOT VERIFIED — approval can only be confirmed by"
            in prompt
        )
        assert "NEVER" in prompt

    def test_competitor_node_forbids_judgment_and_carries_the_label(self):
        prompt = build_system_prompt("competitor_lookup")
        assert "AI ESTIMATE — competitor count only, not a suitability judgment." in prompt
        assert "FORBIDDEN" in prompt
        assert "never estimate a count from your own" in prompt
        assert "saturation assessment" in prompt

    def test_competitor_node_cites_no_domains(self):
        assert domains_for("competitor_lookup") == ()
        prompt = build_system_prompt("competitor_lookup")
        # It takes no web context, so the retrieval hard rules would be noise.
        assert "You may ONLY cite pages from these domains" not in prompt

    def test_employment_node_caps_mudad_at_medium(self):
        prompt = build_system_prompt("employment_social_insurance", employee_count=4)
        assert "mudad.com.sa" in prompt
        assert "capped at\nMEDIUM — never HIGH" in prompt

    def test_ip_node_flags_optionality(self):
        prompt = build_system_prompt("intellectual_property")
        assert "typically OPTIONAL" in prompt


class TestMissingParameters:
    def test_missing_field_degrades_rather_than_raising(self):
        """A blank optional intake field must not crash the graph."""
        prompt = build_system_prompt("employment_social_insurance")
        assert "(not provided)" in prompt

    def test_empty_string_is_treated_as_missing(self):
        prompt = build_system_prompt("commercial_registration", city="")
        assert "(not provided)" in prompt

    def test_supplied_values_are_interpolated(self):
        prompt = build_system_prompt(
            "commercial_registration",
            business_category="food_beverage_fixed",
            city="Riyadh",
            applicant_status="saudi_national",
        )
        assert "food_beverage_fixed" in prompt
        assert "Riyadh" in prompt
        assert "saudi_national" in prompt


def test_hard_rules_are_shared_not_duplicated():
    """One copy of the rules; drift across seven prompts is the failure mode."""
    assert HARD_RULES.count("HARD RULES") == 1
    for node_id, node in NODES.items():
        if node.uses_retrieval:
            assert "HARD RULES" not in node.scope, f"{node_id} re-states the rules"


def test_citable_domains_only_in_retrieval_nodes():
    """Every domain a node may cite is tier-1 citable, not semi-official."""
    for node_id, node in NODES.items():
        for domain in node.domains:
            assert domain in CITABLE_DOMAINS, (
                f"{node_id} lists semi-official {domain} as a primary domain"
            )
