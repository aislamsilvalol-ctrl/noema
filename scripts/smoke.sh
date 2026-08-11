#!/usr/bin/env bash
# End-to-end smoke test against a running stack.
#
# Walks the path a new user actually takes: register, create a subject and a
# notebook, write a note, read it back. Every request carries the session cookie
# and the CSRF header, so this also proves the auth wiring works from the outside
# rather than only in unit tests.
#
# Usage: bash scripts/smoke.sh [base_url]

set -euo pipefail

BASE="${1:-http://localhost:8000}/api/v1"
JAR="$(mktemp)"
EMAIL="smoke-$(date +%s)@example.com"
PASSWORD="correct-horse-battery-staple"

trap 'rm -f "$JAR"' EXIT

fail() { echo "smoke: $1" >&2; exit 1; }

# Read a field from a JSON body on stdin. `field` is a dotted path; list indices
# are written as plain numbers, e.g. `items.0.id`.
json() {
  python3 -c '
import json, sys
value = json.load(sys.stdin)
for part in sys.argv[1].split("."):
    value = value[int(part)] if part.isdigit() else value[part]
print(value)
' "$1"
}

# curl writes a Netscape cookie jar: name is the sixth tab-separated field.
csrf() { awk -F'\t' '$6 == "noema_csrf" { print $7 }' "$JAR"; }

api() {
  local method="$1" path="$2" body="${3:-}"
  local args=(-sS --fail-with-body -X "$method" -b "$JAR" -c "$JAR"
              -H 'content-type: application/json' -H "x-csrf-token: $(csrf)")
  [ -n "$body" ] && args+=(-d "$body")
  curl "${args[@]}" "$BASE$path"
}

echo "smoke: registering $EMAIL"
curl -sS --fail-with-body -c "$JAR" -H 'content-type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"display_name\":\"Smoke\"}" \
  "$BASE/auth/register" > /dev/null || fail "registration failed"

echo "smoke: reading the workspace created on registration"
WORKSPACE=$(api GET "/workspaces" | json 'items.0.id') || fail "no workspace"
[ -n "$WORKSPACE" ] && [ "$WORKSPACE" != "null" ] || fail "registration did not create a workspace"

echo "smoke: creating a subject"
SUBJECT=$(api POST "/subjects" "{\"workspace_id\":\"$WORKSPACE\",\"title\":\"Machine Learning\"}" \
  | json 'id') || fail "subject creation failed"

echo "smoke: creating a notebook"
NOTEBOOK=$(api POST "/notebooks" "{\"subject_id\":\"$SUBJECT\",\"title\":\"Neural Networks\"}" \
  | json 'id') || fail "notebook creation failed"

echo "smoke: writing a note"
NOTE=$(api POST "/notes" \
  "{\"notebook_id\":\"$NOTEBOOK\",\"title\":\"Backpropagation\",\"content_md\":\"See [[Chain Rule]].\"}" \
  | json 'id') || fail "note creation failed"

echo "smoke: reading the note back"
api GET "/notes/$NOTE" | grep -q "Chain Rule" || fail "note content did not round-trip"

echo "smoke: listing providers and credentials"
# Both endpoints serialise frozen slots dataclasses, which is where a working unit
# test and a broken endpoint managed to coexist once already.
api GET "/ai/providers" | grep -q '"name"' || fail "provider listing failed"
[ "$(api GET "/ai/credentials")" = "[]" ] || fail "credential listing should start empty"

echo "smoke: streaming a tutor reply"
curl -sS --fail-with-body -b "$JAR" -H 'content-type: application/json' \
  -H "x-csrf-token: $(csrf)" \
  -d "{\"notebook_id\":\"$NOTEBOOK\",\"mode\":\"socratic\",\"messages\":[{\"role\":\"user\",\"content\":\"what is a derivative\"}]}" \
  "$BASE/ai/chat" | tee /tmp/chat.sse | grep -q "^event: done" \
  || { cat /tmp/chat.sse; fail "chat stream did not complete"; }
