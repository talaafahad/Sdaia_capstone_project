"""LangGraph StateGraph wiring (implementation plan section 3).

    START
      -> intake_planner
      -> (conditional on branch) regulation_router
      -> [parallel] municipal_location (A2A)  +  tax_financial (deterministic)
      -> verifier
      -> (conditional: conflicts non-empty) HUMAN_RESOLUTION_INTERRUPT -> verifier
      -> human_approval_gate (interrupt)
      -> documentation
      -> END

Both human gates use LangGraph's ``interrupt()`` rather than polling, which is
the pattern the course material specifies for pausing a graph mid-execution.

Reducers matter here: ``municipal_location`` and ``tax_financial`` run in
parallel and both append to ``requirements`` and ``evidence_log``. Without
additive reducers LangGraph raises on the concurrent write, and with a naive
"last write wins" one node would silently erase the other's findings — exactly
what section 1's partial-update rule exists to prevent.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents.documentation import documentation_node
from app.agents.intake_planner import intake_planner_node
from app.agents.regulation_router import regulation_router_node
from app.agents.tax_financial import tax_financial_node
from app.agents.verifier import verifier_node
from app.config.category_map import branch_for
from app.tools.a2a_client import municipal_location_node


def merge_requirements(left: list[dict], right: list[dict]) -> list[dict]:
    """Append, de-duplicating by requirement name (later wins)."""
    merged: dict[str, dict] = {}
    for item in [*(left or []), *(right or [])]:
        name = str(item.get("name") or "")
        merged[name] = item
    return list(merged.values())


def merge_evidence(left: list[dict], right: list[dict]) -> list[dict]:
    """Append, de-duplicating on (source_url, claim)."""
    merged: dict[tuple[str, str], dict] = {}
    for item in [*(left or []), *(right or [])]:
        key = (str(item.get("source_url") or ""), str(item.get("claim") or ""))
        merged[key] = item
    return list(merged.values())


def take_last(left: Any, right: Any) -> Any:
    return right if right is not None else left


def merge_dicts(left: dict, right: dict) -> dict:
    """Union of two mappings. Needed because regulation_router and
    municipal_location both contribute passage texts from parallel branches."""
    return {**(left or {}), **(right or {})}


class GraphState(TypedDict, total=False):
    case_id: str
    goal: str
    business_type: Annotated[Any, take_last]
    business_category: Annotated[Any, take_last]
    city: Annotated[Any, take_last]
    district: Annotated[Any, take_last]
    applicant_status: Annotated[Any, take_last]
    area_sqm_stated: Annotated[Any, take_last]
    area_sqm_from_document: Annotated[Any, take_last]
    document_source: Annotated[Any, take_last]
    budget_sar: Annotated[Any, take_last]
    expected_annual_revenue_sar: Annotated[Any, take_last]
    employee_count: Annotated[Any, take_last]
    target_opening_date: Annotated[Any, take_last]
    applicant_age: Annotated[Any, take_last]
    branch: Annotated[Any, take_last]
    missing_fields: Annotated[Any, take_last]

    requirements: Annotated[list[dict], merge_requirements]
    evidence_log: Annotated[list[dict], merge_evidence]
    decision_log: Annotated[list[str], operator.add]
    conflicts: Annotated[Any, take_last]
    readiness_pct: Annotated[Any, take_last]
    vat_registration_required: Annotated[Any, take_last]
    approval_stage: Annotated[Any, take_last]
    artifacts: Annotated[Any, take_last]
    passage_texts: Annotated[dict, merge_dicts]
    supplementary_context: Annotated[Any, take_last]
    submission: Annotated[Any, take_last]


def _progress(config) -> Any:
    return ((config or {}).get("configurable") or {}).get("progress")


def node_intake(state: GraphState, config=None) -> dict:
    progress = _progress(config)
    if progress:
        progress("intake_planner", "active", "Extracting fields from the stated goal")
    update = intake_planner_node(dict(state))
    if progress:
        progress("intake_planner", "complete", f"Branch: {update.get('branch')}")
    return update


def node_regulation(state: GraphState, config=None) -> dict:
    progress = _progress(config)
    if progress:
        progress("regulation_router", "active", "Searching allowlisted domains")

    def topic_progress(node_id: str, status: str) -> None:
        if progress and status == "active":
            progress("regulation_router", "active", f"Retrieving: {node_id}")

    update = regulation_router_node(dict(state), progress=topic_progress)
    cited = sum(1 for r in update.get("requirements", []) if r.get("evidence"))
    unverified = len(update.get("requirements", [])) - cited
    if progress:
        progress(
            "regulation_router",
            "complete",
            f"{cited} requirements cited, {unverified} unverified",
        )
    return update


def node_municipal(state: GraphState, config=None) -> dict:
    progress = _progress(config)
    if progress:
        progress("municipal_location", "active", "Delegated over A2A to :8001")
    update = municipal_location_node(dict(state))
    if progress:
        progress("municipal_location", "complete", "Approval status: NOT VERIFIED")
    return update


def node_tax(state: GraphState, config=None) -> dict:
    progress = _progress(config)
    if progress:
        progress("tax_financial", "active", "Deterministic assessment — no LLM")
    update = tax_financial_node(dict(state))
    if progress:
        result = "required" if update.get("vat_registration_required") else "not required"
        progress("tax_financial", "complete", f"VAT registration {result}")
    return update


def node_verifier(state: GraphState, config=None) -> dict:
    progress = _progress(config)
    if progress:
        progress("verifier", "active", "Auditing citations")
    update = verifier_node(dict(state), (state.get("passage_texts") or {}))
    accepted = sum(1 for e in update.get("evidence_log", []) if e.get("has_explicit_url"))
    rejected = len(update.get("evidence_log", [])) - accepted
    open_conflicts = [c for c in (update.get("conflicts") or []) if c.get("status") == "open"]
    if progress:
        if open_conflicts:
            progress("verifier", "blocked", "Discrepancy — awaiting human resolution")
        else:
            progress("verifier", "complete", f"{accepted} accepted, {rejected} rejected")
    return update


def node_conflict_gate(state: GraphState, config=None) -> dict:
    """HUMAN_RESOLUTION_INTERRUPT — pauses the graph until a human chooses."""
    conflicts = list(state.get("conflicts") or [])
    open_conflicts = [c for c in conflicts if c.get("status") == "open"]
    if not open_conflicts:
        return {}

    conflict = open_conflicts[0]
    answer = interrupt({"kind": "conflict_resolution", "conflict": conflict})

    accepted = (answer or {}).get("accepted", "document")
    note = (answer or {}).get("note")
    accepted_value = (
        conflict["document_value"] if accepted == "document" else conflict["stated_value"]
    )

    from datetime import datetime, timezone

    resolved = {
        **conflict,
        "status": "resolved",
        "resolution": {
            "accepted": accepted,
            "accepted_value": accepted_value,
            "note": note,
            "resolved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    }
    remaining = [c for c in conflicts if c.get("conflict_id") != conflict["conflict_id"]]

    return {
        "conflicts": remaining + [resolved],
        "area_sqm_stated": accepted_value,
        "decision_log": [
            f"Human resolution: \"{accepted}\" value accepted for premises area "
            f"({accepted_value:g} sqm). Readiness unfrozen."
            + (f" Note: {note}" if note else "")
        ],
    }


def node_approval_gate(state: GraphState, config=None) -> dict:
    """Human approval gate — the second interrupt() in section 3."""
    evidence = state.get("evidence_log") or []
    accepted = [e for e in evidence if e.get("has_explicit_url")]
    rejected = [e for e in evidence if not e.get("has_explicit_url")]

    answer = interrupt(
        {
            "kind": "approval_gate",
            "summary": (
                "The proposal below was assembled from verified evidence only. Rejected "
                "claims have been removed entirely, not softened. Approve to generate the "
                "final artifacts."
            ),
            "requirement_count": len(state.get("requirements") or []),
            "accepted_evidence_count": len(accepted),
            "rejected_evidence_count": len(rejected),
        }
    )

    decision = (answer or {}).get("decision", "approve")
    note = (answer or {}).get("note")
    stage = "proposal_approved" if decision == "approve" else "none"
    return {
        "approval_stage": stage,
        "decision_log": [
            f"Human approval gate: {decision.upper()}." + (f" Note: {note}" if note else "")
        ],
    }


def node_documentation(state: GraphState, config=None) -> dict:
    progress = _progress(config)
    if state.get("approval_stage") != "proposal_approved":
        return {
            "decision_log": [
                "Documentation: skipped — the proposal was not approved at the human gate."
            ]
        }
    if progress:
        progress("documentation", "active", "Assembling the six artifacts")
    update = documentation_node(dict(state))
    update["readiness_pct"] = 100
    if progress:
        progress(
            "documentation",
            "complete",
            "Journey, checklist, evidence, fees, packet, log",
        )
    return update


def route_after_intake(state: GraphState) -> str:
    """Conditional edge on the Intake agent's branch classification."""
    return branch_for(state.get("business_category"))


