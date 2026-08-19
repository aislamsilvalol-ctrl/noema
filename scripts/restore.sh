#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh.
#
# Destructive: this drops and recreates every object in the target database and
# overwrites the uploads volume. It exists because an untested restore path is
# not a backup strategy, only a hope — but that same reason is why it refuses to
# run without --yes, and why it says exactly what it is about to overwrite
# before doing it.
#
# Usage: scripts/restore.sh <backup-directory> --yes

set -euo pipefail

fail() { echo "restore: $1" >&2; exit 1; }

DIR="${1:-}"
CONFIRMED="no"
for arg in "$@"; do
  [ "$arg" = "--yes" ] && CONFIRMED="yes"
done

[ -n "$DIR" ] && [ "$DIR" != "--yes" ] || fail "usage: scripts/restore.sh <backup-directory> --yes"
[ -f "$DIR/database.dump" ] || fail "$DIR/database.dump not found — is this a backup.sh directory?"

POSTGRES_SERVICE="${NOEMA_BACKUP_POSTGRES_SERVICE:-postgres}"
API_SERVICE="${NOEMA_BACKUP_API_SERVICE:-api}"
POSTGRES_USER="${NOEMA_BACKUP_POSTGRES_USER:-noema}"
POSTGRES_DB="${NOEMA_BACKUP_POSTGRES_DB:-noema}"
UPLOADS_PATH="${NOEMA_BACKUP_UPLOADS_PATH:-/var/lib/noema/uploads}"

compose() { docker compose exec -T "$@"; }

# See scripts/backup.sh for why this is a captured-then-matched here-string
# rather than a live pipe into `grep -q`.
running_services() { docker compose ps --status running --format '{{.Service}}' 2>/dev/null || true; }
service_running() { grep -qx "$1" <<<"$(running_services)"; }

command -v docker >/dev/null || fail "docker is not on PATH"
service_running "$POSTGRES_SERVICE" \
  || fail "the '$POSTGRES_SERVICE' service is not running — start the stack first"

echo "restore: this will DROP every table in '$POSTGRES_DB' on the '$POSTGRES_SERVICE' service"
echo "restore: and overwrite everything under $UPLOADS_PATH on '$API_SERVICE', replacing it with $DIR"
if [ "$CONFIRMED" != "yes" ]; then
  fail "re-run with --yes once you are sure — nothing has been touched yet"
fi

echo "restore: restoring the database"
compose "$POSTGRES_SERVICE" pg_restore --clean --if-exists --no-owner \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$DIR/database.dump"

if [ -f "$DIR/uploads.tar" ]; then
  if service_running "$API_SERVICE"; then
    echo "restore: restoring uploaded documents"
    compose "$API_SERVICE" sh -c "rm -rf ${UPLOADS_PATH:?}/* && tar -C '$UPLOADS_PATH' -xf -" < "$DIR/uploads.tar"
  else
    fail "'$API_SERVICE' is not running — the database was restored, but uploads.tar was not applied. Start it and re-run to restore uploads."
  fi
else
  echo "restore: no uploads.tar in $DIR (this backup used object storage, or predates uploads) — nothing to restore there"
fi

echo "restore: done. Restart the api and worker services so they pick up the restored state:"
echo "restore:   docker compose restart api worker"
