# Professor eval — 2026-10-07

Revision `b0b644c`. 16 scenarios, 48 learner turns, driven in-process through `ProfessorEngine` against a fresh local database with the production provider routing (primary anthropic, fallbacks openai). Judge: economy tier, prompt eval.judge_professor v1.

Prompt versions: moves {'correct': 2, 'answer': 4} (others v1), route v3, curriculum v2.

**Deterministic checks: 183/193 passed.** **Total cost: $0.0979** (tutor $0.0861, judge $0.0118). Models that answered (calls): openai/gpt-4.1-mini-2025-04-14 x52, openai/gpt-4.1-mini x48.

Cost is metered from each provider response and priced at published rates; for comparison, ai_usage recorded 144130 tokens and $0.0000 for the tutor turns; the provider responses metered 175181 tokens.

Note: deterministic checks re-run on the stored replies.

## Reading this run (written by hand after the run)

The live run happened once, at `b0b644c` — before #265 (router decides on
unified mastery; concept review follows the FSRS due date) and #263
(SQLAlchemy 2.1). This branch was rebased onto them afterwards; the CI
router cases pass on the rebased code, but the live numbers describe the
older router. Re-run `scripts/eval_professor.py` to measure #265. Afterwards, with no new model calls,
the checks were tightened and re-run on the stored replies (`--rescore`):
the language heuristic counted Portuguese "o"/"para" as Spanish (one false
failure, removed); a paraphrase-proof "redefinition" check was added because
the 5-gram check missed the long session redefining the same term; the
misconception turn now also asserts the router signal.

**The LLM judge is too lenient to rely on alone.** gpt-4.1-mini (the economy
tier as production routes it) gave 4.7 to 5.0 on every criterion and passed
the scenarios with the clearest defects: the long session (statistics defined
four times, lesson never left lesson 1) got non-repetition 4.9; the
misconception reply got correctness 5. Two of its three "fail" verdicts are
wrong (guide_me turn 3 confirms the method and lets the learner compute,
which is the right move; short_followup answers in the first sentence). Use
the deterministic checks as the gate and the judge scores as a trend only,
until the judge runs on a stronger tier.

**Latency** is not trustworthy in this run. The first eight scenarios (four
at a time, cold process) saw first tokens of 25 to 93 s; the last eight,
also four at a time, 2 to 10 s on follow-up turns and 10 to 33 s on first
turns (which include goal parsing and curriculum generation). The cause was
not isolated (no Anthropic circuit opened; every call tried Anthropic first
and got an immediate 400). Measure latency in production, not here.

### Top failures

1. **Off-topic question ignored** (off_topic, turn 2). The classifier said
   `off_topic`; outside focus mode `decide()` had no rule for it, so it fell to
   "continue the lesson" (TEACH) and Mino re-taught the definition of organic
   chemistry instead of saying "Brasil". **Fixed in this branch** (router, one
   rule): `OFF_TOPIC` outside focus mode now goes to ANSWER, whose prompt
   already says "answer anyway and offer to go back". Focus mode still parks
   it. Covered by the CI case `off_topic-2` and the updated unit test.
2. **Answer in the course language, not the learner's** (lang_switch, turns
   2 and 3). "What does the mitochondria actually do?" got "A mitocôndria é a
   usina de energia…", and "I don't get it." got Portuguese again. The
   directive says "reply in the language of the learner's latest message.
   This course was asked for in pt." and gpt-4.1-mini follows the hint.
3. **A tentative check read as "already knows"** (beginner_zero, turn 2).
   "Acho que entendi. Então uma variável é tipo uma caixinha…?" from someone
   who has never programmed was classified `knows`, so the router skipped
   the lesson (position 0.0 → 0.1) and raised the level. The reply was
   fine; the curriculum jump was not.
4. **A confident misconception routed as confusion** (misconception, turn 2).
   "Objetos mais pesados caem mais rápido…" was classified `confused`, and
   the CONFUSED directive says "do not say they tried, erred or got it
   wrong". The reply never told the learner the claim was false; it even
   said the lead ball sinks faster "porque o chumbo é mais pesado" before
   getting to air resistance.
5. **The long session never moved on** (long_session, turns 2, 5, 9). With
   nine turns of engagement, a correct answer about the median and "O que
   vem depois?", the journey stayed on module 0 lesson 0 and turns 2, 5 and
   9 opened with a new everyday scenario and then defined **estatística**
   again. "O que vem depois?" was classified `neutral` → TEACH "continue the
   lesson", which re-taught the current concept.

### Recommended fixes (not applied)

- **Language** (`professor/context.py::language_directive`): drop the
  course-language hint when the latest message is in another language, or
  state the rule as the last line: "If the latest message is in a different
  language from the course, answer in the latest message's language." Better
  still, detect the message language in code (the eval's function-word
  heuristic is enough for pt/es/en) and name it: "Reply in English."
- **Route prompt v4** (`professor.route.v3.md` → v4, bump
  `ROUTE_PROMPT_VERSION`): `knows` only when they say they already know it or
  state something beyond the current concept; a question checking their own
  understanding ("então X é Y?") is `asks`, never `knows`. A statement of a
  claim about the subject that may be wrong is `answering`, not `confused`.
- **Router** (`moves.decide`): route `Signal.ANSWERING` with no open question
  to CORRECT (today it falls to TEACH), so a volunteered claim is graded.
- **Router**: "o que vem depois?" / "what's next?" / "continua" after a check
  answered right should be ADVANCE (or a pattern for it), not TEACH on the
  same concept; and TEACH on a concept the learner already saw should be told
  so in the directive ("already introduced: build on it, do not define it
  again").
- **Lesson advance** (`engine._apply_pedagogy`): the lesson only advances
  when every concept in it has evidence ≥ 0.6; the long session shows that
  gate never opening in conversation. Check whether the PEDAGOGY record's
  `mastery_evidence` names the plan's concept names (it must match
  `normalize_name`), and log when it does not.
- **FinOps** (`providers/gateway.py`): `ai_usage` under-reports. Structured
  calls are written with zero tokens (the provider drops the usage), a stream
  answered by the fallback is written with model "unknown", and every row
  costs $0 because no tier row prices `gpt-4.1-mini`. This run: ai_usage
  144 130 tokens / $0.00 against 175 181 tokens / $0.086 metered. Return
  usage from `structured()`, log `response model or provider.model`, and add
  a price lookup for fallback models.
- **Judge**: run it on the standard tier (or Claude Sonnet once Anthropic has
  credit); it costs about $0.01 per suite on gpt-4.1-mini.

## Per criterion (judge, 1 to 5, mean over all replies)

