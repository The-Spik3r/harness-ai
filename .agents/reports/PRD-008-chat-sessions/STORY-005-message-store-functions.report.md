---
story: STORY-005
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-005-message-store-functions.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: 1851c25
status: COMPLETE
completed: 2026-09-03
---

# Implementation Report — STORY-005: append_chat_message and list_chat_messages, ordered by id and scoped by owner

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-005-message-store-functions.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `1851c25`

## Summary

Three public functions and one private row mapper were added to `app/db/database.py`, below STORY-004's session block: `_row_to_stored_message`, `append_chat_message`, `list_chat_messages` and `count_chat_sessions`. All three public functions take `user_id: str` undefaulted, and all three put it in a `WHERE` clause.

`chat_messages` carries no `user_id` column, so ownership on both message functions is the subselect `delete_chat_session` already uses. `append_chat_message` is a single `INSERT ... SELECT ... WHERE EXISTS` — the check and the write are one statement, so there is no window between them (PRD Risk 3). It raises `StorageError` when the session is unknown *or* foreign, with the same message for both, and checks `rowcount` before reading `lastrowid`. `list_chat_messages` reads `ORDER BY id ASC` with no `LIMIT`.

`tests/test_chat_sessions.py` was extended in place, as its own module docstring directed, with 30 new cases in a labelled STORY-005 section.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Probe `rowcount` on a non-matching `INSERT ... SELECT` | — (scratchpad) | ✅ |
| 2 | Import `StoredMessage` | `app/db/database.py` | ✅ |
| 3 | Add `_row_to_stored_message` | `app/db/database.py` | ✅ |
| 4 | Add `append_chat_message` | `app/db/database.py` | ✅ |
| 5 | Add `list_chat_messages` | `app/db/database.py` | ✅ |
| 6 | Add `count_chat_sessions` | `app/db/database.py` | ✅ |
| 7 | Extend the test suite | `tests/test_chat_sessions.py` | ✅ |
| 8 | Full suite and adjacent modules | — | ✅ |

### Task 1 result

The assumption the whole design rests on, probed before any code was written:

```
owned   -> rowcount=1 lastrowid=1
foreign -> rowcount=0 lastrowid=0
foreign -> changes()=0
rows now: 1
```

`rowcount` reports `0` and no row is written. The documented `SELECT changes()` fallback was **not** needed.

## Validation Results

| Check | Result |
|-------|--------|
| `python -c "import app.db.database"` | ✅ |
| `pytest tests/test_chat_sessions.py` | ✅ 56 passed (26 STORY-004 + 30 new) |
| `pytest tests/test_db.py` | ✅ 137 passed |
| Full suite | ⚠️ 1239 passed, 7 failed — all pre-existing, see below |
| E2E | ✅ 7/7 |

### The 7 full-suite failures are pre-existing, not this story

All seven are in `tests/test_untouched_app.py`, a PRD-006 guard suite that pins `app/` and four test modules as byte-unmodified since PRD-006 began. It was verified by stashing this story's entire working tree and re-running against `HEAD` (`6128698`):

```
7 failed, 6 passed in 0.69s
```

— the identical seven names, with none of this story's code present. They were already broken by PRD-007's migration and PRD-008 STORY-002/003/004, each of which changed `app/db/` by design. This story adds an eighth reason for a suite that was already red; it does not cause the failure. Retiring or re-baselining that guard is its own piece of work and is deliberately not done here.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +200 |
| `tests/test_chat_sessions.py` | UPDATE | +473/-9 |

## Deviations from Plan

**None substantive.** Two additions the plan implied but did not enumerate:

1. The plan's test 10 (`test_tokens_used_and_audit_id_round_trip_as_integers`) was split into two cases. The `None`-stays-`None` half is a different claim from the integers-are-integers half — it is what fails if someone adds an `int()` to the row mapper — and merging them would have let one pass while the other was untested.
2. A `SEVEN_KINDS` module constant was introduced to carry each kind's metadata, so the parametrized round trip and any future kind-sensitive test share one list. It is a literal tuple of strings, deliberately not an import from `chat_ui/`, which preserves the boundary the story's technical notes require.

