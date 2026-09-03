---
story: STORY-003
prd: PRD-007
slug: centralize-database-url-fixture
title: "Centralize the 27 DATABASE_URL test sites behind one conftest fixture, still SQLite-backed"
type: REFACTOR
complexity: MEDIUM
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-01
---

# Plan: One conftest, one URL, nineteen files that stop knowing what a `.db` file is

## Summary

Introduce `tests/conftest.py` — the repository has none today — holding the single fixture that provisions a test database and patches `settings.DATABASE_URL` to point at it. Then delete the 29 hand-rolled URL sites across 19 files and let each file request the shared fixture instead. **Nothing about test behavior changes**: the fixture is still SQLite-backed, still `tmp_path`-scoped, still per-test isolated, and every assertion in every file stays byte-identical. What changes is *where the URL comes from*, so that [[STORY-006]] flips one function body instead of 19 files while the suite is red.

The fixture's contract is deliberately narrow and is the whole point of the story: **it yields a URL `str`, never a `Path`**. Two of the three consumers that need something other than "patch settings" get purpose-built seams rather than an escape hatch back to the filesystem — a session-scoped URL *factory* for the subprocess probes (which cannot use a function-scoped fixture), and a `db_connect(url)` callable for the four `test_db.py` tests that must hand-build a pre-migration schema. Both are one-line rewrites in [[STORY-006]]; a `Path` return would not be.

Three facts found during exploration change the shape of the work from what the story assumed, and each is handled below rather than discovered during implementation: there is a **third** subprocess site the story does not name, the two subprocess fixtures are **module-scoped** so a function-scoped fixture cannot reach them, and the suite's **baseline is not green** — seven tests already fail on this branch, four of them a PRD-006 guard that fires precisely because this story is *allowed* to edit those files.

## User Story

As a maintainer
I want every test that provisions a database to obtain its `DATABASE_URL` from a single fixture
So that the driver swap in [[STORY-006]] flips one implementation instead of editing 27 sites across 19 files while the suite is red.

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-003-centralize-database-url-fixture.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md` — Section 2 ("Tests stay hermetic and stay green"), Section 4 (test infrastructure line item), Section 7.6, Section 12 Phase 1, Section 14 Risk 4

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR |
| Complexity | MEDIUM |
| Systems Affected | `tests/` only — 1 file CREATE, 19 files UPDATE. **No** `app/`, **no** `chat_ui/`, **no** `scripts/`, **no** `requirements.txt`. |
| Story | STORY-003 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

**Dependency check**: `depends_on: []` — nothing blocks this story. `blocks: [STORY-006]`, which is `todo`, so no downstream work is waiting on a partial fixture. Cleared to proceed.

**Branch check**: `epic/PRD-007-turso-migration` exists and is the current branch, clean at `5d069cf`. STORY-001 and STORY-002 are both `done` on it. No branch creation needed.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `.agents/skills/frontend-design` | Listed and read in full. Its own `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one" — aesthetic direction, typography, layout. This story writes no UI, renders no output, and emits no user-facing string. | **none** |

`.agents/skills/` was listed: it contains exactly one skill directory, `frontend-design`, whose `SKILL.md` was read in full. Nothing in it constrains a test-fixture refactor. The story frontmatter's `skills: []` is correct; this table records that the scan happened. No skill rule constrains any task below.

