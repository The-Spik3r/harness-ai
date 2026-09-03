---
story: STORY-002
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-002-chat-session-schema.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: e3bb0c7
status: COMPLETE
completed: 2026-09-03
---

# Implementation Report — STORY-002: chat_sessions and chat_messages DDL and dataclasses

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-002-chat-session-schema.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `e3bb0c7`

## Summary

`app/db/models.py` now declares the transcript schema: `CREATE_CHAT_SESSIONS_TABLE`, `CREATE_CHAT_MESSAGES_TABLE`, their two `CREATE INDEX IF NOT EXISTS` constants, and the `ChatSession` / `StoredMessage` dataclasses that mirror them. `audit_logs` gains a nullable `session_id`, declared in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`, and `AuditLog` carries the matching field.

No SQL executes in this story and no function was added. `app/db/database.py` is untouched and still holds zero references to the new table constants — verified, because that boundary is what STORY-003 is for. A real `init_db()` run against the dev database confirms the outcome: `audit_logs.session_id` exists and is nullable, while `chat_sessions` and `chat_messages` do **not** exist yet.

The one thing worth a reader's attention is the `session_id` column arriving a story earlier than the story text implies. `_add_missing_columns` already iterates `AUDIT_LOGS_ADDED_COLUMNS`, so the mapping entry alone migrates every database immediately — which is why two literal column-list pins had to be updated here rather than in STORY-003.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `"session_id": "TEXT"` in `AUDIT_LOGS_ADDED_COLUMNS`, comment block extended to name PRD-008 | `app/db/models.py` | ✅ |
| 2 | `session_id TEXT` in `CREATE_AUDIT_LOGS_TABLE`, with the both-places rule written down | `app/db/models.py` | ✅ |
| 3 | `CREATE_CHAT_SESSIONS_TABLE` + `CREATE_CHAT_SESSIONS_USER_INDEX` | `app/db/models.py` | ✅ |
| 4 | `CREATE_CHAT_MESSAGES_TABLE` + `CREATE_CHAT_MESSAGES_SESSION_INDEX` | `app/db/models.py` | ✅ |
| 5 | `AuditLog.session_id`, positioned before `id` | `app/db/models.py` | ✅ |
| 6 | `ChatSession` and `StoredMessage` dataclasses | `app/db/models.py` | ✅ |
| 7 | Pinned column set repaired + 27 constant-level test cases | `tests/test_db.py` | ✅ |
| 8 | Full-suite regression against a measured baseline | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `tests/test_db.py` | ✅ 124 passed (97 pre-existing + 27 new) |
| `tests/test_migrate_to_turso_cli.py` | ✅ 21 passed |
| Full suite `pytest -q` | ✅ 1170 passed, 7 failed — **all 7 pre-existing**, byte-identical to the measured baseline |
| New failures introduced | ✅ zero (`comm` diff of baseline vs final failure lists is empty) |
| `app.db.models` imports | ✅ |
| `app.db.database` imports, new constants unreferenced | ✅ 0 references |
| Real `init_db()`: `session_id` nullable, no default | ✅ `notnull=0`, `dflt_value=None` |
| Chat tables still absent after `init_db()` | ✅ scope boundary with STORY-003 held |
| Lint | n/a — this repo has no linter or formatter; CI runs `pip install` then `pytest -q` |

### The 7 pre-existing failures, and how that was established

All 7 live in `tests/test_untouched_app.py`. They are PRD-006-scoped guards asserting that files are unchanged **since PRD-006's baseline commit**; PRD-007 and PRD-008 have legitimately changed those files since, so the guards are stale. They are not this story's, and that is measured rather than asserted: the two code files were stashed, the full suite run to produce a baseline (`7 failed, 1143 passed`), the stash restored, and the failure lists diffed. The new-failure set is empty and the pass count rose by exactly 27.

Worth flagging for whoever owns PRD-006's guards: one of the 7 is `test_the_pinned_suites_are_byte_unmodified[tests/test_db.py]`, which pins this very file. It was already failing before this story touched anything, so it hid no regression here — but it will keep failing until those guards are rescoped, and it can no longer detect an unintended edit to `tests/test_db.py`.

### Environment

The suite could not run on this workstation at the start of this story, the same block STORY-001's report recorded: only Python 3.14 was installed, `libsql==0.1.11` publishes no cp314 wheel, and its source build needs an MSVC toolchain that is not present. Two things were fixed, with your approval:

- The `libsql-server` container already existed and was simply stopped; it was started.
- Python 3.11.9 (the version CI pins, and the reason it pins it) was installed via `winget` alongside 3.14, and a project `.venv` was created from it with `requirements.txt` installed. `.venv` is gitignored.

The full suite now runs locally. This unblocks the remaining PRD-008 stories as well as this one.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/models.py` | UPDATE | +133 / -4 |
| `tests/test_db.py` | UPDATE | +216 / -1 |
| `tests/test_migrate_to_turso_cli.py` | UPDATE | +1 / -1 |

## Deviations from Plan

