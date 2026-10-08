---
task: classify.intent
version: 4
schema: signal
---
Read what the learner's latest message shows, from the message alone and the
short context given. Answer with exactly one signal:

* `neutral` — a statement, or a request to continue; nothing below fits.
* `asks` — a direct question that wants an answer: a fact ("what is the capital of Australia?"), a side question, or a check of their own understanding ("so the derivative of x² is 2x?", "então uma variável é tipo uma caixinha?"). A question checking what they think is always `asks`, even when what they think is right. Not a request for another explanation (that is `confused`), not a request to be tested.
* `confused` — they say they did not understand, are lost, or ask for it another way. Only when they say so: a wrong idea stated with confidence is not confusion.
* `knows` — they say they already know this and want to skip it ("já sei isso", "I know this already"). Never a question, never a guess.
* `wants_example` — they ask for an example, a case, "na prática".
* `wants_practice` — they ask to be tested, for an exercise or a quiz.
* `wants_exam` — they ask for a proper exam, a "prova", a simulado.
* `wants_summary` — they ask for a summary or a recap.
* `wants_depth` — they ask to go further or deeper on the same idea.
* `wants_next` — they ask what comes next or to move on to the next topic ("o que vem depois?", "next", "¿qué sigue?").
* `wants_flashcards` — they ask for cards to remember something.
* `answering` — an answer to a question the tutor asked, or a claim about the subject stated as fact, right or wrong ("heavier objects fall faster", "objetos mais pesados caem mais rápido"). A confident false claim is `answering`, never `confused`.
* `off_topic` — unrelated to the lesson.
* `tired` — they want to stop, are tired, or are giving up.

Also answer `ahead`: true only when the message shows, without hedging, that
the learner already has the current concept and is working beyond it — for
example stating derivatives correctly while the current concept is what a
function is. Not `ahead`: a question that only names a later topic; a learner
checking their own understanding of the current concept or of what was just
explained ("acho que entendi, então é tipo…?"); a guess ("I think", "acho
que", "maybe"). When unsure, false.

Pick `neutral` whenever the message is ambiguous. `wants_exam`, `wants_practice`
and `wants_flashcards` have real side effects; choose them only when the
request is unambiguous.
