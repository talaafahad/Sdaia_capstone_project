"""Live-first retrieval for the Municipal service, scoped to Balady.

Same contract as the Case Officer's retrieval layer (live Tavily → corpus
fallback → nothing), implemented compactly here because the two services build
into separate containers. Canonical version:
``backend/case-officer/app/tools/retrieval.py``.
"""

from __future__ import annotations

import math
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.allowlist import entity_for, include_domains, is_citable, registered_domain
from app.settings import settings

LIVE_SEARCH_TIMEOUT_SECONDS = int(os.environ.get("LIVE_SEARCH_TIMEOUT_SECONDS", "12"))
_PLACEHOLDER_MARKERS = ("xxxx", "replace-me", "your-key", "changeme")

_DEFAULT_CORPUS = Path(__file__).resolve().parents[3] / "data" / "gov_corpus"

K1, B, RRF_K = 1.5, 0.75, 60
CHUNK_CHARS, CHUNK_OVERLAP = 1000, 150
MAX_CHUNKS_PER_DOC = 2

_TASHKEEL = re.compile(r"[ً-ْٰـ]")
_ALEF = re.compile(r"[آأإٱ]")
_TOKEN = re.compile(r"[\w؀-ۿ]+", re.UNICODE)
_DOT_LEADER_LINE = re.compile(r"^.*\.{4,}.*$", re.MULTILINE)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _TASHKEEL.sub("", text)
    text = _ALEF.sub("ا", text)
    for a, b in (("ى", "ي"), ("ة", "ه"), ("ؤ", "و"), ("ئ", "ي")):
        text = text.replace(a, b)
    return text.casefold()


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(normalize(text))


@dataclass(frozen=True)
class Passage:
    text: str
    source_url: str
    source_entity: str
    domain: str
    retrieved_at: str
    title: str
    score: float
    origin: str

    def as_prompt_block(self, index: int) -> str:
        return (
            f"[{index}] source_entity: {self.source_entity}\n"
            f"    source_url: {self.source_url}\n"
            f"    retrieved_at: {self.retrieved_at}\n"
            f"    origin: {self.origin}\n"
            f"    text: {self.text}"
        )


def render_context(passages) -> str:
    if not passages:
        return "(no passages were retrieved from any allowed domain)"
    return "\n\n".join(p.as_prompt_block(i + 1) for i, p in enumerate(passages))


@dataclass(frozen=True)
class RetrievalOutcome:
    passages: tuple[Passage, ...]
    path: str
    live_reason: str
    latency_ms: int = 0
    node: str = ""

    @property
    def served(self) -> bool:
        return bool(self.passages)

    def log_line(self) -> str:
        label = f"[{self.node}] " if self.node else ""
        if self.path == "live":
            return f"{label}served LIVE (Tavily): {len(self.passages)} passages in {self.latency_ms}ms."
        if self.path == "corpus_fallback":
            return (
                f"{label}served CORPUS FALLBACK: {len(self.passages)} passages "
                f"(live path unavailable — {self.live_reason})."
            )
        return (
            f"{label}NO SOURCE FOUND: live path {self.live_reason}, corpus fallback also "
            "empty. Requirement must be marked unverified."
        )


# --------------------------------------------------------------------------- corpus


def _corpus_dir() -> Path:
    return Path(os.environ.get("GOV_CORPUS_DIR", str(_DEFAULT_CORPUS)))


_INDEX: list[dict] | None = None


def build_index() -> list[dict]:
    global _INDEX
    if _INDEX is not None:
        return _INDEX

    chunks: list[dict] = []
    directory = _corpus_dir()
    if directory.is_dir():
        for path in sorted(directory.glob("*.md")):
            raw = path.read_text(encoding="utf-8")
            if not raw.startswith("---"):
                continue
            parts = raw.split("\n---\n", 1)
            if len(parts) != 2:
                continue
            meta = yaml.safe_load(parts[0].lstrip("-\n")) or {}
            url = str(meta.get("source_url") or "")
            if not is_citable(url):
                continue  # this service only indexes what it may cite
            body = _DOT_LEADER_LINE.sub("", parts[1]).strip()
            for piece in _split(body):
                chunks.append(
                    {
                        "text": piece,
                        "url": url,
                        "entity": entity_for(url) or "",
                        "domain": registered_domain(url) or "",
                        "retrieved_at": str(meta.get("retrieved_at") or ""),
                        "title": str(meta.get("title") or path.stem),
                        "slug": str(meta.get("slug") or path.stem),
                        "categories": tuple(meta.get("categories") or ()),
                    }
                )
    _INDEX = chunks
    return _INDEX


def reset_index() -> None:
    global _INDEX
    _INDEX = None


