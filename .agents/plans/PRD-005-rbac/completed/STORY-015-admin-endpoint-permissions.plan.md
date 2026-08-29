---
story: STORY-015
prd: PRD-005
slug: admin-endpoint-permissions
title: /audit scoping and /stats gating by permission
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-005-rbac
created: 2026-08-28
---

# Plan: /audit scoping and /stats gating by permission

## Summary

`app/routers/admin.py` currently gates both `/audit` and `/stats` with the same all-or-nothing `dependencies=[Depends(require_admin_token)]`, inherited unchanged from PRD-001 — a compliance reviewer cannot get read access to either endpoint without also holding the admin token that gates everything else. STORY-012 already built `require_identity` (`401`) and `require_permission(p)` (`403`) in `app/middleware/auth.py`, and STORY-009 already added `role`/`denied_permission` columns to `audit_logs` that round-trip through `list_audit_logs()`/`get_audit_log()` but are not yet surfaced by `AuditQueryEntry`. This story moves `/stats` onto `Depends(require_permission(PERMISSION_STATS_READ))` unchanged in every other respect, and moves `/audit` onto `Depends(require_identity)` plus in-handler scoping logic — `audit:read:all` sees every row exactly as today, `audit:read:own` (and no `audit:read:all`) sees only the caller's rows with `total` reflecting the scoped count, and neither permission is a `403`. `list_audit_logs()` and `count_audit_logs()` gain an optional `user_id` keyword so the scoping happens in SQL (`WHERE user_id = ?`), not by fetching everything and filtering in Python. `AuditQueryEntry` gains `role` and `denied_permission` fields, populated straight off the `AuditLog` the router already has in hand — no new query.

## User Story

As a compliance reviewer
I want `/audit` and `/stats` gated by permission with per-user scoping
So that read access can be granted without granting everything the shared token grants today

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-015-admin-endpoint-permissions.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/db/database.py`, `app/models/schemas.py`, `app/routers/admin.py`, `tests/test_audit_router.py`, `tests/test_stats_router.py` |
| Story | STORY-015 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

---

## Skills In Use

None. `skills: []` in story frontmatter; `.agents/skills/` contains only `frontend-design`, which does not apply to this backend-only story.

---

## Patterns to Follow

### `require_permission(permission)` — single-permission gate via `dependencies=[...]` when the handler doesn't need the identity
```
// SOURCE: app/middleware/auth.py:23-31
def require_permission(permission: str):
    def _require_permission(identity: Identity = Depends(require_identity)) -> Identity:
        try:
            authorize(identity, permission)
        except PermissionDenied:
            raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
        return identity

    return _require_permission
```
`/stats` needs no identity in its body (it never scopes), so it stays a bare `dependencies=[Depends(require_permission(PERMISSION_STATS_READ))]` entry — the shape `app/routers/query.py:15-19` uses when it *does* need the identity as a parameter is the second pattern below, needed for `/audit` because AC2 requires scoping by `identity.user_id`.

### `authorize()` / `PermissionDenied` — the two-permission "either grants" check `/audit` needs, which `require_permission` can't express (it checks exactly one permission)
```
// SOURCE: app/services/authz.py:99-109
def authorize(identity: Identity, permission: str) -> None:
    if not settings.RBAC_ENABLED:
        return

    role_permissions = ROLE_PERMISSIONS.get(identity.role)
    if role_permissions is None or permission not in role_permissions:
        raise PermissionDenied(permission)
```
```
// SOURCE: app/services/authz.py:51-57
class PermissionDenied(Exception):
    def __init__(self, permission: str) -> None:
        self.permission = permission
        super().__init__(f"Permission denied: {permission}")
