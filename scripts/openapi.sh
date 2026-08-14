#!/usr/bin/env bash
# Dump the API's OpenAPI schema to a file the web app generates types from.
#
# Committed rather than fetched at build time: the frontend build must not need a
# running backend, and a schema in git means a change to the API surface shows up
# as a reviewable diff rather than as a type error somebody hits later.
set -euo pipefail

cd "$(dirname "$0")/../apps/api"
OUT="../../openapi.json"

python - "$OUT" <<'PY'
import json
import sys

from noema.main import app

schema = app.openapi()
# Sorted and indented so the diff is readable and stable: an unordered dump makes
# every regeneration look like a change.
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(schema, handle, indent=2, sort_keys=True, ensure_ascii=False)
    handle.write("\n")

print(f"{len(schema['paths'])} paths, {len(schema['components']['schemas'])} schemas")
PY
