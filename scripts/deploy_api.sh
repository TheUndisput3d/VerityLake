#!/usr/bin/env bash
# Run on a provisioned host from this repository. The stateful platform must already exist.
set -euo pipefail
cd "$(dirname "$0")/.."
image=${1:?Usage: bash scripts/deploy_api.sh ghcr.io/OWNER/REPO-api@sha256:DIGEST}
[[ "$image" =~ ^ghcr\.io/[a-z0-9._/-]+@sha256:[a-f0-9]{64}$ ]] || { echo 'Require an immutable GHCR digest'; exit 1; }
exec 9>.deploy.lock
flock -n 9 || { echo 'Another deployment is in progress'; exit 1; }
previous=$(docker inspect --format '{{.Config.Image}}' "$(docker compose ps -q api)")
export APP_IMAGE="$image"
docker pull "$APP_IMAGE"
docker compose up -d --no-deps --no-build api
healthy=false
for attempt in $(seq 1 36); do
  if curl --silent --fail --max-time 10 http://127.0.0.1:8000/readyz >/dev/null; then healthy=true; break; fi
  sleep 5
done
if [[ "$healthy" != true ]]; then
  export APP_IMAGE="$previous"
  docker compose up -d --no-deps --no-build api
  echo 'New API did not become ready. Previous image restored; verify recovery manually.' >&2
  exit 1
fi
printf 'APP_IMAGE=%s\n' "$image" > release.env
chmod 600 release.env
echo 'API image deployed. This does not migrate data or update the Airflow worker image.'
echo 'Use --env-file .env --env-file release.env for subsequent Compose commands, or update APP_IMAGE in .env.'
