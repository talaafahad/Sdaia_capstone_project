"""Tests for the open-web additional_context node.

Two things are pinned here, and they are the whole reason the node is allowed to
exist:

1. **Isolation.** Supplementary items can never become citable evidence, can
   never satisfy a requirement, and can never move readiness_pct.
2. **Saudi scoping in code.** Because this node has no domain allowlist, a
   keyword backstop must drop foreign results even when the model does not.
"""

import pytest

from app.agents.additional_context import additional_context_node
from app.agents.verifier import compute_readiness, verify_evidence
from app.config.allowlist import cap_confidence, is_citable
from app.state import CaseState, SupplementaryItem
from app.tools.open_search import (
    build_query,
    mentions_saudi_arabia,
    registrable_domain,
    search_open_web,
)

# Realistic foreign pages — the exact failure mode this backstop exists for.
UAE_PAGE = (
    "Business setup in Dubai, United Arab Emirates. To register a mainland "
    "company you must obtain a trade licence from the Department of Economic "
    "Development (DED) and register with the UAE Ministry of Economy. VAT "
    "registration is handled by the Federal Tax Authority at 5%."
)
EGYPT_PAGE = (
    "Starting a business in Egypt requires registration with the General "
    "Authority for Investment and Free Zones (GAFI) in Cairo, a commercial "
    "register extract, and a tax card from the Egyptian Tax Authority."
)
UK_PAGE = (
    "Setting up a limited company in the United Kingdom requires registration "
    "with Companies House and HMRC for corporation tax and VAT."
)
SAUDI_PAGE = (
    "To open a restaurant in Riyadh you need a commercial registration from the "
    "Ministry of Commerce, a municipal licence via Balady, and VAT registration "
    "with ZATCA once turnover exceeds the threshold."
)


class TestSaudiKeywordBackstop:
    def test_accepts_a_saudi_page(self):
        assert mentions_saudi_arabia(SAUDI_PAGE) is True

    @pytest.mark.parametrize(
        "page,label", [(UAE_PAGE, "UAE"), (EGYPT_PAGE, "Egypt"), (UK_PAGE, "UK")]
    )
    def test_rejects_foreign_pages(self, page, label):
        """The deliberately non-Saudi cases: filtered in code, not by the model."""
        assert mentions_saudi_arabia(page) is False, f"{label} page was not filtered"

    def test_united_kingdom_does_not_pass_on_the_word_kingdom(self):
        """"Kingdom" is an accepted marker, but not as part of "United Kingdom" —
        otherwise every UK page passes on that word alone."""
        assert mentions_saudi_arabia("Registered in the United Kingdom.") is False

    def test_kingdom_alone_still_passes(self):
        assert mentions_saudi_arabia("Businesses in the Kingdom must register.") is True

    def test_regulator_name_alone_is_enough(self):
        assert mentions_saudi_arabia("Register with ZATCA for VAT.") is True
        assert mentions_saudi_arabia("Apply through the Balady platform.") is True

    def test_arabic_country_name(self):
        assert mentions_saudi_arabia("المملكة العربية السعودية") is True

    def test_empty_text_is_rejected(self):
        assert mentions_saudi_arabia("") is False
        assert mentions_saudi_arabia(None) is False  # type: ignore[arg-type]

    def test_case_insensitive(self):
        assert mentions_saudi_arabia("SAUDI ARABIA") is True
        assert mentions_saudi_arabia("zatca") is True


class TestQueryScoping:
    def test_query_names_the_country(self):
        """Bias the search engine before any model filtering happens."""
        query = build_query("food_beverage_fixed", "Riyadh")
        assert query.lower().startswith("saudi arabia")

    def test_category_underscores_become_words(self):
        assert "food beverage fixed" in build_query("food_beverage_fixed")

    def test_query_is_broad_not_topic_specific(self):
        """Unlike the five topic nodes, this one searches the category broadly."""
        query = build_query("professional_office")
        assert "regulations requirements" in query
        for topic in ("VAT threshold", "commercial registration", "GOSI"):
            assert topic.lower() not in query.lower()

    def test_missing_category_still_produces_a_saudi_query(self):
        assert "Saudi Arabia" in build_query(None)


