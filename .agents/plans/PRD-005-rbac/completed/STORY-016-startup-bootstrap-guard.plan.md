---
story: STORY-016
prd: PRD-005
slug: startup-bootstrap-guard
title: Fail-fast startup guard when RBAC is enabled with no seeded users
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-005-rbac
created: 2026-08-29
---

# Plan: Fail-fast startup guard when RBAC is enabled with no seeded users

## Summary

`RBAC_ENABLED` defaults to `true` (STORY-005), which is only safe if a deployment that turns it on without seeding any user fails loudly instead of either silently allowing every request or opaquely `401`-ing all of them forever. This story adds `authz.check_bootstrap()`: a zero-arg guard that raises `RbacNotBootstrappedError` — naming the exact `scripts/manage_users.py create-user` command to fix it — when `RBAC_ENABLED=true` and `count_active_users() == 0`. It deliberately does not consult `ADMIN_TOKEN`: `identity.resolve()` synthesizes an `admin` identity from `ADMIN_TOKEN` without ever touching the `users` table (`app/services/identity.py:46-62`), so a deployment could otherwise "boot" with only a break-glass credential and zero real users — the PRD's Risk 2 explicitly rejects that as sufficient bootstrap. The guard follows the exact idiom `authz.load()` already established for `RBAC_ROLES_FILE` (STORY-007): a module-level `load()`-style function, a small custom exception raised synchronously and left uncaught, called from `app/main.py`'s `lifespan` and registered via `chat_ui/chat_ui/chat_ui.py`'s `app.register_lifespan_task(...)` — the same duplication `init_db()`, `pii_redactor.load()`, and `authz.load()` already require because Reflex's `api_transformer` mounts the FastAPI app under an outer Starlette app whose own lifespan runs instead of `app.main`'s.

## User Story

As an operator upgrading an existing deployment
I want startup to fail with an actionable message when RBAC is on but no users exist
So that enabling it never leaves the service silently open or opaquely broken

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-016-startup-bootstrap-guard.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `app/services/authz.py`, `app/main.py`, `chat_ui/chat_ui/chat_ui.py`, `tests/test_main.py`, `tests/test_chat_ui_startup_guard.py` (new) |
| Story | STORY-016 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

---

## Skills In Use

None. `skills: []` in story frontmatter; `.agents/skills/` contains only `frontend-design`, which does not apply to this backend-only story.

---

## Patterns to Follow

### `authz.load()` / `AuthzConfigError` — the exact idiom this guard mirrors: a zero-arg startup function, a small custom exception, raised synchronously and left uncaught
```
// SOURCE: app/services/authz.py:60-96
class AuthzConfigError(Exception):
    """Raised by load() when RBAC_ROLES_FILE is set but unreadable,
    malformed, or grants an unrecognized permission. Startup fails rather
    than silently falling back to the built-in matrix (STORY-007)."""


def load() -> None:
    """Loads the role matrix from RBAC_ROLES_FILE if set, replacing
    ROLE_PERMISSIONS wholesale -- no merge, so an omitted permission denies
    (STORY-007). Empty RBAC_ROLES_FILE is a no-op: the built-in matrix stands
    and no file is read. Called once at startup (app/main.py's lifespan,
    chat_ui.py's register_lifespan_task); never call this per request."""
    global ROLE_PERMISSIONS
    path_str = settings.RBAC_ROLES_FILE
    if not path_str:
        return
    try:
        raw = Path(path_str).read_text(encoding="utf-8")
    except OSError as exc:
        raise AuthzConfigError(f"Failed to read RBAC_ROLES_FILE '{path_str}': {exc}") from exc
    ...
```
`check_bootstrap()` is the same shape: no args, a guard condition, raise-and-return-nothing on success. No `try/except` anywhere in `app/main.py` — the established fail-fast convention (confirmed by `app/services/pii_redactor.py:13-26`'s `PiiRedactorError`, README.md:354-355: "Because the model is loaded at startup, this kills the boot rather than the first request") is to let the exception escape the `lifespan` context manager before `yield`; Starlette/Uvicorn (and Reflex's own lifespan runner) treats that as fatal and aborts the process. No code in `app/` calls `sys.exit` — that idiom is reserved for `scripts/manage_users.py`'s CLI entry point.

