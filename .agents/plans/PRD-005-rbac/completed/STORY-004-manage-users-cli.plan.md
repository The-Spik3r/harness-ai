---
story: STORY-004
prd: PRD-005
slug: manage-users-cli
title: Bootstrap CLI — scripts/manage_users.py
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-005-rbac        # all stories commit here, no per-story branch
created: 2026-08-28
---

# Plan: Bootstrap CLI — scripts/manage_users.py

## Summary

This story gives the MVP its only administration surface. `scripts/manage_users.py` is a stdlib-`argparse` CLI with four subcommands — `create-user`, `list-users`, `deactivate-user`, `issue-token` — built entirely on helpers STORY-002 and STORY-003 already shipped: `insert_user`, `list_users`, `deactivate_user`, `get_user`, `set_user_token_hash` (`app/db/database.py`) and `issue_token`/`hash_token` (`app/services/identity.py`). No new business logic is introduced; the CLI's only job is orchestration — generate a token, hash it, persist the hash, print the plaintext exactly once, and never print a hash or the plaintext of anything the operator didn't just request. Role validity (`admin`/`auditor`/`user`) is enforced with argparse's own `choices=`, so an invalid `--role` gets argparse's built-in non-zero exit and a message listing the valid roles for free, rather than hand-rolled validation. Because `RBAC_DEFAULT_ROLE` (the fallback when `--role` is omitted) doesn't exist in `Settings` yet — that's STORY-005's job, and STORY-004 depends only on STORY-003 — this plan adds that one field to `app/config.py` now, in a form STORY-005 can build on without conflict. The script also needs its own repo-root `sys.path` bootstrap (the same `Path(__file__).resolve().parents[N]` trick `chat_ui/chat_ui/chat_ui.py` already uses), because running it as `python scripts/manage_users.py` only puts `scripts/` on `sys.path`, not the repo root where `app/` lives.

## User Story

As an operator
I want a CLI to create users, issue tokens, list them, and deactivate them
So that a deployment can be bootstrapped without user-management HTTP endpoints

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-004-manage-users-cli.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md` — Sections 4 (MVP Scope — "Bootstrap CLI"), 7 (Tools/Features — CLI example)
- Upstream plan: `.agents/plans/PRD-005-rbac/completed/STORY-003-identity-resolution.plan.md` — its Handoff section: *"STORY-004 (`scripts/manage_users.py`) calls `issue_token()` to generate a credential and `hash_token()` before calling `insert_user`/`set_user_token_hash` — the CLI is the only place the plaintext is ever printed, and it prints it exactly once by discipline, not by any enforcement in this module."*
- Direct upstream callout: `app/db/database.py:320-323`, `set_user_token_hash()`'s docstring: *"Credential rotation (STORY-004 `issue-token`). The old hash stops resolving the moment this returns."* — this is the evidence that `issue-token` is an in-scope subcommand of this story, not an extension of it; see Design Note 4.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (new script + new tests; one additive field on `Settings`; no existing behavior modified) |
| Complexity | LOW |
| Systems Affected | `scripts/manage_users.py` (new), `scripts/__init__.py` (new), `app/config.py` (additive), `tests/test_manage_users_cli.py` (new) |
| Story | STORY-004 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

**Dependency status**: `depends_on: [STORY-003]` — **satisfied**. STORY-003 is `status: done`, commit `cadaebd`, report at `.agents/reports/PRD-005-rbac/STORY-003-identity-resolution.report.md`. This story consumes `issue_token()`/`hash_token()` from `app/services/identity.py` and `insert_user`/`list_users`/`deactivate_user`/`get_user`/`set_user_token_hash` from `app/db/database.py` (STORY-002) directly, as-is.

**Blocks**: STORY-016 (fail-fast startup guard names this CLI in its error message; `count_active_users() == 0` is the condition it checks against what this CLI seeds).

---

## Skills In Use

None. `.agents/skills/` contains exactly one skill, `frontend-design`, scoped to UI visual design. This story adds a stdlib CLI script and its tests — no UI surface. The story's `skills:` frontmatter field is `[]`.

---

## Patterns to Follow

### Repo-root `sys.path` bootstrap for a script that lives outside the `app` package
```python
# SOURCE: chat_ui/chat_ui/chat_ui.py:1-6
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
```
`scripts/manage_users.py` sits one directory shallower than `chat_ui/chat_ui/chat_ui.py` (`scripts/manage_users.py` vs `chat_ui/chat_ui/chat_ui.py`), so the parent index changes from `parents[2]` to `parents[1]` — everything else about the pattern is identical.

### Service-layer functions this CLI orchestrates, unmodified
```python
# SOURCE: app/services/identity.py:39-43
def issue_token() -> str:
    """Generates a new credential. Returns the plaintext -- the caller is
    responsible for hashing it before persisting and for showing it to the
    operator exactly once (scripts/manage_users.py, STORY-004)."""
    return secrets.token_urlsafe(_TOKEN_NBYTES)
