"""CaseState and its parts — the single source of truth (implementation plan §1).

Every LangGraph node reads this and returns a **partial update**, merged via an
explicit reducer, so one agent can never silently erase another's progress.

``frontend/src/types/caseState.ts`` is a hand-maintained mirror of this module.
Fields added here that the frontend does not yet know about are all OPTIONAL,
so the existing frontend contract keeps deserialising unchanged — see
:data:`FRONTEND_MIRRORED_FIELDS`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Confidence = Literal["HIGH", "MEDIUM", "LOW"]
RequirementStatus = Literal["satisfied", "missing", "unverified"]
ApprovalStage = Literal["none", "proposal_approved", "submitted"]
RetrievalPath = Literal["live", "corpus_fallback", "none"]


class Evidence(BaseModel):
    claim: str
    source_entity: str  # e.g. "Balady"
    source_url: str  # must be from the allowlist
    retrieved_at: datetime
    confidence: Confidence
    has_explicit_url: bool  # Verifier sets this; False = claim gets stripped

    #: Which path served this claim — set by code, never by a model. Optional so
    #: the frontend mirror stays valid until Phase C updates it.
    retrieval_path: Optional[RetrievalPath] = None
    #: Populated by the Verifier when a claim is rejected.
    rejection_reason: Optional[str] = None

    @field_validator("source_url")
    @classmethod
    def _url_must_be_allowlisted_or_blank(cls, value: str) -> str:
        """A blank URL is allowed — that is exactly what the Verifier rejects.

        A NON-blank URL, though, must be allowlisted. Constructing an Evidence
        object citing an unlisted domain is a programming error, not something
        to be caught later downstream.
        """
        from app.config.allowlist import is_searchable

        if value and not is_searchable(value):
            raise ValueError(f"source_url {value!r} is not on the allowlist")
        return value


class RequirementItem(BaseModel):
    name: str
    status: RequirementStatus
    evidence: Optional[Evidence] = None
    note: Optional[str] = None
    #: Which retrieval node produced this, for the decision log.
    produced_by: Optional[str] = None


class ConflictResolution(BaseModel):
    accepted: Literal["stated", "document"]
    accepted_value: float | str
    note: Optional[str] = None
    resolved_at: datetime


class Conflict(BaseModel):
    """Structured discrepancy record (implementation plan §2.5 rule 4).

    Shape confirmed against the frontend contract built in Phase A.
    """

    conflict_id: str
    field: str
    field_label: str
    stated_value: float | str
    stated_source: str
    document_value: float | str
    document_source: str
    detected_by: str = "verifier"
    status: Literal["open", "resolved"] = "open"
    resolution: Optional[ConflictResolution] = None


class SupplementaryItem(BaseModel):
    """A non-government, unverified reference from the open-web node.

    Deliberately NOT an Evidence object and deliberately NOT stored in
    ``evidence_log``. It cannot be cited, cannot satisfy a requirement, and
    cannot move ``readiness_pct``. Confidence is fixed at LOW — the field is a
    literal, so a MEDIUM or HIGH value fails validation rather than being
    silently downgraded.
    """

    claim: str
    #: Always shown in the UI — the whole point is that the user can see the
    #: source is not a government domain.
    source_url: str
    source_domain: str
    title: str = ""
    retrieved_at: datetime
    confidence: Literal["LOW"] = "LOW"
    #: Always False. Present so any consumer must acknowledge the distinction.
    is_official: Literal[False] = False


class CaseState(BaseModel):
    case_id: str
    goal: str
    business_type: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    area_sqm_stated: Optional[float] = None
    area_sqm_from_document: Optional[float] = None
    budget_sar: Optional[float] = None
    expected_annual_revenue_sar: Optional[float] = None
    requirements: list[RequirementItem] = Field(default_factory=list)
    evidence_log: list[Evidence] = Field(default_factory=list)
    readiness_pct: int = 0
    vat_registration_required: Optional[bool] = None
    conflicts: list[Conflict] = Field(default_factory=list)
    approval_stage: ApprovalStage = "none"
    decision_log: list[str] = Field(default_factory=list)

    # ---- Intake fields collected by the frontend (§13) that downstream nodes
    # need but §1's original schema did not carry. All optional and additive.
    business_category: Optional[str] = None
    applicant_status: Optional[str] = None
    employee_count: Optional[int] = None
    target_opening_date: Optional[str] = None
    applicant_age: Optional[int] = None
    #: "food_business" | "general_business", set by the Intake & Planner.
    branch: Optional[str] = None
    #: Fields the Intake agent could not extract — listed, never guessed (§2.1).
    missing_fields: list[str] = Field(default_factory=list)

    #: Open-web references from the additional_context node. Separate from
    #: evidence_log by design: nothing here is citable, and nothing here may
    #: affect readiness_pct or a requirement's status.
    supplementary_context: list[SupplementaryItem] = Field(default_factory=list)

    @property
    def has_open_conflict(self) -> bool:
        """Readiness may not increase while this is true (§2.5 rule 4)."""
        return any(c.status == "open" for c in self.conflicts)


#: Fields the Phase A frontend mirror already knows. Anything outside this set
#: is an additive backend-only field until the mirror is updated in Phase C.
FRONTEND_MIRRORED_FIELDS: frozenset[str] = frozenset(
    {
        "case_id",
        "goal",
        "business_type",
        "city",
        "district",
        "area_sqm_stated",
        "area_sqm_from_document",
        "budget_sar",
        "expected_annual_revenue_sar",
        "requirements",
        "evidence_log",
        "readiness_pct",
        "vat_registration_required",
        "conflicts",
        "approval_stage",
        "decision_log",
        # Additive: the frontend renders these in a visually distinct card. Old
        # clients that do not know the field simply ignore it.
        "supplementary_context",
    }
)


def merge_case_state(current: CaseState, update: dict) -> CaseState:
    """Apply a node's partial update.

    List fields are replaced by the node that owns them rather than appended
    blindly, except ``decision_log``, which is append-only — it is a trace, and
    a node overwriting the trace would destroy the audit record.
    """
    data = current.model_dump()
    for key, value in update.items():
        if key not in data:
            raise KeyError(f"unknown CaseState field: {key}")
        if key == "decision_log":
            data[key] = list(data[key]) + list(value)
        else:
            data[key] = value
    return CaseState.model_validate(data)
