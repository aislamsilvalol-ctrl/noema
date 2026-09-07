# NOEMA — Design V3

What changed on 2026-09-06, why, and the answers to the ten questions the
brief ends with. Companion to `MINO_CHARACTER_SPEC.md` (the character),
`MINO_ASSETS.md` (the files) and `docs/design-system.md` (the tokens).

## 1. What the audit found

The product was already disciplined: no gradients, no blur, no glow, no
icon library, a hand-drawn dark mode. What still read as templated:

- **The landing was six identical bordered cards** in an alternating
  two-column grid, one per beat.
- **One label style everywhere**: `text-xs uppercase tracking-wide`,
  74 times across the app, six on the landing alone.
- **A type-scale bug**: `text-5xl` used twice with no such token, so the
  opening line shrank on desktop.
- **Copy with an LLM cadence**: five of seven titles began "Ele/Eu +
  verb"; "nem antes, nem depois"; the "not X, but Y" eyebrow.
- **Numbers without context** (mastery bars showing `62`, `48`, `20`).
- **A pretend course outline** in onboarding (`t.landing.demoSteps`).
- **`/chat` without its context rail**, so the lesson read as a chat.
- **Mino as a still image** in the hero, a drawing everywhere else.
- Four shadows outside the system; half the interface set in `text-xs`
  and `text-sm`.

## 2. The direction

The reference is the brand's own Instagram: cream ground, one bold black
line with one orange word, the character lit like an object on a table,
a small annotation, and nothing else. The page borrows that discipline:
hairlines and space instead of boxes; two display sizes reserved for the
two lines that matter; a monospace label or an italic serif kicker instead
of small caps; the only card on the page is the flashcard, because it is
a card. Orange is a signature, used where the eye should go (the subject
under the title, the step that is in view, the module that is "now"),
never as a wash.

## 3. Mino, in three dimensions

The character was modelled and lit in Blender from the reference posts
(spec, "Official renders") and now runs in the interface as a model, not
a picture:

| Layer | What it is |
|---|---|
| `public/brand/mino/mino.glb` | 356 KB (from 1.8 MB): pruned, welded, simplified to 45 %, quantized, meshopt-compressed. 51 k triangles, 8 materials, no textures. |
| `three/MinoStage.tsx` | React Three Fiber scene. Reads the controller's `Pose` each frame and damps the rig nodes into it: `Neck` (turn, tilt, gaze follow, breathing), `EyeR/L` (blink, squint, gaze), `mouth` (six shapes by scale), `ShoulderR/L` (seven hand poses; wave and cheer beats), `Tip` (sway), root (lean, lift). Warm key with soft shadows, fill, rim, a synthetic `Environment` of light formers, a contact shadow. ACES tone mapping. |
| `three/MinoCanvas.tsx` | Mounts the stage on the client on approach (240 px root margin); frame loop on demand, paced at 30 fps (24 on medium tiers, 4 under reduced motion) and stopped off screen or in a hidden tab; DPR `[1, 1.75]` high, `[1, 1.25]` otherwise; the rendered still underneath until the first frame; falls back to the still on `low` tier, no WebGL, `saveData`, or a thrown stage (error boundary). |
| `Mino` / `MinoLive` | The stage at `lg`, `xl`, `fill`; the SVG rig at `xs`, `sm`, `md`. The rig is drawn to the model's silhouette. |

Character system, as the state machine already names it: idle, curious,
listening, thinking, teaching, pointing, reading, writing, happy,
celebrating, sleepy, confused, wave, questioning, correcting, exam,
concerned. The landing scripts them by scroll (listening at step 1,
questioning at 2, writing at 3, teaching at 4, curious at 5, thinking at
6, correcting at 7, reading at 8, wave at the close); the product screens
drive them from real events through `MinoPresence`.

Why R3F and not a video, sprites or Rive: the model exists and is tiny;
the states are transforms on named nodes, which a scene graph does for
free; pointer-following gaze is real-time by construction; and the same
`Pose` drives the SVG fallback, so nothing is authored twice.

