import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  /** Shown above the error text so the user knows what failed. */
  label: string
  /** Rendered instead of the default panel, if supplied. */
  fallback?: (error: Error, reset: () => void) => ReactNode
  onError?: (error: Error, info: ErrorInfo) => void
}

interface State {
  error: Error | null
}

/**
 * Catches render errors so one broken subtree cannot unmount the whole app.
 *
 * Without this, a throw inside a modal body took React's entire root down and
 * left a blank dark screen with no controls — the user could not close, go
 * back, or even see what happened. A boundary keeps the surrounding chrome
 * (and therefore the close button) alive, and shows the actual error instead
 * of hiding it.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep it in the console too — the on-screen panel is deliberately terse.
    console.error(`[${this.props.label}] render failed:`, error, info.componentStack)
    this.props.onError?.(error, info)
  }

  reset = () => this.setState({ error: null })

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    if (this.props.fallback) return this.props.fallback(error, this.reset)

    return (
      <div
        className="rounded-xl px-4 py-3 text-xs"
        role="alert"
        style={{
          background: 'rgba(192,86,75,0.08)',
          border: '1px solid rgba(192,86,75,0.35)',
          color: '#E39A92',
        }}
      >
        <p className="font-semibold mb-1">{this.props.label} could not be displayed.</p>
        <p className="mb-2" style={{ color: '#B0B0B0' }}>
          This is a display fault, not a change to your case — nothing was submitted.
        </p>
        <code className="block text-[11px] break-words" style={{ color: '#C0564B' }}>
          {error.message}
        </code>
        <button
          type="button"
          onClick={this.reset}
          className="mt-2.5 px-3 py-1.5 rounded-lg text-xs font-medium"
          style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)', color: '#D4D4D4' }}
        >
          Try again
        </button>
      </div>
    )
  }
}
