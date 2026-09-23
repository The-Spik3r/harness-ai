---
story: STORY-007
prd: PRD-011
slug: startup-load-and-sample-file
title: "pattern_config.load() in both lifespans, and a working sample file"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-011-pattern-policy        # all stories commit here, no per-story branch
created: 2026-09-22
---

# Plan: pattern_config.load() in both lifespans, and a working sample file

## Summary

STORY-005 and STORY-006 built `pattern_config.load()`, which is zero-argument and synchronous, reads `settings.PATTERNS_FILE` at call time, and raises `PatternConfigError`. So far only tests call it. This story registers it at startup in **both** entry points.

- **`app/main.py`'s lifespan** is used by plain uvicorn and the test client.
- **`chat_ui/chat_ui/chat_ui.py`'s `register_lifespan_task` chain** is the one production runs (`reflex run --env prod --backend-only`). Reflex's `api_transformer` mount skips `app.main`'s lifespan entirely (PRD-007).

In both places the call goes right after `authz.load()` and before `authz.check_bootstrap()`, so the two configuration loaders sit next to each other.

The story also ships `examples/patterns.yaml`, a byte-for-byte copy of PRD Section 6.3. A test loads that file through `load()` and asserts the result `==` `BUILT_IN_POLICY`. That equality test is what keeps the sample, the PRD and the built-in policy from drifting apart.

Two tests cover the startup failure: a malformed file fails the FastAPI lifespan with `PatternConfigError`, and fails the Reflex lifespan task too. The Reflex case runs in the subprocess probe that `tests/test_chat_ui_startup_guard.py` already uses. With `PATTERNS_FILE` unset, both paths read no file and leave the built-in policy in place, and every existing startup test passes unchanged.

## User Story

As a platform operator
I want the patterns file loaded and validated at startup whichever way the app is launched
So that a broken file can never reach a running deployment

## Story Reference

