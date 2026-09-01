---
story: STORY-003
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-003-centralize-database-url-fixture.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: eebfc71
status: COMPLETE
completed: 2026-09-01
---

# Implementation Report — STORY-003: Centralize the DATABASE_URL test sites behind one conftest fixture

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-003-centralize-database-url-fixture.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: `eebfc71`

## Summary

`tests/conftest.py` now exists and is the only place in `tests/` that spells a database URL. The 29 hand-rolled sites across 19 files are gone; each file requests the shared fixture instead. Nothing about test behavior changed — the fixtures are still SQLite-backed and `tmp_path`-scoped, every assertion is byte-identical, and no test function was deleted or renamed. What changed is where the URL comes from, so STORY-006 edits two private helpers rather than 19 files while the suite is red.

The fixtures keep the names the suite already spelled (`temp_db`, `uninitialized_db`), so **not one test signature changed** outside the five files that also seed rows — which now override the conftest fixture and delegate to it. The seam is a URL `str`, never a `Path`, and the two consumers that need something else got purpose-built seams: a session-scoped `database_url_factory` for the module-scoped subprocess probes, and a `db_connect(url)` callable for the pre-migration schema builders.

## The fixture surface

| Fixture | Scope | Yields | Patches `settings` | Schema | Consumers |
|---|---|---|---|---|---|
| `database_url` | function | `str` URL | yes | no | the two below |
| `temp_db` | function | `str` URL | yes | `init_db()` | 17 files |
| `uninitialized_db` | function | `str` URL | yes | no | 6 files |
| `database_url_factory` | session | `Callable[[str], str]` | **no** | no | 3 subprocess fixtures |
| `db_connect` | function | `Callable[[str], Connection]` | n/a | n/a | `test_db.py`, `test_rbac.py` |

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Record baseline (7 failed / 1021 passed, 30 grep lines) | — | ✅ |
| 1 | Create the five fixtures; prove the same-name override | `tests/conftest.py`, `tests/test_chat_state.py` | ✅ |
| 2 | Seven single-fixture files | `test_audit_logger`, `test_audit_router`, `test_stats_router`, `test_query_pipeline_authorization`, `test_manage_users_cli`, `test_integration`, `test_identity` | ✅ |
| 3 | The two files also defining `uninitialized_db` | `test_duplicate_checker.py`, `test_auth_dependencies.py` | ✅ |
| 4 | Four remaining seeding files | `test_pii_dedup_isolation`, `test_pii_redaction_integration`, `test_query_router`, `test_main` | ✅ |
| 5 | Seven sites, incl. 4 legacy-schema builders re-signatured to `(connect, url)` | `tests/test_db.py` | ✅ |
| 6 | Three subprocess sites (one not named by the story) | `test_admin_shell`, `test_chat_ui_startup_guard`, `test_render_invariants` | ✅ |
| 7 | `test_rbac.py`, incl. the cross-file legacy helper import | `tests/test_rbac.py` | ✅ |
| 8 | AC-3 sweep | — | ✅ |
| 9 | Order-independence / isolation proof | — | ✅ |
| 10 | Containment (no `app/`, `chat_ui/`, `scripts/`) | — | ✅ |
| 11 | Pinned-suite failures confirmed pre-existing | — | ✅ |
| 12 | Full suite diffed against baseline | — | ✅ |
| + | Contract tests for the new fixtures (Phase 4 requirement) | `tests/test_conftest_fixtures.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Full suite | ✅ 7 failed, 1033 passed — failure set **identical** to baseline |
| `sqlite:///` outside `tests/conftest.py` | ✅ none |
| Per-test isolation (reversed-order runs) | ✅ identical counts both directions |
| Test-function census, all 19 files | ✅ every function preserved |
| Deleted `assert` lines | ✅ zero |
| `app/`, `chat_ui/`, `scripts/` modified | ✅ none |
| `harness_ai.db` written by the probes | ✅ untouched |
| E2E checklist | ✅ 7/7 |

### Pass-count arithmetic

1021 (baseline) − 1 (the removed guard parametrization, see Deviation 2) + 13 (new contract tests) = **1033**. The seven failures are unchanged, node for node.

### The baseline was already red

Recorded because AC 5 says "the same result as before", and before is not green:

- `tests/test_chat_state.py::test_chat_state_holds_no_token_or_role_var` — environmental. Asserts `"_token" in ChatState.__annotations__`; the installed Reflex build reports only `{'is_hydrated', '_reflex_internal_links'}`. Unrelated to the database and failing before this story started.
- Six in `tests/test_untouched_app.py` — PRD-006's containment guard, measuring `git diff` against the pinned baseline `d3e6279`. Earlier work on this branch (including STORY-002's `403b191`) already changed `app/`, the chat modules, and four of the six byte-pinned suites.

