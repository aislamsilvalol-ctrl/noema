# NOEMA landing V7: redesign audit and plan (2026-10-19)

The source of truth is V6 in production (`components/landing/v6`) and
@noemalearn. Captures from production at 1440 and 390 px, 14 scroll positions
each, are the basis of this audit. V6 stays in the tree; rolling back is one
import in `app/page.tsx`.

## Current landing (V6)

The page has eight scenes and about 1,400vh of pinned scroll:

1. Terraces hero.
2. Manifesto, revealed word by word.
3. Mino on a ridge.
4. How it works: four beats.
5. Territory turning into the map.
6. Live tutor.
7. Today.
8. Horizon.

The identity is strong: the cobalt sky, the landscapes, Mino seen from behind,
monumental Inter type and the ember action. The structure is weak.

## What must stay

- The landscapes (one world, one place) and their films.
- Mino as he is: the 3D figure from behind in the landscape and the SVG rig in the interface.
- The palette: cobalt, ultramarine, ink, bone and one ember.
- Monumental Inter with mono metadata.
- The camera push on the hero and the rotating subject under "Aprenda qualquer coisa."
- The knowledge map drawing itself over the cobalt field.
- The live tutor, which is real and not a mockup.
- The horizon as the close.

## What must go

- **The word-by-word manifesto.** It costs 200vh to say one sentence, and on a phone the first frame is an empty bone screen.
- **"Today".** It is a list of three rows with no product in it.
- **Duplicated headlines.** "Um professor, não um chat" and "Um professor com um plano, não um chat com um assunto" are the same idea twice.
- **"Como funciona" in four numbered beats.** Each beat has a paragraph.
- **About 1,400vh of pinning.** The product appears only after roughly 12 screens.
- **Two nav anchors.** "Como funciona" and "Mapa" point to sections that are now gone.

## Main UX problems

1. The product is hidden: the live tutor sits in scene 6.
2. Scroll fatigue: five pinned scenes in a row, three of them only type.
3. The visitor never sees a lesson happen: question, mistake, a change of approach, understanding.
4. On mobile, a reachable CTA exists only in the hero and the close.
5. Modo TDAH, a differentiator, does not appear.

## Main visual problems

1. Bone sections without an image or the product read as empty (manifesto, Today, the tutor's head).
2. Text sits over the image on a flat veil; there is no depth between the landscape and the interface.
3. The four "how it works" frames are four unrelated stills.

## Copy problems

- The main promise ("Uma inteligência que aprende como você aprende") is abstract, and it is the hero's sub-line.
- Paragraphs of 40 to 60 words (Mino, the tutor, the map).
- "Sabelia" is named on the landing, but the visitor does not need to know it.

## Performance risks

- Seven films. Each one loads only near its scene, but a deep scroll still adds up to about 1.1 MB.
- The page imports both V5 and V6 CSS.
- The scroll listener runs for six scenes.
- The LCP is the hero still. Keep it.

## New information architecture

| # | Scene | What it does | Pin |
|---|---|---|---|
| 01 | **Hero:** terraces | NOEMA, Mino and the promise in one image: "Aprenda qualquer coisa." plus the rotating subject, one sub-line and one action | 140vh |
| 02 | **A real lesson** | The product working: question → mistake → Mino changes approach → understanding → mastery is recorded. The visitor can then ask their own question in the same window (the real tutor) | none; the choreography plays when the scene enters the viewport |
| 03 | **Why it works:** valley → trail → horizon | Three ideas: knows where you are · changes its approach · you actually progress. Each one has a real piece of interface | 300vh |
| 04 | **Modo TDAH:** bleach | Five minutes, one thing: the focus card with its step and timer | none |
| 05 | **Territory → map** | The immersive moment: the land turns into your map | 220vh |
| 06 | **Horizon** | The close: one line, one action, the footer | 120vh |

Total pinned scroll: about 780vh instead of 1,400vh. The product appears in
the second screen.

## Hero

The terraces film with a slow camera push toward Mino, who stands small at the
foot of the frame. The type takes the sky:

- "Aprenda qualquer coisa." with the subject rotating in ember.
- One sub-line that says what it is: "Um professor de IA que descobre o que você já sabe e ensina o resto."
- One action, "Começar a aprender".
- A microline in mono: "Grátis para começar".

The nav keeps only the wordmark, "Planos", "Entrar" and "Começar".

## Product demo

A lesson window that looks like the real one, built from the same markup and
tokens as `Lesson.tsx`:

- Mino's avatar with the mono "Mino" label.
- The learner's line with a left rule.
- A quiz card with options, graded right or wrong.
- The `MasteryNote` line (● / ◐).

A JS script plays it in about 12 s:

1. The learner asks.
2. Mino asks a question first.
3. The learner answers wrong.
4. Mino says why and changes approach; the strategy is visible in mono.
5. A second question, answered right.
6. "● velocidade média — entendido".

A side rail names each step ("pergunta · erro · muda de jeito · entende").

At the end the composer opens: "Pergunte qualquer coisa ao Mino". A question
the visitor types streams from the real tutor in the same window. If the tutor
is unavailable, an honest sample answer is shown and labelled as a sample.

## Motion direction

- Camera: the push into the hero and the map, kept from V6.
- Depth: the interface sits over the landscape with a slight scroll offset (parallax on transform).
- Reveals: one clip per idea.
- The lesson demo: a typed line (characters at reading speed), options that settle in, a check that draws itself, and Mino changing state (thinking → teaching → cheering) through the existing rig.
- Focus timer: a real countdown.
- No float, no bounce, no particles.
- Reduced motion shows every scene complete and static, and the demo in its final state.

## Mobile strategy

- Its own composition: the hero type in the sky, Mino at the foot, the CTA reachable with the thumb.
- The demo full width, as the real phone lesson.
- "Why it works" turns into three stacked frames with the type over them; there is no 300vh pin on the phone.
- A sticky bottom CTA bar appears once the hero leaves the screen and hides at the close.
- Targets of 44 px or more, and nothing cut off.

## Component strategy

`components/landing/v7/`:

- `LandingV7.tsx`: composition, nav, sections.
- `LessonDemo.tsx`: the scripted lesson plus the live tutor.
- `FocusDemo.tsx`: the focus card.
- `useInView.ts`: plays a scene once it enters the viewport.

Reused as they are: `SceneFilm`, `Landscape` and `KnowledgeMap` (v5), and
`useSceneProgress` (v6). Tokens live at the top of `styles/landing-v7.css`.

## Implementation plan

1. Copy in PT, EN and ES (`landing7`).
2. `LandingV7` with the hero, the why scene, the map and the horizon (reusing the V6 mechanics).
3. `LessonDemo`: script, choreography, live tutor and fallback.
4. `FocusDemo`.
5. Mobile: the sticky CTA and the per-scene compositions.
6. Tests: order, one CTA, the demo's final state under reduced motion, and the live tutor.
7. Visual QA at 1440, 1024, 768, 390 and 360 px through `shoot.mjs`.
8. Performance: no new dependency, and no film beyond the five scenes used.
