import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator

from rag import answer_question
from guardrails import check_input, check_output

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("knowledge-assistant")

app = FastAPI(title="DevOps Knowledge Assistant")
Instrumentator().instrument(app).expose(app)  # exposes /metrics for Prometheus


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[str]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
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
