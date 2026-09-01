---
story: STORY-003
prd: PRD-005
slug: identity-resolution
title: Identity resolution — token hashing, Identity value object, ADMIN_TOKEN break-glass
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-005-rbac        # all stories commit here, no per-story branch
created: 2026-08-28
---

# Plan: Identity resolution — token hashing, Identity value object, ADMIN_TOKEN break-glass

## Summary

This story gives the system its first notion of a *verified* caller. It adds a single new module, `app/services/identity.py`, containing exactly three functions and one frozen dataclass: `hash_token()` (SHA-256 of a credential), `issue_token()` (`secrets.token_urlsafe(32)`), `resolve(token)` (credential → `Identity` or `None`), and `Identity` itself — an immutable `(user_id, role)` pair that is the single currency every downstream authorization decision will consume. `resolve()` has two paths: a constant-time comparison against `settings.ADMIN_TOKEN` that returns a synthetic `admin` identity without touching the database (the break-glass path PRD-001 already relies on), and a hash-then-lookup path through STORY-002's `find_user_by_token_hash()` for everyone else. The module is deliberately inert — it stores nothing, has no HTTP awareness, and nothing calls it yet. It is pure plumbing that STORY-004 (CLI), STORY-006 (authz), and STORY-012 (FastAPI dependencies) all sit on top of. Nothing existing changes: this is a new file plus a new test file, and the full pre-existing suite (274 tests) is expected to pass completely unmodified.

## User Story

As a security admin
I want a credential resolved server-side into a verified `Identity`
So that every downstream decision rests on who the server confirmed rather than on what the caller claimed

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-003-identity-resolution.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md` — Sections 6 (Core Architecture), 8 (Technology Stack — "Why SHA-256 and not a KDF"), 9 (Security & Configuration)
- Upstream plan: `.agents/plans/PRD-005-rbac/completed/STORY-002-users-table-schema.plan.md` — its Handoff section scopes this story: "It calls `find_user_by_token_hash(sha256(token).hexdigest())` and gets an active `User` or `None`... It must build its `Identity` value object *from* the returned `User`; do not let `User` itself leak into the pipeline as the identity type."

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (new module + new tests; no existing behavior modified) |
| Complexity | MEDIUM |
| Systems Affected | `app/services/identity.py` (new), `tests/test_identity.py` (new) |
| Story | STORY-003 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

**Dependency status**: `depends_on: [STORY-002]` — **satisfied**. STORY-002 is `status: done`, commit `903dee8`, report at `.agents/reports/PRD-005-rbac/STORY-002-users-table-schema.report.md`. This story consumes STORY-002's `find_user_by_token_hash()`, `User` dataclass, and `init_db()` directly.

**Blocks**: STORY-004 (bootstrap CLI needs `issue_token`/`hash_token`), STORY-006 (authz needs `Identity`), STORY-012 (FastAPI dependencies need `resolve()`).

---

## Skills In Use

None.

`.agents/skills/` contains exactly one skill, `frontend-design`, scoped to *"distinctive, intentional visual design when building new UI or reshaping an existing one"*. This story touches `app/services/` and `tests/` only — no UI surface. The story's `skills:` frontmatter field is `[]`, consistent with that reading.

---

## Patterns to Follow

Every snippet below is copied from the current branch. `identity.py` must be indistinguishable in shape from these existing service modules.

### Service module shape — module-level constant, small pure functions, no classes beyond a dataclass/exception
```python
# SOURCE: app/services/duplicate_checker.py:1-23
import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.db.database import find_duplicate_timestamp

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class DuplicateCheckError(Exception):
    pass


@dataclass
class DuplicateCheckResult:
    is_duplicate: bool
    first_query_at: Optional[str] = None


def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
```
`hash_prompt()` is the direct sibling of this story's `hash_token()` — same `hashlib.sha256(...).hexdigest()` shape — but the story's Technical Notes are explicit that it must **not be reused or imported**: same algorithm, different purpose (Design Note 2 below).

### Constant-time comparison against a configured secret — already the house pattern for `ADMIN_TOKEN`
```python
# SOURCE: app/middleware/auth.py:1-18
import secrets
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

