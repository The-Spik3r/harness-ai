---
story: STORY-002
prd: PRD-007
slug: exception-characterization-tests
title: "Characterization tests pinning the three driver-exception behaviors against current SQLite"
type: REFACTOR
complexity: LOW
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-01
---

# Plan: Characterization tests pinning the three driver-exception behaviors

## Summary

Three sites outside `app/db/` catch stdlib `sqlite3` exception types and will silently stop matching when STORY-004 swaps the driver. This story writes tests that pin what those sites **observably do today** — return values, HTTP status codes, CLI stderr and exit codes — so STORY-004's swap is measured against a green baseline instead of memory. No production code changes; `tests/` only. Every assertion is written against observable behavior, never against an exception type, so none of these tests need rewriting when the driver changes. Exploration turned up **two ACs that describe behavior the code does not have** (AC2 and AC4) — both are documented below with the verified current behavior and are pinned as-is, per the story's own rule that a characterization test must never require a production change to go green.

## User Story

As a maintainer
I want the three `except sqlite3.*` behaviors pinned by observable-behavior tests before the driver changes
So that STORY-004's swap is measured against a green baseline rather than against my memory of what the code did

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-002-exception-characterization-tests.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md` — Section 6 Pattern 6, Section 11, Section 12 Phase 1

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (test-only) |
| Complexity | LOW |
| Systems Affected | `tests/` only |
| Story | STORY-002 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

---

## Skills In Use

`.agents/skills/` was listed in full. It contains exactly one skill:

| Skill | Applies? | Reason |
|-------|----------|--------|
| `frontend-design` | **No** | Its `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story touches `tests/` only and renders no UI. |

No skill constrains any task below. This matches the story's `skills: []` frontmatter and its own Technical Note.

---

## Verified Baseline (executed, not assumed)

Every behavior below was executed against the current tree before this plan was written. The four target test files pass today: **81 passed**.

| # | Behavior | Verified current result | Matches story AC? |
|---|---|---|---|
| 1a | `find_user_by_token_hash()` with no `users` table | returns `None` | yes — AC1 |
| 1b | Authenticated endpoint, no `users` table | **401** `{"detail":"Invalid or missing credential"}` | yes — AC1 |
| 2 | Storage failure during duplicate check, through `POST /query` | **500** `{"detail":"Duplicate lookup failed: no such table: audit_logs"}` | **no — AC2, see Discrepancy A** |
| 3 | CLI `create-user` with an existing `user_id` | exit `1`, stderr `Error: a user with user_id 'ana' already exists.` | yes — AC3 |
| 4 | CLI `create-user` with an existing `token_hash`, new `user_id` | exit `1`, stderr `Error: a user with user_id 'bob' already exists.` | **no — AC4, see Discrepancy B** |

### Discrepancy A — AC2 and PRD Pattern 6 both misstate the duplicate-check behavior

AC2 says the query "still completes rather than failing", and the PRD Section 6 Pattern 6 table says "Storage failure degrades the duplicate check without failing the query". **Neither is true of the current code.** The real chain is:

```
duplicate_checker.py:32   except sqlite3.Error -> raise DuplicateCheckError
query.py:35               except DuplicateCheckError -> HTTPException(500)
```

A storage failure during the duplicate check **fails the request with HTTP 500**. There is no degradation path. `tests/test_duplicate_checker.py:110` (`test_malformed_db_raises_duplicate_check_error`) already pins the raise at the service layer and passes today, confirming this is intended service-level behavior — only the router disposition was described wrongly.

**Resolution**: pin the true behavior (storage failure -> `DuplicateCheckError` -> 500). Do **not** change `query.py` to make AC2's wording true — that is a behavior change wearing a characterization test's clothes, and it is exactly what AC5 forbids. STORY-004 must preserve "500, with a message naming the failed lookup". Raise the wording fix against the story and PRD Pattern 6 at implementation time.

### Discrepancy B — AC4's "distinguishably" does not hold today

`scripts/manage_users.py:37` catches `sqlite3.IntegrityError` and prints one message for **both** constraint violations:

