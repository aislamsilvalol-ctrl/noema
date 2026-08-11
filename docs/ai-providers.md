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
| `GeminiProvider` | ✅ | ✅ | native | |
| `OpenRouterProvider` | ✅ | — | varies | capabilities resolved per model at runtime |
| `OllamaProvider` | ✅ | ✅ | prompted | the local-mode default |
| `LocalEmbeddingProvider` | — | ✅ | — | sentence-transformers in-process |

Adding a provider means one file plus a registry entry — the contribution path we most want
to be obvious to a newcomer. `CONTRIBUTING.md` uses it as the worked example.

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
- **Budget guard** — configurable per-user daily ceiling; on breach, degrade rather than
  fail (skip auto-generation, keep the tutor working).
- **Redaction** — API keys never enter logs, traces, or exception messages. Enforced by a
  logging filter *and* a test that asserts a known key string never appears in captured
  output.

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
CI runs them against a deterministic mock provider on every PR; a nightly optional job runs
them against real providers when keys are configured. Prompt changes that regress extraction
F1 or citation accuracy fail the check.

Without this, prompt edits are vibes. With it, they are engineering.
