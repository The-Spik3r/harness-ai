---
id: STORY-011
prd: PRD-015
slug: fault-mapping-and-retry-semantics
title: "Upstream and internal fault mapping with deliberate retry semantics"
type: feature
priority: high
complexity: medium
phase: "2 - Non-streaming endpoint"
status: todo
labels: [backend, api, errors, upstream]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: [STORY-002, STORY-010]
blocks: [STORY-013]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-011: Upstream and internal fault mapping with deliberate retry semantics

## Description

As an integrating developer, I want a transient upstream or storage fault to be one my client retries and a deterministic fault to be one it does not, so that retries recover from blips without hammering the harness on failures that will repeat.

## Acceptance Criteria

- [ ] Given `OpenRouterError(retryable=True)` (timeout, connect, upstream 5xx, upstream 429), when it reaches the `/v1` route, then 502 `api_error` / `upstream_unavailable` without `x-should-retry: false`; given `retryable=False` (upstream 4xx, malformed shape, null content, missing key), then 502 `upstream_error` with `x-should-retry: false`.
- [ ] Given `DuplicateCheckError` or `UsageLimitError`, when raised, then 500 `internal_error`, retryable; given `PiiRedactorError` (input or output), then 500 `redaction_failed` with `x-should-retry: false`.
- [ ] Given each fault, when the audit is read, then the rows are exactly what `/query` writes for the same fault today (one `success=False` row for upstream and redaction errors; none for a failed duplicate lookup or usage gate), with `ingress='v1'`.
- [ ] Given an upstream error message, when it becomes `error.message`, then it is the client's `OpenRouterError` text and never contains the provider's response body.
- [ ] Given a retryable upstream failure retried once by a client and then answered, when the audit is read, then the failed attempt is `success=False` and the retry is not held as a duplicate (PRD-009 Section 6.3).

## Technical Notes

- In `app/routers/v1.py`, an `except` chain around `await run_in_pipeline(...)` mirroring `app/routers/query.py`'s, mapping to error objects instead of `HTTPException`. Keep the mapping as a table in `v1_translate` (exception type + `retryable` → status, `type`, `code`, retry flag) so STORY-013's post-commit error event reuses it.
- `x-should-retry: false` is honoured by the Stainless-generated OpenAI SDKs ahead of their status rule; STORY-015 verifies it against the pinned SDK. Status codes stay the primary lever for clients that ignore the header.
- `ChatSessionError` cannot occur on `/v1` (no session), so it is not mapped; a test asserts `run_conversation` is called with `session_id=None`.
- Tests: extend `tests/test_v1_errors.py`; drive the client failures with `httpx.MockTransport` through the real `call_openrouter` so `retryable` comes from STORY-002's code, not from a hand-built exception.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-002, STORY-010
- **Blocks**: STORY-013

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 2 (Retry only what retrying can fix), 7.5, 11, 15 (D7)
