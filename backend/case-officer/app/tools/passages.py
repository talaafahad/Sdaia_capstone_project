"""The uniform passage shape both retrieval paths produce.

A node's prompt must not be able to tell whether a passage came from a live
Tavily call or the local corpus, except by reading ``origin`` — the citation
rules are identical either way. Keeping one dataclass for both is what makes
that true.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RetrievalPath = Literal["live", "corpus_fallback", "none"]


@dataclass(frozen=True)
class Passage:
    text: str
    source_url: str
    source_entity: str
    domain: str
    #: When the SOURCE was retrieved — "now" for live, the collection timestamp
    #: for corpus passages. Never substitute the current time for a corpus
    #: passage; that would be a false provenance claim.
    retrieved_at: str
    title: str
    score: float
    origin: RetrievalPath

    def as_prompt_block(self, index: int) -> str:
        """Render for the model, with provenance attached to the text itself."""
        return (
            f"[{index}] source_entity: {self.source_entity}\n"
            f"    source_url: {self.source_url}\n"
            f"    retrieved_at: {self.retrieved_at}\n"
            f"    origin: {self.origin}\n"
            f"    title: {self.title}\n"
            f"    text: {self.text}"
        )


def render_context(passages: tuple[Passage, ...] | list[Passage]) -> str:
    """The retrieved-context block injected into a node's user message."""
    if not passages:
        return "(no passages were retrieved from any allowed domain)"
    return "\n\n".join(p.as_prompt_block(i + 1) for i, p in enumerate(passages))
