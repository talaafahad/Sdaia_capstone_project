"""Tests for the Phase 0 corpus loader."""

import pytest

from app.config.allowlist import SEARCHABLE_DOMAINS, is_searchable
from app.tools.corpus import (
    CorpusError,
    corpus_dir,
    corpus_stats,
    docs_for_category,
    docs_for_domains,
    load_corpus,
    reload_corpus,
)


@pytest.fixture(autouse=True)
def _fresh_cache():
    reload_corpus()
    yield
    reload_corpus()


class TestCollectedCorpus:
    def test_corpus_directory_exists(self):
        assert corpus_dir().is_dir(), f"expected a corpus at {corpus_dir()}"

    def test_corpus_is_populated(self):
        """Implementation plan Phase 0 asks for roughly 10-15 pages."""
        docs = load_corpus()
        assert len(docs) >= 10, f"only {len(docs)} documents collected"

    def test_every_document_is_allowlisted(self):
        for doc in load_corpus():
            assert is_searchable(doc.source_url), f"{doc.slug} is off-allowlist"
            assert doc.domain in SEARCHABLE_DOMAINS

    def test_every_document_carries_provenance(self):
        for doc in load_corpus():
            assert doc.source_url.startswith("https://"), doc.slug
            assert doc.source_entity, doc.slug
            assert doc.retrieved_at, doc.slug
            assert doc.text.strip(), doc.slug

    def test_documents_have_meaningful_content(self):
        for doc in load_corpus():
            assert doc.char_count >= 400, f"{doc.slug} is only {doc.char_count} chars"

    def test_slugs_are_unique(self):
        slugs = [d.slug for d in load_corpus()]
        assert len(slugs) == len(set(slugs))

    def test_core_pathways_are_covered(self):
        """The coffee-shop vertical needs municipal, VAT and CR sources."""
        domains = {d.domain for d in load_corpus()}
        assert "balady.gov.sa" in domains, "no municipal source"
        assert "zatca.gov.sa" in domains, "no VAT source"
        assert {"business.sa", "mc.gov.sa"} & domains, "no commercial-registration source"

    def test_mobile_cart_source_present_for_second_vertical(self):
        """Section 10's food-truck vertical hinges on the mobile-cart sub-service."""
        slugs = {d.slug for d in load_corpus()}
        assert "balady-mobile-cart-license-issuance" in slugs

    def test_vat_thresholds_are_backed_by_the_corpus(self):
        """Implementation plan section 2.4: verify both thresholds against zatca.gov.sa.

        The deterministic tax core hardcodes SAR 375,000 / 187,500. If a future
        re-collection loses the page that states them, the numbers become
        unsourced and this test is what catches it.
        """
        zatca = "\n".join(d.text for d in load_corpus() if d.domain == "zatca.gov.sa")
        assert "375,000" in zatca, "no ZATCA source states the mandatory threshold"
        assert "187,500" in zatca, "no ZATCA source states the voluntary threshold"

    def test_implementing_regulations_do_not_state_the_numeric_threshold(self):
        """Guards a real hallucination trap found during Phase 0.

        The VAT Implementing Regulations defer the number to "the Mandatory
        Registration Threshold detailed in the Agreement" (the GCC VAT
        Agreement) and never state it. An agent citing this document for
        375,000 would be fabricating. If a future revision of the PDF does state
        it, this test fails loudly and the citation guidance can be revisited.
        """
        docs = {d.slug: d for d in load_corpus()}
        regs = docs.get("zatca-vat-implementing-regulations")
        if regs is None:
            pytest.skip("implementing-regulations PDF not in the corpus")
        assert "375,000" not in regs.text
        assert "Mandatory Registration Threshold" in regs.text


class TestFiltering:
    def test_docs_for_domains_filters(self):
        docs = docs_for_domains({"zatca.gov.sa"})
        assert docs
        assert all(d.domain == "zatca.gov.sa" for d in docs)

    def test_docs_for_domains_ignores_unlisted(self):
        assert docs_for_domains({"astrolabs.com"}) == ()

    def test_category_filter_includes_untagged_general_docs(self):
        """VAT and CR pages carry no category and must apply to every vertical."""
        docs = docs_for_category("food_truck_mobile")
        slugs = {d.slug for d in docs}
        assert "balady-mobile-cart-license-issuance" in slugs
        assert any(d.domain == "zatca.gov.sa" for d in docs), "general VAT doc was filtered out"

    def test_category_filter_excludes_other_verticals(self):
        docs = docs_for_category("professional_office")
        slugs = {d.slug for d in docs}
        assert "balady-mobile-cart-license-issuance" not in slugs

    def test_no_category_returns_everything(self):
        assert len(docs_for_category(None)) == len(load_corpus())


class TestStats:
    def test_stats_shape(self):
        stats = corpus_stats()
        assert stats["documents"] == len(load_corpus())
        assert stats["total_chars"] > 0
        assert isinstance(stats["domains"], dict)


class TestMalformedDocuments:
    def _write(self, tmp_path, monkeypatch, name, content):
        (tmp_path / name).write_text(content, encoding="utf-8")
        monkeypatch.setenv("GOV_CORPUS_DIR", str(tmp_path))
        # Clear the cache without loading — the load itself is what must raise,
        # inside the pytest.raises block rather than here.
        load_corpus.cache_clear()

    def test_off_allowlist_source_url_is_rejected(self, tmp_path, monkeypatch):
        self._write(
            tmp_path,
            monkeypatch,
            "bad.md",
            "---\nslug: bad\nsource_url: https://astrolabs.com/guide\n---\n\nbody text\n",
        )
        with pytest.raises(CorpusError, match="not on the allowlist"):
            load_corpus()

    def test_missing_frontmatter_is_rejected(self, tmp_path, monkeypatch):
        self._write(tmp_path, monkeypatch, "bad.md", "just a body, no frontmatter\n")
        with pytest.raises(CorpusError, match="missing YAML frontmatter"):
            load_corpus()

    def test_missing_source_url_is_rejected(self, tmp_path, monkeypatch):
        self._write(tmp_path, monkeypatch, "bad.md", "---\nslug: bad\n---\n\nbody\n")
        with pytest.raises(CorpusError, match="no source_url"):
            load_corpus()

    def test_missing_directory_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GOV_CORPUS_DIR", str(tmp_path / "nope"))
        reload_corpus()
        assert load_corpus() == ()
