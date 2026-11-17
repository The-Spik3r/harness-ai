---
story: STORY-003
prd: PRD-018
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-003-unit-of-work-and-kinds.plan.md
epic_branch: epic/PRD-018-db-resilience
commit: pending
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report — STORY-003: _unit_of_work retry boundary, statement kinds, _FaultyClient harness

**Plan**: `.agents/plans/PRD-018-db-resilience/completed/STORY-003-unit-of-work-and-kinds.plan.md`
**Epic Branch**: `epic/PRD-018-db-resilience`
**Commit**: `pending`

## Summary

`app/db/database.py` gains the retry boundary of PRD 6.1: the closed `StatementKind` enum, three budget constants (`_RETRY_MAX_ATTEMPTS = 3`, `_RETRY_BACKOFF_CAPS_SECONDS = (0.05, 0.2)`, `_RETRY_START_DEADLINE_SECONDS = 2.0`), three call-time seams (`_retry_sleep`, `_retry_clock`, `_retry_jitter`), the pure `_retryable(kind, class, phase)`, `_failure_of(exc)` (classifies the rollback's error and the body's `__context__`, most pessimistic wins, a tie goes to the body), `_retry_detail(exc)` and `_unit_of_work(name, kind, fn)`. All 41 public operational functions now run their former `with _session()` body, verbatim, as a local `_op` through `_unit_of_work` with the kinds in the plan. `_translated()`, `init_db()`, `check_database_reachable()`, `_session()` and `get_connection()` are byte-identical to HEAD (checked by comparing their source with `ast`). No breaker and no `StorageUnavailableError`; the three STORY-005 hooks (entry, success, failure) are marked in the loop.

New test infrastructure: `tests/db_faults.py` (`Fault`, `FaultScript`, `_FaultyClient`, captured-text constants) and the `faulty_db` fixture in `tests/conftest.py` (lazy import, so the conftest copied into `test_db_isolation_harness` child runs still imports).

## Orchestrator answers applied

1. `insert_audit_log` and `insert_action_decisions` are `NON_IDEMPOTENT` in this story (docstring and pin-test comment say STORY-004 flips them).
2. AC 4's landed `OUTCOME_UNKNOWN` on `admit_usage` is tested as `Fault(op="commit", when="after")`; the companion `execute`/`after` test pins `usage_daily` absent and one forwarded INSERT.
3. `delete_chat_session` returning `False` after a landed `OUTCOME_UNKNOWN` commit is documented as an accepted residual in its docstring (STORY-014 documents it for operators).
4. CHANGE applied: a refused retry on an infrastructure class logs exactly one WARNING `retry refused op=<name> class=<class> kind=<kind> detail=<redacted>`. `STATEMENT` failures and our own non-`Hrana:` `StorageError`s log nothing. Tested beside the AC 5 log tests (three parametrised refusals, plus the statement and pass-through cases).
5. Out of scope; recorded by the orchestrator in STORY-007 and STORY-012.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Vocabulary, constants, seams, logger | `app/db/database.py` | done |
| 2 | `_retryable`, `_failure_of`, `_retry_detail`; stale "nothing calls `_classify` yet" prose updated | `app/db/database.py` | done |
| 3 | `_unit_of_work` (with `retry refused` / `retry exhausted` / `retry` logs and the STORY-005 hooks) | `app/db/database.py` | done |
| 4 | 41 functions rewritten through `_unit_of_work` (one scripted transformation, three hand-written exceptions) | `app/db/database.py` | done |
| 5 | `_FaultyClient` harness and `faulty_db` fixture | `tests/db_faults.py`, `tests/conftest.py` | done |
| 6 | Pure retry tests and the name -> kind pin | `tests/test_db_resilience_retry.py` | done |
| 7 | Two `test_db.py` tests that pinned "no retry" through a public function | `tests/test_db.py` | done |
| 8 | `db` tests against the real driver | `tests/test_db_resilience_faults.py` | done |
| 9 | Targeted regression run | n/a | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Frontend lint | n/a (no frontend) |
| `test_db_resilience_retry.py` (non-`db`, no driver) | 162 passed |
| `test_db_resilience_faults.py` (`db`) | 20 passed |
| Targeted regression (one pytest process, plan Task 9 set) | 746 passed, 0 failed, 0 skipped, 143 deselected (937 s) |
| E2E checklist | import OK; no diff inside `_translated()`, `init_db()`, `check_database_reachable()`; `with _session() as conn` appears exactly twice (`_unit_of_work`, `init_db`); `_unit_of_work("` appears 41 times; `test_init_db_fails_fast_against_an_unreachable_endpoint` passes unchanged; `FailureClass` / `StatementKind` appear only in `app/db/database.py` |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

