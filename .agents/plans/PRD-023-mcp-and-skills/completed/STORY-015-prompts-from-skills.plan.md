---
story: STORY-015
prd: PRD-023
slug: prompts-from-skills
title: "`prompts/list` and `prompts/get` from held skills"
type: NEW_CAPABILITY
complexity: small
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-23
---

# Plan: `prompts/list` and `prompts/get` from held skills

## Summary

Replace the two placeholder prompt handlers in `app/routers/mcp.py` with thin adapters over two new functions in `app/services/mcp_gateway.py`, next to `visible_catalogue`. Both read `mcp_config.held_skills(identity)` (in-memory config, `authz.holds` per skill). No database, no upstream, no usage admit, no audit row, no log of instruction text. Non-DB tests only.

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-015-prompts-from-skills.md`
- PRD sections used: §6.6 (prompts named `skill-<id>`, instructions as one `user` message), §10 (unknown prompt is `-32602`), D19 (upstream prompts not proxied), D13 (admit is per `tools/call` only, so none here), O11 (`initialize.instructions` stays unset), O5 (results not redacted; N/A, these are operator-authored instructions)
- Systems affected: `app/routers/mcp.py`, `app/services/mcp_gateway.py`, `tests/test_mcp_endpoint.py`, `tests/test_mcp_gateway.py`

## Design Decisions

- **Prompt name**: `skill-<id>`. Resolution builds `{f"skill-{s.id}": s for s in held_skills(identity)}` and looks the requested name up in it. A skill the role does not hold is not in the map, so unknown and not-held share one code path and cannot differ.
- **Constant error message** (new, in `mcp_gateway.py` beside `UNKNOWN_TOOL_MESSAGE`, line 81): `UNKNOWN_PROMPT_MESSAGE = "Unknown prompt"`, code `-32602` (`_INVALID_PARAMS`, line 76). It does not echo the name and says nothing about existence or holding. It is the only message for both cases.
- **Bad `name`** (missing, not a string, empty): `-32602` with the existing `INVALID_NAME_MESSAGE` (line 82). A malformed request is not an existence probe.
- **`prompts/get` `arguments`**: ignored. MCP prompt arguments are declared per prompt; these prompts declare none (list entries carry no `arguments` key), so there is nothing to fill. Extra or malformed `arguments` neither change the result nor raise. (Not verified against the spec text; ignoring is the safe default.)
- **Shapes**. `prompts/list` -> `{"prompts": [{"name": "skill-<id>", "description": s.description}, ...]}` in config order (what `held_skills` returns), one page, no cursor, `params` ignored (as `tools/list`). `prompts/get` -> `{"description": s.description, "messages": [{"role": "user", "content": {"type": "text", "text": s.instructions}}]}`.
- **No side effects (D19, D13)**: no `action_audit`, no `usage_limits.admit`, no `mcp_upstream` call. The router's M0 steps (auth, origin, body bound) run before handlers. Handlers do not check `mcp:connect` (STORY-011 left that out of the seam); do not add it.
- **Logging**: one INFO line per call, like `handle_tools_list` (`app/routers/mcp.py:185-201`): user and count (list), user and prompt name (get, after it resolved). Never the instruction text.
- `initialize.instructions` stays unset (O11); `prompts.listChanged` stays false (`app/routers/mcp.py:179`). No change there.

## Skills In Use

`.agents/skills/` holds only `frontend-design`; not applicable.

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Handler adapter | `app/routers/mcp.py:204-217` (`handle_tools_call`) | catch `GatewayRpcError`, raise `JsonRpcError(exc.code, exc.message)` |
| List handler + log | `app/routers/mcp.py:185-201` | call service, INFO line without text, return dict |
| Constants / errors | `app/services/mcp_gateway.py:76-85`, `:252-258`, `:512` | module constants, `GatewayRpcError(_INVALID_PARAMS, ...)` |
| Skill access | `app/services/mcp_gateway.py:403-406`, `app/services/mcp_config.py:195-202` | `mcp_config.held_skills(identity)` |
| Endpoint tests | `tests/test_mcp_endpoint.py:34-67, 410-420` | patched `resolve`, `client` fixture, `_rpc`/`_post`/`_err` |
| Service tests | `tests/test_mcp_gateway.py:36-39, 56-62` | `Skill(...)` literals, `mcp_config._config` monkeypatch via `_cfg` |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/mcp_gateway.py` | UPDATE | `UNKNOWN_PROMPT_MESSAGE`, `list_prompts(identity)`, `get_prompt(identity, params)` |
| `app/routers/mcp.py` | UPDATE | Replace the two placeholders (`:220-227`) and docstring lines 25-26 |
| `tests/test_mcp_endpoint.py` | UPDATE | `test_seam_placeholders` (`:412-419`), with a PRD-023 STORY-015 comment |
| `tests/test_mcp_gateway.py` | UPDATE | New non-DB prompt tests |

