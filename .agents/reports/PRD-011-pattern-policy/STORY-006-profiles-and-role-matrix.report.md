---
story: STORY-006
prd: PRD-011
plan: .agents/plans/PRD-011-pattern-policy/completed/STORY-006-profiles-and-role-matrix.plan.md
epic_branch: epic/PRD-011-pattern-policy
commit: a75462e
status: COMPLETE
completed: 2026-09-22
---

# Implementation Report — STORY-006: Profiles and the role inspection matrix

**Plan**: `.agents/plans/PRD-011-pattern-policy/completed/STORY-006-profiles-and-role-matrix.plan.md`
**Epic Branch**: `epic/PRD-011-pattern-policy`
**Commit**: `a75462e`

## Summary

`app/services/pattern_config.py` now judges profiles as well as parsing them. The changes:

- `Profile.roles` is typed `Mapping[Role, Action]`. `Role` is imported from `app/models/messages.py`, and `Action = Literal["block", "flag"]`.
- `roles:` is a **required** profile key and is validated at load: shape (a non-empty mapping), role vocabulary (`get_args(Role)`), then action vocabulary.
- `load()` checks that `PATTERN_PROFILE_DEFAULT` names a profile the policy defines.
- `get_profile(name)` is new.

Like STORY-002 to STORY-005, nothing in production calls this code yet. STORY-007 registers `load()`, and STORY-008 is the first caller of `get_profile()`.

Two parts of the diff are worth reading closely:

- **The default check runs on both of `load()`'s paths.** With a file, it runs after profiles parse and before `_policy` is rebound, so a bad default leaves the previous policy in force, like every other rule. With `PATTERNS_FILE` empty, it runs against `BUILT_IN_POLICY` before the early return and still reads no file (a spy on `Path.read_text` asserts this). If it ran only on the file path, `PATTERN_PROFILE_DEFAULT=nope` would boot cleanly and fail on the first request, the request-time failure PRD Section 2 forbids.
- **"Not inspected" means absent, and the tests check absence.** The Section 6.4 matrix is asserted in 8 parametrized cells. The four "not inspected" cells assert `role not in roles`, not `.get(role) is None`, because a key mapped to a falsy value would pass the weaker check.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Role and action vocabulary; narrow `Profile.roles`; `Profile` docstring (the `system` cell and the RBAC asymmetry) | `app/services/pattern_config.py` | ✅ |
| 2 | Validate `roles:` in `_parse_profiles` via `_parse_roles`; `roles` required | `app/services/pattern_config.py` | ✅ |
| 3 | `PATTERN_PROFILE_DEFAULT` cross-check in `load()` on both paths | `app/services/pattern_config.py` | ✅ |
| 4 | `get_profile(name)`; module and `PatternConfigError` docstrings | `app/services/pattern_config.py` | ✅ |
| 5 | Adapt STORY-005 fixtures; rewrite the boundary test in place; six new malformed-file rows | `tests/test_pattern_config.py` | ✅ |
| 6 | New profile suite, AC 1–5 plus the docstring check | `tests/test_pattern_profiles.py` | ✅ |
| 7 | Full regression | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ after every task |
| Frontend lint | N/A (the repo has no `frontend/`; the Reflex UI is not touched) |
| Pattern suites (`test_pattern_profiles.py` + `test_pattern_config.py`) | ✅ 109 passed (46 + 63) |
| Full suite (`pytest tests/`) | ✅ 2463 passed, 26 skipped, 0 failed (204 s) |
| `tests/test_config.py` unchanged | ✅ not in the diff; passes |
| App boot + `GET /health` | ✅ 200 `{"status":"ok"}` (see the E2E note) |
| E2E | ✅ 7/7 |

**E2E checks run** (plan § End-to-End Tests):

1. Both settings unset, then `load()`: profiles are `['chat', 'code']` ✅
2. `PATTERN_PROFILE_DEFAULT=nope` with no file: `PatternConfigError: PATTERN_PROFILE_DEFAULT 'nope' names a profile the built-in policy does not define (defined profiles: chat, code); PATTERNS_FILE is unset` ✅
3. A YAML file with `roles: {admin: block}`: `... profile 'chat': roles: unknown role 'admin' (expected one of: assistant, system, tool, user)` ✅
4. A YAML file with `roles: {}`: `... profile 'chat': roles is empty (...)` ✅
5. `git grep '"assistant"' app/services/pattern_config.py` finds nothing, so there is no second role literal ✅
6. There are no changes under `app/routers` or `app/models`, and no `profile` in the routers or `schemas.py` ✅
7. `uvicorn app.main:app` boots and `/health` returns 200 ✅

**E2E note:** the first boot attempt failed at `authz.check_bootstrap()` with `RbacNotBootstrappedError`, because the local libSQL database has no users and RBAC is on. That failure is not caused by this story: the lifespan does not reach any pattern code until STORY-007. The boot was repeated with `RBAC_ENABLED=false`, and with `DATABASE_URL` pointed at the local dev server rather than the remote Turso URL in `.env`. The same thing happened with E2E 1: the first run exported `PATTERN_PROFILE_DEFAULT=""`, which STORY-004's settings validator rightly rejects. With the variable truly unset, it passed.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/pattern_config.py` | UPDATE | +139/-33 |
| `tests/test_pattern_config.py` | UPDATE | +86/-19 |
| `tests/test_pattern_profiles.py` | CREATE | +401 |
| `.agents/plans/PRD-011-pattern-policy/completed/STORY-006-profiles-and-role-matrix.plan.md` | CREATE (archived plan) | +367 |

