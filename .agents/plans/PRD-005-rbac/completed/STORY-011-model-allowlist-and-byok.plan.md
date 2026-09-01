---
story: STORY-011
prd: PRD-005
slug: model-allowlist-and-byok
title: Server-side model allowlist and BYOK as a privilege
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-005-rbac
created: 2026-08-28
---

# Plan: Server-side model allowlist and BYOK as a privilege

## Summary

`run_query()`'s step-0 block (STORY-010) today checks only `query:submit`. This story adds two more deny-by-default checks to that same block, both evaluated after `query:submit` and both before `check_duplicate()`: the requested `model` against the caller's role, and — only when the request carries one — the caller-supplied `openrouter_api_key` against `query:byok`. The model check is a new `authorize_model()` in `app/services/authz.py`: roles in a small `MODEL_ALLOWLIST_WILDCARD_ROLES` set (`{"admin"}`, matching PRD Section 7's `*` column) may request any model; every other role is checked against `settings.model_allowlist_list` (STORY-005, already shipped). The BYOK check reuses the existing `authorize(identity, PERMISSION_QUERY_BYOK)` — no new function needed. Both denials reuse STORY-010's block-then-return shape (`log_query(...)` then `return QueryBlockedForbiddenResponse(...)`), so a `_deny()` helper is extracted to avoid tripling that boilerplate across three checks in one function. `MODEL_ALLOWLIST` in `chat_ui/chat_ui/config.py` (frontend, different branch) is unaffected and stays a UI affordance only, per the story's Technical Notes.

## User Story

As a security admin
I want the requested model and any caller-supplied OpenRouter key checked against the caller's role
So that the allowlist is a real control rather than a frontend convenience

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-011-model-allowlist-and-byok.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/services/authz.py`, `app/services/query_pipeline.py`, pipeline + authz test suites |
| Story | STORY-011 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

---

## Skills In Use

None. `skills: []` in story frontmatter, and `.agents/skills/` does not exist in this repository (confirmed by glob and by the PRD-005 Appendix note).

---

## Patterns to Follow

### authorize() / PermissionDenied contract (mirror shape for authorize_model())
```
// SOURCE: app/services/authz.py:95-105
def authorize(identity: Identity, permission: str) -> None:
    if not settings.RBAC_ENABLED:
        return
    role_permissions = ROLE_PERMISSIONS.get(identity.role)
    if role_permissions is None or permission not in role_permissions:
        raise PermissionDenied(permission)
```

### Permission constants + policy-table-over-conditionals (mirror for the model wildcard set)
```
// SOURCE: app/services/authz.py:9-21
PERMISSION_QUERY_SUBMIT = "query:submit"
PERMISSION_QUERY_BYOK = "query:byok"
...
_KNOWN_PERMISSIONS = {...}
```

### model_allowlist_list (already shipped, STORY-005)
```
// SOURCE: app/config.py:31-33
@property
def model_allowlist_list(self) -> list[str]:
    return [item.strip() for item in self.MODEL_ALLOWLIST.split(",") if item.strip()]
```

### Current step-0 block in run_query() (what gets extended into a _deny() helper)
```
// SOURCE: app/services/query_pipeline.py:33-47
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

### PRD's documented reason text for a model-policy block (Section 10)
```
// SOURCE: .agents/PRDs/PRD-005-rbac/PRD.md:259-266
{
  "status": "BLOCKED",
  "reason": "Model not permitted for this role",
  "required_permission": "query:model:anthropic/claude-3.5-sonnet"
}
```

### Parametrized full-matrix test style (mirror for authorize_model() role coverage)
```
// SOURCE: tests/test_authz.py:35-55
_MATRIX_CASES = [
    (role, permission, permission in ROLE_PERMISSIONS[role])
    for role in ("admin", "auditor", "user")
    for permission in ALL_PERMISSIONS
]

@pytest.mark.parametrize("role, permission, expected_allowed", _MATRIX_CASES)
def test_matrix_cell_matches_prd_section_7(role, permission, expected_allowed):
    ...
```

### Pipeline authorization test fixtures (mirror for the new model/BYOK cases)
```
// SOURCE: tests/test_query_pipeline_authorization.py:18-45
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path

def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/authz.py` | UPDATE | Add `MODEL_ALLOWLIST_WILDCARD_ROLES` set and `authorize_model(identity, model)` — deny-by-default model check, `RBAC_ENABLED=false` bypass, wildcard roles allow any model, everyone else checked against `settings.model_allowlist_list` |
| `app/services/query_pipeline.py` | UPDATE | Add `authorize_model(identity, model)` after the existing `query:submit` check; add `authorize(identity, PERMISSION_QUERY_BYOK)` guarded by `openrouter_api_key is not None`; extract the repeated log-and-return denial shape into a local `_deny()` helper used by all three checks |
| `tests/test_authz.py` | UPDATE | New tests for `authorize_model()`: admin (wildcard) allows any model, `user` role allows only models in `MODEL_ALLOWLIST`, denial carries `query:model:<model>`, `RBAC_ENABLED=false` bypasses it too |
| `tests/test_query_pipeline_authorization.py` | UPDATE | New tests for AC1/AC2 (model outside allowlist blocked, never reaches `call_openrouter`), AC3/AC4 (BYOK without/with `query:byok`), AC5 (each denial writes exactly one audit row with `role` + the specific `denied_permission`) |

Not touched in this story (explicitly deferred by the Technical Notes / story dependency graph):
- `app/routers/query.py` — still calls `run_query(user_id=...)` from the pre-STORY-010 signature; STORY-013 rewires it to supply `identity` from the bearer token. Not this story's concern.
- `chat_ui/chat_ui/state.py` — STORY-014's concern.
- `chat_ui/chat_ui/config.py`'s `MODEL_ALLOWLIST` (frontend, on the unmerged `epic/PRD-004-chat-ui-redesign` branch) — stays a UI affordance, per the story's Technical Notes; this story's control is entirely server-side in `app/`.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add `authorize_model()` to `app/services/authz.py`

- **File**: `app/services/authz.py`
- **Action**: UPDATE
- **Implement**:
  1. After the `ROLE_PERMISSIONS` dict (around line 44), add a second, small policy table for the model check — data, not an `if identity.role == "admin"` conditional at the call site:
     ```python
     # Roles whose model allowlist is "*" (PRD-005 Section 7). Every other
     # role is checked against settings.model_allowlist_list.
     MODEL_ALLOWLIST_WILDCARD_ROLES = {"admin"}
     ```
  2. After `authorize()` (end of file), add:
     ```python
     def authorize_model(identity: Identity, model: str) -> None:
         """Deny-by-default model check (PRD-005 Section 7). Raises
         PermissionDenied(f"query:model:{model}") unless the identity's role
         has an unrestricted allowlist or the model is in
         settings.model_allowlist_list. RBAC_ENABLED=false bypasses this
         check too, same escape hatch as authorize()."""
         if not settings.RBAC_ENABLED:
             return

         if identity.role in MODEL_ALLOWLIST_WILDCARD_ROLES:
             return

         if model in settings.model_allowlist_list:
             return

         raise PermissionDenied(f"query:model:{model}")
     ```
  3. Do **not** add `query:model:<model>` to `_KNOWN_PERMISSIONS` — that set gates `RBAC_ROLES_FILE`'s static role→permission grants (STORY-007) and model permissions are dynamic per-model strings, not part of that matrix.
- **Mirror**: `app/services/authz.py:95-105` (`authorize()`'s bypass-then-deny-by-default shape).
- **Validate**: `python -c "import app.services.authz"` succeeds; `python -m pytest tests/test_authz.py -q` still passes (no existing test touches the new function or set).

### Task 2: Wire model + BYOK checks into `run_query()`'s step 0

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  1. Widen the import from `app.services.authz`:
     ```python
     from app.services.authz import (
         PERMISSION_QUERY_BYOK,
         PERMISSION_QUERY_SUBMIT,
         PermissionDenied,
         authorize,
         authorize_model,
     )
     ```
  2. Extract the existing denial shape into a module-level helper placed just above `run_query()`:
     ```python
     def _deny(
         identity: Identity, prompt: str, device: Optional[str], exc: PermissionDenied, reason: str
     ) -> QueryBlockedForbiddenResponse:
         log_query(
             user_id=identity.user_id,
             prompt=prompt,
             device=device,
             success=True,
             role=identity.role,
             denied_permission=exc.permission,
         )
         return QueryBlockedForbiddenResponse(reason=reason, required_permission=exc.permission)
     ```
  3. Replace the current step-0 block with three checks in this order — `query:submit`, then model, then BYOK — each using `_deny()`:
     ```python
     try:
         authorize(identity, PERMISSION_QUERY_SUBMIT)
     except PermissionDenied as exc:
         return _deny(identity, prompt, device, exc, "Missing required permission")

     try:
         authorize_model(identity, model)
     except PermissionDenied as exc:
         return _deny(identity, prompt, device, exc, "Model not permitted for this role")

     if openrouter_api_key is not None:
         try:
             authorize(identity, PERMISSION_QUERY_BYOK)
         except PermissionDenied as exc:
             return _deny(identity, prompt, device, exc, "Missing required permission")
     ```
  4. This is a pure refactor of the existing `query:submit` block (Task 1's helper reproduces it exactly) plus two new checks — no other line in `run_query()` changes; `check_duplicate()` still runs immediately after this block, unmoved.
- **Mirror**: `app/services/query_pipeline.py:33-47` (block being refactored); `.agents/PRDs/PRD-005-rbac/PRD.md:259-266` (the `"Model not permitted for this role"` reason text).
- **Validate**: `python -c "import app.services.query_pipeline"` succeeds; `python -m pytest tests/test_query_pipeline_authorization.py tests/test_chat_state.py tests/test_pii_dedup_isolation.py -q` — all pass unmodified (proves the refactor didn't change `query:submit`-denial behavior).

### Task 3: `authorize_model()` tests in `tests/test_authz.py`

- **File**: `tests/test_authz.py`
- **Action**: UPDATE
- **Implement**: Add `import` of `authorize_model` and `MODEL_ALLOWLIST_WILDCARD_ROLES` alongside the existing `authz` imports. Add tests:
  - `test_admin_model_wildcard_allows_any_model` (AC1): `Identity(role="admin")`, call `authorize_model(identity, "some-totally-unlisted-model")`, assert returns `None`.
  - `test_user_role_allows_models_in_allowlist`: `Identity(role="user")`, for each model in `settings.model_allowlist_list`, `authorize_model(...)` returns `None`.
  - `test_user_role_denies_model_outside_allowlist`: `Identity(role="user")`, `authorize_model(identity, "not-a-real-model")` raises `PermissionDenied` with `exc.permission == "query:model:not-a-real-model"`.
  - `test_rbac_disabled_bypasses_model_check` (mirrors `test_rbac_disabled_allows_even_an_unknown_role`): `monkeypatch.setattr(settings, "RBAC_ENABLED", False)`, `Identity(role="user")` (or an unknown role), any model allowed.
- **Mirror**: `tests/test_authz.py:35-55` (parametrized matrix style) and `tests/test_authz.py:110-115` (`RBAC_ENABLED=false` bypass test).
- **Validate**: `python -m pytest tests/test_authz.py -q` — all pass, including new tests.

### Task 4: Model + BYOK denial tests in `tests/test_query_pipeline_authorization.py`

- **File**: `tests/test_query_pipeline_authorization.py`
- **Action**: UPDATE
- **Implement**: Add `PERMISSION_QUERY_BYOK` to the existing `from app.services.authz import ...` line. Add tests, following the file's existing `temp_db` fixture and `_count_audit_rows()`/`_last_audit_id()` helpers:
  - `test_model_outside_allowlist_blocked_before_openrouter` (AC1 negative case / AC2): `Identity(user_id="ana", role="user")`, `model="not-a-real-model"`, `call_openrouter=_fail_if_called`; assert `QueryBlockedForbiddenResponse` with `required_permission == "query:model:not-a-real-model"`.
  - `test_admin_wildcard_model_reaches_openrouter` (AC1 positive case): `Identity(user_id="root", role="admin")`, an out-of-allowlist model string, `call_openrouter=_fake_call_openrouter`; assert `QuerySuccessResponse`.
  - `test_model_denial_writes_audit_row_with_role_and_permission` (AC5 for the model case): same as the AC3-style test already in the file but for the model denial — assert `role == "user"` and `denied_permission == "query:model:not-a-real-model"`.
  - `test_byok_without_permission_blocked_before_openrouter` (AC3): `Identity(user_id="ana", role="user")` (lacks `query:byok`), `openrouter_api_key="sk-caller-supplied"`, `call_openrouter=_fail_if_called`; assert `QueryBlockedForbiddenResponse` with `required_permission == PERMISSION_QUERY_BYOK`.
  - `test_byok_with_permission_uses_supplied_key` (AC4): `Identity(user_id="root", role="admin")` (holds `query:byok`), `openrouter_api_key="sk-caller-supplied"`; use a `call_openrouter` fake that records the `api_key` kwarg it was called with and asserts it equals `"sk-caller-supplied"` — proving the key is used exactly as today once permitted.
  - `test_byok_denial_writes_audit_row_with_role_and_permission` (AC5 for the BYOK case): assert `role == "user"` and `denied_permission == PERMISSION_QUERY_BYOK`.
- **Mirror**: `tests/test_query_pipeline_authorization.py:52-102` (existing AC2/AC3 tests for `query:submit` — same shape, different permission/model).
- **Validate**: `python -m pytest tests/test_query_pipeline_authorization.py -q` — all pass, including new tests.

---

## End-to-End Tests

- [ ] `python -m pytest tests/test_query_pipeline_authorization.py tests/test_authz.py -q` — all green, including the new model/BYOK cases
- [ ] `python -m pytest tests/test_chat_state.py -k "run_query_success or run_query_duplicate or run_query_suspicious or run_query_openrouter_error" tests/test_pii_dedup_isolation.py -k test_hash_prompt_only_ever_receives_raw_text -q` — unaffected direct-call tests stay green (proves the `_deny()` refactor is behavior-preserving for the `query:submit` path)
- [ ] Manual: `authorize_model(Identity(user_id="a", role="user"), "gpt-4")` returns `None` (in the default allowlist); `authorize_model(Identity(user_id="a", role="user"), "gpt-5-turbo-mega")` raises `PermissionDenied("query:model:gpt-5-turbo-mega")`
- [ ] Manual: a `run_query(...)` call with `identity=Identity(user_id="a", role="user")`, `openrouter_api_key="sk-x"` returns `QueryBlockedForbiddenResponse(required_permission="query:byok")` and writes an audit row with `role="user"`, `denied_permission="query:byok"`, `success=1`, without calling the mocked OpenRouter client

---

## Validation

```bash
cd F:/AI/harness-ai
python -m pytest tests/test_authz.py tests/test_query_pipeline_authorization.py tests/test_chat_state.py tests/test_pii_dedup_isolation.py tests/test_config.py tests/test_schemas.py tests/test_audit_logger.py -q
```
Expect all tests in the files above to pass. A full-repo `python -m pytest -q` run continues to show the pre-existing, documented failures from STORY-010 in `tests/test_query_router.py`, `tests/test_pii_redaction_integration.py`, and `tests/test_integration.py` (real router/chat-UI callers not yet updated to supply `identity` — that's STORY-013/STORY-014's scope) — this story neither fixes nor worsens those.

---

## Acceptance Criteria

(Copied from story `STORY-011`)

- [ ] Given a role whose allowlist is `*`, when any model is requested, then it is allowed
- [ ] Given a `user`-role caller requesting a model outside `MODEL_ALLOWLIST`, when `run_query()` runs, then it returns `QueryBlockedForbiddenResponse` with `required_permission="query:model:<model>"` and never calls OpenRouter
- [ ] Given a request carrying `openrouter_api_key` from an identity without `query:byok`, when `run_query()` runs, then it is refused before the OpenRouter call
- [ ] Given the same request from an identity holding `query:byok`, when it runs, then the supplied key is used exactly as today
- [ ] Given either refusal, when it happens, then an audit row records the role and the missing permission
- [ ] All tasks completed
- [ ] `app/services/authz.py` and `app/services/query_pipeline.py` import cleanly and all tasks' tests pass
- [ ] Follows existing block-then-return / `log_query` / policy-table-over-conditionals patterns
