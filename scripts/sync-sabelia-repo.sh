#!/usr/bin/env bash
# Publish the sabelia/ directory to github.com/aislamsilvalol-ctrl/sabelia as one
# commit on top of that repository's main, so the push is a fast-forward and no
# history is rewritten. The repository is a mirror; the monorepo is the source.
set -euo pipefail
REMOTE=${SABELIA_REMOTE:-git@github.com:aislamsilvalol-ctrl/sabelia.git}
cd "$(dirname "$0")/.."
git fetch -q "$REMOTE" main
REMOTE_MAIN=$(git rev-parse FETCH_HEAD)
TREE=$(git rev-parse "HEAD:sabelia")
if [ "$(git rev-parse "$REMOTE_MAIN^{tree}")" = "$TREE" ]; then
  echo "already in sync ($REMOTE_MAIN)"; exit 0
fi
MSG="Sync from noema $(git rev-parse --short HEAD): $(git log -1 --format=%s)"
COMMIT=$(git commit-tree "$TREE" -p "$REMOTE_MAIN" -m "$MSG")
git push -q "$REMOTE" "$COMMIT:refs/heads/main"
echo "pushed $COMMIT ($MSG)"
