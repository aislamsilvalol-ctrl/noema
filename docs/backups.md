# Database backups

Railway's volume backups are not available on the Hobby plan (the API answers
"Not Authorized"), so the production database is backed up by a cron service.

## What runs

- Service `db-backup` in the `noema` project, built from `infra/db-backup/`.
- Every day at 06:00 UTC (03:00 in Brasília): `pg_dump --format=custom` of the
  production database over the private network, checked with `pg_restore
  --list`, uploaded to the Railway bucket `db-backups` under `postgres/`.
- Every run then **proves the dump restores**: it restores it into a scratch
  database (`noema_restore_check`) on the same server, compares the table
  count and checks the accounts came back, and drops the scratch database.
  A failed restore fails the run. `RESTORE_CHECK=0` skips it.
- Dumps older than `KEEP_DAYS` (default 14) are deleted by the same run.
- The run fails loudly, and Railway marks the cron run failed, if the dump
  cannot be read back or the upload fails.

Not covered: the API volume (`api-volume`, uploaded files). If uploads become
important, add a second prefix to the same job.

## Restore

1. Get the bucket credentials: `railway bucket credentials --bucket db-backups --json`.
2. Download the dump you want:
   `aws --endpoint-url <endpoint> s3 ls s3://<bucket>/postgres/` then
   `aws --endpoint-url <endpoint> s3 cp s3://<bucket>/postgres/noema-<stamp>.dump .`
3. Restore into a **new** database first and check it; never straight over
   production:
   `createdb -h <host> -U <user> noema_restore`, then
   `pg_restore --no-owner --no-privileges -d postgresql://<user>:<password>@<host>:<port>/noema_restore noema-<stamp>.dump`
   (the target needs the `vector` extension: `create extension vector;`).
4. Only after checking the restored data, point the API's `DATABASE_URL` at it,
   or restore over the production database in a maintenance window.

A backup that has never been restored is a hope. Try step 3 once after the
first run.
