/**
 * SSE client for the case run.
 *
 * Phase A: talks to `mock-server/index.mjs`, which replays a canned agent
 * sequence and honours the two human-in-the-loop gates.
 * Phase C: point VITE_API_BASE_URL at the real FastAPI service. The endpoint
 * shapes below are the contract the backend has to satisfy — nothing else in
 * the frontend touches the network.
 */

import type { CaseEvent } from '../types/events';
import type { IntakeValues } from '../types/intake';
import type { UploadedDocument } from '../store/caseStore';

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export interface CreateCasePayload {
  intake: IntakeValues;
  document: UploadedDocument | null;
}

export interface ConflictResumePayload {
  kind: 'conflict_resolution';
  conflict_id: string;
  accepted: 'stated' | 'document';
  note?: string;
}

export interface ApprovalResumePayload {
  kind: 'approval_gate';
  decision: 'approve' | 'reject';
  note?: string;
}

export type ResumePayload = ConflictResumePayload | ApprovalResumePayload;

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} — ${path}`);
  }
  return (await res.json()) as T;
}

/** Creates the case and returns its id; the graph does not start until the stream is opened. */
export function createCase(payload: CreateCasePayload): Promise<{ case_id: string }> {
  return postJson<{ case_id: string }>('/api/cases', payload);
}

/** Releases a LangGraph `interrupt()` gate so the run continues. */
export function resumeCase(caseId: string, payload: ResumePayload): Promise<{ ok: true }> {
  return postJson<{ ok: true }>(`/api/cases/${caseId}/resume`, payload);
}

export interface StreamHandlers {
  onEvent: (event: CaseEvent) => void;
  onOpen?: () => void;
  onError?: (message: string) => void;
}

export interface StreamHandle {
  close: () => void;
}

export function openCaseStream(caseId: string, handlers: StreamHandlers): StreamHandle {
  const source = new EventSource(`${BASE_URL}/api/cases/${caseId}/stream`);
  let closed = false;

  source.onopen = () => handlers.onOpen?.();

  source.onmessage = (message) => {
    let event: CaseEvent;
    try {
      event = JSON.parse(message.data) as CaseEvent;
    } catch {
      handlers.onError?.('Received a malformed event from the stream.');
      return;
    }
    handlers.onEvent(event);
    if (event.type === 'done' || event.type === 'error') {
      closed = true;
      source.close();
    }
  };

  source.onerror = () => {
    // EventSource fires onerror on normal close too; only surface real failures.
    if (closed || source.readyState === EventSource.CLOSED) return;
    handlers.onError?.(
      `Lost connection to the case stream at ${BASE_URL}. Is the mock server running (npm run mock)?`
    );
    source.close();
  };

  return {
    close: () => {
      closed = true;
      source.close();
    },
  };
}