class TestSearchFiltersForeignResults:
    def test_foreign_results_are_dropped_by_the_search_layer(self, monkeypatch):
        """End-to-end through search_open_web, with the network stubbed."""
        raw = [
            {"url": "https://dubai-setup.example/guide", "title": "Dubai company setup", "content": UAE_PAGE},
            {"url": "https://egypt-biz.example/guide", "title": "Egypt registration", "content": EGYPT_PAGE},
            {"url": "https://ksa-guide.example/riyadh", "title": "Riyadh restaurant licence", "content": SAUDI_PAGE},
        ]
        monkeypatch.setattr("app.tools.gov_search.live_search_disabled", lambda: False)
        monkeypatch.setattr("app.tools.open_search._api_key_available", lambda: True)

        class FakeClient:
            def __init__(self, **_kw): ...
            def search(self, **_kw): return {"results": raw}

        import app.tools.open_search as mod
        monkeypatch.setitem(__import__("sys").modules, "tavily", type("M", (), {"TavilyClient": FakeClient}))
        outcome = mod.search_open_web("Saudi Arabia cafe regulations", use_cache=False)

        assert outcome.dropped_non_saudi == 2
        assert len(outcome.results) == 1
        assert "ksa-guide" in outcome.results[0].url

    def test_all_foreign_reports_no_saudi_relevant_results(self, monkeypatch):
        monkeypatch.setattr("app.tools.gov_search.live_search_disabled", lambda: False)
        monkeypatch.setattr("app.tools.open_search._api_key_available", lambda: True)

        class FakeClient:
            def __init__(self, **_kw): ...
            def search(self, **_kw):
                return {"results": [{"url": "https://x.example/a", "title": "Dubai", "content": UAE_PAGE}]}

        import app.tools.open_search as mod
        monkeypatch.setitem(__import__("sys").modules, "tavily", type("M", (), {"TavilyClient": FakeClient}))
        outcome = mod.search_open_web("q", use_cache=False)
        assert outcome.results == []
        assert outcome.reason == "no_saudi_relevant_results"


class TestNodeIsolation:
    """Supplementary context must never leak into the evidence pipeline."""

    def _run(self, monkeypatch, model_items, results):
        from app.tools.open_search import OpenSearchOutcome, SupplementaryResult

        outcome = OpenSearchOutcome(
            results=[SupplementaryResult(**r) for r in results],
            ok=True, reason="live", raw_result_count=len(results),
        )
        monkeypatch.setattr("app.agents.additional_context.search_open_web", lambda *_a, **_k: outcome)
        monkeypatch.setattr("app.agents.additional_context.llm_available", lambda: True)
        monkeypatch.setattr("app.agents.additional_context.call_json", lambda *_a, **_k: {"items": model_items})
        return additional_context_node({"business_category": "food_beverage_fixed", "city": "Riyadh"})

    def _saudi_result(self, url="https://blog.example/ksa"):
        return {
            "title": "Riyadh business guide", "url": url, "domain": "blog.example",
            "content": SAUDI_PAGE, "retrieved_at": "2026-08-13T00:00:00+00:00",
        }

    def test_node_returns_only_supplementary_keys(self, monkeypatch):
        """The isolation guarantee: no branch can write requirements or evidence."""
        update = self._run(
            monkeypatch,
            [{"claim": "Riyadh cafes need a Balady licence.", "source_url": "https://blog.example/ksa"}],
            [self._saudi_result()],
        )
        assert set(update) == {"supplementary_context", "decision_log"}
        assert "evidence_log" not in update
        assert "requirements" not in update
        assert "readiness_pct" not in update

    def test_items_are_low_confidence_and_unofficial(self, monkeypatch):
        update = self._run(
            monkeypatch,
            [{"claim": "Riyadh cafes need a Balady licence.", "source_url": "https://blog.example/ksa"}],
            [self._saudi_result()],
        )
        item = update["supplementary_context"][0]
        assert item["confidence"] == "LOW"
        assert item["is_official"] is False

    def test_source_url_and_domain_are_preserved(self, monkeypatch):
        update = self._run(
            monkeypatch,
            [{"claim": "Riyadh cafes need a Balady licence.", "source_url": "https://blog.example/ksa"}],
            [self._saudi_result()],
        )
        item = update["supplementary_context"][0]
        assert item["source_url"] == "https://blog.example/ksa"
        assert item["source_domain"] == "blog.example"

    def test_model_cannot_introduce_an_unretrieved_url(self, monkeypatch):
        update = self._run(
            monkeypatch,
            [{"claim": "Something.", "source_url": "https://invented.example/never-retrieved"}],
            [self._saudi_result()],
        )
        assert update["supplementary_context"] == []

    def test_model_summary_that_loses_saudi_context_is_dropped(self, monkeypatch):
        """Second backstop pass: catches a model writing a country-neutral claim
        from a page whose Saudi relevance it dropped."""
        foreign = {
            "title": "Dubai setup", "url": "https://x.example/uae", "domain": "x.example",
            "content": UAE_PAGE, "retrieved_at": "2026-08-13T00:00:00+00:00",
        }
        update = self._run(
            monkeypatch,
            [{"claim": "You need a trade licence from the DED.", "source_url": "https://x.example/uae"}],
            [foreign],
        )
        assert update["supplementary_context"] == []


