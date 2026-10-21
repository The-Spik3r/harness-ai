---
id: STORY-015
prd: PRD-015
slug: e2e-openai-python-sdk
title: "E2E: OpenAI Python SDK, non-streaming, streaming, blocks and retries"
type: technical
priority: high
complexity: medium
phase: "4 - Real clients, deployment, documentation"
status: todo
labels: [tests, e2e, clients]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: [STORY-012, STORY-013, STORY-014]
blocks: [STORY-016, STORY-017, STORY-019]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-015: E2E: OpenAI Python SDK, non-streaming, streaming, blocks and retries

## Description

As an integrating developer, I want proof that the official OpenAI Python SDK works against the harness with only base URL and key changed, including how it surfaces and retries each error, so that I can trust the endpoint before wiring a real tool to it.

## Acceptance Criteria

- [ ] Given a live `uvicorn` harness pointed at the stub upstream, and `OpenAI(base_url=".../v1", api_key=<user token>)` with default `max_retries`, when `chat.completions.create` is called without and with `stream=True` (and `stream_options={"include_usage": True}`), then the content, `finish_reason`, `usage` and `id` match the stub's script and the audit row.
- [ ] Given a suspicious prompt, a duplicate resend, an over-limit conversation, a non-allowlisted model and an exhausted budget, when each is sent (streamed and not), then the SDK raises `BadRequestError` or `PermissionDeniedError` with the PRD Section 7.5 `code`, and the audit shows exactly one row per call: the SDK did not retry.
- [ ] Given a stub rule returning 503 once and then 200, when called, then the SDK retries and succeeds, leaving one `success=False` row and one success row; given a stub rule returning 400, then the SDK raises after one attempt (one row), proving `x-should-retry: false` is honoured by the pinned SDK version.
- [ ] Given `client.models.list()`, when called, then it returns the allowlist.
- [ ] Given the run, when the report is written, then it records the pinned `openai` version, the exact commands, and the audit rows produced.

## Technical Notes

- Add `requirements-e2e.txt` with `openai==<version current when this story runs>`; it is not added to `requirements.txt` (PRD Section 8).
- Tests in `tests/e2e/test_openai_sdk.py`, marked so the everyday suite skips them (follow the `benchmark` marker's opt-in pattern in `tests/conftest.py`, e.g. `-m e2e --run-e2e`). They start the stub and `uvicorn` as subprocesses on ephemeral ports against a throwaway libSQL container (see the test-env memory notes for the recipe and the RBAC bootstrap: `manage_users.py create-user`).
- Usage-limit case: `USAGE_DAILY_TOKEN_BUDGET=*=0` is rejected at startup; use `*=1` and pre-charge with `usage_limits.charge(...)`.
- If the pinned SDK does not honour `x-should-retry`, record it in the report, and assert the status-code behaviour only; do not change the mapping in this story.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-012, STORY-013, STORY-014
- **Blocks**: STORY-016, STORY-017, STORY-019

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 5 (stories 1, 2, 4, 6), 7.5, 8, 11 (Functional requirements), 15 (Assumptions)
