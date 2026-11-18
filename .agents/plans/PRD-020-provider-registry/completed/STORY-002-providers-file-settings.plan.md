---
story: STORY-002
prd: PRD-020
slug: providers-file-settings
title: PROVIDERS_FILE setting and the conditional OPENROUTER_API_KEY requirement
type: ENHANCEMENT
complexity: small
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-18
---

# Plan: PROVIDERS_FILE setting and the conditional OPENROUTER_API_KEY requirement

## Summary

Two settings changes in `app/config.py` and nothing else in `app/`: add `PROVIDERS_FILE: str = ""`, make `OPENROUTER_API_KEY` default to `""`, and add two `@model_validator(mode="after")` checks (legacy mode needs the key; file mode forbids `V1_TOOL_MODELS`). The file is never opened here (STORY-003). New tests go in `tests/test_config.py`.

- Story: `.agents/stories/PRD-020-provider-registry/STORY-002-providers-file-settings.md` (ACs live there)
- PRD sections used: §4 "Settings", §9.3, D1, D6
- Systems affected: `app/config.py`, `tests/test_config.py`, `tests/test_chat_ui_startup_guard.py` (one env line, hygiene)

## Design Decisions

none beyond the tasks. Binding details:

- Emptiness is plain truthiness (`not self.PROVIDERS_FILE`, `not self.OPENROUTER_API_KEY`), the same test the client uses (`api_key or settings.OPENROUTER_API_KEY`, `openrouter_client.py:235`). No `.strip()`: a whitespace key stays "set", as today.
- Messages name settings only, never a value (`hide_input_in_errors=True`, `config.py:176-178`). The key validator must not echo `self.OPENROUTER_API_KEY` (it is empty there anyway); the D6 validator must not echo `V1_TOOL_MODELS` entries or the `PROVIDERS_FILE` path, only names + "PRD-020 D6".
- Validator order: pydantic runs after-validators in definition order and `ValidationError` carries the first raise. Define BOTH new validators immediately BEFORE `_validate_v1_tool_models` (`config.py:745`), so the D6 message wins over "V1_TOOL_MODELS names model(s) not in MODEL_ALLOWLIST" when both apply (story Technical Notes).
- The "a `key_env` names OPENROUTER_API_KEY" half is STORY-003's (OD4). Do not read or parse the file.

## Skills In Use

`.agents/skills/` holds only `frontend-design`, not applicable (no UI). None.

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Validator shape | `app/config.py:745-771` (`_validate_v1_tool_models`) | `@model_validator(mode="after")`, docstring citing PRD section + decision, `raise ValueError(...)` with setting names + an `Example:` tail, `return self` |
| File setting | `app/config.py:273-277` (`PATTERNS_FILE: str = ""`, comment "empty means ... no file is read at all") | comment style for `PROVIDERS_FILE` |
| Two-field validator | `app/config.py:773-789` (`_validate_audit_buffer_max_bytes`) | docstring says "Both fields are needed, so this is a model validator" |
| Test helper | `tests/test_config.py:95-97` | `_settings(**overrides)` injects `OPENROUTER_API_KEY=test-key`, `ADMIN_TOKEN`, `_env_file=None`; to test the unset key, call `Settings(_env_file=None, ADMIN_TOKEN=..., DATABASE_URL=_LOCAL_URL)` directly AND `monkeypatch.delenv("OPENROUTER_API_KEY")` (conftest sets it via `setdefault`, `tests/conftest.py:92`, so env would otherwise supply it) |
| Not-read test | `tests/test_config.py:1384-1389` (`test_action_policy_file_is_not_read_by_settings`) | a nonexistent `tmp_path` path constructs fine |
| Error-text test | `tests/test_config.py:1450-1460` | `pytest.raises(ValidationError)`, assert named fragments in `str(exc_info.value)` |

## Findings (checked, no change needed)

