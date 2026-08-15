#!/usr/bin/env bash
#
# Ask a deployment which commit it is running, and say so plainly.
#
# A failed deploy is not the dangerous case — the previous container keeps
# serving and nothing breaks. The dangerous case is not knowing. Between 12 and
# 14 August 2026 every deploy of this API failed, the platform reported the
# service as "Online" the whole time, and production served two-day-old code
# while four merged changes sat in main looking shipped.
#
# Health checks cannot catch that: the old container is genuinely healthy. The
# only question that distinguishes the two is "which code are you running", so
# this asks it.
#
#   scripts/check-deployed.sh https://api.example.com
#   scripts/check-deployed.sh https://api.example.com origin/main
#
set -euo pipefail

BASE="${1:-}"
EXPECTED_REF="${2:-HEAD}"

if [ -z "$BASE" ]; then
    echo "usage: $0 <base-url> [git-ref]" >&2
    exit 2
fi

expected="$(git rev-parse "$EXPECTED_REF")"
meta="$(curl -fsS --max-time 15 "${BASE%/}/api/v1/meta")"

# Avoid a jq dependency: this runs from CI, a laptop, and a fresh clone.
deployed="$(printf '%s' "$meta" | sed -n 's/.*"revision":"\([^"]*\)".*/\1/p')"

if [ -z "$deployed" ]; then
    echo "FAIL  ${BASE} does not report a revision at all." >&2
    echo "      Either it predates this check, or it is not a NOEMA API." >&2
    exit 1
fi

if [ "$deployed" = "unknown" ]; then
    echo "FAIL  ${BASE} is running an unstamped build." >&2
    echo "      It cannot say what code it is running, which is the situation" >&2
    echo "      this check exists to prevent. Deploy with NOEMA_GIT_SHA set." >&2
    exit 1
fi

if [ "$deployed" != "$expected" ]; then
    echo "FAIL  ${BASE} is running code that is not ${EXPECTED_REF}." >&2
    echo "        deployed: ${deployed}" >&2
    echo "        expected: ${expected}" >&2
    echo "      The service may well be healthy — an earlier container serves on" >&2
    echo "      when a deploy fails. Check the deploy logs, not the health check." >&2
    exit 1
fi

echo "OK    ${BASE} is running ${deployed}"
