# Operator runbook

## Start, diagnose and stop

```bash
python3 scripts/bootstrap.py
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 model-init airflow-init airflow-scheduler api
curl --fail http://localhost:8000/healthz
curl --fail http://localhost:8000/readyz
```

A process can be alive without a usable dataset. A 503 from readiness before the first successful publication is expected. The Airflow DAG must reach publish, both local models must be installed, and the selected Chroma collection must be complete. Diagnose the first failed dependency rather than repeatedly restarting everything.

Use `docker compose down` to stop and remove containers while retaining data. `docker compose stop` keeps containers as well. A `down --volumes` or volume prune operation is destructive and may delete model downloads; it is not normal cleanup.

## First run does not start

Inspect `minio-init`, `model-init` and `airflow-init` logs. Source image builds require internet and Go module downloads. Models require disk space and a working upstream download path. Invalid `.env` placeholders, occupied localhost ports, DNS failures or insufficient RAM can prevent initialization.

Bootstrap deliberately does not overwrite existing `.env`. Do not regenerate secrets against existing volumes without planning credential updates. Airflow passwords are persisted in its config volume; the `.env` value and persisted value must remain consistent.

## Crawl or quality gate failed

Read the Airflow task log and candidate `raw/<run>/errors.json`, `robots.json`, `quality/<run>/...` and `quarantine/<run>/silver.json` objects. Check source permissions and extraction selectors before changing thresholds. A robots denial or long Retry-After is not a reason to disable respectful crawling.

```bash
make catalog
make history
# A new DAG run is required for new input/configuration.
make trigger
```

The active run should remain unchanged when a new run fails before publication. Replaying a completed run ID returns its checkpoints rather than recrawling. If the pipeline has never published, the API correctly remains unready.

## Publication conflict

A compare-and-swap conflict means another publisher changed the base release. It is not a transient connectivity retry. Confirm which run is active, inspect both candidates, and create a new run from the current base. Do not hand-edit `active.json` or remove the ETag check.

Do not run the CLI pipeline and Airflow concurrently during the demo. `max_active_runs=1` serializes Airflow, not independent shell processes.

## Rollback

```bash
make history
make rollback RUN_ID=REPLACE_WITH_PREVIOUS_32_CHARACTER_RUN_ID
docker compose run --rm tools verify-release
python3 scripts/smoke.py
```

Rollback verifies the target collection count and current encoder identity before changing the pointer. Retain the corresponding object-store data and Chroma collection. If the target uses another encoder digest, restore that exact model first; merely pulling a similarly named tag is not proof of identity. A rollback to a stale dataset still fails the serving freshness policy. Audit intents record requested changes; only the pointer proves selection.

## Dependency outage rehearsal

```bash
docker compose stop ollama
curl -i http://localhost:8000/healthz
curl -i http://localhost:8000/readyz
docker compose start ollama
```

Expected: liveness can remain 200 while readiness is 503. Questions must not get invented fallback answers. Repeat the smoke test after recovery. Timeouts may delay failure observation; inspect the configured model timeout.

## Model drift or bad answers

Use `/catalog` to inspect the selected embedding name/digest and release. Model drift requires restoring the original encoder or a full new embedding/publication run. A low relevant-hit rate requires evaluating extraction, chunking and retrieval before altering generation prompts.

A citation validation abstention is not an infrastructure outage. Inspect retrieval fixtures and conduct human review. Never label a high self-retrieval score as evidence of answer correctness. Questions outside the book catalog should abstain.

## Backup

```bash
make backup
```

The script stops the stack and makes a **cold** snapshot of MinIO, Chroma, Postgres, model data, Airflow config and logs, with SHA-256 checksums. The stack remains stopped until explicitly restarted. The backup contains source content and stored service configuration; keep it private, encrypted and access-controlled. `.env` is deliberately not copied: preserve the original credentials separately in an encrypted location. Grafana/Prometheus historical volumes are not included.

This is a single-host recovery mechanism, not database PITR, an online snapshot protocol or a measured RPO/RTO guarantee. A backup is not trusted until restored and tested.

## Restore rehearsal

Use a fresh project name in a separate copy of the repository, preserve the original credentials, and stop the old stack if its localhost ports conflict. The restore script refuses to overwrite any existing named volumes.

```bash
# In the recovery copy, edit COMPOSE_PROJECT_NAME in the original preserved .env.
bash scripts/restore.sh /absolute/path/to/backup/TIMESTAMP
docker compose up -d
docker compose run --rm tools verify-release
python3 scripts/smoke.py
```

Only restore your own trusted archives. The script does not sanitize adversarial tar files. Record backup creation time, restore start/end, restored run ID and smoke result to measure RPO/RTO. Existing trigger/scheduler state resumes from the restored Airflow database.

## Disk and memory

```bash
df -h
docker system df -v
docker stats --no-stream
```

Model caches, source-build layers, retained Delta versions and Chroma collections consume disk. Review build cache separately from persistent data. Do not delete one side of a retained release independently. No automatic data garbage collector is provided because it must follow cross-store references.

On OOM, first reduce workload/concurrency, close other heavy processes or increase Docker memory. Do not claim five-minute performance after silently switching hardware or page count. The optional observability profile adds memory. Generation/embedding model switches can cause latency on a memory-constrained host.

## API deployment

See [DEVOPS.md](DEVOPS.md). The digest-based script assumes a provisioned host, a running platform and a registry-readable image. It deploys the API only and can interrupt service. A failed readiness check restores the prior image reference, then requires operator verification. It cannot undo schema migrations or recover deleted state.
