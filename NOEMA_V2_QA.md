# NOEMA V2 — QA

*Phase 2 baseline (the experience before V2), the checklist, and — as phases
land — what was verified, how, and what was not.*

## Phase 2 — the experience before V2, observed

Captured 2026-08-15 from a production build of `main` at `df4f7c7` served
locally with the API proxied to production, in the in-app browser, signed in
as the test account. No Chrome is installed on this machine, so these are
observations from screenshots I viewed rather than PNG files in the repo; the
"after" is compared against the same screens the same way. Widths: 1440 desktop
(pane), 375 mobile emulation; light and dark by `prefers-color-scheme`.

| Screen | Before |
|---|---|
| Landing (desktop, light) | Cream ground; serif headline "Aprenda qualquer coisa. Ensinada por algo que lembra."; near-black CTA "Começar a aprender" + outlined GitHub; Mino placeholder at right (grey body, orange sweatshirt, dot eyes), cursor tilt works. No input, no demonstration, no scroll beats beyond Mino's pose swapping. Pillars are a 3-col grid below the fold. |
| Landing (mobile) | Stacks well; headline four lines; Mino below the CTAs (partly out of first viewport). No overflow. |
| Landing (dark) | Warm-black-ish ground `#0E0E10`, orange sweatshirt reads well, headline cream. Looks intentional. CTA becomes cream-on-black. |
| `/today` (dashboard) | Title "Hoje", a row of minute chips (15m selected), then "Planejando…". Nothing about where the learner was. In dark: a black field with one word. |
| `/chat` | "Noema" title, one sentence, empty space, a composer at the bottom, "Enviar" near-black. The empty state does not offer a first step. |
| `/library` | Title + "Novo caderno" button, "Carregando…". |
| `/review` | Only "Carregando…" for the whole content area. |
| `/progress` | Title + "Carregando…". |
| `/settings` | Providers, Add a key, Idioma, Cobrança ("Você está no plano Grátis"). No Appearance control (added in Phase 4). |
| `/chat` (mobile) | Composer sits above the bottom bar correctly; **the bottom bar's first item "Perguntar ao Noema" wraps to two lines** and the bar's height grows — a real defect from adding a fifth-letter-long label to a four-slot bar. |
| Navigation | Eleven items in the sidebar: Perguntar ao Noema, Hoje, Biblioteca, Metas, Revisar, Explicar, Socrático, Erros, Grafo, Progresso, Ajustes. Palette + Sair + language at the bottom. |

Cross-cutting, seen not inferred:

- **Loading is the word "Carregando…" alone** on every data screen. There is no
  skeleton, no Mino, no sense of what is coming. (Nielsen 1.)
- **Nothing is orange except links.** The primary action is near-black on
  every screen; the brand colour is not the signal. (Design principle.)
- **Dark mode is applied by the OS only**; the app offers no control until
  Phase 4's Appearance setting.
- **The Professor surface is a transcript + composer**, exactly the shape the
  brief asks to leave behind.

## Checklist

- [ ] Existing functionality preserved
- [ ] Orange/white identity implemented
- [x] Dark mode redesigned — token set + control (Phase 4); screens pending
- [x] Mino preserved — same art, same map
- [ ] Mino animations improved
- [ ] Mino contextual states
- [ ] Landing redesigned
- [ ] Scroll storytelling
- [ ] Hero interactive
- [ ] Dashboard redesigned
- [ ] Professor redesigned
- [ ] No chatbot-clone feel
- [ ] Learning paths redesigned
- [ ] Flashcards redesigned
- [ ] Reviews redesigned
- [ ] Tests redesigned
- [ ] Notes redesigned
- [ ] Progress redesigned
- [ ] Navigation redesigned
- [ ] New-learning flow redesigned
- [ ] Loading states
- [ ] Error states
- [ ] Mobile
- [ ] Tablet
- [ ] Desktop
- [ ] Reduced motion
- [ ] Accessibility
- [ ] Performance
- [ ] Dark mode QA
- [ ] Light mode QA
- [ ] Functional regression
- [x] Production build — `main` builds clean with the token layer; web unit tests 116/116

## Verified so far

