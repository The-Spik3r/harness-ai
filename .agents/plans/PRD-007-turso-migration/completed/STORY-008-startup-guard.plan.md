---
story: STORY-008
prd: PRD-007
slug: startup-guard
title: "Fail fast and legibly when the database is unreachable or the token is missing"
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-01
---

# Plan: Fail fast and legibly when the database is unreachable or the token is missing

## Summary

`_shared_client()` is lazy (STORY-006 report, handoff note for this story): importing `app.db.database` connects to nothing, so today an unreachable endpoint or a rejected token surfaces as whatever the driver says at the first statement — `ValueError: Hrana: http error: ... Connection refused` — translated by `_translated()` into a bare `StorageError` whose text is the driver's, which quotes the endpoint as the driver formats it and names neither `DATABASE_URL` nor `TURSO_AUTH_TOKEN`. This story adds one deliberate reachability probe, `check_database_reachable()`, and calls it from the **top of `init_db()`** — the single point both entry points already pass through (`app/main.py`'s lifespan, `chat_ui/chat_ui/chat_ui.py`'s import-time call), so no call site changes and both paths fail with identical clarity. The probe issues exactly one `SELECT 1`, classifies the failure into unreachable-endpoint vs credential-rejected, and raises a message that names the responsible setting while quoting only a sanitized endpoint — scheme and host, never a query string, never the token. A `DB_BOOTSTRAP_ENABLED` setting (default `True`) is added so the Dockerfile builder stage can import `chat_ui.chat_ui` for `reflex export` without a live database; **this story provides the switch, STORY-014 sets it**, and the report must say so.

## User Story

As a platform engineer
I want the application to exit immediately with a legible message when it cannot reach the database
So that a misconfigured deployment never serves traffic while silently dropping audit rows

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-008-startup-guard.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md` — Section 5 story 3, 7.7, 9, 10, 11, 12 Phase 2, 14 Risk 5

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | `app/db/` (guard + error surface), `app/config.py` (one flag), tests |
| Story | STORY-008 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` was listed and read in full: it contains only `frontend-design`, whose `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story renders no UI and touches no component, so no skill constrains it. The story's own frontmatter agrees (`skills: []`). | none |

---

## Patterns to Follow

### Naming — module-owned exceptions, all rooted at `StorageError`

```python
# SOURCE: app/db/errors.py:19-31, 46-63
class StorageError(Exception):
    """A storage operation failed. ...
    It is the base of the other two on purpose. It stands in for `sqlite3.Error`...
    """


class MissingRelationError(StorageError):
    def __init__(self, relation: str, message: str) -> None:
        self.relation = relation
        super().__init__(message)
```

New guard exceptions follow this exactly: subclass `StorageError`, carry one structured attribute plus a message, document *who catches it and why*.

### Error classification — match the driver's message text, never its type or code

```python
# SOURCE: app/db/database.py:271-289 (_translated)
    except ValueError as exc:
        message = str(exc)
        if _DRIVER_ERROR not in message:
            raise
        constraint = _constraint_of(exc)
        if constraint is not None:
            raise IntegrityError(constraint, message) from exc
```

libSQL raises a bare `builtins.ValueError` for every failure and `Hrana:` is the only reliable driver marker — the unreachable case carries **no `code:` field at all** (STORY-006 report, error-surface table). The guard's classifier is written against message text for the same reason and lives beside `_translated()`.

### Credential hygiene — quote a sanitized fragment, never the raw URL

```python
# SOURCE: app/config.py:18-29
def _scheme_of(url: str) -> str:
    """The scheme part of a URL, and the only part of one any message quotes.

    A libSQL endpoint may carry `?authToken=...`, and PRD-007 Section 9 requires
    the credential to be "never logged, never echoed in error messages". Quoting
    the scheme alone makes that structural rather than something every `raise`
    below has to remember.
    """
```

`app/db/`'s guard needs more than the scheme — AC 1 wants the endpoint identified — so it quotes `scheme://host[:port]` and drops userinfo, query and fragment. Same principle, one segment wider.