- Story file: `.agents/stories/PRD-011-pattern-policy/STORY-007-startup-load-and-sample-file.md`
- PRD: `.agents/PRDs/PRD-011-pattern-policy/PRD.md`, Sections 6.3, 6.8, 6.9, 7 (F3), 11 (Quality indicators), 12 (Phase 2)
- Predecessor plans: `.agents/plans/PRD-011-pattern-policy/completed/STORY-005-pattern-config-load-and-validate.plan.md`, `.../completed/STORY-006-profiles-and-role-matrix.plan.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `app/main.py`, `chat_ui/chat_ui/chat_ui.py`, `app/config.py` (comment only), `examples/patterns.yaml` (new), `tests/test_main.py`, `tests/test_chat_ui_startup_guard.py`, `tests/test_pattern_config.py` |
| Story | STORY-007 |
| PRD | PRD-011 |
| Epic Branch | `epic/PRD-011-pattern-policy` (commit directly on this branch) |

---

## Design Decisions

| # | Decision | Why |
|---|----------|-----|
| D-A | **Order in both lifespans: `init_db` → `pii_redactor.load` → `authz.load` → `pattern_config.load` → `authz.check_bootstrap`.** | The story asks for "after `authz.load()`" and for the two loaders to be adjacent, so PRD-015's loader has an obvious place to go. It also runs before `check_bootstrap`, which reads the database: a pure config error is reported before a database-state error, and fails without touching `users`. Reflex runs lifespan tasks in the order they were registered (`.venv/Lib/site-packages/reflex/app_mixins/lifespan.py:89-118`), so registration order matters. The Reflex probe asserts it. |
| D-B | **Register `pattern_config.load` directly with `app.register_lifespan_task(pattern_config.load)`, with no wrapper.** | This is the same shape as `authz.load` at `chat_ui/chat_ui/chat_ui.py:199`. Reflex calls a sync zero-argument function, and an exception escapes `_run_lifespan_tasks` and stops startup. Registering the function object itself also lets the probe check membership with `chat_ui_module.pattern_config.load in tasks`. |
| D-C | **The Reflex failure test extends `tests/test_chat_ui_startup_guard.py`'s existing `_CHECK_SCRIPT`/`_run_probe` pattern. It checks that the task is registered and calls it by hand. It does not start Reflex's lifespan.** | The story's Technical Notes name this file. `check_bootstrap` uses the same "registered + raises when called" pattern (`:51-61`, `:91-100`). Driving `app._run_lifespan_tasks` would depend on private Reflex API and would load spaCy through `pii_redactor.load`. The child process builds its own `Settings()`, so `PATTERNS_FILE` has to be passed in the child's **environment**, not set with monkeypatch. |
| D-D | **The probe's new keys are added alongside the existing ones, and no existing assertion changes.** `_CHECK_SCRIPT` gains `patterns_load_registered`, `patterns_load_adjacent` and `patterns_raised` (the exception class name, or `null`). | AC 5 says "no existing startup test changes". Three existing tests read `result[...]` keys that remain as they are. |
| D-E | **The malformed file is well-formed YAML with a misspelled key (`mach: word`), not a missing path.** | This is PRD User Story 2's example. The error message then names the list and the key, and the tests assert that text, which proves the error is `load()`'s validation and not an `OSError` wrapper. A missing path would also be a valid `PatternConfigError`, but it would say less. |
| D-F | **Sample equality: `load()` with `PATTERNS_FILE=examples/patterns.yaml`, then `get_policy() == BUILT_IN_POLICY`, plus declared order: `list(policy.lists) == ["injection", "keywords"]` and `list(policy.profiles) == ["chat", "code"]`.** | The dataclasses are `frozen=True` (`app/services/pattern_config.py:95-158`), so `==` compares field by field. `re.Pattern` compares equal by pattern and flags (checked on Python 3.11.9: `re.compile('a', re.I) == re.compile('a', re.I)` is `True`). Dict `==` ignores order. Pattern order inside each list is already covered by the `patterns` tuples, and the ordered-key checks cover list and profile order. |
| D-G | **No byte-comparison against the PRD's markdown in tests.** | The story says the policy-equality test is what enforces "cannot drift". The verbatim copy is checked once, at implementation time (Task 4 Validate), with a scripted diff. That diff is recorded in the report and does not become a test coupled to a planning document. |
| D-H | **The test that loads the sample goes in `tests/test_pattern_config.py`, and the FastAPI lifespan tests go in `tests/test_main.py`.** | `test_pattern_config.py` already has `_reset_policy` and the autouse `_default_profile_is_chat` it needs. `test_main.py` is where lifespan tests already live (`:47-117`, `:166-188`). |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` contains only `frontend-design`, which covers visual UI design. This story is backend startup wiring and a YAML sample, and the story's `skills: []` and PRD Appendix both say no skill applies. | — |

---

## Patterns to Follow

### Lifespan registration (FastAPI)
```python
# SOURCE: app/main.py:8-18
from app.services import authz, pii_redactor, pipeline_executor

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    pii_redactor.load()
    authz.load()
    authz.check_bootstrap()
    yield
    pipeline_executor.shutdown()
```

### Lifespan registration (Reflex mount) + the "same bypass" comment style
```python
# SOURCE: chat_ui/chat_ui/chat_ui.py:196-204
# Same bypass, same reason (STORY-007): without this, the chat UI would
# enforce the built-in role matrix while the API enforces RBAC_ROLES_FILE's
# override -- two different permission matrices for the same deployment.
app.register_lifespan_task(authz.load)
# Same bypass again (STORY-016): app.main's fail-fast bootstrap guard would
# otherwise never run for this ingress, ...
app.register_lifespan_task(authz.check_bootstrap)
```
(Note: that "STORY-007" is PRD-005's, not this one. The new comment should say "PRD-011 STORY-007" so the two can't be confused.)

### Error Handling (startup failure through the FastAPI lifespan)
```python
# SOURCE: tests/test_main.py:109-117
def test_lifespan_fails_fast_when_rbac_enabled_and_no_active_users(_empty_users_db, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    assert count_active_users() == 0

    with pytest.raises(authz.RbacNotBootstrappedError):
        with TestClient(app):
            pass
```

