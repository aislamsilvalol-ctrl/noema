# NOEMA motion system (2026-09-30, landing V6 the same day)

> **The landing is V6** (`components/landing/v6/LandingV6.tsx`, `styles/landing-v6.css`).
> The first pass (ambient films on the V5 page) read to the owner as "nothing
> changed"; V6 rebuilt the page as pinned, scroll-driven scenes. V5 stays in the
> tree; rollback is one import in `app/page.tsx`.

Companion to `docs/brand-os.md`. The landing is a film in five scenes; the
product moves only to explain state.

## Diagnosis (before)

- The landscapes were stills: a strong frame, nothing alive in it.
- After the hero the page alternated bone and cobalt blocks with hard cuts,
  so it read as sections glued together, not scenes.
- The territory metaphor stopped at the title: "What you learn becomes
  territory" sat on a flat cobalt field above an abstract diagram.
- The pale "bleach" frame was cropped to sky; Mino, sitting on a rock at its
  foot, was cut out.
- The interface Mino did not breathe, although the rig's docs said it did.
- The "blank sections" in full-page captures were a capture artefact
  (headless tabs throttled in the background), not a bug users saw; the
  capture tool now keeps every tab in the foreground.

## Motion language

| Layer | Speed | Rule |
|---|---|---|
| Camera (landing) | 14 s settle on arrival, then a 40 s push each way | Transform only, on `.scene-camera` / `.scene-drift`; never baked into footage, so a loop never jumps |
| Environment (landing films) | Continuous, near-imperceptible | Grass, haze, water; locked-off camera; no particles, no new objects |
| Mino in the landscapes | Slow | Breath, weight shift, a head tilt that holds and returns |
| Mino in the interface | 5.2 s breath, rare blinks and glances, pointer gaze | State machine in `components/mino/machine.ts`; the breath is CSS on `.mino-figure`, only on animating tiers |
| Type | Once | `data-reveal`: 14 px rise + fade, 560 ms, `cubic-bezier(0.2, 0, 0, 1)`; no per-letter motion |
| Interface | 120–320 ms | Existing tokens; motion explains state, never decorates |

Easing token: `--ease-camera: cubic-bezier(0.2, 0, 0, 1)`.

Film stock: stills carry grain; compressed films lose it, so a grain texture
(`/brand/texture/grain.webp`, overlay, 9 %) steps over a scene only while its
film plays.

## Storyboard (V6)

Mechanics: `useSceneProgress` writes `--p` (0→1) on each pinned scene from one
passive scroll listener and one rAF; everything that moves is CSS on `--p`
(transform, opacity, clip-path; stroke-dashoffset for the map). Two repeated
transitions: the camera pushing into a landscape, and the next ground rising
from the bottom of the frame. Reduced motion or no hydration: no pinning, every
scene static and complete.

1. **Terraces (hero), pinned.** Monumental headline with the rotating subject; the camera pushes toward Mino; bone rises into the next scene.
2. **Manifesto, pinned.** The statement lights up word by word.
3. **Mino, pinned.** Mino large on a ridge (film); his four lines arrive one by one.
4. **How it works, pinned.** Four steps, giant cobalt numbers, valley/trail/bleach/horizon crossfading, a progress rule.
5. **Territory → map, pinned.** The highland of paths gives way to the cobalt map, whose lines draw in.
6. **The live tutor** on bone.
7. **Today** — the daily plan.
8. **Horizon** — the close, monumental type, CTA, footer.

## Storyboard (V5, superseded)

1. **Valley (hero).** Cobalt sky, Mino from behind on the path, breathing. Headline in the sky.
2. **Statement** on bone.
3. **Bleached frame.** The same world burnt to paper; Mino sits on a rock and turns toward you, then back. Carries the page from blue to bone.
4. **One question.** The live tutor demo (product).
5. **Territory → map.** The highland of paths, Mino at a fork, the title in its sky; at its foot the land dissolves into the exact cobalt the knowledge map is drawn on, and the map begins.
6. **Trail.** "The more you learn, the better it teaches you." Foreground grass in the wind, Mino about to take a step.
7. **Today.** The daily plan on bone (product).
8. **Horizon.** Mino tiny on an immense plain facing the mountains; the call to action in the sky.