| Phase | What | How | Result |
|---|---|---|---|
| 4 | Token layer compiles and is inert without the flag | `npm run build` without `NEXT_PUBLIC_DESIGN_V2`; screens above rendered from that build | Identical to before |
| 4 | Types, lint, unit tests | `tsc --noEmit`, `next lint`, `vitest` | Clean; 116 passed |
| 4 | Contrast of every semantic token pair | Script in the design-system commit | All text pairs ≥ 4.5:1; UI-only pairs ≥ 3:1 |
| 4 | The V2 flag build serves the V2 tokens | Built with `NEXT_PUBLIC_DESIGN_V2=1`, served on :4322; read `data-design`, `--primary`, `--surface` in the pane | `v2`, `#b5450c`, `#fbf8f3` — V1 on :4321 unchanged |
| 4 | Appearance control switches and persists | Clicked "Escuro" in Settings; read `data-theme`, tokens, `localStorage`; reloaded | `dark`, `--surface #141311`, `--primary #f26b1d`; still dark after reload (pre-hydration script) |
| 9 | Five-place shell, desktop | V2 build on :4322, `/today` at 1440, dark (stored choice) | Rail: Início · Aprender · Revisar · Notas · Progresso; "Outros jeitos de aprender" lists goals/explain/socratic/mistakes/graph; Ajustes, palette, theme control and language at the bottom; collapse control present |
| 9 | Mobile bar: one line, no wrap | `/chat` at 375; measured `nav.fixed` height and labels via JS | Labels `Início, Aprender, Revisar, Notas, Progresso, Mais`; bar height **43 px** (was growing to two lines before) |
| 8 | Professor empty state | V2 build on :4322, `/chat` at 1440, dark | Mino (curious) beside "O que vamos aprender primeiro?" and the lede; composer directly below; no grey placeholder sentence |
| — | Lesson resumes after reload | Endpoint test in CI; then `scripts/check-teaching-session.py` against **production** (revision 9e5da55) after deploying migration 0017 | Read-back after two messages: `learner, noema, learner, noema`, `turn_count 4`, `/sessions/latest` points at it. The row-lock fix is confirmed live — the second message resumed instead of hanging |
| 10 | Landing hero interaction | V2 build on :4322, typed "Psicologia" and submitted | Mino turned to listen while typing; the input took an orange focus ring; "Me mostra" (orange, the first orange primary in the app) revealed the five-step illustration with the honest "não um resultado gerado" note and "Começar a aprender Psicologia" |
| 12 | Home answers "where was I" | V2 build on :4322 against production, `/today` at 1280 dark, 375 light; sections and tokens read via JS | Order: greeting + Mino → **Continuar aprendendo** (the live lesson from `/ai/sessions/latest`, one orange "Continuar de onde parou") → Revisões ("3 cartões prontos", secondary action) → Sua aprendizagem (notebook list) → Planejar uma sessão (planner unchanged, below the fold). No horizontal scroll at 375; Mino hidden there; light `--surface #fbf8f3`, dark `--primary #f26b1d`. Known: the lesson card titles with the learner's first question until the engine fills `subject` (teaching-policy work) |
| 13 | Professor as a learning session | V2 build on :4322 against production, `/chat`; resumed the stored lesson, then sent a real turn asking for an example and a list; measured the DOM | Header: Mino (sm) beside the title, `thinking` while "Pensando…", `idle` after; learner line quiet with a left rule, Noema block labelled in orange; the reply rendered as lesson prose — **7 `<strong>`, 6 `<li>`, 1 `<h3>`, no literal `**` anywhere** (the old screens printed the asterisks); quick actions Me teste · Aprofundar · Explica de outro jeito · Resumir appear after a reply and send text; Send is the one orange primary; new turns scroll into view. Unit tests: markdown never produces markup from `<img …>` text; unterminated `**` stays literal mid-stream; snake_case is not italicised. 121/121 |

## Not yet verified (stated so it is not assumed)

- The V2 flag build itself (`NEXT_PUBLIC_DESIGN_V2=1`) — nothing consumes the
  new tokens yet, so there is nothing to see until the first primitives land.
- Theme switch on a real device (no white flash) — verified by construction
  (pre-hydration script), not yet by eye.
- Stripe surfaces — no live key on this deployment (per roadmap); billing
  restyle will be verified against the "not configured" state only.
