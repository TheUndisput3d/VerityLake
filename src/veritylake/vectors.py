from __future__ import annotations

from veritylake.config import Settings
from veritylake.embeddings import validate_vectors


class ChromaIndex:
    def __init__(self, settings: Settings, client=None):
        if client is None:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            options = ChromaSettings(anonymized_telemetry=False)
            if settings.chroma_mode == "local":
                client = chromadb.PersistentClient(path=str(settings.chroma_dir), settings=options)
            else:
                client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port,
                                             ssl=settings.chroma_ssl, settings=options)
        self.client = client

    def health(self) -> None:
        self.client.heartbeat()

    def write(self, name: str, chunks: list[dict], embeddings: list[list[float]], identity: dict) -> None:
        dimension = validate_vectors(embeddings, len(chunks))
        collection = self.client.get_or_create_collection(
            name=name, embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
            metadata={"embedding_digest": identity["digest"], "embedding_name": identity["name"],
                      "dimension": dimension, "prefix_version": identity["prefix_version"]},
        )
        metadata = collection.metadata or {}
        if metadata.get("embedding_digest") != identity["digest"] or metadata.get("dimension") != dimension:
            raise ValueError("Attempt to reuse collection with another embedding space")
        for start in range(0, len(chunks), 100):
            items = chunks[start:start + 100]
            collection.upsert(
                ids=[c["chunk_id"] for c in items], embeddings=embeddings[start:start + 100],
                documents=[c["text"] for c in items],
                metadatas=[{k: c[k] for k in ("doc_id", "title", "url", "char_start", "char_end",
                                             "content_sha256", "fetched_at", "raw_key", "ordinal")} for c in items],
            )

    def count(self, name: str) -> int:
        return self.client.get_collection(name=name, embedding_function=None).count()

    def query(self, name: str, vector: list[float], top_k: int) -> list[dict]:
        validate_vectors([vector], 1)
        collection = self.client.get_collection(name=name, embedding_function=None)
        count = collection.count()
        if not count:
            return []
        result = collection.query(query_embeddings=[vector], n_results=min(top_k, count),
                                  include=["documents", "metadatas", "distances"])
        return [dict(id=chunk_id, text=text, distance=float(distance), **metadata)
                for chunk_id, text, metadata, distance in zip(result["ids"][0], result["documents"][0],
                    result["metadatas"][0], result["distances"][0], strict=True)]
