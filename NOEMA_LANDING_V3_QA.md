# NOEMA landing V3 — QA

What was verified, how, and what was not. Build: `main` at the landing V3
commit, served locally against the production API; tests `vitest` 117/117,
`pytest` for the demo endpoint.

## Verified

| Check | How | Result |
|---|---|---|
| The five-second test | Fresh load at 1280 | Eyebrow "Um tutor de IA que ensina, não um chatbot que responde." + "O que você quer aprender?" + input + Mino. Nothing else above the fold. |
| Mino reacts to the field | JS-driven focus, input, 800 ms pause | `idle → listening → thinking` recorded from `data-mino-state`; focus alone → `curious` when the scroll observer is not overriding (see below) |
| Submit follows the request, not a timer | Submitted "Quero aprender JavaScript" against production | `thinking` from submit until the first token; `teaching` from the first token; POST `/api/v1/ai/demo` → 200; reply in Portuguese, one idea + example + question, labelled "Uma resposta real do tutor…" |
| Honest fallback | Same flow against a build whose API had no `/ai/demo` yet (404) | The written sample for Freud appeared with "O tutor está ocupado agora; é assim que os primeiros trinta segundos são." — no broken section |
| Practice adapts to the subject | Typed JavaScript, chose the wrong option, "Certeza" | Question "O que `[1, 2, 3].map(n => n * 2)` devolve?"; verdict "Quase. Repara nesta diferença…" with the `map`/`reduce`/`forEach` distinction; Mino → `thinking` (no sad face) |
| Adapt reorders | After the wrong answer | Concept bars re-sorted weakest first (Promises 18 · map/filter/reduce 30 · Funções como valores 60) with "Reordenado depois da sua resposta" |
| Remember | Tapped the card | `aria-pressed=true`, back face with the answer and "Próxima revisão em 11 dias" |
| Close | Scrolled to the end | "Começar" (orange) with the typed subject beside it; carried into the app via `lib/prefill` |
| No horizontal scroll at 375 | Mobile emulation | `scrollWidth === innerWidth`; the figure is 7 rem at the top right beside the question |
| Reduced motion | Unit tests (`useActiveSection.test.ts`), controller code path | No observer, no spring, no blink; poses switch instantly via the global rule |
| Decorative character | `page.test.tsx` | Every `svg.mino-rig` is `aria-hidden`; legal links present |
| Demo endpoint limits | `test_demo.py`; code review | `max_tokens` 220, per-caller daily allowance in Redis, global limiter, `noema_demo_enabled` kill switch |

## Not verified here (state it, do not assume it)

- **Scroll-driven state and the companion figure by eye.** The in-app
  browser pane was hidden (`document.hidden`) during checks, where
  IntersectionObserver does not fire, so beat-by-beat state changes and the
  companion's fade were confirmed by the hook's unit tests only.
- Safari, Firefox, iOS and Android real devices; slow CPU/network profiles;
  Lighthouse (LCP/INP/CLS) and FPS traces. The page adds no dependency and
  no image; the rig is ~5 KB per figure.
- Mobile keyboard choreography (background motion frozen while typing).
- Visual regression of the character across states — meaningful only once
  the official art replaces the provisional rig.

## Known limitations

- The character art is provisional (see `MINO_CHARACTER_SPEC.md`).
- Hero → companion is a fade between two figures of one controller, not a
  FLIP of one element.
