---
story: STORY-005
prd: PRD-007
slug: turso-configuration
title: "Config: TURSO_AUTH_TOKEN, libSQL DATABASE_URL semantics, and no file fallback"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-01
---

# Plan: Config — TURSO_AUTH_TOKEN, libSQL DATABASE_URL semantics, and no file fallback

## Summary

Move the `DATABASE_URL` scheme check out of `app/db/database.py:24-25` — where it fires on first query — into `app/config.py`, where it fires at import. `DATABASE_URL` loses its `sqlite:///harness_ai.db` default and becomes a required field constrained to the three libSQL schemes (`libsql://`, `https://`, `http://`); `TURSO_AUTH_TOKEN` joins it, required whenever the endpoint is remote and optional for the local `http://` dev server. This is the codebase's **first pydantic validator** — `app/config.py` has never had one — so the plan establishes the shape as well as the rule.

The change is small in production code and large in blast radius, because `app/config.py:36` constructs `Settings()` at import time and nothing in `tests/` currently supplies a `DATABASE_URL`: the suite has been living on the default this story removes. Tasks 4–7 are that fallout, and they are not optional — without them CI cannot even collect. Three subprocess probes (`test_admin_shell.py`, `test_chat_ui_startup_guard.py`, `test_render_invariants.py`) hand a `sqlite:///` URL to a **child process**, where the new validator does run and `monkeypatch` cannot reach; they get a two-line preamble, minted once in `conftest.py`, that STORY-006 deletes wholesale. The Dockerfile placeholder breaks by design and is left to STORY-014, which claims it in writing.

## User Story

As a **platform engineer**
I want `DATABASE_URL` to name a libSQL endpoint and a `sqlite:///` value to be a startup error
So that no deployment can silently create a local database file that nobody reads and nobody backs up.

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-005-turso-configuration.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md` — §4 (in scope), §9 (Security & Configuration), §11 (functional requirements), §12 Phase 2
- Upstream decision record: `.agents/reports/PRD-007-turso-migration/STORY-001-driver-decision.md` — §4 fixes the accepted local endpoint as `http://127.0.0.1:8080` with **no token**

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (configuration surface) |
| Complexity | MEDIUM — small production diff, wide test fallout |
| Systems Affected | `app/config.py`, `.env.example`, `tests/` (5 files) |
| Story | STORY-005 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

---

## Skills In Use

`.agents/skills/` was listed in full. It contains exactly one skill:

| Skill | Applies? | Reason |
|-------|----------|--------|
| `frontend-design` | **No** | Its `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one." This story touches `app/config.py`, `.env.example`, and `tests/`. It renders nothing. |

The story's `skills:` frontmatter field is `[]`, and the story's own Technical Notes reach the same conclusion. **No skill constrains any task below.**

---

## Patterns to Follow

### Naming — settings are grouped under a comment naming the PRD that introduced them

```python
# SOURCE: app/config.py:14-19
    # RBAC (PRD-005). RBAC_DEFAULT_ROLE was added by STORY-004 for
    # scripts/manage_users.py; the rest of this group is added by STORY-005.
    RBAC_ENABLED: bool = True
    RBAC_DEFAULT_ROLE: str = "user"
    RBAC_ROLES_FILE: str = ""
    MODEL_ALLOWLIST: str = "gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet"
```

Required secrets carry no default and sit at the top:

```python
# SOURCE: app/config.py:7-8
    OPENROUTER_API_KEY: str
    ADMIN_TOKEN: str
```

### Error handling — name the setting, quote the offending value, offer the remedy

```python
# SOURCE: app/services/authz.py:92-95
        raise AuthzConfigError(
            f"RBAC_ROLES_FILE '{path_str}' grants unrecognized permission(s): {', '.join(unknown)}"
        )

# SOURCE: app/services/authz.py:119-123 -- the message carries the fix, not just the fault
    raise RbacNotBootstrappedError(
        "RBAC_ENABLED=true but no active users exist. Bootstrap one with: "
        "python scripts/manage_users.py create-user --user-id <id> "
        "--role <admin|auditor|user>"
    )
