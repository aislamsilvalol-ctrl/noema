# Security Policy

## Reporting a vulnerability

**Do not open a public issue.**

Use [GitHub Private Vulnerability Reporting](https://github.com/aislamsilvalol-ctrl/noema/security/advisories/new),
or email `security@noema.dev` (PGP key in `docs/security-pgp.asc`).

Please include: affected version or commit, reproduction steps, impact, and any suggested
fix. You'll get an acknowledgement within **72 hours** and an assessment within **7 days**.
We aim to ship a fix within 30 days for high severity, 90 for the rest, and we'll credit you
in the advisory unless you'd rather we didn't.

We do not currently run a paid bounty. We will not pursue legal action against good-faith
research that stays within these bounds: no accessing other users' data, no degrading the
service, no social engineering.

## Supported versions

Pre-alpha. Only `main` is supported. Once 1.0 ships, the current minor and the one before it
get security fixes.

## Threat model

NOEMA handles material people consider private — coursework, research, medical study notes,
client documents — plus API keys that cost real money. The assets, in priority order:

1. **User API keys** (BYOK). Compromise costs users money directly.
2. **Documents and notes.** Often confidential, sometimes regulated.
3. **Session credentials.**
4. **Learning history.** Sensitive by inference — what someone struggles with is personal.

### Controls

**Authentication.** argon2id (memory-hard params, tuned per deployment). Sessions are
httpOnly + Secure + `SameSite=Lax` cookies with rotating refresh tokens and reuse detection.
CSRF double-submit tokens on every cookie-authenticated mutation. Login and password reset
are rate-limited per account and per IP with constant-time comparison.

**API key storage.** AES-256-GCM with a versioned data key wrapped by `NOEMA_MASTER_KEY`
(env var, or KMS in hosted deployments). Decryption happens only inside the AI gateway.
**No endpoint can return a key** — the response schemas have no field for it, and a test
asserts that. A logging filter redacts anything matching known key patterns, with a test that
a known key string never appears in captured output.

**Uploads.** The largest untrusted-input surface in the system. Content type is detected from
magic bytes, never from the extension. Size caps per type, per-user quotas, archives and
executables rejected. Parsing runs in the worker under memory and wall-clock limits, isolated
from the API process. Files are stored under generated keys, never under user-supplied names,
and are served only through authenticated, short-lived signed URLs.

**Prompt injection.** Documents can contain text aimed at the model. Retrieved content is
passed inside an explicitly delimited data block labelled as material to reason about, not
instructions. **The model is given no tools during RAG answering**, so a successful injection
has nothing to reach. Structured outputs are schema-validated before persistence, and no
AI-generated card or question becomes active without human approval.

**Injection and XSS.** SQLAlchemy parameterised queries throughout; raw SQL requires review.
Markdown is sanitised on render with a strict allowlist; user HTML is not executed. A CSP
without `unsafe-inline` or `unsafe-eval`.

**Multi-tenancy.** Every query is scoped by owner at the repository layer, not by the caller
remembering to filter, and the repository is generic over a base class that requires an owner
column — so a model without one cannot be passed to it. `tests/test_db_tenancy.py` asserts,
for every owned model, that another user's row returns 404 rather than 403: the existence of
someone else's notebook is itself information.

**Rate limiting.** Per user, per IP, and per provider key. BYOK makes runaway loops expensive
for the user, so AI endpoints carry a configurable daily budget ceiling that degrades
gracefully rather than failing hard.

**Supply chain.** API dependencies are pinned to exact versions and the web app ships a
committed lockfile, so an upgrade is a deliberate commit with a CI run attached rather than
whatever resolved that morning. `pip-audit` and `npm audit` run in CI, alongside secret
scanning with push protection.

### Out of scope

Vulnerabilities in self-hosted deployments caused by operator misconfiguration (exposed
Postgres, default `NOEMA_MASTER_KEY`, no TLS), issues in third-party AI providers, and
attacks requiring physical access or a compromised user device.

## Self-hosting checklist

- [ ] Generate a unique `NOEMA_MASTER_KEY` (32 random bytes, base64). Never reuse the example.
- [ ] Terminate TLS in front of the app; set `NOEMA_SECURE_COOKIES=true`.
- [ ] Never expose Postgres or Redis outside the compose network.
- [ ] Set `NOEMA_ALLOW_SIGNUPS=false` on single-user installs.
- [ ] Back up the database *and* the object store; test a restore.
- [ ] Keep the master key out of version control and out of your backups' plaintext.
