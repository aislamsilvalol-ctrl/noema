# NOEMA V1 — launch scope

Written 2026-10-07 (Day 1) from the repository, production and the Cursor
audit map (PR #261). Status words: COMPLETE · PARTIAL · BROKEN · MISSING ·
POST-LAUNCH.

## The promise V1 must keep

Type what you want to learn; Mino builds the path, teaches one idea at a
time, checks what you understood, and brings it back before you forget.

## Main flow

| Step | Status | Note |
|---|---|---|
| Landing (V6) → create account | COMPLETE | PT/EN/ES; CSP; breached-password check |
| Goal → curriculum (lesson one is the topic asked) | COMPLETE | Curriculum prompt v2 |
| Lesson with Mino (streaming, modes, guide, quizzes graded by the server) | COMPLETE | Runs on the OpenAI fallback while Anthropic is out of credit |
| Evidence → mastery → review cards (FSRS) | COMPLETE | Concepts still use a fixed 7-day review (P1) |
| Today / next activity / return | COMPLETE | `GET /me/next-activity` |
| Modo TDAH (`/foco`) | COMPLETE | Short sessions, one step at a time; no medical claims |
| Upgrade (Stripe Checkout → webhook → plan) | BROKEN | Returns to a 404; a second checkout can double-subscribe (P0, in progress) |
| Password reset / email verification | BROKEN for users | Sender is `resend.dev`: mail reaches only the owner (needs a domain) |

## MUST (launch blocks without it)

- Billing returns and single subscription (P0-1).
- Stripe live mode with confirmed prices (owner).
- A verified email domain so reset works for everyone (owner buys domain; engineering wires it).
- AI provider credit on primary and fallback (owner).
- Error tracking with release and request id (owner approves account; engineering wires it).
- Launch analytics: activation, North Star, funnel, MRR, AI cost (in progress).
- Professor eval suite with a bar (in progress).
- Mobile: 44 px tap targets, `svh` with the keyboard open (P2-6, promoted to MUST for a mobile-first launch).
- Admin 2FA (owner).

## SHOULD

- Concept reviews on their own schedule (`next_review_at`) instead of a fixed 7 days.
- The router reads the unified `LearnerState` so a forgotten concept becomes REVIEW.
- `past_due` / payment-failed shown to the learner with a portal link.
- Lighter initial JS on landing and chat.
- Scheduled sweep of abandoned sessions.

## LATER (see POST_LAUNCH.md)

URL ingestion (needs an SSRF-safe fetcher), adaptive placement, re-planning,
social, store, cosmetics, CSP nonces, Tailwind 4 / Vitest majors.

## Activation and North Star

- **Activation:** account created, first lesson started, and at least one
  graded interaction in it (quiz or check answered) within 7 days of signup.
- **North Star:** successful learning sessions per weekly active learner. A
  session is successful when it moves a concept (mastery evidence ≥ 0.6), a
  focus session completes, or a review rates ≥ 5 cards.

Exact queries live in one module shared by the launch dashboard; the
definitions are documented in `docs/analytics.md`.
