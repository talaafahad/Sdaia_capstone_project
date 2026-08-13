# Bosalah — بوصلة

### Build order: Frontend → Backend → Integration
### Companion to GovFlow-KSA-Implementation-Plan.md (agent specs, prompts, allowlist, field spec, theme all live there — this file sequences the actual build)

---

## 1. Model picks — verified live on OpenRouter, August 2026

Pulled directly from OpenRouter's free-models collection rather than a blog summary, since free-tier IDs and availability shift often — reverify at openrouter.ai/models before you actually wire these in, in case anything changed between now and your build session.

| Agent | Model (OpenRouter slug) | Why |
|---|---|---|
| **Regulation & Service Router** | `nvidia/nemotron-3-ultra-550b-a55b:free` | Frontier reasoning/orchestration model, 1M context, explicitly built for "agent orchestration, coding agents, deep research, and complex enterprise tasks" — your highest-stakes citation-discipline agent gets your strongest free model |
| **Verifier** | `nvidia/nemotron-3-ultra-550b-a55b:free` (same as above) | This is your hallucination firewall — don't economize here either. If you hit rate-limit contention running both agents on Ultra, fall back this one node to Nemotron 3 Super below rather than Regulation Router, since Verifier only runs once per case (cheap) while Regulation Router may run multiple retrieval passes |
| **Municipal & Location (A2A service)** | `nvidia/nemotron-3-super-120b-a12b:free` | 120B total/12B active, 1M context, explicitly tuned for "complex multi-agent applications" and cross-document reasoning — strong but lighter than Ultra, appropriate for a narrower-scoped agent |
| **Intake + Planner** | `nvidia/nemotron-nano-9b-v2:free` | Fast, controllable reasoning trace (can be turned off for pure extraction), 128K context — right-sized for structured-field extraction, not a task that needs your biggest model |
| **Tax explanation wrapper** (not the decision — see plan section 2.4) | `nvidia/nemotron-nano-9b-v2:free` | Same model, minimal task — just restates a pre-computed dict in prose |
| **Documentation / Packaging** | `nvidia/nemotron-3-nano-30b-a3b:free` | 256K context, efficient, good fit for templating-heavy output with light reasoning |
| **Embeddings** (hybrid dense+BM25 search over your local regulation corpus) | `nvidia/nemotron-3-embed-1b:free` | Free, purpose-built for RAG/agentic retrieval. **Caveat: verify Arabic-text embedding quality before committing** — its listing doesn't explicitly confirm strong Arabic coverage the way a dedicated multilingual model (e.g. BAAI/bge-m3) would. Run a quick side-by-side retrieval test on a few Arabic regulation snippets from your corpus; if quality is noticeably weaker than English, swap to bge-m3 (also runnable locally or via Hugging Face inference, doesn't need a new API key either way) |

**Rate-limit reality check:** free OpenRouter models are capped around 20 requests/minute per model, with a daily cap that's low with no credits purchased and higher (roughly 1,000/day) once you've added a small amount of credit to your account. Given you're running 5+ agents each potentially calling their model multiple times per case, **add a small top-up ($10) to your OpenRouter account before your heavy testing/demo days** — this is the single easiest way to avoid a rate-limit error mid-demo, and it costs you nothing per-token since you're still calling the `:free` model variants.

---

## 2. API keys — what you have vs. what you still need

You have: **OpenRouter**, **Tavily**.

| Need | Have it? | Action |
|---|---|---|
| LLM inference (all agents) | ✅ OpenRouter | Covered — models above all route through your existing key |
| Regulation-page search restricted to the allowlist | ✅ Tavily | Use its `include_domains` parameter with the allowlist from the implementation plan section 0/9 |
| Location/competitor lookup | **No key needed** | OSM Overpass + Nominatim are free, keyless — nothing to sign up for |
| Document text extraction (lease PDF) | **No key needed** | PyMuPDF/pdfplumber run locally, no API |
| Embeddings for hybrid search | ✅ OpenRouter (see table above) | No separate key — same OpenRouter key covers the embed model too |
| **Observability tracing** | ❌ Not yet obtained | **Sign up for a LangSmith API key** (langsmith has a free tier sufficient for a course project) — this is the one genuinely new signup you need |
| Mock Balady submission auth | **No external key** | This is your own self-issued token/secret for the MCP auth demo (section 2, Phase 5 of the implementation plan) — you generate and manage this yourself, it's not a third-party service |
| Optional: paid Claude API (if you choose the hybrid model option from the implementation plan section 11) | ❌ Not needed unless you opt in | Separate Anthropic Console account with its own billing — only needed if you decide the free-tier models aren't strong enough on the Regulation Router/Verifier nodes specifically |

