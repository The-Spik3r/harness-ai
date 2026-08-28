---
id: STORY-006
prd: PRD-004
slug: chat-state-structural-tests
title: "Migrate test_chat_state.py to structural bubble assertions"
type: technical
priority: high
complexity: medium
phase: "2 - Typed message model"
status: done
labels: [tests, ui, state]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: null
report: null
commit: null
depends_on: [STORY-005]
blocks: [STORY-019]
skills: []
created: 2026-08-21
updated: 2026-08-21
---

# STORY-006: Migrate test_chat_state.py to structural bubble assertions

## Description

As an integrating developer, I want the chat tests to assert on structured message fields instead of rendered strings, so that the typed model is verified more strictly than the old dict-equality checks, and pipeline behavior is provably unchanged (PRD Risk 1, Section 12 Phase 2).

## Acceptance Criteria

- [x] Given the bubble assertions at `tests/test_chat_state.py:181-210`, when migrated, then they assert on structured fields (`kind == "duplicate"`, `first_query_at == timestamp`, `pattern == "override"`) instead of formatted strings such as `f"Blocked — Duplicate query within 24 hours (first sent at {timestamp})"`.
- [x] Given each of `QuerySuccessResponse`, `QueryBlockedDuplicateResponse` and `QueryBlockedSuspiciousResponse`, when its test runs, then every field of that response is asserted to have landed on the appended message (PRD Section 12 Phase 2 validation).
- [x] Given the audit-parity tests at `tests/test_chat_state.py:240-306`, when the suite runs, then they pass **unmodified** — they assert on database rows, not bubbles, and are the proof that pipeline behavior is unchanged (Risk 1).
- [x] Given the four exception paths, when their tests run, then each asserts `kind`, `detail` and `pending is False` — no path asserts merely "a message exists".
- [x] Given the full repo suite (PRD-001/002/003), when it runs, then it passes and `tests/test_chat_state.py` is the only test file changed.

## Technical Notes

- Risk 1 verbatim from the PRD: "Phase 2 migrates them to assert on *structured fields* (`kind == \"duplicate\"`, `first_query_at == timestamp`) rather than on rendered strings — stricter than the current string comparison, not looser. The audit-parity tests (lines 240-306) assert on database rows, not bubbles, and must pass unmodified as the proof that pipeline behavior is unchanged."
- Existing helpers to reuse rather than rewrite: `_make_state()`, `_send()`, `_seed_duplicate()`, `_count_audit_rows()`, `_fail_if_called()` (`tests/test_chat_state.py:33-85`).
- Tests already run under `pytest` + `pytest-asyncio`; no new test dependency (PRD Section 8).
- The temptation to weaken assertions into `assert state.messages[-1].kind` truthiness checks is the exact failure mode Risk 1 names — every migrated assertion must compare a value, not merely presence.

## Dependencies

- **Blocked by**: STORY-005
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (last bullet), Section 11, Section 12 Phase 2, Risk 1
