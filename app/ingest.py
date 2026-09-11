"""
Chunk markdown/text documents, embed them, and upsert into Qdrant.

Usage:
    python app/ingest.py data/sample_docs
"""
import hashlib
import sys
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

from config import (
    QDRANT_URL,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    CHUNK_SIZE_CHARS,
    CHUNK_OVERLAP_CHARS,
)


def chunk_text(text: str, size: int = CHUNK_SIZE_CHARS, overlap: int = CHUNK_OVERLAP_CHARS):
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return [c.strip() for c in chunks if c.strip()]


def ensure_collection(client: QdrantClient):
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        print(f"Created collection '{COLLECTION_NAME}'")


def ingest_directory(directory: str):
    client = QdrantClient(url=QDRANT_URL)
    ensure_collection(client)
    model = SentenceTransformer(EMBEDDING_MODEL)

    doc_paths = list(Path(directory).glob("**/*.md")) + list(Path(directory).glob("**/*.txt"))
    if not doc_paths:
        print(f"No .md or .txt files found in {directory}")
        return

    points = []
    for path in doc_paths:
        text = path.read_text(encoding="utf-8")
        chunks = chunk_text(text)
        embeddings = model.encode(chunks, show_progress_bar=False)
        for chunk, vector in zip(chunks, embeddings):
            digest = hashlib.sha256(f"{path.name}:{chunk}".encode()).digest()
            chunk_id = str(uuid.UUID(bytes=digest[:16]))
            points.append(
                PointStruct(
                    id=chunk_id,
                    vector=vector.tolist(),
                    payload={"source": path.name, "text": chunk},
                )
            )
        print(f"Ingested {len(chunks)} chunks from {path.name}")

    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"Upserted {len(points)} chunks total into '{COLLECTION_NAME}'")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python app/ingest.py <directory_of_docs>")
        sys.exit(1)
    ingest_directory(sys.argv[1])