```
```python
# SOURCE: app/db/database.py:285-306
def insert_user(entry: User) -> str:
    """Raises sqlite3.IntegrityError on a duplicate user_id or token_hash --
    deliberately not caught here; app/db/ has no error handling anywhere and the
    caller needs to tell those two cases apart."""
    ...
```
```python
# SOURCE: app/db/database.py:320-328
def set_user_token_hash(user_id: str, token_hash: str) -> bool:
    """Credential rotation (STORY-004 `issue-token`). The old hash stops
    resolving the moment this returns."""
    ...
```
The CLI's job is entirely: call these in the right order, catch what they explicitly leave for the caller, print what the operator needs, exactly once.

### Env bootstrap + `temp_db` fixture for tests that touch the database
```python
# SOURCE: tests/test_db.py:1-4, 40-45
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

...

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```
Reused verbatim — `tests/test_manage_users_cli.py` must not redefine its own database wiring.

### `Settings` field shape — plain typed attribute with a default, no property needed for a scalar
```python
# SOURCE: app/config.py:7-13
    OPENROUTER_API_KEY: str
    ADMIN_TOKEN: str

    DATABASE_URL: str = "sqlite:///harness_ai.db"
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    LOG_LEVEL: str = "INFO"
```
`RBAC_DEFAULT_ROLE: str = "user"` follows this exact shape — a plain default-valued field, not a CSV-parsed property like `PII_ENTITIES` (that pattern is for lists; `RBAC_DEFAULT_ROLE` is a single scalar, so it doesn't need one).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | UPDATE | Add `RBAC_DEFAULT_ROLE: str = "user"` — needed now because `create-user --role` omitted must resolve to it (AC2); STORY-005 adds `RBAC_ENABLED`, `RBAC_ROLES_FILE`, `MODEL_ALLOWLIST` on top of this without touching this field. |
| `scripts/__init__.py` | CREATE | Empty package marker — every other directory in this repo (`app/`, `app/db/`, `app/middleware/`, `app/models/`, `app/routers/`, `app/services/`, `tests/`) is a package with an `__init__.py`; this makes `scripts.manage_users` importable the same way in tests. |
| `scripts/manage_users.py` | CREATE | The CLI itself: `create-user`, `list-users`, `deactivate-user`, `issue-token`. |
| `tests/test_manage_users_cli.py` | CREATE | Full AC coverage plus the `issue-token` subcommand (Design Note 4). |

**Explicitly NOT touched**:
- `app/db/database.py`, `app/db/models.py`, `app/services/identity.py` — this story consumes STORY-002/STORY-003's helpers exactly as they are. No new database helper or identity primitive is added.
- `app/services/authz.py` — does not exist yet (STORY-006). Role validity here is a local, hardcoded `_VALID_ROLES` tuple in the CLI (Design Note 2), not an import from a module that doesn't exist.
- `app/middleware/auth.py`, `app/routers/*`, `chat_ui/*` — this CLI has no HTTP surface and no chat UI awareness. It is a pure offline administration tool, consistent with PRD Section 4's "User-management HTTP endpoints... Out of Scope."
- `requirements.txt` — `argparse` is stdlib; no new dependency, per PRD Section 8.

---

## Design Notes (decisions worth stating up front)

1. **`RBAC_DEFAULT_ROLE` is added to `Settings` by this story, not deferred to STORY-005.** STORY-004's own AC2 requires `--role` omitted to resolve to `RBAC_DEFAULT_ROLE`, and `depends_on: [STORY-003]` only — STORY-005 (which formally introduces the full `RBAC_*` env-var group) is not a dependency and may land before or after this story on the same epic branch. Adding just this one field now, in the exact shape (`str`, default `"user"`, no CSV property) STORY-005's own AC1 expects it to already have (*"`RBAC_ENABLED` ... `RBAC_DEFAULT_ROLE` ... `RBAC_ROLES_FILE` ... `MODEL_ALLOWLIST` are all available"*), means STORY-005 only needs to add the three remaining fields — no rename, no merge conflict, no rework.

2. **The three valid roles (`admin`, `auditor`, `user`) are a local tuple in `scripts/manage_users.py`, not imported from `app/services/authz.py`.** That module doesn't exist yet — it's STORY-006, which this story does not depend on. PRD Section 4 fixes the role set at exactly three for the entire MVP ("no custom roles beyond the three fixed ones"), so a small, explicitly-commented duplication here carries bounded risk: there is nothing to add or remove from this set within this PRD's scope. When STORY-006 ships, its matrix keys are the authoritative set; this constant does not need to change unless the fixed-role decision itself changes, which is out of scope.

3. **Role validation goes through argparse's `choices=`, not a hand-written `if role not in ...` branch.** AC3 requires "exits non-zero with a message listing the valid roles" — `argparse` already does exactly this when given `choices=_VALID_ROLES`: an invalid `--role` makes `parse_args()` print `invalid choice: 'x' (choose from 'admin', 'auditor', 'user')` to stderr and call `sys.exit(2)`. This satisfies the AC with zero custom code and is the idiomatic stdlib-argparse way to do it, matching the story's Technical Notes ("stdlib `argparse` only").

4. **`issue-token` is an in-scope fourth subcommand, not scope creep.** The story's AC list only spells out `create-user`, `list-users`, and `deactivate-user`, but its Description explicitly says "create users, **issue tokens**, list them, and deactivate them," and PRD Section 4 lists the CLI's job as "create, list, deactivate users **and issue tokens**." Most concretely, `set_user_token_hash()` in `app/db/database.py:320-323` was built by STORY-002 with a docstring naming this exact story and subcommand: *"Credential rotation (STORY-004 `issue-token`)."* Omitting it would leave that helper's stated purpose entirely unused by the one PRD-defined administration surface (user-management HTTP endpoints are explicitly out of scope), so there would be no way to rotate a compromised credential without deleting and recreating the user — which isn't supported either. This is followed, not invented: the plan implements exactly what the upstream story already committed to serving.

5. **`insert_user`'s `sqlite3.IntegrityError` is caught here, not left to propagate as a traceback.** `insert_user`'s own docstring says the exception is "deliberately not caught" at the database layer "and the caller needs to tell those two cases apart" (duplicate `user_id` vs. duplicate `token_hash`). A duplicate `user_id` is the realistic case for `create-user` (an operator re-running the command, or a typo) — `token_hash` collisions are astronomically unlikely from a fresh `issue_token()` call and are not user-facing here. The CLI catches `sqlite3.IntegrityError`, prints an actionable message naming the `user_id`, and exits `1` rather than showing a raw traceback to an operator running a bootstrap script.

6. **`main(argv=None) -> int` returns an exit code rather than calling `sys.exit()` internally**, except for argparse's own `choices=`/`required=` validation failures, which are `SystemExit` by argparse's design and are asserted with `pytest.raises(SystemExit)`. This makes every other path testable as a plain function call (`main(["create-user", "--user-id", "ana"])` returns `0` or `1`), with `capsys` capturing stdout/stderr — no subprocess, matching how the rest of this repo's test suite avoids process-spawning tests.

7. **`list-users` prints exactly `user_id`, `role`, `active`, `created_at` — the `User` dataclass's `token_hash` field is never referenced in the print path.** This is a straightforward field selection, not a redaction step: the CLI never reads `token_hash` off the `User` objects `list_users()` returns; it isn't filtered out, it's simply not touched. Task 8's test asserts no token or hash-shaped string appears in captured stdout.

8. **`init_db()` is called at the top of every subcommand handler, not once in `main()` before dispatch.** The story's Technical Notes say "Call `init_db()` first so the script works against a fresh checkout with no database file" — calling it inside each handler (rather than unconditionally in `main()` before argparse even validates the subcommand) means a bad invocation (missing `--user-id`, an argparse error) never touches the database at all, and each handler stays independently correct if handlers are ever invoked directly in future tests or code.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Verify the baseline before writing anything

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - `git branch --show-current` → `epic/PRD-005-rbac`.
  - `scripts/` does not exist yet; `tests/test_manage_users_cli.py` does not exist yet.
  - `app/config.py` does not yet define `RBAC_DEFAULT_ROLE`.
  - `app/db/database.py` already exposes `insert_user`, `list_users`, `deactivate_user`, `get_user`, `set_user_token_hash`; `app/services/identity.py` already exposes `issue_token`, `hash_token`, `resolve` (all from STORY-002/STORY-003).
  - Full suite is green at **296 passed**.
  - If any of the above differs, stop and re-plan.
- **Mirror**: STORY-003 plan Task 1 (same verification-gate shape)
- **Validate**:
  ```bash
  git branch --show-current
  .venv/Scripts/python.exe -m pytest -q   # 296 passed
  .venv/Scripts/python.exe -c "from app.db.database import insert_user, list_users, deactivate_user, get_user, set_user_token_hash; from app.services.identity import issue_token, hash_token, resolve; print('deps ok')"
  ```

### Task 2: Add `RBAC_DEFAULT_ROLE` to `app/config.py`

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**: Insert after the existing `LOG_LEVEL` field, before the `PII_*` block:
  ```python
      # RBAC (PRD-005). RBAC_DEFAULT_ROLE is needed here for scripts/manage_users.py
      # (STORY-004); RBAC_ENABLED, RBAC_ROLES_FILE, and MODEL_ALLOWLIST are added by
      # STORY-005 on top of this field.
      RBAC_DEFAULT_ROLE: str = "user"
  ```
- **Mirror**: `app/config.py:10-13` (plain typed field with a default, same style as `DATABASE_URL`/`PORT`/`HOST`/`LOG_LEVEL`)
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -c "from app.config import settings; print(settings.RBAC_DEFAULT_ROLE)"
  ```
  expect `user`

### Task 3: Create `scripts/__init__.py`

- **File**: `scripts/__init__.py`
- **Action**: CREATE
- **Implement**: Empty file (0 bytes), matching `app/__init__.py`, `app/db/__init__.py`, `tests/__init__.py`.
- **Mirror**: `app/services/__init__.py` (empty package marker)
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -c "import scripts; print('scripts is a package')"
  ```

### Task 4: Create `scripts/manage_users.py`

- **File**: `scripts/manage_users.py`
- **Action**: CREATE
- **Implement**:
  ```python
  import argparse
  import sqlite3
  import sys
  from pathlib import Path
  from typing import Optional, Sequence

  REPO_ROOT = Path(__file__).resolve().parents[1]
  if str(REPO_ROOT) not in sys.path:
      sys.path.insert(0, str(REPO_ROOT))

  from app.config import settings
  from app.db.database import (
      deactivate_user,
      get_user,
      init_db,
      insert_user,
      list_users,
      set_user_token_hash,
  )
  from app.db.models import User
  from app.services.identity import hash_token, issue_token

  # The three fixed roles PRD-005 Section 4 defines for the MVP. STORY-006's
  # app/services/authz.py will own the authoritative role->permission matrix;
  # until it exists, this is the only place a role name is validated, so it
  # mirrors the PRD rather than a module that isn't there yet (see plan Design
  # Note 2).
  _VALID_ROLES = ("admin", "auditor", "user")


  def _create_user(args: argparse.Namespace) -> int:
      init_db()
      role = args.role or settings.RBAC_DEFAULT_ROLE
      token = issue_token()
      try:
          insert_user(User(user_id=args.user_id, role=role, token_hash=hash_token(token)))
      except sqlite3.IntegrityError:
          print(f"Error: a user with user_id '{args.user_id}' already exists.", file=sys.stderr)
          return 1

      print(f"Created user '{args.user_id}' with role '{role}'.")
      print(f"Token (save this now -- it cannot be recovered): {token}")
      return 0


  def _list_users(args: argparse.Namespace) -> int:
      init_db()
      for user in list_users():
          print(f"{user.user_id}\t{user.role}\t{user.active}\t{user.created_at}")
      return 0


  def _deactivate_user(args: argparse.Namespace) -> int:
      init_db()
      if not deactivate_user(args.user_id):
          print(f"Error: no user with user_id '{args.user_id}'.", file=sys.stderr)
          return 1
      print(f"Deactivated user '{args.user_id}'.")
      return 0


  def _issue_token(args: argparse.Namespace) -> int:
      init_db()
      if get_user(args.user_id) is None:
          print(f"Error: no user with user_id '{args.user_id}'.", file=sys.stderr)
          return 1
      token = issue_token()
      set_user_token_hash(args.user_id, hash_token(token))
      print(f"Issued a new token for '{args.user_id}'.")
      print(f"Token (save this now -- it cannot be recovered): {token}")
      return 0


  def _build_parser() -> argparse.ArgumentParser:
      parser = argparse.ArgumentParser(prog="manage_users.py")
      subparsers = parser.add_subparsers(dest="command", required=True)

      create = subparsers.add_parser("create-user", help="Create a user and issue its first token")
      create.add_argument("--user-id", required=True)
      create.add_argument("--role", choices=_VALID_ROLES, default=None)
      create.set_defaults(func=_create_user)

      list_cmd = subparsers.add_parser("list-users", help="List all users")
      list_cmd.set_defaults(func=_list_users)

      deactivate = subparsers.add_parser("deactivate-user", help="Deactivate a user")
      deactivate.add_argument("--user-id", required=True)
      deactivate.set_defaults(func=_deactivate_user)

      issue = subparsers.add_parser("issue-token", help="Rotate a user's token")
      issue.add_argument("--user-id", required=True)
      issue.set_defaults(func=_issue_token)

      return parser


  def main(argv: Optional[Sequence[str]] = None) -> int:
      parser = _build_parser()
      args = parser.parse_args(argv)
      return args.func(args)


  if __name__ == "__main__":
      sys.exit(main())
  ```
- **Mirror**: `chat_ui/chat_ui/chat_ui.py:1-6` (repo-root `sys.path` bootstrap); `app/services/identity.py`/`app/db/database.py` (functions called as-is, no wrapping logic beyond orchestration)
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -c "from scripts.manage_users import main; print('imports ok')"
  .venv/Scripts/python.exe scripts/manage_users.py --help
  ```

### Task 5: Tests — `create-user` (AC1, AC2, AC3)

- **File**: `tests/test_manage_users_cli.py`
- **Action**: CREATE
- **Implement**: Start with the mandatory env bootstrap and shared fixture, then add the `create-user` tests:
  ```python
  import os

  os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
  os.environ.setdefault("ADMIN_TOKEN", "test-token")

  import pytest

  from app.config import settings
  from app.db.database import find_user_by_token_hash, get_user, init_db
  from scripts.manage_users import main


  @pytest.fixture
  def temp_db(tmp_path, monkeypatch):
      db_path = tmp_path / "test.db"
      monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
      init_db()
      return db_path


  # --- create-user (AC1, AC2, AC3) ---


  def test_create_user_prints_token_exactly_once_with_recovery_warning(temp_db, capsys):
      exit_code = main(["create-user", "--user-id", "ana", "--role", "user"])

      out = capsys.readouterr().out
      assert exit_code == 0
      user = get_user("ana")
      assert user is not None
      assert user.role == "user"
      # exactly one line carries the warning + token
      warning_lines = [line for line in out.splitlines() if "cannot be recovered" in line]
      assert len(warning_lines) == 1
      token = warning_lines[0].rsplit(": ", 1)[1]
      assert find_user_by_token_hash_matches(token)


  def find_user_by_token_hash_matches(token: str) -> bool:
      from app.services.identity import hash_token

      return find_user_by_token_hash(hash_token(token)) is not None


  def test_create_user_role_omitted_uses_rbac_default_role(temp_db, monkeypatch):
      monkeypatch.setattr(settings, "RBAC_DEFAULT_ROLE", "auditor")

      exit_code = main(["create-user", "--user-id", "bob"])

      assert exit_code == 0
      assert get_user("bob").role == "auditor"


  def test_create_user_invalid_role_exits_nonzero_and_lists_valid_roles(temp_db, capsys):
      with pytest.raises(SystemExit) as exc_info:
          main(["create-user", "--user-id", "eve", "--role", "superuser"])

      assert exc_info.value.code != 0
      err = capsys.readouterr().err
      assert "admin" in err and "auditor" in err and "user" in err
      assert get_user("eve") is None


  def test_create_user_duplicate_user_id_exits_nonzero(temp_db, capsys):
      main(["create-user", "--user-id", "ana", "--role", "user"])

      exit_code = main(["create-user", "--user-id", "ana", "--role", "admin"])

      assert exit_code == 1
      assert "already exists" in capsys.readouterr().err
      assert get_user("ana").role == "user"  # first row untouched
  ```
- **Mirror**: `tests/test_identity.py:19-24` (`temp_db` fixture), `tests/test_db.py:916-921` (`test_insert_user_rejects_duplicate_user_id` — same IntegrityError scenario, one layer up)
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_manage_users_cli.py -q -k create_user`

### Task 6: Tests — `list-users` (AC4)

- **File**: `tests/test_manage_users_cli.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  # --- list-users (AC4) ---


  def test_list_users_prints_expected_fields_never_token_or_hash(temp_db, capsys):
      main(["create-user", "--user-id", "ana", "--role", "user"])
      capsys.readouterr()  # discard create-user's own output, including its token

      exit_code = main(["list-users"])

      out = capsys.readouterr().out
      assert exit_code == 0
      assert "ana" in out
      assert "user" in out
      assert "True" in out  # active
      assert "cannot be recovered" not in out
      assert "Token" not in out


  def test_list_users_empty_table_prints_nothing(temp_db, capsys):
      exit_code = main(["list-users"])

      assert exit_code == 0
      assert capsys.readouterr().out == ""
  ```
- **Mirror**: `tests/test_db.py:936-943` (`test_list_users_includes_deactivated` — same `list_users()` call, one layer up)
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_manage_users_cli.py -q -k list_users`

### Task 7: Tests — `deactivate-user` (AC5)

- **File**: `tests/test_manage_users_cli.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  # --- deactivate-user (AC5) ---


  def test_deactivate_user_blocks_next_resolve(temp_db):
      from app.services.identity import resolve

      main(["create-user", "--user-id", "ana", "--role", "user"])
      user_before = get_user("ana")

      exit_code = main(["deactivate-user", "--user-id", "ana"])

      assert exit_code == 0
      assert get_user("ana").active is False
      # the credential this user was just issued no longer resolves --
      # exercised via find_user_by_token_hash, since the plaintext token
      # itself is only ever visible in create-user's captured stdout.
      assert find_user_by_token_hash(user_before.token_hash) is None


  def test_deactivate_user_unknown_user_exits_nonzero(temp_db, capsys):
      exit_code = main(["deactivate-user", "--user-id", "ghost"])

      assert exit_code == 1
      assert "no user" in capsys.readouterr().err
  ```
- **Mirror**: `tests/test_db.py:790-801` (`test_find_user_by_token_hash_ignores_deactivated_user`), `tests/test_identity.py:60-64` (`test_resolve_deactivated_user_returns_none`)
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_manage_users_cli.py -q -k deactivate_user`

### Task 8: Tests — `issue-token` (Design Note 4; not separately ACed but committed to by `set_user_token_hash`'s docstring)

- **File**: `tests/test_manage_users_cli.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  # --- issue-token (Design Note 4: PRD Section 4 "issue tokens";
  #     app/db/database.py:320-323 names this exact subcommand) ---


  def test_issue_token_rotates_credential(temp_db, capsys):
      main(["create-user", "--user-id", "ana", "--role", "user"])
      old_token_hash = get_user("ana").token_hash
      capsys.readouterr()

      exit_code = main(["issue-token", "--user-id", "ana"])

      out = capsys.readouterr().out
      assert exit_code == 0
      assert get_user("ana").token_hash != old_token_hash
      assert find_user_by_token_hash(old_token_hash) is None
      warning_lines = [line for line in out.splitlines() if "cannot be recovered" in line]
      assert len(warning_lines) == 1


  def test_issue_token_unknown_user_exits_nonzero(temp_db, capsys):
      exit_code = main(["issue-token", "--user-id", "ghost"])

      assert exit_code == 1
      assert "no user" in capsys.readouterr().err
  ```
- **Mirror**: `tests/test_db.py:945-957` (`test_set_user_token_hash_rotates_the_credential`, `test_set_user_token_hash_unknown_returns_false` — same rotation semantics, one layer up)
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_manage_users_cli.py -q -k issue_token`

### Task 9: Full-suite regression and diff gate

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - `.venv/Scripts/python.exe -m pytest tests/test_manage_users_cli.py -v` — count the collected tests (expect **10**: 4 from Task 5, 2 from Task 6, 2 from Task 7, 2 from Task 8) and confirm all pass.
  - `.venv/Scripts/python.exe -m pytest -q` → **306 passed** (296 + 10). Any pre-existing test that now fails is a real regression — this story only adds files and one additive `Settings` field.
  - `git status --short` shows exactly: `scripts/__init__.py`, `scripts/manage_users.py`, `tests/test_manage_users_cli.py` (new/untracked) and `app/config.py` (modified) — plus the pre-existing unstaged `README.md`, not this story's concern.
  - `grep -n "RBAC_DEFAULT_ROLE" app/config.py scripts/manage_users.py` — both files reference it.
- **Mirror**: STORY-003 plan's final task (same regression + diff gate shape)
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -m pytest tests/test_manage_users_cli.py -v
  .venv/Scripts/python.exe -m pytest -q
  git status --short
  git diff --name-only
  grep -n "RBAC_DEFAULT_ROLE" app/config.py scripts/manage_users.py
  ```

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `.venv/Scripts/python.exe -m pytest tests/test_manage_users_cli.py -v` — 10 pass
- [ ] `.venv/Scripts/python.exe -m pytest -q` — 306 pass, zero pre-existing failures
- [ ] `git status --short` — only the four files listed in Task 9 are new/modified (plus the pre-existing unstaged `README.md`)
- [ ] **Real on-disk round trip against a scratch database** — create, list, issue-token, deactivate, all via the actual CLI entry point:
  ```bash
  cd /f/AI/harness-ai
  DATABASE_URL=sqlite:///scratch_manage_users.db .venv/Scripts/python.exe scripts/manage_users.py create-user --user-id ana --role user
  DATABASE_URL=sqlite:///scratch_manage_users.db .venv/Scripts/python.exe scripts/manage_users.py list-users
  DATABASE_URL=sqlite:///scratch_manage_users.db .venv/Scripts/python.exe scripts/manage_users.py issue-token --user-id ana
  DATABASE_URL=sqlite:///scratch_manage_users.db .venv/Scripts/python.exe scripts/manage_users.py deactivate-user --user-id ana
  DATABASE_URL=sqlite:///scratch_manage_users.db .venv/Scripts/python.exe scripts/manage_users.py list-users
  rm scratch_manage_users.db
  ```
  expect: `create-user` prints one token line; `list-users` shows `ana  user  True  <timestamp>`; `issue-token` prints a second, different token line; `deactivate-user` confirms; final `list-users` shows `ana  user  False  <timestamp>` (row retained, not deleted)
- [ ] `--role` outside the fixed set fails fast: `.venv/Scripts/python.exe scripts/manage_users.py create-user --user-id x --role nope` exits non-zero and stderr lists `admin`, `auditor`, `user`
- [ ] `.venv/Scripts/python.exe -c "from app.main import app"` — imports clean, no circular-import issues introduced by the new `Settings` field
- [ ] Existing behavior untouched: `.venv/Scripts/python.exe -m pytest tests/test_identity.py tests/test_db.py -q` — all green, unmodified

---

## Validation

```bash
cd /f/AI/harness-ai
.venv/Scripts/python.exe -m pytest tests/test_manage_users_cli.py -v
.venv/Scripts/python.exe -m pytest -q
git status --short
git diff --name-only
grep -n "RBAC_DEFAULT_ROLE" app/config.py scripts/manage_users.py
curl http://localhost:8000/health
```

Frontend lint: **N/A** — this repository has no npm frontend; the UI is Reflex (Python) and this story does not touch it.

---

## Handoff to downstream stories

- **STORY-016** (fail-fast startup guard) names `python scripts/manage_users.py create-user` in its error message when `RBAC_ENABLED=true` and `count_active_users() == 0` — the exact command this story implements. No further CLI change is needed for STORY-016; it only needs this script to already exist and work.
- **STORY-005** (RBAC configuration settings) adds `RBAC_ENABLED`, `RBAC_ROLES_FILE`, `MODEL_ALLOWLIST` to `Settings` alongside the `RBAC_DEFAULT_ROLE` this story introduces — no rename or merge conflict expected (Design Note 1).
- **STORY-006** (authz service) becomes the authoritative source for the three fixed roles once it ships. This story's `_VALID_ROLES` tuple in `scripts/manage_users.py` is a bounded, documented duplication (Design Note 2) — not wired to import from `authz.py`, since STORY-004 does not depend on STORY-006 and must work standalone.
- **Not delivered, by design**: no user-management HTTP endpoints (PRD Section 4, explicitly out of scope), no role-matrix validation against `authz.py` (doesn't exist yet), no password/passphrase support (PRD Section 13, deferred), no bulk import/export.

---

## Acceptance Criteria

(Copied from story `STORY-004`)

- [ ] Given `python scripts/manage_users.py create-user --user-id ana --role user`, when it runs, then the row is created and the plaintext token is printed exactly once with a warning that it cannot be recovered — *Task 4, 5*
- [ ] Given `--role` is omitted, when a user is created, then the role is `RBAC_DEFAULT_ROLE` — *Task 2, 4, 5*
- [ ] Given a role outside the known set, when `create-user` runs, then it exits non-zero with a message listing the valid roles — *Task 4 (`choices=`), 5*
- [ ] Given `list-users`, when it runs, then it prints `user_id`, `role`, `active`, `created_at` — and never a token or a hash — *Task 4, 6*
- [ ] Given `deactivate-user --user-id ana`, when it runs, then that user's next `resolve()` returns `None` — *Task 4, 7*
- [ ] All tasks completed
- [ ] Backend server starts without error
- [ ] Full pytest suite green (10 in `tests/test_manage_users_cli.py`, 306 overall)
- [ ] `scripts/manage_users.py` uses stdlib `argparse` only — no new dependency in `requirements.txt`
- [ ] Follows existing patterns
