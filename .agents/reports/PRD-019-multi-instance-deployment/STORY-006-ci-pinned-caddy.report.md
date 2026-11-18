---
story: STORY-006
prd: PRD-019
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-006-ci-pinned-caddy.plan.md
epic_branch: epic/PRD-019-multi-instance-deployment
commit: pending
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report - STORY-006: CI installs a pinned Caddy

**Plan**: `.agents/plans/PRD-019-multi-instance-deployment/completed/STORY-006-ci-pinned-caddy.plan.md`
**Commit**: `pending`

## Summary

Added `tests/_caddy.py` (pin constant, `caddy_binary`, `caddy_env`, `free_port`), `tests/test_caddy_pin.py` (three-way pin check, helper unit tests, live version assertion), switched STORY-005's `caddy validate` test to the helper, and added an "Install pinned Caddy" step plus `HARNESS_REQUIRE_CADDY: "1"` to `ci.yml`.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| ci.yml `yaml.safe_load` | OK; step is plain bash |
| (a) CADDY_BIN = local caddy.exe | 22 passed, 0 skipped |
| (b) no caddy, flag unset | 20 passed, 2 skipped (live tests, with reason) |
| (c) no caddy, HARNESS_REQUIRE_CADDY=1 | 20 passed, 2 failed (the two live tests, helper reason) |
| Local `caddy version` | `v2.11.7 h1:...` |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

| File | Action |
|------|--------|
| `tests/_caddy.py` | CREATE |
| `tests/test_caddy_pin.py` | CREATE |
| `tests/test_lb_caddyfile.py` | UPDATE (helper import, validate test, docstring; unused `shutil`/`pytest` imports dropped) |
| `.github/workflows/ci.yml` | UPDATE |

## Deviations from Plan

- The ci.yml static test checks `caddy version` with a regex (`caddy"? version`), since the step runs it by full path (GITHUB_PATH only reaches later steps).
- Dropped the now-unused `import pytest` in `test_lb_caddyfile.py` as well as `shutil`.

## Acceptance Criteria

- [x] CI downloads, SHA-256-verifies, puts Caddy on PATH, sets HARNESS_REQUIRE_CADDY=1 (`test_ci_installs_the_pinned_caddy`; real proof is the CI run after push)
- [x] Helper: CADDY_BIN/PATH, skip, fail under the flag (`test_helper_skips_or_fails_when_caddy_is_absent`, runs (b), (c))
- [x] Version equals the pin, no drift (`test_caddy_version_is_the_pinned_one`, `test_compose_image_tag_is_the_pinned_version`, `test_ci_installs_the_pinned_caddy`)
- [x] Helper validates the Caddyfile (`test_caddy_validate_accepts_the_file`)
