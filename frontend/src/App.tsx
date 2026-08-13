import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import Navbar from './components/Navbar'
import Footer from './components/Footer'
import HeroSection from './components/HeroSection'
import HowItWorks from './components/HowItWorks'
import IntakeForm from './components/IntakeForm'
import AgentRoster from './components/AgentRoster'
import ApprovalModal from './components/ApprovalModal'
import ConflictModal from './components/ConflictModal'
import ActionGateModal from './components/ActionGateModal'
import AuditLog from './components/AuditLog'
import EvidencePanel from './components/EvidencePanel'
import JourneyTimeline from './components/JourneyTimeline'

import type { ActionGateItem, AgentCard, FormValues } from './types/bosalah'
import type {
  BackendAgentId,
  BackendAgentStatus,
  CaseEvent,
  CaseState,
  Conflict,
  DocumentationArtifacts,
  RequirementStatus,
  UploadedDocument,
} from './types/caseState'
import {
  apiBaseUrl,
  createCase,
  extractDocument,
  openCaseStream,
  resumeCase,
  type StreamHandle,
} from './api/caseStream'
import {
  formatClock,
  resolveSide,
  toAuditEntries,
  toConflictData,
  toEvidenceItems,
  toIntakePayload,
  toJourneySteps,
  toUiAgentStatus,
} from './lib/adapters'

// ─── Agent roster: names and blurbs are UI copy, status comes from the API ────

const AGENT_META: { id: BackendAgentId; name: string; description: string; badge: AgentCard['badge'] }[] = [
  { id: 'intake_planner', name: 'Intake & Planner', badge: 'LLM',
    description: 'Parses your goal, extracts structured requirements, and selects the branch.' },
  { id: 'regulation_router', name: 'Regulation & Service Router', badge: 'LLM',
    description: 'Retrieves requirements from allowlisted government domains only.' },
  { id: 'municipal_location', name: 'Municipal & Location', badge: 'A2A',
    description: 'Separate A2A service: Balady requirements and nearby competitor context.' },
  { id: 'tax_financial', name: 'Tax / Financial', badge: 'DETERMINISTIC',
    description: 'VAT threshold comparison in plain Python — no model in the decision path.' },
  { id: 'verifier', name: 'Verifier', badge: 'LLM',
    description: 'Audits every claim against its source. Rejected claims are removed entirely.' },
  { id: 'documentation', name: 'Documentation', badge: 'LLM',
    description: 'Assembles the journey, checklist, evidence report, fees and packet.' },
]

const EMPTY_FORM: FormValues = {
  businessGoal: '', businessCategory: '', city: '', district: '', applicantStatus: '',
  areaSqm: '', annualRevenueSAR: '', budgetSAR: '', numberOfEmployees: '',
  targetOpeningDate: '', applicantAge: '',
}

type Phase = 'intake' | 'running' | 'awaiting_conflict' | 'awaiting_approval' | 'complete' | 'failed'

const emptyCase = (): CaseState => ({
  case_id: '', goal: '', requirements: [], evidence_log: [], readiness_pct: 0,
  conflicts: [], approval_stage: 'none', decision_log: [],
})

/**
 * Demo-only. The submission secret belongs server-side; a real deployment would
 * gate /submit by session and never expose the token to a browser bundle.
 */
