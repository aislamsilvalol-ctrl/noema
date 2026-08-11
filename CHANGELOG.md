# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) from 1.0.0 onward.

Entries are generated from [Conventional Commits](https://www.conventionalcommits.org/).

## [Unreleased]

### Added

- Architecture design documents: topology, data model, AI provider layer, ingestion/RAG
  pipeline, Mastery Engine formulas, FSRS integration, Adaptive Learning Engine.
- Monorepo skeleton (`apps/api`, `apps/web`, `packages/`).
- Reference implementations of the FSRS scheduler and Mastery Engine as pure functions,
  with unit and property tests.
- `AIProvider` protocol, capability descriptors and provider registry.
- Docker Compose stack: web, api, worker, postgres+pgvector, redis.
- CI: lint, typecheck, tests, build, evals, dependency and secret scanning.
- Open-source project files: contributing guide, code of conduct, security policy,
  issue and pull request templates, roadmap.

[Unreleased]: https://github.com/noema-dev/noema/commits/main
