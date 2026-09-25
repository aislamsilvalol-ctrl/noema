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
| Files | Uploads sniffed by content, size-limited, per-user quota | Stored under generated ids; downloads go through owned-resource checks. |

## 2. Identity and sessions

- **Passwords:** Argon2id (t=3, m=64 MiB, p=4), rehash on login when parameters rise. Minimum 12 characters, no composition rules, paste allowed. **done**
- **Sessions:** server-side. The browser holds a random 256-bit refresh token in an `HttpOnly; Secure; SameSite=Lax` cookie; the database holds only its SHA-256. Every refresh rotates it; a replayed token revokes the whole family. **done**
- **CSRF:** double-submit token checked on every mutating route, on top of `SameSite=Lax`. **done**
- **Enumeration:** login hashes even for unknown emails; forgot-password always answers 204. Signup does reveal a taken address (usability trade-off, rate-limited). **accepted**
- **Brute force:** per-caller limit on auth routes (10/min, from the right-most trusted `X-Forwarded-For` hop) and, since 2026-09-25, per-account failure count (20 wrong passwords per hour pause that account, from any address). **done**
- **Password reset:** hashed, single-use, expiring, row-locked while used, revokes every session. **done**
- **Step-up:** export and account deletion need the password again and a browser session; an integration token can do neither. A wrong confirmation is `403 wrong-password`, never a 401 that would sign the owner out. **done**
- **Password change, device list, sign out one device or all others** (Settings, Security). Changing the password signs out every other device. **done**
- **MFA (TOTP, recovery codes), required for admins:** **gap, planned after step-up.**
- **Email verification, breached-password check (k-anonymity), security notifications by email:** **gap, P2.**

## 3. Authorization

- Every owned table goes through `OwnedRepository`, which ANDs `owner_id` into every query; cross-user tests cover retrieval, sessions and notebooks. **done**
- Admin is an allowlist of emails in server config (`NOEMA_ADMIN_EMAILS`), checked server-side on every admin route. It exposes business and cost data only. **done**, MFA for admins is the gap above.
- Request bodies are Pydantic models with explicit fields; there is no generic "update from body". **done**

## 4. Web

- Headers on every page: HSTS (1 year), `X-Frame-Options: DENY`, `nosniff`, strict referrer, restrictive Permissions-Policy. **done**
- CSP enforced: `frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'`. **done**
- CSP for scripts, styles and connections: **report-only** until a real browser session shows no violations, then enforced. **gap, needs a browser check.**
- The only raw HTML is the static theme boot script. Lesson Markdown renders to React elements and creates no links. **done**

## 5. AI, memory, retrieval

- Retrieval is owner-scoped at every helper, with an adversarial test for guessed notebook ids. **done**
- Secrets never become memory: a credential the learner pastes (AI provider, AWS, GitHub, GitLab, Slack, Stripe keys, JWTs, PEM private keys) is answered in that turn and stored as `[redacted]` in the transcript and in every memory summary. The same list feeds log redaction. **done**
- Retrieved text is data: citations are enforced in code, the chat path has no tools. Delimiter escaping of retrieved text is **gap** (see `NOEMA_RAG_AUDIT.md`).
- Budgets: daily token budget per user, interactive reserve, demo per-caller cap. **done**
- Identity: prompts never name the underlying provider. **done**

## 6. Operations

- Secrets live in Railway variables; history scanned clean (`NOEMA_SECRET_SCAN_2026-09-02.md`); log redaction covers Anthropic, OpenAI, Google, GitHub and Stripe key shapes. **done**
- CI: lint, types, tests, dependency audit and secret scan on every PR. **done**

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