```
Calling `authorize()` directly (catching `PermissionDenied`) rather than composing two `Depends(require_permission(...))` is the only way to express "all wins over own, own is enough on its own, neither is 403" — a router `Depends` can't conditionally fall through to a second permission check. When `RBAC_ENABLED=false`, `authorize()` never raises, so the first check (`audit:read:all`) always passes and `scope_user_id` stays `None` — preserving today's "return everything" behavior under the documented escape hatch, exactly as `run_query()`'s pipeline checks already do.

### Router resolving the identity as a parameter (not a bare dependency) because the handler body needs it
```
// SOURCE: app/routers/query.py:15-19
@router.post("/query", response_model=QueryResponse)
def query(
    request: QueryRequest,
    identity: Identity = Depends(require_permission(PERMISSION_QUERY_SUBMIT)),
) -> QueryResponse:
```
`/audit`'s handler mirrors this shape with `Depends(require_identity)` instead (no single permission gates entry — the scoping decision happens inside the body), giving it `identity` to authorize against and to scope the query by.

### `list_audit_logs` / `count_audit_logs` — current unscoped shape, extended additively
```
// SOURCE: app/db/database.py:135-147
def count_audit_logs() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]


def list_audit_logs(limit: int = 100) -> list[AuditLog]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_audit_log(row) for row in rows]
```
Both gain an optional `user_id: Optional[str] = None` keyword, defaulting to today's unscoped query so every existing caller (`/stats`'s `count_audit_logs()`, all of `tests/test_db.py`) is unaffected. Scoping is a second, parametrized branch of the same query — not a Python-side filter — per the story's Technical Notes.

### `AuditLog` already carries `role`/`denied_permission` — `AuditQueryEntry` just needs to read them
```
// SOURCE: app/db/models.py:70-90
@dataclass
class AuditLog:
    ...
    role: Optional[str] = None
    denied_permission: Optional[str] = None
    id: Optional[int] = None
```
`_row_to_audit_log()` (`app/db/database.py:101-122`) already round-trips both fields from every `SELECT *` — STORY-009 finished this half. This story's only remaining wiring is `AuditQueryEntry` gaining the same two fields and the list comprehension in `get_audit()` passing them through, exactly the "small, isolated addition" the STORY-009 plan called out.

### `AuditQueryEntry` — current shape, extended additively
```
// SOURCE: app/models/schemas.py:54-65
class AuditQueryEntry(BaseModel):
    audit_id: int
    user_id: str
    timestamp: str
    model: Optional[str] = None
    prompt_hash: str
    was_duplicate_blocked: bool
    suspicious_pattern_detected: bool
    device: Optional[str] = None
    pii_detected_input: bool = False
    pii_detected_output: bool = False
    pii_entities: List[str] = []
```
`role: Optional[str] = None` and `denied_permission: Optional[str] = None` follow the same `Optional[...] = None` shape already used for `model`/`device` — historical pre-RBAC rows have `NULL` in both columns (STORY-009 AC2), so both must default, never required.

### `insert_user` + `hash_token` seeding pattern — real DB-backed non-admin identities for `TestClient`
```
// SOURCE: tests/test_query_router.py:83-94
insert_user(
    User(user_id="reviewer", role="auditor", token_hash=hash_token("auditor-token"))
)
monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
auditor_client = TestClient(app, headers={"Authorization": "Bearer auditor-token"})

response = auditor_client.post("/query", json={"prompt": "hello world"})

assert response.status_code == 403
assert response.json() == {"detail": f"Permission denied: {PERMISSION_QUERY_SUBMIT}"}
```
Used to seed `auditor` (has `audit:read:all` + `audit:read:own` + `stats:read`, no `query:submit`) and `user` (has only `audit:read:own`) identities. For "neither permission" (AC3), no built-in role lacks *both* `audit:read:own` and `audit:read:all` — `authorize()`'s deny-by-default falls through for any role string absent from `ROLE_PERMISSIONS` (`app/services/authz.py:107-109`: `role_permissions is None` denies), so seeding `role="guest"` (not a key in the matrix) via `insert_user` produces a real, resolvable identity that `authorize()` denies for every permission — no monkeypatching the matrix required.

### Tests — `temp_db` fixture + `AuditLog`/`User` insert-then-assert shape
```
// SOURCE: tests/test_audit_router.py:17-22, tests/test_db.py:486-503
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | `list_audit_logs`/`count_audit_logs` gain optional `user_id` scoping param |
| `app/models/schemas.py` | UPDATE | `AuditQueryEntry` gains `role`, `denied_permission` |
| `app/routers/admin.py` | UPDATE | `/audit` moves to `require_identity` + in-handler `audit:read:all`/`audit:read:own` scoping; `/stats` moves to `require_permission(PERMISSION_STATS_READ)` |
| `tests/test_audit_router.py` | UPDATE | Extend key-set assertion; add scoping (`all` vs `own`), 403-on-neither, and role/denied_permission-serialization tests |
| `tests/test_stats_router.py` | UPDATE | Add 403-without-`stats:read` and 200-with-`stats:read`-non-admin tests |

