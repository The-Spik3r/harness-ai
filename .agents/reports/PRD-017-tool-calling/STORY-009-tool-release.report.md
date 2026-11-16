---
story: STORY-009
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-009-tool-release.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: d207ac7
status: COMPLETE
completed: 2026-11-16
---

# Implementation Report - STORY-009: tool_release.apply_decisions

**Plan**: `.agents/plans/PRD-017-tool-calling/completed/STORY-009-tool-release.plan.md`
**Epic Branch**: `epic/PRD-017-tool-calling`
**Commit**: `d207ac7`

## Summary

New pure module `app/services/tool_release.py`: `Release` (frozen: `tool_calls`, `notes`, `finish_reason`), `apply_decisions(calls, decisions)`, `content_with_notes(content, notes)`, and the constants `DENIAL_NOTE_TEMPLATE` and `NOTE_FIELD_CAP = 64`. Allow and flag calls are released as the same `ToolCallSpec` objects in model order; each deny yields one note; `finish_reason` is `"tool_calls"` / `"stop"` / `None` (no calls). Length mismatch, id mismatch at a position, or an unknown decision value raise `ValueError` (all pairs validated before building; messages carry indexes and counts, never values). No caller is wired; flag-off behaviour is untouched.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create the pure module | `app/services/tool_release.py` | done |
| 2 | Tests incl. purity and import graph | `tests/test_tool_release.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (`test_tool_release.py`, `test_action_policy.py`, `test_messages.py`, one call) | 224 passed, 0 failed, 0 skipped |
| E2E | no endpoint change; import check and targeted run above |
| Full suite | deferred to orchestrator (user decision) |

## Files Changed

| File | Action |
|------|--------|
| `app/services/tool_release.py` | CREATE |
| `tests/test_tool_release.py` | CREATE |
| `.agents/` plan (archived), report, story/index edits (STORY-009/010/011 notes) | UPDATE/CREATE |

## Deviations from Plan

- None in code. As the plan recorded, the story's "add to the shared purity test" does not exist; the purity (AST) and import-graph (subprocess) tests live in `tests/test_tool_release.py`. No existing test edited.
- `finish_reason is None` when there are no calls (orchestrator decision).

## Tests Written

`tests/test_tool_release.py`: allowed released / denied noted; all denied -> stop; flag released; mixed order; 64-cut and reason unchanged (braces); length mismatch; out-of-order ids; bad pair no partial release; unknown decision; vocabulary pinned to `DECISIONS`; no calls; frozen fields; `content_with_notes` (parametrized); purity (AST); import graph (subprocess).

## Acceptance Criteria

- [x] AC1: `test_allowed_released_denied_noted`
- [x] AC2: `test_every_call_denied_is_stop_with_notes_in_order`, `test_flag_is_released_without_a_note`
- [x] AC3: `test_note_cuts_name_and_id_to_64_and_keeps_reason_unchanged`
- [x] AC4: `test_length_mismatch_raises`, `test_out_of_order_decisions_raise_without_naming_values`
- [x] AC5: `test_content_with_notes`
