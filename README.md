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
| B | Backend (implementation plan Phases 0–5) | Not started |
| C | Integration — real SSE, real `interrupt()` gates, LangSmith | Not started |

Backend modules under `app/` are intentionally placeholders until Phase B.

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
