# Evaluation and performance protocol

## Four different questions

**Pipeline correctness:** Can malformed data, a stale publisher, incomplete vectors or embedding drift be rejected without replacing a good release? Unit tests, SDK contract tests and native integration tests cover different portions of this question. A mock cannot validate a real service implementation.

**Index integrity:** Can stored vectors be counted and retrieved under the correct embedding identity? Count/dimension/self-retrieval gates establish a limited integrity check, not semantic relevance.

**Retrieval quality:** Do relevant source URLs appear among retrieved results for independently labeled questions? `eval/retrieval.jsonl` provides four first-page book-catalog smoke cases. The evaluator reports URL Recall@k and document-deduplicated MRR. It queries the release index directly without generation. This small set is neither representative nor a valid source of large statistical claims.

**Answer quality:** Is the answer correct, relevant and supported by the cited evidence, and does it abstain appropriately? Source-ID/exact-quote checks are necessary but insufficient. No automated judge is treated as ground truth.

## Local acceptance

```bash
python3 scripts/smoke.py
make evaluate
make benchmark
make benchmark-airflow
```

The smoke script demands a real non-abstained answer with sources for a known answerable question. It saves the captured result, not a canned answer. A correct abstention on that answerable case still fails this useful-answer smoke criterion and needs investigation; the tool does not lower the bar to a 200 status.

Retrieval evaluation saves actual ranks and URLs. Review a failure for extraction, source selection, chunk boundaries, encoder identity and semantic relevance before changing the threshold or prompt.

## Build an honest answer benchmark

Before using this project as senior-level evidence, author a held-out set from the material actually ingested. Include answerable single-source questions, multiple-source questions, changed/stale facts, near-duplicate names, absent facts, hostile instructions and requests for secrets. Do not auto-generate and auto-grade all questions with the same model without independent review.

Use `eval/human_review.csv` for question/run/model identity, expected answerability, observed status, factual correctness, citation support and notes. A practical starting goal is 30-50 reviewed cases, with an independently reviewed subset; this is a recommendation, not data already collected.

Report answerable-question accuracy, supported-claim rate, citation validity, helpful answer rate, unanswerable-question abstention and false-abstention rate separately. A model that abstains on everything is not useful. Include examples of failures, confidence intervals where meaningful, and dataset/version details. The repository contains no fabricated scores for these measures.

## Five-minute pipeline target

The brief specifies 50-100 pages in at most 300 seconds on four CPU cores. The default is 60 selected product documents; pagination and robots requests are additional. Respecting a slower server's required delays takes priority over this target.

`make benchmark` measures the synchronous CLI pipeline and writes `reports/benchmark.json`. It excludes Airflow scheduling. `make benchmark-airflow` uses the actual Airflow public API to trigger a new DAG and records Airflow duration and trigger-to-terminal observed duration. The latter includes queue and polling overhead. Its exit code fails when the run is unsuccessful or the observed span exceeds the budget. It does not mislabel the CLI result as a full DAG result.

Measure three scenarios separately:

| Scenario | Conditions | What it establishes |
|---|---|---|
| Cold bootstrap | No images, models, database or cache | Installation experience; excluded from the warm DAG target |
| Warm services, uncached corpus | Images/models resident, empty embedding cache for that approved corpus | Ingestion/transform/new-embedding pipeline timing |
| Warm services, cached corpus | Same source/model text already embedded | Re-ingestion plus cache benefit, not new-embedding throughput |

Use a dedicated test lake/index or fresh test project for uncached measurements instead of deleting production cache/release objects. Never silently disable robots handling, lower page count below the brief or switch to a fake encoder to pass the target. Repeat several runs and report each observation, median and tail variation. A three-run maximum is not a defensible p95 estimate.

Record CPU model, cores/quota, RAM, free disk, Docker limits, OS, source response conditions, network speed, model digests, accepted/rejected documents, chunks, cache hits/misses, stage durations and Git SHA. `cpu_count` alone does not prove CPU quota. GitHub runner timings are not laptop timings.

**No end-to-end five-minute result has been measured in the supplied artifact.** Cold setup and real local generation were not run in the packaging environment. The live workflow and scripts are acceptance tooling, not pre-existing evidence that the target is met.

## Failure demonstrations

Capture the active release ID before and after an intentionally failed candidate. Demonstrate a stale publication conflict, an Ollama outage with distinct liveness/readiness, an invalid-citation abstention, a retained-release rollback and a fresh-project backup restore. Record actual outputs and recovery times. Unit fixtures cover several of these contracts, but a real recorded demo remains necessary.

## Report template

| Field | Value to fill after execution |
|---|---|
| Commit, release IDs, model digests | Actual identifiers |
| Hardware and CPU quota | Actual machine |
| Pages/documents/chunks | Actual counts |
| Warmness/cache condition | Explicit description |
| CLI duration / Airflow duration | Separate measured values |
| Retrieval cases / Recall@k / MRR | Actual evaluation output |
| Reviewed answer cases and rubric | Actual human evidence |
| Known failures / false abstentions | Include examples |
| Backup restore and rollback results | Actual observed outcomes |

Never replace an unmeasured field with an attractive invented number.
