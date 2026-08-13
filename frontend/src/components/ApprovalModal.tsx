import { useState } from 'react'
import type { CaseSummary } from '../types/bosalah'

interface ApprovalModalProps {
  isOpen: boolean
  caseSummary: CaseSummary
  onApprove: () => void
  onDisapprove: (reason: string) => void
}

export default function ApprovalModal({
  isOpen,
  caseSummary,
  onApprove,
  onDisapprove,
}: ApprovalModalProps) {
  // Pure UI state — controls the disapprove flow before callback fires
  const [showReason, setShowReason] = useState(false)
  const [reason, setReason] = useState('')

  if (!isOpen) return null

  const summaryText =
    typeof caseSummary === 'string'
      ? caseSummary
      : JSON.stringify(caseSummary, null, 2)

  function handleDisapproveSubmit() {
    if (reason.trim()) {
      onDisapprove(reason.trim())
      setReason('')
      setShowReason(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.65)' }}
      role="dialog"
      aria-modal="true"
      aria-label="Case approval"
    >
      <div
        className="relative w-full max-w-xl rounded-2xl border border-white/10 flex flex-col"
        style={{ background: '#171B3D', color: '#F1F1F1', maxHeight: '90vh' }}
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-white/10">
          <h2 className="text-lg font-bold" style={{ color: '#F1F1F1' }}>
            Review &amp; Approve
          </h2>
          <p className="mt-1 text-sm" style={{ color: '#B0B0B0' }}>
            Bosalah has prepared a case summary. Review it below and approve or send back for
            revision.
          </p>
        </div>

        {/* Body — scrollable */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <pre
            className="text-sm leading-relaxed whitespace-pre-wrap break-words rounded-xl p-4"
            style={{ background: '#10122B', color: '#B0B0B0', fontFamily: 'inherit' }}
          >
            {summaryText}
          </pre>

          {/* Disapprove reason textarea */}
          {showReason && (
            <div className="mt-5">
              <label
                htmlFor="disapproveReason"
                className="block text-sm font-medium mb-2"
                style={{ color: '#F1F1F1' }}
              >
                What's wrong?
              </label>
              <textarea
                id="disapproveReason"
                rows={4}
                placeholder="What's wrong? This goes back to the agents to fix."
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="w-full rounded-lg px-3.5 py-2.5 text-sm resize-none focus:outline-none focus:ring-1"
                style={{
                  background: '#10122B',
                  border: '1px solid rgba(255,255,255,0.15)',
                  color: '#F1F1F1',
                  caretColor: '#9D7CFF',
                }}
              />
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-white/10 flex items-center justify-end gap-3">
          {!showReason ? (
            <>
              <button
                onClick={() => setShowReason(true)}
                className="px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
                style={{
                  background: 'rgba(217,164,65,0.12)',
                  border: '1px solid rgba(217,164,65,0.35)',
                  color: '#D9A441',
                }}
              >
                Disapprove
              </button>
              <button
                onClick={onApprove}
                className="px-5 py-2.5 rounded-lg text-sm font-semibold transition-colors"
                style={{
                  background: 'rgba(91,205,132,0.15)',
                  border: '1px solid rgba(91,205,132,0.35)',
                  color: '#5BCD84',
                }}
              >
                Approve
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => { setShowReason(false); setReason('') }}
                className="px-5 py-2.5 rounded-lg text-sm font-medium"
                style={{ color: '#B0B0B0', background: 'transparent', border: '1px solid rgba(255,255,255,0.1)' }}
              >
                Cancel
              </button>
              <button
                onClick={handleDisapproveSubmit}
                disabled={!reason.trim()}
                className="px-5 py-2.5 rounded-lg text-sm font-semibold transition-colors disabled:opacity-40"
                style={{
                  background: 'rgba(217,164,65,0.15)',
                  border: '1px solid rgba(217,164,65,0.35)',
                  color: '#D9A441',
                }}
              >
                Send back to agents
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