```python
except sqlite3.IntegrityError:
    print(f"Error: a user with user_id '{args.user_id}' already exists.", file=sys.stderr)
    return 1
```

A duplicate `token_hash` on a *new* `user_id` therefore prints `Error: a user with user_id 'bob' already exists.` — same template, same exit code, and **factually false**, since `bob` does not exist. The two cases are indistinguishable at the CLI surface.

This is a real gap against intent: `insert_user()`'s docstring (`app/db/database.py`) says the exception is deliberately not caught there because the caller "needs to tell those two cases apart" — and the caller then does not.

**Resolution**: pin what the CLI actually does, in a test whose name and docstring state plainly that the cases are *not* currently distinguished. That is the honest baseline and it is what STORY-004 must preserve. Fixing the CLI to distinguish them is a behavior change and belongs in its own story — flag it at implementation time; do not fold it in here.

---

## Patterns to Follow

### Initialized-DB fixture (the idiom across the suite; STORY-003 centralizes it — do not pre-empt)
```python
# SOURCE: tests/test_db.py:40-45
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```

### Uninitialized-DB fixture — the existing precedent for "the table does not exist"
```python
# SOURCE: tests/test_duplicate_checker.py:46-50
@pytest.fixture
def uninitialized_db(tmp_path, monkeypatch):
    db_path = tmp_path / "malformed.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    return db_path
```
`init_db()` is simply never called, so no table exists. This is the mechanism AC1 asks for.

### Endpoint-level auth assertion via the file's own fake app
```python
# SOURCE: tests/test_auth_dependencies.py:20-22, 38, 52-56
@_fake_app.get("/fake-identity")
def fake_identity(identity=Depends(require_identity)) -> dict:
    return {"user_id": identity.user_id, "role": identity.role}

client = TestClient(_fake_app)

def test_require_identity_rejects_missing_credential():
    response = client.get("/fake-identity")
    assert response.status_code == 401
```

### Router-level 500 assertion
```python
# SOURCE: tests/test_query_router.py:379-388
def test_redactor_failure_returns_500_and_never_calls_openrouter(temp_db, monkeypatch):
    ...
    assert response.status_code == 500
```
`tests/test_query_router.py:38-46`'s `temp_db` also seeds the authenticating user, and `client` at `:33` carries `_AUTH_HEADERS`, so an authenticated request is one line.

### CLI assertion via `main()` + `capsys`
```python
# SOURCE: tests/test_manage_users_cli.py:59-65
def test_create_user_duplicate_user_id_exits_nonzero(temp_db, capsys):
    main(["create-user", "--user-id", "ana", "--role", "user"])
    ...
    assert "already exists" in capsys.readouterr().err
```

### Anti-pattern to avoid (present in the suite, and STORY-004's problem, not ours)
```python
# SOURCE: tests/test_db.py:1029-1042
with pytest.raises(sqlite3.IntegrityError):
    insert_user(User(user_id="ana", role="admin", token_hash="h-2"))
```
Two such assertions exist at `tests/test_db.py:1032` and `:1041`. **Do not add any more, and do not fix these here** — they are driver-typed and are STORY-004's rewrite surface. Every test this story adds must survive the driver swap untouched.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_db.py` | UPDATE | Behavior 1a — `find_user_by_token_hash()` returns `None` when `users` does not exist |
| `tests/test_auth_dependencies.py` | UPDATE | Behavior 1b — the same condition resolves to 401, not 500 |
| `tests/test_query_router.py` | UPDATE | Behavior 2 — duplicate-check storage failure -> 500 through the real router |
| `tests/test_manage_users_cli.py` | UPDATE | Behaviors 3 and 4 — duplicate `user_id` and duplicate `token_hash` at the CLI |

No files created. `tests/test_duplicate_checker.py` is **not** modified: `test_malformed_db_raises_duplicate_check_error` at `:110` already pins the service-layer half of Behavior 2 against observable behavior, and duplicating it adds nothing.

---

## Environment Note (blocks running the suite locally; not a repo defect)

