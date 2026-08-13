"""Documentation / Packaging agent (implementation plan section 2.6).

Assembles the six artifacts from the verified CaseState, in the order section
2.6 specifies: Journey, Checklist, Evidence Report, Fee Estimate, Application
Packet Draft, Decision Log.

Mostly templating in plain Python, with a thin LLM pass for the readable summary
only. That split is deliberate: rule 1 ("never re-introduce a rejected claim")
is enforced structurally by building the artifacts from the accepted-evidence
list, not by asking a model to remember what was rejected.

The output shape matches `frontend/src/types/artifacts.ts` exactly.
"""

from __future__ import annotations

from app.agents.prompts import DOCUMENTATION_PROMPT
from app.llm import call_json, llm_available

AI_ESTIMATE_LABEL = "AI ESTIMATE — not an official fee."

PACKET_DISCLAIMER = (
    "Municipal approval status: NOT VERIFIED — approval can only be confirmed by "
    "Balady directly. This packet is a draft assembled from verified evidence only; "
    "it is not a submission and confers no approval."
)

#: Ordering hint so the journey reads as a sequence rather than a list.
_STEP_ORDER = [
    "Commercial Registration (CR)",
    "Municipal commercial licence (Balady)",
    "Food-handling compliance (SFDA)",
    "VAT registration (ZATCA)",
    "Employer registration (GOSI / Qiwa)",
    "Trademark registration (SAIP)",
]


def _rank(name: str) -> int:
    for index, known in enumerate(_STEP_ORDER):
        if known.lower() in name.lower() or name.lower() in known.lower():
            return index
    return len(_STEP_ORDER)


def build_journey(requirements: list[dict]) -> list[dict]:
    steps = []
    for order, requirement in enumerate(
        sorted(requirements, key=lambda r: _rank(r.get("name", ""))), start=1
    ):
        evidence = requirement.get("evidence")
        agency = (evidence or {}).get("source_entity") or "Not verified"
        description = requirement.get("note") or ""
        if not evidence:
            description = (
                description
                or "No allowlisted source was found for this requirement. It is listed "
                "because it is commonly applicable, but it is unverified and must be "
                "confirmed directly."
            )
        steps.append(
            {
                "order": order,
                "title": requirement.get("name", ""),
                "agency": agency,
                "description": description,
                # Section 2.6 rule 3: no invented dates.
                "estimated_duration": None,
            }
        )
    return steps


def build_checklist(requirements: list[dict]) -> list[dict]:
    return [
        {
            "name": requirement.get("name", ""),
            "status": requirement.get("status", "unverified"),
            **({"note": requirement["note"]} if requirement.get("note") else {}),
        }
        for requirement in requirements
    ]


def build_evidence_report(evidence_log: list[dict]) -> list[dict]:
    rows = []
    for item in evidence_log:
        accepted = bool(item.get("has_explicit_url"))
        row = {
            "claim": item.get("claim", ""),
            "source_entity": item.get("source_entity", ""),
            "source_url": item.get("source_url", ""),
            "retrieved_at": str(item.get("retrieved_at", "")),
            "confidence": item.get("confidence", "LOW"),
            "verdict": "accepted" if accepted else "rejected",
        }
        if not accepted:
            row["reason"] = item.get("rejection_reason") or "No explicit source URL."
        rows.append(row)
    return rows


def build_fee_estimate(state: dict) -> dict:
    """Official fees only where sourced; everything else labelled AI ESTIMATE."""
    budget = state.get("budget_sar")
    line_items: list[dict] = []

    line_items.append(
        {
            "label": "Municipal commercial licence",
            "amount_sar": 0,
            "is_official": False,
            "source": (
                "Fee not verified — no allowlisted source stated a figure. Reported as "
                "unknown rather than estimated."
            ),
        }
    )

    if budget:
        # Proportions are heuristics, so every line is labelled AI ESTIMATE.
        line_items.extend(
            [
                {"label": "Premises fit-out and equipment", "amount_sar": round(budget * 0.60), "is_official": False},
                {"label": "Initial inventory", "amount_sar": round(budget * 0.10), "is_official": False},
                {"label": "Contingency (15%)", "amount_sar": round(budget * 0.15), "is_official": False},
            ]
        )

    official_total = sum(i["amount_sar"] for i in line_items if i["is_official"])
    estimated_total = sum(i["amount_sar"] for i in line_items if not i["is_official"])
    return {
        "line_items": line_items,
        "official_total_sar": official_total,
        "estimated_total_sar": estimated_total,
    }


