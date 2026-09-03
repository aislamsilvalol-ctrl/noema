# NOEMA V2 — Design System

*Orange is the signal. Mino is the face. Learning is the interface.*

This is the system the V2 screens are built from. It extends the existing
token layer (`apps/web/src/styles/globals.css`, `tailwind.config.ts`) rather
than replacing it: the warm neutral ramp, the type faces, the reading measure
and the motion discipline were already right. What was missing is named and
added here — an orange scale with measured contrast, a designed dark ground,
radius/elevation/motion scales, a button hierarchy, a Mino state system, and
primitives so consistency stops depending on discipline.

Every value below is behind `NOEMA_DESIGN_V2` until validated; then V1 CSS is
removed. Two products are not maintained.

---

## 1. Identity in one paragraph

Warm white, charcoal text, one orange that means *do this next*. Serif where
you read, grotesque where you act. Space instead of boxes; hierarchy instead
of borders. Mino appears where a teacher would — not everywhere. In the dark,
the room goes warm-black and the same orange becomes a single light on the
desk. Nothing glows, nothing bounces, nothing is a gradient blob.

Not: ChatGPT (transcript + composer + sidebar), Duolingo (streaks, hearts, a
bouncing owl), Notion (a blank document), an AI SaaS template (purple, stars,
glass).

---

## 2. Colour

### 2.1 The orange ramp — chosen by measurement

WCAG contrast measured against the V2 grounds (script in the audit commit).
AA small text = 4.5:1, AA large text / UI = 3:1.

| step | hex | on warm white `#FBF8F3` | white text on it | on warm black `#141311` | charcoal text on it |
|---|---|---|---|---|---|
| 50 | `#FFF6EE` | 1.01 | — | 17.4 | 16.4 |
| 100 | `#FFE8D6` | 1.12 | — | 15.7 | 14.8 |
| 200 | `#FFD0AD` | 1.33 | — | 13.2 | 12.4 |
| 300 | `#FFB07A` | 1.69 | — | 10.4 | 9.8 |
| 400 | `#FF8F47` | 2.14 | — | **8.2** | 7.7 |
| 500 | `#F26B1D` | 2.87 | 3.05 (UI only) | **6.1** | **5.7** |
| 600 | `#D9570F` | 3.73 (large only) | 3.95 (large only) | 4.7 | 4.4 |
| 700 | `#B5450C` | **5.19** | **5.50** | 3.4 | 3.2 |
| 800 | `#8F370B` | 7.29 | 7.72 | 2.4 | — |
| 900 | `#6B2A0A` | 10.1 | 10.7 | 1.7 | — |

Consequences, stated as rules:

- **Light mode primary is 700 (`#B5450C`).** It is the only step that passes as
  small text on the ground *and* as a button with white text. The current
  accent was measured-correct; it keeps its job.
- **Light mode "intelligent orange" is 500 (`#F26B1D`)** — for large display
  accents, progress fills, Mino's sweatshirt, selected states with a
  charcoal label, the ambient light. **Never small text on white** (2.9:1).
- **Dark mode primary button is 500 with charcoal text** (5.7:1). **Dark mode
  link/text accent is 400 (`#FF8F47`)** (8.2:1). The dark room gets the
  brighter orange — that is the one light, and it is deliberately more
  present than in daylight.
- 50–200 are surfaces and soft fills (light) or are not used (dark).
- `--critical` stays a genuinely different hue (`#8F3A33` / lifted in dark) so
  error and brand never blur for colour-blind readers.

### 2.2 Tokens

```css
/* brand */
--noema-orange-50 … --noema-orange-900   (the ramp above, same in both themes)

/* semantic — these are what components use */
--primary            light: orange-700   dark: orange-500
--primary-fg         light: #FFFFFF      dark: #1C1917
--primary-hover      light: orange-800   dark: orange-400
--accent-text        light: orange-700   dark: orange-400
--accent-soft        light: orange-100   dark: #2A1A0F
--signal             light: orange-500   dark: orange-400   (progress, active, focus, Mino light)

/* ground and text */
--surface            light: #FBF8F3 (warm white)   dark: #141311 (warm black)
--surface-raised     light: #FFFFFF                dark: #1E1C19 (graphite)
--surface-sunken     light: #F4EFE8 (soft cream)   dark: #0F0E0D
--line               light: #E9E3DA                dark: #2B2824
--ink-*              (existing warm ramp; dark set re-based on the warm black)
--text               light: #1C1917 (charcoal, 16.5:1)   dark: #F7F4EF (16.9:1)
```

