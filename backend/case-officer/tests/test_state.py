"""Tests for the CaseState schema (implementation plan §1)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.state import (
    FRONTEND_MIRRORED_FIELDS,
    CaseState,
    Conflict,
    ConflictResolution,
    Evidence,
    RequirementItem,
    merge_case_state,
)


def _evidence(**overrides) -> dict:
    base = {
        "claim": "A commercial registration is required.",
        "source_entity": "Saudi Business Center",
        "source_url": "https://business.sa/en/services/commercial-registration",
        "retrieved_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
        "confidence": "HIGH",
        "has_explicit_url": True,
    }
    base.update(overrides)
    return base


class TestEvidence:
    def test_accepts_an_allowlisted_url(self):
        assert Evidence.model_validate(_evidence()).confidence == "HIGH"

    def test_rejects_a_non_allowlisted_url(self):
        """Constructing evidence citing a consultancy blog is a programming error."""
        with pytest.raises(ValidationError, match="not on the allowlist"):
            Evidence.model_validate(_evidence(source_url="https://astrolabs.com/guide"))

    def test_rejects_a_suffix_confusion_url(self):
        with pytest.raises(ValidationError):
            Evidence.model_validate(_evidence(source_url="https://evilbalady.gov.sa/x"))

    def test_allows_a_blank_url(self):
        """A blank URL is precisely what the Verifier looks for and rejects."""
        model = Evidence.model_validate(_evidence(source_url="", has_explicit_url=False))
        assert model.has_explicit_url is False

    def test_confidence_is_constrained(self):
        with pytest.raises(ValidationError):
            Evidence.model_validate(_evidence(confidence="VERY_HIGH"))

    def test_retrieval_path_is_optional_and_typed(self):
        assert Evidence.model_validate(_evidence()).retrieval_path is None
        model = Evidence.model_validate(_evidence(retrieval_path="corpus_fallback"))
        assert model.retrieval_path == "corpus_fallback"
        with pytest.raises(ValidationError):
            Evidence.model_validate(_evidence(retrieval_path="telepathy"))


class TestRequirementItem:
    def test_status_is_constrained(self):
        with pytest.raises(ValidationError):
            RequirementItem.model_validate({"name": "CR", "status": "probably_fine"})

    def test_evidence_is_optional(self):
        item = RequirementItem.model_validate({"name": "CR", "status": "unverified"})
        assert item.evidence is None


class TestCaseState:
    def test_defaults_are_empty_not_none(self):
        state = CaseState(case_id="c1", goal="open a cafe")
        assert state.requirements == []
        assert state.evidence_log == []
        assert state.conflicts == []
        assert state.decision_log == []
        assert state.readiness_pct == 0
        assert state.approval_stage == "none"

    def test_approval_stage_is_constrained(self):
        with pytest.raises(ValidationError):
            CaseState(case_id="c1", goal="g", approval_stage="approved_ish")

    def test_has_open_conflict(self):
        state = CaseState(case_id="c1", goal="g")
        assert state.has_open_conflict is False

        conflict = Conflict(
            conflict_id="conf1",
            field="area_sqm",
            field_label="Premises area (sqm)",
            stated_value=120,
            stated_source="Intake form",
            document_value=95,
            document_source="lease.pdf",
        )
        state = state.model_copy(update={"conflicts": [conflict]})
        assert state.has_open_conflict is True

        resolved = conflict.model_copy(
            update={
                "status": "resolved",
                "resolution": ConflictResolution(
                    accepted="document",
                    accepted_value=95,
                    resolved_at=datetime.now(timezone.utc),
                ),
            }
        )
        state = state.model_copy(update={"conflicts": [resolved]})
        assert state.has_open_conflict is False

    def test_frontend_mirrored_fields_all_exist(self):
        for field in FRONTEND_MIRRORED_FIELDS:
            assert field in CaseState.model_fields, f"{field} missing from CaseState"

    def test_backend_only_fields_are_optional(self):
        """Additive fields must not break the Phase A frontend contract."""
        extra = set(CaseState.model_fields) - FRONTEND_MIRRORED_FIELDS
        assert extra, "expected some backend-only intake fields"
        for name in extra:
            field = CaseState.model_fields[name]
            assert not field.is_required(), f"{name} is additive but required"

    def test_serialises_with_only_mirrored_fields_when_asked(self):
        state = CaseState(case_id="c1", goal="g", business_category="food_beverage_fixed")
        payload = state.model_dump(include=set(FRONTEND_MIRRORED_FIELDS))
        assert set(payload) == FRONTEND_MIRRORED_FIELDS


class TestMerge:
    def test_partial_update_leaves_other_fields_intact(self):
        state = CaseState(case_id="c1", goal="g", city="Riyadh")
        merged = merge_case_state(state, {"readiness_pct": 42})
        assert merged.readiness_pct == 42
        assert merged.city == "Riyadh"
        assert merged.goal == "g"

    def test_decision_log_appends_rather_than_replaces(self):
        """A node overwriting the trace would destroy the audit record."""
        state = CaseState(case_id="c1", goal="g", decision_log=["first"])
        merged = merge_case_state(state, {"decision_log": ["second"]})
        assert merged.decision_log == ["first", "second"]

    def test_unknown_field_is_rejected(self):
        state = CaseState(case_id="c1", goal="g")
        with pytest.raises(KeyError, match="unknown CaseState field"):
            merge_case_state(state, {"favourite_colour": "sage"})

    def test_merge_returns_a_new_object(self):
        state = CaseState(case_id="c1", goal="g")
        merged = merge_case_state(state, {"readiness_pct": 10})
        assert state.readiness_pct == 0
        assert merged is not state

    def test_invalid_value_is_rejected_at_merge_time(self):
        state = CaseState(case_id="c1", goal="g")
        with pytest.raises(ValidationError):
            merge_case_state(state, {"approval_stage": "nonsense"})
