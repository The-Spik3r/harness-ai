---
story: STORY-008
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-008-startup-guard.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: c924b32
status: COMPLETE
completed: 2026-09-01
---

# Implementation Report — STORY-008: Fail fast and legibly when the database is unreachable or the token is missing

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-008-startup-guard.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: `c924b32`

## Summary

`check_database_reachable()` issues one `SELECT 1` through the existing shared client and turns
whatever the driver says into one of two named failures: `DatabaseUnreachableError`, which points an
operator at `DATABASE_URL`, or `DatabaseAuthError`, which points them at `TURSO_AUTH_TOKEN`. It is
called from the top of `init_db()` — the one function every boot path already calls — so
`app/main.py`'s lifespan, `chat_ui/chat_ui/chat_ui.py`'s import-time call and `scripts/manage_users.py`
are all covered without a line changing at any of them. Messages quote a sanitized
`scheme://host[:port]` and never the configured URL, and the driver's own text is scrubbed of the
credential in both forms it can take before being embedded. `DB_BOOTSTRAP_ENABLED` (default `True`)
gates the guard *and* the schema work, so the Docker builder stage can import the app with no database;
**this story provides that switch, STORY-014 sets it** (see "The STORY-014 handoff" below).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `DatabaseUnreachableError` / `DatabaseAuthError` | `app/db/errors.py` | ✅ |
| 2 | `_safe_endpoint()` and `_redacted()` | `app/db/database.py` | ✅ |
| 3 | `_classify_startup_failure()` + `_AUTH_MARKERS` | `app/db/database.py` | ✅ |
| 4 | `check_database_reachable()`, called from `init_db()` | `app/db/database.py` | ✅ |
| 5 | `DB_BOOTSTRAP_ENABLED: bool = True` | `app/config.py` | ✅ |
| 6 | Flag documented as build-time-only | `.env.example` | ✅ |
| 7 | Unit coverage (19 tests) | `tests/test_db.py` | ✅ |
| 8 | Reflex import path, subprocess style (2 tests) | `tests/test_chat_ui_startup_guard.py` | ✅ |
| 9 | FastAPI lifespan fails at startup (1 test) | `tests/test_main.py` | ✅ |
| 10 | Config coverage for the flag (2 tests) | `tests/test_config.py` | ✅ |
| 11 | Full-module regression + this handoff | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `import app.db.database`, `from app.main import app` | ✅ |
| `tests/test_db.py` | ✅ 83 passed (64 before, 19 new) |
| `tests/test_config.py` | ✅ 26 passed (24 before, 2 new) |
| `tests/test_main.py` | ✅ 10 passed (9 before, 1 new) |
| `tests/test_chat_ui_startup_guard.py` | ✅ 4 passed (2 before, 2 new) |
| Negative control (new tests vs. guard removed) | ✅ all 4 guard-dependent tests fail without it |
| Full suite, per module | ✅ failure set byte-identical to the unmodified tree |
| E2E | ✅ 6/6 |
| Guard cost, measured | ✅ 1.5 ms, one statement |
| `sqlite3` code-level hits in `app/`, `chat_ui/`, `scripts/` | ✅ zero (docstring prose only) |

### The negative control

The guard call inside `init_db()` was replaced with `pass` and the tests that are supposed to depend
on it were re-run:

| Test | Guard removed |
|---|---|
| `test_init_db_fails_fast_against_an_unreachable_endpoint` | **FAILS** |
| `test_lifespan_fails_when_the_database_is_unreachable` | **FAILS** |
| `test_chat_ui_import_fails_when_the_database_is_unreachable` | **FAILS** |
| `test_chat_ui_failure_names_the_endpoint_not_the_credential` | **FAILS** |
| the two pre-existing RBAC bootstrap tests in the same module | pass, as they must |

### Full-suite regression, measured both ways

Every test module was run in its own pytest process (STORY-007's substituted validation for the
pre-existing single-process `STREAM_EXPIRED` breakage, unchanged and untouched here). Five modules
fail; each was re-run against the stashed, unmodified tree and fails **identically** there:

