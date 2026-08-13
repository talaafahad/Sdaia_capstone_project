import { useState } from 'react'
import { ShieldAlert, AlertTriangle, CheckCircle2, X } from 'lucide-react'
import type { ActionGateItem, ActionGateType } from '../types/bosalah'

// ─── Gate type config ────────────────────────────────────────────────────────

const GATE_CONFIG: Record<ActionGateType, { label: string; color: string; icon: typeof ShieldAlert }> = {
  submit_application: { label: 'Submit Application', color: '#9D7CFF', icon: ShieldAlert     },
  make_payment:       { label: 'Make Payment',        color: '#D9A441', icon: AlertTriangle   },
  send_document:      { label: 'Send Document',       color: '#BEA9FF', icon: ShieldAlert     },
  custom:             { label: 'Confirm Action',      color: '#B0B0B0', icon: ShieldAlert     },
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface ActionGateModalProps {
  isOpen: boolean
  action: ActionGateItem | null
  /** Called when user types their explicit confirmation and clicks Confirm */
  onConfirm: (actionId: string) => void
  onCancel: () => void
}

export default function ActionGateModal({
  isOpen,
  action,
  onConfirm,
  onCancel,
}: ActionGateModalProps) {
  const [confirmation, setConfirmation] = useState('')
  const [checkedRisks, setCheckedRisks] = useState<boolean[]>([])

  if (!isOpen || !action) return null

  const cfg = GATE_CONFIG[action.type]
  const GateIcon = cfg.icon

  // Initialise risk checkboxes lazily
  const risks = action.consequences
  const allRisksAcknowledged = risks.length === 0 || (
    checkedRisks.length === risks.length &&
    checkedRisks.every(Boolean)
  )
  const CONFIRMATION_WORD = 'CONFIRM'
  const confirmationValid = confirmation.trim().toUpperCase() === CONFIRMATION_WORD
  const canProceed = allRisksAcknowledged && confirmationValid

  function handleRiskToggle(i: number) {
    setCheckedRisks(prev => {
      const next = prev.length === risks.length
        ? [...prev]
        : Array.from({ length: risks.length }, (_, j) => prev[j] ?? false)
      next[i] = !next[i]
      return next
    })
  }

  // Captured after the `if (!isOpen || !action) return null` guard above, so
  // TypeScript can narrow it inside this callback.
  const confirmedAction = action

  function handleConfirm() {
    if (canProceed) {
      onConfirm(confirmedAction.id)
      setConfirmation('')
      setCheckedRisks([])
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.75)' }}
      role="dialog"
      aria-modal="true"
      aria-label="Action approval gate"
    >
      <div
        className="relative w-full max-w-lg rounded-2xl flex flex-col overflow-hidden"
        style={{
          background: '#10122B',
          border: `1px solid ${cfg.color}33`,
          maxHeight: '92vh',
          boxShadow: `0 0 60px ${cfg.color}22`,
        }}
      >
        {/* ── Header ── */}
        <div
          className="px-6 pt-6 pb-5"
          style={{ borderBottom: `1px solid rgba(255,255,255,0.06)` }}
        >
          <div className="flex items-start justify-between gap-4 mb-3">
            <div
              className="flex items-center justify-center rounded-xl"
              style={{ width: 44, height: 44, background: `${cfg.color}15`, border: `1px solid ${cfg.color}33` }}
            >
              <GateIcon size={20} style={{ color: cfg.color }} />
            </div>
            <button onClick={onCancel}>
              <X size={18} style={{ color: '#616161' }} />
            </button>
          </div>

          {/* Gate type badge */}
          <span
            className="inline-flex items-center text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-full mb-2"
            style={{ background: `${cfg.color}15`, color: cfg.color, border: `1px solid ${cfg.color}30` }}
          >
            ⚠ Real Action Required — {cfg.label}
          </span>

          <h2 className="text-lg font-bold mb-1" style={{ color: '#F1F1F1' }}>
            {action.title}
          </h2>
          <p className="text-sm leading-relaxed" style={{ color: '#B0B0B0' }}>
            {action.description}
          </p>
        </div>

        {/* ── Scrollable body ── */}
        <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-5">

          {/* Summary table */}
          <div>
            <p className="text-xs font-bold uppercase tracking-widest mb-2.5" style={{ color: '#616161' }}>
              What will be submitted
            </p>
            <div
              className="rounded-xl overflow-hidden"
              style={{ border: '1px solid rgba(255,255,255,0.07)' }}
            >
              {Object.entries(action.summary).map(([key, val], i, arr) => (
                <div
                  key={key}
                  className="flex items-center justify-between gap-4 px-4 py-2.5 text-sm"
                  style={{
                    borderBottom: i < arr.length - 1 ? '1px solid rgba(255,255,255,0.05)' : 'none',
                    background: i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent',
                  }}
                >
                  <span style={{ color: '#616161' }}>{key}</span>
                  <span className="font-medium text-right" style={{ color: '#F1F1F1' }}>{val}</span>
                </div>
              ))}
            </div>

            {/* Cost callout */}
            {action.estimatedCostSAR && (
              <div
                className="mt-3 flex items-center justify-between px-4 py-3 rounded-xl"
                style={{ background: 'rgba(217,164,65,0.08)', border: '1px solid rgba(217,164,65,0.2)' }}
              >
                <span className="text-sm font-medium" style={{ color: '#D9A441' }}>Estimated cost</span>
                <span className="text-base font-bold" style={{ color: '#D9A441' }}>
                  SAR {action.estimatedCostSAR}
                </span>
              </div>
            )}
          </div>

          {/* Risk acknowledgements */}
          {risks.length > 0 && (
            <div>
              <p className="text-xs font-bold uppercase tracking-widest mb-2.5" style={{ color: '#616161' }}>
                Acknowledge before proceeding
              </p>
              <div className="flex flex-col gap-2">
                {risks.map((risk, i) => {
                  const checked = checkedRisks[i] ?? false
                  return (
                    <label
                      key={i}
                      className="flex items-start gap-3 cursor-pointer p-3 rounded-xl transition-colors"
                      style={{
                        background: checked ? 'rgba(91,205,132,0.06)' : 'rgba(255,255,255,0.02)',
                        border: `1px solid ${checked ? 'rgba(91,205,132,0.25)' : 'rgba(255,255,255,0.07)'}`,
                      }}
                    >
                      <div
                        className="mt-0.5 shrink-0 flex items-center justify-center rounded"
                        style={{
                          width: 16, height: 16,
                          background: checked ? '#5BCD84' : 'transparent',
                          border: `1.5px solid ${checked ? '#5BCD84' : 'rgba(255,255,255,0.2)'}`,
                        }}
                      >
                        {checked && <CheckCircle2 size={10} style={{ color: '#10122B' }} strokeWidth={3} />}
                      </div>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => handleRiskToggle(i)}
                        className="sr-only"
                      />
                      <span className="text-xs leading-relaxed" style={{ color: '#B0B0B0' }}>
                        {risk}
                      </span>
                    </label>
                  )
                })}
              </div>
            </div>
          )}

          {/* Explicit confirmation input */}
          <div>
            <p className="text-xs font-bold uppercase tracking-widest mb-2" style={{ color: '#616161' }}>
              Type <span style={{ color: cfg.color, fontFamily: 'monospace' }}>{CONFIRMATION_WORD}</span> to proceed
            </p>
            <input
              type="text"
              value={confirmation}
              onChange={e => setConfirmation(e.target.value)}
              placeholder={`Type ${CONFIRMATION_WORD} here…`}
              className="field-input"
              style={{
                borderColor: confirmationValid ? 'rgba(91,205,132,0.5)' : undefined,
                boxShadow: confirmationValid ? '0 0 0 3px rgba(91,205,132,0.1)' : undefined,
              }}
              autoComplete="off"
            />
          </div>
        </div>

        {/* ── Footer ── */}
        <div
          className="px-6 py-4 flex items-center justify-between gap-3"
          style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}
        >
          <button
            onClick={onCancel}
            className="px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#B0B0B0' }}
          >
            Cancel — go back
          </button>
          <button
            onClick={handleConfirm}
            disabled={!canProceed}
            className="px-6 py-2.5 rounded-lg text-sm font-semibold transition-all duration-200"
            style={{
              background: canProceed
                ? `linear-gradient(135deg, ${cfg.color}cc, ${cfg.color})`
                : 'rgba(255,255,255,0.05)',
              color: canProceed ? '#10122B' : '#616161',
              cursor: canProceed ? 'pointer' : 'not-allowed',
              border: `1px solid ${canProceed ? cfg.color : 'rgba(255,255,255,0.08)'}`,
              boxShadow: canProceed ? `0 4px 16px ${cfg.color}40` : 'none',
            }}
          >
            Confirm &amp; Proceed
          </button>
        </div>
      </div>
    </div>
  )
}
