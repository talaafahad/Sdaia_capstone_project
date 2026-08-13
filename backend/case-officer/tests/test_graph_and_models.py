"""Graph structure, state reducers, model assignments and artifact assembly."""

import pytest

from app.agents.documentation import (
    AI_ESTIMATE_LABEL,
    build_evidence_report,
    build_fee_estimate,
    documentation_node,
)
from app.agents.regulation_router import nodes_for_category
from app.graph import (
    build_graph,
    merge_dicts,
    merge_evidence,
    merge_requirements,
    route_after_intake,
    route_after_verifier,
)
from app.llm import MODEL_ASSIGNMENTS, ULTRA, model_for, model_report


class TestGraphStructure:
    def test_all_nodes_present(self):
        graph = build_graph()
        nodes = {n for n in graph.get_graph().nodes if not n.startswith("__")}
        assert nodes == {
            "intake_planner",
            "regulation_router",
            "municipal_location",
            "tax_financial",
            "verifier",
            "conflict_gate",
            "approval_gate",
            "documentation",
        }

    def test_branch_routing(self):
        assert route_after_intake({"business_category": "food_beverage_fixed"}) == "food_business"
        assert route_after_intake({"business_category": "professional_office"}) == "general_business"

    def test_verifier_routes_to_conflict_gate_when_open(self):
        state = {"conflicts": [{"status": "open"}]}
        assert route_after_verifier(state) == "conflict_gate"

    def test_verifier_routes_to_approval_when_clear(self):
        assert route_after_verifier({"conflicts": []}) == "approval_gate"
        assert route_after_verifier({"conflicts": [{"status": "resolved"}]}) == "approval_gate"


class TestReducers:
    def test_requirements_merge_dedupes_by_name(self):
        left = [{"name": "CR", "status": "missing"}]
        right = [{"name": "CR", "status": "satisfied"}, {"name": "VAT", "status": "missing"}]
        merged = merge_requirements(left, right)
        assert len(merged) == 2
        assert next(r for r in merged if r["name"] == "CR")["status"] == "satisfied"

    def test_evidence_merge_dedupes_by_url_and_claim(self):
        item = {"source_url": "https://zatca.gov.sa/x", "claim": "c"}
        assert len(merge_evidence([item], [item])) == 1

    def test_parallel_branches_do_not_erase_each_other(self):
        """municipal_location and tax_financial both append in parallel."""
        municipal = [{"name": "Municipal licence", "status": "missing"}]
        tax = [{"name": "VAT registration (ZATCA)", "status": "missing"}]
        merged = merge_requirements(municipal, tax)
        assert len(merged) == 2

    def test_dict_merge_unions(self):
        assert merge_dicts({"a": "1"}, {"b": "2"}) == {"a": "1", "b": "2"}

    def test_dict_merge_handles_none(self):
        assert merge_dicts(None, {"b": "2"}) == {"b": "2"}


class TestTopicNodeSelection:
    def test_food_business_includes_food_safety(self):
        assert "food_safety" in nodes_for_category("food_beverage_fixed")

    def test_office_excludes_food_safety_includes_ip(self):
        nodes = nodes_for_category("professional_office")
        assert "food_safety" not in nodes
        assert "intellectual_property" in nodes

    def test_food_truck_skips_employment(self):
        """A mobile cart licence does not presuppose employees (section 10)."""
        assert "employment_social_insurance" not in nodes_for_category("food_truck_mobile")

    def test_every_category_gets_cr_and_vat(self):
        for category in ("food_beverage_fixed", "professional_office", "nonprofit_org"):
            nodes = nodes_for_category(category)
            assert "commercial_registration" in nodes
            assert "vat_registration" in nodes

    def test_municipal_is_never_a_router_node(self):
        """Balady belongs to the A2A service, not the Regulation Router."""
        for category in ("food_beverage_fixed", "food_truck_mobile", "professional_office"):
            assert "municipal_requirements" not in nodes_for_category(category)