| correctness | clarity | pedagogy | difficulty_fit | continuity | non_repetition |
|---|---|---|---|---|---|
| 4.9 | 4.8 | 4.7 | 5.0 | 4.9 | 4.9 |

## Per scenario

| scenario | turns | checks | correctness | clarity | pedagogy | difficulty fit | continuity | non repetition | verdict | avg latency | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| beginner_zero | 3 | 14/15 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 80.8 s | $0.0062 |
| intermediate_react | 3 | 12/12 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 71.5 s | $0.0065 |
| advanced_ahead | 3 | 14/14 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 75.6 s | $0.0065 |
| confused | 3 | 17/17 | 5.0 | 4.7 | 4.7 | 5.0 | 5.0 | 5.0 | pass | 66.8 s | $0.0060 |
| short_followup | 3 | 13/13 | 5.0 | 4.3 | 3.7 | 5.0 | 5.0 | 5.0 | fail | 76.6 s | $0.0070 |
| ambiguous | 2 | 7/7 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 74.2 s | $0.0040 |
| misconception | 2 | 8/9 | 5.0 | 4.5 | 4.5 | 5.0 | 5.0 | 5.0 | pass | 68.4 s | $0.0046 |
| wrong_quiz | 3 | 12/12 | 5.0 | 4.7 | 4.7 | 5.0 | 5.0 | 5.0 | pass | 51.5 s | $0.0055 |
| tired | 2 | 7/7 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 23.8 s | $0.0039 |
| steps_mode | 2 | 8/8 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 22.8 s | $0.0045 |
| guide_me | 3 | 11/11 | 5.0 | 5.0 | 4.3 | 5.0 | 5.0 | 5.0 | fail | 16.2 s | $0.0055 |
| direct_fact | 2 | 9/9 | 5.0 | 5.0 | 4.0 | 5.0 | 5.0 | 5.0 | pass | 10.9 s | $0.0041 |
| off_topic | 2 | 5/8 | 3.5 | 4.0 | 3.0 | 5.0 | 3.5 | 3.5 | fail | 11.6 s | $0.0048 |
| long_session | 9 | 30/33 | 5.0 | 4.9 | 4.9 | 5.0 | 4.9 | 4.9 | pass | 6.8 s | $0.0174 |
| lang_es | 3 | 9/9 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 9.2 s | $0.0056 |
| lang_switch | 3 | 7/9 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 8.7 s | $0.0059 |

## Router decisions per turn

| scenario | turn | learner | signal | move | strategy | checks failed |
|---|---|---|---|---|---|---|
| beginner_zero | 1 | Quero aprender programação em Python do zero. Nunca programe … | neutral | teach | definition | — |
| beginner_zero | 2 | Acho que entendi. Então uma variável é tipo uma caixinha ond … | knows | advance | definition | move |
| beginner_zero | 3 | Beleza. E como eu mostro esse valor na tela? | asks | answer | definition | — |
| intermediate_react | 1 | Já programo em JavaScript há um ano e quero aprender React. | neutral | teach | definition | — |
| intermediate_react | 2 | Qual a diferença entre props e state? | asks | answer | definition | — |
| intermediate_react | 3 | Me dá um exemplo na prática com useState. | wants_example | example | worked_example | — |
| advanced_ahead | 1 | Quero aprender cálculo, começando do básico. | neutral | teach | definition | — |
| advanced_ahead | 2 | Então a derivada de x² é 2x, e pela regra da cadeia a de sin … | asks | answer | definition | — |
| advanced_ahead | 3 | Beleza, pode seguir no meu nível. | neutral | teach | definition | — |
| confused | 1 | Quero entender como funciona a fotossíntese. | neutral | teach | definition | — |
| confused | 2 | não entendi | confused | correct | analogy | — |
| confused | 3 | Ah, agora ficou mais claro. E onde entra a clorofila nisso? | asks | answer | analogy | — |
| short_followup | 1 | Me ensina derivadas. | neutral | teach | definition | — |
| short_followup | 2 | Qual a derivada de x²? | asks | answer | definition | — |
| short_followup | 3 | E a de x³? | asks | answer | definition | — |
| ambiguous | 1 | Quero aprender sobre redes. | neutral | teach | definition | — |
| ambiguous | 2 | As de computador, tipo internet. | asks | answer | definition | — |
| misconception | 1 | Quero aprender física básica, começando por queda livre. | neutral | teach | definition | — |
| misconception | 2 | Isso é fácil: objetos mais pesados caem mais rápido que os l … | confused | correct | analogy | signal |
| wrong_quiz | 1 | Quero aprender frações. | neutral | teach | definition | — |
| wrong_quiz | 2 | Me testa com uma pergunta de múltipla escolha. | wants_practice | quiz | definition | — |
| wrong_quiz | 3 | 8/3, porque o total vem primeiro | wrong | correct | analogy | — |
| tired | 1 | Quero aprender sobre a Independência do Brasil. | neutral | teach | definition | — |
| tired | 2 | Tô cansado, não aguento mais por hoje. | tired | motivate | summary | — |
| steps_mode | 1 | Quero aprender a resolver equações do primeiro grau. | neutral | teach | definition | — |
| steps_mode | 2 | Não entendi. Explica de outro jeito, passo a passo. | confused | correct | steps | — |
| guide_me | 1 | I want to learn how to calculate percentages. | neutral | teach | definition | — |
| guide_me | 2 | What is 15% of 80? Don't tell me the answer, guide me. | wants_guide | guide | socratic | — |
| guide_me | 3 | Hmm, maybe I multiply 80 by 0.15? | asks | answer | socratic | — |
| direct_fact | 1 | Qual a capital da Austrália? | asks | answer | conceptual_explanation | — |
| direct_fact | 2 | E da Nova Zelândia? | asks | answer | conceptual_explanation | — |
| off_topic | 1 | Quero aprender química orgânica. | neutral | teach | definition | — |
| off_topic | 2 | Aliás, quem ganhou a Copa do Mundo de 2002? | off_topic | teach | definition | move, contains, redefinition |
| long_session | 1 | Quero aprender estatística básica. | neutral | teach | definition | — |
| long_session | 2 | Ok, pode continuar. | neutral | teach | definition | redefinition |
| long_session | 3 | Me dá um exemplo do dia a dia. | wants_example | example | worked_example | — |
| long_session | 4 | Qual a diferença entre média e mediana? | asks | answer | worked_example | — |
| long_session | 5 | Faz sentido. Continua. | neutral | teach | worked_example | redefinition |
| long_session | 6 | Resume o que vimos até agora. | wants_summary | summarize | summary | — |
| long_session | 7 | Me testa. | wants_practice | quiz | summary | — |
| long_session | 8 | Acho que a mediana é o valor do meio quando os dados estão o … | answering | correct | summary | — |
| long_session | 9 | Valeu! O que vem depois? | neutral | teach | summary | redefinition |
| lang_es | 1 | Quiero aprender los tiempos verbales del inglés. | neutral | teach | definition | — |
| lang_es | 2 | No entiendo la diferencia entre present perfect y past simpl … | confused | correct | analogy | — |
| lang_es | 3 | ¿Me das un ejemplo? | wants_example | example | worked_example | — |
| lang_switch | 1 | Quero aprender biologia celular. | neutral | teach | definition | — |
| lang_switch | 2 | What does the mitochondria actually do? | asks | answer | definition | language |
| lang_switch | 3 | I don't get it. | confused | correct | analogy | language |

