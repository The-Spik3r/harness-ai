---
story: STORY-007
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-007-ownership-signature-guard.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: c2b093b
status: COMPLETE
completed: 2026-09-03
---

# Implementation Report — STORY-007: tests/test_session_ownership.py, the ownership rule asserted against signatures

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-007-ownership-signature-guard.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `c2b093b`

## Summary

One new test module, `tests/test_session_ownership.py` (27 cases), which **discovers** the session/message surface instead of listing it: every public function defined in `app/db/database.py` whose name contains `_chat_session` or `_chat_message` (nine today), and every public function defined in `app/services/chat_sessions.py` (eight today). Over the store it asserts `user_id` is present, undefaulted and annotated `str`; over the service it asserts `identity: Identity` is first and no bare `user_id` leaks back out. Both surfaces are then driven with a second real user's credential — reads must return `None` / `[]` / `False` / `0`, writes must leave both transcript tables byte-identical, and a refused delete must leave `count_audit_logs()` and the owner's transcript alone.

**No production code changed.** No signature had to move: the surface STORY-004, STORY-005 and STORY-006 shipped already satisfies the rule in full, which is the outcome this story hoped for rather than the one it was written to force.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Module docstring, imports, discovery helpers | `tests/test_session_ownership.py` | ✅ |
| 2 | Census tests — the floor under the discovery | `tests/test_session_ownership.py` | ✅ |
| 3 | AC 1 — undefaulted `user_id` on every discovered store function | `tests/test_session_ownership.py` | ✅ |
| 4 | AC 3 — `Identity` first on every discovered service function | `tests/test_session_ownership.py` | ✅ |
| 5 | Real credentials, call tables, coverage tests | `tests/test_session_ownership.py` | ✅ |
| 6 | AC 4 — every read path driven with a foreign credential | `tests/test_session_ownership.py` | ✅ |
| 7 | AC 5 — every write path, row counts and full rows unchanged | `tests/test_session_ownership.py` | ✅ |
| 8 | AC 6 — `count_audit_logs()` across a refused delete | `tests/test_session_ownership.py` | ✅ |
| 9 | AC 2 — the red proof, twice, then reverted | `app/db/database.py`, `app/services/chat_sessions.py` (temporary) | ✅ |
| 10 | Neighbours, full suite, offline property | — | ✅ |
| 11 | Report and commit | `.agents/` artifacts | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `pytest tests/test_session_ownership.py -q` | ✅ 27 passed |
| Neighbours (`test_chat_sessions`, `test_rbac`, `test_db`, `test_identity`) | ✅ 290 passed |
| Full suite | ✅ 1325 passed, 7 failed — the same 7 that fail without this file (see below) |
| Offline (no `.env`, no `TURSO_*`) | ✅ 27 passed |
| `git diff -- app/ chat_ui/` | ✅ empty |

### The 7 full-suite failures are pre-existing and not this story's

All 7 live in `tests/test_untouched_app.py` and are the same 7 STORY-001, STORY-002 and STORY-003 each recorded: PRD-006-scoped provenance guards asserting files are unchanged since PRD-006's pinned baseline `d3e6279`, which PRD-007 and PRD-008 have legitimately changed since. Measured rather than assumed, by the precedent those reports set:

- `git stash push -u -- tests/test_session_ownership.py`, full suite → **7 failed, 1298 passed**
- stash popped, full suite → **7 failed, 1325 passed**
- New-failure set: **empty**. Pass delta: **+27**, exactly the cases added here.

The libSQL dev server was restarted before each measured run: an intervening run produced 973 fixture errors, which is the known degradation of the dev container under repeated suites and not a signal about any code.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_session_ownership.py` | CREATE | +559 |
| `.agents/plans/PRD-008-chat-sessions/completed/STORY-007-ownership-signature-guard.plan.md` | CREATE (archived) | plan |
| `.agents/reports/PRD-008-chat-sessions/STORY-007-ownership-signature-guard.report.md` | CREATE | this file |
| `.agents/stories/PRD-008-chat-sessions/STORY-007-ownership-signature-guard.md` | UPDATE | frontmatter |
| `.agents/PRDs/PRD-008-chat-sessions/index.md` | UPDATE | status + links |

Nothing under `app/` or `chat_ui/`.

## AC 2 — the red, observed twice and then removed

**Store probe.** `def list_chat_messages_for_everyone(session_id: str) -> list` appended to `app/db/database.py`. Three tests went red:

```
FAILED test_every_discovered_store_function_requires_an_undefaulted_user_id
    AssertionError: list_chat_messages_for_everyone names no owner
    assert 'user_id' in mappingproxy(OrderedDict([('session_id', <Parameter "session_id: str">)]))
FAILED test_the_store_call_table_covers_every_discovered_function
    At index 6 diff: 'list_chat_sessions' != 'list_chat_messages_for_everyone'
FAILED test_the_read_and_write_partitions_cover_the_whole_discovered_surface
    Extra items in the left set: 'list_chat_messages_for_everyone'
```

**Service probe.** `def purge(session_id: str) -> bool` appended to `app/services/chat_sessions.py`. Three tests went red:

```
FAILED test_every_discovered_service_function_takes_an_identity_first
    AssertionError: purge does not take identity first
    assert 'session_id' == 'identity'