### `app/main.py` lifespan — current shape, one more call added
```
// SOURCE: app/main.py:11-16
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    pii_redactor.load()
    authz.load()
    yield
```

### `chat_ui/chat_ui/chat_ui.py` — the duplication this story extends, with its established "why" comment convention
```
// SOURCE: chat_ui/chat_ui/chat_ui.py:20-24, 60-66
init_db()
...
app.register_lifespan_task(pii_redactor.load)
# Same bypass, same reason (STORY-007): without this, the chat UI would
# enforce the built-in role matrix while the API enforces RBAC_ROLES_FILE's
# override -- two different permission matrices for the same deployment.
app.register_lifespan_task(authz.load)
```
`init_db()` runs eagerly at import (not deferred) specifically so the `users`/`audit_logs` tables exist before anything else touches the database, including during `reflex export --frontend-only`; `pii_redactor.load()`/`authz.load()` are deferred to `register_lifespan_task` specifically to avoid triggering the spaCy download during that same frontend-only export. `check_bootstrap()` does no heavy work and touches only the already-created `users` table, so it belongs with the deferred group (registered, not called at import) — it has nothing to do during a frontend-only export and Reflex never runs lifespan tasks in that mode.

### `count_active_users()` and `identity.resolve()`'s `ADMIN_TOKEN` break-glass — why the guard checks the table directly instead of "is ADMIN_TOKEN set"
```
// SOURCE: app/db/database.py:298-303
def count_active_users() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE active = 1"
        ).fetchone()
        return row["n"]
```
```
// SOURCE: app/services/identity.py:46-62
def resolve(token: Optional[str]) -> Optional[Identity]:
    if not token:
        return None
    if secrets.compare_digest(token, settings.ADMIN_TOKEN):
        return Identity(user_id=_ADMIN_BREAK_GLASS_USER_ID, role=_ADMIN_ROLE)
    user = find_user_by_token_hash(hash_token(token))
    if user is None:
        return None
    return Identity(user_id=user.user_id, role=user.role)
```
`ADMIN_TOKEN` resolves to a synthetic identity without ever reading the `users` table, so `count_active_users() == 0` is fully possible with `ADMIN_TOKEN` configured. The guard must check `count_active_users()`, never `bool(settings.ADMIN_TOKEN)` — that is exactly AC5.

### `scripts/manage_users.py` — the exact command the error message must name
```
// SOURCE: scripts/manage_users.py:74-79
create = subparsers.add_parser("create-user", help="Create a user and issue its first token")
create.add_argument("--user-id", required=True)
create.add_argument("--role", choices=_VALID_ROLES, default=None)
create.set_defaults(func=_create_user)
```
Invocation: `python scripts/manage_users.py create-user --user-id <id> --role <admin|auditor|user>`.

### Tests — `TestClient(app)` as a context manager triggers lifespan; bare instantiation does not
```
// SOURCE: tests/test_main.py:1-14, 63-75
import os
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app.main import app
import app.services.authz as authz
import app.services.pii_redactor as pii_redactor

client = TestClient(app)


def test_lifespan_loads_roles_file_before_serving_requests(tmp_path, monkeypatch):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text('{"user": ["query:submit"]}')
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))
    original = authz.ROLE_PERMISSIONS
    try:
        with TestClient(app) as test_client:
            assert authz.ROLE_PERMISSIONS == {"user": {"query:submit"}}
            response = test_client.get("/health")
            assert response.status_code == 200
    finally:
        authz.ROLE_PERMISSIONS = original
```
Only `with TestClient(app) as test_client:` runs the ASGI lifespan startup; the bare module-level `client = TestClient(app)` (used by `test_health_returns_ok`) does not. A test asserting the guard fires wraps `with TestClient(app):` in `pytest.raises(authz.RbacNotBootstrappedError)`.