Not touched in this story:
- `app/middleware/auth.py` — `require_identity`/`require_permission` are complete from STORY-012; nothing new needed there
- `app/services/authz.py` — the matrix and `authorize()` are unchanged; this story is a consumer
- `app/services/query_pipeline.py` — already writes `role`/`denied_permission` on denial (STORY-010/STORY-011); this story only makes `/audit` display what's already stored
- `tests/test_admin_auth.py` — exercises `require_admin_token` directly against a fake app, not `/audit`/`/stats`; unaffected by this story

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `list_audit_logs`/`count_audit_logs` gain optional per-user scoping

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Replace both functions:
  ```python
  def count_audit_logs(user_id: Optional[str] = None) -> int:
      with get_connection() as conn:
          if user_id is not None:
              row = conn.execute(
                  "SELECT COUNT(*) AS n FROM audit_logs WHERE user_id = ?",
                  (user_id,),
              ).fetchone()
          else:
              row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
          return row["n"]
  ```
  ```python
  def list_audit_logs(limit: int = 100, user_id: Optional[str] = None) -> list[AuditLog]:
      with get_connection() as conn:
          if user_id is not None:
              rows = conn.execute(
                  """
                  SELECT * FROM audit_logs
                  WHERE user_id = ?
                  ORDER BY timestamp DESC LIMIT ?
                  """,
                  (user_id, limit),
              ).fetchall()
          else:
              rows = conn.execute(
                  "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
                  (limit,),
              ).fetchall()
          return [_row_to_audit_log(row) for row in rows]
  ```
  Both keep `_row_to_audit_log(row)` untouched — only the query changes, not the row mapping. `user_id=None` (the default) reproduces today's exact unscoped query byte-for-byte, so every existing caller with no `user_id` argument is unaffected.
- **Mirror**: `app/db/database.py:135-147` (functions being replaced), `app/db/database.py:87-98` (`find_duplicate_timestamp`) for the parametrized `WHERE ... = ?` shape already used elsewhere in this file.
- **Validate**: `python -c "from app.db.database import count_audit_logs, list_audit_logs"` succeeds.

### Task 2: `AuditQueryEntry` gains `role` and `denied_permission`

- **File**: `app/models/schemas.py`
- **Action**: UPDATE
- **Implement**: Add two fields to `AuditQueryEntry`, after `pii_entities`:
  ```python
  class AuditQueryEntry(BaseModel):
      audit_id: int
      user_id: str
      timestamp: str
      model: Optional[str] = None
      prompt_hash: str
      was_duplicate_blocked: bool
      suspicious_pattern_detected: bool
      device: Optional[str] = None
      pii_detected_input: bool = False
      pii_detected_output: bool = False
      pii_entities: List[str] = []
      role: Optional[str] = None
      denied_permission: Optional[str] = None
  ```
- **Mirror**: `app/models/schemas.py:58,62` (`model`, `device`) for the `Optional[str] = None` shape on the same model.
- **Validate**: `python -c "import app.models.schemas"` succeeds.

### Task 3: `/audit` moves to `require_identity` + scoping; `/stats` moves to `require_permission`

