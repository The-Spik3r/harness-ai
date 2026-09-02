---
story: STORY-009
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-009-top-pii-entities-sql-aggregation.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: TBD
status: COMPLETE
completed: 2026-09-01
---

# Implementation Report — STORY-009: Aggregate `top_pii_entities()` in SQL

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-009-top-pii-entities-sql-aggregation.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: `TBD`

## Summary

`top_pii_entities()` no longer reads every PII-bearing row. Its two-part body — a
`SELECT pii_entities FROM audit_logs WHERE pii_entities IS NOT NULL` followed by a
Python `dict` count and a `sorted()` — is replaced by one statement: a recursive CTE
that splits the comma-separated TEXT column server-side, groups, orders, and applies
`LIMIT ?`. The function now has the same shape as `top_models()` and `top_users()`
directly above it.

Measured against the live libSQL endpoint with 50 PII-bearing rows spanning seven
entity types: **50 rows in the table, 5 rows on the wire.** Before, all 50 crossed
the network to produce the same five-element answer, and that number grew with every
audited query.

Signature, return type, and the descending-frequency contract are unchanged. One
behavior change is deliberate and declared below: the tie-break.

## The tie-break — declared behavior change (AC 3)

The implementation this replaced sorted with
`sorted(counts.items(), key=lambda item: item[1], reverse=True)`. Python's sort is
stable, so entities with equal counts came back in `dict` insertion order — which is
to say, in whatever order the database happened to return the rows. That was
incidental, not designed, and under multiple instances it is not even stable.

**The chosen rule is `ORDER BY COUNT(*) DESC, entity ASC`**: count descending, then
entity name ascending. Deterministic, independent of row order, identical across
instances.

The difference is observable only among tied entities, and only in which of the tied
names lands inside the `limit` cut. Verified against the live endpoint over 50 seeded
rows, where four entities tie at 9 and three tie at 8:

```
counts                          : EMAIL_ADDRESS 9, LOCATION 9, PERSON 9, US_SSN 9,
                                  CREDIT_CARD 8, IBAN_CODE 8, PHONE_NUMBER 8
old impl (incidental tie order) : [EMAIL_ADDRESS, LOCATION, PERSON, US_SSN, PHONE_NUMBER, CREDIT_CARD, IBAN_CODE]
new impl (STORY-009 tie rule)   : [EMAIL_ADDRESS, LOCATION, PERSON, US_SSN, CREDIT_CARD, IBAN_CODE, PHONE_NUMBER]
```

Same entities, same counts; the three 8s order by name instead of by row arrival.
`tests/test_db.py::test_top_pii_entities_breaks_ties_by_entity_name` pins the rule
and inserts its rows in a deliberately non-alphabetical order, so it fails if row
order ever decides the outcome again.

## The `NULL` seed — why the SQL is not the textbook idiom

The common SQLite split CTE seeds with `SELECT '', col || ','` and discards the seed
with `WHERE entity <> ''`. That filter would also discard genuine empty segments: a
stored `"A,,B"` would yield `{A, B}` where `"A,,B".split(",")` yields `{A, "", B}`.
AC 4 asks that each segment count "exactly as the current loop does", so the seed
selects `NULL` and the filter is `WHERE entity IS NOT NULL`, which separates "the
seed row" from "an empty entity" and reproduces `str.split(",")` exactly.

**No test pins the `"A,,B"` case, deliberately.** Such a value is unreachable through
`app/services/audit_logger.py:45`, which writes `",".join(...) if pii_entities else None`
— an empty list becomes `NULL`, never an empty segment. A test would pin behavior on
data the application cannot produce. The parity was verified during planning against
stdlib `sqlite3` (SQL and the Python loop agreed row-for-row, `""` included), and the
reasoning lives in the function's docstring so a later "simplification" to
`WHERE entity <> ''` reads as the regression it would be.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Rewrite `top_pii_entities()` as one aggregating statement | `app/db/database.py` | ✅ |
| 2 | Add multi-entity, tie-break, within-row-repeat and no-PII cases | `tests/test_db.py` | ✅ |
| 3 | Confirm no caller and no copy changed | — | ✅ |
| 4 | Run the suites that read this figure | — | ✅ (see caveat) |

## Validation Results

| Check | Result |
|-------|--------|
| Module imports (`import app.db.database`, endpoint supplied) | ✅ |
| `tests/test_db.py -k top_pii_entities` | ✅ 6 passed (2 pre-existing, unmodified + 4 new) |
| `tests/test_db.py` (whole module) | ✅ 87 passed |
| `tests/test_stats_router.py` | ✅ 7 passed |
| `tests/test_admin_state.py` | ✅ 101 passed (identical to baseline) |
| `tests/test_pii_redaction_integration.py` | ⚠️ fails identically at baseline `d253f1a` — pre-existing, see below |
| E2E round-trip cap + old/new parity probe vs live endpoint | ✅ all probes passed |
| `git diff -- chat_ui/` | ✅ empty |
| Full suite in one process | ⚠️ pre-existing `STREAM_EXPIRED` breakage, see below |

