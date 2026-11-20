---
story: STORY-004
prd: PRD-022
slug: registry-anthropic-type-and-fields
title: Registry accepts type anthropic and the PRD-022 catalogue fields; adapter dispatch by provider type
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: Registry type `anthropic`, catalogue fields, adapter dispatch

## Summary

Widen the closed registry vocabulary: `TYPES` gains `anthropic`; capabilities gain `forced_tool_choice` / `sampling_params`; models gain `default_max_tokens` and `prompt_cache`. Fix the hard-coded `type="openai_compatible"` in the `Provider(...)` built by `_parse_provider`. Add a small type->adapter mapping in `upstream/__init__.py` whose `anthropic` entry raises a non-retryable `UpstreamError(kind="incompatible")` until STORY-005. Legacy registry and `openai_compatible` behaviour stay byte-identical (every new field has a default).

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-004-registry-anthropic-type-and-fields.md`
- PRD sections used: 6.5 (request table: `forced_tool_choice`, `max_tokens`, `sampling_params`; usage note), 9.3 "Registry additions", D4, D5
- Systems affected: `provider_registry`, `upstream/__init__`, registry and seam tests, `examples/providers.yaml` (comment only)

## Design Decisions

Not a critical story; no design points. Orchestrator notes and the choices that follow:

- `passthrough: true` on `type: anthropic` is **refused** at load (STORY-001 found no reason to allow it). Message names file, provider and rule: `passthrough: refused for 'type: anthropic' (catalogue ids only, PRD-022 D4)`.
- Missing `default_max_tokens` on a model of an anthropic provider: `_fail(source, where, "default_max_tokens: required for 'type: anthropic' (the Messages API requires max_tokens, PRD-022 6.5)")`. `where` already holds provider and model id (`providers[0] 'p1' models[0] 'm1'`; `_parse_model` does `where = f"{where} {model_id!r}"`).
- `default_max_tokens` (int >= 1, bool refused) and `prompt_cache` (`off | auto`, default `off`) are parsed for every provider type, stored, and unused by `openai_compatible` (say so in the dataclass docstring). Only the *required* rule is type-specific. New vocabulary tuple `PROMPT_CACHE = ("off", "auto")`, validated with `_choice`.
- `usage_missing` on anthropic: accepted unchanged; a comment says it has no effect (Anthropic always reports usage; a missing `usage` is a `shape` error, 6.5). No new validation.
- Dispatch: seam signatures unchanged. `client: httpx.Client` goes only to the openai_compatible factory. The anthropic factory raises `UpstreamError("<label>: the 'anthropic' adapter is not available yet", provider=provider.name, kind="incompatible")` (`retryable` defaults False; no prompt text, T10). It raises at call time in both seams (`stream_upstream` already raises route/key errors at call time, `upstream/__init__.py:129`). Do NOT create `upstream/anthropic.py` (STORY-005).
- Key resolution is unchanged: `_resolve_call` (`upstream/__init__.py:61-88`) runs first, so a keyless anthropic provider still yields `misconfigured`.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; no `chat_ui/` work).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Vocabulary | `provider_registry.py:49-52` | closed tuples (`TYPES`, `USAGE_MISSING`); add `PROMPT_CACHE` beside them |
| Key lists | `provider_registry.py:80-81` | `_MODEL_KEYS`, `_CAPABILITY_KEYS` are what `_check_keys` allows; append the new names |
| Bool / choice parse | `provider_registry.py:257`, `:274` | `_bool(...)`, `_choice(...)` for the capability bools and `prompt_cache` |
| Positive int | `provider_registry.py:303-306` | `max_context_tokens` check (bool refused, `< 1` refused); copy for `default_max_tokens` |
| Dataclass | `provider_registry.py:86-105` | frozen; new fields with defaults go last (`CatalogModel` ends with `provider_name`, so they follow it) |
| Error text | `provider_registry.py:164-166` | `_fail(source, where, rule)`: file, node, rule |
| Legacy build | `provider_registry.py:541-562` | builds `Capabilities(...)`/`CatalogModel(...)` by keyword: defaults need no edit |
| Seam | `upstream/__init__.py:107`, `:130` | both build `OpenAICompatibleAdapter(route.provider, client)` inline; replace with one factory lookup |
| Registry tests | `tests/test_provider_registry.py:134-171` (`_BAD` table), `:205-212`; helpers `:20-68` | add rows with a fragment; `FULL`/`MINIMAL`/`_p()` |
| Seam tests | `tests/test_stream_upstream_seam.py:40-50` (`provider_file`, `_MSG`, `_KEY`), `:280-300` | file-mode route + `pytest.raises(UpstreamError)` |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/provider_registry.py` | UPDATE | vocabulary, dataclasses, parsers, type/passthrough rules |
| `app/services/upstream/__init__.py` | UPDATE | type->adapter mapping, `incompatible` stub for anthropic |
| `tests/test_provider_registry.py` | UPDATE | new rows and tests; the `"type"` row at `:168` changes |
| `tests/test_stream_upstream_seam.py` (or new `tests/test_upstream_dispatch.py`) | UPDATE/CREATE | dispatch tests for both seams |
| `examples/providers.yaml` | UPDATE | `:7` comment "the only accepted type" (comment only; no active anthropic block until STORY-005). `docs/features.md:413` waits for the docs story |

