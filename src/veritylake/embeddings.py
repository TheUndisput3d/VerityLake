from __future__ import annotations

import math

import httpx

from veritylake.config import Settings
from veritylake.storage import ObjectStore
from veritylake.util import digest, json_bytes


class ModelUnavailable(RuntimeError):
    pass


def validate_vectors(vectors: list, expected_count: int, dimension: int | None = None) -> int:
    if len(vectors) != expected_count or not vectors:
        raise ValueError("Embedding response count mismatch")
    dim = dimension or len(vectors[0])
    if dim < 1:
        raise ValueError("Empty embedding")
    for vector in vectors:
        if len(vector) != dim or any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in vector):
            raise ValueError("Non-finite or inconsistent embedding")
        if not any(x != 0 for x in vector):
            raise ValueError("Zero embedding")
    return dim


class OllamaEmbedder:
    PREFIX_VERSION = "nomic-search-prefix-v1"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(base_url=settings.ollama_base_url,
                                            timeout=settings.model_timeout_seconds, trust_env=False)
        self.owns_client = client is None

    def close(self) -> None:
        if self.owns_client:
            self.client.close()

    def identity(self) -> dict:
        response = self.client.get("/api/tags")
        response.raise_for_status()
        wanted = self.settings.embedding_model
        canonical = wanted if ":" in wanted else wanted + ":latest"
        for model in response.json().get("models", []):
            if model.get("name") in (wanted, canonical) or model.get("model") in (wanted, canonical):
                if not model.get("digest"):
                    break
                return {"name": wanted, "digest": model["digest"], "prefix_version": self.PREFIX_VERSION}
        raise ModelUnavailable("Embedding model not installed. Run make models.")

    def embed(self, texts: list[str], query: bool = False) -> list[list[float]]:
        if not texts:
            return []
        # nomic-embed-text expects different prefixes for indexing and retrieval.
        # For other encoders, override the adapter instead of silently reusing these semantics.
        prefix = "search_query: " if query else "search_document: "
        response = self.client.post("/api/embed", json={"model": self.settings.embedding_model,
                                   "input": [prefix + t for t in texts], "truncate": False, "keep_alive": "10m"})
        response.raise_for_status()
        vectors = response.json()["embeddings"]
        validate_vectors(vectors, len(texts))
        return vectors


class EmbeddingCache:
    def __init__(self, store: ObjectStore, embedder: OllamaEmbedder, batch_size: int = 16):
        self.store, self.embedder, self.batch_size = store, embedder, batch_size

    def encode(self, texts: list[str], identity: dict) -> tuple[list[list[float]], dict]:
        fingerprint = digest(json_bytes(identity))
        keys = [f"embeddings/cache/{fingerprint}/{digest(text)}.json" for text in texts]
        vectors = [self.store.maybe_json(key) for key in keys]
        missing = [i for i, value in enumerate(vectors) if value is None]
        for start in range(0, len(missing), self.batch_size):
            indices = missing[start:start + self.batch_size]
            batch = self.embedder.embed([texts[i] for i in indices])
            validate_vectors(batch, len(indices))
            for i, vector in zip(indices, batch, strict=True):
                self.store.put_json(keys[i], vector)
                vectors[i] = vector
        if texts:
            validate_vectors(vectors, len(texts))
        if self.embedder.identity() != identity:
            raise ModelUnavailable("Embedding model changed while indexing; release blocked")
        return vectors, {"cache_hits": len(texts) - len(missing), "cache_misses": len(missing),
                         "embedding_fingerprint": fingerprint}
