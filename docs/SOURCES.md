# Official references and version decisions

Reviewed for this artifact on **September 18, 2026**. These references explain selected interfaces and known risks; they are not evidence that the generated full stack has been executed. Version tags are deliberate baselines, not an assertion that every dependency is the latest or has no vulnerabilities.

| Area | Primary reference | Use in this project |
|---|---|---|
| Public source | https://books.toscrape.com/ | Explicit scraping sandbox; book data is demonstration data |
| Airflow Docker | https://airflow.apache.org/docs/apache-airflow/3.2.0/howto/docker-compose/index.html | Multi-component Airflow 3.2 local setup; not production guidance |
| Airflow simple authentication | https://airflow.apache.org/docs/apache-airflow/3.2.0/core-concepts/auth-manager/simple/index.html | Development/testing auth and persisted password file |
| Airflow token | https://airflow.apache.org/docs/apache-airflow/3.2.0/core-concepts/auth-manager/simple/token.html | JSON `/auth/token` request for real DAG benchmark |
| Airflow run request schema | https://github.com/apache/airflow/blob/3.2.0/airflow-core/src/airflow/api_fastapi/core_api/datamodels/dag_run.py | Explicit nullable logical date in trigger request |
| Delta S3 coordination | https://delta-io.github.io/delta-rs/usage/writing/writing-to-s3-with-locking-provider/ | MinIO conditional puts; DynamoDB tablePath/fileName keys for AWS |
| Delta S3 configuration | https://delta-io.github.io/delta-rs/integrations/object-storage/s3/ | Storage options and credential/locking choices |
| DuckDB Arrow integration | https://duckdb.org/docs/stable/guides/python/sql_on_arrow.html | SQL transforms over Arrow data without runtime extension downloads |
| Chroma client API | https://docs.trychroma.com/reference/python/client | Persistent and HTTP clients, collection access |
| Chroma Docker | https://docs.trychroma.com/guides/deploy/docker | Internal server and persistent `/data` mount |
| Ollama embeddings | https://docs.ollama.com/api/embed | Explicit input embeddings API |
| Ollama structured output | https://docs.ollama.com/capabilities/structured-outputs | JSON schema generation; not semantic truth verification |
| Embedding model | https://ollama.com/library/nomic-embed-text | Local encoder family; selected tag v1.5 |
| Generation model | https://ollama.com/library/qwen3:4b | Local generator baseline |
| Ollama releases | https://github.com/ollama/ollama/releases | Image baseline 0.34.2 |
| MinIO source releases | https://github.com/minio/minio/releases | Archived community repository; source baseline RELEASE.2025-10-15T17-29-55Z includes published security fix |
| MinIO client releases | https://github.com/minio/mc/releases | Source client baseline RELEASE.2025-08-13T08-35-41Z |
| OpenLineage object model | https://openlineage.io/docs/spec/object-model/ | Per-attempt events and input/output dataset identifiers |
| Terraform AWS provider | https://registry.terraform.io/providers/hashicorp/aws/latest/docs | S3, DynamoDB and IAM storage foundation |

Direct Python dependencies are pinned in `requirements.txt`. Airflow is separately pinned in its Dockerfile to avoid mixing the orchestration package into the API image. CI matrix environments resolve the full dependency tree; release SBOMs/digests capture the resulting image. A fully locked/hash-verified transitive install and commit-pinned upstream source/actions are deliberate hardening work, not features silently claimed by this baseline.