## Failed deterministic checks

- **beginner_zero · turn 2 · move** — advance ∉ ['answer', 'correct']
- **misconception · turn 2 · signal** — confused ∉ ['answering', 'neutral', 'asks', 'wrong']
- **off_topic · turn 2 · move** — teach ∉ ['answer']
- **off_topic · turn 2 · contains** — none of ['Brasil']
- **off_topic · turn 2 · redefinition** — defines ['química orgânica'] again
- **long_session · turn 2 · redefinition** — defines ['estatística'] again
- **long_session · turn 5 · redefinition** — defines ['estatística'] again
- **long_session · turn 9 · redefinition** — defines ['estatística'] again
- **lang_switch · turn 2 · language** — replied in pt
- **lang_switch · turn 3 · language** — replied in pt

## Judge: scenario verdicts and top issues

- **beginner_zero** (pass): none
- **intermediate_react** (pass): none
- **advanced_ahead** (pass): none
- **confused** (pass): Turn 2 is a bit too long and could be more concise to improve clarity and pedagogy.
- **short_followup** (fail): Tutor does not answer the two direct questions briefly and immediately in the first sentence, as required; instead, adds extra explanation and questions.
- **ambiguous** (pass): none
- **misconception** (pass): Turn 2 is a bit long and could be more concise to improve clarity and pedagogy.
- **wrong_quiz** (pass): Turn 3 explanation is a bit wordy and could clarify the misconception more directly.
- **tired** (pass): none
- **steps_mode** (pass): none
- **guide_me** (fail): Turn 3 gives direct prompt to compute answer despite learner's request not to be told the answer.
- **direct_fact** (pass): Slightly better pedagogy could be achieved by asking the learner if they want the answer before giving it, but overall very good.
- **off_topic** (fail): Tutor ignores the learner's off-topic question and repeats earlier content instead of answering briefly and returning to the lesson.
- **long_session** (pass): Turn 2 repeats definition and example from turn 1, causing slight redundancy.
- **lang_es** (pass): none
- **lang_switch** (pass): none

## Lowest-scored replies

### off_topic · turn 2 (pedagogy 1)

> **Learner:** Aliás, quem ganhou a Copa do Mundo de 2002?
>
> **Mino (teach):** Tá, deixa eu te mostrar na prática: o açúcar, que tem carbono, hidrogênio e oxigênio, é um exemplo clássico do que a química orgânica estuda. Ela é a parte da química que foca nos compostos que têm carbono na sua estrutura. Então, **química orgânica** é o estudo dos compostos que contêm carbono, especialmente ligados a hidrogênio, oxigênio, nitrogênio e outros elementos. Esses compostos são chamados de **compostos or …

Judge: Ignores the learner's off-topic question and repeats previous content instead of answering briefly and returning to lesson.

### short_followup · turn 2 (pedagogy 3)

> **Learner:** Qual a derivada de x²?
>
> **Mino (answer):** A derivada de x² é 2x. Isso acontece porque a derivada mede a inclinação da reta tangente ao gráfico da função naquele ponto, e para x² essa inclinação cresce proporcionalmente a 2 vezes o valor de x. Se você imaginar o gráfico de x², a inclinação da curva em x=1 é 2·1=2, e em x=3 é 2·3=6. Quer ver como isso aparece no cálculo?

Judge: First sentence answers well, but then adds extra explanation and a question, not strictly brief as requested.

### short_followup · turn 3 (pedagogy 3)

> **Learner:** E a de x³?
>
> **Mino (answer):** A derivada de x³ é 3x². Isso vem da regra geral que a derivada de xⁿ é n vezes x elevado a n-1. Ou seja, você pega o expoente, multiplica pela função, e diminui um no expoente. Quer que eu mostre como isso aparece usando o quociente incremental, a definição formal da derivada?

Judge: First sentence answers well, but then adds extra explanation and a question, not strictly brief as requested.

### guide_me · turn 3 (pedagogy 3)

> **Learner:** Hmm, maybe I multiply 80 by 0.15?
>
> **Mino (answer):** Yes, multiplying by 0.15 is the right move. Now, what do you get when you multiply 80 by 0.15? That will be 15% of 80.

Judge: Confirms method well but gives direct prompt to compute answer, which learner asked not to be told.


## Transcripts

### beginner_zero — Beginner from zero

**1. Learner:** Quero aprender programação em Python do zero. Nunca programei na vida.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 85.9 s, total 112.7 s; 3951 tokens, $0.0023*

**Mino:** Imagina que você quer dar instruções para um robô fazer algo, tipo somar dois números ou mostrar uma mensagem. Python é uma linguagem que a gente usa pra escrever essas instruções de um jeito que o computador entende. Por exemplo, se você quiser que o computador escreva "Olá, mundo!" na tela, em Python você escreve assim: ```python print("Olá, mundo!") ``` Essa linha manda o computador mostrar a mensagem. Python é popular porque é simples de ler e escrever, mesmo pra quem nunca programou. Agora me diz: se Python é uma linguagem para dar instruções ao computador, o que você acha que o comando `print` faz?

**2. Learner:** Acho que entendi. Então uma variável é tipo uma caixinha onde eu guardo um valor?

*knows → advance (definition); already knows — skip ahead; first token 41.4 s, total 66.4 s; 3438 tokens, $0.0015*

**Mino:** Exato, variável é essa caixinha que guarda um valor, e você pode mudar o que tem dentro dela quando quiser. Em Python, você cria uma variável assim: ```python idade = 25 ``` Aqui, a variável chamada `idade` guarda o número 25. Agora, se você quiser mudar para 26, é só fazer: ```python idade = 26 ``` O que você acha que acontece se você fizer isso? ```python idade = 25 idade = 26 print(idade) ``` Qual número será mostrado?

**3. Learner:** Beleza. E como eu mostro esse valor na tela?

