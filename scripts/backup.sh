#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then echo 'Missing .env' >&2; exit 1; fi
# Only read the project name; do not source arbitrary files as shell code.
project=$(python3 -c 'import sys; sys.path.insert(0,"scripts"); from envutil import local_env; print(local_env().get("COMPOSE_PROJECT_NAME","veritylake"))')
[[ "$project" =~ ^[a-z0-9_-]+$ ]] || { echo 'Invalid project name'; exit 1; }
destination="$(pwd)/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$destination"; chmod 700 "$destination"
echo 'Stopping the stack for a consistent cold snapshot. Backups contain source data; keep them private.'
docker compose stop
for name in minio-data chroma-data postgres-data ollama-data airflow-config airflow-logs; do
  volume="${project}_${name}"
  docker volume inspect "$volume" >/dev/null
  docker run --rm --user 0 --volume "$volume:/source:ro" --volume "$destination:/backup" \
    python:3.12-slim-bookworm tar -C /source -czf "/backup/${name}.tar.gz" .
done
(cd "$destination" && sha256sum ./*.tar.gz > SHA256SUMS)
printf '%s\n' "$project" > "$destination/project.txt"
echo "Backup stored in $destination"
echo 'The stack remains stopped. Preserve .env separately in an encrypted location. Restart: docker compose up -d'
