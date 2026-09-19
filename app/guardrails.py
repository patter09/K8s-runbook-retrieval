"""
Lightweight governance layer.

Deliberately simple (regex-based) so the *pattern* is easy to explain: every
request and response passes through a governance check before it reaches the
model or the user. A production platform would swap these functions for
NeMo Guardrails, Presidio (PII), or a hosted moderation API without changing
the call sites in main.py.
"""
import re

# Restructured from [a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,} (flagged
# by SonarCloud SAST, rule python:S8786, as non-linear-backtracking risk —
# found on a re-scan AFTER the CARD_RE fix below, a genuinely separate
# issue in a different regex, not a stale repeat of it). The domain group
# [a-zA-Z0-9.-]+ included literal '.' in its own character class while
# being immediately followed by \.[a-zA-Z]{2,}, which also matches dots
# and letters — the two constructs can consume the same characters in many
# different ways, the classic email-regex ReDoS shape. Restructured as
# (?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}: each repeated unit consumes exactly one
# label plus its trailing dot, and the label's own character class no
# longer includes '.', so there is only one way to split any given input —
# no ambiguity left for the engine to backtrack across.
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b")
# Rewritten from \b(?:\d[ -]*?){13,16}\b (flagged by SonarCloud SAST as
# both a super-linear/catastrophic-backtracking risk AND a reluctant
# quantifier that could only ever match 0 repetitions in practice — the
# same nested `[ -]*?` inside a bounded outer repeat caused both). This
# is a genuine ReDoS concern, not just a lint nit: contains_pii() runs on
# every request and response, so a pathological input could exploit it.
# Fixed by bounding the separator to 0-or-1 (`?`, not `*?`) per digit,
# with a fixed-width repeated unit — no nested unbounded quantifier left
# for the engine to backtrack across.
CARD_RE = re.compile(r"\b\d(?:[ -]?\d){12,15}\b")

INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard your instructions",
    "you are now",
    "system prompt",
    "reveal your prompt",
]


def contains_pii(text: str) -> list[str]:
    """Return a list of PII categories found in text, empty if none."""
    found = []
    if EMAIL_RE.search(text):
        found.append("email")
    if PHONE_RE.search(text):
        found.append("phone_number")
    if CARD_RE.search(text):
        found.append("card_number_like")
    return found


def redact_pii(text: str) -> str:
    # Order matters here, and it's not arbitrary: CARD_RE (13-16 digits)
    # runs BEFORE PHONE_RE, because a card-number-shaped string can
    # partially satisfy PHONE_RE's shorter, more general pattern (groups
    # of 3-4 digits separated by dashes). Found by a real test failure:
    # with PHONE_RE running first, "4111-1111-1111-1111" got partially
    # consumed as "[REDACTED_PHONE]-1111" before CARD_RE ever saw the
    # intact digit sequence, leaving a corrupted, half-redacted result.
    # The more specific/longer pattern needs first claim on the digits.
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = CARD_RE.sub("[REDACTED_NUMBER]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text


def detect_prompt_injection(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in INJECTION_PATTERNS)


def check_input(text: str) -> dict:
    """
    Run all input-side checks. Returns a dict the caller can log/audit and
    use to decide whether to block or proceed.
    """
    pii_found = contains_pii(text)
    injection_flagged = detect_prompt_injection(text)
    return {
        "blocked": injection_flagged,
        "pii_found": pii_found,
        "sanitized_text": redact_pii(text) if pii_found else text,
    }


def check_output(text: str) -> dict:
    pii_found = contains_pii(text)
    return {
        "pii_found": pii_found,
        "sanitized_text": redact_pii(text) if pii_found else text,
    }