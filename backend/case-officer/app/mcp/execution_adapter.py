"""Mock Balady submission behind MCP auth (implementation plan Phase 5, step 15).

This is the only tool in the system with side-effect semantics, so it is the one
that gets an auth gate. The secret is self-issued (``MCP_AUTH_SECRET``), not a
third-party credential.

Nothing here contacts Balady. It is a mock execution adapter: it validates the
packet, checks authorisation, and returns a synthetic reference number that is
clearly marked as such. A demo that appeared to file a real government
application would be worse than one that plainly does not.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config.settings import settings


class NotAuthorised(PermissionError):
    """Raised when the submission tool is called without a valid token."""


class PacketIncomplete(ValueError):
    """Raised when the packet is missing something required for submission."""


@dataclass(frozen=True)
class SubmissionReceipt:
    ok: bool
    reference: str
    submitted_at: str
    target_agency: str
    is_mock: bool
    notice: str


MOCK_NOTICE = (
    "MOCK SUBMISSION — no application was filed with any government agency. "
    "This reference number is synthetic and confers no status, approval, or "
    "queue position."
)


def check_auth(token: str | None) -> None:
    """Constant-time comparison against the self-issued secret."""
    expected = (settings.mcp_auth_secret or "").strip()
    if not expected:
        raise NotAuthorised("MCP_AUTH_SECRET is not configured on this service")
    if not token:
        raise NotAuthorised("missing authorization token")
    if not hmac.compare_digest(token.strip(), expected):
        raise NotAuthorised("invalid authorization token")


def validate_packet(packet: dict, state: dict) -> None:
    """Refuse to submit a packet the case is not actually ready for."""
    if state.get("approval_stage") != "proposal_approved":
        raise PacketIncomplete(
            "case has not passed the human approval gate; submission refused"
        )
    open_conflicts = [c for c in (state.get("conflicts") or []) if c.get("status") == "open"]
    if open_conflicts:
        raise PacketIncomplete(
            f"{len(open_conflicts)} unresolved discrepancy(ies); submission refused "
            "until a human reconciles them"
        )
    if not (packet.get("fields") or []):
        raise PacketIncomplete("packet has no fields")


def submit_to_balady(packet: dict, state: dict, auth_token: str | None) -> SubmissionReceipt:
    """Auth-gated mock submission. Raises before doing anything if unauthorised."""
    check_auth(auth_token)
    validate_packet(packet, state)

    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(
        f"{state.get('case_id')}|{now.isoformat()}".encode("utf-8")
    ).hexdigest()[:10].upper()

    return SubmissionReceipt(
        ok=True,
        reference=f"MOCK-BLD-{digest}",
        submitted_at=now.isoformat(timespec="seconds"),
        target_agency=packet.get("target_agency") or "Balady",
        is_mock=True,
        notice=MOCK_NOTICE,
    )


def build_mcp_server():
    """Expose the adapter as a FastMCP server (course Day 3/4 pattern).

    Imported lazily so the FastAPI app does not require FastMCP at import time.
    """
    from fastmcp import FastMCP

    server = FastMCP("govflow-execution-adapter")

    @server.tool()
    def submit_balady_application(
        packet: dict, case_state: dict, auth_token: str
    ) -> dict:
        """Submit a prepared application packet (MOCK). Requires auth_token."""
        receipt = submit_to_balady(packet, case_state, auth_token)
        return {
            "ok": receipt.ok,
            "reference": receipt.reference,
            "submitted_at": receipt.submitted_at,
            "target_agency": receipt.target_agency,
            "is_mock": receipt.is_mock,
            "notice": receipt.notice,
        }

    return server
