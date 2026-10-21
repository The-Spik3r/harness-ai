---
id: STORY-016
prd: PRD-015
slug: e2e-aider
title: "E2E: Aider applies a scripted edit through the harness"
type: technical
priority: medium
complexity: medium
phase: "4 - Real clients, deployment, documentation"
status: todo
labels: [tests, e2e, clients]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: [STORY-013, STORY-014, STORY-015]
blocks: [STORY-019]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-016: E2E: Aider applies a scripted edit through the harness

## Description

As an integrating developer using Aider, I want Aider, with its default streaming, to complete an edit through the harness and to stop on a block, so that I can adopt the harness without changing how I work.

## Acceptance Criteria

- [ ] Given a throwaway git repository with one file, a live harness on the stub upstream, and Aider configured with `OPENAI_API_BASE` / `OPENAI_API_KEY` (harness token) and a model from the allowlist, when Aider is run non-interactively with an edit request, then the stub's scripted SEARCH/REPLACE edit is applied to the file and committed by Aider.
- [ ] Given that run, when the audit is read, then every row has `ingress='v1'`, `profile='code'`, `streamed=1`, one `conversation_key`, and `ignored_params` naming what Aider sent that was not forwarded; the report lists those names.
- [ ] Given a request the harness blocks (an injection phrase in the edit request), when Aider sends it, then Aider prints the harness reason and exits or returns to its prompt without retrying (one row).
- [ ] Given the run, when the report is written, then it records the pinned `aider-chat` version, the full command line, the `.aider` settings used, and whether Aider sends `tools` in this mode.

## Technical Notes

- `aider-chat==<pinned>` goes in `requirements-e2e.txt`, ideally a separate venv if its dependency pins clash with the harness's; record the choice.
- Aider reaches OpenAI-compatible servers through litellm; the model name may need the `openai/` provider prefix in Aider's config while the harness sees the bare allowlisted name. Work out and document the mapping; that is part of the README setup STORY-019 writes.
- The stub script returns an edit block in Aider's default edit format for the chosen model; pin `--edit-format` so the script stays valid.
- If Aider sends `tools` or a parameter in the reject set by default, the expected result is the explicit 400 (PRD Risk 2); find the configuration that avoids it, and record both in the report.
- Marked `e2e`, opt-in, like STORY-015.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-013, STORY-014, STORY-015
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 5 (stories 3, 7), 8, 11, 14 (Risks 2, 3)
