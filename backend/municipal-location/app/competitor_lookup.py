"""Nearby competitor count via OpenStreetMap Overpass + Nominatim.

Free and keyless, which is the point (implementation plan section 6): no billing
account is a demo-day dependency. Google Places is a production-path line in the
deck, not the default.

This module returns a COUNT and nothing else. Implementation plan section 2.3
rule 2 forbids converting it into a suitability score, rating or recommendation,
so no such function exists here to be called by mistake.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")

# Nominatim's usage policy requires a real identifying User-Agent.
UA = "GovFlowKSA/0.1 (capstone project; contact via repository)"

TIMEOUT = 25

#: OSM tags that correspond to each business category.
CATEGORY_TAGS: dict[str, list[str]] = {
    "food_beverage_fixed": ['amenity~"cafe|restaurant|fast_food"'],
    "food_truck_mobile": ['amenity~"fast_food|food_court"'],
    "personal_care_spa": ['shop~"beauty|hairdresser"', 'leisure~"spa"'],
    "professional_office": ['office'],
    "nonprofit_org": ['office~"ngo|association"'],
}

DEFAULT_RADIUS_M = 500

AI_ESTIMATE_LABEL = "AI ESTIMATE — competitor count only, not a suitability judgment."


@dataclass
class CompetitorResult:
    ok: bool
    count: int | None
    radius_m: int
    source: str
    label: str = AI_ESTIMATE_LABEL
    lat: float | None = None
    lon: float | None = None
    resolved_place: str | None = None
    #: "district" | "place" | "street" — how confidently the centroid was found.
    #: A "street" match means the count is centred on a road of that name, not
    #: the district, and is reported so it can be discounted rather than trusted.
    match_quality: str | None = None
    reason: str = "ok"
    notes: list[str] = field(default_factory=list)


#: Nominatim viewbox per supported city: (min_lon, min_lat, max_lon, max_lat).
#: Free-text geocoding picks the wrong governorate readily — "Al-Olaya, Riyadh"
#: resolved to Al Olaya in Al Quwayiyah, ~160 km away, and then reported zero
#: nearby competitors. A wrong location that yields a confident-looking count is
#: worse than an obvious failure, so the query is bounded to the city's box and
#: a result outside it is refused rather than silently used.
CITY_VIEWBOX: dict[str, tuple[float, float, float, float]] = {
    "riyadh": (46.35, 24.40, 47.15, 25.10),
    "jeddah": (38.95, 21.25, 39.40, 21.90),
    "dammam": (49.85, 26.25, 50.30, 26.65),
    "makkah": (39.70, 21.25, 40.05, 21.60),
}


def _viewbox_for(city: str) -> tuple[float, float, float, float] | None:
    key = (city or "").strip().lower().replace("al-", "").replace("al ", "").strip()
    # Guard the empty string explicitly: "" is a substring of every city name,
    # so a case with no city would otherwise be geocoded as if it were Riyadh.
    if not key:
        return None
    for name, box in CITY_VIEWBOX.items():
        if name in key or key in name:
            return box
    return None


def _within(lat: float, lon: float, box: tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = box
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


#: OSM feature types that represent an actual district rather than a street.
_DISTRICT_TYPES = {
    "suburb",
    "neighbourhood",
    "quarter",
    "city_district",
    "district",
    "town",
    "village",
    "administrative",
}


def _match_rank(item: dict) -> int:
    """Prefer a district polygon over a street that happens to share its name.

    Searching "Al Malqa, Riyadh" returns six ``class=highway`` results — roads
    named Al Malqa scattered across the city — before any district feature.
    Taking the first hit centres the competitor search on an arbitrary street.
    """
    cls, typ = item.get("class"), item.get("type")
    if cls in ("place", "boundary") and typ in _DISTRICT_TYPES:
        return 0
    if cls in ("place", "boundary"):
        return 1
    return 2


def _match_quality(item: dict) -> str:
    rank = _match_rank(item)
    if rank == 0:
        return "district"
    if rank == 1:
        return "place"
    return "street"  # a road of that name, not the district itself


def geocode_district(district: str, city: str, country: str = "Saudi Arabia"):
    """Resolve a district to a centroid. Returns (lat, lon, display_name) or None.

    Bounded to the city's viewbox where one is known, so a same-named district
    in another governorate cannot be returned. Any candidate falling outside the
    box is discarded, and if none survive the lookup fails honestly rather than
    producing a count for the wrong place.
    """
    query = ", ".join(p for p in (district, city, country) if p)
    box = _viewbox_for(city)

    params: dict[str, object] = {
        "q": query,
        "format": "json",
        "limit": 8,
        "countrycodes": "sa",
        "addressdetails": 1,
    }
    if box:
        params["viewbox"] = ",".join(str(v) for v in box)
        params["bounded"] = 1

    try:
        response = httpx.get(
            NOMINATIM_URL,
            params=params,
            headers={"User-Agent": UA, "Accept-Language": "en"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        results = response.json()
    except Exception:  # noqa: BLE001 — a geocode failure is a lookup failure
        return None
    if not results:
        return None

    city_key = (city or "").strip().lower()
    candidates = []
    for item in results:
        try:
            lat, lon = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if box and not _within(lat, lon, box):
            continue  # right name, wrong governorate
        name = item.get("display_name", "")
        candidates.append(
            (
                _match_rank(item),
                0 if city_key and city_key in name.lower() else 1,
                lat,
                lon,
                name,
                _match_quality(item),
            )
        )

    if not candidates:
        return None

    candidates.sort(key=lambda c: (c[0], c[1]))
    _, _, lat, lon, name, quality = candidates[0]
    return lat, lon, name, quality


def lookup_nearby_competitors(
    district: str,
    city: str,
    business_category: str = "food_beverage_fixed",
    radius_m: int = DEFAULT_RADIUS_M,
) -> CompetitorResult:
    """Raw count of similar establishments near a district centroid.

    Reports failure honestly rather than guessing — an invented count would be
    exactly the kind of unverifiable number this project exists to avoid.
    """
    located = geocode_district(district, city)
    if located is None:
        return CompetitorResult(
            ok=False,
            count=None,
            radius_m=radius_m,
            source="OpenStreetMap Nominatim",
            reason="district_not_geocoded",
            notes=[
                f"Could not resolve '{district}, {city}' to coordinates inside the "
                f"{city} bounding box. No count is reported — a centroid from another "
                "governorate would give a confident-looking but meaningless number."
            ],
        )

    lat, lon, place, quality = located
    extra_notes: list[str] = []
    if quality == "street":
        extra_notes.append(
            f"Centroid came from a STREET named '{district}', not a district boundary. "
            "The count below is centred on that road and should be discounted."
        )
    tags = CATEGORY_TAGS.get(business_category) or CATEGORY_TAGS["food_beverage_fixed"]
    clauses = "\n".join(f'  node[{tag}](around:{radius_m},{lat},{lon});' for tag in tags)
    query = f"[out:json][timeout:{TIMEOUT}];\n(\n{clauses}\n);\nout count;"

    try:
        response = httpx.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": UA},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        return CompetitorResult(
            ok=False,
            count=None,
            radius_m=radius_m,
            source="OpenStreetMap Overpass",
            lat=lat,
            lon=lon,
            resolved_place=place,
            match_quality=quality,
            reason=f"overpass_error:{exc.__class__.__name__}",
            notes=[*extra_notes, "The competitor lookup failed; no count is available."],
        )

    count = None
    for element in payload.get("elements") or []:
        tags_out = element.get("tags") or {}
        if "total" in tags_out:
            try:
                count = int(tags_out["total"])
            except (TypeError, ValueError):
                count = None
            break

    if count is None:
        return CompetitorResult(
            ok=False,
            count=None,
            radius_m=radius_m,
            source="OpenStreetMap Overpass",
            lat=lat,
            lon=lon,
            resolved_place=place,
            match_quality=quality,
            reason="no_count_in_response",
            notes=extra_notes,
        )

    return CompetitorResult(
        ok=True,
        count=count,
        radius_m=radius_m,
        source="OpenStreetMap Overpass",
        lat=lat,
        lon=lon,
        resolved_place=place,
        match_quality=quality,
        notes=extra_notes,
    )
