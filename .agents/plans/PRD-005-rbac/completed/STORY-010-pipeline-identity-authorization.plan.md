---
story: STORY-010
prd: PRD-005
slug: pipeline-identity-authorization
title: run_query() requires an Identity and authorizes as step 0
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-005-rbac
created: 2026-08-28
---

# Plan: run_query() requires an Identity and authorizes as step 0

## Summary

`app/services/query_pipeline.py:run_query()` currently takes a free-standing `user_id: str` and starts with `check_duplicate()`. We make `identity: Identity` a required parameter — replacing `user_id` entirely — and insert authorization as step 0: `authorize(identity, PERMISSION_QUERY_SUBMIT)` runs before `check_duplicate()`. A denial writes one audit row (`role`, `denied_permission`, `success=True`) via the existing `log_query(...)` block-then-return shape and returns the `QueryBlockedForbiddenResponse` STORY-008 already added to the `QueryResponse` union — `call_openrouter` is never reached. Because `identity` has no default, any caller that omits it fails at the call site rather than silently bypassing the check; this is the structural fix for PRD Risk 1. `app/routers/query.py` and `chat_ui/chat_ui/state.py` are **not** touched here — updating those callers to actually supply `identity` is STORY-013 and STORY-014, which this story blocks.

## User Story

As a security admin
I want `run_query()` to require a verified identity and authorize before anything else
So that both ingresses are covered by one check that cannot be forgotten

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-010-pipeline-identity-authorization.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/services/query_pipeline.py`, pipeline test suite |
| Story | STORY-010 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

---

## Skills In Use

None. `skills: []` in story frontmatter; `.agents/skills/` contains only `frontend-design`, which does not apply to this backend-only story.

---

## Patterns to Follow

### Block-then-return shape (mirror for the new forbidden block)
```
// SOURCE: app/services/query_pipeline.py:27-40 (duplicate block)
duplicate_result = check_duplicate(prompt)

if duplicate_result.is_duplicate:
    log_query(
        user_id=user_id,
        prompt=prompt,
        device=device,
        was_duplicate_blocked=True,
        success=True,
    )
    return QueryBlockedDuplicateResponse(
        reason="Duplicate query within 24 hours",
        first_query_at=duplicate_result.first_query_at,
    )
```

### authorize() / PermissionDenied contract
```
// SOURCE: app/services/authz.py:95-105
def authorize(identity: Identity, permission: str) -> None:
    if not settings.RBAC_ENABLED:
        return
    role_permissions = ROLE_PERMISSIONS.get(identity.role)
    if role_permissions is None or permission not in role_permissions:
        raise PermissionDenied(permission)
```
`PermissionDenied.permission` (app/services/authz.py:47-53) carries the permission name that was checked — that value is both `denied_permission` in the audit row and `required_permission` in the response body, with no re-derivation needed.

### Identity value object
```
// SOURCE: app/services/identity.py:19-29
@dataclass(frozen=True)
class Identity:
    user_id: str
    role: str
