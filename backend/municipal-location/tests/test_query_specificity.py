"""Regression tests for the Municipal node's query/prompt specificity.

Symptoms this guards against, both observed in real runs:

    "No allowlisted source found specifying requirements for this activity
     and area"
    "The retrieved sources do not mention food_beverage_fixed or area-specific
     requirements for Al-Olaya, Riyadh"

Both are the same failure: demanding that a source match the exact activity
string AND the district AND the premises area, when Balady publishes
requirements for commercial premises generally and never names a district or a
square-metre figure.
"""

import pytest

from app.agent import RATE_LIMIT_BACKOFF, _is_rate_limit
from app.prompts import MUNICIPAL_REQUIREMENTS_SCOPE, build_system_prompt
from app.retrieval import CONTEXT_WINDOW_CHARS, relevant_excerpt, render_context


class FakePassage:
    def __init__(self, text, url="https://balady.gov.sa/en/services/x"):
        self.text = text
        self.source_url = url
        self.source_entity = "Balady"
        self.retrieved_at = "2026-08-13T00:00:00+00:00"
        self.origin = "live"


class TestPromptDoesNotDemandAnExactMatch:
    def test_question_no_longer_binds_district_and_area(self):
        """The question asked what applies in THIS district at THIS area, so a
        source that did not name both was treated as a miss."""
        question = MUNICIPAL_REQUIREMENTS_SCOPE.split("Question:")[1].split("\n\n")[0]
        assert "{district}" not in question
        assert "{area_sqm_stated}" not in question

    def test_explicitly_tells_the_model_not_to_require_an_exact_match(self):
        assert "DO NOT REQUIRE AN EXACT MATCH" in MUNICIPAL_REQUIREMENTS_SCOPE

    def test_names_the_exact_wrong_answer_it_used_to_give(self):
        assert "no source specifies requirements for this activity and area" in (
            MUNICIPAL_REQUIREMENTS_SCOPE
        )

    def test_instructs_recording_conditions_rather_than_discarding(self):
        assert "RECORD CONDITIONS, DO NOT DISCARD THEM" in MUNICIPAL_REQUIREMENTS_SCOPE
        assert "decided downstream" in MUNICIPAL_REQUIREMENTS_SCOPE

    def test_case_facts_are_still_available_for_stating_conditions(self):
        """They must remain in the prompt — just not as a filter."""
        prompt = build_system_prompt(
            "municipal_requirements",
            business_category="food_beverage_fixed",
            city="Riyadh",
            district="Al-Olaya",
            area_sqm_stated=120,
        )
        assert "Al-Olaya" in prompt and "120" in prompt
        assert "never as a filter on what you report" in prompt

    def test_mandatory_approval_line_survived_the_rewrite(self):
        prompt = build_system_prompt("municipal_requirements", city="Riyadh")
        assert "Municipal approval status: NOT VERIFIED" in prompt


class TestContextWindowing:
    def test_long_passage_is_windowed(self):
        """Live momah pages measured 52,713 chars; sending them whole buried the
        requirements in a service catalogue."""
        noise = "Release panoramas. Issue maps and spatial information. " * 900
        target = "Required documents: a lease contract and a civil defence safety certificate."
        passage = noise + target + noise
        assert len(passage) > 50_000

        excerpt = relevant_excerpt("commercial activity licence requirements documents", passage)
        assert len(excerpt) <= CONTEXT_WINDOW_CHARS
        assert "civil defence" in excerpt

    def test_short_passage_is_untouched(self):
        assert relevant_excerpt("q", "short text") == "short text"

    def test_render_context_caps_total_size(self):
        passages = [FakePassage("x" * 50_000) for _ in range(6)]
        rendered = render_context(passages, "commercial licence requirements")
        assert len(rendered) < 6 * (CONTEXT_WINDOW_CHARS + 400)

    def test_render_context_keeps_provenance(self):
        rendered = render_context([FakePassage("some requirement text")], "requirement")
        assert "source_url:" in rendered
        assert "retrieved_at:" in rendered
        assert "Balady" in rendered

    def test_empty_passages_are_explicit(self):
        assert "no passages were retrieved" in render_context([], "q")


class TestRateLimitHandling:
    """The municipal node was the only LLM caller with no 429 backoff, so a rate
    limit surfaced as 'unverified' — indistinguishable from a genuine miss."""

    def test_detects_status_code(self):
        exc = Exception("boom")
        exc.status_code = 429  # type: ignore[attr-defined]
        assert _is_rate_limit(exc) is True

    def test_detects_message(self):
        assert _is_rate_limit(Exception("HTTP 429 Too Many Requests")) is True

    def test_detects_class_name(self):
        class RateLimitError(Exception):
            pass

        assert _is_rate_limit(RateLimitError("slow down")) is True

    def test_timeout_is_not_a_rate_limit(self):
        assert _is_rate_limit(TimeoutError("read timed out")) is False

    def test_backoff_schedule_crosses_a_minute(self):
        """Free-tier limits are per-minute; the last step must clear the window."""
        assert max(RATE_LIMIT_BACKOFF) >= 60

    def test_backoff_retries_then_reraises(self, monkeypatch):
        import app.agent as agent

        calls = {"n": 0}
        slept: list[float] = []

        class Boom(Exception):
            status_code = 429

        class FakeLLM:
            def invoke(self, _m):
                calls["n"] += 1
                raise Boom("429")

        monkeypatch.setattr(agent, "MODEL", "x")
        monkeypatch.setitem(
            __import__("sys").modules, "langchain_openai",
            type("M", (), {"ChatOpenAI": lambda **_k: FakeLLM()}),
        )
        monkeypatch.setitem(
            __import__("sys").modules, "langchain_core.messages",
            type("M", (), {"HumanMessage": lambda content: content,
                           "SystemMessage": lambda content: content}),
        )
        import time as _t
        monkeypatch.setattr(_t, "sleep", lambda s: slept.append(s))

        with pytest.raises(Boom):
            agent._call_json("sys", "user")
        assert calls["n"] == len(RATE_LIMIT_BACKOFF) + 1
        assert slept == list(RATE_LIMIT_BACKOFF)
