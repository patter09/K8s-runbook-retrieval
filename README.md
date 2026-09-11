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

# run the API — must bind 0.0.0.0, not the default 127.0.0.1, or Prometheus
# (running in a container) can't reach it. See the debugging log below.
cd app
uvicorn main:app --reload --port 8000 --host 0.0.0.0
```

**Linux only:** if you have `ufw` (or another firewall) active, it will likely
block Prometheus's container from reaching the host on port 8000 by default.
See "Issue 5" in the debugging log below for the correctly-scoped fix
(don't just disable the firewall).

Then:
```bash
curl -X POST localhost:8000/query -H "Content-Type: application/json" \
  -d '{"question": "What should I check first when an AKS pod is stuck in CrashLoopBackOff?"}'
```

Grafana: http://localhost:3000 (default admin/admin). Add a Prometheus data
source with URL `http://prometheus:9090` (container DNS name, not
`localhost` — Grafana and Prometheus are both containers on the same Compose
network). Two panels worth building first:

```
rate(http_requests_total{handler="/query"}[5m])        # request rate
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{handler="/query"}[5m]))   # p95 latency
```

![Grafana dashboard showing RAG query rate and p95 latency](docs/images/grafana-dashboard.png)

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

## Debugging log — what actually broke, and how it was fixed

This project was built and debugged interactively, one verified step at a
time, rather than written once and assumed correct. The issues below are
real, in the order they were hit, with root cause and fix — this log is
arguably the most interview-relevant part of the repo, since anyone can
copy working code but this is the actual troubleshooting trail.

### Issue 1 — `openai` / `httpx` version conflict

**Symptom:** `TypeError: Client.__init__() got an unexpected keyword argument
'proxies'` on startup, inside the OpenAI SDK's own client construction.

**Root cause:** `requirements.txt` pinned `openai==1.51.0` but left `httpx`
(a transitive dependency) unpinned. Pip installed the newest `httpx`
(0.28.x), which removed the `proxies` argument from `httpx.Client.__init__`
— but `openai==1.51.0` still passes it internally. Two libraries that were
compatible when this repo was written drifted apart because one wasn't
pinned tightly enough.

**Fix:** pin `httpx==0.27.2` explicitly in `requirements.txt`, alongside
`openai`, instead of leaving it to resolve freely.

### Issue 2 — non-idempotent ingestion

**Symptom:** running `python app/ingest.py data/sample_docs` twice doubled
`points_count` in Qdrant (9 → 18) instead of leaving it unchanged.

**Root cause:** each chunk was assigned a random `uuid.uuid4()` on every
run, so re-ingesting unchanged content created new points instead of
updating existing ones.

**Fix:** derive each point's ID deterministically from its content
(`source filename + chunk text`, hashed with SHA-256, formatted as a UUID
via `uuid.UUID(bytes=digest[:16])` since Qdrant requires int or UUID IDs).
Re-ingesting identical content now overwrites the same point instead of
duplicating it — verified by ingesting twice in a row and confirming
`points_count` stayed at 9 both times.

### Issue 3 — flaky eval result traced to two separate causes

**Symptom:** `eval/run_eval.py` failed one case
("What should I check first when an AKS pod is stuck in CrashLoopBackOff?")
with `missing keywords: ['logs', 'oomkilled']` — but manually re-running the
same question sometimes *did* include those words.

