---
story: STORY-013
prd: PRD-005
slug: query-router-authentication
title: POST /query bearer authentication and status-code mapping
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-005-rbac
created: 2026-08-28
---

# Plan: POST /query bearer authentication and status-code mapping

## Summary

`app/routers/query.py` currently trusts `QueryRequest.user_id` as identity and has no authentication at all — `run_query()` was updated by STORY-010 to require an `Identity` and to authorize `query:submit` itself as pipeline step 0 (returning `200` + `status: "BLOCKED"` on denial), but nothing upstream of it resolves who the caller actually is. STORY-012 built `require_identity` (`401` on no/invalid credential) and `require_permission(permission)` (`403` on a resolved-but-unauthorized identity) in `app/middleware/auth.py` for exactly this purpose. This story wires `Depends(require_permission(PERMISSION_QUERY_SUBMIT))` onto `POST /query` so `query:submit` is enforced at the HTTP boundary with the PRD's documented `403`, ahead of — and in addition to — the pipeline's own defense-in-depth check; makes `QueryRequest.user_id` an `Optional[str]`, deprecated and never trusted as identity, refusing a mismatching value with `403` rather than silently overriding it; and passes the router-resolved `Identity` into `run_query()` so the audited user id always comes from the credential. Model-allowlist and BYOK-without-permission refusals stay exactly as `run_query()` already returns them — in-band `200` + `BLOCKED` — untouched by this story.

## User Story

As an integrating developer
I want `POST /query` to authenticate via a bearer token and map each outcome to the documented status code
So that the endpoint has a predictable auth contract

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-013-query-router-authentication.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/routers/query.py`, `app/models/schemas.py`, `tests/test_query_router.py` |
| Story | STORY-013 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

---

## Skills In Use

None. `skills: []` in story frontmatter; `.agents/skills/` contains only `frontend-design`, which does not apply to this backend-only story.

---

## Patterns to Follow

### `require_permission(permission)` — dependency factory returning the resolved Identity
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
Used as `identity: Identity = Depends(require_permission(PERMISSION_QUERY_SUBMIT))` (a parameter, not a bare `dependencies=[...]` entry) so the router gets the resolved `Identity` to pass into `run_query()`. `401` (missing/invalid credential) fires before `403` (lacks permission) because `require_identity` runs first in the chain — both fire before the route function body executes, so no audit row is written for either.

### `run_query()` — Identity-first signature, own `query:submit` check as defense in depth
```
// SOURCE: app/services/query_pipeline.py:45-56
def run_query(
    identity: Identity,
    prompt: str,
    device: Optional[str],
    model: str,
    openrouter_api_key: Optional[str],
    call_openrouter: Callable[..., OpenRouterResult] = call_openrouter,
) -> QueryPipelineResult:
    try:
        authorize(identity, PERMISSION_QUERY_SUBMIT)
    except PermissionDenied as exc:
        return _deny(identity, prompt, device, exc, "Missing required permission")
```
`run_query()`'s own `query:submit` check (PRD Risk 1's structural choke point, covering the chat-UI in-process ingress from STORY-014) still runs even after the router-level `403` gate — for the HTTP path it will never trigger, because `require_permission` already refused the request first. That redundancy is intentional, not something this story removes. Model-allowlist and BYOK checks further down `run_query()` are untouched — this story does not add a router-level counterpart for them; they stay in-band `200` + `BLOCKED` per PRD Section 9's table.

### Current `QueryRequest` (user_id becomes deprecated/optional)
```
// SOURCE: app/models/schemas.py:6-11
class QueryRequest(BaseModel):
    user_id: str
    prompt: str
    device: Optional[str] = None
    model: str = "gpt-4"
    openrouter_api_key: Optional[str] = None
```

### Current `app/routers/query.py` (in full — the file this story rewrites)
```
// SOURCE: app/routers/query.py:1-32
from fastapi import APIRouter, HTTPException

