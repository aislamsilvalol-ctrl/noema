# Roadmap

Phases are ordered by dependency, not by ambition. Each ends with something usable — no
phase exists purely as scaffolding for the next.

Dates are deliberately absent. This is an open-source project built in the open; the order is
a commitment, the timing is not.

---

## Phase 1 — Foundation *(complete)*

Goal: **you can put material in and talk to it.**

- [x] Monorepo, tooling, CI (lint, typecheck, test, build on every PR)
- [x] PostgreSQL 16 + pgvector schema, Alembic migrations
- [x] Auth: argon2id, cookie sessions, refresh rotation, CSRF
- [x] Workspace → Subject → Notebook hierarchy
- [x] Markdown note editor with slash commands and selection actions
- [x] `AIProvider` abstraction + Anthropic, OpenAI, Ollama implementations
- [x] AI gateway: retries, timeouts, fallback, token accounting, redaction
- [x] BYOK credential storage (AES-GCM, write-only endpoints)
- [x] Streaming AI chat scoped to a notebook
- [x] Design system tokens, shell layout, dark/light
- [x] `docker compose up` works from a clean clone — verified in CI on every push

**Exit criterion:** a new contributor clones, runs `docker compose up`, creates a notebook,
and chats with a local Ollama model without editing a config file.

---

## Phase 2 — Knowledge *(complete)*

Goal: **the system understands the material, and never makes things up about it.**

- [x] Upload pipeline with validation, quotas, checksum dedupe
- [x] Parsers: PDF (+OCR fallback), DOCX, MD, TXT, CSV, URL, transcripts → shared IR
- [x] Structure-aware chunking with heading paths and page anchors
- [x] Embedding pipeline — batched embedding, HNSW index, and a Redis cache keyed on text + model
- [x] Hybrid retrieval (vector + full-text, RRF) — reranking still open
- [x] Grounded answering: enforced citations, refusal when unsupported
- [x] Concept extraction + deterministic resolution/merge
- [x] Knowledge graph — storage, DAG validation, and a keyboard-navigable visualiser
- [x] Global semantic search
- [x] Eval harness — recall@k and refusal rate over a labelled corpus, with thresholds in CI

**Exit criterion:** upload a textbook chapter, ask a question, get an answer with a page
citation you can verify — and get an honest "not in your materials" when it isn't.

---

## Phase 3 — Learning *(in progress)*

Goal: **practice, and a number that means something.**

- [ ] Flashcards — basic, definition, concept, code, cloze and reverse work; image does not
- [x] AI card generation with mandatory human review before activation
- [x] FSRS implementation with parity tests against the reference
- [ ] Review session UI, keyboard-first, offline-tolerant queue
- [x] Question generation and answering — every type the generator produces has an input, keyboard-operable
- [x] Semantic AI grading with rubrics, partial credit, missing-concept feedback
- [x] Confidence capture
- [x] Mistake Bank — misconceptions first, and each row leads back into the question
- [x] Mastery Engine with stored component breakdown
- [x] Exam mode: assisted-free, timed, with concept-level results
- [x] Progress: mastery with its breakdown, review forecast, and the system's own calibration

**Exit criterion:** a month of daily use produces mastery scores a user agrees with when
they read the breakdown.

---

## Phase 4 — Intelligence *(complete)*

Goal: **you stop deciding what to study.**

- [x] Adaptive Learning Engine: candidate generation, utility, constrained selection
- [x] Explained session plans (`rationale` on every block)
- [x] Prerequisite Engine — blocking prerequisites detected, prioritised, and named in the plan's rationale
- [x] Misconception correction — the belief is named, discriminating questions are written, and it resolves only on spaced evidence
- [x] Study goals with deadlines, ordered paths, and an honest verdict when the date does not fit
- [x] Feynman Mode — explain-back, judged against your own material, counted as evidence
- [x] Socratic Mode — a dialogue that concludes, and counts as evidence
- [x] Per-user FSRS parameter optimisation — fitted on your earlier reviews, judged on your later ones
- [x] Counterfactual replay harness for scheduler changes

**Exit criterion:** "Start Session" is the primary action on the dashboard, and users take it
without second-guessing the plan.

---

## Phase 5 — Platform

Goal: **other people extend it.**

- [ ] Plugin SDK: providers, importers, exporters, question generators, themes
- [x] Public REST API with scoped tokens — a bearer token authenticates against
      the same endpoints the web app calls, checked once and centrally in
      `get_current_user` so a route added later is scoped by construction. Scope
      is deliberately coarse for now: `read` (safe methods) and `write`
      (everything else), not per-resource — narrower scopes are a compatible
      later addition, not a rewrite.
- [ ] Import from Anki, Obsidian, Notion, Readwise, Zotero
  - [x] Anki `.apkg`, carrying the review history across rather than starting from zero.
        Media and the zstd-compressed `.anki21b` export are refused by name, not silently.
  - [x] Obsidian vault (zipped): every `.md` file becomes a note, frontmatter
        stripped and wikilinks read as the titles they name. A re-import updates
        a note with the same title rather than duplicating it — notes carry no
        review history for that to put at risk.
  - [x] Notion export (zipped "Markdown & CSV"): every page becomes a note, its
        id suffix and any redundant leading heading stripped, page links read
        as the titles they name, a database's `.csv` summary skipped since its
        rows are already imported as pages. Same re-import-by-title update as
        Obsidian.
- [x] Export to Anki and Markdown
  - [x] Anki `.apkg`, review history included — the inverse of the import above,
        with the same honest limits: a card mid learning-step leaves as new
        rather than guessing at Anki's intraday scheduling, and a card whose
        answer is an image is left behind rather than exported wrong.
  - [x] Markdown, one notebook's notes as a zip of plain `.md` files — the same
        idea as the full-account export, narrowed to a notebook.
- [x] Data export (zip: Markdown + original files + JSON) and account deletion with purge
- [x] Hardened self-hosting: backups, upgrades, single-user mode
  - [x] `scripts/backup.sh` / `scripts/restore.sh` — database and uploads
        together, needing nothing beyond Docker on the host. CI proves the
        restore path actually works: it drops the schema smoke.sh's data
        lives in outright and asserts the row count comes back, rather than
        trusting an untested "just run pg_dump" instruction.
  - [x] Upgrades and single-user mode were already real (`docker compose pull`,
        migrations on API start, `NOEMA_ALLOW_SIGNUPS=false`) — see
        `docs/self-hosting.md`; backups were the piece with no tooling behind
        the documentation.
- [x] Local mode as a fully supported, tested configuration (egress blocked at the runtime, asserted in CI)
- [ ] Community extension registry

---

## Explicitly out of scope

Social feeds, leaderboards, XP, badges, streak guilt. Real-time collaborative editing.
Being a general note-taking app. Being a chat product.

Every proposal is measured against one question: **does this help someone actually learn and
remember?** If the honest answer is no, it doesn't ship — however good the demo looks.
