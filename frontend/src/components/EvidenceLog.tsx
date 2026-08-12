/**
 * Timestamped agent decision trace, plus the raw evidence the agents cited.
 *
 * The Evidence view deliberately shows rejected items too — an entry with
 * `has_explicit_url: false` is struck through and labelled, because the point
 * the Verifier makes (implementation plan section 2.5) is only legible if you
 * can see what it threw away, not just what survived.
 */

import { useState } from 'react';

import type { Evidence } from '../types/caseState';
import type { TraceEntry } from '../store/caseStore';
import styles from './EvidenceLog.module.css';

interface EvidenceLogProps {
  trace: TraceEntry[];
  evidence: Evidence[];
}

type View = 'trace' | 'evidence';

const time = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? '--:--:--'
    : d.toLocaleTimeString(undefined, { hour12: false });
};

export function EvidenceLog({ trace, evidence }: EvidenceLogProps) {
  const [view, setView] = useState<View>('trace');
  const rejected = evidence.filter((e) => !e.has_explicit_url).length;

  return (
    <section className={styles.wrap} aria-label="Evidence and decision log">
      <header className={styles.head}>
        <div className={styles.tabs} role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={view === 'trace'}
            className={`${styles.tab} ${view === 'trace' ? styles.tabOn : ''}`}
            onClick={() => setView('trace')}
          >
            Decision trace <span className={styles.count}>{trace.length}</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === 'evidence'}
            className={`${styles.tab} ${view === 'evidence' ? styles.tabOn : ''}`}
            onClick={() => setView('evidence')}
          >
            Evidence <span className={styles.count}>{evidence.length}</span>
          </button>
        </div>
        {rejected > 0 && (
          <span className={styles.rejectedPill}>
            {rejected} rejected by Verifier
          </span>
        )}
      </header>

      <div className={styles.body}>
        {view === 'trace' && (
          trace.length === 0 ? (
            <p className={styles.empty}>No decisions recorded yet.</p>
          ) : (
            <ol className={styles.trace}>
              {trace.map((entry, i) => (
                <li key={`${entry.at}-${i}`} className={styles.traceItem}>
                  <time className={styles.time} dateTime={entry.at}>
                    {time(entry.at)}
                  </time>
                  <span className={styles.traceText}>{entry.text}</span>
                </li>
              ))}
            </ol>
          )
        )}

        {view === 'evidence' && (
          evidence.length === 0 ? (
            <p className={styles.empty}>No evidence retrieved yet.</p>
          ) : (
            <ul className={styles.evidence}>
              {evidence.map((e, i) => (
                <li
                  key={`${e.source_url}-${i}`}
                  className={`${styles.item} ${e.has_explicit_url ? '' : styles.itemRejected}`}
                >
                  <div className={styles.itemHead}>
                    <span className={styles.entity}>{e.source_entity}</span>
                    <span className={`${styles.conf} ${styles[`conf${e.confidence}`]}`}>
                      {e.confidence}
                    </span>
                    {!e.has_explicit_url && <span className={styles.rejectTag}>REJECTED</span>}
                  </div>

                  <p className={styles.claim}>{e.claim}</p>

                  <div className={styles.itemFoot}>
                    {e.source_url ? (
                      <a
                        className={styles.url}
                        href={e.source_url}
                        target="_blank"
                        rel="noreferrer noopener"
                      >
                        {e.source_url}
                      </a>
                    ) : (
                      <span className={styles.noUrl}>no explicit source URL</span>
                    )}
                    <time className={styles.retrieved} dateTime={e.retrieved_at}>
                      {time(e.retrieved_at)}
                    </time>
                  </div>
                </li>
              ))}
            </ul>
          )
        )}
      </div>
    </section>
  );
}
