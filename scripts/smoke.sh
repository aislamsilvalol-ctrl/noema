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

echo "smoke: a mutation without the CSRF header must be refused"
STATUS=$(curl -sS -o /dev/null -w '%{http_code}' -X POST -b "$JAR" \
  -H 'content-type: application/json' \
  -d "{\"subject_id\":\"$SUBJECT\",\"title\":\"Forged\"}" "$BASE/notebooks")
[ "$STATUS" = "403" ] || fail "CSRF protection did not reject a missing token (got $STATUS)"

echo "smoke: an anonymous read must be refused"
STATUS=$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/notebooks")
[ "$STATUS" = "401" ] || fail "anonymous access was not refused (got $STATUS)"

echo "smoke: ok"
