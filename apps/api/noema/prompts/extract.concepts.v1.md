---
task: extract.concepts
version: 1
schema: concepts
---
Extract the concepts a learner would need to understand the passages below.

A concept is something a person can be said to know or not know: an idea, a method,
a theorem, a technique, a defined term. It is not a section title, not an author,
not a figure number, and not a topic so broad it could not be tested.

For each concept give:

* `name` — how the material itself refers to it, in its shortest standard form.
  Prefer "chain rule" over "the chain rule of differentiation".
* `definition` — one sentence, drawn from the passage rather than from your own
  knowledge. If the passage names a concept without defining it, leave this empty.
* `difficulty` — 0 to 1, how hard this is for someone meeting it for the first time.
  Arithmetic is 0.1; a measure-theoretic construction is 0.9.
* `prerequisites` — concepts a learner must already understand to follow this one.
  Only what the passage itself relies on. Do not reach for the wider field.
* `relations` — other concepts named in the passage, with how they relate:
  `part_of`, `related_to`, or `contrasts_with`.

Rules:

* Extract only what the passage supports. A concept you know belongs to this field
  but that the passage never mentions does not belong in this learner's graph.
* Prefer fewer, well-defined concepts to many vague ones. Five real concepts beat
  twenty fragments.
* Use the passage's own vocabulary. If it says "backprop", do not rename it.
* Prerequisites point *backwards*: `chain rule` is a prerequisite of
  `backpropagation`, never the reverse. Getting this direction wrong inverts the
  order a learner is sent through the material.
