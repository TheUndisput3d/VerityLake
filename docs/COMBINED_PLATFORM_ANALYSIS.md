# VerityLake + CiteMind: integration feasibility and design

Analysis date: 21 September 2026. Scope: static inspection of both local repositories, not a runtime acceptance test. No application changes or migration performed. “Two gateways” is interpreted as two ingestion entry points, website collection and document/paper import, under one application. Two query modes are proposed separately below.

## Recommendation

Combine VerityLake's data preparation, quality gates, provenance and conditional release publication with CiteMind's research interface, document adapters, hybrid retrieval and reranking. Treat this as an architectural integration rather than concatenating folders or installing both requirements files into one environment.

The resulting product could be a governed research knowledge platform: collect approved web content and research documents, preserve source versions, publish checked datasets, and answer with traceable passages and page references. Better retrieval and stronger evidence handling are plausible benefits to evaluate, not measured achievements.

## What exists today

| Capability | VerityLake | CiteMind research RAG |
|---|---|---|
| Web acquisition | Bounded same-origin crawler with robots, URL and content checks | Explicit URL loading with WebBaseLoader; Tavily discovery/search routes |
| PDFs | Not supported by its current crawler | Local PDF uploads parsed with PyMuPDFLoader |
| arXiv | No adapter | ID/title lookup, metadata request and PDF download |
| Other documents | HTML-derived text | TXT and Markdown loaders |
| Original evidence | Raw HTML and diagnostics retained in MinIO | Upload/arXiv temporary files deleted after indexing |
| Structured processing | Bronze/Silver/Gold Delta snapshots | LangChain documents/chunks directly indexed |
| Chunking | 220-word windows, 35-word overlap, exact Silver offsets | Recursive 1,000-character splitting, 200-character overlap, start-index metadata |
| Retrieval | Chroma cosine dense search | Qdrant named dense/sparse vectors; FastEmbed BM25 |
| Reranking | None | CrossEncoder, default 24 retrieval candidates and final six |
| Encoder identity | Tag, digest and prefix version; checked cache identity | Cache namespace based on model name; dimension/schema checks |
| Publication | Per-run collections, manifest, conditional active pointer | Session collection updated in place |
| Answer checks | Structured answer, source-ID consistency and exact quote matching | Model prompting and source inspector; no equivalent quote validator |
| Conversation | One-question interface | React sessions, SSE chat, retrieved context, graph inspection |
| Orchestration | Airflow ingestion DAG | LangGraph online routing/rewrite/generation |
| State | MinIO, Chroma, Airflow PostgreSQL | Qdrant, session JSON, SQLite checkpoints, local embedding cache |
| Operations | Real API metrics, scoped tests and release/recovery tooling | Compose/Kubernetes templates, smoke/evaluation scripts; gaps below |

The tools have different responsibilities. Airflow should schedule ingestion jobs; LangGraph should coordinate bounded question workflows. There is no need to choose one orchestrator for both responsibilities.

## Current PDF behavior: important exact boundaries

VerityLake's `src/veritylake/crawler.py` accepts HTML/XHTML responses and skips discovered `.pdf` links. Its default source selector and record pattern are book-specific. The generic HTML adapter can be configured for other suitable sites, but does not parse PDFs or execute browser JavaScript. Same-origin rules also reject ordinary cross-domain paper downloads unless a separate explicit download policy is introduced.

CiteMind's `backend/paper_loader.py` supports local PDFs. However, `load_document()` sends every HTTP(S) input to `load_webpage()` before inspecting extensions. The `/documents/urls` route also calls `load_webpage()` directly. Consequently, arbitrary PDF URLs do not have a dedicated PDF-download path. The arXiv path is separate and does download PDFs.

Its arXiv ID parser strips version suffixes such as v2, so requesting a specific revision does not preserve that revision in the download identifier. Its title-search path automatically takes one result. A stronger product should preserve resolved versions and ask the user to select ambiguous search results.