### Tests: file-loading lifespan success + state restore
```python
# SOURCE: tests/test_main.py:79-98
def test_lifespan_loads_roles_file_before_serving_requests(tmp_path, monkeypatch, temp_db):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text('{"user": ["query:submit"]}')
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    original = authz.ROLE_PERMISSIONS
    try:
        with TestClient(app) as test_client:
            assert authz.ROLE_PERMISSIONS == {"user": {"query:submit"}}
    finally:
        authz.ROLE_PERMISSIONS = original
```

### Tests: Reflex-mount probe (subprocess, env-driven)
```python
# SOURCE: tests/test_chat_ui_startup_guard.py:51-61, 80-88
tasks = chat_ui_module.app.get_lifespan_tasks()
result["guard_registered"] = chat_ui_module.authz.check_bootstrap in tasks
try:
    chat_ui_module.authz.check_bootstrap()
    result["raised"] = False
except chat_ui_module.authz.RbacNotBootstrappedError:
    result["raised"] = True

@pytest.fixture
def _empty_rbac_env(database_url_factory):
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(_PYTHONPATH)}
    env.update(child_db_env(database_url_factory("chat_ui_guard")))
    env["RBAC_ENABLED"] = "true"
    return env
```

### Tests: pattern_config state isolation + "no file read"
```python
# SOURCE: tests/test_pattern_config.py:60-77, 104-115
@pytest.fixture
def _reset_policy():
    original = pattern_config._policy
    yield
    pattern_config._policy = original

@pytest.fixture(autouse=True)
def _default_profile_is_chat(monkeypatch):
    monkeypatch.setattr(settings, "PATTERN_PROFILE_DEFAULT", "chat")

def test_load_is_noop_when_patterns_file_unset(monkeypatch, _reset_policy):
    monkeypatch.setattr(settings, "PATTERNS_FILE", "")
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("read_text should not be called when PATTERNS_FILE is empty")
    monkeypatch.setattr(Path, "read_text", _fail_if_called)
    assert load() is None
    assert get_policy() is BUILT_IN_POLICY
```

### Naming
- Test names describe behaviour in full: `test_lifespan_fails_when_the_database_is_unreachable`, `test_check_bootstrap_registered_as_chat_ui_lifespan_task`.
- Every new test's docstring cites the PRD/story and the AC it proves (`tests/test_main.py:166-175`).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/main.py` | UPDATE | Import `pattern_config`; call `pattern_config.load()` between `authz.load()` and `authz.check_bootstrap()` (AC 1) |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | Import `pattern_config`; `app.register_lifespan_task(pattern_config.load)` between the `authz.load` and `authz.check_bootstrap` registrations, with a "same bypass" comment (AC 2) |
| `app/config.py` | UPDATE | Comment only. The pattern-settings header at `:125-127` says "no production code reads these yet", which stops being true for `PATTERNS_FILE`/`PATTERN_PROFILE_DEFAULT`/`PATTERNS_ALLOW_REGEX` once `load()` runs at startup |
| `examples/patterns.yaml` | CREATE | PRD Section 6.3 verbatim, comments included (AC 3) |
| `tests/test_pattern_config.py` | UPDATE | Add the test that loads the sample and checks it equals the built-in policy (AC 3) |
| `tests/test_main.py` | UPDATE | Add tests for a malformed file (fails), the sample file (loads) and an unset setting (no file read) through the FastAPI lifespan (AC 1, 4, 5) |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | Probe: registration, adjacency, raise on malformed file, no raise when unset (AC 2, 4, 5); module docstring lists the new concern |

No new dependency: `PyYAML` is already explicit in `requirements.txt` (STORY-005). `Dockerfile` uses `COPY . .` in both stages and `.dockerignore` does not exclude `examples/`, so the sample ships in the image with no build change.

---

## Tasks

Execute in order. Each task is atomic and can be checked on its own.

### Task 1: Wire `pattern_config.load()` into `app/main.py`'s lifespan

