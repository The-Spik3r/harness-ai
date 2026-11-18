---
id: STORY-014
prd: PRD-018
slug: docs-and-deployment
title: Docs, compose volume, .env.example, roadmap, and PRD close-out
type: technical
priority: medium
complexity: small
phase: "5 - Visible and documented"
status: done
labels: [docs, deployment]
epic_branch: epic/PRD-018-db-resilience
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-014-docs-and-deployment.plan.md
report: .agents/reports/PRD-018-db-resilience/STORY-014-docs-and-deployment.report.md
commit: 62a7167
depends_on: [STORY-012, STORY-013]
blocks: []
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-014: Document what a database outage does

## Description

As a platform operator, I want the deployment docs, compose file and env template to describe the retry, breaker, journal and its volume, so that I can run and reason about the harness during an outage without reading the code.

## Acceptance Criteria

- [ ] Given `docs/deployment.md`, when read, then the "hard dependency" section (`:46-50`) is rewritten as "What a database outage does": the failure classes and what is retried, the 503s and `Retry-After` per ingress, the journal and its volume, the drain order consequence (`id` ≠ time order), the residual cross-instance duplicate gap (T4) and the stall limitation (Risk 2).
- [ ] Given `docker-compose.yml`, when read, then a named volume `harness-audit-buffer:/var/lib/harness/audit-buffer` is mounted with `AUDIT_BUFFER_DIR=/var/lib/harness/audit-buffer`, and the "No volume / stateless" comment is amended for the journal only. `.env.example` documents `AUDIT_BUFFER_DIR` and `AUDIT_BUFFER_MAX_BYTES`.
- [ ] Given `docs/api.md` and `docs/features.md`, when read, then they list the 503 rows (`/query`, `/v1` `storage_unavailable`, `Retry-After`), `audit_ref` / `X-Harness-Audit-Ref`, and `GET /storage/status`.
- [ ] Given `docs/roadmap.md`, when read, then the first two resilience boxes are ticked, pointing to PRD-018.
- [ ] Given the PRD, when this story closes, then its frontmatter is `status: done`, open decisions O2 and O8 read as resolved by the user on 2026-11-17, `gen_index.py` prints `errors: none` and the board shows 100%.

## Technical Notes

- Docs only, plus compose and `.env.example`. Any test that pins `docker-compose.yml` or `.env.example` contents (search `tests/` for them, e.g. a settings/env census) must be updated with a comment citing PRD-018.
- Match the docs' existing voice and structure; no marketing tone.
- Validation: `docker compose config` parses; the relevant config/compose tests pass.
- Document (STORY-006): the `/v1` 503 error object carries `"harness": null` like every `/v1` error (`ErrorDetail` schema); `/query`'s identity 503 detail is `"Storage unavailable"` while the gate 503 is `"Storage unavailable: the request was not sent to the model."`; a post-commit SSE `storage_unavailable` event cannot carry `Retry-After` (headers already sent). The shared rule lives in `app/services/storage_faults.py`.
- Document (STORY-013 measurements, report `.agents/reports/PRD-018-db-resilience/STORY-013-success-criteria-fault-suite.report.md`): healthy-path overhead measured +0.04 ms p50 against a local file database (code overhead); over Docker Desktop's network the 0.5 ms budget is below the noise floor (+0.80 ms with a 1.70 ms spread), stated as unresolvable, not a pass. On a Windows host a refused connect takes ~2 s, so the 2 s start deadline allows a single attempt there (`reason=deadline`); Linux refuses in milliseconds. Mention `--run-chaos` (opt-in, restarts the dev server, never in CI) in the testing docs where `--run-e2e` is described.
- Known residual to document (STORY-003): `delete_chat_session` is IDEMPOTENT, so after an `OUTCOME_UNKNOWN` commit that actually landed, the retry finds nothing and returns `False`. The data is correct, but the UI may report "not found" for a delete that worked.

## Dependencies

- **Blocked by**: STORY-012, STORY-013
- **Blocks**: None

## PRD Reference

Source: [`PRD-018-db-resilience/PRD.md`](../../PRDs/PRD-018-db-resilience/PRD.md) — sections 4 (Deployment and docs), 7 (F9), 9.3, 14 (Risk 4)
