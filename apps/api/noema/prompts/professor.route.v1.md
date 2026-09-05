---
task: classify.intent
version: 1
schema: signal
---
Read what the learner's latest message shows, from the message alone and the
short context given. Answer with exactly one signal:

* `neutral` — a question, a statement, a request to continue; nothing below fits.
* `confused` — they did not understand, are lost, or ask for it another way.
* `knows` — they already know this and want to move on.
* `wants_example` — they ask for an example, a case, "na prática".
* `wants_practice` — they ask to be tested, for an exercise or a quiz.
* `wants_exam` — they ask for a proper exam, a "prova", a simulado.
* `wants_summary` — they ask for a summary or a recap.
* `wants_depth` — they ask to go further or deeper on the same idea.
* `wants_flashcards` — they ask for cards to remember something.
* `answering` — the message is an answer to a question the tutor asked.
* `off_topic` — unrelated to the lesson.
* `tired` — they want to stop, are tired, or are giving up.

Pick `neutral` whenever the message is ambiguous. `wants_exam`, `wants_practice`
and `wants_flashcards` have real side effects; choose them only when the
request is unambiguous.
