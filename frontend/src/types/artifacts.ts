/**
 * The six artifacts produced by the Documentation agent
 * (implementation plan section 2.6): Journey, Checklist, Evidence Report,
 * Fee Estimate, Application Packet Draft, Decision Log — in that order.
 *
 * Section 2.6 says only "structured JSON the frontend will render" without
 * pinning the keys, so this shape is the frontend's proposal. Confirm it when
 * `agents/documentation.py` is written in Phase B.
 */

import type { Confidence, RequirementStatus } from './caseState';

export interface JourneyStep {
  order: number;
  title: string;
  agency: string;
  description: string;
  /** null when not derivable from CaseState — section 2.6 forbids inventing dates. */
  estimated_duration?: string | null;
}

export interface ChecklistEntry {
  name: string;
  status: RequirementStatus;
  note?: string;
}

export interface EvidenceReportRow {
  claim: string;
  source_entity: string;
  source_url: string;
  retrieved_at: string;
  confidence: Confidence;
  verdict: 'accepted' | 'rejected';
  /** Populated for rejected rows — why the Verifier stripped the claim. */
  reason?: string;
}

export interface FeeLineItem {
  label: string;
  amount_sar: number;
  /**
   * false renders the mandatory "AI ESTIMATE — not an official fee." label
   * required by implementation plan section 2.6 rule 2.
   */
  is_official: boolean;
  source?: string;
}

export interface PacketField {
  label: string;
  value: string;
  source: string;
}

export interface DocumentationArtifacts {
  journey: JourneyStep[];
  checklist: ChecklistEntry[];
  evidence_report: EvidenceReportRow[];
  fee_estimate: {
    line_items: FeeLineItem[];
    official_total_sar: number;
    estimated_total_sar: number;
  };
  application_packet: {
    target_service: string;
    target_agency: string;
    fields: PacketField[];
    /** Never claim approval — implementation plan section 2.3 rule 3. */
    disclaimer: string;
  };
  decision_log: string[];
}
