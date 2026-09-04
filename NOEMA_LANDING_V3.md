# NOEMA landing V3 — meeting the tutor

`apps/web/src/components/landing/v3/`. The page is one narrative and one
character.

## Structure

| # | Beat | What happens | Mino |
|---|---|---|---|
| 01 | **Ask** | "O que você quer aprender?" — one input, examples rotating in the placeholder. Focus → curious; typing → listening, eyes on the field; a pause → thinking; submit → thinking until the first token, then teaching. The reply streams under the field. | idle → curious → listening → thinking → teaching |
| 02 | **Learn** | The reply, carried down as a lesson block (learner line, NOEMA label, markdown prose) — the same component the Professor uses. | teaching |
| 03 | **Practice** | One question adapted to the subject; three options; then "Certeza?" with two confidence buttons. Right: "Isso. Próxima ideia." and a small nod. Wrong: "Quase. Repara nesta diferença…" and the distinction that matters. | curious → happy / thinking |
| 04 | **Adapt** | Three concept bars for the subject; after a wrong answer the weak concept drops and the list reorders — "Reordenado depois da sua resposta". No brain, no graph animation; the product's own mastery bars. | thinking |
| 05 | **Remember** | A review card that turns over on tap; "Próxima revisão em 11 dias". | reading |
| — | **Close** | "Aprenda qualquer coisa." — the large figure again, one orange Começar (Continuar aprendendo when signed in). The typed subject is carried into the app via `lib/prefill`. | wave |

The companion figure (bottom-right, 64–80 px) is the same character drawn
from the same controller; it appears once the hero has scrolled away and
fades before the close brings the large figure back.

## The demo

`POST /ai/demo` (`apps/api/noema/api/v1/demo.py`): one subject in, up to
`noema_demo_max_tokens` (220) of a real lesson opening out, from the
deployment's default provider (`noema_demo_model` overrides), no account,
no history, no retrieval, no session. Limits: the global per-minute limiter,
plus `noema_demo_per_caller_per_day` (6) per hashed IP in Redis;
`noema_demo_enabled=false` switches it off. The prompt
(`demo.teach.v1.md`) asks for one idea, one example, one question, ≤ 90
words, in the subject's language, and declines non-subjects politely.

The page never fakes a delay: Mino's `thinking` lasts exactly as long as the
request, `teaching` starts on the first token. A 429, a 503 or a network
failure falls back to the written sample for that subject, labelled
"O tutor está ocupado agora; é assim que os primeiros trinta segundos são."

## Local adaptation

`subjects.ts` holds three written banks (Freud, Italian, JavaScript) in
PT/EN/ES and a template for everything else. The banks feed the sample, the
practice question and its correction, the concept bars and the review card.
Free text is the rule; the banks are only better than the template.

## Copy

Eyebrow: "Um tutor de IA que ensina, não um chatbot que responde." Headline:
"O que você quer aprender?" One sentence per beat. No "unlock your
potential", no feature grids, no pricing, no testimonials.

## Removed

The V2 hero (`HeroAsk`), the six beats grid (`Beats`), `MinoStage`,
`useHeroTilt`, `useScrollMinoState`, the pricing section and the closing
principle. Plans remain in Settings.

## Not done

- Spatial FLIP transition of the hero figure into the companion (today a
  fade/translate between two figures of the same controller).
- Mobile keyboard choreography beyond the layout: background motion is not
  yet frozen while the keyboard is open.
- The official art (see `MINO_CHARACTER_SPEC.md`, asset audit).