### Performance budget

| Item | Budget | Measured |
|---|---|---|
| Model over the wire | ≤ 500 KB | 356 KB (`mino.glb`) |
| three + fiber + drei chunk | loaded only where a stage mounts, never in the shared bundle | see the build table below |
| Frame loop | ≤ 30 fps, 0 fps off screen / hidden tab | paced by `Pacer` |
| Pixel ratio | ≤ 1.75 | by tier |
| Stills | ≤ 220 KB each | 206–214 KB (800 px PNG, alpha) |
| Layout shift | none | the still occupies the box first |

## 4. The landing

Sections, in order, and what each shows rather than says:

1. **Opening** — "Learn anything." with the subject turning under it; the
   field; the real tutor's first thirty seconds. Mino, live.
2. **How Noema teaches** — eight numbered steps, each with a fragment:
   the learner's sentence; the probe ("Then we will not start with
   Freud"); the path with "now"; the lesson text; the question with
   confidence; the mastery list that reorders after a wrong answer; the
   explanation that changes; the card that comes back nine days later.
3. **Why not open a chatbot?** — four plain pairs.
4. **Rhythm** — the same lesson, Normal and Focus.
5. **Close** — the line again, the button, Mino waving.

Copy rules applied: say what it does, name the mechanism, no "unlock",
"revolutionise", "smarter not harder", "the future of"; the learner's
subject appears in the sentences once typed.

## 5. The product

`/chat` now has the study rail: subject and objective, where we are
(module › lesson › concept), what the engine thinks you know with
misconceptions flagged, parked topics, the newest memory fold, today's
movement. Onboarding shows the engine's real next steps instead of a
fake outline. The uppercase label is gone from every screen.

## 6. The ten questions

1. **Is Mino really 3D?** Yes: a GLB model rendered in WebGL, lit and
   posed at runtime. The stills are renders of the same model.
2. **Anywhere the old 2D Mino remains without a technical reason?** The
   SVG rig draws only the 28/48/80 px figures (a GL context per message
   avatar is not defensible) and the no-WebGL fallback. Both are technical
   reasons, and the rig is drawn to the model's silhouette.
3. **Recognisable as NOEMA without the logo?** The cream ground, the
   orange word under a black display line, hairline rhythm, and the
   character itself. Yes.
4. **Could the copy belong to another AI SaaS?** Every sentence names a
   mechanism (the probe, the path, the confidence, the nine days). No.
5. **Cards, badges, icons or animations without function?** Removed. The
   remaining card is a flashcard; the remaining animation is the subject
   turning, the step number lighting, the mastery bar moving, the card
   flipping — each carries information.
6. **In five seconds, why Noema over a chatbot?** The opening line and
   lead say it; the comparison section makes it explicit.
7. **Does the landing demonstrate?** The hero calls the real tutor; the
   question is answerable; the mastery moves; the explanation changes.
8. **Mobile designed as mobile?** The figure is small and first, the
   steps stack with the fragment under the sentence, the field is a
   single underlined line, nothing depends on hover.
9. **Acceptable 3D performance?** The budget above; the loop stops off
   screen.
10. **Human, careful, or vibecoded?** The remaining risk is inside the
    product's dense screens (`text-xs`/`text-sm` everywhere); the landing
    and the study rail are the standard the rest should follow.

## 7. Not done, said plainly

- The WebGL stage could not be seen in this session's browser (the
  preview pane does not composite while hidden, and the Chrome bridge was
  not connected). It is verified structurally (rig nodes and positions
  via three's loader in Node), type-checked, tested for its fallback, and
  guarded by an error boundary. Look at it on the deployed site.
- The product's inner screens still carry the older density; the study
  rail and landing set the direction, they do not finish it.
- Mouth shapes are scale/rotation of one mesh; a modelled set of mouths
  would be finer.
