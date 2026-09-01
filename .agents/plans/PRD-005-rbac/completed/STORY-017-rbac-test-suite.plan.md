---
story: STORY-017
prd: PRD-005
slug: rbac-test-suite
title: RBAC test suite — full matrix coverage and ingress parity
type: technical
complexity: medium
epic_branch: epic/PRD-005-rbac
created: 2026-08-29
---

# Plan: RBAC test suite — full matrix coverage and ingress parity

## Summary

STORY-006 through STORY-016 already built the RBAC control and left substantial *piecemeal* test coverage behind them (`tests/test_authz.py`'s raw matrix, `tests/test_query_router.py`'s router-level checks, `tests/test_chat_state.py`'s chat-side checks, `tests/test_audit_router.py`/`tests/test_stats_router.py`'s admin-endpoint checks, `tests/test_db.py`'s migration fixture). What does **not** exist yet is a single suite that (a) walks the full role×permission matrix through the *real* endpoints/pipeline rather than only `authorize()` in isolation, and (b) proves, for the permissions `run_query()` itself enforces, that the HTTP ingress and the chat-UI ingress reach the identical authorization decision — the regression guard for PRD Risk 1. This story adds `tests/test_rbac.py` (new) for the matrix-through-real-surfaces coverage and a full pre-RBAC-database-to-successful-query lifecycle test, and extends `tests/test_chat_state.py` with the cross-ingress parity tests, following the exact pattern its own `test_chat_and_api_audit_rows_share_schema_and_fields` already established for the grant path. No production code changes — this is a test-only story.

A close reading of the current implementation surfaces one nuance the acceptance criteria don't spell out, and this plan makes an explicit, documented call on it rather than silently picking one interpretation — see **Design Decision: query:submit's audit-row asymmetry** below. If the user disagrees with that call, it's cheap to revise before `/implement` runs.

## User Story

As a maintainer
I want a suite covering the whole permission matrix through both ingresses
So that the control cannot silently degrade when a new caller is added

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-017-rbac-test-suite.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | medium |
| Systems Affected | `tests/` only (backend + chat UI test suites); no production code |
| Story | STORY-017 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` contains only `frontend-design` (visual/CSS design guidance for new UI surfaces), which does not apply — this story writes pytest test code against an already-implemented backend and an already-implemented `ChatState`, with no new UI or visual work. The story's own frontmatter carries `skills: []`. (The `chat_ui/AGENTS.md` Reflex-skills requirement gates *writing or editing Reflex components/state*; this story only edits a test file that exercises the existing `ChatState`, so it doesn't trigger that requirement either.)

---

## Design Decision: query:submit's audit-row asymmetry

PRD Section 9's HTTP semantics table draws a deliberate line: a missing *endpoint* permission (`query:submit`, `audit:read:*`, `stats:read`) is a `401`/`403` transport failure, while a *content* policy refusal (model outside allowlist, BYOK without permission) is `200` + `status: "BLOCKED"`, logged like any other pipeline block. STORY-013 implemented `query:submit`'s HTTP-side check as `Depends(require_permission(PERMISSION_QUERY_SUBMIT))` on the router itself — confirmed in `app/routers/query.py:18` and proven by the existing `tests/test_query_router.py::test_identity_lacking_query_submit_returns_403_naming_permission` (asserts `_count_audit_rows() == 0`). That means an HTTP `query:submit` denial **never reaches** `run_query()`'s own step-0 `authorize()` call (`app/services/query_pipeline.py:54`) — the router stops it first, and no audit row is written for that denial.

The chat ingress has no router layer at all: `ChatState._do_send()` calls `run_query(...)` directly, so its *only* enforcement of `query:submit` is that same step-0 check inside `run_query()` — which **does** log an audit row via `_deny()` (`app/services/query_pipeline.py:31-42`) and returns a `QueryBlockedForbiddenResponse`, rendered as a `"forbidden"` bubble.

So for `query:submit` specifically, taken literally, "exactly one audit row" (Story AC3) is true for the chat ingress and false for the HTTP ingress (zero rows) — by design, not by omission. This plan does not paper over that by weakening the HTTP-side assertion or inventing a redundant audit write. Instead, Task 5 asserts **decision parity** (both ingresses refuse to serve the request; OpenRouter is never called by either) while explicitly asserting and documenting the differing audit-row mechanics, citing PRD Section 9 and the STORY-013 report's own stated rationale ("ahead of — and in addition to — `run_query()`'s own ... defense-in-depth check"). `query:byok` and the model allowlist have no such asymmetry — both ingresses reach them only through `run_query()`'s internal checks, so Task 4's parity test for the model allowlist gets a real, symmetric one-row-per-ingress assertion, which is the strongest single proof of PRD Risk 1's mitigation this suite can offer.

One more structural fact worth surfacing rather than treating as a gap: `ChatState._do_send()` hardcodes `openrouter_api_key=None` on every call (`chat_ui/chat_ui/state.py:163`) — the chat UI has no BYOK input at all. `query:byok` is therefore reachable only through the HTTP ingress; there is no second ingress to compare it against. Task 3 asserts this as a pinned invariant (so a future BYOK affordance added to the chat UI is forced to reconsider this story's coverage) rather than silently skipping BYOK's ingress-parity story.

---

## Patterns to Follow

### Per-file test setup (no `tests/conftest.py` exists anywhere in this repo — deliberate convention; every file redefines these ~15 lines locally)
```python
# SOURCE: tests/test_query_router.py:1-46, tests/test_chat_state.py:1-56 (same shape in every test file)
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import get_connection, init_db, insert_user
from app.db.models import User
from app.main import app
from app.services.identity import hash_token

client = TestClient(app)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path


def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]


