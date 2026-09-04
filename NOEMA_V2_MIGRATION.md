# NOEMA V2 — Migration

*How V2 lands without a big bang, how V1 and V2 coexist while it does, and how
V1 is removed when it is done.*

## The flag

`NEXT_PUBLIC_DESIGN_V2=1` at build time sets `<html data-design="v2">`. The
token layer at the end of `apps/web/src/styles/globals.css` is scoped to that
attribute. Nothing else in the app tests the flag: **components never branch
on it.** A migrated component uses semantic tokens (`bg-primary`,
`text-primary-fg`, `text-signal`, `rounded-md`, `shadow-elevation-1`,
`duration-normal`) that resolve to V2 values under the attribute and to V1's
accent otherwise — so a V2 primitive dropped into a V1 build still renders
sensibly, and the two can be compared from one code base.

Comparison in development: build twice (with and without the variable), serve
on two ports, open the same screen side by side. In CI the flag is on from
Phase 9 (shell) onward, so regressions are caught against V2.

## Order, mapped to this codebase

| Phase | Lands | Touches | Status |
|---|---|---|---|
| 1–2 | Audit, before-screenshots | docs | done |
| 3–6 | Visual system, tokens, type, motion | `globals.css`, `tailwind.config.ts`, `lib/theme.tsx`, Settings | done |
| 7 | Mino state system | `components/mino/`, `brand/mino.ts` (map unchanged) | done |
| 8 | Primitives | `components/ui/` (Button, Notice so far; Input, Select, Modal, Popover, Tooltip, Progress, Tabs, Toast as screens need them) | in progress |
| 9 | Shell | `components/Shell.tsx` (five areas, collapsible rail, theme toggle), redirects for old nav items | done |
| 10 | Landing hero | `app/page.tsx`, `components/landing/HeroAsk.tsx` | done |
| 11 | Scroll beats | `app/page.tsx`, `components/landing/` | |
| 12 | Dashboard | `app/today/page.tsx` (becomes Home) | done |
| 13 | Professor | `app/notebooks/[id]/professor`, `app/chat`, `components/professor/Lesson.tsx`, `lib/markdown.tsx` — on the persisted session (`teaching_sessions`, migration 0017); lesson metadata still to come from the engine | done |
| 14 | Create learning | `app/learn/new`; creates subject + notebook and opens the Professor with the goal as the first turn, until the journey table exists | done |
| 15 | Subject home | `app/notebooks/[id]/page.tsx` | done |
| 16 | Path | `ui/Progress` path variant — waits on the engine's lesson plan (`teaching_sessions.plan` is empty until the teaching policy lands) | |
| 17–18 | Flashcards, reviews | `app/review` | done |
| 19 | Tests | `app/notebooks/[id]/{cards,quiz,exam}`, `QuestionCard/Input` | |
| 20 | Notes | `app/library`; editor prose already token-driven | done |
| 21 | Progress | `app/progress` + `ProgressTabs` over `/graph` and `/mistakes` | done |
| 22 | Settings, auth, billing surfaces | `components/auth/AuthFrame`, `app/{login,forgot-password,reset-password}` done; settings/billing pending | in progress |
| 23–26 | Dark, mobile, a11y, performance | every screen | |
| 27–28 | Regression, production QA | `NOEMA_V2_QA.md` | |

## Rules while both exist

- No screen is half-migrated: a screen moves to V2 primitives in one commit.
- No logic changes ride along with restyles. Where a UX change needs backend
  support (persisted session, lesson metadata), it is a separate, named commit
  in the teaching-engine program, and the UI consumes it after it lands.
- Routes are preserved; navigation changes are redirects plus a new
  information architecture, not deletions.
- `docs/design-system.md` is superseded by `NOEMA_V2_DESIGN_SYSTEM.md` and is
  replaced (not appended) when V1 is removed.

## Removing V1

When `NOEMA_V2_QA.md`'s checklist is complete:

1. Promote the `[data-design='v2']` blocks to `:root` and delete the V1 values
   they overrode; delete the `--accent` alias.
2. Remove `DESIGN_V2` from `layout.tsx` and the variable from CI/Vercel.
3. Delete any class strings the primitives replaced that survived by accident
   (`grep` for `bg-ink-900 px-4 py-2` and friends).
4. Replace `docs/design-system.md`.
5. Record it in `NOEMA_V2_CHANGELOG.md`.

Two designs are a transition, not a state.
