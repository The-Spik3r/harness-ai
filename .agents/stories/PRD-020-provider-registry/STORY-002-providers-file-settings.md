---
id: STORY-002
prd: PRD-020
slug: providers-file-settings
title: PROVIDERS_FILE setting and the conditional OPENROUTER_API_KEY requirement
type: feature
priority: high
complexity: small
phase: "1 - Registry and legacy equivalence"
status: in-progress
labels: [backend, config]
epic_branch: epic/PRD-020-provider-registry
plan: .agents/plans/PRD-020-provider-registry/STORY-002-providers-file-settings.plan.md
report: null
commit: null
depends_on: []
blocks: [STORY-003]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-002: PROVIDERS_FILE setting and the conditional OPENROUTER_API_KEY requirement

## Description

As a platform operator, I want a `PROVIDERS_FILE` setting and an `OPENROUTER_API_KEY` that is required only when no registry file is used, so that a deployment with only local models boots without an OpenRouter key and an existing deployment is unaffected.

## Acceptance Criteria

- [ ] Given `PROVIDERS_FILE` empty (the default) and no `OPENROUTER_API_KEY`, when `Settings()` is built, then startup fails with an error that names `OPENROUTER_API_KEY` and contains no key value.
- [ ] Given `PROVIDERS_FILE` set and `OPENROUTER_API_KEY` unset, when `Settings()` is built, then it succeeds and `settings.OPENROUTER_API_KEY == ""`.
- [ ] Given `PROVIDERS_FILE` set and a non-empty `V1_TOOL_MODELS`, when `Settings()` is built, then startup fails with an error naming both settings and saying capabilities now live in the registry (D6); with `V1_TOOL_MODELS` empty it passes.
- [ ] Given the existing settings tests, when `tests/test_config.py` runs, then every pre-existing assertion passes unchanged except any that asserted `OPENROUTER_API_KEY` is a required field, which carries a comment citing PRD-020 D1.
- [ ] Given `PROVIDERS_FILE` set, when `Settings()` is built, then the file is not opened or parsed (parsing is STORY-003).

## Technical Notes

- `OPENROUTER_API_KEY: str` is a required field at `app/config.py:180`; make it `str = ""` and add a `@model_validator(mode="after")` (the shape of `_validate_v1_tool_models`, `app/config.py:745-770`). Add `PROVIDERS_FILE: str = ""` next to the other file settings (`PATTERNS_FILE`, `ACTION_POLICY_FILE`).
- `model_config` has `hide_input_in_errors=True` (`app/config.py:176-178`): keep error text to setting names, never values. The "key_env names it" half of the requirement is enforced by STORY-003, which resolves the variable (OD4).
- `V1_TOOL_MODELS` is parsed by `v1_tool_models_list` (`app/config.py:816-818`); its existing validator requires every entry in `MODEL_ALLOWLIST`, so the new D6 check must run first or independently so the message names `PROVIDERS_FILE`.
- `tests/conftest.py:92` sets `OPENROUTER_API_KEY` by `os.environ.setdefault`, so the suite never sees the empty default; build `Settings(_env_file=None, ...)` in the new tests as `tests/test_config.py` does.
- Orchestrator decision (stories): PRD open decisions O1-O8 are adopted as proposed.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-003

## PRD Reference

Source: [`PRD-020/PRD.md`](../../PRDs/PRD-020-provider-registry/PRD.md) — Sections 4 (Settings), 9.3; decisions D1, D6
