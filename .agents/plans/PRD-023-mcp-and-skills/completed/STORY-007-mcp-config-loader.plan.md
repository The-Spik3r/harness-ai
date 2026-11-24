---
story: STORY-007
prd: PRD-023
slug: mcp-config-loader
title: "`mcp_config`: servers, skills, aliases, cross-validation, digest, loaded in both lifespans"
type: NEW_CAPABILITY
complexity: large
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-22
---

# Plan: mcp_config loader

## Summary

New `app/services/mcp_config.py`, modelled on `app/services/action_config.py`: frozen dataclasses, a module-level `_config` swapped as the last statement of `load()`, strict YAML, `MCPConfigError` in the `"<source>: <node>: <message>"` shape. `load()` is a no-op when `MCP_ENABLED` is false; when on it parses `MCP_CONFIG_FILE`, resolves credential env values, and cross-validates against the loaded action policy and the loaded role matrix. Pure accessors `held_skills` / `visible_tools` read `authz.holds` (no RBAC bypass). Wired into both lifespans right after `action_config.load()`.

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-007-mcp-config-loader.md` (AC text lives there)
- PRD sections: 6.6, 6.8 (`v1_aliases`), 9.1, 9.3, D5, D6, O2, O7, User Story 8 (PRD.md:156 message)
- Systems: `app/services/mcp_config.py` (new), `app/main.py`, `chat_ui/chat_ui/chat_ui.py`, examples, tests

## Design Decisions (binding ones from the orchestrator, plus plan choices)

- **Enabled switch.** `load()` returns at once when `settings.MCP_ENABLED` is false: opens nothing; it sets `_config = EMPTY_CONFIG` so a previous test's config cannot leak (assignment only, no file). Enabled + empty `MCP_CONFIG_FILE` -> `MCPConfigError` (source `MCP_CONFIG_FILE`, message says set a path or MCP_ENABLED=false). Settings are read at call time (`action_config.py:1225` shape).
- **Source/node shape.** `source = f"MCP_CONFIG_FILE '{path}'"`; `_fail(source, *parts)` as `action_config.py:379`. Nodes: `servers.<id>.auth.token_env`, `skills.<id>.tools[<i>]` (0-based; Story 8's `[2]` is the third entry). Story 8 message verbatim: `... skills.open-pull-request.tools[2]: 'github__create_pullrequest' has no mcp_tools or mcp_opaque_tools entry in ACTION_POLICY_FILE`.
- **Strictness.** `strict_yaml.safe_load`; `yaml.YAMLError` -> "is not valid YAML" (covers duplicate keys); `OSError`/`UnicodeDecodeError` -> "cannot be read" (`action_config.py:1228-1240`). A local `_check_keys(source, where, body, allowed, required)` copied from `action_config.py:971` (private there; copy the ~8 lines, as action_config did from pattern_config). Unknown keys refused at top level (`servers`, `skills`, `v1_aliases`, all optional), server, `auth`, skill and `v1_aliases`.
- **Server.** id `[a-z0-9][a-z0-9-]{0,31}` (same literal as `action_config.py:407`; no `_`, O7). `url`: `urllib.parse.urlsplit`, scheme `http|https`, non-empty hostname; `http` needs `allow_insecure: true` (bool only). Added rule: userinfo in the URL refused (a credential in a URL would reach the digest and logs). `auth` optional, default `none`; `type` in `bearer|header|none`; bearer requires `token_env`, header requires `name` + `value_env`, none takes no keys. `timeout_seconds` default `settings.MCP_CALL_TIMEOUT_SECONDS`, range 1-600 (PRD 9.3, per-server override); `max_result_bytes` default `settings.MCP_MAX_RESULT_BYTES`, `>= 1024` (PRD 9.3). Reject `bool` for ints. Defaults are resolved at load so the digest holds effective values.
- **Header name.** Refused: `Authorization` (case-insensitive), the hop-by-hop set (`connection, keep-alive, proxy-authenticate, proxy-authorization, proxy-connection, te, trailer, transfer-encoding, upgrade`), any `mcp-*`; must also be an HTTP token (`[A-Za-z0-9!#$%&'*+.^_`|~-]+`).
- **Credentials.** `os.environ.get(name)`; unset or `""` -> error naming the env var NAME only (never a value or the URL). The value lives in `McpAuth._secret: str = field(default="", repr=False, compare=False)`. Narrow accessor `upstream_auth_headers(server_id) -> dict[str, str]` (bearer -> `{"Authorization": "Bearer <v>"}`, header -> `{name: v}`, none -> `{}`) for STORY-010; the only reader. Nothing calls `dataclasses.asdict` on config; the digest uses an explicit `_canonical()`.
- **Skills.** id checked with `authz.is_skill_permission(f"skill:{id}")` (one pattern, `authz.py:75`); `version` non-empty `str` (unquoted `1.0` parses as float: refuse with a "quote it" hint); `description` and `instructions` required `str`; `tools` non-empty list of non-empty strs; `requires` optional list of strs, each in `authz.ACTION_PERMISSIONS`.
- **Tool split.** Public `split_tool(name) -> (server, tool)` at the FIRST `__` (O7); `server` must be configured, `tool` non-empty; no `__` -> malformed. Reusable by STORY-013/016.
- **v1_aliases.** Optional; `prefixes` list of non-empty strs fullmatching `[A-Za-z0-9_-]+`, no duplicates. Absent -> `()` (no aliases: PRD 6.8 crosses into gateway mappings only for prefixes the operator declared; orchestrator decision). `examples/mcp.yaml` declares both confirmed prefixes explicitly. Stored as `McpConfig.v1_prefixes`.
- **Cross-validation (after parse, in this order).** (1) each skill tool has an entry in `action_config.get_policy().mcp_tools[server]` or `.mcp_opaque_tools[server]`; (2) every server id in either policy section is in `servers` (node `ACTION_POLICY_FILE mcp_tools.<server>`); (3) for each role in `sorted(authz.ROLE_PERMISSIONS)`, each `skill:<id>` it holds names a defined skill (node `roles.<role>`); (4) it also holds every `requires` of that skill (O2; message names role, skill, missing permission). `authz.ROLE_PERMISSIONS` is a public module attribute, so no authz accessor is added.
- **Visibility.** `held_skills(identity)` = defined skills, config order, with `authz.holds(identity, f"skill:{id}")`. Verified: `holds` reads `ROLE_PERMISSIONS` only (`authz.py:240`), no `RBAC_ENABLED` bypass, so no direct matrix check is needed; RBAC off + built-in matrix -> empty. `visible_tools` = union over held skills grouped by server -> `MappingProxyType[str, frozenset[str]]` (bare tool names; servers with no tool absent). `mcp:connect` is not checked (STORY-011); withheld tools are STORY-012. Both pure over `_config`.
- **Digest.** `mcp_config_digest(config=None) -> "sha256:<hex>"` over canonical JSON (`sort_keys`, `separators=(",", ":")`, `ensure_ascii=False`, `action_config.py:914` shape): servers (url, allow_insecure, auth type, env var NAME, header name, timeout_seconds, max_result_bytes), skills (version, description, instructions, tools in order, requires in order), `v1_aliases`. No secret values. MCP disabled -> `_config` is empty, so the digest is the empty-config constant.
- **Warning.** After validation, before the swap: one `logger.warning` per skill tool whose `<server>__<tool>` exceeds 55 characters, naming skill and tool (STORY Technical Notes; `tests/corpora/mcp/SOURCES.md` Clients).
- **Failure keeps the old config**: `_config` is assigned last.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; the chat UI change is one registration line).

