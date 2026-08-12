---
task: generate.cards
version: 1
schema: cards
---
Write flashcards that test recall of the passages below.

A good card has exactly one answer, and a learner who understands the material can
give it in a few seconds. A card asking "what are the four properties of X" is four
cards.

For each card:

* `front` — the question. Ask for the thing itself, not for the passage's wording.
  "What does the chain rule let you differentiate?" not "What does the text say
  about the chain rule?"
* `back` — the answer. Short. If it needs three sentences, the question was too big.
* `type` — `basic` for a question and answer, `definition` for a term and its
  meaning, `concept` for why something matters or how it relates, `code` when the
  answer is code.
* `concept` — the concept this card tests, named as the passage names it.

Rules:

* Every card must be answerable from the passage alone. A card whose answer is not
  in the material teaches the learner something you invented.
* No cards whose answer is the question rephrased.
* No trivia. Dates, figure numbers and author names are not understanding.
* Prefer why and how over what, except for genuine definitions.
* If a passage does not support a good card, return none for it. Fewer real cards
  beat filling a quota.