def route_after_verifier(state: GraphState) -> str:
    open_conflicts = [c for c in (state.get("conflicts") or []) if c.get("status") == "open"]
    return "conflict_gate" if open_conflicts else "approval_gate"


def build_graph(checkpointer=None):
    """Compile the static graph. Conditional edges, not runtime composition."""
    builder = StateGraph(GraphState)

    builder.add_node("intake_planner", node_intake)
    builder.add_node("regulation_router", node_regulation)
    builder.add_node("municipal_location", node_municipal)
    builder.add_node("tax_financial", node_tax)
    builder.add_node("verifier", node_verifier)
    builder.add_node("conflict_gate", node_conflict_gate)
    builder.add_node("approval_gate", node_approval_gate)
    builder.add_node("documentation", node_documentation)

    builder.add_edge(START, "intake_planner")

    # Both branches currently run the same router; the router itself selects the
    # topic nodes per category (section 10's generalisation point). The
    # conditional edge is kept because section 3 specifies it and because a
    # food-specific pre-step would attach here.
    builder.add_conditional_edges(
        "intake_planner",
        route_after_intake,
        {"food_business": "regulation_router", "general_business": "regulation_router"},
    )

    # Fan out to the A2A service and the deterministic tax core in parallel.
    builder.add_edge("regulation_router", "municipal_location")
    builder.add_edge("regulation_router", "tax_financial")

    # Both must finish before the Verifier audits what they produced.
    builder.add_edge("municipal_location", "verifier")
    builder.add_edge("tax_financial", "verifier")

    builder.add_conditional_edges(
        "verifier",
        route_after_verifier,
        {"conflict_gate": "conflict_gate", "approval_gate": "approval_gate"},
    )
    # Resolution loops back so the Verifier re-audits with the accepted value.
    builder.add_edge("conflict_gate", "verifier")
    builder.add_edge("approval_gate", "documentation")
    builder.add_edge("documentation", END)

    return builder.compile(checkpointer=checkpointer or MemorySaver())


_GRAPH = None


def get_graph():
    """Process-wide compiled graph with an in-memory checkpointer.

    MemorySaver means a case does not survive a restart — acceptable for a demo
    where one case runs at a time. Swapping to SqliteSaver is a one-line change
    if durability is needed.
    """
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH
