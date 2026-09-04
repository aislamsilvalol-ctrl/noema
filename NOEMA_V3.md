# NOEMA V3 — Mino is the AI

Noema is the platform. Mino is who the learner meets. This document records
how that is built and what is locked.

## Brand lock

**There is no logo file.** The shipped NOEMA identity is the word set in the
product's display face, **Newsreader** (`apps/web/src/fonts/newsreader.woff2`,
weights 400–500, loaded in `app/layout.tsx` as `--font-display`), in capitals,
with wide tracking. `components/brand/Wordmark.tsx` is now the only place it
is drawn; every screen (rail, auth, landing) uses it. Size and colour are the
only choices a call site has. No symbol was created, no font substituted, no
effect applied. The favicon remains the pre-existing placeholder letterform.

Product typography (Inter for UI, Newsreader for reading, JetBrains Mono for
code) is unchanged and is distinct from the wordmark: the wordmark uses the
display face at a fixed size; headlines use it as product typography.

## The conversation is with Mino

- Replies are labelled **Mino** with a 28 px avatar of the same rig as the
  live figure (`<Mino size="xs">`); the composer says "Pergunte qualquer coisa
  pro Mino…"; the screen title is Mino until the session names a subject.
- **Persona layer** — `apps/api/noema/prompts/mino.persona.v1.md`, placed
  first in the system prompt for the intents that teach: curious, calm,
  precise, lightly playful; no flattery; a new approach when the learner is
  lost; "Perfeito, então pulamos essa parte" when they already know it;
  direct answers to direct questions; Socratic questions only where a wrong
  belief is likely.
- **Identity** — the identity clause now says Mino, the tutor inside Noema.
- The engine layers are separate files, composed at request time:
  persona (`mino.persona`) → mode prompt (`tutor.*` / `rag.*`) → teaching
  principles + tools + PEDAGOGY record (`teaching.principles`) →
  `<STUDENT_MEMORY>` (mastery, misconceptions) → `<ACTIVE_SESSION>` (the
  lesson's state). No single giant prompt; the student model is data, not
  prose the model invents.

## Learning blocks (generative UI)

The engine may place one fenced block per reply whose language is
`noema:<tool>` and whose body is one JSON object:

| Tool | Draws | When |
|---|---|---|
| `layers` | a visible part above an orange line, the hidden part below | iceberg-shaped ideas: surface vs mechanism |
| `steps` | numbered sequence | order matters |
| `compare` | two-column table | a distinction the learner keeps confusing |
| `quiz` | question, options, verdict with the engine's explanation | checking the idea just taught |
| `flashcard` | a card that turns | something worth remembering verbatim |

`lib/markdown.tsx` parses a *closed* block into `{kind:'tool'}`, holds a
half-streamed one back (no raw JSON flashes), and shows a malformed one as
code. `components/professor/LearningBlocks.tsx` draws them in the product's
own tokens. A quiz compares against the engine's `answer` and emits
`correct` / `wrong`; the character reacts through the controller. The model
never names an animation, a coordinate or a frame.

Contextual actions: the quick actions (Me teste · Aprofundar · Explica de
outro jeito · Resumir) appear after a prose reply and not after one that
already carries a learning block.

## Presence

`components/mino/MinoPresence.tsx` derives a level from the controller's
state and the viewport:

| Level | When | Where |
|---|---|---|
| avatar | any phone (< 768 px) | only the message avatar; nothing over content |
| peek | idle, sleepy | 58 % below the bottom edge, arms on the edge of the conversation |
| half | curious, listening, thinking, teaching, pointing | rises to 34 % below |
| contextual | confused | same as half |
| celebration | happy, celebrating | 8 % below, for the transient's duration |
| hidden | reserved | — |

The figure is fixed at the bottom-right of the content area, 9–11 rem wide,
`pointer-events: none`, `aria-hidden`. Both Professor screens wrap in
`MinoProvider`; the empty-state figure is hidden where the presence figure
exists.

## Chat ↔ character events

| Product event | Mino |
|---|---|
| typing in the composer | listening |
| submit / request started | thinking |
| first token | teaching |
| stream done | idle |
| stream error | confused → curious |
| quiz answered right / wrong | happy / thinking |

Streaming and the character loop are independent: the reply re-renders per
token; the rig re-renders only when the controller's pose changes (state,
gaze spring, blink).

## The three tests

- "Quero aprender psicologia segundo Freud do zero." → Mino teaches (verified
  against production: an opening idea, the slip example, no "create a
  notebook").
- "Não entendi." → the persona forbids repeating the paragraph; the
  principles prescribe a strategy switch (analogy → scenario → prerequisite).
- "Isso eu já sei." → "Perfeito, então pulamos essa parte." and more depth.

The second and third are prompt-level rules verified by reading the reply
transcripts in `evals/teaching/` after each deploy, not by unit tests.

## Verified (2026-09-04, production API at 8203677, local V3 build)

| Check | Result |
|---|---|
| "Quero aprender psicologia segundo Freud do zero." | Mino opens with the one idea, the slip example, and a `noema:layers` iceberg block ("A mente como iceberg", consciente / inconsciente) — `evals/teaching/v3-three-tests-338ec32.md` |
| "Não entendi." | "Beleza, esquece o iceberg e o lapso de língua por um segundo." — a new approach (what you know now vs. what a photo would bring back), not the same paragraph |
| "Isso eu já sei." | "Perfeito, então pulamos essa parte." — then deeper: pré-consciente vs inconsciente, a `noema:compare` table, recalque |
| Blocks render as UI | In the app, "Me mostra isso visualmente" produced a layers figure ("O modelo da mente (Freud)"); no raw fence reached the page; unit tests cover closed / half-streamed / malformed blocks and the quiz outcome event |
| Identity | Replies labelled Mino with the avatar; composer "Pergunte qualquer coisa pro Mino…"; title "Mino" |
| Presence | `avatar` on phones; `half` while typing/thinking/teaching; `peek` at rest — read from `data-mino-presence` |
| Rail | Black in light mode (`rgb(19,18,16)`), wordmark in the display face, sticky for long conversations |

## Not done

- Voice input ("Repete comigo") and file/image attachments in the composer.
- Mino appearing *inside* a diagram block (pointing at the submerged part);
  today he rises beside the conversation instead.
- Mobile keyboard choreography.
- The official character art (see `MINO_CHARACTER_SPEC.md`).
