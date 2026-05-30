#!/usr/bin/env bash
# SweepBot 데이터 백업
# crontab: 0 3 * * * /home/ubuntu/projects/SweepBot/scripts/backup.sh >> /home/ubuntu/logs/sweepbot_backup.log 2>&1

set -euo pipefail
BACKUP_SRC="/home/ubuntu/.openclaw"
BACKUP_DST="/home/ubuntu/backups/sweepbot"
KEEP_DAYS=7
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DST}/openclaw_${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DST"

if [ ! -d "$BACKUP_SRC" ]; then
    echo "[$(date)] WARN: 백업 대상 없음 — ${BACKUP_SRC}"
    exit 0
fi

tar -czf "$BACKUP_FILE" \
    --exclude="${BACKUP_SRC}/logs" \
    -C "$(dirname "$BACKUP_SRC")" "$(basename "$BACKUP_SRC")"

echo "[$(date)] OK: 백업 완료 → ${BACKUP_FILE} ($(du -sh "$BACKUP_FILE" | cut -f1))"
find "$BACKUP_DST" -name "openclaw_*.tar.gz" -mtime "+${KEEP_DAYS}" -delete
echo "[$(date)] OK: ${KEEP_DAYS}일 초과 파일 정리 완료"