from app.models.schemas import QueryRequest, QueryResponse
from app.services.duplicate_checker import DuplicateCheckError
from app.services.openrouter_client import OpenRouterError, call_openrouter
from app.services.pii_redactor import PiiRedactorError
from app.services.query_pipeline import run_query

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    if not request.user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")

    try:
        return run_query(
            user_id=request.user_id,
            prompt=request.prompt,
            device=request.device,
            model=request.model,
            openrouter_api_key=request.openrouter_api_key,
            call_openrouter=call_openrouter,
        )
    except DuplicateCheckError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except PiiRedactorError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except OpenRouterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```
The `user_id.strip()` / `400` guard is removed outright — it validated a field that is now optional and never trusted as identity, so there is nothing left for it to guard.

### Default role matrix — who has `query:submit` / `query:byok` for test seeding
```
// SOURCE: app/services/authz.py:27-44
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {PERMISSION_QUERY_SUBMIT, PERMISSION_QUERY_BYOK, PERMISSION_AUDIT_READ_ALL, PERMISSION_AUDIT_READ_OWN, PERMISSION_STATS_READ},
    "auditor": {PERMISSION_AUDIT_READ_ALL, PERMISSION_AUDIT_READ_OWN, PERMISSION_STATS_READ},
    "user": {PERMISSION_QUERY_SUBMIT, PERMISSION_AUDIT_READ_OWN},
}
```
`role="user"` has `query:submit` but not `query:byok` — exactly the identity needed for both "existing tests keep passing" (seed the default test user as `role="user"`) and the new BYOK-refusal test. `role="auditor"` has neither — used for the `403` "lacks query:submit" test.

### `insert_user` + `hash_token` seeding pattern (real DB-backed identity for TestClient)
```
// SOURCE: tests/test_auth_dependencies.py:83-89, 104-110
insert_user(User(user_id="ana", role="user", token_hash=hash_token("tok")))
response = client.get("/fake-identity", headers={"Authorization": "Bearer tok"})
...
insert_user(User(user_id="ana", role="user", token_hash=hash_token("tok")))
response = client.get("/fake-byok", headers={"Authorization": "Bearer tok"})
assert response.status_code == 403
assert response.json() == {"detail": f"Permission denied: {PERMISSION_QUERY_BYOK}"}
```

### `TestClient(app, headers=...)` sets default headers on every request
Verified against the installed `fastapi==0.139.0` / `httpx==0.28.1`: `starlette.testclient.TestClient.__init__` accepts `headers: dict[str, str] | None = None`, applied to every request made through that client instance. This lets `tests/test_query_router.py` seed one default authenticated identity and leave ~35 existing test bodies (`json={"user_id": "juan@empresa.com", ...}`) completely unchanged, since that `user_id` will already match the seeded credential's `user_id`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/schemas.py` | UPDATE | `QueryRequest.user_id` becomes `Optional[str] = None`, documented as deprecated |
| `app/routers/query.py` | UPDATE | Add `Depends(require_permission(PERMISSION_QUERY_SUBMIT))`; drop the obsolete `user_id.strip()` `400` guard; add the body/credential `user_id` mismatch → `403` check; pass `identity` into `run_query()` |
| `tests/test_query_router.py` | UPDATE | Seed a default authenticated `role="user"` identity via `temp_db` + set it as the `TestClient`'s default headers; replace the two now-obsolete `user_id` validation tests with 6 new tests covering STORY-013's ACs |

Not touched in this story:
- `app/services/query_pipeline.py` — `run_query()`'s signature and internal checks are STORY-010/STORY-011 territory and are unchanged
- `app/routers/admin.py` — still gated by `require_admin_token`; STORY-015 moves `/audit`/`/stats` onto `require_permission(...)`
- `chat_ui/chat_ui/state.py` — STORY-014's ingress, not this one

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `QueryRequest.user_id` becomes optional and deprecated

- **File**: `app/models/schemas.py`
- **Action**: UPDATE
- **Implement**: Change the field and add a short comment recording why it's kept but never trusted:
  ```python
  class QueryRequest(BaseModel):
      # Deprecated (PRD-005 Section 10): accepted for backward compatibility
      # only. Never trusted as identity -- the audited user id always comes
      # from the authenticated credential. A value that doesn't match the
      # credential is refused with 403 rather than silently overridden.
      user_id: Optional[str] = None
      prompt: str
      device: Optional[str] = None
      model: str = "gpt-4"
      openrouter_api_key: Optional[str] = None
  ```
- **Mirror**: `app/models/schemas.py:9,11` — existing `Optional[str] = None` fields on the same model (`device`, `openrouter_api_key`) for the exact typing/default shape.
- **Validate**: `python -c "import app.models.schemas"` succeeds.

### Task 2: Wire `require_permission(PERMISSION_QUERY_SUBMIT)` and identity-sourced `user_id` into the router

