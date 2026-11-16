---
id: STORY-001
prd: PRD-017
slug: client-survey
title: "Client survey: OpenCode 2.0.10 and Cline request/response shapes; PRD-016 mappings re-verified"
type: spike
priority: high
complexity: medium
phase: "1 - Survey and foundations"
status: todo
labels: [research, clients, action-policy]
epic_branch: epic/PRD-017-tool-calling
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-008, STORY-010, STORY-016, STORY-017]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-001: Client survey: OpenCode 2.0.10 and Cline request/response shapes; PRD-016 mappings re-verified

## Description

As the PRD-017 implementer, I want to know exactly what OpenCode 2.0.10 and the current Cline send and expect on a tool-calling `/v1` request, so that the request translator accepts their shapes and the action policy's built-in mappings name their real tools.

## Acceptance Criteria

- [ ] Given OpenCode 2.0.10 (installed on the dev machine) and the Cline CLI at a pinned version, when their tool schemas are read from the installed package or the pinned source, then `tests/corpora/actions/SOURCES.md` records, per client: version, every tool name, each tool's target argument key(s) and shape, and the source location — and says where they differ from PRD-016's survey (OpenCode v1.19.5, Cline 4.1.26).
- [ ] Given each client's request to an OpenAI-compatible provider, when inspected (source, or a recording proxy run against the stub), then a new spike note `.agents/spikes/PRD-017-tool-calling/client-survey.md` lists the top-level keys it sends with tools on (`tools`, `tool_choice`, `parallel_tool_calls`, `stream`, `stream_options`, anything else), how it writes assistant `tool_calls` and `tool` turns in history (content `null` vs `""`, text parts, `tool_call_id`), and whether it expects incremental `tool_calls` deltas or accepts one complete fragment per index.
- [ ] Given a tool whose name or argument key drifted since PRD-016, when the survey finds it, then the built-in mapping in `app/services/action_config.py` is corrected as data (old names kept as candidates where a still-supported version uses them), and `tests/test_action_adapters.py` / the synthetic corpus gain a case for the new shape; if nothing drifted, the note says so.
- [ ] Given Cline, when the note is written, then it states how STORY-017 will drive it headlessly against a custom base URL (CLI flags, config file, environment), or, if that is impossible, the fallback (replaying Cline's recorded request shapes) and what that cannot prove.

## Technical Notes

- PRD-016's survey and its method: `tests/corpora/actions/SOURCES.md`, `.agents/spikes/PRD-016-action-policy-rules/threat-model.md`. Follow its provenance format (client, version or commit, schema location).
- OpenCode: `opencode --version` prints `2.0.10`; the package is under `C:/Users/nahue/AppData/Roaming/npm/node_modules/`. Read the tool definitions there; do not upgrade or reinstall it.
- Cline: not installed. If a local install is needed, install it into a git-ignored directory (e.g. `tests/e2e/.clients/`, add it to `.gitignore`), pinned, never with `npm -g`. Record the exact command.
- A recording proxy for request shapes exists: `tests/e2e/_live.py` (names only, never content). Reuse it with `scripts/stub_openrouter.py` if a live capture is simpler than reading source.
- Do not change request-path code in this story; mapping data in `action_config` and its tests only.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-008, STORY-010, STORY-016, STORY-017

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 8 (Clients), 12 (Phase 1), 14 (Risks 3, 7)
