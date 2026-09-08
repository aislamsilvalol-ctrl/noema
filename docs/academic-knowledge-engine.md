# Academic Knowledge Engine — Phase 0 audit, architecture, and Phase 1 (source registry)

The third system in the brief: turn public, officially published university
material (MIT OpenCourseWare, Stanford and Harvard public lectures and
their official YouTube channels) into structured, source-traceable
knowledge that NOEMA's Professor can teach from. This document is the
Phase 0 audit, the architecture, and the status of Phase 1 (the source
registry, built; see Status). Segmentation, extraction and everything after
them are not built; the sections below say exactly what would be, in what
order, and what stops it from being "YouTube → transcript → embeddings →
chatbot".

## Phase 0 — what NOEMA has today

- `noema/ingestion/` and `noema/retrieval/`: the notebook pipeline
  (upload → chunk → embed → retrieve with citations validated on the way
  out). Chunks carry `source_id`, page and offsets; `retrieval/grounding`
  numbers citations into the prompt and drops invented ones
  (`CitationFilter`). This is the right *shape* for provenance and is
  reused as-is for derived knowledge.
- `noema/knowledge/`: `Concept` (per workspace, `normalized_name`,
  `difficulty_prior`, embedding, status candidate/active/merged) and
  `ConceptEdge` (`prerequisite_of`, `part_of`, `related_to`,
  `contrasts_with`, weight). A concept graph exists; it is per workspace
  and populated by extraction from the user's own material.
- `noema/professor/curriculum.py`: plans modules → lessons → concepts from
  the learner's goal with a language model; it does not consult any
  external curriculum.
- Nothing fetches external sources; nothing tracks licences; nothing
  distinguishes source-supported from inferred claims.

## The rule that shapes everything

**Store structure and provenance, not courses.** A lecture becomes
concepts, relations, short evidenced claims and timestamped pointers back
to the source; the raw transcript is a cache used to derive those, never a
product surface. This keeps the system inside what the licences allow
(MIT OCW is CC BY-NC-SA 4.0; Stanford Online and Harvard material vary per
course and must be recorded per source; YouTube's terms allow viewing and
the platform's own caption API, not redistribution) and is also what makes
it *knowledge* rather than a pile of text.

## Architecture

```
Source Registry ─► Discovery ─► Acquisition ─► Segmentation ─► Extraction ─► Reconciliation ─► Stores ─► Retrieval
   (what, whose,     (official     (metadata,      (chapters,      (concepts,     (same concept    (concept,   (pedagogical:
    which licence)    playlists)    captions,       segments,       relations,     across sources,   graph,      level, prereqs,
                                    notes, slides)  timestamps)     claims,        disagreement)     citation,   source quality)
                                                                    examples)                        teaching)
```

### Source Registry (`academic_sources`)

`source_id`, `university`, `department`, `course_code`, `course_title`,
`instructor`, `content_type` (lecture_video | lecture_notes | slides |
problem_set | transcript | syllabus), `title`, `url`, `published_at`,
`language`, `licence` (SPDX-like: `CC-BY-NC-SA-4.0`, `CC-BY-4.0`,
`terms-of-service`, `unknown`), `trust` (official | verified | unknown),
`ingestion_status`, `last_checked_at`, `checksum`, `metadata` JSON.
Only `official` sources enter the automatic pipeline; `verified` after a
human marks them; `unknown` never.

### Discovery

Per university, an adapter lists official course pages and official
playlists (OCW course listings; the universities' YouTube channels through
the YouTube Data API, playlists first so lectures keep their order). Output
is registry rows with `trust = official` only when the channel or domain
is in a hand-maintained allow-list. Change detection by playlist etag /
page checksum: new lecture, removed lecture, changed metadata.

### Acquisition

Metadata; captions via the platform's caption API when present (official
captions preferred over auto-generated; the registry records which);
OCW-hosted transcripts, notes and slides (PDF) when the course provides
them. No video download unless the licence permits and the material is
needed for a visual step; the raw cache is private, checksummed, and
carries the licence of its source.