### Tests — a credential sentinel asserted absent from the message

```python
# SOURCE: tests/test_config.py:170-176
def test_no_failure_message_ever_echoes_the_token(url):
    """AC 6: the credential is "never echoed in error messages" (PRD Section 9)."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=url, TURSO_AUTH_TOKEN=_TOKEN_SENTINEL)

    assert _TOKEN_SENTINEL not in str(exc_info.value)
```

### Tests — the subprocess probe this story must extend, not reinvent

```python
# SOURCE: tests/test_chat_ui_startup_guard.py:31-65
_CHECK_SCRIPT = r"""
import json, sys
result = {"errors": []}
try:
    import chat_ui.chat_ui as chat_ui_module
except Exception as exc:
    print(json.dumps({"errors": ["import: {}: {}".format(type(exc).__name__, exc)]}))
    sys.exit(0)
...
"""

def _run_probe(env):
    proc = subprocess.run([sys.executable, "-c", _CHECK_SCRIPT], cwd=str(REPO_ROOT / "chat_ui"),
                          env=env, capture_output=True, text=True)
```

Note the existing script **swallows the import failure into `errors`** and exits 0. The new unreachable-database case wants the opposite — a non-zero exit with the message on stderr — so it needs its own small script beside `_CHECK_SCRIPT`, run through a `_run_failing_probe()` helper in the same subprocess style, with the same `_PYTHONPATH` / `child_db_env` construction.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/errors.py` | UPDATE | Add `DatabaseUnreachableError` and `DatabaseAuthError`, both `StorageError` subclasses |
| `app/db/database.py` | UPDATE | Add `_safe_endpoint()`, `_redacted()`, `_classify_startup_failure()`, `check_database_reachable()`; call it from `init_db()` behind `settings.DB_BOOTSTRAP_ENABLED` |
| `app/config.py` | UPDATE | Add `DB_BOOTSTRAP_ENABLED: bool = True` |
| `.env.example` | UPDATE | Document the new flag as build-time-only |
| `tests/test_db.py` | UPDATE | Unit coverage: classification, sanitization, one round trip, no re-fire, bootstrap flag |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | AC 6: unreachable database at Reflex import, in the existing subprocess style |
| `tests/test_main.py` | UPDATE | AC 4: the FastAPI lifespan fails with the same error, not per-request |
| `tests/test_config.py` | UPDATE | The new setting defaults to `True` and is opt-in to disable |

No changes to `app/main.py` or `chat_ui/chat_ui/chat_ui.py`: both already call `init_db()`, which is where the guard is installed. That is the design, not an omission — see Risk 2.

---

## Design decisions worth stating before the tasks

**1. The guard lives inside `init_db()`, not in each entry point.** Three consumers reach the database at boot — `app/main.py:13` (lifespan), `chat_ui/chat_ui/chat_ui.py:33` (import time), `scripts/manage_users.py:32,50,57,66` (CLI) — and all three funnel through `init_db()`. Installing the probe at its top gives AC 4's "both are covered" for free and makes it impossible for a fourth entry point to be added without the guard. The alternative — a `check_database_reachable()` that each caller must remember to call — is the shape that produces exactly the silent gap this story exists to close.

**2. One `SELECT 1`, and it is the only added round trip (AC 5).** `init_db()` already issues DDL immediately afterwards, so on a healthy database the guard costs one extra statement against an already-open client and nothing else — no retries, no backoff, no second client (a second client is the pattern STORY-006 measured losing 169 of 200 writes to `TRANSACTION_TIMEOUT`). The probe reuses `_shared_client()` through `get_connection()`.

**3. The guard does not re-fire (AC 7).** It runs only from `init_db()`, and nothing calls `init_db()` per-request. Liveness is explicitly out of MVP scope (PRD Section 4, Section 13). This is asserted, not merely stated in prose — see Task 7, test 8.

**4. The credential-rejected branch is classified by message text and tested at unit level, not against a live Turso.** The unreachable message is documented evidence (STORY-006 report: `http error: ... Connection refused`, no `code:` field). A 401 from Turso is **not** — the suite runs against a local libSQL primary that takes no token and cannot produce one, and PRD Section 12's non-negotiable is that tests need no account. So the classifier recognizes auth markers in the message (`401`, `unauthorized`, `authentication`, `auth token`, `invalid token`), tested by feeding those strings to the classifier directly, and any unrecognized driver failure falls back to the unreachable message. That fallback direction is deliberate: mislabeling a bad token as unreachable sends an operator to check the endpoint and then the token; mislabeling an outage as a bad token sends them to rotate a credential that was fine.

**5. `DB_BOOTSTRAP_ENABLED` is provided here and consumed by STORY-014.** The Docker builder stage runs `reflex export`, which imports `chat_ui.chat_ui`, which calls `init_db()` — so the build already required a reachable database the moment STORY-006 landed, before this story. The guard does not create that constraint, but it does make it permanent and legible, so the switch belongs here and the flag's only sanctioned use is the Dockerfile's build-time placeholder block (which STORY-014 already owns, along with replacing `DATABASE_URL=sqlite:///:memory:` at `Dockerfile:17`). Default `True`; a deployment that sets it `False` boots without schema and fails on first use — documented in the flag's own comment and in the report.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add the two guard exceptions

