---
story: STORY-017
prd: PRD-023
slug: admin-api
title: "Admin API: `GET /audit/actions` MCP filters and fields, `GET /skills`"
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-23
---

# Plan: Admin API for MCP audit and skills

## Summary

Extend `GET /audit/actions` with `?surface=`, `?server=`, `?outcome=`, `?linked=` (pushed down into `list_action_decisions` as fixed SQL clauses, ANDed with scoping) and the PRD 10 entry fields; add read-only `GET /skills` (`stats:read`) listing skills with holding roles and the config digest. No credential or URL is read.

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-017-admin-api.md`
- PRD sections used: 4 (API and admin console), 6.9 (D21), 10, F11
- Systems affected: `app/routers/admin.py`, `app/db/database.py`, `app/models/schemas.py`, `app/services/authz.py`, `Caddyfile`, tests

## Design Decisions

- **Filters** (binding): `linked=true` -> `linked_decision_id IS NOT NULL`; `linked=false` -> `surface = 'mcp' AND linked_decision_id IS NULL` (PRD 6.8: an unlinked gateway call is a first-class filter). All combine with AND with each other, with `user_id`/`decision`/`audit_id` and with the scoping. `server` is `mcp_server = ?` (exact; unknown id = empty list). Only values are bound.
- **Validation** = FastAPI `Query` types, 422 before the handler (as `decision`, `admin.py:146,157`). `surface: Optional[Literal["v1","mcp"]]`; `outcome: Optional[McpOutcome]` imported from `app/db/models.py:545` (no restated literals); `linked: Optional[bool]`; `server: Optional[str] = Query(None, min_length=1, max_length=64)`. No surface vocabulary constant exists in code (`action_audit.py:293` hardcodes "mcp"), so the `surface` Literal is restated in admin.py with a pin test, exactly as `ActionDecisionFilter` (`admin.py:142-146`, pinned by `tests/test_admin_actions.py:254`).
- **Scoping unchanged**: the `authorize(...AUDIT_READ_ALL/OWN)` block (`admin.py:169-179`) is not touched; new filters only narrow.
- **Entry fields** (names stable for STORY-018), added to `ActionDecisionEntry` after `policy_digest`: `surface: str`, `mcp_server: Optional[str]`, `skills: Optional[List[str]]` (decoded from the JSON column; NULL stays `None`; a corrupt value is a 500, like `classifications`), `linked_decision_id: Optional[int]`, `outcome: Optional[str]`, `duration_ms: Optional[int]`, `result_bytes: Optional[int]`, `result_flags: Optional[List[Any]]` (JSON-parsed; elements are strings or `{"list","pattern_id"}` / `{"uninspected"}` dicts, STORY-014; see `models.py:505`). **Not exposed**: `result_hash`, `arguments_canonical_hash`, `mcp_config_digest`: PRD 10 lists exactly the eight, and the PRD-016 precedent keeps storage aids off the wire (`schemas.py:360-364`). The new fields get defaults so the construction in `tests/test_schemas.py:215` keeps working.
- **`GET /skills`** response (field names binding for STORY-018): `{"skills":[{"id","version","description","tools":[...],"requires":[...],"roles":[...]}],"mcp_config_digest": str|null}`. `roles` = sorted roles whose `authz.ROLE_PERMISSIONS` set holds `skill:<id>` (PRD 10 key is `roles`; empty when none, which is every built-in role, O1). Skill order = config order. Never `instructions`, never server URLs or auth `name`/`*_env`: the response model is a fixed whitelist and the `Skill` dataclass (`mcp_config.py:143`) holds none of them.
- **`MCP_ENABLED=false`**: the route stays mounted (admin router is always mounted, so no route-census special case) and returns **200** `{"skills":[],"mcp_config_digest":null}`. Chosen over 404 so the console renders one empty state without error handling; `stats:read` is still enforced first. Document in the handler docstring. Gate on `settings.MCP_ENABLED` read per call (as `query_pipeline.py:164`), not on `get_config()` being empty, so an enabled deployment with zero skills returns its real digest.
- **Roles read**: new `authz.roles_holding(permission) -> tuple[str, ...]` beside `holds()` (`authz.py:240`), reading the module global at call time (`load()` rebinds `ROLE_PERMISSIONS`, `authz.py:198`, so a `from ... import ROLE_PERMISSIONS` would go stale). No RBAC bypass, like `holds`.
- **`list_action_decisions`** (`database.py:3594`) gains four keyword params defaulted to None. Census (`test_db_resilience_retry.py:676`, `K.READ`) unchanged: no new function and no new `_session` caller. Still one SELECT.

## Skills In Use

None: `.agents/skills/` holds only `frontend-design` (UI; no UI here, STORY-018 owns it).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Query filters | `admin.py:153-190`, `database.py:3615-3626` | optional Query params -> kwargs -> fixed clauses + bound values |
| Permission gate | `admin.py:220-224` | `dependencies=[Depends(require_permission(PERMISSION_STATS_READ))]` gives the 403 |
| Response model | `schemas.py:356-392` | read model, no validators, defaults for new fields |
| JSON column decode | `admin.py:213-215` | decode in `_action_entry`, no catch |
| Tests | `tests/test_admin_actions.py:326-340` | recorder monkeypatch of `app.routers.admin.list_action_decisions`; `temp_db` for SQL |
| Config in tests | `tests/test_mcp_gateway.py:60`, `test_mcp_endpoint.py:92` | `monkeypatch.setattr(mcp_config, "_config", McpConfig(...))`, `settings.MCP_ENABLED` |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | `list_action_decisions(..., surface, mcp_server, outcome, linked)` + docstring |
| `app/models/schemas.py` | UPDATE | new `ActionDecisionEntry` fields; `SkillEntry`, `SkillsResponse` |
| `app/services/authz.py` | UPDATE | `roles_holding()` |
| `app/routers/admin.py` | UPDATE | query params, `_action_entry` fields, `GET /skills` |
| `Caddyfile` | UPDATE | add `/skills` to `@backend_routes` (line 5) |
| `tests/test_caddyfile_routes.py` | UPDATE | `/skills` in `EXPECTED_MATCHER` (+ `/skillsx` in `STATIC_PATHS`) |
| `tests/test_admin_actions.py` | UPDATE | field set, kwargs assertion (Task 5) |
| `tests/test_admin_mcp.py` | CREATE | filters, entry fields, `/skills` |

## Tasks

### Task 1: DB reader filters
- **File**: `app/db/database.py` `list_action_decisions`
- **Implement**: params `surface`, `mcp_server`, `outcome`, `linked: Optional[bool]`. Clauses `surface = ?`, `mcp_server = ?`, `outcome = ?`; `linked is True` -> `linked_decision_id IS NOT NULL`; `linked is False` -> `surface = 'mcp' AND linked_decision_id IS NULL` (fixed string). Test with `is True/False`, never truthiness. Extend the docstring (D21, PRD 6.8).
- **Mirror**: `database.py:3615-3626`

### Task 2: Schemas
- **File**: `app/models/schemas.py`. Fields above on `ActionDecisionEntry` (comment: PRD-023 D21, why hashes/digest are absent). Add `SkillEntry(id, version, description, tools: List[str], requires: List[str], roles: List[str])` and `SkillsResponse(skills: List[SkillEntry], mcp_config_digest: Optional[str] = None)`.

### Task 3: `authz.roles_holding`
- **File**: `app/services/authz.py`, after `holds()`: sorted roles whose set contains the permission; docstring cites D6 and the no-bypass rule.

### Task 4: Router
- **File**: `app/routers/admin.py`. Add the params to `get_audit_actions`, pass them to the reader, extend its docstring (including that `linked=false` excludes `/v1` rows). `_action_entry`: decode `skills` and `result_flags` when not None. `GET /skills` with the `stats:read` dependency and `response_model=SkillsResponse`: off -> empty + `None`; on -> map `mcp_config.get_config().skills` with `authz.roles_holding(f"skill:{s.id}")` and `mcp_config.mcp_config_digest()`. Import `settings`, `authz`, `mcp_config`, `McpOutcome`.
- **Mirror**: `admin.py:220-231`, `:153-190`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 5: Existing tests and Caddy
- `Caddyfile:5`: append `/skills`. `test_caddyfile_routes.py`: `"/skills"` in `EXPECTED_MATCHER` (comment PRD-023 STORY-017), `/skillsx` in `STATIC_PATHS`. The route census covers it because the admin router is always mounted.
- `tests/test_admin_actions.py:344`: `_SECTION_10_FIELDS` grows by the eight names (comment citing PRD-023 D21); keep the "no `arguments_*`" asserts and add `result_hash`, `arguments_canonical_hash`, `mcp_config_digest` not in entry. Lines `337-339`: the kwargs dict gains `surface/mcp_server/outcome/linked: None` (comment PRD-023 STORY-017). `test_admin_state.py:415` uses `**_kwargs` and is fine.

### Task 6: New tests `tests/test_admin_mcp.py`
- Not db (recorder monkeypatch): every filter reaches the reader; `?linked=maybe`, `?surface=x`, `?outcome=bogus`, `?server=` -> 422 with the reader not called; `get_args` of the `surface` Literal equals `("v1","mcp")`; the `outcome` annotation's args equal `MCP_OUTCOME_VALUES`.
- db (`temp_db`, rows via `insert_action_decisions`): `surface=mcp&outcome=timeout`; `server=github`; `linked=true` returns only linked rows; `linked=false` returns unlinked mcp rows and not v1 rows; filter ANDs with `decision`; an `audit:read:own` user sees only own rows with filters applied; entry carries the eight fields, `skills` is a list, `result_flags` parsed (both flag shapes); a v1 row reads `surface="v1"` and nulls.
- `/skills` (break-glass `ADMIN_TOKEN` header; monkeypatch `authz.ROLE_PERMISSIONS`, `settings.MCP_ENABLED`, `mcp_config._config`): 200 shape, sorted `roles`, `[]` when none hold; `MCP_ENABLED=false` -> 200 empty + null digest; 403 for a role without `stats:read` (reuse the `test_admin_auth.py` identity pattern). Secret scan: two servers with distinct URLs, `auth.name`, `token_env`/`value_env` and skill `instructions` text; assert none of those strings occur in `response.text`.

## End-to-End Tests
- [ ] `TestClient(app)` `GET /audit/actions?surface=mcp&linked=false` over seeded rows (db, CI)
- [ ] `GET /skills` with a loaded config, `MCP_ENABLED` on and off
- [ ] No `chat_ui/` change (STORY-018 consumes the field names above)

## Validation
```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider -m "not db" tests/test_admin_mcp.py tests/test_admin_actions.py tests/test_caddyfile_routes.py tests/test_schemas.py tests/test_untouched_app.py tests/test_actions_view.py tests/test_admin_state.py
```
`db` tests (incl. the unchanged retry census) run in CI; Docker is down locally. No test is renamed or removed, so no `_DELIBERATELY_SUPERSEDED_TESTS` entry.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 filters, fields, scoping | 1, 2, 4 | `test_admin_mcp.py` db tests; `test_admin_actions.py::test_entry_has_exactly_the_section_10_fields` |
| AC2 invalid value -> 422 | 4 | `test_admin_mcp.py` parametrized 422 (not db) |
| AC3 `/skills` shape, 403, off = empty 200, no secrets | 3, 4 | `test_admin_mcp.py` skills tests incl. the serialised-response scan |

## Risks
- `ActionDecisionEntry` grows: run `test_untouched_app.py` and `test_actions_view.py`; if the latter fails on extra keys, report rather than edit chat_ui.
- `linked=false` deliberately excludes `/v1` rows; the docstring says so, so STORY-018's filter copy matches.
