# Mino — animation system

How the character moves, and how a screen talks to it. Code lives in
`apps/web/src/components/mino/`.

## Architecture

```
MinoProvider (MinoController.tsx)   owns state, pose, blink, gaze, quality
   ├─ useMino()                     the handle screens use
   ├─ <MinoLive primary />          the figure gaze is measured against
   └─ <MinoLive />                  any number of further figures, same pose
<Mino state="…" />                  standalone figure: own blink, no wiring
MinoRig (rig/MinoRig.tsx)           draws a Pose; nothing else
machine.ts                          states, event→state, transient returns, poses
```

The UI never names an animation. It calls `mino.on('input_typing')`; the
machine decides `listening`; the pose table decides what that looks like;
the rig draws it; CSS and the spring move between the two.

## States

`idle · curious · listening · thinking · teaching · pointing · reading ·
writing · happy · celebrating · sleepy · confused · wave` plus three aliases
kept for existing screens (`reviewing`, `focused`, `sleeping`).

Transient states return on their own unless something else happens:
`happy` → idle after 1.4 s, `celebrating` → happy after 1.6 s, `wave` →
idle after 1.8 s, `confused` → curious after 2.4 s.

## Event bridge

| Product event | State |
|---|---|
| `input_focus` | curious |
| `input_typing` | listening |
| `input_pause` (600–1000 ms after the last key) | thinking |
| `input_submit`, `request_started` | thinking |
| `response_streaming` (first token) | teaching |
| `response_done` | idle |
| `exercise_correct` | happy |
| `exercise_wrong` | thinking |
| `read` / `write` / `point` / `greet` / `lost` | reading / writing / pointing / wave / confused |
| `idle_timeout` (90 s without interaction) | sleepy |

Storyboarded sections may call `setState` directly; product screens should
not. Mino holds no business logic: the learning code decides whether an
answer was right and emits the event.

## Handle

```ts
const mino = useMino();
mino.on('input_typing');
mino.react('correct');        // → exercise_correct
mino.lookAt(x, y);            // viewport pixels
mino.focus(inputElement);     // look toward an element
mino.reset();
mino.setState('teaching');    // scripted only
```

## Motion

- **Poses**: each state is a `Pose` — gaze, turn, tilt, eye openness,
  squint, mouth, hands, lean, lift. Transitions between poses are CSS
  (`transform` 320 ms standard ease on layers; hands on the spring curve;
  lids 90 ms). No JS tween.
- **Gaze/head**: a critically damped spring (k=120, c=16) in one rAF loop,
  advanced only while moving, paused while the tab is hidden. Pointer
  position is *sampled* (~12 Hz), never handled per event.
- **Blink**: 140 ms, every 7–15 s at random; one in three idle beats adds a
  short glance to the side that returns within ~1.2 s. Never a fixed loop.
- **Breath**: `scaleY 1 → 1.018` over 5.2 s on the body; the curl sways 4°
  over 6 s. Both are CSS.
- **Pointer**: eyes follow only in idle/curious/happy/wave, only on fine
  pointers, only on high/medium quality; leaving the document returns the
  gaze to centre. Range is clamped to ±1 with a dead zone at the centre.

## Quality tiers

| Tier | When | What |
|---|---|---|
| high | ≥ 5 cores, fine pointer | everything |
| medium | ≤ 4 cores or coarse pointer | no pointer tracking (touch) — same states, transitions and breath |
| low | ≤ 2 cores or ≤ 2 GB | no pointer tracking, no spring loop; poses switch with CSS transitions only |
| reduced | `prefers-reduced-motion: reduce` | no spring, no blink, no breath, no scroll observer; poses switch instantly (the global rule collapses transitions) |

## Budget

- Rig: ~5 KB of SVG per figure, no images, no fonts.
- Controller: one rAF loop per provider (idle when at rest), one 80 ms
  sampler for the pointer, three timers.
- No dependency added. No canvas, no WebGL.

## Accessibility

Every figure is `aria-hidden`. Nothing the character does is announced;
if it ever carries information, the same information must be text beside it.

## Replacing the art

Each layer in `MinoRig.tsx` is a `<g className="mino-layer mino-…">` with a
fixed `transformOrigin`. Official art replaces the geometry inside the
group (paths, or `<image>` elements from a sliced render) and keeps the
group, its class and its origin. Poses, events, CSS and the controller are
untouched.
