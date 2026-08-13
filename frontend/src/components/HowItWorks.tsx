import { Target, Search, MapPin, ShieldCheck, FileText, Navigation } from 'lucide-react'

const SPOKE_NODES = [
  { icon: Target,      label: 'Understands your goal',             color: '#9D7CFF' },
  { icon: Search,      label: 'Checks official sources',           color: '#BEA9FF' },
  { icon: MapPin,      label: 'Verifies municipal requirements',   color: '#9D7CFF' },
  { icon: ShieldCheck, label: 'Audits every claim',                color: '#5BCD84' },
  { icon: FileText,    label: 'Assembles your packet',             color: '#93DEAE' },
  { icon: Navigation,  label: 'Guides your next step',             color: '#9D7CFF' },
]

const HUB_R   = 185   // hub-to-spoke distance (px in viewBox units)
const VBOX    = 580   // square viewBox
const CX      = VBOX / 2
const CY      = VBOX / 2
const NODE_R  = 36    // spoke circle radius

function polar(angleDeg: number, radius: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180
  return { x: CX + radius * Math.cos(rad), y: CY + radius * Math.sin(rad) }
}

export default function HowItWorks() {
  const n = SPOKE_NODES.length

  return (
    <section id="how-it-works" className="py-28 px-6">
      <div className="max-w-5xl mx-auto">

        {/* Heading */}
        <div className="text-center mb-16 animate-fade-up">
          <p className="section-label justify-center mb-4" style={{ justifyContent: 'center', gap: 8 }}>
            <span style={{ flex: 'none' }}>How it works</span>
          </p>
          <h2
            className="font-extrabold tracking-tight mb-4"
            style={{ fontSize: 'clamp(28px, 5vw, 44px)', color: '#F1F1F1' }}
          >
            Six agents.{' '}
            {/* "One seamless flow" in green to echo Saudi palette */}
            <span className="gradient-text-green">One seamless flow.</span>
          </h2>
          <p className="text-base max-w-md mx-auto" style={{ color: '#B0B0B0' }}>
            From your first sentence to a ready-to-submit government packet.
          </p>
          {/* Purple → green accent bar — Saudi dual-colour signature */}
          <div className="saudi-bar mx-auto mt-5 rounded-full" style={{ width: 64, height: 3, opacity: 0.7 }} />
        </div>

        {/* ── Radial diagram (sm+) ── */}
        <div className="hidden sm:block relative w-full max-w-[580px] mx-auto" style={{ aspectRatio: '1' }}>
          <svg
            viewBox={`0 0 ${VBOX} ${VBOX}`}
            className="absolute inset-0 w-full h-full"
            aria-hidden
          >
            {/* Outer decorative ring — alternating purple / green dashes */}
            <circle cx={CX} cy={CY} r={HUB_R + 40} stroke="url(#duoRing)" strokeWidth="1.5" fill="none" strokeDasharray="6 3" opacity="0.4" />
            <defs>
              <linearGradient id="duoRing" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%"   stopColor="#9D7CFF" />
                <stop offset="50%"  stopColor="#5BCD84" />
                <stop offset="100%" stopColor="#9D7CFF" />
              </linearGradient>
              <linearGradient id="duoSpoke" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%"   stopColor="#9D7CFF" stopOpacity="0.6" />
                <stop offset="100%" stopColor="#5BCD84" stopOpacity="0.6" />
              </linearGradient>
            </defs>

            {/* Spoke lines */}
            {SPOKE_NODES.map((node, i) => {
              const angle = (360 / n) * i
              const spoke = polar(angle, HUB_R)
              // Line starts at hub edge, ends at spoke circle edge
              const hubEdge   = polar(angle, 52)
              const spokeEdge = polar(angle, HUB_R - NODE_R)
              return (
                <g key={i}>
                  <line
                    x1={hubEdge.x} y1={hubEdge.y}
                    x2={spokeEdge.x} y2={spokeEdge.y}
                    stroke="rgba(129,116,201,0.25)"
                    strokeWidth="1.5"
                    strokeDasharray="5 4"
                  />
                  {/* Glowing dot along the spoke */}
                  <circle
                    cx={(hubEdge.x + spoke.x) / 2}
                    cy={(hubEdge.y + spoke.y) / 2}
                    r="2.5"
                    fill={node.color}
                    opacity="0.5"
                  />
                </g>
              )
            })}

            {/* Hub glow — purple inner, green outer */}
            <circle cx={CX} cy={CY} r="70" fill="rgba(91,205,132,0.04)" />
            <circle cx={CX} cy={CY} r="62" fill="rgba(157,124,255,0.07)" />
            <circle cx={CX} cy={CY} r="52" fill="#171B3D" stroke="url(#duoRing)" strokeWidth="1.5" />

            {/* Spoke circles */}
            {SPOKE_NODES.map((node, i) => {
              const angle = (360 / n) * i
              const pos   = polar(angle, HUB_R)
              return (
                <g key={i}>
                  <circle
                    cx={pos.x} cy={pos.y} r={NODE_R}
                    fill="#1E2347"
                    stroke={node.color}
                    strokeWidth="1"
                    strokeOpacity="0.4"
                  />
                  {/* Number badge */}
                  <text
                    x={pos.x - NODE_R + 8}
                    y={pos.y - NODE_R + 14}
                    fontSize="8"
                    fill={node.color}
                    opacity="0.7"
                    fontWeight="700"
                    fontFamily="Inter, sans-serif"
                  >
                    {String(i + 1).padStart(2, '0')}
                  </text>
                </g>
              )
            })}
          </svg>

          {/* Hub label (HTML overlay) */}
          <div
            className="absolute flex flex-col items-center justify-center gap-1"
            style={{
              width: 96, height: 96,
              top: '50%', left: '50%',
              transform: 'translate(-50%, -50%)',
            }}
          >
            <span className="text-sm font-bold" style={{ color: '#F1F1F1' }}>Bosalah</span>
            <span className="text-xs rtl-text" style={{ color: '#8174C9' }}>بوصلة</span>
          </div>

          {/* Spoke labels (HTML overlays — icon + text) */}
          {SPOKE_NODES.map((node, i) => {
            const angle  = (360 / n) * i
            const pos    = polar(angle, HUB_R)
            const leftPct = (pos.x / VBOX) * 100
            const topPct  = (pos.y / VBOX) * 100
            const Icon   = node.icon

            return (
              <div
                key={node.label}
                className="absolute flex flex-col items-center gap-1.5 text-center"
                style={{
                  left: `${leftPct}%`,
                  top:  `${topPct}%`,
                  transform: 'translate(-50%, -50%)',
                  width: 72,
                }}
              >
                <Icon size={16} style={{ color: node.color }} />
                <span
                  className="leading-tight font-medium"
                  style={{ fontSize: 10, color: '#B0B0B0', lineHeight: 1.4 }}
                >
                  {node.label}
                </span>
              </div>
            )
          })}
        </div>

        {/* ── Mobile list (xs only) ── */}
        <div className="sm:hidden grid grid-cols-1 gap-3 mt-4">
          {SPOKE_NODES.map((node, i) => {
            const Icon = node.icon
            return (
              <div
                key={node.label}
                className="flex items-center gap-4 p-4 rounded-2xl"
                style={{
                  background: '#171B3D',
                  border: '1px solid rgba(129,116,201,0.18)',
                }}
              >
                <div
                  className="flex items-center justify-center rounded-xl shrink-0"
                  style={{
                    width: 40, height: 40,
                    background: 'rgba(129,116,201,0.1)',
                    border: `1px solid ${node.color}33`,
                  }}
                >
                  <Icon size={16} style={{ color: node.color }} />
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs font-bold" style={{ color: node.color, minWidth: 20 }}>
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span className="text-sm font-medium" style={{ color: '#F1F1F1' }}>{node.label}</span>
                </div>
              </div>
            )
          })}
        </div>

      </div>
    </section>
  )
}
