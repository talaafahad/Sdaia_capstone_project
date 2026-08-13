/**
 * Reconciles the new UI's vocabulary with the backend's actual contract.
 *
 * Every mismatch found when comparing types/bosalah.ts against the live API:
 *
 * | UI                                   | Backend                                  |
 * |--------------------------------------|------------------------------------------|
 * | applicantStatus 'saudi'              | 'saudi_national'                         |
 * | applicantStatus 'gcc'                | 'gcc_national'                           |
 * | applicantStatus 'non_gcc'            | 'non_gcc_resident'                       |
 * | businessCategory 'Food & Beverage'   | 'food_beverage_fixed'                    |
 * | AgentStatus waiting/working/completed| pending/active/complete (+ blocked)      |
 * | FormValues camelCase                 | IntakePayload snake_case                 |
 *
 * The UI's category list has 11 entries; the backend's category map has 5.
 * Unmapped categories fall back to 'professional_office' rather than being sent
 * through as free text, because the backend uses the category to choose which
 * topic nodes run — an unknown value silently widens the search to every
 * allowlisted domain.
 */

import type {
  AgentStatus,
  AuditEntry,
  AuditSeverity,
  ConflictData,
  EvidenceItem,
  EvidenceType,
  FormValues,
  JourneyStep,
  JourneyStepStatus,
} from '../types/bosalah'
import type {
  BackendAgentStatus,
  Conflict,
  Evidence,
  IntakePayload,
  JourneyStepArtifact,
  RequirementStatus,
} from '../types/caseState'

// ─── Enums ────────────────────────────────────────────────────────────────────

const APPLICANT_STATUS: Record<string, string> = {
  saudi: 'saudi_national',
  gcc: 'gcc_national',
  non_gcc: 'non_gcc_resident',
}

const BUSINESS_CATEGORY: Record<string, string> = {
  'Food & Beverage': 'food_beverage_fixed',
  'Tourism & Hospitality': 'food_beverage_fixed',
  Retail: 'professional_office',
  'Professional Services': 'professional_office',
  'Technology & IT': 'professional_office',
  'Education & Training': 'professional_office',
  'Health & Wellness': 'personal_care_spa',
  'Construction & Real Estate': 'professional_office',
  'Transportation & Logistics': 'professional_office',
  Manufacturing: 'professional_office',
  Other: 'professional_office',
}

export function toBackendApplicantStatus(ui: string): string {
  return APPLICANT_STATUS[ui] ?? ui
}

export function toBackendCategory(ui: string): string {
  return BUSINESS_CATEGORY[ui] ?? 'professional_office'
}

/** Backend statuses -> the four the AgentRoster renders. */
export function toUiAgentStatus(status: BackendAgentStatus): AgentStatus {
  switch (status) {
    case 'active':
      return 'working'
    case 'complete':
      return 'completed'
    case 'blocked':
      return 'error'
    default:
      return 'waiting'
  }
}

// ─── Intake ───────────────────────────────────────────────────────────────────

const num = (v: string): number | undefined => {
  if (v === undefined || v === null || String(v).trim() === '') return undefined
  const n = Number(String(v).replace(/,/g, ''))
  return Number.isFinite(n) ? n : undefined
}

export function toIntakePayload(values: FormValues): IntakePayload {
  return {
    goal: values.businessGoal.trim(),
    business_category: toBackendCategory(values.businessCategory),
    city: values.city,
    district: values.district.trim(),
    applicant_status: toBackendApplicantStatus(values.applicantStatus),
    area_sqm_stated: num(values.areaSqm) ?? 0,
    expected_annual_revenue_sar: num(values.annualRevenueSAR) ?? 0,
    budget_sar: num(values.budgetSAR),
    employee_count: num(values.numberOfEmployees),
    target_opening_date: values.targetOpeningDate || undefined,
    applicant_age: num(values.applicantAge),
  }
}

// ─── Timestamps ───────────────────────────────────────────────────────────────

/**
 * The API emits two formats: "2026-08-13 00:26:55.927930+00:00" from evidence
 * serialised through the graph, and ISO "2026-08-12T17:28:07+00:00" from
 * artifact rows. Normalise before Date parsing, which rejects the first on
 * Safari.
 */
