"""Regression tests for passage windowing (the "wrong 700 characters" bug).

Origin: the Verifier was handed the first N characters of each source passage.
One source is a 113k-char regulation PDF, so it received a cover page and
rejected well-supported claims for want of evidence it had never been shown.

Two things are pinned here:

1. The CORPUS fallback path is structurally immune — passages are pre-chunked,
   so no corpus passage can ever exceed the window. If chunking is ever removed
   or the chunk size raised above the window, that immunity silently disappears
   and these tests catch it.

2. The LIVE path is NOT immune, and not only for the document that exposed the
   bug. Measured largest live passage per node:
       employment_social_insurance  130,688 chars
       vat_registration             113,540
       food_safety                   71,910
       commercial_registration       24,862
       intellectual_property          5,441
   Four of five nodes exceed the window, so the windowing is exercised against
   real corpus documents of comparable size rather than one synthetic case.
"""

import pytest

from app.agents.verifier import VERIFIER_WINDOW, relevant_excerpt
from app.tools.corpus import load_corpus
from app.tools.hybrid_search import CHUNK_CHARS, build_index


@pytest.fixture(scope="module")
def corpus_by_slug():
    return {d.slug: d for d in load_corpus()}


class TestCorpusPathIsStructurallyImmune:
    def test_no_corpus_chunk_exceeds_the_verifier_window(self):
        """Every corpus passage fits whole into the window, so nothing is trimmed."""
        chunks = build_index()
        assert chunks, "corpus index is empty"
        largest = max(len(c.text) for c in chunks)
        assert largest <= CHUNK_CHARS
        assert CHUNK_CHARS <= VERIFIER_WINDOW, (
            "chunk size exceeds the Verifier window — corpus passages would be "
            "trimmed and the original bug returns on the fallback path"
        )

    def test_short_passage_is_returned_untouched(self):
        chunk = build_index()[0].text
        assert relevant_excerpt("any claim", chunk, VERIFIER_WINDOW) == chunk


class TestLongDocumentWindowing:
    """The live path hands over whole documents; these stand in for that."""

    @pytest.mark.parametrize(
        "slug,needle",
        [
            # ~162k chars — the document that originally exposed the bug.
            ("zatca-vat-implementing-regulations", "Eligible Used Goods"),
            # ~26k chars — a different agency, different structure.
            ("gosi-establishment-registration", "Nitaqat"),
        ],
    )
    def test_finds_a_phrase_buried_deep_in_a_real_document(
        self, corpus_by_slug, slug, needle
    ):
        doc = corpus_by_slug.get(slug)
        if doc is None:
            pytest.skip(f"{slug} not in the corpus")
        assert needle in doc.text, "test needle no longer present — update the fixture"
        assert len(doc.text) > VERIFIER_WINDOW * 5, "document too short to be a real test"

        excerpt = relevant_excerpt(f"A claim about {needle}.", doc.text, VERIFIER_WINDOW)
        assert needle in excerpt, (
            f"windowing failed on {slug}: the supporting phrase was not selected"
        )

    def test_naive_head_trim_would_have_missed_it(self, corpus_by_slug):
        """Demonstrates the regression this guards against."""
        doc = corpus_by_slug.get("zatca-vat-implementing-regulations")
        if doc is None:
            pytest.skip("regulations PDF not in the corpus")
        needle = "Eligible Used Goods"
        assert needle not in doc.text[:VERIFIER_WINDOW], (
            "phrase is near the top, so this no longer demonstrates the bug"
        )
        assert needle in relevant_excerpt(f"About {needle}.", doc.text, VERIFIER_WINDOW)

    def test_scales_to_the_largest_observed_live_passage(self):
        """employment_social_insurance returned 130,688 chars from a live call."""
        filler = "Irrelevant boilerplate about unrelated procedures. " * 2600
        target = (
            "An employer must register the establishment with GOSI within "
            "thirty days of employing the first worker."
        )
        passage = filler + target + filler
        assert len(passage) > 130_000

        excerpt = relevant_excerpt(
            "Employers must register the establishment with GOSI within thirty days.",
            passage,
            VERIFIER_WINDOW,
        )
        assert "thirty days" in excerpt

    def test_numerals_win_over_generic_word_overlap(self):
        """A threshold figure is the strongest signal of the right window."""
        decoy = "registration requirements for the establishment and its owner. " * 300
        target = "the mandatory registration threshold is SAR 375,000 per year."
        passage = decoy + target + decoy

        excerpt = relevant_excerpt(
            "The mandatory registration threshold is SAR 375,000.", passage, 300
        )
        assert "375,000" in excerpt

    def test_window_never_exceeds_requested_width(self, corpus_by_slug):
        doc = corpus_by_slug.get("zatca-vat-implementing-regulations")
        if doc is None:
            pytest.skip("regulations PDF not in the corpus")
        assert len(relevant_excerpt("threshold", doc.text, 400)) <= 400

    def test_claim_with_no_usable_terms_still_returns_something(self):
        passage = "x" * 5000
        excerpt = relevant_excerpt("a of to", passage, 400)
        assert len(excerpt) == 400
