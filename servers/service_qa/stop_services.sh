#!/usr/bin/env bash
# Stop the services started by start_services.sh (same LOG_DIR).
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$DIR/../.." && pwd)"
LOG_DIR="${LOG_DIR:-$REPO/runs/service_qa/server_logs}"
shopt -s nullglob
for pidfile in "$LOG_DIR"/*.pid; do
  pid="$(cat "$pidfile")"
  if kill "$pid" 2>/dev/null; then echo "stopped $(basename "$pidfile" .pid) ($pid)"; fi
  rm -f "$pidfile"
done
