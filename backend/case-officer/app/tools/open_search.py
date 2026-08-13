"""Unrestricted web search for the additional_context node.

This is the ONLY retrieval path in the system without a domain allowlist, which
makes it the weakest link by construction. Three layers compensate, in
decreasing order of reliability:

1. **The query itself** carries "Saudi Arabia" — bias the search engine toward
   Saudi results before any model sees them.
2. **A code-level keyword backstop** (:func:`mentions_saudi_arabia`) drops any
   result whose text never mentions Saudi Arabia, the Kingdom, or a Saudi
   regulator. Cheap and dumb on purpose: it is a floor, not a judgment.
3. **The system prompt** tells the model to ignore other countries' rules.

The prompt is listed last deliberately — it is the layer most likely to fail
silently, and here there is no allowlist underneath it to catch the failure.

Nothing this module returns may ever become citable Evidence. See
``app.agents.additional_context``.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit

from app.config.settings import settings
from app.tools import search_cache

OPEN_SEARCH_TIMEOUT_SECONDS = int(os.environ.get("OPEN_SEARCH_TIMEOUT_SECONDS", "12"))
DEFAULT_MAX_RESULTS = 6

_PLACEHOLDER_MARKERS = ("xxxx", "replace-me", "your-key", "changeme")

#: Sentinel used as the cache "domain set" so open-web queries can never collide
#: with an allowlisted search for the same string.
_OPEN_WEB_CACHE_KEY = ["__open_web__"]

#: Saudi-specific regulator and platform names. A page discussing Saudi business
#: regulation will almost always name at least one of these or the country.
SAUDI_REGULATORS = (
    "zatca",
    "balady",
    "gosi",
    "qiwa",
    "hrsd",
    "sfda",
    "saip",
    "monshaat",
    "monsha'at",
    "absher",
    "muqeem",
    "mudad",
    "saudi business center",
    "ministry of commerce",
    "misa",
)

SAUDI_NAMES = (
    "saudi arabia",
    "saudi arabian",
    "saudi",
    "ksa",
    "kingdom of saudi arabia",
    "المملكة العربية السعودية",
    "السعودية",
)


def registrable_domain(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().lstrip("www.")
    except ValueError:
        return ""


def mentions_saudi_arabia(text: str) -> bool:
    """Cheap keyword floor: does this text concern Saudi Arabia at all?

    Deliberately not NLP. It exists to catch the case where the model's judgment
    silently fails, because unlike every other node there is no domain allowlist
    underneath to stop a foreign source being reported.

    "Kingdom" alone is accepted per spec, but NOT when it is part of "United
    Kingdom" — otherwise every UK page passes the filter on that word alone,
    which is precisely the failure this is meant to prevent.
    """
    if not text:
        return False
    lowered = text.lower()

    if any(name in lowered for name in SAUDI_NAMES):
        return True
    if any(reg in lowered for reg in SAUDI_REGULATORS):
        return True

    # Bare "kingdom" counts only if it is not "united kingdom".
    without_uk = re.sub(r"united\s+kingdom", " ", lowered)
    return "kingdom" in without_uk


@dataclass
class SupplementaryResult:
    title: str
    url: str
    domain: str
    content: str
    retrieved_at: str


@dataclass
class OpenSearchOutcome:
    results: list[SupplementaryResult] = field(default_factory=list)
    ok: bool = False
    reason: str = "not_attempted"
    cached: bool = False
    latency_ms: int = 0
    raw_result_count: int = 0
    dropped_non_saudi: int = 0


def build_query(business_category: str | None, city: str | None = None) -> str:
    """Broad, category-level query with Saudi Arabia baked in.

    Deliberately broader than the five topic nodes: this node exists to surface
    general context, not to answer a specific regulatory question.
    """
    category = (business_category or "business").replace("_", " ")
    parts = ["Saudi Arabia", category, "business regulations requirements"]
    if city:
        parts.insert(2, city)
    return " ".join(parts)


def _api_key_available() -> bool:
    key = (settings.tavily_api_key or "").strip().lower()
    return bool(key) and not any(m in key for m in _PLACEHOLDER_MARKERS)


def search_open_web(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    *,
    use_cache: bool = True,
) -> OpenSearchOutcome:
    """Unrestricted search, Saudi-filtered in code. Never raises."""
    from app.tools.gov_search import live_search_disabled

    started = time.perf_counter()

    def _from_raw(raw: list[dict], cached: bool, reason: str) -> OpenSearchOutcome:
        kept: list[SupplementaryResult] = []
        dropped = 0
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for item in raw:
            url = str(item.get("url") or "")
            text = str(item.get("raw_content") or item.get("content") or "")
            title = str(item.get("title") or "")
            if not url or not text.strip():
                continue
            # The backstop. Title + body + URL are all considered, so a page
            # whose body is thin but whose title names the country still passes.
            if not mentions_saudi_arabia(f"{title}\n{url}\n{text}"):
                dropped += 1
                continue
            kept.append(
                SupplementaryResult(
                    title=title,
                    url=url,
                    domain=registrable_domain(url),
                    content=text.strip(),
                    retrieved_at=now,
                )
            )
        return OpenSearchOutcome(
            results=kept,
            ok=bool(kept),
            reason=reason if kept else "no_saudi_relevant_results",
            cached=cached,
            latency_ms=int((time.perf_counter() - started) * 1000),
            raw_result_count=len(raw),
            dropped_non_saudi=dropped,
        )

    if use_cache:
        entry = search_cache.read(query, _OPEN_WEB_CACHE_KEY, max_results)
        if entry is not None:
            outcome = _from_raw(entry.results, True, "cache_hit")
            if outcome.results:
                return outcome

    if live_search_disabled():
        return OpenSearchOutcome(reason="live_search_disabled")
    if not _api_key_available():
        return OpenSearchOutcome(reason="no_tavily_api_key")

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(
            query=query,
            # NOTE: deliberately no include_domains — this is the open-web node.
            max_results=max_results,
            search_depth="basic",
            include_raw_content=False,
            timeout=OPEN_SEARCH_TIMEOUT_SECONDS,
        )
        raw = list(response.get("results") or [])
    except Exception as exc:  # noqa: BLE001 — degrades, never propagates
        name = exc.__class__.__name__
        reason = "timeout" if "timeout" in name.lower() else f"error:{name}"
        return OpenSearchOutcome(
            reason=reason, latency_ms=int((time.perf_counter() - started) * 1000)
        )

    if use_cache and raw:
        search_cache.write(query, _OPEN_WEB_CACHE_KEY, max_results, raw)

    return _from_raw(raw, False, "live")
