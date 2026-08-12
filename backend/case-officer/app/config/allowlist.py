"""Single source of truth for the government-domain allowlist.

PLACEHOLDER — implemented in Phase B step 6 (implementation plan Phase 0).

Deliberately left empty rather than pre-filled: implementation plan sections 0
and 9 require each domain to be verified against its live site before being
hardcoded, and several candidates (GOSI, National Address/SPL, HRSD, sdb.gov.sa,
momah.gov.sa) are explicitly flagged as unverified. Phase 0 does that check.

Both the Tavily ``include_domains`` tool config and the agent system prompts
must read from this module — the tool-level restriction is the real guardrail,
the prompt-level one is defense in depth.
"""
