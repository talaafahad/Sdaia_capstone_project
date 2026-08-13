"""Runs a case through the graph and turns it into the SSE event stream.

The wire format is the contract the frontend already implements
(``frontend/src/types/events.ts``), unchanged:

    agent_status | state_patch | decision | interrupt | artifacts_ready | done | error

The graph runs on a worker thread and pushes events onto a queue that the SSE
endpoint drains, because LangGraph's ``stream`` is synchronous and a blocking
model call inside an async handler would stall the event loop for every client.

``interrupt()`` surfaces here as a ``__interrupt__`` payload: the run stops, the
event goes out, and the resume endpoint injects the human's answer via
``Command(resume=...)``.
"""

from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from langgraph.types import Command

from app.graph import get_graph
from app.state import FRONTEND_MIRRORED_FIELDS

#: Graph node -> the agent id the frontend roster displays.
NODE_TO_AGENT = {
    "intake_planner": "intake_planner",
    "regulation_router": "regulation_router",
    "municipal_location": "municipal_location",
    "tax_financial": "tax_financial",
    "verifier": "verifier",
    "documentation": "documentation",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class CaseRun:
    case_id: str
    intake: dict
    document: dict | None = None
    events: queue.Queue = field(default_factory=queue.Queue)
    thread: threading.Thread | None = None
    finished: threading.Event = field(default_factory=threading.Event)
    #: Set by the resume endpoint; the worker waits on it at an interrupt.
    resume_value: dict | None = None
    resume_ready: threading.Event = field(default_factory=threading.Event)
    awaiting: str | None = None
    last_state: dict = field(default_factory=dict)
    error: str | None = None

    def emit(self, event: dict) -> None:
        self.events.put({**event, "at": _now()})


_RUNS: dict[str, CaseRun] = {}


def get_run(case_id: str) -> CaseRun | None:
    return _RUNS.get(case_id)


def create_run(intake: dict, document: dict | None) -> CaseRun:
    case_id = f"case_{uuid.uuid4().hex[:10]}"
    run = CaseRun(case_id=case_id, intake=intake, document=document)
    _RUNS[case_id] = run
    return run


def _initial_state(run: CaseRun) -> dict:
    intake = run.intake
    state: dict[str, Any] = {
        "case_id": run.case_id,
        "goal": intake.get("goal") or "",
        "business_category": intake.get("business_category"),
        "business_type": intake.get("business_category"),
        "city": intake.get("city"),
        "district": intake.get("district"),
        "applicant_status": intake.get("applicant_status"),
        "area_sqm_stated": intake.get("area_sqm_stated"),
        "expected_annual_revenue_sar": intake.get("expected_annual_revenue_sar"),
        "budget_sar": intake.get("budget_sar"),
        "employee_count": intake.get("employee_count"),
        "target_opening_date": intake.get("target_opening_date"),
        "applicant_age": intake.get("applicant_age"),
        "requirements": [],
        "evidence_log": [],
        "decision_log": [],
        "conflicts": [],
        "readiness_pct": 0,
        "approval_stage": "none",
        "passage_texts": {},
    }
    if run.document:
        # Feeds CaseState.area_sqm_from_document directly (section 13's note).
        state["area_sqm_from_document"] = run.document.get("extracted_area_sqm")
        state["document_source"] = (
            f"{run.document.get('filename')} — extracted text layer"
            if run.document.get("filename")
            else None
        )
    return state


def _patch_for_frontend(state: dict) -> dict:
    """Only the fields the frontend mirror knows, so its merge stays valid."""
    return {k: v for k, v in state.items() if k in FRONTEND_MIRRORED_FIELDS}


def _run_graph(run: CaseRun) -> None:
    graph = get_graph()
    config = {
        "configurable": {
            "thread_id": run.case_id,
            "progress": lambda agent, status, message=None: run.emit(
                {
                    "type": "agent_status",
                    "agent": NODE_TO_AGENT.get(agent, agent),
                    "status": status,
                    "message": message,
                }
            ),
        },
        "recursion_limit": 50,
    }

    try:
        emitted_decisions = 0
        payload: Any = _initial_state(run)

        while True:
            interrupted = None
            for chunk in graph.stream(payload, config=config, stream_mode="updates"):
                for node_name, update in (chunk or {}).items():
                    if node_name == "__interrupt__":
                        interrupted = update
                        continue
                    if not isinstance(update, dict):
                        continue

                    snapshot = graph.get_state(config).values
                    run.last_state = snapshot

                    patch = _patch_for_frontend(update)
                    # readiness/conflicts live on the snapshot, not every update
                    for key in ("readiness_pct", "conflicts", "approval_stage"):
                        if key in snapshot:
                            patch[key] = snapshot[key]
                    if patch:
                        run.emit({"type": "state_patch", "patch": patch})

                    decisions = snapshot.get("decision_log") or []
                    for entry in decisions[emitted_decisions:]:
                        run.emit({"type": "decision", "entry": entry})
                    emitted_decisions = len(decisions)

                    if node_name == "documentation" and snapshot.get("artifacts"):
                        run.emit(
                            {"type": "artifacts_ready", "artifacts": snapshot["artifacts"]}
                        )

            if interrupted is None:
                break

            # LangGraph reports interrupts as a tuple of Interrupt objects.
            first = interrupted[0] if isinstance(interrupted, (list, tuple)) else interrupted
            value = getattr(first, "value", first)
            run.awaiting = (value or {}).get("kind")
            run.resume_ready.clear()
            run.emit({"type": "interrupt", "interrupt": value})

            run.resume_ready.wait()
            if run.finished.is_set():
                return
            payload = Command(resume=run.resume_value or {})
            run.awaiting = None

        run.emit({"type": "done"})
    except Exception as exc:  # noqa: BLE001 — surfaced to the client as an error event
        run.error = f"{exc.__class__.__name__}: {exc}"
        run.emit({"type": "error", "message": run.error})
    finally:
        run.finished.set()
        run.events.put(None)  # sentinel closes the SSE generator


def start(run: CaseRun) -> None:
    run.thread = threading.Thread(target=_run_graph, args=(run,), daemon=True)
    run.thread.start()


def resume(run: CaseRun, value: dict) -> bool:
    if run.finished.is_set() or run.awaiting is None:
        return False
    run.resume_value = value
    run.resume_ready.set()
    return True


def stop(run: CaseRun) -> None:
    run.finished.set()
    run.resume_ready.set()


#: A retrieval node can sit silent for minutes while a free-tier model queues.
#: Without a heartbeat the connection looks dead to anything with a read
#: timeout — browsers, reverse proxies, and the test client all drop it. SSE
#: comment lines are ignored by EventSource, so this is invisible to the app.
SSE_KEEPALIVE_SECONDS = 15


def sse_stream(run: CaseRun) -> Iterator[str]:
    """Drain the queue as text/event-stream frames, with keepalive comments."""
    import json

    while True:
        try:
            event = run.events.get(timeout=SSE_KEEPALIVE_SECONDS)
        except queue.Empty:
            if run.finished.is_set():
                break
            yield ": keepalive\n\n"
            continue
        if event is None:
            break
        yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