class TestModelAssignments:
    def test_citation_critical_nodes_run_on_ultra(self):
        for node in ("commercial_registration", "vat_registration", "verifier"):
            assert model_for(node) == ULTRA, f"{node} must run on the strongest model"

    def test_verifier_has_the_documented_fallback(self):
        """Handoff section 1: drop the Verifier to Super under contention."""
        assert MODEL_ASSIGNMENTS["verifier"].fallback is not None

    def test_intake_uses_the_small_model(self):
        assert "nano" in model_for("intake_planner")

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MODEL_VERIFIER", "some/other-model")
        assert model_for("verifier") == "some/other-model"

    def test_unknown_node_raises(self):
        with pytest.raises(KeyError):
            model_for("no_such_node")

    def test_report_covers_every_node(self):
        report = model_report()
        assert {r["node"] for r in report} == set(MODEL_ASSIGNMENTS)
        assert all(r["why"] for r in report)


class TestDocumentationArtifacts:
    def test_unsourced_fee_lines_are_labelled(self):
        fees = build_fee_estimate({"budget_sar": 350000})
        unofficial = [i for i in fees["line_items"] if not i["is_official"]]
        assert unofficial, "expected estimated lines"
        assert AI_ESTIMATE_LABEL.startswith("AI ESTIMATE")

    def test_unverified_municipal_fee_is_not_invented(self):
        fees = build_fee_estimate({})
        licence = next(i for i in fees["line_items"] if "Municipal" in i["label"])
        assert licence["amount_sar"] == 0
        assert licence["is_official"] is False

    def test_evidence_report_shows_rejected_rows(self):
        rows = build_evidence_report(
            [
                {"claim": "a", "source_url": "https://zatca.gov.sa/x", "has_explicit_url": True,
                 "confidence": "HIGH", "source_entity": "ZATCA", "retrieved_at": "t"},
                {"claim": "b", "source_url": "", "has_explicit_url": False,
                 "confidence": "LOW", "source_entity": "?", "retrieved_at": "t",
                 "rejection_reason": "No source URL."},
            ]
        )
        assert [r["verdict"] for r in rows] == ["accepted", "rejected"]
        assert rows[1]["reason"]

    def test_documentation_skipped_without_approval(self):
        from app.graph import node_documentation

        update = node_documentation({"approval_stage": "none"})
        assert "artifacts" not in update
        assert "not approved" in update["decision_log"][0]

    def test_packet_flags_an_unresolved_conflict(self, monkeypatch):
        monkeypatch.setattr("app.agents.documentation.llm_available", lambda: False)
        state = {
            "requirements": [],
            "evidence_log": [],
            "conflicts": [
                {
                    "conflict_id": "c1",
                    "status": "open",
                    "stated_value": 120,
                    "document_value": 95,
                }
            ],
        }
        artifacts = documentation_node(state)["artifacts"]
        area = next(
            f for f in artifacts["application_packet"]["fields"] if "area" in f["label"].lower()
        )
        assert "UNRESOLVED" in area["value"]

    def test_packet_disclaimer_never_claims_approval(self, monkeypatch):
        monkeypatch.setattr("app.agents.documentation.llm_available", lambda: False)
        artifacts = documentation_node({"requirements": [], "evidence_log": []})["artifacts"]
        disclaimer = artifacts["application_packet"]["disclaimer"]
        assert "NOT VERIFIED" in disclaimer
        assert "confers no approval" in disclaimer

    def test_six_artifact_sections_present(self, monkeypatch):
        monkeypatch.setattr("app.agents.documentation.llm_available", lambda: False)
        artifacts = documentation_node({"requirements": [], "evidence_log": []})["artifacts"]
        for section in (
            "journey",
            "checklist",
            "evidence_report",
            "fee_estimate",
            "application_packet",
            "decision_log",
        ):
            assert section in artifacts
