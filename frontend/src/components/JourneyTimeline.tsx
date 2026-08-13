import { CheckCircle, Circle, AlertCircle, Clock, ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'
import type { JourneyStep, JourneyStepStatus } from '../types/bosalah'

// ─── Config ───────────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<JourneyStepStatus, {
  icon: typeof Circle
  color: string
  ringColor: string
  trackColor: string
  label: string
}> = {
  done:     { icon: CheckCircle, color: '#5BCD84', ringColor: 'rgba(91,205,132,0.3)',   trackColor: '#5BCD84',              label: 'Completed' },
  active:   { icon: Circle,      color: '#9D7CFF', ringColor: 'rgba(157,124,255,0.3)',  trackColor: 'rgba(157,124,255,0.4)', label: 'In progress' },
  blocked:  { icon: AlertCircle, color: '#C0564B', ringColor: 'rgba(192,86,75,0.3)',    trackColor: 'rgba(192,86,75,0.3)',   label: 'Blocked' },
  upcoming: { icon: Circle,      color: '#333660', ringColor: 'rgba(255,255,255,0.06)', trackColor: 'rgba(255,255,255,0.05)', label: 'Upcoming' },
}

// ─── Single step ─────────────────────────────────────────────────────────────

function StepNode({ step, index, isLast }: { step: JourneyStep; index: number; isLast: boolean }) {
  const [open, setOpen] = useState(step.status === 'active')
  const cfg = STATUS_CONFIG[step.status]
  const Icon = cfg.icon
  const isDim = step.status === 'upcoming'

  return (
    <div className="relative flex gap-4" style={{ opacity: isDim ? 0.45 : 1 }}>
      {/* ── Left track ── */}
      <div className="flex flex-col items-center" style={{ width: 32, flexShrink: 0 }}>
        {/* Step circle */}
        <div
          className="relative flex items-center justify-center rounded-full z-10 shrink-0"
          style={{
            width: 32, height: 32,
            background: cfg.ringColor,
            border: `1.5px solid ${cfg.color}`,
          }}
        >
          {step.status === 'active' ? (
            /* Pulsing ring for active step */
            <>
              <div
                className="absolute inset-0 rounded-full animate-pulse-ring"
                style={{ background: cfg.ringColor }}
              />
              <span
                className="relative text-xs font-bold tabular-nums"
                style={{ color: cfg.color }}
              >
                {String(index + 1).padStart(2, '0')}
              </span>
            </>
          ) : (
            <Icon size={14} style={{ color: cfg.color }} strokeWidth={2.5} />
          )}
        </div>

        {/* Vertical track line (hidden on last step) */}
        {!isLast && (
          <div
            className="flex-1 mt-1"
            style={{
              width: 2,
              minHeight: 40,
              background: `linear-gradient(to bottom, ${cfg.trackColor}, rgba(255,255,255,0.05))`,
              borderRadius: 1,
            }}
          />
        )}
      </div>

      {/* ── Content ── */}
      <div className="flex-1 pb-8">
        <button
          className="w-full text-left flex items-start justify-between gap-3 group"
          onClick={() => setOpen(v => !v)}
          disabled={isDim}
        >
          <div>
            <div className="flex items-center gap-2 flex-wrap mb-0.5">
              <span
                className="text-sm font-semibold leading-snug"
                style={{ color: step.status === 'done' ? '#F1F1F1' : step.status === 'active' ? '#F1F1F1' : '#B0B0B0' }}
              >
                {step.label}
              </span>
              {/* Status pill */}
              <span
                className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full"
                style={{
                  background: cfg.ringColor,
                  color: cfg.color,
                  border: `1px solid ${cfg.color}33`,
                }}
              >
                {cfg.label}
              </span>
              {step.agentName && (
                <span className="text-[10px]" style={{ color: '#616161' }}>
                  by {step.agentName}
                </span>
              )}
            </div>
            <p className="text-xs leading-relaxed" style={{ color: '#7A7A8A' }}>
              {step.description}
            </p>
            {step.completedAt && (
              <p className="text-xs mt-1 flex items-center gap-1" style={{ color: '#616161' }}>
                <Clock size={10} />
                {new Date(step.completedAt).toLocaleString('en-SA', { dateStyle: 'medium', timeStyle: 'short' })}
              </p>
            )}
          </div>
          {step.subSteps && step.subSteps.length > 0 && !isDim && (
            <span className="shrink-0 mt-1">
              {open
                ? <ChevronUp size={13} style={{ color: '#616161' }} />
                : <ChevronDown size={13} style={{ color: '#616161' }} />
              }
            </span>
          )}
        </button>

        {/* Sub-steps */}
        {open && step.subSteps && step.subSteps.length > 0 && (
          <ul className="mt-3 flex flex-col gap-1.5">
            {step.subSteps.map((sub, i) => (
              <li key={i} className="flex items-center gap-2.5">
                <span
                  className="w-4 h-4 flex items-center justify-center rounded-full shrink-0"
                  style={{
                    background: sub.done ? 'rgba(91,205,132,0.15)' : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${sub.done ? '#5BCD84' : 'rgba(255,255,255,0.1)'}`,
                  }}
                >
                  {sub.done && <CheckCircle size={9} style={{ color: '#5BCD84' }} strokeWidth={3} />}
                </span>
                <span className="text-xs" style={{ color: sub.done ? '#B0B0B0' : '#616161' }}>
                  {sub.label}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

// ─── Panel ────────────────────────────────────────────────────────────────────

interface JourneyTimelineProps {
  steps: JourneyStep[]
}

export default function JourneyTimeline({ steps }: JourneyTimelineProps) {
  const doneCount    = steps.filter(s => s.status === 'done').length
  const progressPct  = steps.length > 0 ? Math.round((doneCount / steps.length) * 100) : 0

  return (
    <section id="journey" className="py-16 px-6">
      <div className="max-w-3xl mx-auto">

        {/* Header */}
        <div className="mb-8 animate-fade-up">
          <p className="section-label mb-3">Journey Roadmap</p>
          <div className="flex items-end justify-between gap-4 flex-wrap">
            <div>
              <h2
                className="font-extrabold tracking-tight mb-1"
                style={{ fontSize: 'clamp(22px, 3.5vw, 32px)', color: '#F1F1F1' }}
              >
                Your path to a permit
              </h2>
              <p className="text-sm" style={{ color: '#B0B0B0' }}>
                {doneCount} of {steps.length} steps completed
              </p>
            </div>
            {/* Mini progress ring */}
            <div className="flex items-center gap-3">
              <svg width="40" height="40" viewBox="0 0 40 40">
                <circle cx="20" cy="20" r="16" fill="none" stroke="rgba(129,116,201,0.15)" strokeWidth="3.5" />
                <circle
                  cx="20" cy="20" r="16"
                  fill="none"
                  stroke="url(#ringGrad)"
                  strokeWidth="3.5"
                  strokeLinecap="round"
                  strokeDasharray={`${2 * Math.PI * 16}`}
                  strokeDashoffset={`${2 * Math.PI * 16 * (1 - progressPct / 100)}`}
                  transform="rotate(-90 20 20)"
                />
                <defs>
                  <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#9D7CFF" />
                    <stop offset="100%" stopColor="#5BCD84" />
                  </linearGradient>
                </defs>
                <text x="20" y="24" textAnchor="middle" fontSize="9" fontWeight="700" fill="#F1F1F1">
                  {progressPct}%
                </text>
              </svg>
              <div>
                <p className="text-xs font-semibold" style={{ color: '#F1F1F1' }}>{progressPct}%</p>
                <p className="text-xs" style={{ color: '#616161' }}>done</p>
              </div>
            </div>
          </div>

          {/* Progress bar */}
          <div className="mt-4 h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(129,116,201,0.15)' }}>
            <div
              className="h-full rounded-full transition-[width] duration-700"
              style={{
                width: `${progressPct}%`,
                background: 'linear-gradient(to right, #9D7CFF, #5BCD84)',
              }}
            />
          </div>
        </div>

        {/* Timeline */}
        <div
          className="rounded-2xl p-6"
          style={{ background: 'rgba(23,27,61,0.6)', border: '1px solid rgba(129,116,201,0.15)' }}
        >
          {steps.map((step, i) => (
            <StepNode
              key={step.id}
              step={step}
              index={i}
              isLast={i === steps.length - 1}
            />
          ))}
        </div>
      </div>
    </section>
  )
}