- **File**: `app/routers/query.py`
- **Action**: UPDATE
- **Implement**: Rewrite the file to:
  ```python
  from fastapi import APIRouter, Depends, HTTPException

  from app.middleware.auth import require_permission
  from app.models.schemas import QueryRequest, QueryResponse
  from app.services.authz import PERMISSION_QUERY_SUBMIT
  from app.services.duplicate_checker import DuplicateCheckError
  from app.services.identity import Identity
  from app.services.openrouter_client import OpenRouterError, call_openrouter
  from app.services.pii_redactor import PiiRedactorError
  from app.services.query_pipeline import run_query

  router = APIRouter()


  @router.post("/query", response_model=QueryResponse)
  def query(
      request: QueryRequest,
      identity: Identity = Depends(require_permission(PERMISSION_QUERY_SUBMIT)),
  ) -> QueryResponse:
      if request.user_id is not None and request.user_id != identity.user_id:
          raise HTTPException(
              status_code=403,
              detail="user_id does not match the authenticated identity",
          )

      try:
          return run_query(
              identity=identity,
              prompt=request.prompt,
              device=request.device,
              model=request.model,
              openrouter_api_key=request.openrouter_api_key,
              call_openrouter=call_openrouter,
          )
      except DuplicateCheckError as exc:
          raise HTTPException(status_code=500, detail=str(exc)) from exc
      except PiiRedactorError as exc:
          raise HTTPException(status_code=500, detail=str(exc)) from exc
      except OpenRouterError as exc:
          raise HTTPException(status_code=502, detail=str(exc)) from exc
  ```
  Notes:
  - The `Depends(require_permission(...))` gate runs (and can `401`/`403`) before the function body, so no audit row is written for either case — satisfies AC1 and AC2 without extra code.
  - The mismatch check runs before the `try:` block, so a `403` here also never reaches `run_query()` and writes no audit row — satisfies AC3.
  - `DuplicateCheckError` / `PiiRedactorError` / `OpenRouterError` handlers are untouched, per the story's Technical Notes.
- **Mirror**: `app/middleware/auth.py:23-31` for the `require_permission` factory shape; `app/services/query_pipeline.py:45-51` for the `identity: Identity` parameter `run_query()` now requires.
- **Validate**: `python -c "import app.routers.query"` succeeds.

### Task 3: Update `tests/test_query_router.py` for the new auth contract

