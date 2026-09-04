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
| 14 | Create learning, end to end | V2 build on :4322 against production; `/learn/new`, typed "Fotossíntese", chose "Começando do zero" and "Uma prova ou um trabalho", pressed Começar; watched the network | Steps "Passo 1 de 4" → 4; Mino listening while typing, teaching on the path preview; `POST /subjects` 201, `POST /notebooks` 201, landed on `/notebooks/{id}/professor` with the notebook's title under the header; the first turn was sent without a second press — learner line "Quero aprender Fotossíntese. Estou começando do zero. É para uma prova ou um trabalho."; `/ai/sessions/latest` has that sentence as `learning_goal` and the new `notebook_id`; the reply rendered as a lesson (14 bold terms, heading, list). No alerts. Hero "Começar a aprender X" and Home "Começar a aprender" now enter this flow; sign-up lands here; sign-in lands on Home |
| 15 | Subject home | V2 build on :4322 against production; the new Fotossíntese notebook (open lesson) and Sistema cardiovascular (no lesson, one note, cards due); read the DOM, clicked the note | Order: title → **Onde você está** ("Fotossíntese · Última aula há 8 minutos", one orange "Continuar a aula" → professor; on the other notebook "Nenhuma aula ainda" + "Começar com a Noema") → **Praticar** ("3 cartões prontos para revisar" + Começar a revisar; Cards/Quiz/Prova as quiet links) → **Notas** (list; no editor on load; clicking "Ciclo cardíaco" marked it *Editando*, mounted the ProseMirror editor below with "Fechar nota") → **Material** folded. Tutor rail unchanged. No alerts |
| 17–18 | Reviews as a card you turn over | V2 build on :4322 against production (3 due); space to reveal, `3` to rate, DOM read at 1280 and 375 | Mino small (`reviewing`) beside "1 de 3" and a thin orange progress line; the card is a raised object that **rotates** on reveal (`matrix3d(-1…)` on the face container; captured mid-turn), the back carrying the question small and the answer large; the four ratings with their interval previews and keys are unchanged, targets 113 px tall at 375; `3` made Mino `celebrating` then back to `reviewing` within a second; the confidence row then Skip appear exactly as before. Found and fixed on the way: an **imported cloze card reviewed as raw `{{c1::France}}` with an empty answer** — the Anki importer stored the note unexpanded; it now renders per deletion like `/cards/cloze` (API tests), and the page blanks/reveals any raw one still in the database ("The capital of […] is Paris" / "…France is Paris"). Empty and complete states use `Notice` with Mino sleeping/celebrating |
| 22 | Auth | V2 build on :4322; `/login` at 1280 and 375, `/reset-password` without a token | Desktop: a quiet panel (Mino `idle`, one sentence, "Open source · AGPL") beside the form; mobile: the panel is `display: none`, the form has the screen, no horizontal scroll; one orange primary ("Entrar"); fields take the orange focus border; the reset page's terminal states use the primary link ("Pedir um novo link"). Sign-in/sign-up/forgot/reset logic and their tests unchanged (123/123) |
| 21 | Progress as one place | V2 build on :4322 against production; `/progress` and `/mistakes` DOM read | Header: Mino + "Progresso" + the one-line summary ("Nada medido ainda." on this account); tabs Visão geral · Mapa · Erros with `aria-current` on the open one, the same row on `/graph` and `/mistakes`; the 14-day forecast in orange (today solid, the rest tinted); calibration section with the secondary Button. Mastery rows carry a bar per concept (none to show on this account yet). No maths changed; no alerts |
| 20 | Notes | V2 build on :4322 against production; `/library` DOM read | "Notas" + lede; "Novo aprendizado" (orange) → `/learn/new` beside "Novo caderno"; "3 cartões vencendo" with a secondary Começar a revisar; groups Fisiologia · Fotossíntese with dated rows; no alerts |
| — | API revision after the importer fix | `scripts/check-deployed.sh … c536a4d` after `railway redeploy` (the `up` was skipped as identical to the already-deployed archive) | OK — production runs `c536a4d`; the Anki cloze fix is live |
| 19 | Tests | V2 build on :4322; `/notebooks/{id}/quiz` (no questions) and `/exam` (not started) | Quiz empty state: Mino `curious`, "Nenhuma pergunta ainda." with the one orange "Gerar perguntas"; exam start: Mino `focused`, orange "10 perguntas · 15 min" beside the secondary 20/30. `QuestionCard` (shared by quiz, exam-less practice and mistakes): Mino reviewing → celebrating/focused on the verdict, orange Answer, confidence as secondary buttons, the verdict on a green/red rule; `QuestionInput` options are raised, orange when chosen, `aria-pressed`. Grading, timer, hand-in logic unchanged; 123/123 |

## Not yet verified (stated so it is not assumed)

- The V2 flag build itself (`NEXT_PUBLIC_DESIGN_V2=1`) — nothing consumes the
  new tokens yet, so there is nothing to see until the first primitives land.
- Theme switch on a real device (no white flash) — verified by construction
  (pre-hydration script), not yet by eye.
- Stripe surfaces — no live key on this deployment (per roadmap); billing
  restyle will be verified against the "not configured" state only.
