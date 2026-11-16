---
id: STORY-009
prd: PRD-017
slug: tool-release
title: "tool_release.apply_decisions: release allowed calls, drop denied ones with a note, finish_reason"
type: feature
priority: high
complexity: small
phase: "3 - Decide and release"
status: done
labels: [backend, action-policy]
epic_branch: epic/PRD-017-tool-calling
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-009-tool-release.plan.md
report: .agents/reports/PRD-017-tool-calling/STORY-009-tool-release.report.md
commit: d207ac7
depends_on: [STORY-003]
blocks: [STORY-010]
skills: []
created: 2026-11-15
updated: 2026-11-16
---

# STORY-009: tool_release.apply_decisions: release allowed calls, drop denied ones with a note, finish_reason

## Description

As an integrating developer, I want a denied tool call removed and explained in a sentence while my allowed calls still go through, so that one denial costs me one call and my agent can report why.

## Acceptance Criteria

- [ ] Given calls `[read, bash-curl-sh]` decided `[allow, deny]`, when `apply_decisions` runs, then `Release.tool_calls == (read,)` (the same `ToolCallSpec` object, unmodified), one note `[harness] tool call bash (call_2) was denied: <reason>`, `finish_reason == "tool_calls"`.
- [ ] Given every call denied, then `tool_calls == ()`, one note per call in model order, `finish_reason == "stop"`; given a `flag` decision, then the call is released (D9) and no note is written.
- [ ] Given a model-chosen `name` or `id` longer than 64 characters, when the note is built, then each is cut to 64; `reason` is PRD-016's `ActionDecision.reason`, inserted unchanged.
- [ ] Given `calls` and `decisions` of different lengths or out of order (by `tool_call_id`), when called, then `ValueError` (a programming error, never a silent release).
- [ ] Given a content string and the notes, when the PRD Section 6.6 joining helper runs, then `content = "\n\n".join(filter(None, [content, *notes]))`, and `""` with no notes stays `""` (the result translator maps it to `null`, STORY-011).

## Technical Notes

- New pure module `app/services/tool_release.py`: no settings, no I/O, no logging. It may import `ActionDecision` for typing only (`TYPE_CHECKING`), and `ToolCallSpec` from `app.models.messages`.
- Decisions come from `action_policy.evaluate_all` (`app/services/action_policy.py:343-360`), one per call, same order (it preserves input order).
- The note template and the 64-character cut are PRD-017 Section 6.6; keep them module constants so the docs (STORY-018) and the E2E assertions can cite one source.
- Add `tool_release` to the purity/import-graph test that covers `action_policy` etc. (find it in `tests/test_action_*.py`).
- Tests: new `tests/test_tool_release.py`.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-003
- **Blocks**: STORY-010

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 5 (stories 2, 3), 6.6, 7 (F6), 15 (D1, D2, D9)
