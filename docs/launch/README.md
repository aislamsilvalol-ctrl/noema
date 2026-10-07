# NOEMA — Launch Command Center (2026-10-07 → 2026-11-03)

Day 1 is 2026-10-07; Day 28, the public launch, is 2026-11-03.
Rule: **ship over perfect, but never trade away security, data integrity,
auth, the main learning flow, payments, observability or mobile.**

| File | What it holds |
|---|---|
| [V1_SCOPE.md](V1_SCOPE.md) | MUST / SHOULD / LATER, the main flow, the activation event, the North Star |
| [RISK_REGISTER.md](RISK_REGISTER.md) | P0–P3 risks, owner, status, mitigation |
| [POST_LAUNCH.md](POST_LAUNCH.md) | Everything consciously moved after launch |
| [VISUAL_DNA.md](VISUAL_DNA.md) | The Brand Guardian's checklist, from the landing and @noemalearn |
| [CREATIVE_LIBRARY.md](CREATIVE_LIBRARY.md) | Folder layout and brief format for social and paid pieces |
| [../analytics.md](../analytics.md) | Event taxonomy, activation and North Star queries (lands with the launch dashboard) |
| [../operations.md](../operations.md) | Health, readiness, request ids, ops view, incident playbook |

## Calendar

| Days | Dates | Phase | Exit gate |
|---|---|---|---|
| 1–3 | Oct 07–09 | Audit, V1 scope | Scope and risks written; P0s have owners |
| 4–9 | Oct 10–15 | Core | Main flow complete on mobile; billing returns work |
| 10–13 | Oct 16–19 | AI engine | Professor eval suite passing its bar; cost per session known |
| 14–16 | Oct 20–22 | Polish | Mobile tap targets, empty/error states, copy pass |
| 17–19 | Oct 23–25 | QA, security, performance | Release gates green except owner items |
| 20–21 | Oct 26–27 | Monetisation, analytics | Stripe live, launch dashboard reading real data |
| 22–24 | Oct 28–30 | Pre-launch | Creative library stocked; waitlist/soft-launch list ready |
| 25–26 | Oct 31–Nov 01 | Soft launch | 10–30 real learners; war-room drill |
| 27 | Nov 02 | Release candidate, freeze | Only P0 fixes after this |
| 28 | Nov 03 | Launch, war room | Dashboard watched hourly; rollback ready |

## Release gates (all must hold on the release candidate)

1. CI 5/5 on the release commit; `/health/ready` 200 in production with database, Redis and migrations ok.
2. Main flow passes end to end on a phone width in production: sign up → goal → first lesson → a graded answer → review card scheduled → return.
3. Stripe in live mode: checkout returns to `/settings`, webhook moves the plan, the portal cancels, a second checkout is refused.
4. Email from a verified domain: reset password reaches a non-owner inbox.
5. AI provider with credit on the primary and the fallback; circuit breaker tested; per-user rate and plan quotas on.
6. Professor eval suite at or above its bar; no scenario regresses from the last run.
7. Backups: last nightly dump restore-checked within 24 h.
8. Error tracking receives a test exception from web and API, tagged with release and request id.
9. Admin 2FA enrolled; no secret in the repo or the client bundle.
10. Legal pages either in honest early-access mode or filled and `stage: 'launched'`.

## Task format

Every task: OWNER → OUTPUT → ACCEPTANCE CRITERIA → TEST → DONE. A task is done
when its acceptance criteria were checked against the running thing, not when
the file exists.