```

### log_query() role/denied_permission kwargs (already shipped, STORY-009)
```
// SOURCE: app/services/audit_logger.py:12-28
def log_query(
    user_id: str,
    prompt: str,
    ...
    role: Optional[str] = None,
    denied_permission: Optional[str] = None,
) -> int:
```

### QueryBlockedForbiddenResponse (already shipped, STORY-008)
```
// SOURCE: app/models/schemas.py:36-39
class QueryBlockedForbiddenResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    required_permission: str
```

### Direct-call pipeline test shape (what the two test-file edits mirror)
```
// SOURCE: tests/test_chat_state.py:91-108
def test_run_query_success_returns_response_and_logs_row(temp_db):
    def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

    result = run_query(
        user_id="juan@empresa.com",
        prompt="hello world",
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_fake_call_openrouter,
    )
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/query_pipeline.py` | UPDATE | Replace `user_id: str` with required `identity: Identity`; add step-0 `authorize()` check ahead of `check_duplicate()`; route `user_id=` in every `log_query(...)` call through `identity.user_id`; widen `QueryPipelineResult` to include `QueryBlockedForbiddenResponse` |
| `tests/test_chat_state.py` | UPDATE | AC1 section's four direct `run_query(...)` calls (success, duplicate, suspicious, openrouter-error) pass `identity=Identity(user_id="juan@empresa.com", role="user")` instead of `user_id="juan@empresa.com"`; import `Identity` |
| `tests/test_pii_dedup_isolation.py` | UPDATE | The one direct `run_query(...)` call (`test_hash_prompt_only_ever_receives_raw_text`) gets the same `identity=` swap; import `Identity` |
| `tests/test_query_pipeline_authorization.py` | CREATE | New tests for AC2 (deny before `check_duplicate`/`call_openrouter`), AC3 (exactly one audit row, `role` + `denied_permission`, `success=True`), AC5 (omitting `identity` raises `TypeError` — enforcement by signature) |

Not touched in this story (explicitly deferred by the Technical Notes / story dependency graph):
- `app/routers/query.py` — STORY-013 supplies `identity` from the bearer token
- `chat_ui/chat_ui/state.py` — STORY-014 supplies `identity` from the login session

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add step-0 authorization to `run_query()`

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  1. Add imports:
     ```python
     from app.models.schemas import (
         QueryBlockedDuplicateResponse,
         QueryBlockedForbiddenResponse,
         QueryBlockedSuspiciousResponse,
         QuerySuccessResponse,
     )
     from app.services.authz import PERMISSION_QUERY_SUBMIT, PermissionDenied, authorize
     from app.services.identity import Identity
     ```
  2. Widen the result alias:
     ```python
     QueryPipelineResult = Union[
         QuerySuccessResponse,
         QueryBlockedDuplicateResponse,
         QueryBlockedSuspiciousResponse,
         QueryBlockedForbiddenResponse,
     ]
     ```
  3. Change the signature's first parameter from `user_id: str` to `identity: Identity` (keeps `call_openrouter`'s default last, as today):
     ```python
     def run_query(
         identity: Identity,
         prompt: str,
         device: Optional[str],
         model: str,
         openrouter_api_key: Optional[str],
         call_openrouter: Callable[..., OpenRouterResult] = call_openrouter,
     ) -> QueryPipelineResult:
     ```
  4. Insert step 0 as the first statement in the function body, before the existing `duplicate_result = check_duplicate(prompt)` line:
     ```python
     try:
         authorize(identity, PERMISSION_QUERY_SUBMIT)
     except PermissionDenied as exc:
         log_query(
             user_id=identity.user_id,
             prompt=prompt,
             device=device,
             success=True,
             role=identity.role,
             denied_permission=exc.permission,
         )
         return QueryBlockedForbiddenResponse(
             reason="Missing required permission",
             required_permission=exc.permission,
         )
     ```
  5. In every remaining `log_query(...)` call in the function (duplicate block, suspicious block, redact-input-failure block, openrouter-error block, redact-output-failure block, success block — six call sites total), replace `user_id=user_id` with `user_id=identity.user_id`.
- **Mirror**: the duplicate block immediately below (`app/services/query_pipeline.py:27-40`) for the try/log/return shape; `app/services/authz.py:95-105` for the `authorize()`/`PermissionDenied` contract.
- **Validate**: `python -c "import app.services.query_pipeline"` succeeds; `cd . && python -m pytest tests/test_authz.py tests/test_schemas.py -q` still passes (unaffected modules, cheap smoke check that nothing at import time broke).

### Task 2: Update `tests/test_chat_state.py`'s direct `run_query()` calls for AC1/AC4

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**:
  1. Add `from app.services.identity import Identity` to the imports (near the existing `from app.services.query_pipeline import run_query` at line 24).
  2. In the four AC1-section tests (`test_run_query_success_returns_response_and_logs_row` at line 91, `test_run_query_duplicate_blocked_before_openrouter_call` at line 111, `test_run_query_suspicious_pattern_blocked_before_openrouter_call` at line 130, `test_run_query_openrouter_error_raises_and_logs_failure` at line 148), replace the `user_id="juan@empresa.com",` line with `identity=Identity(user_id="juan@empresa.com", role="user"),` — `user` role holds `query:submit`, so behavior is unchanged (AC4).
- **Mirror**: `app/services/authz.py:27-44` (ROLE_PERMISSIONS — confirms `"user"` grants `query:submit`).
- **Validate**: `python -m pytest tests/test_chat_state.py -k "run_query_success or run_query_duplicate or run_query_suspicious or run_query_openrouter_error" -q` passes.

### Task 3: Update `tests/test_pii_dedup_isolation.py`'s direct `run_query()` call

- **File**: `tests/test_pii_dedup_isolation.py`
- **Action**: UPDATE
- **Implement**:
  1. Add `from app.services.identity import Identity` to the imports (near line 29's `from app.services.query_pipeline import run_query`).
  2. In `test_hash_prompt_only_ever_receives_raw_text` (line 265), replace `user_id="juan@empresa.com",` (line 286) with `identity=Identity(user_id="juan@empresa.com", role="user"),`.
- **Mirror**: same as Task 2.
- **Validate**: `python -m pytest tests/test_pii_dedup_isolation.py -k test_hash_prompt_only_ever_receives_raw_text -q` passes.

### Task 4: New authorization-at-step-0 test file

- **File**: `tests/test_query_pipeline_authorization.py`
- **Action**: CREATE
- **Implement**: Follow the `temp_db` fixture + `_count_audit_rows()` helper pattern from `tests/test_chat_state.py:36-47`. Cover:
  - `test_forbidden_identity_blocked_before_check_duplicate` (AC2): identity with role `auditor` (lacks `query:submit`) calls `run_query(...)`; assert result is `QueryBlockedForbiddenResponse` with `required_permission == PERMISSION_QUERY_SUBMIT`; assert `call_openrouter` fixture (`_fail_if_called`) never invoked; spy/monkeypatch `query_pipeline.check_duplicate` to assert it is **not** called either, proving the check short-circuits ahead of dedup as AC2 requires.
  - `test_forbidden_identity_writes_exactly_one_audit_row` (AC3): before/after `_count_audit_rows()` delta is exactly 1; fetch the row via `get_audit_log(...)` and assert `role == "auditor"`, `denied_permission == PERMISSION_QUERY_SUBMIT`, `success is True`.
  - `test_authorized_identity_reaches_openrouter` (AC4 sanity): role `user` (or `admin`) with a fake `call_openrouter` returns `QuerySuccessResponse`, proving the new step 0 does not disturb the happy path beyond the identity argument change already covered by Tasks 2-3.
  - `test_run_query_without_identity_raises_type_error` (AC5): call `run_query(prompt=..., device=None, model="gpt-4", openrouter_api_key=None)` with no `identity` kwarg and assert `pytest.raises(TypeError)` — "enforcement by signature," not a runtime guard.
  - Import `PERMISSION_QUERY_SUBMIT` from `app.services.authz` and `Identity` from `app.services.identity`; use `os.environ.setdefault(...)` + `temp_db` fixture exactly as the other pipeline test files do (see Task 2's mirror file for the boilerplate header).
- **Mirror**: `tests/test_chat_state.py:36-67` (fixtures/helpers), `tests/test_authz.py:45-55` (parametrized matrix-cell style, if useful for role coverage), `app/services/query_pipeline.py:27-40` (what "before check_duplicate" means operationally).
- **Validate**: `python -m pytest tests/test_query_pipeline_authorization.py -q` — all new tests pass.

---

## End-to-End Tests

- [ ] `python -m pytest tests/test_query_pipeline_authorization.py tests/test_authz.py tests/test_schemas.py tests/test_audit_logger.py -q` — all green
- [ ] `python -m pytest tests/test_chat_state.py -k "run_query_success or run_query_duplicate or run_query_suspicious or run_query_openrouter_error" tests/test_pii_dedup_isolation.py -k test_hash_prompt_only_ever_receives_raw_text -q` — all green (the direct-call pipeline tests, AC4)
- [ ] Manual: a denied `run_query(identity=Identity(user_id="a", role="auditor"), prompt="hi", device=None, model="gpt-4", openrouter_api_key=None)` returns `QueryBlockedForbiddenResponse(reason=..., required_permission="query:submit")` and the audit row it wrote has `role="auditor"`, `denied_permission="query:submit"`, `success=1`

**Known, accepted regression (not a gate for this story — verified by running the full suite)**: any test that drives `run_query()` through the real, unmigrated callers now fails with `TypeError: run_query() got an unexpected keyword argument 'user_id'` (router) or the equivalent through `chat_ui.state.send()`'s real call. This is **not** limited to two files — running `python -m pytest tests/ -q` after this story's changes shows exactly 71 failures, all contained to:
- `tests/test_query_router.py` (30) — hits `POST /query` via `TestClient`, real router
- `tests/test_pii_redaction_integration.py` (14) — same, real router
- `tests/test_integration.py` (10) — same, real router
- `tests/test_pii_dedup_isolation.py` (11 of its tests, not just the one updated in Task 3) — several call `POST /query` via `TestClient` rather than `run_query()` directly
- `tests/test_chat_state.py` (6 of its tests, not the 4 updated in Task 2) — tests that only monkeypatch `call_openrouter`/`chat_state_mod.call_openrouter` and let the real `chat_ui.state.send()` call the real `run_query()`, which now requires `identity`

No other test file is affected (`test_authz.py`, `test_schemas.py`, `test_audit_logger.py`, `test_admin_auth.py`, `test_db.py`, `test_identity.py`, `test_manage_users_cli.py`, `test_config.py`, `test_main.py`, `test_duplicate_checker.py`, `test_openrouter_client.py`, `test_pattern_detector.py`, `test_route_reservations.py`, `test_stats_router.py`, `test_chat_components_import.py`, `test_copy.py`, `test_pii_badge.py`, `test_pii_redactor.py`, `test_success_metadata_footer.py`, and the new `test_query_pipeline_authorization.py` all stay green). This is the direct, unavoidable consequence of the story's own Technical Notes deferring `app/routers/query.py` to STORY-013 and `chat_ui/chat_ui/state.py` to STORY-014 — do not patch either caller in this story; that would duplicate their scope with a throwaway shape (no bearer-token resolution or login session yet exists on those paths).

---

## Validation

```bash
cd F:/AI/harness-ai
python -m pytest tests/test_query_pipeline_authorization.py tests/test_authz.py tests/test_schemas.py tests/test_audit_logger.py tests/test_chat_state.py tests/test_pii_dedup_isolation.py -q
```
Expect all tests in the files above to pass. A full-repo `python -m pytest -q` run will additionally show the accepted, documented failures in `tests/test_query_router.py` and `tests/test_integration.py` described above — do not treat those as this story's regressions.

---

## Acceptance Criteria

(Copied from story `STORY-010`)

- [ ] Given `run_query(...)`, when its signature is defined, then `identity: Identity` is a **required** parameter and the free-standing `user_id: str` input is removed — the audited user id comes from `identity.user_id`
- [ ] Given an identity lacking `query:submit`, when `run_query()` is called, then it returns `QueryBlockedForbiddenResponse` before `check_duplicate()` runs, and `call_openrouter` is never invoked
- [ ] Given that denial, when it happens, then exactly one audit row is written carrying `role` and `denied_permission="query:submit"`, with `success=1`
- [ ] Given an authorized identity, when `run_query()` runs, then steps 1-6 behave exactly as today and every existing pipeline test passes with only the identity argument added
- [ ] Given a caller that omits `identity`, when the call is made, then it fails outright rather than proceeding unauthorized
- [ ] All tasks completed
- [ ] `app/services/query_pipeline.py` imports cleanly and existing pipeline-level tests (Tasks 2-4) pass
- [ ] Follows existing block-then-return / `log_query` patterns
