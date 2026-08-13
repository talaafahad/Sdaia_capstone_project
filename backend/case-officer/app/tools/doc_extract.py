"""Lease/document text extraction — feeds the discrepancy-detection centrepiece.

Implementation plan section 13's closing note: the uploaded document must
populate ``CaseState.area_sqm_from_document`` **directly**, because the
Verifier's discrepancy check depends on that one field being reliably set
before it runs.

Text-layer PDFs and plain text only. Scanned images needing OCR are explicitly
out of scope for the prototype — and, importantly, a scanned PDF is reported as
``no text layer`` rather than as "no area found", so an OCR-needing document is
never mistaken for a document that simply omits the area.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_PAGES = 40

#: Matches "120 sqm", "120 m2", "120 square metres", "المساحة 120 متر مربع".
_AREA_PATTERNS = [
    re.compile(
        r"(?:area|total\s+area|leased\s+area|premises\s+area)\D{0,30}?(\d{1,6}(?:[.,]\d+)?)\s*"
        r"(?:sq\.?\s*m|sqm|m2|m²|square\s+met(?:er|re)s?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(\d{1,6}(?:[.,]\d+)?)\s*(?:sq\.?\s*m|sqm|m2|m²|square\s+met(?:er|re)s?)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:المساحة|مساحة)\D{0,30}?(\d{1,6}(?:[.,]\d+)?)\s*(?:متر\s*مربع|م2|م²)"),
    re.compile(r"(\d{1,6}(?:[.,]\d+)?)\s*(?:متر\s*مربع|م2|م²)"),
]


@dataclass
class ExtractedDocument:
    filename: str
    kind: str  # "pdf" | "txt"
    text: str
    area_sqm: float | None = None
    #: The sentence the area came from, so the conflict record can quote a source.
    area_context: str | None = None
    has_text_layer: bool = True
    notes: list[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.text)


def _to_float(raw: str) -> float | None:
    cleaned = raw.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def find_area_sqm(text: str) -> tuple[float | None, str | None]:
    """First plausible premises area in the document, with its surrounding text.

    Labelled patterns are tried before bare "<n> sqm" so that a lease mentioning
    both a plot area and a leased area prefers the labelled one.
    """
    for pattern in _AREA_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        value = _to_float(match.group(1))
        if value is None or value <= 0:
            continue
        start = max(0, match.start() - 90)
        end = min(len(text), match.end() + 90)
        context = " ".join(text[start:end].split())
        return value, context
    return None, None


def extract_pdf_text(data: bytes) -> tuple[str, bool]:
    """Return (text, has_text_layer)."""
    import pymupdf

    chunks: list[str] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for page in doc[:MAX_PAGES]:
            chunks.append(page.get_text("text"))
    text = "\n".join(chunks).strip()
    return text, bool(text)


def extract_document(filename: str, data: bytes) -> ExtractedDocument:
    """Extract text and the premises area from an uploaded document."""
    lower = filename.lower()
    notes: list[str] = []

    if lower.endswith(".pdf"):
        try:
            text, has_layer = extract_pdf_text(data)
        except Exception as exc:  # noqa: BLE001
            return ExtractedDocument(
                filename=filename,
                kind="pdf",
                text="",
                has_text_layer=False,
                notes=[f"PDF could not be parsed: {exc.__class__.__name__}"],
            )
        if not has_layer:
            notes.append(
                "PDF has no text layer — it is probably a scan. OCR is out of scope for "
                "this prototype, so no area could be read. This is NOT the same as the "
                "document omitting an area."
            )
            return ExtractedDocument(
                filename=filename, kind="pdf", text="", has_text_layer=False, notes=notes
            )
        kind = "pdf"
    else:
        text = data.decode("utf-8", errors="replace").strip()
        kind = "txt"
        if not text:
            notes.append("File was empty.")

    area, context = find_area_sqm(text)
    if area is None and text:
        notes.append("No premises area could be read from the document.")

    return ExtractedDocument(
        filename=filename,
        kind=kind,
        text=text,
        area_sqm=area,
        area_context=context,
        has_text_layer=bool(text),
        notes=notes,
    )