- **File**: `app/db/errors.py`
- **Action**: UPDATE
- **Implement**: Add `DatabaseUnreachableError(StorageError)` and `DatabaseAuthError(StorageError)`. Both take `(endpoint: str, message: str)` and set `self.endpoint`, mirroring `MissingRelationError.__init__`'s `(relation, message)` shape. Docstrings state: raised only by `check_database_reachable()` at boot; both subclass `StorageError` so `app/services/duplicate_checker.py:31-33`'s degradation arm keeps its `sqlite3.Error`-equivalent breadth; the `endpoint` attribute is **already sanitized** by the raiser, so a caller may print it. Import nothing driver-shaped — the module header at `app/db/errors.py:9-13` says it deliberately imports no driver, and that stays true.
- **Mirror**: `app/db/errors.py:33-63` (`MissingRelationError`)
- **Validate**: `python -c "from app.db.errors import DatabaseUnreachableError, DatabaseAuthError, StorageError; assert issubclass(DatabaseUnreachableError, StorageError)"`

### Task 2: Sanitizers — `_safe_endpoint()` and `_redacted()`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Two module-private helpers placed beside `_translated()`, after the regex/evidence block.
  - `_safe_endpoint(url: str) -> str` — returns `scheme://host[:port]`, dropping any `user:pass@` userinfo, path, query and fragment. `urllib.parse.urlsplit` is enough; on any parse failure return the scheme alone rather than the raw URL. Never return the input unchanged when it contains `?` or `@`.
  - `_redacted(message: str) -> str` — removes the credential from driver text before it is embedded in a raised message: replace any `authToken=<value>` / `auth_token=<value>` run with `authToken=***`, and, when `settings.TURSO_AUTH_TOKEN` is non-empty, replace that literal value with `***`. Belt and braces on purpose: the driver's `http error:` text formats the endpoint itself, and the endpoint may carry the token in its query string (`tests/test_config.py:178-192` is the precedent for treating that as a real case, not a hypothetical).
- **Mirror**: `app/config.py:18-29` (`_scheme_of`) for rationale and comment style; `app/db/database.py:238-252` for where message-shaped constants live.
- **Validate**: `pytest tests/test_db.py -q -k "safe_endpoint or redacted"`