1. **A third file was changed: `tests/test_migrate_to_turso_cli.py`.** The plan predicted a two-file diff. `test_dest_columns_match_the_ddl` pins the `audit_logs` column list as a literal, exactly like `test_schema_has_no_ip_or_location_column` which the plan *did* anticipate — the exploration found one such pin and missed the second. Its own docstring says it exists so "a future schema change that breaks the assumption breaks a test rather than a migration", so it was doing its job. One name appended, with a comment naming the PRD.

   The migration script itself needed nothing: `scripts/migrate_to_turso.py` derives its column list from the DDL through `_ddl_columns`, so it picked `session_id` up automatically. `_TELEMETRY_COLUMNS` there was deliberately left alone — it is a curated PRD-007 list driving the read-back sample, not a schema mirror, and nothing about it is broken.

2. **Three tests beyond the plan's list**, each pinning a decision the plan argued for in prose but left unenforced: `test_chat_messages_declares_no_foreign_key`, `test_chat_session_indexes_are_not_unique`, and `test_every_added_column_is_also_declared_in_the_create`. The last one generalizes Task 2's both-places rule from `session_id` to every migrated column, so the next schema story inherits the check instead of rediscovering the argument.

3. **`test_chat_dataclasses_require_their_identifying_fields`** was added to pin that the identifying fields carry no defaults — a `StoredMessage` with a defaulted `session_id` would be a message belonging to nobody, and PRD Risk 2 is precisely about ownership being forgotten silently.

Nothing else deviated. `app/db/database.py` was not touched, no function was added, and no SQL runs.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_chat_table_ddl_declares_if_not_exists[chat_sessions, chat_messages]` (AC 5) · `test_chat_sessions_key_columns_declare_not_null_explicitly` (AC 1, AC 2) · `test_chat_messages_ddl_orders_by_an_autoincrement_key` (AC 3) · `test_chat_messages_ddl_carries_every_restorable_chat_message_field[×10]` (AC 3) · `test_chat_messages_ddl_requires_the_columns_every_bubble_has` (AC 3) · `test_chat_messages_pii_redacted_follows_the_boolean_convention` · `test_chat_messages_ddl_stores_no_humanized_duplicate_copy[×2]` (AC 4) · `test_chat_messages_declares_no_foreign_key` · `test_chat_indexes_cover_the_two_read_paths` (AC 5) · `test_chat_session_indexes_are_not_unique` · `test_audit_logs_added_columns_carries_a_nullable_session_id` (AC 6) · `test_every_added_column_is_also_declared_in_the_create` · `test_audit_log_carries_session_id_without_breaking_construction` (AC 7) · `test_stored_message_mirrors_the_chat_messages_columns` (AC 8) · `test_chat_session_mirrors_the_chat_sessions_columns` (AC 8) · `test_chat_dataclasses_require_their_identifying_fields` |

16 functions, 27 collected cases after parametrization.

These assert the DDL **constants as strings**, not `PRAGMA table_info`, and that is deliberate: `init_db()` does not execute these statements until STORY-003, so there is no table to interrogate yet. STORY-003's AC 6 owns the `PRAGMA` assertions. A comment block above the tests says so, because otherwise the choice reads as laziness.

The two that earn their place most: `test_stored_message_mirrors_the_chat_messages_columns` compares the dataclass against the parsed DDL mechanically, so the real long-run risk — dataclass and table drifting as later stories add fields — fails a test rather than a reading. And `test_chat_messages_ddl_stores_no_humanized_duplicate_copy` asserts an *omission*, which will look strange to a future reader, so it carries PRD Section 6's sentence in its docstring.

## Acceptance Criteria

- [x] `CREATE_CHAT_SESSIONS_TABLE` declares `session_id TEXT PRIMARY KEY NOT NULL`, `user_id TEXT NOT NULL`, `title TEXT NOT NULL`, `created_at TEXT NOT NULL`, `updated_at TEXT NOT NULL`
- [x] Both key columns declare `NOT NULL` explicitly, with the `users` table's reason stated verbatim
- [x] `CREATE_CHAT_MESSAGES_TABLE` declares the five required columns plus all ten metadata columns
- [x] Neither `duplicate_relative_info` nor `duplicate_release_info` has a column
- [x] Both indexes are `CREATE INDEX IF NOT EXISTS` over `chat_sessions(user_id, updated_at DESC)` and `chat_messages(session_id, id)`
- [x] `AUDIT_LOGS_ADDED_COLUMNS` carries `"session_id": "TEXT"`; `test_added_columns_declaring_not_null_also_declare_a_default` passes unmodified
- [x] `AuditLog` carries `session_id: Optional[str] = None`, before `id`, breaking no construction
- [x] `ChatSession` and `StoredMessage` mirror their tables, in the style of `AuditLog` and `User`
- [x] `tests/test_db.py` passes, with the new DDL constants asserted for `IF NOT EXISTS` and for the explicit `NOT NULL` on both key columns
- [x] All tasks completed
- [x] Full suite green apart from 7 measured pre-existing failures; the fourteen suites in PRD Section 15 pass unmodified
- [x] No SQL executed and no function added — `app/db/database.py` untouched
- [x] Follows existing patterns
