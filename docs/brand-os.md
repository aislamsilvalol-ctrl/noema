# NOEMA — Brand OS

> **Revised 2026-09-17 on the owner's reference set** (Vero ×2, Satoshi, Growcode,
> TWK Lausanne, ElevenLabs). The reference DNA: one monumental image as protagonist;
> cobalt/ultramarine as the universe with warm light and one ember accent, all inside
> the image or in a single button; print grain over digital imagery; one grotesk line;
> tiny mono metadata; monumental scale against a small figure seen from behind; the sky
> as negative space; radical reduction. Thesis: **knowledge is a territory, and NOEMA is
> the cobalt sky over it — a small figure seen from behind, crossing it. Mino is who
> walks.** Sections §6–§9 below are rewritten to that; §11 replaces the mascot with a
> sculpture.

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

## 6. Colour — one signature

One chromatic universe, everywhere, so that the landing in thumbnail reads as a
single brand: blue, bone, and one point of ember.

| token | value | role |
|---|---|---|
| `cobalt` | `#1D3FD1` | the sky; the primary action on light ground; the field of colour |
| `cobalt-deep` | `#1733AD` | hover, links, accent text on bone |
| `ultramarine` | `#12247A` | depth; the dark room (dark theme, the rail) |
| `ink` | `#0B1440` | all type on light ground — blue-black, never grey |
| `bone` | `#F6F2EA` | the ground of the product and of editorial statements; Mino's body |
| `ember` | `#E4471F` | the one warm signal: a button on blue, a word, the hoodie |

Inside the landscapes only: earth green, peach light, snow. They never become
UI colours, section grounds or chips. Green, purple, black and orange fields
are gone (they were the "several sites glued together").

Dark theme is the ultramarine room: ground `#0F1F6B`, bone type, ember as the
action. Same universe, lights off.

## 7. Typography — one grotesk

- **Display and interface: one grotesk** (Inter, variable 100–900, vendored). Headlines
  at weight 500–600, tracking −0.03 to −0.045 em, monumental sizes from the fluid
  scale. White on cobalt, ink on bone. Never two display families.
- **Wordmark: Newsreader** — the one serif on the site, the way a masthead is. It is
  drawn only by `components/brand/Wordmark.tsx`.
- **Reading surface** (lesson prose, notes): the serif remains for long text — a
  book is still the right shape for reading. It is a reading face, not a display face.
- **System: JetBrains Mono**, letter-spaced caps at 11–12 px for metadata, labels,
  states. Never a paragraph.

Fluid scale: `--text-display: clamp(2.75rem, 9vw, 6.5rem)`,
`--text-display-2: clamp(2rem, 5.5vw, 4rem)`.

Decision revised 2026-09-17: the reference set is unanimous on grotesk display;
the serif display of 2026-09-04 gave way. If the owner wants Satoshi or TWK
Lausanne's timbre, Satoshi is free on Fontshare (web licence) and is one vendored
file away; Inter carries the system until then.

## 8. Image — NOEMA Landscapes

Image is the protagonist. The product's imagery is one system, **NOEMA
Landscapes**: scenes built in Blender with Mino physically in them — same sun,
contact shadows, atmospheric depth, depth of field — rendered once, then passed
through one post pipeline (one curve, one grain, one chromatic bleed;
`scratchpad/grain.mjs` → AVIF/WebP at 1600/1000/640). Five sibling scenes:
**Valley** (hero: Mino small, seen from behind), **Two routes**, **Crest** (sitting,
looking out), **Trail** (walking, in profile), **Horizon** (almost all sky).

Rules: familiar, dreamlike, editorial, slightly impossible. No tourism, no stock,
no fantasy wallpaper, no sci-fi, no game concept art. The test: remove logo,
headline and button — is it still a NOEMA piece? Three landscapes side by side
without text must read as one campaign; they do because they are one scene.

No photography of people. No icons as illustration. Texture lives on the
landscapes and on editorial grounds, never on type, never in the product UI.

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

## 11. Mino — character sculpture, not mascot

Why the previous model failed: eyes at 18 % of the body height, a toy-like 1.5:1
proportion, a saturated glossy hoodie, studio-white lighting, always frontal and
waving. It read as a startup mascot.

The rebuilt Mino (Blender project revision 11+, `M2.*`): one continuous lathed
mass, 1.0 m tall and 0.44 m wide (2.3:1), a small curl off the crown, two small
dark eyes set into the surface and nothing else on the face — no blush, no
mouth; expression is tilt, gaze and posture. Material: bone porcelain (controlled
roughness, faint subsurface, a ceramic coat), the hoodie in matte ember with the
three-lobed bone mark, ink trousers. The silhouette test: curl + hood seam + wide
base must be enough in pure black.

Scenes, not poses: seen from behind in the valley, sitting on a crest, walking
the trail, looking at the map. Frontal only as the product avatar. Never a Funko,
vinyl toy, Pixar-generic robot, blob, or big-eyed cartoon.

Where Mino appears is unchanged from §11 of the first edition: lesson, onboarding,
Home, review, errors, empty states — always with a job.

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
