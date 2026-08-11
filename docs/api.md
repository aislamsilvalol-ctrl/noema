# NOEMA — API

FastAPI, OpenAPI 3.1 at `/openapi.json`, interactive docs at `/docs`. The TypeScript client
in `packages/schemas` is **generated** from the spec in CI — the frontend never hand-writes a
response type, and a breaking API change fails the web typecheck immediately.

## Conventions

- Base path `/api/v1`. Breaking changes bump the prefix; additive ones do not.
- Cursor pagination: `?cursor=&limit=` → `{items, next_cursor}`. No offset pagination.
- Errors are RFC 9457 problem details:
  ```json
  {"type": "https://noema.dev/errors/quota-exceeded", "title": "Storage quota exceeded",
   "status": 413, "detail": "Workspace limit is 2 GB.", "instance": "/api/v1/sources"}
  ```
- Mutations accept `Idempotency-Key`.
- Timestamps ISO 8601 UTC. Durations in seconds. Money in cents.

## Endpoints

### Workspaces
```
GET    /workspaces                    POST /workspaces
GET    /workspaces/{id}               PATCH /workspaces/{id}     DELETE /workspaces/{id}
GET    /workspaces/{id}/subjects      POST /workspaces/{id}/subjects
```

### Notebooks
```
GET    /notebooks?subject_id=         POST /notebooks
GET    /notebooks/{id}                PATCH /notebooks/{id}      DELETE /notebooks/{id}
GET    /notebooks/{id}/overview       → counts, mastery summary, due items
POST   /notebooks/{id}/export         → markdown + json bundle
```

### Sources & documents
```
POST   /sources/upload-url            → {upload_url, source_id}   (presigned)
POST   /sources/{id}/ingest           → {job_id}
GET    /sources/{id}                  → status, stage, error
GET    /sources/{id}/events           → SSE ingestion progress
DELETE /sources/{id}                  → cascades chunks + embeddings
```

### Notes
```
GET/POST /notes        GET/PATCH/DELETE /notes/{id}
POST   /notes/{id}/actions/{explain|simplify|expand|flashcard|question|example}
       body: {selection: {from, to}}  → streamed result, never auto-saved
```

### Concepts & graph
```
GET    /concepts?workspace_id=&status=        GET /concepts/{id}
PATCH  /concepts/{id}                          POST /concepts/merge  {source_ids, target_id}
GET    /concepts/{id}/graph?depth=2            → nodes + edges for the visualiser
POST   /concepts/{id}/edges                    DELETE /concepts/edges/{id}
GET    /mastery?workspace_id=&weak=true        → scores + component breakdown
```

### Cards & reviews
```
GET    /cards?notebook_id=&due=true            POST /cards        POST /cards/generate
PATCH  /cards/{id}                             POST /cards/{id}/approve
POST   /reviews                                → {card_id, rating, elapsed_ms, confidence?}
POST   /reviews/batch                          → offline-tolerant flush
GET    /reviews/forecast?days=30               → workload projection
```

### Questions, exams, mistakes
```
POST   /questions/generate     {concept_ids, types, difficulty, count}
POST   /answers                → grading result (deterministic or AI)
POST   /exams                  {concept_ids | "everything studied since", count, minutes}
GET    /exams/{id}             POST /exams/{id}/submit  → score + concept breakdown
GET    /mistakes?unresolved=true               POST /mistakes/practice-session
```

### Learning
```
GET    /learning-session/plan?minutes=30       → the plan in learning-engine.md §7
POST   /learning-session/start                 POST /learning-session/{id}/complete
GET    /goals    POST /goals                   GET /goals/{id}/path
GET    /analytics/overview?range=30d
```

### AI
```
POST   /ai/chat                → SSE stream; body {notebook_id, mode, messages, scope}
POST   /ai/feynman             → {concept_id, explanation} → gaps, contradictions, feedback
GET    /ai/providers           → configured providers + capabilities
POST   /ai/credentials         → {provider, label, api_key}  (write-only)
DELETE /ai/credentials/{id}
GET    /ai/usage?range=30d     → tokens and cost by task class
```

### Search
```
GET    /search?q=&scope=workspace|subject|notebook&types=notes,sources,cards,questions,chats
```

### Account
```
GET    /me    PATCH /me    POST /me/export    DELETE /me
```
`POST /me/export` produces a complete portable archive; `DELETE /me` schedules a 30-day purge
of everything including embeddings and object storage. Both are first-class endpoints, not
support tickets.

## Auth

Cookie sessions for the web app (httpOnly, `SameSite=Lax`, rotating refresh, CSRF
double-submit on mutations). Bearer PATs for the public API, scoped per resource type, shown
once at creation. Rate limits per user and per IP, returned as `RateLimit-*` headers.