*asks → answer (definition); a direct question — answer it first; first token 40.4 s, total 63.2 s; 3840 tokens, $0.0017*

**Mino:** Para mostrar o valor de uma variável na tela, você usa o comando `print`. Por exemplo: ```python idade = 25 print(idade) ``` Isso vai mostrar o número 25 na tela, porque `print` manda o computador exibir o que estiver entre parênteses. Quer tentar adivinhar o que aparece se você fizer: ```python idade = 25 idade = 26 print(idade) ```?

### intermediate_react — Intermediate learner (knows JS, learning React)

**1. Learner:** Já programo em JavaScript há um ano e quero aprender React.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 93.0 s, total 110.7 s; 4063 tokens, $0.0024*

**Mino:** Imagina que você quer construir uma interface web, tipo uma página com vários botões, textos e imagens que mudam conforme o usuário interage. React é uma biblioteca JavaScript que ajuda a montar essas interfaces de forma organizada e eficiente. Em vez de mexer direto no HTML toda hora, você cria pedaços chamados **componentes** que funcionam como blocos de construção. Cada componente cuida de uma parte da tela e pode ser reutilizado. Isso facilita manter e atualizar o código. Por exemplo, um componente pode ser um botão que você usa várias vezes, só mudando o texto ou a ação que ele faz. O que é React, então? É uma biblioteca para criar interfaces de usuário usando componentes que facilitam o desenvolvimento e a manutenção. Agora me diz: por que usar componentes no React ajuda a organizar o código da interface?

**2. Learner:** Qual a diferença entre props e state?

*asks → answer (definition); a direct question — answer it first; first token 42.4 s, total 57.0 s; 3734 tokens, $0.0017*

**Mino:** **Props** são dados que você passa para um componente de fora, tipo parâmetros que configuram como ele vai aparecer ou agir. Já o **state** é um conjunto de dados que o próprio componente controla e pode mudar ao longo do tempo, como o estado de um botão ligado ou desligado. Por exemplo, você pode passar uma prop chamada `cor` para um botão, e ele vai usar essa cor. Mas se o botão precisa lembrar se foi clicado ou não, isso fica no state dele. Quer tentar me dizer qual desses dois você usaria para mudar o texto de um botão quando o usuário clicar?

**3. Learner:** Me dá um exemplo na prática com useState.

*wants_example → example (worked_example); asked for an example; first token 25.8 s, total 46.7 s; 3197 tokens, $0.0016*

**Mino:** Beleza, vamos ver um exemplo prático com o **useState**, que é o jeito que o React oferece pra guardar e mudar o estado dentro de um componente. Imagina um botão que, quando você clica, troca o texto entre "Ligado" e "Desligado". O estado aqui é se o botão está ligado ou desligado. ```jsx import React, { useState } from 'react'; function BotaoLigaDesliga() { const [ligado, setLigado] = useState(false); // começa desligado function alternar() { setLigado(!ligado); // troca o estado pro contrário } return ( <button onClick={alternar}> {ligado ? 'Ligado' : 'Desligado'} </button> ); } ``` O que acontece aqui? 1. `useState(false)` cria uma variável de estado chamada `ligado`, que começa como `false`. 2. `setLigado` é a função que muda esse estado. 3. Quando o botão é clicado, a função `alternar` é chamada, que troca o valor de `ligado`. 4. O texto do botão muda conforme o valor de `ligado`. Agora, pensa num componente que recebe uma prop chamada `cor` e mostra um quadrado nessa cor. Onde estaria o uso de props e onde o uso de state nesse caso? Qual desses dois conceitos você identifica em cada parte?

### advanced_ahead — Advanced learner shows they are ahead

**1. Learner:** Quero aprender cálculo, começando do básico.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 88.0 s, total 110.9 s; 4047 tokens, $0.0024*

**Mino:** Imagina que você está dirigindo um carro e quer saber a velocidade naquele exato momento, não a média da viagem toda. A velocidade instantânea é como a **derivada**: ela mede a taxa de variação, ou seja, o quanto a posição do carro muda em relação ao tempo, naquele instante. A derivada é justamente isso: a **taxa de variação** de uma função. Se a função mostra a posição do carro ao longo do tempo, a derivada diz a velocidade, que é a mudança da posição por unidade de tempo. Quer ver se pegou? Se a posição do carro muda muito rápido num curto intervalo, a derivada será alta ou baixa?

**2. Learner:** Então a derivada de x² é 2x, e pela regra da cadeia a de sin(x²) é 2x·cos(x²), certo?

*asks → answer (definition); a direct question — answer it first; first token 42.8 s, total 55.5 s; 3751 tokens, $0.0016*

**Mino:** Sim, a derivada de x² é 2x, porque a taxa de variação da função x² cresce proporcionalmente a 2 vezes o valor de x. E a derivada de sin(x²) é mesmo 2x·cos(x²), aplicando a regra da cadeia: você deriva o "dentro" (x²) e multiplica pela derivada do "fora" (sin) avaliada no "dentro". Quer continuar daí e ver como a derivada se relaciona com a inclinação da reta tangente?

**3. Learner:** Beleza, pode seguir no meu nível.

*neutral → teach (definition); continue the lesson; first token 41.2 s, total 60.5 s; 3670 tokens, $0.0017*

**Mino:** Olha só: se você tem uma função que cresce sempre do mesmo jeito, tipo f(x) = 3x, isso é uma **função linear**. O gráfico dela é uma reta, e a taxa de variação é constante — aqui, 3. Isso significa que pra cada aumento de 1 no x, o valor de f(x) aumenta 3. Função linear é isso: uma função cujo gráfico é uma reta, e a variação entre x e f(x) é sempre a mesma. Qual é a taxa de variação da função f(x) = 5x?

Blocks: quiz

### confused — Confused learner ("não entendi")

**1. Learner:** Quero entender como funciona a fotossíntese.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 84.6 s, total 110.7 s; 3868 tokens, $0.0021*

**Mino:** Imagina uma planta no sol. Ela usa a luz do sol pra fazer sua própria comida, tipo uma cozinha natural. Isso é a **fotossíntese**: o processo onde plantas pegam luz, água e gás carbônico e transformam em açúcar (alimento) e oxigênio. A luz é a energia que faz essa transformação acontecer. Sem luz, a planta não consegue produzir seu alimento. Qual desses elementos a planta usa para fazer a fotossíntese? 1. Luz, água e gás carbônico 2. Luz, oxigênio e água 3. Gás carbônico, oxigênio e luz

**2. Learner:** não entendi

*confused → correct (analogy); lost — a different way in; first token 26.0 s, total 41.8 s; 3022 tokens, $0.0014*

