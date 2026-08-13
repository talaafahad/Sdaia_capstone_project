"""Tests for lease/document extraction — feeds the discrepancy centrepiece."""

import pymupdf

from app.tools.doc_extract import extract_document, find_area_sqm


def _pdf(text_lines: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 80
    for line in text_lines:
        page.insert_text((50, y), line, fontsize=11)
        y += 20
    data = doc.tobytes()
    doc.close()
    return data


class TestAreaPatterns:
    def test_labelled_area(self):
        value, _ = find_area_sqm("The leased area of the premises is 95 sqm.")
        assert value == 95

    def test_m2_notation(self):
        value, _ = find_area_sqm("Total area: 120.5 m2")
        assert value == 120.5

    def test_square_metres_spelled_out(self):
        value, _ = find_area_sqm("Premises area of 210 square metres")
        assert value == 210

    def test_thousands_separator(self):
        value, _ = find_area_sqm("area 1,250 sqm")
        assert value == 1250

    def test_arabic_area(self):
        value, _ = find_area_sqm("المساحة 95 متر مربع")
        assert value == 95

    def test_labelled_beats_bare_number(self):
        """A lease naming both a plot and a leased area must prefer the label."""
        text = "Plot: 400 sqm. The leased area of the premises is 95 sqm."
        value, _ = find_area_sqm(text)
        assert value == 95

    def test_no_area_returns_none(self):
        value, context = find_area_sqm("This lease has no measurements.")
        assert value is None and context is None

    def test_context_is_returned(self):
        _, context = find_area_sqm("Clause 3.1 the leased area is 95 sqm in Al-Olaya.")
        assert context and "95" in context


class TestExtractDocument:
    def test_pdf_with_text_layer(self):
        data = _pdf(["LEASE AGREEMENT", "The leased area of the premises is 95 sqm."])
        result = extract_document("lease.pdf", data)
        assert result.kind == "pdf"
        assert result.has_text_layer is True
        assert result.area_sqm == 95

    def test_pdf_without_text_layer_is_distinguished_from_missing_area(self):
        """A scan and a lease that omits the area are different failures."""
        empty = pymupdf.open()
        empty.new_page()
        data = empty.tobytes()
        empty.close()

        result = extract_document("scan.pdf", data)
        assert result.has_text_layer is False
        assert result.area_sqm is None
        assert any("no text layer" in n.lower() for n in result.notes)
        assert any("OCR" in n for n in result.notes)

    def test_pdf_with_text_but_no_area(self):
        data = _pdf(["LEASE AGREEMENT", "No measurements are stated."])
        result = extract_document("lease.pdf", data)
        assert result.has_text_layer is True
        assert result.area_sqm is None
        assert any("No premises area" in n for n in result.notes)

    def test_plain_text_document(self):
        result = extract_document("notes.txt", b"The leased area is 88 sqm.")
        assert result.kind == "txt"
        assert result.area_sqm == 88

    def test_corrupt_pdf_reports_cleanly(self):
        result = extract_document("broken.pdf", b"not a pdf at all")
        assert result.area_sqm is None
        assert result.has_text_layer is False
        assert result.notes
