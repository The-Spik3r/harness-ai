---
id: STORY-014
prd: PRD-007
slug: deployment-cutover
title: "Cutover: remove the harness_data volume, the build placeholder, and harness_ai.db"
type: technical
priority: high
complexity: small
phase: "4 - Data migration and cutover"
status: done
labels: [infra, docker, deployment, security]
epic_branch: epic/PRD-007-turso-migration
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-014-deployment-cutover.plan.md
report: .agents/reports/PRD-007-turso-migration/STORY-014-deployment-cutover.report.md
commit: null
depends_on: [STORY-006, STORY-008, STORY-013]
blocks: [STORY-015, STORY-016]
skills: []
created: 2026-09-01
updated: 2026-09-02
---

# STORY-014: Cutover: remove the harness_data volume, the build placeholder, and harness_ai.db

## Description

As a platform engineer, I want every remaining trace of the local database file removed from the repository, the image, and the compose stack, so that no deployment path can fall back to a file and no database file can be committed.

PRD Section 2: "The file is gone, not hidden." This story is where that becomes literally true.

## Acceptance Criteria

- [ ] Given [docker-compose.yml](../../../docker-compose.yml), when it is read, then the `harness_data` named volume and its service mount are gone, along with the `DATABASE_URL: sqlite:////app/data/harness_ai.db` environment entry. The Turso connection variables are supplied through the existing `env_file` mechanism, consistent with how `OPENROUTER_API_KEY` and `ADMIN_TOKEN` are handled today.
- [ ] Given [Dockerfile](../../../Dockerfile), when it is read, then the build-time placeholder `DATABASE_URL=sqlite:///:memory:` is replaced with a value that satisfies the configuration validation from [[STORY-005]].
- [ ] Given `docker build`, when it runs with **no reachable database**, then it succeeds. `reflex export` imports `chat_ui.chat_ui`, which calls `init_db()` at import time, so this is a real constraint and the interaction with [[STORY-008]]'s startup guard must be resolved here if it was not resolved there.
- [ ] Given the repository, when `harness_ai.db` is looked for at the root, then it is gone, and `*.db` is gitignored. A database file carrying real audit rows and `users` token hashes must never be committable.
- [ ] Given `git log`, when the deletion is reviewed, then it happens **after** [[STORY-013]]'s migration and verification have been run and recorded — not before. Deleting the source is the last step, not the first.
- [ ] Given `grep -rn "sqlite" app/ chat_ui/ docker-compose.yml Dockerfile`, when it runs, then there are no hits in any production path. `scripts/migrate_to_turso.py` is the one documented exception (it reads the legacy file by design); if it is excluded, say so explicitly.
- [ ] Given `docker compose down -v`, when it is run, then no application data is destroyed. This is PRD Section 5 story 1's acceptance in one command.
- [ ] Given the running stack, when it is started with valid Turso credentials, then the application boots, serves `POST /query`, and the admin console renders.

## Technical Notes

- Files: [docker-compose.yml](../../../docker-compose.yml), [Dockerfile](../../../Dockerfile), `.gitignore`, and the deletion of `harness_ai.db`.
- The Dockerfile's placeholder exists for a documented reason, stated in its own comment: "Build-time-only placeholders so importing `chat_ui.chat_ui` (which imports `app.main`, which imports `app.config.settings`) doesn't fail Pydantic's required-field validation. Real secrets come from docker-compose's `env_file` at runtime." That rationale still holds; only the value changes. Add `TURSO_AUTH_TOKEN` to the same placeholder block if validation now requires it.
- The build-without-a-database constraint is the sharp edge. `init_db()` at import time plus a startup guard that probes the database equals a build that needs a live Turso instance — which PRD Section 11 forbids. Whichever of [[STORY-008]] or this story resolves it, the resolution must be deliberate and documented, not an accident of ordering.
- The `WORKDIR /app` comment in the Dockerfile records that `docker-compose run harness-ai pytest tests/ ...` must keep working as documented in the README. Verify that still holds — the test suite now needs a libSQL dev server, which may not exist inside that container. If it does not, that is a finding for [[STORY-015]]'s documentation.
- Deleting `harness_ai.db` from the working tree does not remove it from git history. If the committed file ever contained real audit rows or `users` token hashes, say so in the report — history rewriting is out of scope for this story but the security consequence should be recorded rather than assumed away.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches infrastructure files. No skill applies.

## Dependencies

- **Blocked by**: STORY-006, STORY-008, STORY-013
- **Blocks**: STORY-015, STORY-016

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 4 (in scope), Section 9 (security), Section 11 (functional requirements), Section 12 Phase 4