`chat_ui/AGENTS.md` mandates the `reflex-docs` skill for changes to Reflex state, events, or the database read path (see the PRD index's Skills table, which applies it to STORY-012). This story changes no Reflex module — `tests/test_render_invariants.py` and `tests/test_admin_shell.py` are edited only in their *fixtures*, not in the probe scripts' Reflex assertions — so that mandate does not reach here.

---

## Findings That Change The Work

Everything in this section was established by reading the tree, and each one alters a task below. None of it is a substitute for running the suite.

### F1 — There is a **third** subprocess site, and the story does not name it

The story's AC 2 names two: `tests/test_admin_shell.py:709` and `tests/test_chat_ui_startup_guard.py:65`. A third exists and is different in kind:

```python
# SOURCE: tests/test_render_invariants.py:165-170 (inside _CHECK_SCRIPT, runs in the child)
    # First, and before any database call: init_db() against the default
    # sqlite:///harness_ai.db would write sentinel previews into the developer's
    # real audit log.
    settings.DATABASE_URL = "sqlite:///{}/console.db".format(
        tempfile.mkdtemp().replace("\\", "/")
    )
```

The child builds its **own** URL from `tempfile.mkdtemp()` rather than receiving one — its `probe` fixture at `tests/test_render_invariants.py:261-266` passes `PYTHONPATH`, `ADMIN_TOKEN` and `OPENROUTER_API_KEY` through `env` but **not** `DATABASE_URL`. AC 3 ("the only production-facing occurrence of `sqlite:///` is inside `tests/conftest.py`") cannot be satisfied while this stands, and the comment at line 166 also contains a literal `sqlite:///harness_ai.db` that the same grep will hit. Task 6 converts it. The story's AC 2 is satisfied as written *and* extended by one site; the story report must record the extension.

### F2 — The two subprocess fixtures are **module-scoped**, so a function-scoped fixture cannot reach them

```python
# SOURCE: tests/test_admin_shell.py:695-698
@pytest.fixture(scope="module")
def pages_probe(tmp_path_factory):
```

`tests/test_render_invariants.py:261` is module-scoped too. A module-scoped fixture requesting a function-scoped one is a `ScopeMismatch` error, not a subtle bug — so the conftest cannot serve these with the same fixture the other 17 files use. This is why the design below carries a **session-scoped `database_url_factory`** alongside the function-scoped fixture: same URL construction, one implementation, two scopes. Both are one line to change in [[STORY-006]].

`tests/test_chat_ui_startup_guard.py:65`'s `_empty_rbac_env` is function-scoped and could use either; it uses the factory, because what it needs is a URL for a *child process*, not a patch of this process's `settings`. Keeping the two subprocess spellings identical is worth more than saving a fixture argument.

### F3 — The baseline is **not green**: 7 failures already, 4 of them the PRD-006 containment guard

`python -m pytest tests -q` on `5d069cf` with a clean tree:

```
FAILED tests/test_chat_state.py::test_chat_state_holds_no_token_or_role_var
FAILED tests/test_untouched_app.py::test_no_file_under_app_changed_since_prd_006_began
FAILED tests/test_untouched_app.py::test_the_chat_modules_are_unchanged_since_prd_006_began
FAILED tests/test_untouched_app.py::test_the_pinned_suites_are_byte_unmodified[tests/test_audit_router.py]
FAILED tests/test_untouched_app.py::test_the_pinned_suites_are_byte_unmodified[tests/test_stats_router.py]
FAILED tests/test_untouched_app.py::test_the_pinned_suites_are_byte_unmodified[tests/test_db.py]
FAILED tests/test_untouched_app.py::test_the_pinned_suites_are_byte_unmodified[tests/test_chat_state.py]
7 failed, 1021 passed, 1 warning in 17.36s
```

Two separate things, and neither is this story's to fix:

- **`test_chat_state_holds_no_token_or_role_var`** is environmental. It asserts `"_token" in ChatState.__annotations__`, and the installed Reflex build reports `{'is_hydrated', '_reflex_internal_links'}` only. Unrelated to the database, unrelated to this story, failing before it starts.
- **`tests/test_untouched_app.py`** is PRD-006's containment guard, measuring `git diff` against the pinned baseline `d3e6279`. It fails because earlier work on this branch — including STORY-002's own commit `403b191` — already changed `app/`, the chat modules, and four of the six suites it pins byte-for-byte.

This matters twice over. First, AC 5's "passes with the same result as before" means **exactly these seven and no others**, which Task 0 records verbatim and Task 12 diffs against. Second, `_UNMODIFIED_SUITES` at `tests/test_untouched_app.py:88-95` pins six suites, four of which this story must edit (`test_audit_router.py`, `test_stats_router.py`, `test_db.py`, `test_chat_state.py`) — all four are **already failing**, so this story adds no new failure. The remaining two, **`tests/test_admin_auth.py` and `tests/test_route_reservations.py`, contain no `sqlite:///` site and must not be opened** — touching either would turn a green parametrization red and violate AC 5.

### F4 — The real count is 29 sites, in three shapes, not 27 + 2

`grep -rn "sqlite:///" tests/ --include=*.py` returns 30 lines. One (`tests/test_render_invariants.py:166`) is a comment; the other 29 are code:

| Shape | Count | Sites |
|---|---|---|
| `monkeypatch.setattr(settings, "DATABASE_URL", ...)` | 26 | the 17 files below plus the multi-site files |
| Direct assignment `settings.DATABASE_URL = ...` | 1 | `test_render_invariants.py:168` (inside the child script) |
| Subprocess environment `env["DATABASE_URL"] = ...` | 2 | `test_admin_shell.py:709`, `test_chat_ui_startup_guard.py:65` |

Per-file counts, verified rather than assumed (the story warns not to assume one per file, and it is right — `test_db.py` has **seven**, not the six the story states):

```
test_admin_shell 1   test_audit_logger 1   test_audit_router 1   test_auth_dependencies 2
test_chat_state 1    test_chat_ui_startup_guard 1                test_db 7
test_duplicate_checker 2   test_identity 2   test_integration 1   test_main 1
test_manage_users_cli 1    test_pii_dedup_isolation 1   test_pii_redaction_integration 1
test_query_pipeline_authorization 1   test_query_router 1   test_rbac 2
test_render_invariants 2 (one is the comment)   test_stats_router 1
```

Task 12 re-runs this grep as the acceptance check; the story report records 29/19, and the discrepancy with the story's "27" is a correction to note, not a scope change.

### F5 — Some tests deliberately run against the developer's real database, and stay that way

`tests/test_main.py:31` and `:73` disable `RBAC_ENABLED` with the comment "the real dev `DATABASE_URL` these tests run against has no seeded users". Those tests set no URL and are **out of scope** — this story centralizes the sites that exist, it does not add fixture usage to tests that never had it. Widening here would change behavior, which AC 5 forbids. Recorded so the implementer does not "helpfully" fix it.

---

## Patterns to Follow

### The idiom being replaced (the canonical shape, 17 files)

```python
# SOURCE: tests/test_audit_logger.py:19-24
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```

### The two names to preserve, because ~400 test signatures spell them

`temp_db` (initialized) and `uninitialized_db` (schema never created) are the names every consuming test already uses. The conftest fixtures **take those exact names**, so no test function signature changes anywhere in the suite. That is what keeps AC 5 provable by diff rather than by argument.

```python
# SOURCE: tests/test_auth_dependencies.py:49-55 — the uninitialized shape (AC 4)
@pytest.fixture
def uninitialized_db(tmp_path, monkeypatch):
    """A database init_db() never ran against, so the `users` table is absent."""
    db_path = tmp_path / "uninitialized.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    return db_path
```

Its three consumers are the [[STORY-002]] characterization tests, which must survive this story untouched: `tests/test_db.py:927`, `tests/test_auth_dependencies.py:136`, `tests/test_duplicate_checker.py:115`.

### Fixtures that do more than set the URL — preserved by pytest's override mechanism

```python
# SOURCE: tests/test_chat_state.py:51-59
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

A module-level fixture may **override** a conftest fixture of the same name *and request it*, which is exactly the seam wanted: the local fixture keeps its seeding and delegates the URL.

```python
# The shape every seeding file adopts
@pytest.fixture
def temp_db(temp_db):          # requests the conftest fixture of the same name
    insert_user(User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN)))
    return temp_db
