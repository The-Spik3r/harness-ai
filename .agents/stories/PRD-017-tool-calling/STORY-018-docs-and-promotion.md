---
id: STORY-018
prd: PRD-017
slug: docs-and-promotion
title: README, docs/features.md, docs/roadmap.md, .env.example; brief promotion verified
type: technical
priority: medium
complexity: small
phase: "4 - Real clients and docs"
status: in-progress
labels: [docs]
epic_branch: epic/PRD-017-tool-calling
plan: .agents/plans/PRD-017-tool-calling/STORY-018-docs-and-promotion.plan.md
report: null
commit: null
depends_on: [STORY-013, STORY-015, STORY-016, STORY-017]
blocks: []
skills: []
created: 2026-11-15
updated: 2026-11-16
---

# STORY-018: README, docs/features.md, docs/roadmap.md, .env.example; brief promotion verified

## Description

As a platform operator, I want tool calling documented as shipped — how to turn it on, how to set up OpenCode and Cline, what a denial looks like and what is not covered — so that I can enable it safely.

## Acceptance Criteria

- [ ] Given `docs/features.md`, when read, then a *Tool calling* section describes the flag, `V1_TOOL_MODELS`, the order of steps (configure `ACTION_POLICY_FILE` first), what each check does with tool content (PRD-017 Section 6.5), the denial note and `finish_reason` rule, `harness.actions`, the buffered tool-call deltas, the dedup rule for tool loops, and the limits (no execution, history calls not re-evaluated, tool schemas not inspected, `functions` refused); the *Action policy rules* section no longer says nothing calls the engine.
- [ ] Given the README and `docs/features.md`, when read, then they give per-client setup for OpenCode and Cline (provider config, model name, workspace root and `shell.allow`, the Cline `tools:` mapping) taken from the E2E runs.
- [ ] Given `docs/roadmap.md`, when read, then the *OpenAI-compatible endpoint* "Not yet" paragraph and the *Action policy rules* "What PRD-017 adds" paragraph describe what shipped, and the Action policy checkbox is ticked.
- [ ] Given `.env.example`, when read, then `V1_TOOLS_ENABLED` and `V1_TOOL_MODELS` are present with comments in the existing style.
- [ ] Given `pre-prds/PRE-PRD-016-tool-calling.md` and `pre-prds/README.md`, when checked, then the brief is `status: promoted` with `prd:` pointing at this PRD, the track table links PRD-017, and Milestone 2 is marked reached (done at PRD creation where possible; this story verifies and fixes drift); every relative link in the changed docs resolves.

## Technical Notes

- Orchestrator note (STORY-017 plan): document the Cline CLI 3.0.74 setup (`cline auth --data-dir <ABSOLUTE dir> --provider openai-compatible --baseurl <harness>/v1`, then `--yolo --json -c <dir>`), and its pitfalls: a relative `--data-dir` silently falls back to api.openai.com; `-t` is not honoured and the loop only ends on `submit_and_exit`; Cline fetches feature flags from its own service at startup (outbound traffic the harness does not see, no known switch). A Cline deployment needs `opaque_tools: {submit_and_exit: allow}` and its own `tools:`/`shell.allow` (see `tests/e2e/cline/action_policy.yaml`).
- Orchestrator note (STORY-016): document the verified OpenCode 2.0.10 headless setup (provider `@ai-sdk/openai-compatible` with `options.baseURL`, `OPENCODE_CONFIG_CONTENT`, `agent.title.disable`, `OPENCODE_DISABLE_MODELS_FETCH=1`, `run --standalone`, stdin closed) and the pitfalls: `opencode run` waits on a non-closed stdin; it takes its working directory from `PWD`, not the process cwd; OpenCode sends `store` (recorded in `ignored_params`).
- Orchestrator note (STORY-001): `docs/features.md` (around line 279) lists only OpenCode v1.19.5 tool names; add the 2.0.10 names (`shell`, `patch`, `path` keys), the `execute` CodeMode tool (always denied), and the Cline CLI 3.0.74 headless setup from the survey note.
- Read every PRD-017 story report's Deviations for doc items, and the orchestrator notes added to this story's Technical Notes during the run.
- Follow PRD-016 STORY-020 and PRD-015 STORY-019 for structure and tone; `docs/roadmap.md:37, 43-52, 78-82` are the paragraphs named above.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-013, STORY-015, STORY-016, STORY-017
- **Blocks**: None

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 4 (Documentation), 6.5, 6.6, 9.2, 15
