/**
 * Typed accessors over the hand-written Phase-A fixture.
 *
 * `mockCase.json` is the single copy of this data — the Express mock server in
 * `mock-server/` reads the same file, so the streamed sequence and the static
 * fixture cannot drift apart.
 */

import type { CaseState } from '../types/caseState';
import type { DocumentationArtifacts } from '../types/artifacts';
import raw from './mockCase.json';

interface MockFixture {
  _note: string;
  case_state: CaseState;
  artifacts: DocumentationArtifacts;
}

const fixture = raw as unknown as MockFixture;

export const MOCK_FIXTURE_NOTE = fixture._note;

/** Deep copy on every read so component-level mutation can't corrupt the fixture. */
export const mockCaseState = (): CaseState =>
  structuredClone(fixture.case_state);

export const mockArtifacts = (): DocumentationArtifacts => {
  const artifacts = structuredClone(fixture.artifacts);
  // The Documentation agent's sixth section is the case's own decision log.
  artifacts.decision_log = structuredClone(fixture.case_state.decision_log);
  return artifacts;
};

/** Empty shell used before a case is started. */
export const emptyCaseState = (): CaseState => ({
  case_id: '',
  goal: '',
  requirements: [],
  evidence_log: [],
  readiness_pct: 0,
  conflicts: [],
  approval_stage: 'none',
  decision_log: [],
});