_bearer_scheme = HTTPBearer(auto_error=False)


def require_admin_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> None:
    if credentials is None or not secrets.compare_digest(
        credentials.credentials, settings.ADMIN_TOKEN
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")
```
`resolve()` performs the identical comparison (`secrets.compare_digest(token, settings.ADMIN_TOKEN)`), reading `settings.ADMIN_TOKEN` live off the singleton rather than caching it, exactly as this dependency does.

### The consumer this story's `resolve()` calls into
```python
# SOURCE: app/db/database.py:254-265
def find_user_by_token_hash(token_hash: str) -> Optional[User]:
    """Active users only. A revoked credential is indistinguishable from an
    unknown one by design -- PRD-005 Section 9 maps both to 401, and separating
    them would be a credential-enumeration oracle."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE token_hash = ? AND active = 1",
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_user(row)
```
`resolve()` never sees `active` directly — the filter already happened in SQL (STORY-002 Design Note 5), so `resolve()`'s only job on a hit is to translate `User` into `Identity`.

### Tests: env bootstrap before any `app.*` import
```python
# SOURCE: tests/test_db.py:1-4
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```
Must stay at the top of `tests/test_identity.py`, above every `app.*` import — `app.config.Settings` requires both env vars at import time.

### Tests: temp DB via the monkeypatched settings singleton
```python
# SOURCE: tests/test_db.py:31-36 (reused verbatim, do not redefine)
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```

### Tests: tracking a monkeypatched stdlib call to assert *how* something was checked, not just the result
```python
# SOURCE: tests/test_admin_auth.py:79-94
def test_token_compared_via_constant_time_check(monkeypatch):
    calls = []
    original_compare_digest = auth_module.secrets.compare_digest

    def _tracking_compare_digest(a, b):
        calls.append((a, b))
        return original_compare_digest(a, b)

    monkeypatch.setattr(auth_module.secrets, "compare_digest", _tracking_compare_digest)

    response = client.get(
        "/fake-audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    assert response.status_code == 200
    assert len(calls) == 1
```
Same technique proves `resolve()` uses `secrets.compare_digest` for the `ADMIN_TOKEN` path (AC3) rather than `==`.

### Tests: seeding via the real DB helpers, not mocks
```python
# SOURCE: tests/test_db.py (STORY-002 tests) — insert_user / deactivate_user / temp_db
insert_user(User(user_id="ana", role="user", token_hash=hash_token("plaintext-token")))
```
`tests/test_duplicate_checker.py` and `tests/test_db.py` both seed a real temp SQLite file rather than mocking `app.db.database` — `identity.py`'s tests follow the same convention: no mocks, a real `temp_db`, real `insert_user`/`deactivate_user` calls.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/identity.py` | CREATE | `Identity` frozen dataclass, `hash_token()`, `issue_token()`, `resolve()`. |
| `tests/test_identity.py` | CREATE | Full AC coverage: valid/unknown/malformed/empty/deactivated tokens, `ADMIN_TOKEN` break-glass + its constant-time comparison, token issuance, hashing, immutability. |

**Explicitly NOT touched**:
- `app/db/models.py`, `app/db/database.py` — this story consumes STORY-002's helpers as-is; it does not add a `create_user`-with-plaintext convenience wrapper (that would duplicate hashing logic in the wrong layer, the exact anti-pattern STORY-002 Design Note 2 warned against).
- `app/services/duplicate_checker.py` — `hash_prompt()` is not imported, reused, or refactored into a shared "hash a string" helper. Same algorithm, deliberately different purpose (Design Note 2).
- `app/middleware/auth.py`, `app/routers/*`, `chat_ui/*` — nothing wires `resolve()` into an HTTP path or the chat UI yet. That is STORY-012 (dependencies) and STORY-010/014 (pipeline/chat UI). This story has **zero runtime-visible effect** on any existing request path.
- `app/config.py` — `ADMIN_TOKEN` already exists as a required `Settings` field; no new env var is introduced by this story.
- `requirements.txt` — `hashlib` and `secrets` are stdlib, per PRD Section 8.

---

## Design Notes (decisions worth stating up front)

1. **`Identity` is a frozen dataclass, and it is the first one in this codebase.** `grep -rn "frozen=True"` across the repo currently returns nothing — every existing dataclass (`AuditLog`, `User`, `DuplicateCheckResult`) is mutable. `Identity` is different on purpose: PRD Section 6 calls it "an immutable dataclass produced only by `identity.resolve(...)`", and PRD Risk 5 depends on nothing downstream being able to mutate a role after it was resolved. `@dataclass(frozen=True)` makes an errant `identity.role = "admin"` raise `dataclasses.FrozenInstanceError` instead of silently succeeding. Task 4 tests this directly.

2. **`hash_token()` is a new, separate function — `hash_prompt()` is never imported.** Both end up as `hashlib.sha256(x.encode("utf-8")).hexdigest()`, and it would be trivial to import one from the other. The PRD and story Technical Notes both call this out explicitly: "`hash_prompt()` from `duplicate_checker.py` is deliberately **not** reused: same algorithm, different purpose." The purposes diverge the moment either concern changes — `hash_prompt` hashes prompt *content* for deduplication (no security property required, collisions are a UX nit) while `hash_token` hashes a *credential* (a collision or a change to the algorithm is a security incident). Coupling them by import would mean a duplicate-detection change could silently alter credential hashing. Task 6 greps for this.

3. **SHA-256, not a KDF (argon2/bcrypt) — and this is a documented, conditional decision, not an oversight.** PRD Section 8 states plainly why: the input is `secrets.token_urlsafe(32)`, a 256-bit value with full entropy, not a human-chosen password subject to dictionary or brute-force attack — so a fast hash is the *correct* choice, not a shortcut. This holds only as long as tokens stay machine-generated (PRD Section 13 flags human-chosen passwords as a future item that would flip this decision). No password-hashing library is added to `requirements.txt`.

4. **The `ADMIN_TOKEN` break-glass path is checked *before* the database is touched, and is unconditional on database health.** `resolve()`'s first branch is `secrets.compare_digest(token, settings.ADMIN_TOKEN)`; only on a miss does it call `hash_token()` + `find_user_by_token_hash()`. This ordering is a resilience property PRD Section 9 implies but does not spell out line-by-line: "break-glass" means the credential must work even if the `users` table is empty, missing, or the identity-store code has a bug — which is exactly the scenario break-glass access exists for. Task 4 proves this with a database that has never had `init_db()` called on it (no `users` table at all): `resolve(ADMIN_TOKEN)` still succeeds, because the admin branch returns before any SQL runs.

5. **The synthetic admin identity's `user_id` is a private module constant, not the literal `"admin"` scattered at the call site.** `_ADMIN_BREAK_GLASS_USER_ID = "admin"` and `_ADMIN_ROLE = "admin"` are declared once, near the top of the module, mirroring how `_TIMESTAMP_FORMAT` is declared as a private module constant in `duplicate_checker.py` and `audit_logger.py`. This keeps the one place that decides "what does the break-glass caller get called in the audit log" singular and greppable. No story asks for this value to be configurable, so it is not read from `Settings`.

6. **`resolve()` accepts `Optional[str]` and treats falsy input as an immediate `None`, before any hashing or comparison.** AC2 requires empty and malformed tokens to resolve to `None`; `secrets.compare_digest` and `hash_token`'s `.encode("utf-8")` both work on empty strings without raising, but guarding early (`if not token: return None`) avoids a wasted `compare_digest` call and a wasted database round-trip for the single most common bad input (no `Authorization` header at all, which upstream code will represent as `None` or `""`). This mirrors `pii_redactor.py:50` (`if not settings.PII_REDACTION_ENABLED or not text: return text, []`) — guard on falsy input at the top, before doing any work.

7. **`resolve()` does not distinguish "unknown token" from "deactivated user" from "malformed token" — all three return bare `None`.** This is not a shortcut; it is the literal AC2 requirement and the same non-negotiable already established for `find_user_by_token_hash` (STORY-002 Design Note 5, PRD Section 9): separating these cases in the response would let a caller enumerate which tokens once existed. `resolve()` has exactly one failure value.

8. **`issue_token()` takes no arguments and does not persist anything.** PRD Section 6 places `app/services/identity.py` and `scripts/manage_users.py` in different files for a reason — this module owns the *primitive* (generate 256 bits, return the string), while STORY-004's CLI owns the *orchestration* (generate → hash → `insert_user`/`set_user_token_hash` → print once → discard). Giving `issue_token()` a side effect here would mean two modules could independently decide how a credential reaches storage. `_TOKEN_NBYTES = 32` is a private module constant (not a magic number inline) so a future audit only has one place to check that it matches PRD Section 4's `secrets.token_urlsafe(32)`.

9. **No new exception type.** `duplicate_checker.py` and `pii_redactor.py` each define a domain exception because they wrap operations that can fail unexpectedly (a broken DB connection, a failed model load) and the caller needs to distinguish "no result" from "something broke". `resolve()` has no such failure mode — a bad token is an expected, common input with a well-defined answer (`None`), not an error. Introducing `IdentityError` here would give `resolve()` two ways to signal "not authenticated" (`None` vs. raise), which is exactly the kind of ambiguity PRD Section 6's "one enforcement point" principle argues against down at the pipeline level. If `find_user_by_token_hash` ever raises `sqlite3.Error`, it propagates unmodified — `app/db/database.py` has no exception handling of its own (STORY-002 Design Note 8), and this module does not add any either.

10. **Nothing in this story reads or writes `harness_ai.db`'s repo-root file — every test runs against `tmp_path`.** Same discipline as `tests/test_db.py` and `tests/test_duplicate_checker.py`.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Verify the baseline before writing anything

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - `git branch --show-current` → `epic/PRD-005-rbac`.
  - `app/services/identity.py` does not exist yet; `tests/test_identity.py` does not exist yet.
  - `app/db/database.py` already exposes `find_user_by_token_hash`, `insert_user`, `deactivate_user`, and `app/db/models.py` already exposes `User` (all from STORY-002 — confirm import works).
  - Full suite is green at **274 passed**; `tests/test_db.py` at **50 passed**.
  - If any of the above differs, stop and re-plan.
- **Mirror**: STORY-001/STORY-002 plan Task 1 (same verification-gate shape)
- **Validate**:
  ```bash
  git branch --show-current
  .venv/Scripts/python.exe -m pytest -q                    # 274 passed
  .venv/Scripts/python.exe -m pytest tests/test_db.py -q   # 50 passed
  .venv/Scripts/python.exe -c "from app.db.database import find_user_by_token_hash, insert_user, deactivate_user; from app.db.models import User; print('deps ok')"
  ```

### Task 2: Create `app/services/identity.py`

- **File**: `app/services/identity.py`
- **Action**: CREATE
- **Implement**:
  ```python
  import hashlib
  import secrets
  from dataclasses import dataclass
  from typing import Optional

  from app.config import settings
  from app.db.database import find_user_by_token_hash

  # secrets.token_urlsafe(32) -> 256 bits of entropy, matching PRD Section 4.
  _TOKEN_NBYTES = 32

  # Synthetic identity for the ADMIN_TOKEN break-glass credential (PRD-001,
  # retained by PRD-005 Section 4). It resolves without a row in `users` and
  # without the database being reachable at all -- see Design Note 4.
  _ADMIN_BREAK_GLASS_USER_ID = "admin"
  _ADMIN_ROLE = "admin"


  @dataclass(frozen=True)
  class Identity:
      """The single currency of authorization in the system (PRD Section 4).

      Produced only by resolve() below -- nothing else in production code
      constructs one. Frozen so a role cannot be mutated after the point it
      was verified (PRD Risk 5).
      """

      user_id: str
      role: str


  def hash_token(token: str) -> str:
      """SHA-256 digest of a credential. Deliberately not shared with
      duplicate_checker.hash_prompt(): same algorithm, different purpose --
      see the story's Technical Notes."""
      return hashlib.sha256(token.encode("utf-8")).hexdigest()


  def issue_token() -> str:
      """Generates a new credential. Returns the plaintext -- the caller is
      responsible for hashing it before persisting and for showing it to the
      operator exactly once (scripts/manage_users.py, STORY-004)."""
      return secrets.token_urlsafe(_TOKEN_NBYTES)


  def resolve(token: Optional[str]) -> Optional[Identity]:
      """Verifies a credential and returns the Identity it belongs to, or
      None. None covers every failure case alike -- unknown, malformed,
      empty, or deactivated -- so the caller cannot distinguish them (PRD
      Section 9; STORY-002 Design Note 5 makes the same choice one layer
      down)."""
      if not token:
          return None

      if secrets.compare_digest(token, settings.ADMIN_TOKEN):
          return Identity(user_id=_ADMIN_BREAK_GLASS_USER_ID, role=_ADMIN_ROLE)

      user = find_user_by_token_hash(hash_token(token))
      if user is None:
          return None

      return Identity(user_id=user.user_id, role=user.role)
  ```
- **Mirror**: `app/services/duplicate_checker.py:1-23` (module shape, private constants, small pure functions), `app/middleware/auth.py:12-18` (`secrets.compare_digest` against `settings.ADMIN_TOKEN`)
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -c "
  from app.services.identity import Identity, hash_token, issue_token, resolve
  print(Identity('ana', 'user'))
  print(hash_token('abc') == hash_token('abc'))
  t = issue_token(); print(len(t) > 30, t != issue_token())
  "
  ```
  expect `Identity(user_id='ana', role='user')`, then `True`, then `True True`

### Task 3: Tests — valid, unknown, malformed, empty, and deactivated tokens (AC1, AC2)

- **File**: `tests/test_identity.py`
- **Action**: CREATE
- **Implement**: Start the file with the mandatory env bootstrap, then:
  ```python
  import os

  os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
  os.environ.setdefault("ADMIN_TOKEN", "test-token")

  import dataclasses

  import pytest

  from app.config import settings
  from app.db.database import deactivate_user, init_db, insert_user
  from app.db.models import User
  from app.services import identity as identity_module
  from app.services.identity import Identity, hash_token, issue_token, resolve


  @pytest.fixture
  def temp_db(tmp_path, monkeypatch):
      db_path = tmp_path / "test.db"
      monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
      init_db()
      return db_path
  ```
  Then add:
  - `test_resolve_returns_identity_for_valid_active_user` — `insert_user(User(user_id="ana", role="user", token_hash=hash_token("plaintext-token")))`; `resolve("plaintext-token") == Identity(user_id="ana", role="user")`.
  - `test_resolve_hashes_the_credential_not_the_stored_digest` — same seed as above, but assert `resolve(hash_token("plaintext-token")) is None`. Proves `resolve()` hashes its input rather than treating it as an already-hashed value — the security property that stops a leaked database row (which only ever holds the digest) from being usable as a credential on its own.
  - `test_resolve_unknown_token_returns_none` — empty `temp_db`, `resolve("never-issued") is None`.
  - `test_resolve_empty_token_returns_none` — `resolve("") is None`.
  - `test_resolve_none_token_returns_none` — `resolve(None) is None`. (Defensive: no caller is expected to pass `None` yet, but Design Note 6 makes it an explicit contract, not an accident of `hashlib` raising.)
  - `test_resolve_malformed_token_returns_none` — `resolve("not-a-real-token-!@#$") is None` against a `temp_db` seeded with one unrelated user.
  - `test_resolve_deactivated_user_returns_none` — insert, `deactivate_user("ana")`, then `resolve("plaintext-token") is None`.
- **Mirror**: `tests/test_db.py:31-36` (`temp_db` fixture), `tests/test_duplicate_checker.py` (seeding real rows, no mocks)
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_identity.py -q -k "resolve and not admin"`

### Task 4: Tests — `ADMIN_TOKEN` break-glass, its constant-time comparison, and DB-independence (AC3)

- **File**: `tests/test_identity.py`
- **Action**: UPDATE
- **Implement**:
  - `test_resolve_admin_token_returns_synthetic_admin_identity` — `resolve(settings.ADMIN_TOKEN) == Identity(user_id="admin", role="admin")`, against a `temp_db` with zero users.
  - `test_resolve_admin_token_uses_compare_digest` — tracking-wrapper pattern from `tests/test_admin_auth.py:79-94`, monkeypatching `identity_module.secrets.compare_digest`, asserting it is called at least once and the real comparison is delegated to it:
    ```python
    def test_resolve_admin_token_uses_compare_digest(monkeypatch, temp_db):
        calls = []
        original = identity_module.secrets.compare_digest

        def _tracking(a, b):
            calls.append((a, b))
            return original(a, b)

        monkeypatch.setattr(identity_module.secrets, "compare_digest", _tracking)

        result = resolve(settings.ADMIN_TOKEN)

        assert result == Identity(user_id="admin", role="admin")
        assert len(calls) == 1
        assert calls[0] == (settings.ADMIN_TOKEN, settings.ADMIN_TOKEN)
    ```
  - `test_resolve_wrong_token_is_not_treated_as_admin` — `resolve("close-but-wrong") is None` against an empty `temp_db`, guarding against a substring/prefix comparison bug.
  - `test_resolve_admin_token_works_without_users_table` — **does not** use the `temp_db` fixture. Points `settings.DATABASE_URL` at a `tmp_path` file that is never passed to `init_db()` (no `users` table, no `audit_logs` table, file may not even exist yet), then asserts `resolve(settings.ADMIN_TOKEN) == Identity(user_id="admin", role="admin")` still succeeds. This is Design Note 4's DB-independence guarantee, proved directly rather than assumed:
    ```python
    def test_resolve_admin_token_works_without_users_table(tmp_path, monkeypatch):
        db_path = tmp_path / "never-initialized.db"
        monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")

        result = resolve(settings.ADMIN_TOKEN)

        assert result == Identity(user_id="admin", role="admin")
    ```
- **Mirror**: `tests/test_admin_auth.py:79-94` (constant-time-check tracking wrapper), `tests/test_duplicate_checker.py:47-51` (`uninitialized_db`-style fixture that never calls `init_db()`)
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_identity.py -q -k admin`

### Task 5: Tests — token issuance (AC5) and hashing correctness

- **File**: `tests/test_identity.py`
- **Action**: UPDATE
- **Implement**:
  - `test_issue_token_uses_token_urlsafe_with_32_bytes` — monkeypatch `identity_module.secrets.token_urlsafe` to a tracking wrapper, call `issue_token()`, assert it was called once with `32`.
  - `test_issue_token_returns_distinct_high_entropy_values` — call `issue_token()` twice, assert the two values differ and each has length `> 32` (a 32-byte `token_urlsafe` value is 43 characters; assert generously to avoid coupling the test to the exact encoding length).
  - `test_issue_token_returns_a_string` — `isinstance(issue_token(), str)`.
  - `test_hash_token_matches_manual_sha256` — `hash_token("abc") == hashlib.sha256(b"abc").hexdigest()` (import `hashlib` in the test file for this one assertion).
  - `test_hash_token_is_deterministic` — `hash_token("same") == hash_token("same")`.
  - `test_hash_token_differs_for_different_input` — `hash_token("a") != hash_token("b")`.
  - `test_hash_token_is_case_sensitive` — `hash_token("Token") != hash_token("token")`.
- **Mirror**: `tests/test_admin_auth.py:79-94` (tracking-wrapper technique, reapplied to `token_urlsafe`)
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_identity.py -q -k "issue_token or hash_token"`

### Task 6: Tests — `Identity` immutability, equality, and the `hash_prompt` isolation guard (AC4 support + Design Notes 1, 2)

- **File**: `tests/test_identity.py`
- **Action**: UPDATE
- **Implement**:
  - `test_identity_is_frozen` —
    ```python
    def test_identity_is_frozen():
        ident = Identity(user_id="ana", role="user")
        with pytest.raises(dataclasses.FrozenInstanceError):
            ident.role = "admin"
    ```
  - `test_identity_equality_by_value` — `Identity("ana", "user") == Identity("ana", "user")` and `Identity("ana", "user") != Identity("ana", "admin")`.
  - `test_identity_is_hashable` — `{Identity("ana", "user")}` does not raise (a side effect of `frozen=True` the story doesn't require but shouldn't accidentally break — `eq=True` default plus `frozen=True` makes dataclasses hashable).
  - `test_identity_module_does_not_import_hash_prompt` — a static guard, not a runtime behavior test, so it is written as a source-inspection assertion rather than a mock:
    ```python
    def test_identity_module_does_not_import_hash_prompt():
        import inspect

        source = inspect.getsource(identity_module)
        assert "hash_prompt" not in source
        assert "duplicate_checker" not in source
    ```
    This is Design Note 2, enforced so a future edit that "simplifies" the two hashing functions into one shared import fails the suite immediately rather than silently coupling credential hashing to prompt deduplication.
- **Mirror**: none directly — this is the first frozen dataclass and the first source-inspection test in the repo; both are new patterns introduced by this story and documented here so later stories don't need to rediscover the reasoning.
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_identity.py -q -k "identity_is or identity_equality or does_not_import"`

### Task 7: Full-suite regression and diff gate

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - `.venv/Scripts/python.exe -m pytest tests/test_identity.py -v` — count the collected tests (expect **21**: 7 from Task 3, 4 from Task 4, 7 from Task 5, 4 from Task 6) and confirm all pass.
  - `.venv/Scripts/python.exe -m pytest -q` → **295 passed** (274 + 21). Any pre-existing test that now fails is a real regression — this story adds a file, it does not modify one.
  - `git diff --name-only` / `git status --short` show exactly two new files: `app/services/identity.py`, `tests/test_identity.py`. (`README.md` remains separately, pre-existing-modified and unstaged — not this story's concern, STORY-018's territory.)
  - `grep -rn "hash_prompt\|duplicate_checker" app/services/identity.py` returns nothing (Design Note 2, redundant with Task 6's runtime test but cheap to also check statically).
  - `grep -n "frozen=True" app/services/identity.py` finds the `Identity` declaration (Design Note 1).
- **Mirror**: STORY-001/STORY-002 plan's final task (same regression + diff gate shape)
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -m pytest tests/test_identity.py -v
  .venv/Scripts/python.exe -m pytest -q
  git status --short
  git diff --name-only
  grep -rn "hash_prompt\|duplicate_checker" app/services/identity.py || echo "clean: identity.py does not couple to duplicate_checker"
  grep -n "frozen=True" app/services/identity.py
  ```

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `.venv/Scripts/python.exe -m pytest tests/test_identity.py -v` — 21 pass
- [ ] `.venv/Scripts/python.exe -m pytest -q` — 295 pass, zero pre-existing failures
- [ ] `git status --short` — only `app/services/identity.py` and `tests/test_identity.py` are new/untracked (plus the pre-existing unstaged `README.md`)
- [ ] **Real on-disk round trip** — issue a token, hash it, persist it, resolve it back, revoke it, confirm it stops resolving:
  ```bash
  DATABASE_URL=sqlite:///probe3.db .venv/Scripts/python.exe -c "
  from app.db.database import init_db, insert_user, deactivate_user
  from app.db.models import User
  from app.services.identity import hash_token, issue_token, resolve

  init_db()
  token = issue_token()
  insert_user(User(user_id='ana', role='user', token_hash=hash_token(token)))

  ident = resolve(token)
  print('resolved', ident.user_id, ident.role)

  deactivate_user('ana')
  print('after revoke', resolve(token))
  "
  ```
  expect `resolved ana user` then `after revoke None`; then delete `probe3.db`
- [ ] **Break-glass works against the real repo-root database without any bootstrap**:
  ```bash
  .venv/Scripts/python.exe -c "
  from app.config import settings
  from app.services.identity import resolve
  print(resolve(settings.ADMIN_TOKEN))
  "
  ```
  expect `Identity(user_id='admin', role='admin')`
- [ ] `.venv/Scripts/python.exe -c "from app.main import app"` — imports clean, no circular-import issues from the new module
- [ ] `.venv/Scripts/python.exe -m uvicorn app.main:app --port 8001 &` then `curl http://localhost:8001/health` — starts and responds `{"status":"ok"}`, proving `app/services/identity.py` has no import-time side effect that breaks app startup; then stop the process
- [ ] Existing behavior untouched: `.venv/Scripts/python.exe -m pytest tests/test_admin_auth.py tests/test_db.py tests/test_query_router.py tests/test_chat_state.py -q` — all green, unmodified

---

## Validation

```bash
cd /f/AI/harness-ai
.venv/Scripts/python.exe -m pytest tests/test_identity.py -v
.venv/Scripts/python.exe -m pytest -q
git status --short
git diff --name-only
grep -rn "hash_prompt\|duplicate_checker" app/services/identity.py || echo "clean"
grep -n "frozen=True" app/services/identity.py
curl http://localhost:8000/health
```

Frontend lint: **N/A** — this repository has no npm frontend; the UI is Reflex (Python) and this story does not touch it.

---

## Handoff to downstream stories

- **STORY-004** (`scripts/manage_users.py`) calls `issue_token()` to generate a credential and `hash_token()` before calling `insert_user`/`set_user_token_hash` — the CLI is the only place the plaintext is ever printed, and it prints it exactly once by discipline, not by any enforcement in this module (Design Note 8).
- **STORY-006** (`app/services/authz.py`) takes `Identity` as the argument to `authorize(identity, permission)`. It must not construct an `Identity` itself in production code — only `resolve()` does that (PRD Section 6, "Value object" pattern) — though its own tests are free to construct one directly for isolation, the same way `tests/test_identity.py` does here.
- **STORY-012** (`require_identity` FastAPI dependency) wraps `resolve(credentials.credentials)`: `None` → `401 "Invalid or missing credential"`, non-`None` → the `Identity` is returned as the dependency's value. This story deliberately does not raise `HTTPException` itself — `identity.py` has no FastAPI import and no awareness of HTTP status codes, keeping the transport concern entirely in the middleware layer (PRD's "Adapter/facade" pattern, Section 6).
- **STORY-010** (`run_query()`) receives an already-resolved `Identity` as a required parameter — it never calls `resolve()` itself; that happens once, upstream, in whichever ingress produced the credential (the router dependency for HTTP, `ChatState.login()`/`send()` for the chat UI).
- **Not delivered, by design**: no HTTP-facing code, no exception type (Design Note 9), no persistence of issued tokens (Design Note 8), no role validation against the fixed three-role set (that is STORY-006's `authorize()` job — `resolve()` returns whatever role string is stored, unvalidated).

---

## Acceptance Criteria

(Copied from story `STORY-003`)

- [ ] Given a valid active user token, when `resolve(token)` is called, then it returns `Identity(user_id, role)` — *Task 2, 3*
- [ ] Given an unknown, malformed, empty, or deactivated token, when `resolve(token)` is called, then it returns `None` — never a partial, default, or anonymous identity — *Task 2, 3*
- [ ] Given the configured `ADMIN_TOKEN`, when `resolve(token)` is called, then it returns a synthetic `Identity` with role `admin`, compared with `secrets.compare_digest` — *Task 2, 4*
- [ ] Given a token is issued, when it is persisted, then only its SHA-256 digest is stored and the plaintext appears nowhere in the database or logs — *Task 2 (`hash_token`/`issue_token` never touch storage), End-to-End round-trip check*
- [ ] Given `issue_token()`, when it generates a credential, then it uses `secrets.token_urlsafe(32)` and returns the plaintext exactly once — *Task 2, 5*
- [ ] All tasks completed
- [ ] Backend server starts without error
- [ ] Full pytest suite green (21 in `tests/test_identity.py`, 295 overall)
- [ ] `app/services/identity.py` does not import or reference `hash_prompt`/`duplicate_checker` (Design Note 2)
- [ ] `Identity` is declared `frozen=True` and cannot be mutated after construction
- [ ] Follows existing patterns
