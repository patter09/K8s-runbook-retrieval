import os

from dotenv import load_dotenv

# Load .env explicitly — Docker Compose auto-injects env vars into
# CONTAINERS, but this file is also imported when running the app or
# scripts directly on the host (uvicorn, ingest.py, run_eval.py), where
# nothing loads .env automatically otherwise. Missing this was the real
# cause of a "No connected db." error from LiteLLM: with no .env loaded,
# LITELLM_API_KEY fell back to the hardcoded default below, which no
# longer matched the real rotated master key after the security fix —
# LiteLLM's error message blames a missing database, but the actual fault
# was a key mismatch (LiteLLM only hits its database for non-master keys).
load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "runbooks")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIM = 384  # dimension for all-MiniLM-L6-v2

LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://localhost:4000")
# No hardcoded secret fallback — if LITELLM_API_KEY isn't set, fail loudly
# and immediately rather than silently authenticating with a stale or
# guessable default value.
LITELLM_API_KEY = os.environ["LITELLM_API_KEY"]
APP_API_KEY = os.environ["APP_API_KEY"]
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "knowledge-assistant")

TOP_K = int(os.getenv("TOP_K", "3"))
CHUNK_SIZE_CHARS = int(os.getenv("CHUNK_SIZE_CHARS", "800"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "100"))