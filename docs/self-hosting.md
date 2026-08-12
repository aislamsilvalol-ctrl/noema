# Self-hosting NOEMA

NOEMA is designed to be run by one person on a laptop, by a lab on a workstation, or by a
university on a server. All three are supported configurations, not afterthoughts.

## Minimum requirements

| | single user | small team (≤ 25) |
|---|---|---|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB (16 GB with local models) | 16 GB |
| Disk | 20 GB + your documents | 100 GB + |
| GPU | optional, only for local models | recommended for local mode |

Postgres 16 with `pgvector` and Redis 7 are the only external dependencies.

## Cloud providers (default)

```bash
git clone https://github.com/aislamsilvalol-ctrl/noema.git && cd noema
cp .env.example .env

python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"  # ×2
# paste into NOEMA_MASTER_KEY and NOEMA_SESSION_SECRET

docker compose up -d
```

Users then add their own API keys in Settings → AI Providers. You do not have to hold keys
centrally, and on a shared install you probably should not — BYOK means each person's usage
is billed to them and revocable by them.

## Fully local

No outbound network calls. Documents, embeddings, conversations and progress never leave the
machine.

Models are served by an `ollama` container on the closed network, so pulling one is a
deliberate, separate act — done once, with network, before the stack starts:

```bash
docker run --rm -v noema_ollama:/root/.ollama ollama/ollama pull llama3.1:8b
docker run --rm -v noema_ollama:/root/.ollama ollama/ollama pull nomic-embed-text

# in .env
NOEMA_DEFAULT_PROVIDER=ollama
NOEMA_EMBEDDING_PROVIDER=ollama
NOEMA_EMBEDDING_MODEL=nomic-embed-text
NOEMA_EMBEDDING_DIM=768

docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

`NOEMA_MODE=local` is set by the override file itself, so the two halves of the guarantee
cannot drift apart:

- **Application.** The provider registry refuses to construct a provider that would make a
  network call.
- **Runtime.** `docker-compose.local.yml` puts api, worker, postgres, redis and ollama on a
  Docker network declared `internal: true` — no route out. The guarantee therefore survives a
  bug in the first half, which is the only reason to have both.

CI asserts the second half rather than describing it: it starts the local stack and requires
`socket.create_connection(("1.1.1.1", 443))` from inside both the api and the worker to
fail. Published ports still work, so the app is reachable from your browser as usual.

`GET /api/v1/meta` reports `local: true`, and the UI uses it to hide hosted-provider settings
instead of offering a button that cannot work.

Quality trade-off, stated plainly: local 8B-class models extract concepts and generate
flashcards acceptably, and grade open answers noticeably worse than frontier models. Mastery
discounts AI-graded evidence (`w_src = 0.7`) partly for this reason.

## Single-user install

```
NOEMA_ALLOW_SIGNUPS=false
```

Create your account first, then set it and restart.

## Production notes

- **TLS.** Terminate in front (Caddy, nginx, Traefik) and set `NOEMA_SECURE_COOKIES=true`.
- **Never expose Postgres or Redis** outside the compose network. No published ports.
- **Object storage.** The local filesystem driver is fine for one machine. For anything
  redundant, set the `S3_*` variables — any S3-compatible service works.
- **Workers.** Ingestion is the CPU-heavy part. Scale with
  `docker compose up -d --scale worker=4`. Keep `mem_limit` in place; a malformed PDF should
  kill one worker, not the host.
- **Backups.** `pg_dump` *and* the object store, together. A database backup without the
  documents restores a catalogue of missing files. **Back up `NOEMA_MASTER_KEY`
  separately** — without it, stored API keys are unrecoverable (which is the point).
- **Account purges — you have to schedule this.** `DELETE /api/v1/me` closes an account
  immediately and marks it for permanent deletion 30 days later, but NOEMA ships no
  scheduler. Until something runs the purge, "deleted" means "hidden", which is not what
  the person was told. Run it daily from cron, a systemd timer, or your platform's
  scheduler:

  ```
  docker compose exec worker python -c \
    "from noema.workers import purge_accounts; purge_accounts.send()"
  ```

  It is idempotent and does nothing when no account is past its grace period. Note that
  purged data is gone from the live system but still present in older backups — expire
  those on a schedule you can describe to a user.
- **Upgrades.** `docker compose pull && docker compose up -d`. Migrations run on API start.
  Read `CHANGELOG.md` before a major bump; embedding-model changes trigger a re-embed job
  that costs time and, on cloud providers, money.

## Health and monitoring

```
GET /health        liveness
GET /health/ready  database, redis and provider reachability
GET /metrics       Prometheus (enable with NOEMA_METRICS_ENABLED=true)
```

Worth alerting on: ingestion job failure rate, worker queue depth, AI error rate by provider,
and p95 retrieval latency.

## Troubleshooting

**Ingestion stuck at `parsing`.** Check `docker compose logs worker`. Usually a scanned PDF
falling back to OCR, which is slow — or a document larger than the worker's memory limit.

**"Could not find this in your materials" on content you know is there.** Confirm the source
reached `ready`. If it did, the chunk probably lacks the query's vocabulary; hybrid search
helps but is not magic. Check the notebook's retrieval settings — raising top-k is the first
thing to try.

**Provider errors after adding a key.** `last_verified_at` on the credential tells you
whether the validation call ever succeeded. Keys are validated on save.

**Wrong embedding dimension on startup.** `NOEMA_EMBEDDING_DIM` must match the model.
Changing models requires re-embedding; NOEMA refuses to mix dimensions in one column rather
than silently degrading your search.
