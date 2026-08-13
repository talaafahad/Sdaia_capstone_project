"""On-disk cache for model replies.

Same rationale as the search cache, for a sharper reason: the free Nemotron
tier queues rather than rejects under load, and measured latency is 60-70s for
even a trivial call. A full case makes roughly seven model calls, so an uncached
run takes minutes. Caching by (node, model, prompt) makes a repeat of the same
case near-instant, which is what makes a live demo re-runnable.

Deterministic by construction: every agent runs at temperature 0, so the same
prompt is meant to produce the same answer. Caching does not change behaviour,
it removes the wait.

No expiry, matching the search cache. Delete the directory or use
``clear()`` to bust it.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

_DEFAULT_DIR = Path(__file__).resolve().parents[4] / "data" / ".llm_cache"


def cache_dir() -> Path:
    return Path(os.environ.get("LLM_CACHE_DIR", str(_DEFAULT_DIR)))


def enabled() -> bool:
    return os.environ.get("DISABLE_LLM_CACHE", "").lower() not in ("1", "true", "yes")


def cache_key(node: str, model: str, system_prompt: str, user_prompt: str) -> str:
    payload = json.dumps(
        {"node": node, "model": model, "system": system_prompt, "user": user_prompt},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read(node: str, model: str, system_prompt: str, user_prompt: str) -> Any | None:
    if not enabled():
        return None
    path = cache_dir() / f"{cache_key(node, model, system_prompt, user_prompt)}.json"
    if not path.is_file():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None  # a corrupt entry is a miss, never a crash
    return blob.get("result")


def write(node: str, model: str, system_prompt: str, user_prompt: str, result: Any) -> None:
    """Best-effort persist. Never raises."""
    if not enabled():
        return
    directory = cache_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        key = cache_key(node, model, system_prompt, user_prompt)
        payload = {"node": node, "model": model, "result": result, "cached_at": time.time()}
        tmp = directory / f".{key}.tmp"
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(directory / f"{key}.json")
    except (OSError, TypeError, ValueError):
        return


def clear() -> int:
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
        return {"dir": str(directory), "entries": 0, "enabled": enabled()}
    entries = list(directory.glob("*.json"))
    return {
        "dir": str(directory),
        "entries": len(entries),
        "bytes": sum(p.stat().st_size for p in entries),
        "enabled": enabled(),
    }
