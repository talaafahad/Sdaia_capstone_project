/**
 * Direct TypeScript mirror of the backend Pydantic models in
 * `backend/case-officer/app/state.py` (implementation plan section 1).
 *
 * Keep this file field-for-field faithful to the Python schema — implementation
 * plan section 5 makes this the reason Phase C integration is a swap rather
 * than a rewrite. Do not add frontend-only fields here; those live in
 * `types/events.ts` and `types/artifacts.ts`.
 */

export type Confidence = 'HIGH' | 'MEDIUM' | 'LOW';

export interface Evidence {
  claim: string;
  /** e.g. "Balady" */
  source_entity: string;
  /** Must be from the allowlist (implementation plan section 0). */
  source_url: string;
  /** ISO-8601 datetime string (Python `datetime` serialises to this). */
  retrieved_at: string;
  confidence: Confidence;
  /** Set by the Verifier; false means the claim is stripped from the report. */
  has_explicit_url: boolean;
}

export type RequirementStatus = 'satisfied' | 'missing' | 'unverified';

export interface RequirementItem {
  name: string;
  status: RequirementStatus;
  evidence?: Evidence | null;
}

export type ApprovalStage = 'none' | 'proposal_approved' | 'submitted';

/**
 * `CaseState.conflicts` is `list[dict]` on the Python side — untyped there, so
 * this shape is the frontend's contract for what the Verifier emits. It is
 * derived from implementation plan section 2.5 ("a structured conflict record
 * with both values and their sources"); confirm the exact keys when
 * `agents/verifier.py` is written in Phase B.
 */
export interface Conflict {
  conflict_id: string;
  /** CaseState field pair in dispute, e.g. "area_sqm". */
  field: string;
  field_label: string;
  stated_value: number | string;
  stated_source: string;
  document_value: number | string;
  document_source: string;
  detected_by: string;
  status: 'open' | 'resolved';
  resolution?: ConflictResolution | null;
}

export interface ConflictResolution {
  /** Which value the human chose to treat as authoritative. */
  accepted: 'stated' | 'document';
  accepted_value: number | string;
  note?: string;
  resolved_at: string;
}

export interface CaseState {
  case_id: string;
  goal: string;
  business_type?: string | null;
  city?: string | null;
  district?: string | null;
  area_sqm_stated?: number | null;
  area_sqm_from_document?: number | null;
  budget_sar?: number | null;
  expected_annual_revenue_sar?: number | null;
  requirements: RequirementItem[];
  evidence_log: Evidence[];
  readiness_pct: number;
  vat_registration_required?: boolean | null;
  conflicts: Conflict[];
  approval_stage: ApprovalStage;
  decision_log: string[];
}
