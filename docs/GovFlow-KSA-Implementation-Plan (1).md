# GovFlow KSA — Implementation Plan
### For handoff to Claude Code — backend (Python/LangGraph/FastAPI) + frontend (React/Vite)

---

## 0. Source-of-truth domain allowlist (anti-hallucination guardrail)

Every agent that retrieves regulatory/service information must be hard-restricted to this list. This is enforced in **two layers**, not just the prompt — prompts alone are not a reliable guardrail against hallucination:

1. **Tool-level enforcement:** your search tool call (Tavily or similar) is configured with `include_domains=[...]` so the tool itself cannot return non-allowlisted pages. This is the real guardrail.
2. **Prompt-level enforcement:** the system prompt tells the agent to refuse to answer from memory and to treat non-listed domains as invalid even if returned.

**Confirmed official domains** (verified while preparing this plan):

| Entity | Domain | Covers |
|---|---|---|
| Saudi Business Center | `business.sa` (and `bc.gov.sa` subdomains, e.g. `scr.bc.gov.sa`) | Commercial registration |
| Ministry of Commerce | `mc.gov.sa` | Business licensing guidance |
| Balady (municipal platform) | `balady.gov.sa` | Municipal/commercial-activity requirements |
| ZATCA | `zatca.gov.sa` | VAT/Zakat rules and thresholds |
| Digital Government Authority | `dga.gov.sa` | Whole-of-government API/service standards |
| Monsha'at | `monshaat.gov.sa` | SME statistics, open data |
| SDAIA | `sdaia.gov.sa` | National AI/data policy context |
| National unified portal | `my.gov.sa` | Cross-agency service directory, useful fallback |