def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")
```

### Driving the matrix off the real matrix, never a re-hardcoded copy
```python
# SOURCE: app/services/authz.py:10-45 — import the live constants so a future
# permission/role change makes this suite fail loudly instead of silently
# testing a stale copy (the exact "cannot silently degrade" the story exists for).
from app.services.authz import (
    PERMISSION_AUDIT_READ_ALL,
    PERMISSION_AUDIT_READ_OWN,
    PERMISSION_QUERY_BYOK,
    PERMISSION_QUERY_SUBMIT,
    PERMISSION_STATS_READ,
    ROLE_PERMISSIONS,
)

_ROLES = ("admin", "auditor", "user")
```

### Ingress 1 — HTTP, mocking `call_openrouter` at the router seam
```python
# SOURCE: tests/test_query_router.py:73-94
monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
response = client.post(
    "/query",
    headers={"Authorization": f"Bearer {token}"},
    json={"prompt": "hello world"},
)
```

### Ingress 2 — chat UI, bypassing the background-task guard
```python
# SOURCE: tests/test_chat_state.py:89-99
def _make_state(user_id: str, token: str) -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = user_id
    state._token = token
    return state


async def _send(state: ChatState, text: str) -> None:
    state.input_text = text
    handler = type(state).event_handlers["send"]
    await handler.fn(state)  # bypasses the background-task chain guard on state.send()
```
Mock `call_openrouter` at `chat_state_mod.call_openrouter` (not `app.routers.query.call_openrouter` — a different import binding), per `tests/test_chat_state.py:196`.

### Cross-ingress comparison in one test (the direct precedent for this story's parity tests)
```python
# SOURCE: tests/test_chat_state.py:416-462 (test_chat_and_api_audit_rows_share_schema_and_fields)
# — the grant-path precedent this story mirrors for the deny path.
state = _make_state()
await _send(state, "prompt from chat")
chat_row_id = _last_audit_id()

client.post("/query", headers={"Authorization": f"Bearer {_AUTH_TOKEN}"}, json={"prompt": "prompt from api"})
api_row_id = _last_audit_id()

chat_entry = get_audit_log(chat_row_id)
api_entry = get_audit_log(api_row_id)
for field in ("user_id", "model_used", "tokens_used", ...):
    assert getattr(chat_entry, field) == getattr(api_entry, field), field