## Tasks

### Task 1: Registry vocabulary, dataclasses, parsers

- **File**: `app/services/provider_registry.py`
- **Action**: UPDATE
- **Implement**:
  1. `:49` `TYPES = ("openai_compatible", "anthropic")`; add `PROMPT_CACHE = ("off", "auto")` near `:52`. Comment: PRD-022 addition to PRD-020's set.
  2. `:80` `_MODEL_KEYS += ("default_max_tokens", "prompt_cache")`; `:81` `_CAPABILITY_KEYS += ("forced_tool_choice", "sampling_params")`.
  3. `Capabilities` (`:86`): append `forced_tool_choice: bool = False`, `sampling_params: bool = False` (docstring: "claimed, not assumed", PRD-020 O6; PRD-022 6.5). `CatalogModel` (`:97`): append `default_max_tokens: Optional[int] = None`, `prompt_cache: str = "off"` after `provider_name`.
  4. `_parse_capabilities` (`:297`): add the two `_bool(...)` calls to `Capabilities(...)`.
  5. `_parse_model` (`:315`): new parameter `provider_type: str`. Parse `default_max_tokens` (`must be an integer` / `must be at least 1, got N`) and `prompt_cache` via `_choice`. If `provider_type == "anthropic"` and `default_max_tokens` is absent, `_fail` (text above). Update the caller in `_parse_provider` (`:379`) to pass `body["type"]`.
  6. `_parse_provider` `:346-352`: replace the single-type refusal with `_choice(source, where, "type", body["type"], TYPES)` (the message then names the allowed set; drop the "arrive with PRD-022" text). After `passthrough` is parsed (`:376`), refuse it when type is `anthropic`. At `:395` change `type="openai_compatible"` to `type=body["type"]`.
  7. Comment beside `usage_missing` (`:399`): no effect for `type: anthropic`.
- **Mirror**: `:303-306`, `:257`, `:274`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_provider_registry.py`

### Task 2: Adapter dispatch

- **File**: `app/services/upstream/__init__.py`
- **Action**: UPDATE
- **Implement**: below `_resolve_call` add `_build_adapter(provider, client) -> ProviderAdapter` driven by a module-level mapping `_ADAPTER_FACTORIES` (type -> `Callable[[Provider, Optional[httpx.Client]], ProviderAdapter]`): `"openai_compatible"` builds `OpenAICompatibleAdapter(p, c)`; `"anthropic"` is `_anthropic_unavailable` (raises the `incompatible` error; comment "STORY-005 replaces this entry"). Index with `[provider.type]`, not `.get`, so a gap is loud (the registry vocabulary is closed, so an unknown type cannot arrive). Replace `:107` and `:130` with `_build_adapter(route.provider, client)`. Seam signatures, `__all__` and `reasoning=route.capabilities.reasoning` (`:133`) stay.
- **Mirror**: `upstream/types.py:48-63` for `UpstreamError(message, provider=..., kind=...)`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_stream_upstream_seam.py tests/test_upstream_adapter.py`

### Task 3: Tests