- **File**: `app/main.py`
- **Action**: UPDATE
- **Implement**:
  - Line 8 becomes `from app.services import authz, pattern_config, pii_redactor, pipeline_executor` (alphabetical, as it is now).
  - Insert `pattern_config.load()` on its own line between `authz.load()` (`:15`) and `authz.check_bootstrap()` (`:16`).
  - Add no comment in the lifespan body. It currently has none, and the adjacency explains itself.
- **Mirror**: `app/main.py:14-15` (`pii_redactor.load()`, `authz.load()`)
- **Validate**: `python -c "import app.main"` exits 0. `pytest tests/test_main.py -q` is green with no test edited yet, which shows AC 5 on this path: `PATTERNS_FILE` is unset, so the call is a no-op.

### Task 2: Register `pattern_config.load` in the Reflex mount

- **File**: `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Implement**:
  - Line 13 becomes `from app.services import authz, pattern_config, pii_redactor, pipeline_executor`.
  - After `app.register_lifespan_task(authz.load)` (`:199`) and before the STORY-016 comment and `check_bootstrap` registration, add:
    ```python
    # Same bypass (PRD-011 STORY-007): without this the chat UI would inspect
    # prompts with the built-in pattern policy while the API enforces
    # PATTERNS_FILE -- and a malformed file would stop uvicorn but not the
    # deployment that actually serves traffic. Kept beside authz.load: both are
    # pure configuration loads, and the next one (PRD-015) belongs here too.
    app.register_lifespan_task(pattern_config.load)
    ```
- **Mirror**: `chat_ui/chat_ui/chat_ui.py:196-199`
- **Validate**: `pytest tests/test_chat_ui_startup_guard.py -q` is green with no test edited yet (the existing probe still imports and runs).

### Task 3: Refresh the stale settings comment

- **File**: `app/config.py`
- **Action**: UPDATE (comment only)
- **Implement**: In the header at `:125-127` ("no production code reads these yet -- each field names the story that becomes its consumer"), say that `pattern_config.load()` now reads `PATTERNS_FILE`, `PATTERN_PROFILE_DEFAULT` and `PATTERNS_ALLOW_REGEX` at startup in both lifespans (STORY-007), and that `PATTERN_MAX_SCAN_CHARACTERS` and the request-path read of `PATTERN_PROFILE_DEFAULT` are still waiting on STORY-008. Leave the per-field comments alone. They already name their consumers.
- **Mirror**: the comment voice in `app/config.py:129-146`
- **Validate**: `python -c "from app.config import settings"` exits 0.

### Task 4: Create `examples/patterns.yaml`

- **File**: `examples/patterns.yaml`
- **Action**: CREATE (the `examples/` directory is new)
- **Implement**: Copy the body of the PRD Section 6.3 YAML fence **verbatim**. That runs from the `# examples/patterns.yaml` comment line through the end of the `code` profile, with inline comments, blank lines and two-space indentation. Add nothing and reformat nothing. End the file with a single trailing newline.
- **Mirror**: `.agents/PRDs/PRD-011-pattern-policy/PRD.md:186-217`
- **Validate** (verbatim check, one-off, recorded in the report):
  ```bash
  python - <<'EOF'
  import re, pathlib
  prd = pathlib.Path(".agents/PRDs/PRD-011-pattern-policy/PRD.md").read_text(encoding="utf-8")
  fence = re.search(r"### 6\.3 The patterns file\s+```yaml\n(.*?)```", prd, re.S).group(1)
  sample = pathlib.Path("examples/patterns.yaml").read_text(encoding="utf-8")
  assert sample == fence, "examples/patterns.yaml differs from PRD Section 6.3"
  print("verbatim: OK")
  EOF
  ```

### Task 5: The sample loads and equals the built-in policy