- Missing-key path: `openrouter_client.py:235-239`. With `api_key=""` and `settings.OPENROUTER_API_KEY == ""` the `or` yields `""`, `not resolved_key` is true, it raises `OpenRouterError("OpenRouter API key not configured: pass openrouter_api_key or set OPENROUTER_API_KEY")`, byte-identical to `tests/fixtures/prd020_legacy/errors.json:52` `key_missing`. Making the field `= ""` does not touch this code; do not edit the client or the fixture. After the change this path is reachable at runtime only via a test monkeypatch (legacy startup now fails first), which is exactly how STORY-001 pins it.
- Only `DATABASE_URL` is asserted required (`tests/test_config.py:152`, `tests/test_conftest_fixtures.py:72`). No test asserts `OPENROUTER_API_KEY` is required, and none builds `Settings` without it, so AC4 needs no changed pre-existing assertion (no PRD-020 D1 comment needed on an existing line; say so in the report).
- Every suite process gets the key from `os.environ.setdefault` (conftest + ~60 test modules), so legacy-mode behaviour in the suite is unchanged. `tests/test_chat_ui_startup_guard.py` child inherits `os.environ` (`:167`) with the key and no `PROVIDERS_FILE`; it passes unchanged.
- `Dockerfile:27` (`OPENROUTER_API_KEY=build-placeholder`) and `ci.yml:50` keep working; leave them.
- Docs are STORY-015's (`.env.example` header "(required)" at `.env.example:1`, `docs/configuration.md:13`, `docs/testing.md:122`). Do NOT edit them here. Do NOT add `PROVIDERS_FILE=` to `.env.example` in this story: `tests/test_config.py` enforces comment-above + defaults for env vars it names, and STORY-015 owns the three-line comment.

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | UPDATE | field defaults + two validators |
| `tests/test_config.py` | UPDATE | new section "PRD-020 STORY-002" with 7 tests |
| `tests/test_chat_ui_startup_guard.py` | UPDATE (optional, 2 lines) | `env["PROVIDERS_FILE"] = ""` in `_empty_rbac_env` (`:176-180` style) so a developer's shell cannot flip the child into file mode |

## Tasks

### Task 1: Settings fields
- **File**: `app/config.py`
- **Implement**: `:180` `OPENROUTER_API_KEY: str = ""` with a comment: required unless `PROVIDERS_FILE` is set (PRD-020 §4, §9.3, D1), enforced by `_validate_openrouter_api_key_required`; a provider's `key_env` naming it is checked by the registry (STORY-003). Add `PROVIDERS_FILE: str = ""` after `PATTERNS_FILE` (`:277`) or beside `OPENROUTER_BASE_URL` (`:251`) with a comment in the `PATTERNS_FILE` shape: empty means the implicit legacy provider and no file is read; the file is read by `provider_registry.load()` (STORY-003), not Settings.
- **Mirror**: `app/config.py:273-277`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Validators (before `_validate_v1_tool_models`, i.e. above `:745`)
- **Implement**:
  - `_validate_openrouter_api_key_required`: if `not self.PROVIDERS_FILE and not self.OPENROUTER_API_KEY` raise ValueError naming `OPENROUTER_API_KEY` and `PROVIDERS_FILE`: "OPENROUTER_API_KEY is required when PROVIDERS_FILE is empty: without a registry file the harness calls OpenRouter with it. Set it, or set PROVIDERS_FILE to a registry that does not use OpenRouter (PRD-020 D1). Example: OPENROUTER_API_KEY=sk-or-..." Use a clearly fake example token, not a real-looking key.
  - `_validate_providers_file_vs_v1_tool_models`: if `self.PROVIDERS_FILE and self.v1_tool_models_list` raise ValueError naming `V1_TOOL_MODELS` and `PROVIDERS_FILE`, saying capabilities now live in the registry (`models[].capabilities.tools`), PRD-020 D6, and to empty `V1_TOOL_MODELS`. Use `v1_tool_models_list` (not truthiness of the raw string) so whitespace/comma-only passes, as `tests/test_config.py:1463-1467` expects for blank values. The existing validator's blank-value behaviour is preserved because with `PROVIDERS_FILE` set and the list empty the new check passes.
- **Mirror**: `app/config.py:745-771`, docstrings cite "PRD-020 Section 9.3, D1" and "D6".
- **Validate**: Task 3 tests.

