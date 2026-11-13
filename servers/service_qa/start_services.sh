#!/usr/bin/env bash
# Start the five question-answering services in the background and wait until
# the two retrieval indexes are loaded. Stop them with stop_services.sh.
#
#   bash servers/service_qa/start_services.sh
#
# Environment:
#   PYTHON            interpreter with servers/service_qa/requirements.txt installed (default: python3)
#   RAG_HOST          bind address (default: 127.0.0.1)
#   RAG_EMBED_PORT / RAG_VEC_PORT / RAG_BM25_PORT / RAG_RERANK_PORT / RAG_GEN_PORT  (defaults: 8201-8205)
#   RAG_GEN_BACKEND   qwen (default) | template (plumbing check only)
#   RAG_CORPUS_DIR    corpus directory (default: $WBENCH_DATA/service_qa/corpus or <repo>/data/service_qa/corpus)
#   LOG_DIR           service logs and pid files (default: <repo>/runs/service_qa/server_logs)
#   WAIT_S            seconds to wait for the indexes (default: 1800)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$DIR/../.." && pwd)"
PYTHON="${PYTHON:-python3}"
LOG_DIR="${LOG_DIR:-$REPO/runs/service_qa/server_logs}"
WAIT_S="${WAIT_S:-1800}"
: "${RAG_HOST:=127.0.0.1}"
: "${RAG_EMBED_PORT:=8201}"
: "${RAG_VEC_PORT:=8202}"
: "${RAG_BM25_PORT:=8203}"
: "${RAG_RERANK_PORT:=8204}"
: "${RAG_GEN_PORT:=8205}"
: "${RAG_GEN_BACKEND:=qwen}"
export RAG_HOST RAG_EMBED_PORT RAG_VEC_PORT RAG_BM25_PORT RAG_RERANK_PORT RAG_GEN_PORT RAG_GEN_BACKEND
mkdir -p "$LOG_DIR"

start() {  # name file
  echo "starting $1 -> $LOG_DIR/$1.log"
  nohup "$PYTHON" "$DIR/$2" > "$LOG_DIR/$1.log" 2>&1 &
  echo $! > "$LOG_DIR/$1.pid"
}

start embedder      embedder_server.py
start vector_search vector_search_server.py
start bm25          bm25_server.py
start reranker      reranker_server.py
start generator     generator_server.py

t0=$(date +%s)
while :; do
  ok=1
  for p in "$RAG_EMBED_PORT" "$RAG_RERANK_PORT" "$RAG_GEN_PORT"; do
    curl -sf "http://$RAG_HOST:$p/health" > /dev/null || ok=0
  done
  for p in "$RAG_VEC_PORT" "$RAG_BM25_PORT"; do
    curl -sf "http://$RAG_HOST:$p/health" | grep -q '"loaded":true' || ok=0
  done
  [ "$ok" = 1 ] && break
  if [ $(( $(date +%s) - t0 )) -ge "$WAIT_S" ]; then
    echo "services not ready after ${WAIT_S}s; see $LOG_DIR" >&2
    exit 1
  fi
  sleep 5
done
echo "all five services ready after $(( $(date +%s) - t0 ))s"
for p in "$RAG_EMBED_PORT" "$RAG_VEC_PORT" "$RAG_BM25_PORT" "$RAG_RERANK_PORT" "$RAG_GEN_PORT"; do
  printf '  :%s %s\n' "$p" "$(curl -sf "http://$RAG_HOST:$p/health")"
done