- **File**: `app/routers/admin.py`
- **Action**: UPDATE
- **Implement**: Rewrite the file:
  ```python
  from fastapi import APIRouter, Depends, HTTPException

  from app.db.database import (
      count_audit_logs,
      count_blocked_duplicates,
      count_blocked_suspicious,
      count_pii_detected_queries,
      count_successful_queries,
      count_unique_users,
      list_audit_logs,
      top_models,
      top_pii_entities,
      top_users,
  )
  from app.middleware.auth import require_identity, require_permission
  from app.models.schemas import AuditQueryEntry, AuditResponse, StatsResponse
  from app.services.authz import (
      PERMISSION_AUDIT_READ_ALL,
      PERMISSION_AUDIT_READ_OWN,
      PERMISSION_STATS_READ,
      PermissionDenied,
      authorize,
  )
  from app.services.identity import Identity

  router = APIRouter()


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

      total = count_audit_logs(user_id=scope_user_id)
      queries = [
          AuditQueryEntry(
              audit_id=log.id,
              user_id=log.user_id,
              role=log.role,
              denied_permission=log.denied_permission,
              timestamp=log.timestamp,
              model=log.model_used,
              prompt_hash=log.prompt_hash,
              was_duplicate_blocked=log.was_duplicate_blocked,
              suspicious_pattern_detected=log.suspicious_pattern is not None,
              device=log.device,
              pii_detected_input=log.pii_detected_input,
              pii_detected_output=log.pii_detected_output,
              pii_entities=log.pii_entities.split(",") if log.pii_entities else [],
          )
          for log in list_audit_logs(limit=100, user_id=scope_user_id)
      ]
      return AuditResponse(total=total, queries=queries)


  @router.get(
      "/stats",
      response_model=StatsResponse,
      dependencies=[Depends(require_permission(PERMISSION_STATS_READ))],
  )
  def get_stats() -> StatsResponse:
      total = count_audit_logs()
      successful = count_successful_queries()
      success_rate = f"{(successful / total * 100):.1f}%" if total > 0 else "0.0%"

      return StatsResponse(
          total_queries=total,
          blocked_duplicates=count_blocked_duplicates(),
          blocked_suspicious=count_blocked_suspicious(),
          unique_users=count_unique_users(),
          success_rate=success_rate,
          top_models=top_models(),
          top_users=top_users(),
          pii_detected_queries=count_pii_detected_queries(),
          top_pii_entities=top_pii_entities(),
      )
  ```
  Notes:
  - `get_stats()`'s body is byte-for-byte unchanged from today — only its `dependencies=[...]` entry changes from `require_admin_token` to `require_permission(PERMISSION_STATS_READ)`. Satisfies "response shape is unchanged" (AC4).
  - `get_audit()`'s scoping tries `audit:read:all` first (today's full-visibility behavior, including for `admin` and any future role granted both) and falls back to `audit:read:own`; only when both raise does it return `403` — satisfies AC1–AC3. The `try/except PermissionDenied` chain is the only way to express "either grants, neither denies" since `require_permission` checks exactly one permission.
  - `require_admin_token` is no longer imported by this file — it stays exactly as STORY-012 left it in `app/middleware/auth.py`, still exercised directly by `tests/test_admin_auth.py`, but no route in this codebase uses it as a dependency after this change. That is expected: PRD Section 4 keeps `ADMIN_TOKEN` as a break-glass credential resolved to the `admin` role by `identity.resolve()`, and `admin` already holds every permission these two endpoints check, so `ADMIN_TOKEN` keeps working end-to-end through `require_identity`/`require_permission` rather than through `require_admin_token` directly.
- **Mirror**: `app/routers/query.py:15-19` for `Depends(...)` as a parameter (not a bare `dependencies=[...]` entry) when the handler needs the resolved identity; `app/services/query_pipeline.py:31-42` (`_deny`) for the `try: authorize(...); except PermissionDenied:` shape.
- **Validate**: `python -c "import app.routers.admin"` succeeds.

### Task 4: Update `tests/test_audit_router.py` for scoping + the new fields

