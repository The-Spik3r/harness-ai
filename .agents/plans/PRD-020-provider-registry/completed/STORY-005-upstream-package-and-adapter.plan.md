---
story: STORY-005
prd: PRD-020
slug: upstream-package-and-adapter
title: Upstream package, OpenAI-compatible adapter and call_upstream
type: REFACTOR
complexity: large
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-18
---

# Plan: Upstream package, OpenAI-compatible adapter and call_upstream

## Summary

Move `openrouter_client.py` into `app/services/upstream/` and parameterize the call by `Provider`. `params.py` takes the params classes unchanged; `types.py` holds `UpstreamError`, `UpstreamResult`, `UpstreamRequest`, `ProviderAdapter`; `openai_compatible.py` holds the wire helpers and `OpenAICompatibleAdapter(provider, client=None).complete(request, api_key)` (today's body, `openrouter_client.py:219-332`); `__init__.py` holds `call_upstream` (resolve, D10 key choice, adapter call). `openrouter_client.py` becomes aliases. App modules import from `app.services.upstream` under their existing names. The stub gains `usage: null`, `auth=yes|no`, a 302 reply, and an optional in-process `require_key`.

- Story: `.agents/stories/PRD-020-provider-registry/STORY-005-upstream-package-and-adapter.md`
- PRD sections used: 6.4, 6.5, F3, F6, T1, T6, T7, D2, D5, D10, D11, D12
- Systems affected: `app/services/` (upstream pkg, query_pipeline, v1_translate), `app/routers/{query,v1}.py`, `scripts/stub_openrouter.py`, tests

## Design Decisions

- **Signature** (binding): `call_upstream(messages, model=_DEFAULT_MODEL, api_key=None, params=None, client=None, *, tools=None) -> UpstreamResult`; `_DEFAULT_MODEL = "gpt-4"` stays (D15 is STORY-012). Order: empty messages -> `UpstreamError("messages must not be empty")` (before resolve, as `:233`); `resolve(model)` None -> non-retryable `UpstreamError("No provider route for the requested model")` (no key, no URL); key choice; adapter.
- **Key (D10, T6)**: `key = api_key if (api_key and provider.byok) else api_key_for(provider)`. Keyless (`provider.key_env is None`): no key at all, no Authorization header, caller key ignored. Keyed and `key is None`: `UpstreamError(f"{label} API key not configured: pass openrouter_api_key or set {key_env}")` when `byok`, else `f"{label} API key not configured: set {key_env}"`. Legacy (label OpenRouter, key_env OPENROUTER_API_KEY, byok) yields exactly STORY-001 `errors.json` `key_missing` ("OpenRouter API key not configured: pass openrouter_api_key or set OPENROUTER_API_KEY"). Non-retryable, no key in text. Done in `call_upstream`, before any client is built.
- **Types, no import cycle**: `UpstreamError`/`UpstreamResult` keep OpenRouterError/OpenRouterResult's exact attributes, fields, defaults and docstrings (`:11-28`, `:202-217`). They live in `upstream/types.py` (deviation from 6.5's file list: `__init__` imports the adapter and the adapter needs the error). `UpstreamRequest` is a frozen dataclass per 6.4 (`messages, upstream_model, params, tools`). `ProviderAdapter` Protocol has `complete` only (STORY-013 adds `stream`/`collect`/events). `__init__` re-exports all of it plus the params names.
- **model_used**: `complete` returns `model_used=request.upstream_model`; `call_upstream` then `dataclasses.replace(result, model_used=model)` so `model_used` stays the requested id (D13: "`model_used` unchanged in meaning"). Identical in legacy. STORY-007 takes the audit `upstream_model` from the route, not from the result.
- **Client**: injected client wins (as `:264`). Else `httpx.Client(timeout=provider.timeout_seconds, follow_redirects=False)`, closed in `finally`. URL `provider.base_url.rstrip("/") + "/chat/completions"` (as `:268`). `httpx.Client` is looked up at call time (tests patch it on the httpx module).
- **Redirects, version-independent**: after `post`, before `raise_for_status`: `if 300 <= resp.status_code < 400:` raise `UpstreamError(f"{label} request failed: unexpected redirect (HTTP {code}); redirects are not followed", upstream_status=code, retryable=False)`. Never include `Location`. Do not rely on `raise_for_status` for 3xx (varies by httpx version; installed is 0.28.1, CI may differ).
- **Labels (T7)**: every `"OpenRouter ..."` string takes `provider.label`: request failed (`:274`), unexpected shape (`:285`, `:312`, and `prefix` in `_parse_tool_calls` `:77`), no text (`:308`). `_parse_tool_calls(raw, label)`; message tails unchanged. `_wire_message`, `_token_count`, `_classify_http_error` move unchanged.
- **No D8 here**: missing or `null` usage still raises the `unexpected response shape` error (`:311-316`).
- **Keys never leak**: `Provider` holds no key; the adapter gets the key only as an argument and puts it only in the headers dict. Headers: `Authorization` (only when a key exists) then `Content-Type`, today's order.

