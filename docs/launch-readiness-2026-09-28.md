# NOEMA // Launch readiness report — 2026-09-28

Production: web `web-production-34d29.up.railway.app`, API `api-production-3ab4.up.railway.app`, both on `main` after #230.
Method: three read-only audits (web surfaces, API security and isolation, core learning loop), then fixes, CI 5/5 on every head, deploy, and checks against production with two fresh QA accounts.

## Launch status

**NOT READY — one blocker, owner-only:** `/privacy` and `/terms` are public, in the sitemap, and show a red "configuration required" box, "[email de contato a definir]" and no last-updated date, because `apps/web/src/lib/legal-config.ts` is all `null` by design (legal identity is never invented). Filling the seven fields in that file clears it; nothing else needs to change.

With that done: **READY WITH KNOWN NON-BLOCKING LIMITATIONS**, for a small controlled cohort first.

## Shipped in this pass

| PR | What |
|---|---|
| #222 | Curriculum prompt v2: lesson one is the topic asked for, prerequisites live inside lessons. Answer prompt v4: "Sim" only confirms a claim. Web build receives Railway domain/env, so canonical, og:url, sitemap and analytics are correct in production (they said `http://localhost:3000`). `/signup` and `/register` redirect to account creation. |
| #223 | Lesson cards approved at creation, migration 0029 approves old ones, so they reach `/review`. One lesson skip per turn (was two). Journey dedupe checks every recent active journey. |
| #224 | Quizzes graded by the server against the stored answer key; the client's `correct` is ignored. |
| #225 | "Explain differently" honours the chosen mode; every strategy carries a one-line meaning in the directive; "Guide me" is a GUIDE move (questions, hints, never the answer). |
| #226 | Funnel events: `onboarding_completed`, `lesson_started`, `review_session`. |
| #227 | Plan quota enforced on every AI route (402 `plan-limit-reached`), per-user AI rate limit (30/min), input caps, default output caps, API docs off in production, forgot-password per-email cooldown, admin search hardening, zip-bomb caps. |
| #228 | Quiz math shows x⁵, not x^5. |
| #229 | "Report a problem" dialog (sidebar, More menu, error page) → `POST /feedback`, admin list; migration 0030. BottomSheet focus bug fixed. |
| #230 | The turn directive names the reply language. An English question in an account with a Portuguese course was answered in Portuguese. |
| #218–#221 (same day) | Mino answers direct questions first, skips a lesson when the learner is ahead, short "?" questions are classified; CSP enforced; breached-password check. |

## Verified in production

- Cross-user isolation: user B gets 404 on user A's session, journey, recap, feedback and on continuing A's lesson through `/ai/professor`.
- Derivatives from a fresh account: lesson one teaches the derivative; "E a de x³?" answered without "Sim"; "passo a passo" gives numbered steps; "Me guia" asks without telling.
- English learner gets English.
- `/feedback` 204; `/docs` and `/openapi.json` 404; `/signup` 307 to register; CSP allows Plausible; canonical is the real domain.
- Screens at 360, 390, 768 and 1440 px: landing, login, today, lesson, review, progress, settings, 404 — no clipping, no horizontal scroll, no blank sections.

## Known limitations (non-blocking)

- Level is parsed once from the goal sentence; `engines/placement.py` (adaptive placement) is not wired; no re-plan. A learner far ahead of an old plan advances one lesson per showing.
- The quiz answer key still ships to the browser for the instant reveal; a learner reading devtools can pick the right option.
- Open-check answers count as `conversation` evidence (weight 0.35); mastery leans on quizzes and cards.
- Two mastery views: `/graph` and the weak-concept row use the graph model, so chat-only learners see an empty graph.
- No lesson-end/abandon event; lesson completed/skipped/hint have no event rows.
- Learner memory (patterns, summaries, misconceptions) is not viewable or deletable except via full export or account deletion.
- Email verification not implemented. CSP uses `'unsafe-inline'`, not nonces.
- Legal pages are Portuguese-only.
- Social, store, profile cosmetics: not implemented and not linked anywhere (correctly hidden).

## Owner checklist before opening the doors

- [ ] Fill `apps/web/src/lib/legal-config.ts` (company, address, city, region, postal code, country, contact email).
- [ ] Top up Anthropic credit (OpenAI fallback is carrying production).
- [ ] Enrol 2FA on the admin account (admin routes require it).
- [ ] Open a lesson on a real iPhone and a real Android phone.
- [ ] Confirm the Plausible dashboard receives `signup_completed`, `lesson_started`, `review_session`.
- [ ] Confirm Railway Postgres backups are on.
