---
story: STORY-014
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-014-opencode-realtime-e2e.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: pending
status: COMPLETE
completed: 2026-11-19
---

# Implementation Report - STORY-014: OpenCode end-to-end on a real-time stream

## Summary

New opt-in module `tests/e2e/test_opencode_realtime.py` runs the real OpenCode (2.3.2) against a harness with
real time on (file-mode registry, `STREAMING_ENABLED=true`, roles file granting `stream:realtime` /
`reasoning:view`). `_live.Recorder` gained an opt-in `keep_sse` capture. No `app/` change; `test_opencode.py` untouched.

## Live run (the proof; CI skips e2e)

`--run-e2e` against a throwaway libSQL (`harness-libsql-e2e021-014`, :8089): **5 passed in 28.7 s**.
Without `--run-e2e`: 5 skipped (AC4). `tests/e2e/test_opencode.py` the same way: 3 passed, 1 failed
(`test_the_pinned_opencode_is_the_one_that_runs`: pins v2.0.10, installed 2.3.2; pre-existing, not touched).
Container removed; no harness, stub or OpenCode process left.

## Findings

- OpenCode: `opencode v2.3.2`. The 2.0.10 script vocabulary (`shell` tool, `advertises: shell`, `path` keys) and the
  existing `npm`/`options` provider config still work unchanged on 2.3.2.
- Reasoning field: docs https://opencode.ai/docs/models name `compatibility.reasoningField` (value
  `reasoning_content` accepted among others). Used it with `reasoning_content` (O5). OpenCode accepts any unknown key
  silently, so acceptance proves nothing; `--thinking` is what shows thinking blocks (`type: reasoning` events).
  Direct-to-stub probe: with `--thinking` OpenCode displayed the stub's `reasoning` delta even without the key.
  Through the harness (`reasoning_content`, key set): displayed = True, 1 reasoning event. Observation only, not asserted.
- Real time was not silently buffered: every audit row had `streamed_realtime` true, `completion_id` `chatcmpl-harness-rt-*`
  equal to the SSE chunk id. No app bug found.

## Tasks

| # | Task | File |
|---|------|------|
| 1 | Recorder `keep_sse` + unit test | `tests/e2e/_live.py`, `tests/test_e2e_live.py` |
| 2 | Stub script, 3 scenarios | `tests/e2e/scripts/opencode_realtime.json` |
| 3 | Pure helpers | `tests/e2e/_opencode_realtime.py` |
| 4 | Live module | `tests/e2e/test_opencode_realtime.py` |
| 5 | Fast pins | `tests/test_e2e_opencode_realtime_script.py` |

## Validation

| Check | Result |
|---|---|
| Backend import | OK |
| Targeted tests (realtime_script, opencode_script, e2e_live, e2e_marker, untouched_app) | 54 passed |
| Live e2e | 5 passed |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- `--thinking` added to the OpenCode command so reasoning events are emitted (observation only).
- Reasoning key given as `compatibility.reasoningField`, docs-confirmed.
- Roles trick as planned (`user`/`auditor` redefined; `manage_users.py` limits `--role`).

## Acceptance Criteria

- [x] AC1 `test_the_answer_text_streams_in_pieces`
- [x] AC2 `test_a_denied_drop_table_never_leaves_in_pieces`
- [x] AC3 `test_reasoning_is_shown_live_and_never_written_down`
- [x] AC4 skipped without `--run-e2e` (5 skipped)