## Deviations from Plan

- **The `_check_default_profile` signature** is `(profiles, source, note="")`. The `"; PATTERNS_FILE is unset"` suffix is passed as `note`. The plan left the choice open ("via a `suffix` parameter or by building `source` accordingly").
- **More AC 2 cases in the new module** than the plan listed: `unknown-role-wrong-case` (`User: block`), `unknown-action-after-a-good-role` (the first offender is reported after a valid role) and `roles-a-string`. They pin the exact-match and declared-order behaviour documented in `_parse_roles`.
- **A dedicated `test_missing_roles_key_fails_load`** in the new module, alongside the `missing-roles` row in `test_pattern_config.py`'s table. AC 2 is covered in depth in one place, as the plan intended.
- **The rewritten boundary test also asserts `get_policy() is BUILT_IN_POLICY`** after the failed load, in addition to the message.

There were no scope deviations. No route, request field or per-endpoint setting was added (D-K).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pattern_profiles.py` (new, 46 cases) | AC 1: `test_built_in_matrix_cell` ×8, `test_the_matrix_has_no_cells_beyond_section_6_4`, `test_built_in_profile_lists`, `test_every_built_in_role_and_action_is_in_the_vocabulary`. AC 2: `test_bad_roles_map_fails_load_naming_the_offender` ×8, `test_missing_roles_key_fails_load`, `test_every_role_and_action_is_accepted` ×8, `test_roles_keep_declared_order`. AC 3: `test_built_in_profile_lists_are_the_policys_own_objects` ×2, `test_undefined_list_is_a_startup_error_not_a_key_error`. AC 4: `test_default_naming_an_undefined_profile_fails_load_from_a_file`, `..._without_a_file`, `test_default_code_loads_against_the_built_in_policy`, `test_default_may_name_any_profile_the_file_defines`, `test_get_profile_returns_the_policys_profile` ×2, `test_get_profile_unknown_name_raises_the_same_error_type`, `test_get_profile_reads_the_loaded_policy_not_the_built_in_one`. AC 5: `test_pattern_config_uses_the_messages_role`, `test_every_role_member_is_an_accepted_roles_key` ×4. Technical Notes: `test_profile_docstring_states_absent_means_not_inspected` |
| `tests/test_pattern_config.py` (57 → 63) | New `_MALFORMED_CASES` rows: `missing-roles`, `empty-roles`, `null-roles`, `roles-not-a-mapping`, `unknown-role`, `unknown-action`. These also feed `test_every_malformed_case_names_the_file_path`. `test_roles_are_stored_but_not_validated_here` is rewritten in place as `test_roles_are_validated_at_load`. Fixtures adapted, each with a `PRD-011 STORY-006` comment: the autouse `_default_profile_is_chat`, `test_load_compiles_every_pattern_once_at_load`, `test_declared_order_survives_parsing`, `_REGEX_FILE` and the `undefined-list-in-profile` row |

## Notes for later stories

- **STORY-007:** once `load()` is in both lifespans, a deployment whose `PATTERN_PROFILE_DEFAULT` names no defined profile fails at boot. That is intended, and worth one assertion in the lifespan test.
- **STORY-008:** `pattern_detector` cannot import `Action` or `Profile` from `pattern_config`, because `pattern_config` imports `pattern_detector`. `PatternHit.action` and `inspect(messages, profile)` need a deliberate choice: move the `Action` literal down into `pattern_detector`, or type `profile` structurally. `get_profile()` takes a name only; resolving `profile=None` to `settings.PATTERN_PROFILE_DEFAULT` is `run_conversation`'s job.

## Acceptance Criteria

- [x] Given the built-in policy, when its profiles are read, then `chat` is `lists: [injection, keywords]`, `roles: {user: block}` and `code` is `lists: [injection]`, `roles: {user: block, tool: flag}`: the matrix in PRD Section 6.4, asserted cell by cell, including the four "not inspected" cells.
- [x] Given a profile's `roles:` map, when it names a role outside `Literal["system", "user", "assistant", "tool"]` or an action outside `block | flag`, then `load()` raises `PatternConfigError` naming the profile, the key and the allowed values. An empty `roles:` map is likewise an error (PRD 9.2 T5).
- [x] Given a profile, when it is built, then its `lists` are resolved to `PatternList` objects at load time, so an undefined list name is a startup error and can never surface as a request-time `KeyError`.
- [x] Given `PATTERN_PROFILE_DEFAULT` naming a profile the loaded policy does not define, when `load()` runs, then it raises `PatternConfigError` naming the setting, the missing profile and the profiles that do exist. Given `get_profile("nope")`, then it raises the same error type.
- [x] Given `Role` in `app/models/messages.py`, when the role vocabulary is needed, then it is imported from there. This story introduces no second role literal, and a test asserts every member of that `Literal` is an accepted `roles:` key.
