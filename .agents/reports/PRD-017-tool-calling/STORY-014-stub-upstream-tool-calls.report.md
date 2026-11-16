---
story: STORY-014
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-014-stub-upstream-tool-calls.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: f32424d
status: COMPLETE
completed: 2026-11-16
---

# Implementation Report — STORY-014: Stub upstream: scripted tool_calls replies, rules matching on any last turn

**Plan**: `.agents/plans/PRD-017-tool-calling/completed/STORY-014-stub-upstream-tool-calls.plan.md`
**Epic Branch**: `epic/PRD-017-tool-calling`
**Commit**: `f32424d`

## Summary

`scripts/stub_openrouter.py` (stdlib only) now answers with scripted `tool_calls` (content null by default, `type: "function"`, generated `call_<n>` ids, `finish_reason` `tool_calls`), lets a rule match the last message of any role (`role`, `last_role`) plus two content-independent qualifiers (`after_call`, `advertises`), and logs `tools=<n> calls=<n>`. `tests/e2e/scripts/tool_loop.json` scripts read, edit, `npm test`, final text. The stub never streams (`call_openrouter` never sends `stream`).

`after_call` and `advertises` are the plan's additions beyond the story text: `after_call` makes a loop sequence independent of client-rewritten ids and tool-result wording (STORY-016/017), and `advertises` lets one script serve OpenCode and Cline and end Cline's loop with `submit_and_exit`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Reply `tool_calls` parsing and body | `scripts/stub_openrouter.py` | done |
| 2 | Rule qualifiers and `Request` view | `scripts/stub_openrouter.py` | done |
| 3 | Log counts and docstring | `scripts/stub_openrouter.py` | done |
| 4 | Example script | `tests/e2e/scripts/tool_loop.json` | done |
| 5 | Tests (appended) | `tests/test_stub_openrouter.py` | done |
| 6 | README | `tests/e2e/scripts/README.md` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| stub imports | stdlib only |
| Targeted tests (`test_stub_openrouter.py`, `test_openrouter_client.py`, `test_untouched_app.py`) | 215 passed, 0 failed, 0 skipped |
| E2E | the loop test drives the whole script over a loopback socket through `call_openrouter` |
| Full suite | deferred to orchestrator (user decision) |

## Deviations from Plan

None. No existing assertion edited; the only removed lines in `tests/test_stub_openrouter.py` are the two import lines extended with `ToolCallSpec` / `ToolParams`. `Script.select(subject, hits)` kept as a wrapper. The optional manual CLI start was not run (the existing CLI test covers it).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_stub_openrouter.py` | tool_calls reply parses through `call_openrouter`; body shape (content null, type, string arguments, finish_reason override, content beside calls, no key without calls); generated and explicit ids; `role: tool`; role absent; `last_role`; `after_call` and `advertises`; role-less back-compat; tool loop run and failure branch; log counts and no leaks; failed answer logs 0 calls; rejection table (19 rows); arguments never echoed; `tool_loop.json` loads |

## Acceptance Criteria

- [x] AC 1 — tool_calls reply (`test_tool_calls_reply_parses_through_call_openrouter`, `test_tool_calls_body_...`, `test_generated_ids_...`)
- [x] AC 2 — role / last_role, role-less unchanged (`test_role_tool_matches_the_last_tool_message`, `test_last_role_...`, `test_rules_without_role_keep_matching_the_last_user_message`, existing suite)
- [x] AC 3 — log counts only (`test_tool_loop_log_names_counts_never_arguments_or_tool_content`, existing log tests)
- [x] AC 4 — example loop (`tool_loop.json`, `test_tool_loop_script_runs_read_edit_test_then_final_text`, `test_the_tool_loop_script_loads`)
