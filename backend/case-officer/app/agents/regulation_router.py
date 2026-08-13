"""Regulation & Service Router (implementation plan section 2.2).

Not one agent with one prompt — a fan-out over narrowly-scoped topic nodes, each
with its own system prompt and its own allowed-domain subset. Every node runs
live-first retrieval with corpus fallback.

The Router deliberately does NOT own balady.gov.sa: the Municipal & Location A2A
service owns every Balady requirement (section 2.3).

Section 2.2 rule 3 is enforced structurally, not just by prompt: when neither
retrieval path returns a passage, the requirement is written as ``unverified``
with "no allowlisted source found" **without a model call at all**. There is no
code path in which an empty retrieval can produce a cited claim.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

from app.agents.prompts import NODES, build_system_prompt, domains_for
from app.config.allowlist import cap_confidence, entity_for, is_citable
from app.config.category_map import FOOD_CATEGORIES
from app.llm import call_json, llm_available
from app.tools.passages import Passage, render_context
from app.tools.retrieval import RetrievalOutcome, corpus_fallback, retrieve

#: Which topic nodes run for which business categories. Municipal requirements
#: are absent by design — they are delegated over A2A.
NODE_QUERIES: dict[str, str] = {
    "commercial_registration": "commercial registration requirements to start a business",
    "vat_registration": "VAT registration mandatory threshold for businesses",
    "food_safety": "food safety requirements for food service establishments",
    "employment_social_insurance": "employer establishment registration social insurance",
    "intellectual_property": "trademark registration for a business trade name",
}


def nodes_for_category(category: str | None) -> list[str]:
    """Topic nodes applicable to a business category."""
    nodes = ["commercial_registration", "vat_registration"]
    if category in FOOD_CATEGORIES:
        nodes.append("food_safety")
    if category != "food_truck_mobile":
        # A mobile cart licence does not presuppose employees (section 10 map).
        nodes.append("employment_social_insurance")
    if category == "professional_office":
        nodes.append("intellectual_property")
    return nodes


@dataclass
class NodeResult:
    node_id: str
    requirements: list[dict]
    evidence: list[dict]
    outcome: RetrievalOutcome
    decisions: list[str]


def _unverified_requirement(node_id: str, reason: str) -> dict:
    """Section 2.2 rule 3, produced without consulting a model."""
    return {
        "name": _REQUIREMENT_NAMES[node_id],
        "status": "unverified",
        "evidence": None,
        "note": reason,
        "produced_by": node_id,
    }


_REQUIREMENT_NAMES = {
    "commercial_registration": "Commercial Registration (CR)",
    "vat_registration": "VAT registration (ZATCA)",
    "food_safety": "Food-handling compliance (SFDA)",
    "employment_social_insurance": "Employer registration (GOSI / Qiwa)",
    "intellectual_property": "Trademark registration (SAIP)",
}


def _normalise_evidence(
    raw: dict, passages: tuple[Passage, ...], node_id: str, path: str
) -> dict | None:
    """Force a model's evidence claim back onto verifiable ground.

    The URL must be one the node actually retrieved — a model may not introduce
    a URL of its own, even an allowlisted one. Entity name and confidence
    ceiling come from the allowlist, not from the model.
    """
    url = str(raw.get("source_url") or "").strip()
    retrieved_urls = {p.source_url for p in passages}
    if url not in retrieved_urls:
        return None
    if not is_citable(url):
        return None

    claim = str(raw.get("claim") or "").strip()
    if not claim:
        return None

    confidence = str(raw.get("confidence") or "LOW").upper()
    if confidence not in ("HIGH", "MEDIUM", "LOW"):
        confidence = "LOW"

    source = next((p for p in passages if p.source_url == url), None)
    return {
        "claim": claim,
        "source_entity": entity_for(url) or (source.source_entity if source else ""),
        "source_url": url,
        # Provenance comes from the passage, never from the model (prompt rule 6).
        "retrieved_at": source.retrieved_at if source else datetime.now(timezone.utc).isoformat(),
        "confidence": cap_confidence(url, confidence),
        "has_explicit_url": True,  # the Verifier re-decides this in Phase 4
        "retrieval_path": path,
    }


def _read_passages(node_id: str, state: dict, outcome: RetrievalOutcome) -> NodeResult:
    """Turn a retrieved passage set into requirements + evidence.

    Shared by the first-pass retrieval and the low-confidence escalation, so both
    apply exactly the same citation discipline.
    """
    decisions: list[str] = []

    if not outcome.served:
        return NodeResult(
            node_id,
            [_unverified_requirement(node_id, "no allowlisted source found")],
            [],
            outcome,
            decisions,
        )

    if not llm_available():
        return NodeResult(
            node_id,
            [_unverified_requirement(node_id, "no model available to read retrieved sources")],
            [],
            outcome,
            [f"Regulation Router [{node_id}]: no LLM configured."],
        )

    system = build_system_prompt(
        node_id,
        business_category=state.get("business_category"),
        city=state.get("city"),
        district=state.get("district"),
        applicant_status=state.get("applicant_status"),
        expected_annual_revenue_sar=state.get("expected_annual_revenue_sar"),
        employee_count=state.get("employee_count"),
        area_sqm_stated=state.get("area_sqm_stated"),
    )
    user = (
        "RETRIEVED CONTEXT\n"
        "=================\n"
        f"{render_context(outcome.passages)}\n\n"
        "Produce JSON of the form:\n"
        '{"requirements": [{"name": str, "status": "satisfied"|"missing"|"unverified", '
        '"note": str, "evidence": {"claim": str, "source_url": str, "confidence": '
        '"HIGH"|"MEDIUM"|"LOW"}}]}\n'
        "Use only source_url values that appear in the context above."
    )

    try:
        parsed = call_json(node_id, system, user, max_tokens=2500)
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            node_id,
            [_unverified_requirement(node_id, f"model call failed: {exc.__class__.__name__}")],
            [],
            outcome,
            [f"Regulation Router [{node_id}]: model call failed ({exc.__class__.__name__})."],
        )

    raw_requirements = parsed.get("requirements") if isinstance(parsed, dict) else None
    if not isinstance(raw_requirements, list) or not raw_requirements:
        return NodeResult(
            node_id,
            [_unverified_requirement(node_id, "model returned no requirements")],
            [],
            outcome,
            decisions,
        )

    requirements: list[dict] = []
    evidence: list[dict] = []
    dropped = 0

    for item in raw_requirements:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or _REQUIREMENT_NAMES[node_id]).strip()
        status = str(item.get("status") or "unverified")
        if status not in ("satisfied", "missing", "unverified"):
            status = "unverified"

        normalised = None
        if isinstance(item.get("evidence"), dict):
            normalised = _normalise_evidence(
                item["evidence"], outcome.passages, node_id, outcome.path
            )
            if normalised is None:
                dropped += 1

        if normalised is None:
            # A requirement with no usable citation is unverified, never asserted.
            requirements.append(
                {
                    "name": name,
                    "status": "unverified",
                    "evidence": None,
                    "note": str(item.get("note") or "") or "no allowlisted source found",
                    "produced_by": node_id,
                }
            )
            continue

        requirements.append(
            {
                "name": name,
                "status": status,
                "evidence": normalised,
                "note": str(item.get("note") or ""),
                "produced_by": node_id,
            }
        )
        evidence.append(normalised)

    if dropped:
        decisions.append(
            f"Regulation Router [{node_id}]: dropped {dropped} claim(s) citing a URL "
            "the node did not retrieve."
        )

    return NodeResult(node_id, requirements, evidence, outcome, decisions)


def _query_for(node_id: str, state: dict) -> str:
    return f"{NODE_QUERIES[node_id]} {state.get('city') or ''}".strip()


def run_topic_node(node_id: str, state: dict) -> NodeResult:
    """One narrowly-scoped retrieval node, live-first with corpus fallback."""
    outcome = retrieve(
        _query_for(node_id, state),
        domains=set(domains_for(node_id)),
        category=state.get("business_category"),
        top_k=5,
        node=node_id,
    )
    result = _read_passages(node_id, state, outcome)
    result.decisions.insert(0, f"Regulation Router {outcome.log_line()}")
    return result


def escalate_if_low_confidence(result: NodeResult, state: dict) -> NodeResult:
    """The confidence-bar clause of the fallback rule.

    Live results that yield nothing at MEDIUM or better are treated as a miss,
    and the corpus is consulted instead — this can only be judged after the
    model has read the passages, which is why it lives here and not in
    ``retrieve``.
    """
    if result.outcome.path != "live":
        return result
    best = {e["confidence"] for e in result.evidence}
    if best & {"HIGH", "MEDIUM"}:
        return result

    node_id = result.node_id
    fallback = corpus_fallback(
        _query_for(node_id, state),
        domains=set(domains_for(node_id)),
        category=state.get("business_category"),
        live_reason="no_evidence_at_medium_or_better",
        node=node_id,
    )
    if not fallback.served:
        return result

    retried = _read_passages(node_id, state, fallback)
    retried.decisions.insert(
        0,
        f"Regulation Router [{node_id}]: live results were below the citation-confidence "
        "bar; escalated to corpus fallback.",
    )
    return retried


def regulation_router_node(state: dict, progress=None) -> dict:
    """Fan out over the applicable topic nodes and merge their partial updates.

    Nodes run concurrently: each makes an independent network call, so running
    them in sequence would multiply the live-search latency by the node count.
    """
    category = state.get("business_category")
    node_ids = [n for n in nodes_for_category(category) if n in NODES]

    def _run(node_id: str) -> NodeResult:
        if progress:
            progress(node_id, "active")
        result = run_topic_node(node_id, state)
        result = escalate_if_low_confidence(result, state)
        if progress:
            progress(node_id, "complete")
        return result

    with ThreadPoolExecutor(max_workers=min(5, len(node_ids) or 1)) as pool:
        results = list(pool.map(_run, node_ids))

    requirements: list[dict] = []
    evidence: list[dict] = []
    decisions: list[str] = []
    # The Verifier audits each claim against the passage it came from, so the
    # passage text has to travel with the evidence. Without this the Verifier
    # sees claims with no supporting text and correctly rejects every one.
    passage_texts: dict[str, str] = {}
    for result in results:
        requirements.extend(result.requirements)
        evidence.extend(result.evidence)
        decisions.extend(result.decisions)
        for passage in result.outcome.passages:
            existing = passage_texts.get(passage.source_url, "")
            if len(passage.text) > len(existing):
                passage_texts[passage.source_url] = passage.text

    served_live = sum(1 for r in results if r.outcome.path == "live")
    served_corpus = sum(1 for r in results if r.outcome.path == "corpus_fallback")
    unserved = sum(1 for r in results if r.outcome.path == "none")
    decisions.append(
        f"Regulation Router: {len(node_ids)} topic nodes — {served_live} live, "
        f"{served_corpus} corpus fallback, {unserved} with no allowlisted source."
    )

    return {
        "requirements": requirements,
        "evidence_log": evidence,
        "decision_log": decisions,
        "passage_texts": passage_texts,
    }
