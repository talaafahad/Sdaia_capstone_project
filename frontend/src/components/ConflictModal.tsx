import type { ConflictData } from '../types/bosalah'

interface ConflictModalProps {
  isOpen: boolean
  conflict: ConflictData | null
  onResolveConflict: (chosenValue: string | number) => void
  onClose: () => void
}

export default function ConflictModal({
  isOpen,
  conflict,
  onResolveConflict,
  onClose,
}: ConflictModalProps) {
  if (!isOpen || !conflict) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.65)' }}
      role="dialog"
      aria-modal="true"
      aria-label="Conflict resolution"
    >
      <div
        className="relative w-full max-w-2xl rounded-2xl border border-white/10 flex flex-col"
        style={{ background: '#171B3D', color: '#F1F1F1', maxHeight: '90vh' }}
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-white/10">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p
                className="text-xs font-semibold tracking-widest uppercase mb-1"
                style={{ color: '#D9A441' }}
              >
                Conflict detected
              </p>
              <h2
                className="text-lg font-bold"
                style={{ color: '#D9A441' }}
              >
                {conflict.label}
              </h2>
            </div>
            <button
              onClick={onClose}
              className="shrink-0 text-sm px-3 py-1.5 rounded-lg"
              style={{ color: '#B0B0B0', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)' }}
            >
              Dismiss
            </button>
          </div>
          <p className="mt-2 text-sm" style={{ color: '#B0B0B0' }}>
            Two conflicting values were found. Choose which one Bosalah should use to proceed.
          </p>
        </div>

        {/* Body — side by side comparison */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Value A */}
            <div
              className="flex flex-col gap-3 rounded-xl p-5"
              style={{ background: '#10122B', border: '1px solid rgba(255,255,255,0.08)' }}
            >
              <p className="text-xs font-semibold tracking-widest uppercase" style={{ color: '#616161' }}>
                Source A
              </p>
              <p className="text-3xl font-bold" style={{ color: '#F1F1F1' }}>
                {conflict.valueA}
              </p>
              <p className="text-sm" style={{ color: '#B0B0B0' }}>
                {conflict.sourceA}
              </p>
              <button
                onClick={() => onResolveConflict(conflict.valueA)}
                className="mt-auto w-full py-2.5 rounded-lg text-sm font-semibold transition-colors"
                style={{
                  background: 'rgba(157,124,255,0.15)',
                  border: '1px solid rgba(157,124,255,0.35)',
                  color: '#9D7CFF',
                }}
              >
                Use this value
              </button>
            </div>

            {/* Value B */}
            <div
              className="flex flex-col gap-3 rounded-xl p-5"
              style={{ background: '#10122B', border: '1px solid rgba(255,255,255,0.08)' }}
            >
              <p className="text-xs font-semibold tracking-widest uppercase" style={{ color: '#616161' }}>
                Source B
              </p>
              <p className="text-3xl font-bold" style={{ color: '#F1F1F1' }}>
                {conflict.valueB}
              </p>
              <p className="text-sm" style={{ color: '#B0B0B0' }}>
                {conflict.sourceB}
              </p>
              <button
                onClick={() => onResolveConflict(conflict.valueB)}
                className="mt-auto w-full py-2.5 rounded-lg text-sm font-semibold transition-colors"
                style={{
                  background: 'rgba(157,124,255,0.15)',
                  border: '1px solid rgba(157,124,255,0.35)',
                  color: '#9D7CFF',
                }}
              >
                Use this value
              </button>
            </div>
          </div>
        </div>

        {/* Footer note */}
        <div className="px-6 py-4 border-t border-white/10">
          <p className="text-xs" style={{ color: '#616161' }}>
            Your choice will be used for all downstream calculations and the final permit packet.
          </p>
        </div>
      </div>
    </div>
  )
}
