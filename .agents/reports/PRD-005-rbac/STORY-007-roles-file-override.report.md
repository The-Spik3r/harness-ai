---
story: STORY-007
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-007-roles-file-override.plan.md
epic_branch: epic/PRD-005-rbac
commit: 9769412
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-007: Role matrix loaded from RBAC_ROLES_FILE at startup

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-007-roles-file-override.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: `9769412`

## Summary

Added `authz.load()` to `app/services/authz.py`: when `RBAC_ROLES_FILE` is set, it reads the path as JSON at startup and wholesale-replaces the module's `ROLE_PERMISSIONS` dict — no merge, so a permission the file omits is a denial rather than an inherited grant. An empty `RBAC_ROLES_FILE` (the default) is a no-op; the built-in STORY-006 matrix stands and no file is touched. A missing file, unreadable file, malformed JSON, or a JSON matrix granting a permission name outside the five known constants all raise a new `AuthzConfigError` naming the file and the underlying error, aborting startup instead of silently falling back to the default. `load()` is wired into both `app/main.py`'s `lifespan` (next to `pii_redactor.load()`) and `chat_ui/chat_ui/chat_ui.py` via `app.register_lifespan_task(...)`, replicating the exact dual-registration pattern PRD-002/PRD-003 established for `pii_redactor.load()` — Reflex's `api_transformer` bypasses `app.main`'s own lifespan, so skipping the chat_ui registration would leave the chat UI enforcing a different matrix than the API.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add `AuthzConfigError`, `_KNOWN_PERMISSIONS`, `load()` | `app/services/authz.py` | ✅ |
| 2 | Add `load()` test coverage for all 5 ACs | `tests/test_authz.py` | ✅ |
| 3 | Wire `authz.load()` into `app/main.py`'s lifespan | `app/main.py` | ✅ |
| 4 | Add lifespan test proving `authz.load()` runs | `tests/test_main.py` | ✅ |
| 5 | Register `authz.load` as a chat_ui lifespan task | `chat_ui/chat_ui/chat_ui.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`app.main`) | ✅ |
| chat_ui import (`chat_ui.chat_ui`) | ✅ |
| Tests (`tests/test_authz.py`) | ✅ (28 passed) |
| Tests (`tests/test_main.py`) | ✅ (5 passed) |
| Tests (`tests/test_chat_components_import.py`) | ✅ (4 passed) |
| Full suite (`tests/`) | ✅ (341 passed) |
| E2E | ✅ (5/5) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/authz.py` | UPDATE | +42/-0 |
| `app/main.py` | UPDATE | +2/-1 |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | +5/-1 |
| `tests/test_authz.py` | UPDATE | +99/-1 |
| `tests/test_main.py` | UPDATE | +14/-0 |
| `.agents/plans/PRD-005-rbac/completed/STORY-007-roles-file-override.plan.md` | CREATE (archived plan) | +454 |

## Deviations from Plan

One deviation, discovered during test validation:

- **Error messages drop `!r` around the file path.** The plan specified `f"Failed to read RBAC_ROLES_FILE {path_str!r}: {exc}"` (and the parse/unknown-permission equivalents). On Windows, `repr()` of a backslash-heavy path doubles every backslash in the string, so `str(roles_file) in str(exc_info.value)`-style assertions fail even though the file is correctly named in the message. Switched to plain interpolation with manual quotes — `f"Failed to read RBAC_ROLES_FILE '{path_str}': {exc}"` — which is platform-independent and equally readable. All three `AuthzConfigError` messages (unreadable, malformed, unrecognized permission) use this form.

No other deviations. All five tasks implemented exactly as planned, including the `_reset_role_permissions` fixture and the `try/finally` restore in `test_main.py` to avoid the module-global (`authz.ROLE_PERMISSIONS`) leaking a custom matrix into other tests in the same session.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_authz.py` | `test_load_is_noop_when_roles_file_unset`, `test_load_replaces_matrix_wholesale_from_valid_file`, `test_load_raises_on_malformed_json`, `test_load_raises_on_missing_file`, `test_load_raises_on_unrecognized_permission`, `test_authorize_does_not_read_file_per_call` |
| `tests/test_main.py` | `test_lifespan_loads_roles_file_before_serving_requests` |

## Acceptance Criteria

- [x] Given `RBAC_ROLES_FILE` is empty, when the app starts, then the built-in matrix is used and no file is read
- [x] Given a valid JSON matrix, when the app starts, then it fully replaces the built-in matrix — no merge, so an omitted permission is a denial
- [x] Given a malformed or unreadable file, when the app starts, then startup fails with a message naming the file and the parse error, rather than silently falling back to the default
- [x] Given a file granting an unrecognized permission name, when it loads, then startup fails listing the unknown name
- [x] Given the file loads, when it happens, then it happens once at startup, never per request
