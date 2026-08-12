/**
 * Phase-A mock backend.
 *
 * Replays a canned agent-status sequence over SSE so the live-update UX
 * (progress bar filling, agent roster lighting up) and both human-in-the-loop
 * gates can be validated before any real backend exists — handoff doc
 * section 4, Phase A step 5.
 *
 * It listens on the same port the real FastAPI service will use (8000), so
 * Phase C is a VITE_API_BASE_URL change and nothing else.
 *
 * The case data comes from `src/mocks/mockCase.json` — the same file the React
 * app imports, so the streamed sequence and the static fixture cannot drift.
 *
 *   node mock-server/index.mjs
 */

import express from 'express';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(
  readFileSync(join(__dirname, '..', 'src', 'mocks', 'mockCase.json'), 'utf8')
);

const FIXTURE_STATE = fixture.case_state;
const FIXTURE_ARTIFACTS = fixture.artifacts;
const PORT = Number(process.env.MOCK_PORT ?? 8000);

/** Wall-clock pacing so the roster visibly steps through the graph. */
const TICK = Number(process.env.MOCK_TICK_MS ?? 700);

const app = express();
app.use(express.json({ limit: '1mb' }));

app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  if (req.method === 'OPTIONS') {
    res.sendStatus(204);
    return;
  }
  next();
});

/** case_id -> { intake, document, pendingGate } */
const cases = new Map();
let caseCounter = 0;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const now = () => new Date().toISOString();
const req = (name) => FIXTURE_STATE.requirements.find((r) => r.name === name);
const evi = (i) => FIXTURE_STATE.evidence_log[i];

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', service: 'govflow-mock', cases: cases.size });
});

app.post('/api/cases', (request, response) => {
  const { intake, document } = request.body ?? {};
  if (!intake) {
    response.status(400).json({ error: 'intake payload is required' });
    return;
  }
  const caseId = `case_mock_${String(++caseCounter).padStart(3, '0')}`;
  cases.set(caseId, { intake, document: document ?? null, pendingGate: null });
  response.json({ case_id: caseId });
});

app.post('/api/cases/:id/resume', (request, response) => {
  const record = cases.get(request.params.id);
  if (!record) {
    response.status(404).json({ error: 'unknown case' });
    return;
  }
  if (!record.pendingGate) {
    response.status(409).json({ error: 'no gate is currently open for this case' });
    return;
  }
  const gate = record.pendingGate;
  record.pendingGate = null;
  gate.resolve(request.body ?? {});
  response.json({ ok: true });
});

app.get('/api/cases/:id/stream', async (request, response) => {
  const caseId = request.params.id;
  const record = cases.get(caseId);
  if (!record) {
    response.status(404).json({ error: 'unknown case' });
    return;
  }

  response.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no',
    'Access-Control-Allow-Origin': '*',
  });
  response.flushHeaders?.();

  let clientGone = false;
  request.on('close', () => {
    clientGone = true;
    if (record.pendingGate) {
      record.pendingGate.resolve({ aborted: true });
      record.pendingGate = null;
    }
  });

  const send = (event) => {
    if (clientGone) return;
    response.write(`data: ${JSON.stringify({ ...event, at: now() })}\n\n`);
  };
  const status = (agent, s, message) => send({ type: 'agent_status', agent, status: s, message });
  const patch = (p) => send({ type: 'state_patch', patch: p });
  const decide = (entry) => send({ type: 'decision', entry });

  /** Blocks the run on a LangGraph-style interrupt() until /resume is called. */
  const gate = (interrupt) => {
    send({ type: 'interrupt', interrupt });
    return new Promise((resolve) => {
      record.pendingGate = { kind: interrupt.kind, resolve };
    });
  };

  try {
    await runSequence({ record, send, status, patch, decide, gate, isGone: () => clientGone });
  } catch (error) {
    send({ type: 'error', message: String(error?.message ?? error) });
  } finally {
    if (!clientGone) response.end();
  }
});