- **File**: `tests/test_query_router.py`
- **Action**: UPDATE
- **Implement**:
  1. Extend the import block:
     ```python
     from app.db.database import (
         get_audit_log,
         get_connection,
         init_db,
         insert_audit_log,
         insert_user,
     )
     from app.db.models import AuditLog, User
     from app.main import app
     import app.services.query_pipeline as query_pipeline
     from app.services.authz import PERMISSION_QUERY_BYOK, PERMISSION_QUERY_SUBMIT
     from app.services.duplicate_checker import hash_prompt
     from app.services.identity import hash_token
     from app.services.openrouter_client import OpenRouterError, OpenRouterResult
     from app.services.pii_redactor import PiiRedactorError
     ```
  2. Add module-level constants and make `client` send them by default, replacing the bare `client = TestClient(app)`:
     ```python
     _AUTH_USER_ID = "juan@empresa.com"
     _AUTH_TOKEN = "test-user-token"
     _AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}

     client = TestClient(app, headers=_AUTH_HEADERS)
     ```
  3. Seed that identity inside `temp_db` so it exists on every test's fresh database:
     ```python
     @pytest.fixture
     def temp_db(tmp_path, monkeypatch):
         db_path = tmp_path / "test.db"
         monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
         init_db()
         insert_user(
             User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
         )
         return db_path
     ```
     Every existing test body already posts `json={"user_id": "juan@empresa.com", ...}` (grep confirms no other `user_id` value appears in this file), so with the default header now in place they keep passing unmodified — the `user_id` in the body matches `identity.user_id` from the credential.
  4. Delete `test_missing_user_id_returns_422` and `test_empty_user_id_returns_400_before_any_side_effect` (lines 58-75 of the current file) — both assert behavior of the removed `user_id.strip()` `400` guard, which no longer exists now that `user_id` is optional and untrusted. Replace them in place with:
     ```python
     def test_missing_authorization_header_returns_401_and_no_audit_row(temp_db, monkeypatch):
         monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
         unauth_client = TestClient(app)

         response = unauth_client.post("/query", json={"prompt": "hello world"})

         assert response.status_code == 401
         assert _count_audit_rows() == 0


     def test_identity_lacking_query_submit_returns_403_naming_permission(temp_db, monkeypatch):
         insert_user(
             User(user_id="reviewer", role="auditor", token_hash=hash_token("auditor-token"))
         )
         monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
         auditor_client = TestClient(app, headers={"Authorization": "Bearer auditor-token"})

         response = auditor_client.post("/query", json={"prompt": "hello world"})

         assert response.status_code == 403
         assert response.json() == {"detail": f"Permission denied: {PERMISSION_QUERY_SUBMIT}"}
         assert _count_audit_rows() == 0


     def test_body_user_id_mismatch_returns_403_without_overriding(temp_db, monkeypatch):
         monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

         response = client.post(
             "/query", json={"user_id": "someone-else", "prompt": "hello world"}
         )

         assert response.status_code == 403
         assert _count_audit_rows() == 0


     def test_body_user_id_absent_proceeds_with_credential_user_id(temp_db, monkeypatch):
         def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
             return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

         monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)

         response = client.post("/query", json={"prompt": "hello world"})

         assert response.status_code == 200
         entry = get_audit_log(response.json()["audit_id"])
         assert entry.user_id == _AUTH_USER_ID


     def test_body_user_id_matching_credential_proceeds(temp_db, monkeypatch):
         def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
             return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

         monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)

         response = client.post(
             "/query", json={"user_id": _AUTH_USER_ID, "prompt": "hello world"}
         )

         assert response.status_code == 200
         entry = get_audit_log(response.json()["audit_id"])
         assert entry.user_id == _AUTH_USER_ID


     def test_byok_without_permission_returns_200_blocked_with_required_permission(
         temp_db, monkeypatch
     ):
         monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

         response = client.post(
             "/query",
             json={"prompt": "hello world", "openrouter_api_key": "sk-whatever"},
         )

         assert response.status_code == 200
         body = response.json()
         assert body["status"] == "BLOCKED"
         assert body["required_permission"] == PERMISSION_QUERY_BYOK
     ```
     These six map 1:1 onto the story's five ACs (the mismatch/absent/matching trio together covers AC3+AC4).
- **Mirror**: `tests/test_auth_dependencies.py:104-110` for the `insert_user(...)` + `403` assertion shape; `app/services/authz.py:27-44` for which role to seed for each case.
- **Validate**: `python -m pytest tests/test_query_router.py -q` — all tests (existing + new) pass.

---

## End-to-End Tests

- [ ] `python -m pytest tests/test_query_router.py -q` — full file green, including all pre-existing tests unmodified
- [ ] `python -m pytest tests/test_query_pipeline_authorization.py tests/test_auth_dependencies.py tests/test_authz.py -q` — untouched suites still pass (no regression from the router change)
- [ ] Manual: `curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"prompt":"hi"}'` (no `Authorization` header) → `401`
- [ ] Manual: same request with `Authorization: Bearer <a user-role token>` and `"user_id":"someone-else"` in the body → `403`

---

## Validation

```bash
cd F:/AI/harness-ai
python -c "import app.routers.query"
python -m pytest tests/test_query_router.py tests/test_query_pipeline_authorization.py tests/test_auth_dependencies.py -q
```

---

## Acceptance Criteria

(Copied from story `STORY-013`)

- [ ] Given no `Authorization` header, when `POST /query` is called, then it returns `401` and no audit row is written
- [ ] Given a valid credential whose role lacks `query:submit`, when it is called, then it returns `403` naming the permission
- [ ] Given a body `user_id` different from the authenticated user, when it is called, then it returns `403` rather than silently overriding it
- [ ] Given a body `user_id` that matches or is absent, when it is called, then the request proceeds and the audited user id comes from the credential
- [ ] Given a policy refusal (model outside the allowlist, or BYOK without permission), when it is called, then it returns `200` with `status: "BLOCKED"` and `required_permission`
- [ ] All tasks completed
- [ ] `tests/test_query_router.py` passes in full, including all pre-existing tests unmodified in behavior
- [ ] Follows existing `Depends(require_permission(...))` / `HTTPException` / pipeline-identity patterns
