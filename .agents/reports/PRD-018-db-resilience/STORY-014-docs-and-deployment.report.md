---
story: STORY-014
prd: PRD-018
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-014-docs-and-deployment.plan.md
epic_branch: epic/PRD-018-db-resilience
commit: 62a7167
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report — STORY-014: Docs, compose volume, .env.example, roadmap, and PRD close-out

**Plan**: `.agents/plans/PRD-018-db-resilience/completed/STORY-014-docs-and-deployment.plan.md`
**Epic Branch**: `epic/PRD-018-db-resilience`
**Commit**: `62a7167`

## Summary

Docs, compose, `.env.example` and PRD frontmatter only; no application code. `docs/deployment.md`'s "hard dependency" section is now "What a database outage does" and describes what STORY-001..013 built: the four failure classes and what is retried, the breaker, what each ingress returns, the audit journal (volume, settings, security, torn tail vs held-back, adoption, headroom, `audit_ref`, drain order), `GET /storage/status`, the residual gaps and the STORY-013 measurements (the Docker Desktop figure stated as unresolvable, not a pass; +0.04 ms code overhead). Every constant was re-read from `app/db/database.py` (3 attempts, 50/200 ms caps, 2.0 s deadline, 5 failures, 10 s), `app/db/audit_journal.py` (65536 reserve) and `app/config.py` (default 67108864, minimum workers x 65536 x 2).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Named volume `harness-audit-buffer`, `AUDIT_BUFFER_DIR` in `environment`, comment amended | `docker-compose.yml` | done |
| 2 | Both settings documented | `.env.example`, `docs/configuration.md` | done |
| 3 | Three `.env.example` pin tests | `tests/test_config.py` | done |
| 4 | Section rewrite + local-state sentence | `docs/deployment.md` | done |
| 5 | `audit_ref`, 503 section, `GET /storage/status`, `/v1` journaled shape, errors table, audit ordering note | `docs/api.md` | done |
| 6 | "Database outages" subsection, `/v1` id/header and 503 mentions, stale link text | `docs/features.md` | done |
| 7 | Roadmap boxes ticked + Shipped entry; `--run-chaos` / `--run-e2e`; 500 -> 503 troubleshooting; README volume sentence, roadmap, docs table | `docs/roadmap.md`, `docs/testing.md`, `README.md` | done |
| 8 | PRD `status: done`, `updated: 2026-11-17`; story done; index regenerated | PRD.md, story, index | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| `docker compose config` | parses; shows `harness-audit-buffer` volume and `AUDIT_BUFFER_DIR=/var/lib/harness/audit-buffer`; with the smoke overlay (`HARNESS_SMOKE_ADMIN_TOKEN`, `HARNESS_SMOKE_WORKERS` set) it also parses and the env merges |
| Tests | `tests/test_config.py` + `tests/test_untouched_app.py` + `tests/test_caddyfile_routes.py`: 247 passed, 0 failed, 0 skipped |
| Old anchor grep | zero hits for `the-database-is-a-hard-dependency-of-every-request` in docs and README |
| `/storage/status` example | validated against `StorageStatusResponse` |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

`docker-compose.yml`, `.env.example`, `docs/configuration.md`, `docs/deployment.md`, `docs/api.md`, `docs/features.md`, `docs/roadmap.md`, `docs/testing.md`, `README.md`, `tests/test_config.py`, `.agents/PRDs/PRD-018-db-resilience/PRD.md`, plan (archived), report, story, index.

## Deviations from Plan

- The plan's note that `/audit` ordering should be in `docs/api.md` is done as a bold paragraph after the scoping paragraph, not as a bullet.
- Counter keys in the `/storage/status` example use the lowercase failure-class values (`admit_usage:not_sent`), as `FailureClass` values are lowercase in code; the plan wrote them uppercase.
- No test was added for compose or docs prose (none pins them, per the plan).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` | `test_env_example_documents_both_audit_buffer_vars_with_a_comment`, `test_env_example_audit_buffer_vars_appear_in_settings_field_order`, `test_env_example_audit_buffer_defaults_match_settings` |

## Acceptance Criteria

- [x] `docs/deployment.md` "hard dependency" section rewritten as "What a database outage does"
- [x] `docker-compose.yml` mounts the volume with `AUDIT_BUFFER_DIR`; comment amended; `.env.example` documents both settings
- [x] `docs/api.md` and `docs/features.md` list the 503 rows, `audit_ref` / `X-Harness-Audit-Ref`, `GET /storage/status`
- [x] `docs/roadmap.md` first two resilience boxes ticked, pointing to PRD-018
- [x] PRD `status: done`; O2 and O8 already read "Resolved by the user (2026-11-17)"; `gen_index.py` prints `errors: none`, board 14/14
- [x] `docker compose config` parses; config tests pass; app imports; docs voice matched
