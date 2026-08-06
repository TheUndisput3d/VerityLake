# Security model and disclosure

## Scope

VerityLake is a single-user, single-host development/portfolio platform. It is not a public multi-tenant service, a security certification, or a promise that an archived dependency is safe. Keep the published host ports bound to localhost. Use a private repository security advisory to report a vulnerability after hosting the project; do not file real credentials in a public issue.

## Implemented controls

The crawler validates URLs, rejects private/reserved DNS answers outside tests, restricts origin/path scope, handles redirects manually, honors robots and delays, bounds retries/pages/bytes, and does not bypass paywalls or access controls. Raw material is untrusted. Normalization redacts simple email patterns and quarantines a small set of instruction-like strings.

The API needs a random key, uses constant-time comparison, enforces request size/top-k and per-process rate/concurrency limits, runs as a non-root user with a read-only root filesystem, dropped capabilities and no-new-privileges. Chroma and Ollama have no host-published ports. The API gets only the MinIO catalog-reader credential; Airflow gets the writer credential; root credentials are limited to storage/bootstrap services.

The custom UI uses text nodes, not untrusted HTML insertion, and has a restrictive content security policy. It holds the key only in page memory. Uvicorn access logs are disabled; application logs exclude question bodies, query strings, model prompts and credentials. Container logs rotate locally. `.env` is generated with restrictive permissions and ignored by Git and Docker build context.

Release images receive SBOM/provenance and are signed after scan gates. Deploy verifies the exact expected repository/workflow/tag identity before using the image digest. These controls require actual successful workflow execution; source YAML alone is not an attestation.

## Known boundaries

| Threat | Remaining limitation / required production control |
|---|---|
| SSRF and DNS rebinding | Pre-request DNS validation has a resolution/connection gap. Enforce network-level outbound policy or a trusted fetch proxy. Docker bridge networking is not an egress firewall. |
| Prompt injection | Regex quarantine and prompts are incomplete defenses. There are no model tools, but hostile text can still degrade answers. Use representative adversarial evaluation and stronger isolation before sensitive deployments. |
| PII and licensed content | Email redaction is narrow and raw HTML remains unredacted. It does not detect names, addresses, health data or all secrets. Ingest only approved sources; apply real retention/privacy review. |
| Catalog/index mutation | Immutability is application convention. A privileged writer or compromised Chroma server can alter same-count data. Introduce stronger access separation, object retention controls and content verification. |
| Authentication | One shared API key and local Airflow SimpleAuth are not user identity or tenant isolation. Add OIDC/mTLS/gateway controls and secret management. |
| Network service trust | Chroma and Ollama are trusted internal services without a public auth boundary in this stack. A container on the network is a privileged actor. |
| Request abuse | Rate limits are per process and do not limit all administrative routes. Add gateway body limits, distributed quotas, timeouts and model scheduling before scaling. |
| GET questions | Browsers and proxies can retain URLs. Prefer POST and review every logging hop. |
| Supply chain | Direct Python requirements are pinned but transitive dependencies, base-image tags and action refs are not fully digest/SHA locked. Resolve/review locks, pin source commits and images, and rescan regularly. |
| Maintenance | MinIO community is archived. The patched-source baseline is not ongoing support. Production storage must have a maintenance owner. |
| Credentials and backups | Docker inspect can expose environment credentials to a Docker administrator. Backups contain sensitive service state. Use workload identity/secrets and encrypted controlled backups in production. |
| Availability | A single host, volume or model process failure can stop service. No HA, multi-zone design or measured disaster-recovery objective is supplied. |

## Deployment prerequisites

Before public or business use, perform an explicit threat review, replace local auth, use TLS at every appropriate boundary, limit crawler egress, review source rights, upgrade to maintained dependencies, run actual build/scanner/service tests, test restore and migration procedures, and establish monitoring ownership. No cloud access keys should be committed. Terraform role trust and deployment host hardening remain operator responsibilities.

Scanner findings are not automatically waived. The image gate currently blocks **fixable** HIGH/CRITICAL findings (`--ignore-unfixed`); unfixed and lower-severity findings need review and are not proof of safety. An unsigned candidate image may exist if a post-push scan fails; only verified signed digests may be deployed.
