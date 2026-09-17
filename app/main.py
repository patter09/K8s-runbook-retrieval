import logging
import secrets

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator

import config
from rag import answer_question
from guardrails import check_input, check_output

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("knowledge-assistant")

app = FastAPI(title="DevOps Knowledge Assistant")
Instrumentator().instrument(app).expose(app)  # exposes /metrics for Prometheus

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


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, api_key: str = Depends(verify_api_key)):
    input_check = check_input(req.question)

    # Audit log every request's governance result — this is what makes the
    # platform's guardrails auditable rather than just "best effort."
    logger.info(
        "query_received",
        extra={"pii_found": input_check["pii_found"], "blocked": input_check["blocked"]},
    )

    if input_check["blocked"]:
        raise HTTPException(
            status_code=400,
            detail="Request blocked by input guardrail (possible prompt injection).",
        )

    result = answer_question(input_check["sanitized_text"])

    output_check = check_output(result["answer"])
    if output_check["pii_found"]:
        logger.warning("output_pii_redacted", extra={"categories": output_check["pii_found"]})

    return QueryResponse(answer=output_check["sanitized_text"], sources=result["sources"])