```

Five files need this: `test_chat_state.py`, `test_integration.py`, `test_pii_dedup_isolation.py`, `test_pii_redaction_integration.py`, `test_query_router.py`. Task 1 proves the mechanism before Task 4 relies on it 5 times.

### Raw-connection seeding of a pre-migration schema (`test_db.py`, 4 call sites)

```python
# SOURCE: tests/test_db.py:137-144
def _create_pre_pii_database(db_path) -> None:
    """Builds the 14-column audit_logs table exactly as it shipped before PRD-003.

    Uses raw sqlite3.connect rather than get_connection() so the fixture is the
    genuine pre-migration shape, unaffected by whatever init_db() does today.
    """
    legacy = sqlite3.connect(db_path)
```

These are the only tests that genuinely need a connection rather than a URL. They get one from the conftest-provided `db_connect` callable, so the URL→connection translation lives in conftest with everything else.

### The subprocess-environment shape (3 sites after F1)

```python
# SOURCE: tests/test_chat_ui_startup_guard.py:62-68
@pytest.fixture
def _empty_rbac_env(tmp_path):
    db_path = tmp_path / "chat_ui_guard_test.db"
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(_PYTHONPATH)}
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
```

`app/config.py:4-10` is a pydantic `BaseSettings` with `DATABASE_URL` as a declared field, so a `DATABASE_URL` in the child's environment is picked up with no code in the child. That is what lets Task 6 delete the child-side assignment in `test_render_invariants.py` outright rather than replace it.

---

## Design

### `tests/conftest.py` — the whole public surface

Five names. Everything else in the file is private.

| Fixture | Scope | Yields | Patches `settings`? | Schema created? | Consumers |
|---|---|---|---|---|---|
| `database_url` | function | `str` URL | yes (`monkeypatch`) | no | the two below; direct use is allowed but unnecessary |
| `temp_db` | function | `str` URL | yes (via `database_url`) | yes — `init_db()` | 17 files |
| `uninitialized_db` | function | `str` URL | yes (via `database_url`) | no | 3 files (the STORY-002 tests) |
| `database_url_factory` | **session** | `Callable[[str], str]` | **no** | no | 3 subprocess fixtures |
| `db_connect` | function | `Callable[[str], sqlite3.Connection]` | n/a | n/a | `test_db.py`, `test_rbac.py` legacy seeding |

Design commitments, each of which is a thing [[STORY-006]] will thank this story for:

1. **`str`, never `Path`.** Stated by the story as the seam and honored literally. Every returning fixture returns the URL string. No consumer does path arithmetic on it.
2. **`sqlite:///` appears in exactly one place** — one private helper in `conftest.py` that builds a URL from a temp directory. `db_connect` strips the same prefix in one other private helper. Both are the two lines [[STORY-006]] replaces.
3. **`db_connect` does not reuse `app.db.database._db_path()`.** Coupling the test seam to a private production function that [[STORY-006]] deletes would make the swap harder, not easier.
4. **`database_url_factory` does not patch `settings`.** Its callers hand the URL to a child process; patching the parent's settings would be a lie about what the fixture does, and would make `test_admin_shell.py`'s module-scoped probe leak a patch across the module.
5. **Isolation is per-test and comes from `tmp_path`**, unchanged from today. `database_url_factory` uses `tmp_path_factory.mktemp(name)`, which is already what `test_admin_shell.py:699` does.

### Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/conftest.py` | **CREATE** | The five fixtures. The only file in `tests/` allowed to contain `sqlite:///`. |
| `tests/test_audit_logger.py` | UPDATE | delete local `temp_db` (1 site) |
| `tests/test_audit_router.py` | UPDATE | delete local `temp_db` (1) — *pinned suite, already failing (F3)* |
| `tests/test_stats_router.py` | UPDATE | delete local `temp_db` (1) — *pinned suite, already failing (F3)* |
| `tests/test_query_pipeline_authorization.py` | UPDATE | delete local `temp_db` (1) |
| `tests/test_identity.py` | UPDATE | delete local `temp_db`; inline site at `:97` → `uninitialized_db` (2) |
| `tests/test_manage_users_cli.py` | UPDATE | delete local `temp_db` (1) |
| `tests/test_main.py` | UPDATE | `_empty_users_db` delegates to `temp_db` (1) |
| `tests/test_duplicate_checker.py` | UPDATE | delete local `temp_db` + `uninitialized_db` (2) |
| `tests/test_auth_dependencies.py` | UPDATE | delete local `temp_db` + `uninitialized_db` (2) |
| `tests/test_chat_state.py` | UPDATE | override `temp_db`, keep seeding (1) — *pinned suite, already failing (F3)* |
| `tests/test_integration.py` | UPDATE | override `temp_db`, keep two `insert_user` (1) |
| `tests/test_pii_dedup_isolation.py` | UPDATE | override `temp_db`, keep two `insert_user` (1) |
| `tests/test_pii_redaction_integration.py` | UPDATE | override `temp_db`, keep `insert_user` (1) |
| `tests/test_query_router.py` | UPDATE | override `temp_db`, keep `insert_user` (1) |
| `tests/test_rbac.py` | UPDATE | delete local `temp_db`; legacy-seeding test at `:273` → `uninitialized_db` + `db_connect` (2) |
| `tests/test_db.py` | UPDATE | **7 sites**: 2 fixtures + 5 inline, incl. 4 legacy-schema builders → `db_connect` — *pinned suite, already failing (F3)* |
| `tests/test_admin_shell.py` | UPDATE | module-scoped probe → `database_url_factory` (1) |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | `_empty_rbac_env` → `database_url_factory` (1) |
| `tests/test_render_invariants.py` | UPDATE | **F1**: pass URL through `env`, delete child-side assignment and the comment at `:166` (2) |

**Must not be opened**: `tests/test_admin_auth.py`, `tests/test_route_reservations.py` (F3), anything under `app/`, `chat_ui/`, `scripts/` (AC 6).

### Dependency order

Task 1 (conftest) must precede everything. Tasks 2–7 are independent of each other and are ordered by rising risk — the 12 mechanical files first, so that if the harder files misbehave the failure is unambiguous. Task 8 is the AC-3 sweep, Tasks 9–12 are verification.

