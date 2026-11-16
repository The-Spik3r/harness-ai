---
story: STORY-016
prd: PRD-016
slug: audit-actions-endpoint-and-stats
title: GET /audit/actions with audit scoping, and the three action counts on /stats
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-016-action-policy-rules
created: 2026-11-15
---

# Plan: GET /audit/actions with audit scoping, and the three action counts on /stats

## Summary

This story exposes STORY-015's `action_decisions` table over the API (PRD-016 Sections 4, 7 F11, 9.1, 10). It has three parts.

1. **`GET /audit/actions`** in `app/routers/admin.py`, next to `get_audit`. It copies `get_audit`'s two-step `authorize` scoping (`audit:read:all` reads every user's rows, `audit:read:own` reads only the caller's, neither gives 403 `Permission denied: audit:read:own`). It reads `list_action_decisions(limit, user_id, decision)`. `?limit=` is 1–500 with a default of 100, and `?decision=` is `allow|flag|deny`. Both are validated by FastAPI, so a bad value gives 422.
2. **Schemas** in `app/models/schemas.py`. `ActionClassificationEntry` is `{rule, kind, detail}`. `ActionDecisionEntry` has exactly the 15 fields of the Section 10 example. `ActionsResponse` is `{entries}`. `StatsResponse` gains `actions_denied`, `actions_flagged` and `actions_allowed`, each an int defaulting to 0.
3. **`/stats`** reads `count_action_decisions()` and maps its keys onto the three fields.

Two changes are outside the story text but required by the code:
- **Caddyfile.** The `@backend_routes` matcher lists `/audit` as an exact path, so in production Caddy would send `/audit/actions` to the static file server. `tests/test_caddyfile_routes.py::test_every_harness_route_is_proxied_by_caddy` catches this. The fix adds the exact token `/audit/actions`.
- **Pinned `/stats` key sets.** Six existing assertions pin the exact `/stats` key set or body, and each gains the three keys with a PRD-016 F11 comment.

## User Story

As a security admin
I want to read recent action decisions over the API, filtered by decision and scoped by my audit permission
So that denied actions can be reviewed and exported like the rest of the audit

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-016-audit-actions-endpoint-and-stats.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md` (Sections 4 line 100-101, 6.10, 6.11 line 423-424, 7 F11 line 513, 9.1 line 538, 10 line 572-602)
- Depends on: STORY-015 (`0ceb250`), done.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | `app/routers/admin.py`, `app/models/schemas.py`, `Caddyfile`, tests |
| Story | STORY-016 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (visual UI design). This story has no UI; the Actions view is STORY-019. Story frontmatter `skills: []`. | — |

---

## Patterns to Follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| ROUTE + SCOPING | `app/routers/admin.py:22-35` | `require_identity` dependency, then `authorize(ALL)` → `scope_user_id=None`; on `PermissionDenied`, `authorize(OWN)` → `scope_user_id=identity.user_id`; else `HTTPException(403, f"Permission denied: {exc.permission}")` |
| ROW → ENTRY | `app/routers/admin.py:37-81` | List comprehension building the response model from the DB dataclass, with a comment on each passthrough citing the PRD |
| STATS | `app/routers/admin.py:84-146` | `require_permission(PERMISSION_STATS_READ)` as a route dependency; plain `def` (threadpool); long rationale comment; `StatsResponse(...)` with per-PRD comment on additive fields |
| SCHEMAS | `app/models/schemas.py:171-267` | Pydantic `BaseModel`, `Optional[...] = None`, `List[...]`, long comments citing PRD sections; additive `StatsResponse` fields default to 0 (`:263-267`) |
| DB READS | `app/db/database.py:2311-2360` | `list_action_decisions` (id DESC, filters AND-ed, `decision` not validated: "STORY-016's router rejects an unknown value with 422"); `count_action_decisions()` → `{"allow","flag","deny"}` all keys present |
| ROW MODEL | `app/db/models.py:578-605`, `:408` | `ActionDecisionRow` (`classifications` is JSON text: "Decoding it belongs to the reader (STORY-016's API)"); `ACTION_DECISION_VALUES = ("allow","flag","deny")` |
| JSON SHAPE | `app/services/action_audit.py:128-141` | `classifications` = `[{"rule", "kind" (str or null), "detail" (str)}]` |
| 403 TESTS | `tests/test_audit_router.py:242-294` | `insert_user(User(..., role="auditor"/"user"/"guest", token_hash=hash_token(tok)))`, `Bearer tok`; guest → 403 |
| PRE-DB REJECT | `tests/test_audit_router.py:19-38` | `_fail_if_called` monkeypatched onto `app.routers.admin.<fn>`; no/wrong token → 401/403 |
| STATS TESTS | `tests/test_stats_router.py:188-209` (zero body), `:116-130`, `:273-287`, `:441-455` | Exact key sets / exact bodies with `# PRD-013 6.10: ... (STORY-006).` comments on additive keys |

