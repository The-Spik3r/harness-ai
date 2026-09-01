---
story: STORY-007
prd: PRD-005
slug: roles-file-override
title: "Role matrix loaded from RBAC_ROLES_FILE at startup"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-005-rbac
created: 2026-08-28
---

# Plan: Role matrix loaded from RBAC_ROLES_FILE at startup

## Summary

Extend `app/services/authz.py` (STORY-006) with a `load()` function that, when `RBAC_ROLES_FILE` is set, reads that path as JSON at startup and **wholesale-replaces** the module's `ROLE_PERMISSIONS` dict — no merge, so any permission the file omits is denied. An empty `RBAC_ROLES_FILE` (the default) is a no-op: no file is touched and the built-in matrix from STORY-006 stands. A missing file, unreadable file, malformed JSON, or a JSON matrix that grants a permission name outside the five module constants all fail startup loudly, naming the file and the specific problem — never a silent fallback to the built-in matrix. `load()` is wired into both places PRD-002/PRD-003 already learned the hard way that a plain FastAPI `lifespan` isn't enough: `app/main.py`'s `lifespan` (next to `pii_redactor.load()`) and `chat_ui/chat_ui/chat_ui.py` via `app.register_lifespan_task(...)`, since Reflex's `api_transformer` mounts `fastapi_app` under an outer Starlette app whose own lifespan runs instead, and skipping the chat_ui registration would leave the chat UI enforcing a different (built-in) matrix than the API.

## User Story

As an operator
I want the role matrix overridable by a versioned JSON file
So that permissions are per-deployment configuration rather than a code change

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-007-roles-file-override.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | Backend authorization service (`app/services/authz.py`), FastAPI app startup (`app/main.py`), Reflex chat UI startup (`chat_ui/chat_ui/chat_ui.py`), backend test suite (`tests/`) |
| Story | STORY-007 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/frontend-design/SKILL.md` was checked and does not apply — this story touches Reflex only to register a zero-arg startup task (one line in `chat_ui.py`), not any UI/component surface.

---

## Patterns to Follow

### Startup-loaded configuration — the exact PRD-002/PRD-003 dual-registration trap

```python
// SOURCE: app/main.py:1-18 (current, pre-STORY-007)
from app.db.database import init_db
from app.services import pii_redactor

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    pii_redactor.load()
    yield

app = FastAPI(title="Harness IA", lifespan=lifespan)
```

```python
// SOURCE: chat_ui/chat_ui/chat_ui.py:19-24, 57-62 (current, pre-STORY-007)
# Reflex's api_transformer mounts fastapi_app as a Starlette sub-app under a
# new outer Starlette app whose own lifespan runs instead ...
init_db()
...
app = rx.App(api_transformer=fastapi_app, ...)
app.add_page(index)

# Same api_transformer lifespan bypass as init_db() above: app.main's lifespan —
# and so STORY-002's pii_redactor.load() — never fires under Reflex. Registered as
# a lifespan task (not called at import) so `reflex export --frontend-only` in the
# Dockerfile's builder stage still never touches the spaCy model. load() is
# zero-arg, sync and PII_REDACTION_ENABLED-aware, so Reflex runs it as-is.
app.register_lifespan_task(pii_redactor.load)
```

`authz.load()` must be zero-arg, sync, and safe to call at Reflex-export time (i.e. a no-op whenever `RBAC_ROLES_FILE` is empty, exactly like `pii_redactor.load()` is a no-op whenever `PII_REDACTION_ENABLED` is false) — both properties fall straight out of the design in this plan. It is added to `app/main.py`'s `lifespan` right next to `pii_redactor.load()`, and registered in `chat_ui.py` right next to the existing `app.register_lifespan_task(pii_redactor.load)` line. Skipping the second registration is the exact PRD-002/PRD-003 trap the story's Technical Notes call out by name.

### Error handling — "fails loudly, names the file and the error" precedent

```python
// SOURCE: app/services/pii_redactor.py:17-26
def _build_analyzer() -> AnalyzerEngine:
    ...
    try:
        nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
        return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    except Exception as exc:
        raise PiiRedactorError(f"Failed to load Presidio NLP model {settings.PII_NLP_MODEL!r}: {exc}") from exc
