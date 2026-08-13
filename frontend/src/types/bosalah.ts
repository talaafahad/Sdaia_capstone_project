// ─── Agent types ──────────────────────────────────────────────────────────────

export type AgentStatus = 'waiting' | 'working' | 'completed' | 'error'

export type AgentBadge = 'LLM' | 'A2A' | 'DETERMINISTIC'

export interface AgentCard {
  name: string
  description: string
  badge: AgentBadge
  status: AgentStatus
}

// ─── Intake form types ────────────────────────────────────────────────────────

export type ApplicantStatus = '' | 'saudi' | 'gcc' | 'non_gcc'

export interface FormValues {
  // Required fields
  businessGoal: string
  businessCategory: string
  city: string
  district: string
  /** Use ApplicantStatus values; typed as string so generic onChange(field, string) works */
  applicantStatus: string
  areaSqm: string
  annualRevenueSAR: string

  // Optional fields
  budgetSAR: string
  numberOfEmployees: string
  targetOpeningDate: string
  applicantAge: string
}

// ─── Modal types ──────────────────────────────────────────────────────────────

export type CaseSummary = string | Record<string, unknown>

export interface ConflictData {
  label: string
  valueA: string | number
  sourceA: string
  valueB: string | number
  sourceB: string
}

// ─── Audit log ────────────────────────────────────────────────────────────────
// These were imported by the components but never defined, so the app did not
// typecheck as shipped. Field sets are taken from how each component uses them.

export type AuditSeverity = 'info' | 'success' | 'warning' | 'error'

export interface AuditEntry {
  id: string
  /** ISO-8601 string. AuditLog formats it — do NOT pass a pre-formatted time. */
  timestamp: string
  message: string
  detail?: string
  severity: AuditSeverity
}

// ─── Action gate ──────────────────────────────────────────────────────────────

export type ActionGateType =
  | 'submit_application'
  | 'make_payment'
  | 'send_document'
  | 'custom'

export interface ActionGateItem {
  id: string
  type: ActionGateType
  title: string
  /**
   * Key/value pairs rendered as the "What will be submitted" table. MUST be an
   * object: the modal calls Object.entries() on it, so passing a string walks
   * it character by character and renders one numbered row per letter.
   */
  summary: Record<string, string | number>
  description: string
  /** Risks the user must tick before the action can proceed. */
  consequences: string[]
  estimatedCostSAR?: number
}