No `Query(...)` is used anywhere in `app/` yet (`grep -rn "Query(" app/` is empty). This route is the first to validate query parameters. FastAPI's default 422 body `{"detail": [...]}` is the error shape, the same one already returned for request-body validation errors.

### Naming / scoping (copy exactly)
```python
# SOURCE: app/routers/admin.py:22-35
@router.get("/audit", response_model=AuditResponse)
def get_audit(identity: Identity = Depends(require_identity)) -> AuditResponse:
    try:
        authorize(identity, PERMISSION_AUDIT_READ_ALL)
        scope_user_id = None
    except PermissionDenied:
        try:
            authorize(identity, PERMISSION_AUDIT_READ_OWN)
        except PermissionDenied as exc:
            raise HTTPException(
                status_code=403, detail=f"Permission denied: {exc.permission}"
            ) from exc
        scope_user_id = identity.user_id
```

### Masking
`GET /audit` applies **no per-role masking**. It returns the same fields to `audit:read:all` and `audit:read:own` callers, and the scoping is a row filter only (`admin.py:36-81`). The new route mirrors that. `target_preview` is already redacted at write time (`action_audit.py:24-37`). `arguments_preview` and `arguments_hash` are left off the entry entirely (Section 10, the same reasoning PRD-009 D5 gives for `dedup_key`).

### Tests
```python
# SOURCE: tests/test_audit_router.py:285-294
def test_identity_lacking_both_audit_permissions_returns_403(temp_db):
    insert_user(
        User(user_id="outsider", role="guest", token_hash=hash_token("guest-token"))
    )
    response = client.get("/audit", headers={"Authorization": "Bearer guest-token"})
    assert response.status_code == 403
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/schemas.py` | UPDATE | `ActionClassificationEntry`, `ActionDecisionEntry`, `ActionsResponse`; `StatsResponse` + 3 ints |
| `app/routers/admin.py` | UPDATE | `GET /audit/actions`; `/stats` reads `count_action_decisions()` |
| `Caddyfile` | UPDATE | `@backend_routes` gains the exact path `/audit/actions` |
| `tests/test_admin_actions.py` | CREATE | Endpoint, scoping, validation, entry shape, `/stats` counts |
| `tests/test_caddyfile_routes.py` | UPDATE | `EXPECTED_MATCHER` gains `/audit/actions` (PRD-016 F11 comment) |
| `tests/test_stats_router.py` | UPDATE | 4 pinned key sets/bodies gain the 3 keys (`:116`, `:192`, `:273`, `:441`) |
| `tests/test_reporting_invariance.py` | UPDATE | 2 pinned key sets gain the 3 keys (`:277`, `:564`) |
| `tests/test_schemas.py` | UPDATE | `test_stats_response_shape` model_dump (`:208-222`) gains 3 zero keys; new shape tests for the action schemas |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Schemas

