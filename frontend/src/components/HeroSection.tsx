import { Compass, ArrowRight } from 'lucide-react'

/**
 * Tagline options (pass one as `tagline` prop):
 *   A: "Your compass through Saudi government procedures."
 *   B: "Navigate every licence requirement with confidence."
 *   C: "From goal to permit — guided every step of the way."
 */

interface HeroSectionProps {
  tagline: string
  onSuggestedCaseClick: (text: string) => void
  onStartClick: () => void
}

const SUGGESTED_CASES = [
  'Open a coffee shop in Riyadh',
  'Register a specialty spa',
  'Start a food truck',
  'Set up a professional office',
]

export default function HeroSection({ tagline, onSuggestedCaseClick, onStartClick }: HeroSectionProps) {
  return (
    <section
      id="hero"
      className="relative flex flex-col items-center justify-center min-h-screen px-6 py-32 text-center overflow-hidden"
    >
      {/* ── Deep dual-colour radial glow — purple left, green right ─── */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 55% 55% at 30% 45%, rgba(129,116,201,0.13) 0%, transparent 70%),' +
            'radial-gradient(ellipse 55% 55% at 70% 55%, rgba(91,205,132,0.10) 0%, transparent 70%)',
        }}
      />

      {/* ── Decorative blurred orbs — purple top-left, green bottom-right ─── */}
      <div
        aria-hidden
        className="pointer-events-none absolute"
        style={{
          width: 360, height: 360, top: '10%', left: '5%',
          background: 'radial-gradient(circle, rgba(157,124,255,0.09) 0%, transparent 70%)',
          borderRadius: '50%', filter: 'blur(50px)',
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute"
        style={{
          width: 300, height: 300, bottom: '15%', right: '8%',
          background: 'radial-gradient(circle, rgba(91,205,132,0.10) 0%, transparent 70%)',
          borderRadius: '50%', filter: 'blur(45px)',
        }}
      />
      {/* Extra small green orb top-right for balance */}
      <div
        aria-hidden
        className="pointer-events-none absolute"
        style={{
          width: 180, height: 180, top: '8%', right: '18%',
          background: 'radial-gradient(circle, rgba(91,205,132,0.07) 0%, transparent 70%)',
          borderRadius: '50%', filter: 'blur(30px)',
        }}
      />

      {/* ── Floating compass graphic ─── */}
      <div
        aria-hidden
        className="pointer-events-none absolute"
        style={{ top: '12%', right: '12%', opacity: 0.12 }}
      >
        <div className="animate-spin-slow" style={{ width: 200, height: 200 }}>
          {/* Compass rose — outer ring purple, inner ring green */}
          <svg viewBox="0 0 200 200" fill="none">
            {/* Outer dashed ring — purple */}
            <circle cx="100" cy="100" r="94" stroke="#9D7CFF" strokeWidth="1" strokeDasharray="6 4" />
            {/* Middle dashed ring — green */}
            <circle cx="100" cy="100" r="70" stroke="#5BCD84" strokeWidth="0.8" strokeDasharray="3 6" opacity="0.7" />
            {/* Inner solid ring — purple */}
            <circle cx="100" cy="100" r="46" stroke="#8174C9" strokeWidth="0.5" opacity="0.5" />
            {/* 12 tick marks — alternating purple / green */}
            {[0,30,60,90,120,150,180,210,240,270,300,330].map((a, idx) => {
              const rad = (a - 90) * Math.PI / 180
              const x1 = 100 + 72 * Math.cos(rad), y1 = 100 + 72 * Math.sin(rad)
              const x2 = 100 + 88 * Math.cos(rad), y2 = 100 + 88 * Math.sin(rad)
              return <line key={a} x1={x1} y1={y1} x2={x2} y2={y2} stroke={idx % 2 === 0 ? '#9D7CFF' : '#5BCD84'} strokeWidth="1" />
            })}
            {/* North needle — purple (lavender) */}
            <polygon points="100,18 104,92 100,100 96,92" fill="#9D7CFF" />
            {/* South needle — Saudi green */}
            <polygon points="100,182 104,108 100,100 96,108" fill="#5BCD84" />
            {/* Center jewel */}
            <circle cx="100" cy="100" r="7" fill="#9D7CFF" />
            <circle cx="100" cy="100" r="3" fill="#5BCD84" />
          </svg>
        </div>
      </div>

      {/* ── Main content ─── */}
      <div className="relative z-10 max-w-4xl mx-auto flex flex-col items-center gap-8">

        {/* Badge */}
        <div className="animate-fade-up-1">
          <span
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-semibold tracking-widest uppercase"
            style={{
              background: 'linear-gradient(135deg, rgba(129,116,201,0.12), rgba(91,205,132,0.08))',
              border: '1px solid rgba(157,124,255,0.2)',
              color: '#BEA9FF',
            }}
          >
            {/* Purple dot */}
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: '#9D7CFF', boxShadow: '0 0 5px #9D7CFF' }} />
            AI-Powered
            <span style={{ color: '#616161' }}>·</span>
            {/* Green-tinted "Saudi Government" */}
            <span style={{ color: '#5BCD84' }}>Saudi Government Guide</span>
            {/* Green dot */}
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: '#5BCD84', boxShadow: '0 0 5px #5BCD84' }} />
          </span>
        </div>

        {/* Title */}
        <div className="animate-fade-up-2 flex flex-col items-center gap-3">
          <h1
            className="font-extrabold leading-none tracking-tight"
            style={{ fontSize: 'clamp(52px, 9vw, 96px)' }}
          >
            <span className="gradient-text">Bosalah</span>
          </h1>
          {/* Arabic name in Saudi green */}
          <p
            className="rtl-text font-bold tracking-wide gradient-text-green"
            style={{ fontSize: 'clamp(28px, 5vw, 48px)' }}
          >
            بوصلة
          </p>
        </div>

        {/* Animated compass icon */}
        <div className="animate-fade-up-2 animate-float relative">
          {/* Outer pulse ring — blends purple + green */}
          <div
            className="animate-pulse-ring absolute rounded-full"
            style={{
              inset: -8,
              background: 'conic-gradient(from 0deg, rgba(157,124,255,0.2), rgba(91,205,132,0.2), rgba(157,124,255,0.2))',
            }}
          />
          <div
            className="relative flex items-center justify-center rounded-full"
            style={{
              width: 76, height: 76,
              background: 'linear-gradient(135deg, #1E2347 0%, #152E1E 100%)',
              border: '1.5px solid transparent',
              backgroundClip: 'padding-box',
              boxShadow: '0 0 24px rgba(157,124,255,0.2), 0 0 24px rgba(91,205,132,0.15)',
              outline: '1.5px solid rgba(91,205,132,0.2)',
            }}
          >
            <Compass size={32} style={{ color: '#9D7CFF' }} />
          </div>
        </div>

        {/* Tagline */}
        <p
          className="animate-fade-up-3 text-xl sm:text-2xl max-w-2xl leading-relaxed"
          style={{ color: '#B0B0B0' }}
        >
          {tagline}
        </p>

        {/* Suggested case chips */}
        <div className="animate-fade-up-4 flex flex-wrap justify-center gap-3">
          {SUGGESTED_CASES.map((text) => (
            <button
              key={text}
              onClick={() => onSuggestedCaseClick(text)}
              className="group flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all duration-200"
              style={{
                background: 'rgba(129,116,201,0.08)',
                border: '1px solid rgba(129,116,201,0.25)',
                color: '#BEA9FF',
              }}
              onMouseEnter={e => {
                const t = e.currentTarget
                t.style.background = 'rgba(157,124,255,0.15)'
                t.style.borderColor = 'rgba(157,124,255,0.5)'
                t.style.color = '#9D7CFF'
                t.style.transform = 'translateY(-1px)'
              }}
              onMouseLeave={e => {
                const t = e.currentTarget
                t.style.background = 'rgba(129,116,201,0.08)'
                t.style.borderColor = 'rgba(129,116,201,0.25)'
                t.style.color = '#BEA9FF'
                t.style.transform = 'translateY(0)'
              }}
            >
              {text}
              <ArrowRight size={13} className="opacity-0 group-hover:opacity-100 transition-opacity -translate-x-1 group-hover:translate-x-0 duration-200" />
            </button>
          ))}
        </div>

        {/* CTA buttons */}
        <div className="animate-fade-up-5 flex flex-col sm:flex-row items-center gap-4">
          {/* CTA — purple → green gradient (Saudi palette) */}
          <button
            onClick={onStartClick}
            className="group relative px-10 py-4 rounded-xl font-semibold text-base text-white overflow-hidden transition-all duration-200"
            style={{
              background: 'linear-gradient(135deg, #8174C9 0%, #9D7CFF 55%, #5BCD84 100%)',
              boxShadow: '0 4px 20px rgba(157,124,255,0.3), 0 4px 20px rgba(91,205,132,0.15)',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.transform = 'translateY(-2px)'
              e.currentTarget.style.boxShadow = '0 8px 28px rgba(157,124,255,0.45), 0 8px 28px rgba(91,205,132,0.2)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.transform = 'translateY(0)'
              e.currentTarget.style.boxShadow = '0 4px 20px rgba(157,124,255,0.3), 0 4px 20px rgba(91,205,132,0.15)'
            }}
          >
            Start Your Case
          </button>
          <a
            href="#how-it-works"
            className="flex items-center gap-2 text-sm font-medium transition-colors"
            style={{ color: '#616161' }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = '#B0B0B0' }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = '#616161' }}
          >
            See how it works
            <ArrowRight size={13} />
          </a>
        </div>
      </div>

      {/* ── Scroll cue ─── */}
      <div
        className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2"
        style={{ opacity: 0.35 }}
      >
        <span className="text-xs tracking-[0.2em] uppercase" style={{ color: '#B0B0B0' }}>
          Scroll
        </span>
        <div
          className="w-px h-10"
          style={{ background: 'linear-gradient(to bottom, #8174C9, transparent)' }}
        />
      </div>
    </section>
  )
}
