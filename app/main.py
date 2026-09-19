import logging
import secrets
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator

import audit
import config
from rag import answer_question
from guardrails import check_input, check_output

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("knowledge-assistant")

app = FastAPI(title="DevOps Knowledge Assistant")
Instrumentator().instrument(app).expose(app)  # exposes /metrics for Prometheus
audit.init_db()


@app.middleware("http")
async def add_security_headers(request, call_next):
    # Fixes 2 real findings from an OWASP ZAP DAST scan (WARN-NEW, not
    # false positives): X-Content-Type-Options Header Missing and
    # Cross-Origin-Resource-Policy Header Missing or Invalid. Applied as
    # middleware — runs for every response on every route, including
    # /query — rather than repeated per-endpoint, so a future new route
    # can't forget to set these.
    response = await call_next(request)
    # Stops browsers from MIME-sniffing a response into a different
    # content type than what Content-Type declares (a real vector for
    # turning a JSON/text response into executable content in some
    # browser contexts).
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Blocks other origins from embedding/reading this resource
    # (e.g. via <img>/<script> tags) unless explicitly permitted —
    # "same-origin" is the strictest, correct default for an internal
    # API with no legitimate cross-origin embedding use case.
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    return response


# APIKeyHeader reads the "X-API-Key" header; auto_error=False lets us return
# our own 401 (with a clear message) instead of FastAPI's generic one.
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(_api_key_header)) -> str:
    if api_key is None:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header.")
    # secrets.compare_digest instead of `==` — a plain string comparison
    # short-circuits on the first mismatched character, so its timing
    # leaks information about how many leading characters were correct
    # (a timing side-channel attack). compare_digest runs in constant time
    # regardless of where the mismatch is.
    if not secrets.compare_digest(api_key, config.APP_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key.")
    return api_key


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[str]


@app.get("/health")
def health():
    # Deliberately NOT behind auth: health checks (readinessProbe in
    # k8s/knowledge-assistant.yaml) need to reach this without credentials.
    return {"status": "ok"}


@app.post(
    "/query",
    response_model=QueryResponse,
    responses={400: {"description": "Request blocked by an input guardrail (e.g. possible prompt injection)."}},
)
def query(req: QueryRequest, api_key: Annotated[str, Depends(verify_api_key)]):
    input_check = check_input(req.question)

    # Audit log every request's governance result — this is what makes the
    # platform's guardrails auditable rather than just "best effort."
    logger.info(
        "query_received",
        extra={"pii_found": input_check["pii_found"], "blocked": input_check["blocked"]},
    )

    if input_check["blocked"]:
        audit.log_request(
            api_key=api_key,
            # sanitized_text, not req.question — same PII-redaction
            # discipline as the answer field below. Storing the raw
            # question here would defeat the point of redacting PII at
            # all, since it would just reappear in the audit log.
            question=input_check["sanitized_text"],
            status="blocked_injection",
            pii_found_input=input_check["pii_found"],
        )
        raise HTTPException(
            status_code=400,
            detail="Request blocked by input guardrail (possible prompt injection).",
        )

    result = answer_question(input_check["sanitized_text"])

    output_check = check_output(result["answer"])
    if output_check["pii_found"]:
        logger.warning("output_pii_redacted", extra={"categories": output_check["pii_found"]})

    audit.log_request(
        api_key=api_key,
        question=input_check["sanitized_text"],
        status="allowed",
        answer=output_check["sanitized_text"],
        sources=result["sources"],
        pii_found_input=input_check["pii_found"],
        pii_found_output=output_check["pii_found"],
    )

    return QueryResponse(answer=output_check["sanitized_text"], sources=result["sources"])