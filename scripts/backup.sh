#!/usr/bin/env bash
# Back up the database and the uploaded documents together.
#
# A database backup without the documents restores a catalogue of missing
# files — docs/self-hosting.md says so, and this is the script that makes
# "pg_dump *and* the object store, together" something you run rather than
# something you remember. It shells out to `docker compose exec` for both
# halves, so it needs nothing installed on the host beyond Docker itself —
# not even a Postgres client.
#
# Object storage (STORAGE_DRIVER=s3) backs up the database only: the bucket is
# already off-host, and its backup is that provider's responsibility, not
# this script's guess at how to reach it.
#
# NOEMA_MASTER_KEY is not backed up here on purpose. It lives in .env, next to
# this script, and belongs in whatever secret store already holds the rest of
# your deployment secrets — bundling it into a backup archive would put the
# one thing that makes the ciphertext unrecoverable in the same place as the
# ciphertext itself.
#
# Usage: scripts/backup.sh [destination-directory]
#   Defaults to ./backups/<timestamp>/

set -euo pipefail

DEST="${1:-backups/$(date +%Y%m%dT%H%M%SZ)}"
POSTGRES_SERVICE="${NOEMA_BACKUP_POSTGRES_SERVICE:-postgres}"
API_SERVICE="${NOEMA_BACKUP_API_SERVICE:-api}"
POSTGRES_USER="${NOEMA_BACKUP_POSTGRES_USER:-noema}"
POSTGRES_DB="${NOEMA_BACKUP_POSTGRES_DB:-noema}"
UPLOADS_PATH="${NOEMA_BACKUP_UPLOADS_PATH:-/var/lib/noema/uploads}"

fail() { echo "backup: $1" >&2; exit 1; }

compose() { docker compose exec -T "$@"; }

# Captured once and matched against with a here-string rather than piped
# straight into `grep -q`: `grep -q` exits the moment it finds a match without
# draining the rest of its input, and under `pipefail` a multi-line producer
# still writing when that happens can turn a real match into a spurious
# failure — this hit in testing, not in theory.
running_services() { docker compose ps --status running --format '{{.Service}}' 2>/dev/null || true; }
service_running() { grep -qx "$1" <<<"$(running_services)"; }

command -v docker >/dev/null || fail "docker is not on PATH"
service_running "$POSTGRES_SERVICE" \
  || fail "the '$POSTGRES_SERVICE' service is not running — start the stack first"

mkdir -p "$DEST"
echo "backup: writing to $DEST"

echo "backup: dumping the database"
compose "$POSTGRES_SERVICE" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom \
  > "$DEST/database.dump"
[ -s "$DEST/database.dump" ] || fail "the database dump came back empty"

STORAGE_DRIVER="$(docker compose exec -T "$API_SERVICE" \
  python -c "from noema.core.config import get_settings; print(get_settings().storage_driver)" \
  2>/dev/null || echo unknown)"

if [ "$STORAGE_DRIVER" = "s3" ]; then
  echo "backup: STORAGE_DRIVER=s3 — the bucket backs itself up, skipping uploads"
elif service_running "$API_SERVICE"; then
  echo "backup: archiving uploaded documents"
  compose "$API_SERVICE" tar -C "$UPLOADS_PATH" -cf - . > "$DEST/uploads.tar"
  [ -s "$DEST/uploads.tar" ] || echo "backup: uploads.tar is empty — fine for a fresh install, worth a second look otherwise" >&2
else
  echo "backup: '$API_SERVICE' is not running, could not determine storage_driver — skipping uploads" >&2
fi

echo "backup: done"
echo "backup:   $DEST/database.dump"
[ -f "$DEST/uploads.tar" ] && echo "backup:   $DEST/uploads.tar"
echo "backup: NOEMA_MASTER_KEY is not in this archive — back it up separately, see docs/self-hosting.md"
