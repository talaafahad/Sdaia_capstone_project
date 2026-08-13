"""Live government search — Tavily, locked to the allowlist.

This is the PRIMARY source for every retrieval node. ``include_domains`` is the
real anti-hallucination guardrail (implementation plan section 0): the tool
itself cannot return a non-allowlisted page, so the prompt rule is defense in
depth rather than the only defense.

Results are additionally re-checked against the allowlist on the way out. If
Tavily ever returns something off-list — a redirect, an aggregator, a bug — it
is dropped here rather than reaching a model.

A short timeout with no retry is deliberate: the corpus fallback IS the retry,
and retrying twice before falling back costs more than it saves.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config.allowlist import entity_for, is_searchable, registered_domain, tavily_include_domains
from app.config.settings import settings
from app.tools import search_cache
from app.tools.passages import Passage

#: Measured Tavily latency on this corpus of queries is 1.9-5.2s at
#: search_depth="advanced". A 5s ceiling therefore fails *intermittently*, which
#: is worse than failing outright — the live path would pass in testing and drop
#: to fallback unpredictably during a demo. 12s clears the observed range; the
#: cost of waiting is bounded because retrieval nodes run concurrently and
#: repeat queries are served from the disk cache.
LIVE_SEARCH_TIMEOUT_SECONDS = int(os.environ.get("LIVE_SEARCH_TIMEOUT_SECONDS", "12"))

DEFAULT_MAX_RESULTS = 6

#: Values that mean "the key was never filled in" — .env ships with placeholders,
#: and a placeholder must degrade to the corpus fallback, not raise at startup.
_PLACEHOLDER_MARKERS = ("xxxx", "replace-me", "your-key", "changeme")


@dataclass(frozen=True)
class LiveSearchOutcome:
    passages: tuple[Passage, ...] = ()
    ok: bool = False
    #: Machine-readable why. Surfaces in the decision log.
    reason: str = "not_attempted"
    cached: bool = False
    cache_age_hours: float | None = None
    latency_ms: int = 0
    dropped_off_allowlist: int = 0
    raw_result_count: int = 0
    domains_queried: list[str] = field(default_factory=list)


def live_search_disabled() -> bool:
    """Kill switch for the live path.

    Set ``DISABLE_LIVE_SEARCH=1`` to force every node onto the corpus fallback.
    Used by the test suite so fallback behaviour is deterministic whether or not
    a real key is configured, and useful on demo day to run entirely offline
    from the pre-verified corpus.
    """
    return os.environ.get("DISABLE_LIVE_SEARCH", "").lower() in ("1", "true", "yes")


def _api_key_available() -> bool:
    key = (settings.tavily_api_key or "").strip()
    if not key:
        return False
    lowered = key.lower()
    return not any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def _to_passages(results: list[dict], now_iso: str) -> tuple[tuple[Passage, ...], int]:
    """Convert Tavily hits to Passages, dropping anything off-allowlist."""
    passages: list[Passage] = []
    dropped = 0
    for item in results:
        url = str(item.get("url") or "")
        if not is_searchable(url):
            dropped += 1
            continue
        text = str(item.get("raw_content") or item.get("content") or "").strip()
        if not text:
            dropped += 1
            continue
        domain = registered_domain(url) or ""
        passages.append(
            Passage(
                text=text,
                source_url=url,
                source_entity=entity_for(url) or domain,
                domain=domain,
                retrieved_at=now_iso,
                title=str(item.get("title") or ""),
                score=float(item.get("score") or 0.0),
                origin="live",
            )
        )
    return tuple(passages), dropped


def search_gov_sources(
    query: str,
    domains: list[str] | set[str] | frozenset[str] | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    *,
    use_cache: bool = True,
    timeout_seconds: int = LIVE_SEARCH_TIMEOUT_SECONDS,
) -> LiveSearchOutcome:
    """One allowlist-scoped live search.

    Never raises: every failure mode is reported through ``reason`` so the
    caller can fall back to the corpus and log which path served the answer.
    """
    include = tavily_include_domains(set(domains) if domains is not None else None)
    if not include:
        return LiveSearchOutcome(reason="no_allowlisted_domains_requested", domains_queried=[])

    started = time.perf_counter()

    if use_cache:
        entry = search_cache.read(query, include, max_results)
        if entry is not None:
            now_iso = datetime.fromtimestamp(entry.fetched_at, tz=timezone.utc).isoformat(
                timespec="seconds"
            )
            passages, dropped = _to_passages(entry.results, now_iso)
            if passages:
                return LiveSearchOutcome(
                    passages=passages,
                    ok=True,
                    reason="cache_hit",
                    cached=True,
                    cache_age_hours=entry.age_hours,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    dropped_off_allowlist=dropped,
                    raw_result_count=len(entry.results),
                    domains_queried=include,
                )

    # Checked after the cache read on purpose: the kill switch blocks the
    # NETWORK call, not the local cache. A cached result is exactly the offline
    # safety net this flag is meant to fall back on.
    if live_search_disabled():
        return LiveSearchOutcome(
            reason="live_search_disabled",
            latency_ms=int((time.perf_counter() - started) * 1000),
            domains_queried=include,
        )

    if not _api_key_available():
        return LiveSearchOutcome(
            reason="no_tavily_api_key",
            latency_ms=int((time.perf_counter() - started) * 1000),
            domains_queried=include,
        )

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(
            query=query,
            include_domains=include,
            max_results=max_results,
            search_depth="advanced",
            include_raw_content=True,
            timeout=timeout_seconds,
        )
        results = list(response.get("results") or [])
    except Exception as exc:  # noqa: BLE001 — every failure falls back, none propagate
        name = exc.__class__.__name__
        reason = "timeout" if "timeout" in name.lower() or "timeout" in str(exc).lower() else f"error:{name}"
        return LiveSearchOutcome(
            reason=reason,
            latency_ms=int((time.perf_counter() - started) * 1000),
            domains_queried=include,
        )

    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    passages, dropped = _to_passages(results, now_iso)
    latency_ms = int((time.perf_counter() - started) * 1000)

    if not passages:
        return LiveSearchOutcome(
            reason="no_allowlisted_results",
            latency_ms=latency_ms,
            dropped_off_allowlist=dropped,
            raw_result_count=len(results),
            domains_queried=include,
        )

    if use_cache:
        search_cache.write(query, include, max_results, results)

    return LiveSearchOutcome(
        passages=passages,
        ok=True,
        reason="live",
        latency_ms=latency_ms,
        dropped_off_allowlist=dropped,
        raw_result_count=len(results),
        domains_queried=include,
    )
