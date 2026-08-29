# Architecture decision records

## ADR-001: DuckDB + delta-rs, not a local Spark cluster

**Decision:** use DuckDB SQL for deterministic small-data transforms and delta-rs for transactional table I/O. Keep all stages as separately orchestrated tasks.

**Reasoning:** the workload is 50-100 HTML documents, not terabytes. A JVM/Spark service adds startup, memory and debugging cost without evidence of need. The requirement explicitly permits DuckDB instead of Spark. This is a resource and operability choice, not a statement that Spark is inferior.

**Trade-off:** large distributed joins and compute elasticity are out of scope. Delta paths and stage contracts permit a later Spark implementation, but it would need concurrency and schema-evolution tests.

## ADR-002: Release indirection instead of a mutable global vector collection

**Decision:** produce isolated candidate tables and a candidate vector collection, then switch one active pointer conditionally.

**Reasoning:** a mutable shared collection exposes partially indexed data during ingestion and makes rollback ambiguous. A release contains explicit table versions, vector count, model identity and quality evidence.

**Trade-off:** extra storage and retained candidate cleanup are required. There is no cross-system transaction. Operators must preserve referenced objects and understand post-commit acknowledgement failures.

## ADR-003: One local model service; explicit embedding identity

**Decision:** Ollama provides both a dedicated encoder and a separate generator. The default models are nomic-embed-text:v1.5 and qwen3:4b.

**Reasoning:** no paid inference dependency; a single local model-service interface; embedding prefixes and resolved digest are testable contracts. These defaults are starting points, not a claim of best model quality.

**Trade-off:** loading one model at a time conserves memory but adds model-switch latency. Cold downloads are not offline and do not count as warm pipeline execution. Local model weights still have their own terms. Generation identity pinning needs strengthening for audited production deployments.

## ADR-004: Respectful public sandbox as the default source

**Decision:** crawl Books to Scrape at runtime, cap product pages and requests, and allow a reviewed generic HTML adapter.

**Reasoning:** a purposely provided scraping sandbox makes the demo reproducible without targeting private data, paid content or uncertain publisher permissions.

**Trade-off:** book-catalog questions are a small demonstration domain, not proof of enterprise-document retrieval quality. A docs-domain adapter should bring its own terms review and evaluation set.

## ADR-005: Local MinIO only, with an explicit maintenance warning

**Decision:** retain the requested local MinIO API but build the upstream October 15, 2025 security-fix source release. Provide AWS S3/Delta coordination code and optional Terraform.

**Reasoning:** the public community repository is archived, and using a convenient earlier image would conceal both maintenance risk and a later published security fix.

**Trade-off:** slower cold builds, upstream copyleft obligations, unverified future security exposure. Source build does not equal ongoing maintenance. Production adoption requires a maintained object-storage choice.

## ADR-006: Compose first; useful DevOps over decorative Kubernetes

**Decision:** deliver a single-host Compose stack with real CI, signed image release, approved API deployment, monitoring and recovery tools. Do not bundle an untested "production Kubernetes" stack.

**Reasoning:** the strongest evidence is a working trust/recovery story. A cluster manifest without identity, storage, networking, backup and upgrade ownership would imply more operational maturity than exists.

**Trade-off:** no HA or elastic serving. Scaling introduces distributed rate limiting, identity, workload permissions, storage coordination, data residency and release migration design; those are explicit future decisions.

## ADR-007: Conservative abstention, measured quality

**Decision:** reject invalid citations and unsupported source IDs; retain a human evaluation workflow rather than treating a judge-model score as truth.

**Trade-off:** the prototype may abstain on answerable questions or cite genuine but insufficient evidence. Measure groundedness and useful-answer rate together. Do not hide failures by reducing strictness without evidence.

Official dependency/interface references and their review date are in [SOURCES.md](SOURCES.md).
