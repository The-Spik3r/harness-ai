---
story: STORY-001
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-001-action-threat-model-and-adapter-survey.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: pending
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-001: Action threat model and adapter survey (OpenCode, Cline, Aider) with SOURCES.md

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-001-action-threat-model-and-adapter-survey.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `pending`

## Summary

This is a research spike. No file under `app/`, `chat_ui/` or `tests/*.py` changed.

- **`tests/corpora/actions/SOURCES.md`** (new) records every tool the built-in adapters may map, using fixed-column tables a test can parse: client, tool, operation kind, target key, multi-target, paths, version, commit, schema permalink. It covers OpenCode v1.19.5, Cline v4.1.26 (current) and v3.89.2 (legacy, per variant with transport), Aider v0.86.0 and `main` @ `5dc9490`, and the generic SQL names. Every fact was re-read at the pinned commit during implementation, not copied from the plan. All 62 unique GitHub URLs in the file return HTTP 200.
- **`.agents/spikes/PRD-016-action-policy-rules/threat-model.md`** (new) maps T1–T13 to Section 6.3 rules and to a corpus group or unit test. **8 threats are answered by a rule and 5 are open findings (T4, T7, T10, T11, T13).** It also lists ten survey findings, S1–S10. Three of them are gaps where a rule fires but does not cover the threat: S3, PowerShell destructive commands under the grantable `shell.unlisted`; S7, a secret glob in `glob.pattern`; S9, directory searches returning secret contents.
- **PRD** Section 4 (the adapter and SQL bullets) and Section 15 (assumptions marked *Corrected* / *Verified*) are corrected. So are the factual Cline path statements in 6.5 items 2 and 4 and the 6.6 sample comment. No D-number changed.
- **STORY-004** gained one Technical Notes bullet pointing to *Implications for STORY-004*. Its ACs are unchanged.

Key findings:

- OpenCode `patch` is now `apply_patch` (`patchText`, with several paths inside the patch text). It also replaces `edit`/`write` for `gpt-` models. `list` was removed. `lsp` exists.
- Cline 4.x renamed every tool (`run_commands`, `read_files`, `editor`, `apply_patch`, `fetch_web_content`, `search_codebase`, …). Its targets are arrays or patch text, its executors accept many alias shapes, and it asks for **absolute** paths. The VS Code extension at v4.1.26 runs this SDK tool set, and the legacy `system-prompt/tools/` directory no longer exists.
- Cline 3.x tool names are the same in every variant, but the keys differ (`absolutePath` vs `path`). A native family with no spec of its own falls back to the GENERIC spec, so both spellings reach `tool_calls`.
- Aider: no reachable mode emits `tool_calls`, at either ref. The assumption is confirmed.
- SQL: `query` → `sql`, `execute_sql` → `query`, `run_sql` → `query` (Timeplus). Through OpenCode and Cline, MCP tools arrive prefixed (`postgres_query`, `supabase__execute_sql`).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Pin and verify OpenCode (latest release re-resolved: still v1.19.5) | research → `SOURCES.md` | ✅ |
| 2 | Pin and verify Cline 4.x (latest still v4.1.26) and 3.x per variant, plus extension wiring and transport | research → `SOURCES.md` | ✅ |
| 3 | Aider at v0.86.0 and `main` (every `aider/**/*.py` grepped at both refs) | research → `SOURCES.md` | ✅ |
| 4 | Generic SQL keys, plus a `run_sql` search | research → `SOURCES.md` | ✅ |
| 5 | Write `SOURCES.md` | `tests/corpora/actions/SOURCES.md` | ✅ |
| 6 | Write the threat model | `.agents/spikes/PRD-016-action-policy-rules/threat-model.md` | ✅ |
| 7 | PRD corrections (Sections 4 and 15; 6.5 items 2 and 4; 6.6 comment) | `PRD.md` | ✅ |
| 7b | STORY-004 Technical Notes pointer (orchestrator decision 4) | `STORY-004-tool-call-adapter-layer.md` | ✅ |
| 8 | Report, plan archive, story status, index | `.agents/` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ `OK` |
| Frontend lint | n/a (no `frontend/` in this repo) |
| Targeted tests: `tests/test_pattern_corpus.py -m "not db"` | ✅ 58 passed, 5 deselected |
| Full suite | not run, on the orchestrator's instruction (the test DB was in use). Only `.md` files changed |
| No code diff: `git diff --name-only d8a0fa4 -- app chat_ui 'tests/*.py'` | ✅ empty |
| Corpus discovery does not pick up `actions/` (`_corpus()` is called only for `code` and `agent_prompts`, and `SOURCES.md` is excluded by name) | ✅ |
| AC1/AC2 name loops, `tool.unknown`, the Corrections heading | ✅ no missing names |
| `## Aider`, `tool_calls` | ✅ |
| No branch links (`/(blob|tree)/(main|dev|master|timeplus)/`) | ✅ none |
| Every GitHub URL resolves (blob → raw, commit pages) | ✅ 62/62 HTTP 200 |
| T1–T13 rows, `## Open findings` | ✅ |
| Rule ids cited in the threat model all appear in PRD 6.3 | ✅ (the only non-match is `shell.allow`, a policy key, not a rule id) |
| `gen_index.py` | ✅ `errors: none | count: 20` |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/corpora/actions/SOURCES.md` | CREATE | +266 |
| `.agents/spikes/PRD-016-action-policy-rules/threat-model.md` | CREATE | +74 |
| `.agents/PRDs/PRD-016-action-policy-rules/PRD.md` | UPDATE | +7/-5 |
| `.agents/stories/PRD-016-action-policy-rules/STORY-004-tool-call-adapter-layer.md` | UPDATE | +1 |
| `.agents/stories/PRD-016-action-policy-rules/STORY-001-action-threat-model-and-adapter-survey.md` | UPDATE | frontmatter |
| `.agents/PRDs/PRD-016-action-policy-rules/index.md` | UPDATE | regenerated |
| `.agents/plans/PRD-016-action-policy-rules/completed/STORY-001-action-threat-model-and-adapter-survey.plan.md` | CREATE (archived) | +393 |
| this report | CREATE | — |

## Deviations from Plan

1. **PRD edits outside Sections 4 and 15** (allowed by orchestrator decision 3). Cline 4.x asks for absolute paths, which was confirmed in `schemas.ts#L15-L17` and `#L198-L203`. On that basis:
   - 6.5 item 2: "Cline's tools send relative paths" became "every surveyed client's executor accepts a relative path … (Cline 3.x's generic tool specs ask for one)".
   - 6.5 item 4: "OpenCode sends absolute paths, so an OpenCode deployment must set its root" became "OpenCode and Cline 4.x ask the model for absolute paths …, so a deployment of either must set its root".
   - 6.6 sample comment: `# OpenCode sends absolute paths; Cline relative ones` became `# OpenCode and Cline 4.x send absolute paths`.

   D11's rule is unchanged.
