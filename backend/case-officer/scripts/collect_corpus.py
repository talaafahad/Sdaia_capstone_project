"""Phase 0 corpus collector.

Fetches the target government pages listed in TARGETS and writes each one to
``data/gov_corpus/<slug>.md`` with YAML frontmatter carrying its provenance
(source URL, entity, retrieval timestamp), so an Evidence object can always be
traced back to the exact page and moment it came from.

This is a build-time tool, not a runtime dependency — nothing in ``app/`` imports
it, and its bs4/markdownify deps live in the dev group.

    uv run python scripts/collect_corpus.py            # fetch all
    uv run python scripts/collect_corpus.py --dry-run  # list targets only

Every URL here must be on the allowlist; the script refuses anything else.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pymupdf
import truststore
import yaml
from bs4 import BeautifulSoup
from markdownify import markdownify

# Several Saudi government sites serve a chain that certifi does not carry but
# the OS trust store does (curl succeeds where a bare httpx client fails).
# Use the system trust store rather than disabling verification — provenance is
# the whole point of this corpus.
truststore.inject_into_ssl()

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.allowlist import entity_for, is_searchable, registered_domain  # noqa: E402

CORPUS_DIR = Path(__file__).resolve().parents[3] / "data" / "gov_corpus"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


@dataclass
class Target:
    slug: str
    url: str
    title: str
    categories: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    kind: str = "html"  # "html" | "pdf"


# Chrome that appears on every .gov.sa portal page. A page consisting only of
# these lines has no retrievable content, however many characters it contains —
# a raw length threshold alone lets those through (ZATCA's FAQ pages are 5k
# chars of pure boilerplate around a client-rendered "Loading...").
BOILERPLATE_MARKERS = [
    "A government website registered with the Government of the Kingdom of Saudi Arabia",
    "Links to official Saudi websites end with gov.sa",
    "All links to official websites of government agencies",
    "Government websites use the HTTPS protocol for encryption",
    "Secure websites in the Kingdom of Saudi Arabia use the HTTPS protocol",
    "Registered on Digital Government Authority",
    "Comments and Suggestions",
    "For any inquiries or notes about authority services",
    "Add a comment",
    "Voice Commands",
    "Greyscale Mode",
    "Font Size",
    "Skip to main content",
    "Loading...",
    "Contact Us",
    "Listen",
    "Login",
]


def strip_boilerplate(text: str) -> str:
    """Remove known portal chrome so content length means what it says."""
    kept: list[str] = []
    for line in text.splitlines():
        bare = line.lstrip("#* -+").strip()
        if not bare:
            kept.append(line)
            continue
        if any(marker.lower() in bare.lower() for marker in BOILERPLATE_MARKERS):
            continue
        kept.append(line)
    out = "\n".join(kept)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


TARGETS: list[Target] = [
    # --- Balady: municipal licensing (the core of the coffee-shop vertical) ---
    Target(
        "balady-issuing-commercial-license",
        "https://balady.gov.sa/en/services/issuing-commercial-license",
        "Issuing a Commercial License",
        ["food_beverage_fixed", "personal_care_spa"],
        ["municipal_license"],
    ),
    Target(
        "balady-commercial-activities-municipal-requirements",
        "https://balady.gov.sa/en/services/commercial-activities-and-municipal-requirements",
        "Commercial Activities and Municipal Requirements",
        ["food_beverage_fixed", "food_truck_mobile", "personal_care_spa"],
        ["municipal_requirements"],
    ),
    Target(
        "balady-commercial-license-requirements",
        "https://balady.gov.sa/en/node/10856",
        "Requirements for Issuing a Commercial License",
        ["food_beverage_fixed", "personal_care_spa"],
        ["municipal_license", "municipal_requirements"],
    ),
    Target(
        "balady-fast-track-commercial-license",
        "https://balady.gov.sa/en/services/issuing-fast-track-commercial-license",
        "Issuing a Fast-Track Commercial License",
        ["food_beverage_fixed"],
        ["municipal_license"],
    ),
    # Food-SERVICE requirements live on Balady, not the SFDA: restaurant/cafe
    # premises are municipally licensed, while the SFDA's remit is manufacture,
    # import and product registration. This page is the food vertical's real
    # requirements source.
    Target(
        "balady-restaurant-requirements",
        "https://balady.gov.sa/ar/consultations/%D8%A7%D8%B4%D8%AA%D8%B1%D8%A7%D8%B7%D8%A7%D8%AA-%D8%A7%D9%84%D9%85%D8%B7%D8%A7%D8%B9%D9%85",
        "اشتراطات المطاعم — Restaurant Requirements",
        ["food_beverage_fixed", "food_truck_mobile"],
        ["municipal_requirements", "food_safety"],
    ),
    # --- Balady: the mobile-cart sub-service — the second vertical (section 10) ---
    Target(
        "balady-mobile-cart-license-issuance",
        "https://balady.gov.sa/en/services/mobile-cart-license-issuance",
        "Mobile Cart License Issuance",
        ["food_truck_mobile"],
        ["municipal_license", "mobile_cart"],
    ),
    Target(
        "balady-commercial-licenses-product",
        "https://balady.gov.sa/en/products/commercial-licenses",
        "Commercial Licenses (product overview)",
        ["food_beverage_fixed", "food_truck_mobile", "personal_care_spa"],
        ["municipal_license"],
    ),
    # --- ZATCA: VAT. The portal pages render their answers client-side, so the
    # authoritative registration thresholds come from the regulation PDFs. ---
    Target(
        "zatca-vat-implementing-regulations",
        "https://zatca.gov.sa/en/RulesRegulations/Taxes/Documents/Implmenting%20Regulations%20of%20the%20VAT%20Law_EN.pdf",
        "Implementing Regulations of the Value Added Tax Law",
        [],
        ["vat", "threshold", "registration"],
        kind="pdf",
    ),
    Target(
        "zatca-vat-economic-activity-guideline",
        "https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Economic%20Activity.pdf",
        "VAT Guideline — Economic Activity",
        [],
        ["vat", "threshold"],
        kind="pdf",
    ),
    # --- ZATCA: VAT ---
    Target(
        "zatca-vat-rules",
        "https://zatca.gov.sa/en/RulesRegulations/VAT/Pages/default.aspx",
        "Value Added Tax — rules and regulations",
        [],
        ["vat"],
    ),
    Target(
        "zatca-vat-registration-individuals",
        "https://zatca.gov.sa/en/eServices/Pages/eServices_002.aspx",
        "VAT Registration",
        [],
        ["vat", "registration"],
    ),
    Target(
        "zatca-vat-mandatory-threshold-faq",
        "https://zatca.gov.sa/en/HelpCenter/FAQs/Pages/FAQ_026.aspx",
        "FAQ — mandatory VAT registration threshold",
        [],
        ["vat", "threshold"],
    ),
    # --- Saudi Business Center / Ministry of Commerce: commercial registration ---
    Target(
        "business-sa-commercial-registration",
        "https://business.sa/en/servicesprocedures/details/3f37df76-a853-4616-ef34-08dced12ee80",
        "Commercial Registration",
        [],
        ["commercial_registration"],
    ),
    Target(
        "mc-start-your-project",
        "https://mc.gov.sa/en/Pages/Start-your-project.aspx",
        "Start your business",
        [],
        ["commercial_registration", "startup_guidance"],
    ),
    Target(
        "mc-commercial-registration-establishment",
        "https://mc.gov.sa/en/eservices/Pages/ServiceDetails.aspx?sID=38",
        "A commercial registration for an establishment",
        [],
        ["commercial_registration"],
    ),
    # --- SFDA: food safety.
    # The English e-service detail pages are client-rendered and yield nothing.
    # This Arabic FAQ is server-rendered and, more usefully, defines the SCOPE of
    # the SFDA's local-food-establishment licensing system — which is what stops
    # the food_safety node applying a manufacturing rule to a cafe. ---
    Target(
        "sfda-local-food-establishment-scope",
        "https://www.sfda.gov.sa/ar/faq/85156",
        "ماذا نقصد بنظام تسجيل وترخيص المنشآت الغذائية المحلية؟",
        ["food_beverage_fixed", "food_truck_mobile"],
        ["food_safety"],
    ),
    # --- GOSI: employer registration ---
    Target(
        "gosi-establishment-registration",
        "https://www.gosi.gov.sa/GOSIOnline/Registration&locale=en_US",
        "Registration — General Organization for Social Insurance",
        [],
        ["gosi", "employer_registration"],
    ),
    # --- Monsha'at: SME context ---
    Target(
        "monshaat-home",
        "https://monshaat.gov.sa/en",
        "Monsha'at — SME authority",
        [],
        ["sme_support"],
    ),
]

# NOTE: do NOT strip <form>. The .aspx government portals (ZATCA, mc.gov.sa,
# SFDA) are ASP.NET WebForms, which wrap the entire page body in a single
# <form runat="server"> — removing it deletes the whole document.
STRIP_TAGS = ["script", "style", "noscript", "svg", "iframe", "button"]
STRIP_ROLES = ["navigation", "banner", "contentinfo", "search"]


def extract(html: str) -> str:
    """Reduce a government page to its readable content as markdown."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(STRIP_TAGS):
        tag.decompose()
    for role in STRIP_ROLES:
        for tag in soup.find_all(attrs={"role": role}):
            tag.decompose()
    for name in ("nav", "header", "footer"):
        for tag in soup.find_all(name):
            tag.decompose()

    # Pick the richest container rather than the first that exists: several of
    # these sites (ZATCA, SFDA) render an empty <main> and put the real content
    # elsewhere, which a first-match chain silently reduces to nothing.
    candidates = [
        soup.find("main"),
        soup.find(attrs={"role": "main"}),
        soup.find("article"),
        soup.find(id="contentBox"),
        soup.body,
        soup,
    ]
    main = max(
        (c for c in candidates if c is not None),
        key=lambda c: len(c.get_text(" ", strip=True)),
    )

    md = markdownify(str(main), heading_style="ATX", strip=["a", "img"])
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = re.sub(r"[ \t]+\n", "\n", md)
    lines = [ln.rstrip() for ln in md.splitlines()]

    # Drop runs of near-empty menu residue that survive the tag strip.
    cleaned: list[str] = []
    for line in lines:
        if not line.strip() and cleaned and not cleaned[-1].strip():
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def extract_pdf(data: bytes, max_pages: int = 80) -> str:
    """Text layer of a PDF. Same PyMuPDF path the lease parser uses in Phase 4."""
    chunks: list[str] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for page in doc[:max_pages]:
            page_text = page.get_text("text").strip()
            if page_text:
                chunks.append(page_text)
    text = "\n\n".join(chunks)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def write_doc(target: Target, text: str, retrieved_at: str, status: int) -> Path:
    domain = registered_domain(target.url)
    frontmatter = {
        "slug": target.slug,
        "title": target.title,
        "source_url": target.url,
        "source_entity": entity_for(target.url),
        "domain": domain,
        "retrieved_at": retrieved_at,
        "http_status": status,
        "categories": target.categories,
        "topics": target.topics,
        "char_count": len(text),
    }
    body = (
        "---\n"
        + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
        + "---\n\n"
        + text
        + "\n"
    )
    path = CORPUS_DIR / f"{target.slug}.md"
    path.write_text(body, encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-chars", type=int, default=400)
    args = parser.parse_args()

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    offlist = [t for t in TARGETS if not is_searchable(t.url)]
    if offlist:
        for t in offlist:
            print(f"REFUSED (not on allowlist): {t.url}")
        return 1

    if args.dry_run:
        for t in TARGETS:
            print(f"{t.slug:52s} {registered_domain(t.url):20s} {t.url}")
        return 0

    ok, thin, failed = 0, [], []
    with httpx.Client(
        follow_redirects=True,
        timeout=40.0,
        headers={"User-Agent": UA, "Accept-Language": "en,ar;q=0.8"},
    ) as client:
        for t in TARGETS:
            response = None
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    response = client.get(t.url)
                    break
                except Exception as exc:  # noqa: BLE001 - retry, then report
                    last_error = exc
                    if attempt < 2:
                        print(f"  retry {t.slug} ({exc.__class__.__name__})")
            if response is None:
                failed.append((t.slug, repr(last_error)))
                print(f"  FAIL  {t.slug}: {last_error!r}")
                continue

            if response.status_code >= 400:
                failed.append((t.slug, f"HTTP {response.status_code}"))
                print(f"  FAIL  {t.slug}: HTTP {response.status_code}")
                continue

            if t.kind == "pdf":
                text = extract_pdf(response.content)
            else:
                text = strip_boilerplate(extract(response.text))
            retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

            if len(text) < args.min_chars:
                thin.append((t.slug, len(text)))
                print(f"  THIN  {t.slug}: only {len(text)} chars of content — skipped")
                continue

            path = write_doc(t, text, retrieved_at, response.status_code)
            ok += 1
            print(f"  OK    {t.slug}: {len(text):>6} chars -> {path.name}")

    print(f"\n{ok} written, {len(thin)} too thin, {len(failed)} failed")
    if thin:
        print("thin:", ", ".join(f"{s}({n})" for s, n in thin))
    if failed:
        print("failed:", ", ".join(f"{s}: {e}" for s, e in failed))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
