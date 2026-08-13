"""Rate-limit handling and LLM cache-key stability.

The failure that matters most is not a crash — it is a 429 during the Verifier's
audit being indistinguishable from "the Verifier looked and found nothing
sourced". Both produce a report with zero accepted evidence; one is a broken run
and the other is a finding. These tests pin the difference.
"""

import app.llm as llm_module
import pytest

from app.agents.verifier import verify_evidence
from app.llm import (
    RATE_LIMIT_BACKOFF,
    DailyQuotaExhausted,
    ModelUnavailable,
    RateLimited,
    _is_rate_limit,
    _retry_after_seconds,
    call_json,
)
from app.tools import llm_cache

GOOD_URL = "https://zatca.gov.sa/en/eServices/Pages/eServices_002.aspx"


class FakeResponse:
    def __init__(self, status_code=429, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class FakeRateLimitError(Exception):
    def __init__(self, message="Rate limit exceeded", headers=None):
        super().__init__(message)
        self.status_code = 429
        self.response = FakeResponse(429, headers)


class TestRateLimitDetection:
    def test_status_code_attribute(self):
        assert _is_rate_limit(FakeRateLimitError()) is True

    def test_response_status_code(self):
        exc = Exception("boom")
        exc.response = FakeResponse(429)
        assert _is_rate_limit(exc) is True

    def test_message_mentioning_429(self):
        assert _is_rate_limit(Exception("HTTP 429 Too Many Requests")) is True

    def test_class_name_mentioning_rate_limit(self):
        class RateLimitError(Exception):
            pass

        assert _is_rate_limit(RateLimitError("slow down")) is True

    def test_ordinary_timeout_is_not_a_rate_limit(self):
        assert _is_rate_limit(TimeoutError("read timed out")) is False

    def test_value_error_is_not_a_rate_limit(self):
        assert _is_rate_limit(ValueError("bad json")) is False


class TestRetryAfter:
    def test_honours_retry_after_header(self):
        exc = FakeRateLimitError(headers={"retry-after": "12"})
        assert _retry_after_seconds(exc) == 12

    def test_caps_absurd_retry_after(self):
        exc = FakeRateLimitError(headers={"retry-after": "99999"})
        assert _retry_after_seconds(exc) <= 90

    def test_missing_header_returns_none(self):
        assert _retry_after_seconds(FakeRateLimitError()) is None

    def test_garbage_header_returns_none(self):
        exc = FakeRateLimitError(headers={"retry-after": "soon"})
        assert _retry_after_seconds(exc) is None


class TestBackoffBehaviour:
    @pytest.fixture(autouse=True)
    def _no_real_sleeping(self, monkeypatch, tmp_path):
        self.slept: list[float] = []
        monkeypatch.setattr(llm_module.time, "sleep", lambda s: self.slept.append(s))
        monkeypatch.setattr(llm_module, "llm_available", lambda: True)
        monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "llm"))
        yield

    def _always_rate_limited(self, monkeypatch, headers=None):
        class FakeLLM:
            def invoke(self, _messages):
                raise FakeRateLimitError(headers=headers)

        monkeypatch.setattr(llm_module, "get_llm", lambda *a, **k: FakeLLM())

    def test_retries_with_backoff_then_raises_rate_limited(self, monkeypatch):
        self._always_rate_limited(monkeypatch)
        with pytest.raises(RateLimited):
            call_json("verifier", "sys", "user")
        # One full backoff schedule per candidate model (verifier has a fallback).
        assert self.slept[: len(RATE_LIMIT_BACKOFF)] == list(RATE_LIMIT_BACKOFF)

    def test_retry_after_overrides_the_schedule(self, monkeypatch):
        self._always_rate_limited(monkeypatch, headers={"retry-after": "3"})
        with pytest.raises(RateLimited):
            call_json("verifier", "sys", "user")
        assert self.slept[0] == 3

    def test_succeeds_after_a_transient_rate_limit(self, monkeypatch):
        calls = {"n": 0}

        class FlakyLLM:
            def invoke(self, _messages):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise FakeRateLimitError()

                class R:
                    content = '{"ok": true}'

                return R()

        monkeypatch.setattr(llm_module, "get_llm", lambda *a, **k: FlakyLLM())
        assert call_json("verifier", "sys", "user") == {"ok": True}
        assert len(self.slept) == 1

    def test_timeout_does_not_trigger_rate_limit_backoff(self, monkeypatch):
        class TimingOutLLM:
            def invoke(self, _messages):
                raise TimeoutError("read timed out")

        monkeypatch.setattr(llm_module, "get_llm", lambda *a, **k: TimingOutLLM())
        with pytest.raises(ModelUnavailable) as exc:
            call_json("verifier", "sys", "user")
        assert not isinstance(exc.value, RateLimited)
        assert self.slept == []  # no waiting on a non-quota failure

    def test_failed_calls_are_never_cached(self, monkeypatch, tmp_path):
        """A poisoned cache would make a broken run reproducible forever."""
        self._always_rate_limited(monkeypatch)
        with pytest.raises(RateLimited):
            call_json("verifier", "sys", "user")
        assert llm_cache.stats()["entries"] == 0

    def test_timeout_is_never_cached(self, monkeypatch):
        class TimingOutLLM:
            def invoke(self, _m):
                raise TimeoutError("read timed out")

        monkeypatch.setattr(llm_module, "get_llm", lambda *a, **k: TimingOutLLM())
        with pytest.raises(ModelUnavailable):
            call_json("verifier", "sys", "user")
        assert llm_cache.stats()["entries"] == 0

    def test_malformed_json_is_never_cached(self, monkeypatch):
        """extract_json raises before the write, so a garbage reply is not stored."""
        class GarbageLLM:
            def invoke(self, _m):
                return type("R", (), {"content": "I cannot help with that."})()

        monkeypatch.setattr(llm_module, "get_llm", lambda *a, **k: GarbageLLM())
        with pytest.raises(ModelUnavailable):
            call_json("verifier", "sys", "user", attempts=1)
        assert llm_cache.stats()["entries"] == 0

    def test_rate_limit_then_success_caches_only_the_success(self, monkeypatch):
        """The scenario that matters for a regression run after a throttled
        session: a 429 must not leave anything behind, and the eventual real
        answer must be what gets replayed."""
        calls = {"n": 0}

        class FlakyLLM:
            def invoke(self, _m):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise FakeRateLimitError()
                return type("R", (), {"content": '{"verdicts": [{"index": 0, "accepted": true}]}'})()

        monkeypatch.setattr(llm_module, "get_llm", lambda *a, **k: FlakyLLM())
        result = call_json("verifier", "sys", "user")

        assert result == {"verdicts": [{"index": 0, "accepted": True}]}
        assert llm_cache.stats()["entries"] == 1
        # And what comes back out is the real answer, not the failure.
        replayed = llm_cache.read("verifier", llm_module.model_for("verifier"), "sys", "user")
        assert replayed == result

    def test_a_replayed_entry_is_byte_identical(self, monkeypatch, tmp_path):
        """No mutation on the round trip — the regression run replays exactly
        what the successful call produced."""
        monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "roundtrip"))
        payload = {"requirements": [{"name": "VAT", "note": "SAR 375,000 — الضريبة"}]}
        llm_cache.write("vat_registration", "m", "sys", "user", payload)
        assert llm_cache.read("vat_registration", "m", "sys", "user") == payload


