---
story: STORY-003
prd: PRD-020
slug: registry-loader-and-validation
title: Provider registry loader, validation and the legacy implicit provider
type: NEW_CAPABILITY
complexity: large
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-18
---

# Plan: Provider registry loader, validation and the legacy implicit provider

## Summary

New pure-after-load module `app/services/provider_registry.py`: frozen dataclasses, strict-YAML parse of `PROVIDERS_FILE`, one validator per F1 rule family (messages in `action_config._fail` style), the D5 `classify_base_url` helper, the three F1 WARNINGs, per-provider key resolution held outside the dataclasses, and a legacy registry derived from LIVE settings. Plus lifespan wiring in both processes and the `tests/_providers.py` fixture that stories 004-014 use. No `resolve`/`visible_models`/`supports_tools` (STORY-004), no adapter (STORY-005).

- Story: `.agents/stories/PRD-020-provider-registry/STORY-003-registry-loader-and-validation.md`
- PRD sections used: §4 Registry, §6.2, F1, F3, F4, §9.2 T1/T2/T4/T11, §9.3, D1, D5, D6, D7, O3, O4
- Systems affected: `app/services/`, both lifespans, `tests/`

## Design Decisions (binding, from the orchestrator, with edge cases)

- **State.** `_snapshot: Optional[Registry] = None` (file mode only) and `_keys: dict[str, str]` beside it. `current() -> Registry`: the snapshot if set, else the legacy registry from live settings, memoized single-slot on `(MODEL_ALLOWLIST, V1_TOOL_MODELS, OPENROUTER_BASE_URL, OPENROUTER_TIMEOUT_SECONDS)`. `load()` with `PROVIDERS_FILE` empty sets `_snapshot=None`, `_keys={}`, no I/O. `reset()` clears snapshot, keys, memo. `load()` rebinds `_snapshot`/`_keys` as its LAST statement, so a failing file leaves the previous state (`action_config.py:1094`).
- **Data model** (`@dataclass(frozen=True)`, `action_config.py:138` style): `Capabilities(tools, streaming, reasoning, max_context_tokens)` defaults false/None; `CatalogModel(id, upstream, roles, capabilities, provider_name)`; `Provider(name, label, type, base_url, key_env, insecure_http, trust, pii, byok, passthrough, passthrough_capabilities, usage_missing, estimate_chars_per_token, timeout_seconds, roles, models)`; `Registry(default_model, providers, models_by_id (MappingProxyType), passthrough_provider, is_legacy)`. NO key field anywhere. Vocab constants `TRUSTS`, `PII_MODES`, `USAGE_MISSING`, `TYPES=("openai_compatible",)`.
- **Keys.** `api_key_for(provider)`: file mode `_keys.get(provider.name)` (None if keyless); legacy `settings.OPENROUTER_API_KEY` at call time. File-mode resolution: `key_env == "OPENROUTER_API_KEY"` -> `settings.OPENROUTER_API_KEY`; else `os.environ.get(name)`, then `dotenv_values(".env")` (same relative path pydantic reads, `app/config.py:176-177`; `python-dotenv` is `requirements.txt:6`). Unset or empty -> error naming the variable only.
- **Legacy registry** exactly as the orchestrator's point 4 (`openrouter`/`OpenRouter`, live `OPENROUTER_BASE_URL` not re-validated, timeout live, external/standard, byok, passthrough, `usage_missing=error`, 4 chars/token, roles None; one model per `settings.model_allowlist_list` (`config.py:855`) with `tools = (not v1_tool_models_list) or id in list` (`config.py:859`); `passthrough_capabilities.tools = not v1_tool_models_list` (keeps `config.py:690-695`'s rule); `default_model="gpt-4"`; `is_legacy=True`). A repeated allowlist entry is de-duplicated, first wins.
- **`classify_base_url(url) -> (scheme, host, kind)`**: `urlsplit(url.strip())`, scheme like `config._scheme_of` (`config.py:100`), host `.hostname or ""` (`ValueError` -> ""). `kind`: host in `_LOOPBACK_HOSTS` (`config.py:97`, exactly today's set) -> `loopback`; IP literal inside the explicit networks 10/8, 172.16/12, 192.168/16, fc00::/7 -> `private_ip` (NOT `ip.is_private`: it includes link-local and more, O4); any other literal (CGNAT, link-local, IPv4-mapped IPv6) -> `public_ip`; else `hostname`. Empty host is rejected by the caller as "names no host".
- **D5 rule** `_check_base_url`: https+host ok; http+loopback ok; http+private_ip only with `insecure_http: true`; http+hostname/public_ip refused even with it; other scheme or no host refused. `insecure_http: true` on https/loopback is accepted (a no-op, and no WARNING: the WARNING fires only when the URL is plain http and `insecure_http` is true).
- **`trust: internal`**: `public_ip` -> error regardless of scheme; `hostname` -> WARNING (O3); loopback/private silent. `pii: relaxed` without `internal` -> error.
- **Warnings** (`logger = logging.getLogger(__name__)`, one record per condition per provider, emitted only after the whole file validated, so a failing file logs none): insecure_http (scheme+host); internal on hostname (scheme+host); `key_env` not matched by `action_config.get_policy().secrets.env.compiled` (`any(c.search(name))`, as `tests/test_action_config.py:124`), naming the variable. `get_policy()` returns the built-in policy before `action_config.load()`, so the fallback is automatic.
- **Parsing**: top keys `version` (required, must be 1), `default_model` (required), `providers` (required non-empty list). Provider keys = F1 list + `passthrough_capabilities` (accepted only when `passthrough: true`, F4). `models` required unless `passthrough: true`. `name` matches `[a-z0-9][a-z0-9_-]{0,31}`. Model keys `id`, `upstream`, `roles`, `capabilities`; capability keys `tools/streaming/reasoning` bool, `max_context_tokens` int >= 1; bools refused where numbers are expected. `roles`: non-empty list of non-empty strings, not cross-checked with the RBAC matrix (F1 lists no such error).
- **Cross checks**: duplicate provider name / model id; more than one `passthrough`; `default_model` neither catalogued nor passthrough-routable; `byok: true` with `passthrough: false` and no models; `type` != `openai_compatible` names PRD-022. `V1_TOOL_MODELS` + file is already a Settings startup error (`config.py:773-785`); the registry does not repeat it.
- **Defaults**: `label`=name; `timeout_seconds`=`settings.OPENROUTER_TIMEOUT_SECONDS`, must be > 0; `estimate_chars_per_token`=4, in (0, 8]; `usage_missing="estimate"`; trust external; pii standard; byok/passthrough/insecure_http false.

## Skills In Use

None: `.agents/skills/` holds only `frontend-design` (not applicable; story `skills: []`).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Module/`load()` shape | `app/services/action_config.py:1042-1094` | empty setting = no I/O; read, `strict_yaml.safe_load`, validate all, rebind last |
| Errors | `action_config.py:360-366`, `:851-874` | `_fail`, `_check_keys` (unknown then missing, with allowed list), `_mapping` (copy small; they are private there) |
| Read/parse errors | `action_config.py:1074-1083` | `OSError`/`UnicodeDecodeError`, `yaml.YAMLError` wrapped by `_fail(source, "file", ...)` |
| Frozen models | `action_config.py:138-190` | frozen dataclasses, tuples, `MappingProxyType` |
| URL | `app/config.py:97-112`, `:522-564` | `_scheme_of`, `_LOOPBACK_HOSTS`; quote scheme+host only |
| Logger | `app/services/audit_logger.py:13` | `logger = logging.getLogger(__name__)` |
| Lifespan | `app/main.py:23-24`; `chat_ui/chat_ui/chat_ui.py:267-272` | after `action_config.load`, before `authz.check_bootstrap`; "Same bypass (PRD-020 STORY-003): ..." comment |
| Tests | `tests/test_action_config.py:107-148`, `tests/test_action_policy.py:342-365` | message-fragment asserts; `caplog.set_level(..., logger=...)`; no-I/O test patching `read_text` |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/provider_registry.py` | CREATE | everything above |
| `app/main.py` | UPDATE | import + `provider_registry.load()` after `:23` |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | import + `app.register_lifespan_task(provider_registry.load)` after `:267` |
| `tests/_providers.py` | CREATE | file-mode fixture (OD2) |
| `tests/test_provider_registry.py` | CREATE | all ACs |

## Tasks

### Task 1: Model, vocab, errors, `classify_base_url`
`app/services/provider_registry.py` (CREATE): dataclasses, constants, `ProviderRegistryError`, `_fail`, `_check_keys`, `_mapping`, `classify_base_url`. Validate: `python -c "import app.services.provider_registry"`.

### Task 2: Validators, one pure function per family
`_check_version`, `_parse_identity` (name/label/type), `_check_base_url`, `_check_trust_pii`, `_check_numbers`, `_check_roles`, `_parse_capabilities`, `_parse_model`, `_parse_provider`, `_check_registry` (duplicates, passthrough count, default_model, byok unusable). Message shape: `PROVIDERS_FILE '<path>': providers[1] 'gpu-box': base_url: <rule>`. They read no I/O. Mirror `action_config._validate_*`.

### Task 3: Keys, warnings, `load`/`current`/`reset`/`api_key_for`
`_resolve_keys(source, providers)`, `_warn(providers)`, `_build_legacy()`, public API. Settings read at call time, never at import. Mirror `action_config.load` (`:1042`).

### Task 4: Lifespan wiring
Edit both files as in the table. Validate: `.venv/Scripts/python -c "from app.main import app; print('OK')"`; `tests/test_chat_ui_startup_guard.py`.

### Task 5: `tests/_providers.py`
Documented API: `providers_file(tmp_path, yaml_text, *, monkeypatch, env=None) -> Registry`, a context manager that writes `tmp_path/providers.yaml`, sets `settings.PROVIDERS_FILE` and `V1_TOOL_MODELS=""`, `monkeypatch.setenv`s each `env` pair, calls `load()`, yields `current()`, and calls `reset()` in `finally` (also when `load()` raises); `write_registry(tmp_path, text) -> str` for error tests that call `load()` themselves; and a pytest fixture `provider_file` (callable, finalizer calls `reset()`). `reset()` does not depend on settings, so monkeypatch undo order is safe.

### Task 6: `tests/test_provider_registry.py`
One test per F1 error and per WARNING (parametrized snippets; assert file path, provider/model, rule text; assert no key value and no whole URL, using URLs carrying `user:pw@` and `?token=`). Also: defaults and immutability (`FrozenInstanceError`, `TypeError` on `models_by_id`); D5 matrix (`10.0.0.1`, `172.16.0.1`, `172.32.0.1` public, `192.168.1.1`, `fd00::1`, `100.64.0.1` and `169.254.1.1` refused, `http://[::1]:8000`, hostname+`insecure_http` refused); `classify_base_url` direct; key resolution (environ, `.env` via `monkeypatch.chdir`, `OPENROUTER_API_KEY` via settings, keyless None, legacy live read); `repr(current())` free of keys; legacy equals §6.2 and re-derives after `monkeypatch.setattr(settings, "MODEL_ALLOWLIST", ...)`; empty `load()` does no I/O; failed load keeps the previous snapshot; `reset()`; both lifespans call `load` after `action_config.load` (source-order check, `test_chat_ui_startup_guard.py` style); fixture restores legacy on teardown and on failure.

## End-to-End Tests
- [ ] `TestClient(app)` with `PROVIDERS_FILE` set to a valid tmp file starts; a bad file makes the lifespan raise `ProviderRegistryError`; empty setting starts in legacy mode.
- [ ] Chat UI probe from `tests/test_chat_ui_startup_guard.py`.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_provider_registry.py tests/test_action_config.py tests/test_config.py tests/test_chat_ui_startup_guard.py tests/test_untouched_app.py
```
No request path changes, so STORY-001's legacy fixture tests must stay green untouched.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 defaults + frozen | 1-3 | `test_provider_registry.py::test_full_file_exposes_defaults`, `::test_snapshot_is_immutable` |
| AC2 each F1 error, no leak | 2,3 | `::test_startup_error[<rule>]` (one param per error), `::test_errors_never_echo_key_or_url` |
| AC3 D5 matrix | 1,2 | `::test_base_url_matrix`, `::test_classify_base_url` |
| AC4 three WARNINGs | 3 | `::test_warning_insecure_http`, `::test_warning_internal_hostname`, `::test_warning_key_env_not_secret_glob`, `::test_warnings_never_fail_or_leak` |
| AC5 legacy live + lifespans | 3,4 | `::test_legacy_registry_matches_section_6_2`, `::test_legacy_tracks_live_settings`, `::test_lifespans_call_load_after_action_config` |
| AC6 fixture | 5 | `::test_providers_file_restores_legacy`, `::test_providers_file_restores_on_failure` |

## Risks / questions
- `roles:` not cross-checked against the RBAC matrix (F1 lists no such error); an unknown role is simply never matched. Orchestrator may want it in STORY-004.
- `.env` lookup is cwd-relative like pydantic; tests use `monkeypatch.chdir`.
- A test that patches `settings.V1_TOOL_MODELS` after construction bypasses `config.py:773`; the fixture forces `""`.
- No design point was found impossible.
