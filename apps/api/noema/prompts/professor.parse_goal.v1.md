---
task: classify.intent
version: 1
schema: goal
---
Turn what a learner wrote into a learning goal a tutor can plan from.

* `subject` — the field, named the way a syllabus would (2–6 words). "Quero
  aprender psicologia segundo Freud" → "Psicanálise freudiana".
* `objective` — one sentence: what they want to be able to do or understand.
  Keep their emphasis (a job, an exam, curiosity).
* `inferred_level` — where they are now, from what they said: `introductory`
  ("do zero", "nunca vi"), `foundational` (the default when nothing is said),
  `intermediate` ("já vi um pouco", "quero aprofundar"), `advanced`, `expert`.
* `desired_depth` — how far they want to go; usually one step above the level.
* `prerequisites` — up to five things a learner at that level typically lacks
  and this subject needs. Empty when the subject stands alone.
* `language` — the language they wrote in (pt, en, es …).

Write `subject` and `objective` in the learner's language. Never invent an
objective they did not imply.