class TestVerifierDistinguishesFailureFromFinding:
    """The headline guarantee: a 429 must not read as 'nothing was sourced'."""

    def _evidence(self):
        return [
            {
                "claim": "Businesses must register for VAT.",
                "source_entity": "ZATCA",
                "source_url": GOOD_URL,
                "retrieved_at": "2026-08-12T00:00:00+00:00",
                "confidence": "HIGH",
                "has_explicit_url": True,
            }
        ]

    def test_rate_limited_audit_is_flagged_loudly(self, monkeypatch):
        monkeypatch.setattr("app.agents.verifier.llm_available", lambda: True)

        def boom(*_a, **_k):
            raise RateLimited("verifier: rate limited")

        monkeypatch.setattr("app.agents.verifier.call_json", boom)

        accepted, rejected, decisions = verify_evidence(
            self._evidence(), {GOOD_URL: "Businesses must register for VAT."}
        )
        assert accepted == []
        assert len(rejected) == 1
        text = " ".join(decisions)
        assert "VERIFICATION INCOMPLETE" in text
        assert "rate limited" in text
        assert "NOT a finding" in text
        assert "incomplete" in text.lower()

    def test_withheld_claim_says_not_audited_not_unsupported(self, monkeypatch):
        monkeypatch.setattr("app.agents.verifier.llm_available", lambda: True)
        monkeypatch.setattr(
            "app.agents.verifier.call_json",
            lambda *_a, **_k: (_ for _ in ()).throw(RateLimited("429")),
        )
        _, rejected, _ = verify_evidence(
            self._evidence(), {GOOD_URL: "Businesses must register for VAT."}
        )
        reason = rejected[0]["rejection_reason"]
        assert "NOT AUDITED" in reason
        assert "withheld, not judged unsupported" in reason

    def test_partial_outage_keeps_the_batches_that_succeeded(self, monkeypatch):
        """Batching means one 429 costs a few claims, not the whole audit."""
        monkeypatch.setattr("app.agents.verifier.llm_available", lambda: True)
        monkeypatch.setattr("app.agents.verifier.AUDIT_BATCH_SIZE", 2)

        calls = {"n": 0}

        def flaky(_node, _sys, user, **_k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RateLimited("429")
            import re as _re
            idx = [int(i) for i in _re.findall(r"\[(\d+)\] claim:", user)]
            return {"verdicts": [{"index": i, "accepted": True, "reason": "ok"} for i in idx]}

        monkeypatch.setattr("app.agents.verifier.call_json", flaky)

        evidence = [
            {
                "claim": f"Claim number {n}.",
                "source_entity": "ZATCA",
                "source_url": GOOD_URL,
                "retrieved_at": "2026-08-12T00:00:00+00:00",
                "confidence": "HIGH",
                "has_explicit_url": True,
            }
            for n in range(4)
        ]
        accepted, rejected, decisions = verify_evidence(
            evidence, {GOOD_URL: "Claim number 0. Claim number 1. Claim number 2. Claim number 3."}
        )
        assert len(accepted) == 2, "the successful batch must survive the failed one"
        assert len(rejected) == 2
        assert all("NOT AUDITED" in r["rejection_reason"] for r in rejected)
        assert "2 of 4 claim(s) were NOT audited" in " ".join(decisions)

    def test_sustained_rate_limit_fails_fast_after_the_first_batch(self, monkeypatch):
        """Re-waiting the full backoff per batch would stall the run for minutes."""
        monkeypatch.setattr("app.agents.verifier.llm_available", lambda: True)
        monkeypatch.setattr("app.agents.verifier.AUDIT_BATCH_SIZE", 1)

        calls = {"n": 0}

        def always_limited(*_a, **_k):
            calls["n"] += 1
            raise RateLimited("429")

        monkeypatch.setattr("app.agents.verifier.call_json", always_limited)

        evidence = [
            {
                "claim": f"Claim {n}.",
                "source_entity": "ZATCA",
                "source_url": GOOD_URL,
                "retrieved_at": "2026-08-12T00:00:00+00:00",
                "confidence": "HIGH",
                "has_explicit_url": True,
            }
            for n in range(5)
        ]
        _, rejected, _ = verify_evidence(evidence, {GOOD_URL: "Claim 0. Claim 1."})
        assert len(rejected) == 5
        assert calls["n"] == 1, "only the first batch should pay the backoff cost"

    def test_a_real_rejection_reads_differently(self, monkeypatch):
        monkeypatch.setattr("app.agents.verifier.llm_available", lambda: True)
        monkeypatch.setattr(
            "app.agents.verifier.call_json",
            lambda *_a, **_k: {
                "verdicts": [{"index": 0, "accepted": False, "reason": "unsupported"}]
            },
        )
        _, rejected, decisions = verify_evidence(
            self._evidence(), {GOOD_URL: "Businesses must register for VAT."}
        )
        assert rejected[0]["rejection_reason"] == "unsupported"
        assert "VERIFICATION INCOMPLETE" not in " ".join(decisions)


class TestCacheKeyStability:
    """A warm-up run only primes the recorded take if the key is stable."""

    ARGS = ("verifier", "model-x", "system prompt", "user prompt")

    def test_identical_inputs_give_the_same_key(self):
        assert llm_cache.cache_key(*self.ARGS) == llm_cache.cache_key(*self.ARGS)

    def test_key_is_stable_across_calls_in_sequence(self):
        keys = {llm_cache.cache_key(*self.ARGS) for _ in range(50)}
        assert len(keys) == 1

    @pytest.mark.parametrize("position", range(4))
    def test_every_component_changes_the_key(self, position):
        changed = list(self.ARGS)
        changed[position] = changed[position] + "!"
        assert llm_cache.cache_key(*changed) != llm_cache.cache_key(*self.ARGS)

    def test_roundtrip_returns_the_same_object(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
        payload = {"verdicts": [{"index": 0, "accepted": True}]}
        llm_cache.write(*self.ARGS, payload)
        assert llm_cache.read(*self.ARGS) == payload

    def test_unicode_prompts_are_stable(self, monkeypatch, tmp_path):
        """Prompts carry Arabic corpus text; the key must not depend on encoding luck."""
        monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
        args = ("verifier", "m", "نظام", "اشتراطات المطاعم 375,000")
        llm_cache.write(*args, {"ok": True})
        assert llm_cache.read(*args) == {"ok": True}
        assert llm_cache.cache_key(*args) == llm_cache.cache_key(*args)

    def test_whitespace_difference_is_a_different_key(self):
        """Honest about what 'identical' means — prompts must match exactly."""
        a = llm_cache.cache_key("n", "m", "system", "user")
        b = llm_cache.cache_key("n", "m", "system ", "user")
        assert a != b

    def test_disabled_cache_reads_nothing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
        llm_cache.write(*self.ARGS, {"ok": True})
        monkeypatch.setenv("DISABLE_LLM_CACHE", "1")
        assert llm_cache.read(*self.ARGS) is None


class TestDailyCapFailsFast:
    """A per-day cap and a per-minute throttle need opposite responses.

    Observed live: "Rate limit exceeded: free-models-per-day",
    X-RateLimit-Limit 50, limit_source openrouter_free_tier_daily, resetting at
    00:00 UTC. Backing off 90s per node against that — then retrying the
    fallback model, which draws on the same account-wide allowance — turned a
    fast failure into a ten-minute one.
    """

    @pytest.fixture(autouse=True)
    def _no_sleeping(self, monkeypatch, tmp_path):
        self.slept: list[float] = []
        monkeypatch.setattr(llm_module.time, "sleep", lambda s: self.slept.append(s))
        monkeypatch.setattr(llm_module, "llm_available", lambda: True)
        monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "llm"))
        yield

    def _daily_capped(self, monkeypatch):
        class DailyCapError(Exception):
            status_code = 429

        class FakeLLM:
            def invoke(self, _m):
                raise DailyCapError(
                    "Rate limit exceeded: free-models-per-day. Add 10 credits to "
                    "unlock 1000 free model requests per day"
                )

        monkeypatch.setattr(llm_module, "get_llm", lambda *a, **k: FakeLLM())

    def test_detected_from_the_provider_message(self):
        assert llm_module._is_daily_cap(Exception("Rate limit exceeded: free-models-per-day"))
        assert llm_module._is_daily_cap(Exception("limit_source: openrouter_free_tier_daily"))

    def test_a_plain_throttle_is_not_a_daily_cap(self):
        assert llm_module._is_daily_cap(Exception("429 Too Many Requests")) is False

    def test_raises_daily_quota_exhausted(self, monkeypatch):
        self._daily_capped(monkeypatch)
        with pytest.raises(DailyQuotaExhausted):
            call_json("verifier", "sys", "user")

    def test_does_not_sleep_at_all(self, monkeypatch):
        """The whole point: no 90s of pointless waiting."""
        self._daily_capped(monkeypatch)
        with pytest.raises(DailyQuotaExhausted):
            call_json("verifier", "sys", "user")
        assert self.slept == []

    def test_does_not_try_the_fallback_model(self, monkeypatch):
        """The allowance is account-wide, so Super is capped too."""
        models = []

        class DailyCapError(Exception):
            status_code = 429

        class FakeLLM:
            def invoke(self, _m):
                raise DailyCapError("Rate limit exceeded: free-models-per-day")

        def fake_get_llm(node, *, max_tokens=4096, model=None):
            models.append(model)
            return FakeLLM()

        monkeypatch.setattr(llm_module, "get_llm", fake_get_llm)
        with pytest.raises(DailyQuotaExhausted):
            call_json("verifier", "sys", "user")
        assert len(models) == 1, f"tried {models} — should stop after the first"

    def test_message_is_actionable(self, monkeypatch):
        self._daily_capped(monkeypatch)
        with pytest.raises(DailyQuotaExhausted) as exc:
            call_json("verifier", "sys", "user")
        text = str(exc.value)
        assert "00:00 UTC" in text and "Waiting will not help" in text

    def test_still_a_rate_limit_subclass(self):
        """Callers that catch RateLimited keep working unchanged."""
        assert issubclass(DailyQuotaExhausted, llm_module.RateLimited)

    def test_nothing_is_cached(self, monkeypatch):
        self._daily_capped(monkeypatch)
        with pytest.raises(DailyQuotaExhausted):
            call_json("verifier", "sys", "user")
        assert llm_cache.stats()["entries"] == 0
