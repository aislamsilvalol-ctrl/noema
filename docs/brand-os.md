# NOEMA — Brand OS

The one document every future page, screen, campaign and render is measured
against. It records what the brand is, the decisions that made it, and the
things it refuses. Companions: `docs/design-system.md` (tokens),
`MINO_CHARACTER_SPEC.md` (the character), `docs/product-audit-2026-09.md`
(where the product stood when this was written).

## 1. Purpose

NOEMA exists so that learning adapts to the person, not the person to the
course. Its promise in one line:

> **An intelligence that learns how you learn.**

Everything on a screen either serves that line or is overhead.

## 2. Positioning

NOEMA is a **personal learning system**. It is not a chatbot, a search box, a
course catalogue, a video library or a wrapper around a model. The difference
is what happens before and after an answer: it finds out what you know, plans
a path, teaches one idea at a time, asks, notices which concept moved, changes
strategy, and returns before you forget.

Two entities, never confused:

| | Sabelia | Mino |
|---|---|---|
| What it is | the intelligence — the learner model, the memory, the scheduling, the adaptation | the presence — teacher, guide, companion, the voice and face of the platform |
| Where it appears | inside the engine; named in the Lab and in technical writing; rarely on a product screen | every screen where something is taught, asked, celebrated or paused |
| Voice | none; it does not speak | speaks in first person, as Mino |

The product says "NOEMA learns how you learn"; the interface shows Mino
doing the teaching; the engineering names Sabelia. A screen that makes the
learner think about the model has failed.

## 3. Personality

Curious, intelligent, direct, warm, occasionally funny. Less corporate, less
formal, less robotic than the category. Confident without volume.

Mino specifically: a teacher who asks before telling, notices when you are
reciting, tries another route when the first one did not land, and marks the
moments that deserve it — not every one. Humour is contextual and rare. No
slang for its own sake, no memes, no sarcasm at the learner's expense.

## 4. Voice and copy

Rules, in order of importance:

1. **Name the mechanism.** "It remembers what you struggle with" beats "AI-powered personalisation". If a sentence could sit on any SaaS site, rewrite it.
2. **Concrete over abstract.** A fragment of a real lesson beats a paragraph about lessons.
3. **Short lines, generous space.** Headlines are one idea. Body copy rarely passes three sentences.
4. **Honest tense.** What exists is present tense; what is planned is not on the page.
5. **Nothing invented.** No student counts, testimonials, logos, or numbers without a basis. An illustrative number is labelled as one.

Banned: unlock your potential · revolutionise · AI-powered · next-generation ·
smarter not harder · the future of learning · seamless · empower · supercharge.

Reference lines (direction, not final):

- EN: *An intelligence that learns how you learn.* / *Learn like no one else does.* / *NOEMA doesn't just remember what you studied. It remembers what you struggle with.*
- PT: *Uma inteligência que aprende como você aprende.* / *Aprenda como ninguém.* / *O NOEMA não lembra só o que você estudou. Lembra do que te trava.*
- ES: *Una inteligencia que aprende cómo aprendes.* / *Aprende como nadie.* / *NOEMA no solo recuerda lo que estudiaste. Recuerda lo que te cuesta.*

## 5. Visual principles

The brand lives between pairs: **tech × culture · digital × analog ·
intelligence × humanity · precision × curiosity · future × memory · science ×
imagination.** In practice:

- **Editorial, not templated.** Sections are composed — a monumental line, one figure, a fragment, space. No card grids. A card exists only when the thing is a card (a flashcard).
- **Atmosphere shifts.** A page changes ground as it scrolls — cream, then deep blue, then mineral green, then near-black — and stays one brand because type, character and rhythm do not change.
- **Colour used editorially.** Large single-colour fields; one accent word per composition; never a rainbow of chips.
- **Texture as a layer, not a style.** Grain, halftone or a print-like bleed on a section ground or a figure's backdrop, at low opacity, never on text.
- **Quiet technology.** Nothing glows, pulses, floats in gradients or sparkles. Motion is slow, small, and carries information.
- **The character is lit like an object.** Mino is rendered with a warm key light on a plain ground, as a thing on a table, never as a sticker.

## 6. Colour

Two layers: the **interface** palette (unchanged — it passes WCAG and is measured in `globals.css`) and the **atmosphere** palette for editorial grounds.

Interface (per `design-system.md`): warm ink ramp; terracotta primary (`--noema-orange-700` light / `500` dark) with `--signal` (`500`/`400`) for large emphasis only; positive/caution/critical; cream ground `#fbf8f3`, dark room `#141311`.

Atmosphere (new; sections and campaigns, never interactive controls):

| token | value | role |
|---|---|---|
| `--atmo-cream` | `#fbf8f3` | the default ground — paper |
| `--atmo-cobalt` | `#1f3fbf` | deep blue field; type in cream; orange word allowed |
| `--atmo-ultramarine` | `#12247a` | the darker blue, for depth behind cobalt |
| `--atmo-mineral` | `#1f5a48` | mineral green field; type in cream |
| `--atmo-deep-green` | `#0f3a2f` | the darker green |
| `--atmo-black` | `#0e0d0c` | the black section; orange and cream type |
| `--atmo-burnt` | `#b5450c` | burnt orange field (rare); type in cream |
| `--atmo-orange-red` | `#e4471f` | the loud one; a word, a rule, a dot — never a field |

