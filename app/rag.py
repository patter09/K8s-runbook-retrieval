from openai import OpenAI
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from config import (
    QDRANT_URL,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    LITELLM_BASE_URL,
    LITELLM_API_KEY,
    LLM_MODEL_NAME,
    TOP_K,
)

_qdrant = QdrantClient(url=QDRANT_URL)
_embedder = SentenceTransformer(EMBEDDING_MODEL)

# LiteLLM exposes an OpenAI-compatible API, so the standard OpenAI SDK works
# unmodified — this is the point of putting a gateway in front of the model.
_llm_client = OpenAI(base_url=LITELLM_BASE_URL, api_key=LITELLM_API_KEY)

SYSTEM_PROMPT = (
    "You are a DevOps knowledge assistant. Answer ONLY using the provided "
    "context from internal runbooks. Be thorough: if the context lists "
    "multiple relevant checks, causes, or steps, include all of them rather "
    "than stopping at the first one, even if the question is phrased as "
    "asking for a single thing. If the context does not contain the answer, "
    "say you don't have enough information rather than guessing."
)


def retrieve(question: str, top_k: int = TOP_K):
    query_vector = _embedder.encode(question).tolist()
    results = _qdrant.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=top_k,
    )
    return [
        {"text": r.payload["text"], "source": r.payload["source"], "score": r.score}
        for r in results
    ]


def build_prompt(question: str, context_chunks: list[dict]) -> str:
    context_block = "\n\n".join(
        f"[Source: {c['source']}]\n{c['text']}" for c in context_chunks
    )
    return (
        f"Context:\n{context_block}\n\n"
        f"Question: {question}\n\n"
        "Answer using only the context above, and cite the source file(s) you used."
    )


def generate_answer(question: str, context_chunks: list[dict], temperature: float = 0.1) -> str:
    prompt = build_prompt(question, context_chunks)
    response = _llm_client.chat.completions.create(
        model=LLM_MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
    )
    return response.choices[0].message.content


def answer_question(question: str, temperature: float = 0.1) -> dict:
    context_chunks = retrieve(question)
    answer = generate_answer(question, context_chunks, temperature=temperature)
    return {
        "answer": answer,
        "sources": list({c["source"] for c in context_chunks}),
        "context_chunks": context_chunks,
    }
