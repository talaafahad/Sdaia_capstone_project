import { create } from 'zustand';

import type { CaseState, Conflict } from '../types/caseState';
import type { DocumentationArtifacts } from '../types/artifacts';
import type { AgentId, AgentRuntime, CaseEvent, CaseInterrupt } from '../types/events';
import { AGENT_ROSTER } from '../types/events';
import { emptyCaseState, mockArtifacts, mockCaseState } from '../mocks/mockCase';

export type CasePhase =
  | 'intake'
  | 'running'
  | 'awaiting_conflict'
  | 'awaiting_approval'
  | 'complete'
  | 'failed';

export interface UploadedDocument {
  filename: string;
  size_bytes: number;
  kind: 'pdf' | 'txt';
  /**
   * Phase A stands in for PyMuPDF text extraction. This value is what feeds
   * `CaseState.area_sqm_from_document`, which is the field the Verifier's
   * discrepancy check reads (implementation plan section 13, final note).
   */
  extracted_area_sqm: number | null;
  extraction_note: string;
}

const initialAgents = (): Record<AgentId, AgentRuntime> =>
  Object.fromEntries(
    AGENT_ROSTER.map((a) => [a.id, { status: 'pending' } as AgentRuntime])
  ) as Record<AgentId, AgentRuntime>;

/**
 * `CaseState.decision_log` is `list[str]` on the Python side and carries no
 * timestamps. Rather than bend the schema mirror, the arrival time of each
 * entry is kept alongside it here so the trace can be rendered timestamped
 * (implementation plan section 5: "timestamped agent decision trace").
 */
export interface TraceEntry {
  text: string;
  at: string;
}

interface CaseStore {
  phase: CasePhase;
  caseState: CaseState;
  trace: TraceEntry[];
  agents: Record<AgentId, AgentRuntime>;
  artifacts: DocumentationArtifacts | null;
  activeInterrupt: CaseInterrupt | null;
  uploadedDocument: UploadedDocument | null;
  connected: boolean;
  streamError: string | null;

  setConnected: (connected: boolean) => void;
  setUploadedDocument: (doc: UploadedDocument | null) => void;
  beginCase: (caseId: string, goal: string) => void;
  applyEvent: (event: CaseEvent) => void;
  clearInterrupt: () => void;
  loadFixture: () => void;
  reset: () => void;
}

export const useCaseStore = create<CaseStore>((set) => ({
  phase: 'intake',
  caseState: emptyCaseState(),
  trace: [],
  agents: initialAgents(),
  artifacts: null,
  activeInterrupt: null,
  uploadedDocument: null,
  connected: false,
  streamError: null,

  setConnected: (connected) => set({ connected }),

  setUploadedDocument: (uploadedDocument) => set({ uploadedDocument }),

  beginCase: (caseId, goal) =>
    set({
      phase: 'running',
      caseState: { ...emptyCaseState(), case_id: caseId, goal },
      trace: [],
      agents: initialAgents(),
      artifacts: null,
      activeInterrupt: null,
      streamError: null,
    }),

  applyEvent: (event) =>
    set((s) => {
      switch (event.type) {
        case 'agent_status':
          return {
            agents: {
              ...s.agents,
              [event.agent]: {
                status: event.status,
                message: event.message,
                started_at:
                  event.status === 'active' ? event.at : s.agents[event.agent]?.started_at,
                finished_at: event.status === 'complete' ? event.at : undefined,
              },
            },
          };

        case 'state_patch':
          // Merge, never overwrite — mirrors the LangGraph reducer contract in
          // implementation plan section 1.
          return { caseState: { ...s.caseState, ...event.patch } };

        case 'decision':
          return {
            caseState: {
              ...s.caseState,
              decision_log: [...s.caseState.decision_log, event.entry],
            },
            trace: [...s.trace, { text: event.entry, at: event.at }],
          };

        case 'interrupt':
          return {
            activeInterrupt: event.interrupt,
            phase:
              event.interrupt.kind === 'conflict_resolution'
                ? 'awaiting_conflict'
                : 'awaiting_approval',
          };

        case 'artifacts_ready':
          return { artifacts: event.artifacts };

        case 'done':
          return { phase: 'complete' as CasePhase, activeInterrupt: null };

        case 'error':
          return { phase: 'failed' as CasePhase, streamError: event.message };

        default:
          return {};
      }
    }),

  clearInterrupt: () => set({ activeInterrupt: null, phase: 'running' }),

  /**
   * Renders every component straight from the hand-written fixture, with no
   * server involved. This is the Phase-A safety net from the handoff doc's
   * checkpoint note: the UI stays demoable even if the mock server is down.
   */
  loadFixture: () => {
    const caseState = mockCaseState();
    const base = Date.now() - caseState.decision_log.length * 1400;
    set({
      phase: 'complete',
      caseState,
      trace: caseState.decision_log.map((text, i) => ({
        text,
        at: new Date(base + i * 1400).toISOString(),
      })),
      agents: Object.fromEntries(
        AGENT_ROSTER.map((a) => [a.id, { status: 'complete' } as AgentRuntime])
      ) as Record<AgentId, AgentRuntime>,
      artifacts: mockArtifacts(),
      activeInterrupt: null,
      connected: false,
      streamError: null,
    });
  },

  reset: () =>
    set({
      phase: 'intake',
      caseState: emptyCaseState(),
      trace: [],
      agents: initialAgents(),
      artifacts: null,
      activeInterrupt: null,
      uploadedDocument: null,
      streamError: null,
    }),
}));

/** True while an unresolved conflict freezes readiness (implementation plan section 2.5, rule 4). */
export const selectReadinessFrozen = (s: {
  caseState: CaseState;
}): boolean => s.caseState.conflicts.some((c: Conflict) => c.status === 'open');