### Segmentation

Chapters from the source when present, else topic segmentation on the
transcript (sentence embeddings + change-point detection), each segment
with `start_ms`, `end_ms`, text and a `quality` flag (low-confidence
words, likely formula speech, incomplete sentences). Nothing is summarised
at this step.

### Extraction (per segment, language model, structured output)

Concepts (`canonical_name`, aliases, definition, difficulty), relations
(`prerequisite_of`, `part_of`, `related_to`, `used_in`,
`contrasts_with`, `example_of`), claims (a short statement with the
segment's timestamps as evidence), examples, analogies, formulas (LaTeX,
validated by a parser; symbols never silently normalised), misconceptions
the instructor names, and an epistemic tag per claim: `fact | model |
theory | interpretation | hypothesis | example`. Every extracted object
carries `support = source_supported` (the text says it) or `inferred`
(the model connected it) — the flag is stored, never collapsed.

### Reconciliation

Candidate concepts are matched to the global concept store by name,
alias and embedding, and **merged only above a high threshold or by a
reviewer**; below it they are linked as `possibly_same` and queued.
When two sources define a concept differently the difference is kept as
`source_disagreement`, not resolved. Cross-source agreement raises a
concept's `confidence`; freshness scoring applies only in domains flagged
as fast-moving (AI, biology, law, economics), not to calculus.

### Stores

`academic_sources`, `academic_courses` (course → lectures in order),
`academic_lectures` (segments), `academic_concepts` (global, with
aliases, difficulty, confidence, review status), `academic_edges`,
`academic_claims` (text, epistemic tag, support flag, evidence pointers
`source_id + start_ms + end_ms`), `academic_materials` (derived teaching
representations: beginner / standard / advanced explanations, analogy,
example, counterexample, question, exercise, common error, prerequisite
check — each marked `generated` and linked to the claims it was generated
from), an embedding index over claims and materials, and a review queue.
Versioning on every derived row: `parser_version`, `extractor_version`,
`concept_version`, `embedding_version`.

### Pedagogical retrieval

Input: the learner's subject, current concept, Sabelia's state
(mastery/recall per concept, weak prerequisites) and level. Output:
claims and materials for the *current* concept at the learner's level,
plus prerequisite material when Sabelia says a prerequisite is weak,
ranked by source quality × cross-source agreement × level fit — not
top-k by cosine. Every returned item carries its citation (university,
course, lecture, timestamp) so the Professor can say where it came from.

### Evaluation

A hand-labelled set (a few lectures per pilot area) with gold concepts,
relations, prerequisites and claim-to-timestamp pointers. Metrics:
concept extraction P/R/F1, relation and prerequisite F1, citation accuracy
(does the timestamp contain the claim), hallucination rate (claims with no
supporting segment), deduplication precision, retrieval relevance at the
learner's level. Quality gates, not "looks good".

## Pilot

