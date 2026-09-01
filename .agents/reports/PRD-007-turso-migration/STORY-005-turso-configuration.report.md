---
story: STORY-005
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-005-turso-configuration.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: PENDING
status: COMPLETE
completed: 2026-09-01
---

# Implementation Report — STORY-005: Config: TURSO_AUTH_TOKEN, libSQL DATABASE_URL semantics, and no file fallback

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-005-turso-configuration.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: `PENDING` (recorded by the follow-up chore commit, as for STORY-001..004)

## Summary

`DATABASE_URL` is now a required, scheme-validated libSQL endpoint, and `TURSO_AUTH_TOKEN` is required whenever that endpoint is remote. The `sqlite:///harness_ai.db` default is gone — removed, not replaced — so a misconfigured deployment fails at import instead of quietly creating an audit database in an ephemeral container layer. These are the codebase's first pydantic validators; `app/config.py` had none.

The production diff is 75 lines in one file. The story's real content was the blast radius, and it was larger than the plan predicted in one direction and smaller in another. **Larger:** six tests were reaching storage without ever requesting a database fixture, passing on whatever they found in the repo-root `harness_ai.db`. Removing the default turned that latent dependency into six failures, and one of the two files involved is a suite PRD-006 pinned byte-for-byte, so the fix had to be made somewhere else entirely — an autouse fixture in `tests/conftest.py` that now gives *every* test an isolated database whether it asked for one or not. **Smaller:** the plan's fear that a `sqlite:///` fixture URL would start failing never materialized, because `monkeypatch.setattr` assigns to a constructed instance and does not re-run validators, exactly as the plan predicted.

One pre-existing bug was fixed incidentally and is worth flagging: **`pytest -q` could not collect at all in a clean checkout** before this story. `tests/conftest.py` imports `app.config` before any test module's `os.environ.setdefault` prologue runs, so with no `.env` present — which is CI's situation, since `.env` is gitignored and `.github/workflows/ci.yml` sets no `env:` block — `Settings()` raised `ADMIN_TOKEN Field required` during collection. The bootstrap this story had to add for `DATABASE_URL` sets all three, so CI now collects and runs.

## Tasks Completed

| # | Task | File / Target | Status |
|---|------|------|--------|
| 1 | `DATABASE_URL` validated as a libSQL endpoint; `TURSO_AUTH_TOKEN` added | `app/config.py` | ✅ |
| 2 | Both settings documented as endpoint + credential | `.env.example` | ✅ |
| 3 | AC 7's five cases plus AC 4/5/6 coverage | `tests/test_config.py` | ✅ |
| 4 | Session-wide env bootstrap above the `app.config` import | `tests/conftest.py` | ✅ |
| 5 | Child-process preamble and `child_db_env()` helper | `tests/conftest.py` | ✅ |
| 6 | Preamble applied at the three subprocess probes | `tests/test_admin_shell.py`, `tests/test_chat_ui_startup_guard.py`, `tests/test_render_invariants.py` | ✅ |
| 7 | Assertion repaired against the removed default | `tests/test_conftest_fixtures.py` | ✅ |
| 8 | Full-suite verification; declared breakages stated | — | ✅ |
| — | **Added:** isolate the six tests that reached storage without a fixture | `tests/conftest.py`, `tests/test_main.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (valid config) | ✅ `from app.main import app` → OK |
| Full suite, local (`.env` present) | ✅ **1052 passed, 8 failed** — the identical 8 pre-existing failures |
| Full suite, **CI view** (no `.env`, no env vars) | ✅ **1052 passed, 8 failed** — same set. Before this story: **collection error** |
| New failures introduced | ✅ **zero** |
| `tests/test_config.py` | ✅ 24 passed |
| Three subprocess probes | ✅ 154 passed |
| E2E checklist | ✅ 7/7 |
| `app/db/database.py` unmodified | ✅ empty diff |

### Baseline correction

The plan's gate quoted **1017 passed / 7 failed**, taken from STORY-001's report. That figure was measured on `main`; three stories have landed since. The measured baseline on this branch immediately before any edit was **1034 passed / 8 failed**, and that is what the gate was applied against. The eight are unchanged in identity, not merely in count:

```
tests/test_chat_state.py::test_chat_state_holds_no_token_or_role_var
tests/test_pii_dedup_isolation.py::...[app/services/duplicate_checker.py]
tests/test_untouched_app.py::test_no_file_under_app_changed_since_prd_006_began
tests/test_untouched_app.py::test_the_chat_modules_are_unchanged_since_prd_006_began
tests/test_untouched_app.py::test_the_pinned_suites_are_byte_unmodified[tests/test_audit_router.py]
tests/test_untouched_app.py::test_the_pinned_suites_are_byte_unmodified[tests/test_stats_router.py]
tests/test_untouched_app.py::test_the_pinned_suites_are_byte_unmodified[tests/test_db.py]
tests/test_untouched_app.py::test_the_pinned_suites_are_byte_unmodified[tests/test_chat_state.py]
```

All are PRD-006 provenance guards that diff against a pinned baseline and no longer hold now that PRD-006 has merged and PRD-007 has begun. They were failing before this story and fail identically after it.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/config.py` | UPDATE | +72/-3 |
| `.env.example` | UPDATE | +9/-2 |
| `tests/conftest.py` | UPDATE | +80/-3 |
| `tests/test_config.py` | UPDATE | +177/-0 |
| `tests/test_conftest_fixtures.py` | UPDATE | +9/-3 |
| `tests/test_main.py` | UPDATE | +18/-5 |
| `tests/test_admin_shell.py` | UPDATE | +9/-1 |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | +9/-2 |
| `tests/test_render_invariants.py` | UPDATE | +7/-1 |
| **`app/db/database.py`** | **UNCHANGED** | `_db_path()` and `_SQLITE_PREFIX` are STORY-006's to delete |

