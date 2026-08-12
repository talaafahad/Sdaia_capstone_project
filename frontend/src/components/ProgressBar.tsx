/**
 * Case readiness — `CaseState.readiness_pct`.
 *
 * The fill is the one place a saturated accent earns visual priority
 * (implementation plan section 12), so it uses the lavender base→deep gradient.
 * While a conflict is open the bar switches to the alert colour and says so:
 * implementation plan section 2.5 rule 4 forbids readiness increasing until the
 * discrepancy is resolved by a human, and that freeze should be visible.
 */

import styles from './ProgressBar.module.css';

interface ProgressBarProps {
  value: number;
  frozen: boolean;
  /** Fields from section 13 left blank, which cap achievable readiness. */
  limitingFactors?: string[];
}

export function ProgressBar({ value, frozen, limitingFactors = [] }: ProgressBarProps) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));

  return (
    <section className={styles.wrap} aria-label="Case readiness">
      <header className={styles.head}>
        <h2 className={styles.title}>Readiness</h2>
        <span className={`${styles.value} ${frozen ? styles.valueFrozen : ''}`}>{pct}%</span>
      </header>

      <div
        className={styles.track}
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuetext={frozen ? `${pct} percent, frozen pending conflict resolution` : `${pct} percent`}
      >
        <div
          className={`${styles.fill} ${frozen ? styles.fillFrozen : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {frozen && (
        <p className={styles.frozenNote}>
          <span className={styles.frozenDot} aria-hidden="true" />
          Frozen — readiness cannot increase while a document discrepancy is unresolved.
        </p>
      )}

      {!frozen && limitingFactors.length > 0 && (
        <p className={styles.limitNote}>
          Readiness-limiting: {limitingFactors.join(' · ')}
        </p>
      )}
    </section>
  );
}
