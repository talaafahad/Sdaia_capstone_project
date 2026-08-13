"""Domain-checked page fetch — defense in depth (implementation plan section 0).

The allowlist is enforced at the search layer already. It is enforced again here
because a fetch tool that will retrieve any URL handed to it is a hole in the
guardrail: a model that emits an off-allowlist URL must not be able to make the
system go and read it.

Redirects are followed manually so that a redirect *off* the allowlist is
refused rather than silently followed to an unlisted destination.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.config.allowlist import entity_for, is_searchable, registered_domain
from app.tools.passages import Passage

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

FETCH_TIMEOUT_SECONDS = 15
MAX_REDIRECTS = 5
MAX_BYTES = 4_000_000


class DomainNotAllowed(ValueError):
    """Raised when a fetch is attempted against a non-allowlisted URL."""


@dataclass(frozen=True)
class FetchResult:
    ok: bool
    url: str
    status_code: int | None
    text: str
    reason: str

    def as_passage(self) -> Passage | None:
        if not self.ok or not self.text.strip():
            return None
        domain = registered_domain(self.url) or ""
        return Passage(
            text=self.text,
            source_url=self.url,
            source_entity=entity_for(self.url) or domain,
            domain=domain,
            retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            title="",
            score=1.0,
            origin="live",
        )


def _extract_text(html: str) -> str:
    """Strip markup to readable text. Mirrors the Phase 0 collector's rules."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    # Do NOT strip <form>: the .aspx government portals wrap the entire page
    # body in <form runat="server">.
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "button"]):
        tag.decompose()
    for name in ("nav", "header", "footer"):
        for tag in soup.find_all(name):
            tag.decompose()
    body = soup.body or soup
    return " ".join(body.get_text(" ", strip=True).split())


def fetch_page(url: str) -> FetchResult:
    """Fetch an allowlisted page. Never raises for network problems."""
    if not is_searchable(url):
        raise DomainNotAllowed(
            f"refusing to fetch {url!r} — not on the allowlist (implementation plan section 0)"
        )

    current = url
    try:
        with httpx.Client(
            follow_redirects=False,
            timeout=FETCH_TIMEOUT_SECONDS,
            headers={"User-Agent": UA, "Accept-Language": "en,ar;q=0.8"},
        ) as client:
            for _ in range(MAX_REDIRECTS):
                response = client.get(current)
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        return FetchResult(False, current, response.status_code, "", "redirect_without_location")
                    nxt = str(httpx.URL(current).join(location))
                    if not is_searchable(nxt):
                        # The important case: a redirect that leaves the allowlist.
                        return FetchResult(
                            False, current, response.status_code, "", f"redirect_off_allowlist:{nxt}"
                        )
                    current = nxt
                    continue

                if response.status_code >= 400:
                    return FetchResult(False, current, response.status_code, "", f"http_{response.status_code}")

                content = response.content[:MAX_BYTES]
                ctype = response.headers.get("content-type", "")
                if "pdf" in ctype.lower() or current.lower().endswith(".pdf"):
                    import pymupdf

                    with pymupdf.open(stream=content, filetype="pdf") as doc:
                        text = "\n".join(p.get_text("text") for p in doc[:40])
                else:
                    text = _extract_text(content.decode(response.encoding or "utf-8", "replace"))
                return FetchResult(True, current, response.status_code, text, "ok")

            return FetchResult(False, current, None, "", "too_many_redirects")
    except Exception as exc:  # noqa: BLE001 — a fetch failure is a retrieval miss
        return FetchResult(False, current, None, "", f"error:{exc.__class__.__name__}")
