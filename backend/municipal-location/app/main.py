"""FastAPI entrypoint for the Municipal & Location A2A microservice.

Runs independently of the Case Officer and is discovered via its Agent Card at
``/.well-known/agent-card.json`` (implementation plan section 2.3, Phase 3).

Run with:  uv run uvicorn app.main:app --reload --port 8001
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from pydantic import BaseModel

from app.agent import MODEL, competitor_context, llm_available, municipal_requirements
from app.allowlist import include_domains
from app.retrieval import build_index
from app.settings import settings

MUNICIPAL_URL = os.environ.get("MUNICIPAL_SERVICE_URL", "http://localhost:8001")

app = FastAPI(
    title="GovFlow KSA — Municipal & Location",
    version="0.1.0",
)


def agent_card() -> dict:
    return {
        "protocolVersion": "0.2.0",
        "name": "GovFlow KSA — Municipal & Location",
        "description": (
            "Independent A2A service owning Balady municipal requirements and "
            "OpenStreetMap competitor context for a district."
        ),
        "url": MUNICIPAL_URL,
        "version": "0.1.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": [
            {
                "id": "municipal_requirements",
                "name": "Balady municipal requirements",
                "description": (
                    "Retrieves municipal licensing requirements from balady.gov.sa "
                    "only. Never asserts approval."
                ),
                "tags": ["balady", "municipal", "licensing"],
                "endpoint": "/a2a/municipal_requirements",
            },
            {
                "id": "competitor_lookup",
                "name": "Nearby competitor count",
                "description": (
                    "Raw count of similar establishments near a district centroid "
                    "from OpenStreetMap Overpass. Not a suitability judgment."
                ),
                "tags": ["openstreetmap", "location"],
                "endpoint": "/a2a/competitor_lookup",
            },
        ],
    }


@app.get("/.well-known/agent-card.json")
def well_known_agent_card() -> dict:
    return agent_card()


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "municipal-location",
        "model": MODEL,
        "llm_available": llm_available(),
        "citable_domains": include_domains(),
        "corpus_chunks": len(build_index()),
        "tavily_configured": bool(settings.tavily_api_key),
    }


class MunicipalRequest(BaseModel):
    business_category: str | None = None
    city: str | None = None
    district: str | None = None
    area_sqm_stated: float | None = None


@app.post("/a2a/municipal_requirements")
def a2a_municipal_requirements(request: MunicipalRequest) -> dict:
    return municipal_requirements(request.model_dump())


class CompetitorRequest(BaseModel):
    business_category: str | None = "food_beverage_fixed"
    city: str | None = None
    district: str | None = None
    radius_m: int = 500


@app.post("/a2a/competitor_lookup")
def a2a_competitor_lookup(request: CompetitorRequest) -> dict:
    return competitor_context(request.model_dump())
