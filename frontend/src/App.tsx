/**
 * GovFlow KSA — app shell.
 *
 * Phase A: everything below runs against the Express mock server in
 * `mock-server/`, or entirely offline via "Preview with mock data". No backend
 * is involved. Phase C replaces the event source only — the components, store
 * and types are already shaped for real agent output.
 */

import { useEffect, useRef, useState } from 'react';

import { AgentRoster } from './components/AgentRoster';
import { ApprovalGate } from './components/ApprovalGate';
import { ArtifactTabs } from './components/ArtifactTabs';
import { ConflictModal } from './components/ConflictModal';
import { EvidenceLog } from './components/EvidenceLog';
import { GoalInput } from './components/GoalInput';
import { ProgressBar } from './components/ProgressBar';
import { createCase, openCaseStream, resumeCase } from './api/caseStream';
import type { StreamHandle } from './api/caseStream';
import { selectReadinessFrozen, useCaseStore } from './store/caseStore';
import type { UploadedDocument } from './store/caseStore';
import type { IntakeValues } from './types/intake';
import { CITIES } from './types/intake';
import styles from './App.module.css';

const PHASE_LABEL: Record<string, string> = {
  intake: 'Awaiting intake',
  running: 'Agents running',
  awaiting_conflict: 'Paused — discrepancy',
  awaiting_approval: 'Paused — approval',
  complete: 'Complete',
  failed: 'Failed',
};

export default function App() {
  const {
    phase,
    caseState,
    trace,
    agents,
    artifacts,
    activeInterrupt,
    uploadedDocument,
    connected,
    streamError,
    setConnected,
    setUploadedDocument,
    beginCase,
    applyEvent,
    clearInterrupt,
    loadFixture,
    reset,
  } = useCaseStore();

  const frozen = selectReadinessFrozen({ caseState });
  const streamRef = useRef<StreamHandle | null>(null);
  const [resuming, setResuming] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  useEffect(() => () => streamRef.current?.close(), []);

  const handleStart = async (values: IntakeValues, document: UploadedDocument | null) => {
    setStartError(null);
    try {
      const { case_id } = await createCase({ intake: values, document });
      beginCase(case_id, values.goal);
      streamRef.current?.close();
      streamRef.current = openCaseStream(case_id, {
        onOpen: () => setConnected(true),
        onEvent: (event) => {
          applyEvent(event);
          if (event.type === 'done' || event.type === 'error') setConnected(false);
        },
        onError: (message) => {
          setConnected(false);
          applyEvent({ type: 'error', message, at: new Date().toISOString() });
        },
      });
    } catch (error) {
      setStartError(
        `Could not reach the mock server at ${import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'} — start it with "npm run mock". (${String(error)})`
      );
    }
  };

  const resume = async (payload: Parameters<typeof resumeCase>[1]) => {
    setResuming(true);
    try {
      await resumeCase(caseState.case_id, payload);
      clearInterrupt();
    } catch (error) {
      applyEvent({
        type: 'error',
        message: `Could not resume the case: ${String(error)}`,
        at: new Date().toISOString(),
      });
    } finally {
      setResuming(false);
    }
  };

  const startOver = () => {
    streamRef.current?.close();
    streamRef.current = null;
    setStartError(null);
    reset();
  };

  const cityLabel = CITIES.find((c) => c.value === caseState.city)?.label ?? caseState.city;
  const busy = phase !== 'intake';

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true" />
          <div>
            <h1 className={styles.wordmark}>GovFlow KSA</h1>
            <p className={styles.tagline}>Multi-agent government-journey orchestrator</p>
          </div>
        </div>

        <div className={styles.headerRight}>
          <span className={styles.phasePill}>{PHASE_LABEL[phase]}</span>
          {phase === 'intake' ? (
            <button type="button" className={styles.ghostBtn} onClick={loadFixture}>
              Preview with mock data
            </button>
          ) : (
            <button type="button" className={styles.ghostBtn} onClick={startOver}>
              Start over
            </button>
          )}
        </div>
      </header>

      <div className={styles.phaseBanner}>
        <strong>Phase A — mocked.</strong> No backend is connected. Agent output, evidence, fees
        and source URLs on this screen are hand-written fixture data, not retrieved from any
        government source.
      </div>

      <main className={styles.layout}>
        <AgentRoster agents={agents} connected={connected} />

        <div className={styles.content}>
          {phase === 'intake' && (
            <>
              <GoalInput
                onSubmit={handleStart}
                document={uploadedDocument}
                onDocumentChange={setUploadedDocument}
                busy={false}
              />
              {startError && (
                <p className={styles.error} role="alert">
                  {startError}
                </p>
              )}
            </>
          )}

          {busy && (
            <>
              <ProgressBar value={caseState.readiness_pct} frozen={frozen} />

              <section className={styles.summary}>
                <p className={styles.goal}>{caseState.goal}</p>
                <dl className={styles.facts}>
                  <Fact label="City" value={cityLabel} />
                  <Fact label="District" value={caseState.district} />
                  <Fact
                    label="Area (sqm)"
                    value={caseState.area_sqm_stated}
                    warn={frozen}
                    suffix={
                      caseState.area_sqm_from_document != null &&
                      caseState.area_sqm_from_document !== caseState.area_sqm_stated
                        ? `document says ${caseState.area_sqm_from_document}`
                        : undefined
                    }
                  />
                  <Fact
                    label="VAT registration"
                    value={
                      caseState.vat_registration_required == null
                        ? undefined
                        : caseState.vat_registration_required
                          ? 'Required'
                          : 'Not required'
                    }
                  />
                  <Fact
                    label="Requirements"
                    value={caseState.requirements.length || undefined}
                  />
                  <Fact
                    label="Approval"
                    value={caseState.approval_stage.replace('_', ' ')}
                  />
                </dl>
              </section>

              {streamError && (
                <p className={styles.error} role="alert">
                  {streamError}
                </p>
              )}

              <EvidenceLog trace={trace} evidence={caseState.evidence_log} />

              {artifacts && <ArtifactTabs artifacts={artifacts} />}
            </>
          )}
        </div>
      </main>

      {activeInterrupt?.kind === 'conflict_resolution' && (
        <ConflictModal
          conflict={activeInterrupt.conflict}
          busy={resuming}
          onResolve={(accepted, note) =>
            resume({
              kind: 'conflict_resolution',
              conflict_id: activeInterrupt.conflict.conflict_id,
              accepted,
              note,
            })
          }
        />
      )}

      {activeInterrupt?.kind === 'approval_gate' && (
        <ApprovalGate
          gate={activeInterrupt}
          busy={resuming}
          onDecide={(decision, note) => resume({ kind: 'approval_gate', decision, note })}
        />
      )}
    </div>
  );
}

function Fact({
  label,
  value,
  suffix,
  warn = false,
}: {
  label: string;
  value?: string | number | null;
  suffix?: string;
  warn?: boolean;
}) {
  return (
    <div className={styles.fact}>
      <dt>{label}</dt>
      <dd className={warn && suffix ? styles.factWarn : undefined}>
        {value === undefined || value === null || value === '' ? (
          <span className={styles.pendingValue}>—</span>
        ) : (
          value
        )}
        {suffix && <span className={styles.factSuffix}>{suffix}</span>}
      </dd>
    </div>
  );
}
