import { Check, X, Clock, Zap, Bot, Cpu } from 'lucide-react'
import type { AgentCard as AgentCardType } from '../types/bosalah'
import ProgressBar from './ProgressBar'

// ─── Badge config ────────────────────────────────────────────────────────────

const BADGE_CONFIG: Record<AgentCardType['badge'], { label: string; icon: typeof Bot; bg: string; color: string; border: string }> = {
  LLM:           { label: 'LLM',   icon: Bot,  bg: 'rgba(223,212,255,0.08)', color: '#BEA9FF', border: 'rgba(129,116,201,0.3)' },
  A2A:           { label: 'A2A',   icon: Zap,  bg: 'rgba(91,205,132,0.08)',  color: '#5BCD84', border: 'rgba(91,205,132,0.3)' },
  DETERMINISTIC: { label: 'DET',   icon: Cpu,  bg: 'rgba(255,255,255,0.04)', color: '#B0B0B0', border: 'rgba(255,255,255,0.1)' },
}

// ─── Status indicator ────────────────────────────────────────────────────────

function StatusIndicator({ status }: { status: AgentCardType['status'] }) {
  if (status === 'completed')
    return (
      <span className="flex items-center gap-1.5 text-xs font-semibold" style={{ color: '#5BCD84' }}>
        <Check size={11} strokeWidth={3} />
        Completed
      </span>
    )
  if (status === 'error')
    return (
      <span className="flex items-center gap-1.5 text-xs font-semibold" style={{ color: '#C0564B' }}>
        <X size={11} strokeWidth={3} />
        Error
      </span>
    )
  if (status === 'working')
    return (
      <span className="flex items-center gap-1.5 text-xs font-semibold animate-bosalah-pulse" style={{ color: '#9D7CFF' }}>
        <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: '#9D7CFF' }} />
        Working…
      </span>
    )
  return (
    <span className="flex items-center gap-1.5 text-xs" style={{ color: '#616161' }}>
      <Clock size={11} />
      Waiting
    </span>
  )
}

// ─── Border + bg per status ──────────────────────────────────────────────────

const STATUS_STYLE: Record<AgentCardType['status'], { border: string; bg: string }> = {
  waiting:   { border: 'rgba(255,255,255,0.07)', bg: 'rgba(23,27,61,0.5)' },
  working:   { border: 'rgba(157,124,255,0.45)', bg: 'rgba(23,27,61,0.9)' },
  completed: { border: 'rgba(91,205,132,0.3)',   bg: 'rgba(91,205,132,0.04)' },
  error:     { border: 'rgba(192,86,75,0.35)',   bg: 'rgba(192,86,75,0.04)' },
}

const STATUS_LEFT: Record<AgentCardType['status'], string> = {
  waiting:   '#333660',
  working:   '#9D7CFF',
  completed: '#5BCD84',
  error:     '#C0564B',
}

// ─── Single card ─────────────────────────────────────────────────────────────

function AgentCardItem({ agent, index }: { agent: AgentCardType; index: number }) {
  const { border, bg } = STATUS_STYLE[agent.status]
  const badge = BADGE_CONFIG[agent.badge]
  const BadgeIcon = badge.icon
  const isWorking = agent.status === 'working'
  const isDim = agent.status === 'waiting'

  return (
    <div
      className="relative overflow-hidden rounded-xl transition-all duration-300"
      style={{
        background: bg,
        border: `1px solid ${border}`,
        borderLeft: `3px solid ${STATUS_LEFT[agent.status]}`,
        opacity: isDim ? 0.55 : 1,
      }}
    >
      <div className="px-4 py-3.5 flex flex-col gap-0">
        {/* Top row: step number + name + badge */}
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <div className="flex items-center gap-2.5 min-w-0">
            <span
              className="text-[10px] font-bold tabular-nums shrink-0"
              style={{ color: STATUS_LEFT[agent.status], minWidth: 20 }}
            >
              {String(index + 1).padStart(2, '0')}
            </span>
            <span className="text-sm font-semibold truncate" style={{ color: isDim ? '#B0B0B0' : '#F1F1F1' }}>
              {agent.name}
            </span>
          </div>
          <span
            className="shrink-0 inline-flex items-center gap-1 text-[10px] font-bold tracking-wide uppercase px-2 py-0.5 rounded-full"
            style={{ background: badge.bg, color: badge.color, border: `1px solid ${badge.border}` }}
          >
            <BadgeIcon size={9} />
            {badge.label}
          </span>
        </div>

        {/* Description */}
        <p className="text-xs leading-snug mb-2.5 pl-8" style={{ color: '#7A7A8A' }}>
          {agent.description}
        </p>

        {/* Status */}
        <div className="pl-8">
          <StatusIndicator status={agent.status} />
        </div>

      </div>

      {/* Working: animated bar at bottom */}
      {isWorking && (
        <div
          className="absolute bottom-0 left-0 h-0.5 animate-bosalah-fill"
          style={{ background: 'linear-gradient(to right, #8174C9, #9D7CFF, #BEA9FF)' }}
        />
      )}

      {/* Completed: faint checkmark watermark */}
      {agent.status === 'completed' && (
        <div
          className="absolute right-3 bottom-2 pointer-events-none"
          style={{ opacity: 0.08 }}
        >
          <Check size={40} style={{ color: '#5BCD84' }} strokeWidth={1.5} />
        </div>
      )}
    </div>
  )
}

// ─── Roster panel ────────────────────────────────────────────────────────────

interface AgentRosterProps {
  agents: AgentCardType[]
  overallProgress: number
}

export default function AgentRoster({ agents, overallProgress }: AgentRosterProps) {
  const working   = agents.filter(a => a.status === 'working').length
  const completed = agents.filter(a => a.status === 'completed').length

  return (
    <aside
      id="execution"
      className="flex flex-col gap-4 rounded-2xl p-5"
      style={{
        background: 'rgba(23,27,61,0.8)',
        border: '1px solid rgba(129,116,201,0.2)',
        backdropFilter: 'blur(12px)',
      }}
    >
      {/* Header */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-bold" style={{ color: '#F1F1F1' }}>Agent Activity</h3>
          <div className="flex items-center gap-3 text-xs" style={{ color: '#616161' }}>
            {working > 0 && (
              <span className="animate-bosalah-pulse" style={{ color: '#9D7CFF' }}>
                {working} running
              </span>
            )}
            <span>{completed}/{agents.length} done</span>
          </div>
        </div>
        <ProgressBar percentage={overallProgress} />
      </div>

      {/* Divider */}
      <div style={{ height: 1, background: 'rgba(129,116,201,0.12)' }} />

      {/* Agent cards */}
      <div className="flex flex-col gap-2.5">
        {agents.map((agent, i) => (
          <AgentCardItem key={agent.name} agent={agent} index={i} />
        ))}
      </div>

      {/* Legend */}
      <div
        className="flex items-center justify-center gap-4 pt-1 flex-wrap"
        style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: 12 }}
      >
        {[
          { color: '#5BCD84', label: 'Done' },
          { color: '#9D7CFF', label: 'Working' },
          { color: '#333660', label: 'Waiting' },
          { color: '#C0564B', label: 'Error' },
        ].map(s => (
          <span key={s.label} className="flex items-center gap-1.5 text-xs" style={{ color: '#616161' }}>
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </aside>
  )
}
