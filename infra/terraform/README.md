# Optional AWS object-storage foundation

This module provisions S3, DynamoDB Delta commit coordination and scoped IAM policies. It does **not** deploy Airflow, compute, Ollama, Chroma, networking, or a production control plane. Local Compose remains the default. It does not create AWS access keys.

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit the unique bucket name and, optionally, existing role names.
terraform init
terraform fmt -recursive
terraform validate
terraform plan -out=plan.tfplan
# Review the plan and your account's current costs before applying.
terraform apply plan.tfplan
```

Use an authenticated AWS CLI/SSO or workload role. Do not place credentials in tfvars. Initial provider resolution creates `.terraform.lock.hcl`; review and commit that lock file. Keep Terraform state in an access-controlled encrypted backend before collaborating; no remote backend is silently created by this example.

For application processes on the target infrastructure, set `STORAGE_BACKEND=s3`, `S3_ENDPOINT_URL=` (empty means AWS), `S3_BUCKET`, `S3_REGION`, and `DELTA_LOCK_TABLE` to the module outputs. Give ingestion the writer role and serving the reader role. SDK workload-identity credentials are preferred. Explicit short-lived `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN` are also supported. The stock Compose file injects **local MinIO credentials**, so do not assume changing only its bucket name switches it to AWS. Use a deployment-specific environment overlay for all application/Airflow services or the standalone CLI/API with these variables. Do not run `init-store` with the writer role: Terraform creates and versions the bucket.

The DynamoDB keys are `tablePath` (partition) and `fileName` (sort), with optional `expireTime` TTL. This matches the selected delta-rs locking provider. No unsafe-rename mode is enabled. S3 conditional publication is a separate operation from Delta commits.

`prevent_destroy`, bucket `force_destroy=false`, and DynamoDB deletion protection are deliberate. Decommission by reviewing retained releases and backups first; changing safeguards requires an explicit code review. Only incomplete multipart uploads expire automatically; published data is never blindly aged out.

**Cost and validation:** cloud storage, requests, DynamoDB, backup and transfer can incur charges. No free-tier guarantee is made. This module was not applied or validated with Terraform in the artifact-building environment. CI contains `init -backend=false` and `validate` checks; their results must be obtained after pushing the repository.

References: https://delta-io.github.io/delta-rs/usage/writing/writing-to-s3-with-locking-provider/ and https://registry.terraform.io/providers/hashicorp/aws/latest/docs .
