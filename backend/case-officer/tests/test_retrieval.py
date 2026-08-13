"""Tests for live-first retrieval, corpus fallback, hybrid search and caching.

These run offline. The shipped .env carries placeholder keys, so the live path
reports ``no_tavily_api_key`` and the corpus fallback serves — which is exactly
the path that must keep working when Tavily has a bad moment on demo day.
"""



import pytest

from app.tools import search_cache
from app.tools.gov_search import search_gov_sources
from app.tools.hybrid_search import (
    hybrid_search,
    normalize,
    reset_index,
    strip_dot_leaders,
    tokenize,
)
from app.tools.passages import Passage, render_context
from app.tools.retrieval import corpus_fallback, retrieve


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SEARCH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DISABLE_DENSE_SEARCH", "1")  # keep tests deterministic/offline
    reset_index()
    yield
    reset_index()


class TestArabicNormalisation:
    def test_alef_variants_fold_together(self):
        assert normalize("الأنشطة") == normalize("الانشطة")
        assert normalize("إصدار") == normalize("اصدار")

    def test_teh_marbuta_and_yeh_fold(self):
        assert normalize("رخصة") == normalize("رخصه")
        assert normalize("علي") == normalize("على")

    def test_diacritics_are_stripped(self):
        assert normalize("رُخْصَة") == normalize("رخصة")

    def test_latin_case_folds(self):
        assert normalize("VAT Registration") == "vat registration"

    def test_tokenizer_handles_mixed_script(self):
        tokens = tokenize("VAT ضريبة 375,000")
        assert "vat" in tokens
        assert "375" in tokens
        assert any("ضريب" in t for t in tokens)


class TestHybridSearchOverCorpus:
    def test_finds_the_vat_threshold_passage(self):
        results = hybrid_search("mandatory VAT registration threshold 375,000", top_k=5)
        assert results, "corpus search returned nothing for the VAT threshold"
        assert any("375,000" in p.text for p in results)

    def test_threshold_passage_outranks_the_long_regulations_pdf(self):
        """Regression: one 162k-char source used to monopolise every slot.

        The Implementing Regulations never state the figure (Phase 0 finding),
        so if they crowd out the eServices page the VAT node sees only context
        it is forbidden to cite for a number, and reports "unverified" despite
        the corpus holding the answer.
        """
        results = hybrid_search(
            "mandatory VAT registration threshold 375,000",
            domains={"zatca.gov.sa"},
            top_k=3,
        )
        assert any("375,000" in p.text for p in results[:1]), (
            "the page that states the threshold must rank first"
        )

    def test_no_single_document_monopolises_the_results(self):
        results = hybrid_search("VAT registration threshold", domains={"zatca.gov.sa"}, top_k=6)
        from collections import Counter

        per_doc = Counter(p.source_url for p in results)
        assert max(per_doc.values()) <= 2

    def test_max_per_doc_is_configurable(self):
        results = hybrid_search(
            "VAT registration", domains={"zatca.gov.sa"}, top_k=6, max_per_doc=1
        )
        assert len({p.source_url for p in results}) == len(results)

    def test_pdf_contents_pages_are_stripped(self):
        """Dot-leader lines are contents formatting, never an answer."""
        from app.tools.hybrid_search import strip_dot_leaders

        raw = "CHAPTER ONE .......... 3\nCHAPTER TWO ........... 8\nReal prose here."
        assert strip_dot_leaders(raw) == "Real prose here."

    def test_stripping_keeps_prose_adjacent_to_contents(self):
        raw = "INTRO ........ 1\nA Person must register within thirty days."
        cleaned = strip_dot_leaders(raw)
        assert "thirty days" in cleaned
        assert "........" not in cleaned

    def test_no_retrieved_passage_is_a_contents_page(self):
        results = hybrid_search("VAT registration threshold", domains={"zatca.gov.sa"}, top_k=6)
        for passage in results:
            assert "....." not in passage.text

    def test_results_are_scoped_to_requested_domains(self):
        results = hybrid_search("commercial licence requirements", domains={"balady.gov.sa"})
        assert results
        assert all(p.domain == "balady.gov.sa" for p in results)

    def test_domain_scoping_excludes_other_agencies(self):
        results = hybrid_search("VAT registration", domains={"balady.gov.sa"})
        assert all(p.domain == "balady.gov.sa" for p in results)

    def test_origin_is_marked_corpus_fallback(self):
        results = hybrid_search("commercial registration", top_k=3)
        assert results
        assert all(p.origin == "corpus_fallback" for p in results)

    def test_retrieved_at_is_the_collection_time_not_now(self):
        """Prompt rule 6 depends on corpus passages carrying their real age."""
        from datetime import datetime, timezone

        results = hybrid_search("commercial registration", top_k=3)
        assert results
        for passage in results:
            assert passage.retrieved_at
            collected = datetime.fromisoformat(passage.retrieved_at)
            assert collected <= datetime.now(timezone.utc)

    def test_unknown_domain_returns_nothing(self):
        assert hybrid_search("anything", domains={"astrolabs.com"}) == ()

    def test_nonsense_query_returns_nothing_rather_than_noise(self):
        assert hybrid_search("zzzzqqqq xyzzyplugh qwertyuiopasdf") == ()

    def test_category_scoping(self):
        results = hybrid_search("licence", category="food_truck_mobile", top_k=8)
        for passage in results:
            assert passage.domain in {"balady.gov.sa", "zatca.gov.sa", "business.sa",
                                      "mc.gov.sa", "gosi.gov.sa", "monshaat.gov.sa"}


