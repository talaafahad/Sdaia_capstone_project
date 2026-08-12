/**
 * Human-in-the-loop approve/reject gate.
 *
 * Corresponds to the second LangGraph `interrupt()` in implementation plan
 * section 3 — the graph is paused here, not polling. Approving moves
 * `approval_stage` to "proposal_approved" and releases the Documentation agent.
 *
 * Neutral off-white/charcoal palette only (section 12) — decision-critical.
 */

import { useState } from 'react';

import type { ApprovalInterrupt } from '../types/events';
import styles from './ApprovalGate.module.css';

interface ApprovalGateProps {
  gate: ApprovalInterrupt;
  onDecide: (decision: 'approve' | 'reject', note?: string) => void;
  busy?: boolean;
}

export function ApprovalGate({ gate, onDecide, busy = false }: ApprovalGateProps) {
  const [note, setNote] = useState('');

  return (
    <div className={styles.backdrop} role="presentation">
      <div
        className={styles.dialog}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="approval-title"
        aria-describedby="approval-desc"
      >
        <span className={styles.flag}>Awaiting your approval</span>

        <h2 className={styles.title} id="approval-title">
          Review the proposal before the packet is generated
        </h2>

        <p className={styles.desc} id="approval-desc">
          {gate.summary}
        </p>

        <dl className={styles.stats}>
          <div className={styles.stat}>
            <dt>Requirements</dt>
            <dd>{gate.requirement_count}</dd>
          </div>
          <div className={styles.stat}>
            <dt>Evidence accepted</dt>
            <dd className={styles.ok}>{gate.accepted_evidence_count}</dd>
          </div>
          <div className={styles.stat}>
            <dt>Evidence rejected</dt>
            <dd className={styles.alert}>{gate.rejected_evidence_count}</dd>
          </div>
        </dl>

        <p className={styles.caveat}>
          Approving generates a draft application packet. It is not a submission and confers no
          approval from any agency.
        </p>

        <label className={styles.noteLabel} htmlFor="approval-note">
          Note <span className={styles.noteOptional}>(optional — recorded in the decision log)</span>
        </label>
        <textarea
          id="approval-note"
          className={`field-control ${styles.note}`}
          rows={2}
          value={note}
          disabled={busy}
          placeholder="e.g. Proceed, but I will confirm the GOSI requirement separately."
          onChange={(e) => setNote(e.target.value)}
        />

        <div className={styles.actions}>
          <button
            type="button"
            className={styles.reject}
            disabled={busy}
            onClick={() => onDecide('reject', note.trim() || undefined)}
          >
            Reject
          </button>
          <button
            type="button"
            className={styles.approve}
            disabled={busy}
            onClick={() => onDecide('approve', note.trim() || undefined)}
          >
            {busy ? 'Resuming…' : 'Approve and generate'}
          </button>
        </div>
      </div>
    </div>
  );
}