- **Files**: `tests/test_provider_registry.py`, the seam test file.
- **Action**: UPDATE
- **Implement**:
  - `_BAD` row `"type"` (`:168`) replaced `openai_compatible` by `anthropic` and expected `"PRD-022"`; anthropic is now valid (and would fail on `default_max_tokens`). Change it to `MINIMAL.replace("openai_compatible", "bedrock")` expecting `"anthropic, openai_compatible"`, with a comment citing PRD-022 F1-addition / STORY-004. Keep the row id.
  - New `_BAD` rows: anthropic model without `default_max_tokens` (fragment `default_max_tokens: required`; plus a test asserting the message names `'p1'` and `'m1'`, like `test_startup_error_names_provider_and_model` `:220`); `default_max_tokens` of `0`, `true`, `"8"`; `prompt_cache: sometimes`; `passthrough: true` on anthropic (fragment `passthrough: refused`).
  - New tests: an anthropic provider with `default_max_tokens`, `prompt_cache: auto`, `forced_tool_choice`, `sampling_params`, `usage_missing: error` loads, values held, `provider.type == "anthropic"`, fields frozen (`dataclasses.FrozenInstanceError`); an openai_compatible model with none of the keys gets the defaults (`default_max_tokens is None`, `prompt_cache == "off"`, both capability bools False); legacy test near `:415-430` gains default assertions.
  - Seam tests (`provider_file` fixture): `call_upstream` and `stream_upstream` on an anthropic model raise `UpstreamError` with `kind == "incompatible"`, `provider` set, `retryable is False`, `fallback_eligible is False`, message free of prompt text; with the key env unset the error is `misconfigured` (key check runs first). For openai_compatible, patch `OpenAICompatibleAdapter` in `app.services.upstream` and assert one build with `(provider, client)`.
- **Mirror**: `tests/test_provider_registry.py:134-212`; `tests/test_stream_upstream_seam.py:280-300`.
- **Validate**: command in Validation.

### Task 4: Example comment

- **File**: `examples/providers.yaml:7`. Reword the comment only. Run `grep -rn "examples/providers" tests` and run any test it finds.

## End-to-End Tests

- [ ] A file-mode registry with one anthropic and one openai_compatible provider loads; `resolve()` returns the right `Route.provider.type` for each.
- [ ] Legacy/openai_compatible-only flows unchanged: the routing and seam suites in Validation.
- [ ] An anthropic model through `call_upstream` fails fast as `incompatible`, no retry (seam level; a TestClient check only if cheap).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_provider_registry.py tests/test_provider_routing.py tests/test_stream_upstream_seam.py tests/test_upstream_adapter.py tests/test_untouched_app.py <new seam test file if created>
```

Grep done while planning: `Capabilities(`/`CatalogModel(` appear in tests only at `tests/test_provider_registry.py:87,113,114` (keyword or equality, unaffected by defaults). No test is renamed or removed, so `test_pii_redaction_integration.py` is not needed. No `database.py`, audit or pipeline signature is touched.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 type anthropic accepted; unknown type names allowed set | 1, 3 | new anthropic-loads test; `_BAD` row `type` (allowed-set fragment) |
| AC2 fields parse, frozen, unknown keys refused | 1, 3 | new fields test; existing `unknown-capability`/`unknown-model` rows; invalid `default_max_tokens`/`prompt_cache` rows |
| AC3 missing `default_max_tokens` names file/provider/model/rule; passthrough refused; `usage_missing` accepted | 1, 3 | `_BAD` rows + names-test; anthropic-loads test sets `usage_missing` |
| AC4 dispatch by type; anthropic `incompatible`; openai_compatible unchanged | 2, 3 | new seam tests + existing `test_stream_upstream_seam.py`, `test_upstream_adapter.py` |
| AC5 legacy defaults | 1, 3 | extended legacy registry test |

Plus: all tasks done, validation passes, patterns followed.

## Risks

- `type=` hard-coded in the `Provider(...)` call (`:395`) is easy to miss; a test asserting `provider.type == "anthropic"` guards it.
- `passthrough_capabilities` goes through `_parse_capabilities`, so it accepts the new keys; harmless (passthrough is refused for anthropic), left as is.
- Raising in `stream_upstream` at call time (not first `next()`) matches today's route/key errors; later pipeline code wrapping the call must already handle that.