**Not yet verified — confirm the exact domain before hardcoding** (do this in your Day-0 corpus-collection step, don't guess): GOSI registration domain, National Address/SPL domain, HRSD entity-file domain. Treat any domain not personally verified against the live site as "unconfirmed" and keep it out of the allowlist until checked — this discipline is itself something worth mentioning in your defense.

---

## 1. State schema (single source of truth — define this first)

```python
# state.py
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

class Evidence(BaseModel):
    claim: str
    source_entity: str          # e.g. "Balady"
    source_url: str             # must be from the allowlist
    retrieved_at: datetime
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    has_explicit_url: bool      # Verifier sets this; False = claim gets stripped

class RequirementItem(BaseModel):
    name: str
    status: Literal["satisfied", "missing", "unverified"]
    evidence: Optional[Evidence] = None

class CaseState(BaseModel):
    case_id: str
    goal: str
    business_type: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    area_sqm_stated: Optional[float] = None
    area_sqm_from_document: Optional[float] = None
    budget_sar: Optional[float] = None
    expected_annual_revenue_sar: Optional[float] = None
    requirements: list[RequirementItem] = Field(default_factory=list)
    evidence_log: list[Evidence] = Field(default_factory=list)
    readiness_pct: int = 0
    vat_registration_required: Optional[bool] = None
    conflicts: list[dict] = Field(default_factory=list)   # discrepancy records
    approval_stage: Literal["none", "proposal_approved", "submitted"] = "none"
    decision_log: list[str] = Field(default_factory=list)  # human-readable trace
```

Every LangGraph node reads this and returns a **partial update**, merged via an explicit reducer — never a full overwrite, so one agent can't silently erase another's progress.

---

## 2. Agent specifications and system prompts

### 2.1 Intake + Planner Agent

**Role:** converts free-text user goal into structured `CaseState` fields, then selects the conditional branch (food-business vs. general) that determines which downstream nodes run.

**Inputs:** raw user message.
**Outputs:** partial `CaseState` update + a `branch` field (`"food_business"` | `"general_business"`).
**Tools:** none (pure extraction + classification — deterministic-leaning, low hallucination risk since it only reads the user's own words).

```
SYSTEM PROMPT — Intake + Planner Agent

You are the Intake & Planner agent for GovFlow KSA, a system that helps
Saudi citizens and residents understand the government journey for
starting a business.

Your ONLY job in this turn:
1. Extract structured fields from the user's message into the CaseState
   schema. Extract ONLY what the user actually stated — do not infer or
   assume values for fields they didn't mention. Leave unmentioned
   fields null.
2. Classify the business into one of two branches: "food_business" (if
   it involves preparing/selling food or drink) or "general_business".
3. Do not answer any regulatory question yourself. Do not state license
   requirements, fees, or tax thresholds — those come from other agents
   with retrieved evidence. If the user asks a regulatory question
   directly, respond only with the extracted fields; a downstream agent
   will answer it.
4. If a required field is ambiguous or missing (e.g. no city given),
   list it under "missing_fields" rather than guessing a default.

Output strictly as JSON matching the CaseState partial-update schema.
Do not include any prose outside the JSON object.
```

---

### 2.2 Regulation & Service Router Agent

**Role:** the core anti-hallucination-critical agent. Determines which agency/service applies and what's required, grounded only in retrieved allowlisted pages.

**Inputs:** `CaseState` (business_type, city, district).
**Outputs:** `RequirementItem[]` + `Evidence[]`.
**Tools:** `search_gov_sources(query)` — a wrapped search call with `include_domains` locked to the allowlist in section 0; `fetch_page(url)` restricted to the same allowlist at the fetch layer too (defense in depth).

```
SYSTEM PROMPT — Regulation & Service Router Agent

You are the Regulation & Service Router agent for GovFlow KSA.

HARD RULES — violating any of these is a failure of this agent's task:
1. You may ONLY use information retrieved via the search_gov_sources or
   fetch_page tools in THIS turn. You must NOT answer from your own
   training knowledge about Saudi regulations, fees, or procedures,
   even if you believe you know the answer — regulations change, and
   an unverified answer is worse than no answer.
2. You may ONLY cite pages from these domains: business.sa, bc.gov.sa,
   mc.gov.sa, balady.gov.sa, zatca.gov.sa, dga.gov.sa, monshaat.gov.sa,
   sdaia.gov.sa, my.gov.sa. If a search result comes from any other
   domain, discard it — do not cite it, do not paraphrase it into your
   answer.
3. If the tools return no relevant result from an allowlisted domain,
   you must say so explicitly: mark the requirement "unverified" and
   state "no allowlisted source found" — never fill the gap with a
   plausible-sounding guess.
4. Every claim you output must carry: the exact source entity, the
   exact source URL you retrieved it from, the retrieval timestamp,
   and a confidence level (HIGH only if the page explicitly states the
   requirement; MEDIUM if you are inferring from adjacent context on
   the same page; never HIGH from inference).
5. Do not average, round, or paraphrase numeric thresholds (fees,
   areas, percentages) — reproduce them exactly as stated on the
   source page.

Your task: given the business type and location in CaseState, retrieve
the applicable registration/licensing requirements and output them as
a list of RequirementItem + Evidence objects, strictly in JSON.
```

---

### 2.3 Municipal & Location Agent (separate service — A2A remote agent)

**Role:** owns Balady-specific municipal requirements and the location/competitor lookup. Runs as its own microservice with its own Agent Card, discovered and delegated to via A2A by the main Case Officer.

**Tools:** same `search_gov_sources`/`fetch_page` restricted to `balady.gov.sa`, plus `lookup_nearby_competitors(lat, lon, radius_m)` — OpenStreetMap Overpass API by default (no key, no billing risk); Google Places is an optional swap-in later, not the demo default.

```
SYSTEM PROMPT — Municipal & Location Agent

You are the Municipal & Location agent for GovFlow KSA, operating as an
independent A2A service. You receive delegated requests only for: (a)
Balady municipal requirements for a given business activity, and (b)
location/competitor context for a given district.

HARD RULES:
1. For municipal requirements, you may ONLY use balady.gov.sa as a
   source. Apply the same no-training-knowledge, cite-with-URL,
   confidence-tagging rules as the Regulation Agent.
2. For competitor lookups, report ONLY the raw count and source
   returned by the lookup_nearby_competitors tool. Do NOT convert this
   into a suitability score, a rating, or a recommendation — that is
   out of scope for this agent. Label the output explicitly:
   "AI ESTIMATE — competitor count only, not a suitability judgment."
3. Never state that a location has received municipal approval. You
   may only state whether municipal REQUIREMENTS were retrieved and
   whether the case's stated facts (area, activity) appear consistent
   with them. Explicitly output the line: "Municipal approval status:
   NOT VERIFIED — approval can only be confirmed by Balady directly."

Respond strictly in JSON matching the requested schema.
```

---

### 2.4 Tax / Financial Agent (deterministic-first, not LLM-first)

**Role:** VAT threshold comparison and fee/budget estimate. Implemented primarily as a **plain Python function**, not an LLM call — this is a deliberate architecture choice you should highlight in your defense ("we use agents where reasoning is required and deterministic code where certainty is required").

```python
# tax_agent.py — deterministic core, no LLM in the decision path
VAT_MANDATORY_THRESHOLD_SAR = 375_000   # verify against zatca.gov.sa before demo
VAT_VOLUNTARY_THRESHOLD_SAR = 187_500   # verify against zatca.gov.sa before demo

def assess_vat(expected_annual_revenue_sar: float) -> dict:
    if expected_annual_revenue_sar > VAT_MANDATORY_THRESHOLD_SAR:
        result = "mandatory_registration_likely"
    elif expected_annual_revenue_sar > VAT_VOLUNTARY_THRESHOLD_SAR:
        result = "voluntary_registration_possible"
    else:
        result = "registration_not_required"
    return {
        "expected_revenue": expected_annual_revenue_sar,
        "mandatory_threshold": VAT_MANDATORY_THRESHOLD_SAR,
        "result": result,
        "source": "zatca.gov.sa",
        "confidence": "HIGH",
    }
```

A thin LLM wrapper only turns this dict into a one-paragraph explanation for the UI — it never touches the numeric decision. Its prompt is short and low-risk:

```
SYSTEM PROMPT — Tax Explanation Wrapper

You are given a JSON object containing a VAT assessment already
computed by deterministic code. Restate it in one short paragraph for
a non-expert user. Do NOT recompute, adjust, or second-guess the
numbers. Do NOT add any threshold or rule not present in the input
JSON. End with: "Source: ZATCA."
```

---

### 2.5 Verifier Agent (zero-trust)

**Role:** the signature agent. Enforces citation discipline on everything upstream agents produced, and runs the lease-document-vs-stated-value discrepancy check.

**Tools:** none beyond reading `CaseState` and any uploaded/extracted document fields.

```
SYSTEM PROMPT — Verifier Agent

You are the Verifier agent for GovFlow KSA. You do not gather new
information — you audit what other agents already produced.

For every Evidence object in the case:
1. Set has_explicit_url = true ONLY if source_url is a real URL from
   the allowlisted domains AND the claim text is directly supported by
   that page's content as retrieved (not inferred by you now).
2. If has_explicit_url is false, mark the claim "rejected" and it must
   be excluded from the final report to the user — do not soften or
   rephrase a rejected claim into the output, remove it entirely.
3. You are not permitted to accept a claim because it "sounds
   plausible" or matches your own background knowledge. Absence of a
   verifiable source is grounds for rejection, full stop.

Discrepancy check:
4. Compare CaseState.area_sqm_stated against
   CaseState.area_sqm_from_document (if both present). If they differ
   by any amount, do not silently pick one. Output a structured
   conflict record with both values and their sources, and set the
   case to require explicit user resolution before readiness can
   increase.

Output strictly as JSON: {accepted_evidence: [...], rejected_evidence:
[...], conflicts: [...]}.
```

---

### 2.6 Documentation / Packaging Agent

**Role:** assembles the final artifacts (journey plan, checklist, evidence report, fee estimate, application packet, decision log) from the now-verified `CaseState`. Mostly templating, with a thin LLM pass for the readable summary only.

```
SYSTEM PROMPT — Documentation Agent

You are the Documentation agent for GovFlow KSA. You receive a fully
verified CaseState (post-Verifier) and produce the final user-facing
report.

RULES:
1. Only include requirements/evidence that were accepted by the
   Verifier agent. Never re-introduce a rejected claim.
2. Every number that is not directly sourced (e.g. general cost
   estimates like equipment or contingency) must be explicitly labeled
   "AI ESTIMATE — not an official fee."
3. Do not invent milestones, dates, or next steps beyond what is
   derivable from the current CaseState.

Produce the six sections: Journey, Checklist, Evidence Report, Fee
Estimate, Application Packet Draft, Decision Log — in that order, as
structured JSON the frontend will render.
```

---

## 3. LangGraph wiring (static graph, conditional edges — not runtime-compiled)

```
START
  → intake_planner
      → (conditional: branch == "food_business")
          → regulation_router (food-specific query set)
      → (conditional: branch == "general_business")
          → regulation_router (general query set)
  → [parallel] municipal_location (A2A call)  +  tax_financial (deterministic)
  → verifier
  → (conditional: conflicts non-empty)
      → HUMAN_RESOLUTION_INTERRUPT  → back to verifier
  → human_approval_gate (LangGraph interrupt)
  → documentation_agent
  → (conditional: user clicks "Continue Application")
      → mock_execution_adapter (MCP, auth-gated)  → END
```

Use LangGraph's `interrupt()` for both human-in-the-loop gates (conflict resolution and final approval) rather than polling — this is the correct pattern from the course material for pausing a graph mid-execution for user input.

---

## 4. Backend project structure

```
govflow-backend/
├── app/
│   ├── main.py                 # FastAPI app, OpenResponses-style endpoint
│   ├── state.py                 # CaseState, Evidence, RequirementItem (Pydantic)
│   ├── graph.py                 # LangGraph StateGraph wiring (section 3)
│   ├── agents/
│   │   ├── intake_planner.py
│   │   ├── regulation_router.py
│   │   ├── tax_financial.py     # deterministic + thin wrapper
│   │   ├── verifier.py
│   │   └── documentation.py
│   ├── tools/
│   │   ├── gov_search.py        # Tavily wrapper, include_domains locked
│   │   ├── gov_fetch.py         # domain-checked fetch
│   │   └── competitor_lookup.py # OSM Overpass client
│   ├── mcp/
│   │   ├── municipal_server.py  # FastMCP server for the Municipal & Location agent
│   │   ├── execution_adapter.py # mock Balady submission tool, auth-gated
│   │   └── agent_card.py        # /.well-known/agent-card.json for both services
│   └── config/
│       └── allowlist.py         # the domain list from section 0, single source of truth
├── data/
│   └── gov_corpus/              # pre-scraped Balady/ZATCA/MCI pages (see build order)
├── tests/
├── docker-compose.yml           # case-officer + municipal-location services
├── Dockerfile.case-officer
├── Dockerfile.municipal
└── requirements.txt
```

---

## 5. Frontend — React + Vite

**Why this fits cleanly with the backend:** FastAPI streams agent progress over Server-Sent Events (SSE) or WebSocket; React consumes that stream to update the agent-roster sidebar and progress bar live, which is exactly the "watch the agents work" demo moment from the plan.

```
govflow-frontend/
├── index.html
├── vite.config.ts
├── package.json
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/
│   │   └── caseStream.ts        # SSE/WebSocket client to the FastAPI backend
│   ├── components/
│   │   ├── GoalInput.tsx        # the single-sentence entry point
│   │   ├── ProgressBar.tsx      # readiness_pct
│   │   ├── AgentRoster.tsx      # live agent status sidebar
│   │   ├── EvidenceLog.tsx      # timestamped agent decision trace
│   │   ├── ConflictModal.tsx    # the lease-area discrepancy resolution UI
│   │   ├── ApprovalGate.tsx     # human-in-the-loop approve/reject
│   │   └── ArtifactTabs.tsx     # journey / checklist / evidence / fees / packet
│   ├── types/
│   │   └── caseState.ts         # mirrors the backend Pydantic schema
│   └── styles/
└── .env                          # VITE_API_BASE_URL
```

**Key integration point:** define `caseState.ts` types as a direct TypeScript mirror of the Python `CaseState` Pydantic model (section 1) so the frontend never guesses field shapes — regenerate it from the Pydantic schema if you want to avoid drift (`pydantic` → JSON Schema → a codegen step, optional but worth it if time allows).

State management: React Context or Zustand is enough here — this app has one active case at a time in the demo, no need for Redux-level machinery.

---

## 6. APIs and tools required

| Need | Recommended | Notes |
|---|---|---|
| Web search restricted to allowlist | **Tavily API** (`include_domains` parameter) | Has a free tier; this is the actual anti-hallucination enforcement point, not just the prompt |
| Location/competitor data | **OpenStreetMap Overpass + Nominatim** | Free, no key, no billing account — the safe default for demo day |
| Location data (optional upgrade) | Google Places API | Requires a billing-enabled Google Cloud project even for free-tier calls — treat as a "production path" line in your deck, not a demo dependency |
| Document extraction (lease PDF) | **PyMuPDF** (`fitz`) or `pdfplumber` | Local, no API needed, keeps the discrepancy-detection demo dependency-free |
| Agent orchestration | **LangGraph** | Per course curriculum |
| Agent-to-agent protocol | **A2A** (Agent Card + delegation) | Per course Day 3 |
| Tool exposure | **FastMCP** | Per course Day 3 |
| Observability | **LangSmith** | Per course Day 4 — trace every run, including the conflict-resolution branch |
| Auth on sensitive tools | **MCP auth** | Gate the mock Balady submission tool per course Day 4 pattern |
| Backend framework | **FastAPI** | OpenResponses-style streaming endpoint |
| Frontend | **React + Vite** | As requested |

---

## 7. Model recommendations

Match model choice to what each agent actually needs — don't put your most expensive model on every node:

| Agent | Recommended model class | Why |
|---|---|---|
| Intake + Planner | Mid-size instruction model with reliable structured JSON output (course's free-tier Nemotron 30B/70B via OpenRouter is adequate) | Extraction + classification, not deep reasoning |
| Regulation & Service Router | Your strongest available reasoning model (Nemotron 120B/550B tier if available, or whatever top-tier free/course-provided model you have) | This agent's citation discipline matters most — a weaker model is more likely to paraphrase past its retrieved evidence |
| Municipal & Location | Same mid-size model as Intake | Narrow, well-scoped task |
| Tax/Financial | **No LLM in the decision path** (see section 2.4) — only a small model for the one-paragraph explanation wrapper | Keep certainty out of LLM hands where code can be exact |
| Verifier | Your strongest available reasoning model, **temperature 0** | This is your hallucination firewall — don't economize here |
| Documentation | Mid-size model | Templating-heavy, low reasoning need |
| Embeddings (for the hybrid dense+BM25 search over your local regulation corpus) | A multilingual embedding model with strong Arabic support — e.g. `BAAI/bge-m3` or `intfloat/multilingual-e5-large` | Your regulation source pages are partly Arabic; an English-only embedding model will underperform on Arabic legal terminology, which is exactly the nuance the improvements discussion flagged |

Set **temperature 0 (or as close to it as the model allows) on every agent that touches a citation or a numeric claim** — Intake, Regulation Router, Municipal, Verifier. Creative variance has no place in a system whose whole value proposition is not hallucinating.

---

## 8. Build order for Claude Code (phased task list)

**Phase 0 — Corpus & config**
1. Manually collect and save the ~10–15 target pages (Balady commercial-license page, ZATCA VAT page, MCI startup guidance, business.sa registration page) into `data/gov_corpus/` as plain text/markdown.
2. Verify the two unconfirmed domains (GOSI, National Address) against their live sites; add to `config/allowlist.py` only once confirmed.
3. Build `config/allowlist.py` as the single source of truth both the search tool and the prompts reference.

**Phase 1 — State & deterministic core**
4. Implement `state.py` (CaseState, Evidence, RequirementItem).
5. Implement `agents/tax_financial.py` deterministic function + tests (this has no external dependency and can be fully unit-tested first).

**Phase 2 — Retrieval-grounded agents**
6. Implement `tools/gov_search.py` (Tavily wrapper, `include_domains` locked) and `tools/gov_fetch.py`.
7. Implement `agents/intake_planner.py` and `agents/regulation_router.py` with the system prompts in section 2.1–2.2.
8. Implement hybrid search (dense + BM25) over the local corpus from Phase 0.

**Phase 3 — Municipal microservice (A2A)**
9. Implement `mcp/municipal_server.py` as a standalone FastMCP service with its own Agent Card.
10. Implement `tools/competitor_lookup.py` against OSM Overpass.
11. Wire A2A discovery/delegation from the main graph to this service; verify it works as two separately runnable `docker compose` services.

**Phase 4 — Verification & documentation**
12. Implement `agents/verifier.py` (citation enforcement + discrepancy detection) — protect time for this, it's your demo centerpiece.
13. Implement `agents/documentation.py`.

**Phase 5 — Human-in-the-loop & execution**
14. Wire LangGraph `interrupt()` for the conflict-resolution and approval gates.
15. Implement `mcp/execution_adapter.py` (mock Balady submission) behind MCP auth; test both the unauthenticated-fails and authenticated-succeeds cases explicitly.

**Phase 6 — Frontend**
16. Scaffold Vite + React app; implement `GoalInput` → SSE stream → `AgentRoster`/`ProgressBar` live updates.
17. Implement `ConflictModal` and `ApprovalGate` tied to the backend `interrupt()` points.
18. Implement `ArtifactTabs` rendering the six Documentation-agent outputs.

**Phase 7 — Observability & packaging**
19. Turn on LangSmith tracing across both services.
20. Record the end-to-end coffee-shop scenario, capture the trace, write the README and defense deck.

Hand this document to Claude Code phase-by-phase rather than all at once — ask it to complete and test one phase before starting the next, since later phases (frontend, A2A wiring) depend on the earlier ones actually working.

---

## 9. Expanded domain allowlist (verified)

Checked each platform from your list against its live site. Classification matters because your Verifier agent's citation rule ("only cite allowlisted domains") needs a clean list, not a mix of official and consultancy sources.

| Platform | Domain | Status |
|---|---|---|
| Qiwa | `qiwa.sa` | **Confirmed official** — HRSD's digital labor platform |
| GOSI | `gosi.gov.sa` | **Confirmed official** |
| Balady (incl. mobile cart license) | `balady.gov.sa` | **Confirmed official** — already in the base allowlist, includes the mobile-cart-license sub-service |
| SFDA | `sfda.gov.sa` | **Confirmed official** |
| SAIP (trademarks/IP) | `saip.gov.sa` | **Confirmed official** |
| Mudad (WPS payroll) | `mudad.com.sa` | **Not a .gov.sa domain** — it's a payment-processing platform mandated by HRSD but commercially operated. Treat as semi-official: usable for procedural "how WPS works" context, but don't let the Regulation Agent cite it for anything a HIGH-confidence claim depends on. If in doubt, cite the HRSD/Qiwa page describing the WPS requirement instead. |
| Saudi Post / National Address | `splonline.com.sa` | **Not a .gov.sa domain.** Saudi Post is state-owned but this is a commercial-facing domain, not a `.gov.sa` one. Verify the current National Address registration path live before hardcoding — it may now route through `my.gov.sa` or an Absher Business flow instead. |
| Social Development Bank | `sdb.gov.sa` | `.gov.sa` TLD is a strong positive signal but **not independently verified in this session** — confirm the live site during Phase 0 before adding to the hard allowlist. |
| Ministry of Municipal, Rural Affairs & Housing (momah) | `momah.gov.sa` | Same as above — plausible given the `.gov.sa` TLD, **not independently verified in this session**, confirm before hardcoding. |

**Everything else in your pasted source list — astrolabs.com, absherbusiness.com, setupinsaudi.com, cspgroupme.com, motaded.com.sa, mercans.com, arabdreams.com, saftteam.com, baticfirm.com, foodics.com, setupdubai.business, linkedin.com, job-ksa.com, safwahr.com — are consultancy/blog sites, not government sources.** They're useful for you personally to sanity-check what platforms exist, but they must never enter the agent's allowlist or be cited as evidence — this is exactly the class of source the Verifier agent's "reject if not on the allowlist" rule exists to catch, and it's worth mentioning in your defense that you deliberately excluded them even though they contain accurate-sounding information.

---

## 10. Generalizing beyond one business vertical (and applicant types)

You asked for the system to eventually cover restaurant/spa/office/organization/food-truck/other verticals, and Saudi/resident/GCC-national/minor applicant types. This is the right instinct for the *architecture*, but worth separating two different things clearly:

**Generalize the retrieval layer and the agent logic — this is cheap and worth doing now.** Nothing in the agent design (sections 2.1–2.6) is coffee-shop-specific except the demo script. Structure the corpus and the Regulation Agent's query logic by **business category → applicable agencies**, not as one hardcoded path:

```python
# category_map.py — the generalization point
BUSINESS_CATEGORY_AGENCIES = {
    "food_beverage_fixed":  ["mc.gov.sa", "balady.gov.sa", "sfda.gov.sa", "zatca.gov.sa", "qiwa.sa", "gosi.gov.sa"],
    "food_truck_mobile":    ["mc.gov.sa", "balady.gov.sa", "sfda.gov.sa", "zatca.gov.sa"],  # + mobile-cart sub-service
    "personal_care_spa":    ["mc.gov.sa", "balady.gov.sa", "zatca.gov.sa", "qiwa.sa", "gosi.gov.sa"],
    "professional_office":  ["mc.gov.sa", "zatca.gov.sa", "qiwa.sa", "gosi.gov.sa", "saip.gov.sa"],
    "nonprofit_org":        ["mc.gov.sa", "hrsd.gov.sa"],  # note: nonprofit/association registration likely has a
                                                            # different pathway (National Center for NPO Sector) —
                                                            # verify before building this branch, don't assume it
                                                            # mirrors commercial registration
}
```

The Intake+Planner agent's classification step (section 2.1) just needs one more output field — `business_category` — mapped against this table, and the Regulation Agent's `include_domains` call becomes `BUSINESS_CATEGORY_AGENCIES[category]` instead of a hardcoded list. That's a small, worthwhile change.

**Keep the demo script narrow — this doesn't change.** The architecture being general and the *demonstrated* scope being wide are two different claims, and conflating them is exactly the scope-creep risk flagged earlier in this plan. Recommendation: fully build and test **two verticals** end-to-end for the defense — the coffee shop (fixed food/beverage) and the food truck (mobile) — since they share almost the entire agent pipeline but exercise a genuinely different Balady sub-service (`mobile-cart-license-issuance` vs. the standard commercial license). That's a much stronger "look, it generalizes" demo moment than listing five categories in a dropdown where only one has actually been tested.

**On applicant types (Saudi national / resident / GCC national / minor):** treat this the same way — add the field to intake, but don't build four different legal pathways for the capstone. One honest caution: **do not build a "minor applicant" pathway without first verifying the actual legal framework** (guardianship requirements, minimum age for commercial registration) against an official source — I don't have verified current information on this, and it's exactly the kind of claim where a wrong guess in a government-facing tool is worse than not covering the case. If you want to include it, scope it as: the Intake Agent detects the applicant states they're under 18, and the system explicitly declines to proceed with an application pathway, instead outputting "commercial registration for minors requires guardian involvement — consult [official source] directly" rather than fabricating a process. That's honest and still demonstrates responsible-agent design.

---

## 11. Claude Sonnet — what your Pro plan does and doesn't cover

Two different things are easy to conflate here, worth being precise about:

- **Claude Code (using Claude Sonnet to help you *write* the GovFlow backend/frontend code)** — this is covered by your Pro plan. Pro includes Claude Code in the terminal and in supported IDEs (VS Code, JetBrains), sharing the same usage limits as Claude.ai chat. Anthropic's own description frames Pro-tier Claude Code as suited to "light coding work on small repositories" — for a capstone-sized project that's a reasonable fit, though on a heavy day you could hit the shared usage limit faster than on a dedicated coding-only plan.
- **Calling the Claude API from inside your deployed GovFlow agents at runtime** (i.e., your Python agent code making `api.anthropic.com` requests to Claude Sonnet as the reasoning model for Regulation/Verifier/etc.) — **this is a separate product and is NOT included in the Pro plan.** It requires a Claude Console account with its own pay-as-you-go API billing, charged per token, independent of your Pro subscription.

Practical implication for your build: use Claude Code (Pro plan) as your coding assistant throughout — that's exactly what you were already planning to hand this document to. For the agents' actual runtime model calls, you have three options, and it's worth deciding deliberately rather than defaulting:

1. **Course-provided free-tier models** (Nemotron via OpenRouter, as used elsewhere in this plan) — zero additional cost, adequate for most nodes, weaker on the citation-discipline nuance discussed in section 7.
2. **Pay-as-you-go Claude API** (separate Console billing) — noticeably stronger instruction-following for the citation-enforcement-critical agents (Regulation Router, Verifier) specifically, at real per-token cost across your test runs plus the live demo.
3. **Hybrid** — free-tier models for the lower-risk nodes (Intake, Municipal, Documentation) and paid Claude API only for the two agents where citation discipline is make-or-break (Regulation Router, Verifier). This is probably the best cost/quality tradeoff if you're willing to set up Console billing at all.

For current Claude API pricing specifically, check https://docs.claude.com or https://support.claude.com before budgeting — pricing details are exactly the kind of thing that can move, and this plan shouldn't guess at a number.

---

## 12. Frontend — Saudi theme (sage green + lavender)

**Palette:**

| Role | Suggested hex | Notes |
|---|---|---|
| Primary (sage green) | `#87A08C` (base), `#6B8570` (deeper, for text/icons on light bg), `#B8CBB9` (tint, for card backgrounds) | Government-command-center feel without going literal-flag-green |
| Secondary (lavender) | `#B8A9D9` (base), `#8E7BB5` (deeper, for active states), `#E4DCF1` (tint, for subtle highlights/badges) | Use sparingly — as accent (progress bar fill, active agent indicator), not as a dominant field |
| Neutral base | warm off-white (`#FAF9F6`) rather than pure white, plus a dark charcoal (`#2B2B2B`) for text | Keeps the sage/lavender from looking washed out against stark white |
| Status colors (keep separate from the theme palette) | green `#4A9B6E` (satisfied), amber `#D9A441` (warning/unverified), red `#C0564B` (conflict/rejected) | Don't reuse sage green for "satisfied" status — it'll be visually ambiguous against the sage-green theme background |

**Background imagery — one important caveat:** don't source actual photographs of Saudi landmarks (Kingdom Tower, Al-Ula, Diriyah, Masjid al-Haram) from a generic web image search and drop them in as backgrounds — most are copyrighted press/stock photography, and reproducing them isn't something I can help pull directly. Two workable paths instead:
1. **Properly licensed stock** — Unsplash and Pexels both host genuinely royalty-free photography of these locations (search directly on unsplash.com/pexels.com and check the individual photo's license, since not every upload on either site is unrestricted).
2. **Stylized illustration instead of photography** — a low-opacity, single-color-tinted line illustration of a skyline (Kingdom Centre silhouette, Najdi geometric pattern motifs, a simplified Al-Ula rock formation) as a subtle background layer reads as more "considered design system" than a literal photo背景 anyway, and sidesteps the licensing question entirely. This also composites more cleanly with the sage/lavender palette than a busy photograph would.

**Layout suggestion, tying back to the component list in section 5:**
- Full-bleed, low-opacity (8–12%) background illustration behind the whole app shell, sage-green-tinted.
- `AgentRoster` cards use the lavender tint for the "currently active" agent, sage tint for "completed."
- `ProgressBar` fill in the lavender base color (`#B8A9D9`→`#8E7BB5` gradient) — this is the one place a saturated accent color earns visual priority.
- Keep `ConflictModal` and `ApprovalGate` on the neutral off-white/charcoal palette, not the theme colors — these are decision-critical moments and shouldn't compete visually with decorative branding.

---

## 13. Confirmed intake form fields (required vs. optional)

**Required fields** (block progression to the Regulation Agent without these):

| Field | Type | Notes |
|---|---|---|
| Business goal (free text) | textarea | The single-sentence entry point |
| Business category | dropdown | From the `BUSINESS_CATEGORY_AGENCIES` map in section 10 |
| City | dropdown/autocomplete | Scope to cities you've actually built a corpus for (Riyadh at minimum) |
| District | text/autocomplete | Feeds the Municipal & Location agent's competitor lookup |
| Applicant status | dropdown: Saudi national / GCC national / non-GCC resident | Determines which registration pathway applies — do **not** default this silently, an unselected value should block progression, not assume "Saudi national" |
| Estimated area (sqm) | number | Feeds the discrepancy-detection centerpiece against the uploaded lease |
| Expected annual revenue (SAR) | number | Feeds the deterministic VAT assessment |

**Optional fields** (proceed without them, but flag as "readiness-limiting" if absent):

| Field | Type | Notes |
|---|---|---|
| Budget (SAR) | number | Feeds the fee/estimate report, explicitly labeled AI ESTIMATE either way |
| Number of employees | number | Relevant to GOSI/Qiwa/WPS branches if you build them out |
| Timeline / target opening date | date | Feeds the roadmap artifact |
| Applicant age | number | Only collect if you build the minor-applicant handling from section 10 — otherwise omit the field entirely rather than collecting data you don't act on |

**Optional file upload:**

| Accepted types | Purpose |
|---|---|
| PDF | Lease agreements (the discrepancy-detection centerpiece), any other supporting document |
| TXT / plain text | Free-form additional context the user wants the Regulation Agent to consider |
| (Explicitly out of scope for the prototype) | Images, scanned documents needing OCR — PyMuPDF/pdfplumber handle text-layer PDFs; add OCR only if time allows, don't block the centerpiece demo on it |

One frontend note tying back to section 5: model the upload as a distinct `DocumentUpload` component feeding the same `CaseState.area_sqm_from_document` field the Verifier reads — keep the wiring direct rather than routing uploads through a generic "attachments" bucket, since the discrepancy-check depends on that field being populated reliably before the Verifier node runs.