### Risks + mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | The same-name fixture override (`def temp_db(temp_db)`) misbehaves and silently shadows instead of delegating, so seeding runs against an unpatched URL — i.e. the developer's real `harness_ai.db`. | Task 1 proves the mechanism on **one** file (`test_chat_state.py`) and runs that file alone before Task 4 applies it to the other four. Fallback if it does not hold: the local fixture requests `database_url` and calls `init_db()` itself — one extra line per file, no signature change. |
| R2 | A conftest at `tests/` changes collection or import behavior for the suite (there is none today). | `tests/` has no `__init__.py`; pytest's rootdir insertion already puts it on `sys.path`. Task 1's validation is a full-suite run, not a single file, precisely to catch a collection-level surprise early. |
| R3 | `test_db.py`'s 7 sites are edited as a batch and one legacy-schema test starts passing for the wrong reason (e.g. `init_db()` run before `_create_pre_pii_database`). | Task 5 edits `test_db.py` alone and validates with `pytest tests/test_db.py -q`, comparing pass/fail counts against Task 0's per-file baseline — not just "green". |
| R4 | Editing four PRD-006-pinned suites is read as new breakage. | F3 records that all four `test_the_pinned_suites_are_byte_unmodified` parametrizations already fail at `5d069cf`. Task 12 asserts the failure **set** is unchanged, and the story report names the four explicitly with the reason. |
| R5 | `test_render_invariants.py`'s probe stops isolating the database and writes sentinel previews into the developer's real `harness_ai.db` — the exact disaster its docstring exists to prevent. | Task 6 passes `DATABASE_URL` through `env` **before** deleting the child-side assignment, and its validation asserts the probe still returns seeded rows *and* that `git status` shows no modification to `harness_ai.db`. |
| R6 | `database_url_factory` is session-scoped; two module-scoped probes requesting it collide on a temp directory name. | The factory takes a required `name` argument and calls `tmp_path_factory.mktemp(name)`, which pytest already makes unique per call (`admin_pages0`, `admin_pages1`, …). Each of the three call sites passes a distinct name. |
| R7 | Scope creep into `test_main.py`'s real-database tests (F5). | Named in F5 as explicitly out of scope; Task 12's grep is the acceptance check, and it does not flag tests that set no URL. |

---

## Tasks

Execute in order. Each task is atomic and independently verifiable.

### Task 0: Record the baseline, per-file and per-node

- **File**: none (scratch only — nothing committed)
- **Action**: MEASURE
- **Implement**: On a clean tree at `5d069cf`, run the full suite and save the exact failure list and the totals. Also record the per-file counts for the three files that get their own validation step:
  ```bash
  python -m pytest tests -q > "$SCRATCH/baseline.txt" 2>&1
  python -m pytest tests/test_db.py tests/test_rbac.py tests/test_render_invariants.py -q >> "$SCRATCH/baseline.txt" 2>&1
  grep -rn "sqlite:///" tests/ --include=*.py > "$SCRATCH/baseline-sites.txt"
  ```
  Expected, per F3: `7 failed, 1021 passed`, with the seven node IDs listed there. If the observed baseline differs, **stop and report** — the plan's AC-5 check is calibrated to this list.
- **Mirror**: n/a
- **Validate**: `$SCRATCH/baseline.txt` ends with `7 failed, 1021 passed`; `$SCRATCH/baseline-sites.txt` has 30 lines.

### Task 1: Create `tests/conftest.py` and prove the override mechanism

- **File**: `tests/conftest.py` (CREATE), `tests/test_chat_state.py` (UPDATE)
- **Action**: CREATE + UPDATE
- **Implement**:
  1. Write the five fixtures from the Design table. One private `_url_for(directory, name) -> str` builds `f"sqlite:///{directory / name}"` — **the only `sqlite:///` literal in the repository's tests**. One private `_path_from_url(url) -> str` strips the prefix for `db_connect`. `database_url` uses `tmp_path` + `monkeypatch.setattr(settings, "DATABASE_URL", url)` and yields the `str`. `temp_db` requests `database_url`, calls `init_db()`, returns it. `uninitialized_db` requests `database_url` and returns it unchanged, with a docstring naming the [[STORY-002]] tests it serves. `database_url_factory` is `scope="session"`, requests `tmp_path_factory`, and returns a `Callable[[str], str]`. `db_connect` returns a callable opening `sqlite3.connect(_path_from_url(url))`.
  2. Give the module a docstring stating the contract in one line — *this file is the seam; STORY-006 changes it and nothing else* — and stating why the return type is `str` and not `Path`.
  3. Convert `tests/test_chat_state.py` (lines 50-59) to the override shape, as the single proof of R1 before it is used four more times.
- **Mirror**: `tests/test_audit_logger.py:19-24` for the fixture body; `tests/test_admin_shell.py:699` for `tmp_path_factory.mktemp` usage.
- **Validate**:
  ```bash
  python -m pytest tests/test_chat_state.py -q        # same result as Task 0's per-file baseline
  python -m pytest tests -q                            # still exactly 7 failed, 1021 passed (R2)
  ```

### Task 2: Convert the seven single-fixture files

