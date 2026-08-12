#!/bin/sh
# Start as root only long enough to make the storage directory writable, then run
# the application as an unprivileged user.
#
# A mounted volume arrives owned by root, whatever the image says. Without this
# the container starts, answers health checks, and fails on the first upload with
# a permission error — which is how it failed the first time this was deployed.
#
# Parsing runs against untrusted documents, so root is exactly what the process
# handling them must not have.
set -e

STORAGE_LOCAL_PATH="${STORAGE_LOCAL_PATH:-/var/lib/noema/uploads}"

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$STORAGE_LOCAL_PATH"
    chown -R noema:noema "$STORAGE_LOCAL_PATH"
    exec su noema -s /bin/sh -c '"$0" "$@"' -- "$@"
fi

exec "$@"
