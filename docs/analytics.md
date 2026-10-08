# Launch analytics

Two sources, each with one job:

- **The database is authoritative** for everything that says whether a learner
  got value: activation, active learners, sessions, retention, revenue, AI cost.
  `GET /admin/launch` computes all of it; the `/admin` page's Launch section
  draws it.
- **Plausible** (production only, no cookies, no personal data) covers what the
  database cannot see: the top of the funnel (landing → signup) and where a
  visitor came from. A blocked script changes nothing below the signup.

The learning definitions live in one module,
`apps/api/noema/services/launch_definitions.py`. The dashboard and any later job
import them from there; the copy below says the same thing in prose. All days
are **UTC** calendar days.

## Activation

> An account that, **within 7 days of signing up**, **started a lesson** (a
> teaching session with at least one learner turn) **and answered at least one
> graded item in it**: a `mastery_events` row of kind `quiz`, `check`,
> `assessment`, `teach_back` or `flashcard`.

Why this and not something looser:

- *Signup* and *onboarding* are intent. A lesson started is the first real use,
  but a lesson can be opened and abandoned at the first reply.
- A graded answer is the smallest act that is NOEMA's actual product: the
  learner did something, and the system now knows something about what they
  understand. It is the point where adaptivity can start working for them.
- A wrong answer counts. Activation is about doing the thing, not doing it well.
- `conversation` events (the professor reading a chat line) do not count: the
  learner did not answer anything.
- Flashcard events carry no session id; they count against the lesson's journey.
- 7 days is long enough for a "sign up tonight, try it at the weekend" learner,
  short enough to be read within a launch week.

The **activation rate** is computed only over signups at least 7 days old (the
"activation cohort"), so recent signups that have not had their full window do
not drag it down. Daily rows still show how many of each day's signups have
activated so far.

## North Star

> **Successful learning sessions per weekly active learner.**

A **successful learning session** is any of:

| Kind | Definition | Dated by |
| --- | --- | --- |
| `teaching` | a teaching session with ≥ 1 `mastery_events` row scoring ≥ 0.6 | its first such row; counted once however long the lesson runs |
| `focus` | a Modo TDAH focus session with status `completed` | `completed_at` |
| `review` | ≥ 5 rated cards by one learner on one UTC day (reviews carry no session id, so a day is the session) | the first review of the day |

A focus *review* sitting also rates cards, so a day with one can count as both a
`focus` and a `review` success. That is accepted: both happened.

An **active learner** on a day (DAU) or in a week (WAU) is someone with a row in
`learning_events`, a learner turn in `teaching_turns`, or a rated card in
`reviews` in that period.

The headline value is over the **last 7 UTC days** (today included):
successful sessions in those days ÷ distinct active learners in those days. The
dashboard also gives it per ISO week. Why this metric: it grows only when
learners come back *and* the sessions work; it does not reward time-on-site,
message volume, or sessions where nothing was learned.

## Other dashboard figures

| Figure | Source and rule |
| --- | --- |
| Signups / day | `users.created_at` |
| Lessons started / completed | `learning_events` (`lesson_started`, `lesson_completed`; facts start at migration 0034, not backfilled) |
| Focus sessions | `focus_sessions.started_at`, completed by `completed_at` |
| D1 / D7 retention | of a signup-day cohort, the share active on exactly day 1 / day 7 after signup; a cohort counts once that day has fully passed |
| Paying users, MRR | a paid plan on an account with a Stripe customer (webhooks move cancelled subscriptions back to Free); price from `plan_configs` (BRL). A paid plan without a Stripe customer was set by hand and is shown as **comped**, not revenue |
| AI calls, failures, cost | `ai_usage` (`succeeded`, `cost_cents` in **USD** cents) |
| AI latency p50/p95 | **not recorded**: `ai_usage` has no latency column; the endpoint returns null and lists `ai_latency_ms` under `not_recorded` |
| Feedback reports | `feedback_reports.created_at` |

`GET /admin/launch?days=` takes 7–180 days (default 30). Admin only
(allowlisted email + two-step verification).

## Client events (Plausible)

No event carries personal data or lesson content. Props are short enums.

| Event | When | Props |
| --- | --- | --- |
| `cta_clicked` | a landing call to action | `location` |
| `signup_started` | the login page switched to "create account" | — |
| `signup_completed` | registration succeeded | — |
| `onboarding_completed` | `/learn/new` submitted | `level`, `purpose` |
| `learning_goal_created` | same moment: the goal was handed to the first lesson | — |
| `lesson_started` | a new teaching session opened | — |
| `exercise_answered` | a quiz option chosen, or an open check answered | `kind` (`quiz`/`check`); `correct` (`'true'`/`'false'`) for quizzes only — an open check is graded on the server, so its verdict is not known in the browser |
| `mastery_updated` | a concept firmed up in the lesson | `step` (`mastered`/`learning`) |
| `learning_session_completed` | the journey plan marks a new lesson done, or a focus session is completed | `kind` (`lesson`/`focus`) |
| `review_session` | a review session finished | — |
| `adhd_mode_enabled` | `/foco` opened (once per tab session) or the Focus preference switched on | `via` (`foco`/`preference`) |
| `pricing_viewed` | `/pricing` opened | — |
| `checkout_started` | a Subscribe button pressed | `plan` |
| `subscription_started` | `/settings?billing=success` (Stripe's return), once per tab session | — |

`subscription_started` is the browser's view; whether a subscription exists is
decided by the Stripe webhook, and the dashboard's paying users come from there.

## Attribution

On any page load, `utm_source`, `utm_medium`, `utm_campaign` and `utm_content`
in the URL are kept in `localStorage` (`noema.attribution`). First touch wins: a
later tagged visit does not overwrite it. Registration sends them as
`attribution`; the API keeps only those four keys, trimmed to 100 characters,
in `users.signup_attribution` (JSONB, migration 0036), and never refuses a
signup over a malformed tag. The account export includes it.

Plausible reads the same UTM tags from the landing URL on its own, so traffic
sources there need nothing extra.