### Pre-existing: the shared client's Hrana stream expires mid-run

Running the whole suite in one process produces a large number of errors reading:

```
ValueError: Hrana: `api error: `status=400 Bad Request,
  body={"message":"The stream has expired due to inactivity","code":"STREAM_EXPIRED"}``
```

**This is not caused by this story, and this story does not fix it.** Measured on a
clean worktree at `d253f1a` (HEAD before this work) against the same dev server:

| Tree | Result |
|------|--------|
| Baseline `d253f1a` | 1 failed, 335 passed, **756 errors** |
| With STORY-009 | 1 failed, 335 passed, **760 errors** |

The delta is exactly 4 — this story's four new tests, joining the same pre-existing
failure mode. `tests/test_pii_redaction_integration.py` reproduces the failure on its
own at baseline (1 failed, 18 errors), unchanged by this story.

Cause: STORY-006 made the libSQL client process-wide and long-lived, and the Hrana
stream behind it expires after an idle window. Slow modules — `presidio-analyzer`
and `spacy` take roughly 20 seconds to load their models — idle it out, and every
database access afterwards in that process fails. Each module passes when run alone,
which is why it has stayed invisible. It is a shared-client lifetime concern, not a
query concern, and it belongs with the connection layer rather than here. PRD Section
4 also puts "Retry, circuit-breaker, or offline-queue behavior for transient network
failure" out of MVP scope, so silently adding a reconnect under this story would have
been the wrong call. **Flagged for the PRD owner — it likely warrants its own story
before STORY-016 tries to prove multi-instance behavior.**

Separately and also pre-existing: a bare `import app.db.database` with no environment
fails, because the repo `.env` still carries `DATABASE_URL=sqlite:///harness_ai.db`
and STORY-005's validator rejects it. STORY-014 owns that cutover.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +43/-7 |
| `tests/test_db.py` | UPDATE | +100/-0 |

## Deviations from Plan

| Deviation | Rationale |
|-----------|-----------|
| Plan's Task 1 validation `python -c "import app.db.database"` needed `DATABASE_URL` supplied | Pre-existing `.env` condition (above), not a consequence of the change. Verified clean once an endpoint is set. |
| Plan's Task 4 "full suite passes" not met | Pre-existing `STREAM_EXPIRED` breakage, present identically at baseline. Discharged instead by running each affected suite in isolation and diffing counts against baseline `d253f1a`. Reported rather than worked around. |
| Tests run in a `harness-test:py311` container rather than on the host | `libsql==0.1.11` publishes no wheel for the host's Python 3.14 and fails to build. The container is the same one earlier stories in this PRD used. |
| No test added for `"A,,B"` | Deliberate; reasoning in "The `NULL` seed" above. |

Implementation otherwise matched the plan, including the exact SQL statement.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_top_pii_entities_counts_each_entity_in_a_multi_entity_value` — one row of three entities contributes one to each; the two tied 1s order by name |
| | `test_top_pii_entities_breaks_ties_by_entity_name` — pins the chosen tie rule, rows inserted non-alphabetically so row order cannot satisfy it |
| | `test_top_pii_entities_counts_repeats_within_one_value` — `"PERSON,PERSON,EMAIL_ADDRESS"` counts PERSON twice from one row; the case a `DISTINCT` rewrite gets wrong |
| | `test_top_pii_entities_ignores_rows_without_pii` — rows at the `None` default contribute neither `None` nor `""` |

The two pre-existing cases (`test_top_pii_entities_ranked_by_frequency_desc`,
`test_top_pii_entities_respects_limit`) pass **unmodified**, as AC 6 requires.
The empty *table* case (AC 5) was already covered by
`test_aggregates_on_empty_db_return_zero_or_empty` and was not duplicated; the
"rows but no PII" half is covered by the fourth new test above. Both were
additionally exercised by the E2E probe.

## Acceptance Criteria

- [x] Signature, return type (`list[str]`), and ordering semantics unchanged: descending frequency, capped at `limit`.
- [x] Transfers at most `limit` rows — measured 5 on the wire against 50 PII-bearing rows. The whole-table scan into Python is gone.
- [x] Identical output to the old implementation, including tie order — same entities and counts verified against the live endpoint; the tie-break was incidental and the chosen rule (count desc, then entity name) is stated above.
- [x] Each entity in a multi-entity value contributes one to its own count, exactly as the replaced loop did — including repeats within one value and empty segments.
- [x] Empty table and rows-without-PII both return an empty list without error.
- [x] Existing `top_pii_entities` coverage passes unmodified, plus new multi-entity, tie and empty cases.
- [x] `chat_ui/chat_ui/admin_copy.py:317` contract still holds; `git diff -- chat_ui/` is empty. No copy change made.
- [x] All tasks completed.
- [x] Follows existing patterns (`top_models` / `top_users` shape, `_session()` error surface).
- [ ] **Full test suite passes** — not met, and not met at baseline either. Pre-existing `STREAM_EXPIRED` defect documented above; every suite touching this story passes in isolation with counts identical to baseline.
