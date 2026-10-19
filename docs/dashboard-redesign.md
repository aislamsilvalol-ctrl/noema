# NOEMA dashboard redesign (2026-10-19)

The home (`/today`) is being redesigned. This document holds the audit, the
three directions, the choice and the build plan. The code follows it, in
`apps/web/src/components/dashboard/`.

## Current dashboard audit

The audit is based on screenshots of `/today` taken on 2026-10-19. The
learner had one journey (Matemática → Equações quadráticas, 3 of 7 lessons,
3 of 5 concepts mastered). Desktop is 1440 wide and mobile 390 wide.

### What works

- **The data is honest.** Every number comes from the engine (the journey
  plan, concept stages, due cards, next activity, progression). Estimates are
  marked "≈". Nothing is invented. This survives intact.
- **The order is right in principle:** continue first, then reviews and weak
  concepts, then growth, and missions under the learning, never above it.
- **No streak anxiety, no "+15 XP!!!".** The progression is named after
  places (first steps, trail, crossing…).
- **Modo TDAH has a way in from Home.**
- **First run gets one invitation, not an empty grid.**

### What feels generic

- The page is a typeset list on bone. Nothing on it says NOEMA. The cobalt
  sky, the territory and Mino, which carry the landing, are absent. It could
  be any well-made SaaS settings page.
- The greeting ("Boa noite.") is the largest thing on the screen and says
  nothing.
- Every section uses the same mono kicker, ink line and hairline. With no
  rhythm, there is no hierarchy.

### Information overload

- The visible height holds eleven separate facts. They include a "Hoje · ~7
  min" budget line the learner never set and doesn't need, plus two
  continue-like actions (Continuar Matemática and the Modo TDAH card, both on
  "Discriminante").
- Missions (3 rows), level, XP today, a weak concept, knowledge growth and a
  folded session planner all sit at the same visual weight.
- The session planner (`<details>`) is a second, competing way to decide
  "what now". The home already answers that question.

### Visual problems

- The content runs in a 68ch column, and two thirds of a 1440 screen is empty
  bone. That reads as unfinished, not as calm.
- The progress line is 1px, so progress is almost invisible.
- Concept stages are 6px dots in a wrapped row. They are a legend with no map.
- The primary action is the default cobalt button, at the same size as
  anywhere else in the app.
- On mobile, the tab bar overlaps the mission list. The Modo TDAH card wraps
  its estimate onto a new line.

### UX problems

- The page never states "here is what to do now" in one sentence. The
  learner has to choose between Continue, Começar (TDAH), Trabalhar nele and
  the planner.
- A returning learner can't see where they are on the path (module → lesson →
  concept). It is flattened into a breadcrumb string.
- Nothing invites exploring a new subject. Starting something new means
  finding "Aprender" in the rail.
- The weak concept says "Fórmula de Bhaskara · incerto", which is technical
  vocabulary, not a human sentence.

### What should be removed

- The "Hoje · ~N min" budget line.
- The folded session planner. Its job moves to the one recommendation, and
  `/review` keeps the session.
- The duplicate Modo TDAH card when it points at the same thing as Continue.
  It becomes one of two options in the "Agora" band.
- The full mission list. It becomes one quiet line, with the detail on
  Progress.
- "Missões de hoje", "Crescimento do conhecimento" and other kicker labels
  over single facts.

### What should become primary

Continue, as a large, visual and unmistakable hero. Under it, one sentence:
what is the next best thing, and why, in human language.

## Top 5 problems

1. There is no single, obvious "what do I do now". Four actions compete.
2. Zero brand presence: no landscape, no Mino, no colour.
3. Progress is invisible (1px line, 6px dots).
4. Everything has the same weight, so there is no hierarchy, rhythm or scale.
5. There is no path to discovery and no visible map of where the learner is.

## New information hierarchy

1. **Where am I, what am I learning, what now:** the hero. Greeting, subject,
   current lesson, next concept, progress ring, Continue.
2. **The path:** the journey as a trail of modules and lessons, with the
   concepts placed on it and colour-coded by stage. This is also the
   knowledge-map preview.
3. **The next best action:** one sentence from the engine, with at most two
   options (the recommendation, and a 10-minute focus session).
4. **How I'm growing:** four signals at most.
5. **Resume:** other open lessons and journeys, as tiles. Shown only when
   there is more than one.
6. **Explore:** three or four editorial tiles.
7. **Secondary:** marks and today's missions, in one quiet line.

## Direction A — Cinematic learning

The whole first fold is a landscape plate, full bleed. Greeting and Continue
float in the sky. Below it, sections keep a dimmed plate behind them.

- **Strength:** the most "NOEMA". It is the landing, continued.
- **Weakness:** atmosphere outweighs information, and the second and later
  visits feel like a splash screen. Plates behind every section become
  wallpaper. It also costs the most to render on phones.

## Direction B — Editorial color

No photography. Large flat fields of cobalt, ultramarine, bone and alpenglow
pink alternate. Display type is huge, metrics are set like magazine numbers,
and the grid is asymmetric.

