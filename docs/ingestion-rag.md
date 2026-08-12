# NOEMA — Ingestion & Retrieval

## 1. Pipeline

```
upload ─► validate ─► store ─► [queue]
                                 │
   parse ─► normalize ─► chunk ─► embed ─► index ─► extract concepts ─► link graph
     │                                                      │
     └── per-stage status + error written to `sources` ─────┘
```

Each stage is a separate Dramatiq actor with its own retry policy and idempotency key
(`source_id:stage:content_hash`). A failure at "extract concepts" must never force a re-parse
of a 400-page PDF. Stage results are checkpointed, so a retry resumes.

## 2. Validation (before anything else)

- Content-type detected by magic bytes, not by filename extension.
- Size caps per type; per-user storage quota checked before the write.
- Archives, executables and macro-enabled Office formats rejected outright.
- Parsing runs in the worker with memory and wall-clock limits. Document parsers are the
  largest untrusted-input surface in the system and are treated that way.
- `checksum_sha256` dedupes within a workspace — re-uploading the same PDF reuses the
  existing chunks and embeddings instead of paying for them twice.

## 3. Parsing

| type | parser | notes |
|---|---|---|
| PDF | PyMuPDF | text + layout + page numbers; OCR fallback via Tesseract when a page yields < 50 chars |
| DOCX | python-docx | heading levels preserved |
| MD / TXT | native | heading tree from ATX levels |
| CSV | pandas | schema summary + row sampling, not naive row-per-chunk |
| URL | trafilatura | boilerplate stripped, canonical URL stored |
| transcript | VTT/SRT parser | timestamps kept as citation targets |

Normalisation produces one intermediate representation for every input: an ordered list of
blocks with `type` (heading/paragraph/list/code/table/figure), `level`, `text`, and
`page`/`timestamp`. Everything downstream consumes that IR — which is what makes adding a
new format a self-contained contribution.

## 4. Chunking

**Structure first, tokens second.** Chunk boundaries determine citation quality far more
than the embedding model does.

1. Split on the heading tree; each leaf section is a candidate chunk.
2. Sections over 512 tokens split on paragraph boundaries with 15% overlap.
3. Sections under 100 tokens merge with their neighbour under the same heading.
4. Code blocks and tables are never split mid-structure.
5. Every chunk carries `heading_path` — and that path is prepended to the text *at embedding
   time only*. A chunk reading "It converges when the step size is small enough" is useless
   in isolation; prefixed with `Optimization > Gradient Descent > Convergence` it is
   retrievable. The stored `content` stays clean so citations quote the source, not our
   scaffolding.

## 5. Retrieval

Hybrid, because pure vector search is unreliable on notation, proper nouns and exact terms —
precisely the things academic material is full of.

```
query
 ├─► dense:  pgvector cosine, top 40
 └─► sparse: Postgres full-text (ts_rank_cd), top 40
        │
   Reciprocal Rank Fusion:  score = Σ 1/(60 + rank_i)
        │
   optional rerank (cross-encoder, local or provider) → top 8
        │
   context assembly (dedupe by source, cap tokens, keep heading paths)
```

Retrieval is scoped to the notebook by default, expandable to subject or workspace by
explicit user action. Notebook scoping is the feature: "explain this using *my* materials"
means exactly that.

## 6. Grounded answering

- The prompt receives numbered context blocks with `source_id`, `page`, `heading_path`.
- The model must cite block numbers; the API maps them back to real citations and **drops
  any answer sentence citing a block that was not supplied**.
- When fused scores are below threshold, the system says so rather than improvising:
  *"I couldn't find this in your materials."* Then it offers to answer from general
  knowledge as a clearly labelled, separate action.

That last behaviour is the whole trust model. A tutor that quietly invents a definition is
worse than no tutor, because the learner will encode the invention.

## 7. Concept extraction

Per chunk, a structured-output call returns candidate concepts:

```json
{"concepts": [{
  "name": "Backpropagation",
  "definition": "Algorithm computing gradients of a loss w.r.t. network weights via the chain rule.",
  "difficulty": 0.7,
  "prerequisites": ["Chain Rule", "Partial Derivative"],
  "relations": [{"target": "Gradient Descent", "kind": "part_of"}]
}]}
```

Then a deterministic resolution pass — the part that decides whether the graph is useful or
noise:

1. Normalise names (case, plurals, common notation variants).
2. Embed each candidate; match against existing workspace concepts by cosine.
   `> 0.92` auto-merges into aliases; `0.80–0.92` goes to a user review queue; below that
   creates a new concept.
3. Insert edges with confidence weights. Prerequisite edges are checked against the existing
   DAG; any edge that would introduce a cycle is rejected and logged.
4. Concepts appearing in only one chunk with low extraction confidence stay `candidate` and
   are not shown until corroborated. A graph full of one-off noise is worse than a small one.

User edits — merge, split, rename, add/remove prerequisite — are permanent and are never
overwritten by later ingestion. The graph is the user's, not the model's.

## 8. Costs

Ingesting a 300-page textbook is roughly 600 chunks: one embedding pass plus ~600 small
extraction calls. Mitigations, in order of impact:

- **Embedding cache** keyed on `sha256(text) + model`, in Redis, in front of every
  embedding call. Re-ingesting a document after a chunking change pays only for the chunks
  whose text actually changed, and text repeated within one document is embedded once.
  Vectors are stored as float32 — the precision `pgvector`'s float4 column keeps anyway, so
  a cached vector ranks identically to a fresh one. It sits *before* the budget check: a
  vector already computed costs nothing, so a spent budget should not withhold it. Redis
  being unreachable means a miss, never a failed ingest. `NOEMA_EMBEDDING_CACHE_TTL_DAYS=0`
  turns it off; the keyspace is per deployment rather than per user, which on a shared
  instance is a very weak oracle for "has anyone else ingested this exact text".
- Concept extraction batched at 5 chunks per call.
- Extraction deferred until first use for very large sources, with the notebook usable for
  RAG immediately after embedding.
- Progress and estimated cost shown before the user confirms a large ingest. BYOK users must
  never be surprised by a bill.