- **File**: `tests/test_pattern_config.py`
- **Action**: UPDATE (add; no existing test modified)
- **Implement**: Add a section `# --- STORY-007: examples/patterns.yaml is loaded, not merely documented ---` containing:
  - A module constant `_SAMPLE_FILE = Path(__file__).resolve().parents[1] / "examples" / "patterns.yaml"`.
  - `test_examples_patterns_yaml_loads_to_the_built_in_policy(monkeypatch, _reset_policy)`:
    - `monkeypatch.setattr(settings, "PATTERNS_FILE", str(_SAMPLE_FILE))`, then `load()` and `policy = get_policy()`.
    - `assert policy is not BUILT_IN_POLICY`. This proves a file was actually read, so equality is not trivially true.
    - `assert policy == BUILT_IN_POLICY`.
    - `assert list(policy.lists) == list(BUILT_IN_POLICY.lists)` and the same for `profiles`. These check declared order (D-F).
    - Docstring cites PRD-011 Section 11's quality indicator: "a sample that does not parse is worse than no sample". Also say that this equality is what stops the PRD, the sample and `_build_built_in()` drifting apart.
  - `_default_profile_is_chat` is already autouse, so the developer's `.env` cannot affect the cross-check.
- **Mirror**: `tests/test_pattern_config.py:235-248` (`test_load_replaces_the_policy_wholesale`)
- **Validate**: `pytest tests/test_pattern_config.py -q -k examples` passes. Then temporarily change `override` to `overrides` in the sample, check that the test fails, and revert.

### Task 6: FastAPI lifespan tests

- **File**: `tests/test_main.py`
- **Action**: UPDATE (add; no existing test modified)
- **Implement**:
  - Imports:
    - `import app.services.pattern_config as pattern_config`
    - `from app.services.pattern_config import BUILT_IN_POLICY, PatternConfigError`
    - `from pathlib import Path`
  - Constants:
    - `_MALFORMED_PATTERNS`: the Section 6.3 shape with `match: word` misspelled as `mach: word` under `injection`.
    - `_SAMPLE_FILE`: the same path as in Task 5.
  - Fixture `_pattern_startup(monkeypatch, temp_db)`:
    - `monkeypatch.setattr(settings, "RBAC_ENABLED", False)` and `monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)`, which keeps spaCy out of these tests. Comment these the way `_small_model_and_reset` is commented.
    - `monkeypatch.setattr(settings, "PATTERN_PROFILE_DEFAULT", "chat")`.
    - Save `pattern_config._policy`, yield, then restore it.
  - `test_lifespan_fails_when_patterns_file_is_malformed(_pattern_startup, tmp_path, monkeypatch)`:
    - Write the malformed file and set `PATTERNS_FILE`.
    - `with pytest.raises(PatternConfigError) as excinfo: with TestClient(app): pass`.
    - Assert `"injection" in str(excinfo.value)` and `"mach" in str(excinfo.value)`.
    - Assert `pattern_config.get_policy() is BUILT_IN_POLICY` (nothing half-applied).
    - Covers AC 1 and AC 4, FastAPI path.
  - `test_lifespan_loads_patterns_file_before_serving_requests(_pattern_startup, monkeypatch)`:
    - Set `PATTERNS_FILE` to `_SAMPLE_FILE`.
    - Inside `with TestClient(app) as c:`, assert `pattern_config.get_policy() is not BUILT_IN_POLICY`, `== BUILT_IN_POLICY`, and `c.get("/health").status_code == 200`.
    - Proves the lifespan calls `load()`, not just that it would fail.
  - `test_lifespan_reads_no_patterns_file_when_unset(_pattern_startup, monkeypatch)`:
    - Set `PATTERNS_FILE` to `""`.
    - Patch `pattern_config.Path` with a stand-in whose construction raises `AssertionError`. This scopes the "no read" check to `pattern_config`, where a global `Path.read_text` patch would also catch other startup code.
    - Inside `with TestClient(app):`, assert `get_policy() is BUILT_IN_POLICY`.
    - Covers AC 5.
- **Mirror**: `tests/test_main.py:79-98` (success, with state restore) and `:109-117` (failure)
- **Validate**: `pytest tests/test_main.py -q` passes. Temporarily remove the `pattern_config.load()` line from `app/main.py` and check that the malformed-file and sample tests fail, then restore the line.

### Task 7: Reflex-mount probe tests

