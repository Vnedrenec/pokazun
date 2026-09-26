#!/bin/sh
# Daily at 00:30 UTC (02:30/03:30 Kyiv). On failure posts to the ops group immediately;
# the worker's backup_freshness job alerts again if no success within 26 hours.
set -u

alert() {
  [ -n "${POKAZUN_ALERT_CHAT_ID:-}" ] || return 0
  curl -fsS -m 20 "https://api.telegram.org/bot${POKAZUN_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${POKAZUN_ALERT_CHAT_ID}" \
    --data-urlencode "text=🔴 [${POKAZUN_ENV}] backup
$(date -u '+%Y-%m-%d %H:%M:%S') UTC
$1" > /dev/null || true
}

while true; do
  now=$(date -u +%s)
  target=$(date -u -d "$(date -u +%Y-%m-%d) 00:30:00" +%s)
  [ "$target" -gt "$now" ] || target=$((target + 86400))
  sleep $((target - now))
  if ! /usr/local/bin/backup.sh; then
    alert "backup.sh failed, see: docker compose logs backup"
  fi
done
