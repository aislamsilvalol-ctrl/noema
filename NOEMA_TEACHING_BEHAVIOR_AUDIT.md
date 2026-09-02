# NOEMA Teaching Behavior Audit — "Why does Noema require a notebook?"

Read-only investigation. No code changed. Scope: trace, at file:line granularity,
every mechanism that could make Noema behave as if it needs a notebook/material
before it can teach, for the specific scenario in the brief — a brand-new account,
zero notebooks, that says "Quero aprender psicologia."

Desired behavior (per the brief): Noema should start teaching immediately from
general knowledge, with materials as optional enhancement, never a prerequisite.

## 1. Backend API contract — `notebook_id` optionality

**Verdict: real, and it already works.** This is NOT the cause.

- `ChatIn.notebook_id: uuid.UUID | None = None` — `apps/api/noema/api/v1/schemas.py:191`.
  Genuinely optional; `None` is the schema default.
- `chat()` (`apps/api/noema/api/v1/ai.py:50-163`): when `notebook_id` is `None`, the
  ownership lookup is skipped (`ai.py:64-65`), and:
  ```
  grounded = payload.notebook_id is not None and payload.grounded   # ai.py:69
  ```
  `grounded` is forced `False` regardless of `payload.grounded`'s value (which
  defaults to `True`, `schemas.py:196`) whenever there's no notebook.
- `_assemble(mode, grounded, results)` (`ai.py:599-613`): with `grounded=False` it
  takes the first branch and returns `tutor(mode)` — the plain, ungrounded prompt —
  with no context block. No RAG code path is touched.
- `professor_chat()` (`ai.py:166-263`) is identical: ownership check skipped when
  `notebook_id is None` (`ai.py:184-185`); `needs_notebook_material()` only
  intercepts three intents (see §3); EXPLAIN/DEEPEN/SUMMARIZE fall through to
  `_dispatch_stream` (`ai.py:381-490`), which computes `grounded` the same way
  (`ai.py:398`) and reaches `tutor(mode)` the same way. Professor-memory injection
  is itself gated on `payload.notebook_id is not None` (`ai.py:424-438`), so it is
  cleanly skipped, not an error path.
- **Conclusion:** a request with `notebook_id: null` and intent EXPLAIN produces a
  real, ungrounded, general-knowledge streaming reply today. The backend
  architecture does not require a notebook to answer. Nothing here rejects or
  redirects a notebook-less EXPLAIN turn.

## 2. Prompt language — CONFIRMED real bug

The literal phrase the brief flagged is not isolated to a UI copy string — it is
inside the system prompt sent to the model on the ungrounded path itself:

- `apps/api/noema/prompts/tutor.explain.v1.md:6` — *"You are NOEMA, a tutor
  working inside the learner's own notebook."* This is `tutor("explain")`, which
  is exactly what `_assemble()` returns for a notebook-less EXPLAIN/DEEPEN turn
  (§1). EXPLAIN is also the classifier's fail-safe default
  (`professor.py:101-124`) and the intent used whenever `needs_notebook_material`
  redirects (§3). It is the single most-executed conversational prompt in the
  system, and it asserts a notebook context that, in the zero-notebook scenario,
  does not exist.
- `apps/api/noema/prompts/tutor.summarize.v1.md:6` — the same sentence, verbatim,
  for the SUMMARIZE intent's ungrounded path.
- Full sweep of every prompt file (`grep -rniE "notebook|material" *.md`) found
  no other conversational prompt using this framing: `tutor.socratic.v1.md`,
  `tutor.feynman.v1.md`, `tutor.examiner.v1.md` have none of it.
  `tutor.study_partner.v1.md:6` says "this material alongside the learner" — a
  softer echo of the same assumption, present regardless of grounding.
- `rag.answer.v1.md` / `rag.no_context.v1.md` never fire on the notebook-less
  path — see §6.
- **Effect:** on a brand-new account's very first "explain X to me" or "resume
  isso," the model is told outright that it works "inside the learner's own
  notebook," with no notebook in front of it. This plausibly explains the model
  spontaneously asking "which notebook/material is this about?" even though
  nothing downstream required one.

## 3. Intent classification and dispatch requirements

**Verdict: NOT a bug.** `needs_notebook_material()` behaves exactly as intended.

- `NEEDS_NOTEBOOK = frozenset({QUIZ_ME, CREATE_FLASHCARD, CREATE_EXAM})` —
  `apps/api/noema/services/professor.py:231-233`.