Three areas, a handful of complete courses each, chosen for licence
clarity: MIT OCW 18.06 Linear Algebra (CC BY-NC-SA), MIT OCW 6.0001
Introduction to CS and Programming in Python (CC BY-NC-SA), and a
psychology or humanities course with a clear licence (to be selected from
OCW's listing). Stanford and Harvard channels are added after the OCW
pipeline is validated, each with its licence recorded per course.

## Boundaries

- Open-source candidate: parsers, schemas, adapters, extraction pipeline,
  registry tooling, evaluation harness, a synthetic demo corpus.
- Private: the acquired cache, NOEMA's user data, Sabelia learner
  states, private analytics.
- The word for this pipeline is **knowledge ingestion**. Nothing in it
  trains model weights; fine-tuning is a separate, licence-gated decision.

## Status (2026-09-07)

Phase 1 exists: `apps/api/noema/academic/` holds the registry records
(`SourceRecord`, `CourseRecord`, `Licence`, `Trust`, `ContentType`, the
official-domain and official-channel allow-lists) and the OCW discovery
adapter, which reads OCW's own machine-readable `data.json` for a course,
its video gallery, and each lecture resource — licence URL, YouTube id,
official `.vtt` captions and transcript PDF, archive.org file. Run:

```bash
apps/api/.venv/bin/python scripts/academic-register.py --ocw 18-06-linear-algebra-spring-2010 --out registry/mit-18-06.jsonl
```

Pilot result: MIT 18.06 Linear Algebra (Strang, Spring 2010) — 35 lecture
videos, 35 with official captions, all CC BY-NC-SA 4.0, all usable under
their licence for derived, attributed, non-commercial knowledge.

Phase 2 exists too: `academic/acquire.py` fetches the official `.vtt` of
every *usable* record once (skipping, with the reason recorded, anything whose
trust or licence does not allow it), into a private cache with a manifest
line per file — source URL, page URL, licence, trust, checksum, byte count,
fetch time. `academic/captions.py` turns a caption file into cues, then into
sentences that keep the timing of the words they contain, then into topic
segments by lexical cohesion (TextTiling), each with a quality flag:
`short`, `repetitive`, `disfluent`, `unpunctuated`, `spoken_math`. Run:

```bash
apps/api/.venv/bin/python scripts/academic-acquire.py \
    --registry registry/mit-18-06.jsonl --cache .cache/academic \
    --segments out/18-06-segments.jsonl
```

Pilot result: 35 lectures fetched, **1,164 segments**, median 72 seconds and
12 sentences each; 731 carry no quality flag, 413 are flagged `spoken_math`,
37 `repetitive`, 4 `short`, 1 `disfluent`. The `spoken_math` threshold is a
density (0.12 of words), read off this course: at a mere mention of a matrix
it flagged 82% of the segments, which told a reader nothing. The cache and
the segments are gitignored: the pipeline stores structure and provenance,
not courses.

Phase 3 is built but has not been run against a real model. `academic/
extraction.py` sends one segment at a time (`extract.lecture` prompt +
`extract.lecture.schema.json`, structured output) and validates what comes
back: every concept, relation and claim carries the lecture id and the
segment's start and end in milliseconds; every one carries
`source_supported` or `inferred`, and **anything not explicitly marked
supported is stored as inferred** — the asymmetry is deliberate, since an
unmarked object is one nobody promised the segment carried. A claim with no
epistemic tag (`fact | model | theory | interpretation | hypothesis |
example`) is dropped rather than stored untagged; a relation pointing at a
concept the model did not return is dropped rather than creating a node no
segment supports; a flagged segment is never sent at all. Run:

```bash
apps/api/.venv/bin/python scripts/academic-extract.py \
    --segments out/18-06-segments.jsonl --dry-run          # cost first
apps/api/.venv/bin/python scripts/academic-extract.py \
    --segments out/18-06-segments.jsonl --out out/18-06-knowledge.jsonl \
    --provider anthropic --model <model> --limit 40        # then a sample
```

For 18.06 the dry run reports 1,164 segments ≈ 1.07 M input tokens and up to
0.47 M output tokens (731 segments ≈ 0.66 M / 0.29 M with `--skip-flagged`).
No model has seen them: this machine has no provider key. The output is a
file, never a database row — Phase 4 (reconciliation against `Concept`, with
disagreement kept rather than resolved) reads it after a person does.

## Order of work

1. Registry tables and the allow-list; the OCW adapter (course pages +
   transcripts); change detection.
2. Segmentation and extraction with the support flag and epistemic tags;
   the review queue.
3. Concept reconciliation against `Concept`; disagreement records.
4. Pedagogical retrieval wired into the Professor's `<MATERIALS>` block
   with citations.
5. Evaluation set and gates; then Stanford, then Harvard; then the Atlas
   view.