The working copy's untracked `.env` carries three extra keys — `tursoDBToken`, `databaseTursoDB`, `databaseURL` — added while scoping this epic. `app/config.py:5` builds `Settings` with pydantic's default `extra="forbid"`, so **importing `app.config` from the repo root currently raises `ValidationError` and no test can run**:

```
ValidationError: 3 validation errors for Settings
  tursodbtoken     Extra inputs are not permitted
  databasetursodb  Extra inputs are not permitted
  databaseurl      Extra inputs are not permitted
```

This is local-only (`.env` is not tracked) but it must be cleared before Task 6, or the "all green" gate cannot be evaluated. Two options, in order of preference:

1. **Remove the three keys from `.env`.** They are not read by `Settings` and duplicate `DATABASE_URL`. The credentials they hold belong in the settings fields STORY-005 adds (`TURSO_AUTH_TOKEN`), not in ad-hoc keys.
2. Run pytest from a directory that is not the repo root with `PYTHONPATH` set to it, so `env_file=".env"` resolves to nothing. Used for this plan's verification; a workaround, not a fix.

Do **not** "fix" this by loosening `Settings` to `extra="ignore"` — that is a production change, outside this story's scope, and it would mask real misconfiguration that PRD-007's startup guard is meant to catch.

---

## Tasks

Execute in order. Each task is atomic and verifiable. Every assertion is on a return value, an HTTP status code, or CLI output — **never on an exception type**.

### Task 0: Clear the local `.env` blocker

- **File**: `.env` (untracked, local only — not part of the diff)
- **Action**: UPDATE
- **Implement**: Remove the `tursoDBToken`, `databaseTursoDB`, and `databaseURL` lines. Preserve the Turso endpoint and token values somewhere outside the repo first — STORY-005 will need them. Leave the tracked `DATABASE_URL` line untouched.
- **Validate**: `python -c "from app.config import settings; print('ok')"` prints `ok` from the repo root.

### Task 1: Pin `find_user_by_token_hash()` returning `None` with no `users` table (AC1, first half)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: Add an `uninitialized_db` fixture beside the existing `temp_db` at `:40`, mirroring `tests/test_duplicate_checker.py:46-50` (set `DATABASE_URL` to a `tmp_path` file, do **not** call `init_db()`). Add `test_find_user_by_token_hash_returns_none_when_users_table_does_not_exist`, placed in the users section next to `test_find_user_by_token_hash_unknown_returns_none` at `:916`. Assert `find_user_by_token_hash("any-hash") is None`. Docstring: this is the `sqlite3.OperationalError` arm at `app/db/database.py:289`, pinned by return value so it survives the driver swap.
- **Mirror**: `tests/test_db.py:916-919`; fixture from `tests/test_duplicate_checker.py:46-50`
- **Validate**: `python -m pytest tests/test_db.py -q` — all pass, one new test.

### Task 2: Pin the endpoint-level consequence — 401, not 500 (AC1, second half)

- **File**: `tests/test_auth_dependencies.py`
- **Action**: UPDATE
- **Implement**: Add an `uninitialized_db` fixture alongside `temp_db` at `:40`. Add `test_require_identity_returns_401_not_500_when_users_table_does_not_exist`, using the file's existing module-level `client` against `/fake-identity` with `headers={"Authorization": "Bearer anything"}`. Assert `response.status_code == 401` and explicitly `!= 500`. Docstring must carry the security rationale, not just the number: PRD-005 Section 9 treats this as a credential-enumeration control — a 500 here separates "table missing" from "unknown credential" and reopens the oracle that `find_user_by_token_hash()`'s docstring closes. Verified: returns 401.
- **Mirror**: `tests/test_auth_dependencies.py:52-56` and `:122-128` (`..._with_401_not_403`, the same not-the-other-status idiom)
- **Validate**: `python -m pytest tests/test_auth_dependencies.py -q` — all pass, one new test.

### Task 3: Pin the duplicate-check storage failure through the router (AC2, as actually implemented)

