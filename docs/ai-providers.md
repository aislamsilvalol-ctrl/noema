# NOEMA — AI Provider Layer

No feature code ever imports an SDK. Everything goes through one interface and one gateway.

## 1. Interface

```python
class AIProvider(Protocol):
    name: str
    capabilities: Capabilities

    async def chat(self, req: ChatRequest) -> ChatResponse: ...
    async def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]: ...
    async def embed(self, req: EmbedRequest) -> EmbedResponse: ...
    async def structured(self, req: StructuredRequest[T]) -> T: ...
    async def health(self) -> HealthReport: ...
```

`Capabilities` is data, not flags on the caller's side:

```python
@dataclass(frozen=True, slots=True)
class Capabilities:
    chat: bool
    streaming: bool
    embeddings: bool
    structured_output: Literal["native", "tool_call", "prompted", "none"]
    vision: bool
    max_context: int
    max_output: int
```

Callers negotiate rather than assume. `structured()` uses native JSON-schema output where
available, falls back to a tool-call shim, then to prompted JSON with retry-on-parse-failure
— and a provider that lands on `"prompted"` gets validated twice, because that path is where
malformed flashcards come from.

## 2. Implementations

| provider | chat | embed | structured | notes |
|---|---|---|---|---|
| `AnthropicProvider` | ✅ | — | native | pairs with any embedding provider |
| `OpenAIProvider` | ✅ | ✅ | native | |
| `OllamaProvider` | ✅ | ✅ | prompted | the local-mode default |
| `MockProvider` | ✅ | ✅ | native | deterministic, no network — what CI and local dev run against |

Gemini, OpenRouter and a sentence-transformers local-embedding provider are planned but not
yet written — `LOCAL_PROVIDERS` in `noema/providers/registry.py` already reserves the name
`local-embeddings` for the last of those. Until one of these lands, adding it is exactly the
"one file plus a registry entry" story below, worked example and all.

Adding a provider means one file plus a registry entry — the contribution path we most want
to be obvious to a newcomer, whether the file lives in this repo or in a separate installed
package. `CONTRIBUTING.md` uses it as the worked example; `docs/plugins.md` covers the latter.

## 3. Task routing

Different jobs want different models. Users configure per *task class*, not per call site:

| task | default (cloud) | default (local) |
|---|---|---|
| `tutor.chat` | strongest available | best local chat model |
| `extract.concepts` | mid-tier, structured output required | local + strict validation |
| `generate.cards` | mid-tier | local |
| `grade.open_answer` | strongest — grading errors are expensive | local, discounted in mastery |
| `embed` | dedicated embedding model | local embeddings |
| `summarize` | small/fast | local |

Resolution order: notebook override → user setting → workspace default → deployment default.

## 4. Gateway

`providers/gateway.py` wraps every call with:

- **Timeouts** — per task class, not global.
- **Retries** — exponential backoff with jitter on 429/5xx/timeouts only. Never retry a
  4xx that indicates a bad request; that is a bug to surface, not to paper over.
- **Fallback chain** — if the primary provider fails health checks, fall through to the next
  configured one and *tell the user in the UI* which model answered.
- **Token accounting** — every call writes prompt/completion tokens and estimated cost to
  `ai_usage`, per user and per task class. BYOK users are spending their own money and
  deserve to see exactly where.
- **Budget guard** — a per-user ceiling over a rolling 24 hours
  (`NOEMA_AI_DAILY_TOKEN_BUDGET`), enforced in the gateway before any provider call. On
  breach it degrades rather than failing: card and question generation, concept extraction
  and embedding stop once the remaining budget reaches the interactive reserve
  (`NOEMA_AI_INTERACTIVE_RESERVE`, 15% by default), while the tutor, grading and
  summarisation keep working until the budget is genuinely gone. A runaway generation loop
  should cost you tomorrow's card drafts, not the ability to ask about the chapter you are
  reading now.
- **Redaction** — API keys never enter logs, traces, or exception messages. Enforced by a
  logging filter *and* a test that asserts a known key string never appears in captured
  output.

### Interleaving providers (`NOEMA_AI_ROUTING`)

By default the gateway asks `NOEMA_DEFAULT_PROVIDER` first and every other provider the
deployment (or the learner) has a key for only when it fails. To use several providers at
the same time, give them weights:

```
NOEMA_AI_ROUTING=anthropic:50,openai:50
```

- **First choice by weight.** Each chat, stream and structured call picks its first
  provider by weight among the configured ones whose circuit is not open (half-open counts,
  so a recovering provider gets its probe). The others follow in weight order as the
  fallback chain, and the usual retry / circuit / failover rules apply to them.
