---
story: STORY-021
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-021-two-instance-and-flag-off-smoke.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: 9e0dafc
status: COMPLETE
completed: 2026-09-07
---

# Implementation Report — STORY-021: Two instances serve one session, and CHAT_HISTORY_ENABLED=false writes nothing

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-021-two-instance-and-flag-off-smoke.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `9e0dafc`

## Summary

Two of PRD Section 11's functional requirements were prose; both are now tests, and **no production code changed**.

`tests/test_two_instance_smoke.py` gained the session surface. Its two long-lived `subprocess.Popen` children each build their own `_shared_client()` in their own interpreter, so a transcript written through instance A and read back through instance B *is* the "separate, freshly constructed client, not the writing one" that PRD-007 STORY-006 named as Risk 1's mitigation — a stronger instrument than the story asked for, and the reason it could absorb a second epic without a second harness. Three new tests: a seven-kind transcript round trip compared field for field, a delete that lands on the instance that did not create the row, and a `session_id` refused with `403` on the instance that never saw it created.

`tests/test_history_off_integration.py` is new. It drives the **application** with `CHAT_HISTORY_ENABLED=false` — a full send through `ChatState` and `POST /query` through `TestClient` — where `tests/test_chat_sessions.py` drives only the service. Every "nothing was read" claim is carried by a `_Tripwire` that raises on attribute *lookup*, never by an empty return value: an empty database returns empty either way.

**Each guard was proven red before being trusted green.** Three negative controls were run against the real production modules and reverted (see Validation Results).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Session surface on the child instance: seven handlers, all through `chat_sessions` | `tests/test_two_instance_smoke.py` | ✅ |
| 2 | `do_query` carries an optional `session_id`; `do_rows` projects `session_id` and `error_message` | `tests/test_two_instance_smoke.py` | ✅ |
| 3 | AC 1 + AC 2 — transcript written on A reads back whole on B | `tests/test_two_instance_smoke.py` | ✅ |
| 4 | AC 3 — deleted on B, gone from both tables on A, audit trail unchanged | `tests/test_two_instance_smoke.py` | ✅ |
| 5 | AC 7 — a foreign `session_id` is 403 on the other instance | `tests/test_two_instance_smoke.py` | ✅ |
| 6 | Module docstring and a sixth `_INVARIANTS` entry | `tests/test_two_instance_smoke.py` | ✅ |
| 7 | The flag-off module's frame: docstring, fixtures, `_Tripwire`, `_Recording` | `tests/test_history_off_integration.py` | ✅ |
| 8 | AC 4 — a full send writes no transcript; response and audit row unchanged | `tests/test_history_off_integration.py` | ✅ |
| 9 | AC 5 — four read paths reach the database module for nothing at all | `tests/test_history_off_integration.py` | ✅ |
| 10 | AC 6 — the flag flipped back resumes persistence, issuing no DDL | `tests/test_history_off_integration.py` | ✅ |
| 11 | AC 8 — the whole suite, offline | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| `chat_ui` import | ✅ |
| `tests/test_two_instance_smoke.py` | ✅ 10 passed |
| `tests/test_history_off_integration.py` | ✅ 9 passed |
| Full suite, `TURSO_AUTH_TOKEN` unset | ✅ 1680 passed in 123s |
| No production code changed (`git diff -- app chat_ui`) | ✅ empty |
| E2E checklist | ✅ 7/7 |

### Negative controls — every new guard was watched fail

| Control | Sabotage | Result |
|---------|----------|--------|
| AC 1/AC 2 | `_row_to_stored_message` returns `pii_entities=None` | ✅ red: `{'pii_entities': None} != {'pii_entities': 'EMAIL_ADDRESS,PERSON'}` |
| AC 5 | the `CHAT_HISTORY_ENABLED` guard deleted from `chat_sessions.list_for` | ✅ red: `a read path reached database.list_chat_sessions with CHAT_HISTORY_ENABLED off` |
| AC 3 | `delete_chat_session`'s message delete removed, orphaning the rows | ✅ red on `counts["messages"] == 0` **while the owner-scoped `transcript` read still returned empty** — confirming both reads earn their place |

