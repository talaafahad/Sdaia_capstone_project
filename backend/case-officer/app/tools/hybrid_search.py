"""Hybrid dense + BM25 search over the local corpus — the fallback path.

BM25 is implemented here rather than pulled from a library so the Arabic
normalisation happens inside the tokeniser: the corpus is bilingual, and an
un-normalised Arabic token ("الأنشطة" vs "الانشطة") simply never matches.

The dense half calls OpenRouter's ``/embeddings`` endpoint. It is optional by
design — with no usable API key the search degrades to BM25 alone rather than
failing, which keeps the fallback path working offline and keeps the tests
deterministic. Fusion is Reciprocal Rank Fusion, which needs no score
normalisation between two very differently-scaled rankers.
"""

from __future__ import annotations

import functools
import json
import math
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.tools.corpus import CorpusDoc, load_corpus
from app.tools.passages import Passage

K1 = 1.5
B = 0.75
RRF_K = 60

CHUNK_CHARS = 1000
CHUNK_OVERLAP = 150

_EMBED_CACHE_DIR = Path(__file__).resolve().parents[4] / "data" / ".embed_cache"

# Arabic diacritics (tashkeel), superscript alef, and tatweel.
_TASHKEEL = re.compile(r"[ً-ْٰـ]")
_ALEF_VARIANTS = re.compile(r"[آأإٱ]")
_TOKEN = re.compile(r"[\w؀-ۿ]+", re.UNICODE)


def normalize(text: str) -> str:
    """Fold Arabic orthographic variation and Latin case into one form."""
    text = unicodedata.normalize("NFKC", text)
    text = _TASHKEEL.sub("", text)
    text = _ALEF_VARIANTS.sub("ا", text)  # أ إ آ ٱ -> ا
    text = text.replace("ى", "ي")  # ى -> ي
    text = text.replace("ة", "ه")  # ة -> ه
    text = text.replace("ؤ", "و")  # ؤ -> و
    text = text.replace("ئ", "ي")  # ئ -> ي
    return text.casefold()


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(normalize(text))


@dataclass(frozen=True)
class Chunk:
    doc_slug: str
    title: str
    source_url: str
    source_entity: str
    domain: str
    retrieved_at: str
    text: str
    categories: tuple[str, ...]
    topics: tuple[str, ...]


