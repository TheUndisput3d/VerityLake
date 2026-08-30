# Delivery and operational infrastructure

## Workflow map

| Workflow | Trigger | What it actually does |
|---|---|---|
| `ci.yml` | PR, main push, reusable call, manual | Python 3.12/3.13 tests, Ruff, static/config checks, JS/shell syntax, pip audit, secret scan, real MinIO/Chroma/Delta contract job, actual Airflow DAG parse check, Terraform validation |
| `release.yml` | `v*` tag | Runs CI, builds/pushes four images, generates SBOM/provenance, scans exact digest, keyless-signs after passing, publishes build attestation |
| `deploy.yml` | Manual approved request | Validates a version/digest, checks Cosign signing identity, connects over pinned-host-key SSH, updates API and health-gates rollback |
| `live-acceptance.yml` | Manual | Boots the full stack, waits for a published dataset, asks the real model, evaluates retrieval, measures CLI and actual Airflow runs, uploads results |

Committing workflow files does not enable branch protection, environment approvals, or a successful build. There are no fake green status badges. Native integration CI still uses a deterministic **test-only encoder/source** to isolate database contracts; only the manual live workflow exercises runtime web ingestion and actual Ollama generation.

## Publish the repository

```bash
git init -b main
git add .
git status --short
# Verify .env, .venv, backups, cloud state, model files and private runtime data are absent.
git commit -m "Build governed scrape-to-RAG platform with reversible data publication"
# Create an empty repository in your GitHub account, then use its actual URL:
git remote add origin REPLACE_WITH_YOUR_REPOSITORY_URL
git push -u origin main
```

Review `.gitignore` and the packaging report before the first push. A generated ZIP is not a previously published GitHub repository. Configure required CI checks and PR review on main, read-only default workflow token permissions, and Dependabot updates. Pin action commits and reviewed image digests as a hardening follow-up. Direct Python pins do not constitute a complete transitive hash lock.

## Release images

After CI genuinely passes:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Image naming is `ghcr.io/<owner>/<repository>-api`, `-airflow`, `-minio`, and `-storage-tools`. Names are derived from your repository; no namespace is hardcoded to someone else's account. Images are pushed before the scan, then signed only after passing. A failed scan can therefore leave an **unsigned candidate tag**. Never deploy a tag just because it exists.

Inspect the workflow artifacts, dependency findings, image SBOM, provenance and signature. The current Trivy gate uses HIGH/CRITICAL with `--ignore-unfixed`; this is an explicit policy for fixable findings, not a zero-vulnerability claim. Review unfixed findings separately. The storage Dockerfile ships its corresponding upstream source archives/licenses inside the images; review all redistribution obligations.

## Approved API deployment

The target host must already have Docker/Compose, this exact repository layout, a private `.env`, initialized lake/model/database volumes, a successful published dataset, and registry read access. It is a pre-provisioned **single-host API upgrade path**, not a full server provisioning or platform migration workflow.

Create a GitHub environment named `production`, require an approver and restrict allowed release refs. Add environment secrets:

| Secret | Meaning |
|---|---|
| `DEPLOY_HOST` | Trusted host DNS name or IPv4 address |
| `DEPLOY_USER` | Dedicated deployment user |
| `DEPLOY_PATH` | Absolute repository directory on that host |
| `DEPLOY_SSH_KEY` | Restricted deployment SSH private key |
| `DEPLOY_KNOWN_HOSTS` | Host-key entries verified through a trusted channel |

The deployment user must access Docker; that access is effectively privileged and needs host-level restrictions. Do not use unverified `ssh-keyscan` output as your trust root. Configure private GHCR read credentials on the host separately when required. No long-lived registry credential is embedded in the repository.

Manually dispatch `deploy.yml` with the actual pushed API SHA-256 digest and version label. The workflow verifies the certificate identity for this repository's release workflow and that exact tag, verifies the issuer, and then invokes `scripts/deploy_api.sh`.

The script serializes deployments with `flock`, pulls the digest, replaces the API, and polls readiness. If readiness fails it restarts the previous image reference. **There may be downtime**, the rollback is not guaranteed to succeed, and it does not undo data/schema changes. Verify recovery. It does not deploy the Airflow image or storage services and does not provide database migration compatibility guarantees.

A successful API deployment writes `release.env`. Subsequent commands must use `docker compose --env-file .env --env-file release.env ...`, or you must deliberately update `APP_IMAGE` in `.env`; otherwise an ordinary Compose command may select the old default image. The standalone script does not verify signatures itself; the protected workflow does. Running it manually bypasses that verification unless the operator performs it separately.

## Observability

`make observe` enables Prometheus and Grafana. The dashboard JSON is versioned under `ops/grafana/dashboards`. It displays request rate, latency, answer/abstention outcomes, HTTP status distribution, active chunks and dataset age. Alerts cover availability/errors/stale data. The local rules do not configure an Alertmanager notification destination; an operator still needs to connect an alerting channel.

The API exposes process liveness separately from dataset/index/model readiness. The readiness gauge represents the **last readiness probe**, not a continuously running dependency monitor. Metrics avoid source URLs/questions as labels. JSON logs contain request/run IDs for correlation. Airflow UI/logs are the stage-duration and orchestration view; no fake distributed tracing spans are emitted.

`ops/loadtest.js` is a k6 starting point. It generates genuine inference load and can compete with pipeline/model work. Record its load, hardware and model residency. It does not establish an SLO until executed and interpreted.

## Infrastructure and recovery

The local Compose stack supplies bootstrap dependency ordering, persistent volumes, resource limits and selected container hardening. The AWS Terraform module supplies storage/IAM coordination only. No Kubernetes cluster, public load balancer, TLS certificate, managed database or cloud GPU is silently provisioned.

Cold backup/restore procedures are in [RUNBOOK.md](RUNBOOK.md). Rehearse restoration with a new project name and record results. "Backup script exists" is not evidence of recovery. Security limitations and production prerequisites are in [SECURITY.md](../SECURITY.md).