### Task 3: Tests (`tests/test_config.py`, new section after the PRD-017 STORY-002 block, `~:1493`)
Use `_settings(DATABASE_URL=_LOCAL_URL, ...)`; for "key unset" build `Settings(_env_file=None, ADMIN_TOKEN="test-token", DATABASE_URL=_LOCAL_URL)` after `monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)` and `delenv("PROVIDERS_FILE", raising=False)`.
1. `test_openrouter_api_key_is_no_longer_a_required_field`: `not Settings.model_fields["OPENROUTER_API_KEY"].is_required()` and default `""`. Comment: PRD-020 D1 (was required).
2. `test_no_file_and_no_key_is_a_startup_error_naming_the_key`: ValidationError, message contains `OPENROUTER_API_KEY` and `PROVIDERS_FILE`; also build with `ADMIN_TOKEN="s3cr3t-sentinel"` and assert the sentinel is absent from the message (reuse `_TOKEN_SENTINEL`, `:89`).
3. `test_no_file_and_empty_string_key_is_a_startup_error`: `OPENROUTER_API_KEY=""` explicit.
4. `test_providers_file_set_and_no_key_constructs`: `PROVIDERS_FILE=str(tmp_path/"missing.yaml")`, key unset; `result.OPENROUTER_API_KEY == ""`.
5. `test_providers_file_is_not_read_by_settings`: nonexistent path constructs and round-trips (mirror `:1384`); AC5.
6. `test_providers_file_with_v1_tool_models_is_a_startup_error`: `MODEL_ALLOWLIST="gpt-4,openai/gpt-4o"`, `V1_TOOL_MODELS="openai/gpt-4o"`, file set; message has `V1_TOOL_MODELS`, `PROVIDERS_FILE`, `D6`, `registry`; assert it does NOT contain "not in MODEL_ALLOWLIST". Second case: entry NOT in allowlist plus file set still yields the D6 message (proves ordering).
7. `test_providers_file_with_blank_v1_tool_models_passes` (parametrize `""`, `"   "`, `" , ,"`) and `test_no_file_with_v1_tool_models_still_validates_as_before` (existing allowlist rule unchanged; covered by `:1441-1460`, so a single positive case suffices).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_config.py`

### Task 4: Guard hygiene
- `tests/test_chat_ui_startup_guard.py` `_empty_rbac_env`: add `env["PROVIDERS_FILE"] = ""` with a comment citing PRD-020 STORY-002 (the "no registry file" case stated, not inherited), after `:180`.

## End-to-End Tests

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` (conftest-free: env supplies key, legacy mode)
- [ ] Subprocess check (optional, one-off, not committed): with `OPENROUTER_API_KEY` removed and `PROVIDERS_FILE` unset, `import app.config` fails naming `OPENROUTER_API_KEY`; with `PROVIDERS_FILE=x.yaml` it imports (`settings = Settings()` at `config.py:820` runs at import).
- [ ] No `chat_ui/` code changes; only the guard test env line.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_config.py tests/test_chat_ui_startup_guard.py tests/test_untouched_app.py tests/test_openrouter_client.py tests/test_prd020_legacy_fixtures.py
```

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 no file + no key -> error naming key, no value | 2 | `test_no_file_and_no_key_is_a_startup_error_naming_the_key`, `..._empty_string_key_...` |
| AC2 file set, no key -> `""` | 1, 2 | `test_providers_file_set_and_no_key_constructs` |
| AC3 file + `V1_TOOL_MODELS` -> D6 error; empty passes | 2 | `test_providers_file_with_v1_tool_models_is_a_startup_error`, `..._blank_...` |
| AC4 existing config tests unchanged | 1 | whole `tests/test_config.py` run; no pre-existing assertion needs editing (none asserts the key is required) |
| AC5 file not opened | 1 | `test_providers_file_is_not_read_by_settings` |

## Risks

- A `.env` with `OPENROUTER_API_KEY=` empty (deployments copying the template with the value blanked) now fails at startup with a clear message instead of at the first call; intended (D1).
- `OPENROUTER_API_KEY` is also read from `settings` by scripts using `setdefault` (`scripts/measure_*.py`); unchanged.
- STORY-003 must still reject a file whose provider `key_env` names `OPENROUTER_API_KEY` when it is empty.