- **File**: `tests/test_query_router.py`
- **Action**: UPDATE
- **Implement**: Add `test_duplicate_check_storage_failure_returns_500`. Use the file's existing `temp_db` fixture (it seeds the auth user, so authentication still succeeds) and then induce a **genuine** storage failure by dropping the table the duplicate check reads:
  ```python
  with get_connection() as conn:
      conn.execute("DROP TABLE audit_logs")
  ```
  `get_connection` is already imported at `:15`. POST to `/query` via the module-level `client` and assert `response.status_code == 500` and that the detail names the failed lookup (`"Duplicate lookup failed"`). Pass `_fail_if_called` (`:68`) as the openrouter stub to prove the failure short-circuits before the upstream call.
  **Do not** monkeypatch anything to raise `sqlite3.Error` — dropping a table is a real failure and keeps the test free of driver types. Verified: 500, `{"detail":"Duplicate lookup failed: no such table: audit_logs"}`.
- **Docstring must record Discrepancy A**: AC2 and PRD Pattern 6 describe a degradation that does not exist; the request fails with 500 and STORY-004 must preserve that.
- **Mirror**: `tests/test_query_router.py:379-388`
- **Validate**: `python -m pytest tests/test_query_router.py -q` — all pass, one new test.

### Task 4: Pin the CLI duplicate-`user_id` error (AC3)

- **File**: `tests/test_manage_users_cli.py`
- **Action**: UPDATE
- **Implement**: The existing `test_create_user_duplicate_user_id_exits_nonzero` at `:59` covers the exit code and `"already exists"`. Strengthen it in place (do not add a near-duplicate) so it also asserts the observable contract STORY-004 must preserve: exit code is exactly `1`, the message goes to **stderr** and not stdout, it names the offending `user_id` (`'ana'`), and **no token is printed** — `"cannot be recovered" not in out` — since a failed create must not leak a credential. Verified: exit `1`, stderr `Error: a user with user_id 'ana' already exists.`, stdout empty.
- **Mirror**: `tests/test_manage_users_cli.py:59-65`; stdout/token idiom from `:25-37`
- **Validate**: `python -m pytest tests/test_manage_users_cli.py -q` — all pass.

### Task 5: Pin the CLI duplicate-`token_hash` case (AC4, as actually implemented)

- **File**: `tests/test_manage_users_cli.py`
- **Action**: UPDATE
- **Implement**: Add `test_create_user_duplicate_token_hash_is_not_distinguished_from_duplicate_user_id`. `_create_user` issues a random token via `issue_token()`, so a collision cannot occur naturally — force it by monkeypatching `hash_token` **on the `scripts.manage_users` module** (the name it resolved at import, `scripts/manage_users.py:21`) to return the first user's existing `token_hash`:
  ```python
  monkeypatch.setattr(mu, "hash_token", lambda token: ana.token_hash)
  ```
  Then run `create-user --user-id bob` and assert the verified behavior: exit `1`, and stderr is the **`user_id` message naming `bob`** — a user that does not exist.
- **The test name and docstring must state Discrepancy B explicitly**: the duplicate-credential case is *not* distinguished from the duplicate-`user_id` case, and the message is misleading; `insert_user()`'s docstring says the caller "needs to tell those two cases apart" and the caller does not. This test pins the current, wrong-but-real behavior so STORY-004 does not change it by accident. Fixing it is separate scope. Verified: exit `1`, stderr `Error: a user with user_id 'bob' already exists.`
- **Mirror**: `tests/test_manage_users_cli.py:59-65`; `monkeypatch.setattr` module-attribute idiom as used across `tests/test_query_router.py`
- **Validate**: `python -m pytest tests/test_manage_users_cli.py -q` — all pass, one new test.

### Task 6: Confirm the green baseline and the tests-only diff (AC5, AC6)

- **File**: none
- **Action**: VERIFY
- **Implement**: Run the whole suite with no production changes staged. Then confirm the diff touches `tests/` only. If any new test needs a production change to pass, **stop and raise it** — per AC5 that means the test found a bug, not a baseline.
- **Validate**:
  ```bash
  python -m pytest -q
  git diff main --stat
  ```
  Every path in the stat output must begin with `tests/`.

---

## End-to-End Tests

