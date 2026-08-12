"""
No-embedding fallback: skip sentence-transformers download, use plain text.
search() returns text chunks; check_relevance() always passes (keyword filter handles it).
"""
import hashlib
from pathlib import Path


def text_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def split_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    if chunk_size <= chunk_overlap:
        raise ValueError("chunk_size must exceed chunk_overlap")
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == n:
            break
        start = end - chunk_overlap
    return chunks


class DummyVectorStore:
    """Fake vector store that returns text chunks directly, no embeddings needed."""

    def __init__(self, chunks: list[str]):
        self._chunks = chunks

    def search(self, query: str, k: int = 4) -> list[str]:
        # Return first k chunks (the resume is small, all chunks are relevant)
        return self._chunks[:k]

    def check_relevance(self, query: str, distance_threshold: float = 1.3) -> tuple[bool, float]:
        # Always pass — keyword pre-filter in job_matcher handles relevance
        return True, 0.0


def embed_resume(resume_text: str, base_dir: str = "./vectorstores") -> DummyVectorStore:
    chunks = split_text(resume_text)
    if not chunks:
        raise ValueError("No text extracted from resume")
    print(f"✅ 简历已分块（{len(chunks)} 块），跳过向量化")
    return DummyVectorStore(chunks)


# Keep compatibility with existing imports
VectorStore = DummyVectorStore
