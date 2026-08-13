"""LLM client and per-node model assignment.

Model picks come from the handoff doc section 1 — match the model to what the
node actually needs rather than putting the biggest model on every node. All
four chat slugs were re-verified against openrouter.ai/api/v1/models on
2026-08-12, as section 1 instructs.

Temperature is 0 everywhere (implementation plan section 7): every node here
either touches a citation or a numeric claim, and creative variance has no place
in a system whose value proposition is not hallucinating.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any

_LOG = logging.getLogger(__name__)

from app.config.settings import settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

ULTRA = "nvidia/nemotron-3-ultra-550b-a55b:free"
SUPER = "nvidia/nemotron-3-super-120b-a12b:free"
NANO_9B = "nvidia/nemotron-nano-9b-v2:free"
NANO_30B = "nvidia/nemotron-3-nano-30b-a3b:free"
EMBED = "nvidia/nemotron-3-embed-1b:free"


@dataclass(frozen=True)
class ModelChoice:
    model: str
    why: str
    #: Used when the primary is rate-limited. Section 1 says the Verifier may
    #: drop to Super under contention (it runs once per case) before the
    #: Regulation Router does (it may run several retrieval passes).
    fallback: str | None = None


#: node id -> model. Retrieval node ids match app.agents.prompts.NODES.
MODEL_ASSIGNMENTS: dict[str, ModelChoice] = {
    "intake_planner": ModelChoice(
        NANO_9B,
        "Structured field extraction and classification from the user's own words — "
        "not a task needing the biggest model.",
    ),
    # Every Regulation Router topic node is citation-critical, so all get Ultra.
    "commercial_registration": ModelChoice(
        ULTRA, "Citation discipline is make-or-break on this node.", SUPER
    ),
    "vat_registration": ModelChoice(
        ULTRA, "Numeric threshold reporting — the highest-risk claim in the system.", SUPER
    ),
    "food_safety": ModelChoice(
        ULTRA, "Must resist applying manufacturing rules to food service by analogy.", SUPER
    ),
    "employment_social_insurance": ModelChoice(
        ULTRA, "Multi-domain node that can meet a semi-official source.", SUPER
    ),
    "intellectual_property": ModelChoice(
        ULTRA, "Must not present an optional registration as mandatory.", SUPER
    ),
    "municipal_requirements": ModelChoice(
        SUPER,
        "Narrower, well-scoped agent on a separate A2A service; 120B/12B active is "
        "sized for it.",
    ),
    "competitor_lookup": ModelChoice(
        SUPER, "Restates a tool result; runs in the same service as municipal_requirements."
    ),
    "verifier": ModelChoice(
        ULTRA,
        "The hallucination firewall. Runs once per case, so Ultra is cheap here; "
        "section 1 says drop THIS node to Super first under rate-limit contention.",
        SUPER,
    ),
    "documentation": ModelChoice(
        NANO_30B, "Templating-heavy with light reasoning; 256K context suits the assembly."
    ),
    "tax_explanation": ModelChoice(
        NANO_9B,
        "Restates a dict the deterministic core already decided. Minimal task, and "
        "explicitly NOT in the decision path.",
    ),
}

_PLACEHOLDER_MARKERS = ("xxxx", "replace-me", "your-key", "changeme")


class ModelUnavailable(RuntimeError):
    """A model call could not be completed for an infrastructure reason.

    Distinct from "the model answered and the answer was no". Callers must not
    treat this as a finding — see the Verifier, where conflating the two would
    turn a rate limit into a report claiming nothing was sourced.
    """


class RateLimited(ModelUnavailable):
    """The provider returned 429 (or an equivalent quota signal)."""


#: Backoff schedule between attempts on the same model, in seconds. Free-tier
#: limits are per-minute, so the last step deliberately crosses a minute
#: boundary rather than hammering a window that has not reset.
RATE_LIMIT_BACKOFF = (5, 20, 65)

MAX_RETRY_AFTER_SECONDS = 90


def _is_rate_limit(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    if status == 429:
        return True
    response = getattr(exc, "response", None)
    if response is not None and getattr(response, "status_code", None) == 429:
        return True
    text = f"{exc.__class__.__name__} {exc}".lower()
    return "ratelimit" in text.replace("_", "").replace(" ", "") or "429" in text


def _retry_after_seconds(exc: Exception) -> float | None:
    """Honour the provider's own Retry-After when it sends one."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    for key in ("retry-after", "Retry-After", "x-ratelimit-reset-after"):
        raw = headers.get(key) if hasattr(headers, "get") else None
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return min(value, MAX_RETRY_AFTER_SECONDS)
    return None


def llm_available() -> bool:
    key = (settings.openrouter_api_key or "").strip().lower()
    return bool(key) and not any(m in key for m in _PLACEHOLDER_MARKERS)


def model_for(node: str) -> str:
    """Model slug for a node, with an env override for demo-day contention."""
    override = os.environ.get(f"MODEL_{node.upper()}")
    if override:
        return override
    choice = MODEL_ASSIGNMENTS.get(node)
    if choice is None:
        raise KeyError(f"no model assigned for node {node!r}")
    return choice.model


