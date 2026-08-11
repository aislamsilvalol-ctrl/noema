# NOEMA — Design System

## Principle

The interface should feel like a well-set book that happens to be interactive. Reading and
thinking are the primary activities; every pixel that is not content is overhead.

The AI is invisible infrastructure. There is no assistant avatar, no chat bubble in the
corner, no sparkle icon. When AI acts, it produces content in place — an explanation, a
question, a plan — and cites what it used.

## Type

Type carries the whole identity, so it gets the budget that a logo usually would.

| role | face | size / leading |
|---|---|---|
| Display | serif with real personality (Newsreader / Signifier) | 48–64 / 1.05, tight tracking |
| UI | grotesque (Inter Variable) | 13–15 / 1.5 |
| Reading | serif, 68ch measure | 17 / 1.65 |
| Mono | JetBrains Mono | 13 / 1.55 |

The serif/grotesque split is the signature: editorial where you read, neutral where you act.

Scale: 12, 13, 15, 17, 20, 24, 32, 48, 64. Nine sizes, no others.

## Colour

One neutral ramp, one accent, three semantic. Chrome is nearly monochrome; colour means
something.

```
--ink-{50..900}      warm neutral ramp, not pure grey
--accent             a deep ink blue (#2C4A7C light / #7DA2E8 dark)
--positive --caution --critical
```

Mastery uses a single-hue sequential ramp from `--ink-200` to `--accent`, never
red→yellow→green. Traffic lights turn a learning state into a judgement, and 8% of male
users cannot read them.

Dark mode is a designed theme, not an inversion: warm near-black `#0E0E10`, elevated surfaces
by lightness, and the serif's optical weight compensated by a slightly heavier grade.

## Space

4px base. Layout in 8/12/16/24/32/48/64/96. Generous — a notebook page is mostly margin.

Three-region shell:

```
┌──────┬──────────────────────────────┬──────────┐
│ nav  │  content (max 68ch reading)  │ context  │
│ 240  │                              │ 320      │
└──────┴──────────────────────────────┴──────────┘
```

Nav collapses to icons; the context rail (citations, related concepts, mastery for what you
are reading) hides entirely in Focus Mode. Focus Mode is a real mode — content, timer,
nothing else.

## Motion

- 120ms for state, 200ms for entrances, `cubic-bezier(0.2, 0, 0, 1)`.
- Animate opacity and transform only.
- The knowledge graph is the one place with expressive motion — force simulation settling,
  edges drawing on expand — because there the motion carries structural information.
- Everything respects `prefers-reduced-motion`.

## Components

Built on shadcn/ui primitives (Radix underneath, so keyboard and screen-reader behaviour is
correct by default), restyled to the tokens above. Distinctive to NOEMA:

- **Mastery meter** — thin bar with a confidence band, never a percentage alone.
- **Citation chip** — inline superscript expanding to the source excerpt with page.
- **Concept pill** — name + mastery dot; hovering shows prerequisites.
- **Review controls** — four keys with their resulting intervals visible.
- **Session plan** — the day's blocks with each block's one-line rationale.
- **Command palette** (`⌘K`) and **Ask NOEMA** (`⌘J`), context-aware.

## Anti-patterns

Explicitly banned from the codebase: purple-to-blue AI gradients, brain and robot iconography,
glow effects, confetti, streak guilt, XP, badges, card grids where a list would do, and any
number presented without the basis for it.

## Accessibility

WCAG 2.2 AA as a merge requirement, not a phase. Full keyboard operation including review
sessions and the graph, visible focus rings, `axe` in CI, and the reading surface tested at
200% zoom.
