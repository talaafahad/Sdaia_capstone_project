import { Compass } from 'lucide-react'

export default function Footer() {
  return (
    <footer className="py-12 px-6 mt-16">
      {/* Saudi dual-colour top border — purple left, green right */}
      <div className="saudi-bar w-full h-px mb-10" style={{ opacity: 0.35 }} />

      <div className="max-w-7xl mx-auto">
        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
          {/* Brand */}
          <div className="flex items-center gap-2.5">
            <div
              className="flex items-center justify-center rounded-lg"
              style={{
                width: 28, height: 28,
                background: 'linear-gradient(135deg, rgba(129,116,201,0.14), rgba(91,205,132,0.1))',
                border: '1px solid rgba(91,205,132,0.2)',
              }}
            >
              <Compass size={13} style={{ color: '#5BCD84' }} />
            </div>
            <div className="flex items-baseline gap-1.5">
              <span className="text-sm font-semibold gradient-text">Bosalah</span>
              <span className="text-sm rtl-text font-semibold" style={{ color: '#5BCD84', opacity: 0.7 }}>بوصلة</span>
            </div>
          </div>

          {/* Links */}
          <div className="flex items-center gap-6">
            {['How it works', 'Start a case', 'Agent activity'].map((label, i) => (
              <a
                key={i}
                href={['#how-it-works', '#intake', '#execution'][i]}
                className="text-xs transition-colors"
                style={{ color: '#616161' }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = '#B0B0B0' }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = '#616161' }}
              >
                {label}
              </a>
            ))}
          </div>

          {/* Note */}
          <p className="text-xs text-center" style={{ color: '#3A3D60' }}>
            AI guidance only — always verify with official Saudi government sources.
          </p>
        </div>
      </div>
    </footer>
  )
}
