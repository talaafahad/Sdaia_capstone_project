"""Loader for the local government corpus collected in Phase 0.

Each document is a markdown file under ``data/gov_corpus/`` carrying YAML
frontmatter with its provenance. Provenance travels with the text so an
Evidence object can always name the exact page and retrieval moment it came
from — never a filename alone.

The loader refuses to serve a document whose ``source_url`` is not on the
allowlist. A corpus file pointing off-allowlist is a build error, not something
to be silently retrieved and cited.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config.allowlist import entity_for, is_searchable, registered_domain

_DEFAULT_CORPUS_DIR = Path(__file__).resolve().parents[4] / "data" / "gov_corpus"


def corpus_dir() -> Path:
    """Corpus location. Overridable so the container mount can differ."""
    return Path(os.environ.get("GOV_CORPUS_DIR", str(_DEFAULT_CORPUS_DIR)))


@dataclass(frozen=True)
class CorpusDoc:
    slug: str
    title: str
    source_url: str
    source_entity: str
    domain: str
    retrieved_at: str
    categories: tuple[str, ...]
    topics: tuple[str, ...]
    text: str

    @property
    def char_count(self) -> int:
        return len(self.text)


class CorpusError(RuntimeError):
    """Raised when a corpus file is malformed or points off the allowlist."""


def _split_frontmatter(raw: str, path: Path) -> tuple[dict, str]:
    if not raw.startswith("---"):
        raise CorpusError(f"{path.name}: missing YAML frontmatter")
    # Split on the closing fence only, so '---' inside the body is harmless.
    parts = raw.split("\n---\n", 1)
    if len(parts) != 2:
        raise CorpusError(f"{path.name}: unterminated YAML frontmatter")
    meta = yaml.safe_load(parts[0].lstrip("-\n")) or {}
    if not isinstance(meta, dict):
        raise CorpusError(f"{path.name}: frontmatter is not a mapping")
    return meta, parts[1].strip()


def _parse(path: Path) -> CorpusDoc:
    meta, body = _split_frontmatter(path.read_text(encoding="utf-8"), path)

    source_url = str(meta.get("source_url") or "")
    if not source_url:
        raise CorpusError(f"{path.name}: frontmatter has no source_url")
    if not is_searchable(source_url):
        raise CorpusError(
            f"{path.name}: source_url {source_url!r} is not on the allowlist — "
            "a corpus document may never come from an unlisted domain"
        )

    domain = registered_domain(source_url) or ""
    return CorpusDoc(
        slug=str(meta.get("slug") or path.stem),
        title=str(meta.get("title") or path.stem),
        source_url=source_url,
        # Trust the allowlist for the entity name over whatever is in the file.
        source_entity=entity_for(source_url) or str(meta.get("source_entity") or ""),
        domain=domain,
        retrieved_at=str(meta.get("retrieved_at") or ""),
        categories=tuple(meta.get("categories") or ()),
        topics=tuple(meta.get("topics") or ()),
        text=body,
    )


@functools.lru_cache(maxsize=1)
def load_corpus() -> tuple[CorpusDoc, ...]:
    """Every corpus document, parsed and allowlist-checked. Cached per process."""
    directory = corpus_dir()
    if not directory.is_dir():
        return ()
    docs = [_parse(p) for p in sorted(directory.glob("*.md"))]
    return tuple(docs)


def reload_corpus() -> tuple[CorpusDoc, ...]:
    """Drop the cache and re-read from disk (used by tests and the collector)."""
    load_corpus.cache_clear()
    return load_corpus()


def docs_for_domains(domains: set[str] | frozenset[str] | list[str]) -> tuple[CorpusDoc, ...]:
    """Corpus documents whose domain is in the given set."""
    wanted = set(domains)
    return tuple(d for d in load_corpus() if d.domain in wanted)


def docs_for_category(category: str | None) -> tuple[CorpusDoc, ...]:
    """Documents tagged for a business category, plus untagged general ones.

    Untagged documents (VAT, commercial registration) apply to every vertical,
    so they are always included rather than being category-gated.
    """
    docs = load_corpus()
    if not category:
        return docs
    return tuple(d for d in docs if not d.categories or category in d.categories)


def corpus_stats() -> dict[str, object]:
    """Summary used by the /health endpoint and the Phase 0 check."""
    docs = load_corpus()
    by_domain: dict[str, int] = {}
    for doc in docs:
        by_domain[doc.domain] = by_domain.get(doc.domain, 0) + 1
    return {
        "dir": str(corpus_dir()),
        "documents": len(docs),
        "total_chars": sum(d.char_count for d in docs),
        "domains": dict(sorted(by_domain.items())),
    }