### Task 3: The classifier

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: A module-level marker tuple and `_classify_startup_failure(exc: Exception, endpoint: str) -> StorageError`. Comment it with the evidence, in the style of the `_MISSING_RELATION` block at `app/db/database.py:229-252`: unreachable is `Hrana: http error: ... Connection refused` **with no `code:` field** (STORY-006 report error-surface table); the auth case is not reproducible against the local dev server and is therefore matched on markers, listed in the comment as unverified-against-Turso with a pointer to STORY-014's first real deployment as the place to confirm.
  - Auth markers (case-insensitive, on `str(exc)`): `401`, `unauthorized`, `authentication`, `auth token`, `auth_token`, `invalid token`, `expired token`.
  - Auth match → `DatabaseAuthError(endpoint, ...)` whose message names the setting: `"TURSO_AUTH_TOKEN was rejected by the database at {endpoint}. The endpoint answered; the credential did not authenticate. Check that TURSO_AUTH_TOKEN matches the database named by DATABASE_URL and has not expired."` plus `_redacted(str(exc))` as the driver detail.
  - Anything else → `DatabaseUnreachableError(endpoint, ...)`: `"Cannot reach the database at {endpoint}. The application will not start: PRD-007 removed the local-file fallback deliberately, so there is nothing to degrade to. Check DATABASE_URL and that the endpoint is reachable from this host."` plus the same redacted detail.
  - Neither message interpolates `settings.DATABASE_URL` or `settings.TURSO_AUTH_TOKEN` — only `endpoint`, which arrives from `_safe_endpoint()`.
- **Mirror**: `app/db/database.py:229-252` (evidence-in-comments), `app/config.py:66-84` (a message that names the fix, not just the fault)
- **Validate**: `pytest tests/test_db.py -q -k classify`

### Task 4: `check_database_reachable()` and its call from `init_db()`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  - `check_database_reachable() -> None` — public (the report and any future entry point may call it). Body: `_safe_endpoint(settings.DATABASE_URL)`, then one statement through the shared client — `get_connection().execute("SELECT 1").fetchone()` inside `try` — catching `Exception` and re-raising `_classify_startup_failure(exc, endpoint) from exc`. Deliberately **not** wrapped in `_translated()`: that helper exists to turn driver errors into the operational surface, and its `Hrana:`-prefix pass-through would let a non-driver failure escape unclassified, while the guard wants every boot-time failure classified. Do not open a transaction and do not commit — a read needs neither, and `_Connection.close()` is already a no-op by design (`app/db/database.py:196-204`).
  - `init_db()` gains two lines at the top:
    ```python
    def init_db() -> None:
        if not settings.DB_BOOTSTRAP_ENABLED:
            return
        check_database_reachable()
        with _session() as conn:
            ...
    ```
    with a docstring explaining both: the guard is here because `init_db()` is the one call every entry point already makes (`app/main.py:13`, `chat_ui/chat_ui/chat_ui.py:33`, `scripts/manage_users.py`), and the flag is the build-time escape hatch described in Task 5.
- **Mirror**: `app/db/database.py:309-314` (current `init_db()`), `app/db/database.py:214-222` (`get_connection()` docstring style)
- **Validate**: `pytest tests/test_db.py tests/test_conftest_fixtures.py -q` — the whole existing `init_db` suite must stay green; against a reachable database the guard adds a round trip, not a behavior change

### Task 5: The `DB_BOOTSTRAP_ENABLED` setting

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**: `DB_BOOTSTRAP_ENABLED: bool = True`, placed in the Turso block after `TURSO_AUTH_TOKEN` (`app/config.py:38-45`). Comment states: the only sanctioned `False` is the Dockerfile builder stage, where `reflex export` imports `chat_ui.chat_ui` and PRD Section 11 requires the build to succeed with no reachable database; setting it `False` in a running deployment boots an application that has never created its schema, which this flag deliberately does not defend against, because defending against it would mean probing the database — the very thing being skipped. Cross-reference STORY-014 as the consumer.
- **Mirror**: `app/config.py:38-45` (the Turso comment block)
- **Validate**: `pytest tests/test_config.py -q`

### Task 6: Document the flag in `.env.example`

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: Add `DB_BOOTSTRAP_ENABLED` with its default and a one-line "build-time only; leave unset in any deployment" note, matching the file's existing comment style for `DATABASE_URL` / `TURSO_AUTH_TOKEN`. Ship no value that disables it.
- **Mirror**: the existing `DATABASE_URL` / `TURSO_AUTH_TOKEN` entries in `.env.example`
- **Validate**: `pytest tests/test_config.py -q -k env_example`

