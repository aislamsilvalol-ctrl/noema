## What and why

<!-- What changed, and what problem it solves. Link the issue: Closes #123 -->

## How it was verified

<!-- Tests added, manual steps taken, screenshots for UI work. -->

## Checklist

- [ ] Conventional Commit title (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)
- [ ] Tests cover the change (regression test for a bug fix)
- [ ] `make check` passes locally
- [ ] Docs updated if behaviour or configuration changed

## Architecture rules

Tick what applies; strike out what doesn't.

- [ ] `domain/` and `engines/` stayed pure — no I/O, no ambient clock
- [ ] No evidence rows (`reviews`, `answers`, `mistakes`) are updated or deleted
- [ ] No AI SDK imported outside `providers/`
- [ ] AI-generated content is schema-validated, and carries `source_chunk_ids` provenance
- [ ] No secret can reach a response schema or a log line

## Migration

<!-- Alembic revision id, whether it's blocking, and how to roll back. "None" is fine. -->
