# Mino — character spec

The permanent reference for drawing and animating Mino. Anything that moves
the character must pass this document before it ships.

## Asset audit (2026-09-04)

Searched: the repository (every tracked file and every branch, including
`claude/mino-svg-polish`), the machine's Desktop, Downloads, Documents,
Pictures and iCloud folders, the other project folders, and the image
generation account attached to this workspace.

| Where | What was found | Verdict |
|---|---|---|
| `apps/web/public/brand/mino/*.svg` | Six hand-authored placeholder SVGs, ~2 KB each, 14 primitives, flat grey body with an orange rectangle for the hoodie. `MINO_ASSETS.md` calls them "explicitly not commissioned character art". | Not source art |
| Repository, all branches | No PNG, WebP, GLB, GLTF, FBX, Lottie, Rive, sprite sheet or source render named or resembling Mino | None |
| Machine (home folders, iCloud) | No file matching mino / noema / mascot in any image or model format | None |
| Image-generation account | Ten uploads and the generation history: campaign art for another company (polygonal wolves), toy product shots. No Mino | None |
| This request | Describes "the provided assets" in words; no files were attached | Description only |

**Conclusion: there is no source art of Mino.** The written description in
the brief is the only reference. That changes what "do not redesign the
character" can mean here: there is nothing to preserve except the
description, so the rig in `apps/web/src/components/mino/rig/MinoRig.tsx`
is authored from it and marked **provisional**. It is built exactly the way
the final rig will be built — separate layers with fixed transform origins —
so official renders replace geometry in place without touching the
controller, the states or any screen.

**Blocked on the owner:** the official renders (or a model). Until they
arrive, every state is drawn against this spec.

## Reference (2026-09-05)

The reference arrived with the Professor Engine brief: the `@noemalearn`
Instagram posts (profile picture and three carousel covers). They settle the
character:

- one continuous soft body, wide at the base, narrowing to a rounded top,
  with a single small curl pointing back-right — not a ball on an egg;
- very large, tall, glossy black eyes with a large upper-left highlight and a
  small lower-right one; body-coloured lids;
- a tiny, low mouth; a faint warm blush; short rounded arms; stubby feet;
- the orange hoodie over the lower body with the white three-lobed NOEMA
  mark on the chest; dark trousers in the standing pose;
- cream body, black eyes, orange, white — nothing else.

The rig (`rig/MinoRig.tsx`) was redrawn to this silhouette inside the same
layer contract. It is still a drawing of the reference; the posts are
screenshots, not vector sources, and were not traced or generated from. The
official renders remain the right replacement, layer for layer.

## Official renders (2026-09-06)

Mino now exists as a 3D model. It was modelled, lit and rendered in Blender
5.2 (Eevee) from the reference posts, entirely in code — no image model, no
tracing — in the workspace's 3D Jutsu project
<https://higgsfield.ai/3d-jutsu/24b11671-d3e1-4c7d-af71-01cb72cbbc04>
(project id `24b11671-d3e1-4c7d-af71-01cb72cbbc04`; the committed scene
also exports a GLB).

The model, in metres, standing on z = 0, about 1.05 m tall:

- **Head**: a UV sphere (r 0.31, centre z 0.76) displaced into a drop —
  the lower 40 % keeps its round, heavy cheeks (×1.05 wide, ×0.93 tall);
  above that the radius narrows by `1 − 0.62·u^2.1` and rises by
  `0.065·u^1.4` toward the crown. The head is the widest part of the
  character. One short, chubby tip (bevelled curve, r 0.04, tapering to
  0.4) curls from the crown toward the character's left.
- **Face**: placed *on the head's surface* by `face_point(x, z)`, which
  inverts the displacement. Eyes: black glossy ellipsoids r 0.057 scaled
  (1, 0.5, 1.42) at x ±0.108, z 0.765, sunk 13 mm in; a big highlight upper-
  left and a small one lower-right, both white, on the surface. A tiny
  smile (bevelled curve r 0.0068) 0.105 below the eyes. Blush: two
  flattened discs at x ±0.22, 30 % alpha.
- **Body**: a sphere r 0.235 at z 0.35, ×0.86 deep, flattened below the
  equator and tapered 12 % toward the collar, in the hoodie; a darker
  collar torus, a pocket seam, the three-lobed white mark on the chest at
  z ≈ 0.38. Sleeves are bevelled curves (r 0.05) from the shoulders at
  (±0.20, −0.02, 0.45); hands are skin spheres r 0.058. Legs are dark
  curves r 0.062 with flattened dark feet.
- **Materials**: skin `#f6efe3`, roughness 0.55, subsurface 0.35; hoodie
  `#f26b1d`, roughness 0.7; trousers `#2b2a33`; eyes `#0d0b0a`, roughness
  0.1 with a clear coat; mark and highlights `#fbf8f3`.
- **Light and camera**: a warm key disc (330 W, ⌀1.4 m) up-left in front, a
  wide fill (100 W) low right, a rim (150 W) behind right; a faint warm
  world. Camera 65 mm at (0.5, −3.0, 0.62) aimed at z 0.60 — front three-
  quarter, slightly below the eye line. Khronos PBR Neutral, transparent
  film, 1000 px.

Poses are arm curves and a small head turn, rendered as queries against
the committed scene (one render per query; the worker's 5-minute limit
holds one render, not four). Shipped in `apps/web/public/brand/mino/3d/`
at 800 px: `idle`, `wave`, `think` (hand to the chin, eyes up), `point`.
`components/mino/Mino3D.tsx` shows them; the landing hero and close use
them. The live rig (`rig/MinoRig.tsx`) was redrawn to the same silhouette,
so the still figure and the moving one are the same character.

