"""Tests for the Verifier — the hallucination firewall (implementation plan §2.5).

The deterministic checks are the ones that must never depend on a model being
available or cooperative, so they are tested directly.
"""

from datetime import datetime, timezone

from app.agents.verifier import (
    compute_readiness,
    detect_area_conflict,
    deterministic_verdict,
    verifier_node,
    verify_evidence,
)

GOOD_URL = "https://zatca.gov.sa/en/eServices/Pages/eServices_002.aspx"


def _ev(**over) -> dict:
    base = {
        "claim": "Businesses must register for VAT.",
        "source_entity": "ZATCA",
        "source_url": GOOD_URL,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "confidence": "HIGH",
        "has_explicit_url": True,
    }
    base.update(over)
    return base


class TestDeterministicChecks:
    def test_blank_url_is_rejected_without_a_model(self):
        verdict = deterministic_verdict(_ev(source_url=""), {})
        assert verdict is not None
        assert verdict[0] is False
        assert "No source URL" in verdict[1]

    def test_off_allowlist_url_is_rejected_without_a_model(self):
        verdict = deterministic_verdict(_ev(source_url="https://astrolabs.com/x"), {})
        assert verdict is not None and verdict[0] is False

    def test_numeric_claim_absent_from_passage_is_rejected(self):
        """The Phase 0 trap: a passage naming a threshold without stating it."""
        passages = {
            GOOD_URL: "the Mandatory Registration Threshold detailed in the Agreement"
        }
        verdict = deterministic_verdict(
            _ev(claim="Businesses with supplies over SAR 375,000 must register."), passages
        )
        assert verdict is not None
        assert verdict[0] is False
        assert "375000" in verdict[1] or "375,000" in verdict[1]

    def test_numeric_claim_present_in_passage_is_not_auto_rejected(self):
        passages = {GOOD_URL: "Individuals whose annual revenues exceed SAR 375,000."}
        verdict = deterministic_verdict(
            _ev(claim="Businesses with revenue over SAR 375,000 must register."), passages
        )
        assert verdict is None  # deferred to the model, not rejected outright

    def test_small_numbers_do_not_trigger_the_numeric_check(self):
        """Step counts and years must not be treated as sourced figures."""
        passages = {GOOD_URL: "Follow the steps to register."}
        verdict = deterministic_verdict(
            _ev(claim="There are 3 steps to registration."), passages
        )
        assert verdict is None


class TestRelevantExcerpt:
    """Regression: the Verifier was shown the wrong slice of long passages.

    One retrieved source is a 113k-char regulation PDF. Trimming from the start
    handed the Verifier a cover page, so it rejected well-supported claims for
    want of evidence it had never been shown.
    """

    def test_finds_the_supporting_window_in_a_long_passage(self):
        from app.agents.verifier import relevant_excerpt

        passage = (
            "Cover page and preamble. " * 400
            + "A resident person whose taxable supplies exceed SAR 187,500 over "
            "12 months may apply for voluntary registration."
            + " Appendix and annexes. " * 400
        )
        claim = "Taxable supplies exceeding SAR 187,500 allow voluntary registration."
        excerpt = relevant_excerpt(claim, passage, width=400)
        assert "187,500" in excerpt

    def test_short_passage_is_returned_whole(self):
        from app.agents.verifier import relevant_excerpt

        assert relevant_excerpt("claim", "short text") == "short text"

    def test_empty_passage_is_safe(self):
        from app.agents.verifier import relevant_excerpt

        assert relevant_excerpt("claim", "") == ""

    def test_numerals_are_weighted_over_words(self):
        from app.agents.verifier import relevant_excerpt

        passage = (
            "registration registration registration " * 60
            + " the threshold is SAR 375,000 exactly "
            + "registration registration registration " * 60
        )
        excerpt = relevant_excerpt("threshold of SAR 375,000", passage, width=200)
        assert "375,000" in excerpt


class TestVerdictParsing:
    """Regression: a bare JSON array crashed the audit and rejected a whole case."""

    def _run(self, monkeypatch, payload):
        monkeypatch.setattr("app.agents.verifier.llm_available", lambda: True)
        monkeypatch.setattr("app.agents.verifier.call_json", lambda *a, **k: payload)
        passages = {GOOD_URL: "Businesses must register for VAT."}
        return verify_evidence([_ev()], passages)

    def test_object_shape_is_accepted(self, monkeypatch):
        accepted, rejected, _ = self._run(
            monkeypatch, {"verdicts": [{"index": 0, "accepted": True, "reason": "ok"}]}
        )
        assert len(accepted) == 1 and not rejected

    def test_bare_array_shape_is_accepted(self, monkeypatch):
        accepted, _, _ = self._run(
            monkeypatch, [{"index": 0, "accepted": True, "reason": "ok"}]
        )
        assert len(accepted) == 1

    def test_array_without_index_falls_back_to_position(self, monkeypatch):
        accepted, _, _ = self._run(monkeypatch, [{"accepted": True, "reason": "ok"}])
        assert len(accepted) == 1

    def test_unparseable_shape_rejects_rather_than_crashing(self, monkeypatch):
        accepted, rejected, _ = self._run(monkeypatch, "not json at all")
        assert accepted == [] and len(rejected) == 1

    def test_model_rejection_is_honoured(self, monkeypatch):
        accepted, rejected, _ = self._run(
            monkeypatch, {"verdicts": [{"index": 0, "accepted": False, "reason": "unsupported"}]}
        )
        assert accepted == []
        assert rejected[0]["rejection_reason"] == "unsupported"


