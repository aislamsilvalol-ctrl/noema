# NOEMA — Secret Scan

Generated 2026-09-02, Phase 4 of the Launch Readiness program. Scope per the
brief's items 59-61: frontend bundle/`NEXT_PUBLIC_*`/localStorage/source maps,
full git history, and application logging. **No secret value found during this
scan is printed anywhere in this document — locations and severities only,**
per the explicit constraint on this pass.

## Method

- `grep -rn "NEXT_PUBLIC_"` across `apps/web/src` and `next.config.*`.
- Checked `next.config.*` for `productionBrowserSourceMaps` (source-map exposure).
- `git log --all -p | grep -Eo <patterns>` for Anthropic (`sk-ant-`), OpenAI
  (`sk-`), Google (`AIza`), OpenRouter (`sk-or-`), GitHub (`ghp_`), AWS
  (`AKIA`), Stripe (`sk_live_`/`sk_test_`/`whsec_`/`pk_live_`/`pk_test_`), and
  credentialed Postgres URLs, across every ref in the repository (`--all`), not
  just the current branch.
- Read `noema/core/logging.py` in full for its redaction processor and pattern
  list.
- Checked the untracked `apps/api/uv.lock` (visible in `git status`) for
  embedded secrets before it's ever committed.

## Findings

### 1. Frontend / `NEXT_PUBLIC_*` — CLEAN
Only two client-exposed variables exist in the entire frontend codebase:
`NEXT_PUBLIC_API_URL` (the API base URL) and `NEXT_PUBLIC_DEMO` (a boolean flag
gating an inert demo proxy route). Neither is secret-shaped or secret-adjacent.
No `NEXT_PUBLIC_*` variable anywhere references a key, token, or credential.

### 2. Source maps — CLEAN
`next.config.*` does not set `productionBrowserSourceMaps: true`, so it defaults
to `false` — a production build does not ship source maps that could expose
bundling context or accidentally-inlined values.

### 3. Git history (`git log --all -p`) — CLEAN
No Anthropic, OpenAI, Google, OpenRouter, GitHub, AWS, or Stripe key-shaped
string has ever been committed to any ref in this repository. The only pattern
that matched at all was the default local/Docker-Compose development Postgres
URL (`noema:noema@localhost` / `@postgres`), which appears in `config.py`'s
own default value and `docker-compose.yml` — this is an intentionally public,
non-production placeholder credential, not a leak. Every real credential the
user has supplied this session (Anthropic key, OpenAI key, Stripe test-mode
secret key) was configured directly as a Railway environment variable and never
appears in any commit, consistent with the standing discipline for this
session.

### 4. `apps/api/uv.lock` (untracked) — CLEAN
Grepped for the same key-shaped patterns; it's a plain dependency lockfile
(package names/versions/hashes), nothing secret-shaped present. Flagging only
because `git status` shows it as untracked and it will need a normal `.gitignore`
or intentional-commit decision at some point — not a secret-scan issue.

### 5. Log redaction (`noema/core/logging.py`) — **PARTIAL, one real gap**
The redaction processor is real, structlog-integrated, and covers both
key-shaped value patterns and a sensitive-key-name denylist
(`api_key`/`password`/`token`/`secret`/`master_key`/etc.) applied recursively to
dicts and lists — not just a top-level scrub. It is genuinely tested (the
module's own docstring notes "there is a test asserting a known key never
survives this pipeline").

**Gap: the `_SECRET_PATTERNS` list has no pattern for Stripe key shapes.**
Current patterns cover `sk-ant-`, generic `sk-`, `AIza`, `sk-or-`, and `ghp_` —
all pre-date the Stripe integration (PR #120, 2026-08-31). Stripe secret keys
(`sk_live_...`/`sk_test_...`) and webhook signing secrets (`whsec_...`) use an
underscore after the prefix, which the existing generic `sk-[A-Za-z0-9_-]{20,}`
pattern does not match (it requires a literal hyphen, not underscore,
immediately after `sk`). **Practical exposure today is low** — `billing.py`'s
own log calls only ever log identifiers (`event["id"]`, `event["type"]`), never
the secret key or webhook payload verbatim, so no current call site actually
puts a raw Stripe secret into a log event. But the redaction net itself has a
real hole: if any future code path ever does log a Stripe key (a stack trace
from an SDK call, a misplaced debug log, a config dump), nothing would catch
it today. **Severity: Medium** — no active exposure found, but a real gap in a
security control that exists specifically to catch exactly this class of
mistake. Recommended fix (not applied — read-only pass): add `sk_live_`,
`sk_test_`, `whsec_`, `pk_live_`, `pk_test_` patterns to `_SECRET_PATTERNS` in
`noema/core/logging.py`, and extend the existing redaction test to cover them.

### 6. localStorage — not independently re-audited this pass
No `localStorage`/`sessionStorage` writes of credential-shaped data were found
via the `NEXT_PUBLIC_*` and general secret-pattern greps run above, and BYOK
credentials are documented (and were independently verified in a prior session
per `noema_saas_pivot_2026-08-29.md`) to be write-only from the frontend's
perspective — the API never returns a stored key's plaintext. Not re-verified
with a dedicated `grep -rn "localStorage"` pass in this session; flagged as a
narrow scope gap rather than claimed clean.

## Overall verdict

**No live, exploitable secret leak found.** One real, medium-severity control
gap (Stripe key shapes absent from log redaction patterns) — a small, low-risk
fix that fits cleanly inside the Phase 0 feature freeze's "security" exception
and is a reasonable first item for Phase 5 (Security Baseline) to close.
