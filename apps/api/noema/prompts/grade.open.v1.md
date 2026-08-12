---
task: grade.open_answer
version: 1
schema: grade
---
Grade the learner's answer against the rubric.

You are judging whether they demonstrated the understanding, not whether they used
the source's words. An answer that is correct in different vocabulary is correct. An
answer that repeats the source's phrasing without the substance is not.

Score 0 to 1:

* 1.0 — every point in the rubric, correctly.
* 0.7–0.9 — the substance, missing a qualifier or a condition.
* 0.4–0.6 — the central idea, with a real gap or a wrong detail.
* 0.1–0.3 — a fragment, or the right words around a wrong model.
* 0.0 — absent, or contradicts the material.

Return also:

* `missing` — rubric points they did not cover. Name the concept, not the sentence.
* `errors` — things they said that are wrong. Be specific; "some inaccuracies" helps
  nobody.
* `feedback` — two sentences at most, addressed to them. Say what to fix, not how
  well they did.

Do not be generous. A learner told they were right when they were half right will
stop there, and the score feeds a model that decides what they see next.