### Task 7: Unit coverage in `tests/test_db.py`

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: Add a `STORY-008` section at the end, following the file's plain `def test_...(fixture)` style and its existing `monkeypatch.setattr(settings, ...)` usage:
  1. `test_safe_endpoint_drops_query_userinfo_and_path` — parametrized over `libsql://db-org.turso.io?authToken=<SENTINEL>`, `https://user:pw@db-org.turso.io/x`, `http://127.0.0.1:8080`; asserts the sentinel and `@` are gone and the host survives.
  2. `test_redacted_removes_a_token_carried_in_driver_text` — with `settings.TURSO_AUTH_TOKEN` monkeypatched to a sentinel, both the query-string form and the bare value are replaced.
  3. `test_classify_names_the_token_setting_for_an_auth_failure` — parametrized over the auth markers; asserts `DatabaseAuthError` and `"TURSO_AUTH_TOKEN"` in the message.
  4. `test_classify_falls_back_to_unreachable` — the verbatim STORY-006 unreachable text plus one unrecognized message; asserts `DatabaseUnreachableError`, `"DATABASE_URL"` in the message, and the sanitized endpoint present.
  5. `test_no_guard_message_ever_echoes_the_token` — AC 3, the direct analogue of `tests/test_config.py:170-176`: sentinel token in the setting, in the URL's query string, and in the driver text; sentinel absent from `str(exc)` for both branches.
  6. `test_init_db_fails_fast_against_an_unreachable_endpoint` — `monkeypatch.setattr(settings, "DATABASE_URL", "http://127.0.0.1:1")` (a closed loopback port: no DNS, no network wait) and assert `pytest.raises(DatabaseUnreachableError)`. **Reset `database._client` / `database._client_key` in teardown** so the repointed client cannot leak into the next test — `_shared_client()` keys on `(URL, token)` and rebuilds on change (`app/db/database.py:47-56`), but leave nothing to chance.
  7. `test_guard_issues_exactly_one_extra_statement` — AC 5: count `_Connection.execute` calls via `monkeypatch`, call `check_database_reachable()`, assert one.
  8. `test_guard_does_not_run_outside_init_db` — AC 7: after a successful `init_db()`, monkeypatch `check_database_reachable` to raise, then exercise a normal read and write (`count_audit_logs()`, `insert_audit_log(...)`) and assert both succeed — proving no per-operation liveness check crept in.
  9. `test_bootstrap_disabled_skips_the_guard_and_the_schema` — with `DB_BOOTSTRAP_ENABLED=False` and an unreachable URL, `init_db()` returns cleanly and creates nothing.
