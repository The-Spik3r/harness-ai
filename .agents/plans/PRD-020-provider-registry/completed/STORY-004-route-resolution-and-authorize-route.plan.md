---
story: STORY-004
prd: PRD-020
slug: route-resolution-and-authorize-route
title: Route resolution, visible models and authorize_route
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-18
---

# Plan: Route resolution, visible models and authorize_route

## Summary

Add the routing contract to `provider_registry.py` (`Route`, `resolve`, `visible_models`, `supports_tools`) and `authorize_route` to `authz.py`; re-implement `authorize_model` as `authorize_route(...)` discarding the result. All of it is pure over `current()`, so legacy mode (live settings, implicit `openrouter` provider with passthrough) reproduces today's verdicts exactly. No pipeline, /v1 or chat UI change.

- Story: `.agents/stories/PRD-020-provider-registry/STORY-004-route-resolution-and-authorize-route.md` (AC text lives there)
- PRD sections used: 6.3, 6.6 (`relaxes_input`), F2, F4, 9.2 T3, 10 "Internal API", D3, D4, O1
- Systems affected: `app/services/provider_registry.py`, `app/services/authz.py`; tests only otherwise

## Design Decisions (binding, from the orchestrator)

1. `Route` frozen dataclass: `model_id, upstream_model, provider: Provider, capabilities: Capabilities, catalogued: bool, model: Optional[CatalogModel]`. `relaxes_input()` = `settings.PII_REDACTION_ENABLED and provider.trust == "internal" and provider.pii == "relaxed"`, setting read at call time. No key field (T1); `api_key_for(route.provider)` stays the only key path.
2. `resolve(model) -> Optional[Route]`: `reg = current()`; `reg.models_by_id.get(model)` -> catalogued (`upstream_model=m.upstream`, `capabilities=m.capabilities`, `provider` = the provider whose `name == m.provider_name`); else `reg.passthrough_provider` -> uncatalogued (`upstream_model=model` verbatim, `passthrough_capabilities`, `model=None`); else `None`. Exact, case-sensitive, no prefix parsing, no string surgery. No I/O.
3. `authz.authorize_route(identity, model) -> Route`: `resolve` None -> `PermissionDenied(f"query:model:{model}")` even with RBAC off. RBAC off -> route. Role in `MODEL_ALLOWLIST_WILDCARD_ROLES` -> route (O1). Uncatalogued + non-wildcard -> deny (OD3). Catalogued: effective roles = `model.roles` else `provider.roles` else every role; role outside -> deny. All denials byte-identical text (T3). `authorize_model` keeps signature and `None` return, body = `authorize_route(identity, model)`.
4. `visible_models(identity) -> list[CatalogModel]`: registry order (iterate `reg.providers`, then `provider.models`), catalogued only; RBAC off or wildcard role -> all; else the same role rule as 3. `supports_tools(model) -> bool`: `route.capabilities.tools`, False when unresolved. `/v1` is not rewired (STORY-011).

Implementation notes (code reality):
- **Circular import**: `provider_registry.py:39` imports `authz` at top (`authz.ROLE_PERMISSIONS`, used `:266`). So `authz` must NOT import `provider_registry` at module level: import it inside `authorize_route` (comment: provider_registry imports authz). Annotate the return as a string / `TYPE_CHECKING` import.
- **One role rule, two callers**: add to `authz.py` `role_may_use(role, model: Optional[CatalogModel], provider) -> bool` (pure: effective roles `model.roles` -> `provider.roles` -> every role) and `sees_every_model(identity) -> bool` (`not RBAC_ENABLED or role in MODEL_ALLOWLIST_WILDCARD_ROLES`). `authorize_route` and `visible_models` both use them, so they cannot drift. Implement these first (Task 1), then the registry functions.
- Catalogued route's provider: `Registry` has no name index; scan `reg.providers` by `name == m.provider_name` inside `resolve`. Do not add a field to `Registry` (STORY-003's frozen shape).
- Legacy equivalence reasoning: catalogue = `MODEL_ALLOWLIST` items with `roles=None`, provider `roles=None` -> every role; non-allowlisted -> passthrough -> non-wildcard denied, admin allowed; RBAC off -> allowed (passthrough always resolves in legacy). An unknown role on an allowlisted model is allowed in old and new code alike (old code never checked a role matrix there).
- `supports_tools` legacy: catalogued `tools = not V1_TOOL_MODELS or id in it`, passthrough `tools = not V1_TOOL_MODELS` (`provider_registry.py:513-540`) equals the `v1_translate.py:529` rule for every state the Settings validator allows (`config.py:805-811`: each tool model must be in the allowlist). Only a monkeypatched, validator-bypassing "in V1_TOOL_MODELS but not in MODEL_ALLOWLIST" state differs; do not test it, mention it in the report.

## Skills In Use

`.agents/skills/` holds only `frontend-design` (no UI here). None apply.

## Patterns to Follow