### Subprocess probe with isolated `PYTHONPATH` — how the chat UI entry point is exercised without polluting this process's `sys.path`
```
// SOURCE: tests/test_chat_components_import.py:1-14, 24-25, 108-125
"""Smoke test for the Reflex component layer.
...
The checks run in a subprocess with PYTHONPATH set to `chat_ui/`, which is how
Reflex itself imports the app (`chat_ui.components...`, not
`chat_ui.chat_ui.components...`). Doing it in-process would put the inner
package on sys.path and break every other test module, which reaches the same
files by their repo-root path.
"""
REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]

@pytest.fixture(scope="module")
def probe():
    proc = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT, ...],
        cwd=str(REPO_ROOT / "chat_ui"),
        env={**os.environ, "PYTHONPATH": os.pathsep.join(_PYTHONPATH)},
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"component probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])
```
No existing test imports `chat_ui.chat_ui` (the module with `app = rx.App(...)` and the two `register_lifespan_task` calls) at all — this story adds the first coverage of that file's module-level wiring, following the identical subprocess-isolation pattern rather than importing it in-process. `rx.App` exposes `app.get_lifespan_tasks() -> tuple[Callable, ...]` (`reflex/app_mixins/lifespan.py:81-87`), which lets the probe assert `authz.check_bootstrap` is one of the registered callables, and — since it is a plain synchronous zero-arg function — call it directly against a real, empty database to prove it actually raises, without needing to drive Reflex's async lifespan machinery.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/authz.py` | UPDATE | Add `RbacNotBootstrappedError` and `check_bootstrap()` |
| `app/main.py` | UPDATE | Call `authz.check_bootstrap()` in `lifespan`, after `authz.load()` |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | Register `authz.check_bootstrap` as a lifespan task, after `authz.load` |
| `tests/test_main.py` | UPDATE | Guard fires/doesn't fire across RBAC_ENABLED, active-user count, and ADMIN_TOKEN-alone cases |
| `tests/test_chat_ui_startup_guard.py` | CREATE | Proves the guard is wired into the chat UI entry point and behaves identically there |

Not touched in this story:
- README.md / `.env.example` — STORY-018 ("README, .env.example, and roadmap updates for RBAC") owns documenting the guard, the bootstrap procedure, and `RBAC_ENABLED=false` as the migration escape hatch; this story only ships the mechanism its Technical Notes describe. README's env-var table and Troubleshooting section are already missing all of STORY-004/005/006/007's RBAC variables (pre-existing gap, not introduced here) — out of scope here.
- `scripts/manage_users.py` — read-only reference for the exact command name; no change needed.
- `app/services/identity.py` — `resolve()`'s `ADMIN_TOKEN` break-glass path is unchanged; this story only ensures it can never substitute for the guard.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `authz.check_bootstrap()` and `RbacNotBootstrappedError`

- **File**: `app/services/authz.py`
- **Action**: UPDATE
- **Implement**: Add the import and, immediately after `load()`, the new exception and function:
  ```python
  from app.db.database import count_active_users
  ```
  ```python
  class RbacNotBootstrappedError(Exception):
      """Raised by check_bootstrap() when RBAC_ENABLED=true and no active
      user exists. ADMIN_TOKEN alone does not satisfy this -- identity.resolve()
      synthesizes an admin identity from it without ever reading the users
      table, so break-glass is not a substitute for bootstrap (PRD-005 Risk 2,
      STORY-016)."""


  def check_bootstrap() -> None:
      """Fail-fast startup guard (STORY-016). If RBAC_ENABLED and no active
      user is seeded, every request would resolve to a 401 with no
      explanation -- or, if only ADMIN_TOKEN is configured, the service would
      appear to work for exactly one break-glass credential and nobody else.
      Called once at startup (app/main.py's lifespan, chat_ui.py's
      register_lifespan_task) after init_db() has run."""
      if not settings.RBAC_ENABLED:
          return
      if count_active_users() > 0:
          return
      raise RbacNotBootstrappedError(
          "RBAC_ENABLED=true but no active users exist. Bootstrap one with: "
          "python scripts/manage_users.py create-user --user-id <id> "
          "--role <admin|auditor|user>"
      )
  ```
  Place the new import alongside the existing `from app.config import settings` / `from app.services.identity import Identity` import block at the top of the file. Place `RbacNotBootstrappedError` and `check_bootstrap()` directly after `load()` (before `authorize()`), grouping the two startup-time functions together.
- **Mirror**: `app/services/authz.py:60-96` (`AuthzConfigError` / `load()`) for the exception-plus-guard-function shape and docstring style.
- **Validate**: `python -c "from app.services.authz import check_bootstrap, RbacNotBootstrappedError"` succeeds.

### Task 2: Wire the guard into `app/main.py`'s lifespan

- **File**: `app/main.py`
- **Action**: UPDATE
- **Implement**: Add one line after `authz.load()`:
  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI):
      init_db()
      pii_redactor.load()
      authz.load()
      authz.check_bootstrap()
      yield
  ```
  No new import needed — `authz` is already imported (`from app.services import authz, pii_redactor`).
