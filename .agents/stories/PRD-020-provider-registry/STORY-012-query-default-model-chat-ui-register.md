---
id: STORY-012
prd: PRD-020
slug: query-default-model-chat-ui-register
title: /query default model, chat UI model selector and Register provider column
type: feature
priority: medium
complexity: medium
phase: "3 - Policies that depend on the provider"
status: done
labels: [backend, frontend, chat-ui]
epic_branch: epic/PRD-020-provider-registry
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-012-query-default-model-chat-ui-register.plan.md
report: .agents/reports/PRD-020-provider-registry/STORY-012-query-default-model-chat-ui-register.report.md
commit: 9dba70d
depends_on: [STORY-007, STORY-004]
blocks: [STORY-015]
skills: [frontend-design]
created: 2026-11-18
updated: 2026-11-18
---

# STORY-012: /query default model, chat UI model selector and Register provider column

## Description

As a chat user, I want the model selector to list the models my role may use, including local ones, and as an admin I want the Register to show which provider answered each row, so that the UI matches what the registry will actually route.

## Acceptance Criteria

- [x] Given file mode, when `/query` is called without `model`, then `QueryRequest.model` defaults to the registry `default_model`; in legacy mode it stays `"gpt-4"` and the STORY-001 fixtures pass.
- [x] Given file mode, when the chat UI loads for a role, then the selector lists exactly `visible_models(identity)` and the initial selection is `default_model` when visible to that role (else the first visible); in legacy mode it lists `chat_ui/chat_ui/config.py`'s `MODEL_ALLOWLIST` and `DEFAULT_MODEL` unchanged.
- [x] Given the admin Register, when a row has a provider, then the row shows it (long provider names truncate without wrapping, as `model_used` does), and a row without one (denials, pre-PRD-020 rows) shows the existing empty-cell treatment.
- [x] Given the existing chat and admin copy/contrast/render tests, when run, then they pass unchanged, and the new strings live in `copy.py` / `admin_copy.py` (no inline literals).
- [x] Given a keyboard user, when tabbing to the selector, then focus is visible and the control remains operable at phone width.

## Technical Notes

- `QueryRequest.model: str = "gpt-4"` at `app/models/schemas.py:18`; the request is consumed in `app/routers/query.py:184` (`model=request.model`). Make the field optional and resolve the default in the router so the pipeline always receives a concrete model.
- Chat UI: allowlist and default in `chat_ui/chat_ui/config.py:1-8`; state `selected_model: str = DEFAULT_MODEL` at `chat_ui/chat_ui/state.py:216`, setter `:313`, send reads `self.selected_model` at `:1050`; selector component `chat_ui/chat_ui/components/shell.py:98-111` (`rx.select(MODEL_ALLOWLIST, ...)`, id `model-selector`).
- Register: row cells `chat_ui/chat_ui/components/register.py:536` (`_cell(row.model_used)`), truncation note `:164`; the audit read API field (`provider`) is provided by STORY-006; model/formatting in `chat_ui/chat_ui/admin_models.py`, `admin_formatting.py`, `admin_copy.py`.
- Skill `frontend-design` (`.agents/skills/frontend-design/SKILL.md`) applies to the selector and the Register field only. Rules to follow, verbatim:
  - "Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built."
  - "Treat failure and emptiness as moments for direction, not mood. Explain what went wrong and how to fix it, in the interface's voice rather than a person's."
  - "Build to a quality floor without announcing it: responsive down to mobile, visible keyboard focus, reduced motion respected."
  - "Match complexity to the vision. Maximalist directions need elaborate execution; minimal directions need precision in spacing, type, and detail."
- These are additive controls in an existing, themed UI (`chat_ui/chat_ui/theme.py`): reuse the shell's tokens and `_cell` styles; do not introduce a new visual direction. Existing guards: `tests/test_chat_shell.py`, `tests/test_register.py`, `tests/test_contrast.py`, `tests/test_render_invariants.py`.
- Orchestrator decision (stories): legacy mode reads settings LIVE. The suite monkeypatches `settings.MODEL_ALLOWLIST`, `V1_TOOL_MODELS` and `OPENROUTER_*` per test (~53 references). The immutable snapshot exists only in file mode; in legacy mode the accessors derive the implicit provider from the current settings on each call (memoizing on those settings values is allowed).

## Dependencies

- **Blocked by**: STORY-007, STORY-004
- **Blocks**: STORY-015

## PRD Reference

Source: [`PRD-020/PRD.md`](../../PRDs/PRD-020-provider-registry/PRD.md) — Sections 4 (Ingresses), 5 (stories 6, 7), 10; decisions D15