```

The rule this story replaces, for reference:

```python
# SOURCE: app/db/database.py:22-26
def _db_path() -> str:
    url = settings.DATABASE_URL
    if not url.startswith(_SQLITE_PREFIX):
        raise ValueError(f"Unsupported DATABASE_URL scheme: {url}")
    return url[len(_SQLITE_PREFIX):]
```

**Deliberate divergence from that line:** it echoes the whole URL. A libSQL URL can carry `?authToken=…`, and AC 6 forbids a message containing the token. The validator echoes **the scheme only**. This is the one place the plan does not mirror the existing code, and the reason is an acceptance criterion.

### Validators — no precedent exists

A repo-wide search for `field_validator|model_validator|@validator|Field(` returns no production hit. `app/config.py`'s only computed members are two properties (`:27-33`). pydantic is **2.13.4** / pydantic-settings **2.15.0**, so `field_validator` and `model_validator(mode="after")` are both available. This story sets the precedent; keep it plain and keep the helpers module-private, matching the `_`-prefixed style of `app/db/database.py:18`.

### Tests — construction, raising, and `.env.example`

```python
# SOURCE: tests/test_config.py:45-50 -- the suite's only direct Settings() construction
def test_settings_construct_without_new_env_vars(monkeypatch):
    for var in ("RBAC_ENABLED", "RBAC_DEFAULT_ROLE", "RBAC_ROLES_FILE", "MODEL_ALLOWLIST"):
        monkeypatch.delenv(var, raising=False)

    fresh = Settings(_env_file=None)

# SOURCE: tests/test_schemas.py:2,21-23 -- the ValidationError import to follow
from pydantic import ValidationError

def test_query_request_missing_prompt_raises():
    with pytest.raises(ValidationError):
        QueryRequest(user_id="juan@empresa.com")

# SOURCE: tests/test_authz.py:170-174 -- assert on the message, not only the type
    with pytest.raises(AuthzConfigError) as exc_info:
        load()

    assert str(roles_file) in str(exc_info.value)

# SOURCE: tests/test_config.py:62-68 -- .env.example is asserted, not assumed
def test_env_example_documents_every_new_rbac_var_with_a_comment():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in ("RBAC_ENABLED", "RBAC_DEFAULT_ROLE", "RBAC_ROLES_FILE", "MODEL_ALLOWLIST"):
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"
```

### The test seam — one file spells a URL

```python
# SOURCE: tests/conftest.py:34-40
# The only `sqlite:///` literal in tests/. STORY-006 replaces these two helpers
# with the libSQL endpoint equivalents; nothing else in this directory knows the
# scheme exists.
_SQLITE_PREFIX = "sqlite:///"
```

STORY-003 bought this property one commit ago. Every test-side change below is made **in `conftest.py` or against a constant exported from it**, so STORY-006 still has one place to change.

---

## The load-bearing fact this plan is built on

`monkeypatch.setattr(settings, "DATABASE_URL", …)` — `tests/conftest.py:63`, the single in-process patch site — **assigns to an already-constructed instance and therefore does not run validators.** In-process tests may keep using `sqlite:///{tmp_path}` after this story, unchanged, and they do. Only two things actually break:

1. **Import-time construction.** `app/config.py:36` runs `Settings()` on every import of `app.config`. With no default, `DATABASE_URL` must come from the environment. CI (`.github/workflows/ci.yml:22-25`) supplies none, and `.env` is gitignored, so **collection fails for all 21 test modules** unless something sets it first. → Task 4.
2. **Child processes.** Three fixtures pass `DATABASE_URL=sqlite:///…` through a subprocess environment, where a real `Settings()` is constructed and the validator *does* fire: `tests/test_admin_shell.py:712`, `tests/test_chat_ui_startup_guard.py:64`, `tests/test_render_invariants.py:270`. → Tasks 5–6.

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | UPDATE | `DATABASE_URL` required + scheme-validated; `TURSO_AUTH_TOKEN` added; two validators |
| `.env.example` | UPDATE | `DATABASE_URL` re-documented as an endpoint; `TURSO_AUTH_TOKEN` documented |
| `tests/test_config.py` | UPDATE | AC 7's five cases, plus `.env.example` coverage for the two vars |
| `tests/conftest.py` | UPDATE | Session-wide `DATABASE_URL` bootstrap + the child-process preamble constant |
| `tests/test_conftest_fixtures.py` | UPDATE | `:57` asserts against a default that no longer exists |
| `tests/test_admin_shell.py` | UPDATE | Child probe preamble |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | Child probe preamble |
| `tests/test_render_invariants.py` | UPDATE | Child probe preamble |

**Not touched, deliberately:** `app/db/database.py` (`_db_path()` and `_SQLITE_PREFIX` stay exactly as they are — STORY-006 deletes them), `Dockerfile`, `docker-compose.yml`, `README.md`.

## Dependency order

Task 1 → 2 (production rule, then its documentation) → 4 (unbreak collection) → 5 → 6 (unbreak the children) → 3 (the story's own tests, written against a suite that can run) → 7 (the invalidated assertion) → 8 (full-suite verification).

Task 3 is deliberately *after* Task 4: writing `tests/test_config.py` against a suite that cannot collect wastes a cycle.

---

## Tasks

### Task 1: Make `DATABASE_URL` a validated libSQL endpoint and add `TURSO_AUTH_TOKEN`

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**:
  1. Add module-private constants above the class, mirroring `app/db/database.py:18`'s `_`-prefixed style:
     - `_REMOTE_SCHEMES = ("libsql://", "https://")` — TLS or libSQL protocol; PRD §9 "The connection is TLS for any remote endpoint".
     - `_LOCAL_SCHEME = "http://"` — PRD §9: "a plaintext `http://` endpoint is permitted only for the local development server".
     - `_SQLITE_SCHEME = "sqlite:"` — matches `sqlite:///x`, `sqlite:////abs`, and `sqlite:///:memory:` alike.
  2. Replace `DATABASE_URL: str = "sqlite:///harness_ai.db"` (`:10`) with `DATABASE_URL: str` — **no default**. Move it into a new group directly under `ADMIN_TOKEN`, with the group comment naming the PRD, matching `:14-15`:
     ```python
     # Turso / libSQL (PRD-007). DATABASE_URL names a network endpoint, not a
     # file, and carries no default: a default that silently creates a local
     # database nobody reads and nobody backs up is the failure mode PRD-007
     # removes. TURSO_AUTH_TOKEN is required for a remote endpoint and unused
     # against the local dev server, which takes no token.
     DATABASE_URL: str
     TURSO_AUTH_TOKEN: str = ""
     ```
  3. A `_scheme_of(url: str) -> str` module-private helper returning everything up to and including `://` (or the whole string when absent). **Every message below quotes this, never the URL** — AC 6, and a libSQL URL may carry `?authToken=`.
  4. `@field_validator("DATABASE_URL")` (classmethod; the default `mode="after"` is right here):
     - `sqlite:` prefix → `ValueError` naming the replacement form, e.g.
       `"DATABASE_URL must name a libSQL endpoint, not a file. Replace the 'sqlite:' URL with 'libsql://<database>-<org>.turso.io' (or 'http://127.0.0.1:8080' for the local dev server). PRD-007 removed the file fallback deliberately."`
     - Not one of `_REMOTE_SCHEMES + (_LOCAL_SCHEME,)` → `ValueError(f"Unsupported DATABASE_URL scheme: {_scheme_of(value)!r}. Expected one of: libsql://, https://, http:// (local dev server only).")`
     - Empty string → same "unsupported scheme" path; a blank endpoint must not pass.
  5. `@model_validator(mode="after")` — it needs both fields, so it cannot be a field validator. If `DATABASE_URL` starts with a `_REMOTE_SCHEMES` entry and `TURSO_AUTH_TOKEN.strip()` is empty → `ValueError("TURSO_AUTH_TOKEN is required when DATABASE_URL names a remote endpoint (libsql:// or https://). The local libSQL dev server on http:// takes no token.")` Return `self`.
  6. Import `field_validator, model_validator` from `pydantic` (2.13.4 — confirmed present).
- **Mirror**: `app/config.py:14-19` for the group comment; `app/services/authz.py:92-95,119-123` for message shape.
- **Watch for**: `"https://".startswith("http://")` is `False`, so check ordering is not a trap — but assert it in Task 3 anyway, because a future reader will assume otherwise.
- **Validate**:
  ```bash
  python -c "from app.config import Settings; s=Settings(_env_file=None, OPENROUTER_API_KEY='k', ADMIN_TOKEN='t', DATABASE_URL='http://127.0.0.1:8080'); print(s.DATABASE_URL, repr(s.TURSO_AUTH_TOKEN))"
  ```
  prints the endpoint and `''`.

### Task 2: Document both settings in `.env.example`

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: Replace lines 4-5 (`# SQLite connection string for the audit_logs database` / `DATABASE_URL=sqlite:///harness_ai.db`) with an endpoint-shaped entry, and add `TURSO_AUTH_TOKEN` **immediately after it** — `tests/test_config.py:70-77` asserts `.env.example` order matches `Settings` field order, so the file order must follow Task 1's declaration order:
  ```
  # libSQL endpoint for the audit_logs and users database (required, no default).
  # A sqlite:/// value is a startup error -- PRD-007 removed the file fallback.
  # Local dev server: http://127.0.0.1:8080
  DATABASE_URL=libsql://your-database-your-org.turso.io

  # Bearer token for the Turso database (required for libsql:// and https://
  # endpoints; leave empty for the local http:// dev server, which takes no token)
  TURSO_AUTH_TOKEN=
  ```
- **Mirror**: every existing entry in `.env.example` — one or more `#` comment lines directly above `VAR=`, no blank line between them. Task 3's regex `(?m)^#.+\n{var}=` depends on the comment line being the one **immediately** above.
- **Never**: put a real token value here. The file is committed.
- **Validate**: `grep -n -A1 "^DATABASE_URL\|^TURSO_AUTH_TOKEN" .env.example`

### Task 3: Cover AC 7's five cases in `tests/test_config.py`

- **File**: `tests/test_config.py`
- **Action**: UPDATE
- **Implement**: Add a `# --- PRD-007 STORY-005: DATABASE_URL semantics and TURSO_AUTH_TOKEN ---` section, keeping the existing RBAC sections untouched. Add `from pydantic import ValidationError` alongside the existing imports (mirroring `tests/test_schemas.py:2`). Use `Settings(_env_file=None, …)` with explicit kwargs throughout — never `os.environ` — so no test depends on the shell it runs in. A small local helper keeps the cases readable:
  ```python
  def _settings(**overrides):
      base = {"OPENROUTER_API_KEY": "k", "ADMIN_TOKEN": "t"}
      return Settings(_env_file=None, **{**base, **overrides})
  ```
  Cases, one test each (AC 7 lists five; the rest are AC 4/5/6 and the scheme table):

  | # | Test | Asserts |
  |---|------|---------|
  | 1 | remote `libsql://…` with `TURSO_AUTH_TOKEN=""` | `pytest.raises(ValidationError)`; `"TURSO_AUTH_TOKEN" in str(exc.value)` |
  | 1b | remote `https://…` with empty token | same — both remote schemes, not just one |
  | 2 | `http://127.0.0.1:8080` with no token | **constructs**; `TURSO_AUTH_TOKEN == ""` |
  | 3 | `DATABASE_URL="sqlite:///harness_ai.db"` | raises; message contains `"libsql://"` — the replacement form is named (AC 4) |
  | 3b | `sqlite:///:memory:` and `sqlite:////app/data/harness_ai.db` | both raise — parametrized; these are the literal Dockerfile and compose values |
  | 4 | `DATABASE_URL` omitted entirely | raises; `"DATABASE_URL"` in the message. Also assert `Settings.model_fields["DATABASE_URL"].is_required()` — pin that the default is *removed*, not replaced (AC 5) |
  | 5 | valid remote pair (`libsql://…` + token) | constructs; both values round-trip |
  | 6 | token never echoed | for each failing case, pass `TURSO_AUTH_TOKEN="s3cr3t-sentinel"` and assert `"s3cr3t-sentinel" not in str(exc.value)`. Cover the *scheme* failure too: `_settings(DATABASE_URL="sqlite:///x.db", TURSO_AUTH_TOKEN="s3cr3t-sentinel")` (AC 6) |
  | 7 | unsupported scheme | `postgres://…` raises and the message names the accepted schemes |
  | 8 | `.env.example` | extend the existing comment/order assertions to `DATABASE_URL` and `TURSO_AUTH_TOKEN` — mirror `test_env_example_documents_every_new_rbac_var_with_a_comment` in shape |
- **Mirror**: `tests/test_config.py:45-56` (construction), `tests/test_authz.py:170-174` (assert on message text), `tests/test_config.py:62-77` (`.env.example`).
- **Note**: `pytest.raises(ValidationError)` — pydantic wraps the `ValueError` a validator raises. Assert on `str(exc.value)`, which includes the original message.
- **Validate**: `pytest tests/test_config.py -q`

### Task 4: Give the suite a `DATABASE_URL` before anything imports `app.config`

- **File**: `tests/conftest.py`
- **Action**: UPDATE
- **Implement**: `DATABASE_URL` is now required at import, and **no test file supplies one** — the 21 prologues set only `OPENROUTER_API_KEY` and `ADMIN_TOKEN` (`tests/test_config.py:3-4` and 20 siblings) because the default covered it. `tests/conftest.py` is loaded before any test module, and it imports `app.config` itself at `:29`, so the bootstrap goes **above that import**:
  ```python
  import os

  # The endpoint every child process and every unpatched import validates
  # against. Nothing connects to it: it is the local dev-server URL from the
  # STORY-001 decision record, chosen because it satisfies STORY-005's
  # validator without a token.
  _PLACEHOLDER_URL = "http://127.0.0.1:8080"

  # DATABASE_URL lost its default in STORY-005 and app/config.py constructs
  # Settings() at import, so a value must exist before `from app.config import
  # settings` below -- CI supplies no .env. This is a *placeholder that
  # satisfies validation*, not the database any test reads: every fixture below
  # repoints settings.DATABASE_URL through monkeypatch, which bypasses
  # validators by design.
  os.environ.setdefault("DATABASE_URL", _PLACEHOLDER_URL)
  os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
  os.environ.setdefault("ADMIN_TOKEN", "test-token")
  ```
  Fold the two secret prologue lines in here too — they are already `setdefault` in 21 files, so this is additive and changes no existing behavior, but it makes CI's requirement legible in one place.
- **Mirror**: `tests/test_config.py:1-4` for the `setdefault` idiom; `tests/conftest.py:34-40` for the "one place a URL is spelled" comment style.
- **Do not**: change `_SQLITE_PREFIX`, `_url_for`, `_path_from_url`, or any fixture body. In-process tests keep their `sqlite:///{tmp_path}` URLs — `monkeypatch.setattr` does not validate, and STORY-006 owns the real swap.
- **Validate**: `pytest tests/test_config.py tests/test_db.py -q` collects and passes.

### Task 5: Mint the child-process preamble in `conftest.py`

- **File**: `tests/conftest.py`
- **Action**: UPDATE
- **Implement**: The three subprocess fixtures put a `sqlite:///` URL in the **child's** `DATABASE_URL`, where a genuine `Settings()` is constructed and the new validator does fire — `monkeypatch` cannot reach a subprocess. The children still need a real sqlite file until STORY-006, so the URL must arrive by a channel the validator does not police. Export from `conftest.py`, next to the existing seam comment:
  ```python
  #: Environment variable the child probes carry their real (still SQLite)
  #: database URL in. `DATABASE_URL` itself must satisfy STORY-005's validator
  #: at child startup, so the throwaway URL travels beside it and is assigned
  #: onto the constructed Settings -- the subprocess equivalent of the
  #: `monkeypatch.setattr` every in-process fixture does. STORY-006 deletes
  #: both this constant and the preamble: once the fixtures mint libSQL
  #: endpoints, DATABASE_URL carries them directly again.
  TEST_DATABASE_URL_ENV = "HARNESS_TEST_DATABASE_URL"

  CHILD_SETTINGS_PREAMBLE = f"""
  import os as _os
  from app.config import settings as _settings
  _settings.DATABASE_URL = _os.environ["{TEST_DATABASE_URL_ENV}"]
  """


  def child_db_env(url: str) -> dict[str, str]:
      """The two DATABASE_URL entries a probe subprocess needs."""
      return {"DATABASE_URL": _PLACEHOLDER_URL, TEST_DATABASE_URL_ENV: url}
  ```
  `child_db_env` is a plain module function, not a fixture — the three call sites are a mix of function- and module-scoped fixtures, and a helper sidesteps the `ScopeMismatch` that `tests/conftest.py:88-97` already documents.
- **Why the preamble runs first**: prepending it puts `from app.config import settings` ahead of every probe's own imports, including `chat_ui.chat_ui`, whose `init_db()` at import (`chat_ui/chat_ui/chat_ui.py:33`) is exactly what must see the temp database.
- **Validate**: `python -c "from tests.conftest import CHILD_SETTINGS_PREAMBLE, child_db_env; print(child_db_env('sqlite:///x.db'))"`

### Task 6: Apply the preamble at the three subprocess sites

- **Files**: `tests/test_admin_shell.py`, `tests/test_chat_ui_startup_guard.py`, `tests/test_render_invariants.py`
- **Action**: UPDATE
- **Implement**: In each file, `from tests.conftest import CHILD_SETTINGS_PREAMBLE, child_db_env` (`tests/__init__.py` exists, so `tests` is an importable package and `REPO_ROOT` is on `sys.path`), then:
  1. Prepend the preamble to the script string:
     - `tests/test_admin_shell.py:634` — `_PAGES_CHECK_SCRIPT = CHILD_SETTINGS_PREAMBLE + r"""…`
     - `tests/test_chat_ui_startup_guard.py:25` — `_CHECK_SCRIPT = CHILD_SETTINGS_PREAMBLE + r"""…`
     - `tests/test_render_invariants.py:155` — `_CHECK_SCRIPT = CHILD_SETTINGS_PREAMBLE + r"""…`
  2. Replace the `"DATABASE_URL": <url>` entry in each `env=` dict with `**child_db_env(<url>)`:
     - `tests/test_admin_shell.py:712` (`db_url`, from `database_url_factory("admin_pages")`)
     - `tests/test_chat_ui_startup_guard.py:64` (`env["DATABASE_URL"] = …` → `env.update(child_db_env(database_url_factory("chat_ui_guard")))`)
     - `tests/test_render_invariants.py:270` (`database_url_factory("render_probe")`)
  3. Leave every surrounding comment that explains *why* the URL is pinned (`test_admin_shell.py:691-698`, `test_render_invariants.py:163-166`) and extend it with one sentence on the two-variable split. Those comments are the reason the next reader will not undo this.
- **Do not** change `database_url_factory` or what it returns. The URLs stay `sqlite:///`; only the channel changes.
- **Validate**:
  ```bash
  pytest tests/test_admin_shell.py tests/test_chat_ui_startup_guard.py tests/test_render_invariants.py -q
  ```
  Each probe fixture `pytest.fail`s with the child's stderr on a non-zero exit, so a validator rejection in the child is loud, not silent.

### Task 7: Repair the assertion that compared against the removed default

- **File**: `tests/test_conftest_fixtures.py`
- **Action**: UPDATE
- **Implement**: `:57` reads `assert temp_db != Settings.model_fields["DATABASE_URL"].default`. With the default gone, `.default` is `PydanticUndefined` and the assertion passes vacuously — it can no longer fail, which voids the docstring's stated purpose ("a fixture that silently failed to patch would leave the developer's own configured database in place"). Replace with an assertion against the value the fixture protects *from* — the process-level configured URL:
  ```python
  assert temp_db != os.environ["DATABASE_URL"]
  assert Settings.model_fields["DATABASE_URL"].is_required()
  ```
  and update the docstring: the comparison is now against the environment's configured endpoint rather than a declared default, because STORY-005 removed the default rather than changing it. The second line pins the removal itself, so the intent survives.
- **Mirror**: the file's existing docstring-per-test style (`tests/test_conftest_fixtures.py:42-45,50-56`).
- **Validate**: `pytest tests/test_conftest_fixtures.py -q`

### Task 8: Full-suite verification and the two declared breakages

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**: Run the suite and compare against the baseline STORY-001 recorded — **1017 passed, 7 failed**, the 7 being `test_untouched_app.py`'s PRD-006 provenance guards plus one `test_chat_state.py` assertion, all pre-existing on `main`. This story must not add an eighth. Then confirm in writing, for the report:
  1. **`Dockerfile:17`** (`DATABASE_URL=sqlite:///:memory:`) now fails the build at `reflex export`. **STORY-014 owns this in writing** — its AC at line 34 says the placeholder "is replaced with a value that satisfies the configuration validation from STORY-005", and its Technical Note at line 45 assigns the `TURSO_AUTH_TOKEN` placeholder to the same block. STORY-014 `depends_on: [STORY-006, STORY-008, STORY-013]`, so the image build is **red from this commit until STORY-014**. The story's Technical Notes require this said out loud rather than fixed here; say it in the report, and do not touch the Dockerfile.
  2. **`docker-compose.yml:12`** (`DATABASE_URL: sqlite:////app/data/harness_ai.db`) is the same situation, also STORY-014's (its line 33).
  3. **Local dev environments** carrying `.env` / `chat_ui/.env` with `DATABASE_URL=sqlite:///harness_ai.db` (both gitignored, both present on this machine) will now fail to start. That is the story working as designed, but it needs a line in the report so the next person does not read it as a regression.
- **Validate**:
  ```bash
  pytest -q
  git diff --stat
  grep -rn "sqlite" app/config.py .env.example   # expect: only the rejection rule and its comment
  ```

---

## End-to-End Tests

- [ ] `DATABASE_URL=libsql://db-org.turso.io` with `TURSO_AUTH_TOKEN` unset → `import app.config` exits non-zero, message names `TURSO_AUTH_TOKEN`, contains no token value
- [ ] `DATABASE_URL=http://127.0.0.1:8080`, no token → imports cleanly
- [ ] `DATABASE_URL=sqlite:///harness_ai.db` → exits non-zero, message names `libsql://` as the replacement
- [ ] `DATABASE_URL` unset and no `.env` present → exits non-zero as a missing required field
- [ ] `pytest -q` → 1017 passed / 7 failed, matching the STORY-001 baseline exactly; no new failure
- [ ] `pytest tests/test_admin_shell.py tests/test_chat_ui_startup_guard.py tests/test_render_invariants.py -q` → all three subprocess probes still start their children and return JSON
- [ ] `git grep -n "sqlite" -- app/` → `app/db/database.py` only; `app/config.py` mentions the scheme solely to reject it

## Validation

```bash
pytest tests/test_config.py -q
pytest tests/test_conftest_fixtures.py -q
pytest tests/test_admin_shell.py tests/test_chat_ui_startup_guard.py tests/test_render_invariants.py -q
pytest -q
```

## Risks + Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| 1 | **The suite cannot collect.** `DATABASE_URL` is required at import and no test supplies one; CI has no `.env`. A green local run hides this entirely, because the developer's gitignored `.env` supplies the value. | Task 4 puts the bootstrap in `conftest.py`, above its own `app.config` import. Verify the way CI sees it: `pytest -q` with `DATABASE_URL` unset and `.env` temporarily renamed. |
| 2 | **The three child probes fail in a way that looks like an unrelated bug.** A child that dies during `import app.config` prints a pydantic traceback, surfaced through `pytest.fail`, but it reads as a chat-UI problem. | Tasks 5-6 fix it at the source, and the preamble comment names STORY-005 and STORY-006 so the next reader knows what it is and when it goes away. |
| 3 | **The token leaks into an error message.** AC 6 is explicit, and the natural instinct — mirroring `database.py:25` — echoes the whole URL, which may carry `?authToken=`. | `_scheme_of()` in Task 1: messages quote the scheme, never the URL. Task 3 case 6 asserts a sentinel token is absent from every failure message, including the scheme failure. |
| 4 | **Docker build red until STORY-014.** | Accepted and pre-assigned: STORY-014's AC (line 34) and Technical Note (line 45) both name it. Task 8 requires it in the report; the story's Technical Notes demand exactly this. |
| 5 | **`monkeypatch.setattr` bypassing validators reads as a loophole** and gets "fixed" later into `Settings(...)` reconstruction, which would then reject every `sqlite:///` fixture URL and turn the suite red. | Stated in Task 4's comment as deliberate, with the reason. It is also temporary by construction: STORY-006 replaces the minted URLs with libSQL endpoints that validate cleanly. |
| 6 | **`.env.example` order test breaks silently.** `tests/test_config.py:70-77` compares `.env.example` order to a hardcoded list, so adding vars in the wrong order fails a test that looks unrelated. | Task 2 fixes the order explicitly against Task 1's declaration order, and Task 3 case 8 extends the assertion to the two new vars. |
| 7 | **`http://` accepted for a production host.** The local-only intent is documented, not enforced — `http://prod.example.com` passes. | Out of scope by AC: the criteria distinguish schemes, not hosts. Note it in the report as a known gap for STORY-008's startup guard, where a reachability probe would naturally live. |

## Acceptance Criteria

(Copied from story `STORY-005`)

- [ ] Given `app/config.py`, when it is read, then `TURSO_AUTH_TOKEN` is declared alongside `OPENROUTER_API_KEY` and `ADMIN_TOKEN`, loaded through the same pydantic-settings `.env` mechanism.
- [ ] Given a remote endpoint (`libsql://` or `https://`), when `TURSO_AUTH_TOKEN` is empty, then configuration validation fails with a message naming the setting.
- [ ] Given a local dev-server endpoint (`http://`), when `TURSO_AUTH_TOKEN` is empty, then that is accepted.
- [ ] Given `DATABASE_URL` set to any `sqlite:///` value, when configuration is validated, then it raises an error whose message names the correct replacement form. It must never fall back to opening a file, and never be silently ignored.
- [ ] Given `DATABASE_URL` unset, when configuration is validated, then it fails as a required setting. The `sqlite:///harness_ai.db` default is removed, not replaced with another default.
- [ ] Given a validation failure for either setting, when the message is inspected, then it does not contain the token value.
- [ ] Given `tests/test_config.py`, when it runs, then it covers: remote URL without token (fail), local URL without token (pass), `sqlite:///` URL (fail, message names the replacement), unset URL (fail), and a valid remote pair (pass).
- [ ] All tasks completed
- [ ] `pytest -q` matches the STORY-001 baseline (1017 passed, 7 pre-existing failures) with no new failure
- [ ] `app/db/database.py` is unmodified — `_db_path()` and `_SQLITE_PREFIX` are STORY-006's to delete
- [ ] The Dockerfile / compose breakage is stated in the report and left to STORY-014
- [ ] Follows existing patterns
