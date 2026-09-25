---
id: STORY-010
prd: PRD-012
slug: redaction-size-limit
title: "Size limit and the redaction_characters refusal arm"
type: feature
priority: high
complexity: medium
phase: "3 - Policy into the pipeline"
status: in-progress
labels: [backend, pii, security, api]
epic_branch: epic/PRD-012-pii-for-code
plan: .agents/plans/PRD-012-pii-for-code/STORY-010-redaction-size-limit.plan.md
report: null
commit: null
depends_on: [STORY-009]
blocks: [STORY-011]
skills: []
created: 2026-09-23
updated: 2026-09-25
---

# STORY-010: Size limit and the redaction_characters refusal arm

## Description

As a security admin, I want a `code` request too large to analyze refused rather than forwarded unmasked, so that size is never a way past redaction.

## Acceptance Criteria

- [ ] Given `profile="code"` and analyzable characters (covered roles, fenced blocks blanked, newline runs not counted) above `PII_MAX_CHARACTERS_CODE`, when `run_conversation` runs, then it returns `QueryBlockedContextLimitResponse(reason="Conversation exceeds redaction limit", limit="redaction_characters", maximum=..., actual=...)` and `call_openrouter` is not called.
- [ ] Given that refusal, when the audit is read, then exactly one row was written by the arm: `success=0`, `error_message="redaction limit: characters {actual} > {maximum}"`, explicit `session_id`, non-NULL `dedup_key`; and a later identical request is not held as a duplicate.
- [ ] Given a conversation whose raw size exceeds the limit only because of fenced blocks, when it runs under `code`, then it is not refused.
- [ ] Given `app/models/schemas.py`, when it is read, then `limit` is `Literal["messages", "characters", "redaction_characters"]`, and the chat UI's context-limit bubble renders the new value with copy that names it.
- [ ] Given `/query` or the chat UI (`chat`, `max_characters=None`), when any input within `CONTEXT_MAX_CHARACTERS` is sent, then this arm cannot fire, which a test pins.

## Technical Notes

- The check sits at the head of step 6, after patterns, because what it measures depends on the policy (PRD Sections 6.1, 6.7). It never calls the analyzer. It only measures the lengths of blanked text.
- This is a fail-closed arm only. Skip-and-flag is deferred (D4) and must not appear, not even as an unused setting.
- Reuse PRD-010's context-limit audit shape; no new response class.
- Chat UI copy lives in `chat_ui/chat_ui/copy.py`. The bubble branches on `limit`.
- Skills: none applicable. The only UI change is one copy string on an existing bubble.

## Dependencies

- **Blocked by**: STORY-009
- **Blocks**: STORY-011

## PRD Reference

Source: [`PRD-012-pii-for-code/PRD.md`](../../PRDs/PRD-012-pii-for-code/PRD.md) — sections 6.1, 6.7 (D4), 9.2 (T5), 10, 11 (Functional requirements)
