"""Tests for the business-category → agency map (implementation plan section 10)."""

from app.config.allowlist import SEARCHABLE_DOMAINS
from app.config.category_map import (
    BUSINESS_CATEGORY_AGENCIES,
    agencies_for,
    branch_for,
)

# Mirrors frontend/src/types/intake.ts — drift here breaks intake silently.
FRONTEND_CATEGORIES = {
    "food_beverage_fixed",
    "food_truck_mobile",
    "personal_care_spa",
    "professional_office",
    "nonprofit_org",
}


def test_categories_match_the_frontend_dropdown():
    assert set(BUSINESS_CATEGORY_AGENCIES) == FRONTEND_CATEGORIES


def test_every_mapped_agency_is_allowlisted():
    for category, domains in BUSINESS_CATEGORY_AGENCIES.items():
        for domain in domains:
            assert domain in SEARCHABLE_DOMAINS, f"{category} maps to unlisted {domain}"


def test_agencies_for_known_category():
    domains = agencies_for("food_beverage_fixed")
    assert "balady.gov.sa" in domains
    assert "sfda.gov.sa" in domains
    assert "zatca.gov.sa" in domains


def test_food_truck_excludes_employment_agencies():
    """Mobile carts need no employer registration in the section 10 mapping."""
    domains = agencies_for("food_truck_mobile")
    assert "gosi.gov.sa" not in domains
    assert "qiwa.sa" not in domains


def test_unknown_category_widens_rather_than_guesses():
    """A wider search is still allowlist-bounded; a narrower guess could hide a requirement."""
    assert set(agencies_for("space_tourism")) == set(SEARCHABLE_DOMAINS)
    assert set(agencies_for(None)) == set(SEARCHABLE_DOMAINS)


def test_branch_selection():
    assert branch_for("food_beverage_fixed") == "food_business"
    assert branch_for("food_truck_mobile") == "food_business"
    assert branch_for("professional_office") == "general_business"
    assert branch_for(None) == "general_business"
