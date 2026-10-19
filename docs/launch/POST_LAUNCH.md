# NOEMA — after launch

Consciously moved out of V1. Each line says why, so nobody re-litigates it
during the freeze.

| Item | Why it waits | Revisit |
|---|---|---|
| URL ingestion (paste a link to learn from) | Shipped: `POST /api/v1/sources/url` fetches https only, pins DNS, and re-checks every redirect. The web UI still uploads files. | Done |
| Adaptive placement (`engines/placement.py`) and re-planning | Level already rises when the learner shows they are ahead | First month |
| CSP nonces instead of `'unsafe-inline'` | Nonces force every page dynamic; the CSP is enforced today | Quarter |
| AI cost in integer micro-cents | New `ai_usage` rows write `cost_micro_cents` and the legacy float. Sums prefer the integer and fall back to the float when it is null. | Done |
| Social features, store, profile cosmetics | Not built, not linked | Product review |
| Native apps | The web app is mobile-first | After retention data |
| Tailwind 4, Vitest 5 majors | Upgrade risk during the freeze | After launch week |
| Old Dependabot PRs #148–#166 | Superseded by grouped bumps | After launch week |
| Backups of uploaded files (api volume) | Postgres is backed up nightly; uploads are re-creatable | First month |
| Knowledge map drawing its lines on arrival | Cosmetic | Polish sprint |
| Satoshi / TWK display face | Inter carries the system | Brand review |