```

Direct precedent for a startup `load()` that raises a dedicated, single-purpose exception naming the resource and the underlying error via `from exc` — `authz.load()` follows this exactly for `AuthzConfigError`, both for the read/parse failure and the unknown-permission failure.

```python
// SOURCE: app/db/database.py:22
raise ValueError(f"Unsupported DATABASE_URL scheme: {url}")
```

Confirms the codebase's general idiom of raising a plain, descriptive exception on startup misconfiguration rather than logging-and-continuing — reinforces that `AuthzConfigError` should propagate uncaught out of `load()` (and thus abort the `lifespan`/Reflex startup), not be swallowed.

### Full-replace, not merge — the exact mechanism

```python
// SOURCE: app/services/authz.py:12-33 (current, STORY-006)
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {...},
    "auditor": {...},
    "user": {...},
}
```

`ROLE_PERMISSIONS` is currently a plain module-level binding, so `load()` reassigns it wholesale with `global ROLE_PERMISSIONS` — no `.update()`, no per-role merge. This is deliberate per the story's Technical Notes ("a partial override that silently inherits grants is how a permission gets granted by accident") and matches the module-level-dict-as-policy-table pattern STORY-006 already established.

### Tests — settings + tmp_path precedent, and the module-global reset problem

```python
// SOURCE: tests/test_manage_users_cli.py:14-19
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```

Direct precedent for writing a fixture file under `tmp_path` and pointing a setting at its `str()` path via `monkeypatch.setattr`. `test_authz.py`'s `load()` tests write JSON to `tmp_path / "roles.json"` and set `settings.RBAC_ROLES_FILE` the same way.

```python
// SOURCE: tests/test_pii_redactor.py:13-18
@pytest.fixture(autouse=True)
def _small_model_and_reset(monkeypatch):
    monkeypatch.setattr(settings, "PII_NLP_MODEL", "en_core_web_sm")
    monkeypatch.setattr(pii_redactor, "_analyzer", None)
    monkeypatch.setattr(pii_redactor, "_anonymizer", None)
    yield
```

Precedent for resetting a module-level singleton around each test — but `monkeypatch.setattr` only auto-restores a value it *itself* set. `authz.load()` reassigns `authz.ROLE_PERMISSIONS` internally via `global`, so a test-level fixture must explicitly snapshot and restore `authz.ROLE_PERMISSIONS` after every test that calls `load()` with a custom file — otherwise a later test in the same session (including the existing STORY-006 full-matrix parametrized tests, which read the module attribute through `authorize()`, not through their own imported name) would silently run against a leftover custom matrix. This plan's Task 2 adds an explicit `_reset_role_permissions` fixture for this reason — do not rely on bare `monkeypatch.setattr(settings, "RBAC_ROLES_FILE", ...)` alone to make this safe.

```python
// SOURCE: tests/test_main.py:30-34
def test_lifespan_loads_pii_analyzer_before_serving_requests(_small_model_and_reset):
    with TestClient(app) as test_client:
        assert pii_redactor._analyzer is not None
        response = test_client.get("/health")
        assert response.status_code == 200
```

Direct precedent for asserting a `lifespan`-registered `load()` actually ran, using `TestClient` as a context manager (which drives the ASGI lifespan). `test_main.py`'s new test does the same for `authz.load()` / `authz.ROLE_PERMISSIONS`.

```python
// SOURCE: tests/test_config.py:61-65
def test_env_example_documents_every_new_rbac_var_with_a_comment():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for var in ("RBAC_ENABLED", "RBAC_DEFAULT_ROLE", "RBAC_ROLES_FILE", "MODEL_ALLOWLIST"):
        assert re.search(rf"(?m)^#.+\n{var}=", text), ...
