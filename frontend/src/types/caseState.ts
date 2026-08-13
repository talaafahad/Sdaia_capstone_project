/**
 * Mirror of the backend's Pydantic models in
 * `backend/case-officer/app/state.py`, plus the SSE wire protocol.
 *
 * Written against the API's ACTUAL responses (captured from a live run), not
 * from the previous frontend's types. Two things that differ from what you
 * might assume from reading state.py alone:
 *
 * 1. `state_patch` only carries the fields a node CHANGED. A run emits patches
 *    containing approval_stage, area_sqm_stated, business_type, conflicts,
 *    decision_log, evidence_log, readiness_pct, requirements and
 *    vat_registration_required — never case_id, goal, city, district, budget or
 *    expected revenue, which are set at creation. The client must therefore
 *    seed state from the intake payload and merge patches over it.
 *
 * 2. `retrieved_at` arrives in two formats. Evidence serialised through the
 *    graph comes out as "2026-08-13 00:26:55.927930+00:00" (space separator),
 *    while artifact rows use ISO "2026-08-12T17:28:07+00:00". Parse defensively.
 */

export type Confidence = 'HIGH' | 'MEDIUM' | 'LOW'
export type RequirementStatus = 'satisfied' | 'missing' | 'unverified'
export type ApprovalStage = 'none' | 'proposal_approved' | 'submitted'
export type RetrievalPath = 'live' | 'corpus_fallback' | 'none'

export interface Evidence {
  claim: string
  source_entity: string
  /** Empty string when the Verifier rejected the claim for having no URL. */
  source_url: string
  retrieved_at: string
  confidence: Confidence
  /** false = rejected by the Verifier and excluded from the report. */
  has_explicit_url: boolean
  retrieval_path?: RetrievalPath | null
  rejection_reason?: string | null
}

export interface RequirementItem {
  name: string
  status: RequirementStatus
  evidence?: Evidence | null
  note?: string | null
  produced_by?: string | null
}

export interface ConflictResolution {
  accepted: 'stated' | 'document'
  accepted_value: number | string
  note?: string | null
  resolved_at: string
}

export interface Conflict {
  conflict_id: string
  field: string
  field_label: string
  stated_value: number | string
  stated_source: string
  document_value: number | string
  document_source: string
  detected_by: string
  status: 'open' | 'resolved'
  resolution?: ConflictResolution | null
}

export interface CaseState {
  case_id: string
  goal: string
  business_type?: string | null
  city?: string | null
  district?: string | null
  area_sqm_stated?: number | null
  area_sqm_from_document?: number | null
  budget_sar?: number | null
  expected_annual_revenue_sar?: number | null
  requirements: RequirementItem[]
  evidence_log: Evidence[]
  readiness_pct: number
  vat_registration_required?: boolean | null
  conflicts: Conflict[]
  approval_stage: ApprovalStage
  decision_log: string[]
}

// ─── Artifacts (Documentation agent, §2.6) ────────────────────────────────────

export interface JourneyStepArtifact {
  order: number
  title: string
  agency: string
  description: string
  estimated_duration?: string | null
}

export interface ChecklistEntry {
  name: string
  status: RequirementStatus
  note?: string
}

export interface EvidenceReportRow {
  claim: string
  source_entity: string
  source_url: string
  retrieved_at: string
  confidence: Confidence
  verdict: 'accepted' | 'rejected'
  reason?: string
}

export interface FeeLineItem {
  label: string
  amount_sar: number
  /** false renders the mandatory "AI ESTIMATE — not an official fee." label. */
  is_official: boolean
  source?: string
}

export interface DocumentationArtifacts {
  journey: JourneyStepArtifact[]
  checklist: ChecklistEntry[]
  evidence_report: EvidenceReportRow[]
  fee_estimate: {
    line_items: FeeLineItem[]
    official_total_sar: number
    estimated_total_sar: number
  }
  application_packet: {
    target_service: string
    target_agency: string
    fields: { label: string; value: string; source: string }[]
    disclaimer: string
  }
  decision_log: string[]
  summary?: string
}

// ─── SSE wire protocol ────────────────────────────────────────────────────────

export type BackendAgentId =
  | 'intake_planner'
  | 'regulation_router'
  | 'municipal_location'
  | 'tax_financial'
  | 'verifier'
  | 'documentation'

/** Backend vocabulary — NOT the UI's 'waiting|working|completed|error'. */
export type BackendAgentStatus = 'pending' | 'active' | 'complete' | 'blocked'

export interface ConflictInterrupt {
  kind: 'conflict_resolution'
  conflict: Conflict
}

export interface ApprovalInterrupt {
  kind: 'approval_gate'
  summary: string
  requirement_count: number
  accepted_evidence_count: number
  rejected_evidence_count: number
}

export type CaseInterrupt = ConflictInterrupt | ApprovalInterrupt

export type CaseEvent =
  | {
      type: 'agent_status'
      agent: BackendAgentId
      status: BackendAgentStatus
      message?: string
      at: string
    }
  | { type: 'state_patch'; patch: Partial<CaseState>; at: string }
  | { type: 'decision'; entry: string; at: string }
  | { type: 'interrupt'; interrupt: CaseInterrupt; at: string }
  | { type: 'artifacts_ready'; artifacts: DocumentationArtifacts; at: string }
  | { type: 'done'; at: string }
  | { type: 'error'; message: string; at: string }

// ─── Intake payload the backend expects (snake_case) ──────────────────────────

export interface IntakePayload {
  goal: string
  business_category: string
  city: string
  district: string
  applicant_status: string
  area_sqm_stated: number
  expected_annual_revenue_sar: number
  budget_sar?: number
  employee_count?: number
  target_opening_date?: string
  applicant_age?: number
}

export interface UploadedDocument {
  filename: string
  kind: string
  size_bytes: number
  extracted_area_sqm: number | null
  extraction_note: string
  area_context?: string | null
  has_text_layer: boolean
}
