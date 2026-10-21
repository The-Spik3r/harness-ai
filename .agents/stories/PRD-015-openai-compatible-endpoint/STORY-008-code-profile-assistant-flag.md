---
id: STORY-008
prd: PRD-015
slug: code-profile-assistant-flag
title: "code profile flags assistant turns; examples/patterns.yaml matches again"
type: enhancement
priority: medium
complexity: small
phase: "1 - Foundations"
status: todo
labels: [backend, patterns, security]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-019]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-008: code profile flags assistant turns; examples/patterns.yaml matches again

## Description

As a compliance admin, I want an injection phrase written into a caller-supplied `assistant` turn to be recorded under the `code` profile, so that a `/v1` caller cannot get past the `user` block invisibly by forging history.

## Acceptance Criteria

- [ ] Given `BUILT_IN_POLICY`, when the `code` profile is read, then `roles == {"user": "block", "assistant": "flag", "tool": "flag"}` in that declared order and `lists` is still only `injection`; `chat` is unchanged.
- [ ] Given `examples/patterns.yaml`, when it is loaded, then it equals `BUILT_IN_POLICY` (the existing equality test, with its expectation updated and nothing else).
- [ ] Given `run_conversation(profile="code")` with `ignore previous instructions` in an `assistant` turn and a clean last `user` turn, when it runs, then the request is answered and writes a flag row with `pattern_role='assistant'`, `pattern_action='flag'`, followed by the success row.
- [ ] Given the same conversation under `chat`, and an `assistant` turn containing `override` (a `keywords` entry not loaded by `code`) under `code`, when each runs, then neither writes a flag row.
- [ ] Given the PRD-011 corpora (`tests/test_pattern_corpus.py`) and the default-config regression, when they run, then any change in their results is only the new `assistant` flag cell, and each changed expectation is listed in the story report.

## Technical Notes

- `app/services/pattern_config.py` `_build_built_in()`: add `"assistant": "flag"` to `code`, and rewrite the comment above it so it states D9: `system` is the client's own prompt and is not inspected; `assistant` is flagged, not blocked, because real agent history quotes such phrases. Update the `Profile` docstring's "PRD-014 is where that cell may change" sentence to say it changed here.
- `examples/patterns.yaml`: the `code` profile gains `assistant: flag`.
- The flag arm in `run_conversation` already exists (PRD-011 STORY-009); no pipeline change. Its comment "Unreachable from any ingress today" becomes reachable once STORY-009 mounts `/v1`; update the comment there.
- README wording is STORY-019's.
- Tests: `tests/test_pattern_config.py`, `tests/test_pattern_profiles.py`, `tests/test_query_pipeline_patterns.py`.
- Skills: none applicable.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 7.8, 9.2 (T1, T2), 14 (Risk 8), 15 (D9)
