/**
 * The SSE wire protocol between FastAPI and the browser.
 *
 * These types are NOT part of the Pydantic `CaseState` mirror — they describe
 * the transport. The shape follows implementation plan section 1's rule that
 * "every LangGraph node reads this and returns a **partial update**": the
 * stream carries partial patches, never whole-state overwrites, so one late
 * event cannot erase another node's progress.
 *
 * Phase A: served by `mock-server/index.mjs`.
 * Phase C: served by the real FastAPI streaming endpoint. Only the URL changes.
 */

import type { CaseState, Conflict } from './caseState';
import type { DocumentationArtifacts } from './artifacts';

/** Node names taken from the graph in implementation plan section 3. */
export type AgentId =
  | 'intake_planner'
  | 'regulation_router'
  | 'municipal_location'
  | 'tax_financial'
  | 'verifier'
  | 'documentation';

export type AgentRunStatus = 'pending' | 'active' | 'complete' | 'blocked';

export interface AgentDescriptor {
  id: AgentId;
  label: string;
  /** Shown in the roster so the A2A/deterministic split is visible in the demo. */
  kind: 'llm' | 'deterministic' | 'a2a-remote';
  subtitle: string;
}

export interface AgentRuntime {
  status: AgentRunStatus;
  message?: string;
  started_at?: string;
  finished_at?: string;
}

export type InterruptKind = 'conflict_resolution' | 'approval_gate';

export interface ConflictInterrupt {
  kind: 'conflict_resolution';
  conflict: Conflict;
}

export interface ApprovalInterrupt {
  kind: 'approval_gate';
  summary: string;
  requirement_count: number;
  accepted_evidence_count: number;
  rejected_evidence_count: number;
}

export type CaseInterrupt = ConflictInterrupt | ApprovalInterrupt;

export type CaseEvent =
  | { type: 'agent_status'; agent: AgentId; status: AgentRunStatus; message?: string; at: string }
  /** Partial CaseState update, merged rather than replacing. */
  | { type: 'state_patch'; patch: Partial<CaseState>; at: string }
  | { type: 'decision'; entry: string; at: string }
  /** Graph paused on a LangGraph `interrupt()` — implementation plan section 3. */
  | { type: 'interrupt'; interrupt: CaseInterrupt; at: string }
  | { type: 'artifacts_ready'; artifacts: DocumentationArtifacts; at: string }
  | { type: 'done'; at: string }
  | { type: 'error'; message: string; at: string };

/** Display metadata for the roster sidebar. Order matches the graph's execution order. */
export const AGENT_ROSTER: AgentDescriptor[] = [
  {
    id: 'intake_planner',
    label: 'Intake & Planner',
    kind: 'llm',
    subtitle: 'Extracts fields, picks branch',
  },
  {
    id: 'regulation_router',
    label: 'Regulation & Service Router',
    kind: 'llm',
    subtitle: 'Allowlisted retrieval only',
  },
  {
    id: 'municipal_location',
    label: 'Municipal & Location',
    kind: 'a2a-remote',
    subtitle: 'A2A service · Balady + OSM',
  },
  {
    id: 'tax_financial',
    label: 'Tax / Financial',
    kind: 'deterministic',
    subtitle: 'No LLM in the decision path',
  },
  {
    id: 'verifier',
    label: 'Verifier',
    kind: 'llm',
    subtitle: 'Citation audit + discrepancy check',
  },
  {
    id: 'documentation',
    label: 'Documentation',
    kind: 'llm',
    subtitle: 'Assembles the six artifacts',
  },
];