export function parseTimestamp(raw: string): Date | null {
  if (!raw) return null
  const normalised = raw.includes('T') ? raw : raw.replace(' ', 'T')
  const date = new Date(normalised)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatClock(raw: string): string {
  const date = parseTimestamp(raw)
  return date ? date.toLocaleTimeString(undefined, { hour12: false }) : '--:--:--'
}

// ─── Evidence -> EvidencePanel ────────────────────────────────────────────────

const ENTITY_TYPE: Record<string, EvidenceType> = {
  Balady: 'municipal',
  'Ministry of Municipalities and Housing': 'municipal',
  ZATCA: 'financial',
  'Saudi Business Center': 'regulation',
  'Ministry of Commerce': 'regulation',
  SFDA: 'regulation',
  GOSI: 'regulation',
  Qiwa: 'regulation',
  HRSD: 'regulation',
  SAIP: 'regulation',
  'OpenStreetMap Overpass': 'web',
}

function evidenceType(entity: string, path?: string | null): EvidenceType {
  if (ENTITY_TYPE[entity]) return ENTITY_TYPE[entity]
  return path === 'corpus_fallback' ? 'document' : 'web'
}

/** EvidencePanel draws five dots from a 0..1 score and filters on `>= 0.8`. */
const CONFIDENCE_SCORE: Record<string, number> = { HIGH: 0.95, MEDIUM: 0.65, LOW: 0.35 }

export function toEvidenceItems(evidence: Evidence[]): EvidenceItem[] {
  return evidence.map((e, i) => ({
    id: `${e.source_url || 'no-url'}-${i}`,
    type: evidenceType(e.source_entity, e.retrieval_path),
    claim: e.claim,
    source: e.source_entity,
    reference: e.source_url,
    // Surfacing WHY a claim was rejected is the point of the Verifier; without
    // it a rejected row looks identical to one that was simply never checked.
    excerpt: e.has_explicit_url
      ? `Retrieved via ${e.retrieval_path === 'corpus_fallback' ? 'pre-verified corpus' : 'live search'}.`
      : `REJECTED — ${e.rejection_reason ?? 'no explicit source URL'}`,
    // A rejected claim scores 0 so it can never be counted as high-confidence.
    confidence: e.has_explicit_url ? (CONFIDENCE_SCORE[e.confidence] ?? 0.35) : 0,
    agentName: 'Verifier',
    timestamp: e.retrieved_at,
  }))
}

// ─── Requirements / journey -> JourneyTimeline ────────────────────────────────

const STATUS_TO_STEP: Record<RequirementStatus, JourneyStepStatus> = {
  satisfied: 'done',
  missing: 'active',
  unverified: 'blocked',
}

export function toJourneySteps(
  journey: JourneyStepArtifact[],
  statusByName: Record<string, RequirementStatus>,
): JourneyStep[] {
  return journey.map(step => ({
    id: String(step.order),
    label: step.title,
    description: step.description,
    status: STATUS_TO_STEP[statusByName[step.title] ?? 'unverified'] ?? 'upcoming',
    agentName: step.agency,
  }))
}

// ─── Decision log -> AuditLog ─────────────────────────────────────────────────

function severityOf(entry: string): AuditSeverity {
  const lower = entry.toLowerCase()
  if (entry.includes('***') || lower.includes('incomplete') || lower.includes('failed'))
    return 'error'
  if (
    lower.includes('discrepancy') ||
    lower.includes('unverified') ||
    lower.includes('not verified') ||
    lower.includes('no allowlisted source') ||
    lower.includes('rejected')
  )
    return 'warning'
  if (lower.includes('accepted') || lower.includes('complete') || lower.includes('approved'))
    return 'success'
  return 'info'
}

export function toAuditEntries(trace: { text: string; at: string }[]): AuditEntry[] {
  return trace.map((item, i) => {
    const [head, ...rest] = item.text.split(/(?<=:)\s/)
    return {
      id: `${i}`,
      // Raw ISO, NOT a pre-formatted clock. AuditLog calls new Date() on this;
      // passing an already-formatted "10:57:45" produced Invalid Date on every
      // entry. The backend stamps `at` on every event, so this is always valid.
      timestamp: item.at,
      message: rest.length ? head.trim() : item.text.slice(0, 90),
      detail: rest.length ? rest.join(' ').trim() : item.text,
      severity: severityOf(item.text),
    }
  })
}

// ─── Conflict -> ConflictModal ────────────────────────────────────────────────

export function toConflictData(conflict: Conflict): ConflictData {
  return {
    label: conflict.field_label,
    valueA: conflict.stated_value,
    sourceA: conflict.stated_source,
    valueB: conflict.document_value,
    sourceB: conflict.document_source,
  }
}

/**
 * The modal hands back the chosen VALUE, but the backend's resume endpoint
 * wants which SIDE was chosen. Compare against the conflict to recover it.
 */
export function resolveSide(
  conflict: Conflict,
  chosen: string | number,
): 'stated' | 'document' {
  const digits = (v: string | number) => String(v).replace(/[^0-9.]/g, '')
  return digits(chosen) === digits(conflict.document_value) ? 'document' : 'stated'
}
