"""Guardrail tests for the domain allowlist.

This module is the anti-hallucination enforcement point (implementation plan
section 0), so its failure modes get tested directly rather than assumed.
"""

import pytest

from app.config.allowlist import (
    CITABLE_DOMAINS,
    EXCLUDED_DOMAINS,
    SEARCHABLE_DOMAINS,
    SEMI_OFFICIAL_DOMAINS,
    VERIFICATION,
    cap_confidence,
    entity_for,
    is_citable,
    is_searchable,
    registered_domain,
    tavily_include_domains,
)


class TestMatching:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://balady.gov.sa/en/services/issuing-commercial-license", "balady.gov.sa"),
            ("https://www.gosi.gov.sa/", "gosi.gov.sa"),
            ("https://scr.bc.gov.sa/", "bc.gov.sa"),
            ("https://new.balady.gov.sa/en/services/x", "balady.gov.sa"),
            ("http://zatca.gov.sa/en/", "zatca.gov.sa"),
            ("https://BALADY.GOV.SA/EN/", "balady.gov.sa"),
        ],
    )
    def test_accepts_allowlisted(self, url, expected):
        assert registered_domain(url) == expected

    @pytest.mark.parametrize(
        "url",
        [
            "https://astrolabs.com/saudi-business-setup",
            "https://setupinsaudi.com/",
            "",
            "not-a-url",
            "ftp://balady.gov.sa/file",
            "file:///etc/passwd",
            None,
        ],
    )
    def test_rejects_non_allowlisted(self, url):
        assert registered_domain(url) is None

    def test_suffix_confusion_is_rejected(self):
        """evilbalady.gov.sa must not match balady.gov.sa."""
        assert registered_domain("https://evilbalady.gov.sa/page") is None
        assert registered_domain("https://notzatca.gov.sa/") is None

    def test_domain_as_prefix_of_another_host_is_rejected(self):
        assert registered_domain("https://balady.gov.sa.attacker.com/x") is None

    def test_credential_spoofed_url_is_rejected(self):
        """https://balady.gov.sa@evil.com/ actually resolves to evil.com."""
        assert registered_domain("https://balady.gov.sa@evil.com/") is None
        assert is_citable("https://balady.gov.sa@evil.com/") is False

    def test_excluded_consultancy_domains_never_match(self):
        for domain in EXCLUDED_DOMAINS:
            assert registered_domain(f"https://{domain}/anything") is None


class TestTiers:
    def test_tiers_are_disjoint(self):
        assert not (CITABLE_DOMAINS & SEMI_OFFICIAL_DOMAINS)

    def test_searchable_is_the_union(self):
        assert SEARCHABLE_DOMAINS == CITABLE_DOMAINS | SEMI_OFFICIAL_DOMAINS

    def test_semi_official_is_searchable_but_not_citable(self):
        url = "https://mudad.com.sa/wps"
        assert is_searchable(url) is True
        assert is_citable(url) is False

    def test_official_is_both(self):
        url = "https://zatca.gov.sa/en/vat"
        assert is_searchable(url) is True
        assert is_citable(url) is True

    def test_every_domain_records_how_it_was_verified(self):
        for domain in SEARCHABLE_DOMAINS:
            assert domain in VERIFICATION, f"{domain} has no verification provenance"

    def test_every_domain_has_an_entity_name(self):
        for domain in SEARCHABLE_DOMAINS:
            assert entity_for(f"https://{domain}/"), f"{domain} has no entity name"


class TestConfidenceCap:
    def test_semi_official_cannot_be_high(self):
        """Section 9: a semi-official source may never back a HIGH claim."""
        assert cap_confidence("https://mudad.com.sa/x", "HIGH") == "MEDIUM"
        assert cap_confidence("https://splonline.com.sa/x", "HIGH") == "MEDIUM"

    def test_semi_official_lower_levels_pass_through(self):
        assert cap_confidence("https://mudad.com.sa/x", "LOW") == "LOW"
        assert cap_confidence("https://mudad.com.sa/x", "MEDIUM") == "MEDIUM"

    def test_official_domains_are_uncapped(self):
        assert cap_confidence("https://zatca.gov.sa/x", "HIGH") == "HIGH"

    def test_unknown_domain_floors_to_low(self):
        """A claim that somehow reaches here must not inherit HIGH."""
        assert cap_confidence("https://astrolabs.com/x", "HIGH") == "LOW"


class TestTavilyIntegration:
    def test_default_returns_all_searchable(self):
        assert set(tavily_include_domains()) == set(SEARCHABLE_DOMAINS)

    def test_narrowing_intersects_with_allowlist(self):
        result = tavily_include_domains({"balady.gov.sa", "astrolabs.com"})
        assert result == ["balady.gov.sa"]

    def test_result_is_sorted_and_deterministic(self):
        assert tavily_include_domains() == sorted(tavily_include_domains())
