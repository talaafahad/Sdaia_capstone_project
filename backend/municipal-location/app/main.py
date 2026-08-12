"""FastAPI entrypoint for the Municipal & Location A2A microservice.

Skeleton only — the FastMCP server, Agent Card and OSM Overpass competitor
lookup arrive in Phase B (implementation plan Phase 3).

Run with:  uv run uvicorn app.main:app --reload --port 8001
"""

from fastapi import FastAPI

from app.settings import settings

app = FastAPI(
    title="GovFlow KSA — Municipal & Location",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe; also confirms .env loaded and required keys are present."""
    return {"status": "ok", "service": "municipal-location"}