- **File**: `tests/test_chat_ui_startup_guard.py`
- **Action**: UPDATE (additive; existing tests and result keys untouched)
- **Implement**:
  - **Module docstring**:
    - Add a fourth bullet: "PRD-011 STORY-007's `pattern_config.load()`, registered as a lifespan task beside `authz.load`. A malformed `PATTERNS_FILE` must stop this ingress too."
    - Add `pattern_config.load()` to the list of duplicated calls.
  - **`_CHECK_SCRIPT`**, after the existing `pipeline_shutdown_registered` key and before the `check_bootstrap` try block:
    ```python
    load = chat_ui_module.pattern_config.load
    result["patterns_load_registered"] = load in tasks
    result["patterns_load_adjacent"] = (
        load in tasks
        and chat_ui_module.authz.load in tasks
        and tasks.index(load) == tasks.index(chat_ui_module.authz.load) + 1
    )
    try:
        load()
        result["patterns_raised"] = None
    except Exception as exc:
        result["patterns_raised"] = type(exc).__name__
        result["patterns_message"] = str(exc)
    ```
    - Catch `Exception` and record the class name rather than `except PatternConfigError`. A wrong exception type then shows up as a failed assertion instead of crashing the probe.
  - **Fixture `_malformed_patterns_env(_empty_rbac_env, tmp_path)`**:
    - Write `_MALFORMED_PATTERNS` (the same `mach: word` text as Task 6; define it at module level here) to `tmp_path/"patterns.yaml"`.
    - Return `{**_empty_rbac_env, "PATTERNS_FILE": str(path), "PATTERN_PROFILE_DEFAULT": "chat"}`.
    - This goes in the child's **environment** because the child builds its own `Settings()` (D-C).
  - **`_empty_rbac_env`**: add `env["PATTERNS_FILE"] = ""` and `env["PATTERN_PROFILE_DEFAULT"] = "chat"`. A developer's shell or `chat_ui/.env` then cannot switch the "unset" case to a file. Add a one-line comment. This does not change any existing assertion.
  - **New tests**:
    - `test_pattern_config_load_registered_as_chat_ui_lifespan_task(_empty_rbac_env)` asserts `patterns_load_registered is True` and `patterns_load_adjacent is True` (AC 2, D-A).
    - `test_pattern_config_load_is_a_noop_when_patterns_file_unset(_empty_rbac_env)` asserts `patterns_raised is None` (AC 5, Reflex path).
    - `test_pattern_config_load_fails_chat_ui_startup_on_malformed_file(_malformed_patterns_env)` asserts `not result["errors"]` (so the import succeeded and the failure is the lifespan task, not the import), `patterns_raised == "PatternConfigError"`, and that `"mach"` appears in `patterns_message` (AC 4, Reflex path).
- **Mirror**: `tests/test_chat_ui_startup_guard.py:41-106`
- **Validate**: `pytest tests/test_chat_ui_startup_guard.py -q` passes. Temporarily remove the registration line from `chat_ui.py` and check that the registration and malformed-file tests fail, then restore the line.

### Task 8: Full regression

- **Action**: run the suite
- **Implement**: `pytest -q` from the repo root, as CI does in `.github/workflows/ci.yml:62`, with sqld running at `HARNESS_TEST_LIBSQL_URL` (default `http://127.0.0.1:8080`). If many fixture errors appear at once, restart the libSQL container rather than bisecting the code, per the PRD Section 11 note.
- **Validate**:
  - The full suite is green.
  - `git diff --stat` shows no changed assertion in `test_query_router.py`, `test_integration.py`, `test_query_outcomes_regression.py`, `test_chat_outcomes_regression.py` or `test_history_off_integration.py`, and none of the existing tests in `test_main.py` or `test_chat_ui_startup_guard.py` edited (PRD Section 11 quality indicators, AC 5).

---

## End-to-End Tests

