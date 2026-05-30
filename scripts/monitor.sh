#!/usr/bin/env bash
# SweepBot 시스템 상태 모니터링 (Oracle Free Tier 자원 회수 방지)
# crontab: */5 * * * * /home/ubuntu/projects/SweepBot/scripts/monitor.sh >> /home/ubuntu/logs/sweepbot_monitor.log 2>&1

set -euo pipefail
LOG_DIR="/home/ubuntu/logs"
mkdir -p "$LOG_DIR"
TS=$(date +"%Y-%m-%d %H:%M:%S")

CPU_IDLE=$(top -bn1 | grep "Cpu(s)" | awk '{print $8}' | tr -d '%id,')
CPU_USED=$(echo "100 - ${CPU_IDLE:-0}" | bc 2>/dev/null || echo "N/A")
MEM_INFO=$(free -m | awk '/^Mem:/{printf "used=%dMB total=%dMB", $3, $2}')
DISK_INFO=$(df -h / | awk 'NR==2{printf "used=%s avail=%s", $3, $4}')
LOAD=$(uptime | awk -F'load average:' '{print $2}' | xargs)

check_service() { systemctl --user is-active "$1" 2>/dev/null || systemctl is-active "$1" 2>/dev/null || echo "inactive"; }

OPENCLAW=$(check_service openclaw-gateway)
MSS_API=$(systemctl is-active mss-api 2>/dev/null || echo "inactive")
NGINX=$(systemctl is-active nginx 2>/dev/null || echo "inactive")

MOLT_PING=$(curl -sf --max-time 5 http://127.0.0.1:3000/molt/ > /dev/null 2>&1 && echo "ok" || echo "fail")

echo "[${TS}] cpu=${CPU_USED}% mem=(${MEM_INFO}) disk=(${DISK_INFO}) load=(${LOAD})"
echo "[${TS}] openclaw=${OPENCLAW} mss-api=${MSS_API} nginx=${NGINX} molt_ping=${MOLT_PING}"

if [ "$OPENCLAW" != "active" ] || [ "$MOLT_PING" != "ok" ]; then
    echo "[${TS}] WARN: SweepBot 비정상 상태 감지"
fi