No new route, no `database.py` change: no census, Caddyfile or audit-field guard applies.

## Tasks

### Task 1: Service functions
- **File**: `app/services/mcp_gateway.py`
- **Implement**: the constant; `list_prompts(identity) -> list[dict]` and `get_prompt(identity, params) -> dict`, both sync with no I/O. `get_prompt` validates `name` (`INVALID_NAME_MESSAGE`), builds the held map, raises `GatewayRpcError(_INVALID_PARAMS, UNKNOWN_PROMPT_MESSAGE)` on a miss, ignores `params["arguments"]`. Section comment `# --- prompts/* (PRD-023 F8, D19)`; docstrings cite D19 and say no row, no upstream, no admit.
- **Mirror**: `_parse_params` (`:409-421`), `visible_catalogue` docstring style.

### Task 2: Router handlers
- **File**: `app/routers/mcp.py`
- **Implement**: `handle_prompts_list` returns `{"prompts": mcp_gateway.list_prompts(identity)}` plus the INFO line; `handle_prompts_get` calls `get_prompt` and maps `GatewayRpcError` to `JsonRpcError`. Update docstring lines 25-26. `_HANDLERS` (`:237-238`) unchanged.
- **Mirror**: `handle_tools_call`.

### Task 3: Update placeholder assertions
- **File**: `tests/test_mcp_endpoint.py::test_seam_placeholders`
- **Implement**: with the default empty config, `prompts/list` still returns `{"prompts": []}` (keep, add comment "PRD-023 STORY-015: served from held skills; an empty config holds none"). `prompts/get {"name": "x"}` becomes `(1, -32602)` (comment "PRD-023 STORY-015, D19: unknown prompt is -32602, no longer the -32601 placeholder"). Grep `tests/` for other `prompts/` hits (e.g. the seam test at `:422+`).

### Task 4: New tests (non-DB)
- **File**: `tests/test_mcp_gateway.py` (service level; two skills via `_cfg`; role holding via the file's existing identity/RBAC setup or by patching `authz.holds`), plus one wire-shape endpoint case in `tests/test_mcp_endpoint.py` (patch `mcp_config.held_skills`).
- Cases: two held -> exactly `skill-open-pull-request` and `skill-run-migration` with descriptions, config order; one held -> only it; none held -> `[]`; get held -> one `user` text message equal to `instructions`; get not-held and get unknown -> `-32602` with identical `UNKNOWN_PROMPT_MESSAGE`; name missing or non-string -> `INVALID_NAME_MESSAGE`; garbage `arguments` ignored; bare `x` does not resolve for held skill `x` (only `skill-x`); no side effects: patch `action_audit.record`, `action_audit.record_outcome`, `usage_limits.admit`, `mcp_upstream.list_tools`, `mcp_upstream.call_tool` to raise `AssertionError`, run list and get.

## End-to-End Tests

- [ ] `TestClient` over `mcp_router.router`, patched `resolve` and config: `prompts/list` then `prompts/get` give the wire shape above; unknown and not-held `prompts/get` give identical `{"code": -32602, "message": "Unknown prompt"}`.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider -m "not db" tests/test_mcp_endpoint.py tests/test_mcp_gateway.py tests/test_untouched_app.py
```
Docker is down locally, hence `-m "not db"`; CI covers DB tests. No test is renamed or removed, so the PII guard is not needed.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 list only held, with descriptions | 1, 2 | `tests/test_mcp_gateway.py::test_prompts_list_only_held_skills` (new) |
| AC2 get returns one `user` message | 1, 2 | `tests/test_mcp_gateway.py::test_prompts_get_returns_instructions_as_user_message` (new) |
| AC3 `-32602`, same message both cases | 1, 3 | `tests/test_mcp_gateway.py::test_prompts_get_unknown_and_not_held_share_one_message` (new); `tests/test_mcp_endpoint.py::test_seam_placeholders` |
| AC4 no row, no upstream, no admit | 1, 2 | `tests/test_mcp_gateway.py::test_prompts_touch_no_audit_usage_or_upstream` (new) |

## Risks

- Default config has no skills, so the endpoint seam test sees `[]`: expected.
- No size cap on instructions: PRD sets none; text is operator-authored config.