- `needs_notebook_material(intent, notebook_id)` (`professor.py:236-244`) is a
  pure boolean check: `intent in NEEDS_NOTEBOOK and notebook_id is None`. It
  returns a bool only — it emits no user-facing text of its own.
- The one caller (`ai.py:221-225`) reassigns `intent = Intent.EXPLAIN` silently
  when it's `True`, then proceeds through the normal EXPLAIN stream. There is no
  "create a notebook first" message anywhere in this path — the redirect is a
  clean, silent fallback to conversation, matching the code comment's own
  reasoning ("Fall back to the conversation itself rather than fail a message
  that was never wrong, just under-specified").
- `professor_chat` can be, and regularly is, called with `notebook_id=None` — the
  ownership-check guard (`ai.py:184`) is conditional on it being non-`None`, not a
  requirement that it be set. Nothing upstream (FastAPI validation, entitlements
  check at `ai.py:187`) rejects a null `notebook_id`.
- **The only residual effect** is that the redirected EXPLAIN turn still hits the
  §2 prompt bug — so a user who says "quero fazer uma prova" with no notebook is
  silently downgraded to conversation, and that conversation opens with "working
  inside the learner's own notebook."

## 4. Frontend routing/navigation — CONFIRMED root cause

There is no notebook-independent entry point to any chat/tutor surface anywhere
in the app.

- Full nav, `apps/web/src/components/Shell.tsx:39-50`: `/today`, `/library`,
  `/goals`, `/review`, `/explain`, `/socratic`, `/mistakes`, `/graph`,
  `/progress`, `/settings`. No `/chat`, `/ask`, or equivalent.
- The only two call sites that hit `POST /ai/professor` or `POST /ai/chat` are:
  - `apps/web/src/app/notebooks/[id]/professor/page.tsx` — a route that only
    exists nested under `/notebooks/[id]`, and always sends
    `notebook_id: notebookId` from the URL param (`professor/page.tsx:106`);
    never omits it, never sends `grounded: false`.
  - `apps/web/src/components/TutorPanel.tsx:51` — the notebook page's side
    rail, same pattern: `{ notebook_id: notebookId, mode, messages: history }`,
    always a real notebook id.
  - Confirmed by `grep -rn "professor" app components` — the string appears
    only inside `notebooks/[id]/...` files.
  - The link into the professor chat is itself only reachable from inside an
    open notebook: `apps/web/src/app/notebooks/[id]/page.tsx:158`,
    `href={`/notebooks/${notebookId}/professor`}`.
- `/explain` (Feynman) and `/socratic` are **not** general chat entry points —
  both list concepts via `api.mastery()` (`explain/page.tsx:41`,
  `socratic/page.tsx:34`), and concepts are produced only by
  `extract.concepts.v1.md` run over ingested notebook material. Their own empty
  states say this outright: `t.socratic.noConcepts` = *"No concepts yet. They
  come from documents you upload."* (`apps/web/src/locales/en.ts:518`).
- `grep -rn "grounded" app components lib` returns exactly two hits, both in the
  generated OpenAPI type file (`lib/api-schema.ts`) — never a component, never a
  toggle. There is no UI affordance anywhere that lets a user explicitly ask for
  an ungrounded/general-knowledge answer.
- **Conclusion:** to reach any chat surface at all, a brand-new user must:
  Library → create a notebook → open it → click into `/notebooks/[id]/professor`.
  The backend's working `notebook_id=null` path (§1) is architecturally
  unreachable from the product's own UI. This is the literal blocker for "Quero
  aprender psicologia" from a fresh account with zero notebooks.

## 5. Onboarding

**Verdict: not a hard gate, but the first-run UX still funnels toward "add
material."**

- Registration redirects straight to `/today` — `apps/web/src/app/login/page.tsx:47`
  (`router.push('/today')`), no forced "create your first notebook" step.
- But `/today`'s empty state, which is exactly what a zero-notebook account sees
  first (`apps/web/src/app/today/page.tsx:84-90`, copy at
  `apps/web/src/locales/en.ts:141-143`): *"Nothing is due and nothing is weak
  enough to drill... add material, or come back when something is due."* No
  alternative CTA — because none exists (§4).
- `/library`'s empty state (`locales/en.ts:174-176`): *"A notebook is one subject
  you are working on... Put material in it and NOEMA starts building a picture
  of what you know."*
- The landing page's own marketing copy (`locales/en.ts:41`): *"Noema is an AI
  tutor built around your own materials..."* — the product's positioning at the
  entry funnel already frames materials as the starting point, not an
  enhancement.
- **Conclusion:** not a redirect/gate bug, but every piece of first-run copy a
  new user encounters — landing page, `/today` empty state, `/library` empty
  state — tells them, in different words, to go add material before anything
  else happens. Combined with §4 (no other action is actually available), this
  is a coherent, self-reinforcing "materials-first" experience even though
  nothing forces it via a hard redirect.

## 6. RAG-path prompts (`rag.answer`, `rag.no_context`)

**Verdict: correctly gated against the *notebook-less* case — but this surfaces a
second, more damaging bug for the *empty-notebook* case.**

- `_assemble()` (`ai.py:599-613`) only reaches `rag.answer`/`rag.no_context` when
  `grounded=True`; `grounded` is only ever `True` when `notebook_id is not None`
  (`ai.py:69`, `ai.py:398`). A genuinely notebook-less request never sees either
  prompt — ruled out as a cause for the zero-notebook scenario specifically.
- However: `ChatIn.grounded` **defaults to `True`** (`schemas.py:196`), and per
  §4, neither of the app's two chat surfaces ever sends `grounded: false`. So
  the moment a user creates a notebook (satisfying §4's forced first step) and
  starts chatting *before uploading anything*, the request is grounded=True by
  default, `retrieve()` returns `results=[]` (no chunks exist yet), and
  `_assemble` returns `rag.no_context.v1.md`, whose body explicitly instructs:
  > "Do not answer from general knowledge — they will be offered that as a
  > separate, clearly labelled choice, and blurring the two is exactly what
  > makes an AI tutor untrustworthy." (`rag.no_context.v1.md:11-12`)
- That "separate, clearly labelled choice" **does not exist** in the frontend
  (confirmed by the `grounded` grep in §4). The promise the prompt makes to the
  model is not backed by any UI the user can actually reach.
- **Effect:** a user who does the only thing the product lets them do — create a
  notebook, open it, start typing — and asks a question before uploading
  anything gets an explicit, prompt-mandated refusal ("this notebook does not
  contain that, I won't answer from general knowledge") instead of a teaching
  answer. This is arguably the single most user-visible instance of "Noema
  needs material," because it is a literal refusal, not just an absent feature.

## Root cause, ranked

Two independent, real bugs compound into the behavior described in the brief;
one prompt bug rides along on both.

**1. (Primary — architectural) No notebook-independent chat entry point exists
in the frontend**, despite the backend fully supporting `notebook_id=null` for
EXPLAIN/DEEPEN/SUMMARIZE end-to-end (§1, §3). `Shell.tsx`'s nav has ten links and
none of them is chat; `/explain` and `/socratic` require pre-existing concepts
mined from uploaded material; the only two components that call `/ai/professor`
or `/ai/chat` are nested under `/notebooks/[id]` and always pass a real
`notebook_id`. A brand-new user physically cannot reach the code path that
already works. **Fix:** add a notebook-independent chat surface (e.g. a
top-level `/chat`, or make it the CTA in `/today`'s empty state) that calls
`POST /ai/professor` with `notebook_id: null`.

**2. (Primary — backend default + missing UI) An empty, just-created notebook
silently defaults to a hard refusal.** `ChatIn.grounded` defaults to `True` and
no UI ever overrides it, so the first message in any new notebook hits
`rag.no_context.v1.md`, which explicitly refuses to use general knowledge and
promises an opt-out ("a separate, clearly labelled choice") that the frontend
never built. **Fix:** either default `grounded` to `False`/auto-detect when a
notebook has zero ingested sources (degrade gracefully to the ungrounded tutor
path until material exists), or actually build the labelled
opt-out `rag.no_context.v1.md` already promises.

**3. (Contributing — prompt bias) `tutor.explain.v1.md:6` and
`tutor.summarize.v1.md:6`** open with "You are NOEMA, a tutor working inside the
learner's own notebook," and this is precisely the prompt used on every
ungrounded turn (no notebook, or an empty one routed through §1's fallback).
Even once §1/§2 are fixed so the *code path* reaches a real answer, this line
still primes the model to assume/ask about a notebook that may not exist.
**Fix:** drop or condition the notebook-specific framing out of the shared
opening of these two prompts (the identity clause injection point in
`apps/api/noema/prompts/__init__.py:94-95` shows the mechanism already exists
for content that should vary by context; the same idea applies here).

Of the three, #1 is what a user hits first in the exact scenario from the brief
(fresh account, zero notebooks) — they cannot reach chat at all without first
creating a notebook. #2 is what they hit next, immediately after doing the only
thing the product lets them do. #3 is a smaller, compounding bias once either of
the other two is reached.
