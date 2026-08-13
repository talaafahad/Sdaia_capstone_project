import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'

// Root-level boundary. A throw anywhere in the tree used to unmount the whole
// root, leaving a blank dark screen with no controls at all — no way to close,
// go back, or even see what failed. This guarantees the user always gets an
// error they can read and a way to recover.
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary
      label="Bosalah"
      fallback={(error, reset) => (
        <div className="min-h-screen flex items-center justify-center p-6" style={{ background: '#10122B' }}>
          <div
            className="max-w-lg w-full rounded-2xl p-6"
            style={{ background: 'rgba(23,27,61,0.9)', border: '1px solid rgba(192,86,75,0.35)' }}
          >
            <h1 className="text-lg font-bold mb-2" style={{ color: '#F1F1F1' }}>
              Something broke while rendering
            </h1>
            <p className="text-sm mb-3" style={{ color: '#B0B0B0' }}>
              This is a display fault in the interface. Your case is unaffected and
              nothing was submitted to any agency.
            </p>
            <code className="block text-xs break-words mb-4" style={{ color: '#C0564B' }}>
              {error.message}
            </code>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={reset}
                className="px-4 py-2 rounded-lg text-sm font-semibold"
                style={{ background: 'linear-gradient(135deg,#8174C9,#9D7CFF)', color: '#10122B' }}
              >
                Try again
              </button>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="px-4 py-2 rounded-lg text-sm font-medium"
                style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)', color: '#D4D4D4' }}
              >
                Reload the page
              </button>
            </div>
          </div>
        </div>
      )}
    >
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)
