---
id: STORY-011
prd: PRD-018
slug: duplicate-overlay-and-headroom
title: Duplicate overlay over journaled rows and the admission headroom check
type: technical
priority: high
complexity: small
phase: "4 - Never lose a row"
status: todo
labels: [backend, security]
epic_branch: epic/PRD-018-db-resilience
plan: null
report: null
commit: null
depends_on: [STORY-006, STORY-008, STORY-009, STORY-010]
blocks: [STORY-013]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-011: Duplicate overlay and headroom

## Description

As a security admin, I want a resend of a just-answered prompt still held while its row sits in this instance's journal, and a full journal to refuse requests before they pay for an upstream call, so that buffering opens neither a duplicate bypass nor an unrecorded release.

## Acceptance Criteria

- [ ] Given a journaled success row for `(user_id, dedup_key)` and a recovered database, when the same user resends before the drain reaches it, then `check_duplicate` (after a successful database lookup that found nothing) consults `audit_journal.pending_duplicate(user_id, dedup_key, since)` and the response is `QueryBlockedDuplicateResponse(first_query_at=<journaled timestamp>)`.
- [ ] Given the overlay, when the database lookup fails, then the request still fails closed (`DuplicateCheckError`); the overlay never stands in for the database and is never consulted when the lookup found a row.
- [ ] Given each row shape `find_duplicate_timestamp` excludes (outside the window, `success = 0`, `was_duplicate_blocked`, `denied_permission` set, `pattern_action = 'flag'`, `limit_exceeded` set, another user, another key), when a `db` test writes it both to the table and to the journal, then the SQL lookup and the overlay give the same answer for every shape (parity, Risk 6). Both predicates carry a cross-reference comment.
- [ ] Given `journal.bytes > AUDIT_BUFFER_MAX_BYTES − PIPELINE_MAX_WORKERS × 65536`, when a request enters the pipeline, then it is refused **before step 2** with `503` (`/query` fixed detail, `/v1` `storage_unavailable`, chat UI `internal_error` bubble), no row is written and the upstream stub records zero calls.
- [ ] Given a drained entry, when its drain commits, then it leaves the overlay index, and a resend after that is held by the database lookup instead.

## Technical Notes

- `app/services/duplicate_checker.py:29-39`, `app/db/database.py:857-899` (`find_duplicate_timestamp`, predicate at `:885-898`), `app/db/audit_journal.py` (index from STORY-008), `app/services/query_pipeline.py` (pipeline entry, before step 2).
- Headroom reuses STORY-008's `headroom_ok()` and STORY-006's 503 mapping. Decide which exception carries it (e.g. `AuditUnavailableError` raised at entry, or a dedicated subclass) so all three ingresses map it without new arms where possible.
- Residual T4 (cross-instance resend) is accepted and documented in STORY-014. Do not try to close it.
- Tests: `tests/test_db_resilience_overlay.py` (`db` parity), headroom test non-`db` with the journal on `tmp_path`.

## Dependencies

- **Blocked by**: STORY-006, STORY-008, STORY-009, STORY-010
- **Blocks**: STORY-013

## PRD Reference

Source: [`PRD-018-db-resilience/PRD.md`](../../PRDs/PRD-018-db-resilience/PRD.md) — sections 5 (story 6), 6.7 (headroom row), 6.8 (Bounds, Duplicate overlay), 9.2 (T4, T5), 11 (overlay parity, headroom), 14 (Risk 6), 15 (D10, D12)
