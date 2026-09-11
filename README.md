# DevOps Knowledge Assistant — Self-Service RAG Platform

A small but real implementation of the core capabilities behind an enterprise "AI
platform": model serving, an AI gateway, a vector database, eval-gated CI/CD,
observability, and basic governance — all running locally with free/open-source
tools.

**The use case:** engineering teams have runbooks, postmortems, and architecture
docs scattered across wikis. This platform lets them drop docs into a collection
and query them through a governed, observable API instead of grepping Confluence
at 2am during an incident.

This is deliberately built as a *platform*, not a chatbot demo: every piece maps
to a real enterprise AI-platform requirement, and the README below spells out
which one, so you can talk through the mapping in an interview.

---

## Architecture

```
                 ┌─────────────┐
   documents ──▶ │  ingest.py  │──▶ embeddings (sentence-transformers)
                 └─────────────┘            │
                                             ▼
                                      ┌─────────────┐
                                      │   Qdrant    │  (vector DB)
                                      └─────────────┘
                                             ▲
                                             │ retrieve
  client ──▶ FastAPI /query ─────────────────┘
                  │
                  ▼
            LiteLLM Proxy  (AI gateway: auth, rate limits, cost/token logging)
                  │
                  ▼
               Ollama  (local LLM serving — llama3.2:3b)

  FastAPI also exposes /metrics ──▶ Prometheus ──▶ Grafana
  guardrails.py runs on every request (PII filter, prompt-injection check)
  eval/run_eval.py runs in CI on every change (grounding/faithfulness gate)
```

## Why each piece is here (map to platform-engineering requirements)

| Component | JD-style requirement it demonstrates |
|---|---|
| Qdrant | Vector databases |
| Ollama | Model serving frameworks |
| LiteLLM proxy | AI gateways, per-team API keys, developer self-service |
| `eval/run_eval.py` + GitHub Actions | MLOps/LLMOps CI/CD, model/prompt lifecycle management |
| Prometheus + Grafana | Observability, platform reliability |
| `guardrails.py` | Responsible AI, governance, auditability |
| Docker Compose (→ later: Helm/Terraform) | Cloud-native infra, IaC, Kubernetes |

## Quick start

```bash
cp .env.example .env
docker compose up -d qdrant ollama litellm prometheus grafana

# pull a small local model (one-time, ~2GB)
docker exec -it ollama ollama pull llama3.2:3b

# install deps for the app + scripts (run on host, not in a container, for simplicity)
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# ingest the sample runbooks
python app/ingest.py data/sample_docs

# run the API
uvicorn app.main:app --reload --port 8000
```

Then:
```bash
curl -X POST localhost:8000/query -H "Content-Type: application/json" \
  -d '{"question": "What should I check first when an AKS pod is stuck in CrashLoopBackOff?"}'
```

Grafana: http://localhost:3000 (default admin/admin) — add Prometheus
(`http://prometheus:9090`) as a data source and graph request latency and count
from the `/metrics` endpoint.

## Running the eval gate locally

```bash
python eval/run_eval.py
```

This retrieves context and generates an answer for every question in
`eval/testset.yaml`, then checks that the answer is actually *grounded* in the
retrieved context (not hallucinated) and covers the expected key points. It
exits non-zero if the pass rate drops below threshold — that's the check
`.github/workflows/ci.yml` runs on every change, so a bad prompt or retrieval
change can't get merged silently. This is the "LLMOps CI/CD" piece most
DevOps-background candidates skip, and it's worth walking through explicitly.

## What's deliberately simple (and the honest way to talk about it)

- The eval check is a lightweight grounding/keyword-coverage check, not full
  RAGAS — good enough to demonstrate the *pattern* (gate merges on quality,
  not just tests passing) without needing a second LLM as judge. Swapping in
  RAGAS or a proper LLM-as-judge is a natural "next step" to mention.
- Guardrails are regex-based PII/prompt-injection checks, not a full
  NeMo Guardrails setup — same reasoning: demonstrates the governance
  *pattern* that an enterprise platform needs, cheaply and explainably.
- Runs on Docker Compose, not Kubernetes yet. That's the next phase: the same
  services move into Helm charts on a local `kind` cluster, provisioned by
  Terraform — which is where your existing AKS/EKS/Terraform experience plugs
  in directly. Say so in the interview: this repo is phase 1 of that plan.

## Interview talking points

- "I built the AI-specific layer (vector search, model serving, gateway) the
  same way I've always built platforms: IaC-able, observable, and gated by
  automated checks before anything ships."
- Walk through `run_eval.py` and explain *why* eval-gating matters for LLM
  changes specifically (non-deterministic output means "tests pass" isn't
  enough — you need to gate on answer quality/grounding).
- Be upfront about what's simplified and what the production version would
  add (RAGAS, NeMo Guardrails, Kubernetes/Helm, a real model registry via
  MLflow) — this signals platform-engineering judgment, not just tool usage.
