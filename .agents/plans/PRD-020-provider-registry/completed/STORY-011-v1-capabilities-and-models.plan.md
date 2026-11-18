---
story: STORY-011
prd: PRD-020
slug: v1-capabilities-and-models
title: /v1 tool capability from the registry and per-role GET /v1/models
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-18
---

# Plan: /v1 tool capability from the registry and per-role GET /v1/models

## Summary

The router decides the tool-capability rule per request and passes it to the settings-free translator; `GET /v1/models*` branch on the registry mode. Legacy paths keep today's code and bytes. File mode uses `provider_registry.supports_tools` / `visible_models`.

- Story: `.agents/stories/PRD-020-provider-registry/STORY-011-v1-capabilities-and-models.md`
- PRD sections used: Section 4 (Ingresses), F4, Section 10, D6, D14, T3
- Systems affected: `app/routers/v1.py`, `app/services/v1_translate.py`, `app/models/v1_schemas.py`

## Design Decisions

- **Mode accessor**: none to add. `Registry.is_legacy` exists (`provider_registry.py:136`; True only from `_build_legacy`, `:573`), so `provider_registry.current().is_legacy` is exactly `_snapshot is None`. The router uses it and never reads `settings.PROVIDERS_FILE`. No new `is_file_mode()`.
- **Translator signature**: add `tools_supported: Optional[bool] = None` after `tool_models` (`v1_translate.py:495`). `None` = legacy: today's `tool_models` list rule and `_TOOL_MODEL_RULE` (`:168`). Non-None = file mode: refuse when `False`, with new constant `_TOOL_CAPABILITY_RULE = "model is not enabled for tool calling"`. Same `V1RequestError(TOOLS_NOT_SUPPORTED, rule, "tools")`, same spot (`:531-532`). No settings or registry import.
- **Order kept**: with the flag on, `translate_request` runs: rejected keys (minus tool params) -> `_tool_params` -> model/capability check (only when `tools is not None`) -> forwarded keys -> stream_options -> messages. "Model not allowed" is not in the translator: it is `authorize_route` in the pipeline, after translation. So today `tools_not_supported` pre-empts model-not-allowed for a tools request; keep it (the new check is on the same line, same position).
- **Router** (`v1.py:353-358`): `file_mode = not provider_registry.current().is_legacy`; pass `tool_models=() if file_mode else settings.v1_tool_models_list` and `tools_supported=<per the T3 bullet below> if file_mode else None`. Read per request (OD1). `tools_enabled=settings.V1_TOOLS_ENABLED` untouched: flag off takes the `else: _check_rejected` branch (`v1_translate.py:533-534`) and never reaches the check, so flag-off is unchanged in both modes.
- **`harness` key absent in legacy**: `ModelCapabilities` (`tools/streaming/reasoning: bool`, `max_context_tokens: Optional[int]`), `ModelHarness` (`provider: str`, `capabilities`), `ModelEntry.harness: Optional[ModelHarness] = None`, plus a `@model_serializer(mode="wrap")` on `ModelEntry` that pops `harness` when None: the pattern of `_drop_absent_usage` (`v1_schemas.py:271-276`). NOT `exclude_none`/`exclude_unset` on the dump: `exclude_none` also drops `max_context_tokens: null`, which the spec keeps. Key order stays `id, object, created, owned_by[, harness]`. Confirm against `tests/fixtures/prd020_legacy/v1/*.json` (fixture list body: entries are exactly `id, object, created, owned_by`) via `tests/test_prd020_legacy_fixtures.py:477` and unchanged `tests/test_v1_models.py`.
- **List, file mode**: `visible_models(identity)` in registry order; entry `owned_by=m.provider_name`, `harness.provider=m.provider_name`, capabilities from `m.capabilities`. Passthrough never listed (`visible_models` walks `provider.models` only). Legacy: the current `settings.model_allowlist_list` path, untouched (keeps duplicates, per the story note); do not route legacy through the registry.
- **Retrieve, file mode**: found iff `model_id` is in `visible_models(identity)`; otherwise one shared 404 branch: `_error(404, "invalid_request_error", MODEL_NOT_FOUND, "model not found")` (proposed mode-neutral text), same log line (no id). Uncatalogued, catalogued-but-not-visible and passthrough ids all take that branch, so bodies are equal by construction (T3). Legacy message `model is not in MODEL_ALLOWLIST` unchanged.
- **T3 resolved (orchestrator decision)**: the file-mode tool decision is made only for a model the caller may use. Router: `try: route = authz.authorize_route(identity, body.model)` -> `tools_supported = route.capabilities.tools`; `except PermissionDenied: tools_supported = True` (defer: the pipeline's step-2 `authorize_route` then gives its one uniform denial). `authorize_route` is pure (no log, no I/O; `authz.py:208-227`). So an uncatalogued, a forbidden and a passthrough-not-allowed id all get the same pipeline verdict, and a forbidden model's `tools` flag never leaks. Tests in `test_v1_tools_registry.py`: (a) tools request to an uncatalogued id and to a catalogued role-forbidden `tools: true` id and a role-forbidden `tools: false` id give byte-equal bodies (status, code, message); (b) an allowed `tools: false` id gives `400 tools_not_supported`, message `model is not enabled for tool calling`.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Serializer | `app/models/v1_schemas.py:271-276` | wrap serializer dropping an absent key |
| Error | `app/routers/v1.py:191-205`, `:476-479` | `_error(404, ..., MODEL_NOT_FOUND, msg)`; log has no id |
| Translator test | `tests/test_v1_tools.py:358-370` | `TOOLS_NOT_SUPPORTED` + param `tools` assertion |
| Models test | `tests/test_v1_models.py:58-100` | `temp_db` + user fixture, `client`, `_assert_response` |
| File mode | `tests/_providers.py` (`provider_file`) | YAML under tmp_path, reset on teardown |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/v1_translate.py` | UPDATE | `tools_supported`, `_TOOL_CAPABILITY_RULE`, docstring (cite PRD-020 D6) |
| `app/models/v1_schemas.py` | UPDATE | `ModelCapabilities`, `ModelHarness`, `ModelEntry.harness` + serializer |
| `app/routers/v1.py` | UPDATE | import `provider_registry`; chat_completions decision; list/retrieve file-mode branches; `_registry_entry` |
| `tests/test_v1_models_registry.py` | CREATE | file-mode list/retrieve + T3 |
| `tests/test_v1_tools_registry.py` | CREATE | file-mode tools check, translator unit cases, flag off |

## Tasks

### Task 1: Translator
- **File**: `app/services/v1_translate.py` (`:168`, `:495`, `:531`)
- **Implement**: as above; defaults keep every existing call working; keep the module pure (purity tests).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_v1_translate_request.py tests/test_v1_tools.py`

### Task 2: Schema
- **File**: `app/models/v1_schemas.py:279-285`
- **Implement**: models + serializer; `harness` absent when None, `max_context_tokens` null kept.
- **Validate**: `tests/test_v1_schemas.py tests/test_v1_models.py`

### Task 3: Router
- **File**: `app/routers/v1.py:353-358, 420-479`
- **Implement**: per Design Decisions; legacy branch bytes unchanged. Import `provider_registry` from `app.services`.
- **Validate**: `tests/test_v1_router.py tests/test_prd020_legacy_fixtures.py -k v1`

### Task 4: Tests (no existing test renamed; `_DELIBERATELY_SUPERSEDED_TESTS` untouched)
- **`tests/test_v1_models_registry.py`** (YAML: two providers, one passthrough, one admin-only model, one model without `max_context_tokens`): user list = visible only, order, `owned_by`, full `harness` shape incl. `max_context_tokens: null`; passthrough not listed; admin sees every catalogued; no audit rows; retrieve 200 for a visible id; 404 for uncatalogued, role-forbidden catalogued and passthrough ids with the three `response.content` byte-equal (T3), message `model not found`, `x-should-retry: false`; break-glass still refused; legacy list has no `harness` key.
- **`tests/test_v1_tools_registry.py`**: file mode, `V1_TOOLS_ENABLED=True`, stub upstream like `test_v1_tools.py:718-745`: `tools: false` model -> 400 `tools_not_supported`, `param: "tools"`, message exactly `model is not enabled for tool calling`; `tools: true` passes; passthrough id uses `passthrough_capabilities`; translator-level `tools_supported` True/False/None (None + list keeps the `(V1_TOOL_MODELS)` message; check follows rejected keys); legacy message unchanged through the router; **flag off in file mode**: tools request refused as `test_v1_tools.py:669` (PRD-015 exactly), `tools_supported=False` ignored.

## End-to-End Tests

- [ ] `TestClient(app)`, file mode: GET /v1/models as `user` and `admin`; GET /v1/models/{id} for the three 404 cases.
- [ ] POST /v1/chat/completions with `tools`, file mode and legacy (legacy keeps the suffix).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_v1_models_registry.py tests/test_v1_tools_registry.py tests/test_v1_models.py tests/test_v1_tools.py tests/test_v1_translate_request.py tests/test_v1_schemas.py tests/test_v1_router.py tests/test_prd020_legacy_fixtures.py tests/test_untouched_app.py
```

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 file-mode refusal, legacy message | 1, 3 | `test_v1_tools_registry.py` router cases; existing `test_v1_tools.py:365` |
| AC2 per-role list with `harness` | 2, 3 | `test_v1_models_registry.py::test_list_*` |
| AC3 legacy byte-identical | 2, 3 | `test_prd020_legacy_fixtures.py::test_v1_models_bodies_match_recorded`; unchanged `test_v1_models.py` |
| AC4 identical 404 | 3 | `test_v1_models_registry.py::test_retrieve_404_bodies_are_byte_equal` |
| AC5 flag off unchanged | 3 | `test_v1_tools_registry.py::test_flag_off_in_file_mode` |