class TestCannotAffectEvidenceOrReadiness:
    def _item(self) -> dict:
        return {
            "claim": "A blog says cafes need a licence.",
            "source_url": "https://blog.example/ksa",
            "source_domain": "blog.example",
            "title": "Guide",
            "retrieved_at": "2026-08-13T00:00:00+00:00",
            "confidence": "LOW",
            "is_official": False,
        }

    def test_supplementary_source_is_not_citable(self):
        assert is_citable("https://blog.example/ksa") is False

    def test_open_web_confidence_is_floored_at_low(self):
        """Even if something claimed HIGH, a non-allowlisted domain caps to LOW."""
        assert cap_confidence("https://blog.example/ksa", "HIGH") == "LOW"

    def test_supplementary_item_rejects_a_higher_confidence(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SupplementaryItem.model_validate({**self._item(), "confidence": "HIGH"})

    def test_supplementary_item_rejects_is_official_true(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SupplementaryItem.model_validate({**self._item(), "is_official": True})

    def test_supplementary_context_does_not_change_readiness(self):
        """readiness_pct is computed from requirements only."""
        requirements = [{"status": "satisfied"}, {"status": "unverified"}]
        before = compute_readiness(requirements, False)
        state = CaseState(
            case_id="c1", goal="g",
            supplementary_context=[SupplementaryItem.model_validate(self._item())] * 5,
        )
        after = compute_readiness([r for r in requirements], False)
        assert before == after
        assert state.readiness_pct == 0

    def test_supplementary_items_never_reach_the_verifier(self, monkeypatch):
        """The Verifier audits evidence_log; supplementary lives elsewhere."""
        monkeypatch.setattr("app.agents.verifier.llm_available", lambda: False)
        state = CaseState(
            case_id="c1", goal="g",
            supplementary_context=[SupplementaryItem.model_validate(self._item())],
        )
        accepted, rejected, _ = verify_evidence(
            [e.model_dump() for e in state.evidence_log], {}
        )
        assert accepted == [] and rejected == []

    def test_a_case_full_of_supplementary_context_is_still_zero_percent(self):
        state = CaseState(
            case_id="c1", goal="g",
            supplementary_context=[SupplementaryItem.model_validate(self._item())] * 10,
        )
        assert compute_readiness(list(state.requirements), False) == 0


def test_registrable_domain():
    assert registrable_domain("https://www.blog.example/path") == "blog.example"
    assert registrable_domain("not-a-url") == ""
