---
task: generate.questions
mode: correction
version: 1
---
The learner answered confidently and was wrong. Your job is to name the belief that
would make their answer sensible, and then write questions that break it.

`belief` is one sentence, in the learner's terms, stating the wrong model their
answer implies. Not "they misunderstood X" — the actual claim they seem to hold. If
their answer looks like a slip rather than a belief, say so in `belief` and return no
questions: drilling a typo teaches nothing.

Each question must be a **discriminating case**: one where the wrong model and the
correct model give different answers. A question both models answer the same way
cannot tell the learner — or us — which one they are using.

Judge against the SOURCE material. Do not invent facts to build a clean contrast.

Prefer `mcq` and `true_false`, whose grading is unambiguous. Every option must be
plausible to someone holding the belief; an obviously silly distractor makes the
question easy for the wrong reason.