def _chunk_text(text: str) -> list[str]:
    """Paragraph-aware windows with overlap, so a requirement is not split mid-list."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= CHUNK_CHARS:
            current = f"{current}\n\n{para}" if current else para
            continue
        if current:
            chunks.append(current)
            tail = current[-CHUNK_OVERLAP:]
            current = f"{tail}\n\n{para}"
        else:
            current = para
        # A single paragraph longer than the window (PDF regulation text) gets
        # hard-split rather than dropped.
        while len(current) > CHUNK_CHARS:
            chunks.append(current[:CHUNK_CHARS])
            current = current[CHUNK_CHARS - CHUNK_OVERLAP :]
    if current.strip():
        chunks.append(current)
    return chunks


#: A run of dot leaders is unmistakable table-of-contents formatting.
_DOT_LEADER_LINE = re.compile(r"^.*\.{4,}.*$", re.MULTILINE)


def strip_dot_leaders(text: str) -> str:
    """Remove PDF contents-page lines, keeping the real prose around them.

    Dropping whole chunks was too blunt: a chunk can be half contents page and
    half the first real chapter, and discarding it loses genuine content while
    keeping it lets BM25 rank a contents page above the text that answers the
    question.
    """
    cleaned = _DOT_LEADER_LINE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _chunks_for(doc: CorpusDoc) -> list[Chunk]:
    return [
        Chunk(
            doc_slug=doc.slug,
            title=doc.title,
            source_url=doc.source_url,
            source_entity=doc.source_entity,
            domain=doc.domain,
            retrieved_at=doc.retrieved_at,
            text=body,
            categories=doc.categories,
            topics=doc.topics,
        )
        for body in _chunk_text(strip_dot_leaders(doc.text))
        if body.strip()
    ]


@functools.lru_cache(maxsize=1)
def build_index() -> tuple[Chunk, ...]:
    chunks: list[Chunk] = []
    for doc in load_corpus():
        chunks.extend(_chunks_for(doc))
    return tuple(chunks)


def reset_index() -> None:
    build_index.cache_clear()
    _bm25_stats.cache_clear()


@functools.lru_cache(maxsize=1)
def _bm25_stats() -> tuple[tuple[Counter, ...], dict[str, int], float, int]:
    chunks = build_index()
    tfs = tuple(Counter(tokenize(c.text)) for c in chunks)
    df: dict[str, int] = {}
    for tf in tfs:
        for term in tf:
            df[term] = df.get(term, 0) + 1
    lengths = [sum(tf.values()) for tf in tfs]
    avgdl = (sum(lengths) / len(lengths)) if lengths else 0.0
    return tfs, df, avgdl, len(chunks)


def bm25_scores(query: str, candidate_ids: list[int]) -> dict[int, float]:
    tfs, df, avgdl, total = _bm25_stats()
    if total == 0 or avgdl == 0:
        return {}
    terms = tokenize(query)
    scores: dict[int, float] = {}
    for idx in candidate_ids:
        tf = tfs[idx]
        length = sum(tf.values())
        score = 0.0
        for term in terms:
            freq = tf.get(term, 0)
            if not freq:
                continue
            n_q = df.get(term, 0)
            idf = math.log(1 + (total - n_q + 0.5) / (n_q + 0.5))
            denom = freq + K1 * (1 - B + B * length / avgdl)
            score += idf * (freq * (K1 + 1)) / denom
        if score > 0:
            scores[idx] = score
    return scores


# --------------------------------------------------------------------------
# Dense half — optional, degrades to BM25-only when unavailable
# --------------------------------------------------------------------------

_PLACEHOLDER_MARKERS = ("xxxx", "replace-me", "your-key", "changeme")


def embedding_model() -> str:
    """Handoff doc section 1's pick, swappable without a code change.

    Section 1 flags that its Arabic coverage is unconfirmed and suggests
    ``baai/bge-m3`` if retrieval quality on Arabic is visibly weaker. Both are
    served by OpenRouter, so switching is an env var.
    """
    return os.environ.get("EMBEDDING_MODEL", "nvidia/nemotron-3-embed-1b:free")


def _dense_available() -> bool:
    if os.environ.get("DISABLE_DENSE_SEARCH", "").lower() in ("1", "true", "yes"):
        return False
    from app.config.settings import settings

    key = (settings.openrouter_api_key or "").strip().lower()
    return bool(key) and not any(marker in key for marker in _PLACEHOLDER_MARKERS)


def _embed(texts: list[str]) -> list[list[float]] | None:
    """Embed via OpenRouter. Returns None on any failure — never raises."""
    from app.config.settings import settings

    try:
        import httpx

        response = httpx.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={"model": embedding_model(), "input": texts},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json().get("data") or []
        return [row["embedding"] for row in data]
    except Exception:  # noqa: BLE001 — dense is optional by design
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _chunk_vectors() -> list[list[float]] | None:
    """Corpus embeddings, cached on disk so they are computed once per model."""
    chunks = build_index()
    if not chunks:
        return None
    cache_path = _EMBED_CACHE_DIR / f"{embedding_model().replace('/', '_')}.json"
    if cache_path.is_file():
        try:
            blob = json.loads(cache_path.read_text(encoding="utf-8"))
            if blob.get("count") == len(chunks):
                return blob["vectors"]
        except (json.JSONDecodeError, OSError, KeyError):
            pass
    vectors = _embed([c.text for c in chunks])
    if vectors is None or len(vectors) != len(chunks):
        return None
    try:
        _EMBED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"count": len(chunks), "vectors": vectors}), encoding="utf-8"
        )
    except OSError:
        pass
    return vectors


def dense_scores(query: str, candidate_ids: list[int]) -> dict[int, float]:
    if not _dense_available():
        return {}
    vectors = _chunk_vectors()
    if vectors is None:
        return {}
    query_vec = _embed([query])
    if not query_vec:
        return {}
    q = query_vec[0]
    return {idx: _cosine(q, vectors[idx]) for idx in candidate_ids}


# --------------------------------------------------------------------------
# Fusion
# --------------------------------------------------------------------------


def _rrf(rankings: list[list[int]]) -> dict[int, float]:
    """Reciprocal Rank Fusion — combines rankers without score normalisation."""
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)
    return fused


#: At most this many chunks from any one document may occupy the final result
#: set. Without it a single very long source (the 162k-char VAT Implementing
#: Regulations) wins every slot on term frequency alone and crowds out the
#: shorter page that actually states the figure being asked about.
MAX_CHUNKS_PER_DOC = 2


def hybrid_search(
    query: str,
    domains: set[str] | frozenset[str] | list[str] | None = None,
    top_k: int = 5,
    category: str | None = None,
    max_per_doc: int = MAX_CHUNKS_PER_DOC,
) -> tuple[Passage, ...]:
    """Search the local corpus, scoped to the same domains the live call used."""
    chunks = build_index()
    if not chunks:
        return ()

    wanted = set(domains) if domains else None
    candidate_ids = [
        i
        for i, c in enumerate(chunks)
        if (wanted is None or c.domain in wanted)
        and (category is None or not c.categories or category in c.categories)
    ]
    if not candidate_ids:
        return ()

    lexical = bm25_scores(query, candidate_ids)
    if not lexical:
        return ()

    rankings = [sorted(lexical, key=lambda i: lexical[i], reverse=True)]
    semantic = dense_scores(query, candidate_ids)
    if semantic:
        rankings.append(sorted(semantic, key=lambda i: semantic[i], reverse=True))

    fused = _rrf(rankings)
    ranked = sorted(fused, key=lambda i: fused[i], reverse=True)

    # Enforce per-document diversity while preserving fused order.
    ordered: list[int] = []
    per_doc: Counter = Counter()
    for idx in ranked:
        slug = chunks[idx].doc_slug
        if per_doc[slug] >= max_per_doc:
            continue
        per_doc[slug] += 1
        ordered.append(idx)
        if len(ordered) == top_k:
            break

    return tuple(
        Passage(
            text=chunks[i].text,
            source_url=chunks[i].source_url,
            source_entity=chunks[i].source_entity,
            domain=chunks[i].domain,
            # The corpus collection time — NOT now. Rule 6 of the node prompts
            # depends on this being honest.
            retrieved_at=chunks[i].retrieved_at,
            title=chunks[i].title,
            score=fused[i],
            origin="corpus_fallback",
        )
        for i in ordered
    )
