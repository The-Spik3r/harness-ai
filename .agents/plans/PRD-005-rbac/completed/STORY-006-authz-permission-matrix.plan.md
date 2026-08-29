---
story: STORY-006
prd: PRD-005
slug: authz-permission-matrix
title: "authz service — permission constants, default role matrix, deny-by-default authorize()"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-005-rbac
created: 2026-08-28
---

# Plan: authz service — permission constants, default role matrix, deny-by-default authorize()

## Summary

Create `app/services/authz.py`, a greenfield module holding the role→permission policy table for RBAC: five module-level permission-name constants, a plain-dict `ROLE_PERMISSIONS` matrix for the three fixed roles (`admin`, `auditor`, `user`), a `PermissionDenied` exception carrying the denied permission name, and a deny-by-default `authorize(identity, permission)` function. `authorize()` is a pure decision function with no side effects — it does not touch the pipeline, the database, or FastAPI; it only reads `settings.RBAC_ENABLED` for the documented bypass branch and looks up `identity.role` in the matrix. This story deliberately does not touch `app/services/query_pipeline.py` (wiring `authorize()` in as pipeline step 0 is STORY-010) or any FastAPI dependency (that's STORY-012) — its only consumer today is its own test suite.

## User Story

As a security admin
I want a data-driven role→permission matrix with a deny-by-default `authorize()`
So that access decisions live in one auditable table instead of conditionals scattered across the codebase

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-006-authz-permission-matrix.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | Backend authorization service (`app/services/`), backend test suite (`tests/`) |
| Story | STORY-006 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/frontend-design/SKILL.md` was checked and does not apply — this story is a backend-only, UI-less policy module.

---

## Patterns to Follow

### Naming — value-object shape `authorize()` receives

```python
// SOURCE: app/services/identity.py:19-29
@dataclass(frozen=True)
class Identity:
    """The single currency of authorization in the system (PRD Section 4).
    Produced only by resolve() below -- nothing else in production code
    constructs one. Frozen so a role cannot be mutated after the point it
    was verified (PRD Risk 5)."""
    user_id: str
    role: str
```
`authorize(identity, permission)` takes this exact `Identity` (imported from `app.services.identity`) and reads `identity.role`, a plain `str` — there is no `Role` enum anywhere in the codebase (confirmed by grep) and the `users` table (`app/db/models.py:48-56`) stores `role` as `TEXT` with no DB-level constraint. `authz.py` does **not** introduce a `Role` enum or type — it stays consistent with the plain-string-role convention already established by `Identity` and `User`. This is a deliberate scope decision, since the PRD's module-list comment (`PRD.md:136`) mentions `Role` in passing but the story's own Acceptance Criteria and Technical Notes never require one.

### Settings access

```python
// SOURCE: app/config.py:15-20
RBAC_ENABLED: bool = True
RBAC_DEFAULT_ROLE: str = "user"
RBAC_ROLES_FILE: str = ""
MODEL_ALLOWLIST: str = "gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet"
```
```python
// SOURCE: app/services/identity.py:55 (equivalent settings-read pattern)
if secrets.compare_digest(token, settings.ADMIN_TOKEN):
```
`authz.py` imports `from app.config import settings` and reads `settings.RBAC_ENABLED` directly off the singleton — same idiom `identity.py` uses for `settings.ADMIN_TOKEN`.

### Error Handling — deliberate divergence from sibling services

```python
// SOURCE: app/services/duplicate_checker.py:12-19
class DuplicateCheckError(Exception):
    pass

@dataclass
class DuplicateCheckResult:
    is_duplicate: bool
    first_query_at: Optional[str] = None
```
The sibling "policy check" services (`duplicate_checker.py`, `pattern_detector.py`) return a small `@dataclass` verdict object for a business-level negative outcome, reserving exceptions for infra failures only. `authz.py` intentionally breaks from that convention — per STORY-006 AC2/AC3, a denial is `raise PermissionDenied(permission)`, not a returned "denied" dataclass. This is spec'd by the story, not an oversight; the plan flags it so a future reader doesn't "fix" it back to a dataclass return.

```python
// SOURCE: precedent for an exception carrying one attribute + message (pattern reused, not copied verbatim — no existing "denied with reason" exception exists in the codebase yet; this is the first one)
class PermissionDenied(Exception):
    def __init__(self, permission: str) -> None:
        self.permission = permission
        super().__init__(f"Permission denied: {permission}")
```

### Tests — full-matrix parametrization precedent

```python
// SOURCE: tests/test_pattern_detector.py:14-19
@pytest.mark.parametrize("expected_pattern", SUSPICIOUS_PATTERNS)
def test_...(expected_pattern):
    ...
```
Direct precedent for STORY-006's AC "Tests assert every cell of the matrix in both directions, grant and deny" — `test_authz.py` parametrizes over `(role, permission, expected_allowed)` tuples covering every cell of `ROLE_PERMISSIONS` × all five permission constants.

```python
// SOURCE: tests/test_identity.py:1-4, tests/test_duplicate_checker.py:1-4 (env bootstrap header, identical in every existing test file)
import os
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```

```python
// SOURCE: tests/test_duplicate_checker.py:42, tests/test_config.py:29 (settings toggle pattern)
monkeypatch.setattr(settings, "RBAC_ENABLED", False)
```
Direct precedent for the AC5 bypass test ("a single explicit branch with its own test").

```python
// SOURCE: tests/test_duplicate_checker.py:116-117 (exception-raising assertion pattern)
with pytest.raises(DuplicateCheckError):
    ...
```
Direct precedent for asserting `PermissionDenied` is raised, and for asserting `exc.value.permission == <expected>`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/authz.py` | CREATE | Permission constants, `ROLE_PERMISSIONS` matrix, `PermissionDenied`, `authorize(identity, permission)` |
| `tests/test_authz.py` | CREATE | Full matrix coverage (grant + deny, every cell), unknown-role deny, missing-permission deny with correct `.permission` attribute, granted-permission returns `None`, `RBAC_ENABLED=false` bypass |

No existing file is modified. `app/services/query_pipeline.py` is explicitly out of scope (STORY-010 wires `authorize()` in as pipeline step 0).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `app/services/authz.py`

- **File**: `app/services/authz.py`
- **Action**: CREATE
- **Implement**:
  1. Imports: `from app.config import settings`, `from app.services.identity import Identity` (for type-hinting `authorize`'s `identity` parameter only — no other coupling to `identity.py`).
  2. Five module-level permission-name string constants, one per PRD Section 7 / STORY-006 AC1, so call sites never use string literals:
     ```python
     PERMISSION_QUERY_SUBMIT = "query:submit"
     PERMISSION_QUERY_BYOK = "query:byok"
     PERMISSION_AUDIT_READ_ALL = "audit:read:all"
     PERMISSION_AUDIT_READ_OWN = "audit:read:own"
     PERMISSION_STATS_READ = "stats:read"
     ```
  3. `ROLE_PERMISSIONS: dict[str, set[str]]` — a plain module-level dict (policy table, not conditionals), one entry per role, built exactly from PRD Section 7's matrix:
     - `"admin"`: all five constants
     - `"auditor"`: `PERMISSION_AUDIT_READ_ALL`, `PERMISSION_AUDIT_READ_OWN`, `PERMISSION_STATS_READ`
     - `"user"`: `PERMISSION_QUERY_SUBMIT`, `PERMISSION_AUDIT_READ_OWN`
     No wildcard/`"*"` entry and no `"query:byok"` for `auditor`/`user` — deny-by-default means every permission not listed for a role is absent from its set.
  4. `class PermissionDenied(Exception)` with `__init__(self, permission: str)` storing `self.permission = permission` and calling `super().__init__(f"Permission denied: {permission}")`, matching STORY-006's Technical Notes ("carries `permission` so callers can report and audit it without re-deriving it").
  5. `def authorize(identity: Identity, permission: str) -> None:`
     - First line: `if not settings.RBAC_ENABLED: return` — the single explicit bypass branch required by AC5.
     - `role_permissions = ROLE_PERMISSIONS.get(identity.role)`
     - `if role_permissions is None or permission not in role_permissions: raise PermissionDenied(permission)`
     - Falls through to implicit `return None` on grant.
  6. No docstring narrative is mandatory, but add one short module-level comment tying the matrix to PRD Section 7, consistent with `identity.py`'s PRD-citation habit — keep it to the module and the two public symbols (`PermissionDenied`, `authorize`), not per-constant.
- **Mirror**: `app/services/identity.py:19-62` for import style, PRD-citation comment habit, and settings-singleton access; `app/services/duplicate_checker.py:12-13` for the shape of a one-purpose exception class (adapted to carry `permission` instead of being bare).
- **Validate**: `python -c "from app.services.authz import authorize, PermissionDenied, ROLE_PERMISSIONS, PERMISSION_QUERY_SUBMIT, PERMISSION_QUERY_BYOK, PERMISSION_AUDIT_READ_ALL, PERMISSION_AUDIT_READ_OWN, PERMISSION_STATS_READ; print('ok')"` — imports cleanly with no error.

### Task 2: Create `tests/test_authz.py`

- **File**: `tests/test_authz.py`
- **Action**: CREATE
- **Implement**:
  1. Standard env bootstrap header (`os.environ.setdefault("OPENROUTER_API_KEY", "test-key")`, `os.environ.setdefault("ADMIN_TOKEN", "test-token")`) before any app import, matching every existing test file.
  2. Imports: `pytest`, `from app.config import settings`, `from app.services.identity import Identity`, `from app.services.authz import (authorize, PermissionDenied, ROLE_PERMISSIONS, PERMISSION_QUERY_SUBMIT, PERMISSION_QUERY_BYOK, PERMISSION_AUDIT_READ_ALL, PERMISSION_AUDIT_READ_OWN, PERMISSION_STATS_READ)`.
  3. **AC1 — full matrix coverage, both directions.** Build a parametrized case list covering every `(role, permission)` pair across the three roles × five permission constants (15 cells total), each tagged with the expected outcome derived directly from PRD Section 7's table. Use `@pytest.mark.parametrize("role, permission, expected_allowed", <cases>)`:
     - Granted cells (`expected_allowed=True`): assert `authorize(Identity(user_id="u", role=role), permission)` returns `None` and raises nothing.
     - Denied cells (`expected_allowed=False`): assert `pytest.raises(PermissionDenied)` and that `exc.value.permission == permission`.
     Group under a `# --- AC1: full matrix, grant + deny ---` banner comment, matching the codebase's per-AC comment-banner convention (`test_identity.py:27`, `test_config.py:14`).
  4. **AC2 — unknown role denies.** `authorize(Identity(user_id="u", role="superadmin"), PERMISSION_QUERY_SUBMIT)` raises `PermissionDenied`.
  5. **AC3 — permission absent from role's grants raises with the permission name.** E.g. `authorize(Identity(user_id="u", role="user"), PERMISSION_QUERY_BYOK)` raises `PermissionDenied` and `exc.value.permission == PERMISSION_QUERY_BYOK`.
  6. **AC4 — granted permission returns `None`, raises nothing.** E.g. `assert authorize(Identity(user_id="u", role="admin"), PERMISSION_STATS_READ) is None`.
  7. **AC5 — `RBAC_ENABLED=false` bypass, its own dedicated test.** `monkeypatch.setattr(settings, "RBAC_ENABLED", False)`, then assert `authorize(Identity(user_id="u", role="superadmin"), PERMISSION_QUERY_BYOK)` (an otherwise-guaranteed-deny case) returns `None` without raising — proves the bypass branch actually short-circuits the matrix lookup rather than coincidentally passing.
  8. Snake-case test names following `test_<subject>_<condition>_<expected_outcome>`, matching the repo-wide convention.
- **Mirror**: `tests/test_pattern_detector.py:14-19` for the parametrize-over-constants shape; `tests/test_duplicate_checker.py:42,116-117` and `tests/test_config.py:29` for the `monkeypatch.setattr(settings, ...)` and `pytest.raises(...)` patterns.
- **Validate**: `python -m pytest tests/test_authz.py -v` — all cases pass.

---

## End-to-End Tests

This story has no HTTP or UI surface — `authorize()` has no consumer yet (STORY-010 wires it into the pipeline). Validation is unit-level only:

- [ ] `python -m pytest tests/test_authz.py -v` — every one of the 15 matrix cells plus the four extra ACs (unknown role, missing permission, granted permission, bypass) passes
- [ ] `python -m pytest tests/ -v` — full existing suite (`test_identity.py`, `test_duplicate_checker.py`, `test_pattern_detector.py`, `test_admin_auth.py`, `test_config.py`, etc.) still passes unmodified, confirming `authz.py` introduces no import-time side effects or circular imports

---

## Validation

```bash
python -c "from app.services.authz import authorize, PermissionDenied, ROLE_PERMISSIONS; print('ok')"
python -m pytest tests/test_authz.py -v
python -m pytest tests/ -v
```

---

## Acceptance Criteria

(Copied from story `STORY-006`)

- [ ] Given the built-in matrix, when evaluated, then it matches PRD Section 7 exactly for `admin`, `auditor`, and `user` across `query:submit`, `query:byok`, `audit:read:all`, `audit:read:own`, and `stats:read`
- [ ] Given an identity whose role is not in the matrix, when `authorize()` runs, then it raises `PermissionDenied` — deny by default, never a fallback grant
- [ ] Given a permission absent from the role's grants, when `authorize()` runs, then it raises `PermissionDenied` carrying the permission name
- [ ] Given a granted permission, when `authorize()` runs, then it returns `None` and raises nothing
- [ ] Given `RBAC_ENABLED=false`, when `authorize()` runs, then it allows, and that bypass is a single explicit branch with its own test
- [ ] All tasks completed
- [ ] `python -m pytest tests/test_authz.py -v` passes
- [ ] `python -m pytest tests/ -v` passes unmodified
- [ ] Follows existing patterns (`identity.py` settings/PRD-citation style, `duplicate_checker.py`/`pattern_detector.py` module-constant style, repo-wide test conventions)