**Mino:** Olha só, pensa numa fábrica de biscoitos. Essa fábrica precisa de três coisas: energia (a eletricidade), matéria-prima (a farinha) e um lugar pra trabalhar (a cozinha). A planta é essa fábrica, só que ela faz comida dela mesma. Na fotossíntese, a luz do sol é a eletricidade, a água é a farinha, e o gás carbônico é o ar que entra na cozinha. Com esses ingredientes, a planta "cozinha" o açúcar, que é o alimento dela, e ainda solta oxigênio, que é como o cheiro gostoso que sai da cozinha. Faz sentido pensar na luz do sol como a energia que liga a fábrica da planta?

**3. Learner:** Ah, agora ficou mais claro. E onde entra a clorofila nisso?

*asks → answer (analogy); a direct question — answer it first; first token 29.6 s, total 47.9 s; 3852 tokens, $0.0017*

**Mino:** A clorofila é tipo o painel solar da planta. Ela fica nas folhas e captura a luz do sol, transformando essa luz em energia que a planta vai usar pra fazer o açúcar. Sem a clorofila, a planta não conseguiria aproveitar a luz direito, igual uma casa sem painel solar não gera energia. Se a luz é a eletricidade da fábrica, a clorofila é o equipamento que capta essa eletricidade pra ligar as máquinas. Faz sentido assim?

### short_followup — Short follow-up question ("E a de x³?")

**1. Learner:** Me ensina derivadas.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 52.2 s, total 60.8 s; 3894 tokens, $0.0022*

**Mino:** Imagina que você está dirigindo e quer saber a velocidade do carro num instante exato, não só a média da viagem. A velocidade naquele momento é a mudança da distância em relação ao tempo, mas olhando só um ponto, não um intervalo. A **derivada** é isso: ela mede a taxa de variação instantânea de uma função. Ou seja, mostra como a função está mudando exatamente num ponto, não numa média entre dois pontos. Por exemplo, se a distância que você percorre é dada por uma função do tempo, a derivada dessa função no tempo t te dá a velocidade naquele instante t. Qual é a diferença entre a taxa de variação média e a taxa de variação instantânea?

**2. Learner:** Qual a derivada de x²?

*asks → answer (definition); a direct question — answer it first; first token 38.9 s, total 86.5 s; 3676 tokens, $0.0016*

**Mino:** A derivada de x² é 2x. Isso acontece porque a derivada mede a inclinação da reta tangente ao gráfico da função naquele ponto, e para x² essa inclinação cresce proporcionalmente a 2 vezes o valor de x. Se você imaginar o gráfico de x², a inclinação da curva em x=1 é 2·1=2, e em x=3 é 2·3=6. Quer ver como isso aparece no cálculo?

**3. Learner:** E a de x³?

*asks → answer (definition); a direct question — answer it first; first token 53.6 s, total 82.6 s; 4783 tokens, $0.0024*

**Mino:** A derivada de x³ é 3x². Isso vem da regra geral que a derivada de xⁿ é n vezes x elevado a n-1. Ou seja, você pega o expoente, multiplica pela função, e diminui um no expoente. Quer que eu mostre como isso aparece usando o quociente incremental, a definição formal da derivada?

### ambiguous — Ambiguous request ("redes")

**1. Learner:** Quero aprender sobre redes.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 59.2 s, total 68.6 s; 3750 tokens, $0.0020*

**Mino:** Imagina que você tem dois computadores em casa e quer que eles troquem arquivos ou joguem juntos. Se você ligar esses computadores com um cabo ou via Wi-Fi, eles formam uma **rede de computadores**. Ou seja, uma rede de computadores é um grupo de dispositivos conectados entre si para compartilhar informações e recursos. Agora, me diz: qual é o principal objetivo de conectar computadores em uma rede?

**2. Learner:** As de computador, tipo internet.

*asks → answer (definition); a direct question — answer it first; first token 61.1 s, total 79.8 s; 3577 tokens, $0.0015*

**Mino:** Sim, a internet é um tipo de rede de computadores, só que muito maior e mais complexa. Ela conecta milhões de dispositivos no mundo todo para que eles possam trocar informações, como páginas, vídeos e mensagens. Agora, pensa: além da internet, que outro tipo de rede você acha que existe só dentro de uma casa ou empresa?

### misconception — Confident misconception

**1. Learner:** Quero aprender física básica, começando por queda livre.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 35.1 s, total 51.2 s; 3866 tokens, $0.0022*

**Mino:** Imagina que você solta uma bola no ar, sem empurrar, só deixa cair. Ela vai cair direto para o chão, certo? Isso é um exemplo clássico de **queda livre**. Agora, o que é queda livre? É o movimento de um objeto que está caindo só por causa da gravidade, sem nada segurando ou empurrando ele, e sem o ar atrapalhar. Ou seja, a única força que age nele é a força da gravidade. Se tivesse vento ou resistência do ar, a bola não cairia exatamente assim — ela poderia ir mais devagar ou desviar. Mas na queda livre, só a gravidade manda. Qual dessas situações é um exemplo de queda livre? 1) Uma bola caindo no vácuo (sem ar) 2) Uma bola caindo na chuva com vento forte 3) Uma bola rolando numa rampa Qual você acha?

**2. Learner:** Isso é fácil: objetos mais pesados caem mais rápido que os leves. Uma bola de boliche sempre chega no chão antes de uma bolinha de gude.

*confused → correct (analogy); lost — a different way in; first token 60.0 s, total 85.7 s; 3788 tokens, $0.0018*

**Mino:** Tá, vamos trocar a ideia da bola caindo por outra coisa que a gente vê todo dia: imagine que você está numa piscina e solta duas bolas, uma de isopor e outra de chumbo, lá embaixo da água, ao mesmo tempo. Qual delas vai chegar no fundo primeiro? A de chumbo, né? Porque a água oferece resistência, e o chumbo é mais pesado, então ele afunda mais rápido. Agora, tira a água e imagina que as bolas estão caindo no ar, que é muito menos denso que a água, mas ainda assim oferece uma resistência. A bola de boliche e a bolinha de gude caem quase na mesma velocidade, porque o ar não é tão forte para fazer diferença grande. Se a gente tirasse o ar, como num lugar sem atmosfera, as duas cairiam exatamente igual, porque a única força que atua é a gravidade — isso é a **queda livre**: quando só a gravidade age, sem resistência do ar. Quer tentar dizer qual é a diferença entre o que acontece na piscina e o que acontece na queda livre?

### wrong_quiz — Wrong quiz answer

**1. Learner:** Quero aprender frações.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 31.2 s, total 55.4 s; 3744 tokens, $0.0020*

