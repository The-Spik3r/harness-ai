---
id: STORY-006
prd: PRD-009
slug: pipeline-writes-dedup-key-on-every-arm
title: "run_query computes dedup_key once and log_query writes it on all seven arms"
type: feature
priority: high
complexity: medium
phase: "3 - Switch to the key"
status: todo
labels: [backend, api, audit]
epic_branch: epic/PRD-009-duplicate-rescoping
plan: null
report: null
commit: null
depends_on: [STORY-002, STORY-003]
blocks: [STORY-007]
skills: []
created: 2026-09-16
updated: 2026-09-16
---

# STORY-006: run_query computes dedup_key once and log_query writes it on all seven arms

## Description

As a security admin, I want every audit row the pipeline writes to carry its duplicate key, so that when the lookup switches to the key (STORY-007), no arm silently writes a row that can never count as a prior query.

## Acceptance Criteria

- [ ] Given `run_query` in [app/services/query_pipeline.py](../../../app/services/query_pipeline.py), when it starts, then it computes `key = dedup_key(identity.user_id, [_UserTurn(prompt)])` exactly once, **before** the first `authorize(...)`, using a private frozen dataclass that satisfies `DedupTurn`.
- [ ] Given `log_query` in [app/services/audit_logger.py](../../../app/services/audit_logger.py), when it is read, then it accepts `dedup_key: Optional[str] = None` and puts it on the `AuditLog`. Given `_deny`, then `dedup_key` is a **required** keyword with no default, like `session_id`, with a comment citing PRD-009 Risk 6.
- [ ] Given each of the seven pipeline arms (three denials, duplicate block, suspicious block, input redactor failure, OpenRouter failure, output redactor failure, success; the three denials share `_deny`), when each is driven once, then exactly one row is written and its `dedup_key` equals `dedup_key(identity.user_id, [user(prompt)])`, **non-NULL**. There is one parametrized test per arm.
- [ ] Given the router's foreign-session refusal in [app/routers/query.py](../../../app/routers/query.py), when it logs, then it passes `dedup_key=None` explicitly, with a comment stating that the row is `success=False`, can never match, and why no key is computed there. A test asserts that row's `dedup_key is None`.
- [ ] Given `test_hash_prompt_only_ever_receives_raw_text`, when this story lands, then its expected sequence gains the leading `("duplicate_checker", _PROMPT_A)` from key derivation, with a PRD-009 Section 6.5 comment, and every hashed text is still raw. The lookup is unchanged (still `prompt_hash`), and the regression and characterization modules pass unmodified.

## Technical Notes

- This story only **writes** the key. Reading it is STORY-007. The split keeps each commit reviewable, and it means rows written between the two stories already carry keys.
- Follow PRD-008 STORY-009 ([.agents/stories/PRD-008-chat-sessions/STORY-009-pipeline-session-passthrough.md](../PRD-008-chat-sessions/STORY-009-pipeline-session-passthrough.md)) and the `session_id` comment on `_deny`: required keyword, not a closure.
- `dedup_key` raises `ValueError` only for inputs `/query` can't produce (a single `user` turn always works). Don't catch it; an exception there is a programming error.
- Computing the key before authorization is intentional (PRD Section 6.1): denial rows carry it too, for investigative consistency. `test_forbidden_identity_blocked_before_check_duplicate` must still pass, because computing the key is not checking for duplicates.
- `ChatState.send()` ([chat_ui/chat_ui/state.py](../../../chat_ui/chat_ui/state.py)) calls `run_query(prompt=...)` and needs no change. Confirm that [tests/test_chat_state.py](../../../tests/test_chat_state.py) passes.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-002, STORY-003
- **Blocks**: STORY-007

## PRD Reference

Source: [`PRD-009-duplicate-rescoping/PRD.md`](../../PRDs/PRD-009-duplicate-rescoping/PRD.md) — sections 4 (Pipeline & logging), 6.1, 6.5, 6.7, 7 (F6), 11, 14 (Risk 6)