Task 1's fallback path was not exercised — the probe passed, so `rowcount` is used as planned.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_chat_sessions.py` | **Structural (6):** `test_the_three_message_functions_are_declared`, `test_every_message_signature_requires_an_undefaulted_user_id`, `test_omitting_user_id_is_a_type_error_on_the_message_functions`, `test_every_message_statement_scopes_on_user_id`, `test_list_chat_messages_orders_by_id_and_not_by_a_timestamp`, `test_list_chat_messages_takes_no_limit_parameter` |
| | **Order (2):** `test_twenty_messages_appended_in_one_second_read_back_in_order`, `test_append_returns_the_new_row_id_and_ids_increase` |
| | **Round trip (7 params + 5):** `test_each_of_the_seven_kinds_round_trips_unchanged` (parametrized over all seven kinds), `test_tokens_used_and_audit_id_round_trip_as_integers`, `test_absent_tokens_used_and_audit_id_read_back_as_none_not_zero`, `test_empty_pii_entities_stores_null_and_reads_back_as_none` (3 params), `test_pii_redacted_round_trips_as_a_bool`, `test_append_stamps_created_at_when_omitted_and_keeps_it_when_given` |
| | **Ownership (5):** `test_list_chat_messages_returns_empty_for_a_foreign_owner`, `test_append_for_a_foreign_owner_writes_nothing_and_raises`, `test_append_to_an_unknown_session_raises_the_same_way`, `test_append_ignores_the_session_id_on_the_message`, `test_delete_chat_session_removes_messages_written_through_append` |
| | **Counting (3):** `test_count_chat_sessions_counts_only_the_callers_own`, `test_count_chat_sessions_is_zero_for_an_unknown_user`, `test_count_chat_sessions_ignores_the_list_limit` |

## Design Decisions as Built

All four decisions the plan settled were implemented as written, each recorded in the function docstring that owns it:

- **D1** — one `INSERT ... SELECT ... WHERE EXISTS`; no read-then-write, no TOCTOU window.
- **D2** — `StorageError` for both the foreign and the unknown session, with one message. `test_append_to_an_unknown_session_raises_the_same_way` asserts the type *and* the string match, so a future "helpful" error that names which case occurred fails a test rather than quietly becoming a membership oracle.
- **D3** — the `session_id` parameter is read in both the value list and the predicate; `message.session_id` is never read.
- **D4** — `pii_entities` of `""` is stored as `NULL`, so STORY-015's `split(",")` is never handed an empty string.

## Notes for Later Stories

- **STORY-007** must exclude private helpers from its `*_chat_message*` discovery sweep, or `_row_to_stored_message` — which takes no `user_id` because it touches no database — will be reported as an ownership violation.
- **STORY-014** catches `StorageError` from `append_chat_message` for its degraded arm. That is the type by design (D2); a narrower `except` would let the failure escape as a 500 instead of the "turn was not saved" notice PRD Section 6 specifies.
- **STORY-015** rehydrates `StoredMessage` into `ChatMessage`. `pii_entities` arrives as `None` or a non-empty comma-joined string, never `""` — the split is safe without a guard, though a guard costs nothing.

## Acceptance Criteria

- [x] `app/db/database.py` declares `append_chat_message(message, session_id, user_id) -> int`, `list_chat_messages(session_id, user_id) -> list[StoredMessage]` and `count_chat_sessions(user_id) -> int`
- [x] `user_id: str` required and undefaulted on all three; each statement scopes on ownership; `append_chat_message` checks ownership in the same statement as the insert
- [x] `list_chat_messages` reads `ORDER BY id ASC` and by no timestamp column
- [x] Twenty messages appended inside one second read back in append order
- [x] `list_chat_messages(session_id, foreign_user_id)` returns `[]`
- [x] `append_chat_message(message, session_id, foreign_user_id)` writes no row and raises
- [x] All seven `ChatMessage` kinds round-trip every field, including `pii_entities` and integer `tokens_used`/`audit_id`
- [x] The round trip is asserted per kind, parametrized, not once for a representative kind
- [x] All tasks completed
- [x] `app/db/database.py` imports nothing from `chat_ui/`
- [x] Follows existing patterns
- [⚠️] Full test suite passes — 1239 pass; the 7 `test_untouched_app.py` failures are pre-existing at `HEAD` and unrelated to this story (evidence above)