**Mino:** Imagina que você tem uma pizza dividida em 4 pedaços iguais e come 1 pedaço. Esse 1 pedaço é uma parte do todo, certo? A fração é justamente isso: uma forma de mostrar uma parte de um todo dividido em partes iguais. A fração é escrita assim: 1/4. O número de cima (1) mostra quantas partes você tem, e o número de baixo (4) mostra em quantas partes o todo foi dividido. Qual fração representa 3 pedaços de uma pizza dividida em 5 partes iguais?

**2. Learner:** Me testa com uma pergunta de múltipla escolha.

*wants_practice → quiz (definition); asked to be tested; first token 29.4 s, total 51.7 s; 2865 tokens, $0.0013*

**Mino:** Aqui vai uma pergunta pra você testar se entendeu o que é uma fração: Qual você escolhe?

Blocks: quiz

**3. Learner:** 8/3, porque o total vem primeiro

*wrong → correct (analogy); wrong — name the misconception, switch; first token 38.7 s, total 47.5 s; 3024 tokens, $0.0014*

**Mino:** Olha só, pensa numa barra de chocolate dividida em 4 pedaços iguais. Se você come 1 pedaço, você comeu 1 parte de 4, certo? A fração é como dizer "1 pedaço de 4 pedaços". O número de cima (numerador) é quantos pedaços você tem, e o de baixo (denominador) é em quantos pedaços o chocolate foi dividido. No seu exemplo, 8/3, o 8 é o numerador (quantos pedaços você tem) e o 3 é o denominador (em quantos pedaços o todo foi dividido). O total não vem primeiro, vem o número de partes que você tem. Se eu tenho uma barra dividida em 3 pedaços e como 2, qual fração representa isso?

### tired — Learner giving up ("tô cansado")

**1. Learner:** Quero aprender sobre a Independência do Brasil.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 20.7 s, total 38.9 s; 3813 tokens, $0.0021*

**Mino:** Imagina que o Brasil era como uma casa que pertencia a Portugal. Tudo que acontecia dentro dessa casa, Portugal decidia. A Independência do Brasil foi o momento em que essa casa deixou de ser controlada por Portugal e passou a ser governada pelos próprios brasileiros. Isso aconteceu em 7 de setembro de 1822, quando Dom Pedro I declarou que o Brasil não era mais uma colônia, mas um país livre. Esse ato marcou o fim do domínio português e o começo do Brasil como uma nação independente, com suas próprias leis e governo. Agora me diz: por que a data de 7 de setembro de 1822 é tão importante para a história do Brasil?

**2. Learner:** Tô cansado, não aguento mais por hoje.

*tired → motivate (summary); tired — close the loop kindly; first token 5.6 s, total 8.6 s; 2781 tokens, $0.0012*

**Mino:** Hoje você já entendeu que a Independência do Brasil foi o momento em que o país deixou de ser controlado por Portugal e passou a ser governado por si mesmo, com a famosa data de 7 de setembro de 1822. Na próxima vez, a gente vai ver o que levou a esse momento, as causas que fizeram o Brasil querer se tornar independente. Se quiser, a gente para por aqui hoje, sem problema.

### steps_mode — "Explica de outro jeito, passo a passo"

**1. Learner:** Quero aprender a resolver equações do primeiro grau.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 32.9 s, total 36.0 s; 4005 tokens, $0.0023*

**Mino:** Olha só: se eu te disser que 2x + 3 = 7, o que você acha que isso é? É uma pergunta, um problema, ou uma coisa que a gente chama de equação. Agora vem a parte boa: uma **equação do primeiro grau** é uma conta que tem um número desconhecido (a gente chama isso de **variável**, aqui é o x) e que aparece só com potência 1 — ou seja, x, não x², nem x³. O objetivo é descobrir o valor desse x que faz a conta ficar certa. No exemplo 2x + 3 = 7, a gente quer saber qual número, multiplicado por 2 e somado a 3, dá 7. Isso é uma equação do primeiro grau. Me diz: no exemplo 2x + 3 = 7, qual é a variável e qual é o número que a gente quer descobrir?

**2. Learner:** Não entendi. Explica de outro jeito, passo a passo.

*confused → correct (steps); lost — a different way in; first token 7.7 s, total 9.7 s; 3184 tokens, $0.0015*

**Mino:** Beleza, vamos por partes, passo a passo. 1. Uma **equação** é como uma balança: o que está do lado esquerdo tem que valer o mesmo que o que está do lado direito. Por isso tem o sinal de igualdade (=). 2. A **equação do primeiro grau** tem um número que a gente não sabe, que chamamos de **variável** (geralmente o x), e ele aparece só com potência 1 — tipo x, não x². 3. Exemplo: 2x + 3 = 7. Aqui, 2x + 3 está de um lado da balança, e 7 do outro. 4. O que a gente quer é descobrir qual número, no lugar do x, deixa os dois lados iguais. 5. Para isso, a gente vai mexendo na equação, fazendo operações iguais dos dois lados, até o x ficar sozinho. Agora me diz: nessa equação 2x + 3 = 7, o que você acha que a gente pode fazer primeiro para tentar descobrir o valor do x?

### guide_me — "Guide me" (must not give the answer)

**1. Learner:** I want to learn how to calculate percentages.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 27.5 s, total 33.0 s; 3803 tokens, $0.0021*

**Mino:** Imagine you have a pizza cut into 100 equal slices. If you eat 25 slices, you ate 25 out of 100 slices. That’s exactly what a **percentage** means: a part out of 100. So, 25 slices eaten is 25%. The percent sign (%) just means “per hundred.” When you say 25%, you’re saying 25 parts out of 100. If I say 40%, how many slices out of 100 does that represent?

Blocks: quiz

**2. Learner:** What is 15% of 80? Don't tell me the answer, guide me.

*wants_guide → guide (socratic); asked to be guided, not told; first token 3.1 s, total 5.5 s; 2777 tokens, $0.0012*

**Mino:** Ok, you want to find 15% of 80. Since 15% means 15 out of 100, how could you write 15% as a fraction or a decimal to make it easier to multiply by 80?

**3. Learner:** Hmm, maybe I multiply 80 by 0.15?

*asks → answer (socratic); a direct question — answer it first; first token 9.5 s, total 10.1 s; 3679 tokens, $0.0015*

**Mino:** Yes, multiplying by 0.15 is the right move. Now, what do you get when you multiply 80 by 0.15? That will be 15% of 80.

### direct_fact — Direct fact question (answer first)

**1. Learner:** Qual a capital da Austrália?

