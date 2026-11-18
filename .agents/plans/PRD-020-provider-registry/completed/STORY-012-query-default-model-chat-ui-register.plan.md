---
story: STORY-012
prd: PRD-020
slug: query-default-model-chat-ui-register
title: /query default model, chat UI model selector and Register provider column
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-18
---

# Plan: /query default model, chat UI model selector and Register provider column

## Summary

Three small, independent edits. (1) `QueryRequest.model` becomes `Optional[str] = None`; `query.py` resolves `None` to the registry default (file mode) or a named legacy constant `"gpt-4"`. (2) The chat selector reads a per-session `model_options` state var that `ChatState.login` fills from `visible_models(identity)` (file mode) or `config.MODEL_ALLOWLIST` (legacy); an empty list shows a direction sentence. (3) The Register gains a provider head and cell after Model, fed by a new `AuditRow.provider`.

- Story: `.agents/stories/PRD-020-provider-registry/STORY-012-query-default-model-chat-ui-register.md`
- PRD sections used: section 4 (Ingresses), section 10 (`POST /query`), D13, D15
- Systems affected: `/query` router and schema, chat UI state/shell/register/copy, admin read model

## Design Decisions (binding, from the orchestrator)

- `/query`: `QueryRequest.model: Optional[str] = None`. The router resolves `None` to `provider_registry.current().default_model` when `not reg.is_legacy`, else to `"gpt-4"` held in ONE named constant. An explicit model is never overridden (an explicit JSON `null` gets the default). The pipeline still authorizes whatever results; `run_query` always receives a concrete str.
- Selector options are a per-session state var computed in `login` for the signed-in identity, never at import. The send path is unchanged (`self.selected_model`, `state.py:1050`); no UI-side authorization.
- Legacy: `model_options` stays `list(MODEL_ALLOWLIST)` and `selected_model` is left alone, exactly as today.
- App files touched: only `schemas.py` and `query.py`, so `tests/test_untouched_app.py` runs.

**Hook point (verified).** There is no `on_load` for signed-in state: `login()` is "the page load for a signed-in user" (`state.py:355-360`; `_token` is a backend var, so a refresh signs out). Hook right after `self.user_id = identity.user_id` (`state.py:352`), where `identity` is in hand. `visible_models` is pure (`provider_registry.py:675`), so it is called inline.

**Rule in login** (new module-level pure helper `_model_choices(identity) -> tuple[list[str], Optional[str]]` in `state.py`):
- `reg = provider_registry.current()`; `reg.is_legacy` -> `(list(MODEL_ALLOWLIST), None)`, meaning do not touch `selected_model`.
- File mode: `ids = [m.id for m in visible_models(identity)]`; initial = `reg.default_model` if in `ids`, else `ids[0]`, else `""`. Login always assigns it in file mode (the import-time value is `config.DEFAULT_MODEL`, which may be visible without being the registry default).
- `logout()` keeps `selected_model` (existing `test_chat_state_model_selection` AC5) and resets `model_options` to `[]`; the next login recomputes.
- Empty list: `selected_model = ""` and the shell shows `copy.SHELL_MODEL_NONE_NOTICE` instead of the select. A send with `""` reaches the pipeline, which denies `query:model:` (T3). Nothing UI-side.

## Skills In Use

