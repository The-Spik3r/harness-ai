---
id: STORY-006
prd: PRD-018
slug: ingress-503-mapping
title: Ingress mapping — require_identity, POST /query and /v1 storage_unavailable with Retry-After
type: feature
priority: high
complexity: medium
phase: "3 - Fail fast and say so"
status: todo
labels: [backend, api, v1]
epic_branch: epic/PRD-018-db-resilience
plan: null
report: null
commit: null
depends_on: [STORY-005]
blocks: [STORY-007, STORY-010, STORY-011]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-006: 503 + Retry-After on every HTTP ingress

## Description

As an integrating developer, I want a storage outage to come back as a standard, retryable 503 with `Retry-After` (an OpenAI error object on `/v1`), so that my client backs off and retries instead of seeing a plain-text 500 or a 401.

## Acceptance Criteria

- [ ] Given the identity read raises `StorageUnavailableError`, when any authenticated route is called with a user token, then `require_identity` answers `503 {"detail":"Storage unavailable"}` with `Retry-After: <s>`, never 401. Break-glass `ADMIN_TOKEN` still resolves with no read.
- [ ] Given `POST /query`, when `DuplicateCheckError`, `UsageLimitError` or `ChatSessionError` is caused by `StorageUnavailableError`, then the response is `503 {"detail":"Storage unavailable: the request was not sent to the model."}` with `Retry-After`, the upstream stub records zero calls, and no audit row is written (O7). With a non-transient cause (`MissingRelationError`), today's `500` stands: `test_duplicate_check_storage_failure_returns_500` passes unchanged.
- [ ] Given `/v1/chat/completions` (stream and non-stream), when the same failures happen or identity is unavailable, then the response is `503` with body `{"error":{"message":"Storage is unavailable; the request was not sent to the model.","type":"api_error","param":null,"code":"storage_unavailable"}}`, `Retry-After`, and no `x-should-retry` header. `storage_unavailable` is a new `_FAULTS` entry in `v1_translate.py`, and `_HTTP_ERRORS[503]` maps a 503 `HTTPException` (from `require_identity`) to it.
- [ ] Given `Retry-After`, when computed, then it is `StorageUnavailableError.retry_after_seconds` (seconds to the breaker's next half-open, min 1; `1` when the breaker is closed and only the budget ran out). No 503 body carries driver text. The driver text is logged once through `_redacted()`.
- [ ] Given the breaker forced open in a test, when each of the three ingresses is called (`/query`, `/v1` non-stream, `/v1` stream), then each returns its Section 6.7 response and the upstream stub records zero calls (T1). With storage healthy, every existing `/query` and `/v1` test passes unchanged.

## Technical Notes

- `app/middleware/auth.py:14-20`, `app/services/identity.py:69-92`, `app/routers/query.py:27-41`, `app/routers/v1.py` (`_PIPELINE_FAULTS` `:111-117`, the `HTTPException` handler `:489-501`, the non-transient arm `:208-209`), `app/services/v1_translate.py` (`_FAULTS`, `_HTTP_ERRORS`).
- Detecting "caused by": the gate errors wrap the `StorageError` (`raise ... from exc`), so check `isinstance(exc.__cause__, StorageUnavailableError)` (or carry the flag on the gate error). Pick one rule and apply it on both routers.
- PRD-015 D7: a retryable fault has no `x-should-retry` header. Keep the stream commit rule (PRD-015 Section 6.4): every read that can fail closed runs before step 7, so the 503 keeps its real status. A post-commit fault becomes an SSE `error` event (`_sse_events` `:254-281`); just make sure `storage_unavailable` renders there.
- `docs/api.md` 503 rows are STORY-014. The chat UI is STORY-007. Journal-related 503s (`AuditUnavailableError`, headroom) are STORY-010 / STORY-011, which reuse this story's mapping.
- Any modified pre-existing assertion gets a comment citing PRD-018 D8.
- Tests: `tests/test_db_resilience_ingress.py` (non-`db`, pipeline/storage stubbed), plus `tests/test_query_router.py`, `tests/test_v1_*.py`, `tests/test_auth*.py` as they apply.

## Dependencies

- **Blocked by**: STORY-005
- **Blocks**: STORY-007, STORY-010, STORY-011

## PRD Reference

Source: [`PRD-018-db-resilience/PRD.md`](../../PRDs/PRD-018-db-resilience/PRD.md) — sections 3 (Integrating Developer), 4 (Ingress mapping), 5 (stories 2, 7), 6.7, 9.2 (T1, T9), 10, 15 (D8, D15), Open decisions O4, O7
