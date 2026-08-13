"""Tests for the MCP-auth-gated mock Balady submission (Phase 5, step 15).

The plan asks for both the unauthenticated-fails and authenticated-succeeds
cases to be tested explicitly, so both are here, along with the refusals that
matter more: submitting an unapproved case, or one with an open discrepancy.
"""

import pytest

from app.mcp.execution_adapter import (
    MOCK_NOTICE,
    NotAuthorised,
    PacketIncomplete,
    check_auth,
    submit_to_balady,
    validate_packet,
)

PACKET = {"target_agency": "Balady", "fields": [{"label": "City", "value": "Riyadh"}]}
APPROVED_STATE = {"case_id": "c1", "approval_stage": "proposal_approved", "conflicts": []}


@pytest.fixture
def secret(monkeypatch):
    from app.config.settings import settings

    monkeypatch.setattr(settings, "mcp_auth_secret", "test-secret-value")
    return "test-secret-value"


class TestAuth:
    def test_missing_token_is_refused(self, secret):
        with pytest.raises(NotAuthorised, match="missing authorization token"):
            check_auth(None)

    def test_empty_token_is_refused(self, secret):
        with pytest.raises(NotAuthorised):
            check_auth("")

    def test_wrong_token_is_refused(self, secret):
        with pytest.raises(NotAuthorised, match="invalid authorization token"):
            check_auth("not-the-secret")

    def test_correct_token_passes(self, secret):
        check_auth(secret)  # must not raise

    def test_unconfigured_secret_refuses_everything(self, monkeypatch):
        """A service with no secret must fail closed, not open."""
        from app.config.settings import settings

        monkeypatch.setattr(settings, "mcp_auth_secret", None)
        with pytest.raises(NotAuthorised, match="not configured"):
            check_auth("anything")


class TestPacketValidation:
    def test_unapproved_case_is_refused(self):
        with pytest.raises(PacketIncomplete, match="approval gate"):
            validate_packet(PACKET, {"approval_stage": "none", "conflicts": []})

    def test_open_conflict_blocks_submission(self):
        state = {
            "approval_stage": "proposal_approved",
            "conflicts": [{"conflict_id": "c", "status": "open"}],
        }
        with pytest.raises(PacketIncomplete, match="unresolved discrepancy"):
            validate_packet(PACKET, state)

    def test_resolved_conflict_does_not_block(self):
        state = {
            "approval_stage": "proposal_approved",
            "conflicts": [{"conflict_id": "c", "status": "resolved"}],
        }
        validate_packet(PACKET, state)  # must not raise

    def test_empty_packet_is_refused(self):
        with pytest.raises(PacketIncomplete, match="no fields"):
            validate_packet({"fields": []}, APPROVED_STATE)


class TestSubmission:
    def test_unauthenticated_submission_fails(self, secret):
        with pytest.raises(NotAuthorised):
            submit_to_balady(PACKET, APPROVED_STATE, None)

    def test_authenticated_submission_succeeds(self, secret):
        receipt = submit_to_balady(PACKET, APPROVED_STATE, secret)
        assert receipt.ok is True
        assert receipt.reference.startswith("MOCK-BLD-")
        assert receipt.is_mock is True

    def test_receipt_is_clearly_labelled_as_a_mock(self, secret):
        """A demo that looked like it filed a real application would be worse
        than one that plainly does not."""
        receipt = submit_to_balady(PACKET, APPROVED_STATE, secret)
        assert receipt.notice == MOCK_NOTICE
        assert "no application was filed" in receipt.notice
        assert "MOCK" in receipt.reference

    def test_auth_is_checked_before_packet_validation(self, secret):
        """An unauthorised caller must not learn whether the packet was valid."""
        with pytest.raises(NotAuthorised):
            submit_to_balady({"fields": []}, {"approval_stage": "none"}, None)
