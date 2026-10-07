# NOEMA security — architecture, threat model, runbook

Written 2026-09-25 from the code as it is, not from a checklist. Status
labels: **done** (in code, tested), **gap** (known, planned), **n/a** (the
attack surface does not exist here).

## 1. The stack, as attacked

| Layer | What it is | Notes |
|---|---|---|
| Web | Next.js 15 on Railway | Proxies `/api/v1/*`, so cookies are first-party and CORS never applies to the browser. |
| API | FastAPI on Railway, Postgres, Redis, one worker | Private networking to Postgres and Redis. |
| AI | Anthropic primary, OpenAI fallback, keys server-side only | BYOK keys encrypted at rest (`services/credentials.py`). |
| Money | Stripe Checkout and Billing | No card data touches NOEMA; webhooks signature-verified and idempotent (`StripeEvent`). |
| Files | Uploads sniffed by content, size-limited, per-user quota | Stored under generated ids; downloads go through owned-resource checks. Zip imports (Obsidian, Notion, Anki) are refused on their declared uncompressed size (50 MB per member, 200 MB total) before any member is read. |

## 2. Identity and sessions

- **Passwords:** Argon2id (t=3, m=64 MiB, p=4), rehash on login when parameters rise. Minimum 12 characters, no composition rules, paste allowed. **done**
- **Sessions:** server-side. The browser holds a random 256-bit refresh token in an `HttpOnly; Secure; SameSite=Lax` cookie; the database holds only its SHA-256. Every refresh rotates it; a replayed token revokes the whole family. **done**
- **CSRF:** double-submit token checked on every mutating route, on top of `SameSite=Lax`. **done**
- **Enumeration:** login hashes even for unknown emails; forgot-password always answers 204. Signup does reveal a taken address (usability trade-off, rate-limited). **accepted**
- **Brute force:** per-caller limit on auth routes (10/min, from the right-most trusted `X-Forwarded-For` hop) and, since 2026-09-25, per-account failure count (20 wrong passwords per hour pause that account, from any address). **done**
- **Password reset:** hashed, single-use, expiring, row-locked while used, revokes every session. Since 2026-09-28 one reset email per address per five minutes (Redis, keyed on a hash of the normalised email); a throttled request still answers 204, so the cooldown is not an enumeration oracle. **done**
- **Step-up:** export and account deletion need the password again and a browser session; an integration token can do neither. A wrong confirmation is `403 wrong-password`, never a 401 that would sign the owner out. **done**
- **Password change, device list, sign out one device or all others** (Settings, Security). Changing the password signs out every other device. **done**
- **Two-step verification:** TOTP (RFC 6238, verified against the RFC vectors) with the secret sealed under the master key and the user id as associated data; a code is accepted once; ten recovery codes stored hashed, each single use; a sign-in challenge lives five minutes and dies after five wrong guesses (attempts are committed even when the request fails). Turning it off needs the password and a code. **Required for admin routes.** **done**
- **Security notifications:** an email after a password change, a reset, and two-step verification turned on or off, with a link to reset the password if it was not them. Sent after the response; a mail failure never undoes the change. **done**
- **Breached passwords:** a new password (signup, change, reset) found in Have I Been Pwned is refused, by k-anonymity (only five hex characters of the SHA-1 leave the server), two-second limit, fail-open. **done**
- **Email verification:** since 2026-09-28 a link at signup (hashed, single-use, two days, resend from the banner or the page, one per account per five minutes), `POST /auth/verify-email` to open it, `email_verified` on `/auth/me`. Nothing is gated on it: accounts that predate it stay unverified and see a banner. `NOEMA_REQUIRE_VERIFIED_EMAIL_FOR_AI` (default off) makes every AI route refuse unverified accounts with `403 email-not-verified`. **done**

## 3. Authorization

- Every owned table goes through `OwnedRepository`, which ANDs `owner_id` into every query; cross-user tests cover retrieval, sessions and notebooks. **done**
- Route-level isolation sweep (2026-10-07, `tests/test_db_route_isolation.py`): a second signed-in account presents the first one's ids to every operation that takes one, read from the app's own schema (path ids, and each query, JSON and multipart id field on its own, about 100 probes). Each must answer 403/404 or an empty filtered list, no response may carry the other account's data or ids, and none of their rows may change. No leak found. A route added later is swept automatically. **done**
- Admin is an allowlist of emails in server config (`NOEMA_ADMIN_EMAILS`), checked server-side on every admin route, and every admin request also requires two-step verification to be on. The user list pages at most 200 rows and its search escapes `%` and `_` before the LIKE. **done**
- Request bodies are Pydantic models with explicit fields; there is no generic "update from body". **done**

## 4. Web

- Headers on every page: HSTS (1 year), `X-Frame-Options: DENY`, `nosniff`, strict referrer, restrictive Permissions-Policy. **done**
- CSP enforced: `frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'`. **done**
- CSP for scripts, styles and connections: **enforced** since 2026-09-26, after a headless Chrome session over nine pages (signed in) reported no violations and caught a deliberately injected off-policy script. Nonces instead of `'unsafe-inline'` remain a later step. **done**
- The only raw HTML is the static theme boot script. Lesson Markdown renders to React elements and creates no links. **done**