**So: one new signup (LangSmith), everything else is covered by what you already have.**

---

## 3. Repo structure, `.env` layout, and `uv` setup

Set this up before Phase A starts — Claude Code should create this structure first.

```
govflow-ksa/
├── backend/
│   ├── case-officer/                  # main graph: Intake, Regulation, Tax, Verifier, Documentation
│   │   ├── pyproject.toml
│   │   ├── .env                       # <- real keys, NEVER committed
│   │   ├── .env.example               # <- placeholders, this one IS committed
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── state.py
│   │   │   ├── graph.py
│   │   │   ├── agents/
│   │   │   ├── tools/
│   │   │   └── config/allowlist.py
│   │   └── tests/
│   │
│   └── municipal-location/            # separate A2A microservice
│       ├── pyproject.toml
│       ├── .env
│       ├── .env.example
│       └── app/
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── .env                           # VITE_ vars only
│   ├── .env.example
│   └── src/...
│
├── data/gov_corpus/                   # pre-scraped Balady/ZATCA/MCI pages
├── docker-compose.yml
├── .gitignore
└── README.md
```

**Why `.env` lives per-service, not at the repo root:** each backend service has different secrets (the municipal service doesn't need your Tavily key, for instance), and this way `docker compose` can inject each container's env file independently without a shared file leaking keys across services that don't need them.

**`backend/case-officer/.env` contents:**
```
OPENROUTER_API_KEY=...
TAVILY_API_KEY=...
LANGSMITH_API_KEY=...
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=govflow-ksa
MCP_AUTH_SECRET=...          # self-generated — e.g. `openssl rand -hex 32`
```

**`backend/municipal-location/.env`:** just `OPENROUTER_API_KEY` (and `TAVILY_API_KEY` if this service also does its own Balady retrieval per the implementation plan's agent split) — no Tax/Verifier keys needed here since those live in the other service.

**`frontend/.env`:**
```
VITE_API_BASE_URL=http://localhost:8000
```
(Vite only exposes vars prefixed `VITE_` to the browser bundle — anything else stays server-side, which is correct since the frontend should never see your OpenRouter/Tavily keys directly.)

**`.gitignore` at the repo root:**
```
.env
.venv/
__pycache__/
node_modules/
dist/
```

**Backend dependency setup — using `uv`, per service (not at the repo root, since each service has its own `pyproject.toml`):**

```bash
cd backend/case-officer
uv init --no-readme          # if pyproject.toml doesn't exist yet
uv add fastapi uvicorn langgraph langchain-openai pydantic pydantic-settings \
       python-dotenv tavily-python langsmith fastmcp pymupdf httpx
uv run uvicorn app.main:app --reload --port 8000
```

```bash
cd backend/municipal-location
uv init --no-readme
uv add fastapi uvicorn langgraph langchain-openai pydantic-settings python-dotenv fastmcp httpx
uv run uvicorn app.main:app --reload --port 8001
```

`uv run` uses the project's `.venv` automatically. Load `.env` via `pydantic-settings`'s `BaseSettings(env_file=".env")` rather than raw `os.environ` calls — this pairs naturally with the `CaseState` Pydantic schema already in use and validates that required keys are actually present at startup instead of failing deep inside an agent call.

---

## 4. Build order: Frontend first, then Backend, then Integration

This reorders the phased plan from the implementation doc (which was backend-first) to match what you asked for. The tradeoff to know going in: building the UI before the API it calls exists means the frontend initially runs against **mocked data matching the `CaseState` schema**, not live agent output — that's normal and fine, just flag it to Claude Code explicitly so it builds a mock data layer you can swap out later rather than something throwaway.

### Phase A — Frontend scaffold (mocked data)

1. Scaffold Vite + React app per the structure in the implementation plan section 5.
2. Apply the sage-green/lavender theme (implementation plan section 12) — palette, typography, the low-opacity background treatment.
3. Build every component against a **hand-written mock `CaseState` JSON** (not a live stream yet): `GoalInput`, `ProgressBar`, `AgentRoster`, `EvidenceLog`, `ConflictModal`, `ApprovalGate`, `ArtifactTabs`, `DocumentUpload`.
4. Build the intake form using the full required/optional field spec (implementation plan section 13), with client-side validation on the required fields.
5. Stub the SSE/WebSocket client (`caseStream.ts`) against a local mock server (a tiny Express or json-server instance is fine) that just replays a canned sequence of agent-status updates — this lets you validate the live-update UX (progress bar filling, agent roster lighting up) before any real backend exists.

**Checkpoint before moving to Phase B:** the full mocked user journey should be clickable end-to-end — goal input → mocked agent progress → mocked conflict modal → mocked approval gate → mocked artifact tabs — even though nothing is real yet. This is your safety net: if backend work runs long, you still have a demoable UI.

### Phase B — Backend (per the implementation plan's Phases 0–5, unchanged)

6. Corpus collection + allowlist config (implementation plan Phase 0).
7. State schema + deterministic Tax/Financial core (Phase 1).
8. Retrieval-grounded agents: Intake+Planner, Regulation Router, hybrid search (Phase 2).
9. Municipal & Location A2A microservice (Phase 3).
10. Verifier + Documentation agents (Phase 4).
11. Human-in-the-loop interrupts + mock execution adapter behind MCP auth (Phase 5).

Build and test this against the FastAPI endpoints directly (curl/Postman/pytest) — don't wire the frontend yet, keep this phase's feedback loop backend-only so failures are unambiguous about which layer they're in.

### Phase C — Integration (link them)

12. Replace the frontend's mock SSE server with the real FastAPI streaming endpoint — this should be closer to a swap than a rewrite if `caseState.ts` was kept as a faithful mirror of the Pydantic schema from the start (implementation plan section 5).
13. Wire `ConflictModal` and `ApprovalGate` to the real LangGraph `interrupt()` points.
14. Run the full coffee-shop scenario end-to-end through the real UI, confirm the discrepancy-detection centerpiece fires correctly against a real uploaded lease PDF.
15. Turn on LangSmith across both backend services; capture the full trace.
16. Only then move to the second vertical (food truck) if time allows, per the implementation plan's generalization guidance (section 10) — get one vertical fully solid through the real UI before spreading to a second.

---

## 5. Kickoff prompt — paste this to Claude Code to start

```
I'm building GovFlow KSA, a multi-agent Saudi government-journey orchestrator,
for a capstone course. I have two reference documents:
GovFlow-KSA-Implementation-Plan.md (agent specs, system prompts, domain
allowlist, field spec, frontend theme) and this handoff doc (model picks,
API keys, build order).

First, set up the repo structure, .env/.env.example files, .gitignore, and
uv-managed pyproject.toml for both backend services exactly as specified in
section 3 of this document — don't start writing agent code yet, just get
the skeleton and dependency setup right first.

Then start Phase A only: scaffold the React + Vite frontend, apply the
sage-green/lavender theme from the implementation plan section 12, and
build every component (GoalInput, ProgressBar, AgentRoster, EvidenceLog,
ConflictModal, ApprovalGate, ArtifactTabs, DocumentUpload) against a
hand-written mock CaseState JSON — no backend yet. Include the full
required/optional intake field set from implementation plan section 13
with client-side validation on required fields. Stub the SSE client
against a local mock server that replays a canned agent-status sequence.

Stop and show me the working mocked UI before moving to Phase B (backend).
Ask me before making any architecture decision not already specified in
the two reference documents rather than guessing.
```

Handing it phase-by-phase like this (rather than the whole plan at once) keeps each stage testable before the next depends on it — Phase C integration is much easier to debug if Phase A and Phase B were each independently verified working first.