```

### The pre-RBAC migration fixture already exists — reuse it, don't re-derive it
```python
# SOURCE: tests/test_db.py:202-270 (_create_pre_rbac_database, test_init_db_migrates_pre_rbac_database)
# Builds the 17-column post-PII/pre-RBAC audit_logs table via raw sqlite3.connect,
# inserts one row, then proves init_db() adds role/denied_permission with existing
# rows preserved (NULL in both new fields). AC4 is already fully satisfied by this
# test — Task 2 below builds one level higher (migrate -> bootstrap -> query) rather
# than re-proving the ALTER TABLE mechanics tests/test_db.py already owns.
```

### Deny-by-default with a role absent from the matrix (existing precedent)
```python
# SOURCE: tests/test_audit_router.py:235-245
insert_user(User(user_id="outsider", role="guest", token_hash=hash_token("guest-token")))
response = client.get("/audit", headers={"Authorization": "Bearer guest-token"})
assert response.status_code == 403
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_rbac.py` | CREATE | Full role×permission matrix through the real endpoints/pipeline (not just `authorize()`), the BYOK HTTP-only structural guard, and a pre-RBAC-migration-to-successful-query lifecycle test |
| `tests/test_chat_state.py` | UPDATE | Cross-ingress parity tests: model-allowlist denial (symmetric, one audit row per ingress) and `query:submit` denial (decision parity with documented audit-row asymmetry) |

No production code files change. No `chat_ui` component files change.

---

## Tasks

Execute in order. Each task is atomic and independently verifiable.

### Task 1: Create `tests/test_rbac.py` — full role×permission matrix through real endpoints

- **File**: `tests/test_rbac.py`
- **Action**: CREATE
- **Implement**:
  - Standard preamble (env vars, `temp_db` fixture, `_count_audit_rows`, `_fail_if_called`) per the Patterns section.
  - Import `ROLE_PERMISSIONS` and the five `PERMISSION_*` constants from `app.services.authz` — never hardcode a second copy of the matrix.
  - `test_query_submit_matrix_through_post_query` — parametrized over `_ROLES`; seed one user per role, `expected_allowed = PERMISSION_QUERY_SUBMIT in ROLE_PERMISSIONS[role]`; POST `/query` with a unique clean prompt and a mocked successful `call_openrouter`; assert `200` + `SUCCESS` when allowed, `403` + `{"detail": f"Permission denied: {PERMISSION_QUERY_SUBMIT}"}` and zero new audit rows when denied.
  - `test_stats_read_matrix_through_get_stats` — parametrized over `_ROLES`; `expected_allowed = PERMISSION_STATS_READ in ROLE_PERMISSIONS[role]`; GET `/stats`; assert `200` when allowed, `403` naming the permission when denied.
  - `test_audit_scope_selection_matrix_through_get_audit` — parametrized over `_ROLES`; seed two audit rows for two different users; GET `/audit` as each role; assert admin/auditor (hold `audit:read:all`) see both rows and `total == 2`, `user` (holds only `audit:read:own`) sees exactly its own row and `total == 1`. Mirrors `app/routers/admin.py:29-41`'s actual fallback order (`audit:read:all` tried first) rather than re-deriving it.
  - `test_query_byok_matrix_through_post_query_for_roles_holding_query_submit` — parametrized over `("admin", "user")` only (the two roles holding `query:submit`; `auditor` is denied at the `query:submit` gate before BYOK is ever reachable — document this exclusion in a comment rather than silently omitting it); `expected_allowed = PERMISSION_QUERY_BYOK in ROLE_PERMISSIONS[role]`; POST `/query` with `openrouter_api_key="sk-test"` and `call_openrouter=_fail_if_called`-equivalent monkeypatch; assert `200 SUCCESS` (admin, real mocked success) vs `200 BLOCKED` with `required_permission == PERMISSION_QUERY_BYOK` and one new audit row (`role="user"`, `denied_permission="query:byok"`) for `user`, with `call_openrouter` never invoked in the denied case.
  - `test_model_allowlist_matrix_through_post_query` — parametrized over `("admin", "user")`; `admin` (wildcard) gets an unlisted model and must succeed; `user` gets the same unlisted model and must get `200 BLOCKED` with `required_permission == f"query:model:{model}"`, one audit row, `call_openrouter` never invoked.
  - `test_unknown_role_denied_by_default_through_post_query` — role `"guest"` (absent from `ROLE_PERMISSIONS`, mirroring `tests/test_audit_router.py:235-245`'s precedent) → `403` on `/query`, mirroring the deny-by-default guarantee at the real endpoint rather than only at `authorize()`.
- **Mirror**: `tests/test_query_router.py:73-149` (request/assert shape), `tests/test_audit_router.py:192-245` (scope + deny-by-default), `tests/test_stats_router.py:182-193` (403 naming the permission).
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_rbac.py -q`

### Task 2: Add the pre-RBAC-migration-to-successful-query lifecycle test