Rules: at most three atmospheres on one page; each field carries its own
foreground tokens (a section sets `--fg`, `--fg-muted`, `--accent-on`); the
orange word appears on cream, cobalt and black — not on mineral (it vibrates).

## 7. Typography

- **Display: Newsreader** (variable, weight 200–800, optical size 6–72). The wordmark is locked in it; monumental lines are set at weight 400–500, tight tracking, optical size at maximum. This is the brand's signature and stays.
- **Interface: Inter** (variable, weight 100–900). Everything a learner acts on. Section numbers, monumental *labels* and the few sans-serif display moments use weights 600–800 — the file already carries them.
- **System: JetBrains Mono.** Small labels, metadata, step counters, "now / later". Never a paragraph.

The scale is closed (nine sizes) with two fluid additions for editorial
lines: `--text-display: clamp(2.75rem, 9vw, 6.25rem)` and
`--text-display-2: clamp(2.25rem, 6.5vw, 5rem)`. A headline never overflows
its column; it shrinks with the viewport.

Decision recorded: the brief asks to prioritise a contemporary sans-serif.
The serif display is the brand the owner locked on 2026-09-04 and it is what
makes the site recognisable without a logo; Inter takes every sans role.
Swapping the display to a sans is one decision and one font file away — not
made here.

## 8. Photography, illustration, 3D

- No stock photography. If an image is not the character, it is an abstract
  ground: a treated landscape, a grain field, a topographic or constellation
  drawing in one ink — the learning-landscape metaphor (§10).
- Illustration is line and field, one or two inks, print-like. No 3D icons,
  no isometric scenes, no glossy blobs.
- 3D is Mino only. See §11.

## 9. Motion

Four tokens, and every animation names one:

| token | duration | use |
|---|---|---|
| FAST | 120 ms | state: hover, press, toggle |
| NORMAL | 200 ms | entrances, reveals, tab changes |
| SLOW | 320 ms | poses settling, cards turning, section emphasis |
| AMBIENT | 4–6 s | breathing, the curl's sway, the slow drift of a ground |

Easing `cubic-bezier(0.2, 0, 0, 1)`; the spring `cubic-bezier(0.34, 1.3, 0.64, 1)`
is reserved for Mino's reactions and the flashcard settle. Opacity and
transform only. `prefers-reduced-motion` collapses everything to a cut, and
under it the character is a still.

## 10. The learning landscape

Knowledge as territory: paths, valleys, ridges, islands, constellations. Used
for the Knowledge Map, progress, onboarding's "here is where you are", and
campaign grounds. Never forced: a review screen is a review screen.

Concept states, drawn as terrain: unknown (unmarked), discovering (a faint
outline), learning (hatched), practising (solid, light), understood (solid),
mastered (solid, dark, named), needs review (solid with a dashed ring).

## 11. Mino

Direction: intelligence, curiosity, calm, humour, empathy, sophistication,
friendly futurism, presence. One continuous soft body, wide at the base,
narrowing to a rounded top with a single curl; large glossy black eyes with
two highlights; a tiny mouth; faint blush; orange hoodie with the white
three-lobed mark; dark trousers. Cream, black, orange, white — nothing else.

Refused: generic AI mascot, robot, oversized eyes without character,
plastic toy sheen, glow, cyberpunk, Pixar-generic, anything that reads as
randomly generated.

The character is a **system of states** (`components/mino/machine.ts`), each
with expression, posture, motion, tempo, context and intensity — see
`MINO_CHARACTER_SPEC.md`, "State library". Mino looks alive, not hyperactive:
breathing and the curl's sway are the only self-motion.

Where Mino appears: hero (large, live), lesson (presence), onboarding
(listening, thinking), Home (a small figure), review (celebrating a real
milestone, resting when nothing is due), errors (subtle, never joking on
serious ones), empty states (offering the next step). Never as decoration
that does nothing.

## 12. Product UI

The interface stays the well-set book of `design-system.md`. From this
document it inherits: fluid display sizes, the atmosphere tokens for
editorial moments (a Focus session's black stage; a milestone's cobalt
field), the motion tokens, and the state library.

## 13. Editorial and marketing

Campaign compositions borrow the landing's grammar: one line in Newsreader,
one orange word, one figure, one field of colour, grain. Instagram squares
are the brand's own reference and remain its test: a post that would not
sit beside the existing ones is off-brand.

## 14. Don'ts

Purple-to-blue gradients · glassmorphism · glow · confetti on every answer ·
XP and badges · streak guilt · icons as filler · card grids · brains and
neural-network glows · robots · stock photos · dashboards as hero art ·
buzzwords · invented metrics, testimonials, partners · texture on text ·
motion without information · a second mascot.