Four of those pinned suites — `test_audit_router.py`, `test_stats_router.py`, `test_db.py`, `test_chat_state.py` — hold sites this story had to convert. All four were **already failing**, so this story added no new failure. The other two pinned suites, `tests/test_admin_auth.py` and `tests/test_route_reservations.py`, hold no site and were not opened.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/conftest.py` | CREATE | +118 |
| `tests/test_conftest_fixtures.py` | CREATE | +166 |
| 19 test files | UPDATE | +79 / −210 |

Net: 131 fewer lines of copy-pasted fixture across the suite.

## Deviations from Plan

### 1. A third subprocess site, as the plan predicted (F1) — resolved as planned

`tests/test_render_invariants.py` built its own URL *inside the child* via `tempfile.mkdtemp()`; its `probe` fixture never passed `DATABASE_URL`. It now receives the URL through `env` like the other two, and the child-side assignment is deleted — `app/config.py`'s `BaseSettings` reads the env var with no code in the child. The `from app.config import settings` import stayed, because the child also reads `settings.ADMIN_TOKEN`. The module docstring's paragraph about why the probe must not run in-process is preserved; only its description of the mechanism changed.

### 2. **A second byte-pinning guard the plan did not find, and one parametrization removed**

`tests/test_pii_redaction_integration.py` carries a PRD-003-era guard, `test_pre_epic_test_files_are_unmodified_by_this_epic`, that byte-pins five files against `git merge-base main HEAD`. One of them, **`tests/test_duplicate_checker.py`, holds two of this story's sites** — including the `uninitialized_db` fixture the STORY-002 characterization test depends on. AC 3 (zero `sqlite:///` outside conftest) and that pin cannot both hold.

Resolved by following the file's own documented precedent: PRD-005 faced this exact situation with `tests/test_integration.py`, removed it from the list, and recorded why in a comment above it. `tests/test_duplicate_checker.py` was removed the same way, with a comment stating that only its two fixtures were deleted and not one assertion, docstring, or test function.

**What this costs, stated plainly**: one test node disappears — `test_pre_epic_test_files_are_unmodified_by_this_epic[tests/test_duplicate_checker.py]`. A `--collect-only` diff against the baseline confirms it is the *only* node lost and that none were silently renamed.

**What still holds**: layer 2 of the same guard, `test_no_pre_epic_test_function_was_removed_or_renamed`, walks **every** test file in `tests/` at the merge base and fails if any test function vanished. It is untouched, it passes, and it is the assertion that actually protects against weakening — the byte-pin only protected against the file being opened at all. STORY-006 would have hit this same wall; it now will not.

This is the one judgment call in the story that changed a guard rather than a fixture, and it is worth a reviewer's eye.

### 3. `settings` imports: one removal was wrong and was caught

Six files had their now-unused `from app.config import settings` import removed. In `tests/test_query_router.py` that was a mistake — `settings` is used as a bare `monkeypatch.setattr(settings, ...)` target, which a `settings.` grep does not match. Four tests failed immediately, the import was restored, and every other file was re-audited with a word-boundary grep before proceeding.

### 4. `_empty_users_db` in `test_main.py`

Now requests `temp_db` for its side effect and returns nothing, matching what its four callers already relied on. Per plan F5, the two tests at `test_main.py:31` and `:73` that deliberately run against the developer's real database were **not** touched — they set no URL, and giving them one would change behavior.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_conftest_fixtures.py` | `test_the_fixture_yields_a_url_string_not_a_path`, `test_settings_points_at_the_url_the_fixture_returned`, `test_the_url_is_not_the_configured_default`, `test_isolation_first_test_writes_a_row`, `test_isolation_second_test_sees_an_empty_database`, `test_two_requests_in_one_test_get_one_database`, `test_uninitialized_db_has_no_schema`, `test_uninitialized_db_becomes_usable_after_init_db`, `test_uninitialized_db_also_yields_a_url_string`, `test_factory_yields_a_distinct_url_on_every_call`, `test_factory_does_not_patch_this_process_settings`, `test_db_connect_opens_the_same_database_settings_names`, `test_db_connect_can_build_a_table_init_db_would_not` |

Written against the *contract*, not against SQLite: nothing there opens a file, joins a path, or asserts a scheme, so STORY-006 inherits all 13 unchanged. The isolation pair is deliberately two tests — neither half means anything alone.

## Acceptance Criteria

- [x] **Shared fixture gives an isolated, empty database with `settings.DATABASE_URL` patched; isolation is per-test.** `tests/conftest.py`; proven by `test_settings_points_at_the_url_the_fixture_returned`, the isolation pair, and reversed-order suite runs producing identical counts.
- [x] **The two subprocess sites obtain the URL from the same fixture and pass it through the child environment.** `tests/test_admin_shell.py:709` and `tests/test_chat_ui_startup_guard.py:65` now call `database_url_factory`. A third site, `tests/test_render_invariants.py`, was found and converted the same way — see Deviation 1.
- [x] **`grep -rn "sqlite:///" tests/` hits only `tests/conftest.py`.** Verified. **No test asserts the rejection of a `sqlite:///` URL, so the exemption clause names none** — that assertion arrives with STORY-005.
- [x] **The fixture supports a never-initialized database without a test hand-rolling its own connection.** `uninitialized_db`; the three STORY-002 characterization tests pass with their bodies byte-unchanged.
- [x] **The suite runs with the same result, no assertion weakened or deleted.** Failure set identical node-for-node; zero deleted `assert` lines; every test function preserved across all 19 files. One test node was removed, disclosed in full in Deviation 2.
- [x] **No file under `app/`, `chat_ui/`, or `scripts/` modified.** The commit touches `tests/` and `.agents/` only.
