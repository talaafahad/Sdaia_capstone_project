"""FastAPI entrypoint for the Case Officer service.

Skeleton only — the LangGraph wiring, agent nodes and the SSE streaming
endpoint arrive in Phase B (implementation plan Phases 0-5).

Run with:  uv run uvicorn app.main:app --reload --port 8000
"""

from fastapi import FastAPI

from app.config.settings import settings

app = FastAPI(
    title="GovFlow KSA — Case Officer",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, object]:
    """Liveness probe; also confirms .env loaded and required keys are present."""
    return {
        "status": "ok",
        "service": "case-officer",
        "langsmith_tracing": settings.langsmith_tracing,
        "langsmith_project": settings.langsmith_project,
    }