- **File**: `app/models/schemas.py`
- **Action**: UPDATE
- **Implement**:
  - After `AuditResponse` (`:248-250`), add:
    - `class ActionClassificationEntry(BaseModel)`: `rule: str`, `kind: Optional[str] = None`, `detail: str`. Comment: the decoded form of the `classifications` JSON column (`action_audit._classifications_json`, PRD-016 6.10). `kind` is null for `tool.unknown` and `tool.malformed`.
    - `class ActionDecisionEntry(BaseModel)`, with the fields in the Section 10 example order: `id: int`, `timestamp: str`, `audit_id: Optional[int] = None`, `user_id: str`, `role: str`, `tool_call_id: str`, `tool_name: str`, `operation_kind: Optional[str] = None`, `target_preview: Optional[str] = None`, `decision: str`, `rule: str`, `reason: str`, `granted_by: Optional[str] = None`, `classifications: List[ActionClassificationEntry]`, `policy_digest: str`.
      - Comment: `arguments_preview` and `arguments_hash` are deliberately absent (Section 10; PRD-009 D5 reasoning). `reason` is the stored column, returned as stored (orchestrator decision, STORY-014/015 plans; PRD 6.10 amended).
      - `session_id` is also absent, because the Section 10 example (and therefore AC 3's "exactly the fields") omits it. See Q1.
      - Read model, no validators (the `AuditQueryEntry.session_id` rationale, `:196-199`).
    - `class ActionsResponse(BaseModel)`: `entries: List[ActionDecisionEntry]`. Comment: no `total`, unlike `AuditResponse`. Section 10/F11 define only `entries`, and `count_action_decisions()` takes no `user_id`, so a scoped total has no source (F10).
  - In `StatsResponse` (`:253-267`), append `actions_denied: int = 0`, `actions_flagged: int = 0`, `actions_allowed: int = 0`, with the comment `# PRD-016 F11 / Section 10: decision counts over the whole action_decisions table, 0 when empty.`
- **Mirror**: `app/models/schemas.py:171-267`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Route and /stats

- **File**: `app/routers/admin.py`
- **Action**: UPDATE
- **Implement**:
  - Imports:
    - `from typing import Literal, Optional`
    - `from fastapi import ... Query`
    - `count_action_decisions` and `list_action_decisions` from `app.db.database`, kept alphabetical
    - `import json`
    - `ActionClassificationEntry, ActionDecisionEntry, ActionsResponse` from schemas
  - Module constants, next to the route:
    - `ACTIONS_LIMIT_DEFAULT = 100`
    - `ACTIONS_LIMIT_MAX = 500`, with the comment "Section 10: `?limit=` 1–500, default 100. 100 is `list_audit_logs`' and `list_action_decisions`' default."
    - `ActionDecisionFilter = Literal["allow", "flag", "deny"]`, with the comment that it restates `ACTION_DECISION_VALUES` (`app/db/models.py:408`) because a `Literal` cannot be built from a runtime tuple, and that a test pins the two equal.
  - New route, placed directly after `get_audit` (before `/stats`):
    ```python
    @router.get("/audit/actions", response_model=ActionsResponse)
    def get_audit_actions(
        identity: Identity = Depends(require_identity),
        limit: int = Query(ACTIONS_LIMIT_DEFAULT, ge=1, le=ACTIONS_LIMIT_MAX),
        decision: Optional[ActionDecisionFilter] = Query(None),
    ) -> ActionsResponse:
    ```
    - The body opens with the same two-step `try/except PermissionDenied` block as `get_audit`, copied verbatim (`:24-34`).
    - Docstring/comment: "Scoped exactly as `GET /audit` (PRD-016 9.1)".
    - Then: `entries = [_action_entry(row) for row in list_action_decisions(limit=limit, user_id=scope_user_id, decision=decision)]`, followed by `return ActionsResponse(entries=entries)`.
  - Private `_action_entry(row: ActionDecisionRow) -> ActionDecisionEntry`. It is a verbatim field passthrough, except `classifications=[ActionClassificationEntry(**c) for c in json.loads(row.classifications)]`.
    - Comment: decoding is the reader's job (`models.py:582-584`). The column is always written by `_classifications_json`, so a decode failure is a corrupt row and surfaces as a 500, the same way a broken `/stats` read does (`admin.py:116-118`). No catch.
    - Import `ActionDecisionRow` from `app.db.models` for the annotation only.
  - `/stats` (`:125-146`):
    - After `snapshot = summary_snapshot(row_limit=0)`, add `action_counts = count_action_decisions()`.
    - Pass `actions_denied=action_counts["deny"]`, `actions_flagged=action_counts["flag"]`, `actions_allowed=action_counts["allow"]`.
    - Comment: PRD-016 F11. This is a second statement against a different table, not folded into `_SUMMARY_SQL`: `SUMMARY_FIGURES` is a pinned 13-tuple (`tests/test_audit_stats_prd013.py:323`), and widening it would reopen STORY-010's batched read for a table it never reads. `/stats` is therefore two round trips, one per table. The statement-count test counts `audit_logs` statements only (`tests/test_stats_router.py:370-371`), so the "one `audit_logs` read" claim still holds.
    - Update the first sentence of the long comment (`:90`, "One statement, twelve figures") so it stays true: "One statement for the twelve audit figures; PRD-016 adds a second, over `action_decisions`, for three more."
- **Mirror**: `app/routers/admin.py:22-81`, `:84-146`
- **Validate**: backend import (above), then a manual `TestClient` probe in Task 6.

### Task 3: Caddyfile

- **File**: `Caddyfile`
- **Action**: UPDATE
- **Implement**: In line 5, after `/audit`, insert `/audit/actions` as an **exact** path, not `/audit/*`. The exact form keeps the matcher listing only real routes, the same way `/query` and `/stats` are listed. The result is `@backend_routes path /_event/* /ping /_upload /_upload/* /query /audit /audit/actions /stats /health /v1/*`.
- **Validate**: Task 5's `tests/test_caddyfile_routes.py`.

### Task 4: New test module

- **File**: `tests/test_admin_actions.py`
- **Action**: CREATE
- **Implement**: The header mirrors `tests/test_audit_router.py:1-17` (env defaults, `TestClient(app)`, `_fail_if_called`). The module docstring cites PRD-016 F11, 9.1 and 10. The tests use `temp_db`, so they get the `db` marker automatically (`tests/conftest.py:98-104`). Seed rows with `insert_action_decisions([ActionDecisionRow(...)])` through a small `_row(**overrides)` helper with fixed defaults, so ids and order are deterministic. Test `T9` goes through real `record()` + `evaluate()` instead.
  - **AC 1, scoping**
    - `test_audit_read_all_sees_every_users_rows_newest_first`: an `auditor` user and the admin token. Rows for users `a`, `b` and `a` come back in id-descending order. Assert `[e["id"] for e in entries]` is strictly descending and the users are `{a, b}`.
    - `test_audit_read_own_sees_only_own_rows`: role `user` `ana`; rows for `ana` and `someone-else`; only `ana`'s rows come back.
    - `test_identity_lacking_both_audit_permissions_returns_403_naming_own`: role `guest` returns `403` with `response.json() == {"detail": "Permission denied: audit:read:own"}`, and the same detail from `GET /audit` for the same caller ("matching `GET /audit`").
    - `test_missing_or_wrong_token_rejected_before_db_access`: monkeypatch `app.routers.admin.list_action_decisions` to `_fail_if_called`; no token or a wrong token returns 401/403.
  - **AC 2, filters and validation**
    - `test_decision_deny_limit_1_returns_one_deny_row`: two deny rows plus an allow and a flag. `?decision=deny&limit=1` returns exactly one entry with `decision == "deny"` and the newer deny's id.
    - `test_decision_filter_combines_with_own_scope`: a `user` caller with `?decision=flag` sees only their own flag rows.
    - `test_limit_out_of_range_is_422`: parametrize `limit` over `0, 501, -1, "x"`, each 422.
    - `test_limit_bounds_are_accepted`: `1` and `500` each return 200.
    - `test_unknown_decision_is_422`: parametrize over `"block", "DENY", ""`, each 422. Do not include `""` if FastAPI treats an empty query value as missing; the implementer confirms by running it and records the result in the report.
    - `test_default_limit_is_100`: monkeypatch `list_action_decisions` with a recorder and assert it was called with `limit=100, user_id=None, decision=None`. No 101-row seed is needed.
    - `test_decision_literal_mirrors_the_db_vocabulary`: `set(get_args(admin.ActionDecisionFilter)) == set(ACTION_DECISION_VALUES)`. This test needs no DB.
  - **AC 3, entry shape**
    - `test_entry_has_exactly_the_section_10_fields`: `set(entry) == {id, timestamp, audit_id, user_id, role, tool_call_id, tool_name, operation_kind, target_preview, decision, rule, reason, granted_by, classifications, policy_digest}`; `"arguments_preview" not in entry and "arguments_hash" not in entry`; also `"session_id" not in entry` (Q1).
    - `test_reason_is_returned_as_stored`: seed a row with `reason="stored reason text"` and assert it is returned verbatim.
    - `test_classifications_is_a_list_of_objects`: `T9`. Run `record(_three())`-style decisions from real `evaluate()` (the `tests/test_action_audit.py:88-117` pattern, `BUILT_IN_POLICY` with `shell.unlisted` → flag) and read them back. `classifications` is a `list` of `dict` with keys `{rule, kind, detail}`, and the deny row's `rule`, `decision` and `granted_by` equal the engine's `ActionDecision`.
    - `test_null_kind_classification_and_nullable_fields_pass_through`: an unknown-tool row (`operation_kind=None`, `target_preview=None`, `audit_id=None`, classification `kind: null`) serializes the nulls as `None`.
  - **AC 4, /stats**
    - `test_stats_action_counts_are_zero_on_an_empty_table`: the three keys are 0.
    - `test_stats_reports_action_counts`: seed 3 deny, 2 flag and 1 allow, then assert `actions_denied == 3`, `actions_flagged == 2`, `actions_allowed == 1`, all equal to `count_action_decisions()`, and the existing figures equal their empty-table values (`total_queries == 0`, and so on).
    - `test_stats_rejected_before_action_counts_read`: monkeypatch `app.routers.admin.count_action_decisions` and `summary_snapshot` to `_fail_if_called`; with no token the request is rejected (401/403).
- **Mirror**: `tests/test_audit_router.py:1-38`, `:242-294`; `tests/test_stats_router.py:188-209`; `tests/test_action_audit.py:62-117`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_admin_actions.py -q -p no:cacheprovider`

### Task 5: Update pinned assertions in existing tests

Every edited assertion gets the comment `# PRD-016 F11 / Section 10: three additive action counts (STORY-016).`, or `... 0 on an empty table` where the values are zero. Do not remove or rename any test function: `tests/test_stats_router.py` is a census-guarded suite (`tests/test_untouched_app.py:72-79`), and adding to it passes.

- `tests/test_stats_router.py`:
  - `:116-130` and `:273-287`: add `"actions_denied", "actions_flagged", "actions_allowed"` to the key set.
  - `:192-206`: add the three keys `: 0`.
  - `:441-455` (`test_stats_does_not_fetch_the_register_rows`, which fakes `summary_snapshot`): add the three keys `: 0`. `count_action_decisions()` reads the real empty `temp_db`. Its `calls == [((), {"row_limit": 0})]` assertion is unchanged.
- `tests/test_reporting_invariance.py` `:277-291` and `:564-578`: add the three keys to the key set. Leave the `# StatsResponse's shape: no field added or removed by PRD-009.` comment in place, and add the PRD-016 comment at the new keys.
- `tests/test_schemas.py` `:208-222`: add the three keys `: 0` to `test_stats_response_shape`'s expected dump. Also add `test_actions_response_shape`, which builds `ActionsResponse(entries=[ActionDecisionEntry(...)])` and checks the exact `model_dump()`, mirroring `test_audit_response_shape` `:128-180`.
- `tests/test_caddyfile_routes.py` `:31-41`: add `"/audit/actions",` after `"/audit",` in `EXPECTED_MATCHER`, with the comment `# PRD-016 F11 (STORY-016): GET /audit/actions; /audit is an exact token.` Update the comment at `:29-30` to say "plus `/audit/actions` (PRD-016)".
- **Not changed**: `tests/test_route_reservations.py:31-32` is a `<=` subset check, so it still passes. The `BACKEND_ROUTES` restatements in `tests/test_admin_shell.py:67` and `:176` only guard console-route collisions, and `/audit/actions` is not a console route. `tests/test_db.py` is not changed, because `summary_snapshot` is untouched.
- **Validate**: run the targeted set (below).

### Task 6: Manual probe

- In-process `TestClient` probe (`tests/test_admin_actions.py` covers it). In addition, run one `.venv/Scripts/python -c` that imports `app.main.app` and prints `[r.path for r in admin_router.router.routes]`, and confirm `/audit/actions` is registered before `/stats`. Ordering does not matter for these static paths; the check only confirms the route is registered.

---

## End-to-End Tests

- [ ] `GET /audit/actions` with the admin token on a seeded DB returns 200 and `{"entries": [...]}`, newest first (`test_admin_actions.py`)
- [ ] `GET /audit/actions?decision=deny&limit=1` returns exactly one deny entry with the 15 Section 10 keys
- [ ] `GET /audit/actions?limit=501` returns 422, and `?decision=block` returns 422
- [ ] A `guest` caller gets 403 `{"detail": "Permission denied: audit:read:own"}`, identical to `GET /audit`
- [ ] `GET /stats` on an empty DB includes the three counts at 0, and every other key and value is unchanged
- [ ] `record()` → `GET /audit/actions` round trip against libSQL returns `classifications` as a list of objects
- [ ] Caddy matcher test passes, with `/audit/actions` proxied

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest \
  tests/test_admin_actions.py tests/test_audit_router.py tests/test_stats_router.py \
  tests/test_reporting_invariance.py tests/test_schemas.py tests/test_caddyfile_routes.py \
  tests/test_route_reservations.py tests/test_untouched_app.py \
  -q -p no:cacheprovider
```

That is the targeted set: the new module, the `/audit` and `/stats` route suites, the two other suites that pin the `/stats` keys, the schema shape tests, the route-list guards (Caddy and reservations), and `test_untouched_app.py` because app files change. `tests/test_audit_stats_prd013.py` is deliberately left out: it asserts single figures, never the key set. `tests/test_action_audit.py` is also left out: STORY-015's module is unchanged. Full suite: deferred to orchestrator (user decision).

---

## Risks and Open Questions

- **Q1. `session_id` is not on the entry.** The Section 10 example omits it and AC 3 says "exactly the fields of the PRD Section 10 example", so this plan omits it, although the column exists and `AuditQueryEntry` exposes its own `session_id`. If the orchestrator wants it (for example so STORY-019 can link to a conversation), adding it is one optional field plus one key in the shape test. STORY-019 reads the database functions directly (its story line 40), so it is not blocked either way.
- **Q2. `/stats` becomes two round trips** (`summary_snapshot` plus `count_action_decisions`). PRD 6.11 says "snapshot counts" for `database.py`, but the story's Technical Notes say `/stats` reads `count_action_decisions()`, and STORY-015 shipped that function for this purpose (`database.py:2349-2351`). Folding the counts into `_SUMMARY_SQL` would change the pinned 13-figure `SUMMARY_FIGURES` and the console's snapshot. This plan follows the story and documents the extra statement in the `/stats` comment. The existing statement-count test filters to `audit_logs` and still passes.
- **R1. Caddyfile change not named in the story.** Without it the endpoint works in-process and returns 404 behind Caddy in Docker. The existing guard test fails without it, so this change is required, not scope creep.
- **R2. Validation order.** FastAPI validates query parameters before the handler body runs, so a caller lacking both audit permissions who sends `?limit=0` gets 422, not 403. A missing or invalid token still gets 401 first, because `require_identity` is a dependency. This matches how FastAPI treats any validated input, and no data is disclosed. It is noted, not changed. A test pins the 401-before-DB behaviour.
- **R3. `RBAC_ENABLED=false`.** `authorize()` returns at once (`authz.py:160-161`), so every caller reads all rows, exactly as `GET /audit` does. This route mirrors that and adds nothing. Action *grants* use `holds()`, which this story does not touch.
- **R4. Pinned assertions edited.** The AC says "every existing `/stats` field and assertion is unchanged". Values are unchanged. The six exact key-set and body assertions must gain the three keys, or they fail. Each edit carries the PRD-016 comment, and no value assertion changes.

---

## Acceptance Criteria

(Copied from story `STORY-016`)

- [ ] Given an identity with `audit:read:all`, when it calls `GET /audit/actions`, then every user's rows are returned newest first; with only `audit:read:own`, then only its own; with neither, then 403 with `Permission denied: audit:read:own`, matching `GET /audit`.
- [ ] Given `?decision=deny&limit=1`, when called, then one `deny` row is returned; `limit` outside 1–500 or an unknown `decision` → 422.
- [ ] Given a row, when returned, then the entry has exactly the fields of the PRD Section 10 example and **not** `arguments_preview` or `arguments_hash`; `classifications` is a list of objects.
- [ ] Given recorded decisions, when `GET /stats` is called, then it includes `actions_denied`, `actions_flagged`, `actions_allowed`, each 0 on an empty table, and every existing `/stats` field and assertion is unchanged.
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns
