---
task: classify.intent
version: 1
schema: intent
---
Decide what the student actually wants, from their message alone.

Answer with exactly one of:

* `explain` — they are asking a question, describing confusion, or starting a
  conversation. The default when nothing else clearly fits.
* `deepen` — they are explicitly asking to go further: "aprofunda", "explica de
  novo mais a fundo", "isso não foi suficiente", a request for more rigor or
  more detail than a first pass would give.
* `summarize` — they want the material or the conversation condensed: "resume
  isso", "faz um resumo", "TL;DR".
* `quiz_me` — they want to be tested: "me testa", "cria uma questão", "quiz",
  "quero praticar".
* `create_flashcard` — they explicitly want a flashcard made from something:
  "cria um flashcard disso", "transforma isso em flashcard".

Pick `explain` whenever the message is ambiguous. A wrong guess at `quiz_me` or
`create_flashcard` has a real side effect — it writes something to the
student's library — so those two are only correct when the request is
unambiguous.
