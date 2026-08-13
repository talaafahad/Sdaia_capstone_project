"""On-disk cache for live search results.

Two jobs:

1. Stop repeated identical queries hitting Tavily during development and
   testing (free-tier rate limits are the practical constraint).
2. Act as a demo-day safety net — a cached result from the last successful run
   can still serve if Tavily has a bad moment.

Deliberately has **no expiry**: a stale-but-real cached answer is more useful
than a failed lookup, and every cached entry records when it was fetched so a
stale hit is visible rather than silent. Bust it with ``--refresh`` on the
Phase 0 collector, or by deleting the directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[4] / "data" / ".tavily_cache"


def cache_dir() -> Path:
    return Path(os.environ.get("SEARCH_CACHE_DIR", str(_DEFAULT_CACHE_DIR)))


def cache_key(query: str, domains: list[str], max_results: int) -> str:
    """Stable key over the full request shape.

    Domains are sorted so that two callers requesting the same domain set in a
    different order share one cache entry.
    """
    payload = json.dumps(
        {"q": query.strip(), "d": sorted(domains), "n": max_results},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheEntry:
    key: str
    query: str
    domains: list[str]
    results: list[dict]
    fetched_at: float
    age_seconds: float

    @property
    def age_hours(self) -> float:
        return self.age_seconds / 3600.0


def read(query: str, domains: list[str], max_results: int) -> CacheEntry | None:
    key = cache_key(query, domains, max_results)
    path = cache_dir() / f"{key}.json"
    if not path.is_file():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None  # a corrupt entry is a cache miss, never a crash
    fetched_at = float(blob.get("fetched_at", 0.0))
    return CacheEntry(
        key=key,
        query=blob.get("query", query),
        domains=blob.get("domains", domains),
        results=blob.get("results", []),
        fetched_at=fetched_at,
        age_seconds=max(0.0, time.time() - fetched_at),
    )


def write(query: str, domains: list[str], max_results: int, results: list[dict]) -> None:
    """Persist a successful live response. Never raises — caching is best-effort."""
    directory = cache_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        key = cache_key(query, domains, max_results)
        payload = {
            "query": query,
            "domains": sorted(domains),
            "max_results": max_results,
            "results": results,
            "fetched_at": time.time(),
        }
        tmp = directory / f".{key}.tmp"
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        # Atomic rename so a crash mid-write cannot leave a half-written entry
        # that a later read would treat as a hit.
        tmp.replace(directory / f"{key}.json")
    except OSError:
        return


def clear() -> int:
    """Delete every cached entry. Returns how many were removed."""
    directory = cache_dir()
    if not directory.is_dir():
        return 0
    removed = 0
    for path in directory.glob("*.json"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def stats() -> dict[str, object]:
    directory = cache_dir()
    if not directory.is_dir():
        return {"dir": str(directory), "entries": 0}
    entries = list(directory.glob("*.json"))
    return {
        "dir": str(directory),
        "entries": len(entries),
        "bytes": sum(p.stat().st_size for p in entries),
    }
