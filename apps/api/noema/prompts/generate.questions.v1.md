---
task: generate.questions
version: 1
schema: questions
---
Write questions that test understanding of the passages below.

A good question has one defensible answer and cannot be answered by pattern-matching
the wording of the passage. Prefer questions that require applying the idea over
questions that require finding it.

For each question give `type`, `difficulty`, `prompt`, `concept`, and the payload its
type needs:

* `mcq` — `options` (four, all plausible) and `correct_index`. A distractor nobody
  would pick tests nothing; each wrong option should be what someone with a specific
  misunderstanding would choose.
* `true_false` — `answer`, plus `explanation`. Avoid statements that are true only
  by a technicality.
* `fill_blank` — `accepted`, listing every spelling and synonym you would accept.
* `open` — `rubric.points`, the things a full answer must contain.
* `ordering` — `order`, the correct sequence.

Difficulty is about the thinking required, not the obscurity of the fact:

* `easy` — recall of something stated directly.
* `medium` — connecting two things from the passage.
* `hard` — applying the idea to a case the passage does not cover.
* `expert` — recognising when the idea does not apply, or why it fails.

Every question must be answerable from the passage. A question whose answer is not
in the material tests whether the learner shares your assumptions, not what they
learned.