- **Sticky per conversation.** The pick is a weighted rendezvous hash of a key, so the same
  key always lands on the same provider and Mino keeps one voice across a lesson. The key
  is the call's `routing_key`, else its `metadata["session_id"]`, else the gateway's key
  (the learner's id). The Professor keys every call of a turn by the teaching session
  (`ProfessorEngine.prepare`), so Modo TDAH sessions, which run on the same engine, are
  sticky too. A call with no key at all (the public demo) is a weighted coin toss.
- **Circuits move keys only while open.** When a provider's circuit opens, only the keys it
  was serving move to the next provider; when it closes they move back, and nobody else's
  move at all.
- **Embeddings are never interleaved**: vectors from two models live in two spaces. They
  keep the chain's own order, exactly as before.
- **Draining a provider**: `anthropic:0,openai:100` sends every call to OpenAI first and
  keeps Anthropic as a fallback only. A provider the setting does not name behaves like
  weight 0. To take a provider out entirely, remove its key.
- **Empty** (the default) means no interleaving: the behaviour above this section.
- A malformed value stops the boot; in production a provider with a non-zero weight and no
  key is a boot error too.

**Same tier, each provider's own model.** A Professor call names the model of its cost tier
(`model_tier_config`: economy / standard / premium, all Anthropic models today). When the
call lands on another provider it runs on that provider's model for the same tier
(`TIER_MODELS` in `noema/services/professor.py`):

| tier | used for | anthropic | openai |
|---|---|---|---|
| economy | intent / route classifier, goal parsing, curriculum, memory compaction, flashcard / exam / motivate moves | `claude-haiku-4-5-20251001` | `gpt-4.1-mini` |
| standard | most teaching moves (teach, question, example, quiz, summarize…) | `claude-sonnet-5` | `gpt-4.1` |
| premium | correcting a misconception, "go deeper" | `claude-opus-5` | `gpt-4.1` |

The tier row's own provider always uses the row's model. OpenAI's premium is `gpt-4.1`, not
a reasoning model, because those refuse the `temperature` the gateway sends. Override per
deployment with `NOEMA_TIER_MODELS=openai.premium=gpt-4.1,openai.economy=gpt-4.1-mini`.
Calls outside the Professor (study tools, notes actions, `/ai/chat`) name no model and run
on each provider's default (`claude-sonnet-4-5`, `gpt-4.1-mini`).

Both providers receive the same prompts: nothing under `noema/prompts` is written for one
vendor. The wire differs only where the APIs do: Anthropic gets the system prompt as a
cacheable top-level field and no `temperature`; OpenAI gets it as a system message, the
request `temperature`, and strict JSON schema for structured calls (`strict_schema`).

**Out of credit is an outage, not a bad request.** Anthropic's 400 "credit balance is too
low" and OpenAI's 429 `insufficient_quota` (also `billing_hard_limit_reached`,
`billing_not_active`, or any 402) raise `CreditExhausted`: not retried, the provider's
circuit opens on the first one for `NOEMA_AI_BILLING_COOLDOWN_SECONDS` (600 by default),
and the call fails over at once. A learner's own (BYOK) key out of credit fails over the
same way but does not open the circuit for everyone else.

**Observability.** Every `ai_usage` row records the provider that served the call and, in
`failed_over_from`, the provider it was meant for when that was a different one.
`GET /admin/ops` splits the last 24 h per provider (`ai_providers`: calls, failovers in and
out, errors, cost).

## 5. BYOK and key storage

```
plaintext key ──AES-256-GCM──► ciphertext + nonce ──► provider_credentials
                    ▲
              data key, wrapped by NOEMA_MASTER_KEY (env / KMS)
```

- Encrypt with `cryptography`'s AESGCM; store `key_version` for rotation.
- Decryption happens only inside the gateway, never in a router.
- **No endpoint returns a key.** The API exposes `{provider, label, last4, last_used_at}`.
  There is no code path that can serialise the plaintext, and a test asserts the response
  schema has no field capable of carrying it.
- Keys are validated on save with a minimal live call, and `last_verified_at` is recorded so
  a revoked key surfaces as a clear message instead of a mystery failure mid-session.

## 6. Prompt architecture

Prompts are **versioned files**, not string literals scattered through the codebase:

```
providers/prompts/
├── tutor.explain.v1.md
├── tutor.socratic.v1.md
├── tutor.examiner.v1.md
├── feynman.evaluate.v1.md
├── extract.concepts.v1.md
├── generate.cards.v1.md
├── generate.questions.v1.md
└── grade.open.v1.md
```

Each has front-matter declaring its output schema, its task class, and its eval fixture set.
Changing a prompt is a reviewable diff with a test run — which is the only way prompt work
stays maintainable across contributors.

### Untrusted content

Retrieved document text is untrusted. It is passed inside an explicitly delimited data block
with instructions that content within it is material to reason about, never instructions to
follow. During RAG answering the model is given **no tools**, so a successful injection has
nothing to reach for. Structured outputs are schema-validated before anything is persisted.

## 7. Evaluation harness

`apps/api/tests/evals/` holds fixture documents with hand-labelled expected extractions.
CI will run them against a deterministic mock provider on every PR once the harness lands in Phase 2; a nightly optional job runs
them against real providers when keys are configured. Prompt changes that regress extraction
F1 or citation accuracy fail the check.

Without this, prompt edits are vibes. With it, they are engineering.
