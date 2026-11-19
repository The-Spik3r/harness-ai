---
story: STORY-015
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-015-cline-realtime-e2e.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: pending
status: COMPLETE
completed: 2026-11-19
---

# Implementation Report - STORY-015: Cline end-to-end on a real-time stream

## Summary

New opt-in e2e module `tests/e2e/test_cline_realtime.py` (mirrors STORY-014 for Cline 3.0.74), a stub script, a pure-helper module and a fast pin test. No `app/` change; `test_cline.py`, `_cline.py`, `_live.py` and `_opencode_realtime.py` are untouched.

Live run (`--run-e2e`, throwaway libSQL `harness-libsql-e2e021-015` on :8090, one pytest): **5 passed, 0 skipped, 0 failed** (39 s). The container was removed afterwards; no harness, stub or Cline process remained.

## Live outcomes (cline-realtime-run.json)

| Case | Cline exit | finish_reason | Upstream rules | Harness-side proof |
|------|-----------|---------------|----------------|--------------------|
| text | 0 | completed | [text] | 18 SSE chunks, >= 3 content deltas over >= 0.2 s, `streamed_realtime`, `chatcmpl-harness-rt-` id equals SSE id, whole `submit_and_exit` arguments |
| drop | 0 | completed | [drop, follow-up] | both rows real time; request 1 has no `tool_calls` delta and no `arguments`/`function` key; one deny (`sql.ddl`, `run_commands`, `call_rt_drop`) plus the allowed `submit_and_exit`; `app.db` and `git status` unchanged |
| reason | 0 | completed | [reason] | sentinel in `reasoning_content` deltas, `reasoning_shown` true, sentinel in no content delta, Cline text, workspace file (`.git` included) or audit row |

Risk 4 (client mishandles `reasoning_content`): Cline 3.0.74 **does display it**: 3 `agent_event` events with `contentType == "reasoning"` carried the sentinel. Cline's own data dir was not scanned (stated limit).
No silent fallback to buffered occurred; nothing needed a `pytest.skip`.

## Files Changed

| File | Action |
|------|--------|
| `tests/e2e/scripts/cline_realtime.json` | CREATE |
| `tests/e2e/_cline_realtime.py` | CREATE |
| `tests/e2e/test_cline_realtime.py` | CREATE |
| `tests/test_e2e_cline_realtime_script.py` | CREATE |
| `tests/e2e/scripts/README.md` | UPDATE |

## Validation

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (script pins, cline/opencode-realtime pins, marker, live helpers, untouched app, new module without opt-in) | 62 passed, 5 skipped |
| Live e2e | 5 passed |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

None of substance. The drop test asserts the note reached Cline through request 2 being selected by the note (rule 0 needs it in the last assistant turn) plus `note in texts or "[harness] tool call" in output`.

## Acceptance Criteria

- [x] AC1 text arrives in pieces and Cline completes: `test_the_answer_text_streams_in_pieces`
- [x] AC2 denied call: note shown, no fragment released: `test_a_denied_drop_table_never_leaves_in_pieces`
- [x] AC3 both grants, Cline displays `reasoning_content` (observed True): `test_reasoning_is_shown_live_and_never_written_down`
- [x] AC4 skipped without opt-in: module marker (5 skipped)