- **Strength:** striking, fast and modern.
- **Weakness:** it loses the territory (the brand's thesis), and colour fields
  without image risk "fashion site" over "learning". Mino has no world to
  stand in.

## Direction C — Personal learning OS

Super clean bone surface, dense but quiet. A journey timeline, a knowledge
graph and metrics are integrated in panels.

- **Strength:** clearest for power users, cheapest to build.
- **Weakness:** this is where the current page already is. It is the generic
  SaaS look the brief rejects.

## Recommended direction: A + B, with C's discipline

We use **"the sky over the territory"**:

- **One landscape, once.** The hero is a plate: the cobalt sky is the negative
  space that carries the type, and the territory and a small Mino are in the
  frame. That is A, only at the top, where it means "this is your world".
- **Colour fields for rhythm (B).** After the hero, sections alternate: bone
  for the trail, a deep ultramarine field for "Agora" (the next action), bone
  with editorial numbers for progress, and image tiles for explore. Colour
  marks the role of each band, not decoration.
- **C's discipline inside every band.** One idea per band, real data only, at
  most two actions per band, and one primary action on the screen.

Why it scores best:

- **Identity:** the plates and the cobalt are the landing's own DNA.
- **Clarity:** the hero answers the four questions before any scroll.
- **Beauty and retention:** the plate changes with the learner's state, so
  the page reflects them.
- **Mobile:** the plate crops to the sky and Mino, and bands stack.
- **Performance:** one priority image (AVIF/WebP at 640, 1000 and 1600), with
  everything else lazy.

## Color strategy

The palette is taken from the plates, not invented. It is an experience
layer over the existing tokens:

| Role | Colour | Where it comes from | Used for |
|---|---|---|---|
| Learning | cobalt `#1d3fd1` → ultramarine `#12247a` | the sky | hero type field, "Agora" band, progress ring track, current lesson |
| Action | ember `#e4471f` | Mino's body | the one primary CTA (Continue), the current point on the trail |
| Progress / mastered | mineral `#3f6b4a` (existing `positive`) | the valley floor | mastered concepts, done lessons |
| Reward | alpenglow `#f4b9a4` → `#f7d9c4` | the lit snowcaps | marks, "mastered today", the ring's done arc on cobalt |
| Attention | meadow gold `#c9a35a` | the dry grass | "worth reviewing", shaky concepts |
| Focus (Modo TDAH) | night ultramarine `#0b1440` + ember dot | dusk | the focus option, which is calm and dark, not "special needs" |
| Ground | bone `#f6f2ea` / ink `#0b1440` | existing | everything else |

The rules:

- There is one saturated thing per band.
- There are no gradients except sky to territory, which belongs to the plate.
- There is no neon and no glow.
- Text on cobalt or ultramarine is bone, above 7:1 contrast.

## Landscape strategy

The plate is chosen by the learner's state, not at random:

| State | Plate | Why |
|---|---|---|
| First day | `horizon` | an open field and a vast sky: "where do you want to go?" |
| Continuing a journey | `trail` | a path ahead with Mino on it |
| Review is the next best action | `valley` | going back over ground already walked |
| Something was mastered today | `mino` | Mino close, looking out: a quiet celebration |
| A notebook or lesson without a journey | `terraces` | the landing's own plate |

The time of day changes the copy and a light veil on the plate (morning is
lighter, night is deeper). It does not change the photograph, because the
plates all share one dusk light.

Explore and resume tiles crop the other plates (`routes`, `terraces`,
`valley`, `bleach`), picked by hashing the subject. The same subject always
gets the same place.

## Character strategy

Mino is the companion, with two forms and no third:

1. **In the plate:** a small figure, seen from behind, walking the territory.
   This is the brand's figure, and it is already in the photographs.
2. **The vector Mino (`<Mino>`) at `sm`,** where something is said to the
   learner: beside the "Agora" sentence. His state follows the learner:
   - `pointing` when there is a clear next step;
   - `happy` when something was mastered today;
   - `curious` on the first day;
   - `sleepy` late at night ("uma revisão rápida?").

Mino never takes more than about 48px outside the plate, and he never
appears without a sentence next to him.

## Desktop structure (≥1024)

- The rail stays: it is minimal already, and nav changes are out of scope.
  See the note at the end.
- **01 Hero.** Full content width, 560px tall, with the plate behind it
  (object-position keeps the sky on the left and Mino on the right). On the
  left, set in the sky:
  - greeting (small, bone/70);
  - subject chip;
  - current lesson as a display headline;
  - "Próximo: Discriminante";
  - a ring of mastered concepts / total;
  - one line of status;
  - ember Continue, plus a quiet secondary ("Revisar 6 cartões · 3 min") when
    reviews are due.
- **02 Trail** (bone). The modules are stations on a horizontal line, and the
  lessons are stops. Done stops are filled with mineral, the current stop is
  ember with the xs Mino avatar, and upcoming stops are hollow. Concepts of
  the current module hang under it as labelled nodes coloured by stage, with
  "Ver mapa completo →".
- **03 Agora** (ultramarine field, full bleed inside the content area). On the
  left, Mino sm and the engine's sentence. On the right, two options: the
  recommendation and "10 minutos · Modo TDAH".
- **04 Progress** (bone). Four editorial numbers in a row: concepts mastered,
  level with stage name, active days this week, and today. Below them, one
  line of today's small goals.
- **05 Resume.** Horizontal image tiles. Shown only when there are two or
  more open journeys or lessons.
- **06 Explore.** One large tile (the next module of the current journey,
  "continua daqui") and three small ones (ideas to start).
- **07 Marks.** A quiet strip of earned marks, if any.

## Mobile structure (<768)

- **Hero:** full bleed and 78svh. The plate is cropped to the sky with Mino
  low, and the type sits at the bottom over a sky-to-ink veil. Continue is
  full width.
- **Trail:** vertical. Stops run down a line and only the current module is
  expanded. The others are one line each.
- **Agora:** full-bleed ultramarine, with the two options stacked as rows,
  not cards.
- **Progress:** a 2×2 grid of numbers.
- **Resume and Explore:** horizontal scroll-snap rows, with the tile at 82vw.
- The tab bar is unchanged. The page pads past it.

## Motion strategy

- **Hero:** a 1.4s push-in on the plate (scale 1.06 → 1). Type rises
  60–120ms after it, and a fine pointer adds small parallax between the plate
  and the type (±6px).
- **Ring:** the done arc draws on mount (700ms, ease-noema).
- **Trail:** the line draws left to right, and the current stop has a slow
  ember pulse (3s, opacity only).
- **Tiles:** fade-up with a 60ms stagger when they enter the viewport. On
  hover the image scales to 1.03 inside its frame. The tile itself never
  lifts.
- **Touch:** `active:scale-[0.99]` on tiles and rows.
- **Implementation:** all of it is transform and opacity, CSS only. Under
  `prefers-reduced-motion` everything is still.

## Component plan

`apps/web/src/components/dashboard/`:

| Component | Job |
|---|---|
| `Landscape` | the responsive `<picture>` (AVIF/WebP 640, 1000 and 1600), plus `plateFor(subject)` |
| `DashboardHero` | greeting, current subject and lesson, ring, CTA; first-day variant with an inline "what do you want to learn?" |
| `JourneyProgress` | the trail: modules → lessons, with the current point |
| `KnowledgeMapPreview` | the current module's concepts as named nodes, coloured by stage |
| `NextAction` | the "Agora" band: Mino, the sentence, the two options |
| `FocusSession` | the Modo TDAH option inside "Agora": 10 min, one goal, the time |
| `ProgressSummary` | four numbers and the small-goals line |
| `LearningTile` | a resume tile (plate crop, subject, where you stopped) |
| `ExploreTile` | an editorial suggestion tile (large or small) |
| `CharacterMoment` | Mino sm with a state chosen from the learner's day, plus his sentence |
| `homeState.ts` | pure functions: which plate, what Mino feels, which recommendation and why. Unit-tested. |

These use the global tokens; no new design system. The new colours are added
as `--dash-*` tokens in `globals.css`, each with its dark value.

## Implementation plan

1. Audit (this document).
2. Information architecture: `homeState.ts`, the decisions as pure, tested
   functions.
3. Visual direction: tokens and the `Landscape` component.
4. Core desktop: the hero, trail, Agora and progress.
5. Mobile: the specific layouts above.
6. Motion: CSS, with reduced motion respected.
7. Real data: the existing endpoints only. There is no new API. Every section
   fails on its own.
8. Performance: one priority image and lazy tiles.
9. QA: screenshots at 1440 and 390, first day and returning, light and dark.
   Unit tests for the page and `homeState`.
10. Polish: the senior review below, then cuts.

Analytics: `dashboard_viewed`, `continue_learning_clicked`,
`next_action_clicked`, `explore_clicked`, `quick_session_started`,
`review_started`. They are added to `lib/analytics.ts` and
`docs/analytics.md`.

Success metrics (from the database, `GET /admin/launch`, plus these events):

- time to first action;
- session start rate from Home;
- continue rate;
- returning-user activation.

## What is not in this change

- **Navigation.** The rail (Início, Aprender, Revisar, Notas, Progresso, Metas
  + Modo TDAH) is already minimal. Folding Metas into Progresso and Notas
  into a Biblioteca under Aprender would bring it to four places plus Modo
  TDAH. That is a separate change, because it moves pages.
- **Streak count.** The API doesn't have one, by design ("no streaks, no
  anxiety"). The weekly "active days" mission is the elegant substitute.
- **Time spent learning.** The API doesn't expose it. It is not estimated.
- **Personalised explore.** There is no recommendation endpoint. Explore shows
  the journey's real next module, plus curated starting ideas labelled as
  ideas, not as "recommended for you".