| Module | Changed tree | Unmodified tree |
|---|---|---|
| `tests/test_chat_state.py` | 1 failed, 37 errors | 1 failed, 37 errors |
| `tests/test_pii_badge.py` | 1 collection error (`'chat_ui.chat_ui' is not a package`) | same |
| `tests/test_pii_redaction_integration.py` | 1 failed, 18 errors | same (order-dependent: it passes when it runs after other modules, on both trees) |
| `tests/test_rbac.py` | 1 failed, 15 errors | 1 failed, 15 errors |
| `tests/test_success_metadata_footer.py` | 1 collection error | same |

`tests/test_untouched_app.py`'s 13 provenance guards skip on both trees, so the test-file edits this
story makes do not trip them.

### E2E

| # | Check | Result |
|---|---|---|
| 1 | `init_db()` against `http://127.0.0.1:1` | ✅ exit 1, `DatabaseUnreachableError`, names `DATABASE_URL` and the endpoint, no token |
| 2 | `uvicorn app.main:app` against the same | ✅ exit 3, "Application startup failed", **never bound the port** |
| 3 | `import chat_ui.chat_ui` against the same | ✅ traceback at import, same error class, no token |
| 4 | `uvicorn` against the reachable server | ✅ startup complete, `GET /health` 200 in 2s |
| 4b | The guard's own cost | ✅ **1.5 ms**, one statement |
| 5 | `DB_BOOTSTRAP_ENABLED=false` with no database | ✅ `import chat_ui.chat_ui` succeeds — the `reflex export` case |
| 6 | Database stopped **after** a successful boot | ✅ `check_duplicate()` degraded to `DuplicateCheckError`; an ordinary read raised `StorageError`; **the guard did not re-fire** and its exception never reached a caller |

E2E 6 was run as a real timeline: a container booted against the live server, printed READY, and the
libSQL container was stopped from the host while it waited.

The message an operator actually sees:

```
app.db.errors.DatabaseUnreachableError: Cannot reach the database at http://127.0.0.1:1. The
application will not start: PRD-007 removed the local-file fallback deliberately, so there is
nothing to degrade to. Check DATABASE_URL and that the endpoint is reachable from this host.
Driver said: Hrana: `http error: `error trying to connect: tcp connect error: Connection refused
(os error 111)``
```

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/errors.py` | UPDATE | +44 |
| `app/db/database.py` | UPDATE | +163/-1 |
| `app/config.py` | UPDATE | +15 |
| `.env.example` | UPDATE | +7 |
| `tests/test_db.py` | UPDATE | +229/-1 |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | +82/-1 |
| `tests/test_main.py` | UPDATE | +27 |
| `tests/test_config.py` | UPDATE | +22 |

## The STORY-014 handoff — the answer the story asked for

The story required this to be stated rather than left to ordering: **the Docker-build constraint is
resolved here, by `DB_BOOTSTRAP_ENABLED`, and STORY-014 sets it.**

- The builder stage must add `DB_BOOTSTRAP_ENABLED=false` to the `ENV` block at `Dockerfile:15-17`,
  alongside the `DATABASE_URL=sqlite:///:memory:` placeholder that story already owns replacing.
  None of that stage's `ENV` values reach the final image.
- The build did **not** become dependent on a live database because of this story. `reflex export`
  imports `chat_ui.chat_ui`, which has called `init_db()` at import since long before PRD-007; from
  STORY-006 onward that call reaches a network endpoint. The guard makes the failure legible and
  permanent, it does not introduce it. (The build is in fact broken today for a different reason
  STORY-014 also owns: STORY-005 made `sqlite:///:memory:` a validation error.)
- E2E 5 above proves the escape hatch works: `import chat_ui.chat_ui` succeeds with
  `DATABASE_URL` pointing at a dead port when the flag is `false`.

## Deviations from Plan

**1 — Everything was validated inside a container, as in STORY-006 and STORY-007.** The host runs
Python 3.14 and `libsql==0.1.11` publishes no wheel for it, so nothing in this repo imports on this
machine. Tests, probes and E2E ran in `harness-test:py311` on the `harness-net` Docker network
against the pinned libSQL dev-server image. Environment deviation, not a design one.

