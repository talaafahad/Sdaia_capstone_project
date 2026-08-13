"""The two Municipal & Location nodes (implementation plan section 2.3).

Both hard rules that make this agent safe are enforced in code, not only in the
prompt:

* the mandatory "NOT VERIFIED" approval line is appended by this module, so it
  is present even if a model omits it;
* the competitor count is passed through from the tool untouched, and the
  "AI ESTIMATE" label is attached here — a model is never asked to produce the
  number or to characterise it.
"""

from __future__ import annotations

import os
from dataclasses import asdict

from app.allowlist import entity_for, is_citable
from app.competitor_lookup import AI_ESTIMATE_LABEL, lookup_nearby_competitors
from app.prompts import MANDATORY_APPROVAL_LINE, build_system_prompt
from app.retrieval import render_context, retrieve
from app.settings import settings

_PLACEHOLDER_MARKERS = ("xxxx", "replace-me", "your-key", "changeme")

MODEL = os.environ.get("MUNICIPAL_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")


def llm_available() -> bool:
    key = (settings.openrouter_api_key or "").strip().lower()
    return bool(key) and not any(m in key for m in _PLACEHOLDER_MARKERS)


#: Mirrors the Case Officer's schedule. Without this the municipal node was the
#: only LLM caller in the system with no 429 handling: it failed fast on a rate
#: limit and reported the municipal licence as unverified, which is
#: indistinguishable from "Balady published nothing" in the output.
RATE_LIMIT_BACKOFF = (5, 20, 65)
LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", "240"))


