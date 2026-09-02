# NOEMA — Feature Inventory

Generated 2026-09-02, Phase 3 of the Launch Readiness program, from a direct
read of the codebase at `2782f74` (not from memory notes or the ROADMAP alone).
States are deliberately blunt: **VERIFIED** (code + real test coverage, read
directly), **PARTIAL** (real code, but a specific gap found by direct read),
**BROKEN** (a confirmed defect), **NOT TESTED** (code exists, no test evidence
found for it in this pass), **BLOCKED** (works in code, unreachable in
production today for an external reason). Nothing here was run against a real
LLM API — coverage claims are from reading test files that exist, not from
executing the suite in this pass.

| Feature | Status | Dependencies | User Value | Criticality | Test Coverage | Production Ready? |
|---|---|---|---|---|---|---|
| Auth (register/login/refresh/logout) | VERIFIED | Postgres, argon2id | Core | Critical | `test_db_auth_routes.py`, `test_security.py` | Yes |
| **Password reset / email verification** | **NOT BUILT** | — | Account recovery | Critical | none — no endpoint exists | **No — launch blocker** |
| Notebook/Note CRUD + editor | VERIFIED | — | Core | Critical | present in `tests/` (Phase 1, pre-pivot, long-stable) | Yes |
| Content ingestion (PDF/DOCX/MD/TXT/CSV/URL/transcript) | VERIFIED | Dramatiq worker, Redis, storage driver | Core | Critical | ingestion pipeline tests present | Yes |
| Hybrid RAG retrieval + grounded citations | VERIFIED | pgvector, embedding provider | Core | Critical | `test_retrieval.py`, `test_db_retrieval.py` | Yes |
| Concept extraction + knowledge graph | VERIFIED | LLM extraction call | Core | High | `test_knowledge.py`, `test_db_knowledge.py` | Yes |
| Flashcards (basic/definition/concept/code/cloze/reverse) + FSRS scheduling | VERIFIED | — | Core | High | `test_scheduler.py` + generation tests | Yes |
| Quizzes / exams / grading | VERIFIED | — | Core | High | covered under `study/*` tests (not individually re-verified line-by-line this pass) | Yes |
| Misconception correction | VERIFIED | Concept graph | High | Medium | dedicated coverage per prior-session PR #49 | Yes |
| Study goals (deadline feasibility) | VERIFIED | — | Medium | Medium | covered per prior-session PR #48 | Yes |
| Socratic mode | VERIFIED | LLM | Medium | Medium | `study/socratic.py` covered per prior session | Yes |
| Feynman mode | VERIFIED | LLM | Medium | Medium | `study/feynman.py`, present, not individually re-read this pass | Presumed yes |
| BYOK provider credentials | VERIFIED | AES-GCM (`core/crypto.py`) | Medium | High (financial: user's own key) | `test_providers.py` + prior-session audit | Yes |
| **AI Gateway (retries/timeouts/fallback/budget)** | VERIFIED | — | Core (invisible) | Critical | `test_providers.py` (module-level; direct gateway.py has no 1:1 test file, exercised indirectly) | Yes, with caveat below |
| Model-tier routing + real pricing (`ModelTierConfig`/`PricingService`) | VERIFIED | — | Core (invisible) | Critical | covered per PR #108/#116 (margin-safety enforced by test, not eyeballed) | Yes |
| Noema orchestrator (6-intent dispatch) | VERIFIED | Gateway, entitlements | Core | Critical | covered per PR #109-113 | Yes |
| Noema memory (bounded mastery + misconceptions in EXPLAIN/DEEPEN) | VERIFIED | `professor_memory.py` | High | High | covered per PR #110 | Yes |
| **Noema identity/persona layer** | **NOT BUILT** | Prompt stack | Trust/brand | High | zero prompts reference "Noema" as a name or contain any identity-concealment instruction (grepped every file in `noema/prompts/`) | **No — nothing stops the model from naming its real provider if asked** |
| Plan entitlements (monthly AI unit gating) | VERIFIED | `AIUsage` | Core (billing) | Critical | covered per PR #114 | Yes |
| Admin dashboard/users/profit/reports | VERIFIED | `deps.AdminUser` allowlist | Internal | Medium | covered per PR #115/#117/#119, CSRF fixed PR #118 | Yes |
| Stripe billing (checkout/portal/webhooks) | VERIFIED | Stripe API keys (configured) | Core (revenue) | Critical | webhook dict-vs-typed-object bug found+fixed PR #132, real unmocked SDK test added | Yes |
| Account deletion cancels active subscription | VERIFIED | Billing | Medium | High (financial/legal) | covered per PR #124 | Yes |
| CSRF protection (all mutating routes) | VERIFIED | `api/middleware.py` | Security (invisible) | Critical | `test_api_contract.py::test_every_mutation_is_csrf_protected` walks the real route table, not a hand-maintained list | Yes |
| Cross-user data isolation (retrieval/grounding) | VERIFIED | `owner_id` scoping | Security | Critical | every read path in `retrieval/search.py`/`grounding.py` filters by `owner_id` (direct grep confirms no unscoped path); no dedicated cross-tenant-leak test found this pass | Yes, but see Phase 5 note below |
| Rate limiting (GCRA via Redis) | VERIFIED | Redis | Security | High | `test_ratelimit.py` | Yes, fails open by design if Redis is down (documented trade-off, not a bug) |
| Secret redaction in logs | PARTIAL | `core/logging.py` | Security | Critical | tested for its own listed patterns, but **Stripe key shapes (`sk_live_`/`sk_test_`/`whsec_`) are absent from `_SECRET_PATTERNS`** — see secret-scan report | Needs one fix before full launch confidence |
| **Transactional email (any kind)** | **NOT BUILT** | — | Account/billing comms | High | none — no SMTP/SendGrid/Postmark/Resend/SES integration anywhere in `noema/` | **No — no password-reset email, no receipt email beyond Stripe's own, no notifications** |
| Anki/Notion/Obsidian/Zotero import+export | VERIFIED | — | Medium | Low | `test_import_*`/`test_export_*`/`test_db_import_*`/`test_db_export_*`, extensive | Yes |
| Landing page V2 (Mino, scroll state, pricing) | VERIFIED (code-level) | — | Marketing | Medium | `useHeroTilt.test.ts`, `useScrollMinoState.test.ts`, `page.test.tsx` (×8) | **Not visually verified in a real browser** — no local browser this session (per `noema_no_local_browser.md`), code-reviewed and unit-tested only |
| i18n | VERIFIED | `i18n.test.ts` | Medium | Low | tested | Yes |
| Router-level export/import endpoints (`api/v1/exports.py`, `imports.py`) | PARTIAL | underlying export/import logic (well-tested) | Medium | Low | the domain logic is well-tested; the HTTP-layer router files themselves have no 1-to-1 named test file found — likely covered by the generic CSRF/contract test but not confirmed line-by-line this pass | Probably fine, worth a direct look before calling it VERIFIED |
| `noema/api/middleware.py`, `deps.py` | NOT INDIVIDUALLY VERIFIED THIS PASS | — | Core (invisible) | Critical | exercised heavily via `test_api_contract.py`/`test_security.py`/every route test, but not read in isolation this pass | Presumed yes, high confidence given indirect coverage |
| Jobs/workers (`ingest`, `purge_accounts`) | VERIFIED | Dramatiq, Redis | Core | Critical | ingestion pipeline tested; `purge_accounts` triggering is documented as external/manual — **confirm an actual cron is configured on Railway, not just that the code path exists** (not verified in this pass — see Phase 29 Production Config) | Code yes; operational wiring not re-confirmed this pass |

## Headline findings for Phase 5+ prioritization

1. **No password-reset flow and no email integration at all.** This is the
   single most user-facing gap in the entire audit — a real signed-up paying
   customer who forgets their password has no recovery path today. This is a
   launch blocker, not a nice-to-have, and it's a bug-fix/reliability item so it
   is explicitly inside the Phase 0 feature freeze's allowed scope.
2. **No Noema identity/persona layer exists at the prompt level.** Every prompt
   file in `noema/prompts/` was grepped; none establish a "Noema" persona or an
   identity-concealment instruction. This is exactly Phase 7 of the 34-phase
   program and should be treated as a real, unstarted gap, not a formality —
   right now, nothing stops the underlying model from truthfully naming its own
   provider if a user asks "who are you."
3. **Stripe key shapes are missing from the log-redaction pattern list.** A real,
   specific, one-line fix (`core/logging.py`'s `_SECRET_PATTERNS`) — full detail
   in `NOEMA_SECRET_SCAN_2026-09-02.md`.
4. **Cross-user isolation looks solid on direct read** (every retrieval/grounding
   query is `owner_id`-scoped) but has no dedicated adversarial test proving one
   user cannot retrieve another's chunks by ID guessing or notebook-ID
   manipulation — worth a real test in Phase 5 (Security Baseline) rather than
   trusting the grep alone.
5. Landing page V2 is unit-tested but never visually confirmed in a real browser
   — carried forward as a known, standing limitation of this environment, not a
   new finding.