2. **STORY-004 was edited.** The plan said not to, but orchestrator decision 4 asked for one Technical Notes bullet, and it was added. Its ACs are unchanged.
3. **Section 4's Cline list now names 4.x as current**, with the 3.x names kept as "additional candidates" (orchestrator decision 2). The 3.x list keeps all seven PRD names, because each reaches `tool_calls` in at least one native family or through the GENERIC fallback.
4. **The PRD `updated:` field was already `2026-11-15`**, so setting it was a no-op, not a skipped step.
5. **The full suite was not run** (orchestrator decision 5). Only `tests/test_pattern_corpus.py -m "not db"` was run.
6. **`run_sql` has a source**: Timeplus, key `query`. The plan expected that none might be found. Neon also has `run_sql`, but its schema is generated from an operations spec that was not traced, so no key is recorded for it.
7. **Pins.** The Postgres reference server is pinned to the archive head `9be4674d` (the file last changed in `37415258`). Supabase is pinned to `main` head `9092ab90` (= release `mcp-server-supabase-v0.17.0`). Timeplus is pinned to its default-branch head `20c52f41`.
8. **The plan's guess that `replace_in_file` is multi-target is wrong.** It names one file per call. Recorded in `SOURCES.md`.

## Not changed, for the orchestrator

These are stale or doubtful statements outside the sections this story was allowed to edit:

- **PRD F1 (Section 7)** still says "`edit`/`patch` semantics … (OpenCode's `patch` can name several)". It should say `apply_patch`.
- **The PRD 6.6 sample** maps `run_sql: { kind: sql, target: statement }`. No surveyed server uses `statement`, and Timeplus uses `query`. Its `opaque_tools` names `todoread`, which OpenCode v1.19.5 does not have. Its `tools:` maps `write`/`edit` but not `apply_patch` (S10). STORY-007 owns `examples/action_policy.yaml`.
- **PRD 6.3's "Produced when" wording** for `tool.malformed` omits the T9 classifier-exception trigger, and for `shell.unclassifiable` it omits the D3 depth limit (threat model, *Open findings*).
- **PRD Risk 3** says "Cline on Windows runs PowerShell". It also applies to OpenCode, whose `bash` tool may run `pwsh`, `powershell` or `cmd`. The threat model's S3 is a real gap: a role holding `action:shell:exec` would be allowed `Remove-Item -Recurse -Force`. This is for STORY-010.

## Tests Written

None. This is a research story with no code. STORY-004 (`tests/test_action_adapters.py`, parametrized over the `SOURCES.md` tables) and STORY-017 will add the provenance tests.

## Acceptance Criteria

- [x] AC1: OpenCode. All nine PRD names are accounted for, with exact name, key, version and commit, and schema permalink. `patch` → `apply_patch` and `list` removed are under *Corrections to PRD Section 4*.
- [x] AC2: Cline. All seven PRD names, plus `use_mcp_tool`/`access_mcp_resource`, are recorded as `tool.unknown`, per variant, with the 4.x equivalents.
- [x] AC3: Aider. A sourced statement at v0.86.0 and `main`: no reachable mode emits `tool_calls`, so the assumption is confirmed.
- [x] AC4: Threat model. T1–T13 are mapped to rules and a corpus group or test, and `## Open findings` lists T4, T7, T10, T11 and T13.
- [x] AC5: PRD Sections 4 and 15 are corrected in the story commit. `updated:` is 2026-11-15.
