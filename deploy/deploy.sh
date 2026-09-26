#!/usr/bin/env bash
# Usage: deploy/deploy.sh <staging|prod> [git-ref]
# Order: build → (prod: manual backup) → migrations → restart → smoke check.
set -euo pipefail

ENV_NAME="${1:?usage: deploy.sh <staging|prod> [git-ref]}"
REF="${2:-origin/main}"
case "$ENV_NAME" in staging|prod) ;; *) echo "unknown env: $ENV_NAME" >&2; exit 2 ;; esac

ROOT=/opt/pokazun
SRC="$ROOT/src"
ENV_FILE="$ROOT/$ENV_NAME/.env"
[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE" >&2; exit 2; }

cd "$SRC"
git fetch --tags origin
git checkout --detach "$REF"
SHA=$(git rev-parse --short HEAD)

docker build -t "pokazun:$SHA" .
docker tag "pokazun:$SHA" "pokazun:$ENV_NAME"

set -a; . "$ENV_FILE"; set +a
export POKAZUN_ENV="$ENV_NAME" POKAZUN_ENV_FILE="$ENV_FILE"
DC=(docker compose -f "$SRC/deploy/compose.yml" --env-file "$ENV_FILE")

"${DC[@]}" up -d db
if [ "$ENV_NAME" = prod ]; then
  "${DC[@]}" --profile backup build backup
  "${DC[@]}" --profile backup run --rm backup /usr/local/bin/backup.sh
fi
"${DC[@]}" --profile migrate run --rm migrate
"${DC[@]}" up -d --remove-orphans

for _ in $(seq 1 30); do
  if curl -fsS -m 5 "${POKAZUN_PUBLIC_BASE_URL%/}/healthz"; then
    echo; echo "deployed $ENV_NAME @ $SHA"
    exit 0
  fi
  sleep 2
done
echo "smoke check failed for $ENV_NAME @ $SHA" >&2
exit 1