grep -q "^event: token" /tmp/chat.sse || fail "chat stream produced no tokens"

echo "smoke: explaining a selection"
curl -sS --fail-with-body -b "$JAR" -H 'content-type: application/json' \
  -H "x-csrf-token: $(csrf)" \
  -d '{"text":"the gradient points uphill"}' \
  "$BASE/notes/$NOTE/actions/explain" | tee /tmp/action.sse | grep -q "^event: done" \
  || { cat /tmp/action.sse; fail "selection action did not complete"; }

echo "smoke: the note was not modified by the action"
api GET "/notes/$NOTE" | grep -q "Chain Rule" || fail "note changed after a selection action"

echo "smoke: uploading a document"
DOC=$(mktemp /tmp/noema-smoke-XXXX.md)
cat > "$DOC" <<'DOCUMENT'
# Optimization

Gradient descent minimises a loss by stepping downhill.

## Convergence

It converges when the step size is small enough relative to the curvature.
DOCUMENT

SOURCE=$(curl -sS --fail-with-body -b "$JAR" -H "x-csrf-token: $(csrf)" \
  -F "notebook_id=$NOTEBOOK" -F "file=@$DOC;type=text/markdown" \
  "$BASE/sources" | json 'id') || fail "upload failed"
rm -f "$DOC"

echo "smoke: queueing ingestion"
api POST "/sources/$SOURCE/ingest" '{}' > /dev/null || fail "could not queue ingestion"

echo "smoke: waiting for the worker to finish"
for attempt in $(seq 1 60); do
  STATE=$(api GET "/sources/$SOURCE" | json 'status')
  case "$STATE" in
    ready) break ;;
    failed) api GET "/sources/$SOURCE"; fail "ingestion failed" ;;
  esac
  sleep 2
done
[ "$STATE" = "ready" ] || fail "ingestion did not finish in 120s (last state: $STATE)"

echo "smoke: the document was chunked"
CHUNKS=$(api GET "/sources/$SOURCE" | json 'chunk_count')
[ "$CHUNKS" -gt 0 ] || fail "ingestion produced no chunks"
echo "smoke: $CHUNKS chunks"

echo "smoke: re-uploading the same file is refused as a duplicate"
DUP=$(mktemp /tmp/noema-dup-XXXX.md)
printf '# Optimization\n\nGradient descent minimises a loss by stepping downhill.\n\n## Convergence\n\nIt converges when the step size is small enough relative to the curvature.\n' > "$DUP"
STATUS=$(curl -sS -o /dev/null -w '%{http_code}' -b "$JAR" -H "x-csrf-token: $(csrf)" \
  -F "notebook_id=$NOTEBOOK" -F "file=@$DUP;type=text/markdown" "$BASE/sources")
rm -f "$DUP"
[ "$STATUS" = "409" ] || fail "duplicate upload was not refused (got $STATUS)"

echo "smoke: an executable upload is refused"
EXE=$(mktemp /tmp/noema-exe-XXXX)
printf '\x7fELF\x02\x01\x01' > "$EXE"
STATUS=$(curl -sS -o /dev/null -w '%{http_code}' -b "$JAR" -H "x-csrf-token: $(csrf)" \
  -F "notebook_id=$NOTEBOOK" -F "file=@$EXE;filename=notes.md" "$BASE/sources")
rm -f "$EXE"
[ "$STATUS" = "415" ] || fail "an executable was not refused (got $STATUS)"

echo "smoke: a mutation without the CSRF header must be refused"
STATUS=$(curl -sS -o /dev/null -w '%{http_code}' -X POST -b "$JAR" \
  -H 'content-type: application/json' \
  -d "{\"subject_id\":\"$SUBJECT\",\"title\":\"Forged\"}" "$BASE/notebooks")
[ "$STATUS" = "403" ] || fail "CSRF protection did not reject a missing token (got $STATUS)"

echo "smoke: an anonymous read must be refused"
STATUS=$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/notebooks")
[ "$STATUS" = "401" ] || fail "anonymous access was not refused (got $STATUS)"

echo "smoke: ok"
