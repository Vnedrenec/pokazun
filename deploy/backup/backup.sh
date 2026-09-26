#!/bin/sh
# One backup run: dump → local retention → off-VPS copy → marker. Any failure exits non-zero.
set -eu

TS=$(date -u +%Y%m%dT%H%M%SZ)
FILE="/backups/pokazun-${TS}.dump"

PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h db -U pokazun -d pokazun -Fc -f "${FILE}.partial"
mv "${FILE}.partial" "$FILE"
find /backups -name 'pokazun-*.dump' -mtime +13 -delete

if [ -z "${BACKUP_REMOTE:-}" ]; then
  echo "BACKUP_REMOTE is not set: off-VPS copy is required" >&2
  exit 1
fi
rclone copy "$FILE" "$BACKUP_REMOTE"
rclone delete --min-age 14d "$BACKUP_REMOTE"

date -u +%Y-%m-%dT%H:%M:%SZ > /backups/last_backup_at
echo "backup ok: $FILE"