- [ ] `python -m pytest -q` from the repo root — full suite green, no production file modified
- [ ] `python -m pytest tests/test_db.py tests/test_auth_dependencies.py tests/test_query_router.py tests/test_manage_users_cli.py -q` — green (baseline for the three original targets plus `test_duplicate_checker.py`: 81 passed)
- [ ] `git diff main --stat` lists only paths under `tests/`
- [ ] `grep -rn "sqlite3" tests/test_auth_dependencies.py tests/test_query_router.py tests/test_manage_users_cli.py` returns nothing — no test added by this story names a driver type
- [ ] `grep -c "sqlite3\." tests/test_db.py` is unchanged from `main` (7) — Task 1 adds no driver-typed reference
- [ ] Each of the five new/strengthened tests fails for the right reason when its behavior is inverted by hand (spot-check at least the 401 and the 500), then is reverted

---

## Validation

```bash
# from the repo root, after Task 0
python -c "from app.config import settings; print('config ok')"
python -m pytest -q
git diff main --stat
grep -rn "sqlite3" tests/test_auth_dependencies.py tests/test_query_router.py tests/test_manage_users_cli.py
```

---

## Acceptance Criteria

(Copied from story STORY-002, annotated where exploration changed the reading)

- [ ] Given a database whose `users` table does not exist, when `find_user_by_token_hash(...)` is called, then it returns `None` rather than raising — pinning `app/db/database.py:289`. A companion test asserts the endpoint-level consequence: the request resolves to **401, not 500**. *(Tasks 1-2; verified true today)*
- [ ] Given a storage failure during the duplicate check, when the query pipeline runs, then the query still completes rather than failing — pinning the `except sqlite3.Error` arm at `app/services/duplicate_checker.py:32`. **AMENDED per Discrepancy A**: the verified behavior is `DuplicateCheckError` -> **HTTP 500**; the query does *not* complete. Pinned as-is; the AC wording and PRD Pattern 6 need correcting. *(Task 3)*
- [ ] Given an existing `user_id`, when `scripts/manage_users.py` is asked to create it again, then the CLI reports a duplicate-user error rather than a traceback — pinning `scripts/manage_users.py:37`. *(Task 4; verified true today)*
- [ ] Given an existing `token_hash` on a different `user_id`, when the CLI creates a user with it, then the duplicate-credential case is reported **distinguishably** from the duplicate-`user_id` case. **AMENDED per Discrepancy B**: it is **not** distinguishable today — both print the `user_id` message and exit `1`. Pinned as-is, with the gap named in the test. *(Task 5)*
- [ ] Given these new tests, when they run on `main` with no production changes, then all pass. *(Task 6 — satisfied by construction: every assertion was executed against the current tree before this plan was written)*
- [ ] Given `git diff main --stat`, when it is inspected, then only files under `tests/` are modified. *(Task 6; `.env` in Task 0 is untracked and does not appear in the diff)*
- [ ] All tasks completed
- [ ] Full test suite passes
- [ ] No new test asserts on a driver exception type
- [ ] Follows existing fixture and assertion patterns; STORY-003's fixture centralization is not pre-empted

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| A test that pins a *wrong* behavior (Discrepancies A, B) is later read as endorsement | Both tests carry an explicit docstring naming the gap and the follow-up; the AC4 test's name says `is_not_distinguished` |
| Implementer "fixes" `query.py` or `manage_users.py` to satisfy the AC wording | Task 3 and Task 5 state the prohibition inline; Task 6 and AC6 gate on a tests-only diff |
| A driver-typed assertion sneaks in via test *setup* rather than assertion | Task 3 uses a real `DROP TABLE` instead of a monkeypatched raise; the E2E `grep` check covers all three new-touch files |
| Pre-empting STORY-003's fixture centralization | Tasks 1-2 copy the existing `uninitialized_db` idiom verbatim rather than introducing a shared conftest |
| `.env` blocker is worked around instead of fixed, hiding it from the next story | Task 0 is a prerequisite task with its own validation; the workaround is documented as a workaround |
| `test_db.py:1032`/`:1041` driver-typed assertions get "cleaned up" here | Called out as an anti-pattern above; they are STORY-004's surface, out of scope for this story |