- **File**: `tests/test_audit_router.py`
- **Action**: UPDATE
- **Implement**:
  1. Extend the import block:
     ```python
     from app.db.database import init_db, insert_audit_log, insert_user
     from app.db.models import AuditLog, User
     from app.services.identity import hash_token
     ```
  2. Extend the expected key set in `test_valid_token_returns_expected_shape` (both places a `set(entry.keys())` assertion exists) to include the two new fields:
     ```python
     assert set(entry.keys()) == {
         "audit_id",
         "user_id",
         "timestamp",
         "model",
         "prompt_hash",
         "was_duplicate_blocked",
         "suspicious_pattern_detected",
         "device",
         "pii_detected_input",
         "pii_detected_output",
         "pii_entities",
         "role",
         "denied_permission",
     }
     ```
  3. Add new tests covering STORY-015's ACs, appended after `test_response_never_includes_ip_or_raw_text`:
     ```python
     def test_auditor_role_sees_every_row(temp_db):
         insert_user(
             User(user_id="reviewer", role="auditor", token_hash=hash_token("auditor-token"))
         )
         insert_audit_log(
             AuditLog(timestamp="2026-07-01T10:00:00Z", user_id="a", prompt_hash="h1")
         )
         insert_audit_log(
             AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="b", prompt_hash="h2")
         )

         response = client.get(
             "/audit", headers={"Authorization": "Bearer auditor-token"}
         )

         assert response.status_code == 200
         body = response.json()
         assert body["total"] == 2
         assert {q["user_id"] for q in body["queries"]} == {"a", "b"}


     def test_user_role_sees_only_own_rows_and_scoped_total(temp_db):
         insert_user(
             User(user_id="ana", role="user", token_hash=hash_token("ana-token"))
         )
         insert_audit_log(
             AuditLog(timestamp="2026-07-01T10:00:00Z", user_id="ana", prompt_hash="h1")
         )
         insert_audit_log(
             AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="someone-else", prompt_hash="h2")
         )

         response = client.get(
             "/audit", headers={"Authorization": "Bearer ana-token"}
         )

         assert response.status_code == 200
         body = response.json()
         assert body["total"] == 1
         assert len(body["queries"]) == 1
         assert body["queries"][0]["user_id"] == "ana"


     def test_identity_lacking_both_audit_permissions_returns_403(temp_db):
         insert_user(
             User(user_id="outsider", role="guest", token_hash=hash_token("guest-token"))
         )

         response = client.get(
             "/audit", headers={"Authorization": "Bearer guest-token"}
         )

         assert response.status_code == 403


     def test_audit_entry_carries_role_and_denied_permission(temp_db):
         insert_audit_log(
             AuditLog(
                 timestamp="2026-07-01T10:00:00Z",
                 user_id="ana",
                 prompt_hash="h1",
                 role="user",
                 denied_permission="query:byok",
             )
         )
         insert_audit_log(
             AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="ana", prompt_hash="h2")
         )

         response = client.get(
             "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
         )

         body = response.json()
         by_hash = {q["prompt_hash"]: q for q in body["queries"]}
         assert by_hash["h1"]["role"] == "user"
         assert by_hash["h1"]["denied_permission"] == "query:byok"
         assert by_hash["h2"]["role"] is None
         assert by_hash["h2"]["denied_permission"] is None
     ```
     - `test_auditor_role_sees_every_row` covers AC1 through a non-admin `audit:read:all` grant, distinct from the existing `ADMIN_TOKEN` tests.
     - `test_user_role_sees_only_own_rows_and_scoped_total` covers AC2.
     - `test_identity_lacking_both_audit_permissions_returns_403` covers AC3, seeding `role="guest"` (absent from `ROLE_PERMISSIONS`) so `authorize()` denies by default without touching the matrix.
     - `test_audit_entry_carries_role_and_denied_permission` covers AC5, including the `NULL`-becomes-`None` case for a normal (non-denied) row.
- **Mirror**: `tests/test_query_router.py:83-94` for the `insert_user` + role-specific `TestClient` header pattern; `tests/test_audit_router.py:123-157` (`test_pii_telemetry_fields_reflect_audit_log_values`) for the insert-two-rows-then-assert-by-hash style used in the new field test.
- **Validate**: `python -m pytest tests/test_audit_router.py -q` — all tests (existing + new) pass.

### Task 5: Update `tests/test_stats_router.py` for permission gating

