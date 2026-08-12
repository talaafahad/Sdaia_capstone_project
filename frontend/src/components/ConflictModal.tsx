/**
 * The lease-area discrepancy resolution UI — the demo centrepiece.
 *
 * Mirrors implementation plan section 2.5 rule 4: when the stated value and the
 * document value differ, the system does not silently pick one. Both values are
 * shown with their sources and no option is preselected; the case cannot
 * proceed until a human chooses.
 *
 * Deliberately on the neutral off-white/charcoal palette rather than the sage/
 * lavender theme (section 12) — this is a decision-critical moment and should
 * not compete visually with decorative branding.
 *
 * Phase C: this is wired to the real LangGraph `interrupt()` for conflict
 * resolution. The props do not change.
 */

import { useState } from 'react';

import type { Conflict } from '../types/caseState';
import styles from './ConflictModal.module.css';

interface ConflictModalProps {
  conflict: Conflict;
  onResolve: (accepted: 'stated' | 'document', note?: string) => void;
  busy?: boolean;
}

export function ConflictModal({ conflict, onResolve, busy = false }: ConflictModalProps) {
  const [choice, setChoice] = useState<'stated' | 'document' | null>(null);
  const [note, setNote] = useState('');

  return (
    <div className={styles.backdrop} role="presentation">
      <div
        className={styles.dialog}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="conflict-title"
        aria-describedby="conflict-desc"
      >
        <span className={styles.flag}>Discrepancy detected — Verifier</span>

        <h2 className={styles.title} id="conflict-title">
          {conflict.field_label} does not match your document
        </h2>

        <p className={styles.desc} id="conflict-desc">
          The value you stated and the value read from your document disagree. GovFlow will not
          choose for you — pick which one is authoritative. Readiness stays frozen until you do.
        </p>

        <div className={styles.options} role="radiogroup" aria-label="Which value is correct?">
          <ValueCard
            selected={choice === 'stated'}
            onSelect={() => setChoice('stated')}
            heading="You stated"
            value={conflict.stated_value}
            source={conflict.stated_source}
            disabled={busy}
          />
          <ValueCard
            selected={choice === 'document'}
            onSelect={() => setChoice('document')}
            heading="Your document says"
            value={conflict.document_value}
            source={conflict.document_source}
            disabled={busy}
          />
        </div>

        <label className={styles.noteLabel} htmlFor="conflict-note">
          Note <span className={styles.noteOptional}>(optional — recorded in the decision log)</span>
        </label>
        <textarea
          id="conflict-note"
          className={`field-control ${styles.note}`}
          rows={2}
          value={note}
          disabled={busy}
          placeholder="e.g. The lease covers the ground floor only; the mezzanine is separate."
          onChange={(e) => setNote(e.target.value)}
        />

        <div className={styles.actions}>
          <p className={styles.hint}>
            {choice === null
              ? 'Select a value to continue.'
              : `Proceeding with the ${choice} value.`}
          </p>
          <button
            type="button"
            className={styles.confirm}
            disabled={choice === null || busy}
            onClick={() => choice && onResolve(choice, note.trim() || undefined)}
          >
            {busy ? 'Resuming…' : 'Confirm and continue'}
          </button>
        </div>
      </div>
    </div>
  );
}

function ValueCard({
  selected,
  onSelect,
  heading,
  value,
  source,
  disabled,
}: {
  selected: boolean;
  onSelect: () => void;
  heading: string;
  value: number | string;
  source: string;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      className={`${styles.card} ${selected ? styles.cardOn : ''}`}
      onClick={onSelect}
      disabled={disabled}
    >
      <span className={styles.cardHeading}>{heading}</span>
      <span className={styles.cardValue}>{value}</span>
      <span className={styles.cardSource}>{source}</span>
    </button>
  );
}
