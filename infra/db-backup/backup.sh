#!/bin/sh
# One run: dump, check the dump reads back, upload, drop copies older than
# KEEP_DAYS. Railway's volume backups are not available on this plan, so this
# is the database's safety net. Restore steps: docs/backups.md.
#
# Needs: DATABASE_URL (postgresql://...), AWS_ENDPOINT_URL, AWS_ACCESS_KEY_ID,
# AWS_SECRET_ACCESS_KEY, AWS_S3_BUCKET_NAME, AWS_DEFAULT_REGION.
# Never prints a credential.
set -eu

KEEP_DAYS="${KEEP_DAYS:-14}"
PREFIX="postgres/"
stamp="$(date -u +%Y-%m-%dT%H%MZ)"
key="${PREFIX}noema-${stamp}.dump"
file="/tmp/noema-${stamp}.dump"

s3() {
  aws --endpoint-url "$AWS_ENDPOINT_URL" s3 "$@"
}

echo "backup: dumping"
pg_dump --format=custom --no-owner --no-privileges --dbname="$DATABASE_URL" --file="$file"
# A dump that pg_restore cannot list is not a backup.
tables="$(pg_restore --list "$file" | grep -c ' TABLE ' || true)"
if [ "$tables" -lt 1 ]; then
  echo "backup: dump lists no tables, refusing to upload" >&2
  exit 1
fi
size="$(wc -c < "$file" | tr -d ' ')"
echo "backup: ${tables} tables, ${size} bytes"

s3 cp "$file" "s3://${AWS_S3_BUCKET_NAME}/${key}" --only-show-errors
echo "backup: uploaded ${key}"

# Prove the dump restores: into a scratch database on the same server, then
# compare table counts with the source and drop it. A backup that has never
# been restored is a hope. Skipped with RESTORE_CHECK=0.
if [ "${RESTORE_CHECK:-1}" = "1" ]; then
  scratch="noema_restore_check"
  export PGOPTIONS='-c client_min_messages=warning'
  admin_url="$(echo "$DATABASE_URL" | sed -E 's#/[^/?]+(\?|$)#/postgres\1#')"
  scratch_url="$(echo "$DATABASE_URL" | sed -E "s#/[^/?]+(\\?|$)#/${scratch}\\1#")"
  psql "$admin_url" -qAt -c "DROP DATABASE IF EXISTS ${scratch}" >/dev/null
  psql "$admin_url" -qAt -c "CREATE DATABASE ${scratch}" >/dev/null
  psql "$scratch_url" -qAt -c "CREATE EXTENSION IF NOT EXISTS vector" >/dev/null 2>&1 || true
  pg_restore --no-owner --no-privileges --exit-on-error --dbname="$scratch_url" "$file"
  count="select count(*) from information_schema.tables where table_schema='public'"
  src_tables="$(psql "$DATABASE_URL" -qAt -c "$count")"
  got_tables="$(psql "$scratch_url" -qAt -c "$count")"
  src_users="$(psql "$DATABASE_URL" -qAt -c "select count(*) from users")"
  got_users="$(psql "$scratch_url" -qAt -c "select count(*) from users")"
  psql "$admin_url" -qAt -c "DROP DATABASE ${scratch}" >/dev/null
  # Tables must match; users may only have grown since the dump, and a source
  # with accounts must not restore empty.
  if [ "$src_tables" != "$got_tables" ] || [ "$got_users" -gt "$src_users" ] \
    || { [ "$src_users" -gt 0 ] && [ "$got_users" -lt 1 ]; }; then
    echo "backup: restore check FAILED (tables ${got_tables}/${src_tables}, users ${got_users}/${src_users})" >&2
    exit 1
  fi
  echo "backup: restore check ok (${got_tables} tables, ${got_users} users)"
fi

rm -f "$file"

# Retention by the date in the key, so it does not depend on object metadata.
cutoff="$(date -u -d "@$(( $(date +%s) - KEEP_DAYS * 86400 ))" +%Y-%m-%d)"
s3 ls "s3://${AWS_S3_BUCKET_NAME}/${PREFIX}" | awk '{print $4}' | while read -r name; do
  day="$(echo "$name" | sed -n 's/^noema-\([0-9-]\{10\}\)T.*/\1/p')"
  if [ -n "$day" ] && [ "$day" \< "$cutoff" ]; then
    s3 rm "s3://${AWS_S3_BUCKET_NAME}/${PREFIX}${name}" --only-show-errors
    echo "backup: removed ${name}"
  fi
done
echo "backup: done, keeping ${KEEP_DAYS} days"