- [ ] **uvicorn, malformed file.** `PATTERNS_FILE=<tmp>/bad.yaml` (containing `mach: word`), then `uvicorn app.main:app`. The process exits during startup with `PatternConfigError` naming `injection` and `mach`, and no port is bound.
- [ ] **uvicorn, sample file.** `PATTERNS_FILE=examples/patterns.yaml`, then `uvicorn app.main:app`. It starts, and `curl http://localhost:8000/health` returns `{"status":"ok"}`.
- [ ] **uvicorn, unset.** No `PATTERNS_FILE`. It starts exactly as before.
- [ ] **Reflex backend, malformed file.** `cd chat_ui && PATTERNS_FILE=<abs>/bad.yaml reflex run --env prod --backend-only`. Startup fails with `PatternConfigError` in the log. This is the production path in the story's Technical Notes. If running Reflex locally is impractical, record that the subprocess probe in Task 7 stands in for it, and why.
- [ ] **Reflex backend, sample file.** The same command with `PATTERNS_FILE=<abs>/examples/patterns.yaml` starts, and the backend's `/health` answers.

---

## Validation

```bash
python -c "import app.main"
pytest tests/test_pattern_config.py tests/test_main.py tests/test_chat_ui_startup_guard.py -q
pytest -q
```

No linter is configured in this repository: there is no pyproject.toml or Makefile, and no ruff or flake8 in `requirements.txt` or CI. `pytest` is the only gate.

---

## Risks & Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| R-1 | **A developer's `.env` sets `PATTERNS_FILE` or `PATTERN_PROFILE_DEFAULT`.** Every `TestClient(app)` in the suite now calls `load()`, so a broken local value would fail unrelated lifespan tests. | Neither the repo `.env` nor `chat_ui/.env` sets them today (checked). The new tests pin both explicitly: monkeypatch in-process, and the environment for the probe. A developer who does set a bad value gets exactly the startup failure this story is meant to produce. |
| R-2 | **Leaked policy between tests.** The sample-file lifespan test rebinds `pattern_config._policy`. | `_pattern_startup` and `_reset_policy` restore the original, the same way `authz.ROLE_PERMISSIONS` is restored at `tests/test_main.py:90-98`. |
| R-3 | **`re.Pattern` equality stops holding** (a Python change, or different flags in `compile_pattern` between the built-in and the file path). | Both paths call the same `compile_pattern`. If equality ever breaks, the sample test fails loudly rather than passing vacuously, and `assert policy is not BUILT_IN_POLICY` stops the check from being trivially true. |
| R-4 | **The probe's malformed-file path fails at import rather than at the lifespan task.** For example, a future `Settings` validator might check the file. | The test asserts `not result["errors"]` first, so an import-time failure shows up as a different, clearly labelled failure. It will not pass as AC 4. |
| R-5 | **Sample drift.** Someone edits `examples/patterns.yaml` for local experiments. | The Task 5 equality test fails. The Task 4 verbatim diff is a one-off check at implementation time, and the drift guard from then on is the policy-equality test (D-G). |

---

## Acceptance Criteria

(Copied from story `STORY-007`)

- [ ] Given `app/main.py`'s lifespan, when the app starts, then `pattern_config.load()` runs beside `authz.load()`, and a `PatternConfigError` propagates: the process does not start.
- [ ] Given `chat_ui/chat_ui/chat_ui.py`, when the Reflex backend starts with the FastAPI app mounted through `api_transformer`, then `pattern_config.load()` runs there too. That mount bypasses `app.main`'s lifespan entirely, which is why `init_db()` and `authz.load()` are already registered in both places (PRD-007).
- [ ] Given `examples/patterns.yaml`, when it is read, then it is the file in PRD Section 6.3 verbatim, comments included, and a test loads it through `pattern_config.load()` and asserts the resulting policy equals the built-in policy. A sample that does not parse is worse than no sample (PRD Section 11, Quality indicators).
- [ ] Given a test that points `PATTERNS_FILE` at a malformed file and starts the app, when startup runs, then it fails with `PatternConfigError`, asserted for both entry points.
- [ ] Given an existing deployment with no `PATTERNS_FILE` set, when it starts, then no file is read, the built-in policy stands, and no existing startup test changes.
- [ ] All tasks completed
- [ ] Full `pytest -q` passes (no lint gate exists in this repository)
- [ ] App starts without error under uvicorn with `PATTERNS_FILE` unset and with it set to `examples/patterns.yaml`
- [ ] Follows existing patterns
