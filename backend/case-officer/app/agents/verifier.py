"""Verifier agent (implementation plan section 2.5) — the signature node.

Two jobs:

1. Citation discipline. Every Evidence object upstream produced is audited.
   Rejected claims are removed from the report entirely, not softened.
2. The lease-document discrepancy check. When the stated area and the extracted
   area disagree, a structured conflict is emitted and readiness is frozen until
   a human resolves it — the system never silently picks one.

Deterministic checks run FIRST and are not delegated to the model: a blank URL,
an off-allowlist URL, and a numeric claim whose figure is absent from the source
passage are all decided in code. The model is only asked about claims that
survive those checks, so a model failure can never turn a structurally-invalid
claim into an accepted one.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.agents.prompts import VERIFIER_PROMPT
from app.config.allowlist import cap_confidence, is_citable
from app.llm import RateLimited, call_json, llm_available

CONFLICT_FIELD_LABELS = {"area_sqm": "Premises area (sqm)"}

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


#: Must stay >= hybrid_search.CHUNK_CHARS so a corpus passage is never trimmed —
#: the fallback path should be immune to the windowing problem entirely, not
#: merely less affected by it. A test enforces the relationship.
VERIFIER_WINDOW = 1200


def relevant_excerpt(claim: str, passage: str, width: int = VERIFIER_WINDOW) -> str:
    """The window of a passage most likely to bear on a claim.

    Live passages are whole documents — measured up to 130k characters. Trimming
    from the start hands the Verifier a cover page, and it rejects a
    well-supported claim for want of evidence it was never shown.

    Scoring is phrase-aware rather than bag-of-words. Counting only which terms
    are *present* makes dozens of windows tie in a long regulation (every page
    mentions "eligible", "goods", "supply"), and the first tied window wins by
    accident. Term frequency plus adjacent-pair matches pick the window that
    actually contains the claim's phrasing.
    """
    if not passage:
        return ""
    if len(passage) <= width:
        return passage

    words = [t for t in re.findall(r"\w+", (claim or "").lower()) if len(t) > 3]
    terms = set(words)
    numerals = {t for t in re.findall(r"\d[\d,]*", claim or "") if len(t) >= 3}
    terms |= {n.replace(",", "") for n in numerals}
    # Adjacent word pairs from the claim — "eligible used", "used goods".
    bigrams = {f"{a} {b}" for a, b in zip(words, words[1:])}

    if not terms and not bigrams:
        return passage[:width]

    step = max(width // 6, 1)
    lowered = passage.lower()
    best_start, best_score = 0, -1.0

    for start in range(0, max(len(passage) - width, 0) + step, step):
        window = lowered[start : start + width]
        # Frequency, not mere presence: a window discussing the claim's subject
        # repeatedly beats one that name-drops it once.
        score = float(sum(window.count(term) for term in terms))
        # A matching phrase is far stronger evidence than scattered words.
        score += 5.0 * sum(window.count(bg) for bg in bigrams)
        # An exact figure is the strongest signal of all.
        score += 8.0 * sum(window.count(n.lower()) for n in numerals)
        if score > best_score:
            best_start, best_score = start, score

    return passage[best_start : best_start + width]


def _numbers_in(text: str) -> set[str]:
    """Normalised numerals appearing in a text, for the numeric-claim check."""
    found = set()
    for raw in _NUMBER.findall(text or ""):
        cleaned = raw.replace(",", "").rstrip(".")
        if not cleaned:
            continue
        try:
            value = float(cleaned)
        except ValueError:
            continue
        # Ignore small integers — years, list numbers, step counts.
        if value >= 1000:
            found.add(f"{value:.10g}")
    return found


def deterministic_verdict(evidence: dict, passage_texts: dict[str, str]) -> tuple[bool, str] | None:
    """Reject structurally-invalid claims without consulting a model.

    Returns (accepted, reason) when the outcome is decidable in code, else None.
    """
    url = str(evidence.get("source_url") or "").strip()
    if not url:
        return False, "No source URL. has_explicit_url = false — claim stripped from the report."
    if not is_citable(url):
        return False, f"Source {url} is not an allowlisted citable domain."

    claim = str(evidence.get("claim") or "")
    source_text = passage_texts.get(url, "")
    if source_text:
        claim_numbers = _numbers_in(claim)
        if claim_numbers:
            source_numbers = _numbers_in(source_text)
            missing = claim_numbers - source_numbers
            if missing:
                return (
                    False,
                    f"Claim states {sorted(missing)} but the cited passage does not contain "
                    "that figure. A passage referring to a threshold without stating its "
                    "value cannot support a claim about the value.",
                )
    return None


#: Claims per audit call. The Verifier used to send every claim in one request,
#: which made it the largest prompt in the system and the most rate-limit-prone
#: — and a single 429 then lost every verdict. Smaller batches mean a partial
#: outage costs a few claims instead of the whole audit.
AUDIT_BATCH_SIZE = 4


def _audit_batch(
    batch: list[tuple[int, dict]], passage_texts: dict[str, str]
) -> dict[int, dict]:
    """Ask the model to audit one batch. Raises on an infrastructure failure."""
    listing = "\n\n".join(
        f"[{i}] claim: {item.get('claim')}\n"
        f"    source_url: {item.get('source_url')}\n"
        f"    passage excerpt: "
        + relevant_excerpt(
            str(item.get("claim") or ""),
            passage_texts.get(str(item.get("source_url")), ""),
        )
        for i, item in batch
    )
    result = call_json(
        "verifier",
        VERIFIER_PROMPT,
        f"EVIDENCE TO AUDIT\n=================\n{listing}",
        max_tokens=1200,
    )

    # Models return either {"verdicts": [...]} or a bare [...] — accept both
    # rather than losing every verdict to an AttributeError.
    if isinstance(result, dict):
        raw = result.get("verdicts") or result.get("results") or []
    elif isinstance(result, list):
        raw = result
    else:
        raw = []

    verdicts: dict[int, dict] = {}
    for position, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        try:
            index = int(item["index"]) if "index" in item else batch[position][0]
        except (TypeError, ValueError, IndexError):
            continue
        verdicts[index] = item
    return verdicts


def verify_evidence(
    evidence_log: list[dict], passage_texts: dict[str, str] | None = None
) -> tuple[list[dict], list[dict], list[str]]:
    """Audit every evidence item. Returns (accepted, rejected, decisions).

    When the audit model is unreachable the claims are still withheld — failing
    closed is correct — but the decision log says so explicitly, because
    "verification could not run" and "verification found nothing" produce the
    same numbers and mean opposite things.

    The audit runs in small batches so that a rate limit costs a few claims
    rather than the entire verification.
    """
    passage_texts = passage_texts or {}
    accepted: list[dict] = []
    rejected: list[dict] = []
    decisions: list[str] = []
    undecided: list[tuple[int, dict]] = []

    for index, item in enumerate(evidence_log):
        verdict = deterministic_verdict(item, passage_texts)
        if verdict is None:
            undecided.append((index, item))
            continue
        ok, reason = verdict
        record = {**item, "has_explicit_url": ok}
        if ok:
            accepted.append(record)
        else:
            rejected.append({**record, "rejection_reason": reason})

    verdicts: dict[int, dict] = {}
    unaudited: set[int] = set()
    audit_reason = ""

    if undecided and llm_available():
        batches = [
            undecided[i : i + AUDIT_BATCH_SIZE]
            for i in range(0, len(undecided), AUDIT_BATCH_SIZE)
        ]
        quota_exhausted = False
        for batch in batches:
            if quota_exhausted:
                # The first batch already exhausted its full backoff against a
                # 429. The quota is per account and clearly has not reset, so
                # re-waiting for every remaining batch would stall the run for
                # minutes to reach the same answer. Fail the rest fast.
                unaudited.update(i for i, _ in batch)
                continue
            try:
                verdicts.update(_audit_batch(batch, passage_texts))
            except Exception as exc:  # noqa: BLE001 — recorded, never silent
                unaudited.update(i for i, _ in batch)
                audit_reason = (
                    "rate limited" if isinstance(exc, RateLimited) else exc.__class__.__name__
                )
                if isinstance(exc, RateLimited):
                    quota_exhausted = True

        if unaudited:
            # Loud on purpose. A rate limit that silently reads as "nothing was
            # sourced" is the worst failure this system can have: the report
            # looks like a legitimate finding rather than a broken run.
            decisions.append(
                f"*** VERIFICATION INCOMPLETE — the audit model was unavailable "
                f"({audit_reason}). {len(unaudited)} of {len(undecided)} claim(s) were "
                "NOT audited and are withheld. This is a system failure, NOT a finding "
                "that the claims were unsourced. Re-run before relying on them. ***"
            )

        for index, item in undecided:
            verdict = verdicts.get(index)
            # Withhold rather than accept. Absence of verification is not a
            # finding (§2.5 rule 3) — but the REASON must say whether the
            # Verifier looked and said no, or never got to look.
            ok = bool(verdict and verdict.get("accepted"))
            if index in unaudited:
                reason = (
                    f"NOT AUDITED — the Verifier could not run ({audit_reason}). "
                    "This claim was withheld, not judged unsupported."
                )
            else:
                reason = str(
                    (verdict or {}).get("reason")
                    or "No verdict returned; withheld for want of verification."
                )
            record = {**item, "has_explicit_url": ok}
            if ok:
                accepted.append(record)
            else:
                rejected.append({**record, "rejection_reason": reason})

    elif undecided:
        for _, item in undecided:
            rejected.append(
                {
                    **item,
                    "has_explicit_url": False,
                    "rejection_reason": "No model available to verify; rejected rather than assumed.",
                }
            )
        decisions.append("Verifier: no LLM configured; unverifiable claims rejected.")

    # Re-apply the semi-official ceiling after acceptance.
    for record in accepted:
        record["confidence"] = cap_confidence(record["source_url"], record["confidence"])

    if unaudited:
        decisions.append(
            f"Verifier: {len(accepted)} accepted, {len(rejected)} withheld — but "
            f"{len(unaudited)} claim(s) were never audited. Counts are incomplete."
        )
    else:
        decisions.append(
            f"Verifier: {len(accepted)} evidence objects accepted, {len(rejected)} rejected "
            "for missing or unsupported source URLs. Rejected claims removed from the "
            "report entirely."
        )
    return accepted, rejected, decisions


def detect_area_conflict(state: dict) -> dict | None:
    """Section 2.5 rule 4 — never silently pick one of two disagreeing values."""
    stated = state.get("area_sqm_stated")
    from_doc = state.get("area_sqm_from_document")
    if stated is None or from_doc is None:
        return None
    if float(stated) == float(from_doc):
        return None

    return {
        "conflict_id": "conf_area_001",
        "field": "area_sqm",
        "field_label": CONFLICT_FIELD_LABELS["area_sqm"],
        "stated_value": float(stated),
        "stated_source": "Intake form — value entered by applicant",
        "document_value": float(from_doc),
        "document_source": state.get("document_source")
        or "uploaded document — extracted text layer",
        "detected_by": "verifier",
        "status": "open",
        "resolution": None,
    }


def verifier_node(state: dict, passage_texts: dict[str, str] | None = None) -> dict:
    """Partial CaseState update from the audit + discrepancy check."""
    accepted, rejected, decisions = verify_evidence(
        list(state.get("evidence_log") or []), passage_texts
    )

    accepted_urls = {e["source_url"] for e in accepted}
    requirements: list[dict] = []
    for requirement in state.get("requirements") or []:
        evidence = requirement.get("evidence")
        if evidence and evidence.get("source_url") in accepted_urls:
            requirements.append(requirement)
            continue
        # Strip a rejected citation rather than keep an unsupported assertion.
        requirements.append(
            {
                **requirement,
                "status": "unverified",
                "evidence": None,
                "note": (requirement.get("note") or "")
                + " Citation rejected by the Verifier."
                if evidence
                else requirement.get("note") or "",
            }
        )

    update: dict = {
        "evidence_log": accepted + rejected,
        "requirements": requirements,
    }

    conflict = detect_area_conflict(state)
    existing = list(state.get("conflicts") or [])
    if conflict and not any(c.get("conflict_id") == conflict["conflict_id"] for c in existing):
        update["conflicts"] = existing + [conflict]
        decisions.append(
            f"Verifier: DISCREPANCY — area_sqm_stated ({conflict['stated_value']:g}) does not "
            f"match area_sqm_from_document ({conflict['document_value']:g}). "
            "Readiness frozen pending human resolution."
        )
    else:
        update["conflicts"] = existing

    update["readiness_pct"] = compute_readiness(
        requirements, bool(update["conflicts"]) and any(
            c.get("status") == "open" for c in update["conflicts"]
        )
    )
    update["decision_log"] = decisions
    return update


def compute_readiness(requirements: list[dict], frozen: bool) -> int:
    """Readiness as the share of requirements that are verified.

    Capped while a conflict is open (section 2.5 rule 4): the number may not
    climb on the strength of facts a human has not yet reconciled.
    """
    if not requirements:
        return 0
    scored = 0.0
    for requirement in requirements:
        status = requirement.get("status")
        if status == "satisfied":
            scored += 1.0
        elif status == "missing" and requirement.get("evidence"):
            # Known and sourced, just not yet done — real progress.
            scored += 0.6
    pct = int(round(100 * scored / len(requirements)))
    return min(pct, 68) if frozen else pct
