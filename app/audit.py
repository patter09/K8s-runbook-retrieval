"""
Durable audit logging.

Why SQLite on a persistent volume, not just Python's `logging` module:
main.py already logs via `logging`, but that only ever reaches container
stdout — visible in `docker logs`/`kubectl logs` while the pod is alive,
gone the moment it restarts. This project has hit that exact data-loss
pattern three times already this session (Qdrant twice, Ollama once), so
it's a proven risk, not a hypothetical one. A real audit trail needs to
survive restarts and be queryable later ("show me every request from this
API key in the last 24 hours") — this module gives both, with zero new
infrastructure services to run.

The API key itself is never stored — only a SHA-256 hash of it, so the
audit log can identify "which caller" made a request without itself
becoming a place a real credential could leak from.
"""
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

AUDIT_DB_PATH = os.getenv("AUDIT_DB_PATH", "audit.db")


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


@contextmanager
def _connection():
    conn = sqlite3.connect(AUDIT_DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                caller_key_hash TEXT NOT NULL,
                question TEXT NOT NULL,
                status TEXT NOT NULL,
                answer TEXT,
                sources TEXT,
                pii_found_input TEXT,
                pii_found_output TEXT
            )
            """
        )


def log_request(
    api_key: str,
    question: str,
    status: str,
    answer: str = None,
    sources: list = None,
    pii_found_input: list = None,
    pii_found_output: list = None,
):
    """
    status is one of: "allowed", "blocked_injection". Called for every
    request that reaches the /query handler, whether it was ultimately
    allowed through or rejected by a guardrail — a blocked request is
    exactly as important to have on record as an allowed one.
    """
    with _connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_log
                (timestamp, caller_key_hash, question, status, answer,
                 sources, pii_found_input, pii_found_output)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                _hash_api_key(api_key),
                question,
                status,
                answer,
                json.dumps(sources) if sources else None,
                json.dumps(pii_found_input) if pii_found_input else None,
                json.dumps(pii_found_output) if pii_found_output else None,
            ),
        )