#!/usr/bin/env bash
# Restores the latest dump into a scratch database and checks it. Usage: deploy/restore-test.sh prod
set -euo pipefail

ENV_NAME="${1:-prod}"
ENV_FILE="/opt/pokazun/$ENV_NAME/.env"
set -a; . "$ENV_FILE"; set +a
export POKAZUN_ENV="$ENV_NAME" POKAZUN_ENV_FILE="$ENV_FILE"
DC=(docker compose -f /opt/pokazun/src/deploy/compose.yml --env-file "$ENV_FILE")

"${DC[@]}" exec -T db dropdb -U pokazun --if-exists restore_test
"${DC[@]}" exec -T db createdb -U pokazun restore_test
"${DC[@]}" --profile backup run --rm backup sh -c \
  'LATEST=$(ls -1t /backups/pokazun-*.dump | head -1) && echo "restoring $LATEST" &&
   PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -h db -U pokazun -d restore_test --no-owner "$LATEST"'
"${DC[@]}" exec -T db psql -U pokazun -d restore_test -v ON_ERROR_STOP=1 \
  -c "SELECT version_num FROM alembic_version" \
  -c "SELECT count(*) AS users FROM users"
"${DC[@]}" exec -T db dropdb -U pokazun restore_test
echo "restore test OK"
