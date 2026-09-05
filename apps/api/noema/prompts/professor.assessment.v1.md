---
task: generate.questions
version: 1
schema: assessment
---
Write a short assessment of the concepts listed, at the learner's level, from
what the lesson taught. The goal is to find out what really stayed — not to
trick, not to reward pattern-matching the tutor's words.

* Vary the types: at least one `mcq`, and where the concept allows it a
  `true_false`, a `short` answer (`accepted`: every spelling and synonym you
  would take), an `ordering` (3–5 items in the right `order`), or an `open`
  question (`rubric`: the 2–4 points a full answer must contain).
* `mcq`: four options, all plausible; each wrong option is what someone with
  a specific misunderstanding would choose. `correct_index` is 0-based.
* One question per concept at least; spread the rest over the concepts the
  learner is least sure of.
* `explanation` — one sentence saying why the right answer is right; it is
  shown after grading.
* `title` — short, in the lesson's language ("Checkpoint 1 · O inconsciente").

Write prompts and options in the lesson's language. Nothing the lesson did
not cover.
