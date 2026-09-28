# NOEMA // Launch readiness report — 2026-09-28

Production: web `web-production-34d29.up.railway.app`, API `api-production-3ab4.up.railway.app`, both on `main` after #230.
Method: three read-only audits (web surfaces, API security and isolation, core learning loop), then fixes, CI 5/5 on every head, deploy, and checks against production with two fresh QA accounts.

## Launch status

**READY WITH KNOWN NON-BLOCKING LIMITATIONS — for an early-access validation cohort** (updated after #232–#238).

The legal pages no longer block: `legal-config.ts` has `stage: 'early-access'`, and `/privacy` and `/terms` say plainly that NOEMA is in early access, operated independently by its creator, with contact through "Report a problem" and public GitHub issues. No identity is invented. Switching `stage` to `'launched'` with fields still empty brings the warning back, so general availability cannot ship half-filled.

**Before general availability** (not before the validation cohort): a verified sending domain for email (see below) and the legal identity fields.

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

## Second pass (same day)

| PR | What |
|---|---|
| #232 | The quiz key stays on the server: blocks ship without `answer`/`explain`; `POST /ai/sessions/{id}/quiz` reveals them for a real option, owner-scoped. |
| #233 | Legal pages honest in early access, in PT, EN and ES. |
| #234 | A written answer to Mino's check question counts as `check` evidence (1.0), not idle conversation (0.35). |
| #235 | The learner's level rises one step each time they show they are ahead. |
| #236 | "O que o Mino lembra de você" in Settings: see and forget patterns, summaries and misconceptions per course, or everything. |
| #237 | Email verification (migration 0031), link at signup, banner and `/verify-email`. Asked for only when mail can actually be delivered. |
| #238 | Quiz options shuffled server-side; the model put the right answer first. |

Found while doing it: production sends email from Resend's shared test domain (`resend.dev`), which delivers **only to the Resend account owner**. Password reset, security notices and verification links therefore reach no one else. Verification stays dormant until a real sender is set; `/meta` reports `email_verification: false` meanwhile.

## Verified in production

- Cross-user isolation: user B gets 404 on user A's session, journey, recap, feedback and on continuing A's lesson through `/ai/professor`.
- Derivatives from a fresh account: lesson one teaches the derivative; "E a de x³?" answered without "Sim"; "passo a passo" gives numbered steps; "Me guia" asks without telling.
- English learner gets English.
- `/feedback` 204; `/docs` and `/openapi.json` 404; `/signup` 307 to register; CSP allows Plausible; canonical is the real domain.
- Screens at 360, 390, 768 and 1440 px: landing, login, today, lesson, review, progress, settings, 404 — no clipping, no horizontal scroll, no blank sections.

## Known limitations (non-blocking)

- Level starts from the goal sentence and only rises when the learner shows they are ahead; `engines/placement.py` (adaptive placement) is not wired; no re-plan. A learner far ahead of an old plan advances one lesson per showing.
- Two mastery views: `/graph` and the weak-concept row use the graph model, so chat-only learners see an empty graph.
- No lesson-end/abandon event; lesson completed/skipped/hint have no event rows.
- Emails (reset, security notices, verification) reach only the Resend account owner until a verified sending domain is configured.
- CSP uses `'unsafe-inline'`, not nonces: nonces would force every page to render dynamically; deferred.
- Social, store, profile cosmetics: not implemented and not linked anywhere (correctly hidden).

## Owner checklist

Before the validation cohort:
- [ ] Railway → postgres service → Backups: turn on Daily and Weekly, and take one manual backup. **There are no backups and no schedule today**; the CLI token lacks permission to set them.
- [ ] Open a lesson on a real iPhone and a real Android phone.
- [ ] Confirm the Plausible dashboard receives `signup_completed`, `lesson_started`, `review_session`.
- [ ] Enrol 2FA on the admin account (admin routes require it).
- [ ] Top up AI provider credit (the OpenAI fallback is carrying production while Anthropic is out of credit).

Before general availability:
- [ ] A domain for NOEMA, verified in Resend, and `NOEMA_EMAIL_FROM` set to an address on it. This turns on password reset for everyone and email verification.
- [ ] Fill `apps/web/src/lib/legal-config.ts` identity fields and set `stage: 'launched'`.