*asks → answer (conceptual_explanation); a direct question — answer it first; first token 14.4 s, total 16.8 s; 4404 tokens, $0.0020*

**Mino:** A capital da Austrália é Canberra. Ela foi escolhida como capital porque fica entre as duas maiores cidades do país, Sydney e Melbourne, para evitar rivalidades e garantir uma localização neutra. Você sabe em que estado ou território da Austrália Canberra está localizada?

**2. Learner:** E da Nova Zelândia?

*asks → answer (conceptual_explanation); a direct question — answer it first; first token 4.4 s, total 5.1 s; 3509 tokens, $0.0015*

**Mino:** A capital da Nova Zelândia é Wellington. Ela fica na parte sul da ilha norte do país e é conhecida por ser um centro político e cultural importante. Quer voltar a falar da Austrália ou quer explorar mais sobre a Nova Zelândia?

### off_topic — Off-topic question mid-lesson

**1. Learner:** Quero aprender química orgânica.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 12.2 s, total 15.7 s; 4167 tokens, $0.0026*

**Mino:** Olha só: quando você pensa em química orgânica, o que vem à cabeça? Talvez plantas, alimentos, remédios... Isso faz sentido, porque a química orgânica é o estudo dos compostos que têm carbono — o elemento que forma a base da vida na Terra. Agora vem a parte boa: **química orgânica** é a área da química que estuda os compostos que contêm carbono, especialmente aqueles ligados a hidrogênio, oxigênio, nitrogênio e outros elementos. Esses compostos são chamados de **compostos orgânicos**. Por exemplo, o açúcar que você come, a gasolina que abastece carros, e até o DNA no seu corpo são compostos orgânicos. Qual desses exemplos é um composto orgânico? a) Água (H₂O) b) Gás carbônico (CO₂) c) Açúcar (C₆H₁₂O₆) Qual você acha?

**2. Learner:** Aliás, quem ganhou a Copa do Mundo de 2002?

*off_topic → teach (definition); continue the lesson; first token 6.2 s, total 7.5 s; 3532 tokens, $0.0016*

**Mino:** Tá, deixa eu te mostrar na prática: o açúcar, que tem carbono, hidrogênio e oxigênio, é um exemplo clássico do que a química orgânica estuda. Ela é a parte da química que foca nos compostos que têm carbono na sua estrutura. Então, **química orgânica** é o estudo dos compostos que contêm carbono, especialmente ligados a hidrogênio, oxigênio, nitrogênio e outros elementos. Esses compostos são chamados de **compostos orgânicos**. Agora, me diz: qual desses compostos a química orgânica estuda? a) Sal de cozinha (NaCl) b) Metano (CH₄) c) Água (H₂O) Qual você acha?

### long_session — Long session (9 turns): continuity and repetition

**1. Learner:** Quero aprender estatística básica.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 10.7 s, total 14.0 s; 3846 tokens, $0.0021*

**Mino:** Imagina que você quer entender quantas horas seus amigos estudam por semana. Você anota os números, vê qual é a média, quem estuda mais, quem estuda menos, e tenta tirar conclusões. Isso é estatística. **Estatística** é a ciência que coleta, organiza, analisa e interpreta dados para ajudar a entender informações e tomar decisões. Agora, me diz: se você tem os dados de estudo dos seus amigos, qual seria o primeiro passo para usar a estatística? Organizar os dados, analisar ou interpretar?

**2. Learner:** Ok, pode continuar.

*neutral → teach (definition); continue the lesson; first token 4.3 s, total 8.2 s; 3461 tokens, $0.0017*

**Mino:** Imagina que você anotou quantas horas cada amigo estuda por semana: 5, 7, 3, 6, 4. Agora, você quer entender esses números para saber, por exemplo, qual é a média ou quem estuda mais. **Estatística** é exatamente isso: a ciência que estuda como coletar, organizar, analisar e interpretar dados para tirar conclusões úteis. Sem estatística, esses números seriam só uma lista sem sentido. Com ela, você transforma dados em informação. Agora, me diz: qual dessas ações faz parte da estatística? 1) Coletar dados 2) Jogar dados 3) Ignorar dados

Blocks: quiz

**3. Learner:** Me dá um exemplo do dia a dia.

*wants_example → example (worked_example); asked for an example; first token 2.4 s, total 4.4 s; 2984 tokens, $0.0014*

**Mino:** Olha só um exemplo do dia a dia: você quer saber qual é o sabor de sorvete preferido da sua turma na escola. Você pergunta para 20 colegas e anota as respostas: chocolate, baunilha, morango, chocolate, chocolate, baunilha... Depois, você organiza esses dados, contando quantas vezes cada sabor apareceu. Por fim, você analisa para descobrir qual é o sabor mais popular e interpreta isso para decidir qual sorvete comprar para a festa. Nesse caso, a estatística apareceu em cada passo: coletar as respostas, organizar as informações, analisar os resultados e interpretar para tomar uma decisão. Agora, pensa num exemplo parecido: e se você quisesse saber qual é o esporte favorito dos seus amigos? Como você usaria a estatística para isso?

**4. Learner:** Qual a diferença entre média e mediana?

*asks → answer (worked_example); a direct question — answer it first; first token 5.8 s, total 7.8 s; 4012 tokens, $0.0018*

**Mino:** Média é o valor que você obtém somando todos os números e dividindo pelo total de números. Mediana é o número que fica no meio quando você organiza os dados em ordem. Vamos ver um exemplo: imagine os números 3, 5, 7, 9, 11. A média é (3+5+7+9+11) ÷ 5 = 35 ÷ 5 = 7. A mediana é o número do meio, que é 7, porque quando você coloca os números em ordem, 7 está no centro. Agora, se os números fossem 3, 5, 7, 9, qual seria a mediana?

**5. Learner:** Faz sentido. Continua.

*neutral → teach (worked_example); continue the lesson; first token 6.5 s, total 10.1 s; 4064 tokens, $0.0020*

**Mino:** Imagina que você quer saber quantos livros seus amigos leram no último mês. Você pergunta para cinco amigos e anota: 2, 4, 3, 5, 6 livros. Agora, vamos ver o que a estatística faz com esses números. Primeiro, você **coleta** os dados — que são esses números que você anotou. Depois, você **organiza** os dados, colocando-os em ordem: 2, 3, 4, 5, 6. Agora, você pode **analisar** esses dados calculando a média: (2+3+4+5+6) ÷ 5 = 20 ÷ 5 = 4 livros por amigo. Por fim, você **interpreta** esse resultado: em média, seus amigos leram 4 livros no mês. Essa sequência — coletar, organizar, analisar e interpretar — é o que a gente chama de **estatística**. Agora, me diz: qual é a primeira coisa que você faz quando quer usar estatística com um conjunto de dados?

