---
story: STORY-010
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-010-chat-messages-history-trimmed-column.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: 113633c
status: COMPLETE
completed: 2026-09-18
---

# Implementation Report — STORY-010: chat_messages.history_trimmed column, converged by init_db()

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-010-chat-messages-history-trimmed-column.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `113633c`

## Summary

`chat_messages` gains a nullable `history_trimmed INTEGER`, declared in both `CREATE_CHAT_MESSAGES_TABLE` and a new `CHAT_MESSAGES_ADDED_COLUMNS`, with `StoredMessage.history_trimmed: Optional[int] = None` mirroring it. `_add_missing_columns` now takes `(conn, table, columns)` and is called twice from `init_db()`'s single `_session()` block — `audit_logs` where it has always sat, `chat_messages` immediately after its `CREATE`. The body of that function is unchanged: same pre-check, same `_translated()` around the single `ALTER`, same narrow `_is_duplicate_column` re-raise. `append_chat_message` and `_row_to_stored_message` carry the value with no coercion and no `or None`, so `0` ("this send dropped nothing") and `NULL` ("written before the feature existed") stay distinguishable.

Nothing writes a non-NULL value yet. STORY-012 does, through `ChatMessage` → `_to_stored_message`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Column in the DDL, `CHAT_MESSAGES_ADDED_COLUMNS`, `StoredMessage.history_trimmed` | `app/db/models.py` | ✅ |
| 2 | `_add_missing_columns(conn, table, columns)` + the `chat_messages` pass in `init_db()` | `app/db/database.py` | ✅ |
| 3 | INSERT column/placeholder/value and the row mapper, uncoerced | `app/db/database.py` | ✅ |
| 4 | `_to_chat_message` coverage test derives its excused set from `ChatMessage.model_fields` | `tests/test_chat_state.py` | ✅ |
| 5 | Constant-level tests for the declaration pair | `tests/test_db.py` | ✅ |
| 6 | The built column on a fresh database | `tests/test_db.py` | ✅ |
| 7 | Pre-PRD-010 fixture, migration, and both halves of the ordering rule | `tests/test_db.py` | ✅ |
| 8 | Forced race and the stale-read convergence, both tables | `tests/test_db.py` | ✅ |
| 9 | Round trip: `3`, `0`, and absent | `tests/test_chat_sessions.py` | ✅ |
| 10 | Untouched-surface check, stale docstring corrected, full suite | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | n/a (no frontend build in this repo) |
| `tests/test_db.py` + `test_chat_sessions.py` + `test_chat_state.py` | ✅ 439 passed |
| Regression modules (two-instance, history-off, ownership, migrate CLI, chat shell) | ✅ 106 passed |
| Race set, 3 consecutive runs | ✅ 4 passed each |
| Full suite `pytest tests/ -q` | ✅ 2141 passed, 25 skipped |
| E2E checklist | ✅ 8/8 |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/models.py` | UPDATE | +37/-3 |
| `app/db/database.py` | UPDATE | +60/-8 |
| `tests/test_db.py` | UPDATE | +320/-9 |
| `tests/test_chat_sessions.py` | UPDATE | +59 |
| `tests/test_chat_state.py` | UPDATE | +15/-4 |
| `tests/test_two_instance_smoke.py` | UPDATE | +5 |

`chat_ui/`, `app/services/`, `app/routers/`, `app/models/` and `scripts/` are untouched (`git diff --stat` over those paths is empty).

## Deviations from Plan

1. **`tests/test_two_instance_smoke.py` needed an edit.** The plan's fact 5 said this file passes unmodified, having checked its *schema* assertion (containment, `:655`) but not `_transcript()` at `:917` — a per-field literal compared to the read-back row by whole-dict equality, which gained `history_trimmed: None` on the actual side and failed. Fixed by adding `"history_trimmed": index` to the fixture rather than excusing the key, which turns the failure into real cross-instance evidence for the new column (distinct value per message, `0` on the first). 10 passed.
2. **`tests/test_db.py` gained two imports** — `append_chat_message` and `list_chat_messages` — which the plan did not anticipate: the module had never read a transcript back, and Task 7's migration test asserts the seeded message survives.
3. **Task 7.4's test is named `test_init_db_adds_no_history_trimmed_alter_to_a_fresh_database`** (plan said `..._to_a_fresh_chat_table`) and takes `uninitialized_db, monkeypatch` without `db_connect`, since a database with no tables needs no hand-built fixture.
4. **Task 10's docstring correction was larger than "amend one sentence".** `tests/test_db.py:1581` justified `users` needing no migration by saying `_add_missing_columns` "stays audit_logs-specific", which this story makes false. Rewritten to rest on the claim that is still true — tables arrive through `CREATE`, columns through `ALTER` — and to record that the function gained a second table, not a second mechanism.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_chat_messages_added_columns_carries_a_nullable_history_trimmed`, `test_every_chat_messages_added_column_is_also_declared_in_the_create`, `test_chat_messages_added_columns_declaring_not_null_also_declare_a_default`, `test_stored_message_carries_history_trimmed_without_breaking_construction`, `test_init_db_adds_a_nullable_history_trimmed_column`, `test_init_db_migrates_a_pre_history_trimmed_database`, `test_init_db_adds_the_history_trimmed_column_after_creating_the_table`, `test_init_db_adds_no_history_trimmed_alter_to_a_fresh_database`, `test_two_init_db_calls_racing_on_history_trimmed_both_converge`, plus the `_create_pre_history_trimmed_database` fixture |
| `tests/test_chat_sessions.py` | `test_history_trimmed_round_trips_as_an_integer`, `test_history_trimmed_zero_round_trips_as_zero`, `test_absent_history_trimmed_reads_back_as_none_not_zero` |
| `tests/test_db.py` (extended) | `test_add_missing_columns_treats_an_existing_column_as_success` now asserts convergence on both tables |
| `tests/test_chat_state.py` (extended) | `test_the_rehydration_reads_every_stored_field` derives and pins its excused set |
| `tests/test_two_instance_smoke.py` (extended) | the cross-instance transcript round trip now carries `history_trimmed` |

### Two traps verified live, not assumed

- **The ordering pins are not vacuous.** Moving the `chat_messages` pass above `CREATE_CHAT_MESSAGES_TABLE` fails both ordering tests with `MissingRelationError` — the boot failure they exist to catch. The migration test alone still passed under that arrangement, which is precisely why the explicit pins were worth writing. Reverted; green.
- **The `_to_chat_message` trap is armed.** Temporarily adding `history_trimmed: int = 0` to `ChatMessage` fails `test_the_rehydration_reads_every_stored_field` on the pinned excused set, so STORY-012 cannot add the bubble field without also mapping it. Reverted with an empty `git diff` over `chat_ui/`.

## Acceptance Criteria

- [x] `CREATE_CHAT_MESSAGES_TABLE` declares `history_trimmed INTEGER` (nullable), `CHAT_MESSAGES_ADDED_COLUMNS = {"history_trimmed": "INTEGER"}` exists, and `StoredMessage.history_trimmed: Optional[int] = None`
- [x] A pre-PRD database gains the column, existing rows read `NULL`, and a second `init_db()` issues no `ALTER`
- [x] Two concurrent `init_db()` calls racing the add converge via `_is_duplicate_column` instead of failing boot
- [x] `append_chat_message(history_trimmed=3)` reads back `3`; rows written without it read `None` (and `0` reads back `0`)
- [x] The full suite is green, including `tests/test_db.py` and `tests/test_chat_sessions.py`
- [x] All tasks completed
- [x] Full test suite passes (`pytest tests/ -q`): 2141 passed, 25 skipped
