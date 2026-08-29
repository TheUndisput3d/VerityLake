# Architecture and correctness boundaries

## System of record

The object store is the durable data/metadata record. Delta tables hold schema-bound Parquet data and transaction logs. Chroma is a derived, run-specific retrieval index. DuckDB performs deterministic SQL deduplication and creates a portable metadata database. Airflow records orchestration state; it does not contain the source corpus in XCom.

The active release is selected by `catalog/active.json`. A reader loads that small object once per request, resolves its immutable-by-application-convention manifest, and uses that manifest's collection/model identity. It does not discover "latest" independently in three different systems.

## Stage contracts

| Stage | Durable inputs | Outputs | Failure behavior |
|---|---|---|---|
| Initialize | Current pointer ETag + public configuration | Run ID, creation timestamp, configuration fingerprint, base ETag | Reject reusing a run under different configuration |
| Scrape | Permitted source and robots rules | Original HTML bytes, extracted text, page metadata, robots/errors, document list | Refuse too few accepted documents; preserve diagnostics when the crawl returns |
| Bronze | Raw document list | Typed Delta document table | No active release changes |
| Silver | Exact Bronze version | Normalized, deduplicated Delta documents; quality and quarantine reports | Reject missing/short text, suspicious instruction patterns, bad timestamps, excess rejection or insufficient unique documents |
| Gold | Exact Silver version | Bounded chunks with stable IDs and normalized-text offsets | Reject duplicate IDs, invalid offsets, missing document coverage or excessive chunk counts |
| Embed | Exact Gold version | Cached embeddings, candidate Chroma collection, index-integrity report | Reject invalid vectors/counts, failed self-retrieval or model identity mismatch |
| Publish | Passed stage outputs | DuckDB catalog, release manifest, audit intent, active pointer | Conditional pointer update refuses a stale publisher |

## Data schema

Documents have `doc_id`, canonical `url`, `title`, `text`, timezone-aware `fetched_at`, `content_sha256`, `raw_key`, HTTP `etag`, `last_modified`, status and byte count. Silver replaces the text hash after normalization; HTML identity and normalized identity are different concepts.

Chunks include `chunk_id`, parent `doc_id`, ordinal, URL/title, exact text, `char_start`, `char_end`, text hash, fetch timestamp, raw key and chunker version. Chunk IDs include document/content identity, chunker version, window size, overlap and position. Changing normalization/chunking requires a new run. NFKC and whitespace normalization plus optional email redaction occur before the recorded offsets are created.

Catalog tables are `datasets(name, uri, delta_version, row_count, run_id)`, `columns(dataset, name, type)`, and `checks(stage, name, passed)`. Detailed observations and thresholds live in the corresponding JSON quality reports. The catalog is metadata, not a copy of all source documents.

## Commit protocol

A candidate writes data only below its own run paths and Chroma collection. It validates the candidate, writes a release manifest using put-if-absent, writes a publication-intent record, and then conditionally replaces the active pointer against the ETag captured at initialization. MinIO/S3 use `If-Match` or `If-None-Match`; the filesystem test/development store uses an advisory file lock plus atomic file replacement.

This is **one atomic visibility point**, not a distributed transaction across Delta, Chroma, Airflow and S3. Delta provides table-local transactions; the application composes them with release indirection. Completed paths are immutable by convention, not protected by S3 Object Lock. A privileged writer can still mutate or remove them, so production hardening needs stronger controls and integrity verification.

Crash boundaries matter:

- A failed crawl/transform/embed before pointer commit does not replace the active release.
- Candidate tables or a release manifest can exist without ever becoming active. A publication intent is not proof of success.
- The pointer may commit before a lineage COMPLETE event or Airflow acknowledgement. Retrying publication recognizes an already-active identical release. This is at-least-once execution with idempotent operations, not global exactly-once semantics.
- A new run based on an old active ETag cannot silently overwrite a newer publication. It must be rerun/reviewed against the new base.
- Clearing an already-completed stage returns its recorded result. To recrawl, use a new DAG run; do not clear tasks expecting a new dataset.

A run's stage outputs are checkpointed after durable lineage completion. Retrying an incomplete Delta write uses overwrite **only in that candidate's run-owned table**; published tables are not the retry target. One active Airflow run is allowed. Manual operators must avoid multiple writers to the same run ID; pointer CAS is not a per-stage distributed lease.

## Model and retrieval consistency

The embedding identity contains model name, Ollama-resolved digest and prefix version. It is included in cache keys and stored with the release and collection. The default encoder uses `search_document:` for indexed text and `search_query:` for questions. Vectors are checked for finite values, nonzero norm, consistent count and dimension.

The self-retrieval probe verifies that a known vector can find its own chunk among its nearest hits. It does not evaluate semantic relevance or answer correctness. Retrieval uses explicit externally generated embeddings; Chroma never silently downloads a different default embedder.

Serving checks the live encoder identity against the release and refuses stale data. Readiness also verifies vector count and generation-model availability. These checks cannot detect every same-count content tampering scenario. A compromised storage/index administrator remains outside this prototype's trust boundary.

## Generation boundary

Retrieved passages are untrusted data and cannot call tools. A bounded JSON-schema prompt asks the local model to answer or abstain. Source IDs, inline references and exact contiguous quotes are checked against the supplied passages. Invalid JSON/citations produce an abstention. HTTP/model failures produce 503, not a fabricated answer.

An unrelated but genuine quote can still accompany an incorrect claim. The validator checks provenance syntax, not logical entailment. Human evaluation, stronger claim-level verification and calibrated retrieval/reranking are production work. The retrieval-distance cutoff is a configurable starting heuristic, not a calibrated probability.

## Lineage and logging

Each stage attempt emits OpenLineage START and COMPLETE or FAIL with its own UUID and job identity. Durable JSON is written under `/lineage`; an optional remote receiver is best-effort. No Marquez server is bundled. Stage manifests and release metadata connect the data, quality, model identity and source provenance.

Application logs are structured and use request/run IDs without question bodies, prompts, source content or keys. Logs go to stderr; JSON CLI results go to stdout. Third-party services and upstream proxies have separate logging behavior and must be reviewed before processing private data.

## Retention, availability and scale

The design retains releases for rollback and intentionally does not provide naive age-based deletion. A correct collector must start from active and retained release references, traverse Delta files/catalogs/vector collections, mark live objects, and collect only unreachable candidates after a grace period. Chroma volumes and object-store data must be backed up coherently.

This is a single-node system. No HA scheduler, replicated object store, multi-zone database, tenant-aware authorization or distributed request limiter is claimed. The local database/catalog choice keeps the demo explainable and makes a future boundary change explicit instead of pretending a laptop is a distributed production platform.
