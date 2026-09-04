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

## Technical decision

| Option | Verdict | Why |
|---|---|---|
| Three.js / React Three Fiber | Rejected | No model exists. Faking a 3D mascot from a generated mesh drifts on every angle (§58 of the brief); a real rig would also cost the landing 500 KB+ of runtime for a character that only needs eyes, head, mouth and hands to move. |
| Rive | Deferred | The right tool once official art exists — state machine, inputs, small runtime. Today it would mean vectorising a character that has not been drawn; "visual fidelity takes priority" (§57) cannot be met with nothing to be faithful to. Revisit when renders arrive. |
| Spine | Rejected | Same as Rive with a heavier runtime and a licence. |
| Sprite sheets | Rejected | Frame-based; no real-time gaze or spring motion; every new state is more frames. |
| **Hybrid layered 2D (chosen)** | **Adopted** | One SVG with ten layers, transforms set from a pose, CSS transitions between poses, a rAF spring for gaze/head, ~5 KB, no dependency. Real-time by construction; replaceable layer by layer. |

## Proportions (rig units, 480 × 480 box)

- Head: circle, centre (240, 205), radius 128 — roughly **2.4× the body's width**. The head is the character; the body is a base for it.
- Body: an egg from y=300 to y=446, 180 units wide at the widest; the head overlaps the body's top by ~30 units so the two read as one soft shape.
- Eyes: two circles, radius 21, centres (196, 212) and (284, 212). Interpupillary distance 88 — wide-set. Eye diameter ≈ ⅓ of head radius: **large**.
- Mouth: on y=262, 22–36 units wide, never taller than 18 at full open.
- Curl: a single loop from the crown at (240, 92), 36 units tall, stroke 9. One curl, not hair.
- Hands: round mitts, radius 16, on short arms of stroke 18, shoulders at (176, 372) and (304, 372).
- Ground shadow: an ellipse 224 × 24 under the figure, 10% black. It shrinks when the figure lifts.

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