## 5. AI, memory, retrieval

- Retrieval is owner-scoped at every helper, with an adversarial test for guessed notebook ids. **done**
- Secrets never become memory: a credential the learner pastes (AI provider, AWS, GitHub, GitLab, Slack, Stripe keys, JWTs, PEM private keys) is answered in that turn and stored as `[redacted]` in the transcript and in every memory summary. The same list feeds log redaction. **done**
- Retrieved text is data: citations are enforced in code, the chat path has no tools. Delimiter escaping of retrieved text is **gap** (see `NOEMA_RAG_AUDIT.md`).
- Budgets: daily token budget per user, interactive reserve, demo per-caller cap. **done**
- Cost controls (2026-09-28): the plan's monthly AI allowance is enforced in the gateway dependency itself, so every route that spends on a model (`/ai/chat`, `/cards/generate`, `/questions/generate`, `/answers`, exam submit, `/explanations`, `/socratic`, drills, note actions, `/search`) refuses with `402 plan-limit-reached` before a provider is built; `/ai/professor` keeps its in-stream `blocked` event. On top of that, `NOEMA_AI_CALLS_PER_MINUTE` (default 30) model calls per learner per minute in Redis, fail-open. Every request without an explicit `max_tokens` gets a per-task ceiling in the gateway (chat 2048, grading 1024, classification 512, generation 4096). Prompt-bound inputs are capped: search query 2000 characters, explanation and cloze text 8000, Socratic transcript 40 turns of 4000. **done**
- Identity: prompts never name the underlying provider. **done**
- Provider failures never reach a client in the provider's words (2026-10-07): a timeout is `504 ai-timeout`, anything else `502 provider-unavailable`, each with a fixed sentence; a `ProviderError` that escapes a route is turned into that problem instead of a 500. Six places that used to interpolate the upstream text (Feynman and Socratic grading, the gateway dependency, note actions, open-answer grading feedback, the ingestion concepts warning) now use the fixed sentence. A per-provider circuit breaker counts only outage-class failures (timeout, transport, 429, 5xx), so one learner's bad BYOK key (a 401) cannot switch a provider off for everyone. **done**
- What the tutor remembers is visible and forgettable short of deleting the account (2026-09-28): `GET /ai/journeys/{id}/memory` lists the inferred learner patterns and communication adaptations (`learning_journeys.profile`), the memory summaries and the open misconceptions per concept, in plain terms; each can be forgotten one at a time, or all at once per journey, from Settings → Your data. Forgetting also strips the same line from every stored summary, so it cannot ride back into a prompt; the plan, progress, mastery evidence and cards are never touched. Owner-scoped like every other journey route: another account's journey is a 404. **done**

## 6. Operations

- Secrets live in Railway variables; history scanned clean (`NOEMA_SECRET_SCAN_2026-09-02.md`); log redaction covers Anthropic, OpenAI, Google, GitHub and Stripe key shapes. **done**
- CI: lint, types, tests, dependency audit and secret scan on every PR. **done**
- `/docs`, `/redoc` and `/openapi.json` are not served when `NOEMA_ENV=production`. **done**
- Production refuses to boot (API and worker) without an explicit postgresql `DATABASE_URL`, a `redis://` `REDIS_URL`, an https `NOEMA_WEB_ORIGIN`, and a usable AI provider for chat and embeddings (key present, never `mock`), on top of the real master key and session secret, secure cookies and no wildcard CORS. Messages name the variable, never its value. **done**
- Request ids: a sane incoming `X-Request-ID` (8–128 of `[A-Za-z0-9._:-]`) is kept, anything else replaced, so a caller cannot write into log lines. The id is in every log line, on `ai_usage.request_id`, and carried into Dramatiq jobs. **done**
- Health and ops: `/health` (liveness) touches nothing; `/health/ready` names failing dependencies by error class only; `GET /admin/ops` (admin + two-step) shows circuit states and error classes, never messages or keys. See `docs/operations.md`. **done**

## 7. Incident runbook

For every case: contain, rotate, revoke, investigate, recover, tell users if their data was exposed.

| Leak | Contain and rotate | Revoke | Then |
|---|---|---|---|
| AI provider key | Delete the key in the provider console, set a new one in Railway, redeploy. | n/a | Check provider usage for spend you did not make. |
| Stripe secret or webhook secret | Roll it in Stripe, update Railway. | Old key dies on roll. | Review Stripe events for the window. |
| Database URL | Rotate the Postgres password in Railway. | Kill open connections. | Review who had the variable. |
| A user's session | `UPDATE sessions SET revoked_at = now() WHERE user_id = …` | The row is the session. | Force a password reset for that user. |
| Every session | `UPDATE sessions SET revoked_at = now() WHERE revoked_at IS NULL` | Everyone signs in again. | Use when a session store leak is suspected. |
| Admin account | Remove the email from `NOEMA_ADMIN_EMAILS`, redeploy, revoke its sessions. | As above. | Audit what the admin routes returned in the window. |

Anthropic running out of credit is not a security incident but looks like one ("tutor offline"): see the operator note in the memory of 2026-09-25.