## Skills In Use

None: `.agents/skills/` holds only `frontend-design` (no UI work).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Docstrings | `app/services/openrouter_client.py:11-28` | cite PRD/decision ids; move docstrings verbatim |
| Error shape | `openrouter_client.py:188-199, 270-279` | `_classify_http_error` + `raise ... from exc` |
| Binding rule | `app/routers/v1.py:140-171`, `app/routers/query.py:14,186` | module-level `call_openrouter` name resolved at call time |
| Stub parse | `scripts/stub_openrouter.py:246-261, 295-326, 465-469` | `ScriptError` naming the field; ASCII log, counts only |
| Tests | `tests/test_stub_openrouter.py:77-96, 293-317` | `stub` factory with free port, `_lines`, no-leak assertions |
| File mode | `tests/_providers.py:56-72` | `provider_file(yaml, env=...)`, reset on teardown |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/upstream/__init__.py` | CREATE | `call_upstream`, re-exports |
| `app/services/upstream/types.py` | CREATE | `UpstreamError`, `UpstreamResult`, `UpstreamRequest`, `ProviderAdapter` |
| `app/services/upstream/params.py` | CREATE | `GenerationParams`, `ToolParams`, `UnsupportedParameterError`, moved from `openrouter_client.py:11-117` unchanged (with `_ALLOWED_GENERATION_PARAMS`, `_MAX_STOP_SEQUENCES`) |
| `app/services/upstream/openai_compatible.py` | CREATE | helpers + `OpenAICompatibleAdapter` |
| `app/services/openrouter_client.py` | UPDATE | aliases only: `call_openrouter = call_upstream`, `OpenRouterError = UpstreamError`, `OpenRouterResult = UpstreamResult`, plus the three params names; docstring says deprecated shim |
| `app/routers/query.py:14`, `app/routers/v1.py:61`, `app/services/query_pipeline.py:34-40`, `app/services/v1_translate.py:61-66` | UPDATE | import from `app.services.upstream` with `as` aliases (`UpstreamError as OpenRouterError`, `UpstreamResult as OpenRouterResult`, `call_upstream as call_openrouter`) so every module-level name stays bound |
| `scripts/stub_openrouter.py` | UPDATE | `usage: null`, `auth=`, 302 reply, `require_key` |
| `tests/test_upstream_adapter.py` | CREATE | new tests (Task 5) |
| `tests/test_openrouter_client.py` | UPDATE | lines 172 and 194: kwargs assertion becomes `{"timeout": ..., "follow_redirects": False}` + comment citing PRD-020 D5/F3 (the only pre-existing assertions that change) |
| `tests/test_stub_openrouter.py` | UPDATE | add stub cases for `usage: null`, `auth=`, 302 (existing `endswith("-> 200")` at `:138` holds if `auth=` precedes `->`) |

Not touched: `chat_ui/chat_ui/state.py:24` (imports the shim; keeps working; avoids the chat_ui guard), scripts importing the shim (`spike_pii_placeholders`, `measure_*`).

## Patch-target inventory (must keep working; grep of tests/)

- `"app.routers.query.call_openrouter"`: 139 setattr uses (test_duplicate_*, test_audit_*, test_chat_state, test_db_resilience_*, ...). `query.py:186` passes it into `run_query`.
- `"app.routers.v1.call_openrouter"`: 31 uses (test_v1_*, test_db_resilience_headroom/ingress/release, ...); `_Upstream` at `v1.py:167-170` looks it up at call time.
- `chat_state_mod.call_openrouter` (`chat_ui/chat_ui/state.py`, ~25 uses) and `setattr(query_router_module, "call_openrouter", ...)` (`test_prd020_legacy_fixtures.py:512`).
- Default checks: `tests/test_query_pipeline_run_conversation.py:97,112` assert the `call_openrouter` parameter default `is query_pipeline.call_openrouter`; true while that name is the bound alias.
- Names tests import from the shim: `OpenRouterError`, `OpenRouterResult`, `call_openrouter`, `GenerationParams`, `ToolParams`, `UnsupportedParameterError`.
- No test patches `settings` inside the client module; `httpx.Client` is patched on the httpx module (`test_openrouter_client.py:168,191`).

## Tasks

### Task 1: Package skeleton (params, types)
- Create `upstream/params.py` (move verbatim) and `upstream/types.py`.
- **Validate**: `.venv/Scripts/python -c "import app.services.upstream.params"` (after Task 3 the package imports).

### Task 2: Adapter
- `upstream/openai_compatible.py`: move `_token_count`, `_wire_message`, `_parse_tool_calls(raw, label)`, `_classify_http_error`; add `OpenAICompatibleAdapter.__init__(provider, client=None)` and `complete` per Design. Payload building (`:246-262`) unchanged.
- **Mirror**: `openrouter_client.py:219-332`.

### Task 3: `call_upstream`, shim, imports
- `upstream/__init__.py` per Design; rewrite `openrouter_client.py` as aliases; switch the four app imports.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`; `grep -rn openrouter_client app/` prints nothing; `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_prd020_legacy_fixtures.py tests/test_openrouter_client.py` (fixtures unedited; only the two kwargs assertions change).

