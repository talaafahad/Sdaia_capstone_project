"""FastAPI entrypoint for the Case Officer service.

Exposes exactly the contract the frontend already implements (Phase A):

    POST /api/cases              -> {case_id}
    GET  /api/cases/{id}/stream  -> SSE agent sequence
    POST /api/cases/{id}/resume  -> release an interrupt() gate

Phase C integration is therefore a VITE_API_BASE_URL change and nothing else.

Run with:  uv run uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.tax_financial import assess_vat, tax_financial_node
from app.api import case_runner
from app.config.allowlist import CITABLE_DOMAINS, SEMI_OFFICIAL_DOMAINS
from app.config.settings import settings
from app.llm import llm_available, model_report
from app.mcp.agent_card import case_officer_card
from app.mcp.execution_adapter import (
    NotAuthorised,
    PacketIncomplete,
    submit_to_balady,
)
from app.tools import llm_cache, search_cache
from app.tools.corpus import corpus_stats
from app.tools.doc_extract import extract_document
from app.tools.retrieval import retrieve

app = FastAPI(title="GovFlow KSA — Case Officer", version="0.1.0")

# The Vite dev server runs on a different origin during Phase C.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- meta


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "case-officer",
        "llm_available": llm_available(),
        "langsmith_tracing": settings.langsmith_tracing,
        "langsmith_project": settings.langsmith_project,
        "allowlist": {
            "citable": len(CITABLE_DOMAINS),
            "semi_official": len(SEMI_OFFICIAL_DOMAINS),
        },
        "corpus": corpus_stats(),
        "search_cache": search_cache.stats(),
        "llm_cache": llm_cache.stats(),
    }


@app.get("/.well-known/agent-card.json")
def agent_card() -> dict:
    return case_officer_card()


@app.get("/api/models")
def models() -> dict[str, object]:
    """What each node runs on (handoff doc section 1)."""
    return {"nodes": model_report()}


# --------------------------------------------------------------------------- cases


class CreateCaseRequest(BaseModel):
    intake: dict
    document: dict | None = None


@app.post("/api/cases")
def create_case(request: CreateCaseRequest) -> dict[str, str]:
    if not request.intake:
        raise HTTPException(status_code=400, detail="intake payload is required")
    run = case_runner.create_run(request.intake, request.document)
    return {"case_id": run.case_id}


@app.get("/api/cases/{case_id}/stream")
def stream_case(case_id: str) -> StreamingResponse:
    run = case_runner.get_run(case_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown case")
    if run.thread is None:
        case_runner.start(run)
    return StreamingResponse(
        case_runner.sse_stream(run),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class ResumeRequest(BaseModel):
    kind: str
    conflict_id: str | None = None
    accepted: str | None = None
    decision: str | None = None
    note: str | None = None


@app.post("/api/cases/{case_id}/resume")
def resume_case(case_id: str, request: ResumeRequest) -> dict[str, bool]:
    run = case_runner.get_run(case_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown case")
    if not case_runner.resume(run, request.model_dump(exclude_none=True)):
        raise HTTPException(status_code=409, detail="no gate is currently open for this case")
    return {"ok": True}


@app.post("/api/documents/extract")
async def extract_upload(file: UploadFile) -> dict[str, object]:
    """Extract the premises area from an uploaded lease before the case starts."""
    data = await file.read()
    extracted = extract_document(file.filename or "upload", data)
    return {
        "filename": extracted.filename,
        "kind": extracted.kind,
        "size_bytes": len(data),
        "extracted_area_sqm": extracted.area_sqm,
        "extraction_note": (
            " ".join(extracted.notes)
            if extracted.notes
            else (
                f"Read a leased area of {extracted.area_sqm:g} sqm from the document's "
                f"text layer."
                if extracted.area_sqm is not None
                else "No area found."
            )
        ),
        "area_context": extracted.area_context,
        "has_text_layer": extracted.has_text_layer,
    }


class SubmitRequest(BaseModel):
    auth_token: str | None = None


@app.post("/api/cases/{case_id}/submit")
def submit_case(case_id: str, request: SubmitRequest) -> dict[str, object]:
    """Mock Balady submission behind MCP auth (Phase 5)."""
    run = case_runner.get_run(case_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown case")

    state = run.last_state or {}
    packet = ((state.get("artifacts") or {}).get("application_packet")) or {}
    try:
        receipt = submit_to_balady(packet, state, request.auth_token)
    except NotAuthorised as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PacketIncomplete as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "ok": receipt.ok,
        "reference": receipt.reference,
        "submitted_at": receipt.submitted_at,
        "target_agency": receipt.target_agency,
        "is_mock": receipt.is_mock,
        "notice": receipt.notice,
    }


# --------------------------------------------------------------------------- debug


class VatRequest(BaseModel):
    expected_annual_revenue_sar: float | None = None


@app.post("/api/debug/tax")
def debug_tax(request: VatRequest) -> dict[str, object]:
    return {
        "assessment": assess_vat(request.expected_annual_revenue_sar),
        "state_update": tax_financial_node(
            {"expected_annual_revenue_sar": request.expected_annual_revenue_sar}
        ),
    }


class RetrievalRequest(BaseModel):
    query: str
    node: str = "vat_registration"
    top_k: int = 3


@app.post("/api/debug/retrieve")
def debug_retrieve(request: RetrievalRequest) -> dict[str, object]:
    from app.agents.prompts import NODES, domains_for

    if request.node not in NODES:
        return {"error": f"unknown node {request.node!r}", "known": sorted(NODES)}

    outcome = retrieve(
        request.query,
        domains=set(domains_for(request.node)),
        top_k=request.top_k,
        node=request.node,
    )
    return {
        "path": outcome.path,
        "live_reason": outcome.live_reason,
        "latency_ms": outcome.latency_ms,
        "cached": outcome.cached,
        "log_line": outcome.log_line(),
        "passages": [
            {
                "source_entity": p.source_entity,
                "source_url": p.source_url,
                "retrieved_at": p.retrieved_at,
                "origin": p.origin,
                "excerpt": p.text[:240],
            }
            for p in outcome.passages
        ],
    }
