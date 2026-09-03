# NOEMA V2 — Changelog

Running log of what V2 changed, per phase, with the commit. Newest first.

## 2026-08-15

- `df4f7c7` — **Phase 4: the design-token layer and the theme control.** Orange ramp
  50–900, warm-white / warm-black grounds, semantic tokens, radius/elevation/
  motion scales, all behind `data-design="v2"`. `ThemeProvider` +
  pre-hydration script; Settings → Appearance: Light / Dark / System in PT/EN/ES.
  V1 renders unchanged without the flag (verified from the same build).
- **Phases 3–6 — visual system** (`3ddbe77`). `NOEMA_V2_DESIGN_SYSTEM.md`:
  colours chosen by WCAG measurement (light primary stays `#B5450C` — the only
  step passing as text and as a button; `#F26B1D` is the large-signal orange;
  dark lifts to 400/500), typography kept, space/radius/elevation/motion,
  iconography rule, primitives list, Mino state system, one-orange-action rule,
  learner vocabulary.
- **Phase 1 — audit** (`5f73e2f`). `NOEMA_V2_DESIGN_AUDIT.md`: product map,
  Nielsen findings, every screen as CURRENT / PROBLEM / V2 / PRIORITY, what must
  not change, migration order.
- **Phase 2 — before-screenshots**. Observed and recorded in
  `NOEMA_V2_QA.md`; one mobile defect found (bottom-bar label wrapping).

## Related, same day (teaching engine — the other open program)

- `66796db` `docs/teaching-engine-audit.md` rewritten against the Professor
  path; `evals/teaching/baseline/freud-before.md` captured against production.
  The Professor redesign (Phase 13) and the teaching engine's persisted
  session + lesson metadata are one piece of work.