The existing `--accent` becomes an alias of `--accent-text`, so nothing breaks
while screens migrate.

### 2.3 Where orange may appear

Primary action (one per screen), selected navigation, focus ring, progress,
active learning signal, Mino's light, links. **Not** headings, not borders,
not backgrounds of large regions, not fifteen chips. If two things on a screen
are orange, one of them is wrong.

### 2.4 Dark mode is its own design

Ground is warm black, not inverted cream. Elevation is by surface lightness
(`--surface` → `--surface-raised`), never by shadow. The accent lifts to 400/500
because a dark ground eats saturation. Mino gets a faint warm light behind him
(`orange-500` at 6–8% opacity, blurred) — a lamp, not a glow. No neon, no
gradient mesh.

Theme control: **Light / Dark / System**, in Settings → Appearance and in the
shell. Applied as `data-theme` on `<html>`; the switch transitions
`background-color` and `color` over `--motion-normal` with no white flash
(the ground token changes, the page does not remount).

---

## 3. Typography

Faces are kept: **Newsreader** (display, reading), **Inter** (UI), **JetBrains
Mono**. They already carry the identity; changing them would be change for
its own sake.

| role | face | size / leading | use |
|---|---|---|---|
| Display | Newsreader | 48–64 / 1.05 | landing headline only |
| Title | Newsreader | 32 / 1.2 | screen titles |
| Section | Newsreader | 24 / 1.3 | lesson section, subject name |
| Reading | Newsreader | 17 / 1.65, 68ch | lessons, Professor turns, notes |
| UI | Inter | 13–15 / 1.5 | controls, labels, nav |
| Meta | Inter | 12 / 1.5, tracking +0.04em, uppercase | eyebrows only, never body |
| Mono | JetBrains Mono | 13 / 1.55 | code, numbers |

Rules: reading width **60–75 characters** for anything a learner reads for
more than a sentence; UI text never below 13px; uppercase only for eyebrows.
The Professor's turns are set in the reading face, not the UI face — that one
change is most of "not a chatbot".

---

## 4. Space, radius, elevation

- **Space:** 4px base; layout in 8/12/16/24/32/48/64/96. More margin than
  border. A group is separated by space first, a rule second, a card last.
- **Radius scale:** `--radius-sm: 6px` (chips, inputs), `--radius-md: 10px`
  (buttons, cards), `--radius-lg: 16px` (modals, flashcard), `--radius-full`.
  Nothing else. No 24–32px pillows.
- **Elevation:** `--elevation-0` none; `--elevation-1` `0 1px 2px
  rgb(28 25 23 / 6%)`; `--elevation-2` `0 8px 24px rgb(28 25 23 / 8%)` (modals,
  popovers). In dark, elevation is surface lightness, shadows off.
- **Cards** only when the thing *is* a card (a flashcard, a plan block you act
  on). Lists, sections and groups are typography and space.

---

## 5. Motion

```css
--motion-fast:   120ms   /* state: hover, press, toggle */
--motion-normal: 200ms   /* enter: reveal, panel, theme */
--motion-slow:   320ms   /* flip, layout shift that must be followed */
--ease-standard: cubic-bezier(0.2, 0, 0, 1)
--ease-spring:   cubic-bezier(0.34, 1.3, 0.64, 1)   /* Mino reactions, celebrate — small amplitude */
```

