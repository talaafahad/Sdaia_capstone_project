"""Intake & Planner agent (implementation plan section 2.1).

Converts the free-text goal into structured CaseState fields and selects the
conditional branch. No tools — pure extraction and classification over the
user's own words, which is why it runs on the smallest model.

The structured intake form already supplies most fields directly. This agent
therefore does two things the form cannot: it reads the free-text goal for
anything the user stated but did not enter into a field, and it records what is
still MISSING rather than guessing a default.
"""

from __future__ import annotations

from app.agents.prompts import INTAKE_PLANNER_PROMPT
from app.config.category_map import branch_for
from app.llm import call_json, llm_available

#: Required fields per implementation plan section 13. Absence blocks the
#: Regulation Router rather than being silently defaulted.
REQUIRED_FIELDS = (
    "goal",
    "business_category",
    "city",
    "district",
    "applicant_status",
    "area_sqm_stated",
    "expected_annual_revenue_sar",
)

_EXTRACTABLE = {
    "business_type",
    "city",
    "district",
    "area_sqm_stated",
    "expected_annual_revenue_sar",
    "budget_sar",
    "employee_count",
}


def missing_required(state: dict) -> list[str]:
    return [f for f in REQUIRED_FIELDS if state.get(f) in (None, "", [])]


def intake_planner_node(state: dict) -> dict:
    """Partial CaseState update: normalised fields, branch, missing_fields."""
    category = state.get("business_category")
    branch = branch_for(category)

    update: dict = {
        "business_type": category,
        "branch": branch,
    }
    decisions: list[str] = []

    # The form is authoritative for anything it collected. Only ask the model to
    # read the free-text goal for values the form did not capture.
    gaps = sorted(f for f in _EXTRACTABLE if state.get(f) in (None, ""))
    extracted: dict = {}

    if gaps and state.get("goal") and llm_available():
        try:
            result = call_json(
                "intake_planner",
                INTAKE_PLANNER_PROMPT.format(fields=", ".join(gaps)),
                f"User's goal: {state['goal']}",
                max_tokens=800,
            )
            if isinstance(result, dict):
                for key in gaps:
                    value = result.get(key)
                    if value in (None, "", "null"):
                        continue
                    if key in ("area_sqm_stated", "expected_annual_revenue_sar", "budget_sar"):
                        try:
                            value = float(value)
                        except (TypeError, ValueError):
                            continue
                    elif key == "employee_count":
                        try:
                            value = int(value)
                        except (TypeError, ValueError):
                            continue
                    extracted[key] = value
        except Exception as exc:  # noqa: BLE001 — extraction is best-effort
            decisions.append(
                f"Intake & Planner: free-text extraction unavailable ({exc.__class__.__name__}); "
                "using submitted form fields only."
            )

    update.update(extracted)

    merged = {**state, **update}
    missing = missing_required(merged)
    update["missing_fields"] = missing

    stated = [f"{k}={v}" for k, v in sorted(extracted.items())]
    decisions.insert(
        0,
        "Intake & Planner: extracted "
        + (", ".join(stated) if stated else "no additional fields from free text")
        + f". Branch selected — {branch}."
        + (" No fields inferred." if not stated else ""),
    )
    if missing:
        decisions.append(
            "Intake & Planner: required fields still missing — "
            + ", ".join(missing)
            + ". Listed rather than guessed (section 2.1 rule 4)."
        )

    update["decision_log"] = decisions
    return update
