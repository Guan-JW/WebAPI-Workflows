#!/usr/bin/env bash
# Fetch the pinned upstream application (sparse, shallow) and check its file hashes.
#
#   ./fetch_upstream.sh [DEST]      default DEST: <this directory>/upstream (git-ignored)
#
# Needs git >= 2.27 and network access to github.com. Nothing is executed from the fetched tree.
set -euo pipefail

REPO=https://github.com/Shubhamsaboo/awesome-llm-apps.git
COMMIT=6c16b23f1bacd0fdf240bb5141ef45e59e82c306
APP_PATH=rag_tutorials/hybrid_search_rag
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$HERE/upstream}"

# sha256 of the files the workload uses (source.json "upstream.files").
EXPECTED="
e099e9fe654ddb82083a1b255d1ca11fd1fab7579657e41acf6da9bc5d430cc2  $APP_PATH/main.py
974958236e9eb98305d60463f74af5f9113c68990f0259dba8db6fe90bd4119f  $APP_PATH/requirements.txt
51bdb5ccb798e0f1b41714d01603b25792e368452ccd6c7149eb6877eae9aa60  $APP_PATH/README.md
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