def _is_rate_limit(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status == 429:
        return True
    response = getattr(exc, "response", None)
    if response is not None and getattr(response, "status_code", None) == 429:
        return True
    text = f"{exc.__class__.__name__} {exc}".lower()
    return "ratelimit" in text.replace("_", "").replace(" ", "") or "429" in text


def _call_json(system: str, user: str, max_tokens: int = 2000):
    import time

    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    from app.json_utils import extract_json

    llm = ChatOpenAI(
        model=MODEL,
        api_key=settings.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0,  # citation-touching node — section 7
        max_tokens=max_tokens,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=0,  # handled below so a 429 can back off rather than hammer
    )
    messages = [SystemMessage(content=system), HumanMessage(content=user)]

    attempt = 0
    while True:
        try:
            return extract_json(llm.invoke(messages).content)
        except Exception as exc:  # noqa: BLE001 — classified, then re-raised
            if _is_rate_limit(exc) and attempt < len(RATE_LIMIT_BACKOFF):
                time.sleep(RATE_LIMIT_BACKOFF[attempt])
                attempt += 1
                continue
            raise


def municipal_requirements(payload: dict) -> dict:
    """Balady municipal requirements for a case. Never asserts approval."""
    category = payload.get("business_category")
    city = payload.get("city") or ""
    district = payload.get("district") or ""

    # Broad on purpose. Baking the district or premises area into the query
    # returns nothing useful: Balady publishes requirements for commercial
    # premises generally and its pages never name a district or a sqm figure.
    # Search the requirements broadly; applicability is decided downstream.
    query = "commercial activity licence requirements conditions documents"
    if category == "food_truck_mobile":
        query = "mobile cart licence issuance requirements eligibility conditions"
    outcome = retrieve(query, category=category, top_k=6, node="municipal_requirements")

    result: dict = {
        "requirements": [],
        "evidence": [],
        "approval_status": MANDATORY_APPROVAL_LINE,
        "decision_log": [f"Municipal & Location (A2A) {outcome.log_line()}"],
        "retrieval_path": outcome.path,
        # Returned so the Case Officer's Verifier can audit each claim against
        # the passage it came from. Without this the Verifier has nothing to
        # check against and rejects every claim.
        "passage_texts": {p.source_url: p.text for p in outcome.passages},
    }

    if not outcome.served or not llm_available():
        reason = (
            "no allowlisted source found"
            if not outcome.served
            else "no model available to read retrieved sources"
        )
        result["requirements"] = [
            {
                "name": "Municipal commercial licence (Balady)",
                "status": "unverified",
                "evidence": None,
                "note": reason,
                "produced_by": "municipal_requirements",
            }
        ]
        return result

    system = build_system_prompt(
        "municipal_requirements",
        business_category=category,
        city=city,
        district=district,
        area_sqm_stated=payload.get("area_sqm_stated"),
    )
    user = (
        "RETRIEVED CONTEXT\n=================\n"
        f"{render_context(outcome.passages, query)}\n\n"
        'Produce JSON: {"requirements": [{"name": str, "status": '
        '"satisfied"|"missing"|"unverified", "note": str, "evidence": {"claim": str, '
        '"source_url": str, "confidence": "HIGH"|"MEDIUM"|"LOW"}}], "approval_status": str}\n'
        "Use only source_url values that appear in the context above.\n"
        "Report every municipal requirement the sources state for commercial "
        "premises. Put any condition that limits when a requirement applies in "
        "its note — do not omit the requirement because you cannot confirm the "
        "condition holds for this case."
    )

    try:
        parsed = _call_json(system, user)
    except Exception as exc:  # noqa: BLE001
        result["requirements"] = [
            {
                "name": "Municipal commercial licence (Balady)",
                "status": "unverified",
                "evidence": None,
                "note": f"model call failed: {exc.__class__.__name__}",
                "produced_by": "municipal_requirements",
            }
        ]
        result["decision_log"].append("Municipal & Location (A2A): model call failed.")
        return result

    retrieved_urls = {p.source_url: p for p in outcome.passages}
    for item in (parsed.get("requirements") or []) if isinstance(parsed, dict) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "Municipal commercial licence (Balady)")
        evidence = None
        raw = item.get("evidence")
        if isinstance(raw, dict):
            url = str(raw.get("source_url") or "").strip()
            claim = str(raw.get("claim") or "").strip()
            # A model may not introduce a URL the node did not retrieve.
            if url in retrieved_urls and is_citable(url) and claim:
                source = retrieved_urls[url]
                confidence = str(raw.get("confidence") or "LOW").upper()
                if confidence not in ("HIGH", "MEDIUM", "LOW"):
                    confidence = "LOW"
                evidence = {
                    "claim": claim,
                    "source_entity": entity_for(url) or source.source_entity,
                    "source_url": url,
                    "retrieved_at": source.retrieved_at,
                    "confidence": confidence,
                    "has_explicit_url": True,
                    "retrieval_path": outcome.path,
                }
                result["evidence"].append(evidence)

        status = str(item.get("status") or "unverified")
        if evidence is None:
            status = "unverified"
        result["requirements"].append(
            {
                "name": name,
                "status": status if status in ("satisfied", "missing", "unverified") else "unverified",
                "evidence": evidence,
                "note": str(item.get("note") or "") or ("no allowlisted source found" if evidence is None else ""),
                "produced_by": "municipal_requirements",
            }
        )

    # Appended by code: the line must be present regardless of what the model did.
    result["approval_status"] = MANDATORY_APPROVAL_LINE
    result["decision_log"].append(
        f"Municipal & Location (A2A): Balady requirements retrieved. {MANDATORY_APPROVAL_LINE}"
    )
    return result


def competitor_context(payload: dict) -> dict:
    """Raw competitor count. No model is asked to produce or judge the number."""
    lookup = lookup_nearby_competitors(
        district=payload.get("district") or "",
        city=payload.get("city") or "",
        business_category=payload.get("business_category") or "food_beverage_fixed",
        radius_m=int(payload.get("radius_m") or 500),
    )
    data = asdict(lookup)

    if lookup.ok:
        decision = (
            f"Municipal & Location (A2A): {AI_ESTIMATE_LABEL} {lookup.count} establishments "
            f"within {lookup.radius_m} m of {lookup.resolved_place or payload.get('district')}."
        )
        evidence = [
            {
                "claim": (
                    f"{lookup.count} similar establishments were found within "
                    f"{lookup.radius_m} m of the stated district centroid. {AI_ESTIMATE_LABEL}"
                ),
                "source_entity": "OpenStreetMap Overpass",
                "source_url": "",  # not an allowlisted government source
                "retrieved_at": "",
                "confidence": "MEDIUM",
                "has_explicit_url": False,
                "retrieval_path": "live",
            }
        ]
    else:
        decision = (
            f"Municipal & Location (A2A): competitor lookup failed ({lookup.reason}); "
            "no count is available. No estimate was substituted."
        )
        evidence = []

    return {"competitors": data, "evidence": evidence, "decision_log": [decision]}
