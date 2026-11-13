#!/usr/bin/env bash
# Fetch the pinned upstream application (sparse, shallow) and check its file hashes.
#
#   ./fetch_upstream.sh [DEST]      default DEST: <this directory>/upstream (git-ignored)
#
# Needs git >= 2.27 and network access to github.com. Nothing is executed from the fetched tree.
set -euo pipefail

REPO=https://github.com/Shubhamsaboo/awesome-llm-apps.git
COMMIT=6c16b23f1bacd0fdf240bb5141ef45e59e82c306
APP_PATH=voice_ai_agents/ai_audio_tour_agent
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$HERE/upstream}"

# sha256 of the files the workload uses (source.json "upstream.files").
EXPECTED="
12cb4026c537a324122b4761ed637460fd31fe16c2511890053ea9f6366ca3d5  $APP_PATH/ai_audio_tour_agent.py
75a43dbb23a0fba507100db15ae0e58c51a1625a39b744b86d7f9a14cba1617c  $APP_PATH/manager.py
31aa8fba009757713e0bfb8eab0edce75fdb8b7659a60059cf76f0ef3765ca68  $APP_PATH/agent.py
e58f32a96db2903e1347e007cd08a8b597f8b811d95968bd87eeb9809d9826f4  $APP_PATH/printer.py
2faa93b919a1679cec93f647553db59822b0e36a3178cea2588ea5379e99534f  $APP_PATH/requirements.txt
14f33996a2d100aa2b5a750598c9db93de8f4097a669e32e8cb843534ca5c3c2  $APP_PATH/README.md
c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4  LICENSE
"

mkdir -p "$DEST"
cd "$DEST"
if [ ! -d .git ]; then
  git init -q
  git remote add origin "$REPO"
fi
git sparse-checkout set --no-cone "/$APP_PATH/" /LICENSE
git fetch -q --depth 1 --filter=blob:none origin "$COMMIT"
git -c advice.detachedHead=false checkout -q --detach "$COMMIT"
[ "$(git rev-parse HEAD)" = "$COMMIT" ] || { echo "pin failed: HEAD is $(git rev-parse HEAD)" >&2; exit 1; }

if command -v sha256sum >/dev/null 2>&1; then SHA="sha256sum -c -"; else SHA="shasum -a 256 -c -"; fi
echo "$EXPECTED" | sed '/^$/d' | $SHA
echo "upstream app at $DEST/$APP_PATH (commit $COMMIT)"