| Skill | Why it applies | Tasks |
|-------|---------------|-------|
| frontend-design (`.agents/skills/frontend-design/SKILL.md`, read in full) | Selector and Register cell only. "Write from the end user's side": the head says "Provider", never adapter/route. "Failure and emptiness are moments for direction, not mood": the empty-selector copy says what to do. "Quality floor": visible focus (global `:focus-visible`, `theme.py:289`) and phone width. Additive and themed: no new visual direction, reuse `_label`, `_cell` and tokens | 3, 4 |

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Router default | `app/routers/query.py:179-190` | `model=request.model` is the only consumer; resolve just above `return run_query(` |
| Legacy constant | `app/services/provider_registry.py:569` has a bare `"gpt-4"` literal | `_LEGACY_DEFAULT_MODEL = "gpt-4"` in `query.py`, comment "PRD-020 D15"; do not touch the registry module |
| State var | `chat_ui/chat_ui/state.py:216`, setter `:313` | `model_options: list[str] = list(MODEL_ALLOWLIST)` beside `selected_model`; import `provider_registry` as `chat_ui.py:22` does |
| Selector | `components/shell.py:98-111` | `rx.select(ChatState.model_options, ...)` (accepts a Var list), keep `id="model-selector"` and every prop; `rx.cond(ChatState.model_options.length() > 0, select, notice)`; drop the `MODEL_ALLOWLIST` import (`:49`) |
| Copy | `chat_ui/chat_ui/copy.py:56` | `SHELL_MODEL_NONE_NOTICE` below `SHELL_MODEL_SLOT_LABEL`; notice in the data face, `color=theme.MUTE`, wrapping (not widening the masthead) at phone width |
| Register cell | `components/register.py:536` `_cell(row.model_used)`; `_cell` `:161-178` | `_cell(row.provider)` right after it. Empty provider: `provider=_text(log.provider)` gives `VALUE_ABSENT`, the same treatment as `model_used` (`admin_formatting.py:325`, test `test_admin_formatting.py:257`) |
| Head / grid | `register.py:597-608`, `_GRID` `:93`, `_MIN_WIDTH` `:102` | head after Model; one more track `7rem` after the `9rem` one (11 tracks); `_MIN_WIDTH` `63.75rem` -> `71.5rem` (7rem + 0.75rem gap); update the comments that count columns |
| Tests | `tests/test_chat_state.py:806-830`, `tests/test_admin_formatting.py:40-58` (`make_log`), `tests/_providers.py` (`providers_file`) | file mode through `providers_file`; legacy with live settings |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/schemas.py` | UPDATE | `model: Optional[str] = None` (line 18), comment citing D15 |
| `app/routers/query.py` | UPDATE | resolve the default above `run_query` (`:184`); import `provider_registry` |
| `chat_ui/chat_ui/state.py` | UPDATE | `model_options`, `_model_choices`, login hook after `:352`, logout reset |
| `chat_ui/chat_ui/components/shell.py` | UPDATE | selector from `model_options` plus empty notice; docstring |
| `chat_ui/chat_ui/copy.py` | UPDATE | `SHELL_MODEL_NONE_NOTICE`, e.g. "No models are enabled for your role. Ask an administrator to grant access." |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | `COLUMN_PROVIDER = "Provider"` beside `COLUMN_MODEL` (`:96`) |
| `chat_ui/chat_ui/admin_models.py` | UPDATE | `provider: str = ""` after `model_used` (`:44`). Not present today |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | `provider=_text(log.provider)` in `to_audit_row` (after `:325`). `AuditLog.provider` (db/models.py) and `AuditQueryEntry.provider` (`schemas.py:275`) already exist from STORY-006: no backend change |
| `chat_ui/chat_ui/components/register.py` | UPDATE | head, cell, `_GRID`, `_MIN_WIDTH`, counts in docstrings |
| `tests/test_query_router.py`, `test_chat_state.py`, `test_admin_formatting.py`, `test_register.py` | UPDATE | new tests appended |
| `tests/test_schemas.py`, `test_admin_models.py`, `test_register.py`, `test_copy.py` | UPDATE | the existing assertions listed below |

## Existing assertions that must change (each gets a "PRD-020 STORY-012" comment)

1. `tests/test_schemas.py:27` `request.model == "gpt-4"` -> `is None`: the schema no longer carries the default, the router does. Alternative the orchestrator may prefer: keep `model: str = "gpt-4"` and detect "unset" with `request.model_fields_set`; that leaves this test and the OpenAPI default untouched but departs from the binding `Optional[str] = None`. This plan follows the binding design.
2. `tests/test_admin_models.py:21` `AUDIT_ROW_FIELDS` is an equality set (an extra field fails on purpose): add `"provider"`. `test_audit_row_constructs_with_no_arguments` (`:93`) lists default-empty fields: add `"provider"`.
3. `tests/test_register.py:767-781` `test_the_row_gains_no_column` asserts ten grid tracks: becomes eleven, with a comment that STORY-012 adds the provider column, superseding PRD-013 F15's "no growth" for this one column. Its row-line field loop stays.
4. `tests/test_copy.py` pinned censuses (admin_copy block near `:515-580`, and the chat `copy.py` one): append `COLUMN_PROVIDER` and `SHELL_MODEL_NONE_NOTICE` in a new labelled block; nothing reordered.
5. NOT edited: the `COLUMN_HEADS` / `COPY_NAMES` tuples (`test_register.py:62,174`); a new test covers the new head (rendered in the probe, reaches the screen via `admin_copy.`, no literal).
6. Expected to pass unchanged: `test_chat_shell.py` (only `id:"model-selector"` in the header, `:306`), `test_contrast.py`, `test_render_invariants.py`, `test_chat_state.py:806-820` (config list contains the default; selection survives logout).
7. OpenAPI: no test pins the `/query` body default (`grep openapi tests`: only `test_v1_tools.py:1382`, a different schema, and Caddy route lists). The `model` property turns into `anyOf [string, null]` with default null in both modes. Report it. STORY-001 fixtures: `query/default_model.json` sends no model and still gets `model_used: "gpt-4"`; run `tests/test_prd020_legacy_fixtures.py` unedited.

## Tasks

### Task 1: /query default
- **Files**: `app/models/schemas.py:18`, `app/routers/query.py` (after the foreign-session 403 block, before `return run_query(`).
- **Implement**: `model = request.model`; if `None`, `reg = provider_registry.current()` and use `_LEGACY_DEFAULT_MODEL if reg.is_legacy else reg.default_model`; pass `model=model`. Grep first that nothing else in the router reads `request.model`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_query_router.py tests/test_schemas.py tests/test_prd020_legacy_fixtures.py tests/test_untouched_app.py`

### Task 2: chat state
- **File**: `chat_ui/chat_ui/state.py` (`:51`, `:216`, `:352`, `logout` `:417`). Add var, helper, login assignment, logout reset. `set_selected_model` unchanged.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_chat_state.py -k "model or login or logout"`

### Task 3: selector and copy
- **Files**: `components/shell.py:98-111`, `copy.py:56`. Confirm no rule overrides the global `:focus-visible` for `#model-selector`; the notice must wrap, never widen the masthead.
- **Validate**: `... pytest -q -p no:cacheprovider tests/test_chat_shell.py tests/test_contrast.py tests/test_render_invariants.py tests/test_copy.py`

### Task 4: Register provider
- **Files**: `admin_models.py`, `admin_formatting.py`, `admin_copy.py`, `register.py`.
- **Validate**: `... pytest -q -p no:cacheprovider tests/test_register.py tests/test_admin_models.py tests/test_admin_formatting.py tests/test_admin_copy.py tests/test_admin_state.py`

### Task 5: tests and guards
- Write the tests listed below and the assertion changes above; then run `tests/test_chat_ui_startup_guard.py` and the app-import check.

## End-to-End Tests

- [ ] `TestClient(app)`, file mode via `providers_file`: POST `/query` with no `model` reaches the stub as the registry `default_model`; explicit `model` wins; `"model": null` gets the default.
- [ ] Legacy: no `model` gives `gpt-4`; fixture test passes unedited. A role not allowed the file default gets the pipeline's `query:model:<default>` denial (pipeline stays the authority).
- [ ] Chat state: login as `user` and as `admin` in file mode gives `model_options == [m.id for m in visible_models(identity)]`; `selected_model` is `default_model` when visible, else the first; a role with no models gives `[]`, `""` and the notice in the rendered header; legacy gives `MODEL_ALLOWLIST` and an untouched `selected_model`; logout keeps the model and clears the options; nothing registry-derived exists before login.
- [ ] Register: `to_audit_row(make_log(provider="ollama"))` gives `"ollama"`; `provider=None` gives `VALUE_ABSENT`; head and cell are in the probe; source assert that the cell is `_cell(` with no wrap override (truncation inherited); structural asserts for the quality floor (global focus rule, `_MIN_WIDTH`, `overflow_x="auto"`). A live browser pass is optional.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_query_router.py tests/test_schemas.py tests/test_prd020_legacy_fixtures.py tests/test_untouched_app.py tests/test_admin_models.py tests/test_admin_formatting.py tests/test_admin_copy.py tests/test_admin_state.py tests/test_register.py tests/test_chat_shell.py tests/test_contrast.py tests/test_render_invariants.py tests/test_copy.py tests/test_chat_ui_startup_guard.py
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_chat_state.py -k "model or login or logout"
```

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 `/query` default | 1 | new in `test_query_router.py`; `test_prd020_legacy_fixtures.py`; `test_schemas.py::test_query_request_defaults` (changed) |
| AC2 selector per role | 2, 3 | new `test_chat_state.py` tests; `test_model_config_allowlist_and_default` unchanged |
| AC3 Register provider and empty cell | 4 | new tests in `test_admin_formatting.py`, `test_register.py` |
| AC4 guards pass, strings in copy | 3, 4 | guard files unchanged except the listed edits; copy census appended |
| AC5 focus and phone width | 3 | structural asserts (global `:focus-visible`, masthead tests) |

## Risks

- Eleven tracks widen the table; it already scrolls in its own container, and `_MIN_WIDTH` is raised to match.
- `visible_models` never lists passthrough ids (PRD section 4), so a wildcard role cannot pick one in the UI; by design.
- An empty list blocks sending until access is granted; the notice is the guidance.
