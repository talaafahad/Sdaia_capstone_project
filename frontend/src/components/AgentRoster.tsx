/**
 * Live agent-status sidebar.
 *
 * Per implementation plan section 12: the currently active agent card uses the
 * lavender tint, completed agents use the sage tint. The `kind` badge keeps the
 * architecture legible during the demo — which nodes are LLM agents, which is
 * the remote A2A service, and which one is deterministic Python with no LLM in
 * the decision path (section 2.4).
 */

import type { AgentId, AgentRuntime } from '../types/events';
import { AGENT_ROSTER } from '../types/events';
import styles from './AgentRoster.module.css';

interface AgentRosterProps {
  agents: Record<AgentId, AgentRuntime>;
  connected: boolean;
}

const KIND_LABEL: Record<string, string> = {
  llm: 'LLM',
  deterministic: 'DETERMINISTIC',
  'a2a-remote': 'A2A',
};

const STATUS_LABEL: Record<string, string> = {
  pending: 'Waiting',
  active: 'Running',
  complete: 'Done',
  blocked: 'Blocked',
};

export function AgentRoster({ agents, connected }: AgentRosterProps) {
  return (
    <aside className={styles.roster} aria-label="Agent status">
      <header className={styles.head}>
        <h2 className={styles.title}>Agents</h2>
        <span
          className={`${styles.link} ${connected ? styles.linkUp : styles.linkDown}`}
          title={connected ? 'SSE stream connected' : 'SSE stream not connected'}
        >
          <span className={styles.linkDot} aria-hidden="true" />
          {connected ? 'streaming' : 'idle'}
        </span>
      </header>

      <ol className={styles.list}>
        {AGENT_ROSTER.map((agent) => {
          const runtime = agents[agent.id] ?? { status: 'pending' as const };
          return (
            <li
              key={agent.id}
              className={`${styles.card} ${styles[runtime.status]}`}
              aria-current={runtime.status === 'active' ? 'step' : undefined}
            >
              <div className={styles.cardHead}>
                <span className={styles.name}>{agent.label}</span>
                <span className={`${styles.kind} ${styles[`kind_${agent.kind.replace('-', '_')}`]}`}>
                  {KIND_LABEL[agent.kind]}
                </span>
              </div>

              <p className={styles.subtitle}>{agent.subtitle}</p>

              <div className={styles.statusRow}>
                <span className={styles.indicator} aria-hidden="true" />
                <span className={styles.statusText}>{STATUS_LABEL[runtime.status]}</span>
              </div>

              {runtime.message && <p className={styles.message}>{runtime.message}</p>}
            </li>
          );
        })}
      </ol>
    </aside>
  );
}
