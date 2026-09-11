"""
Lightweight governance layer.

Deliberately simple (regex-based) so the *pattern* is easy to explain: every
request and response passes through a governance check before it reaches the
model or the user. A production platform would swap these functions for
NeMo Guardrails, Presidio (PII), or a hosted moderation API without changing
the call sites in main.py.
"""
import re

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b")
CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")

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
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = CARD_RE.sub("[REDACTED_NUMBER]", text)
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