class TestLiveSearchDegradation:
    def test_placeholder_api_key_reports_cleanly(self):
        """An unusable or disabled live path must degrade to fallback, never raise."""
        outcome = search_gov_sources("VAT threshold", domains={"zatca.gov.sa"})
        assert outcome.ok is False
        assert outcome.reason in ("live_search_disabled", "no_tavily_api_key", "no_allowlisted_results", "timeout")
        assert outcome.passages == ()

    def test_empty_domain_set_is_rejected_before_any_call(self):
        outcome = search_gov_sources("anything", domains={"astrolabs.com"})
        assert outcome.reason == "no_allowlisted_domains_requested"

    def test_domains_are_intersected_with_the_allowlist(self):
        outcome = search_gov_sources(
            "x", domains={"zatca.gov.sa", "astrolabs.com"}
        )
        assert outcome.domains_queried == ["zatca.gov.sa"]


class TestFallbackChain:
    def test_falls_back_to_corpus_when_live_unavailable(self):
        outcome = retrieve(
            "mandatory VAT registration threshold",
            domains={"zatca.gov.sa"},
            node="vat_registration",
        )
        assert outcome.path == "corpus_fallback"
        assert outcome.served
        assert outcome.live_reason == "live_search_disabled"
        assert all(p.origin == "corpus_fallback" for p in outcome.passages)

    def test_returns_none_when_both_paths_are_empty(self):
        """Section 2.2 rule 3 territory — the node must mark this unverified."""
        outcome = retrieve(
            "zzzzqqqq xyzzyplugh qwertyuiopasdf",
            domains={"zatca.gov.sa"},
            node="vat_registration",
        )
        assert outcome.path == "none"
        assert outcome.served is False
        assert "NO SOURCE FOUND" in outcome.log_line()

    def test_food_safety_has_no_corpus_fallback(self):
        """Known, accepted risk: sfda.gov.sa yielded no collectable page."""
        outcome = retrieve(
            "food handling requirements", domains={"sfda.gov.sa"}, node="food_safety"
        )
        assert outcome.path == "none"

    def test_log_line_names_the_serving_path(self):
        served = retrieve("commercial registration", domains={"business.sa", "mc.gov.sa"})
        assert "CORPUS FALLBACK" in served.log_line()
        assert "live path unavailable" in served.log_line()

    def test_corpus_fallback_can_be_escalated_directly_by_a_node(self):
        """Used when live returned results but none reached MEDIUM confidence."""
        outcome = corpus_fallback(
            "commercial registration",
            domains={"business.sa", "mc.gov.sa"},
            live_reason="no_evidence_at_medium_or_better",
            node="commercial_registration",
        )
        assert outcome.path == "corpus_fallback"
        assert "no_evidence_at_medium_or_better" in outcome.log_line()