def _split(text: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= CHUNK_CHARS:
            current = f"{current}\n\n{para}" if current else para
            continue
        if current:
            out.append(current)
            current = f"{current[-CHUNK_OVERLAP:]}\n\n{para}"
        else:
            current = para
        while len(current) > CHUNK_CHARS:
            out.append(current[:CHUNK_CHARS])
            current = current[CHUNK_CHARS - CHUNK_OVERLAP :]
    if current.strip():
        out.append(current)
    return out


def corpus_search(query: str, top_k: int = 5, category: str | None = None) -> tuple[Passage, ...]:
    chunks = build_index()
    if not chunks:
        return ()
    ids = [
        i
        for i, c in enumerate(chunks)
        if category is None or not c["categories"] or category in c["categories"]
    ]
    if not ids:
        return ()

    tfs = [Counter(tokenize(chunks[i]["text"])) for i in ids]
    df: dict[str, int] = {}
    for tf in tfs:
        for term in tf:
            df[term] = df.get(term, 0) + 1
    lengths = [sum(tf.values()) for tf in tfs]
    avgdl = sum(lengths) / len(lengths) if lengths else 0.0
    if not avgdl:
        return ()

    terms = tokenize(query)
    scores: dict[int, float] = {}
    for pos, idx in enumerate(ids):
        tf = tfs[pos]
        length = lengths[pos]
        score = 0.0
        for term in terms:
            freq = tf.get(term, 0)
            if not freq:
                continue
            n_q = df.get(term, 0)
            idf = math.log(1 + (len(ids) - n_q + 0.5) / (n_q + 0.5))
            score += idf * (freq * (K1 + 1)) / (freq + K1 * (1 - B + B * length / avgdl))
        if score > 0:
            scores[idx] = score
    if not scores:
        return ()

    ranked = sorted(scores, key=lambda i: scores[i], reverse=True)
    picked: list[int] = []
    per_doc: Counter = Counter()
    for idx in ranked:
        slug = chunks[idx]["slug"]
        if per_doc[slug] >= MAX_CHUNKS_PER_DOC:
            continue
        per_doc[slug] += 1
        picked.append(idx)
        if len(picked) == top_k:
            break

    return tuple(
        Passage(
            text=chunks[i]["text"],
            source_url=chunks[i]["url"],
            source_entity=chunks[i]["entity"],
            domain=chunks[i]["domain"],
            retrieved_at=chunks[i]["retrieved_at"],
            title=chunks[i]["title"],
            score=scores[i],
            origin="corpus_fallback",
        )
        for i in picked
    )


# --------------------------------------------------------------------------- live


def _tavily_available() -> bool:
    key = (settings.tavily_api_key or "").strip().lower()
    return bool(key) and not any(m in key for m in _PLACEHOLDER_MARKERS)


def live_search(query: str, max_results: int = 5) -> tuple[tuple[Passage, ...], str, int]:
    import time

    started = time.perf_counter()
    if not _tavily_available():
        return (), "no_tavily_api_key", 0
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(
            query=query,
            include_domains=include_domains(),
            max_results=max_results,
            search_depth="advanced",
            include_raw_content=True,
            timeout=LIVE_SEARCH_TIMEOUT_SECONDS,
        )
        results = list(response.get("results") or [])
    except Exception as exc:  # noqa: BLE001
        name = exc.__class__.__name__
        reason = "timeout" if "timeout" in name.lower() else f"error:{name}"
        return (), reason, int((time.perf_counter() - started) * 1000)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    passages = []
    for item in results:
        url = str(item.get("url") or "")
        if not is_citable(url):
            continue  # defense in depth over include_domains
        text = str(item.get("raw_content") or item.get("content") or "").strip()
        if not text:
            continue
        passages.append(
            Passage(
                text=text,
                source_url=url,
                source_entity=entity_for(url) or "",
                domain=registered_domain(url) or "",
                retrieved_at=now,
                title=str(item.get("title") or ""),
                score=float(item.get("score") or 0.0),
                origin="live",
            )
        )
    latency = int((time.perf_counter() - started) * 1000)
    if not passages:
        return (), "no_allowlisted_results", latency
    return tuple(passages), "live", latency


def retrieve(query: str, *, category: str | None = None, top_k: int = 5, node: str = "") -> RetrievalOutcome:
    passages, reason, latency = live_search(query, max_results=top_k)
    if passages:
        return RetrievalOutcome(passages[:top_k], "live", reason, latency, node)
    fallback = corpus_search(query, top_k=top_k, category=category)
    return RetrievalOutcome(
        fallback, "corpus_fallback" if fallback else "none", reason, latency, node
    )