**2 — The auth branch is classified from message markers that are unverified against a live Turso
401.** The suite runs against a local libSQL primary, which takes no token and cannot produce one,
and PRD Section 12 makes "no account needed" non-negotiable for the test infrastructure. The markers
(`401`, `unauthorized`, `authentication`, `auth token`, `auth_token`, `authtoken`, `invalid token`,
`expired token`, `permission denied`) are inference, and the code comment says so. The fallback is
deliberately asymmetric — anything unrecognized becomes *unreachable*, never *auth* — so a missed
marker costs an operator one wrong guess instead of sending them to rotate a healthy credential.
**STORY-014's first real deployment is where to confirm the text**; if it differs, adding a marker is
a one-line change. AC2 is therefore satisfied by construction and unit test, not by a live 401.

**3 — E2E 4 needed one active user seeded and PII redaction disabled.** The first attempt failed
because STORY-016's RBAC bootstrap guard refuses to start against an empty `users` table and the
lifespan otherwise loads `en_core_web_lg`. Neither is related to this story's guard; both were
removed from the measurement so that what E2E 4 times is startup against a reachable database.

**4 — `tests/test_db.py`'s AC7 test uses the real `AuditLog` field set.** The plan sketched an
`insert_audit_log(AuditLog(..., status="success"))` call; `AuditLog` has no `status` field (it has
`success`). Corrected to the shape the rest of the module uses.

**5 — One extra sanitizer test beyond the plan's list.** `_safe_endpoint` gained
`test_safe_endpoint_degrades_rather_than_echoing_an_unparseable_url` and
`test_safe_endpoint_keeps_the_port_so_the_message_identifies_the_database`, because "quote the
endpoint" (AC1) and "quote no credential" (AC3) pull in opposite directions and the boundary between
them is worth pinning.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` (+19) | `test_safe_endpoint_drops_query_userinfo_and_path` (3 params), `test_safe_endpoint_keeps_the_port_so_the_message_identifies_the_database`, `test_safe_endpoint_degrades_rather_than_echoing_an_unparseable_url`, `test_redacted_removes_a_token_carried_in_driver_text`, `test_classify_names_the_token_setting_for_an_auth_failure` (5 params), `test_classify_falls_back_to_unreachable` (2 params), `test_no_guard_message_ever_echoes_the_token` (2 params), `test_init_db_fails_fast_against_an_unreachable_endpoint`, `test_guard_issues_exactly_one_extra_statement`, `test_guard_does_not_run_outside_init_db`, `test_bootstrap_disabled_skips_the_guard_and_the_schema` |
| `tests/test_chat_ui_startup_guard.py` (+2) | `test_chat_ui_import_fails_when_the_database_is_unreachable`, `test_chat_ui_failure_names_the_endpoint_not_the_credential` |
| `tests/test_main.py` (+1) | `test_lifespan_fails_when_the_database_is_unreachable` |
| `tests/test_config.py` (+2) | `test_db_bootstrap_enabled_defaults_to_true`, `test_db_bootstrap_enabled_can_be_turned_off_for_the_build` |

## Acceptance Criteria

- [x] An unreachable `DATABASE_URL` fails at startup with a message identifying the database as the cause — E2E 1–3; it does not start and then fail per-request (E2E 2 never bound the port).
- [x] An invalid or expired `TURSO_AUTH_TOKEN` fails at startup with a message naming the setting — `DatabaseAuthError`, unit-tested across the marker set. See Deviation 2 for what is and is not verified.
- [x] No startup failure message contains a token value or credential fragment — `_safe_endpoint()` + `_redacted()`, asserted on both branches with the token in all three places it can hide, and on the real traceback in the subprocess probe.
- [x] The FastAPI app and the Reflex app are both covered — one guard inside `init_db()`, which both already call; proven independently in `tests/test_main.py` and `tests/test_chat_ui_startup_guard.py`.
- [x] Against a reachable database the guard adds no perceptible delay and at most one round trip — measured at 1.5 ms; `test_guard_issues_exactly_one_extra_statement` asserts `statements == ["SELECT 1"]`.
- [x] `tests/test_chat_ui_startup_guard.py` covers the unreachable-database case in the same subprocess style — same `_PYTHONPATH`, `cwd`, and `child_db_env` construction as the existing probe.
- [x] The guard does not re-fire when the database becomes unreachable after a successful start — E2E 6, with the database stopped mid-flight, plus `test_guard_does_not_run_outside_init_db`.
- [x] All tasks completed
- [x] Backend imports and starts without error against a reachable database
- [x] Full suite failure set identical to the unmodified tree's
- [x] Follows existing patterns