- **Files**: `tests/test_audit_logger.py`, `tests/test_audit_router.py`, `tests/test_stats_router.py`, `tests/test_query_pipeline_authorization.py`, `tests/test_manage_users_cli.py`, `tests/test_integration.py`, `tests/test_identity.py`
- **Action**: UPDATE
- **Implement**: Delete each local `temp_db` fixture entirely. Remove the now-unused `from app.config import settings` import **only where nothing else in the file uses `settings`** — check each file rather than assuming (`test_pii_redaction_integration.py:43` reads `settings.ADMIN_TOKEN`, `test_identity.py` reads `settings.ADMIN_TOKEN` at `:100`). `test_integration.py` keeps a seeding override (two `insert_user` calls). `test_identity.py:96-98` additionally converts its inline site to the `uninitialized_db` fixture.
- **Mirror**: the override shape in Task 1's `test_chat_state.py`.
- **Validate**: `python -m pytest tests/test_audit_logger.py tests/test_audit_router.py tests/test_stats_router.py tests/test_query_pipeline_authorization.py tests/test_manage_users_cli.py tests/test_integration.py tests/test_identity.py -q` — all pass.

### Task 3: Convert the two files that also define `uninitialized_db`

- **Files**: `tests/test_duplicate_checker.py` (`:41-52`), `tests/test_auth_dependencies.py` (`:41-55`)
- **Action**: UPDATE
- **Implement**: Delete both local fixtures from each file; the conftest names match, so no consumer changes. **Do not touch** `test_malformed_db_raises_duplicate_check_error` (`test_duplicate_checker.py:115`) or `test_require_identity_returns_401_not_500_when_users_table_does_not_exist` (`test_auth_dependencies.py:136`) — these are [[STORY-002]] characterization tests and their bodies and docstrings stay byte-identical. This task is the practical proof of AC 4.
- **Mirror**: `tests/test_auth_dependencies.py:49-55` (the fixture being centralized).
- **Validate**: `python -m pytest tests/test_duplicate_checker.py tests/test_auth_dependencies.py -q` — all pass, and the two named characterization tests pass by their own assertions (return value / status code), not by exception type.

### Task 4: Convert the four remaining seeding files

- **Files**: `tests/test_pii_dedup_isolation.py`, `tests/test_pii_redaction_integration.py`, `tests/test_query_router.py`, `tests/test_main.py`
- **Action**: UPDATE
- **Implement**: The first three take the override shape proven in Task 1, keeping their `insert_user` calls verbatim. `tests/test_main.py:87-90`'s `_empty_users_db` becomes a fixture requesting `temp_db` and returning nothing (its callers use it only for its side effect). **Do not** add fixture usage to the tests at `test_main.py:31` and `:73` — F5.
- **Mirror**: Task 1's `test_chat_state.py` override.
- **Validate**: `python -m pytest tests/test_pii_dedup_isolation.py tests/test_pii_redaction_integration.py tests/test_query_router.py tests/test_main.py -q` — all pass.

### Task 5: Convert `test_db.py` — seven sites, four of them legacy-schema builders

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**:
  1. Delete the `temp_db` (`:41-46`) and `uninitialized_db` (`:48-53`) fixtures.
  2. Change `_create_pre_pii_database` (`:137`) and `_create_pre_rbac_database` (`:210`) to take `(connect, url)` instead of a path, calling `connect(url)` for the connection. Their docstrings' claim — raw connection, genuine pre-migration shape, unaffected by `init_db()` — stays true and stays written.
  3. Convert the four inline sites (`:180`, `:253`, `:285`, `:873`) and the synthetic-column test (`:89`) to request `uninitialized_db` + `db_connect`, passing both into the helpers.
  4. Leave `test_init_db_issues_no_alter_when_schema_is_current` (`:118`) and its `set_trace_callback` tracing alone — it requests `temp_db` and needs no change.
- **Mirror**: `tests/test_db.py:137-144` (the helper being re-signatured).
- **Validate**: `python -m pytest tests/test_db.py -q` — pass/fail counts identical to Task 0's per-file baseline; then `grep -c "sqlite:///" tests/test_db.py` returns `0`.

### Task 6: Convert the three subprocess sites, including the one the story does not name (F1)