#: Measured free-tier latency is 60-70s for even a trivial 300-token call —
#: these models queue rather than reject under load. A 120s ceiling therefore
#: fails on any realistically-sized prompt. Configurable for demo day.
LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", "240"))


def get_llm(node: str, *, max_tokens: int = 4096, model: str | None = None):
    """A temperature-0 chat client for a node, routed through OpenRouter."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model or model_for(node),
        api_key=settings.openrouter_api_key,
        base_url=OPENROUTER_BASE_URL,
        temperature=0,
        max_tokens=max_tokens,
        timeout=LLM_TIMEOUT_SECONDS,
        # Retries are handled in call_json so a failure can switch models
        # rather than re-queueing on the same congested one.
        max_retries=0,
        default_headers={
            "HTTP-Referer": "https://github.com/govflow-ksa",
            "X-Title": "GovFlow KSA",
        },
    )


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Parse a model's JSON reply defensively.

    The free Nemotron tier does not reliably honour a JSON response_format, and
    some variants emit a reasoning preamble before the object. Rather than fail
    the whole node on formatting, pull the first well-formed JSON value out of
    the reply.
    """
    if text is None:
        raise ValueError("empty model response")
    candidate = text.strip()

    fenced = _FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Fall back to the first balanced {...} or [...] span.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = candidate.find(opener)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(candidate)):
            ch = candidate[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(candidate[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError(f"no parseable JSON in model response: {text[:300]!r}")


def call_json(
    node: str,
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int = 4096,
    attempts: int = 2,
) -> Any:
    """One JSON-returning model call, with a single reformat retry.

    Raises RuntimeError if the model is unavailable or never returns valid JSON;
    callers treat that the same way they treat an empty retrieval — the
    requirement becomes unverified, never invented.
    """
    if not llm_available():
        raise RuntimeError("no usable OPENROUTER_API_KEY")

    from langchain_core.messages import HumanMessage, SystemMessage

    choice = MODEL_ASSIGNMENTS.get(node)
    # Handoff section 1's documented contention plan: drop to the smaller model
    # rather than re-queueing on a congested one. For the Verifier this is the
    # explicitly sanctioned fallback, since it runs once per case.
    candidates = [model_for(node)]
    if choice and choice.fallback and choice.fallback != candidates[0]:
        candidates.append(choice.fallback)

    from app.tools import llm_cache

    # Every agent runs at temperature 0, so a repeat prompt is meant to produce
    # the same answer. Serving it from disk removes a 60s+ queue wait without
    # changing behaviour.
    for model in candidates:
        cached = llm_cache.read(node, model, system_prompt, user_prompt)
        if cached is not None:
            return cached

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    last_error: Exception | None = None
    saw_rate_limit = False

    for model in candidates:
        llm = get_llm(node, max_tokens=max_tokens, model=model)
        rate_limit_attempt = 0
        format_attempt = 0

        while True:
            try:
                response = llm.invoke(messages)
                parsed = extract_json(response.content)
                llm_cache.write(node, model, system_prompt, user_prompt, parsed)
                return parsed
            except Exception as exc:  # noqa: BLE001 — classified below
                last_error = exc

                # 1. Rate limited: wait and retry the SAME model. Switching
                #    models on a 429 does not help — the quota is per account.
                if _is_rate_limit(exc):
                    saw_rate_limit = True
                    if rate_limit_attempt < len(RATE_LIMIT_BACKOFF):
                        delay = _retry_after_seconds(exc) or RATE_LIMIT_BACKOFF[rate_limit_attempt]
                        rate_limit_attempt += 1
                        _LOG.warning(
                            "%s: rate limited on %s, retrying in %.0fs (attempt %d/%d)",
                            node, model, delay, rate_limit_attempt, len(RATE_LIMIT_BACKOFF),
                        )
                        time.sleep(delay)
                        continue
                    break  # exhausted backoff; try the fallback model

                # 2. Malformed JSON: the model answered, just badly. Ask again.
                if isinstance(exc, ValueError) and format_attempt + 1 < attempts:
                    format_attempt += 1
                    messages.append(
                        HumanMessage(
                            content=(
                                "Your previous reply was not valid JSON. Reply again "
                                "with ONLY the JSON object, no prose, no code fence."
                            )
                        )
                    )
                    continue

                # 3. Timeout or transport failure: retrying the same congested
                #    model will not help — move to the fallback.
                break

    detail = f"{node}: model call failed on {' then '.join(candidates)}: {last_error}"
    if saw_rate_limit:
        raise RateLimited(
            f"{detail} — rate limited after {len(RATE_LIMIT_BACKOFF)} backoff attempts"
        )
    raise ModelUnavailable(detail)


def model_report() -> list[dict[str, str]]:
    """What each node runs on — surfaced on /health and in the defense deck."""
    return [
        {
            "node": node,
            "model": model_for(node),
            "fallback": choice.fallback or "-",
            "why": choice.why,
        }
        for node, choice in MODEL_ASSIGNMENTS.items()
    ]
