"""A2A delegation from the Case Officer to the Municipal & Location service.

The endpoint is discovered from the remote Agent Card rather than hardcoded:
the card is fetched, the skill is looked up by id, and its declared endpoint is
called. That is what makes this genuine A2A delegation rather than an ordinary
HTTP call with extra steps.

A2A failures degrade to "unverified" the same way a retrieval miss does. The
municipal service being down must never turn into an unsourced municipal claim.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

MUNICIPAL_SERVICE_URL = os.environ.get("MUNICIPAL_SERVICE_URL", "http://localhost:8001")
DISCOVERY_TIMEOUT = 5
CALL_TIMEOUT = 90


@dataclass
class A2AResult:
    ok: bool
    data: dict = field(default_factory=dict)
    reason: str = "ok"


def fetch_agent_card(base_url: str = MUNICIPAL_SERVICE_URL) -> dict | None:
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/.well-known/agent-card.json", timeout=DISCOVERY_TIMEOUT
        )
        response.raise_for_status()
        return response.json()
    except Exception:  # noqa: BLE001
        return None


def endpoint_for_skill(card: dict, skill_id: str) -> str | None:
    for skill in card.get("skills") or []:
        if skill.get("id") == skill_id:
            return skill.get("endpoint") or f"/a2a/{skill_id}"
    return None


def delegate(skill_id: str, payload: dict, base_url: str = MUNICIPAL_SERVICE_URL) -> A2AResult:
    """Discover the skill on the remote card, then call it."""
    card = fetch_agent_card(base_url)
    if card is None:
        return A2AResult(False, reason="agent_card_unreachable")

    path = endpoint_for_skill(card, skill_id)
    if not path:
        return A2AResult(False, reason=f"skill_not_advertised:{skill_id}")

    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}{path}", json=payload, timeout=CALL_TIMEOUT
        )
        response.raise_for_status()
        return A2AResult(True, response.json())
    except Exception as exc:  # noqa: BLE001
        return A2AResult(False, reason=f"delegation_failed:{exc.__class__.__name__}")


def municipal_location_node(state: dict) -> dict:
    """Delegate both municipal skills and merge their partial updates."""
    payload = {
        "business_category": state.get("business_category"),
        "city": state.get("city"),
        "district": state.get("district"),
        "area_sqm_stated": state.get("area_sqm_stated"),
    }

    requirements: list[dict] = []
    evidence: list[dict] = []
    decisions: list[str] = []
    passage_texts: dict[str, str] = {}

    municipal = delegate("municipal_requirements", payload)
    if municipal.ok:
        requirements.extend(municipal.data.get("requirements") or [])
        evidence.extend(municipal.data.get("evidence") or [])
        decisions.extend(municipal.data.get("decision_log") or [])
        passage_texts.update(municipal.data.get("passage_texts") or {})
    else:
        decisions.append(
            f"Municipal & Location (A2A): delegation failed ({municipal.reason}). "
            "Municipal requirements marked unverified — no claim substituted."
        )
        requirements.append(
            {
                "name": "Municipal commercial licence (Balady)",
                "status": "unverified",
                "evidence": None,
                "note": f"A2A delegation failed: {municipal.reason}",
                "produced_by": "municipal_requirements",
            }
        )

    competitors = delegate("competitor_lookup", {**payload, "radius_m": 500})
    if competitors.ok:
        evidence.extend(competitors.data.get("evidence") or [])
        decisions.extend(competitors.data.get("decision_log") or [])
    else:
        decisions.append(
            f"Municipal & Location (A2A): competitor lookup unavailable ({competitors.reason})."
        )

    return {
        "requirements": requirements,
        "evidence_log": evidence,
        "decision_log": decisions,
        "passage_texts": passage_texts,
    }
