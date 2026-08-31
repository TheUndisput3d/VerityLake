# Recruiter demonstration and interview guide

## Positioning

**VerityLake: a governed data-to-RAG platform that makes AI data changes inspectable and reversible.** The distinguishing work is not calling an LLM. It is defining and testing the contract between ingestion, table snapshots, retrieval indexes, model identity and application visibility.

Relevant roles include AI Platform Engineer, Data Platform Engineer, MLOps/DataOps Engineer and DevOps Engineer with AI infrastructure responsibilities. A repository does not establish seniority by itself. Explain the choices, reproduce the results, diagnose a failure and show how requirements change the design.

## Demo narrative

Start with a real question and its returned evidence, not a wall of service logos. Open the citation, show the run ID, then the catalog, corresponding Gold/Silver data and raw source. Demonstrate that the claimed traceability actually connects.

Next trigger a candidate that fails a quality gate and show that the active release ID remains the previous good release. Explain why a mutable shared vector collection would make this harder. Show one publication conflict and discuss the single-object commit boundary, not "distributed ACID".

Then stop Ollama. Show liveness, failed readiness and unavailable answers without fabricated fallback. Restore the dependency, show recovery, and perform an explicit rollback to retained data. Discuss model-digest compatibility and freshness limits.

Finish with genuine CI logs, signed digest/SBOM evidence, a real timing report and the known limitations. A good demo admits the difference between a tested local prototype and a production service. Screenshots/videos should hide keys and source data that cannot be redistributed.

## Questions worth preparing for

| Interview question | What a strong answer should address |
|---|---|
| Why not Spark/Kubernetes? | Workload size, resource budget, operability and clear conditions for changing the decision |
| Is publication atomic? | One pointer switch, table-local Delta transactions, no global cross-store transaction, crash-after-commit behavior |
| What does idempotent mean here? | Run IDs, config fingerprints, checkpoints and cache; no global exactly-once claim |
| Can a source attack the system? | Untrusted data, no model tools, crawler limits, remaining DNS-rebinding/injection risks |
| Do citations guarantee truth? | Provenance validation versus entailment; independent held-out answer evaluation |
| How do you upgrade embeddings? | New model identity, cache separation, reindexing, validation, release switch, rollback compatibility |
| What happens at ten million documents? | Revisit compute, incremental ingestion, memory/batching, vector design, retention and orchestration; no extrapolated throughput claim |
| How would you serve multiple customers? | Identity, document ACL filters, tenant-specific storage/index boundaries, quotas and auditability |
| What is your recovery objective? | Actual restore rehearsals and measurements; scripts alone do not establish RPO/RTO |
| What concerns you about MinIO? | Archived community maintenance, patched-source baseline limits, migration to a maintained service |

## Resume wording

Use this only after you have run and understood the project:

> Built a local-first data-to-RAG platform with Airflow, DuckDB/Delta Lake, S3-compatible storage, Chroma and Ollama, including evidence-linked answers, quality-gated dataset publication and model-aware embedding consistency checks.

> Implemented release-indirection and conditional publication controls, structured lineage/quality evidence, explicit data rollback, operational monitoring, and CI workflows for testing, scanning and signed container delivery.

After obtaining your own measurements, add a result such as "processed [actual count] documents on [actual hardware] in [actual measured full-DAG duration]". Do not copy placeholder values, report mocks as real integration tests, or claim production uptime, enterprise scale, a senior title or business impact that did not occur.

## Before applying

Run the full stack on your machine, resolve CI findings, publish actual acceptance artifacts and a small reviewed answer benchmark, rehearse backup restoration, and record a demonstration that includes a failure and recovery. Make one meaningful improvement yourself and write an ADR explaining its trade-off. The ability to own and explain the project is more valuable than a longer technology list.