```

Confirms `RBAC_ROLES_FILE` is already documented in `.env.example` and `app/config.py` by STORY-005 — no config/env changes needed in this story.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/authz.py` | UPDATE | Add `AuthzConfigError`, `_KNOWN_PERMISSIONS`, and `load()` — reads `RBAC_ROLES_FILE`, validates, wholesale-replaces `ROLE_PERMISSIONS` |
| `app/main.py` | UPDATE | Call `authz.load()` in `lifespan`, next to `pii_redactor.load()` |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | `app.register_lifespan_task(authz.load)`, next to the existing `pii_redactor.load` registration |
| `tests/test_authz.py` | UPDATE | Add `load()` coverage for all 5 ACs |
| `tests/test_main.py` | UPDATE | Add a lifespan test proving `authz.load()` runs via `app/main.py`'s `lifespan`, mirroring the existing `pii_redactor` lifespan tests |

No new files. `.env.example` / `app/config.py` already carry `RBAC_ROLES_FILE` from STORY-005 — unchanged.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add `load()` to `app/services/authz.py`

- **File**: `app/services/authz.py`
- **Action**: UPDATE
- **Implement**:
  1. Add imports at the top: `import json` and `from pathlib import Path`.
  2. Add `_KNOWN_PERMISSIONS`, a module-level set built from the five existing permission constants, placed directly after them:
     ```python
     _KNOWN_PERMISSIONS = {
         PERMISSION_QUERY_SUBMIT,
         PERMISSION_QUERY_BYOK,
         PERMISSION_AUDIT_READ_ALL,
         PERMISSION_AUDIT_READ_OWN,
         PERMISSION_STATS_READ,
     }
     ```
  3. Add `class AuthzConfigError(Exception): pass` (or a short one-line docstring), placed next to `PermissionDenied` — a distinct exception type so callers/tests can tell "misconfigured startup" apart from "a live authorization denial".
  4. Add `def load() -> None:` after `PermissionDenied`/before `authorize()` (mirrors `pii_redactor.py`'s `load()`-before-`redact()` ordering):
     ```python
     def load() -> None:
         """Loads the role matrix from RBAC_ROLES_FILE if set, replacing
         ROLE_PERMISSIONS wholesale -- no merge, so an omitted permission
         denies (STORY-007). Empty RBAC_ROLES_FILE is a no-op: the built-in
         matrix stands and no file is read. Called once at startup
         (app/main.py's lifespan, chat_ui.py's register_lifespan_task);
         never call this per request."""
         global ROLE_PERMISSIONS

         path_str = settings.RBAC_ROLES_FILE
         if not path_str:
             return

         try:
             raw = Path(path_str).read_text(encoding="utf-8")
         except OSError as exc:
             raise AuthzConfigError(f"Failed to read RBAC_ROLES_FILE {path_str!r}: {exc}") from exc

         try:
             parsed = json.loads(raw)
             matrix = {role: set(permissions) for role, permissions in parsed.items()}
         except (json.JSONDecodeError, AttributeError, TypeError) as exc:
             raise AuthzConfigError(f"Failed to parse RBAC_ROLES_FILE {path_str!r}: {exc}") from exc

         granted = {permission for permissions in matrix.values() for permission in permissions}
         unknown = sorted(granted - _KNOWN_PERMISSIONS)
         if unknown:
             raise AuthzConfigError(
                 f"RBAC_ROLES_FILE {path_str!r} grants unrecognized permission(s): {', '.join(unknown)}"
             )

         ROLE_PERMISSIONS = matrix
     ```
  5. Note the two `except` clauses deliberately catch different failure classes: `OSError` covers "unreadable" (missing file, permission error); `(json.JSONDecodeError, AttributeError, TypeError)` covers "malformed" (invalid JSON syntax, or valid JSON that isn't an object of arrays-of-strings, e.g. a JSON array at the top level, or a role mapped to a non-iterable). Both re-raise as `AuthzConfigError` naming the file path and carrying the original error via `from exc`, satisfying the AC's "startup fails with a message naming the file and the parse error."
  6. Role names in the file are **not** validated against the built-in three (`admin`/`auditor`/`user`) — the file may define arbitrary role names; only permission *names* are validated against `_KNOWN_PERMISSIONS`, per the AC and PRD Section 7's fixed permission set.
  7. Update the existing comment above `ROLE_PERMISSIONS` (currently "Overridable at startup via RBAC_ROLES_FILE (STORY-007); this is the built-in fallback.") only if wording needs to reference `load()` by name — otherwise leave as-is, it already anticipates this story correctly.
- **Mirror**: `app/services/pii_redactor.py:43-46` (`load()` shape: settings-gated no-op, else build/populate a module global) and `:17-26` (dedicated exception naming the resource + `from exc`).
- **Validate**: `python -c "from app.services.authz import load, AuthzConfigError; load(); print('ok')"` — no-op with default empty `RBAC_ROLES_FILE`, imports and runs cleanly.

### Task 2: Add `load()` test coverage to `tests/test_authz.py`

- **File**: `tests/test_authz.py`
- **Action**: UPDATE
- **Implement**:
  1. Add imports: `import json`, `import app.services.authz as authz` (module import, needed to read back `authz.ROLE_PERMISSIONS` after `load()` mutates it), plus `AuthzConfigError` and `load` to the existing `from app.services.authz import (...)` block.
  2. Add an explicit (non-autouse) fixture, used only by tests in this new section, that snapshots and restores the module global regardless of what `load()` did — see the "module-global reset problem" pattern above:
     ```python
     @pytest.fixture
     def _reset_role_permissions():
         original = authz.ROLE_PERMISSIONS
         yield
         authz.ROLE_PERMISSIONS = original
     ```
  3. **AC1 — empty `RBAC_ROLES_FILE` is a no-op, no file read.**
     ```python
     def test_load_is_noop_when_roles_file_unset(monkeypatch, _reset_role_permissions):
         monkeypatch.setattr(settings, "RBAC_ROLES_FILE", "")
         before = authz.ROLE_PERMISSIONS

         load()

         assert authz.ROLE_PERMISSIONS is before  # same object -- never rebuilt
     ```
     Also assert no filesystem access is attempted: monkeypatch `Path.read_text` (via `monkeypatch.setattr(authz.Path, "read_text", ...)` raising if called, or simpler — a `Mock` that fails the test if invoked) to prove the early-return happens before any I/O.
  4. **AC2 — valid JSON matrix fully replaces, no merge.**
     ```python
     def test_load_replaces_matrix_wholesale_from_valid_file(tmp_path, monkeypatch, _reset_role_permissions):
         roles_file = tmp_path / "roles.json"
         roles_file.write_text(json.dumps({"user": [PERMISSION_QUERY_SUBMIT]}))
         monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))

         load()

         assert authz.ROLE_PERMISSIONS == {"user": {PERMISSION_QUERY_SUBMIT}}
         # PERMISSION_AUDIT_READ_OWN was in the built-in "user" grants and is
         # omitted here -- omission is denial, not inherited from the default.
         identity = Identity(user_id="u", role="user")
         assert authorize(identity, PERMISSION_QUERY_SUBMIT) is None
         with pytest.raises(PermissionDenied):
             authorize(identity, PERMISSION_AUDIT_READ_OWN)
         # "admin" was in the built-in matrix and is entirely absent from the
         # file -- also gone, proving replace rather than a per-role merge.
         with pytest.raises(PermissionDenied):
             authorize(Identity(user_id="a", role="admin"), PERMISSION_STATS_READ)
     ```
  5. **AC3 — malformed/unreadable file fails startup naming the file + parse error, no silent fallback.**
     ```python
     def test_load_raises_on_malformed_json(tmp_path, monkeypatch, _reset_role_permissions):
         roles_file = tmp_path / "roles.json"
         roles_file.write_text("{not valid json")
         monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))
         before = dict(authz.ROLE_PERMISSIONS)

         with pytest.raises(AuthzConfigError) as exc_info:
             load()

         assert str(roles_file) in str(exc_info.value)
         assert authz.ROLE_PERMISSIONS == before  # no silent fallback mutation


     def test_load_raises_on_missing_file(tmp_path, monkeypatch, _reset_role_permissions):
         missing = tmp_path / "does-not-exist.json"
         monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(missing))

         with pytest.raises(AuthzConfigError) as exc_info:
             load()

         assert str(missing) in str(exc_info.value)
     ```
  6. **AC4 — unrecognized permission name fails startup, listing the unknown name.**
     ```python
     def test_load_raises_on_unrecognized_permission(tmp_path, monkeypatch, _reset_role_permissions):
         roles_file = tmp_path / "roles.json"
         roles_file.write_text(json.dumps({"user": [PERMISSION_QUERY_SUBMIT, "query:launch-nukes"]}))
         monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))

         with pytest.raises(AuthzConfigError) as exc_info:
             load()

         assert "query:launch-nukes" in str(exc_info.value)
     ```
  7. **AC5 — loads once at startup, `authorize()` never re-reads the file per call.** Prove `authorize()` itself performs no I/O and consults only the in-memory dict:
     ```python
     def test_authorize_does_not_read_file_per_call(tmp_path, monkeypatch, _reset_role_permissions):
         roles_file = tmp_path / "roles.json"
         roles_file.write_text(json.dumps({"user": [PERMISSION_QUERY_SUBMIT]}))
         monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))
         load()

         read_calls = []
         original_read_text = Path.read_text
         def _counting_read_text(self, *args, **kwargs):
             read_calls.append(self)
             return original_read_text(self, *args, **kwargs)
         monkeypatch.setattr(Path, "read_text", _counting_read_text)

         for _ in range(3):
             authorize(Identity(user_id="u", role="user"), PERMISSION_QUERY_SUBMIT)

         assert read_calls == []
     ```
  8. Group all of the above under a `# --- STORY-007: load() from RBAC_ROLES_FILE ---` banner comment, matching the file's existing per-AC banner convention.
- **Mirror**: `tests/test_manage_users_cli.py:14-19` for `tmp_path` + `monkeypatch.setattr(settings, ...)`; `tests/test_pii_redactor.py:13-18` for the reset-module-global-around-tests shape (adapted here to an explicit fixture rather than autouse, since only the new tests touch `ROLE_PERMISSIONS`); `tests/test_config.py` docstring/banner style.
- **Validate**: `python -m pytest tests/test_authz.py -v` — all existing STORY-006 cases plus the new STORY-007 cases pass, in either run order.

### Task 3: Wire `authz.load()` into `app/main.py`'s lifespan

- **File**: `app/main.py`
- **Action**: UPDATE
- **Implement**: Add `from app.services import authz` alongside the existing `from app.services import pii_redactor`, and call `authz.load()` inside `lifespan`, directly after `pii_redactor.load()`:
  ```python
  from app.services import authz, pii_redactor

  @asynccontextmanager
  async def lifespan(app: FastAPI):
      init_db()
      pii_redactor.load()
      authz.load()
      yield
  ```
- **Mirror**: `app/main.py:11-15` (existing `lifespan` body) — same call shape as `pii_redactor.load()`, same position (after `init_db()`, before `yield`).
- **Validate**: `python -m pytest tests/test_main.py -v` (after Task 4 below); `uvicorn app.main:app --reload` starts without error against a default (empty) `.env`.

### Task 4: Add a lifespan test proving `authz.load()` runs, in `tests/test_main.py`

- **File**: `tests/test_main.py`
- **Action**: UPDATE
- **Implement**: Add `import app.services.authz as authz` to the imports, and a test mirroring the existing `test_lifespan_loads_pii_analyzer_before_serving_requests`:
  ```python
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
  The `try/finally` restore is required here for the same module-global reason as Task 2's `_reset_role_permissions` fixture — `TestClient(app)` drives the real `lifespan`, which calls the real `authz.load()`, which reassigns the shared module attribute that other test files' `authorize()` calls read from.
- **Mirror**: `tests/test_main.py:30-34` (`test_lifespan_loads_pii_analyzer_before_serving_requests`) for the `TestClient(app)`-as-context-manager shape.
- **Validate**: `python -m pytest tests/test_main.py -v` — new test passes; existing `test_lifespan_*` pii_redactor tests still pass (proves `authz.load()` doesn't interfere with `pii_redactor.load()` in the same lifespan).

### Task 5: Register `authz.load` as a chat_ui lifespan task

- **File**: `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Implement**: Add `authz` to the existing `from app.services import pii_redactor` import line, and add a second `register_lifespan_task` call directly after the existing one, with a comment naming the same trap already documented for `pii_redactor.load`:
  ```python
  from app.services import authz, pii_redactor
  ...
  # Same api_transformer lifespan bypass as init_db() above: app.main's lifespan —
  # and so STORY-002's pii_redactor.load() — never fires under Reflex. Registered as
  # a lifespan task (not called at import) so `reflex export --frontend-only` in the
  # Dockerfile's builder stage still never touches the spaCy model. load() is
  # zero-arg, sync and PII_REDACTION_ENABLED-aware, so Reflex runs it as-is.
  app.register_lifespan_task(pii_redactor.load)
  # Same bypass, same reason (STORY-007): without this, the chat UI would
  # enforce the built-in role matrix while the API enforces RBAC_ROLES_FILE's
  # override -- two different permission matrices for the same deployment.
  app.register_lifespan_task(authz.load)
  ```
- **Mirror**: `chat_ui/chat_ui/chat_ui.py:57-62` (existing `pii_redactor` registration + its comment).
- **Validate**: `python -c "import sys; sys.path.insert(0, 'chat_ui'); sys.path.insert(0, '.'); import chat_ui.chat_ui" ` run with `cwd` at repo root and `OPENROUTER_API_KEY`/`ADMIN_TOKEN` env vars set — imports without error (same shape as the existing `test_chat_components_import.py` subprocess probe, which already exercises this module and would fail loudly on an import-time error introduced here). Also run `python -m pytest tests/test_chat_components_import.py -v` to confirm the existing smoke test still passes unmodified.

---

## End-to-End Tests

This story has no new HTTP surface (`authz.load()` has no request-time consumer — `authorize()`'s call sites are STORY-010/STORY-012's job). Validation is startup/unit-level:

- [ ] `python -m pytest tests/test_authz.py -v` — STORY-006's existing matrix tests plus STORY-007's new `load()` tests (no-op on empty file, full-replace on valid file, raises naming file+error on malformed/missing file, raises listing the unknown permission, no per-call file I/O) all pass
- [ ] `python -m pytest tests/test_main.py -v` — new lifespan test proves `authz.load()` runs via `app/main.py`'s `lifespan`; existing `pii_redactor` lifespan tests still pass unmodified
- [ ] `python -m pytest tests/test_chat_components_import.py -v` — chat_ui.py still imports and builds cleanly with the new `authz` import + `register_lifespan_task` call
- [ ] `python -m pytest tests/ -v` — full existing suite passes unmodified, confirming no regression to STORY-001..006
- [ ] Manual: start the app with `RBAC_ROLES_FILE` pointed at a deliberately malformed JSON file → `uvicorn app.main:app` fails to start with a message naming the file path and the JSON error, not a silent fallback

---

## Validation

```bash
python -m pytest tests/test_authz.py -v
python -m pytest tests/test_main.py -v
python -m pytest tests/test_chat_components_import.py -v
python -m pytest tests/ -v
```

---

## Acceptance Criteria

(Copied from story `STORY-007`)

- [ ] Given `RBAC_ROLES_FILE` is empty, when the app starts, then the built-in matrix is used and no file is read
- [ ] Given a valid JSON matrix, when the app starts, then it **fully replaces** the built-in matrix — no merge, so an omitted permission is a denial
- [ ] Given a malformed or unreadable file, when the app starts, then startup fails with a message naming the file and the parse error, rather than silently falling back to the default
- [ ] Given a file granting an unrecognized permission name, when it loads, then startup fails listing the unknown name
- [ ] Given the file loads, when it happens, then it happens once at startup, never per request
- [ ] All tasks completed
- [ ] `python -m pytest tests/test_authz.py -v` passes
- [ ] `python -m pytest tests/test_main.py -v` passes
- [ ] `python -m pytest tests/test_chat_components_import.py -v` passes
- [ ] `python -m pytest tests/ -v` passes unmodified
- [ ] Follows existing patterns (`pii_redactor.py` `load()`/exception style, `app/main.py` + `chat_ui.py` dual lifespan-registration pattern, repo-wide test conventions)
