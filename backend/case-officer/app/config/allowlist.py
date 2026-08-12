"""Single source of truth for the government-domain allowlist.

Implementation plan sections 0 and 9. Both the Tavily ``include_domains`` tool
config and the agent system prompts read from this module — the tool-level
restriction is the real guardrail, the prompt-level one is defense in depth.

Two tiers, per section 9:

* ``CITABLE_DOMAINS`` — confirmed official sources. Evidence may carry any
  confidence level.
* ``SEMI_OFFICIAL_DOMAINS`` — state-mandated but commercially operated
  (Mudad, Saudi Post/SPL). Searchable for procedural context, but confidence is
  hard-capped at MEDIUM by :func:`cap_confidence` so no HIGH-confidence claim
  can ever rest on one. The cap is enforced in code, not by asking a model
  nicely.

Every domain below was checked against its live site on 2026-08-12; see
:data:`VERIFICATION` for how each one was confirmed.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

Confidence = Literal["HIGH", "MEDIUM", "LOW"]

# ---------------------------------------------------------------------------
# Tier 1 — confirmed official, citable at any confidence level
# ---------------------------------------------------------------------------

CITABLE_DOMAINS: frozenset[str] = frozenset(
    {
        "business.sa",  # Saudi Business Center
        "bc.gov.sa",  # Saudi Business Center (incl. scr.bc.gov.sa)
        "mc.gov.sa",  # Ministry of Commerce
        "balady.gov.sa",  # Balady municipal platform
        "zatca.gov.sa",  # Zakat, Tax and Customs Authority
        "dga.gov.sa",  # Digital Government Authority
        "monshaat.gov.sa",  # Monsha'at (SME authority)
        "sdaia.gov.sa",  # SDAIA
        "my.gov.sa",  # National unified portal
        "qiwa.sa",  # Qiwa (HRSD labor platform)
        "gosi.gov.sa",  # General Organization for Social Insurance
        "sfda.gov.sa",  # Saudi Food and Drug Authority
        "saip.gov.sa",  # Saudi Authority for Intellectual Property
        "hrsd.gov.sa",  # Ministry of Human Resources and Social Development
        "sdb.gov.sa",  # Social Development Bank
        "momah.gov.sa",  # Ministry of Municipalities and Housing
    }
)

# ---------------------------------------------------------------------------
# Tier 2 — semi-official: state-mandated, commercially operated, NOT .gov.sa
# ---------------------------------------------------------------------------

SEMI_OFFICIAL_DOMAINS: frozenset[str] = frozenset(
    {
        "mudad.com.sa",  # WPS payroll platform, mandated by HRSD but commercial
        "splonline.com.sa",  # Saudi Post / SPL — state-owned, commercial-facing domain
    }
)

SEARCHABLE_DOMAINS: frozenset[str] = CITABLE_DOMAINS | SEMI_OFFICIAL_DOMAINS

#: Highest confidence an Evidence object may carry, keyed by registered domain.
MAX_CONFIDENCE: dict[str, Confidence] = {d: "MEDIUM" for d in SEMI_OFFICIAL_DOMAINS}

#: ``Evidence.source_entity`` for a given domain — never let a model invent this.
DOMAIN_ENTITY: dict[str, str] = {
    "business.sa": "Saudi Business Center",
    "bc.gov.sa": "Saudi Business Center",
    "mc.gov.sa": "Ministry of Commerce",
    "balady.gov.sa": "Balady",
    "zatca.gov.sa": "ZATCA",
    "dga.gov.sa": "Digital Government Authority",
    "monshaat.gov.sa": "Monsha'at",
    "sdaia.gov.sa": "SDAIA",
    "my.gov.sa": "National Unified Portal",
    "qiwa.sa": "Qiwa",
    "gosi.gov.sa": "GOSI",
    "sfda.gov.sa": "SFDA",
    "saip.gov.sa": "SAIP",
    "hrsd.gov.sa": "HRSD",
    "sdb.gov.sa": "Social Development Bank",
    "momah.gov.sa": "Ministry of Municipalities and Housing",
    "mudad.com.sa": "Mudad",
    "splonline.com.sa": "Saudi Post (SPL)",
}

# ---------------------------------------------------------------------------
# Verification provenance — how each domain was confirmed, for the defense
# ---------------------------------------------------------------------------

VERIFICATION: dict[str, str] = {
    "business.sa": "2026-08-12 HTTP 200, Saudi Business Center portal",
    "bc.gov.sa": "2026-08-12 scr.bc.gov.sa title 'Saudi Business Center'",
    "mc.gov.sa": "2026-08-12 HTTP 200, Ministry of Commerce portal",
    "balady.gov.sa": "2026-08-12 HTTP 200, Balady portal",
    "zatca.gov.sa": "2026-08-12 HTTP 200, ZATCA portal",
    "dga.gov.sa": "2026-08-12 HTTP 200, Digital Government Authority",
    "monshaat.gov.sa": "2026-08-12 HTTP 200, Monsha'at",
    "sdaia.gov.sa": "2026-08-12 HTTP 200, SDAIA",
    # Cloudflare bot protection blocked automated verification. Retained on the
    # strength of implementation plan section 0, which lists it as confirmed by
    # the plan author. Recorded here rather than silently assumed.
    "my.gov.sa": "2026-08-12 BLOCKED by Cloudflare challenge; rests on plan section 0",
    "qiwa.sa": "2026-08-12 HTTP 200 (JS shell, no server-rendered text)",
    "gosi.gov.sa": "2026-08-12 title 'المؤسسة العامة للتأمينات الاجتماعية' (GOSI)",
    "sfda.gov.sa": "2026-08-12 HTTP 200, SFDA portal",
    "saip.gov.sa": "2026-08-12 HTTP 200, SAIP portal",
    "hrsd.gov.sa": "2026-08-12 title 'الموقع الرسمي لوزارة الموارد البشرية والتنمية الاجتماعية'",
    "sdb.gov.sa": "2026-08-12 title 'بنك التنمية الاجتماعية'",
    # NOTE: the ministry's live name is now "وزارة البلديات والإسكان" (Ministry of
    # Municipalities and Housing) — "Rural Affairs" was dropped since the plan
    # was written.
    "momah.gov.sa": "2026-08-12 title 'وزارة البلديات والإسكان'",
    "mudad.com.sa": "2026-08-12 HTTP 200, JS shell; confirmed NOT .gov.sa — semi-official",
    "splonline.com.sa": "2026-08-12 title 'البريد السعودي | سبل'; confirmed NOT .gov.sa — semi-official",
}

#: Domains deliberately excluded. Kept here so the exclusion is a documented
#: decision rather than an oversight — implementation plan section 9.
EXCLUDED_DOMAINS: dict[str, str] = {
    "astrolabs.com": "consultancy blog, not a government source",
    "absherbusiness.com": "consultancy blog, not a government source",
    "setupinsaudi.com": "consultancy blog, not a government source",
    "cspgroupme.com": "consultancy blog, not a government source",
    "motaded.com.sa": "consultancy blog, not a government source",
    "mercans.com": "consultancy blog, not a government source",
    "arabdreams.com": "consultancy blog, not a government source",
    "saftteam.com": "consultancy blog, not a government source",
    "baticfirm.com": "consultancy blog, not a government source",
    "foodics.com": "vendor site, not a government source",
    "setupdubai.business": "consultancy blog, and not Saudi",
    "linkedin.com": "social platform",
    "job-ksa.com": "job board, not a government source",
    "safwahr.com": "consultancy blog, not a government source",
}


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def registered_domain(url: str) -> str | None:
    """Return the allowlisted domain a URL belongs to, or None.

    A URL matches a domain when its host is exactly that domain or a subdomain
    of it. The leading dot in the suffix check matters: ``evilbalady.gov.sa``
    must NOT match ``balady.gov.sa``.

    Only http(s) URLs are considered. ``urlsplit().hostname`` strips any
    ``user:pass@`` prefix, so a credential-spoofed URL such as
    ``https://balady.gov.sa@evil.com/`` resolves to host ``evil.com`` and is
    correctly rejected.
    """
    if not url or not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        return None
    for domain in SEARCHABLE_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return domain
    return None


def is_searchable(url: str) -> bool:
    """True when the URL may be retrieved at all (either tier)."""
    return registered_domain(url) is not None


def is_citable(url: str) -> bool:
    """True when a claim may cite this URL as evidence (tier 1 only)."""
    return registered_domain(url) in CITABLE_DOMAINS


def entity_for(url: str) -> str | None:
    """Authoritative ``Evidence.source_entity`` for a URL's domain."""
    domain = registered_domain(url)
    return DOMAIN_ENTITY.get(domain) if domain else None


_RANK: dict[str, int] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def cap_confidence(url: str, confidence: Confidence) -> Confidence:
    """Lower a claimed confidence to the ceiling its source domain allows.

    Semi-official domains cap at MEDIUM (section 9). An unknown domain caps at
    LOW — it should already have been rejected upstream, but a claim that
    somehow reaches here must not inherit HIGH by default.
    """
    domain = registered_domain(url)
    if domain is None:
        return "LOW"
    ceiling = MAX_CONFIDENCE.get(domain)
    if ceiling is None:
        return confidence
    return confidence if _RANK[confidence] <= _RANK[ceiling] else ceiling


def tavily_include_domains(domains: frozenset[str] | set[str] | None = None) -> list[str]:
    """Domain list for a Tavily ``include_domains`` call.

    Defaults to every searchable domain. Pass a narrower set to scope a query
    to one business category (see :mod:`app.config.category_map`) or to a single
    agency, as the Municipal agent does with ``balady.gov.sa``.
    """
    selected = SEARCHABLE_DOMAINS if domains is None else (set(domains) & SEARCHABLE_DOMAINS)
    return sorted(selected)
