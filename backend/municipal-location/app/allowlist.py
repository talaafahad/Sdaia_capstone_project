"""Allowlist subset for the Municipal & Location service.

Deliberately narrower than the Case Officer's list: this service may only ever
cite Balady and its parent ministry (implementation plan section 2.3 rule 1).
Giving it the full allowlist would let a prompt-injection or a model slip cite
ZATCA from the municipal node, which the service boundary exists to prevent.

Canonical implementation: ``backend/case-officer/app/config/allowlist.py``.
Duplicated rather than imported because the two services build into separate
containers with separate dependency trees — the cost of microservice independence.
"""

from __future__ import annotations

from urllib.parse import urlsplit

CITABLE_DOMAINS: frozenset[str] = frozenset({"balady.gov.sa", "momah.gov.sa"})

DOMAIN_ENTITY: dict[str, str] = {
    "balady.gov.sa": "Balady",
    "momah.gov.sa": "Ministry of Municipalities and Housing",
}


def registered_domain(url: str) -> str | None:
    """The allowlisted domain a URL belongs to, or None.

    ``.hostname`` strips any ``user:pass@`` prefix, so a credential-spoofed URL
    such as ``https://balady.gov.sa@evil.com/`` correctly resolves to evil.com.
    The leading dot in the suffix test stops ``evilbalady.gov.sa`` matching.
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
    for domain in CITABLE_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return domain
    return None


def is_citable(url: str) -> bool:
    return registered_domain(url) is not None


def entity_for(url: str) -> str | None:
    domain = registered_domain(url)
    return DOMAIN_ENTITY.get(domain) if domain else None


def include_domains() -> list[str]:
    return sorted(CITABLE_DOMAINS)
