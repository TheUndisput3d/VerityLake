"""Deterministic TEST DOUBLES. They are never exposed as production model/storage backends."""
import copy
import hashlib
import math

from veritylake.tables import CHUNK_COLUMNS, DOCUMENT_COLUMNS
from veritylake.util import digest, utcnow


class FakeEmbedder:
    def __init__(self):
        self.calls = 0
        self.model_digest = "test-model-sha256"

    def identity(self):
        return {"name": "test-only-hash-encoder", "digest": self.model_digest, "prefix_version": "fixture-v1"}

    def embed(self, texts, query=False):
        self.calls += len(texts)
        out = []
        for text in texts:
            raw = hashlib.sha256(text.encode()).digest()
            vector = [(value - 127.5) / 127.5 for value in raw]
            length = math.sqrt(sum(x * x for x in vector))
            out.append([x / length for x in vector])
        return out


class FakeIndex:
    def __init__(self):
        self.collections = {}

    def write(self, name, chunks, vectors, identity):
        self.collections[name] = {"chunks": copy.deepcopy(chunks), "vectors": copy.deepcopy(vectors)}

    def count(self, name):
        return len(self.collections[name]["chunks"])

    def query(self, name, vector, top_k):
        data = self.collections[name]
        rows = []
        for chunk, other in zip(data["chunks"], data["vectors"], strict=True):
            row = dict(chunk)
            row["id"] = row.pop("chunk_id")
            row["distance"] = 1 - sum(a * b for a, b in zip(vector, other, strict=True))
            rows.append(row)
        return sorted(rows, key=lambda r: r["distance"])[:top_k]


class FakeTables:
    def __init__(self):
        self.tables = {}

    def write(self, key, rows, kind):
        self.tables[key] = copy.deepcopy(rows)
        return {"key": key, "uri": "test://" + key, "version": 0, "rows": len(rows),
                "schema": DOCUMENT_COLUMNS if kind == "documents" else CHUNK_COLUMNS}

    def read(self, table):
        return copy.deepcopy(self.tables[table["key"]])

    @staticmethod
    def deduplicate(rows):
        unique = {}
        for row in sorted(rows, key=lambda r: r["url"]):
            unique.setdefault(row["content_sha256"], row)
        return sorted(unique.values(), key=lambda r: r["doc_id"])

    def build_catalog(self, run_id, tables, quality):
        return {"key": f"catalog/runs/{run_id}/catalog.duckdb", "uri": "test://catalog"}


def document(number=1, text=None):
    return {"doc_id": digest(f"doc-{number}"), "url": f"https://example.org/book-{number}",
            "title": f"Book {number}", "text": text or f"Book {number} describes observability, testing and careful data engineering. " * 4,
            "fetched_at": utcnow(), "content_sha256": digest(text or f"raw-{number}"),
            "raw_key": f"raw/doc-{number}.html", "etag": "", "last_modified": "", "status": 200, "html_bytes": 1000}


class FakeCrawler:
    def __init__(self, settings):
        self.settings = settings

    def crawl(self):
        return {"pages": [dict(document(i), html=f"<h1>Book {i}</h1>", is_document=True) for i in range(1, 4)],
                "robots": {"status": 200, "content": "User-agent: *\nAllow: /"}, "errors": [], "fetch_count": 3}


def valid_release(run_id, count=1):
    quality = {s: {"passed": True, "checks": [{"name": "fixture", "passed": True}]} for s in ("silver", "gold", "embed")}
    return {"schema_version": 1, "run_id": run_id, "created_at": utcnow(), "published_at": utcnow(),
            "quality": quality, "tables": {"gold": {"rows": count}, "silver": {"rows": count}},
            "embedding_identity": FakeEmbedder().identity(), "collection": "vl_" + run_id,
            "vector_count": count, "source_url": "https://example.org", "source_terms_note": "test fixture",
            "catalog": {"key": "catalog/test.duckdb"}, "git_sha": "fixture"}