Blocks: quiz

**6. Learner:** Resume o que vimos até agora.

*wants_summary → summarize (summary); asked for a summary; first token 1.8 s, total 3.6 s; 3511 tokens, $0.0015*

**Mino:** Aqui está o que vimos até agora, passo a passo: Agora me diz: se você tem uma lista de números, qual é o passo que vem antes de calcular a média?

Blocks: steps

**7. Learner:** Me testa.

*wants_practice → quiz (summary); asked to be tested; first token 2.4 s, total 4.5 s; 3569 tokens, $0.0016*

**Mino:** Vamos ver se você entendeu o que é estatística com essa pergunta:

Blocks: quiz

**8. Learner:** Acho que a mediana é o valor do meio quando os dados estão ordenados.

*answering → correct (summary); grading the answer to last turn's question; first token 2.7 s, total 3.8 s; 3755 tokens, $0.0016*

**Mino:** Você acertou: a mediana é mesmo o valor do meio quando os dados estão organizados em ordem. Isso é importante porque ela mostra o ponto central dos dados, diferente da média, que é a soma dividida pelo número de valores. Agora, para resumir o que é estatística: é a ciência que ajuda a gente a entender informações coletando dados, organizando esses dados, analisando números como média e mediana, e interpretando os resultados para tomar decisões. Me diz uma coisa: por que você acha que organizar os dados antes de analisar é importante?

**9. Learner:** Valeu! O que vem depois?

*neutral → teach (summary); continue the lesson; first token 3.0 s, total 5.1 s; 4377 tokens, $0.0020*

**Mino:** Imagina que você quer entender quantas horas as pessoas passam assistindo séries por semana. Você anota esses números, organiza, calcula a média, vê qual é o valor do meio — tudo para entender melhor esse hábito. Isso é o que a **estatística** faz: ela é a ciência que estuda como coletar, organizar, analisar e interpretar dados para tirar conclusões úteis sobre o mundo. Agora, me diz: qual dessas ações não faz parte da estatística? 1) Organizar dados 2) Analisar dados 3) Inventar dados

Blocks: quiz

### lang_es — Spanish course

**1. Learner:** Quiero aprender los tiempos verbales del inglés.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 13.4 s, total 14.7 s; 3901 tokens, $0.0022*

**Mino:** Imagina que quieres contar algo que haces todos los días, como "I eat breakfast" (yo desayuno). Eso que usaste para decir cuándo pasa la acción es un **tiempo verbal**. Un **tiempo verbal** es la forma que tiene un verbo para mostrar cuándo sucede la acción: si es ahora, antes o después. En inglés, los tiempos verbales nos ayudan a entender si algo pasa en el presente, en el pasado o en el futuro. ¿Puedes decirme qué tiempo verbal usaste en la frase "I eat breakfast"?

**2. Learner:** No entiendo la diferencia entre present perfect y past simple.

*confused → correct (analogy); lost — a different way in; first token 4.1 s, total 6.4 s; 3002 tokens, $0.0014*

**Mino:** Piensa en una foto y en un álbum de fotos. El **past simple** es como una foto: muestra un momento exacto que ya pasó, como "I ate breakfast yesterday" (comí desayuno ayer). Es algo que terminó y está fijo en el pasado. El **present perfect** es como un álbum de fotos: no muestra solo un momento, sino una colección de experiencias o acciones que tienen conexión con el presente. Por ejemplo, "I have eaten breakfast" (he desayunado) quiere decir que en algún momento antes de ahora, y que importa para el presente, ya comiste. ¿Puedes decirme cuál de los dos, la foto o el álbum, usarías para contar algo que hiciste ayer?

**3. Learner:** ¿Me das un ejemplo?

*wants_example → example (worked_example); asked for an example; first token 4.7 s, total 6.4 s; 2999 tokens, $0.0014*

**Mino:** Vale, vamos con un ejemplo concreto para que se vea claro. Imagina que ayer fuiste a un restaurante y comiste una hamburguesa. Si quieres contar eso, dirías: "I ate a burger yesterday." Aquí usas el **past simple** porque hablas de algo que pasó en un momento específico y ya terminó: ayer. Ahora, imagina que hoy alguien te pregunta si alguna vez has probado una hamburguesa. Tú respondes: "I have eaten a burger." Aquí usas el **present perfect** porque no dices cuándo, solo que en algún momento antes de ahora, la experiencia pasó y sigue siendo relevante. ¿Puedes pensar en una acción que hiciste en un momento específico y decirla en inglés usando el tiempo verbal que crees correcto?

### lang_switch — Language consistency (EN question in a PT course)

**1. Learner:** Quero aprender biologia celular.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 10.0 s, total 13.1 s; 3914 tokens, $0.0022*

**Mino:** Imagina que você está olhando para uma gota d’água no microscópio. Dentro dela, existem pequenas unidades que fazem tudo funcionar: elas são as células. A célula é a menor parte viva que consegue realizar todas as funções essenciais para a vida, como crescer, se reproduzir e responder ao ambiente. Então, a **célula** é a unidade básica da vida — o tijolinho que constrói todos os seres vivos, desde uma planta até você. Agora, me diz: por que a célula é considerada a unidade básica da vida?

**2. Learner:** What does the mitochondria actually do?

*asks → answer (definition); a direct question — answer it first; first token 5.3 s, total 6.4 s; 3632 tokens, $0.0016*

**Mino:** A mitocôndria é a usina de energia da célula. Ela pega o alimento que você come e transforma em uma molécula chamada ATP, que é como a bateria que alimenta todas as funções da célula. Quer ver? Sem ATP, a célula não conseguiria fazer nada, nem crescer, nem se mover. Agora, me conta: você já ouviu falar em ATP antes?

**3. Learner:** I don't get it.

*confused → correct (analogy); lost — a different way in; first token 3.8 s, total 6.5 s; 3100 tokens, $0.0014*

**Mino:** Pensa numa fábrica de brinquedos. Essa fábrica tem tudo que precisa pra criar um brinquedo do zero: máquinas, trabalhadores, matéria-prima. A célula é como essa fábrica, só que para a vida. Ela tem tudo que precisa pra crescer, se reproduzir e funcionar. Cada parte da célula é uma “máquina” ou “departamento” que faz um trabalho específico. A mitocôndria, por exemplo, é a máquina que gera energia pra fábrica funcionar. Então, a célula é a menor unidade que consegue fazer tudo isso sozinha — como uma fábrica completa, só que minúscula. Agora, me diz: nessa analogia, o que a célula representa?

