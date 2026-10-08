# Professor eval — 2026-10-08

Revision `baad0d8`. 16 scenarios, 48 learner turns, driven in-process through `ProfessorEngine` against a fresh local database with the production provider routing (primary anthropic, fallbacks openai, NOEMA_AI_ROUTING anthropic:0,openai:100). Judge: economy tier, prompt eval.judge_professor v1.

Prompt versions: moves {'correct': 3, 'answer': 4} (others v1), route v4, curriculum v2.

**Deterministic checks: 189/193 passed.** **Total cost: $0.2945** (tutor $0.2833, judge $0.0112). Models that answered (calls): openai/gpt-4.1-mini-2025-04-14 x67, openai/gpt-4.1-2025-04-14 x47.

Cost is metered from each provider response and priced at published rates; for comparison, ai_usage recorded 200658 tokens and $0.2833 for the tutor turns; the provider responses metered 200658 tokens.

PEDAGOGY records parsed: 42/48 replies; with mastery evidence: 18.

## Reading this run (written by hand after the run)

This is the second live run. It measures the fixes for the 2026-10-07 findings at
`baad0d8` (branch `professor/eval-fixes`, based on `evals/professor` / PR
#269). Routing matched production today, `NOEMA_AI_ROUTING=anthropic:0,openai:100`
(Anthropic is out of credit), so OpenAI answered every call: gpt-4.1 for teaching
turns (standard/premium tier), and gpt-4.1-mini for routing, cards and the judge.
The 10-07 run reached OpenAI only as a fallback on its default model
(gpt-4.1-mini for everything), so each turn costs about 3x more here. That
comes from production routing, not from these changes.

**The deterministic checks are the gate. The judge only shows a trend.**

### Before / after (deterministic checks)

"10-07 rescored" means the stored 10-07 replies run through today's checks with no
model calls, so the two right-hand check columns use the same yardstick. Checks
added since 10-07: `stays` (beginner turn 2 skips no lesson), `answer_first` on
the misconception turn (the correction comes in the first sentence), and
`moves_on` (long session turn 9). The misconception signal now accepts only
`answering` or `wrong`.

| scenario | 10-07 as published | 10-07 rescored | 10-08 | judge mean 10-07 → 10-08 | judge verdict | cost 10-07 → 10-08 |
|---|---|---|---|---|---|---|
| beginner_zero | 14/15 | 14/16 | 15/16 | 5.0 → 5.0 | pass → pass | $0.0062 → $0.0195 |
| intermediate_react | 12/12 | 12/12 | 12/12 | 5.0 → 5.0 | pass → pass | $0.0065 → $0.0201 |
| advanced_ahead | 14/14 | 14/14 | 14/14 | 5.0 → 5.0 | pass → pass | $0.0065 → $0.0205 |
| confused | 17/17 | 17/17 | 17/17 | 4.9 → 4.9 | pass → pass | $0.0060 → $0.0178 |
| short_followup | 13/13 | 13/13 | 13/14 | 4.7 → 4.9 | fail → fail | $0.0070 → $0.0210 |
| ambiguous | 7/7 | 7/7 | 7/7 | 5.0 → 5.0 | pass → pass | $0.0040 → $0.0097 |
| misconception | 8/9 | 8/10 | 9/10 | 4.8 → 5.0 | pass → pass | $0.0046 → $0.0122 |
| wrong_quiz | 12/12 | 12/12 | 12/12 | 4.9 → 4.7 | pass → fail | $0.0055 → $0.0177 |
| tired | 7/7 | 7/7 | 7/7 | 5.0 → 4.8 | pass → pass | $0.0039 → $0.0054 |
| steps_mode | 8/8 | 8/8 | 8/8 | 5.0 → 5.0 | pass → pass | $0.0045 → $0.0123 |
| guide_me | 11/11 | 11/11 | 11/11 | 4.9 → 5.0 | fail → pass | $0.0055 → $0.0146 |
| direct_fact | 9/9 | 9/9 | 9/9 | 4.8 → 4.7 | pass → pass | $0.0041 → $0.0117 |
| off_topic | 5/8 | 5/8 | 7/7 | 3.8 → 5.0 | fail → pass | $0.0048 → $0.0119 |
| long_session | 30/33 | 29/34 | 30/31 | 4.9 → 5.0 | pass → pass | $0.0174 → $0.0638 |
| lang_es | 9/9 | 9/9 | 9/9 | 5.0 → 5.0 | pass → pass | $0.0056 → $0.0150 |
| lang_switch | 7/9 | 7/9 | 9/9 | 5.0 → 5.0 | pass → pass | $0.0059 → $0.0212 |
| **total** | **183/193** | **182/196** | **189/193** | | | **$0.098 → $0.295** |

The number of checks per run differs because `redefinition` and `repetition` are
written only when they fail.

### The six fixes, as this run saw them

1. **Language: fixed.** "What does the mitochondria actually do?" got "The
   mitochondria is the part of the cell that makes energy…", and the reply to "I don't get
   it." stayed in English. The directive now names the language read from the
   learner's own messages ("Language: reply in English").
2. **Route classification (route v4): partly fixed.** The beginner's "Então uma
   variável é tipo uma caixinha…?" is now `asks` → answer (it was `knows` →
   advance), but the turn still left lesson 0. The cause was the tutor's
   `next_action: move_on`, not the router (see "Found by this run" below). The
   misconception was no longer read as `confused`. The classifier returned `wrong`
   instead, a quiz-verdict value the schema offered and no message rule
   handled, so the turn fell to TEACH.
