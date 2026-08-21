#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $# -eq 1 ]] || { echo 'Usage: bash scripts/restore.sh backups/TIMESTAMP'; exit 1; }
backup=$(realpath "$1")
[[ -f "$backup/SHA256SUMS" ]] || { echo 'No backup manifest'; exit 1; }
project=$(python3 -c 'import sys; sys.path.insert(0,"scripts"); from envutil import local_env; print(local_env().get("COMPOSE_PROJECT_NAME","veritylake"))')
[[ "$project" =~ ^[a-z0-9_-]+$ ]] || { echo 'Invalid project name'; exit 1; }
(cd "$backup" && sha256sum -c SHA256SUMS)
# Refuse to overwrite any existing state. A restore rehearsal should use a fresh project name.
for name in minio-data chroma-data postgres-data ollama-data airflow-config airflow-logs; do
  if docker volume inspect "${project}_${name}" >/dev/null 2>&1; then
    echo "Refusing to overwrite existing volume ${project}_${name}. Use a fresh COMPOSE_PROJECT_NAME." >&2
    exit 1
  fi
  [[ -f "$backup/${name}.tar.gz" ]] || { echo "Missing ${name}.tar.gz"; exit 1; }
done
for name in minio-data chroma-data postgres-data ollama-data airflow-config airflow-logs; do
  volume="${project}_${name}"
  docker volume create --label "com.docker.compose.project=$project" --label "com.docker.compose.volume=$name" "$volume" >/dev/null
  docker run --rm --user 0 --volume "$volume:/target" --volume "$backup:/backup:ro" \
    python:3.12-slim-bookworm tar -C /target -xzf "/backup/${name}.tar.gz"
done
echo 'Restored cold snapshot. Keep the original .env credentials. Start, then run smoke and verify-release.'