- **Mirror**: `tests/test_db.py:42-50` (fixture-driven `init_db` tests), `tests/test_db.py:102-180` (`test_init_db_issues_no_alter_when_schema_is_current`'s statement-counting instrumentation — reuse it for test 7 rather than inventing another)
- **Validate**: `pytest tests/test_db.py -q`

### Task 8: The Reflex import path, in the existing subprocess style (AC 6)

- **File**: `tests/test_chat_ui_startup_guard.py`
- **Action**: UPDATE
- **Implement**: Add a second probe script `_UNREACHABLE_SCRIPT` that does `import chat_ui.chat_ui` with no `try` — the point is that the import *fails* — and a `_run_failing_probe(env)` helper asserting `proc.returncode != 0` and returning `proc.stderr`. Add a fixture `_unreachable_db_env` built exactly like `_empty_rbac_env` (`tests/test_chat_ui_startup_guard.py:68-77`) but with `child_db_env("http://127.0.0.1:1")` and a sentinel `TURSO_AUTH_TOKEN`. Then:
  - `test_chat_ui_import_fails_when_the_database_is_unreachable` — non-zero exit; `DatabaseUnreachableError` and `DATABASE_URL` in stderr.
  - `test_chat_ui_failure_names_the_endpoint_not_the_credential` — `127.0.0.1:1` present, sentinel absent (AC 3 on the real end-to-end path, where an operator sees a whole traceback, not just the message).
  - Extend the module docstring to record that the file now covers two guards: PRD-005's bootstrap guard and PRD-007's reachability guard.
  The constraint that shapes this: `http://127.0.0.1:1` must pass `Settings` validation in the child (it does — `http://` is the permitted local-dev scheme, `app/config.py:80-83`) so the failure under test is the *guard*, not STORY-005's validator. Assert that distinction explicitly by checking the exception name in stderr.
- **Mirror**: `tests/test_chat_ui_startup_guard.py:31-77` — same `_PYTHONPATH`, same `cwd=REPO_ROOT / "chat_ui"`, same `child_db_env` helper
- **Validate**: `pytest tests/test_chat_ui_startup_guard.py -q`

### Task 9: The FastAPI path fails at startup, not per-request (AC 4)

- **File**: `tests/test_main.py`
- **Action**: UPDATE
- **Implement**: `test_lifespan_fails_when_the_database_is_unreachable` — monkeypatch `settings.DATABASE_URL` to `http://127.0.0.1:1`, then `with pytest.raises(DatabaseUnreachableError): with TestClient(app): pass`. This asserts the failure happens in the lifespan (`app/main.py:11-16`) rather than on the first `POST /query`; say so in a comment, since a reader could otherwise mistake it for a duplicate of Task 7's test 6. Reset the shared client afterwards, as in Task 7.
- **Mirror**: `tests/test_main.py:17` (`TestClient(app)`) and `tests/test_main.py:27-40` (the `monkeypatch`-on-`settings` fixture style)
- **Validate**: `pytest tests/test_main.py -q`

### Task 10: Config coverage for the new flag

- **File**: `tests/test_config.py`
- **Action**: UPDATE
- **Implement**: `test_db_bootstrap_enabled_defaults_to_true` — a constructed `Settings` has it `True`, and `"false"` in the environment turns it off (pydantic's bool coercion), pinning that the escape hatch is opt-in.
- **Mirror**: `tests/test_config.py:101-118` (`_settings(...)` helper usage)
- **Validate**: `pytest tests/test_config.py -q`

### Task 11: Full-suite regression and the STORY-014 handoff

- **File**: — (verification + report)
- **Action**: —
- **Implement**: Run the full suite and diff the failure set against the committed tree's known 16 pre-existing failures (STORY-006 report, Validation Results). Then record in the story report, explicitly, the answer the story asks for: **the Docker build constraint is resolved here by `DB_BOOTSTRAP_ENABLED` and set by STORY-014**, whose AC already owns the `DATABASE_URL=sqlite:///:memory:` placeholder at `Dockerfile:17`; note that the builder stage must set `DB_BOOTSTRAP_ENABLED=false` alongside the replaced placeholder, and that the build already required a reachable database from STORY-006 onward, so this story does not introduce the constraint. Also record that the credential-rejected branch is classified from message markers that are **unverified against a live Turso 401**, to be confirmed at STORY-014's first real deployment.
- **Validate**: `pytest -q` (failure set identical to the committed tree's) and `grep -rn "sqlite3" app/ chat_ui/ scripts/` still empty

---

## End-to-End Tests

- [ ] `DATABASE_URL=http://127.0.0.1:1 python -c "from app.db.database import init_db; init_db()"` → non-zero exit, `DatabaseUnreachableError`, message names `DATABASE_URL`, no token anywhere in the traceback
- [ ] `DATABASE_URL=http://127.0.0.1:1 uvicorn app.main:app` → exits during startup ("Application startup failed"), never binds, never serves a request
- [ ] `DATABASE_URL=http://127.0.0.1:1 PYTHONPATH=chat_ui:. python -c "import chat_ui.chat_ui"` → traceback at import, same error class
- [ ] Against the running local libSQL server: `uvicorn app.main:app` starts normally, `GET /health` returns 200, startup not perceptibly slower than before the guard
- [ ] `DB_BOOTSTRAP_ENABLED=false DATABASE_URL=http://127.0.0.1:1 python -c "import chat_ui.chat_ui"` → imports cleanly, which is the `reflex export` case STORY-014 depends on
- [ ] With the endpoint reachable at boot, stop the libSQL server and issue `POST /query` → the request fails on its own terms (the `duplicate_checker` degradation at `app/services/duplicate_checker.py:31-33` still applies) and the guard does not re-fire (AC 7)

## Validation

```bash
pytest tests/test_db.py tests/test_config.py tests/test_main.py tests/test_chat_ui_startup_guard.py -q
pytest -q
python -c "from app.main import app"
grep -rn "sqlite3" app/ chat_ui/ scripts/
```

---

## Risks + mitigations

**Risk 1 — The auth-failure message is inference, not evidence.** The suite runs against a local libSQL primary that ignores tokens, so no test can produce a real Turso 401; the marker list is a guess.
> *Mitigation:* the fallback direction is unreachable-not-auth (Task 3), so a missed marker degrades to a still-legible message rather than a wrong accusation; the classifier is unit-testable without a network; the gap is written into the code comment and the report, and confirmed at STORY-014's first live deployment.

**Risk 2 — The guard is one call site, so a future entry point that skips `init_db()` skips the guard.** Today all three entry points call it.
> *Mitigation:* this is precisely why the guard sits inside `init_db()` rather than beside it — the trap is a call site *added* elsewhere, not one forgotten. `check_database_reachable()` is public so such a caller has the piece to reuse, and Task 4's docstring says where the guard lives and why.

**Risk 3 — `http://127.0.0.1:1` may behave differently across platforms.** Windows can take longer to refuse a connection on a closed loopback port than Linux, and libSQL's five-second `connect` timeout default (STORY-006 report) is the outer bound.
> *Mitigation:* loopback with no DNS lookup keeps the worst case at that five-second fuse, across three tests. If CI wall-clock proves otherwise, the fix is a shorter driver timeout for the probe, not a mocked driver — a mocked probe would stop testing the thing the story is about.

**Risk 4 — `DB_BOOTSTRAP_ENABLED` is a foot-gun in production.** Set `False` in a deployment, and the application boots with no schema and no guard.
> *Mitigation:* default `True`; documented as build-time-only in `app/config.py`, `.env.example` and the report; STORY-014 sets it in the builder stage only, where none of that stage's `ENV` values reach the final image (`Dockerfile:11-17`). Accepted deliberately as the cost of PRD Section 11's build-without-a-database requirement.

**Risk 5 — The shared client caches an unreachable endpoint into a later test.** `_shared_client()` keys on `(URL, token)` and rebuilds on change, but these tests deliberately repoint `settings.DATABASE_URL`.
> *Mitigation:* an explicit reset of `database._client` / `database._client_key` in the teardown of every test that repoints the URL (Tasks 7 and 9), plus a determinism check in Task 11 — five consecutive full runs, as STORY-006 did.

---

## Acceptance Criteria

(Copied from story `STORY-008`)

- [ ] Given an unreachable `DATABASE_URL`, when the application starts, then it fails at startup with a message identifying the database as the cause. It does not start and then fail per-request.
- [ ] Given an invalid or expired `TURSO_AUTH_TOKEN`, when the application starts, then it fails at startup with a message naming the setting.
- [ ] Given any startup failure message, when it is inspected, then it contains no token value or credential fragment.
- [ ] Given the FastAPI app and the Reflex app, when each is started independently, then both are covered.
- [ ] Given a reachable database, when the application starts, then the guard adds no perceptible startup delay and issues at most one extra round trip.
- [ ] Given `tests/test_chat_ui_startup_guard.py`, when it runs, then it covers the unreachable-database case in the same subprocess style it already uses for its existing guard scenarios.
- [ ] Given the guard, when the database becomes unreachable **after** a successful start, then the guard does not re-fire.
- [ ] All tasks completed
- [ ] Backend imports and starts without error against a reachable database
- [ ] Full suite failure set identical to the committed tree's
- [ ] Follows existing patterns