## Deviations from Plan

1. **Six tests were reaching storage without requesting a database.** Not anticipated by the plan. `tests/test_admin_auth.py::test_incorrect_bearer_token_rejected` (2 params) resolves a wrong bearer token against the `users` table, and four `tests/test_main.py` lifespan tests start the app, whose lifespan calls `init_db()`. With the default gone they hit the placeholder endpoint and `_db_path()` raised. Two of them documented the dependency in a comment — *"the real dev DATABASE_URL these tests run against"* — so this was known and simply never declared. They had been passing against the repo-root `harness_ai.db`, the very file PRD-007 deletes.

2. **The first fix was reverted: `tests/test_admin_auth.py` is a pinned suite.** Adding a `temp_db` fixture parameter to it turned two provenance guards red (`test_untouched_app.py` and `test_pii_redaction_integration.py` both pin that file byte-for-byte). The edit was reverted and the isolation moved into an **autouse fixture in `tests/conftest.py`**, `_never_the_configured_database`, which patches `settings.DATABASE_URL` at a per-test `tmp_path` database for every test. Explicit fixtures still win — pytest instantiates autouse fixtures first, and `database_url` patches over it afterwards. This is the stronger form of the guarantee `conftest.py`'s own docstring already claims, and it required touching no pinned file. `tests/test_main.py` is not pinned and took the fixture directly, which also let two stale comments about the "real dev DATABASE_URL" be corrected.

3. **Two of the plan's Task 3 test cases were wrong as written** and were corrected while implementing:
   - The "unset" case used `Settings(_env_file=None)`, which silences the dotenv source but *not* `os.environ` — where Task 4 had just put a placeholder. It now uses `monkeypatch.delenv`, the idiom the file's existing `test_settings_construct_without_new_env_vars` already uses.
   - The `?authToken=` leak case passed both a valid scheme and a valid token, so nothing raised. It is now its own test with `TURSO_AUTH_TOKEN=""`, which is the actual leak scenario: the credential lives in the URL, validation fails for the *missing setting*, and a message echoing `DATABASE_URL` would print the token while reporting that no token was given.

4. **The plan's pass/fail gate used a stale baseline** (1017/7 from `main`). Re-measured on this branch as 1034/8 and applied against that. See above.

5. **`_scheme_of()` also strips surrounding whitespace** and lowercases for comparison. Not in the plan; a trailing newline in a `.env` value reading as an unknown scheme is a real and confusing failure. Pinned by `test_surrounding_whitespace_is_stripped_not_rejected`.

