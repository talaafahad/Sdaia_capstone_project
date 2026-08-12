"""Business category → applicable agencies.

Implementation plan section 10: this is the generalisation point. The Regulation
Router's ``include_domains`` call becomes ``agencies_for(category)`` instead of a
hardcoded list, so adding a vertical is a table edit rather than a code change.

Category keys match the values the frontend submits (``frontend/src/types/intake.ts``).
"""

from __future__ import annotations

from app.config.allowlist import SEARCHABLE_DOMAINS

BusinessCategory = str

BUSINESS_CATEGORY_AGENCIES: dict[BusinessCategory, list[str]] = {
    "food_beverage_fixed": [
        "mc.gov.sa",
        "business.sa",
        "balady.gov.sa",
        "sfda.gov.sa",
        "zatca.gov.sa",
        "qiwa.sa",
        "gosi.gov.sa",
    ],
    # Same pipeline as fixed premises, but exercises Balady's mobile-cart
    # sub-service rather than the standard commercial licence.
    "food_truck_mobile": [
        "mc.gov.sa",
        "business.sa",
        "balady.gov.sa",
        "sfda.gov.sa",
        "zatca.gov.sa",
    ],
    "personal_care_spa": [
        "mc.gov.sa",
        "business.sa",
        "balady.gov.sa",
        "zatca.gov.sa",
        "qiwa.sa",
        "gosi.gov.sa",
    ],
    "professional_office": [
        "mc.gov.sa",
        "business.sa",
        "zatca.gov.sa",
        "qiwa.sa",
        "gosi.gov.sa",
        "saip.gov.sa",
    ],
    # Implementation plan section 10 flags this branch as unverified: non-profit
    # registration likely runs through the National Center for NPO Sector rather
    # than mirroring commercial registration. Kept minimal on purpose — do not
    # extend this row without verifying the actual pathway first.
    "nonprofit_org": [
        "mc.gov.sa",
        "hrsd.gov.sa",
    ],
}

#: Categories whose pathway has been verified end-to-end. Used to warn rather
#: than silently produce a confident-looking journey for an unbuilt vertical.
VERIFIED_CATEGORIES: frozenset[str] = frozenset(
    {"food_beverage_fixed", "food_truck_mobile"}
)

FOOD_CATEGORIES: frozenset[str] = frozenset({"food_beverage_fixed", "food_truck_mobile"})


def agencies_for(category: str | None) -> list[str]:
    """Domains the Regulation Router may search for a category.

    Falls back to every searchable domain when the category is unknown or
    missing — a wider search is safe because the allowlist still bounds it,
    whereas guessing a narrower set could silently hide a real requirement.
    """
    domains = BUSINESS_CATEGORY_AGENCIES.get(category or "")
    if not domains:
        return sorted(SEARCHABLE_DOMAINS)
    return sorted(set(domains) & SEARCHABLE_DOMAINS)


def branch_for(category: str | None) -> str:
    """Conditional-edge branch used by the graph (implementation plan section 2.1)."""
    return "food_business" if category in FOOD_CATEGORIES else "general_business"
