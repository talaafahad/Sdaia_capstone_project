"""Live-first retrieval with corpus fallback.

Order of preference for every retrieval node:

1. Live Tavily search scoped to the node's allowed domains (5s, no retry).
2. On timeout, error, empty result, or no allowlisted hit — hybrid search over
   the local Phase 0 corpus, scoped to the same domains.
3. If both come up empty, return nothing and let the node apply section 2.2
   rule 3: mark the requirement unverified, "no allowlisted source found".
   Never fabricate to fill the gap.

Which path served an answer is recorded on every Passage (``origin``) and
summarised in :meth:`RetrievalOutcome.log_line` for the decision log.

One part of the fallback rule lives in the node, not here: "live returned
results but none support a claim at MEDIUM or better" can only be known after
the model has read them. A node in that position calls :func:`corpus_fallback`
directly to escalate.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.tools.gov_search import DEFAULT_MAX_RESULTS, search_gov_sources
from app.tools.hybrid_search import hybrid_search
from app.tools.passages import Passage, RetrievalPath


@dataclass(frozen=True)
class RetrievalOutcome:
    passages: tuple[Passage, ...]
    path: RetrievalPath
    #: Why the live path did or did not serve this — carried even when the
    #: corpus answered, so the log explains the fallback rather than hiding it.
    live_reason: str
    latency_ms: int
    cached: bool = False
    cache_age_hours: float | None = None
    node: str = ""

    @property
    def served(self) -> bool:
        return bool(self.passages)

    def log_line(self) -> str:
        """Human-readable decision-log entry naming the path that served."""
        label = f"[{self.node}] " if self.node else ""
        if self.path == "live":
            source = "CACHED live result" if self.cached else "LIVE (Tavily)"
            age = (
                f", cached {self.cache_age_hours:.1f}h ago"
                if self.cached and self.cache_age_hours is not None
                else ""
            )
            return (
                f"{label}served {source}: {len(self.passages)} passages "
                f"in {self.latency_ms}ms{age}."
            )
        if self.path == "corpus_fallback":
            return (
                f"{label}served CORPUS FALLBACK: {len(self.passages)} passages "
                f"(live path unavailable — {self.live_reason})."
            )
        return (
            f"{label}NO SOURCE FOUND: live path {self.live_reason}, corpus fallback "
            f"also empty. Requirement must be marked unverified."
        )


def corpus_fallback(
    query: str,
    domains: list[str] | set[str] | frozenset[str] | None = None,
    *,
    category: str | None = None,
    top_k: int = 5,
    live_reason: str = "escalated_by_node",
    node: str = "",
) -> RetrievalOutcome:
    """Corpus-only retrieval. Used directly when a node rejects the live results."""
    passages = hybrid_search(query, domains=domains, top_k=top_k, category=category)
    return RetrievalOutcome(
        passages=passages,
        path="corpus_fallback" if passages else "none",
        live_reason=live_reason,
        latency_ms=0,
        node=node,
    )


def retrieve(
    query: str,
    domains: list[str] | set[str] | frozenset[str] | None = None,
    *,
    category: str | None = None,
    top_k: int = 5,
    max_results: int = DEFAULT_MAX_RESULTS,
    use_cache: bool = True,
    node: str = "",
) -> RetrievalOutcome:
    """Live first, corpus second, nothing third."""
    live = search_gov_sources(
        query, domains=domains, max_results=max_results, use_cache=use_cache
    )

    if live.ok and live.passages:
        return RetrievalOutcome(
            passages=live.passages[:top_k],
            path="live",
            live_reason=live.reason,
            latency_ms=live.latency_ms,
            cached=live.cached,
            cache_age_hours=live.cache_age_hours,
            node=node,
        )

    fallback = corpus_fallback(
        query,
        domains=domains,
        category=category,
        top_k=top_k,
        live_reason=live.reason,
        node=node,
    )
    return RetrievalOutcome(
        passages=fallback.passages,
        path=fallback.path,
        live_reason=live.reason,
        latency_ms=live.latency_ms,
        node=node,
    )