FAILED test_the_service_call_table_covers_every_discovered_function
    At index 6 diff: 'rename' != 'purge'
FAILED test_the_read_and_write_partitions_cover_the_whole_discovered_surface
    Extra items in the left set: 'purge'
```

Both probes were removed with `git checkout --`; `git diff -- app/ chat_ui/` is empty and the module is green again at 27 passed.

## Deviations from Plan

1. **`test_omitting_user_id_is_a_type_error_on_every_discovered_function` did not go red on the store probe, and correctly so.** The plan predicted it would. It asserts that calling each discovered function with no arguments raises `TypeError`, and `list_chat_messages_for_everyone()` does raise one — it has a required `session_id`. The test is a statement about *requiredness*, not about `user_id` specifically; the `user_id`-specific claim is the signature test beside it, which did fail. Nothing was changed in response: widening this test to inspect the exception message would make it a worse version of the test that already covers the case.

2. **The call tables became module-level dicts (`_STORE_SHAPES`, `_SERVICE_SHAPES`) rather than functions holding a local dict.** The plan's `_call_store(name, ...)` shape was mirrored from `tests/test_chat_sessions.py:1059`, where the table is local. Here the coverage tests need to read the table's *keys*, and a local dict can only be reached by calling the function — which would have meant driving every function against the database merely to discover whether a call shape existed, including `create_chat_session`, which would have written a row as a side effect of a structural test. The thin `_call_store` / `_call_service` wrappers are kept so the drives read the same as the precedent.

3. **One test was added beyond the plan: `test_the_read_and_write_partitions_cover_the_whole_discovered_surface`.** AC 4 and AC 5 ask different questions of reads and of writes, so the drives are split by a pair of name tuples — and a hand-written list of names is precisely what this file exists to distrust. The partitions are therefore checked against the discovery too: every discovered function must be a read, a write, or a named exemption. It is the third test that went red on both probes.

4. **Two control tests were added: `test_the_owner_still_reads_everything_a_stranger_could_not` and `test_the_owners_own_writes_still_land`.** Every foreign-credential assertion in this file is satisfied by a store that returns nothing to *anyone* and writes nothing for *anyone*. Without the controls the suite could go green on a completely broken store, which would be the same vacuous-pass failure the census tests exist to prevent, one layer up.

5. **AC 5's "byte-identical" is asserted as full row tuples, not only counts.** The AC names counting, and counting alone would pass a foreign `rename` that changed a title without changing the number of rows. Both tables are snapshotted whole and compared; the counts are asserted as well, so the criterion is met literally and the stronger claim is met too.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_session_ownership.py` | `test_the_store_surface_is_discovered_and_not_empty`, `test_the_service_surface_is_discovered_and_not_empty`, `test_every_discovered_store_function_requires_an_undefaulted_user_id`, `test_omitting_user_id_is_a_type_error_on_every_discovered_function`, `test_every_discovered_service_function_takes_an_identity_first`, `test_no_discovered_service_function_accepts_a_bare_user_id`, `test_the_store_call_table_covers_every_discovered_function`, `test_the_service_call_table_covers_every_discovered_function`, `test_the_read_and_write_partitions_cover_the_whole_discovered_surface`, `test_every_store_read_path_returns_nothing_for_a_foreign_credential` (×4), `test_every_service_read_path_returns_nothing_for_a_foreign_credential` (×3), `test_the_owner_still_reads_everything_a_stranger_could_not`, `test_every_store_write_path_changes_nothing_for_a_foreign_credential` (×4), `test_every_service_write_path_changes_nothing_for_a_foreign_credential` (×4), `test_the_owners_own_writes_still_land`, `test_a_foreign_delete_leaves_audit_logs_and_the_owners_messages_alone` — 27 cases |

## Acceptance Criteria

- [x] It enumerates every public callable in `app/db/database.py` matching `*_chat_session*` / `*_chat_message*` and asserts each declares a required, undefaulted `user_id` — discovered from the module, with a census test as the floor so a broken predicate cannot pass vacuously.
- [x] A new function on that surface without `user_id` fails the suite — observed twice (store and service probes above), then removed.
- [x] Every public function in `app/services/chat_sessions.py` takes an `Identity` first — and takes no bare `user_id` at all.
- [x] Every read path in both modules, driven with the other user's credential, returns `None` / `[]` / `False` / `0` and never a row; the owner's own reads still find everything, so the assertions are not satisfied by a store that answers nobody.
- [x] Every write path driven with a foreign credential leaves both tables unchanged — asserted by counting rows **and** comparing every row, not by trusting the return value; the falsy-return and the raised-`StorageError`/`ChatSessionError` arms are held to the same invariant.
- [x] A foreign-credential delete leaves `count_audit_logs()` unchanged and the owner's `chat_messages` count unchanged, through both the store and the service.
- [x] The suite passes offline with no Turso account — verified with `.env` moved aside and no `TURSO_*` variable set: 27 passed.
- [x] All tasks completed.
- [x] No production code changed (`git diff -- app/ chat_ui/` empty).
- [x] Full suite green apart from the 7 pre-existing `test_untouched_app.py` failures, measured to be unrelated.
- [x] Follows existing patterns (`tests/test_chat_sessions.py` discovery and call-table idioms, `tests/test_rbac.py` credential seeding, `tests/test_untouched_app.py` docstring register, `temp_db` as the only fixture).