## Technical decision

| Option | Verdict | Why |
|---|---|---|
| Three.js / React Three Fiber | Rejected | No model exists. Faking a 3D mascot from a generated mesh drifts on every angle (§58 of the brief); a real rig would also cost the landing 500 KB+ of runtime for a character that only needs eyes, head, mouth and hands to move. |
| Rive | Deferred | The right tool once official art exists — state machine, inputs, small runtime. Today it would mean vectorising a character that has not been drawn; "visual fidelity takes priority" (§57) cannot be met with nothing to be faithful to. Revisit when renders arrive. |
| Spine | Rejected | Same as Rive with a heavier runtime and a licence. |
| Sprite sheets | Rejected | Frame-based; no real-time gaze or spring motion; every new state is more frames. |
| **Hybrid layered 2D (chosen)** | **Adopted** | One SVG with ten layers, transforms set from a pose, CSS transitions between poses, a rAF spring for gaze/head, ~5 KB, no dependency. Real-time by construction; replaceable layer by layer. |

## Proportions of the live rig (rig units, 480 × 480 box)

- One outline for head and body: a bell. The dome is the narrow end, widest
  at eye level (x 128–352 at y 198); the outline eases in at the waist
  (y 292) and flares to the base, the widest part of the figure (x 108–372
  at y 392), closing at y 432. Nothing sits on anything.
- Eyes: two tall ellipses, rx 26 × ry 34, centres (194, 194) and (286, 194).
  Interpupillary distance 92 — wide-set. Eye height ≈ ⅓ of the dome's
  height: **large**.
- Mouth: on y 258, 18–32 units wide, never taller than 18 at full open.
- Tip: a single short teardrop on the crown at (240, 58), leaning right,
  ~36 units tall. One tip, not hair, not a spiral.
- Hoodie: from the waist down on the body's own outline, collar dipping at
  the front; the mark on the chest centred on (240, 353).
- Hands: round mitts, radius 16, on short sleeves of stroke 22, shoulders at
  (152, 330) and (328, 330).
- Feet: two body-coloured ellipses under the hem, at (200, 437) and (280, 437).
- Ground shadow: an ellipse 224 × 20 under the figure, 10% black. It shrinks
  when the figure lifts.
- Avatar crop: at 28 px the rig frames the head (`viewBox 96 28 288 288`);
  every other size shows the whole figure.

## Colours

| Part | Light | Dark | Note |
|---|---|---|---|
| Skin (body, head, hands) | radial `#fbf6ec → #efe6d6 → #d9ccb6` | same | Cream stays cream in dark mode. Never recoloured. |
| Hoodie | radial `#ff8f47 → #f26b1d → #c9500f` | same | The brand's signal orange. Collar `#c9500f`, pocket `#d9570f`. |
| Mark on the chest | white ring `#fbf8f3`, orange centre `#f26b1d` | same | Placeholder for the official Noema mark; drawn, never generated. |
| Eyes | radial `#2a2622 → #0f0d0b` | same | Two highlights: 6-unit at upper-left, 2.5-unit at lower-right. The highlights carry the gaze. |
| Mouth | `#3d3831` stroke, filled when open | same | |
| Cheeks | `#f4b99a` at 35% | same | Warmth, not blush. |
| Curl | `#d9ccb6` | same | The skin's shadow tone. |
| Environment (dark) | a warm lamp glow behind the figure via `.mino::before` | — | No orange outline around the body. |

## Materials

Soft matte plastic: one broad radial highlight up-left on the head and body,
no specular hot-spot, no rim light on the body. Gradients are the only
shading; there are no strokes on the skin. The hoodie is the same material
in orange.

## Face — expression limits

Eyes: open (1.0), blink (0 for 140 ms), focused (lower lid up ~30%), happy
(lower lid up ~70%, the eye becomes a curve), sleepy (upper lid down to 15%
open). The eye never changes shape otherwise: no wide "surprised" eyes, no
eyebrows, no pupils that leave the eye.

Mouth: six named shapes — neutral, smile, open (speech), think (a small
asymmetric line), o, flat. No teeth, no tongue, no lip sync beyond
open/closed.

Gaze: pupils travel at most 9 units in any direction; the head follows at
35% of gaze on x and turns at most 14 units; head tilt is within ±10°.

## Hands

Seven named poses — rest, point (right hand raised toward content), wave,
hold (a card between both hands), chin (right hand to the chin), up (both
raised, celebrate), write (a pencil in the right hand). Never fingers,
never a second outfit prop.

## Sizes on screen

| Use | Size | Note |
|---|---|---|
| Message avatar | 28 px (`xs`) | Beside the name "Mino" on every reply; the same rig, so the face must read at this size — hence the large eyes |
| Notice / empty state | 48–160 px | Product screens |
| Presence figure | 144–176 px wide, partly below the edge | Professor screens, ≥ 768 px only |
| Landing hero | up to 384 px | The one place the full figure is large |

## Silhouette test

Black the figure out: the oversized round head on the small egg body with
one curl on top and two mitts must still read as Mino in every state. A
state that needs extra shapes to be readable is rejected.

## Camera

Front three-quarter, slightly below the eye line, fixed. The head turns and
tilts; the camera does not move.

## Do not

Redesign, slim down, add hair or a nose, add human fingers or texture, make
the character a baby, recolour it for dark mode, add outfits, put an orange
glow around the whole body, generate frames with an image model.