- **File**: `tests/test_stats_router.py`
- **Action**: UPDATE
- **Implement**:
  1. Extend the import block:
     ```python
     from app.db.database import init_db, insert_audit_log, insert_user
     from app.db.models import AuditLog, User
     from app.services.authz import PERMISSION_STATS_READ
     from app.services.identity import hash_token
     ```
  2. Add new tests, appended after `test_pii_detected_queries_and_top_pii_entities_reflect_flagged_rows`:
     ```python
     def test_identity_lacking_stats_read_returns_403_naming_permission(temp_db):
         insert_user(
             User(user_id="ana", role="user", token_hash=hash_token("ana-token"))
         )

         response = client.get(
             "/stats", headers={"Authorization": "Bearer ana-token"}
         )

         assert response.status_code == 403
         assert response.json() == {"detail": f"Permission denied: {PERMISSION_STATS_READ}"}


     def test_auditor_role_reads_stats_with_unchanged_shape(temp_db):
         insert_user(
             User(user_id="reviewer", role="auditor", token_hash=hash_token("auditor-token"))
         )
         insert_audit_log(
             AuditLog(timestamp="2026-07-01T10:00:00Z", user_id="a", prompt_hash="h1")
         )

         response = client.get(
             "/stats", headers={"Authorization": "Bearer auditor-token"}
         )

         assert response.status_code == 200
         body = response.json()
         assert set(body.keys()) == {
             "total_queries",
             "blocked_duplicates",
             "blocked_suspicious",
             "unique_users",
             "success_rate",
             "top_models",
             "top_users",
             "pii_detected_queries",
             "top_pii_entities",
         }
         assert body["total_queries"] == 1
     ```
     - `test_identity_lacking_stats_read_returns_403_naming_permission` covers AC4's `403` half — `role="user"` lacks `stats:read` per the default matrix.
     - `test_auditor_role_reads_stats_with_unchanged_shape` covers AC4's "response shape is unchanged" half through a non-admin `stats:read` grant.
- **Mirror**: `tests/test_query_router.py:83-94` for the `insert_user` + role-specific header pattern; `tests/test_stats_router.py:102-121` (`test_valid_token_returns_expected_shape_and_values`) for the key-set assertion shape.
- **Validate**: `python -m pytest tests/test_stats_router.py -q` — all tests (existing + new) pass.

---

## End-to-End Tests

- [ ] `python -m pytest tests/test_audit_router.py tests/test_stats_router.py -q` — both files green, including all pre-existing tests unmodified
- [ ] `python -m pytest tests/test_admin_auth.py -q` — unaffected (exercises `require_admin_token` directly, not routed through `/audit`/`/stats` anymore)
- [ ] `python -m pytest tests/test_db.py -q` — `list_audit_logs`/`count_audit_logs` callers with no `user_id` argument still pass unmodified
- [ ] Manual: `curl http://localhost:8000/audit -H "Authorization: Bearer <admin token>"` → `200`, every row, `role`/`denied_permission` present in each entry
- [ ] Manual: `curl http://localhost:8000/audit -H "Authorization: Bearer <user-role token>"` → `200`, only that user's rows, `total` matches the scoped count
- [ ] Manual: `curl http://localhost:8000/stats -H "Authorization: Bearer <user-role token>"` → `403`

---

## Validation

```bash
cd F:/AI/harness-ai
python -c "import app.routers.admin"
python -m pytest tests/test_audit_router.py tests/test_stats_router.py tests/test_admin_auth.py tests/test_db.py -q
```

---

## Acceptance Criteria

(Copied from story `STORY-015`)

- [ ] Given an identity with `audit:read:all`, when `GET /audit` is called, then every row is returned as today
- [ ] Given an identity with only `audit:read:own`, when it is called, then only that user's rows are returned and `total` reflects the scoped count
- [ ] Given an identity with neither permission, when it is called, then it returns `403`
- [ ] Given `GET /stats` and an identity without `stats:read`, when it is called, then it returns `403`; with the permission, the response shape is unchanged
- [ ] Given an audit entry, when serialized, then it carries `role` and `denied_permission`
- [ ] All tasks completed
- [ ] `tests/test_audit_router.py` and `tests/test_stats_router.py` pass in full, including all pre-existing tests unmodified in behavior
- [ ] Follows existing `Depends(require_identity)` / `Depends(require_permission(...))` / `authorize()`/`PermissionDenied` patterns