| Category | Source | What to mirror |
|---|---|---|
| Frozen dataclasses + docstring citing PRD ids | `provider_registry.py:87-141` | `Route` style, field order as the design point |
| Public API section | `provider_registry.py:566-628` (`load/current/api_key_for/reset`) | add `resolve`, `visible_models`, `supports_tools` after `api_key_for`; update the module docstring lines 15-17 ("Resolution ... is STORY-004") |
| Denial text | `authz.py:203` | reuse `PermissionDenied(f"query:model:{model}")` verbatim for every denial |
| Docstring | `authz.py:188-195` | extend `authorize_model` docstring: delegates (PRD-020 D3, D4) |
| Identity in tests | `tests/test_authz.py:57` `Identity(user_id="u", role=role)` | build identities this way |
| File-mode tests | `tests/_providers.py:50-63` `provider_file(yaml, env=None)`; YAML shape `tests/test_provider_registry.py:15-66` | fixture + imports `from tests._providers import provider_file  # noqa: F401` |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `app/services/authz.py` | UPDATE | `role_may_use`, `sees_every_model`, `authorize_route`; `authorize_model` delegates |
| `app/services/provider_registry.py` | UPDATE | `Route`, `resolve`, `visible_models`, `supports_tools`; docstring |
| `tests/test_provider_routing.py` | CREATE | all new tests (file mode via `provider_file`, legacy via monkeypatch) |

`tests/test_authz.py`, `tests/test_rbac.py` stay unchanged and must pass as-is (they prove legacy through the delegating `authorize_model`).

## Tasks

### Task 1: authz helpers, authorize_route, authorize_model delegation
- **File**: `app/services/authz.py`
- **Implement**: helpers above; `authorize_route` order: resolve -> None deny; RBAC off return; wildcard return; not catalogued deny; `role_may_use` else deny. Delegate `authorize_model`.
- **Mirror**: `authz.py:188-203`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_authz.py tests/test_rbac.py` (after Task 2, since resolve must exist)

### Task 2: Route, resolve, supports_tools, visible_models
- **File**: `app/services/provider_registry.py`
- **Implement**: design points 1, 2, 4. `Route.relaxes_input` reads `settings.PII_REDACTION_ENABLED` per call.
- **Mirror**: `provider_registry.py:87-141`, `:602-628`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"` (catches a circular import)

### Task 3: Tests
- **File**: `tests/test_provider_routing.py` (docstring "PRD-020 STORY-004: ..."). File-mode registry: two providers (`openrouter` passthrough with varied model/provider roles, and `ollama` with `trust: internal`, `pii: relaxed`, `roles: [admin, user]`), ids `openai/gpt-4o`, `ollama/qwen2.5-coder:7b`, one model whose `upstream` differs from its id, one provider literally named `openai`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_provider_routing.py`

## End-to-End Tests

- [ ] `tests/test_authz.py` and `tests/test_rbac.py` unchanged and green (legacy through the pipeline's `authorize_model`, including the HTTP `/query` BLOCKED `query:model:<m>` verdicts).
- No `chat_ui/` change.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_provider_routing.py tests/test_provider_registry.py tests/test_authz.py tests/test_rbac.py tests/test_untouched_app.py tests/test_query_pipeline_break_glass.py tests/test_chat_outcomes_regression.py
```
No test is renamed or removed, so the redaction-integration guard is not needed.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|---|---|---|
| AC1 resolve exact / passthrough / None; no prefix parsing | 2 | `test_resolve_catalogued` (incl. upstream differing from id), `test_resolve_passthrough_keeps_id_as_sent`, `test_resolve_none_without_passthrough`, `test_resolve_no_prefix_parsing` (provider `openai` exists; `openai/other` goes to passthrough; `OPENAI/GPT-4O` case miss), `test_route_frozen_and_holds_no_key` |
| AC2 effective roles model > provider > every; same exception for unknown | 1 | `test_effective_roles_matrix` (parametrized), `test_unknown_and_forbidden_are_indistinguishable` (equal `.permission` and `str(exc)`) |
| AC3 wildcard reaches excluded + uncatalogued; non-wildcard denied on passthrough (OD3) | 1 | `test_admin_wildcard_any_model`, `test_passthrough_denied_to_non_wildcard`, `test_wildcard_roles_setting_patch` (patch `MODEL_ALLOWLIST_WILDCARD_ROLES`) |
| AC4 RBAC off: unresolvable denied, resolvable returns route | 1 | `test_rbac_off_unresolvable_denied`, `test_rbac_off_returns_route_without_role_check` |
| AC5 `relaxes_input`, `visible_models`, `supports_tools`, no I/O | 2 | `test_relaxes_input_truth_table` (PII_REDACTION_ENABLED x trust x pii; flips on monkeypatch after Route built), `test_visible_models_order_and_filter` (registry order, passthrough absent, RBAC off / admin see all), `test_supports_tools_file_mode` (catalogued, passthrough caps, unresolved False), `test_pure_no_io` (patch `builtins.open` and `socket.socket.connect` to raise) |
| Legacy equivalence (binding) | 1 | `test_legacy_authorize_model_equivalence`: roles (admin, user, auditor, unknown) x RBAC on/off x allowlisted / non-allowlisted / empty allowlist; compared to an inline copy of the OLD body, same outcome and message |
| Legacy `supports_tools` == `/v1` rule | 2 | `test_legacy_supports_tools_matches_v1_rule`: V1_TOOL_MODELS empty and `"a"` with allowlist `a,b`; ids a, b, `zzz` (passthrough); reference `not tools_list or model in tools_list` |
| `authorize_model` signature / None return | 1 | `test_authorize_model_returns_none` + unchanged `test_authz.py`, `test_rbac.py` |

Also: no key in any repr (`repr(route)` with `OPENROUTER_API_KEY` set to a sentinel), all tasks done, validation passes.