### Task 4: Stub
- `"usage": null` (`_parse_reply` `:322`): accept an explicit `None` as "omit"; keep `Reply.usage` Optional and let `None` mean omitted, with the body at `:501` skipping the key (default stays the `{}` -> 1+1 tokens path). Update docstring `:37-39`.
- Log: add ` auth=yes|no` before ` -> status` (`self.headers.get("Authorization") is not None`, presence only). Update the header note `:69-70`.
- 302: `fail_status` is limited to 400-599 (`:301-304`), so add a reply key `redirect_status` (301, 302, 303, 307, 308) with optional `location` (default `http://127.0.0.1:9/never`), exclusive with body keys like `fail_status`; the handler sends that status plus `Location` and a small JSON body. Add the keys to the allowed-key set (`:88`).
- `make_server(..., require_key: Optional[str] = None)`: in-process only (not a CLI flag, not in script JSON). When set and `Authorization` is not exactly `Bearer <require_key>`, log the line with `-> 401` and answer 401. The value is compared, never logged. This is the cross-check, since headers are never logged.
- **Validate**: `tests/test_stub_openrouter.py`.

### Task 5: Tests
- Unit cases use a small `_FakeClient` (copy `test_openrouter_client.py:23-44`); E2E cases use real stubs.
- AC1: legacy fixtures unedited; shim identity (`call_openrouter is call_upstream`, `OpenRouterError is UpstreamError`, `OpenRouterResult is UpstreamResult`, params names importable and identical to `upstream.params`); `inspect.signature(call_upstream)` equals the old signature; a source scan that no `app/` file mentions `openrouter_client`; an injected `(messages, model, api_key, **kw)` stub still works through `run_query`.
- AC2: two stubs (`make_server` + threads, free ports, `require_key`); stubs start first, then the YAML is written with their ports (loopback `http` is accepted); `openrouter` has `key_env` set (env value A), `local` has none; one model each; call both. Assert logs `auth=yes` / `auth=no`, both 200 (each got its own key), and a swapped key would give 401; neither key value nor "Bearer" appears in either log or `capfd`.
- AC3: spy on `httpx.Client`: kwargs == `{"timeout": provider.timeout_seconds, "follow_redirects": False}`; real stub `redirect_status: 302` -> `UpstreamError`, `retryable is False`, `upstream_status == 302`, stub log shows exactly one request (not followed); a `_FakeClient` returning 302 and 307 `httpx.Response`s.
- AC4: label `Local`: connect failure / 503 -> `Local request failed:`; malformed body -> `Local returned an unexpected response shape:`; null content -> `Local returned no text content`; bad `tool_calls` with `tools=` -> `Local returned an unexpected response shape: choices[0].message.tool_calls`; `usage: null` -> `Local returned an unexpected response shape` (D8 is STORY-009). Legacy strings stay pinned by the fixtures.
- AC5: D10 both ways (byok provider sends the caller key; `byok: false` ignores it and sends its own, checked with `require_key`); legacy empty key -> message equals `errors.json` `key_missing`; keyed file-mode provider with no key -> same-shaped message naming its label and `key_env`; `resolve` None -> non-retryable, text has no key or URL; keyless provider with a caller key still sends no Authorization.
- No-leak: key values absent from `repr(provider)`, `repr(route)`, every `UpstreamError` text and `caplog`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_upstream_adapter.py tests/test_stub_openrouter.py`

## End-to-End Tests

- [ ] Legacy fixtures replay unedited through the real `call_upstream` over `httpx.MockTransport` and `TestClient(app)` (`tests/test_prd020_legacy_fixtures.py`).
- [ ] Two-stub, two-key run (Task 5, AC2), the real adapter over real sockets.
- [ ] `/v1` and `/query` patch targets still intercept (`tests/test_query_router.py`, `tests/test_v1_errors.py`).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_upstream_adapter.py tests/test_stub_openrouter.py tests/test_openrouter_client.py tests/test_prd020_legacy_fixtures.py tests/test_query_router.py tests/test_v1_errors.py tests/test_query_pipeline_run_conversation.py tests/test_untouched_app.py tests/test_pii_redaction_integration.py
```
`tests/test_chat_ui_startup_guard.py` only if `chat_ui/` is touched (the plan does not). No test is renamed or removed.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 fixtures unedited, shim, imports, injected stubs | 1-3, 5 | `test_prd020_legacy_fixtures.py`; `test_upstream_adapter.py::test_shim_*`, `::test_no_app_module_imports_the_shim` |
| AC2 two stubs, auth yes/no, own key, no header in log | 4, 5 | `::test_two_stubs_each_get_only_their_own_key`, `::test_stub_log_never_carries_a_header_value` |
| AC3 client kwargs, 302 not followed | 2, 4, 5 | `::test_default_client_kwargs`, `::test_302_is_a_non_retryable_error_and_not_followed` |
| AC4 `Local ...` labels, legacy byte-identical | 2, 5 | `::test_local_label_*`; legacy fixtures |
| AC5 D10 both ways, legacy `key_missing` | 3, 5 | `::test_byok_key_only_for_byok_provider`, `::test_missing_key_message_matches_errors_json` |

## Risks / open points

- 3xx: handled by the explicit status check, with `_FakeClient` 302/307 tests so an httpx change cannot hide it.
- `types.py` is an extra file versus 6.5; the alternative (types in `__init__` before the adapter import) is import-order fragile.
- `require_key` and `redirect_status` go beyond the story text (the story allows the redirect reply if `fail_status` cannot express it); the key cross-check needs a server-side comparison because headers are never logged.
- The new 3xx check reads `resp.status_code`; implementer should confirm no fake client in the suite returns a bare Mock without it (the ones in `test_openrouter_client.py` return real `httpx.Response`).
