# GovFlow KSA

A multi-agent Saudi government-journey orchestrator. Capstone project.

Reference documents (source of truth for all design decisions):

- [docs/GovFlow-KSA-Implementation-Plan (1).md](<docs/GovFlow-KSA-Implementation-Plan (1).md>) — agent specs, system prompts, domain allowlist, intake field spec, frontend theme
- [docs/GovFlow-KSA-Claude-Code-Handoff.md](docs/GovFlow-KSA-Claude-Code-Handoff.md) — model picks, API keys, build order

## Layout

```
backend/case-officer/        # main LangGraph service (port 8000)
backend/municipal-location/  # A2A microservice (port 8001)
frontend/                    # React + Vite
data/gov_corpus/             # pre-scraped allowlisted government pages
```

Each backend service owns its own `.env` and `pyproject.toml` — secrets are
scoped per service so `docker compose` can inject them independently.

## Setup

Copy each `.env.example` to `.env` and fill in real values:

```bash
cp backend/case-officer/.env.example backend/case-officer/.env
cp backend/municipal-location/.env.example backend/municipal-location/.env
cp frontend/.env.example frontend/.env
```

Generate `MCP_AUTH_SECRET` with `openssl rand -hex 32`.

## Run

### Frontend (Phase A — no backend needed)

```bash
cd frontend
npm install
npm run dev        # starts the mock SSE server on :8000 and Vite on :5173
```

Open http://localhost:5173. Click **Fill sample case**, attach any PDF, and
**Start the case** to watch the mocked agent run — including the lease-area
discrepancy modal and the approval gate. **Preview with mock data** in the
header renders every component straight from the fixture with no server at all.

Useful knobs: `npm run mock` runs only the mock server, `npm run dev:vite` only
Vite. `MOCK_TICK_MS=200 npm run mock` speeds up the canned sequence.

### Backend (Phase B)

```bash
# Case Officer
cd backend/case-officer && uv run uvicorn app.main:app --reload --port 8000

# Municipal & Location
cd backend/municipal-location && uv run uvicorn app.main:app --reload --port 8001
```

Note both the mock server and the real Case Officer service use port 8000 — that
is deliberate, so Phase C integration is a `VITE_API_BASE_URL` change and nothing
else. Do not run them at the same time.

## Build status

| Phase | Scope | Status |
|---|---|---|
| Setup | Repo skeleton, per-service `.env`, uv dependency setup | Done |
| A | Frontend against mocked `CaseState` + mock SSE server | Done |
| B | Backend (implementation plan Phases 0–5) | Done |
| C | Integration — point the frontend at the real API | Next |

## Model assignment per node (handoff §1)

All four chat slugs re-verified against `openrouter.ai/api/v1/models`.
Temperature is 0 everywhere (§7). Override any node with `MODEL_<NODE>=...`.

| Node | Model | Fallback |
|---|---|---|
| `intake_planner` | nemotron-nano-9b-v2:free | — |
| `commercial_registration` | nemotron-3-ultra-550b-a55b:free | super-120b |
| `vat_registration` | nemotron-3-ultra-550b-a55b:free | super-120b |
| `food_safety` | nemotron-3-ultra-550b-a55b:free | super-120b |
| `employment_social_insurance` | nemotron-3-ultra-550b-a55b:free | super-120b |
| `intellectual_property` | nemotron-3-ultra-550b-a55b:free | super-120b |
| `municipal_requirements` (A2A) | nemotron-3-super-120b-a12b:free | — |
| `competitor_lookup` (A2A) | nemotron-3-super-120b-a12b:free | — |
| `verifier` | nemotron-3-ultra-550b-a55b:free | super-120b |
| `documentation` | nemotron-3-nano-30b-a3b:free | — |
| `tax_explanation` | nemotron-nano-9b-v2:free | — |
| embeddings (dense half of hybrid search) | nemotron-3-embed-1b:free | bge-m3 |

`tax_financial` has **no model** — the VAT decision is plain Python (§2.4).
`GET /api/models` returns this table live.

### Free-tier latency

Measured: **60–70s per call even for a trivial prompt** — these models queue
rather than reject. A cold case takes ~7 minutes; a cached one ~80s. Model
replies are cached to `data/.llm_cache/` keyed by (node, model, prompt), which
is safe because every node runs at temperature 0. Clear it to force fresh calls.

### Rate limits (429)

Free-tier quota is the practical constraint, not latency. Handling:

- **Detected** by status code, response status, or message — distinguished from
  a timeout, which is a different failure needing a different response.
- **Retried on the same model** with backoff `5s → 20s → 65s`, honouring
  `Retry-After` when the provider sends one. The last step crosses a minute
  boundary rather than hammering a window that has not reset. Switching models
  on a 429 does not help — the quota is per account, not per model.
- **Never cached.** Only successful calls are written, so a broken run cannot
  become reproducible.
- **The Verifier audits in batches of 4**, so one 429 costs a few claims rather
  than every verdict.

The failure that matters most is a 429 during the Verifier's audit: "could not
verify" and "verified and found nothing sourced" produce identical numbers and
mean opposite things. When the audit cannot complete the decision log says so
explicitly, and each withheld claim reads `NOT AUDITED — … withheld, not judged
unsupported.` Claims are still withheld (failing closed is correct), but the
report never presents an outage as a finding.

### Offline / demo-day switches

| Env var | Effect |
|---|---|
| `DISABLE_LIVE_SEARCH=1` | Corpus fallback only; cached live results still serve |
| `DISABLE_LLM_CACHE=1` | Always call the model |
| `DISABLE_DENSE_SEARCH=1` | BM25-only hybrid search |
| `LIVE_SEARCH_TIMEOUT_SECONDS` | Default 12 (Tavily measured at 1.9–8.6s) |
| `LLM_TIMEOUT_SECONDS` | Default 240 |

## Phase A stack choices

The two reference documents leave these open; they were chosen explicitly
rather than defaulted:

| Decision | Choice |
|---|---|
| Theme mechanism | CSS custom properties (`src/styles/tokens.css`) + CSS Modules |
| State management | Zustand (plan section 5 allowed Context or Zustand) |
| Form validation | react-hook-form + zod |
| Mock SSE server | Standalone Express on :8000 (doc suggested Express or json-server) |

`src/types/caseState.ts` is a hand-maintained mirror of the Pydantic `CaseState`
in `backend/case-officer/app/state.py`. Keep them in sync — that is what makes
Phase C a swap rather than a rewrite.
