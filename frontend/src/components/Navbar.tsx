import { Compass } from 'lucide-react'

export default function Navbar() {
  return (
    <header
      className="navbar-blur fixed top-0 left-0 right-0 z-40"
    >
      <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
        {/* Logo */}
        <a href="#hero" className="flex items-center gap-2.5 group">
          <div
            className="flex items-center justify-center rounded-lg transition-all duration-200"
            style={{
              width: 30, height: 30,
              background: 'linear-gradient(135deg, rgba(129,116,201,0.18) 0%, rgba(91,205,132,0.12) 100%)',
              border: '1px solid rgba(91,205,132,0.2)',
            }}
          >
            <Compass size={15} style={{ color: '#9D7CFF' }} />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-sm font-bold gradient-text">Bosalah</span>
            {/* Arabic in green */}
            <span className="text-sm rtl-text font-semibold" style={{ color: '#5BCD84' }}>بوصلة</span>
          </div>
        </a>

        {/* Nav links */}
        <nav className="hidden md:flex items-center gap-6">
          {[
            { label: 'How it works', href: '#how-it-works' },
            { label: 'Start a case', href: '#intake' },
          ].map(({ label, href }) => (
            <a
              key={href}
              href={href}
              className="text-sm transition-colors"
              style={{ color: '#616161' }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = '#B0B0B0' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = '#616161' }}
            >
              {label}
            </a>
          ))}
        </nav>

        {/* CTA — purple/green dual border */}
        <a
          href="#intake"
          className="hidden sm:inline-flex items-center px-4 py-2 rounded-lg text-sm font-semibold transition-all duration-200"
          style={{
            background: 'linear-gradient(135deg, rgba(129,116,201,0.12), rgba(91,205,132,0.08))',
            border: '1px solid rgba(91,205,132,0.25)',
            color: '#93DEAE',
          }}
          onMouseEnter={e => {
            const t = e.currentTarget as HTMLElement
            t.style.background = 'linear-gradient(135deg, rgba(157,124,255,0.18), rgba(91,205,132,0.14))'
            t.style.borderColor = 'rgba(91,205,132,0.45)'
            t.style.color = '#5BCD84'
          }}
          onMouseLeave={e => {
            const t = e.currentTarget as HTMLElement
            t.style.background = 'linear-gradient(135deg, rgba(129,116,201,0.12), rgba(91,205,132,0.08))'
            t.style.borderColor = 'rgba(91,205,132,0.25)'
            t.style.color = '#93DEAE'
          }}
        >
          Get started
        </a>
      </div>
    </header>
  )
}
