#!/usr/bin/env bash
# Start the four code review services in the foreground; Ctrl+C stops all four.
#
#   bash servers/code_review/start_services.sh
#
# Environment:
#   PYTHON       interpreter with servers/code_review/requirements.txt installed (default: python3)
#   HOST         bind address (default: 127.0.0.1)
#   PARSER_PORT / LINTER_PORT / SCANNER_PORT / SUMMARIZER_PORT   (defaults: 8101-8104)
set -euo pipefail

PYTHON="${PYTHON:-python3}"
HOST="${HOST:-127.0.0.1}"
PARSER_PORT="${PARSER_PORT:-8101}"
LINTER_PORT="${LINTER_PORT:-8102}"
SCANNER_PORT="${SCANNER_PORT:-8103}"
SUMMARIZER_PORT="${SUMMARIZER_PORT:-8104}"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDS=()

cleanup() {
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

"$PYTHON" "$DIR/parser_server.py"     --host "$HOST" --port "$PARSER_PORT" &
PIDS+=("$!")
"$PYTHON" "$DIR/linter_server.py"     --host "$HOST" --port "$LINTER_PORT" &
PIDS+=("$!")
"$PYTHON" "$DIR/scanner_server.py"    --host "$HOST" --port "$SCANNER_PORT" &
PIDS+=("$!")
"$PYTHON" "$DIR/summarizer_server.py" --host "$HOST" --port "$SUMMARIZER_PORT" &
PIDS+=("$!")

echo "parser :$PARSER_PORT  linter :$LINTER_PORT  scanner :$SCANNER_PORT  summarizer :$SUMMARIZER_PORT  (pids ${PIDS[*]})"
wait