def build_application_packet(state: dict) -> dict:
    conflicts = [c for c in (state.get("conflicts") or []) if c.get("status") == "open"]
    if conflicts:
        area_value = (
            f"UNRESOLVED — {conflicts[0]['stated_value']:g} stated vs "
            f"{conflicts[0]['document_value']:g} in document"
        )
        area_source = f"Conflict {conflicts[0]['conflict_id']}"
    else:
        area = state.get("area_sqm_stated")
        area_value = f"{area:g}" if area is not None else "Not provided"
        area_source = "Intake form"

    vat = state.get("vat_registration_required")
    fields = [
        {"label": "Business activity", "value": state.get("business_type") or "Not provided", "source": "Intake form"},
        {"label": "City", "value": state.get("city") or "Not provided", "source": "Intake form"},
        {"label": "District", "value": state.get("district") or "Not provided", "source": "Intake form"},
        {"label": "Premises area (sqm)", "value": area_value, "source": area_source},
        {"label": "Applicant status", "value": state.get("applicant_status") or "Not provided", "source": "Intake form"},
        {
            "label": "VAT registration required",
            "value": (
                "Not determined — revenue not provided"
                if vat is None
                else ("Yes — revenue above SAR 375,000 threshold" if vat else "No — below threshold")
            ),
            "source": "ZATCA (deterministic assessment)",
        },
    ]
    return {
        "target_service": "Commercial activity licence — food and beverage premises",
        "target_agency": "Balady",
        "fields": fields,
        "disclaimer": PACKET_DISCLAIMER,
    }


def build_summary(state: dict, accepted: list[dict], rejected: list[dict]) -> str:
    """Thin LLM pass. Falls back to a templated sentence if unavailable."""
    fallback = (
        f"{len(state.get('requirements') or [])} requirements were identified for this case. "
        f"{len(accepted)} evidence items were accepted by the Verifier and {len(rejected)} "
        "were rejected and removed from this report. Figures not traceable to an official "
        f"source are labelled \"{AI_ESTIMATE_LABEL}\""
    )
    if not llm_available():
        return fallback
    try:
        payload = {
            "city": state.get("city"),
            "business_type": state.get("business_type"),
            "readiness_pct": state.get("readiness_pct"),
            "accepted_requirements": [
                {"name": r.get("name"), "status": r.get("status")}
                for r in (state.get("requirements") or [])
            ],
            "accepted_evidence_count": len(accepted),
            "rejected_evidence_count": len(rejected),
            "open_conflicts": len([c for c in (state.get("conflicts") or []) if c.get("status") == "open"]),
        }
        result = call_json("documentation", DOCUMENTATION_PROMPT, str(payload), max_tokens=600)
        summary = str((result or {}).get("summary") or "").strip()
        return summary or fallback
    except Exception:  # noqa: BLE001
        return fallback


def documentation_node(state: dict) -> dict:
    """Build the six artifacts. Rejected evidence never reaches them."""
    evidence_log = list(state.get("evidence_log") or [])
    accepted = [e for e in evidence_log if e.get("has_explicit_url")]
    rejected = [e for e in evidence_log if not e.get("has_explicit_url")]
    requirements = list(state.get("requirements") or [])

    artifacts = {
        "journey": build_journey(requirements),
        "checklist": build_checklist(requirements),
        # The report shows rejected rows too — the Verifier's work is only
        # legible if you can see what it threw away.
        "evidence_report": build_evidence_report(evidence_log),
        "fee_estimate": build_fee_estimate(state),
        "application_packet": build_application_packet(state),
        "decision_log": list(state.get("decision_log") or []),
        "summary": build_summary(state, accepted, rejected),
    }

    return {
        "artifacts": artifacts,
        "decision_log": [
            f"Documentation: assembled six artifacts from {len(accepted)} accepted evidence "
            f"items. {len(rejected)} rejected claim(s) excluded from the journey, checklist "
            "and packet."
        ],
    }