async function runSequence(ctx) {
  const { record, send, status, patch, decide, gate, isGone } = ctx;
  const { intake, document } = record;
  const statedArea = Number(intake.area_sqm_stated);
  const docArea =
    document && typeof document.extracted_area_sqm === 'number'
      ? document.extracted_area_sqm
      : null;

  const step = async (ms = TICK) => {
    await sleep(ms);
    if (isGone()) throw new Error('client disconnected');
  };

  // ---- intake_planner ----
  status('intake_planner', 'active', 'Extracting fields from the stated goal');
  await step();
  patch({
    goal: intake.goal,
    business_type: intake.business_category,
    city: intake.city,
    district: intake.district,
    area_sqm_stated: statedArea,
    expected_annual_revenue_sar: Number(intake.expected_annual_revenue_sar),
    budget_sar: intake.budget_sar ?? null,
    readiness_pct: 12,
  });
  decide(FIXTURE_STATE.decision_log[0]);
  decide(FIXTURE_STATE.decision_log[1]);
  status('intake_planner', 'complete', 'Branch: food_business');
  await step();

  // ---- regulation_router ----
  status('regulation_router', 'active', 'Searching allowlisted domains');
  await step(TICK * 1.6);
  patch({
    requirements: [
      req('Commercial Registration (CR)'),
      req('Municipal commercial licence (Balady)'),
      req('VAT registration (ZATCA)'),
    ],
    evidence_log: [evi(0), evi(1), evi(2)],
    readiness_pct: 30,
  });
  decide(FIXTURE_STATE.decision_log[2]);
  await step();
  patch({
    requirements: [
      req('Commercial Registration (CR)'),
      req('Municipal commercial licence (Balady)'),
      req('VAT registration (ZATCA)'),
      req('Food-handling compliance (SFDA)'),
      req('GOSI employer registration'),
    ],
    evidence_log: [evi(0), evi(1), evi(2), evi(3), evi(4), evi(5)],
    readiness_pct: 42,
  });
  decide(FIXTURE_STATE.decision_log[3]);
  status('regulation_router', 'complete', '4 requirements cited, 1 unverified');
  await step();

  // ---- municipal_location (A2A) + tax_financial (deterministic), in parallel ----
  status('municipal_location', 'active', 'Delegated over A2A to :8001');
  status('tax_financial', 'active', 'Deterministic assessment — no LLM');
  await step();
  patch({
    vat_registration_required: Number(intake.expected_annual_revenue_sar) > 375000,
    readiness_pct: 52,
  });
  decide(FIXTURE_STATE.decision_log[6]);
  status('tax_financial', 'complete', 'mandatory_registration_likely');
  await step();
  patch({
    requirements: [
      req('Commercial Registration (CR)'),
      req('Municipal commercial licence (Balady)'),
      req('VAT registration (ZATCA)'),
      req('Food-handling compliance (SFDA)'),
      req('GOSI employer registration'),
      req('Premises area meets municipal minimum'),
    ],
    evidence_log: [...FIXTURE_STATE.evidence_log],
    readiness_pct: 60,
  });
  decide(FIXTURE_STATE.decision_log[4]);
  decide(FIXTURE_STATE.decision_log[5]);
  status('municipal_location', 'complete', 'Approval status: NOT VERIFIED');
  await step();

  // ---- verifier ----
  status('verifier', 'active', 'Auditing citations');
  await step(TICK * 1.4);
  patch({ readiness_pct: 68 });
  decide(FIXTURE_STATE.decision_log[7]);

  const hasConflict = docArea !== null && docArea !== statedArea;

  if (hasConflict) {
    const conflict = {
      ...FIXTURE_STATE.conflicts[0],
      stated_value: statedArea,
      document_value: docArea,
      document_source: `${document.filename} — clause 3.1, extracted text layer`,
    };
    patch({ area_sqm_from_document: docArea, conflicts: [conflict] });
    decide(
      `Verifier: DISCREPANCY — area_sqm_stated (${statedArea}) does not match ` +
        `area_sqm_from_document (${docArea}). Readiness frozen pending human resolution.`
    );
    status('verifier', 'blocked', 'Discrepancy — awaiting human resolution');

    const resolution = await gate({ kind: 'conflict_resolution', conflict });
    if (resolution.aborted) return;

    const acceptedValue = resolution.accepted === 'document' ? docArea : statedArea;
    patch({
      conflicts: [
        {
          ...conflict,
          status: 'resolved',
          resolution: {
            accepted: resolution.accepted,
            accepted_value: acceptedValue,
            note: resolution.note,
            resolved_at: now(),
          },
        },
      ],
      area_sqm_stated: acceptedValue,
      readiness_pct: 74,
    });
    decide(
      `Human resolution: "${resolution.accepted}" value accepted for premises area ` +
        `(${acceptedValue} sqm). Readiness unfrozen.`
    );
    status('verifier', 'active', 'Re-running after conflict resolution');
    await step();
  } else if (docArea !== null) {
    patch({ area_sqm_from_document: docArea });
    decide(
      `Verifier: stated area (${statedArea} sqm) matches the value extracted from ` +
        `${document.filename}. No discrepancy.`
    );
  }

  patch({ readiness_pct: 80 });
  status('verifier', 'complete', '5 accepted, 2 rejected');
  await step();

  // ---- human approval gate ----
  const approval = await gate({
    kind: 'approval_gate',
    summary:
      'The proposal below was assembled from verified evidence only. Rejected claims ' +
      'have been removed entirely, not softened. Approve to generate the final artifacts.',
    requirement_count: FIXTURE_STATE.requirements.length,
    accepted_evidence_count: FIXTURE_STATE.evidence_log.filter((e) => e.has_explicit_url).length,
    rejected_evidence_count: FIXTURE_STATE.evidence_log.filter((e) => !e.has_explicit_url).length,
  });
  if (approval.aborted) return;

  if (approval.decision === 'reject') {
    patch({ approval_stage: 'none' });
    decide(`Human approval gate: REJECTED.${approval.note ? ` Note: ${approval.note}` : ''}`);
    send({ type: 'done' });
    return;
  }

  patch({ approval_stage: 'proposal_approved' });
  decide(`Human approval gate: APPROVED.${approval.note ? ` Note: ${approval.note}` : ''}`);
  await step();

  // ---- documentation ----
  status('documentation', 'active', 'Assembling the six artifacts');
  await step(TICK * 1.6);
  patch({ readiness_pct: 92 });
  status('documentation', 'complete', 'Journey, checklist, evidence, fees, packet, log');
  await step();

  send({ type: 'artifacts_ready', artifacts: FIXTURE_ARTIFACTS });
  patch({ readiness_pct: 100 });
  await step(300);
  send({ type: 'done' });
}

app.listen(PORT, () => {
  console.log(`GovFlow mock backend on http://localhost:${PORT}`);
  console.log(`  POST /api/cases              create a case`);
  console.log(`  GET  /api/cases/:id/stream   SSE agent sequence`);
  console.log(`  POST /api/cases/:id/resume   release an interrupt() gate`);
});
