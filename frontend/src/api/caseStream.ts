/**
 * Real backend client. No mocked data anywhere in this file.
 *
 *   POST /api/documents/extract   lease -> area_sqm_from_document
 *   POST /api/cases               start a case  -> { case_id }
 *   GET  /api/cases/{id}/stream   SSE live updates
 *   POST /api/cases/{id}/resume   release BOTH interrupt gates
 *
 * The backend runs on :8000 with CORS open for :5173.
 */

import type { CaseEvent, IntakePayload, UploadedDocument } from '../types/caseState'

const BASE_URL: string =
  (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_BASE_URL ??
  'http://localhost:8000'

export const apiBaseUrl = BASE_URL

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json())?.detail ?? ''
    } catch {
      /* body was not JSON */
    }
    throw new Error(`${res.status} ${res.statusText}${detail ? ` — ${detail}` : ''}`)
  }
  return (await res.json()) as T
}

/** Extract the premises area from a lease before the case starts. */
export async function extractDocument(file: File): Promise<UploadedDocument> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE_URL}/api/documents/extract`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(`Document extraction failed: ${res.status}`)
  return (await res.json()) as UploadedDocument
}

export function createCase(
  intake: IntakePayload,
  document: UploadedDocument | null,
): Promise<{ case_id: string }> {
  return postJson<{ case_id: string }>('/api/cases', { intake, document })
}

export interface ConflictResume {
  kind: 'conflict_resolution'
  conflict_id: string
  accepted: 'stated' | 'document'
  note?: string
}

export interface ApprovalResume {
  kind: 'approval_gate'
  decision: 'approve' | 'reject'
  note?: string
}

/** Releases a LangGraph interrupt() gate so the run continues. */
export function resumeCase(
  caseId: string,
  payload: ConflictResume | ApprovalResume,
): Promise<{ ok: true }> {
  return postJson<{ ok: true }>(`/api/cases/${caseId}/resume`, payload)
}

export interface StreamHandlers {
  onEvent: (event: CaseEvent) => void
  onOpen?: () => void
  onError?: (message: string) => void
}

export interface StreamHandle {
  close: () => void
}

export function openCaseStream(caseId: string, handlers: StreamHandlers): StreamHandle {
  const source = new EventSource(`${BASE_URL}/api/cases/${caseId}/stream`)
  let closed = false

  source.onopen = () => handlers.onOpen?.()

  source.onmessage = (message: MessageEvent<string>) => {
    // The server also sends ": keepalive" comment frames during long model
    // calls. EventSource swallows comments, so nothing arrives here for those —
    // they exist purely to stop proxies treating the connection as dead.
    let event: CaseEvent
    try {
      event = JSON.parse(message.data) as CaseEvent
    } catch {
      handlers.onError?.('Received a malformed event from the stream.')
      return
    }
    handlers.onEvent(event)
    if (event.type === 'done' || event.type === 'error') {
      closed = true
      source.close()
    }
  }

  source.onerror = () => {
    // EventSource also fires onerror on a normal close; only surface real faults.
    if (closed || source.readyState === EventSource.CLOSED) return
    handlers.onError?.(
      `Lost connection to ${BASE_URL}. Is the backend running on port 8000?`,
    )
    source.close()
  }

  return {
    close: () => {
      closed = true
      source.close()
    },
  }
}