## Declared breakages (not fixed here, by design)

1. **The Docker image build is red from this commit until STORY-014.** `Dockerfile:17` sets `DATABASE_URL=sqlite:///:memory:` as a build-time placeholder so `reflex export` can import `chat_ui.chat_ui` past Pydantic validation; that value is now a startup error. **STORY-014 owns this in writing** — its AC (line 34) requires the placeholder be "replaced with a value that satisfies the configuration validation from STORY-005", and its technical note (line 45) assigns the `TURSO_AUTH_TOKEN` placeholder to the same block. STORY-014 `depends_on: [STORY-006, STORY-008, STORY-013]`, so the gap spans several stories. The story's technical notes required this be said out loud rather than patched here; this is that statement.
2. **`docker-compose.yml:12`** (`DATABASE_URL: sqlite:////app/data/harness_ai.db`) is the same situation, also STORY-014's (its line 33).
3. **Local dev environments break until their `.env` is updated.** Both `.env` and `chat_ui/.env` on this machine carry `DATABASE_URL=sqlite:///harness_ai.db`; both are gitignored. `python -c "from app.main import app"` now fails against them, and `reflex run` from `chat_ui/` will too. This is the story working as designed — the fix is to set the value `.env.example` now documents — but it will look like a regression to anyone who does not know the story landed.

## Known gaps

- **`http://` is accepted for any host, not just localhost.** The acceptance criteria distinguish schemes, not hosts, so `http://prod.example.com` passes validation with no token. Enforcing locality belongs with a reachability probe; STORY-008's startup guard is the natural home.
- **`app/db/database.py:24-25` still rejects non-`sqlite:///` URLs at query time**, which is now unreachable through configuration and is why the autouse fixture was needed at all. STORY-006 deletes it.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` | `test_remote_endpoint_without_a_token_is_a_startup_error` (×2: `libsql://`, `https://`); `test_local_dev_server_without_a_token_is_accepted`; `test_any_sqlite_url_is_rejected_and_the_message_names_the_replacement` (×3: the default, `Dockerfile:17`'s `:memory:`, `docker-compose.yml:12`'s absolute path); `test_database_url_is_required_with_no_default`; `test_a_valid_remote_pair_constructs`; `test_no_failure_message_ever_echoes_the_token` (×2); `test_a_token_carried_inside_the_url_is_not_echoed_either`; `test_unsupported_scheme_names_the_accepted_ones`; `test_https_is_remote_even_though_it_starts_like_http`; `test_surrounding_whitespace_is_stripped_not_rejected`; `test_env_example_documents_both_turso_vars_with_a_comment`; `test_env_example_carries_no_sqlite_url`; `test_env_example_turso_vars_appear_in_settings_field_order`; `test_env_example_ships_no_token_value` |
| `tests/test_conftest_fixtures.py` | `test_the_url_is_not_the_configured_default` rewritten against the configured endpoint plus `is_required()` |

18 net new tests (1034 → 1052 passing).

## Acceptance Criteria

- [x] `TURSO_AUTH_TOKEN` is declared alongside `OPENROUTER_API_KEY` and `ADMIN_TOKEN`, loaded through the same pydantic-settings `.env` mechanism
- [x] A remote endpoint (`libsql://` or `https://`) with an empty `TURSO_AUTH_TOKEN` fails validation with a message naming the setting
- [x] A local `http://` endpoint with an empty token is accepted
- [x] Any `sqlite:///` value raises, with a message naming the replacement form; never a file fallback, never silently ignored
- [x] `DATABASE_URL` unset fails as a required setting; the default is removed, not replaced (pinned by `is_required()`)
- [x] No failure message contains the token value — including when the token is carried inside the URL
- [x] `tests/test_config.py` covers all five AC 7 cases, plus the scheme table and both `.env.example` halves
- [x] All tasks completed
- [x] Full suite matches the measured baseline with no new failure (and now collects in CI, which it previously could not)
- [x] `app/db/database.py` unmodified
- [x] The Dockerfile / compose breakage is stated above and left to STORY-014
- [x] Follows existing patterns