**Investigation:** rather than guessing, retrieval was checked directly
(bypassing generation) to confirm the correct runbook chunk — containing
both "logs" and "OOMKilled" verbatim — was in fact being retrieved. It was.
So this wasn't a retrieval bug. Next, the same question was run 3 times in
a row through generation alone: all 3 answered narrowly (literal "first
step only"), while one earlier ad-hoc run happened to mention "OOMKilled."
That confirmed real non-determinism in the model's output, not a
consistent generation failure.

**Two real causes, two fixes:**
1. The eval question itself was genuinely ambiguous — "what should I check
   **first**" has a defensible literal reading (just step one). Reworded
   to "What are **all** the things I should check..." to remove the
   ambiguity rather than fight the model into overriding a reasonable
   reading of the original question.
2. Eval runs need reproducibility that a live chat UI doesn't — added a
   `temperature` parameter threaded through `answer_question()` →
   `generate_answer()`, and set `run_eval.py` to call it with
   `temperature=0` specifically for eval runs (live user queries still use
   `temperature=0.1`). Verified fixed by re-running the eval twice in a row
   and confirming an identical 4/4 pass both times.

### Issue 4 — CI failures (two separate bugs, both environment-specific)

**Symptom 1:** `guardrail-unit-tests` job failed with
`No module named pytest`.
**Root cause:** `pytest` was installed locally with a one-off
`pip install pytest` that was never added back to `requirements.txt` —
worked locally, broke in CI, which installs strictly from the file.
**Fix:** add `pytest==8.3.3` to `requirements.txt`.

**Symptom 2:** `eval-gate` job failed with
`OllamaException - Cannot connect to host ollama:11434 ... Temporary
failure in name resolution`.
**Root cause:** `litellm_config.yaml` hardcoded `api_base:
http://ollama:11434` — a Docker Compose–internal DNS name that only
resolves when LiteLLM and Ollama are containers on the same Compose
network. In CI, both run as plain processes directly on the GitHub Actions
runner (no Docker Compose involved), so there is no `ollama` hostname to
resolve.
**Fix:** parameterized the address via `api_base: os.environ/OLLAMA_API_BASE`
in `litellm_config.yaml`, then set that env var to the environment-correct
value in each place LiteLLM actually runs: `http://ollama:11434` in
`docker-compose.yml`, `http://localhost:11434` in the CI workflow step. Same
logical dependency, two different valid addresses depending on where the
process runs — a good example of why hardcoding infra addresses is fragile.

**Also added:** `needs: guardrail-unit-tests` on the `eval-gate` job, so the
slow, expensive job (pulls a 2GB model) doesn't run at all if the fast, free
job would have failed anyway — a "fail fast" pipeline design choice, not a
required fix.

### Issue 5 — Prometheus couldn't scrape the FastAPI app (three-layer network issue)

**Symptom:** Prometheus target showed `health: down`, first with a DNS
error, then (after a partial fix) `context deadline exceeded`.

This took three separate fixes, each addressing a different layer:

1. **DNS:** `host.docker.internal` didn't resolve at all inside the
   Prometheus container. Root cause: that hostname auto-resolves on Docker
   Desktop (Mac/Windows) but **not** on native Linux — it has to be
   explicitly mapped. Fix: added
   `extra_hosts: ["host.docker.internal:host-gateway"]` to the `prometheus`
   service in `docker-compose.yml`.
2. **Bind address:** DNS then resolved, but the connection timed out. Root
   cause: `uvicorn` was started without `--host`, which defaults to binding
   only `127.0.0.1` (loopback) — reachable from the host's own terminal, but
   not from a container reaching in via the Docker bridge network, even via
   `host.docker.internal`. Fix: start uvicorn with `--host 0.0.0.0` so it
   listens on all interfaces.
3. **Firewall:** still timing out. Root cause: `ufw` was blocking inbound
   traffic on the Docker bridge interface by default. First attempt —
   `sudo ufw allow in on docker0` — didn't work and was actually the wrong
   fix: `docker network inspect` showed this Compose project uses its own
   custom bridge (`devops-ai-assistant_default`, e.g. `br-72ab1c84ca03`),
   not the default `docker0` interface, because Compose always creates a
   dedicated bridge per project rather than using the shared default one.
   Fix: found the real interface with `ip link show | grep br-`, then
   scoped the firewall rule to it specifically —
   `sudo ufw allow in on br-72ab1c84ca03` — with `ufw` left **active**
   throughout, rather than disabling it wholesale (which was tried briefly
   as a diagnostic step, confirmed it was a firewall issue, and was
   immediately reverted in favor of the properly scoped rule).

**Why this is worth mentioning explicitly in an interview:** the wrong
first guess (`docker0`) plus the discipline to verify with
`docker network inspect` instead of assuming, and to scope the fix
narrowly instead of disabling the firewall, is a more realistic and more
convincing demonstration of network troubleshooting than if it had worked
on the first try.

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
- The debugging log above is the most concrete evidence of hands-on
  troubleshooting in this repo — the network/firewall issue (Issue 5) in
  particular is a good default answer to "tell me about a time you debugged
  a tricky infrastructure problem."