- **Mirror**: `app/main.py:11-16` (existing `lifespan`).
- **Validate**: `python -c "import app.main"` succeeds (this only imports the function; it does not run `lifespan`, so it succeeds regardless of DB state).

### Task 3: Wire the guard into the chat UI entry point

- **File**: `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Implement**: Add one registration after the existing `authz.load` registration, with a comment following the file's established convention:
  ```python
  # Same bypass, same reason (STORY-007): without this, the chat UI would
  # enforce the built-in role matrix while the API enforces RBAC_ROLES_FILE's
  # override -- two different permission matrices for the same deployment.
  app.register_lifespan_task(authz.load)
  # Same bypass again (STORY-016): app.main's fail-fast bootstrap guard would
  # otherwise never run for this ingress, so RBAC_ENABLED=true with zero
  # seeded users would boot the chat UI straight into a silent 401 wall
  # instead of refusing to start.
  app.register_lifespan_task(authz.check_bootstrap)
  ```
  No new import needed — `authz` is already imported (`from app.services import authz, pii_redactor`).
- **Mirror**: `chat_ui/chat_ui/chat_ui.py:60-66` (existing `register_lifespan_task` calls and their comment convention).
- **Validate**: `python -c "import ast; ast.parse(open('chat_ui/chat_ui/chat_ui.py').read())"` succeeds (syntax only — the module can't be safely imported from the repo root process; Task 5's subprocess probe is the real import validation).

### Task 4: `tests/test_main.py` — guard behavior across RBAC_ENABLED, active-user count, and ADMIN_TOKEN-alone

- **File**: `tests/test_main.py`
- **Action**: UPDATE
- **Implement**: Extend the import block and add a fixture plus four tests, appended after `test_lifespan_loads_roles_file_before_serving_requests`:
  ```python
  from app.db.database import count_active_users, init_db, insert_user
  from app.db.models import User
  from app.services.identity import hash_token
  ```
  ```python
  @pytest.fixture
  def _empty_users_db(tmp_path, monkeypatch):
      db_path = tmp_path / "test_startup_guard.db"
      monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
      init_db()


  def test_lifespan_fails_fast_when_rbac_enabled_and_no_active_users(
      _empty_users_db, monkeypatch
  ):
      monkeypatch.setattr(settings, "RBAC_ENABLED", True)
      assert count_active_users() == 0

      with pytest.raises(authz.RbacNotBootstrappedError):
          with TestClient(app):
              pass


  def test_lifespan_boots_when_rbac_enabled_and_one_active_user(
      _empty_users_db, monkeypatch
  ):
      monkeypatch.setattr(settings, "RBAC_ENABLED", True)
      insert_user(User(user_id="ana", role="user", token_hash=hash_token("ana-token")))

      with TestClient(app) as test_client:
          response = test_client.get("/health")
          assert response.status_code == 200


  def test_lifespan_skips_guard_when_rbac_disabled(_empty_users_db, monkeypatch):
      monkeypatch.setattr(settings, "RBAC_ENABLED", False)
      assert count_active_users() == 0

      with TestClient(app) as test_client:
          response = test_client.get("/health")
          assert response.status_code == 200


  def test_lifespan_fails_fast_even_with_only_admin_token_configured(
      _empty_users_db, monkeypatch
  ):
      monkeypatch.setattr(settings, "RBAC_ENABLED", True)
      assert settings.ADMIN_TOKEN
      assert count_active_users() == 0

      with pytest.raises(authz.RbacNotBootstrappedError):
          with TestClient(app):
              pass
  ```
  - `test_lifespan_fails_fast_when_rbac_enabled_and_no_active_users` covers AC1.
  - `test_lifespan_boots_when_rbac_enabled_and_one_active_user` covers AC2.
  - `test_lifespan_skips_guard_when_rbac_disabled` covers AC3 — a fresh, empty `users` table plus `RBAC_ENABLED=False` still boots, proving the guard itself (not merely `count_active_users() > 0`) is what's bypassed.
  - `test_lifespan_fails_fast_even_with_only_admin_token_configured` covers AC5 — `settings.ADMIN_TOKEN` is already configured process-wide (`os.environ.setdefault("ADMIN_TOKEN", "test-token")` at the top of this file) and the guard still raises, proving `ADMIN_TOKEN` alone never satisfies it.
  - `_empty_users_db` isolates each test's database via `tmp_path` + `monkeypatch.setattr(settings, "DATABASE_URL", ...)`, so tests never share `count_active_users()` state with each other or with the module-level `client = TestClient(app)` used by `test_health_returns_ok`.
- **Mirror**: `tests/test_main.py:63-75` (`test_lifespan_loads_roles_file_before_serving_requests`) for the `with TestClient(app):`-triggers-lifespan pattern; `tests/test_audit_router.py`'s `temp_db` fixture (referenced in STORY-015's plan) for the `tmp_path` + `monkeypatch.setattr(settings, "DATABASE_URL", ...)` + `init_db()` isolation shape.
- **Validate**: `python -m pytest tests/test_main.py -q` — all tests (existing + new) pass.

### Task 5: `tests/test_chat_ui_startup_guard.py` — the guard is wired into the chat UI entry point

- **File**: `tests/test_chat_ui_startup_guard.py`
- **Action**: CREATE
- **Implement**:
  ```python
  """Startup-guard coverage for the chat UI entry point (STORY-016).

  app/main.py's lifespan never runs under Reflex's api_transformer mount (see
  chat_ui/chat_ui/chat_ui.py's comments) -- init_db(), pii_redactor.load(),
  authz.load(), and now authz.check_bootstrap() are all duplicated there. This
  runs in a subprocess with PYTHONPATH set to chat_ui/, exactly like
  tests/test_chat_components_import.py, so importing chat_ui.chat_ui here
  never puts the inner package on this process's sys.path.
  """

  import json
  import os
  import subprocess
  import sys
  from pathlib import Path

  import pytest

  os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
  os.environ.setdefault("ADMIN_TOKEN", "test-token")

  REPO_ROOT = Path(__file__).resolve().parents[1]
  _PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]

  _CHECK_SCRIPT = r"""
  import json, sys

  result = {"errors": []}
  try:
      import chat_ui.chat_ui as chat_ui_module
  except Exception as exc:
      print(json.dumps({"errors": ["import: {}: {}".format(type(exc).__name__, exc)]}))
      sys.exit(0)

  tasks = chat_ui_module.app.get_lifespan_tasks()
  result["guard_registered"] = chat_ui_module.authz.check_bootstrap in tasks

  try:
      chat_ui_module.authz.check_bootstrap()
      result["raised"] = False
  except chat_ui_module.authz.RbacNotBootstrappedError:
      result["raised"] = True

  print(json.dumps(result))
  """


  def _run_probe(env):
      proc = subprocess.run(
          [sys.executable, "-c", _CHECK_SCRIPT],
          cwd=str(REPO_ROOT / "chat_ui"),
          env=env,
          capture_output=True,
          text=True,
      )
      if proc.returncode != 0 or not proc.stdout.strip():
          pytest.fail(f"chat_ui startup-guard probe crashed:\n{proc.stdout}\n{proc.stderr}")
      return json.loads(proc.stdout.strip().splitlines()[-1])


  @pytest.fixture
  def _empty_rbac_env(tmp_path):
      db_path = tmp_path / "chat_ui_guard_test.db"
      env = {**os.environ, "PYTHONPATH": os.pathsep.join(_PYTHONPATH)}
      env["DATABASE_URL"] = f"sqlite:///{db_path}"
      env["RBAC_ENABLED"] = "true"
      return env


  def test_check_bootstrap_registered_as_chat_ui_lifespan_task(_empty_rbac_env):
      result = _run_probe(_empty_rbac_env)
      assert not result["errors"], result["errors"]
      assert result["guard_registered"] is True


  def test_check_bootstrap_raises_against_empty_users_table(_empty_rbac_env):
      result = _run_probe(_empty_rbac_env)
      assert not result["errors"], result["errors"]
      assert result["raised"] is True
  ```
  - `test_check_bootstrap_registered_as_chat_ui_lifespan_task` directly verifies the Technical Notes' requirement that the guard is "registered in `chat_ui/chat_ui/chat_ui.py`" — not merely present in `authz.py`.
  - `test_check_bootstrap_raises_against_empty_users_table` covers AC4 ("the same guard runs there too") by calling the exact registered callable directly against a real, freshly created, empty `users` table (created by `chat_ui.py`'s eager `init_db()` call at import time, before the probe script gets control) and confirming it raises identically to the `app/main.py` path.
  - Each test gets its own `tmp_path`-scoped `DATABASE_URL` via the subprocess `env`, so neither touches the fixture databases Task 4's tests use, and the two tests don't share database state with each other.
- **Mirror**: `tests/test_chat_components_import.py:1-14, 24-25, 55-125` (subprocess isolation pattern, docstring rationale, `env={**os.environ, ...}` shape); `reflex/app_mixins/lifespan.py:81-87` (`get_lifespan_tasks()` return shape).
- **Validate**: `python -m pytest tests/test_chat_ui_startup_guard.py -q` — both tests pass.

---

## End-to-End Tests

- [ ] `python -m pytest tests/test_main.py -q` — all tests pass, including the four new guard tests
- [ ] `python -m pytest tests/test_chat_ui_startup_guard.py -q` — both new tests pass
- [ ] `python -m pytest tests/ -q` — full suite green (`app/services/authz.py`'s import addition and `app/main.py`'s new lifespan call touch shared modules; confirms no regression in `tests/test_admin_auth.py`, `tests/test_db.py`, `tests/test_query_router.py`, etc.)
- [ ] Manual: with a fresh `harness_ai.db` deleted, `RBAC_ENABLED=true`, and `.env` otherwise valid, `uvicorn app.main:app` exits immediately with a message naming `scripts/manage_users.py create-user`
- [ ] Manual: run `python scripts/manage_users.py create-user --user-id ana --role admin`, then `uvicorn app.main:app` boots normally
- [ ] Manual: `RBAC_ENABLED=false` with the same empty database boots normally (escape hatch preserved)

---

## Validation

```bash
cd F:/AI/harness-ai
python -c "from app.services.authz import check_bootstrap, RbacNotBootstrappedError"
python -c "import app.main"
python -m pytest tests/ -q
```

---

## Acceptance Criteria

(Copied from story `STORY-016`)

- [ ] Given `RBAC_ENABLED=true` and zero active users, when the app starts, then it exits with a message naming `scripts/manage_users.py create-user`
- [ ] Given `RBAC_ENABLED=true` and at least one active user, when it starts, then it boots normally
- [ ] Given `RBAC_ENABLED=false`, when it starts, then the guard does not run and PRD-001 behavior is preserved exactly
- [ ] Given the chat UI entry point, when it starts, then the same guard runs there too
- [ ] Given only `ADMIN_TOKEN` is configured and no users are seeded, when it starts, then the guard still fails — break-glass is not a substitute for bootstrap
- [ ] All tasks completed
- [ ] `tests/test_main.py` and `tests/test_chat_ui_startup_guard.py` pass in full, including all pre-existing tests unmodified in behavior
- [ ] Follows the existing `authz.load()` / custom-exception / `register_lifespan_task` patterns
