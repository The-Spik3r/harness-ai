---
id: STORY-004
prd: PRD-016
slug: tool-call-adapter-layer
title: ToolCall, Operation, the tool mapping layer and built-in OpenCode/Cline/SQL mappings
type: feature
priority: high
complexity: medium
phase: "1 - Threat model and vocabulary"
status: todo
labels: [backend, security, adapters]
epic_branch: epic/PRD-016-action-policy-rules
plan: null
report: null
commit: null
depends_on: [STORY-001, STORY-003]
blocks: [STORY-006, STORY-014]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-004: ToolCall, Operation, the tool mapping layer and built-in OpenCode/Cline/SQL mappings

## Description

As a security admin, I want every tool call mapped to the operation it performs, with unknown and malformed calls named as such, so that classification starts from what the call does rather than what the tool is called.

## Acceptance Criteria

- [ ] Given `ToolCall(id="c1", name="bash", arguments='{"command": "ls"}')` and the built-in mappings, when `map_tool_call` runs, then it returns `Operations((Operation(kind="shell", target="ls", source_tool="bash"),))`.
- [ ] Given each built-in mapping recorded in `SOURCES.md` (STORY-001), when a call with a realistic argument object is mapped, then it yields the documented kind and target; a tool STORY-001 found to name several paths yields one `fs_write` per path.
- [ ] Given `arguments` equal to `"not json"`, `"[]"`, `"{}"` (target key missing), `'{"command": 3}'` (non-string target), or a string longer than the `max_argument_characters` argument, when mapped, then the result is `Malformed(detail)`, and for the over-length case `json.loads` is never called.
- [ ] Given a tool name in no mapping, when mapped, then the result is `Unknown()`; given the name in the `opaque_tools` mapping passed in, then `Opaque(decision)` with the configured decision.
- [ ] Given the module, when imported, then it imports no `settings` and performs no I/O (asserted with the import-graph test pattern used for `pattern_detector`).

## Technical Notes

- New `app/services/action_adapters.py`: `ToolCall`, `Operation`, `ToolMapping(kind, target)`, `MappingResult = Operations | Opaque | Unknown | Malformed`, `map_tool_call(call, tools, opaque_tools, max_argument_characters)`.
- `BUILT_IN_TOOLS: Mapping[str, ToolMapping]` is module data so STORY-006 can place it in the built-in policy (PRD F1: "data in `action_config`, not code"); STORY-006's validator must accept it unchanged.
- Generic SQL names `query`, `execute_sql`, `run_sql` use the target key STORY-001 recorded.
- STORY-001 found that real tools do not fit a single-key `ToolMapping(kind, target)`. The mapping must support the shapes listed in `tests/corpora/actions/SOURCES.md`, section *Implications for STORY-004*: array targets (`commands[]`, `files[].path`, `requests[].url`), mixed string/argv elements, paths inside patch text (`apply_patch`), optional targets with a default (`glob.path?`), a second target key (`glob.pattern`), aliases and per-variant key spellings (`absolutePath`/`path`), and prefixed MCP names. For each shape, it either supports it or states that the shape maps to `tool.malformed` or `tool.unknown`.
- Taking plain parameters (not an `ActionPolicy`) keeps this story independent of STORY-006; STORY-014 passes the policy's fields.
- Tests: `tests/test_action_adapters.py`, parametrized over the `SOURCES.md` entries.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-001, STORY-003
- **Blocks**: STORY-006, STORY-014

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 4 (Operations and adapters), 6.2, 7 (F1), 15 (D1)