## Patterns to Follow

| Category | Source | Mirror |
|----------|--------|--------|
| Error class/shape | `app/services/action_config.py:75`, `:379` | `MCPConfigError`, `_fail` |
| Key checks | `action_config.py:971-995` | unknown then missing key, `_mapping` |
| Module state | `action_config.py:841`, `:1191-1243` | `get_config`; swap last; settings read at call time |
| Digest | `action_config.py:878`, `:914` | explicit canonical dict, never the dataclass |
| Authz | `authz.py:75`, `:109`, `:240` | `is_skill_permission`, `ROLE_PERMISSIONS`, `holds` |
| Lifespan (API) | `app/main.py:24` | line after `action_config.load()` |
| Lifespan (UI) | `chat_ui/chat_ui/chat_ui.py:284` | `register_lifespan_task` after action_config, comment in the existing style |
| Tests | `tests/test_action_config.py:1117`, `tests/test_main.py:508`, `tests/test_chat_ui_startup_guard.py:114-125` | example loads; lifespan order; probe keys |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/mcp_config.py` | CREATE | the module |
| `app/main.py` | UPDATE | import `mcp_config` (line 13); `mcp_config.load()` after line 24 |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | import (services list, line ~16); `app.register_lifespan_task(mcp_config.load)` after line 284 |
| `examples/mcp.yaml` | CREATE | PRD 6.6 sample (servers, skills, v1_aliases) |
| `examples/mcp_action_policy.yaml` | CREATE | `mcp_tools` / `mcp_opaque_tools` sample. `examples/action_policy.yaml` is pinned (`tests/test_action_config.py:1121-1141` asserts 9 tools and the exact `opaque_tools`; `tests/test_action_corpus.py:158` loads it), so it is NOT edited |
| `tests/test_mcp_config.py` | CREATE | all loader tests (no DB) |
| `tests/test_main.py` | UPDATE | lifespan-order test for `mcp_config` (TestClient; already DB-backed) |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | probe keys `mcp_load_registered` / `mcp_load_order_ok` + asserts |

## Tasks

### Task 1: `app/services/mcp_config.py`
- Implement everything under Design Decisions. Dataclasses (`frozen=True`, tuples, `MappingProxyType`): `McpAuth(type, env_name, header_name, _secret)`, `McpServer(id, url, allow_insecure, auth, timeout_seconds, max_result_bytes)`, `Skill(id, version, description, instructions, tools, requires)`, `McpConfig(servers, skills, v1_prefixes)`. Plus `EMPTY_CONFIG`, `_config`, `get_config()`, `held_skills`, `visible_tools`, `upstream_auth_headers`, `split_tool`, `mcp_config_digest`, `load`. Docstrings cite PRD-023 decisions as `authz.py` does.
- Mirror: `action_config.py` refs above.
- Validate: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_mcp_config.py`

