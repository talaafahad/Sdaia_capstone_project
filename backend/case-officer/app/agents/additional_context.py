"""Additional Context agent — the sixth Regulation Router sub-node.

The only node in the system that searches the open web. Everything it produces
is SUPPLEMENTARY: stored in ``CaseState.supplementary_context``, never in
``evidence_log``, never citable, never able to satisfy a requirement or move
``readiness_pct``.

That isolation is structural rather than conventional:

* the node returns a ``supplementary_context`` key and nothing else — it has no
  code path that can write ``requirements`` or ``evidence_log``;
* :class:`app.state.SupplementaryItem` is a different type from ``Evidence``,
  with ``confidence`` pinned to the literal ``"LOW"`` and ``is_official`` pinned
  to ``False``, so a wrong value fails validation instead of degrading quietly;
* readiness is computed from ``requirements`` alone, which this node never
  touches.

Saudi scoping is defended three times over, because there is no allowlist here:
the query names the country, a keyword backstop drops non-Saudi pages in code,
and the prompt tells the model to ignore other jurisdictions.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.agents.prompts import ADDITIONAL_CONTEXT_PROMPT
from app.config.allowlist import cap_confidence
from app.llm import call_json, llm_available
from app.tools.open_search import (
    OpenSearchOutcome,
    build_query,
    mentions_saudi_arabia,
    registrable_domain,
    search_open_web,
)

MAX_ITEMS = 4
#: Passage budget per result in the prompt. Open-web pages are noisy; this node
#: is the least important consumer of model time, so it gets the smallest slice.
EXCERPT_CHARS = 700


def _render_context(outcome: OpenSearchOutcome) -> str:
    return "\n\n".join(
        f"[{i + 1}] title: {r.title}\n"
        f"    source_url: {r.url}\n"
        f"    domain: {r.domain}\n"
        f"    text: {r.content[:EXCERPT_CHARS]}"
        for i, r in enumerate(outcome.results)
    )


def additional_context_node(state: dict) -> dict:
    """Partial update containing ONLY ``supplementary_context`` and decisions."""
    query = build_query(state.get("business_category"), state.get("city"))
    outcome = search_open_web(query)

    decisions: list[str] = [
        f"Additional Context: open-web search (no allowlist) for {query!r} — "
        f"{outcome.raw_result_count} results, {outcome.dropped_non_saudi} dropped as "
        f"not Saudi-related, {len(outcome.results)} kept ({outcome.reason})."
    ]

    if not outcome.results:
        return {"supplementary_context": [], "decision_log": decisions}

    if not llm_available():
        decisions.append("Additional Context: no model available; supplementary context skipped.")
        return {"supplementary_context": [], "decision_log": decisions}

    try:
        parsed = call_json(
            "additional_context",
            ADDITIONAL_CONTEXT_PROMPT,
            f"SEARCH RESULTS\n==============\n{_render_context(outcome)}",
            max_tokens=1200,
        )
    except Exception as exc:  # noqa: BLE001 — supplementary context is optional
        decisions.append(
            f"Additional Context: model call failed ({exc.__class__.__name__}); "
            "no supplementary context recorded."
        )
        return {"supplementary_context": [], "decision_log": decisions}

    raw_items = parsed.get("items") if isinstance(parsed, dict) else parsed
    if not isinstance(raw_items, list):
        return {"supplementary_context": [], "decision_log": decisions}

    by_url = {r.url: r for r in outcome.results}
    items: list[dict] = []
    dropped_unknown_url = 0
    dropped_non_saudi = 0
    now = datetime.now(timezone.utc)

    for raw in raw_items[:MAX_ITEMS]:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("source_url") or "").strip()
        claim = str(raw.get("claim") or "").strip()
        if not claim:
            continue

        # A model may not introduce a URL the node did not retrieve — the same
        # rule the allowlisted nodes enforce, applied here where it matters more.
        source = by_url.get(url)
        if source is None:
            dropped_unknown_url += 1
            continue

        # Second pass of the backstop, now against the claim the model wrote.
        # Catches a model summarising a Saudi page into a country-neutral or
        # foreign-sounding statement.
        if not mentions_saudi_arabia(f"{claim}\n{source.title}\n{source.content}"):
            dropped_non_saudi += 1
            continue

        items.append(
            {
                "claim": claim,
                "source_url": url,
                "source_domain": source.domain or registrable_domain(url),
                "title": source.title,
                "retrieved_at": now,
                # cap_confidence returns LOW for any non-allowlisted domain, so
                # an open-web source can never come out above LOW.
                "confidence": cap_confidence(url, "LOW"),
                "is_official": False,
            }
        )

    if dropped_unknown_url:
        decisions.append(
            f"Additional Context: dropped {dropped_unknown_url} item(s) citing a URL "
            "the node did not retrieve."
        )
    if dropped_non_saudi:
        decisions.append(
            f"Additional Context: dropped {dropped_non_saudi} item(s) that failed the "
            "Saudi-relevance check after the model wrote them."
        )
    decisions.append(
        f"Additional Context: {len(items)} supplementary reference(s) recorded. "
        "Not evidence — cannot satisfy a requirement or affect readiness."
    )

    # NOTE: the return shape is the isolation guarantee. This function has no
    # branch that writes `requirements` or `evidence_log`.
    return {"supplementary_context": items, "decision_log": decisions}
