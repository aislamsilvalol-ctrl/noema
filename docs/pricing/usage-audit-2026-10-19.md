# NOEMA AI usage and unit-economics audit (2026-10-19)

Read-only audit of `origin/main` (head `89c571b`, #276) plus aggregate production data (Railway `production`, Postgres at alembic `0037`). No code changed, no rows written. All DB queries ran inside a `READ ONLY` transaction (asyncpg in the `api` container; the postgres service has no public URL/TCP proxy). No emails, names or message text were selected.

Prices used: Anthropic first-party prices per MTok (input / cache read / output): Haiku 4.5 $1 / $0.10 / $5, Sonnet 5 $2 / $0.20 / $10, Opus 5 $5 / $0.50 / $25. Cache write (5 min) is 1.25x input. These match the `model_tier_configs` rows in prod. OpenAI prices come from `pricing.py` `_LIST_PRICES`: gpt-4.1 $2 / $0.50 / $8, gpt-4.1-mini $0.40 / $0.10 / $1.60. I did not re-verify these, so check them against OpenAI's price page. text-embedding-3-small is $0.02/MTok (assumed; it is not in the code). FX is R$5.20/USD, the same labelled assumption migration 0014 uses.

---

## TL;DR

- **The sample is too small to price from.** Production has 23 users, all on `free`, and 240 `ai_usage` rows in total (2026-08-12 → 2026-10-07). **No AI call has been made in prod for the last 12 days.** Over the last 30 days there were 129 calls from 7 users. Over all time, 39 teaching sessions came from 9 learners. Most of this traffic is internal QA.
- **Recorded cost is wrong.** All-time recorded cost is 69.8¢, and all of it is Anthropic. **Every OpenAI row recorded 0¢**: stream rows were written with model `unknown`, and structured rows were written with 0 tokens and a `claude-haiku` model name. Recomputed real spend is about **$0.83 all-time and about 13¢ in the last 30 days**. Embeddings, worker ingestion and the public demo are not recorded at all.
- **One Professor turn today** (routing `anthropic:0,openai:100` sends standard and premium turns to gpt-4.1) costs **about 1.0–1.3¢** at a 10-turn-session average of about 5k input and 400 output tokens. On Anthropic tiers the same turn costs **about 1.6–2.0¢ on Sonnet 5**. The CORRECT move (premium) runs on **Opus 5 at about 6.2–7.2¢**, which was observed at 6.2¢ per call. The blended Anthropic cost is about **2.5¢ per turn**.
- **A 10-turn lesson costs about 11–14¢ on OpenAI and about 25–30¢ on Anthropic.** A new subject adds a curriculum costing about 0.25¢ (mini) or 0.75¢ (Haiku). Reviews (FSRS) cost $0.
- **A "unit" is not "one short exchange" as the pricing copy says.** 1 unit = 1,000 prompt+completion tokens, and cached tokens count in full. A real turn costs **about 4–8 units** (average about 5.7 over a 10-turn lesson). In practice the plans buy: Free 100 units ≈ 17 turns per month, Student 300 ≈ 53, Pro 600 ≈ 105, Max 1,000 ≈ 175 (about 6 per day).
- **The AI cost of a fully used plan is low:** about $0.0023 per unit on gpt-4.1 and about $0.004 per unit on Anthropic. A fully used Max plan costs R$12–21 against a price of R$99.90. Student costs R$3.6–6.2 against R$29.90. The constraint is plan value (turns per month), not margin.

---

## Part A — Code map

### A1. How a model is chosen

- `deps._gateway` creates the primary from `Router.resolve(TUTOR_CHAT)`, which is `NOEMA_DEFAULT_PROVIDER=anthropic` (no `NOEMA_MODEL_*` set in prod). The fallbacks are every other provider with a key (`_FALLBACK_ORDER` = anthropic, openai, gemini, openrouter). Each call gets a usage writer (`UsageWriter`), the daily token budget and the embedding cache.
- `NOEMA_AI_ROUTING=anthropic:0,openai:100` (`routing.py`) sends every routed call to OpenAI first. Anthropic stays in the chain as a last resort. The choice is sticky per key, where the key is the session id or else the learner.
- `services/professor.tiered_gateway(tier)` reads the `model_tier_configs` row (all three rows are Anthropic). It builds a gateway with that provider as primary and sets `models=` to the other providers' model for the same tier (`TIER_MODELS`, overridable through `NOEMA_TIER_MODELS`, which is unset in prod).
- `gateway._for(provider, request)` behaves as follows. The primary runs the row's model. A non-primary provider runs `models[provider]`. **If the request names no model, every provider runs its own default.**

| Tier | Anthropic (row) | OpenAI (`TIER_MODELS`) | Today in prod |
|---|---|---|---|
| economy | claude-haiku-4-5-20251001 | gpt-4.1-mini | gpt-4.1-mini |
| standard | claude-sonnet-5 | gpt-4.1 | gpt-4.1 |
| premium | claude-opus-5 | gpt-4.1 | gpt-4.1 |
| untiered (model=None) | provider default `claude-sonnet-4-5` | provider default `gpt-4.1-mini` | gpt-4.1-mini |
| embeddings | (none — raises) | text-embedding-3-small | text-embedding-3-small |

Note: before #268 (2026-10-07 21:27 -03), a fallback ran on `model=None`, which means the OpenAI default **gpt-4.1-mini**. Every OpenAI row in prod predates #268, so all of them were served by gpt-4.1-mini.

### A2. Every AI call site

Caps come from `gateway.DEFAULT_MAX_TOKENS`: TUTOR_CHAT 2048, GRADE 1024, CLASSIFY/MODERATE 512, everything else 4096, unless the caller sets its own. Prompt sizes are measured as chars/4 of `noema/prompts/*.md`.

| Feature (ai_usage.feature) | Code | Task class | Tier → model today | max_tokens | Prompt (≈tok) | Recorded? |
|---|---|---|---|---|---|---|
| Professor turn `professor.<move>` | `professor/engine.py` prepare→stream | TUTOR_CHAT (stream) | by move (`moves.MOVE_TIER`): standard for teach/question/review/example/practice/quiz/summarize/advance/reorient/return/answer/guide; **premium for correct**; economy for flashcard/exam/motivate/park → gpt-4.1 / gpt-4.1 / mini | 1,900 (`budget.response`+500); focus: `max_words*1.6+450` = 594/706/866 | system = persona 533 + tutor.explain 184 (or rag.answer 300) + teaching.principles 1,442 ≈ **2,160** (+mino.focus 323 in focus) | yes, with session_id |
| Route classifier `professor.route` | `moves.classify_route` | CLASSIFY_INTENT | economy → mini | 512 | route.v4 636 + context ≈ 750 in / ~15 out | yes (no session_id) |
| Goal parse `professor.parse_goal` | `professor/intent.py` | CLASSIFY_INTENT | economy → mini | 512 | 257 + goal (≤2,000 chars) | yes (no session_id) |
| Curriculum `professor.curriculum` | `professor/curriculum.py` (v2) | SUMMARIZE | economy → mini | 4,096 | 342 + goal ≈ 550 in / ~1,200 out (est.) | yes (no session_id) |
| Flashcards `professor.flashcards` | `professor/flashcards.py` (FLASHCARD move, auto-cards after "understood", checkpoint) | GENERATE_CARDS | economy → mini | 4,096 | 218 + lesson ≤6,000 chars ≈ 1,800 in / ~300 out | yes |
| Checkpoint exam `professor.assessment` | `professor/assessment.py` via `checkpoint.run_checkpoint` (every 4 concepts) | GENERATE_QUESTIONS | economy → mini | 4,096 | 273 + lesson ≤8,000 chars ≈ 2,400 in / ~1,100 out | yes |
| Open-answer grade `professor.grade` | `assessment.py:355` (on submit) | GRADE_OPEN_ANSWER | economy → mini | 1,024 | 279 + answer ≈ 700 / 120 | yes |
| Memory compaction `professor.compact` | `memory.ContextCompactor` (after 4,500 transcript tokens or 24 turns; keeps 6) | SUMMARIZE | economy → mini | 4,096 | 394 + transcript ≤24,000 chars ≈ 5,500 / ~450 | yes |
| Memory recall + RAG query embedding | `memory.render_memory`, `retrieval/search.py` | EMBED | text-embedding-3-small | – | ~20–50 tok | yes, but priced 0 |
| Content guard | `services/guard.py` | MODERATE_CONTENT | economy | 512 | 615 | **off in prod** (`noema_guard_enabled=False`) |
| Sabelia shadow | `professor/shadow.py` | HTTP to a URL, not an LLM | – | – | – | off unless configured |
| `/ai/chat` (notebook TutorPanel) | `api/v1/ai.py:64` | TUTOR_CHAT stream | untiered → **gpt-4.1-mini** | 2,048 | tutor.* 122–195 / rag.answer 300 + **full client history** | yes (no feature tag) |
| Note actions (expand/explain/simplify) | `api/v1/notes_actions.py` | stream | untiered → mini | 2,048 | ~110 + note | yes |
| `/cards/generate` | `study/generation.py` | GENERATE_CARDS | untiered → mini | 4,096 | 321 + material | yes |
| `/questions/generate`, mistake drills | `study/questions.py`, `study/correction.py` | GENERATE_QUESTIONS | untiered → mini | 4,096 | 358 / 257 + material | yes |
| `/answers`, exam submit (grading) | `study/questions.py:369` | GRADE_OPEN_ANSWER | untiered → mini | 1,024 | 279 | yes |
| `/socratic`, Feynman | `study/socratic.py`, `study/feynman.py` | TUTOR_CHAT / GRADE (structured) | untiered → mini | 2,048 / 1,024 | 291 / 252 | yes |
| Ingestion embeddings | `ingestion/pipeline.py` (worker), 512-tok chunks, 15% overlap, batches of 32, Redis-cached | EMBED | text-embedding-3-small | – | – | **not recorded** (worker gateway has no `record_usage`) |
| Ingestion concept extraction | `knowledge/extraction.py` (5 chunks per call) | EXTRACT_CONCEPTS | worker gateway primary=openai, model None → mini | 4,096 | 422 + 5×512 ≈ 3,000 / ~400 | **not recorded, not metered** |
| Lecture extraction | `academic/extraction.py` | EXTRACT_CONCEPTS | – | 4,096 | 681 + schema 491 | no caller found |
| Public landing demo `/demo` | `api/v1/demo.py` | TUTOR_CHAT stream | default gateway + routing, model None → mini | 220 | 280 | **not recorded**; 6 per IP per day |
| OCR | `ingestion/parsers/documents.py` (pymupdf) | local | – | – | – | no model call |
| Recap, reviews, recall, quiz check | journeys/study routes | – | – | – | – | **no AI** (FSRS / server-graded) |
| Evals / judge `eval.judge` | `evals/professor.py` | GRADE | – | 3,000 | 467 | runs locally; no eval rows in prod |

### A3. One learner message → how many model calls (`/ai/professor`)

1. `check_ai_usage` plan gate (DB only). Guard is off.
2. **First message of a new subject:** `parse_goal` (economy) + `curriculum.build_plan` (economy). That is 2 calls.
3. `classify_route` (economy) runs only when the message is NEUTRAL by pattern, carries no UI event, and is longer than 12 chars or is a question. In prod this fired on about 35% of turns (24 route rows / about 69 teaching rows).
4. Move pre-work, sometimes. FLASHCARD runs 1 cards call. EXAM (every 4 concepts) runs assessment + cards and possibly compaction.
5. Retrieval and memory embeddings (1–2 embed calls, about 20–50 tokens each; ignorable).
6. **The teaching stream** (1 call; standard, premium for CORRECT).
7. After the stream, sometimes: auto-cards when a concept lands as "understood" (1 call), and compaction once the transcript passes 4,500 tokens or 24 turns (1 call + 1 embed).

**Typical turn: 1 teaching call + 0.35 route call. First turn of a subject: about 4 calls. Worst turn: about 6 calls** (route + exam + cards + teach + auto-cards + compact).

### A4. Context sent per Professor turn (`engine.prepare`, `context.py`, `budget.py`)

- The system prompt is about 2,160 tokens, identical across every turn and learner. It is marked `cache_control: ephemeral` on Anthropic streams only.
- Transcript: newest stored turns up to `NOEMA_PROFESSOR_TRANSCRIPT_BUDGET=3,500` tokens, sent verbatim. **The full history is not sent**; older turns are compacted into summaries.
- Then `<MATERIALS>` (up to 6,000 tokens when grounded) and a user directive: the move prompt (67–358), strategy, language, the PEDAGOGY reminder, `<COURSE>` plan, `<KNOWLEDGE_STATE>` (≤600), `<LEARNING_MEMORY>` (≤900) and `<ACTIVE_SESSION>`.
- **Observed prompt growth per turn in prod** (`tutor.chat` with session_id): turn 1 = 2,723, turn 2 = 3,024, turn 3 = 3,158, turn 4 = 3,595, turn 5 = 4,241, turn 6 = 7,354 tokens. Steady state by design is about 7–7.5k (2.2k system + 3.5k transcript + about 1.5k state). That gives an average of about 5k over a 10-turn lesson and about 6k over a 20-turn lesson. Grounded turns add up to 6k.
- Output: mini averaged 86–169 tokens per turn. Sonnet 5 averaged 950–1,000. Opus 5 (CORRECT) averaged 1,731. The cap is 1,900. **The gpt-4.1 output length has not been observed yet**; I assume 400 and show 1,000 as a sensitivity case.

### A5. Prompt caching

- **Anthropic stream (teaching):** the system block is marked. Sonnet 5's minimum is 1,024 tokens and Opus 5's is 512, so the 2.2k system prompt caches. This was observed: Opus rows had 9,795 cached of 25,246 input, and Sonnet 3,265 of 49,582 (few turns fell within 5 minutes of each other).
- **Anthropic structured calls** (route, parse_goal, curriculum, cards, assessment, compaction, grade): **no `cache_control`**. Haiku 4.5's minimum is 4,096 tokens anyway, so none of the economy prompts could cache.
- **OpenAI:** caching is automatic for a prefix of 1,024 tokens or more, and the parser reads `prompt_tokens_details.cached_tokens`. **0 cached tokens were observed on 59 OpenAI turns**, consistent with sparse QA traffic (gaps longer than the cache retention). This is unproven under real load.
- **The plan meter counts cached tokens at full weight.** Caching lowers COGS, but it does not lower the units a learner spends.

### A6. Token waste and risks found

1. **The system prompt is 40–80% of every turn's input.** `teaching.principles` alone is 1,442 tokens. It caches on Sonnet and Opus, has not been seen caching on OpenAI, and counts in full against the learner's units.
2. **CORRECT is routed to the premium tier.** On Anthropic that is Opus 5 at about 6–7¢ per turn, about 4x a Sonnet turn, and 13 of about 69 prod turns were CORRECT. On OpenAI, premium is the same as standard (gpt-4.1), so there is no premium today.
3. **`/ai/chat` sends whatever history the client posts**: up to 100 messages × 32,000 chars ≈ 800k tokens, with no server-side trim. On mini that is about 32¢ per call. If it ever lands on Anthropic's untiered default (Sonnet 4.5) it is about $2.40 per call. The plan gate checks only *before* the call, so one call can overshoot the monthly allowance by orders of magnitude. The daily budget (1M tokens per rolling 24h) is also checked only before the call.
4. **Output length differs about 6x by model** (mini about 150, Sonnet about 1,000 tokens). Output is the expensive side (5x input on Anthropic, 4x on OpenAI), and the 1,900 cap allows long replies.
5. Structured calls inherit the 4,096 cap (curriculum, cards, assessment, compaction, extraction). This is a reasonable ceiling but it is not tuned.
6. `gateway.embed` on the request gateway always tries the primary (Anthropic, which has no embeddings) first and then falls through to OpenAI. That costs latency, not money. 17 failed embed rows (2026-08-31 → 09-23) are from before an OpenAI key existed.
7. The economy route prompt (636 tokens) is about 40x the size of its one-enum output. Its cost is negligible on mini.

### A7. Plans, quotas, units (what the user sees)

- `plan_configs` in prod (migration 0014):

| plan | price | monthly_ai_units | tokens/month |
|---|---|---|---|
| free | R$0 | 100 | 100,000 |
| student | R$29,90 | 300 | 300,000 |
| pro | R$59,90 | 600 | 600,000 |
| max | R$99,90 | 1,000 | 1,000,000 |

- `entitlements.TOKENS_PER_UNIT = 1,000`. Usage is the sum of `prompt_tokens + completion_tokens` (cached included) for the calendar month (UTC). It counts every recorded row, failures included (failures have 0 tokens).
- **Enforcement.** `deps.enforce_plan` raises **402 `plan-limit-reached`** on any `GatewayDep` route. `/ai/professor` checks the plan itself and sends an SSE `blocked` event, plus a `warning` event when 10% or less remains. There are also these limits:
  - **30 AI calls per minute per learner** (`NOEMA_AI_CALLS_PER_MINUTE`, Redis, fails open).
  - **Daily ceiling of 1,000,000 tokens per rolling 24h**, with 15% reserved for interactive use; generation is paused below the reserve (413 `quota-exceeded`).
  - Demo: 6 calls per IP per day, 220 output tokens.
  - Input caps: chat message ≤32,000 chars, ≤100 messages; parse_goal truncates to 2,000 chars.
- **Pricing page copy** (`apps/web/src/app/pricing/page.tsx`, plans read from `GET /billing/plans`; currency BRL, no decimals):
  - pt: *"Comece grátis. Suba quando o NOEMA virar parte de como você estuda."* · "`N` unidades de IA por mês" · **"Uma unidade cobre cerca de uma troca curta com o Mino."**
  - en: *"Start free. Upgrade when NOEMA becomes part of how you study."* · "`N` AI units per month" · **"One unit covers roughly one short exchange with Mino."**
  - FAQ (pt): *"Quanto custa? — Começar é grátis, sem cartão. Os planos pagos aumentam o quanto de IA você pode usar por mês."*
  - Lesson UI: limitBlockedTitle *"Você usou o tempo do Noema deste mês"*; limitWarning **"Resta N resposta(s) do Noema neste mês"**. This treats a unit as one reply.
  - **Both claims are inaccurate by about 5x.** One reply is about 3–8 units (2.7k tokens on the first turn, about 7.5k at steady state), plus about 0.27 units for routing and about 2.2 units for a curriculum.
- Stripe prices are configured (`NOEMA_STRIPE_PRICE_STUDENT/PRO/MAX` set). No user is on a paid plan yet.

### A8. How cost is recorded

- `ai_usage` columns: `owner_id, provider, model, task, prompt_tokens, completion_tokens, cached_tokens, cost_cents (float), succeeded, created_at, feature, session_id, request_id, failed_over_from`.
- **PR #273 (`cost_micro_cents` BigInteger, migration 0038) is still OPEN, not merged.** Prod is at 0037.
- `UsageWriter` → `PricingService.cost_cents` looks up the tier row by (provider, model), then `_LIST_PRICES` (gpt-4.1, 4.1-mini, 4.1-nano), and otherwise records 0. The known causes of a 0 or understated cost are:
  - (a) **text-embedding-3-small is not priced**.
  - (b) **Anthropic's untiered default `claude-sonnet-4-5` is not priced** ($3/$15).
  - (c) Before #270 (2026-10-07), every structured call was recorded with **0 tokens** and the *requested* model (`claude-haiku…` on rows OpenAI served), and OpenAI stream rows had model `unknown`. All of these are 0¢ in prod. The current main fixes (c).
  - (d) Anthropic `cache_creation_input_tokens` are billed at 1.25x but priced at 1.0x.
  - (e) Worker ingestion (embeddings + extraction) and `/demo` write no rows.
  - (f) Professor structured calls (route, parse_goal, curriculum, cards, compact) carry no `session_id`. 64 of 131 professor rows have none, so per-lesson cost undercounts side work.
- Readers:
  - `launch_dashboard` sums `cost_cents` per day.
  - `/admin/ops` (`services/ops.provider_split`) sums per provider. It warns: "AI cost counts only models priced in the tier table; others show 0".
  - `professor_economy` shows cost and cache rate per feature, per lesson and per learner.
  - `economics.py` projects margin with Stripe fees (3.99% + R$0.39, Billing 0.7%).

---

## Part B — Production data (aggregate)

**Caveats.** There are 23 accounts (6 created in the last 30 days), all on the free plan. 21 accounts ever called AI, 7 in the last 30 days, **0 in the last 7 days**. The last AI call was 2026-10-07 19:35 UTC. The 2026-10-07/08 eval runs were local and are not in this DB. The traffic is dominated by internal and QA accounts, and the Anthropic credit outages show up as failures (Sep 21–25). **No statistic below is a market estimate.**

### B1. ai_usage by feature/provider/model (all-time, 240 rows)

| feature | provider / model (as recorded) | calls | failed | avg in | p50 in | p95 in | avg out | p95 out | cached | recorded ¢ |
|---|---|---|---|---|---|---|---|---|---|---|
| (none) /ai/chat | anthropic claude-sonnet-5 | 36 | 0 | 892 | 477 | 3,218 | 789 | 1,467 | 0 | 34.82 |
| (none) | mock | 30+9 | 0 | 153 | 130 | 352 | 21 | 54 | 0 | 0 |
| professor.teach | openai `unknown` (= 4.1-mini) | 24 | 0 | 2,658 | 2,523 | 3,099 | 146 | 219 | 0 | **0** |
| professor.answer | openai `unknown` | 13 | 0 | 2,936 | 2,935 | 3,248 | 86 | 152 | 0 | **0** |
| professor.correct | openai `unknown` | 9 | 0 | 2,975 | 2,879 | 3,353 | 169 | 227 | 0 | **0** |
| professor.quiz/advance/example/question/summarize/guide | openai `unknown` | 13 | 0 | 2.7–3.2k | | | 75–168 | | 0 | **0** |
| professor.correct | anthropic claude-opus-5 | 4 | 0 | 5,895 | 5,860 | 7,228 | 1,731 | 1,900 | 9,795 | 24.69 |
| professor.teach / advance | anthropic claude-sonnet-5 | 2+2 | 0 | 3,635 / 5,095 | | | 948 / 1,003 | | 0 / 3,265 | 6.81 |
| (none) chat | anthropic claude-opus-5 | 1 | 0 | 1,666 | | | 1,055 | | 0 | 3.47 |
| professor.route | openai (recorded "claude-haiku") | 23 | 0 | **0** | | | **0** | | | 0 |
| professor.parse_goal | openai / anthropic | 18 / 2 | 0 | **0** | | | **0** | | | 0 |
| professor.curriculum | openai / anthropic | 15 / 2 | 0 | **0** | | | **0** | | | 0 |
| professor.flashcards | anthropic / openai | 2 / 1 | 0 | **0** | | | **0** | | | 0 |
| (none) embed | anthropic (fails: no embeddings) | 17 | 17 | 0 | | | | | | 0 |
| (none) classify/summarize | anthropic haiku (credit outage) | 14 | 14 | 0 | | | | | | 0 |
| (none) embed | openai text-embedding-3-small | 1 | 0 | 27 | | | | | | 0 |

- Failures: 31 of 240 (13%), all on Anthropic (embeds without embeddings, plus the credit outage). Failovers (`failed_over_from`): 0 rows (the column is new, from 0037).
- By month: Aug: 14 users, 42 calls (mostly mock). Sep: 6 users, 172 calls, 207k in / 47k out. Oct: 4 users, 26 calls, 35k in / 1.4k out.
- Last 30 days: 129 calls, 7 users, 167,394 in / 8,087 out / 0 cached, **recorded 0.00¢**.

### B2. Recomputed cost

| bucket | recorded | recomputed (list price) |
|---|---|---|
| Anthropic rows (tier-priced) | 69.78¢ | 69.78¢ (cache writes would add <1¢) |
| OpenAI teaching turns, 59 rows, 167,367 in / 8,087 out | 0¢ | **7.99¢** at gpt-4.1-mini (would be 39.9¢ at today's gpt-4.1) |
| OpenAI/Anthropic structured, 64 rows, 0 tokens recorded | 0¢ | ≈ **5.4¢** estimated from prompt sizes (24 route × 0.032¢ + 20 parse × 0.033¢ + 17 curriculum × 0.21¢ + 3 cards × 0.12¢) |
| **All-time real AI spend** | 69.8¢ | **≈ 83¢ (~$0.83)** |
| **Last 30 days** | 0¢ | **≈ 13¢** |

### B3. Distributions

- **Per user per day** (30 user-days with calls). Calls: p50 4, p90 14, p95 18, p99 40, max 48. Tokens: p50 3.2k, p90 27.4k, p95 35.3k, p99 61.4k, max 71.1k.
- **Per user per month** (22 user-months). Calls: p50 5.5, p90 20.6, p95 28.6, p99 53.5, max 60. Tokens: p50 0.9k, p90 51.4k, p95 54.8k, p99 81.3k, **max 88.4k (88 units, so no account has ever hit the 100-unit Free limit)**. Average 11.4 calls per account all-time, max 65. Only 1 account has made 50 or more calls.
- **Teaching sessions:** 39 (9 learners), 22 journeys. Learner turns per session: **p50 2, p90 4.2, p95 5.1, max 6, mean 2.5**.
- **AI rows joined by session_id:** 23 sessions. Calls per session: mean 2.9, p50 3, p90 4.8. Input per session: mean 9,061, p50 8,144, p90 13,848. Output per session: mean 822. On the OpenAI-only subset (21 sessions): 2.8 teaching calls, 7,970 in / 385 out per session.
- Sessions per active learner per week: median 1, mean 3.25, max 13 (12 learner-weeks).
- Focus (Modo TDAH): 3 sessions by 3 users. There are no focus-specific AI rows; focus runs normal Professor turns.
- Ingestion: 8 sources, 12 chunks, 264 tokens. Cards: 19. Assessments: 0. Memory summaries: 0, so **compaction has never run in prod**. Safety events: 0.

---

## Part C — Unit costs (formulas)

Notation: `cost = in_fresh × p_in + in_cached × p_cached + out × p_out` (USD per token = $/MTok ÷ 1e6). Unless stated otherwise, the "typical turn" is the 10-turn-lesson average: **5,000 input tokens (2,200 of them the cacheable system prompt) and 400 output tokens on OpenAI or 1,000 on Anthropic** (the observed Sonnet behaviour). "Cached" assumes the 2.2k system prefix hits. Route classifier: 765 in / 15 out, firing on 35% of turns.

### C1. Per Professor turn

| model (tier) | uncached | with system cached | units used |
|---|---|---|---|
| gpt-4.1 (standard/premium today) | 5000×2 + 400×8 = **1.32¢** | 2800×2 + 2200×0.5 + 400×8 = **0.99¢** | 5.4 |
| gpt-4.1, 1,000-token reply | 1.80¢ | 1.47¢ | 6.0 |
| gpt-4.1-mini (economy, untiered) | 5000×0.4 + 400×1.6 = 0.26¢ | 0.20¢ | 5.4 |
| Sonnet 5 (standard) | 5000×2 + 1000×10 = **2.00¢** | 2800×2 + 2200×0.2 + 10000 = **1.60¢** (+0.11¢ on a cache-write turn) | 6.0 |
| Opus 5 (premium = CORRECT) | 5900×5 + 1700×25 = **7.20¢** | 3700×5 + 2200×0.5 + 42500 = **6.21¢** (observed 6.17¢ per call) | 7.6 |
| Haiku 4.5 (economy moves) | 5000×1 + 400×5 = 0.70¢ | (no cache: min 4,096) | 5.4 |
| route call: mini / Haiku | 765×0.4 + 15×1.6 = 0.032¢ / 765×1 + 15×5 = 0.084¢ | – | 0.78 |

- **Blended turn today (OpenAI):** 0.99–1.32¢ + 0.35 × 0.032¢ ≈ **1.0–1.3¢** (≈1.5–1.8¢ if gpt-4.1 writes Sonnet-length replies).
- **Blended turn on Anthropic tiers:** using the prod move mix (≈13% CORRECT), 0.87 × 1.6–2.0¢ + 0.13 × 6.2–7.2¢ + 0.35 × 0.084¢ ≈ **2.2–2.7¢**.
- **Units per turn:** ≈ 5.4 + 0.27 (route) ≈ **5.7 units**. That ranges from about 3 (turn 1) to about 8 (steady state).

### C2. Other operations

| operation | tokens (in / out) | gpt-4.1-mini (today) | Haiku 4.5 |
|---|---|---|---|
| Goal parse | 350 / 120 | 0.033¢ | 0.095¢ |
| Curriculum generation | 550 / 1,200 | 0.21¢ | 0.66¢ |
| → **new subject total** (parse + curriculum) | | **≈0.25¢ (2.2 units)** | **≈0.75¢** |
| Flashcards (per batch of 3–4) | 1,800 / 300 | 0.12¢ | 0.33¢ |
| Checkpoint quiz (assessment) | 2,400 / 1,100 | 0.27¢ | 0.79¢ |
| → checkpoint total (+ cards, ± compaction) | | ≈0.4–0.7¢ | ≈1.1–1.9¢ |
| Open-answer grade (per answer) | 700 / 120 | 0.047¢ | 0.13¢ |
| Memory compaction (+1 embed) | 5,500 / 450 | 0.29¢ | 0.78¢ |
| `/questions/generate` | ~2,000 / 1,500 | 0.32¢ | 0.95¢ |
| In-lesson quiz block / quiz check | (inside the teaching turn) | 0 extra | 0 extra |
| Review session (FSRS), recap, recall | none | **$0** | $0 |
| Landing demo (per call, not recorded) | 350 / 220 | 0.05¢ | – |

### C3. Per learning session

Formula: `session = N × turn + new_subject? + checkpoints × 0.4–0.7¢ + compactions × 0.29¢ + cards`.

| session | today (gpt-4.1 / mini) | Anthropic tiers |
|---|---|---|
| **Observed prod median: 2 turns** (2.7k–3.0k in each) | 2 × ~0.7¢ + route ≈ **1.5¢** (+0.25¢ if new subject) | ≈ 2 × 1.6¢ ≈ **3.5¢** |
| 10-turn lesson (1 checkpoint, 1 cards batch) | 10 × 1.0–1.3¢ + 0.5¢ ≈ **11–14¢** (≈57 units) | 10 × 2.2–2.7¢ + 1.4¢ ≈ **23–28¢** |
| 20-turn lesson (avg 6k in, 1 compaction, 2 checkpoints) | ≈ **24–31¢** (≈125 units) | ≈ **50–60¢** |

### C4. Focus session (Modo TDAH)

A focus turn adds 323 system tokens and caps output at 594/706/866 (levels 1–3); assume about 250 output tokens and a check after every move.

- gpt-4.1: 5,300×2 + 250×8 = **1.26¢ uncached, 0.89¢ cached**.
- Sonnet: 5,300×2 + 400×10 = **1.46¢ uncached, about 1.1¢ cached**.
- **A 10-minute sitting of about 8 turns costs about 8–10¢ today and about 9–12¢ on Sonnet** (more if a wrong answer triggers CORRECT on Opus).

### C5. Document ingestion (worker; not recorded, not metered)

Per page: about 550 tokens of text → about 1.15 chunks of 512 tokens with 15% overlap.

- Embeddings: 630 tok × $0.02/MTok = **0.0013¢ per page**.
- Concept extraction: (422 + 5×512 ≈ 3,000 in, ~400 out) per 5 chunks on mini = 0.18¢ per batch → **≈0.04¢ per page**.
- **A 100-page PDF costs about 4.3¢** (≈4.2¢ extraction + 0.13¢ embeddings). It would cost about 0.13¢ if extraction were off. The Redis cache (30 days) makes re-ingestion free for embeddings only.

### C6. Per user per month and plan exposure

| | today (gpt-4.1) | Anthropic tiers |
|---|---|---|
| Cost per unit (1,000 tokens) | 1.0–1.3¢ / 5.7 units ≈ **$0.0018–0.0023** | 2.2–2.7¢ / 6.3 units ≈ **$0.0035–0.0043** (migration 0014 assumed $0.004) |
| Free, 100 units exhausted | $0.18–0.23 (R$0.9–1.2) | $0.35–0.43 (R$1.8–2.2) |
| Student, 300 units (R$29,90) | $0.69 = R$3.6 (12%) | $1.29 = R$6.7 (22%) |
| Pro, 600 units (R$59,90) | $1.38 = R$7.2 (12%) | $2.58 = R$13.4 (22%) |
| Max, 1,000 units (R$99,90) | $2.30 = R$12.0 (12%) | $4.30 = R$22.4 (22%) |
| What the units buy (≈5.7 units per turn) | Free ≈17 turns, Student ≈53, Pro ≈105, Max ≈175 per month | same quota, fewer turns on Anthropic (≈6.3 units per turn: 16 / 48 / 95 / 159) |

- Observed real usage per user-month is p90 = 51 units and max = 88 units. No QA account reached the Free cap.
- At today's routing, a learner who does one 10-turn lesson per weekday (about 22 per month) would use about 1,250 units, which is **more than Max**. The AI COGS for that learner would be about $2.6–3.1 (R$14–16) on gpt-4.1, or about $5.5 (R$29) on Anthropic.

### C7. Recommendations (for the pricing work; not implemented)

1. **Recording first.** Merge #273 (micro-cents). Price `text-embedding-3-small` and `claude-sonnet-4-5` in `_LIST_PRICES`. Price cache writes at 1.25x. Pass `session_id` to the structured Professor calls. Record worker and demo usage. Until then, `/admin/ops`, the launch dashboard and `professor_economy` under-report OpenAI work.
2. **Fix the unit copy** in pricing and the lesson UI ("≈ one short exchange" and "Resta N respostas"). One reply is about 4–8 units. Options: make 1 unit ≈ 1 reply (e.g. 6,000 tokens per unit, or meter by turns), or keep tokens and say "≈ N lessons".
3. **Cap `/ai/chat` history server-side**, for example with the same `fit_transcript` 3.5k budget. Consider a reservation or post-call clamp, so a single call cannot overrun the plan or the daily ceiling.
4. **Reconsider CORRECT → Opus 5**, which costs about 4x a standard turn on Anthropic. Sonnet 5 at standard, or Opus only for repeated errors, would remove about 35% of Anthropic COGS per lesson.
5. **Measure gpt-4.1 reply length and OpenAI cache hits** on real traffic before fixing prices. Those two unknowns swing the per-turn cost by about ±40%.
6. Exclude cached tokens from units (or weight them at 0.1), so the 2.2k system prompt stops consuming about 40% of a learner's allowance.

---

### Method notes

- Queries are in the scratchpad (`sql/*.sql`, `runner.py`). They ran through `railway ssh` into `api`, with asyncpg in `transaction(readonly=True)` (`transaction_read_only = on` confirmed). The postgres service exposes no `DATABASE_PUBLIC_URL` and no TCP proxy; none was created.
- Token estimates for prompts are chars/4 (the codebase's own `budget.estimate`). Prompts are partly in Portuguese and include frontmatter, so real tokenizer counts may differ by ±20%.
- The output sizes for curriculum, cards, assessment and compaction are estimates (prod recorded 0 tokens for all structured calls before #270). Re-measure once new rows exist.
