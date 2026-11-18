---
story: STORY-006
prd: PRD-019
slug: ci-pinned-caddy
title: CI installs a pinned Caddy binary; a shared caddy test helper with HARNESS_REQUIRE_CADDY
type: ENHANCEMENT
complexity: small
epic_branch: epic/PRD-019-multi-instance-deployment
created: 2026-11-17
---

# Plan: Pinned Caddy in CI

## Summary

Add `tests/_caddy.py` (one pin constant, a binary resolver that skips or fails, an env builder and a free-port helper), switch STORY-005's `caddy validate` test to it, add `tests/test_caddy_pin.py` that cross-checks the three pins (helper, compose image tag, ci.yml step env) statically and asserts the live binary's version, and add one install step plus `HARNESS_REQUIRE_CADDY: "1"` to `ci.yml`. No app code, no new dependency, no binary committed.

- Story: `.agents/stories/PRD-019-multi-instance-deployment/STORY-006-ci-pinned-caddy.md`
- PRD sections used: §8 (PRD.md:243-254), §11 Quality indicators (PRD.md:318-321), D8, F3
- Systems affected: `.github/workflows/ci.yml`, `tests/` only

## Design Decisions (binding, from the orchestrator)

- `tests/_caddy.py` exposes `PINNED_CADDY_VERSION = "2.11.7"` and `caddy_binary() -> str`: `CADDY_BIN` first, then `shutil.which("caddy")`; absent -> `pytest.skip(reason)`, or `pytest.fail(reason)` when `HARNESS_REQUIRE_CADDY == "1"`.
- `caddy_env(port: int, admin_port: int, **extra) -> dict`: `{**os.environ, PORT, LB_COOKIE_SECRET (test value), CADDY_ADMIN=f"localhost:{admin_port}", **extra}`. Every caddy child needs a distinct admin port (STORY-004 finding; the current test's `localhost:0` is replaced).
- Free port: grep found only a private `_free_port()` at `tests/test_pipeline_concurrency.py:516-519` (bind `127.0.0.1:0`, read the port). Importing a private from another test module is wrong, so `_caddy.py` gets a public `free_port()` of the same 3 lines (the old one is left alone, not our story). STORY-007/008 import it.
- CI step before "Run tests": download `caddy_2.11.7_linux_amd64.tar.gz` from the GitHub release, `echo "<sha>  caddy.tar.gz" | sha256sum -c -`, extract `caddy` into a dir appended to `$GITHUB_PATH`, run `caddy version`. Version and SHA live in the step's `env:` (one place to bump). `HARNESS_REQUIRE_CADDY: "1"` on the Run tests step. Existing steps are not restructured.
- A static test parses `ci.yml` with `yaml.safe_load` and compares its version and SHA with `PINNED_CADDY_VERSION` and a restated SHA literal, so compose, CI and helper cannot drift.
- Decision: the version tests live in a new `tests/test_caddy_pin.py`, not `test_lb_caddyfile.py`. That file is about the Caddyfile contract; the pin is a toolchain concern. `test_lb_caddyfile.py` keeps its own `_LB_IMAGE` literal and the validate test (via the helper).
- The restated SHA literal (`_LINUX_SHA256`) lives in `test_caddy_pin.py`, same reasoning as `test_lb_caddyfile.py:9-11` (do not derive expectations from the file under test).
- `HARNESS_REQUIRE_CADDY` is read at call time, not import time, so tests can monkeypatch it.
- `CADDY_BIN` set but unresolvable falls through to PATH (per the brief); if neither resolves, skip or fail with a reason naming both.

## Skills In Use

None (`.agents/skills/` holds only `frontend-design`; not applicable).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Test module docstring | `tests/test_lb_caddyfile.py:1-20` | cites PRD sections/decisions, says why values are restated, says what skips |
| Restated pin | `tests/test_lb_caddyfile.py:58-62` | `_LB_IMAGE = "caddy:2.11.7@sha256:..."` literal |
| YAML parse | `tests/test_lb_caddyfile.py:106-107` | `yaml.safe_load(path.read_text(encoding="utf-8"))`; `_ROOT = pathlib.Path(__file__).resolve().parents[1]` |
| Test import path | `tests/test_two_instance_smoke.py:84` | `from tests.conftest import ...` (`tests/__init__.py` exists), so `from tests._caddy import ...` |
| Free port | `tests/test_pipeline_concurrency.py:516-519` | bind port 0 on 127.0.0.1 |
| Test to switch | `tests/test_lb_caddyfile.py:219-238` | uses `shutil.which(os.environ.get("CADDY_BIN") or "caddy")` and `CADDY_ADMIN=localhost:0` |
| Workflow style | `.github/workflows/ci.yml:55-61` | `- name:` steps, `#` comments on anything load-bearing |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/_caddy.py` | CREATE | pin constant, `caddy_binary`, `caddy_env`, `free_port` |
| `tests/test_caddy_pin.py` | CREATE | three-way pin check, live version assertion, helper unit tests |
| `tests/test_lb_caddyfile.py` | UPDATE | validate test uses the helper; docstring lines 18-20 updated; drop `shutil` import if unused afterwards (keep `os`: `os.environ.setdefault` still uses it) |
| `.github/workflows/ci.yml` | UPDATE | install step + `HARNESS_REQUIRE_CADDY` |

## Tasks

### Task 1: `tests/_caddy.py`

- **Implement**: docstring citing PRD-019 D8 and §11 ("a missing binary fails in CI, never skips"). `caddy_binary()`: try `os.environ.get("CADDY_BIN")` then `"caddy"` through `shutil.which`; return the first hit; else build `reason` (names `CADDY_BIN`, PATH and `PINNED_CADDY_VERSION`) and `pytest.fail(reason)` if `os.environ.get("HARNESS_REQUIRE_CADDY") == "1"`, otherwise `pytest.skip(reason)`. `caddy_env` and `free_port` as in Design Decisions. Constant `_TEST_COOKIE_SECRET = "test-secret"`.
- **Mirror**: `tests/test_pipeline_concurrency.py:516-519`
- **Validate**: through Task 2.

### Task 2: `tests/test_caddy_pin.py`

Static tests need no binary and run under `-m "not db"`.
- `test_compose_image_tag_is_the_pinned_version`: `docker-compose.lb.yml` `services.lb.image` starts with `f"caddy:{PINNED_CADDY_VERSION}@sha256:"` and the rest is 64 hex chars.
- `test_ci_installs_the_pinned_caddy`: `yaml.safe_load(.github/workflows/ci.yml)`; find the step in `jobs.test.steps` whose `name` contains "Caddy"; assert `env["CADDY_VERSION"] == PINNED_CADDY_VERSION`, `env["CADDY_SHA256"] == _LINUX_SHA256`; its `run` text contains `sha256sum -c`, `GITHUB_PATH`, `caddy version` and the two env names; its index is lower than the "Run tests" step; the Run tests step has `env["HARNESS_REQUIRE_CADDY"] == "1"` (compare as str).
- `test_helper_skips_or_fails_when_caddy_is_absent`: monkeypatch `CADDY_BIN` to a missing path and `PATH` to an empty tmp dir; unset flag raises `pytest.skip.Exception`; `"1"` raises `pytest.fail.Exception`; the message contains "caddy".
- `test_caddy_env_gives_each_child_its_own_admin_port`: PORT, LB_COOKIE_SECRET, `CADDY_ADMIN == "localhost:<admin>"`, extras merged, `os.environ` preserved.
- `test_caddy_version_is_the_pinned_one` (live): `subprocess.run([caddy_binary(), "version"], capture_output=True, text=True, timeout=30)`, `stdout.startswith(f"v{PINNED_CADDY_VERSION} ")`. Skips locally without a binary; fails in CI when missing.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_caddy_pin.py`

### Task 3: switch `test_caddy_validate_accepts_the_file`

- **File**: `tests/test_lb_caddyfile.py:219-238`
- **Implement**: `caddy = caddy_binary()`; `env = caddy_env(8000, free_port())`; the subprocess call stays. Add `from tests._caddy import caddy_binary, caddy_env, free_port`. Update the comment and the module docstring (lines 18-20) to "skipped locally, fails under `HARNESS_REQUIRE_CADDY=1` (PRD-019 D8)". No test is renamed, so nothing goes into `_DELIBERATELY_SUPERSEDED_TESTS`.

### Task 4: `.github/workflows/ci.yml`

- **Implement**: between "Install dependencies" (`ci.yml:57-58`) and "Run tests" (`:60-61`), add a step with a comment (pin matches the compose image tag and `tests/_caddy.py`; bump all three together; the release checksum file is SHA-512 only, so the SHA-256 is ours from STORY-004):
  ```yaml
  - name: Install pinned Caddy
    env:
      CADDY_VERSION: "2.11.7"
      CADDY_SHA256: "727b91701a392de6ebc5027509f548bf39979e5216340d0faed8fa5e69c84f8b"
    run: |
      curl -fsSL --retry 3 -o caddy.tar.gz "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz"
      echo "${CADDY_SHA256}  caddy.tar.gz" | sha256sum -c -
      mkdir -p "$RUNNER_TEMP/caddy-bin"
      tar -xzf caddy.tar.gz -C "$RUNNER_TEMP/caddy-bin" caddy
      echo "$RUNNER_TEMP/caddy-bin" >> "$GITHUB_PATH"
      "$RUNNER_TEMP/caddy-bin/caddy" version
  ```
  The Run tests step keeps `run: pytest -q` and gains `env: HARNESS_REQUIRE_CADDY: "1"`. Do not touch other steps or the libSQL service.
- **Validate**: `.venv/Scripts/python -c "import yaml;yaml.safe_load(open('.github/workflows/ci.yml'))"`. The first real proof is the CI run after the push; the orchestrator reads it before planning STORY-007 (story note).

## End-to-End Tests

- [ ] With the brief's `caddy.exe` as `CADDY_BIN`: `test_caddy_version_is_the_pinned_one` and `test_caddy_validate_accepts_the_file` run and pass (not skipped).
- [ ] No binary (CADDY_BIN unset, caddy confirmed absent from PATH), `HARNESS_REQUIRE_CADDY=1`: those two tests FAIL. Record it.
- [ ] No binary, flag unset: both skip with the reason.
- [ ] CI (orchestrator, after push): `sha256sum -c` passes, `caddy version` prints `v2.11.7 `, no caddy test skips.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 CADDY_BIN="<caddy.exe path>" .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_caddy_pin.py tests/test_lb_caddyfile.py tests/test_caddyfile_routes.py
# then with CADDY_BIN unset and HARNESS_REQUIRE_CADDY=1 (the two caddy tests must fail)
```
`test_untouched_app.py` is not needed (no `app/` file touched).

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 CI downloads, verifies SHA-256, PATH, `HARNESS_REQUIRE_CADDY=1` | 4 | `test_caddy_pin.py::test_ci_installs_the_pinned_caddy`; real proof is the CI run |
| AC2 helper: PATH/CADDY_BIN, skip, fail under strict flag | 1, 2 | `test_caddy_pin.py::test_helper_skips_or_fails_when_caddy_is_absent` |
| AC3 version equals the pinned one; no drift | 2 | `test_caddy_pin.py::test_caddy_version_is_the_pinned_one`, `::test_compose_image_tag_is_the_pinned_version`, `::test_ci_installs_the_pinned_caddy` |
| AC4 helper validates the Caddyfile; skips locally, passes in CI | 3 | `test_lb_caddyfile.py::test_caddy_validate_accepts_the_file` |

Plus: all tasks completed, validation passes, follows existing patterns.