| File | Action |
|------|--------|
| `app/db/database.py` | UPDATE (+489/-54) |
| `tests/db_faults.py` | CREATE |
| `tests/conftest.py` | UPDATE (+24, `faulty_db` and a docstring bullet) |
| `tests/test_db_resilience_retry.py` | CREATE |
| `tests/test_db_resilience_faults.py` | CREATE |
| `tests/test_db.py` | UPDATE (2 tests) |
| `.agents/` | plan archived, report, STORY-003 status, orchestrator edits to STORY-004/007/012/014 (committed unchanged), index |

## Deviations from Plan

- AC 2's "dead stream on `commit` is not retried" is superseded by the orchestrator decision (it is `NOT_SENT` and is retried); tests pin the new rule.
- `insert_audit_log` had no docstring; one was added to carry the `NON_IDEMPOTENT until STORY-004` note.
- `_retry_detail`'s statement elision also matches the backslash-escaped form of `near "..."` that the driver's quoted messages can produce.
- The plan's init_db fault test said "one forwarded attempt"; a before-forward fault is not forwarded, so the test counts the one call that reached the proxy and asserts no retry record.
- A plan open question became decision 4 above (refused retries do log).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db_resilience_retry.py` | kind x class matrix (27 cells, each also compared with what `_session()` alone raises), `_retryable` over kinds x classes x phases, budget and constants, full jitter and caps order, deadline (inside, past, projected wait, 21 s stall), fresh client per class, rollback-masks-body rule (four cases plus direct `_failure_of` tests incl. the nested `_translated()` shape), pass-through of our own `StorageError` / `KeyError` / non-driver `ValueError`, logs (INFO per retry, exhausted WARNING, refused WARNING x3, nothing for STATEMENT, redaction, SQL elision, length cap), `create_chat_session` duplicate-on-retry rule (3), name -> kind pin (4 assertions over 41 rows) |
| `tests/test_db_resilience_faults.py` | before-forward faults on a READ, an IDEMPOTENT UPDATE and INSERT, a NON_IDEMPOTENT counter (3 texts each); dead stream on commit retried; landed `OUTCOME_UNKNOWN` on `admit_usage` (requests moved by exactly 1, not replayed, no retry log); `execute`/`after` lands nothing; 3-row batch replay; `create_chat_session` after a landed commit; log shape and redaction; exhausted budget logs; `init_db()` fails fast with no retry |

## Acceptance Criteria

- [x] `_unit_of_work` retries per kind x class, at most 3 attempts, full jitter, 2.0 s start deadline: `test_the_kind_by_class_matrix`, `test_retryable_over_the_whole_table`, budget and deadline tests
- [x] `STATEMENT` and `NON_IDEMPOTENT` on `OUTCOME_UNKNOWN` raise on attempt 1 with today's type; dead stream on `commit` retried: matrix rows and the type comparison with `_session()`
- [x] 41 functions through `_unit_of_work`, `create_chat_session` duplicate rule, name -> kind pin: `test_the_table_covers_the_modules_public_functions`, `test_every_public_function_runs_one_unit_of_its_own_name_and_kind`, `test_nothing_opens_a_session_outside_the_unit_and_the_boot_path`
- [x] `_FaultyClient` over PRD-014's recorder; before-forward faults return the fault-free result; landed `OUTCOME_UNKNOWN` on `admit_usage` moves `requests` by exactly 1 and propagates: `tests/test_db_resilience_faults.py`
- [x] INFO per retry, WARNING per exhausted budget (and per refusal, decision 4), redacted, no SQL; `init_db()` fails fast: log tests and `test_init_db_still_fails_fast_with_no_retry`
- [x] `_translated()` unchanged; no breaker; STORY-005 hooks marked
- [x] Backend imports; targeted run green; full suite on CI
- [x] Follows existing patterns
