---
id: STORY-015
prd: PRD-007
slug: readme-and-deployment-docs
title: "README: correct the persistence claim, the env table, and document multi-instance deployment"
type: technical
priority: medium
complexity: small
phase: "4 - Data migration and cutover"
status: done
labels: [docs, deployment]
epic_branch: epic/PRD-007-turso-migration
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-015-readme-and-deployment-docs.plan.md
report: .agents/reports/PRD-007-turso-migration/STORY-015-readme-and-deployment-docs.report.md
commit: 484ba3b
depends_on: [STORY-014]
blocks: []
skills: []
created: 2026-09-01
updated: 2026-09-02
---

# STORY-015: README: correct the persistence claim, the env table, and document multi-instance deployment

## Description

As a platform engineer, I want the README to describe how the system actually persists data, so that I do not configure a deployment against instructions that describe a design the code no longer has.

Two statements are now false. [README.md:177](../../../README.md) claims "The SQLite database persists across container restarts via a named volume — audit history is not lost on redeploy," and [README.md:214](../../../README.md) documents `DATABASE_URL` as a "SQLite connection string" defaulting to `sqlite:///harness_ai.db`. Both describe a volume and a file that [[STORY-014]] deleted.

## Acceptance Criteria

- [ ] Given [README.md:177](../../../README.md), when it is read, then the named-volume persistence claim is replaced by an accurate description: state lives in Turso, no volume is involved, and container lifecycle no longer affects the audit history.
- [ ] Given the environment-variable table at [README.md:214](../../../README.md), when it is read, then `DATABASE_URL` is documented as a libSQL endpoint, required, with no default, and `TURSO_AUTH_TOKEN` is documented alongside it as a required secret for remote endpoints.
- [ ] Given the README, when a reader looks for multi-instance guidance, then it states that multiple instances may now share one database, and names what this PRD did **not** deliver: load balancing, health checks, and Reflex websocket session affinity are separate work (PRD Section 4, Section 13).
- [ ] Given a new contributor, when they follow the README to run the test suite, then it tells them how to obtain a local libSQL server and confirms no Turso account is needed.
- [ ] Given the README's setup instructions, when they are followed end to end against a fresh Turso database, then the application starts and serves a query. Verify by doing it, not by reading.
- [ ] Given `grep -rn "sqlite\|harness_data\|harness_ai.db" README.md`, when it runs, then the only hits are deliberate historical references — for example describing `scripts/migrate_to_turso.py`'s purpose — and each is accurate.
- [ ] Given `docker-compose run harness-ai pytest tests/`, when the README documents it, then the documented command actually works, or the README says what changed. [[STORY-014]]'s report may already have flagged this.

## Technical Notes

- Files: [README.md](../../../README.md). Possibly `.env.example` if the repo carries one.
- Match the existing document's tone and structure. The env table is a real table with Required / Default / Description columns — extend it, do not append a prose paragraph.
- Do not oversell. Multi-instance operation is now *possible*, and PRD Section 4 is explicit that "Actually running multiple instances in production" is out of scope. A README that implies the topology work is done will mislead the next operator.
- The resilience gap is worth one honest sentence. PRD Section 14 Risk 5: the database is now "a hard dependency of every request," and retry, circuit-breaker, and buffering behavior are deliberately out of MVP scope. An operator sizing this deployment should learn that here, not from an incident.
- If [[STORY-013]]'s migration script is meant to be run by an operator rather than only once by the team, document how — otherwise it is a tool nobody knows exists.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story edits documentation. No skill applies.

## Dependencies

- **Blocked by**: STORY-014
- **Blocks**: None

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 4 (in scope), Section 11 (functional requirements), Section 12 Phase 4, Section 13