const MCP_TOKEN: string =
  (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_MCP_AUTH_TOKEN ?? ''

export default function App() {
  const [formValues, setFormValues] = useState<FormValues>(EMPTY_FORM)
  const [phase, setPhase] = useState<Phase>('intake')
  const [caseState, setCaseState] = useState<CaseState>(emptyCase())
  const [trace, setTrace] = useState<{ text: string; at: string }[]>([])
  const [agents, setAgents] = useState<Record<string, { status: BackendAgentStatus; message?: string }>>({})
  const [artifacts, setArtifacts] = useState<DocumentationArtifacts | null>(null)
  const [activeConflict, setActiveConflict] = useState<Conflict | null>(null)
  const [approval, setApproval] = useState<Record<string, unknown> | null>(null)
  const [uploadedDoc, setUploadedDoc] = useState<UploadedDocument | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [showGate, setShowGate] = useState(false)
  const [receipt, setReceipt] = useState<string | null>(null)

  const streamRef = useRef<StreamHandle | null>(null)
  const startedAt = useRef<number>(0)

  useEffect(() => () => streamRef.current?.close(), [])

  // Elapsed-time ticker. A cold case takes minutes on the free model tier, so
  // the UI has to show progress is being made rather than looking frozen.
  const isWorking = phase === 'running' || phase === 'awaiting_conflict' || phase === 'awaiting_approval'
  useEffect(() => {
    if (!isWorking) return
    const id = window.setInterval(() => setElapsed(Math.round((Date.now() - startedAt.current) / 1000)), 1000)
    return () => window.clearInterval(id)
  }, [isWorking])

  const applyEvent = useCallback((ev: CaseEvent) => {
    switch (ev.type) {
      case 'agent_status':
        setAgents(prev => ({ ...prev, [ev.agent]: { status: ev.status, message: ev.message } }))
        break
      case 'state_patch':
        // Patches carry only what changed — merge, never replace.
        setCaseState(prev => ({ ...prev, ...ev.patch }))
        break
      case 'decision':
        setTrace(prev => [...prev, { text: ev.entry, at: ev.at }])
        break
      case 'interrupt':
        if (ev.interrupt.kind === 'conflict_resolution') {
          setActiveConflict(ev.interrupt.conflict)
          setPhase('awaiting_conflict')
        } else {
          const { kind, ...rest } = ev.interrupt
          void kind
          setApproval(rest as Record<string, unknown>)
          setPhase('awaiting_approval')
        }
        break
      case 'artifacts_ready':
        setArtifacts(ev.artifacts)
        break
      case 'done':
        setPhase('complete')
        break
      case 'error':
        setError(ev.message)
        setPhase('failed')
        break
    }
  }, [])

  async function handleSubmit(values: FormValues) {
    setError(null)
    setBusy(true)
    try {
      const { case_id } = await createCase(toIntakePayload(values), uploadedDoc)
      setCaseState({ ...emptyCase(), case_id, goal: values.businessGoal })
      setTrace([])
      setAgents({})
      setArtifacts(null)
      setReceipt(null)
      startedAt.current = Date.now()
      setElapsed(0)
      setPhase('running')

      streamRef.current?.close()
      streamRef.current = openCaseStream(case_id, {
        onEvent: applyEvent,
        onError: message => { setError(message); setPhase('failed') },
      })
      window.setTimeout(
        () => document.getElementById('execution')?.scrollIntoView({ behavior: 'smooth' }),
        150,
      )
    } catch (e) {
      setError(
        `Could not reach the backend at ${apiBaseUrl}. Start it with: ` +
        `cd backend/case-officer && uv run uvicorn app.main:app --port 8000  (${String(e)})`,
      )
      setPhase('failed')
    } finally {
      setBusy(false)
    }
  }

  async function handleFileChange(file: File | null) {
    if (!file) { setUploadedDoc(null); return }
    setError(null)
    try {
      // Real PyMuPDF extraction on the backend — this is what feeds
      // area_sqm_from_document and makes the discrepancy check fire.
      setUploadedDoc(await extractDocument(file))
    } catch (e) {
      setError(`Could not read that document: ${String(e)}`)
    }
  }

  async function resume(payload: Parameters<typeof resumeCase>[1]) {
    setBusy(true)
    try {
      await resumeCase(caseState.case_id, payload)
      setActiveConflict(null)
      setApproval(null)
      setPhase('running')
    } catch (e) {
      setError(`Could not resume the case: ${String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  async function submitToBalady() {
    setShowGate(false)
    setBusy(true)
    try {
      const res = await fetch(`${apiBaseUrl}/api/cases/${caseState.case_id}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auth_token: MCP_TOKEN }),
      })
      const body = await res.json()
      setReceipt(
        res.ok
          ? `${body.reference} — ${body.notice}`
          : `Submission refused (HTTP ${res.status}): ${body.detail}`,
      )
    } catch (e) {
      setReceipt(`Submission failed: ${String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  // ─── Derived view models ────────────────────────────────────────────────────

  const agentCards: AgentCard[] = useMemo(
    () => AGENT_META.map(meta => ({
      name: meta.name,
      description: agents[meta.id]?.message ?? meta.description,
      badge: meta.badge,
      status: toUiAgentStatus(agents[meta.id]?.status ?? 'pending'),
    })),
    [agents],
  )

  const statusByName = useMemo(() => {
    const map: Record<string, RequirementStatus> = {}
    for (const r of caseState.requirements) map[r.name] = r.status
    return map
  }, [caseState.requirements])

  const journeySteps = useMemo(
    () => (artifacts ? toJourneySteps(artifacts.journey, statusByName) : []),
    [artifacts, statusByName],
  )
  const evidenceItems = useMemo(() => toEvidenceItems(caseState.evidence_log), [caseState.evidence_log])
  const auditEntries = useMemo(() => toAuditEntries(trace), [trace])

  const gateAction: ActionGateItem | null = useMemo(() => {
    if (!artifacts) return null
    return {
      id: caseState.case_id,
      type: 'submit_application',
      title: 'Submit the application packet to Balady',
      summary: artifacts.application_packet.target_service,
      description: artifacts.application_packet.disclaimer,
      consequences: [
        'This is a MOCK submission — no application is filed with any government agency.',
        'The reference number returned is synthetic and confers no status or approval.',
        'The request is rejected unless it carries a valid MCP auth token.',
      ],
    }
  }, [artifacts, caseState.case_id])

  const agentProgress = useMemo(() => {
    const done = AGENT_META.filter(m => agents[m.id]?.status === 'complete').length
    return Math.round((done / AGENT_META.length) * 100)
  }, [agents])

  const mm = String(Math.floor(elapsed / 60)).padStart(2, '0')
  const ss = String(elapsed % 60).padStart(2, '0')

  return (
    <div className="min-h-screen text-text-primary" style={{ background: '#10122B' }}>
      <Navbar />

      <div className="pt-14">
        <HeroSection
          tagline="Your compass through Saudi government procedures."
          onSuggestedCaseClick={(text: string) => {
            setFormValues(prev => ({ ...prev, businessGoal: text }))
            document.getElementById('intake')?.scrollIntoView({ behavior: 'smooth' })
          }}
          onStartClick={() => document.getElementById('intake')?.scrollIntoView({ behavior: 'smooth' })}
        />
      </div>

      <HowItWorks />

      <div className="max-w-7xl mx-auto px-6">
        <div className="saudi-bar rounded-full" style={{ height: 1, opacity: 0.25 }} />
      </div>

      <section className="py-8 px-6">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-10 items-start">
          <div className="lg:col-span-2 flex flex-col gap-4">
            <IntakeForm
              values={formValues}
              onChange={(field, value) => setFormValues(prev => ({ ...prev, [field]: value }))}
              onSubmit={handleSubmit}
              onFileChange={handleFileChange}
            />

            {uploadedDoc && (
              <div className="rounded-xl px-4 py-3 text-xs"
                   style={{ background: 'rgba(91,205,132,0.06)', border: '1px solid rgba(91,205,132,0.25)', color: '#93DEAE' }}>
                <strong>{uploadedDoc.filename}</strong> parsed on the backend.
                {uploadedDoc.extracted_area_sqm !== null ? (
                  <> Extracted area: <strong>{uploadedDoc.extracted_area_sqm} sqm</strong>. If this
                  differs from what you typed, the Verifier will stop and ask you which is right.</>
                ) : (
                  <> {uploadedDoc.extraction_note}</>
                )}
              </div>
            )}

            {error && (
              <div className="rounded-xl px-4 py-3 text-xs" role="alert"
                   style={{ background: 'rgba(192,86,75,0.08)', border: '1px solid rgba(192,86,75,0.35)', color: '#E39A92' }}>
                {error}
              </div>
            )}

            {receipt && (
              <div className="rounded-xl px-4 py-3 text-xs"
                   style={{ background: 'rgba(217,164,65,0.08)', border: '1px solid rgba(217,164,65,0.3)', color: '#E8C57A' }}>
                {receipt}
              </div>
            )}

            {auditEntries.length > 0 && (
              <AuditLog agentName="Case Officer" entries={auditEntries} />
            )}
          </div>

          <div className="lg:sticky lg:top-20 flex flex-col gap-4">
            {/* Long-wait expectation setting lives beside the roster, not below
                the form: during a run this is where the user is looking, and
                the free model tier queues ~60-70s per node so a first run
                genuinely takes minutes. */}
            {isWorking && (
              <div className="rounded-xl px-4 py-3"
                   style={{ background: 'rgba(157,124,255,0.07)', border: '1px solid rgba(157,124,255,0.28)' }}>
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <span className="text-xs font-semibold" style={{ color: '#BEA9FF' }}>
                    {phase === 'awaiting_conflict' ? 'Paused — waiting for your decision'
                      : phase === 'awaiting_approval' ? 'Paused — waiting for your approval'
                      : 'Agents are working…'}
                  </span>
                  <span className="text-xs tabular-nums font-semibold" style={{ color: '#9D7CFF' }}>
                    {mm}:{ss} elapsed
                  </span>
                </div>
                <p className="text-xs mt-1.5 leading-relaxed" style={{ color: '#B0B0B0' }}>
                  A first run takes <strong>up to about 7 minutes</strong> — each agent calls a
                  free-tier model that queues for roughly a minute. A repeat of the same case is
                  served from cache in about 80 seconds. This is normal; the connection is kept
                  alive throughout.
                </p>
                {caseState.readiness_pct > 0 && (
                  <p className="text-xs mt-2 font-semibold" style={{ color: '#93DEAE' }}>
                    Case readiness: {caseState.readiness_pct}%
                    {caseState.conflicts.some(c => c.status === 'open') && ' — frozen pending your decision'}
                  </p>
                )}
              </div>
            )}

            {/* Agent completion, not readiness: this sits directly under the
                roster's own "N/6 done" counter, and readiness stays 0 until the
                Verifier runs, which read as "0% with 3 of 6 done". */}
            <AgentRoster agents={agentCards} overallProgress={agentProgress} />

            {phase === 'complete' && artifacts && (
              <button
                type="button"
                onClick={() => setShowGate(true)}
                disabled={busy}
                className="mt-4 w-full rounded-xl px-4 py-3 text-sm font-semibold"
                style={{ background: 'linear-gradient(to right,#8174C9,#9D7CFF)', color: '#10122B' }}
              >
                Continue to submission…
              </button>
            )}
          </div>
        </div>
      </section>

      {journeySteps.length > 0 && <JourneyTimeline steps={journeySteps} />}
      {evidenceItems.length > 0 && <EvidencePanel evidence={evidenceItems} />}

      <Footer />

      <ConflictModal
        isOpen={phase === 'awaiting_conflict' && activeConflict !== null}
        conflict={activeConflict ? toConflictData(activeConflict) : null}
        onResolveConflict={chosen => {
          if (!activeConflict) return
          void resume({
            kind: 'conflict_resolution',
            conflict_id: activeConflict.conflict_id,
            accepted: resolveSide(activeConflict, chosen),
          })
        }}
        onClose={() => {
          // The graph is genuinely paused here; closing without choosing would
          // strand the run, so treat dismissal as accepting the document value.
          if (!activeConflict) return
          void resume({
            kind: 'conflict_resolution',
            conflict_id: activeConflict.conflict_id,
            accepted: 'document',
          })
        }}
      />

      <ApprovalModal
        isOpen={phase === 'awaiting_approval' && approval !== null}
        caseSummary={{
          goal: caseState.goal,
          city: caseState.city ?? formValues.city,
          district: caseState.district ?? formValues.district,
          readiness: `${caseState.readiness_pct}%`,
          requirements: approval?.requirement_count ?? caseState.requirements.length,
          evidenceAccepted: approval?.accepted_evidence_count ?? 0,
          evidenceRejected: approval?.rejected_evidence_count ?? 0,
          vatRegistrationRequired:
            caseState.vat_registration_required === null || caseState.vat_registration_required === undefined
              ? 'Not determined'
              : caseState.vat_registration_required ? 'Required' : 'Not required',
          note: String(approval?.summary ?? ''),
        }}
        onApprove={() => void resume({ kind: 'approval_gate', decision: 'approve' })}
        onDisapprove={reason => void resume({ kind: 'approval_gate', decision: 'reject', note: reason })}
      />

      <ActionGateModal
        isOpen={showGate}
        action={gateAction}
        onConfirm={() => void submitToBalady()}
        onCancel={() => setShowGate(false)}
      />

      {trace.length > 0 && (
        <p className="sr-only">Last update {formatClock(trace[trace.length - 1].at)}</p>
      )}
    </div>
  )
}
