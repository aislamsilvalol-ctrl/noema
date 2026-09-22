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
Landscapes**: one world built in Blender (project `noema-landscapes-v3`) and
rendered from several cameras, so every scene is the same place — a ridged
range with snow on its crests, green flanks in light and shadow, a valley
with a worn track, a line of pines, one tree, a small house with an ember
roof, clouds, air — and Mino in it, seen from behind, walking toward the
range, at a few percent of the frame with his own shadow. Rendered in Cycles
(CPU, ~1100×619, 24 samples, denoised, a scatter volume for aerial
perspective, a low side sun, AgX) with a transparent sky, then finished by
one script (`persist/v3/post.mjs`): the sky is drawn there in the brand's
own cobalt-to-ultramarine with a breath of peach at the horizon, the render's
haze laid over it as light; then a split tone (ultramarine darks, peach
lights), halation, a soft vignette, two octaves of luminance grain, a hair of
chromatic aberration; delivered as JPEG + AVIF/WebP at 1600/1000/640.
Scenes: **Valley** (hero), **Routes**, **Trail**, **Horizon** (almost all
sky), and the **bleach** of the valley.

Rules: familiar, dreamlike, editorial, slightly impossible. No tourism, no
stock, no fantasy wallpaper, no sci-fi, no game concept art. The test: remove
logo, headline and button — is it still a NOEMA piece? Three landscapes side
by side without text must read as one campaign; they do because they are one
world.

**The overexposed treatment** (from the owner's seventh reference — a camera
bug he liked): the same frame burnt to bone, only the shadows left, in ink
(`post.mjs --mode=bleach`). The ground of the editorial statement, where ink
type sits on it. Digital × analog, literally.

No photography of people. No icons as illustration. Texture lives in the
image files — never in CSS, never on type, never in the product UI.

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

## 11. Mino — the character, drawn

Mino is the figure in the owner's own icon (`public/brand/mino/icon-512.png`):
one drop-shaped mass, widest low, its crown narrowing into a single short
curl that leans right; very large, tall, glossy black eyes set wide apart,
each with a big upper-left highlight and a small lower-right one; a faint
warm blush; a tiny low smile; the hoodie as a garment over the lower third —
a U neckline, short sleeves ending in bone mitts, a kangaroo seam, the
three-lobed bone mark — and two dark stubby feet under the hem. Matte
ceramic cream, black, coral-ember, bone: nothing else.

On screen he is a drawing: the SVG rig (`components/mino/rig/MinoRig.tsx`)
at every size, from the 28 px avatar beside a reply to the figure on the
Learn stage and the landing's close-up. It is vector, so it is the same
character at every size, costs no GL context and never falls back to a
poster. The WebGL stage was retired before launch — a drawn Mino that looks
right beats a live one that does not. Three 3D attempts (a toy at 1.5:1, a
2.3:1 "sculpture" with dot eyes, an egg in a bowl) were rejected by the
owner; they are not coming back.

In the landscapes he is a 3D mass seen only from behind or in profile — the
drop, the hood pouch, the curl, the feet — so the scene's own sun lights him
and casts his shadow; the face is never rendered in 3D.

Where Mino appears: the Learn stage (curious), beside every reply (the face),
Home's greeting, loading (thinking), empty states, errors, the landing's
teaching and close-up screens — always with a job, never as decoration on
every message. Never a Funko, a vinyl toy, a Pixar-generic robot, or a
big-eyed cartoon smiling at the camera on every screen.

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
