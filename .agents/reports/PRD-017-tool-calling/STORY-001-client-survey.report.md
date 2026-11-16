---
story: STORY-001
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-001-client-survey.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: pending
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-001: Client survey (OpenCode 2.0.10, Cline CLI 3.0.74)

**Plan**: `.agents/plans/PRD-017-tool-calling/completed/STORY-001-client-survey.plan.md`
**Epic Branch**: `epic/PRD-017-tool-calling`
**Commit**: `pending`

## Summary

Re-surveyed OpenCode 2.0.10 (source at `b8cedc1a` plus the installed binary) and the Cline CLI 3.0.74 (source at `a459f1d0`, the pinned `@ai-sdk/openai-compatible@3.0.67`, a live headless run). OpenCode drifted (`bash` to `shell`, `apply_patch` to `patch`, `filePath` to `path` on read/write/edit, a new CodeMode `execute`), so `BUILT_IN_TOOLS` gained `shell` and `patch` and `filePath|path` on read/write/edit; `execute` stays unmapped (`tool.unknown`). Cline has no tool drift. Cline runs headless against a local base URL (verified); OpenCode's live capture was not achieved.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Pin versions and refs | none | done |
| 2 | OpenCode 2.0.10 tool schemas (source + binary) | none | done |
| 3 | OpenCode request and stream shapes | none | done |
| 4 | Cline CLI local install (git-ignored, pinned) | `.gitignore` | done |
| 5 | Cline tool set and request shapes | none | done |
| 6 | Live capture (time-boxed) | scratchpad only | Cline done; OpenCode not achieved |
| 7 | SOURCES.md | `tests/corpora/actions/SOURCES.md` | done |
| 8 | Mapping data | `app/services/action_adapters.py` | done |
| 9 | Adapter tests | `tests/test_action_adapters.py` | done |
| 10 | Synthetic corpus and vocabulary | `tests/test_action_corpus.py`, 5 yaml files | done |
| 11 | Spike note | `.agents/spikes/PRD-017-tool-calling/client-survey.md` | done |
| 12 | Targeted validation | none | done |
| + | Orchestrator addition: sample policy | `examples/action_policy.yaml`, `tests/test_action_config.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (adapters, corpus, config, secrets, policy, untouched_app) | 1558 passed, 1 skipped, 0 failed |
| Full suite | deferred to orchestrator (user decision) |
| E2E: `cline --version` is 3.0.74, dir git-ignored | pass |
| E2E: Cline live capture (request shapes, tool executed, follow-up request) | pass |
| E2E: OpenCode live capture | not achieved (no request reached the responder in 100 s) |
| E2E: no home config written | pass (`~/.cline` absent; OpenCode state under the scratch dir; see note in the spike) |

`tests/test_action_network.py` + `tests/test_pii_redaction_integration.py` were also run as a guard: `test_action_network.py` passes; `test_pii_redaction_integration.py` failed with `no such table: audit_logs` from the shared libSQL server while another suite was running (a DB state problem in a file this story did not touch; no test was renamed or removed).

## Files Changed

See `git show --stat`. Code: `app/services/action_adapters.py` (data only). Tests: adapters, corpus, config, 5 synthetic files. Docs: SOURCES.md, the spike note, `examples/action_policy.yaml`, `.gitignore`.

## Deviations from Plan

- The mapping data is in `action_adapters.BUILT_IN_TOOLS`, not `action_config.py` (accepted by the orchestrator).
- `examples/action_policy.yaml` was updated (orchestrator decision): `shell`, `patch`, `filePath|path`; 7 to 9 tools, pinned count and a comment in `tests/test_action_config.py`.
- `tests/test_action_corpus.py` had a second hard-coded client tuple in `test_ordinary_agent_work_is_never_denied`; it now includes `OpenCode 2.x`.
- The Cline CLI subsection adds no table rows (no drift in the `--yolo` mode); `spawn_agent`, `team_*` and `web_search` are described in prose.
- Task 6: OpenCode live capture not achieved.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_action_adapters.py` | 13 new SOURCES-driven rows (OpenCode 2.x) with realistic samples; `filePath`+`path` together is Malformed; both spellings alone are one operation; 2.x `read` of a directory; `Environment ID` line is not a target; `patch` does not read `input`; `execute` and `subagent` are Unknown |
| `tests/test_action_corpus.py` | vocabulary and ordinary-work checks include `OpenCode 2.x` |
| synthetic corpus | ordinary-opencode2-{write-relative,edit-relative,patch}, rule-opencode2-{shell-unlisted,execute-unknown} |
| `tests/test_action_config.py` | sample policy loads with 9 tools; `execute` absent |

## Acceptance Criteria

- [x] SOURCES.md records OpenCode 2.0.10 and Cline CLI 3.0.74 (version, names, keys, source locations) and the differences from PRD-016's survey
- [x] Spike note lists request keys, history shapes and delta expectations per client (OpenCode from source, binary and a recorded fixture; Cline also live)
- [x] Drift corrected as data with adapter and corpus cases; Cline's "no drift" stated
- [x] Cline headless method stated and verified live
- [x] All tasks completed (Task 6 partially, time-boxed and optional)
- [x] Backend imports without error
- [x] Targeted tests green; full suite deferred to the orchestrator
- [x] Follows existing patterns
