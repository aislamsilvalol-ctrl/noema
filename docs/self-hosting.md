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
git clone https://github.com/noema-dev/noema.git && cd noema
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

```bash
ollama pull llama3.1
ollama pull nomic-embed-text

# in .env
NOEMA_MODE=local
NOEMA_DEFAULT_PROVIDER=ollama
NOEMA_EMBEDDING_PROVIDER=ollama
NOEMA_EMBEDDING_MODEL=nomic-embed-text
NOEMA_EMBEDDING_DIM=768

docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

`docker-compose.local.yml` attaches the api and worker containers to an internal-only Docker
network, so the restriction is enforced by the runtime rather than by trusting the code. In
this mode the UI hides features that would require a hosted provider instead of failing when
you click them.

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
