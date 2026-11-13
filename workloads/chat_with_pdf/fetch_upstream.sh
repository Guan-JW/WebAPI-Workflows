#!/usr/bin/env bash
# Fetch the pinned upstream application (sparse, shallow) and check its file hashes.
#
#   ./fetch_upstream.sh [DEST]      default DEST: <this directory>/upstream (git-ignored)
#
# Needs git >= 2.27 and network access to github.com. Nothing is executed from the fetched tree.
set -euo pipefail

REPO=https://github.com/Shubhamsaboo/awesome-llm-apps.git
COMMIT=6c16b23f1bacd0fdf240bb5141ef45e59e82c306
APP_PATH=advanced_llm_apps/chat_with_X_tutorials/chat_with_pdf
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$HERE/upstream}"

# sha256 of the files the workload uses (source.json "upstream.files").
EXPECTED="
3f1d44bf1913dcc5620c37d64c556bfedbc02e7861e5757bdfd4cca6f2c61f84  $APP_PATH/chat_pdf.py
8b5e74a86a87b3e753b7cf0ac0199cf39f29e097424491e35e8b9495a4a807b9  $APP_PATH/requirements.txt
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