- **Files**: `tests/test_admin_shell.py`, `tests/test_chat_ui_startup_guard.py`, `tests/test_render_invariants.py`
- **Action**: UPDATE
- **Implement**:
  1. `tests/test_admin_shell.py:695-711`: `pages_probe` requests `database_url_factory` instead of `tmp_path_factory`, and `env["DATABASE_URL"]` becomes `database_url_factory("admin_pages")`. **Keep the comment at `:697-699** — it records *why* the URL is pinned at all (`chat_ui.chat_ui` calls `init_db()` at import) and that constraint is unchanged; reword only the sentence describing the mechanism.
  2. `tests/test_chat_ui_startup_guard.py:62-68`: `_empty_rbac_env` requests `database_url_factory` instead of `tmp_path`; `env["DATABASE_URL"] = database_url_factory("chat_ui_guard")`.
  3. `tests/test_render_invariants.py`: add `"DATABASE_URL": database_url_factory("render_probe")` to the `probe` fixture's `env` dict (`:266-273`), have `probe` request the factory, then **delete lines 165-170 from `_CHECK_SCRIPT`** — the comment and the `settings.DATABASE_URL = ...` assignment — along with the now-unused `tempfile` import in the child. Update the module docstring at `:35` so it describes the env-passed URL rather than "the script sets `settings.DATABASE_URL`"; the paragraph's *point* (this must not run in-process, or sentinels reach the real audit log) is unchanged and stays.
- **Mirror**: `tests/test_chat_ui_startup_guard.py:62-68` for the env shape; `app/config.py:4-10` is why the child needs no code.
- **Validate**:
  ```bash
  python -m pytest tests/test_admin_shell.py tests/test_chat_ui_startup_guard.py tests/test_render_invariants.py -q
  git status --porcelain harness_ai.db     # must be empty (R5)
  ```
  All pass, and `test_the_probe_actually_loaded_the_seeded_record` (`test_render_invariants.py:308`) passing is the proof that the env-passed URL actually reached the child.

### Task 7: Convert `test_rbac.py`

- **File**: `tests/test_rbac.py`
- **Action**: UPDATE
- **Implement**: Delete the local `temp_db` (`:57-62`). The pre-RBAC lifecycle test at `:272-275` requests `uninitialized_db` + `db_connect` and calls `_create_pre_rbac_database` with the new `(connect, url)` signature — this file imports that helper's shape from its own copy or from `test_db.py`; verify which and keep the two in step. Left for its own task because it is the only file that couples to Task 5's re-signatured helper.
- **Mirror**: Task 5's converted call sites.
- **Validate**: `python -m pytest tests/test_rbac.py -q` — all pass.

### Task 8: The AC-3 sweep

- **File**: none (verification), plus any file the sweep flags
- **Action**: VERIFY
- **Implement**:
  ```bash
  grep -rn "sqlite:///" tests/ --include=*.py
  ```
  The only lines returned must be inside `tests/conftest.py`. Every other hit — code **or comment** — is converted or rewritten. Confirm no test currently asserts the *rejection* of a `sqlite:///` URL (exploration found none; that assertion arrives with [[STORY-005]]), and record "none" for that AC's exemption clause in the story report.
- **Mirror**: n/a
- **Validate**: `grep -rn "sqlite:///" tests/ --include=*.py | grep -v "^tests/conftest.py:"` returns nothing (exit 1).

### Task 9: Prove per-test isolation is real, not inherited by luck (AC 1)

- **File**: `tests/conftest.py` (docstring only, if anything)
- **Action**: VERIFY
- **Implement**: Run the suite twice in different orders and confirm the failure set is unchanged, which is what per-test isolation buys:
  ```bash
  python -m pytest tests -q -p no:randomly
  python -m pytest tests/test_integration.py tests/test_db.py tests/test_rbac.py tests/test_chat_state.py -q
  python -m pytest tests/test_chat_state.py tests/test_rbac.py tests/test_db.py tests/test_integration.py -q
  ```
  Any order-dependent result means two tests are sharing a database and the fixture's isolation claim is false — stop and fix before Task 12.
- **Mirror**: n/a
- **Validate**: the two reversed-order runs produce identical pass/fail counts.

### Task 10: Prove the containment claim (AC 6)

- **File**: none
- **Action**: VERIFY
- **Implement**: `git diff main --stat -- app/ chat_ui/ scripts/ requirements.txt` — this story's own commit adds nothing here. Because the branch already carries STORY-001/002 changes under `app/` and `.agents/`, the honest check is the **staged diff of this story's commit**, not the branch diff: `git diff --cached --stat` before committing must list `tests/` paths only.
- **Mirror**: n/a
- **Validate**: `git diff --cached --name-only | grep -v "^tests/\|^.agents/"` returns nothing.

### Task 11: Confirm the four pinned-suite failures are pre-existing, not new (R4/F3)

