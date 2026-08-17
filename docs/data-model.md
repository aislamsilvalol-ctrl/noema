# NOEMA — Data Model

PostgreSQL 16 + pgvector. All ids are UUIDv7 (time-sortable, index-friendly). All tables
carry `created_at` / `updated_at` (UTC). Soft deletes only where export/undo matters
(`notebooks`, `sources`, `notes`); everything else deletes hard.

## Entity map

```
User ──< Workspace ──< Subject ──< Notebook ─┬─< Source ──< Chunk
 │           │                               ├─< Note
 │           └──< Concept ──< ConceptEdge    ├─< Card ──< Review
 │                   │                       ├─< Question ──< Answer
 │                   └──< ConceptMastery     └─< Exam ──< ExamQuestion
 ├──< ProviderCredential
 ├──< StudyGoal ──< LearningPathNode
 ├──< StudySession ──< SessionItem
 └──< Mistake
```

## Core tables

### users
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| email | citext unique | |
| password_hash | text | argon2id |
| display_name | text | |
| settings | jsonb | theme, locale, daily target minutes |
| deleted_at | timestamptz | starts a 30-day purge job |

### workspaces / subjects / notebooks
Straight containment hierarchy, each with `owner_id`, `title`, `slug`, `position`.
`notebooks` additionally carry `ai_provider_override` and `retrieval_settings jsonb`
(top-k, hybrid weights, reranker on/off) so a heavy notebook can be tuned without global
changes.

### sources
| column | type | notes |
|---|---|---|
| id, notebook_id | uuid | |
| kind | enum | `pdf, docx, txt, md, csv, url, transcript, paste` |
| original_filename | text | |
| storage_key | text | object store path |
| checksum_sha256 | text | dedupe within a workspace |
| byte_size | bigint | quota accounting |
| page_count | int | null for non-paginated |
| status | enum | `pending, parsing, chunking, embedding, extracting, ready, failed` |
| error | jsonb | structured failure for the UI |
| metadata | jsonb | title, author, detected language, TOC |

### chunks
| column | type | notes |
|---|---|---|
| id, source_id, notebook_id | uuid | |
| ordinal | int | stable order within source |
| content | text | |
| token_count | int | |
| heading_path | text[] | `{Chapter 3, 3.2 Backpropagation}` |
| page_from, page_to | int | citation targets |
| embedding | vector(1024) | dimension pinned per `embedding_model` |
| embedding_model | text | migrations re-embed rather than mix |
| tsv | tsvector generated | hybrid search |

Indexes: HNSW on `embedding` (`vector_cosine_ops`, m=16, ef_construction=64), GIN on `tsv`,
btree on `(source_id, ordinal)`.

> Storing multiple embedding dimensions in one column is a trap. We pin one active model per
> deployment and re-embed on change, tracked by `embedding_model`.

### notes
Markdown source of truth (`content_md`), plus `content_json` for the editor's tree and
`links jsonb` for `[[wiki-links]]` resolution. Notes are chunked and embedded on the same
pipeline as sources, so the tutor can cite the user's own writing.

## Knowledge graph

### concepts
| column | type | notes |
|---|---|---|
| id, workspace_id | uuid | canonical at workspace scope |
| name | text | |
| aliases | text[] | merge targets |
| definition | text | short, extracted |
| embedding | vector(1024) | dedupe + semantic navigation |
| difficulty_prior | real | 0–1, from extraction; seeds FSRS difficulty |
| source_chunk_ids | uuid[] | provenance — never empty for extracted concepts |
| status | enum | `candidate, active, merged, rejected` |

Unique index on `(workspace_id, lower(name))`. Candidate concepts below a similarity
threshold to an existing one get auto-merged; ambiguous cases surface as a UI review queue.

### concept_edges
| column | type | notes |
|---|---|---|
| src_id, dst_id | uuid | |
| kind | enum | `prerequisite_of, part_of, related_to, contrasts_with` |
| weight | real | 0–1 confidence |
| origin | enum | `extracted, inferred, user` |

`user` edges always win over extracted ones and are never overwritten by re-ingestion.
Prerequisite edges are validated as a DAG on write; a cycle is rejected and logged as an
extraction failure.

## Learning state

### cards
`notebook_id`, `concept_id` (nullable), `type` (`basic, reverse, cloze, image, concept,
definition, code`), `front_md`, `back_md`, `cloze_map jsonb`, `source_chunk_ids uuid[]`,
`origin` (`user, ai`), `approved_at` — AI cards are inert until a human approves them.

### card_states — one row per card, derived
| column | type | notes |
|---|---|---|
| stability | real | FSRS S, in days |
| difficulty | real | FSRS D, 1–10 |
| due_at | timestamptz | indexed with `(user_id, due_at)` |
| last_review_at | timestamptz | |
| reps, lapses | int | |
| state | enum | `new, learning, review, relearning` |

### reviews — append-only evidence
`card_id`, `rating` (1–4), `state_before jsonb`, `state_after jsonb`, `elapsed_ms`,
`confidence` (1–5, nullable), `scheduled_days`, `reviewed_at`.

### questions / answers
Questions carry `type` (`mcq, true_false, open, cloze_blank, matching, ordering, code`),
`difficulty` (`easy, medium, hard, expert`), `payload jsonb` (type-specific), `rubric jsonb`
for open answers, and `concept_ids uuid[]`.

Answers carry `response jsonb`, `is_correct bool`, `score real` (0–1, partial credit from AI
grading), `confidence` int, `elapsed_ms`, `grader` (`deterministic, ai, self`),
`feedback jsonb`.

### concept_mastery — derived projection
`user_id`, `concept_id`, `mastery` (0–100), `retrievability` (0–1), `evidence_count`,
`last_evidence_at`, `calibration` (−1..1, over/under-confidence), `components jsonb`
(the term-by-term breakdown so the UI can explain the number rather than assert it).

### mistakes — the Mistake Bank
`question_id`, `answer_id`, `concept_id`, `confidence`, `is_misconception bool`,
`misconception_summary text`, `resolved_at`. A high-confidence wrong answer sets
`is_misconception` and enqueues targeted question generation.

## Scheduling & goals

`study_goals` (title, deadline, weekly_minutes, target_mastery, concept_ids),
`learning_path_nodes` (goal_id, concept_id, position, state: `locked/available/learning/mastered`),
`study_sessions` (planned_at, mode, planned_minutes, actual_minutes, plan jsonb),
`session_items` (session_id, kind, ref_id, position, outcome jsonb).

Storing the full `plan` blob matters: it lets us replay "what did the engine decide, and was
that a good call?" against outcomes — the only honest way to evaluate the scheduler.

## Credentials

### provider_credentials
`user_id`, `provider`, `label`, `ciphertext bytea`, `nonce bytea`, `key_version int`,
`last_used_at`, `last_verified_at`. No plaintext column exists. The ORM model deliberately
has no serializer that can emit the ciphertext to an API schema.

### api_tokens
`owner_id`, `name`, `token_hash varchar(64)`, `scopes text[]` (`read` and/or `write`),
`last_used_at`, `expires_at`, `revoked_at`. Same rule as `provider_credentials`: no
plaintext column, the secret is returned to its owner exactly once, at creation, and
never again. Scope is checked centrally in `get_current_user`, not per endpoint.

## Migration policy

Alembic, one migration per PR that touches the schema, always with a downgrade. Data
backfills go in separate migrations from DDL so a slow backfill can be rerun without
re-locking tables.