- **File**: `tests/test_rbac.py`
- **Action**: UPDATE (append)
- **Implement**: `test_full_rbac_lifecycle_after_migrating_pre_rbac_database` — reuses the exact `_create_pre_rbac_database(db_path)` helper's shape from `tests/test_db.py:202-237` (either import it directly from `tests.test_db` or duplicate the ~20-line helper per the repo's stated no-shared-fixture convention — prefer importing it, since it is a pure helper function, not a fixture, and re-deriving the legacy 17-column DDL by hand risks it drifting from the real one). Sequence: build the pre-RBAC database file → `init_db()` (proves the migration ran, but do not re-assert the column-level mechanics `tests/test_db.py` already owns) → `insert_user(User(...))` + `hash_token(...)` to bootstrap one `admin`-role user, mirroring exactly what `scripts/manage_users.py:_create_user` does → `resolve(token)` returns a valid `Identity` → `run_query(identity=..., ...)` with a mocked successful `call_openrouter` returns `QuerySuccessResponse` and the legacy row (inserted before migration) is still present and unaffected (`count_audit_logs() == 2`: the pre-existing row plus this new one). This is the one test in the suite that proves the full chain — migration, bootstrap, identity resolution, authorization, and the pipeline — composes correctly end to end, which none of the existing per-layer tests do together.
- **Mirror**: `tests/test_db.py:202-270` (fixture + migration assertions), `scripts/manage_users.py:31-43` (`_create_user`'s exact `insert_user`/`hash_token`/`issue_token` sequence).
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_rbac.py -q`

### Task 3: Add the BYOK-is-HTTP-only structural guard

- **File**: `tests/test_rbac.py`
- **Action**: UPDATE (append)
- **Implement**: `test_chat_state_never_forwards_a_byok_key_so_query_byok_has_no_chat_ingress` — monkeypatch `chat_state_mod.run_query` to capture its `openrouter_api_key` kwarg, drive a real `send()` via the `_make_state`/`_send` pattern (see Task 4/5's chat helpers — duplicate the ~10-line pair here per the no-shared-fixture convention, since this file has no other chat-UI test needing them), and assert the captured value is always `None` — pinning `chat_ui/chat_ui/state.py:163`'s hardcoded `openrouter_api_key=None` as an explicit, named invariant. This documents *why* Task 4/5 don't attempt a BYOK ingress-parity test (there being only one ingress to test), and turns a silent gap into a test that fails the moment someone adds a BYOK field to the chat composer without also revisiting this story's scope.
- **Mirror**: `tests/test_chat_state.py:389-409` (`test_chat_state_send_passes_resolved_identity_and_prompt_to_run_query` — same capture-the-kwarg pattern).
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_rbac.py -q`

### Task 4: Extend `tests/test_chat_state.py` — model-allowlist denial, identical through both ingresses

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE (append)
- **Implement**: `test_model_allowlist_denial_identical_through_chat_and_api` — seed one `user`-role identity; pick a model string not in `settings.model_allowlist_list`; drive it through `_send(state, ...)` with `state.selected_model` set to that model (mock `chat_state_mod.call_openrouter` to `_fail_if_called`) and separately through `client.post("/query", ...)` with the same model and the same identity's token (mock `app.routers.query.call_openrouter` to `_fail_if_called`). Assert: both are denied (`state.messages[-1].kind == "forbidden"` / HTTP `200` `status == "BLOCKED"`), both carry `required_permission == f"query:model:{model}"`, both write exactly one new audit row each (two total) with `role == "user"` and `denied_permission == f"query:model:{model}"`, and `call_openrouter` is never invoked via either monkeypatched target. This is the symmetric, no-caveats proof of PRD Risk 1's mitigation — the strongest single test in the suite.
- **Mirror**: `tests/test_chat_state.py:416-462` (`test_chat_and_api_audit_rows_share_schema_and_fields` — the grant-path structural precedent for comparing both ingresses in one test), `tests/test_chat_state.py:248-269` (`test_chat_state_send_forbidden_response_renders_its_own_bubble_not_injection` — asserting the `"forbidden"` bubble shape), `tests/test_query_router.py:136-149` (the HTTP-side BLOCKED assertion shape).
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_chat_state.py -q`

### Task 5: Extend `tests/test_chat_state.py` — `query:submit` denial decision-parity with documented audit asymmetry

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE (append)
- **Implement**: `test_query_submit_denial_decision_parity_across_ingresses_with_documented_audit_asymmetry` — seed one `auditor`-role identity (holds `audit:read:all`/`audit:read:own`/`stats:read` but not `query:submit`, per `app/services/authz.py:36-40`). Via chat: `_send(state, ...)` with `chat_state_mod.call_openrouter` mocked to `_fail_if_called`; assert `state.messages[-1].kind == "forbidden"`, `required_permission == PERMISSION_QUERY_SUBMIT`, and exactly one new audit row is written carrying `role="auditor"`, `denied_permission="query:submit"`. Via HTTP: `client.post("/query", ...)` with the same identity's token and `app.routers.query.call_openrouter` mocked to `_fail_if_called`; assert `403` with `{"detail": f"Permission denied: {PERMISSION_QUERY_SUBMIT}"}` and **zero** additional audit rows (before/after count unchanged). Assert `call_openrouter` is never invoked via either monkeypatched target in either call. Include a docstring/comment citing PRD Section 9 and `app/routers/query.py:18`'s `Depends(require_permission(...))` as the reason the audit-row counts legitimately differ between ingresses for this one permission, per this plan's Design Decision section — so a future reader sees this as a documented, deliberate assertion rather than an oversight.
- **Mirror**: `tests/test_query_router.py:83-95` (`test_identity_lacking_query_submit_returns_403_naming_permission` — the HTTP-side 403/zero-rows precedent this test's HTTP half reproduces for direct comparison in the same test body).
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_chat_state.py -q`

### Task 6: Full-suite regression and scope check (AC5)

- **File**: n/a (verification only)
- **Action**: n/a
- **Implement**: Run the complete suite and confirm every pre-existing test still passes unmodified, with only the two files in "Files to Change" touched.
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -m pytest tests/ -q
  git status --porcelain
  git diff --name-only
  ```
  Expected: full suite green (baseline count + this story's new tests, no failures, no skips introduced); `git diff --name-only` shows exactly `tests/test_rbac.py` (new, so it appears under `git status`, not `git diff`) and `tests/test_chat_state.py` (modified) — nothing under `app/`, `chat_ui/chat_ui/` (excluding test files), `scripts/`, or any other story's territory.

---

## End-to-End Tests

This is a backend/test-suite story with no new UI or HTTP surface of its own — "E2E" here means the suite itself runs clean end to end, not a browser-driven check.

- [ ] `pytest tests/test_rbac.py -q` — all new tests pass
- [ ] `pytest tests/test_chat_state.py -q` — all pre-existing tests pass unmodified, plus the two new parity tests
- [ ] `pytest tests/ -q` (full repo) — green, matching baseline count plus this story's additions, zero regressions
- [ ] `git diff --name-only` / `git status --porcelain` — only `tests/test_rbac.py` (new) and `tests/test_chat_state.py` (modified) changed
- [ ] Manual spot check: `python -c "from app.main import app"` still imports cleanly (no accidental production import touched)

---

## Validation

```bash
.venv/Scripts/python.exe -m pytest tests/test_rbac.py tests/test_chat_state.py -q
.venv/Scripts/python.exe -m pytest tests/ -q
python -c "from app.main import app"
```

---

## Acceptance Criteria

(Copied from story STORY-017)

- [ ] Given the role/permission matrix, when the suite runs, then every cell is asserted in both directions — granted and denied (Tasks 1, 2)
- [ ] Given each permission, when tested, then it is exercised through **both** `POST /query` and `ChatState.send()`, asserting identical denials — satisfied for `query:submit` (decision parity, documented audit-row asymmetry — see Design Decision) and the model allowlist (full symmetric parity); `audit:read:*`/`stats:read` have no chat-UI ingress to compare against and are asserted at the HTTP layer only (Tasks 1, 3, 4, 5)
- [ ] Given a denial through either ingress, when asserted, then the mocked OpenRouter client is never called and exactly one audit row carries the role and the missing permission — satisfied exactly for the model allowlist and `query:byok`; for `query:submit` the HTTP ingress legitimately writes zero rows by the router's own pre-existing design, asserted and documented rather than papered over (Tasks 4, 5)
- [ ] Given a pre-RBAC fixture database, when `init_db()` runs, then migration preserves every existing row and adds both new columns — already proven by `tests/test_db.py::test_init_db_migrates_pre_rbac_database`; this story adds the full bootstrap-to-successful-query lifecycle on top of it (Task 2)
- [ ] Given the PRD-001/002/003 suites, when the full suite runs, then they pass, modified only where `run_query()` now requires an identity — verified, not re-implemented; no production or pre-existing test file is touched by this story (Task 6)
- [ ] All tasks completed
- [ ] `tests/test_rbac.py` and `tests/test_chat_state.py` pass in full, including every pre-existing test unmodified in behavior
- [ ] Full pytest suite green, no regressions
- [ ] Follows existing per-file fixture conventions (no new `conftest.py` introduced)