## Higgsfield assets

Project "NOEMA — landing motion". Every film is image-to-video with the
production still as both first and last frame, so the loop closes on the
frame the page already shows and Mino stays exactly the approved render.

| Scene | Job | Model | Source | Length | Desktop | Phone |
|---|---|---|---|---|---|---|
| valley | 94348763 | Cinema Studio Video | valley.jpg | 10 s | 1600×900 VP9 203 KB / H.264 449 KB | 540×960 88 KB / 168 KB |
| bleach | 77c6510e | Cinema Studio Video | bleach.jpg | 10 s | 105 KB / 302 KB | 61 KB / 132 KB |
| routes | 49af5abe | Cinema Studio Video | routes.jpg | 10 s | 399 KB / 661 KB | 150 KB / 245 KB |
| trail | 94dcaf30 | Cinema Studio Video | trail.jpg | 10 s | 244 KB / 466 KB | 99 KB / 180 KB |
| horizon | cb2642e2 | Cinema Studio Video | horizon.jpg | 10 s | 172 KB / 439 KB | 66 KB / 163 KB |
| terraces (V6 hero) | still b0e05054 (GPT Image 2.5, refs valley+routes); film 661a2070 | Cinema Studio Video | terraces.jpg | 10 s | 306 KB / 534 KB | 129 KB / 220 KB |
| mino (V6) | still b6165f2e (GPT Image 2.5, refs trail+valley); film b8c6ea28 | Cinema Studio Video | mino.jpg | 10 s | 211 KB / 448 KB | 103 KB / 192 KB |

Tests before production: `2fbb2db1` (Cinema Studio, 5 s) and `aa03f315`
(Wan 2.7, 8 s) on the valley. Cinema Studio kept Mino identical and moved
him more; Wan drifted slowly and did not return to the first frame. Credits
used: 75 of 220 for the V5 films, then 20.5 for V6 (two stills with two
candidates each, two films); about 125 left.

Recipe (per scene): *locked-off tripod shot, the camera never moves; the
scene as it is; Mino breathes / shifts weight / tilts his head and returns;
wind in the grass, haze, water shimmer; keep light, colours and composition
exactly; no new objects, no text, no particles, no camera motion;
photographic, film grain, quiet.*

Post: 1 s crossfade of the tail into the head (a seamless loop), 24 fps, no
audio, BT.709 tags; VP9 CRF 40 and H.264 CRF 27; the phone cut is a 9:16
crop anchored on Mino (valley 84 %, bleach 94 %, routes 50 %, trail 60 %,
horizon 92 %). Encoder script and review sheets live in the session
scratchpad; re-run from the sources in Higgsfield if a scene changes.

## Loading and performance

- The still is the LCP and paints first; nothing about it changed.
- The hero film is chosen 1.2 s after load, on idle; the others only when
  their scene is within 200 px of the viewport. `preload="none"` until then.
- A film plays only while on screen and fades in only once it is actually
  playing, so a slow network shows the still, never a black box.
- No film at all for `prefers-reduced-motion` or Save-Data.
- Whole page, all five scenes watched: 1.1 MB (VP9) on desktop, 0.46 MB on a
  phone. No WebGL, no animation library, no render loop.

## Mino

The character is unchanged, by the owner's decision (2026-09-25). In the
landscapes he now lives: breath, weight, a glance toward you in the bleached
frame. In the interface the rig breathes (new), and keeps its existing
states, rare blinks, glances and pointer gaze.

## Open

- Real Safari/iOS playback check (inline, muted autoplay) on a device.
- The knowledge map could draw its lines in on arrival instead of fading in.
- Product micro-motion beyond the breath (correct/wrong feedback, mastery
  change) is still the existing implementation.
