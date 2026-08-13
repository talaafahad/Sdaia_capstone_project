"""A2A Agent Cards for both services.

Served at ``/.well-known/agent-card.json``. The Case Officer discovers the
Municipal & Location service by fetching its card and reading the skill list,
rather than having the endpoint hardcoded in the graph.
"""

from __future__ import annotations

import os

CASE_OFFICER_URL = os.environ.get("CASE_OFFICER_URL", "http://localhost:8000")
MUNICIPAL_URL = os.environ.get("MUNICIPAL_SERVICE_URL", "http://localhost:8001")


def case_officer_card() -> dict:
    return {
        "protocolVersion": "0.2.0",
        "name": "GovFlow KSA — Case Officer",
        "description": (
            "Orchestrates a Saudi government business-setup journey: intake, "
            "regulation routing, deterministic tax assessment, verification and "
            "document packaging."
        ),
        "url": CASE_OFFICER_URL,
        "version": "0.1.0",
        "capabilities": {"streaming": True, "pushNotifications": False},
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json", "text/event-stream"],
        "skills": [
            {
                "id": "run_case",
                "name": "Run a business-setup case",
                "description": (
                    "Takes an intake payload and streams agent progress, "
                    "human-in-the-loop interrupts and the final artifacts."
                ),
                "tags": ["orchestration", "government", "saudi-arabia"],
            }
        ],
    }


def municipal_card() -> dict:
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
                    "Retrieves municipal licensing requirements for a business "
                    "activity from balady.gov.sa only. Never asserts approval."
                ),
                "tags": ["balady", "municipal", "licensing"],
            },
            {
                "id": "competitor_lookup",
                "name": "Nearby competitor count",
                "description": (
                    "Raw count of similar establishments near a district centroid "
                    "from OpenStreetMap Overpass. Not a suitability judgment."
                ),
                "tags": ["openstreetmap", "location"],
            },
        ],
    }