class TestVerifyEvidence:
    def test_unverifiable_claims_are_rejected_when_no_model(self, monkeypatch):
        monkeypatch.setattr("app.agents.verifier.llm_available", lambda: False)
        accepted, rejected, _ = verify_evidence([_ev()], {GOOD_URL: "some text"})
        assert accepted == []
        assert len(rejected) == 1
        assert rejected[0]["has_explicit_url"] is False

    def test_rejection_sets_a_reason(self, monkeypatch):
        monkeypatch.setattr("app.agents.verifier.llm_available", lambda: False)
        _, rejected, _ = verify_evidence([_ev(source_url="")], {})
        assert rejected[0]["rejection_reason"]

    def test_decision_log_reports_counts(self, monkeypatch):
        monkeypatch.setattr("app.agents.verifier.llm_available", lambda: False)
        _, _, decisions = verify_evidence([_ev(), _ev(source_url="")], {})
        assert any("accepted" in d and "rejected" in d for d in decisions)


class TestDiscrepancy:
    def test_conflict_when_values_differ(self):
        conflict = detect_area_conflict(
            {"area_sqm_stated": 120, "area_sqm_from_document": 95}
        )
        assert conflict is not None
        assert conflict["stated_value"] == 120
        assert conflict["document_value"] == 95
        assert conflict["status"] == "open"

    def test_no_conflict_when_values_match(self):
        assert detect_area_conflict(
            {"area_sqm_stated": 95, "area_sqm_from_document": 95}
        ) is None

    def test_no_conflict_when_document_missing(self):
        assert detect_area_conflict({"area_sqm_stated": 120}) is None

    def test_no_conflict_when_stated_missing(self):
        assert detect_area_conflict({"area_sqm_from_document": 95}) is None

    def test_tiny_difference_still_conflicts(self):
        """Section 2.5: 'if they differ by any amount' — no tolerance band."""
        conflict = detect_area_conflict(
            {"area_sqm_stated": 120, "area_sqm_from_document": 119.9}
        )
        assert conflict is not None


class TestReadiness:
    def test_zero_with_no_requirements(self):
        assert compute_readiness([], False) == 0

    def test_frozen_readiness_is_capped(self):
        requirements = [{"status": "satisfied"} for _ in range(4)]
        assert compute_readiness(requirements, False) == 100
        assert compute_readiness(requirements, True) == 68

    def test_unverified_requirements_score_nothing(self):
        assert compute_readiness([{"status": "unverified"}], False) == 0


class TestNode:
    def test_node_strips_rejected_citations_from_requirements(self, monkeypatch):
        monkeypatch.setattr("app.agents.verifier.llm_available", lambda: False)
        state = {
            "evidence_log": [_ev(source_url="")],
            "requirements": [
                {"name": "CR", "status": "missing", "evidence": _ev(source_url="")}
            ],
            "conflicts": [],
        }
        update = verifier_node(state, {})
        requirement = update["requirements"][0]
        assert requirement["evidence"] is None
        assert requirement["status"] == "unverified"

    def test_node_emits_conflict_and_freezes_readiness(self, monkeypatch):
        monkeypatch.setattr("app.agents.verifier.llm_available", lambda: False)
        state = {
            "evidence_log": [],
            "requirements": [{"name": "CR", "status": "satisfied"}],
            "conflicts": [],
            "area_sqm_stated": 120,
            "area_sqm_from_document": 95,
        }
        update = verifier_node(state, {})
        assert len(update["conflicts"]) == 1
        assert update["readiness_pct"] <= 68
        assert any("DISCREPANCY" in d for d in update["decision_log"])

    def test_node_does_not_duplicate_an_existing_conflict(self, monkeypatch):
        monkeypatch.setattr("app.agents.verifier.llm_available", lambda: False)
        existing = detect_area_conflict(
            {"area_sqm_stated": 120, "area_sqm_from_document": 95}
        )
        state = {
            "evidence_log": [],
            "requirements": [],
            "conflicts": [existing],
            "area_sqm_stated": 120,
            "area_sqm_from_document": 95,
        }
        update = verifier_node(state, {})
        assert len(update["conflicts"]) == 1
