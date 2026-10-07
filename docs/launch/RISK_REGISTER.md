# NOEMA — launch risk register

Updated 2026-10-07 (Day 1). Overall: **LAUNCH RISK YELLOW** — the product
works end to end; the blockers are payments wiring and owner-held accounts.

| # | Pri | Risk | Owner | Status | Mitigation |
|---|---|---|---|---|---|
| R1 | P0 | Stripe Checkout returns to `/billing/success` (404); a second checkout before the webhook creates a second subscription | Engineering | In progress | Return to `/settings?billing=…`; lock the user row; refuse when Stripe has an open session or live subscription |
| R2 | P0 | Stripe keys are test mode | Aislam | Open | Switch to live keys and live price ids; one real purchase and refund before Day 21 |
| R3 | P0 | Email sender is `resend.dev`: reset and verification reach only the owner | Aislam → Engineering | Open | Buy domain, verify in Resend, set `NOEMA_EMAIL_FROM`; then turn on verification and the verified-email gate for AI |
| R4 | P0 | Anthropic key out of credit; production runs on the OpenAI fallback only | Aislam | Open | Top up, or declare OpenAI primary and fund a second provider as fallback; circuit breaker already in place |
| R5 | P0 | No error tracking: a crash in production is seen only in Railway logs | Aislam → Engineering | Open | Sentry (free tier is enough at launch) on web and API with release + request id |
| R6 | P1 | Legal identity fields empty | Aislam | Mitigated for early access | Pages say early access honestly; `stage: 'launched'` is refused while fields are empty |
| R7 | P1 | `past_due` keeps the paid plan; payment failure only logged | Engineering | In progress | Keep access during Stripe retries; show "payment failed" with a portal link |
| R8 | P1 | Professor quality not measured beyond spot checks | AI | In progress | Eval suite with deterministic router checks in CI and a judged live run |
| R9 | P1 | Concept reviews fixed at 7 days; router ignores unified learner state | AI | Open | `next_review_at` on concepts; REVIEW move from `LearnerState` |
| R10 | P1 | AI cost stored as float; spend per learner not on a dashboard | Analytics | In progress | Launch dashboard with AI cost; integer cents follow-up |
| R11 | P2 | 32 px tap targets; `min-h-screen` jumps with the phone keyboard | Product | Open | 44 px targets, `100svh`; real iPhone and Android pass |
| R12 | P2 | Landing and chat ship > 200 kB initial JS | Engineering | Open | Split the lesson composer and landing scenes; measure on a mid phone |
| R13 | P2 | Public demo cap disappears without Redis; proxy hop count 0 | Engineering | Open | Fall back to an in-process cap; set trusted proxy hops for Railway |
| R14 | P2 | Railway Hobby plan: no native backups, limited resources | Aislam | Mitigated | Nightly pg_dump with restore check; uploaded files not backed up |
| R15 | P2 | Ad accounts and pixels do not exist yet | Aislam | Open | Meta and TikTok business accounts by Day 20; pixels behind consent |
| R16 | P3 | Higgsfield credits (~125) limit creative volume | Creative | Open | Reuse the approved films; spend credits only on hooks that tested |

Escalation: any P0 without an owner action by its gate day turns the overall
risk RED for that day's report.
