# NOEMA — AI Architecture Audit

Generated 2026-09-02, Phase 6 of the Launch Readiness program. Read-only pass —
zero code changes, zero calls to any LLM provider. Builds on `NOEMA_SYSTEM_MAP.md`
§4 (the three-layer summary) rather than repeating it; this document is the direct
code read behind that summary, at file:line granularity, at the current commit on
`aislamsilvalol-ctrl/reconcile-noema-orca-agents`. Anything not directly confirmed
by reading the code is marked **NOT VERIFIED** rather than asserted.

## 1. AI Gateway (`noema/providers/gateway.py`, 301 lines)

### Retry policy

`RetryPolicy` (`gateway.py:77-88`): `attempts=3`, `base_delay=0.5s`,
`max_delay=8.0s`, full-jitter exponential backoff (`random.uniform(0, min(base *
2**attempt, max_delay))`) — a deliberate choice per the code comment ("synchronised
retries are worse than the original failure").

**This retry policy applies only to `chat()`, `structured()`, and `embed()`**, all
of which route through `_attempt()` (`gateway.py:205-243`), which loops `for
attempt in range(self.retry.attempts)` per provider in the chain.

**`stream()` (`gateway.py:134-164`) does not use `RetryPolicy` at all.** It tries
each provider in the chain exactly once — if the first-token `await
asyncio.wait_for(anext(iterator), ...)` raises `ProviderError` or `TimeoutError`,
it logs a warning and moves to the next provider in the chain, with no retry loop,
no backoff. This is a real, verifiable asymmetry, not a hunch: `_attempt()` has an
explicit `for attempt in range(self.retry.attempts):` (line 214); `stream()` has no
equivalent loop anywhere in its body. Since **every EXPLAIN/DEEPEN/SUMMARIZE turn
and the plain `/ai/chat` endpoint use `stream()`** (confirmed via
`noema/api/v1/ai.py:114` and `:443`), this means the single most-used call shape in
the product gets zero retries on a transient failure (a dropped connection, a
momentary 503) — it goes straight to "try the next provider" (which in production
is usually nothing, see §1's fallback note below) or failure. `chat()`/`structured()`
(used for classification, card/question generation, grading) do get the full
3-attempt backoff.

What triggers a retry vs. a hard fail (`_attempt()`, `gateway.py:219-228`):
- `ProviderError` with `retryable=True` (429s and 5xx, per each provider's own
  `_raise_for_status`) → retried.
- `ProviderError` with `retryable=False` (4xx other than 429, e.g. a 401 bad key or
  a 400 malformed request) → `break`s out of the retry loop immediately for that
  provider, with the comment "A 400 is our bug. Retrying it wastes time and hides
  it." — a good design, confirmed correct.
- `TimeoutError` → retried (no `break`).
- Any other `Exception` → `break`s immediately, no retry.

### Per-`TaskClass` timeouts (`gateway.py:36-45`)

| TaskClass | Timeout |
|---|---|
| `TUTOR_CHAT` | 120.0s |
| `EXTRACT_CONCEPTS` | 90.0s |
| `GENERATE_CARDS` | 90.0s |
| `GENERATE_QUESTIONS` | 90.0s |
| `GRADE_OPEN_ANSWER` | 60.0s |
| `SUMMARIZE` | 45.0s |
| `EMBED` | 120.0s |
| `CLASSIFY_INTENT` | 15.0s |

Any `TaskClass` not in this dict falls back to 60.0s (`_timeout()`, `gateway.py:245-246`
— `TIMEOUTS.get(task, 60.0)`). `CLASSIFY_INTENT` at 15s is the one timeout that
directly matters for perceived latency on every single Professor turn (it runs
before dispatch), and 15s is a sensible ceiling for a one-token-out structured call.

### Provider fallback — real in the code, dead in production

`AIGateway.chain` (`gateway.py:108-110`) is `[primary, *fallbacks]`, and both
`_attempt()` and `stream()` genuinely iterate it. The mechanism is correctly
implemented and has direct unit coverage (`tests/test_gateway.py`:
`test_falls_back_to_the_next_provider`, `test_streaming_falls_back_before_the_first_token_only`).

**But every real call site that constructs an `AIGateway` in production code passes
no `fallbacks` argument, so `self.fallbacks` is always `[]` and `chain` is always
`[primary]` alone.** Confirmed by grepping every `AIGateway(` construction in
`noema/` (excluding tests):
- `noema/api/v1/deps.py:244-249` (`get_gateway`, the dependency every route uses) —
  no `fallbacks=`.
- `noema/workers/__init__.py:110-116` (ingestion embedding) — no `fallbacks=`.
- `noema/services/professor.py:175-181` (`tiered_gateway`, the Professor's
  per-intent tiered gateway) — no `fallbacks=`.

So "provider fallback" as a resilience feature exists only in `gateway.py` and its
own test file; nothing in the running application ever gives a user a second
provider to fall back to. If the one configured provider is down, the "fallback"
loop still runs (harmlessly, since `chain` has one element) but there is nothing to
fall back *to*. This is worth flagging plainly: the System Map's "provider
fallback" language is accurate about the code's capability, not about what a user
actually experiences today.

### Daily token-budget guard

Tracked by `DailyBudget` (`noema/services/usage.py:64-101`), not `gateway.py`
itself — the gateway only holds a `BudgetGuard` protocol (`gateway.py:54-60`).
`DailyBudget.remaining_tokens()` (`usage.py:92-101`) is a live `SELECT SUM(...)`
over `AIUsage` rows for the user in the trailing 24 hours (a rolling window, not a
counter or cache), compared against `settings.noema_ai_daily_token_budget`
(default `1_000_000`, `config.py:115`). **No pre-allocated counter, no Redis token
bucket — it's recomputed from the database on every gated call.**

Fail-open or fail-closed? **Deliberately asymmetric, by design, and this is
correctly implemented:**
- `INTERACTIVE_TASKS` (`gateway.py:67-74`: `TUTOR_CHAT`, `GRADE_OPEN_ANSWER`,
  `SUMMARIZE`, `CLASSIFY_INTENT`) keep running until `remaining_tokens() <= 0`
  exactly — the reserve doesn't apply to them.
- Everything else (`GENERATE_CARDS`, `GENERATE_QUESTIONS`, `EXTRACT_CONCEPTS`,
  `EMBED`) stops once `remaining <= reserved_tokens`
  (`reserve` default `0.15`, `config.py:119` — 15% of the daily budget), well
  before the budget is literally exhausted.
- Both branches raise `QuotaExceeded` (`gateway.py:261-266` and `:268-276`) with a
  specific, honest, student-facing message ("resets on a rolling 24-hour window;
  everything already in your library still works" / "Generation is paused... the
  rest is reserved for asking questions and grading answers").
- A budget of `0` disables the guard entirely (`deps.py:225-234`: `budget = ...
  if settings.noema_ai_daily_token_budget > 0 else None`) — an unset env var means
  no ceiling, not "allow nothing," which is the right direction to fail for an
  ops mistake.

This part of the design is sound and matches its own docstrings. **What's not
sound is what happens to `QuotaExceeded` once it's raised inside an SSE stream
already in flight — see §6, the single biggest finding of this audit.**

### The `AIUsage`-writing callback

`UsageRecorder` (`gateway.py:48-51`) is implemented by `UsageWriter`
(`noema/services/usage.py:20-61`). Cost is computed fresh at write time from
`PricingService.cost_cents()` (see §3), **not** trusted from `Usage.cost_cents`,
because — per `usage.py`'s own docstring, confirmed by reading `providers/base.py`
— no provider implementation ever populates that field; it defaults to `0.0` and
stays there. This is a correct, deliberate design, not an oversight.

**Could a call go unrecorded on an error path? Yes, one concrete case:**
`_attempt()` (used by `chat()`/`structured()`/`embed()`) does write a failure row
when the whole chain is exhausted — `gateway.py:242`: `await self._log_usage(self.primary,
model or "", task, Usage(), False)` — a zero-token, `succeeded=False` row, before
raising. **`stream()` has no equivalent.** Reading `stream()`
(`gateway.py:134-164`) end to end: `_log_usage` is only called from inside the
per-event loop, when `event.done and event.usage` (line 157-160) — i.e., only on a
*successful* completion. If every provider in the chain fails before yielding a
first token, the `for provider in self.chain:` loop simply exhausts and the
function does `raise last_error or ProviderError(...)` (`gateway.py:164`) with
**no call to `_log_usage` anywhere in that path.** Net effect: a fully-failed
streaming call (the shape used by every EXPLAIN/DEEPEN/SUMMARIZE turn) leaves zero
trace in `AIUsage` — not even the zero-token failure row that `chat()`/`structured()`
would write. This doesn't cause any billing/cost inaccuracy (0 tokens either way),
but it does mean admin-facing reliability metrics built on `AIUsage.succeeded`
(`noema/api/v1/admin.py`'s `GET /intelligence`, per the System Map) **undercount
streaming failures specifically** — a real, narrow, verifiable gap, not asserted
from the docstring alone.

## 2. Provider registry (`noema/providers/registry.py`, 93 lines)

`_REGISTRY` (`registry.py:18`) is populated by `@register("name")` decorators on
each provider class, imported (and thus registered) via `deps.py:15-20`'s
`from noema.providers import anthropic, mock, ollama, openai` — `gemini` and
`openrouter` are named in the System Map/config but **`noema/providers/` has no
`gemini.py` or `openrouter.py` importable from `deps.py`'s import list**; only
`anthropic`, `openai`, `ollama`, `mock` are actually wired up. `config.py` still
has `gemini_api_key`/`openrouter_api_key` settings fields (confirmed at
`config.py:68-69`) and `ai.py:487` lists them in `list_providers`'s
`deployment_keys` dict, but `registry.create("gemini", ...)` would raise
`UnknownProvider` (`registry.py:44-47`) today since nothing registers that name.
**This is worth flagging plainly: two of the five providers the System Map and
`config.py` reference as configurable are not actually implemented providers in
this codebase state** — not verified whether this is intentional (planned,
unbuilt) or a stale config surface; either way it's a real gap between what
`config.py`/`ai.py`'s `list_providers` advertise and what `_REGISTRY` can resolve.

`create()` (`registry.py:43-52`): looks up the factory, raises `UnknownProvider`
(a real `NoemaError` subclass, so it gets a clean JSON error response — see §6) if
the name isn't registered, and raises `FeatureUnavailable` (also a `NoemaError`)
if `local_mode=True` and the provider isn't in `LOCAL_PROVIDERS =
{"ollama", "mock", "local-embeddings"}` (`registry.py:22`). Both of these failure
paths are handled gracefully end-to-end — confirmed, not asserted.

### BYOK override

`build_provider()` (`deps.py:174-206`) is the actual resolution point, not
`registry.py` itself — `registry.py` only knows provider *names*, not
credentials. `build_provider` does `user_key = await
credentials.reveal_for_gateway(name) if credentials else None`, then for
`anthropic`/`openai` explicitly: `api_key=user_key or settings.<provider>_api_key`
(`deps.py:196-197`, `:203`). **BYOK always wins over the deployment key when
present** — confirmed by the `or` short-circuit order, correct per its own intent.
For any other provider name reaching the generic branch (`deps.py:206`):
`api_key=user_key or ""` — no deployment-key fallback at all for a provider not
explicitly special-cased (today that's moot since only `ollama`/`mock` are the
other registered names, and `ollama` is special-cased separately with no
`api_key` param, `mock` likewise).

### What happens with no credentials at all — the one real bug in this section

Traced end to end: `AnthropicProvider.__init__` (`anthropic.py:54-62`) raises
`ProviderError("Anthropic API key is required", provider=self.name)`
**synchronously, in the constructor**, if `api_key` is falsy. `OpenAIProvider`
almost certainly does the same (not fully re-read this pass, but the pattern in
`deps.py:build_provider` treats both the same way — **NOT VERIFIED line-by-line
for `openai.py`, flagged rather than assumed**).

Two call sites reach this constructor differently, with different outcomes:

1. **`professor.tiered_gateway()`** (`professor.py:162-173`) wraps the
   `build_provider(...)` call in `try/except Exception` and falls back to the
   caller's already-working `default_gateway` with `model=None` on *any* failure,
   including this one. **Graceful, confirmed correct.**
2. **`deps.py:get_gateway()`** (`deps.py:219`) — the dependency that builds the
   *default* gateway every route (`/ai/chat`, `/ai/professor`, etc.) uses — calls
   `build_provider(route.provider, settings, credentials)` with **no
   try/except at all**. If the deployment's configured default provider (e.g.
   `NOEMA_DEFAULT_PROVIDER=anthropic`) has no `ANTHROPIC_API_KEY` set and the user
   has no BYOK key for it, this raises a bare `ProviderError` **during FastAPI
   dependency resolution, before any route handler body runs.**

   `ProviderError` (`providers/base.py:144`) is a plain `Exception`, **not** a
   `NoemaError` subclass (confirmed: `core/errors.py` defines `NoemaError` and
   its children `NotFound`/`Unauthorized`/`Forbidden`/`Conflict`/`RateLimited`/
   `QuotaExceeded`/`ProviderUnavailable`/`FeatureUnavailable`; `ProviderError` is
   a separate hierarchy entirely, defined in `providers/base.py`, that shares no
   base class with any of them). `register_error_handlers()`
   (`core/errors.py:91-103`) only installs handlers for `NoemaError` and
   `RequestValidationError`. **There is no catch-all `Exception` handler anywhere
   in `noema/main.py`** (confirmed by grep — only the two `except Exception`
   blocks in `main.py` are inside lifespan/startup code, unrelated to request
   handling). So this specific failure — a syntactically-valid, known provider
   name with genuinely missing credentials — falls through to Starlette's default
   unhandled-exception behavior: a generic 500 with no RFC7807 body, no honest
   message about "which provider" or "no key configured." **This is the opposite
   of graceful, and it's the same failure shape §6 covers for the mid-stream
   case.**

   Contrast this with the established, correct pattern used elsewhere in the same
   codebase: `noema/study/socratic.py:164-166` and `noema/study/feynman.py:84-90`
   both explicitly catch `ProviderError` and re-raise `ProviderUnavailable` (a
   real `NoemaError`, 502, gets the clean JSON handler) — proving the fix is a
   known, already-used one-line pattern, just not applied at `deps.py:219`. This
   is exactly the kind of small, well-scoped reliability gap the Feature Freeze's
   bug-fix exception exists for; **not fixed here per this task's scope.**

   Practical severity today: `noema_default_provider` defaults to `"ollama"`
   (`config.py:65`), which needs no API key, so a stock deployment doesn't hit
   this. It's live risk only for a deployment that sets
   `NOEMA_DEFAULT_PROVIDER=anthropic`/`openai` and then has that key unset or
   removed (a real, plausible ops mistake — e.g. a rotated/revoked Railway env
   var) — per prior session notes, production is currently configured with real
   Anthropic/OpenAI keys, so this is a latent gap, not an active incident.

### Invalid BYOK key specifically

Handled well at the point a key is *stored*: `POST /ai/credentials`
(`ai.py:520-545`) calls `provider.health()` immediately after `service.store(...)`
and records `verification_error` via `mark_verified()`, inside a broad `except
Exception` — so a bad key is caught and surfaced at credential-creation time with
"a clear message, not silently mid-session three days later" (the code's own
comment, confirmed accurate). **Not handled as well if a previously-valid key is
revoked later**: the next live call using it hits the provider's real 401 →
`AnthropicProvider._raise_for_status` (`anthropic.py:211-221`) raises
`ProviderError(f"Anthropic returned {status}", retryable=status==429 or
status>=500, status=status)` — for 401, `retryable=False`, so it's not wastefully
retried (correct), but the message literally names "Anthropic" — a minor tension
with the gateway module's own stated goal ("feature code never learns which
vendor produced one" — `gateway.py:5-6`) that only holds for successful
responses, not error text. Where this `ProviderError` ends up depends entirely on
which dispatch path is running — see §6.

## 3. Pricing / tiering (`noema/services/pricing.py`, `ModelTierConfig`)

**DB-sourced, admin-editable, no staleness detection or alerting of any kind —
confirmed by reading the schema and every call site, not asserted from the
docstring.**

`ModelTierConfig` (`db/models.py:849-882`) is a plain table, `tier` (enum) as
primary key, one row per tier, columns
`provider`/`model`/`input_cost_per_million_usd`/`cached_input_cost_per_million_usd`/
`output_cost_per_million_usd`. `PricingService.cost_cents()`
(`pricing.py:32-52`) does a live `SELECT ... WHERE provider = :p AND model = :m`
against this table on every single usage-recording call (no caching layer, no
in-process copy) — genuinely reads current DB state each time, so an admin editing
a row takes effect on the very next call, for better or worse (better: no stale
in-memory config; worse: nothing validates what they typed).

**No staleness-detection or alerting mechanism exists anywhere in this codebase**
for `ModelTierConfig` drifting from real provider pricing — confirmed by grep:
there is no cron, no scheduled check, no test that re-fetches live pricing and
diffs it against the table, no "last verified" timestamp column on
`ModelTierConfig` itself (contrast with `ProviderCredential`, which does have
`last_verified_at`/`verification_error` columns — the same pattern was *not*
applied here). If Anthropic or OpenAI changes a price, `ModelTierConfig` silently
keeps charging (internally, for cost/margin accounting) at the old number until a
human notices and edits the row by hand. This is a real, standing gap — not a bug
introduced by anything recent, just an absence worth naming for Phase 29+
(production config/monitoring) to close.

**A related, narrower gap found this pass, not previously flagged:**
`cached_input_cost_per_million_usd` exists as a column (seeded with real values by
migration `0014`, e.g. economy tier `$0.10/MTok` cached vs `$1.00/MTok` uncached —
confirmed reading `alembic/versions/0014_real_tier_pricing_and_margin_safe_limits.py:22-24`)
but **`PricingService.cost_cents()` never reads it** — the method only uses
`input_cost_per_million_usd` and `output_cost_per_million_usd`
(`pricing.py:48-51`). This is consistent with `providers/base.py`'s `Usage`
dataclass (`prompt_tokens`/`completion_tokens`/`cost_cents` only — no cached-token
count field anywhere), so there's no data to apply the cached rate to even if the
column were read. Net effect: the schema models prompt-cache pricing but the
runtime never uses it, meaning any call that *did* benefit from provider-side
prompt caching is still charged internally at the full input rate — conservative
in NOEMA's own favor (never undercharges), but it does mean `AIUsage.cost_cents`
and any margin report built on it **overstate** true provider cost whenever
caching is actually happening upstream. Not a margin-safety risk; a reporting
accuracy gap.

### The margin bug the prior session fixed — re-verified, still correct

Read `alembic/versions/0014_real_tier_pricing_and_margin_safe_limits.py` in full.
Its own docstring shows real math, not just an assertion: economy/standard/premium
tier prices sourced from `platform.claude.com/docs`, dated 2026-08-30 (Haiku 4.5 /
Sonnet 5 / Opus 5 at $1/$2/$5 input and $5/$10/$25 output per MTok), a blended
cost-per-unit calculation ($0.004/unit) against a stated tier-usage mix (10%
economy / 80% standard / 10% premium, matching `professor.py`'s actual
`INTENT_TIER` dispatch — cross-checked, this mix is a reasonable real-world
approximation of it), and worst-case gross margin of ~73-74% on every paid plan
even if every subscriber maxes out every month. The arithmetic in the migration
checks out on manual recomputation (student: 300 units × $0.004 = $1.20 = R$6.24 at
R$5.20/USD, 20.9% of R$29.90 — matches). **This is real, sourced, dated, and the
numbers are internally consistent — confirmed, not just trusted from the memory
note.** The one caveat: the R$5.20/USD exchange rate is explicitly a manual,
undated-going-forward assumption (the migration's own words: "recompute if it
moves materially, this is not a live-fetched rate") — another instance of the
same staleness-detection gap above, just for FX rather than model pricing.

## 4. Entitlements (`noema/services/entitlements.py`, 108 lines, read in full)

### Check-before-call ordering — confirmed true by reading `ai.py` directly

`professor_chat()` (`ai.py:161-258`): `EntitlementsService(db,
user).check_ai_usage()` is called at line 182, and its `gate.allowed` is checked
immediately (`if not gate.allowed:`, line 183) — if blocked, the function returns
a `StreamingResponse` that yields a single `"blocked"` SSE event
(`ai.py:188-198`) **without ever calling `professor.classify_intent()`** (which
only happens at line 213, strictly after the `if not gate.allowed:` block has
already returned). This is a real, verified ordering — the System Map's claim
("a blocked turn costs the platform nothing") is accurate: no gateway call of any
kind happens before the entitlement gate passes. Confirmed by direct control-flow
read, not cited from the note.

### Race condition — real and unmitigated, but bounded in severity

`check_ai_usage()` (`entitlements.py:92-108`) computes `used` via
`_used_units_this_period()` (`entitlements.py:79-90`), a live `SELECT SUM(...)`
over historical `AIUsage` rows — **not an atomic counter, not a row with a lock**.
Grepped the entire `noema/` tree for `with_for_update`/`for_update`/
`advisory_lock`/`SELECT ... FOR UPDATE`: the only hits anywhere in the codebase
are `noema/services/imports.py:240` (`.with_for_update(of=Notebook)`, unrelated)
and `noema/workers/__init__.py:137` (`pg_try_advisory_lock`, the ingestion
dedup lock, also unrelated). **Nothing locks `AIUsage` or serializes concurrent
entitlement checks for the same user.**

Concretely: if a user fires two `/ai/professor` requests close together (a
double-click, two browser tabs, a retried request), both can run
`check_ai_usage()` before either has written its resulting `AIUsage` row — since
the `AIUsage` insert only happens inside `UsageWriter.__call__`
(`usage.py:34-61`), triggered by the gateway's `_log_usage` **after the model call
completes**, well after the entitlement check that gated it. Both requests can
see `used < limit` as true from the same pre-call snapshot and both proceed. This
is a genuine, unmitigated TOCTOU race — **confirmed by reading the code path, not
inferred.**

Severity is real but bounded, not catastrophic: the overage per race is capped at
roughly the cost of one extra concurrent call (not unbounded — a third concurrent
request would see the first two's usage once either flushes, and `AIUsage`
inserts do happen mid-request via `await self.db.flush()`, `usage.py:61`, so the
window is the time between two requests' respective `check_ai_usage()` reads and
their triggering call's completion, typically single-digit seconds for a chat
turn). No test in the repo exercises this concurrently — **not tested, flagged as
an open gap for Phase 5+ rather than asserted as exploited.**

## 5. Orchestrator (`noema/services/professor.py`, 244 lines, read in full)

### Intent classification

`classify_intent()` (`professor.py:98-124`) always runs on `ModelTier.ECONOMY` —
enforced structurally, not just by convention: `professor_chat()`
(`ai.py:205-215`) explicitly resolves `professor.tiered_gateway(ModelTier.ECONOMY,
...)` before calling `classify_intent`, so there's no path for classification to
run on a more expensive tier. `TaskClass.CLASSIFY_INTENT` has a 15s timeout
(§1) and uses `gateway.structured()`.

**Failure handling, traced precisely:** the `try/except (ProviderError, KeyError,
ValueError)` at `professor.py:109-124` catches (a) a real provider failure, (b) a
malformed/missing `"intent"` key in the schema response, (c) an intent value
outside the `Intent` enum. A **timeout** during classification is also caught
correctly, though not obviously from reading `classify_intent` alone: a raw
`TimeoutError` raised inside `gateway.structured()` → `_attempt()` never escapes
as a bare `TimeoutError` — `_attempt()`'s final `raise
self._as_provider_error(last_error, self.primary)` (`gateway.py:243`) always
converts it to a `ProviderError` first (`_as_provider_error`, `gateway.py:287-297`:
`if isinstance(exc, TimeoutError): return ProviderError(f"{provider.name} timed
out", ..., retryable=True)`). So by the time it reaches `classify_intent`'s
except clause, a timeout *is* a `ProviderError` and *is* caught. **Confirmed
correct, not just documented as such** — the fail-safe-to-`Intent.EXPLAIN`
behavior genuinely covers provider-down, malformed-response, and timeout cases
alike, all falling back to the exact pre-orchestrator behavior. This is real,
working defensive design.

### Per-intent tier mapping — cost-sensible, checked against the user's own brief

`INTENT_TIER` (`professor.py:77-84`):

| Intent | Tier | TaskClass (`plan()`, `professor.py:213-222`) |
|---|---|---|
| EXPLAIN | STANDARD | `TUTOR_CHAT` |
| DEEPEN | PREMIUM | `TUTOR_CHAT` |
| SUMMARIZE | STANDARD | `SUMMARIZE` |
| QUIZ_ME | STANDARD | `GENERATE_QUESTIONS` |
| CREATE_FLASHCARD | STANDARD | `GENERATE_CARDS` |
| CREATE_EXAM | ECONOMY | `GENERATE_QUESTIONS` (never actually called — see below) |

Against the brief's own standard ("não usar reasoning model caro para 'bom dia',
mas também nunca cortar qualidade pedagógica"): classification (the "bom dia"
case — a throwaway routing decision) is unconditionally economy, confirmed above.
The pedagogically real actions (EXPLAIN, SUMMARIZE, QUIZ_ME, CREATE_FLASHCARD) all
sit on STANDARD, not economy — the code doesn't cut quality on the actions that
teach. Only DEEPEN escalates to PREMIUM, which is the one intent explicitly named
as "go deeper" — the one moment a costlier, more capable model is arguably
warranted. `CREATE_EXAM`'s ECONOMY tag is honestly caveated in the code's own
comment (`professor.py:74-76`) as a placeholder for a `plan()` lookup that never
actually calls a model — `start_exam()` only picks already-generated questions at
random, confirmed by the docstring at `professor.py:319-334` and by `_dispatch_exam`
(`ai.py:313-362`) never touching `dispatch.call.gateway`. **This mapping is
cost-sensible and internally consistent with the stated design goal — verified,
not assumed.**

## 6. Failure-mode audit — the most important section

This is the one place this pass found a real, evidence-backed, load-bearing
inconsistency. Summarized per the five scenarios the task asked for, each traced
through actual exception handling, not guessed:

### a) Configured provider is down (transport failure / 5xx)

- **Pre-stream** (entitlement check, classification): `ProviderError` correctly
  caught and handled at every point covered in §5 — classification fails safe to
  EXPLAIN, no crash, no honest-error gap.
- **Mid-stream** (`_dispatch_stream`, `ai.py:365-469` — EXPLAIN/DEEPEN/SUMMARIZE,
  the most common turn): `except ProviderError as exc:` at `ai.py:467-469` yields
  a clean `_sse("error", {"message": ..., "provider": ...})` event. **Honest and
  correct.** Same pattern in the plain `/ai/chat` streaming handler (`ai.py:148-152`).
- **Mid-stream, QUIZ_ME / CREATE_FLASHCARD** (`_dispatch_action`, `ai.py:261-311`):
  `generate_questions`/`generate_cards` (`noema/study/questions.py:118-134`,
  `noema/study/generation.py:99-116`) catch `ProviderError` **per batch** and
  `continue`, degrading to fewer (or zero) generated items rather than crashing —
  genuinely graceful for a provider-down scenario. **But there is no `except`
  anywhere in `_dispatch_action` itself**, so if `generate_questions`/
  `generate_cards` somehow raised past their own per-batch catch (they don't for
  `ProviderError`, confirmed — but see (c) below for what does), the SSE stream
  would die with no `"error"` event, unlike `_dispatch_stream`'s equivalent path.
  The user-visible result for a fully-down provider on this path today: an
  `"action"` event reporting `count: 0`, with **no message explaining why** — not
  a crash, but a silent, unexplained degradation, less honest than the
  EXPLAIN/DEEPEN/SUMMARIZE path gets for the identical underlying failure.

### b) Daily token budget exhausted — the sharpest finding in this audit

`_check_budget()` raises `QuotaExceeded` (`gateway.py:261-266`,
`:268-276`), which is a `NoemaError` subclass (`core/errors.py:71-73`) — genuinely
well-designed for the case where it fires **before a `StreamingResponse` is
constructed** (e.g. mid-classification, or anywhere in `professor_chat()`'s
synchronous setup before line 254's `return StreamingResponse(...)`): FastAPI's
`register_error_handlers` (`core/errors.py:91-98`) catches it and returns a clean
413 with the exact message the code wrote.

**But once a `StreamingResponse` has started iterating its generator, this handler
can no longer intervene** — that's standard ASGI/Starlette behavior, confirmed by
reading `register_error_handlers`, which only wraps the request/response cycle,
not an in-flight streamed body. Tracing every place `QuotaExceeded` can be raised
*inside* an already-started SSE generator:

- `_dispatch_stream` (`ai.py:365-469`): the `try/except` at line 442/467 only
  catches `ProviderError`. `dispatch.call.gateway.stream(request)` at line 443
  calls `_check_budget()` first thing inside `gateway.stream()` — if the daily
  budget has hit its ceiling (or, for `TUTOR_CHAT` specifically, `remaining <= 0`
  exactly, since it's an `INTERACTIVE_TASK`), this raises `QuotaExceeded`, **which
  is not a `ProviderError`, so the `except ProviderError` clause does not catch
  it.** It propagates out of the async generator uncaught.
- `_dispatch_action` (`ai.py:261-311`): `generate_questions`/`generate_cards` call
  `gateway.structured()` per batch, which also calls `_check_budget()` first.
  `GENERATE_QUESTIONS`/`GENERATE_CARDS` are **not** `INTERACTIVE_TASKS`
  (`gateway.py:67-74` only lists `TUTOR_CHAT`/`GRADE_OPEN_ANSWER`/`SUMMARIZE`/
  `CLASSIFY_INTENT`), so they hit the *reserve* threshold
  (`remaining <= reserved_tokens`, ~15% of the daily budget by default) — meaning
  this is **more likely to trigger** than the interactive-task case, not less.
  `generate_questions`/`generate_cards`'s own `except ProviderError` (confirmed at
  `questions.py:132-134`, `generation.py:114-116`) does not catch `QuotaExceeded`
  either — it propagates straight through, and `_dispatch_action` has no
  try/except of its own at all.

**Net effect, confirmed by reading the code, not guessed:** a student who hits
the daily token budget mid-conversation, or hits the 15%-reserve threshold while
asking for a quiz or flashcards, gets an SSE stream that simply dies — no
`"error"` event, no honest "budget exhausted" message inside the stream, the
exact opposite of the clean, specific message `QuotaExceeded` was written to
carry (`gateway.py:262-263`: "The daily AI token budget is used up... everything
already in your library still works"). That message is real and well-written; it
just never reaches the user in the one shape (an in-flight SSE stream) that is
the actual common case for how these intents are invoked. **This is not tested**
— grepped `tests/test_db_professor.py` (the dedicated Professor test file) for
`QuotaExceeded`/budget-exhaustion scenarios at the API layer: none exist: the
tests cover entitlement blocking (a different, correctly-handled mechanism, §4)
and classification failure, but not a `DailyBudget` trip during dispatch.

### c) User's own BYOK key is invalid

- **At storage time** (`POST /ai/credentials`): validated immediately via
  `provider.health()`, broad `except Exception`, stored as
  `verification_error` — genuinely graceful, confirmed at `ai.py:520-545`.
- **A previously-valid key revoked later**: surfaces as a non-retryable
  `ProviderError` from the real 401 (`anthropic.py:211-221`). Follows the same
  branching as (a) above — honest `"error"` SSE event on the
  EXPLAIN/DEEPEN/SUMMARIZE path, silent `count: 0` degradation with no reason
  given on the QUIZ_ME/CREATE_FLASHCARD path.
- **No BYOK key and no deployment key for the configured provider at all**:
  covered in §2 — an uncaught, un-translated `ProviderError` at
  `deps.py:get_gateway()`, before any route body runs, resulting in a generic,
  unhelpful 500. This is the one failure mode in this entire audit that is a
  genuine crash rather than a degraded-but-honest experience.

### d) Entitlement check fails (plan limit reached)

Cleanly handled — a dedicated `"blocked"` SSE event before any model call, per §4.
This is the one scenario of the five that this audit found to be unambiguously
correct with no caveats.

### e) Classification call times out

Cleanly handled — falls back to `Intent.EXPLAIN`, per §5. Also unambiguously
correct.

### Summary table

| Failure | Pre-stream (before `StreamingResponse`) | Mid-stream, EXPLAIN/DEEPEN/SUMMARIZE | Mid-stream, QUIZ_ME/CREATE_FLASHCARD |
|---|---|---|---|
| Provider down | Handled (fails safe / clean error) | Honest `"error"` SSE event | Silent degrade to `count: 0`, no reason given |
| Daily budget exhausted | Clean 413 via `QuotaExceeded`/`NoemaError` | **Uncaught — stream dies with no error event** | **Uncaught — stream dies with no error event** |
| BYOK key invalid (revoked) | N/A (only checked at credential creation) | Honest `"error"` SSE event | Silent degrade to `count: 0`, no reason given |
| No credentials at all | **Uncaught `ProviderError` — generic 500** | N/A (never reaches dispatch) | N/A |
| Entitlement limit reached | Clean `"blocked"` SSE event | N/A (never reaches dispatch) | N/A |
| Classification timeout | Falls back to EXPLAIN, no error shown | N/A | N/A |

## Headline findings for Phase 7+ prioritization

1. **`QuotaExceeded` (daily token budget) is not caught inside any SSE streaming
   generator in `ai.py`, only `ProviderError` is.** This is the single most
   valuable finding of this audit: a well-designed, honestly-worded budget-guard
   error exists (`gateway.py:261-276`) but silently fails to reach the user in the
   most common code path it can fire from (`_dispatch_stream`, `_dispatch_action`).
   Small, well-scoped fix (broaden the `except` clauses in `ai.py:442-469` and
   wrap `_dispatch_action`'s body), in scope under the Feature Freeze's bug-fix
   exception — not fixed in this pass.
2. **`deps.py:get_gateway()` can raise a bare, uncaught `ProviderError` (not a
   `NoemaError`) when the deployment's default provider has no credentials at
   all**, resulting in a generic 500 instead of the honest error every other
   failure mode in this codebase gets. The fix pattern already exists elsewhere in
   the same codebase (`socratic.py:164-166`, `feynman.py:84-90`: catch
   `ProviderError`, re-raise `ProviderUnavailable`) — not applied here. Low
   current live risk (`noema_default_provider` defaults to `ollama`, and
   production has real keys configured per prior session notes) but a real latent
   gap for any provider-config change.
3. **Provider fallback is fully implemented and unit-tested but never wired up in
   production** — every `AIGateway(...)` construction in the app passes no
   `fallbacks`, so the resilience the System Map describes exists in `gateway.py`
   alone, not in what a user actually experiences.
4. **`stream()` gets zero retries** (no `RetryPolicy` loop), while
   `chat()`/`structured()`/`embed()` get up to 3 attempts with backoff — and
   `stream()` is the path every EXPLAIN/DEEPEN/SUMMARIZE turn uses.
5. **Two of the five providers referenced in `config.py`/`ai.py`'s
   `list_providers` (`gemini`, `openrouter`) have no registered implementation** —
   `registry.create()` would raise `UnknownProvider` for either today.
6. **Entitlements has a real, unmitigated TOCTOU race** (no row lock, no atomic
   counter — a live `SUM()` query gates each call) — bounded in severity (roughly
   one extra call's worth of overage per race), not tested, worth a deliberate
   decision (accept the bound, or add locking) rather than leaving it unexamined.
7. **The margin-safety fix from migration `0014` re-verified as correct** — real,
   dated, sourced pricing; the blended-cost/margin arithmetic checks out on manual
   recomputation. One adjacent, newly-found gap: `cached_input_cost_per_million_usd`
   is seeded with real data but never read by `PricingService.cost_cents()`,
   overstating true cost (conservatively, not a margin risk) whenever provider-side
   prompt caching is actually in effect.
8. **No staleness-detection or alerting exists for `ModelTierConfig` drifting from
   real provider pricing** — an admin can silently let pricing go stale forever;
   nothing in the codebase would notice or flag it.