- **File**: none
- **Action**: VERIFY
- **Implement**: `python -m pytest tests/test_untouched_app.py -q`. The failing parametrizations must be exactly the four from Task 0 — `test_audit_router.py`, `test_stats_router.py`, `test_db.py`, `test_chat_state.py`. If `tests/test_admin_auth.py` or `tests/test_route_reservations.py` appears, this story opened a file it must not have; revert that file.
- **Mirror**: `tests/test_untouched_app.py:88-95` (`_UNMODIFIED_SUITES`).
- **Validate**: the failure set for that file is identical to Task 0's.

### Task 12: Full suite, diffed against the baseline (AC 5)

- **File**: none
- **Action**: VERIFY
- **Implement**:
  ```bash
  python -m pytest tests -q > "$SCRATCH/after.txt" 2>&1
  diff <(grep "^FAILED" "$SCRATCH/baseline.txt" | sort) <(grep "^FAILED" "$SCRATCH/after.txt" | sort)
  ```
  Also confirm no assertion was weakened: `git diff main -- tests/ | grep "^-.*assert"` must show only assertion lines that moved, never any that vanished. Every deleted `assert` has to be accounted for line by line, and the answer should be zero.
- **Mirror**: n/a
- **Validate**: the `diff` is empty; totals read `7 failed, 1021 passed`; no `assert` was deleted.

---

## End-to-End Tests

- [ ] `python -m pytest tests -q` → `7 failed, 1021 passed`, the same seven node IDs as the baseline
- [ ] `grep -rn "sqlite:///" tests/ --include=*.py` → hits only inside `tests/conftest.py`
- [ ] `python -m pytest tests/test_render_invariants.py -q` passes **and** `git status --porcelain harness_ai.db` is empty — the console probe wrote its sentinels into a temp database, not the developer's audit log
- [ ] `python -m pytest tests/test_admin_shell.py -q` passes — the module-scoped probe got a URL from a session-scoped fixture without a `ScopeMismatch`
- [ ] The three [[STORY-002]] characterization tests pass with their bodies unmodified: `tests/test_db.py::test_find_user_by_token_hash_returns_none_when_users_table_does_not_exist`, `tests/test_auth_dependencies.py::test_require_identity_returns_401_not_500_when_users_table_does_not_exist`, `tests/test_duplicate_checker.py::test_malformed_db_raises_duplicate_check_error`
- [ ] Reversed-order runs of four database-heavy files give identical results (isolation)
- [ ] `git diff --cached --name-only` for this story's commit lists only `tests/` and `.agents/` paths

## Validation

```bash
cd c:/Users/tobip/Documents/prog/harness-ai
python -m pytest tests -q
grep -rn "sqlite:///" tests/ --include=*.py | grep -v "^tests/conftest.py:"   # expect: no output
git diff --cached --name-only | grep -v "^tests/\|^\.agents/"                  # expect: no output
git status --porcelain harness_ai.db                                           # expect: no output
```

## Acceptance Criteria

(Copied from story `STORY-003`, with the verifying task named)

- [ ] Given `tests/conftest.py`, when a test requests the shared database fixture, then it receives an isolated, empty database and `settings.DATABASE_URL` is patched to point at it for the duration of that test. Isolation is per-test: no test observes rows written by another. → Tasks 1, 9
- [ ] Given the two subprocess call sites — `tests/test_admin_shell.py:709` and `tests/test_chat_ui_startup_guard.py:65` — when they launch their subprocess, then they obtain the same URL from the same fixture and pass it through the child environment. These two must not keep their own hand-built `sqlite:///` strings. → Task 6 (which also covers the third site, `tests/test_render_invariants.py`, per F1)
- [ ] Given the whole suite, when `grep -rn "sqlite:///" tests/` runs, then the only production-facing occurrence is inside `tests/conftest.py`. Assertions that deliberately test the *rejection* of a `sqlite:///` URL are exempt and, if any exist, are named in the story report. → Task 8 (exploration found none; the report records "none")
- [ ] Given the fixture, when a test needs a database whose schema was never initialized (the `users`-table-missing case from [[STORY-002]]), then the fixture supports that without the test hand-rolling its own connection. → `uninitialized_db`, Tasks 1 and 3
- [ ] Given the full suite, when it runs after this change, then it passes with the same result as before, and no test's own assertions were weakened or deleted to achieve it. → Tasks 0 and 12. **"The same result" is the seven pre-existing failures recorded in F3, not zero failures** — the baseline is red before this story starts and for reasons unrelated to it.
- [ ] Given `git diff main --stat`, when it is inspected, then no file under `app/`, `chat_ui/`, or `scripts/` is modified. → Task 10, asserted on this story's own staged diff (the branch already carries STORY-001/002's `app/` changes)
- [ ] All tasks completed
- [ ] Follows existing patterns