The PDF loader has no explicit OCR workflow, table/figure extraction pipeline, or reading-order quality gate. Plain PDF extraction can yield poor ordering in complex layouts; scanned documents need a separate OCR path. See the primary [PyMuPDF text documentation](https://pymupdf.readthedocs.io/en/latest/recipes-text.html) and [OCR documentation](https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html). Upload support should not be described as comprehensive research-document understanding.

## Proposed gateways and shared processing

```text
Gateway A: approved website seed + crawl policy
  HTML discovery -> capture HTML
  permitted PDF discovery -> bounded PDF downloader

Gateway B: uploaded PDF/TXT/Markdown + PDF URL + arXiv import
  validate input -> resolve source/version -> capture original bytes

Both -> raw objects in MinIO
     -> Bronze extraction records and metadata
     -> Silver normalized blocks/pages and quarantine
     -> Gold source-linked chunks
     -> dense + sparse index in a candidate Qdrant collection
     -> extraction/data/index gates
     -> manifest + conditional active selection
     -> authorized research workspace retrieval
     -> rerank -> generate -> validate citations -> UI
```

A discovered paper should use the same document adapter as a manually imported PDF, avoiding two incompatible parsers. A paper landing page and its linked PDF are related artifacts, not automatically the same source. Store the discovery relationship and distinguish snippets/abstracts from full text.

Share processing contracts while preserving different acquisition policies. Website rules include robots and crawl limits; uploads need bounded bytes/page counts, content-type and signature checks, parser timeouts and resource limits. PDF download redirects and each allowed destination need validation. Access scope must be attached before indexing, not filtered only in the browser.

## Schema and quality changes

Introduce source records with stable source ID, source type, canonical URL or original filename, workspace/owner scope, retrieval timestamp, original byte hash, MIME type, raw-object key, parser/version/settings and acquisition status. Paper-specific metadata should include title, authors, identifiers, explicitly resolved arXiv revision, publication date and relevant source/license information when available. Unknown metadata should remain unknown.

Preserve page/block extraction artifacts. Chunks need source/version ID, page or page range, section when reliably extracted, text, parser/chunker version and offsets into an explicitly identified normalized text artifact. Bounding boxes and structured table cells require additional extraction support; do not invent them from plain text. Current VerityLake offsets cannot simply be reinterpreted as PDF page coordinates.

Keep a distinction between source identity, version identity and duplicate content. One paper downloaded via two gateways should be detectable by bytes/identifiers while retaining both acquisition records and their access scopes. Retrying an upload should not create arbitrary duplicate vectors.

Use quality profiles rather than the book defaults for everything. A one-paper workspace can be valid, so the 50-document gate is inappropriate. Check extraction coverage, empty pages, suspected scan pages, chunk/page provenance and expected index coverage. References or author-contact sections require context-aware handling rather than indiscriminate rejection.

Separate publication age, acquisition time, source revision and last update check. An old paper can remain a valid historical source; a question about the latest state of research requires recent discovery and careful qualification. The 72-hour active-dataset age rule should become a source/corpus policy, not a universal paper-expiration rule.

## Retrieval and release design

Recommended target: one Qdrant-based retrieval adapter with dense/sparse search and optional cross-encoder reranking, while preserving VerityLake's release protocol. Qdrant supports hybrid/multistage retrieval and fusion; see its [official hybrid-query documentation](https://qdrant.tech/documentation/search/hybrid-queries/). This matches functionality already present in CiteMind. Keep Chroma as the migration baseline until equivalent gates and serving checks pass; running both indefinitely is unnecessary for the initial combined product.

Do not copy CiteMind's destructive schema handling: `get_vectorstore()` deletes an existing collection if its schema/dimension check fails. A query path can call this method. A governed implementation should report incompatibility and build a new isolated candidate, never silently delete a published index.

Do not mix scores directly. VerityLake's 0.65 cosine-distance cutoff is not a suitable threshold for fused hybrid scores or reranker outputs. Calibrate each stage with held-out questions. Embed all compatible collections using explicit document/query semantics and an identity including actual model digest, preprocessing and dimension. Record sparse model settings, parser/chunker versions and reranker configuration in release/answer evidence too.

Replace the single global active pointer with scoped release selection for each corpus/workspace. A conversation records which permitted corpus releases it uses. Resolve these once per answer request so rewriting and reranking do not accidentally mix releases after an update. Historical turns retain their exact evidence references even when new data is published.

Start with full candidate snapshots per corpus, as VerityLake does, for an understandable first implementation. Incremental additions/deletions and retention-aware cleanup are later work. An uploaded private paper must never enter every user's global release accidentally.

## Query modes and streaming

Offer “Published sources” as the default: retrieve only authorized published releases, with citation checks and explicit abstention. Offer “Discover research” separately for live search and new paper discovery. Show live search snippets as unpublished external evidence, and provide an import action to bring full documents through the ingestion pipeline. General chat, if retained, should be visibly outside evidence-backed answers.

CiteMind's current generation streams tokens before an equivalent final citation validator exists. A combined strict answer path should stream stage progress, then emit the validated answer. Alternatively, explicitly mark streamed text provisional and finalize/retract it after validation. It must not label unchecked tokens as verified evidence-backed output.

The claim-verification route currently has an LLM assess Tavily snippets. Its prompt asks for real result URLs, but `ClaimVerificationResult` only validates structure; membership in the search results and logical support are not mechanically verified. Treat this as literature-discovery assistance, with uncertainty and source provenance, rather than proof that a scientific claim has been overturned.

## Concrete issues to resolve before reuse

1. `backend/api.py` has no authentication/ownership enforcement on session list/read/delete routes. Session-separated collections are not user authorization.
2. Uploads call `await upload.read()` without an application byte bound, and parsing/indexing run inline in that async route. Move heavy processing to bounded background jobs with status/cancellation semantics.
3. General URL loading has no explicit equivalent of VerityLake's crawler destination policy. Reuse a policy-controlled fetch layer for remote documents.
4. Upload/arXiv raw files are deleted after parsing. Persist original bytes and parser outputs before indexing.
5. Cache identity uses model name, and the collection compatibility check primarily covers dimensions/schema. Replace this with the stricter encoder identity contract.
6. Vector search catches broad exceptions and returns an empty list. Separate infrastructure failure from a legitimate no-match result.
7. `load_session_chats()` attaches the latest stored graph state to the first assistant message. It does not reconstruct accurate per-turn evidence. Persist response/evidence records per turn.
8. Query rewriting appends a synthetic HumanMessage, which the current history serializer can display as a user message. Keep original user input distinct from internal retrieval queries.
9. Session metadata uses read-modify-write JSON without transaction/locking semantics. Session deletion removes metadata and vectors but does not explicitly remove SQLite checkpoints or shared embedding-cache data. Define persistence and deletion ownership.
10. Prometheus is configured to scrape `/api/health`, which returns JSON rather than Prometheus metrics. Replace this with actual metrics exposition. The health route also does not verify Qdrant/model readiness.
11. The HPA template permits multiple replicas while the application relies on local JSON/SQLite state. Templates alone do not establish safe distributed operation. Begin with a verified single-host deployment.
12. VerityLake and CiteMind have conflicting dependency pins, including FastAPI and PyArrow versions. Reconcile/test dependencies or keep workers in separate images. Shared provider configuration must explicitly choose local inference versus external services.

These are code-inspection findings, not claims that vulnerabilities were exploited or runtime errors reproduced.

## UI direction

Reuse CiteMind's React conversation layout, session sidebar, source upload controls, Markdown/math rendering and evidence panel. Add acquisition jobs and extraction failures, corpus/release selection, quality summary, paper page citations and a source viewer. Add a provenance panel connecting response to chunk, paper revision, extraction artifact and original file. Keep developer graph JSON secondary to the user's research task.

The two ingestion gateways can appear as “Collect websites” and “Import papers” within one Sources workspace. They do not require two unrelated applications, logins or vector databases.

## Phased implementation and acceptance

1. Baseline both projects independently; record actual boot, document load, question and recovery behavior. Fix startup/evidence gaps before migration.
2. Define shared source, extraction, chunk, release, workspace and answer-evidence contracts. Implement local digital-PDF upload with original retention and page-linked citations first.
3. Add controlled PDF URL and version-preserving arXiv acquisition; connect allowed PDF discovery from the web gateway. Verify retries and duplicate imports.
4. Add the Qdrant release adapter and compare dense-only, hybrid, and hybrid-plus-reranker retrieval under the same corpus/questions. Preserve candidate isolation and rollback tests.
5. Connect React and bounded LangGraph query workflows to published releases; implement authentication/ownership, per-turn evidence and safe streaming semantics.
6. Add OCR/layout/table handling based on documented extraction failures. Add broader literature discovery after strict published-source answers work.

Acceptance cases: a normal PDF with exact page evidence; an image-only PDF that is OCR-processed or explicitly rejected; a paper imported twice without duplicate identity; a website with a permitted external PDF host; a preserved arXiv revision; a failed candidate leaving active selection unchanged; an incompatible model blocking retrieval without deleting data; a private paper inaccessible to another user; a restarted chat retaining correct per-turn evidence; and an answerable/unanswerable evaluation set with human-reviewed support.

Measure extraction coverage, document/page Recall@k and MRR, citation location/quote validity, useful answers, unsupported claims, abstention errors and latency/resource use. Compare against each existing baseline. More tools and more model calls do not establish a stronger system without this evidence.
