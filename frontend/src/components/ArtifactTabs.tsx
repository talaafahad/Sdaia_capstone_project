/**
 * The six Documentation-agent artifacts, in the order section 2.6 specifies:
 * Journey, Checklist, Evidence Report, Fee Estimate, Application Packet Draft,
 * Decision Log.
 *
 * Two rules from section 2.6 are enforced in the rendering, not just the data:
 *  - any fee line item with `is_official: false` carries the mandatory
 *    "AI ESTIMATE — not an official fee." label;
 *  - rejected evidence appears in the Evidence Report as rejected, and never
 *    contributes to the checklist or the packet.
 */

import { useState } from 'react';

import type { DocumentationArtifacts } from '../types/artifacts';
import styles from './ArtifactTabs.module.css';

interface ArtifactTabsProps {
  artifacts: DocumentationArtifacts;
}

const TABS = [
  { id: 'journey', label: 'Journey' },
  { id: 'checklist', label: 'Checklist' },
  { id: 'evidence', label: 'Evidence Report' },
  { id: 'fees', label: 'Fee Estimate' },
  { id: 'packet', label: 'Application Packet' },
  { id: 'log', label: 'Decision Log' },
] as const;

type TabId = (typeof TABS)[number]['id'];

const sar = (n: number) =>
  new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(n);

export function ArtifactTabs({ artifacts }: ArtifactTabsProps) {
  const [tab, setTab] = useState<TabId>('journey');

  return (
    <section className={styles.wrap} aria-label="Case artifacts">
      <div className={styles.tabs} role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            className={`${styles.tab} ${tab === t.id ? styles.tabOn : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className={styles.panel} role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === 'journey' && (
          <ol className={styles.journey}>
            {artifacts.journey.map((step) => (
              <li key={step.order} className={styles.step}>
                <span className={styles.stepNum}>{step.order}</span>
                <div className={styles.stepBody}>
                  <div className={styles.stepHead}>
                    <h3 className={styles.stepTitle}>{step.title}</h3>
                    <span
                      className={`${styles.agency} ${
                        step.agency === 'Not verified' ? styles.agencyUnverified : ''
                      }`}
                    >
                      {step.agency}
                    </span>
                  </div>
                  <p className={styles.stepDesc}>{step.description}</p>
                </div>
              </li>
            ))}
          </ol>
        )}

        {tab === 'checklist' && (
          <ul className={styles.checklist}>
            {artifacts.checklist.map((item) => (
              <li key={item.name} className={styles.checkItem}>
                <span className={`${styles.statusDot} ${styles[item.status]}`} aria-hidden="true" />
                <div>
                  <span className={styles.checkName}>{item.name}</span>
                  <span className={`${styles.statusLabel} ${styles[`label_${item.status}`]}`}>
                    {item.status}
                  </span>
                  {item.note && <p className={styles.checkNote}>{item.note}</p>}
                </div>
              </li>
            ))}
          </ul>
        )}

        {tab === 'evidence' && (
          <div className={styles.tableScroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Claim</th>
                  <th>Source</th>
                  <th>Confidence</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {artifacts.evidence_report.map((row, i) => (
                  <tr key={i} className={row.verdict === 'rejected' ? styles.rowRejected : ''}>
                    <td>
                      <span className={styles.claimText}>{row.claim}</span>
                      {row.reason && <span className={styles.reason}>{row.reason}</span>}
                    </td>
                    <td>
                      <span className={styles.srcEntity}>{row.source_entity}</span>
                      {row.source_url ? (
                        <a
                          className={styles.srcUrl}
                          href={row.source_url}
                          target="_blank"
                          rel="noreferrer noopener"
                        >
                          {row.source_url}
                        </a>
                      ) : (
                        <span className={styles.srcNone}>no URL</span>
                      )}
                    </td>
                    <td>
                      <span className={`${styles.conf} ${styles[`conf${row.confidence}`]}`}>
                        {row.confidence}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`${styles.verdict} ${
                          row.verdict === 'accepted' ? styles.accepted : styles.rejected
                        }`}
                      >
                        {row.verdict}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === 'fees' && (
          <div className={styles.fees}>
            <ul className={styles.feeList}>
              {artifacts.fee_estimate.line_items.map((item, i) => (
                <li key={i} className={styles.feeItem}>
                  <div className={styles.feeMain}>
                    <span className={styles.feeLabel}>{item.label}</span>
                    <span className={styles.feeAmount}>
                      {item.amount_sar > 0 ? `SAR ${sar(item.amount_sar)}` : '—'}
                    </span>
                  </div>
                  {item.is_official ? (
                    <span className={styles.officialTag}>
                      Official fee
                      {item.source && (
                        <a href={item.source} target="_blank" rel="noreferrer noopener">
                          source
                        </a>
                      )}
                    </span>
                  ) : (
                    <span className={styles.estimateTag}>AI ESTIMATE — not an official fee.</span>
                  )}
                  {!item.is_official && item.source && (
                    <p className={styles.feeNote}>{item.source}</p>
                  )}
                </li>
              ))}
            </ul>

            <div className={styles.feeTotals}>
              <div>
                <span className={styles.totalLabel}>Official fees (sourced)</span>
                <span className={styles.totalValue}>
                  SAR {sar(artifacts.fee_estimate.official_total_sar)}
                </span>
              </div>
              <div>
                <span className={styles.totalLabel}>Estimated costs (AI ESTIMATE)</span>
                <span className={`${styles.totalValue} ${styles.totalEstimate}`}>
                  SAR {sar(artifacts.fee_estimate.estimated_total_sar)}
                </span>
              </div>
            </div>
          </div>
        )}

        {tab === 'packet' && (
          <div className={styles.packet}>
            <div className={styles.packetHead}>
              <h3 className={styles.packetTitle}>{artifacts.application_packet.target_service}</h3>
              <span className={styles.packetAgency}>{artifacts.application_packet.target_agency}</span>
            </div>

            <dl className={styles.packetFields}>
              {artifacts.application_packet.fields.map((f) => (
                <div key={f.label} className={styles.packetField}>
                  <dt>{f.label}</dt>
                  <dd>
                    <span className={styles.packetValue}>{f.value}</span>
                    <span className={styles.packetSource}>{f.source}</span>
                  </dd>
                </div>
              ))}
            </dl>

            <p className={styles.disclaimer}>{artifacts.application_packet.disclaimer}</p>
          </div>
        )}

        {tab === 'log' && (
          <ol className={styles.log}>
            {artifacts.decision_log.map((entry, i) => (
              <li key={i}>{entry}</li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