Animate `opacity` and `transform` only (plus SVG `opacity`/`transform` for
Mino). Everything honours `prefers-reduced-motion: reduce`: transitions drop
to `--motion-fast` or 0, scroll beats become static, Mino holds one pose. No
artificial typing delays (the brief's rule; streaming is real or nothing).

Microinteractions: button press = 1px translate + `--motion-fast`; flashcard
flip = `rotateY` over `--motion-slow` with the answer face pre-rendered (no
layout shift); progress = width over `--motion-normal`; tabs = underline
translate; Mino = one short spring, then still.

---

## 6. Iconography

None by default. The product has shipped without an icon library and reads
better for it. Icons are allowed where they improve recognition over a word —
navigation on the mobile bar (five, hand-drawn to one grid), the theme toggle,
close/back. No Lucide sprinkled through lists. No robot, no sparkle, no star.

---

## 7. Components (`apps/web/src/components/ui/`)

Primitives, each styled once from tokens, adopted screen by screen behind the
flag. Existing hand-written class strings are replaced, not wrapped.

| primitive | notes |
|---|---|
| `Button` | `primary` (orange, one per screen) · `secondary` (neutral outline) · `ghost` · `destructive` (critical). Sizes sm/md/lg. Press microinteraction. `busy` state with label swap, no spinner ring. |
| `Input`, `Textarea`, `Select` | From `Field`; label, hint, error slot; focus ring in `--signal`. |
| `Modal`, `Popover`, `Tooltip` | Focus-trapped, Escape closes, `aria-*` correct, elevation-2. |
| `Progress` | Linear, `--signal` fill; a *path* variant for learning position (where / done / next), never a bare %. |
| `Tabs` | Underline moves; keyboard arrows. |
| `Toast` | One region, bottom; status line for "Saved", "Review complete". |
| `Notice` | Empty / error / info states: title, body, one action; Mino optional slot. Error copy is always human; provider text never rendered. |
| `LessonBlock` | Concept · Example · Definition · Quick Check · Think About It · Mini Exercise · Flashcard · Diagram — the Professor's structured turns. |
| `SessionHeader` | subject → topic → objective, progress; quiet. |
| `Mino` | §8. |

---

## 8. Mino — state system

The art is the existing art: same six files, same map in `brand/mino.ts`.
Official art remains a filename swap. What V2 adds is *behaviour*.

```ts
type MinoState =
  | 'idle'        // present, breathing (2–3% scale, 4s), blinks
  | 'thinking'    // AI working: slight lean, eyes down-left, subtle
  | 'teaching'    // streaming: pointing pose, still
  | 'listening'   // learner typing: attentive, slight turn toward input
  | 'celebrating' // correct / review done: one short spring, then idle
  | 'curious'     // empty states: hero pose, head tilt
  | 'reviewing'   // review mode: studying pose
  | 'sleeping'    // long idle (>90s): eyes closed, no motion
  | 'confused'    // learner said "não entendi": eyes wide, brief
  | 'focused';    // test mode: reading pose, minimal
```

Mapping to the art: idle/curious → `hero`; thinking → `thinking`; teaching →
`pointing`; listening/reviewing/focused → `reading`/`studying`; celebrating →
`celebrating`; sleeping/confused → `hero` with eye overlay. Poses swap with a
crossfade (`opacity`, `--motion-normal`); micro-motion is CSS on `transform`
of the whole figure plus two SVG groups (eyes, arm) exposed by id. Total cost:
the same ≈24 KB of SVG, no runtime library, no Lottie.

Driven by product events, not timers: `stream:start → thinking`,
`token:first → teaching`, `input:focus → listening`, `answer:correct →
celebrating`, `review:complete → celebrating`, `error → curious` (never
"sad"), `idle > 90s → sleeping`. Reduced motion: state changes still swap the
pose, nothing moves.

Where Mino appears: landing hero (reacts to the field), dashboard greeting
(sometimes), Professor (small, beside the session header), review completion,
empty states, meaningful loading (creating a path). Not in lists, not in
settings, not on every request.

---

## 9. Button hierarchy and the one-action rule

Each screen has one primary action, and it is orange: *Continue learning*,
*Start reviewing*, *Hand in*, *Check my explanation*, *Send*. Everything else
is secondary or ghost. The same verb means the same thing everywhere:
**Continue** resumes the last lesson; **Review** opens due cards; **Practice**
opens a quiz; **Ask Mino** opens the Professor at the current concept;
**Complete** ends and records.

---

## 10. Language

Learner-facing words: Aula, Professor, Revisão, Progresso, Praticar,
Continuar, Anotações, Assunto, Caminho. Never: embedding, vector, token,
retrieval, pipeline, provider, model. Errors: "Não consegui carregar sua aula
agora." + Tentar de novo. The API's own sentences are shown only for the
learner's own data (an import report, a validation message) — never for a
model or network failure.

---

## 11. Signature

What someone should recognise as Noema without a logo: the warm white page
with charcoal serif and one orange action; Mino's silhouette and sweatshirt;
the learning path drawn as *where I am / what I learned / what's next* rather
than a percentage; lesson blocks (a Quick Check looks like a Quick Check
everywhere); the still, warm dark room with one light.
