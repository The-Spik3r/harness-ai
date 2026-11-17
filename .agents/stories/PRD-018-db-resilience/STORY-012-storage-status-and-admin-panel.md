---
id: STORY-012
prd: PRD-018
slug: storage-status-and-admin-panel
title: GET /storage/status, in-memory counters, and the admin console Storage panel
type: feature
priority: medium
complexity: medium
phase: "5 - Visible and documented"
status: todo
labels: [backend, api, admin-ui]
epic_branch: epic/PRD-018-db-resilience
plan: null
report: null
commit: null
depends_on: [STORY-005, STORY-008, STORY-009]
blocks: [STORY-014]
skills: [frontend-design]
created: 2026-11-17
updated: 2026-11-17
---

# STORY-012: Storage status endpoint and admin panel

## Description

As a platform operator, I want to see breaker state, journal depth and retry counters without opening a shell, so that I know whether I am looking at a blip, an outage or a backlog.

## Acceptance Criteria

- [ ] Given `database.storage_status()`, when called, then it returns a `StorageStatus` with `instance` (`<host>:<pid>`), `breaker` (`_storage_breaker.status()`), `journal` (`entries`, `bytes`, `max_bytes`, `headroom_bytes`, `oldest_timestamp`, `draining`, `adopted_files`) and `counters` (`retries` and `exhausted` keyed `<op>:<class>`, `breaker_opens`, `journal_appended`, `journal_drained`, `torn_tail_discarded`), all in memory and reset on restart.
- [ ] Given `GET /storage/status` with a token holding `stats:read` (`ADMIN_TOKEN` included), when called, then it returns the PRD Section 10 JSON. Without the permission it returns 403 as other `stats:read` routes do. A non-`db` test with PRD-014's no-driver-call guard asserts the endpoint makes **zero** driver calls, even with the breaker open.
- [ ] Given the breaker open (forced in a test), when `GET /storage/status` is called with `ADMIN_TOKEN`, then it answers 200 with `state: "open"` and `retry_after_seconds ≥ 1`. `/health` is unchanged (`{"status":"ok"}`, no storage).
- [ ] Given the admin console, when an admin opens it, then a Storage panel shows breaker state and `since`, consecutive failures, last failure class, journal entries/bytes/oldest, and the counters, reading `storage_status()` in-process like the other panels, with no network call.
- [ ] Given the counters, when the STORY-003/005/008/009 events happen (retry, exhausted budget, breaker open, journal append, drain, torn tail), then each increments the matching counter exactly once (tests per counter).

## Technical Notes

- `app/routers/admin.py` (or the router that hosts `stats:read` routes; `app/services/authz.py:14`), `app/db/database.py` (`storage_status`, counters), `chat_ui/chat_ui/admin_state.py` and the admin page component.
- `BreakerStatus` is the PRD-019 `/ready` contract: serialize it as is (`dataclasses.asdict`).
- Counters: a small thread-safe structure in `database.py` (or `audit_journal.py` for journal counters); no metrics dependency (D16). Wire the increments into the places STORY-003/005/008/009 already log.
- Admin UI follows the existing admin console components and copy file. The `frontend-design` skill applies to the panel's layout; match the existing panels rather than inventing a style.
- `docs/api.md` row for the endpoint is STORY-014.
- Tests: `tests/test_storage_status.py` (non-`db`), plus the admin console state tests.
- Orchestrator note (STORY-003 plan): `usage_limits.charge` logs the raw `str(exc)` today (`app/services/usage_limits.py:217-227`). PRD Section 11 says every log line carries redacted driver text: route it through `database._redacted()` while touching the logging (cite PRD-018 Quality indicators).
- Orchestrator decision (STORY-009 plan): the drainer (`app/db/journal_drainer.py`) holds back an entry that fails with a non-infrastructure error for the rest of the process (`held_back()`), and the journal holds back corrupt/undecodable files (`JournalStatus.held_back_files`, STORY-008). Expose both in `journal` of `storage_status()` (e.g. `held_back_entries`, `held_back_files`) and in the admin panel: they mean "an operator must look", unlike a normal backlog.
- Orchestrator decision (STORY-003): a refused infrastructure retry (`NON_IDEMPOTENT` on `OUTCOME_UNKNOWN`) logs one WARNING `retry refused ...`. Count it in `counters.exhausted` under `<op>:<class>`, or add a `refused` map, and say which.

## Dependencies

- **Blocked by**: STORY-005, STORY-008, STORY-009
- **Blocks**: STORY-014

## PRD Reference

Source: [`PRD-018-db-resilience/PRD.md`](../../PRDs/PRD-018-db-resilience/PRD.md) — sections 3 (Platform Operator), 4 (Observability), 5 (story 8), 7 (F8), 9.1, 10 (`GET /storage/status`), 11 (zero driver calls), 15 (D16)
