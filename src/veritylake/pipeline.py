from __future__ import annotations

import logging
import time
from collections.abc import Callable
from uuid import uuid4

from veritylake.config import Settings
from veritylake.crawler import Crawler
from veritylake.embeddings import EmbeddingCache, OllamaEmbedder, validate_vectors
from veritylake.lineage import Lineage
from veritylake.publication import Publications
from veritylake.quality import enforce, gold_report, prepare_documents, silver_report
from veritylake.storage import ObjectStore, make_store
from veritylake.tables import DOCUMENT_COLUMNS, DeltaTables
from veritylake.text import chunk_document
from veritylake.util import utcnow, validate_run_id
from veritylake.vectors import ChromaIndex

log = logging.getLogger(__name__)
STAGES = ("scrape", "bronze", "silver", "gold", "embed", "publish")


class Pipeline:
    def __init__(self, settings: Settings, store: ObjectStore | None = None,
                 tables=None, embedder=None, index=None, crawler_factory=Crawler):
        self.settings = settings
        self.store = store or make_store(settings)
        self._tables, self._embedder, self._index = tables, embedder, index
        self.crawler_factory = crawler_factory
        self.publications = Publications(self.store)
        self.lineage = Lineage(self.store, settings.openlineage_url)

    @property
    def tables(self):
        if self._tables is None:
            self._tables = DeltaTables(self.store)
        return self._tables

    @property
    def embedder(self):
        if self._embedder is None:
            self._embedder = OllamaEmbedder(self.settings)
        return self._embedder

    @property
    def index(self):
        if self._index is None:
            self._index = ChromaIndex(self.settings)
        return self._index

    def new_run(self, run_id: str | None = None) -> str:
        run_id = validate_run_id(run_id or uuid4().hex)
        key = f"runs/{run_id}/run.json"
        prior = self.store.maybe_json(key)
        if prior:
            if prior["config_fingerprint"] != self.settings.pipeline_fingerprint():
                raise ValueError("Configuration changed within an existing run")
            return run_id
        run = {"run_id": run_id, "created_at": utcnow(), "schema_version": 1,
               "config_fingerprint": self.settings.pipeline_fingerprint(),
               "config": self.settings.public_pipeline_config(), "base_active_etag": self.publications.active_etag()}
        from veritylake.util import json_bytes

        self.store.compare_and_swap(key, json_bytes(run), None)
        return run_id

    def result(self, run_id: str, stage: str) -> dict:
        validate_run_id(run_id)
        if stage not in STAGES:
            raise ValueError("Unknown stage")
        value = self.store.get_json(f"runs/{run_id}/stages/{stage}.json")
        if value.get("status") != "complete":
            raise RuntimeError(f"{stage} has not completed")
        return value["output"]

    def _stage(self, run_id: str, stage: str, inputs: list[str], outputs: list[str], work: Callable) -> dict:
        validate_run_id(run_id)
        run = self.store.get_json(f"runs/{run_id}/run.json")
        if run["config_fingerprint"] != self.settings.pipeline_fingerprint():
            raise ValueError("Configuration drift detected; start a new run")
        key = f"runs/{run_id}/stages/{stage}.json"
        prior = self.store.maybe_json(key)
        if prior and prior["status"] == "complete":
            return prior["output"]
        started, wall = time.monotonic(), utcnow()
        with self.lineage.stage(run_id, stage, inputs, outputs):
            try:
                result = work()
            except Exception as exc:
                self.store.put_json(key, {"status": "failed", "started_at": wall, "finished_at": utcnow(),
                    "duration_seconds": time.monotonic() - started, "error_type": type(exc).__name__})
                raise
        self.store.put_json(key, {"status": "complete", "started_at": wall, "finished_at": utcnow(),
            "duration_seconds": time.monotonic() - started, "output": result})
        log.info("stage_complete", extra={"fields": {"run_id": run_id, "stage": stage,
                                                     "duration_seconds": time.monotonic() - started}})
        return result

    def scrape(self, run_id: str) -> dict:
        def work():
            crawl = self.crawler_factory(self.settings).crawl()
            rows = []
            for page in crawl["pages"]:
                page = dict(page)
                prefix = f"raw/{run_id}/pages/{page['doc_id']}"
                html = page.pop("html")
                raw_body = page.pop("raw_html", html.encode())
                self.store.put(prefix + ".html", raw_body, "text/html")
                self.store.put(prefix + ".txt", page["text"].encode(), "text/plain; charset=utf-8")
                page["raw_key"] = prefix + ".html"
                self.store.put_json(prefix + ".json", page)
                if page.pop("is_document"):
                    rows.append({k: page[k] for k in DOCUMENT_COLUMNS})
            self.store.put_json(f"raw/{run_id}/robots.json", crawl["robots"])
            self.store.put_json(f"raw/{run_id}/errors.json", crawl["errors"])
            self.store.put_json(f"raw/{run_id}/documents.json", rows)
            if len(rows) < self.settings.min_documents:
                raise RuntimeError("Insufficient successfully crawled documents; raw diagnostics preserved")
            return {"document_count": len(rows), "fetch_count": crawl["fetch_count"],
                    "documents_key": f"raw/{run_id}/documents.json", "robots_key": f"raw/{run_id}/robots.json"}
        return self._stage(run_id, "scrape", [self.settings.source_url], [self.store.uri(f"raw/{run_id}")], work)

    def bronze(self, run_id: str) -> dict:
        source = self.result(run_id, "scrape")
        def work():
            rows = self.store.get_json(source["documents_key"])
            return self.tables.write(f"bronze/{run_id}/documents", rows, "documents")
        return self._stage(run_id, "bronze", [self.store.uri(source["documents_key"])],
                           [self.store.uri(f"bronze/{run_id}/documents")], work)

    def silver(self, run_id: str) -> dict:
        bronze = self.result(run_id, "bronze")
        def work():
            raw = self.tables.read(bronze)
            prepared, rejected = prepare_documents(raw, self.settings)
            rows = self.tables.deduplicate(prepared)
            report = silver_report(len(raw), rows, rejected, self.settings)
            self.store.put_json(f"quarantine/{run_id}/silver.json", rejected)
            self.store.put_json(f"quality/{run_id}/silver.json", report)
            enforce(report)
            return {"table": self.tables.write(f"silver/{run_id}/documents", rows, "documents"), "quality": report}
        return self._stage(run_id, "silver", [bronze["uri"]], [self.store.uri(f"silver/{run_id}/documents")], work)

    def gold(self, run_id: str) -> dict:
        silver = self.result(run_id, "silver")
        def work():
            docs = self.tables.read(silver["table"])
            chunks = [chunk for doc in docs for chunk in chunk_document(
                doc, self.settings.chunk_words, self.settings.chunk_overlap_words)]
            report = gold_report(chunks, docs, self.settings)
            self.store.put_json(f"quality/{run_id}/gold.json", report)
            enforce(report)
            return {"table": self.tables.write(f"gold/{run_id}/chunks", chunks, "chunks"), "quality": report}
        return self._stage(run_id, "gold", [silver["table"]["uri"]], [self.store.uri(f"gold/{run_id}/chunks")], work)

    def embed(self, run_id: str) -> dict:
        gold = self.result(run_id, "gold")
        def work():
            chunks = self.tables.read(gold["table"])
            identity = self.embedder.identity()
            vectors, stats = EmbeddingCache(self.store, self.embedder, self.settings.embedding_batch_size).encode(
                [c["title"] + "\n" + c["text"] for c in chunks], identity)
            dimension = validate_vectors(vectors, len(chunks))
            collection = "vl_" + run_id
            self.index.write(collection, chunks, vectors, identity)
            count = self.index.count(collection)
            probe_count = min(5, len(chunks))
            hits = 0
            for i in range(probe_count):
                found = self.index.query(collection, vectors[i], min(5, count))
                hits += int(chunks[i]["chunk_id"] in {row["id"] for row in found})
            checks = [
                {"name": "vector_count_matches_gold", "passed": count == len(chunks), "observed": count},
                {"name": "embedding_dimension_consistent", "passed": dimension > 0, "observed": dimension},
                {"name": "self_retrieval_integrity", "passed": hits == probe_count, "observed": hits,
                 "threshold": probe_count},
            ]
            report = {"passed": all(c["passed"] for c in checks), "checks": checks,
                      "note": "Self-retrieval tests index integrity, not semantic answer quality."}
            self.store.put_json(f"quality/{run_id}/embed.json", report)
            enforce(report)
            return {"collection": collection, "vector_count": count, "dimension": dimension,
                    "embedding_identity": identity, "quality": report, **stats}
        return self._stage(run_id, "embed", [gold["table"]["uri"]], ["chroma://vl_" + run_id], work)

    def publish(self, run_id: str) -> dict:
        def work():
            existing = self.store.maybe_json(f"catalog/releases/{run_id}.json")
            if existing:
                release = existing
            else:
                bronze, silver, gold, embed = (self.result(run_id, stage) for stage in ("bronze", "silver", "gold", "embed"))
                tables = {"bronze": bronze, "silver": silver["table"], "gold": gold["table"]}
                quality = {"silver": silver["quality"], "gold": gold["quality"], "embed": embed["quality"]}
                catalog = self.tables.build_catalog(run_id, tables, quality)
                run = self.store.get_json(f"runs/{run_id}/run.json")
                release = {"schema_version": 1, "run_id": run_id, "created_at": run["created_at"],
                           "published_at": utcnow(), "tables": tables, "quality": quality, "catalog": catalog,
                           "collection": embed["collection"], "vector_count": embed["vector_count"],
                           "dimension": embed["dimension"], "embedding_identity": embed["embedding_identity"],
                           "source_url": self.settings.source_url, "source_terms_note": self.settings.source_terms_note,
                           "config_fingerprint": run["config_fingerprint"], "git_sha": self.settings.git_sha}
            if self.index.count(release["collection"]) != release["vector_count"]:
                raise RuntimeError("Candidate collection changed before publication")
            if self.embedder.identity() != release["embedding_identity"]:
                raise RuntimeError("Embedding model drift before publication")
            base = self.store.get_json(f"runs/{run_id}/run.json")["base_active_etag"]
            return self.publications.publish(release, base)
        return self._stage(run_id, "publish", ["chroma://vl_" + run_id], [self.store.uri("catalog/active.json")], work)

    def run(self, run_id: str | None = None) -> dict:
        started = time.monotonic()
        run_id = self.new_run(run_id)
        for stage in STAGES:
            getattr(self, stage)(run_id)
        report = {"run_id": run_id, "duration_seconds": time.monotonic() - started,
                  "stages": {s: self.store.get_json(f"runs/{run_id}/stages/{s}.json")["duration_seconds"] for s in STAGES}}
        self.store.put_json(f"reports/{run_id}/benchmark.json", report)
        return report

    def rollback(self, run_id: str) -> dict:
        release = self.publications.load(run_id)
        if self.index.count(release["collection"]) != release["vector_count"]:
            raise RuntimeError("Rollback target is missing vectors; restore it first")
        if self.embedder.identity() != release["embedding_identity"]:
            raise RuntimeError("Restore the rollback target's embedding model before switching")
        return self.publications.rollback(run_id)