class TestSearchCache:
    def test_key_is_order_independent_for_domains(self):
        a = search_cache.cache_key("q", ["b.gov.sa", "a.gov.sa"], 5)
        b = search_cache.cache_key("q", ["a.gov.sa", "b.gov.sa"], 5)
        assert a == b

    def test_key_changes_with_query(self):
        assert search_cache.cache_key("q1", ["a"], 5) != search_cache.cache_key("q2", ["a"], 5)

    def test_roundtrip(self):
        results = [{"url": "https://zatca.gov.sa/x", "content": "hello"}]
        search_cache.write("q", ["zatca.gov.sa"], 5, results)
        entry = search_cache.read("q", ["zatca.gov.sa"], 5)
        assert entry is not None
        assert entry.results == results
        assert entry.age_seconds >= 0

    def test_miss_returns_none(self):
        assert search_cache.read("never-queried", ["zatca.gov.sa"], 5) is None

    def test_corrupt_entry_is_a_miss_not_a_crash(self):
        search_cache.write("q", ["zatca.gov.sa"], 5, [{"url": "https://zatca.gov.sa/x"}])
        key = search_cache.cache_key("q", ["zatca.gov.sa"], 5)
        (search_cache.cache_dir() / f"{key}.json").write_text("{not json", encoding="utf-8")
        assert search_cache.read("q", ["zatca.gov.sa"], 5) is None

    def test_cached_live_result_serves_without_an_api_key(self):
        """The demo-day safety net: a cached hit serves even with no usable key."""
        search_cache.write(
            "VAT threshold",
            ["zatca.gov.sa"],
            6,
            [
                {
                    "url": "https://zatca.gov.sa/en/eServices/Pages/eServices_002.aspx",
                    "title": "VAT Registration",
                    "content": "Individuals whose annual revenues exceed SAR 375,000.",
                    "score": 0.9,
                }
            ],
        )
        outcome = retrieve("VAT threshold", domains={"zatca.gov.sa"}, max_results=6)
        assert outcome.path == "live"
        assert outcome.cached is True
        assert "CACHED live result" in outcome.log_line()

    def test_cached_off_allowlist_entry_is_dropped(self):
        """A poisoned cache must not smuggle a non-allowlisted source through."""
        search_cache.write(
            "q",
            ["zatca.gov.sa"],
            6,
            [{"url": "https://astrolabs.com/guide", "content": "not official"}],
        )
        outcome = search_gov_sources("q", domains={"zatca.gov.sa"}, max_results=6)
        assert outcome.passages == ()

    def test_clear(self):
        search_cache.write("q", ["zatca.gov.sa"], 5, [{"url": "https://zatca.gov.sa/x"}])
        assert search_cache.clear() >= 1
        assert search_cache.read("q", ["zatca.gov.sa"], 5) is None


class TestContextRendering:
    def test_provenance_travels_with_each_passage(self):
        passage = Passage(
            text="Some requirement.",
            source_url="https://zatca.gov.sa/x",
            source_entity="ZATCA",
            domain="zatca.gov.sa",
            retrieved_at="2026-08-12T12:00:00+00:00",
            title="VAT",
            score=1.0,
            origin="corpus_fallback",
        )
        block = render_context([passage])
        assert "https://zatca.gov.sa/x" in block
        assert "2026-08-12T12:00:00+00:00" in block
        assert "corpus_fallback" in block

    def test_empty_context_is_explicit(self):
        assert "no passages were retrieved" in render_context([])
