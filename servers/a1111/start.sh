#!/usr/bin/env bash
# Start the AUTOMATIC1111 WebUI API server(s) set up by setup.sh, as deployed in development.
#
#   bash start.sh DIR [unload|default|both]     (default: both)
#
#   unload   port 7861, started with DINO_UNLOAD_AFTER_CALL=1.
#            Serves head_fashion, image_blur and segment_ocr (their default --a1111-url).
#   default  port 7860, no extra environment. Serves caption_compare (its default --a1111-url).
#   both     both instances, from the same install, on the same GPU (as in development).
#
# Environment: HOST (default 127.0.0.1), A1111_ARGS (extra launch flags, default none),
# CUDA_VISIBLE_DEVICES, HF_HOME. Logs go to DIR/logs/. The script returns when every started
# instance answers GET /sam/heartbeat (model loading can take a few minutes) or after 15 minutes.
# Stop with: pkill -f "launch.py --skip-prepare-environment --nowebui --api"
set -euo pipefail
DIR=$(cd "${1:?usage: start.sh DIR [unload|default|both]}" && pwd)
WHICH=${2:-both}
W=$DIR/webui
HOST=${HOST:-127.0.0.1}
mkdir -p "$DIR/logs"

launch() {  # name port unload(0|1)
  local envs=()
  [ "$3" = 1 ] && envs+=(DINO_UNLOAD_AFTER_CALL=1)
  ( cd "$W" && env ${envs[@]+"${envs[@]}"} venv_dir=venv nohup bash ./webui.sh --skip-prepare-environment --nowebui --api \
      --server-name "$HOST" --port "$2" ${A1111_ARGS:-} > "$DIR/logs/a1111_$1.log" 2>&1 & )
  echo "started $1 on $HOST:$2 (DINO_UNLOAD_AFTER_CALL=$([ "$3" = 1 ] && echo 1 || echo unset)); log $DIR/logs/a1111_$1.log"
}

PORTS=""
case $WHICH in
  unload)  launch unload 7861 1; PORTS="7861" ;;
  default) launch default 7860 0; PORTS="7860" ;;
  both)    launch default 7860 0; launch unload 7861 1; PORTS="7860 7861" ;;
  *) echo "unknown instance '$WHICH' (unload|default|both)" >&2; exit 1 ;;
esac

t0=$(date +%s)
for p in $PORTS; do
  until [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://$HOST:$p/sam/heartbeat")" = 200 ]; do
    if [ $(( $(date +%s) - t0 )) -gt 900 ]; then echo "port $p not ready after 900 s; see $DIR/logs" >&2; exit 1; fi
    sleep 10
  done
  echo "ready: http://$HOST:$p  ($(( $(date +%s) - t0 )) s)"
done