### Task 2: lifespans
- `app/main.py` and `chat_ui/chat_ui/chat_ui.py` as in the table. Order: authz, ..., action_config, mcp_config, then provider_registry.
- Validate: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 3: examples
- `examples/mcp.yaml` per PRD 6.6, header comments in the `examples/action_policy.yaml` style (required env vars; `allow_insecure` is recorded in the digest). `examples/mcp_action_policy.yaml`: the PRD 6.6 policy sections, mapping every tool the example skills use (`github.create_branch`, `push_files`, `create_pull_request`; `postgres-staging.query`). If `target: "files[].path"` does not validate under the real adapter, use a form that does and say so in the report. Note: PRD 6.6 spells the tool `create_pull_request`; Story 8's typo `create_pullrequest` is only the failing example.

### Task 4: tests (`tests/test_mcp_config.py`, no DB)
- Fixtures: tmp-file writers; `monkeypatch.setenv` for the example env vars; `monkeypatch.setattr(settings, ...)`; restore `mcp_config._config`, `action_config._policy` and `authz.ROLE_PERMISSIONS` by `monkeypatch.setattr` to their current values first. The policy loads through `action_config.load()` with `ACTION_POLICY_FILE=examples/mcp_action_policy.yaml`; roles via `monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {...})`.
- One parametrized case id per rule, each asserting `MCPConfigError`, file path, node and failing text: unknown key (top, server, auth, skill, v1_aliases), server id pattern (uppercase, `_`, 33 chars), url scheme / relative, `http` without `allow_insecure`, bad `auth.type`, `token_env` unset, `token_env` empty, `value_env` unset, header `Authorization` / `authorization` / `Connection` / `Mcp-Session-Id`, `timeout_seconds` 0 and 601, `max_result_bytes` 1023, skill id pattern, empty `tools`, malformed tool (no `__`, `github__`, `nope__x`), unmapped tool (full-message equality with Story 8's text), bad `requires`, `skill:ghost` granted, role holding a skill without its `requires`, empty alias prefix, bad prefix chars, duplicate YAML key, policy `mcp_tools` server absent from `servers`.
- Disabled: `MCP_ENABLED=false` with `MCP_CONFIG_FILE` set to a path and `Path.read_text`/`open` patched to fail if touched -> returns; `get_config()` empty; `visible_tools` empty for an admin. Enabled + `""` -> `MCPConfigError`. A failing load keeps the previous config (`is` check).
- Valid config: contents of `get_config()`; `held_skills` / `visible_tools` for roles with and without grants; RBAC off + built-in matrix -> empty; RBAC off + a granting matrix -> non-empty (proves no bypass); two skills sharing a tool expose it once; values are `frozenset`.
- Digest: version change changes it; changing only a credential env value does not; changing an env var NAME does; disabled digest is stable and differs from the example's; file key order does not matter.
- Secrets: sentinel `s3ntinel-secret-value` as the env value; absent from `repr(get_config())`, `json.dumps(mcp_config._canonical(...))`, `caplog.text` (DEBUG) and every `str(MCPConfigError)` from the failure cases run with the sentinel set; `upstream_auth_headers("github")` does carry it (the one sanctioned path).
- Warning: a 56-char `<server>__<tool>` logs exactly one WARNING naming skill and tool; a 55-char one logs none; load succeeds either way.
- Examples: `examples/mcp.yaml` + `examples/mcp_action_policy.yaml` + a matrix granting both skills (the `run-migration` role also holds `action:sql:ddl`) load.

### Task 5: lifespan tests
- `tests/test_main.py`: copy `test_lifespan_runs_action_config_load_after_authz_load` (:508), recording `authz`, `action_config`, `mcp_config` -> exact order list.
- `tests/test_chat_ui_startup_guard.py`: probe adds `mcp_load_registered`, `mcp_load_order_ok` (`authz.load < action_config.load < mcp_config.load < authz.check_bootstrap`) and a call of `mcp_config.load()` (no-op, disabled); assert beside `action_load_registered` (:321, :339).

## End-to-End Tests
- [ ] Real `app` under `TestClient` with `MCP_ENABLED=true`, the example files, a granting matrix and env set: lifespan boots, `get_config()` holds both skills; with `MCP_CONFIG_FILE` broken, boot raises `MCPConfigError`.
- [ ] Chat UI probe (the guard test) shows the task registered in order.

## Validation
```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_mcp_config.py tests/test_authz.py tests/test_chat_ui_startup_guard.py tests/test_untouched_app.py
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_main.py -k "lifespan"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_action_config.py -k "example or mcp"
```
`test_main.py` lifespan tests need the libSQL server; `test_mcp_config.py` does not. No full suite (CI).

## Acceptance Criteria -> Tasks -> Tests

| AC | Task | Test |
|----|------|------|
| AC1 each 9.3 rule, Story 8 message | 1, 4 | `tests/test_mcp_config.py::test_rule_*` (one id per rule), `::test_unmapped_tool_message_is_story_8_exact` |
| AC2 disabled opens no file; enabled + empty fails | 1, 4 | `::test_disabled_opens_no_file`, `::test_enabled_without_file_fails` |
| AC3 accessors; RBAC off empty | 1, 4 | `::test_held_skills_and_visible_tools`, `::test_rbac_off_built_in_matrix_sees_nothing` |
| AC4 digest and secrecy | 1, 4 | `::test_digest_*`, `::test_secret_value_appears_nowhere` |
| AC5 both lifespans, examples load | 2, 3, 5 | `tests/test_main.py::test_lifespan_runs_mcp_config_load_after_action_config_load`, startup-guard probe asserts, `::test_examples_load` |

## Risks / open questions
- Rules added beyond 9.3 (flag to orchestrator): userinfo in URL refused; non-string `version` refused; duplicate alias prefixes refused.
- Absent `v1_aliases` means no aliases (`()`), orchestrator decision. Absent `servers`/`skills` are allowed (empty), not an error.
- Env var names are only checked for non-empty `str`; no identifier pattern is imposed (not in 9.3).