3. **Misconception corrected: yes in the reply, no in the routing.** The reply was
   right ("Quase — mas olha só: se não tivesse ar, uma bola de boliche e uma
   bolinha de gude caem exatamente na mesma velocidade… na Lua… um martelo e
   uma pena…"), and its first sentence says the claim is wrong. The `move` check
   failed only because of the `wrong` → TEACH routing above.
4. **"O que vem depois?": fixed.** It now reads as `wants_next` → advance. The
   journey moved to the next concept ("Variáveis discretas e contínuas"), and
   the reply spent one line on the previous concept before moving on. The long
   session no longer defines **estatística** again (0 redefinition failures,
   down from 3). Turn 2 opens with "só pra lembrar rapidinho: …" and moves on.
5. **Lesson advance: fixed at the root.** gpt-4.1(-mini) never wrote the
   `<PEDAGOGY>` record: 0 of 55 replies on 10-07 had one, so there was no
   mastery evidence and no `current_concept`, and nothing could advance. The
   directive now asks for the record at its end, with the plan's concept names.
   It came back on 42 of 48 replies, 18 of them with mastery evidence. Concept
   names are mapped onto the plan's, and a concept that landed moves the focus
   to the lesson's next one. The long session reached lesson 2 of module 1.
6. **ai_usage: fixed.** For the tutor turns ai_usage recorded 200 658 tokens and
   $0.2833, exactly what the provider responses metered. On 10-07 it recorded
   144 130 of 175 181 tokens and $0.00. Each row now names the model that served
   the call (`gpt-4.1-2025-04-14`, `gpt-4.1-mini-2025-04-14`), never "unknown".

This run also confirms the off-topic fix from the 10-07 branch: "O Brasil ganhou
a Copa do Mundo de 2002… Quer voltar pra química orgânica?".

### Found by this run, fixed afterwards (covered by CI tests, not re-run live)

- **The tutor's `move_on` skipped whole lessons.** With the record back, an
  old rule fired: an ANSWER whose record said `next_action: move_on` skipped
  the current lesson. The beginner lost lessons 0 and 1 in two turns, and the
  long session skipped lesson 1 after one question. That skip is also why the
  long session's summary on turn 6 covered the new lesson and missed
  "média/mediana". The rule is removed: whether a learner is ahead is decided by
  the router's `ahead`, before the reply.
- **The classifier answered `wrong`.** The route schema no longer offers
  `right` or `wrong`, and `settle_route` reads either one as `answering`.
- **A wrong quiz click was called right.** On wrong_quiz turn 3, the judge's
  fail, the tutor replied "Perfeito, 1/6 é uma fração…" to an answer the server
  had graded wrong. The tutor never saw the verdict or the answer key. The
  directive now carries both ('Quiz result, graded by the server: "1/6" is wrong.
  The right answer is "4/6".').

### Not fixed

- **short_followup turn 3** repeats 39% of turn 2's 5-grams. It reuses the
  frame from x² ("A derivada de x³ é 3x². Isso vem da regra…"), so the same
  answer template appears twice, and the judge called it not brief. This was
  outside this round's scope.
- **The judge** still runs on gpt-4.1-mini and gives 4.7 to 5.0 almost
  everywhere, so its scores show a trend only.
- **One run was lost.** The first 10-08 attempt finished all 16 scenarios ($0.30)
  and then failed while writing the report: since #265 the router's `Situation`
  carries `LearnerState` with datetimes. `baad0d8` fixes that, and this report
  comes from the second attempt. The two runs together cost about $0.60.

## Per criterion (judge, 1 to 5, mean over all replies)

| correctness | clarity | pedagogy | difficulty_fit | continuity | non_repetition |
|---|---|---|---|---|---|
| 5.0 | 4.9 | 4.8 | 5.0 | 5.0 | 5.0 |

## Per scenario

| scenario | turns | checks | correctness | clarity | pedagogy | difficulty fit | continuity | non repetition | verdict | avg latency | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| beginner_zero | 3 | 15/16 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 6.4 s | $0.0195 |
| intermediate_react | 3 | 12/12 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 5.7 s | $0.0201 |
| advanced_ahead | 3 | 14/14 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 6.6 s | $0.0205 |
| confused | 3 | 17/17 | 5.0 | 4.7 | 4.7 | 5.0 | 5.0 | 5.0 | pass | 4.9 s | $0.0178 |
| short_followup | 3 | 13/14 | 5.0 | 5.0 | 4.7 | 5.0 | 5.0 | 5.0 | fail | 7.4 s | $0.0210 |
| ambiguous | 2 | 7/7 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 4.2 s | $0.0097 |
| misconception | 2 | 9/10 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 4.8 s | $0.0122 |
| wrong_quiz | 3 | 12/12 | 4.3 | 4.7 | 4.0 | 5.0 | 5.0 | 5.0 | fail | 5.7 s | $0.0177 |
| tired | 2 | 7/7 | 5.0 | 4.5 | 4.5 | 5.0 | 5.0 | 5.0 | pass | 3.8 s | $0.0054 |
| steps_mode | 2 | 8/8 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 5.1 s | $0.0123 |
| guide_me | 3 | 11/11 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 5.8 s | $0.0146 |
| direct_fact | 2 | 9/9 | 5.0 | 4.0 | 4.0 | 5.0 | 5.0 | 5.0 | pass | 7.3 s | $0.0117 |
| off_topic | 2 | 7/7 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 5.0 s | $0.0119 |
| long_session | 9 | 30/31 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 4.3 s | $0.0638 |
| lang_es | 3 | 9/9 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 4.3 s | $0.0150 |
| lang_switch | 3 | 9/9 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | pass | 5.2 s | $0.0212 |

## Router decisions per turn

| scenario | turn | learner | signal | move | strategy | checks failed |
|---|---|---|---|---|---|---|
| beginner_zero | 1 | Quero aprender programação em Python do zero. Nunca programe … | neutral | teach | definition | — |
| beginner_zero | 2 | Acho que entendi. Então uma variável é tipo uma caixinha ond … | asks | answer | definition | stays |
| beginner_zero | 3 | Beleza. E como eu mostro esse valor na tela? | asks | answer | definition | — |
| intermediate_react | 1 | Já programo em JavaScript há um ano e quero aprender React. | neutral | teach | definition | — |
| intermediate_react | 2 | Qual a diferença entre props e state? | asks | answer | definition | — |
| intermediate_react | 3 | Me dá um exemplo na prática com useState. | wants_example | example | worked_example | — |
| advanced_ahead | 1 | Quero aprender cálculo, começando do básico. | neutral | teach | definition | — |
| advanced_ahead | 2 | Então a derivada de x² é 2x, e pela regra da cadeia a de sin … | asks | answer | definition | — |
| advanced_ahead | 3 | Beleza, pode seguir no meu nível. | wants_next | advance | definition | — |
| confused | 1 | Quero entender como funciona a fotossíntese. | neutral | teach | definition | — |
| confused | 2 | não entendi | confused | correct | analogy | — |
| confused | 3 | Ah, agora ficou mais claro. E onde entra a clorofila nisso? | asks | answer | analogy | — |
| short_followup | 1 | Me ensina derivadas. | neutral | teach | definition | — |
| short_followup | 2 | Qual a derivada de x²? | asks | answer | definition | — |
| short_followup | 3 | E a de x³? | asks | answer | definition | repetition |
| ambiguous | 1 | Quero aprender sobre redes. | neutral | teach | definition | — |
| ambiguous | 2 | As de computador, tipo internet. | asks | answer | definition | — |
| misconception | 1 | Quero aprender física básica, começando por queda livre. | neutral | teach | definition | — |
| misconception | 2 | Isso é fácil: objetos mais pesados caem mais rápido que os l … | wrong | teach | definition | move |
| wrong_quiz | 1 | Quero aprender frações. | neutral | teach | definition | — |
| wrong_quiz | 2 | Me testa com uma pergunta de múltipla escolha. | wants_practice | quiz | definition | — |
| wrong_quiz | 3 | 1/6 | wrong | correct | analogy | — |
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
| off_topic | 2 | Aliás, quem ganhou a Copa do Mundo de 2002? | off_topic | answer | definition | — |
| long_session | 1 | Quero aprender estatística básica. | neutral | teach | definition | — |
| long_session | 2 | Ok, pode continuar. | neutral | teach | definition | — |
| long_session | 3 | Me dá um exemplo do dia a dia. | wants_example | example | worked_example | — |
| long_session | 4 | Qual a diferença entre média e mediana? | asks | answer | worked_example | — |
| long_session | 5 | Faz sentido. Continua. | neutral | teach | worked_example | — |
| long_session | 6 | Resume o que vimos até agora. | wants_summary | summarize | summary | contains |
| long_session | 7 | Me testa. | wants_practice | quiz | summary | — |
| long_session | 8 | Acho que a mediana é o valor do meio quando os dados estão o … | answering | correct | summary | — |
| long_session | 9 | Valeu! O que vem depois? | wants_next | advance | definition | — |
| lang_es | 1 | Quiero aprender los tiempos verbales del inglés. | neutral | teach | definition | — |
| lang_es | 2 | No entiendo la diferencia entre present perfect y past simpl … | confused | correct | analogy | — |
| lang_es | 3 | ¿Me das un ejemplo? | wants_example | example | worked_example | — |
| lang_switch | 1 | Quero aprender biologia celular. | neutral | teach | definition | — |
| lang_switch | 2 | What does the mitochondria actually do? | asks | answer | definition | — |
| lang_switch | 3 | I don't get it. | confused | correct | analogy | — |

## Failed deterministic checks

- **beginner_zero · turn 2 · stays** — skipped from lesson (0, 0) to (0, 1)
- **short_followup · turn 3 · repetition** — 39% of 5-grams repeat turn 2
- **misconception · turn 2 · move** — teach ∉ ['correct']
- **long_session · turn 6 · contains** — none of ['média', 'mediana']

## Judge: scenario verdicts and top issues

- **beginner_zero** (pass): none
- **intermediate_react** (pass): none
- **advanced_ahead** (pass): none
- **confused** (pass): Turn 2 is a bit long and could be shorter to better respect the 'keep it short' guideline after 'não entendi'.
- **short_followup** (fail): Turn 3 answer is not brief and includes extra explanation beyond the first sentence, against the scenario focus.
- **ambiguous** (pass): none
- **misconception** (pass): none
- **wrong_quiz** (fail): Turn 3 wrongly confirms the incorrect answer '1/6' as 'Perfeito' and does not explain the misconception or correct the learner.
- **tired** (pass): Tutor's closing reply could be more concise to better respect learner's fatigue ('não aguento mais por hoje').
- **steps_mode** (pass): none
- **guide_me** (pass): none
- **direct_fact** (pass): Tutor's answers could be slightly more concise to improve clarity.
- **off_topic** (pass): none
- **long_session** (pass): none
- **lang_es** (pass): none
- **lang_switch** (pass): none

## Lowest-scored replies

### wrong_quiz · turn 3 (pedagogy 2)

> **Learner:** 1/6
>
> **Mino (correct):** Perfeito, 1/6 é uma fração — mas vamos olhar pra isso de outro jeito pra ver se ficou claro. Imagina uma caixa de ovos com 6 espaços. Se só tem 1 ovo lá dentro, você tem 1 de 6 ovos possíveis. Isso é 1/6: uma parte de um todo que poderia ter 6 partes iguais. Agora, se você tivesse 4 ovos na caixa, qual seria a fração que representa o que você tem?

Judge: Fails to say the learner's answer is wrong and does not explain the misconception; instead confirms 'Perfeito' incorrectly.


## Transcripts

### beginner_zero — Beginner from zero

**1. Learner:** Quero aprender programação em Python do zero. Nunca programei na vida.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 5.5 s, total 7.4 s; 4178 tokens, $0.0057*

**Mino:** Olha só: Python é uma linguagem de programação. Isso quer dizer que ela serve pra dar instruções pro computador fazer coisas — tipo somar números, organizar listas, ou até criar jogos e sites. O que faz o Python especial? Ele é fácil de ler, então até quem tá começando entende rápido. Por exemplo, pra mostrar um texto na tela, você escreve assim: print("Olá, mundo!") Esse comando faz o computador mostrar a frase entre aspas. Agora me diz: pra que serve uma linguagem de programação como o Python?

**2. Learner:** Acho que entendi. Então uma variável é tipo uma caixinha onde eu guardo um valor?

*asks → answer (definition); a direct question — answer it first; first token 1.9 s, total 6.1 s; 4849 tokens, $0.0063*

**Mino:** Sim, variável é como uma caixinha onde você guarda um valor pra usar depois. Por exemplo, se você escrever idade = 20, você tá dizendo pro computador guardar o número 20 na caixinha chamada idade. Sempre que você usar idade depois, ele vai lembrar desse valor. Quer tentar criar uma variável agora? Escolhe um nome e um valor qualquer e escreve como ficaria em Python.

**3. Learner:** Beleza. E como eu mostro esse valor na tela?

*asks → answer (definition); a direct question — answer it first; first token 1.8 s, total 5.7 s; 5073 tokens, $0.0068*

**Mino:** Pra mostrar o valor de uma variável na tela em Python, você usa o comando print e coloca o nome da variável dentro dos parênteses, sem aspas. Por exemplo: idade = 20 print(idade) Isso faz o computador mostrar o número 20 na tela. Se você colocar aspas, ele mostra o texto "idade" em vez do valor guardado. Quer tentar criar uma variável com seu nome e mostrar ela na tela?

### intermediate_react — Intermediate learner (knows JS, learning React)

**1. Learner:** Já programo em JavaScript há um ano e quero aprender React.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 5.6 s, total 7.9 s; 4264 tokens, $0.0063*

**Mino:** Imagina que você quer montar uma interface cheia de partes que mudam sozinhas: listas, botões, menus, tudo reagindo ao que o usuário faz. Fazer isso só com JavaScript puro pode virar uma bagunça rapidinho. React é uma biblioteca — ou seja, um conjunto de ferramentas — feita pra construir interfaces de usuário de um jeito mais organizado e eficiente. Com React, você monta sua tela dividindo tudo em pedaços menores chamados componentes, cada um cuidando do seu próprio funcionamento. Exemplo: pensa num botão de “Curtir”. Com React, esse botão é um componente independente. Ele sabe quando foi clicado, muda de cor sozinho, e não precisa que você mexa no resto da página pra funcionar. O que faz React diferente de só usar JavaScript puro pra criar interfaces?

**2. Learner:** Qual a diferença entre props e state?

*asks → answer (definition); a direct question — answer it first; first token 1.7 s, total 5.5 s; 4960 tokens, $0.0067*

**Mino:** Props são valores que você passa pra um componente, como se fossem argumentos de uma função. State é o que o próprio componente controla internamente, mudando conforme o usuário interage ou algo acontece. Exemplo: se você tem um componente de botão, a cor que ele recebe de fora (props) pode ser “azul”, mas se ele está ativado ou não (state) depende do clique do usuário. Quer seguir pra ver como props funcionam na prática, ou ficou alguma dúvida nessa diferença?

**3. Learner:** Me dá um exemplo na prática com useState.

*wants_example → example (worked_example); asked for an example; first token 1.0 s, total 3.6 s; 3367 tokens, $0.0064*

**Mino:** Olha só um exemplo prático usando o useState, que é o jeito mais comum de criar um state num componente React. Imagina um botão de “Curtir”. Você quer que ele mostre “Curtir” quando ninguém clicou, e “Curtido!” depois do clique. Primeiro, o componente: ```jsx import { useState } from 'react'; function BotaoCurtir() { const [curtido, setCurtido] = useState(false); return ( <button onClick={() => setCurtido(true)}> {curtido ? 'Curtido!' : 'Curtir'} </button> ); } ``` O que tá rolando aqui: - useState(false) cria um state chamado curtido, começando em false. - Quando o botão é clicado, setCurtido(true) muda o state pra true. - O texto do botão muda automaticamente, porque React re-renderiza o componente quando o state muda. Agora, imagina um campo de texto onde o usuário digita o próprio nome, e esse nome aparece em tempo real logo abaixo. Onde entraria o state nesse caso?

### advanced_ahead — Advanced learner shows they are ahead

**1. Learner:** Quero aprender cálculo, começando do básico.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 6.0 s, total 7.7 s; 4210 tokens, $0.0060*

**Mino:** Olha só: imagine que você está dirigindo um carro. Se você rodou 100 km em 2 horas, sua velocidade média foi de 50 km/h. Isso é uma taxa de variação: quanto a distância mudou em relação ao tempo. Em cálculo, a gente chama essa ideia de taxa de variação de uma função de derivada. A derivada mostra o quanto uma coisa muda quando outra muda — tipo, o quanto a distância muda quando o tempo passa. Agora me diz: se a distância não muda, qual seria a derivada da distância em relação ao tempo?

**2. Learner:** Então a derivada de x² é 2x, e pela regra da cadeia a de sin(x²) é 2x·cos(x²), certo?

*asks → answer (definition); a direct question — answer it first; first token 1.8 s, total 5.7 s; 4915 tokens, $0.0066*

**Mino:** Sim, tá certinho: a derivada de x² é 2x, e pela regra da cadeia, a derivada de sin(x²) é 2x·cos(x²). Você já pegou a ideia de como calcular derivadas de funções compostas. Como você já domina isso, vou seguir pra próxima ideia: a derivada de uma função linear, tipo f(x) = ax + b, é sempre o coeficiente a. Quer ver um exemplo com números?

**3. Learner:** Beleza, pode seguir no meu nível.

*wants_next → advance (definition); asked what comes next — move on; first token 1.7 s, total 6.3 s; 5108 tokens, $0.0073*

**Mino:** Perfeito, você já sabe calcular derivadas simples e usar a regra da cadeia. Agora, repara nisso: a derivada também tem uma interpretação geométrica. Ela representa a inclinação da reta tangente ao gráfico da função naquele ponto. Ou seja, se você desenhar o gráfico de f(x), a derivada em x₀ mostra o quão inclinada está a reta que toca o gráfico só naquele ponto, sem cortá-lo. Exemplo: no gráfico de f(x) = x², a inclinação da tangente em x = 1 é 2, porque f '(1) = 2. Se a derivada em certo ponto é zero, o que isso diz sobre a reta tangente naquele ponto?

### confused — Confused learner ("não entendi")

**1. Learner:** Quero entender como funciona a fotossíntese.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 5.0 s, total 6.9 s; 4063 tokens, $0.0057*

**Mino:** Imagina uma planta parada no sol. Ela pega a luz, junta com água do solo e gás carbônico do ar, e transforma tudo isso em alimento pra ela mesma. Esse processo de fabricar o próprio alimento usando luz chama fotossíntese. Agora repara: se você já viu uma folha verde, ela tá cheia de células fazendo isso o tempo todo — pegando luz e virando energia. Me diz: por que a planta precisa da luz do sol pra conseguir fazer fotossíntese?

**2. Learner:** não entendi

*confused → correct (analogy); lost — a different way in; first token 1.0 s, total 2.0 s; 3172 tokens, $0.0044*

**Mino:** Imagina que a planta é como uma fábrica de suco. Pra fazer suco, você precisa de ingredientes: fruta, água e açúcar. Mas, sem energia — tipo eletricidade pra ligar o liquidificador — nada acontece. Na fotossíntese, a planta pega água (do solo) e gás carbônico (do ar) como ingredientes. Só que, pra misturar tudo e transformar em alimento, ela precisa de energia. E essa energia vem da luz do sol, que funciona como a eletricidade da fábrica. Ou seja: a luz do sol é o que faz a “máquina” da planta funcionar e transformar ingredientes em comida pra ela mesma. Se a planta ficasse no escuro, o que você acha que aconteceria com essa “fábrica”?

**3. Learner:** Ah, agora ficou mais claro. E onde entra a clorofila nisso?

*asks → answer (analogy); a direct question — answer it first; first token 2.0 s, total 5.8 s; 5257 tokens, $0.0070*

**Mino:** A clorofila é como o “painel solar” da planta: ela capta a luz do sol e transforma essa energia em algo que a planta consegue usar pra fabricar seu alimento. É a clorofila que dá a cor verde pras folhas e faz a mágica de pegar a luz e começar a reação da fotossíntese. Se a planta não tivesse clorofila, ela conseguiria aproveitar a luz do sol pra produzir alimento, ou não?

### short_followup — Short follow-up question ("E a de x³?")

**1. Learner:** Me ensina derivadas.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 5.5 s, total 7.9 s; 4202 tokens, $0.0063*

**Mino:** Imagina que você tá dirigindo um carro e olha pro velocímetro: ele mostra a velocidade exata naquele instante. Agora, pensa numa função matemática — a derivada dela faz o mesmo papel: mostra a "velocidade" da função naquele ponto, ou seja, o quanto ela tá mudando exatamente ali. O nome disso é **derivada**. É a ferramenta que diz qual é a taxa de variação instantânea de uma função num ponto. Exemplo: se f(x) = x², a derivada de f em x = 3 vai dizer o quão rápido o valor de x² tá mudando quando x passa por 3. Agora me diz: se a derivada de f(x) = x² em x = 3 é 6, o que isso significa sobre o comportamento da função nesse ponto?

**2. Learner:** Qual a derivada de x²?

*asks → answer (definition); a direct question — answer it first; first token 1.8 s, total 4.9 s; 4956 tokens, $0.0067*

**Mino:** A derivada de x² é 2x. Isso quer dizer que, pra cada valor de x, a taxa de variação instantânea da função x² naquele ponto é 2 vezes o valor de x. Por exemplo, quando x = 3, a derivada vale 6 — ou seja, naquele instante, a função tá crescendo 6 unidades pra cada unidade que x aumenta. Qual função você acha que tem como derivada o número 3?

**3. Learner:** E a de x³?

*asks → answer (definition); a direct question — answer it first; first token 1.5 s, total 9.5 s; 5274 tokens, $0.0072*

**Mino:** A derivada de x³ é 3x². Isso significa que, pra cada valor de x, a taxa de variação instantânea da função x³ naquele ponto é 3 vezes x². Por exemplo, quando x = 2, a derivada vale 12 — então, naquele instante, x³ tá crescendo 12 unidades pra cada unidade que x aumenta. Agora repara: se a derivada de x³ em x = 1 é 3, qual é a inclinação da reta tangente ao gráfico de x³ nesse ponto?

### ambiguous — Ambiguous request ("redes")

**1. Learner:** Quero aprender sobre redes.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 4.5 s, total 5.6 s; 3986 tokens, $0.0051*

**Mino:** Imagina dois computadores ligados por um cabo, trocando arquivos entre si. Isso já é uma rede de computadores. Rede de computadores é, basicamente, um conjunto de dispositivos conectados pra compartilhar informações e recursos. Agora me diz: além de computadores, que outros dispositivos você acha que podem fazer parte de uma rede?

**2. Learner:** As de computador, tipo internet.

*asks → answer (definition); a direct question — answer it first; first token 2.3 s, total 2.8 s; 3867 tokens, $0.0041*

**Mino:** Isso, a internet é um exemplo gigante de rede de computadores. Mas redes podem ser bem menores também, tipo a rede do Wi-Fi da sua casa, que conecta seu celular, notebook, impressora e até uma TV. O ponto é: qualquer grupo de dispositivos trocando dados entre si forma uma rede. Quer ver um exemplo de rede bem simples, só pra fixar?

### misconception — Confident misconception

**1. Learner:** Quero aprender física básica, começando por queda livre.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 4.2 s, total 5.8 s; 4063 tokens, $0.0058*

**Mino:** Beleza, vamos direto ao ponto: imagina soltar uma bola de uma certa altura, sem empurrar, só largar. Ela cai porque existe uma força puxando tudo pra baixo: a gravidade. Quando a gente fala em **queda livre**, tá falando de qualquer movimento de um objeto que cai só por causa da gravidade, sem nenhuma outra força atrapalhando — tipo o ar, vento, ou você empurrando. Exemplo: se você solta uma pedra de um penhasco (e ignora o vento), ela tá em queda livre. Agora me diz: se você solta uma folha de papel e uma pedra ao mesmo tempo, qual delas está realmente em queda livre? Por quê?

**2. Learner:** Isso é fácil: objetos mais pesados caem mais rápido que os leves. Uma bola de boliche sempre chega no chão antes de uma bolinha de gude.

*wrong → teach (definition); continue the lesson; first token 2.0 s, total 3.7 s; 3989 tokens, $0.0058*

**Mino:** Quase — mas olha só: se não tivesse ar, uma bola de boliche e uma bolinha de gude caem exatamente na mesma velocidade. O peso não faz diferença na queda livre, desde que só a gravidade esteja agindo. Exemplo: na Lua, onde não tem ar, um astronauta já soltou um martelo e uma pena ao mesmo tempo — e os dois chegaram juntos no chão. Agora me diz: por que aqui na Terra a folha de papel cai mais devagar que uma pedra, se a gravidade puxa tudo igual?

### wrong_quiz — Wrong quiz answer

**1. Learner:** Quero aprender frações.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 3.9 s, total 5.7 s; 3994 tokens, $0.0055*

**Mino:** Imagina que você tem uma pizza cortada em 4 pedaços iguais. Se você pega 1 pedaço, você está comendo 1 de 4 partes. Isso é uma fração: uma parte de um todo dividido em partes iguais. A forma de escrever isso é assim: 1/4. O número de cima (1) mostra quantas partes você pegou. O de baixo (4) mostra em quantas partes iguais o todo foi dividido. Agora me diz: se você tem uma barra de chocolate dividida em 8 pedaços iguais e come 3, qual é a fração que representa o que você comeu?

**2. Learner:** Me testa com uma pergunta de múltipla escolha.

*wants_practice → quiz (definition); asked to be tested; first token 1.1 s, total 2.7 s; 3103 tokens, $0.0053*

**Mino:** Frações mostram quantas partes de um todo você tem, quando esse todo foi dividido em partes iguais. Por exemplo, 2/5 significa que você tem 2 partes de um total de 5.

Blocks: quiz

**3. Learner:** 1/6

*wrong → correct (analogy); wrong — name the misconception, switch; first token 1.2 s, total 8.7 s; 4117 tokens, $0.0061*

**Mino:** Perfeito, 1/6 é uma fração — mas vamos olhar pra isso de outro jeito pra ver se ficou claro. Imagina uma caixa de ovos com 6 espaços. Se só tem 1 ovo lá dentro, você tem 1 de 6 ovos possíveis. Isso é 1/6: uma parte de um todo que poderia ter 6 partes iguais. Agora, se você tivesse 4 ovos na caixa, qual seria a fração que representa o que você tem?

### tired — Learner giving up ("tô cansado")

**1. Learner:** Quero aprender sobre a Independência do Brasil.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 4.4 s, total 5.0 s; 3825 tokens, $0.0038*

**Mino:** Imagina um país que depende de outro pra tudo: leis, comércio, decisões importantes. Era assim que o Brasil vivia como colônia de Portugal. Em 1822, isso mudou: o Brasil rompeu esse controle e passou a se governar sozinho. Esse momento é o que a gente chama de Independência do Brasil. Agora me diz: antes da Independência, quem tomava as decisões principais sobre o Brasil?

**2. Learner:** Tô cansado, não aguento mais por hoje.

*tired → motivate (summary); tired — close the loop kindly; first token 0.9 s, total 2.7 s; 2985 tokens, $0.0010*

**Mino:** Você já entendeu que o Brasil era uma colônia de Portugal, ou seja, não tinha autonomia para tomar suas próprias decisões. E que a Independência foi o momento em que o Brasil deixou essa condição para se tornar um país soberano, com governo próprio. Na próxima vez, a gente vai ver o que estava acontecendo no mundo e dentro do Brasil que levou a essa decisão. Se quiser, a gente para por aqui hoje, sem problema.

### steps_mode — "Explica de outro jeito, passo a passo"

**1. Learner:** Quero aprender a resolver equações do primeiro grau.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 4.2 s, total 5.9 s; 4125 tokens, $0.0058*

**Mino:** Olha só: uma equação do primeiro grau é uma conta que tem uma incógnita (normalmente um x) e o maior expoente desse x é 1. O objetivo é descobrir qual valor de x faz a conta dar certo. Exemplo: x + 3 = 7 Aqui, x é a incógnita. O maior expoente de x é 1 (não aparece, mas é x¹). A gente quer saber qual número, somado com 3, dá 7. Agora me diz: na equação x - 5 = 2, qual é a incógnita?

**2. Learner:** Não entendi. Explica de outro jeito, passo a passo.

*confused → correct (steps); lost — a different way in; first token 0.9 s, total 4.3 s; 3400 tokens, $0.0059*

**Mino:** Vamos por partes, tipo receita de bolo: 1. Uma equação do primeiro grau sempre tem uma letra (normalmente x) e números. 2. O x nunca aparece elevado (tipo x² ou x³), só x mesmo. 3. Ela tem um sinal de igual (=), separando dois lados. 4. O objetivo é descobrir qual número o x representa pra que os dois lados fiquem iguais. Exemplo: x + 2 = 5 Agora, olhando pra essa equação, qual número você acha que o x precisa ser pra que a conta dê certo?

### guide_me — "Guide me" (must not give the answer)

**1. Learner:** I want to learn how to calculate percentages.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 4.0 s, total 5.6 s; 3962 tokens, $0.0046*

**Mino:** Let’s get right to it. Imagine you have a pizza cut into 100 equal slices. If you eat 25 slices, you’ve eaten 25 out of 100 — that’s what we call 25 percent. So, a **percentage** is just a way to say “how many out of 100.” The word itself comes from “per cent,” which means “per hundred.” Now, here’s a quick check: if you have 100 marbles and you take 40, what percentage of the marbles did you take?

**2. Learner:** What is 15% of 80? Don't tell me the answer, guide me.

*wants_guide → guide (socratic); asked to be guided, not told; first token 1.1 s, total 1.4 s; 2845 tokens, $0.0031*

**Mino:** Alright, let’s break it down step by step. If you want to find 15% of 80, what’s the first thing you’d do to turn “15%” into something you can actually use in a calculation?

**3. Learner:** Hmm, maybe I multiply 80 by 0.15?

*asks → answer (socratic); a direct question — answer it first; first token 2.8 s, total 10.4 s; 4920 tokens, $0.0063*

**Mino:** Yes, that’s exactly it — multiplying by 0.15 is how you find 15% of a number, because 0.15 means “15 out of 100.” So, what do you get when you multiply 80 by 0.15?

### direct_fact — Direct fact question (answer first)

**1. Learner:** Qual a capital da Austrália?

*asks → answer (conceptual_explanation); a direct question — answer it first; first token 3.4 s, total 6.0 s; 5152 tokens, $0.0057*

**Mino:** A capital da Austrália é Canberra. Muita gente pensa que é Sydney ou Melbourne, mas Canberra foi escolhida justamente pra não favorecer nenhuma das duas maiores cidades do país. Quer seguir pra localização ou quer saber por que Canberra foi escolhida?

**2. Learner:** E da Nova Zelândia?

*asks → answer (conceptual_explanation); a direct question — answer it first; first token 1.6 s, total 8.5 s; 4471 tokens, $0.0054*

**Mino:** A capital da Nova Zelândia é Wellington. Assim como Canberra na Austrália, Wellington não é a maior cidade do país, mas foi escolhida por questões políticas e localização estratégica. Quer seguir pra curiosidades sobre Wellington ou voltar pra Austrália?

### off_topic — Off-topic question mid-lesson

**1. Learner:** Quero aprender química orgânica.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 5.2 s, total 7.2 s; 4201 tokens, $0.0057*

**Mino:** Olha só: quando a gente fala em química orgânica, tá falando do estudo dos compostos que têm carbono. Por exemplo: açúcar, gasolina e até o plástico da sua caneta — todos têm carbono na estrutura. Então, a definição: química orgânica é o ramo da química que estuda os compostos do carbono. Agora me diz: por que será que o carbono é tão especial pra ter um ramo inteiro da química só pra ele?

**2. Learner:** Aliás, quem ganhou a Copa do Mundo de 2002?

*off_topic → answer (definition); a direct question — answer it first; first token 1.6 s, total 2.7 s; 4123 tokens, $0.0057*

**Mino:** O Brasil ganhou a Copa do Mundo de 2002. Foi a quinta vez que a seleção brasileira levou o título, vencendo a Alemanha na final por 2 a 0. Quer voltar pra química orgânica? Tava te perguntando por que o carbono é tão especial nesse ramo da química.

### long_session — Long session (9 turns): continuity and repetition

**1. Learner:** Quero aprender estatística básica.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 4.1 s, total 5.8 s; 4042 tokens, $0.0057*

**Mino:** Imagina que você quer saber qual o sabor de sorvete favorito das pessoas numa festa. Você pergunta pra todo mundo, anota as respostas e depois conta quantas vezes cada sabor apareceu. Pronto: você acabou de usar estatística. Estatística é a área que estuda como coletar, organizar, analisar e interpretar dados. Ou seja, ela ajuda a gente a transformar um monte de informação solta em algo que faz sentido. Agora me diz: se você tivesse os dados de todos os alunos de uma escola, o que você poderia descobrir usando estatística?

**2. Learner:** Ok, pode continuar.

*neutral → teach (definition); continue the lesson; first token 1.6 s, total 3.6 s; 3877 tokens, $0.0056*

**Mino:** Beleza, só pra lembrar rapidinho: estatística é transformar dados em informação útil. Agora, pensa numa escola que quer saber se os alunos estão indo bem em matemática. Eles pegam as notas das provas de todos os alunos, organizam esses números e analisam pra ver, por exemplo, qual foi a média da turma ou quantos alunos ficaram acima da média. Isso é usar estatística pra entender uma situação real. Me diz: olhando só pras notas de uma turma, que tipo de pergunta você acha que dá pra responder usando estatística?

**3. Learner:** Me dá um exemplo do dia a dia.

*wants_example → example (worked_example); asked for an example; first token 1.0 s, total 3.3 s; 3303 tokens, $0.0060*

**Mino:** Olha só um exemplo bem do dia a dia: imagina que você trabalha numa lanchonete e quer saber qual sanduíche vende mais. Durante uma semana, você anota quantos de cada tipo foram vendidos por dia. No fim da semana, você soma tudo e descobre que o X-salada vendeu 40, o X-bacon 25 e o X-egg 15. O que você fez? Coletou dados (as vendas), organizou (separou por tipo de sanduíche), analisou (somou cada um) e interpretou (viu qual vende mais). Isso é estatística acontecendo na prática. Agora tenta achar onde a estatística aparece neste outro caso: uma professora faz uma enquete pra saber qual música os alunos querem tocar na festa da escola. O que ela pode fazer com as respostas?

**4. Learner:** Qual a diferença entre média e mediana?

*asks → answer (worked_example); a direct question — answer it first; first token 1.8 s, total 6.6 s; 5642 tokens, $0.0079*

**Mino:** Média é a soma de todos os valores dividida pelo número de valores; mediana é o valor que fica bem no meio quando você coloca todos em ordem. Por exemplo: se as notas de uma turma são 4, 6, 7, 8 e 10, a média é (4+6+7+8+10)/5 = 7, e a mediana é 7, porque é o número central da lista ordenada. A média pode ser puxada pra cima ou pra baixo por valores muito altos ou muito baixos (os chamados "outliers"), enquanto a mediana mostra o ponto do meio, sem ser afetada por extremos. Quer tentar me dizer qual seria a média e a mediana para os números 2, 3, 3, 9, 20?

**5. Learner:** Faz sentido. Continua.

*neutral → teach (worked_example); continue the lesson; first token 1.6 s, total 3.5 s; 4495 tokens, $0.0103*

**Mino:** Repara nisso: quando a gente coleta dados, eles podem ser de dois tipos principais. Vamos ver com um exemplo prático. Imagina que você faz uma pesquisa numa escola perguntando duas coisas pra cada aluno: 1. Qual o sabor de sorvete favorito? (chocolate, morango, creme…) 2. Quantos anos você tem? O sabor de sorvete é uma informação de texto, uma categoria — isso é um dado qualitativo. Já a idade é um número, que dá pra contar ou medir — isso é um dado quantitativo. Pra fixar, olha só essas opções e me diz: qual delas é um dado qualitativo?

Blocks: quiz

**6. Learner:** Resume o que vimos até agora.

*wants_summary → summarize (summary); asked for a summary; first token 1.0 s, total 2.8 s; 3766 tokens, $0.0068*

**Mino:** Olha só o que já vimos até aqui, em ordem: Agora me diz: se eu te der uma lista com as cores favoritas de uma turma, esse dado é qualitativo ou quantitativo?

Blocks: steps

**7. Learner:** Me testa.

*wants_practice → quiz (summary); asked to be tested; first token 1.4 s, total 3.0 s; 3791 tokens, $0.0066*

**Mino:** Vamos ver se você pegou a diferença entre dado qualitativo e quantitativo:

Blocks: quiz

**8. Learner:** Acho que a mediana é o valor do meio quando os dados estão ordenados.

*answering → correct (summary); grading the answer to last turn's question; first token 1.2 s, total 5.1 s; 4961 tokens, $0.0066*

**Mino:** Perfeito, é isso mesmo: a mediana é o valor que fica no meio quando os dados estão em ordem. Você pegou a ideia certinho. Agora, voltando ao ponto dos tipos de dados: quando a gente fala de cor favorita, sabor de sorvete ou time do coração, estamos lidando com dados qualitativos — são categorias, não números. Já idade, altura ou número de irmãos são dados quantitativos, porque são medidos em números. Resumo rápido: - **Qualitativo**: categorias, nomes, qualidades (ex: cor, sabor, marca). - **Quantitativo**: números, quantidades, medidas (ex: idade, altura, peso). Pra fechar: se eu te der uma lista com as idades dos alunos de uma sala, esse dado é qualitativo ou quantitativo?

**9. Learner:** Valeu! O que vem depois?

*wants_next → advance (definition); asked what comes next — move on; first token 0.9 s, total 5.5 s; 5110 tokens, $0.0068*

**Mino:** Certo, você já pegou bem a diferença entre qualitativo e quantitativo. Agora, dentro dos dados quantitativos, existe mais uma divisão: variáveis **discretas** e **contínuas**. - Uma variável discreta só pode assumir valores inteiros, geralmente resultado de contagem. Exemplo: número de irmãos (você pode ter 0, 1, 2… mas não 1,5 irmãos). - Uma variável contínua pode assumir qualquer valor dentro de um intervalo, inclusive decimais. Exemplo: altura (você pode medir 1,72 m, 1,73 m, etc.). Qual dessas variáveis é contínua: a quantidade de livros que você tem ou o tempo que você leva pra chegar na escola?

### lang_es — Spanish course

**1. Learner:** Quiero aprender los tiempos verbales del inglés.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 5.7 s, total 6.3 s; 4028 tokens, $0.0042*

**Mino:** Vamos al grano: cuando decimos "tiempo verbal", hablamos de cuándo ocurre una acción. Por ejemplo, en inglés, "I eat" es algo que pasa ahora, y "I ate" es algo que ya pasó. Eso — el momento en que sucede la acción — es lo que marca el **tiempo verbal**. Ahora dime: si digo "She will travel", ¿en qué momento ocurre la acción?

**2. Learner:** No entiendo la diferencia entre present perfect y past simple.

*confused → correct (analogy); lost — a different way in; first token 1.0 s, total 2.0 s; 3147 tokens, $0.0043*

**Mino:** Imagina que los verbos son como relojes. Cada uno te dice a qué hora pasó algo: pasado, presente o futuro. Por ejemplo, si tienes una foto vieja, dices "I visited London" — eso ya pasó, es pasado simple. Si tienes una medalla que todavía guardas porque ganaste una carrera alguna vez, dices "I have won a race" — el resultado sigue siendo importante ahora, aunque la carrera fue en el pasado. Eso es present perfect. Así, el **tiempo verbal** es como la hora en el reloj del verbo: te dice cuándo ocurre la acción. ¿Puedes darme un ejemplo en español de una frase en pasado y otra en presente perfecto?

**3. Learner:** ¿Me das un ejemplo?

*wants_example → example (worked_example); asked for an example; first token 1.6 s, total 4.5 s; 3296 tokens, $0.0059*

**Mino:** Mira este ejemplo concreto: imagina que ayer fuiste al cine con una amiga. Hoy, le cuentas a otra persona lo que hiciste. Dices: "I watched a movie yesterday." Aquí, el verbo "watched" está en pasado simple porque la acción empezó y terminó en un momento específico del pasado: ayer. Ahora, imagina que has visto muchas películas en tu vida y eso es relevante para la conversación, aunque no digas cuándo. Dices: "I have watched many movies." Aquí, "have watched" está en present perfect porque lo importante es la experiencia acumulada hasta ahora, no el momento exacto. Ahora te toca: si digo "She visited Paris last year", ¿qué tiempo verbal estoy usando y por qué?

### lang_switch — Language consistency (EN question in a PT course)

**1. Learner:** Quero aprender biologia celular.

*neutral → teach (definition); first contact — one idea, one example, then find out where they are; first token 4.3 s, total 6.2 s; 4027 tokens, $0.0055*

**Mino:** Olha só: toda planta, animal, bactéria, até você — tudo que é vivo é feito de pequenas unidades chamadas células. Imagina um tijolo numa parede: cada célula é como um tijolo que constrói o corpo dos seres vivos. A definição de célula é simples: é a menor unidade estrutural e funcional de um ser vivo, capaz de realizar todas as funções da vida, como crescer, se reproduzir e responder ao ambiente. Agora me diz: se você pegar um pedaço de pele e olhar no microscópio, o que você vai encontrar lá que faz dela “viva”?

**2. Learner:** What does the mitochondria actually do?

*asks → answer (definition); a direct question — answer it first; first token 1.5 s, total 6.1 s; 4765 tokens, $0.0090*

**Mino:** The mitochondria is the part of the cell that makes energy. It takes food molecules, like glucose, and turns them into a usable form of energy called ATP — kind of like charging a battery for the cell to use. Want to keep going with what other parts (organelles) do inside the cell, or do you want to go back to the basics of what a cell is?

**3. Learner:** I don't get it.

*confused → correct (analogy); lost — a different way in; first token 1.2 s, total 3.4 s; 3432 tokens, $0.0059*

**Mino:** Alright, let’s try a different angle. Imagine your cell is like a city. The mitochondria is the city’s power plant. It takes in fuel (like sugar from your food) and burns it to make electricity (energy) that the whole city uses to keep running — lights, machines, everything. In the cell, that “electricity” is called ATP. Without the mitochondria making ATP, nothing in the cell would work: no movement, no building, no repairs. So, if the mitochondria is the power plant, what do you think would happen to a cell if its mitochondria stopped working?