All three sabotages were reverted with `git checkout --`; `git status --short -- app chat_ui` is clean and neither file contains the marker.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_two_instance_smoke.py` | UPDATE | +406/-5 |
| `tests/test_history_off_integration.py` | CREATE | +525 |

## Deviations from Plan

1. **Test counts in the plan's validation steps were estimates and were wrong.** The smoke module held 7 tests, not 8, so it now holds 10 rather than the predicted 12. Nothing else about those steps changed; the counts in this report are the measured ones.
2. **`do_rows` also projects `error_message`, which the plan did not name.** Task 5 asserts the audited 403 is visible across instances, and `success is False` plus a `session_id` does not distinguish a foreign-session refusal from any other failed send. The exact detail string (`app/routers/query.py:15`) is what makes that assertion specific.
3. **The flag-off module has two fixtures where the plan described one.** `history_off` sets the flag only; `tripwired` sets it and installs the stand-in. They cannot be one: the AC 4 tests need a real database to count rows on, and a tripwire would make "no row was written" unobservable. The plan anticipated the tension in Task 7's wording but named a single fixture.
4. **Negative control 3 was reframed.** The plan proposed widening `delete_chat_session`'s predicate, then noted no test here should change — an assertion about nothing happening. Removing the message delete entirely is the sharper control: it distinguishes the two reads AC 3 asks for, showing the raw-table count catching an orphan the owner-scoped read cannot see.
5. **AC 6 asserts `restored[0].kind == "assistant"`, not a user bubble first.** The first send appends the user bubble *before* the lazy create, so it has no session to be filed under — inherited from STORY-014 and recorded in STORY-015's Deviations. The resumed send's transcript therefore starts at its outcome bubble. This is existing, documented behaviour, not a regression this story found.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_two_instance_smoke.py` | `test_a_transcript_written_on_one_instance_reads_back_whole_on_the_other`, `test_a_session_deleted_on_one_instance_is_gone_from_both_tables_on_the_other`, `test_a_session_owned_by_another_user_is_refused_on_the_other_instance` |
| `tests/test_history_off_integration.py` | `test_a_full_send_with_history_off_writes_no_session_and_no_message`, `test_post_query_with_history_off_writes_no_transcript_row`, `test_the_response_and_the_audit_row_are_what_they_were_with_history_on`, `test_login_reads_no_session_and_no_transcript_when_history_is_off`, `test_selecting_a_session_reads_nothing_when_history_is_off`, `test_retry_sessions_reads_nothing_when_history_is_off`, `test_post_query_consults_no_row_for_a_supplied_session_id_when_history_is_off`, `test_no_read_path_touches_the_database_module_when_history_is_off`, `test_persistence_resumes_when_the_flag_is_flipped_back` |

## Acceptance Criteria

- [x] A session created and written through one client is read back in full through a **separate, freshly constructed** client — instance B, a different process with a different `_shared_client()`, never the writing one.
- [x] Every message matches in order and in every field, including the verdict metadata — seven kinds, every optional field set to a non-default value so a dropped column cannot hide behind a default; only the store-stamped `created_at` and `id` are excluded, and `id` is separately asserted present, unique and ascending.
- [x] A session deleted on instance B is gone from both tables when instance A reads it, and `count_audit_logs()` is unchanged — with the surviving row identified by the `session_id` it names, so a delete-and-tombstone would not pass.
- [x] With `CHAT_HISTORY_ENABLED=false` a full end-to-end send leaves `chat_sessions` and `chat_messages` empty, writes the audit row as normal, and returns an unchanged response — proven by sending the same prompt under both flag states and comparing body and audit row field for field.
- [x] With the flag off the database module is not called at all on the read paths — login, session select, rail retry and `POST /query`'s ownership check, each against `_Tripwire`, plus one test driving all four so a fifth path added later fails here.
- [x] Flipped back to `true`, persistence resumes with no restart-time migration (`init_db()` is deliberately not called, and no `ALTER`/`CREATE`/`DROP` is issued) and no error about missing rows.
- [x] A `session_id` created by user A is `403` when user B sends it to `POST /query` against the second instance — with the owner's `200` on the same id and the same instance proving the refusal is about ownership rather than about an id instance B has not seen.
- [x] The suite runs offline with no Turso account: 1680 passed with `TURSO_AUTH_TOKEN` unset, against the local libSQL dev server `tests/conftest.py` provisions.
- [x] All tasks completed
- [x] No production code changed
- [x] Full suite passes
- [x] Follows existing patterns
