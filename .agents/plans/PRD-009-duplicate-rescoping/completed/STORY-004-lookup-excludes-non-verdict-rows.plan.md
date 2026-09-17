---
story: STORY-004
prd: PRD-009
slug: lookup-excludes-non-verdict-rows
title: "Duplicate lookup ignores failed, policy-denied and duplicate-blocked rows"
type: BUG_FIX
complexity: MEDIUM
epic_branch: epic/PRD-009-duplicate-rescoping
created: 2026-09-17
---

# Plan: Duplicate lookup ignores failed, policy-denied and duplicate-blocked rows

## Summary

This change adds three flag predicates to `find_duplicate_timestamp`'s `WHERE` clause in `app/db/database.py`: `success = 1 AND was_duplicate_blocked = 0 AND denied_permission IS NULL`. The existing `prompt_hash = ? AND timestamp >= ?` stays, and so do `ORDER BY timestamp ASC LIMIT 1` and the `(prompt_hash, since)` signature. The lookup still matches on `prompt_hash` and is still global (PRD-009 Section 12, Phase 2), so the fix ships and is reviewed on its own. `check_duplicate(prompt)` and `run_query` are **not touched**.

The tests change in three ways:

1. **Flip in place.** Four STORY-001 characterization tests in `tests/test_duplicate_characterization.py` get their assertions rewritten in place, each with a comment citing PRD-009 D1 or D3 and STORY-004. The four tests cover the `OpenRouterError` retry, the input `PiiRedactorError` retry, the model-allowlist denial, and the chaining case.
2. **New store-level tests.** `tests/test_duplicate_checker.py` gets one test per row kind: failed, `query:submit` denial, duplicate-blocked, suspicious-pattern, and success at −10h plus blocked at −2h.
3. **New pipeline-level tests.** These go in the same file and drive `run_query`. They cover the BYOK denial, the missing-`query:submit` denial, the suspicious-pattern resend (still `BLOCKED`, D1), and the output-`PiiRedactorError` retry (excluded, T6/Risk 4).

Exploration found these facts that the story text doesn't mention:

1. **Only four of the five characterization tests flip.** `test_pre_prd009_row_from_one_user_blocks_same_prompt_from_another_user` (`tests/test_duplicate_characterization.py:218-249`) is cross-user and belongs to STORY-005. Its prior is a live, unflagged `success=1` row, so it stays green without edits. AC 5 requires leaving it alone.
2. **The characterization suite pins only one of the three denial arms, model allowlist (`:178-215`).** Neither BYOK nor missing `query:submit` has a characterization test. AC 3 for those two is covered by **new** tests, not flips. Nothing pre-existing pins them, so there is nothing to flip.
3. **Every flipped test currently wires `call_openrouter` to `_fail_if_called` for the retry.** Once the retry reaches the model, that fake raises `AssertionError`, and the router turns that into a 500 or a raised exception, not a clean assertion failure. Each flip must swap in `_counting_success(calls)` and assert `len(calls) == 1`. That is the proof the model was reached, and the fixture helpers for it already exist at `:93-102`.
4. **The duplicate check runs before the pattern check** (`app/services/query_pipeline.py:91-122`). A second send of a suspicious prompt is therefore blocked with `reason: "Duplicate query within 24 hours"`, not `"Suspicious pattern detected"`. The D1 test asserts exactly that.
5. **No guard pins `database.py` or the lookup SQL.** The `git merge-base` "unmodified" guards only cover `duplicate_checker.py` (retired for PRD-009 in STORY-003) and `pattern_detector.py` (`tests/test_pii_dedup_isolation.py:200-212`). `tests/test_session_ownership.py` selects `database.py` functions by session/message name, and `find_duplicate_timestamp` doesn't match. Grepping for `find_duplicate_timestamp` in `tests/` finds only `test_dedup_key.py:221` (a stub) and the `test_db.py:1933` docstring.
6. **`tests/test_db.py:1931-1933` still reads correctly.** Its docstring says the lookup "does not take this shape until STORY-007". That remains true because this story still matches on `prompt_hash` with no `user_id`. **No edit.**
7. **No other test depends on a failed, denied or blocked prior.** All of these seed a default `success=True` row or send a live success, so they stay green: `_seed_duplicate` in `test_query_router.py:52-63` and `test_chat_state.py:88-99`, `test_integration.py:72-96`, `test_query_outcomes_regression.py:96-117`, `test_two_instance_smoke.py:670-699`, and `test_pii_dedup_isolation.py:124-141`, which is cross-user and belongs to STORY-005.
8. **This is the first `denied_permission IS NULL` predicate in `database.py`.** Every other flag filter compares against a literal, not a bound parameter: `count_successful_queries` (`:886-891`, `success = 1`) and `count_blocked_duplicates` (`:862-867`, `was_duplicate_blocked = 1`). `insert_audit_log` stores booleans as `int(...)` (`:753-755`), and the DDL has `NOT NULL DEFAULT` on both flags (`app/db/models.py:16,18`), so literal `= 1` / `= 0` is exact.

## User Story

As an end user
I want a retry after an upstream error or a policy denial to go through, and a blocked resend not to extend the window
So that a duplicate block only ever means "this already got a real answer (or a content-check verdict) in the last 24 hours".

## Story Reference

- Story file: `.agents/stories/PRD-009-duplicate-rescoping/STORY-004-lookup-excludes-non-verdict-rows.md`
- PRD: `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md`, Sections 4 (Lookup), 5 (stories 1, 4), 6.3, 6.4, 7 (F4), 9.2 (T3–T6), 11, 12 (Phase 2)
- Depends on: STORY-001 (`9abef61`, **done**)
- Blocks: STORY-005

## Metadata

| Field | Value |
|-------|-------|
| Type | BUG_FIX |
| Complexity | MEDIUM |
| Systems Affected | `app/db/database.py` (`find_duplicate_timestamp`), `tests/test_duplicate_characterization.py`, `tests/test_duplicate_checker.py` |
| Story | STORY-004 |
| PRD | PRD-009 |
| Epic Branch | `epic/PRD-009-duplicate-rescoping` (commit directly on this branch) |

---

## Skills In Use

I listed `.agents/skills/` in full. It contains one skill, and the story's `skills` field is `[]`.

| Skill | Applies? | Reason |
|-------|----------|--------|
| `frontend-design` | **No** | Its `description` limits it to "visual design when building new UI or reshaping an existing one". This story changes one SQL predicate and some tests, and renders nothing. |

No task depends on a skill.

---

## Patterns to Follow

### Naming / SQL: flag predicates are literals, never bound parameters

```python
# SOURCE: app/db/database.py:886-891 (count_successful_queries)
            "SELECT COUNT(*) AS n FROM audit_logs WHERE success = 1"
# SOURCE: app/db/database.py:862-867 (count_blocked_duplicates)
            "SELECT COUNT(*) AS n FROM audit_logs WHERE was_duplicate_blocked = 1"
# SOURCE: tests/test_db.py:1946-1948 (the target shape STORY-002 proved against the index)
                "AND success = 1 AND was_duplicate_blocked = 0 "
                "AND denied_permission IS NULL "
```

### The function being changed

```python
# SOURCE: app/db/database.py:769-780
def find_duplicate_timestamp(prompt_hash: str, since: str) -> Optional[str]:
    with _session() as conn:
        row = conn.execute(
            """
            SELECT timestamp FROM audit_logs
            WHERE prompt_hash = ? AND timestamp >= ?
            ORDER BY timestamp ASC
            LIMIT 1
            """,
            (prompt_hash, since),
        ).fetchone()
        return row["timestamp"] if row is not None else None
```

### Error Handling: unchanged, callers translate

```python
# SOURCE: app/services/duplicate_checker.py (check_duplicate)
    try:
        match = find_duplicate_timestamp(prompt_hash, cutoff)
    except StorageError as exc:
        raise DuplicateCheckError(f"Duplicate lookup failed: {exc}") from exc
```

`_session()` / `_translated()` (`app/db/database.py:582-632`) already map driver errors to `StorageError`. The new predicates add no new failure mode. `test_malformed_db_raises_duplicate_check_error` and `test_outcome_6_internal_failure_duplicate_storage` keep covering the error path.

### Comments citing the PRD decision (house style)

```python
# SOURCE: app/services/duplicate_checker.py (dedup_key)
    # user_id sits inside the key as well as in the lookup's WHERE clause: defence
    # in depth (PRD-009 Section 6.2), so a lookup that forgets the column still
    # cannot match across users. The last turn contributes the prompt_hash value.
```

### Tests: characterization flip convention (from the module docstring)

```python
# SOURCE: tests/test_duplicate_characterization.py:18-21
A story that flips one of these must rewrite the assertion in place with a
comment citing PRD-009 and its decision -- not delete the test.
```

### Tests: store-level seeding

```python
# SOURCE: tests/test_duplicate_checker.py:26-35
def _seed(prompt_hash: str, hours_ago: float) -> str:
    timestamp = _timestamp(hours_ago)
    insert_audit_log(
        AuditLog(
            timestamp=timestamp,
            user_id="juan@empresa.com",
            prompt_hash=prompt_hash,
        )
    )
    return timestamp
```

### Tests: driving `run_query` with an Identity (denial arms)

```python
# SOURCE: tests/test_query_pipeline_authorization.py:195-208
def test_byok_without_permission_blocked_before_openrouter(temp_db):
    identity = Identity(user_id="ana", role="user")  # lacks query:byok

    result = run_query(
        identity=identity,
        prompt="hello world",
        device=None,
        model="gpt-4",
        openrouter_api_key="sk-caller-supplied",
        call_openrouter=_fail_if_called,
    )

    assert isinstance(result, QueryBlockedForbiddenResponse)
    assert result.required_permission == PERMISSION_QUERY_BYOK
```

(`Identity(user_id="reviewer", role="auditor")` lacks `query:submit`, per `:53`.)

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | Add the three flag predicates to `find_duplicate_timestamp`, with a comment citing PRD-009 F4 / D1 / D3 and `IS NULL`. |
| `tests/test_duplicate_characterization.py` | UPDATE | Flip 4 tests in place (docstring + assertions + cited comments). Update the module docstring's "who flips what" so it records that STORY-004 has landed. Leave the cross-user test untouched. |
| `tests/test_duplicate_checker.py` | UPDATE | Add a `_seed_row(**fields)` helper (existing `_seed` and tests byte-identical), store-level exclusion tests, and `run_query`-level tests for the BYOK and `query:submit` denials, the suspicious resend, and the output-redactor retry. |

No files created. `tests/test_query_outcomes_regression.py`, `tests/test_db.py` and every `app/services/*` file stay **unmodified**.

---

## Tasks

Execute in order. Each task is atomic and verifiable. **Before any task:** `docker start harness-libsql-dev` (or the `docker run` in `tests/conftest.py`). On mass fixture errors, `docker restart harness-libsql-dev` and re-run rather than bisecting.

### Task 1: Add the non-verdict predicates to the lookup

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Change the `WHERE` in `find_duplicate_timestamp` to:
  ```sql
  WHERE prompt_hash = ? AND timestamp >= ?
    AND success = 1
    AND was_duplicate_blocked = 0
    AND denied_permission IS NULL
  ORDER BY timestamp ASC
  LIMIT 1
  ```
  Leave the parameters `(prompt_hash, since)`, the signature and the return unchanged. Add a short comment above the `conn.execute` that makes four points:
  - Only a row with a real verdict counts: one that reached the model, or one a content check blocked (PRD-009 F4, D1).
  - Failures (`success = 0`, including the output-redaction arm, T6), policy denials (D1) and duplicate blocks (D3, so a blocked row cannot chain the window) are excluded.
  - `denied_permission` is nullable, so the predicate is `IS NULL`, not `= ''`.
  - The lookup still matches globally on `prompt_hash` until STORY-005 and STORY-007.
- **Mirror**: literal flag comparisons in `count_successful_queries` (`app/db/database.py:886-891`); the target SQL spelled out in `tests/test_db.py:1943-1949`.
- **Validate**: `pytest tests/test_duplicate_checker.py tests/test_query_outcomes_regression.py -q`. All existing tests must be green **unmodified**, including window, boundary, whitespace, earliest and malformed-DB. Then run `pytest tests/test_duplicate_characterization.py -q`, where exactly the 4 STORY-004 tests should fail and the cross-user test should pass. That confirms Task 2 targets the right tests.

### Task 2: Flip the OpenRouterError retry characterization (AC 2, AC 5)

- **File**: `tests/test_duplicate_characterization.py`
- **Action**: UPDATE, in place (same function name, same position)
- **Implement**: In `test_pre_prd009_openrouter_failure_row_blocks_same_prompt_retry` (`:113-141`):
  - **Docstring:** keep the "Pins pre-PRD-009 behaviour" paragraph as history. Replace "Expected to flip in STORY-004 ..." with "Flipped in **STORY-004** (PRD-009 Section 6.3, F4): a `success=0` row is no longer a prior query, so the retry reaches the model."
  - **Line 131:** replace `_fail_if_called` with `calls = []` and `monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))`.
  - **Lines 134-141:** keep `status_code == 200`. Above the rewritten block, add the comment `# PRD-009 STORY-004 (Section 6.3, F4): failed rows no longer count -- was BLOCKED with first_query_at = failed_entry.timestamp.` Replace the `BLOCKED` dict assertion with `assert retry.json()["status"] == "SUCCESS"` and add `assert len(calls) == 1`.
  - **Remaining assertions:** keep `_latest_entry().was_duplicate_blocked is False` (flipped from `True`) and add `_latest_entry().success is True`. Keep `_count_audit_rows() == 2` (still one row per attempt).
- **Mirror**: `_counting_success` usage in `test_pre_prd009_row_from_one_user_blocks_same_prompt_from_another_user` (`:229-230, :246`).
- **Validate**: `pytest tests/test_duplicate_characterization.py -q -k openrouter_failure`

### Task 3: Flip the input PiiRedactorError retry characterization (AC 2, AC 5)

- **File**: `tests/test_duplicate_characterization.py`
- **Action**: UPDATE, in place
- **Implement**: `test_pre_prd009_input_redactor_failure_row_blocks_same_prompt_retry` (`:144-175`), using the same shape as Task 2:
  - **Docstring:** mark the test "Flipped in **STORY-004**". Keep the sentence about restoring the real redactor, reworded: the retry now reaching the model proves the redactor was really restored.
  - **Retry fake:** after restoring `redact` (`:165`), set `call_openrouter` to `_counting_success(calls)`. The first send keeps `_fail_if_called`, because the redactor raises before the model call.
  - **Assertions:** add the cited comment (PRD-009 STORY-004, Section 6.3 / F4), then assert `"SUCCESS"`, `len(calls) == 1`, `was_duplicate_blocked is False`, and `_count_audit_rows() == 2`.
- **Mirror**: Task 2.
- **Validate**: `pytest tests/test_duplicate_characterization.py -q -k input_redactor_failure`

### Task 4: Flip the model-allowlist denial characterization (AC 3, AC 5)

- **File**: `tests/test_duplicate_characterization.py`
- **Action**: UPDATE, in place
- **Implement**: `test_pre_prd009_policy_denial_row_blocks_same_user_resend_with_allowed_model` (`:178-215`):
  - **Docstring:** change it to "Flipped in **STORY-004** (D1: a policy denial is not a prior query)".
  - **Keep as-is:** the denial-side assertions at `:198-203`. `denial_entry.success is True` is exactly *why* `denied_permission IS NULL` is needed, so say that in a one-line comment.
  - **Resend:** before the resend, swap `call_openrouter` to `_counting_success(calls)`.
  - **Assertions at `:209-215`:** add the comment `# PRD-009 STORY-004 (D1): ...was BLOCKED with first_query_at = denial_entry.timestamp`, then assert `resend.json()["status"] == "SUCCESS"`, `len(calls) == 1`, `_count_audit_rows() == 2`.
- **Mirror**: Task 2.
- **Validate**: `pytest tests/test_duplicate_characterization.py -q -k policy_denial`

### Task 5: Flip the D3 chaining characterization (AC 4, AC 5)

- **File**: `tests/test_duplicate_characterization.py`
- **Action**: UPDATE, in place
- **Implement**: `test_pre_prd009_duplicate_blocked_row_keeps_window_alive_after_original_ages_out` (`:252-300`):
  - **Docstring:** keep the timeline diagram. Change its last line to `t=now   same prompt -> reaches the model (was: BLOCKED, first_query_at = B)`, and mark the test "Flipped in **STORY-004** (D3, PRD-009 Section 6.4)".
  - **Name:** keep the function name. AC 5 says in place, and the name still describes the pre-PRD pin the test was written against. Say so in the docstring.
  - **Seeding (`:271-289`):** unchanged.
  - **Model fake:** replace `_fail_if_called` (`:290`) with `_counting_success(calls)`.
  - **Assertions at `:294-300`:** add the comment `# PRD-009 STORY-004 (D3): a duplicate-blocked row no longer extends the window -- was BLOCKED with first_query_at = b_timestamp`. Then assert `status_code == 200`, `response.json()["status"] == "SUCCESS"`, `len(calls) == 1`.
- **Mirror**: Task 2.
- **Validate**: `pytest tests/test_duplicate_characterization.py -q -k keeps_window_alive`

### Task 6: Update the characterization module docstring

- **File**: `tests/test_duplicate_characterization.py`
- **Action**: UPDATE
- **Implement**: In the "Who flips what" list (`:14-16`), record the STORY-004 line as landed: "... -> **STORY-004** (flipped; assertions now pin PRD-009 behaviour, each cited in place)". Leave the STORY-005 line as is. Add one sentence saying the module now mixes pre-PRD pins (STORY-005's) with flipped ones, and that each test's docstring says which kind it is. Do **not** touch `test_pre_prd009_row_from_one_user_blocks_same_prompt_from_another_user`.
- **Validate**: `pytest tests/test_duplicate_characterization.py -q` → all 5 green. Then `git diff tests/test_duplicate_characterization.py` must show no hunk inside `:218-249`.

### Task 7: Store-level exclusion tests (Technical Notes, AC 3, AC 4)

- **File**: `tests/test_duplicate_checker.py`
- **Action**: UPDATE (append only; existing `_seed` and the 8 existing tests stay byte-identical)
- **Implement**:
  - **Helper:** add `_seed_row(prompt_hash, hours_ago, **fields) -> str` after `_seed`. It builds the same `AuditLog(timestamp=..., user_id="juan@empresa.com", prompt_hash=..., **fields)` and returns the timestamp.
  - **Section comment:** add `# PRD-009 STORY-004 (F4): only rows with a real verdict count as a prior query.`
  - **Tests to add:**
    - `test_failed_row_is_not_a_prior_query`: seed `success=False` at −2h. Expect `is_duplicate is False`.
    - `test_policy_denied_row_is_not_a_prior_query`: seed `denied_permission="query:submit"` at −2h (success defaults to True). Expect `False`.
    - `test_duplicate_blocked_row_is_not_a_prior_query`: seed `was_duplicate_blocked=True` at −2h. Expect `False`.
    - `test_suspicious_pattern_row_is_a_prior_query`: seed `suspicious_pattern="ignore previous instructions"` at −2h. Expect `True`, with `first_query_at` equal to the seeded timestamp (D1: content checks count).
    - `test_success_outside_window_and_blocked_row_inside_is_not_a_duplicate`: success at −25h, `was_duplicate_blocked=True` at −2h. Expect `False` (D3).
    - `test_first_query_at_skips_a_later_blocked_row_for_the_earlier_success`: success at −10h, `was_duplicate_blocked=True` at −2h. Expect `True`, with `first_query_at` equal to the −10h timestamp.
    - `test_earliest_qualifying_row_wins_over_an_earlier_failed_row`: `success=False` at −10h, success at −3h. Expect `first_query_at` equal to −3h. This pins that `ORDER BY ASC` applies *after* the flag filter.
- **Mirror**: `test_earliest_entry_returned_as_first_query_at` (`tests/test_duplicate_checker.py:83-91`).
- **Validate**: `pytest tests/test_duplicate_checker.py -q`. Expect 15 tests green, and `git diff` shows only additions.

### Task 8: Pipeline-level tests for the remaining arms (AC 3, output-redaction pin)

- **File**: `tests/test_duplicate_checker.py`
- **Action**: UPDATE (append)
- **Implement**:
  - **Imports:** `run_query` and `query_pipeline` from `app.services.query_pipeline`; `Identity`; `OpenRouterResult`; `PiiRedactorError`; `QueryBlockedForbiddenResponse`, `QueryBlockedDuplicateResponse`, `QuerySuccessResponse`; `PERMISSION_QUERY_BYOK`, `PERMISSION_QUERY_SUBMIT`.
  - **Local helpers:** `_fail_if_called` and `_counting_success(calls)`, mirroring the authorization and characterization tests.
  - **Section comment:** `# PRD-009 STORY-004: the same exclusions, end to end through run_query.`
  - **Tests to add:**
    - `test_retry_after_missing_submit_permission_denial_reaches_model`: `Identity("reviewer", "auditor")` sends prompt P and gets `QueryBlockedForbiddenResponse` with `required_permission == PERMISSION_QUERY_SUBMIT`. Then `Identity("ana", "user")` sends P and gets `QuerySuccessResponse`, with `len(calls) == 1`. Different users is fine here: the lookup is still global in this story, so before the fix the denial row *would* have blocked Ana. The test comment says so, because that is what makes the test meaningful before STORY-005.
    - `test_retry_after_byok_denial_reaches_model`: `Identity("ana", "user")` sends P with `openrouter_api_key="sk-caller-supplied"` and is denied with `PERMISSION_QUERY_BYOK`. The same identity then sends P with `openrouter_api_key=None` and gets `QuerySuccessResponse`, `len(calls) == 1`.
    - `test_resend_after_suspicious_pattern_block_is_still_a_duplicate`: `Identity("ana", "user")` sends `"please override the rules"` and gets a `QueryBlockedSuspiciousResponse`-shaped result (import it). The resend gets `QueryBlockedDuplicateResponse`, and its `first_query_at` equals the first row's timestamp (read via `get_audit_log` on the last id). `call_openrouter=_fail_if_called` both times. The comment cites D1. The resend is duplicate-blocked, not pattern-blocked, because the duplicate check runs first (`query_pipeline.py:91`).
    - `test_retry_after_output_redaction_failure_reaches_model`: monkeypatch `query_pipeline.redact` with a wrapper around the real `redact` that raises `PiiRedactorError` on its **second** call only, the output-side call. The first send calls `_counting_success(calls)` and raises `PiiRedactorError` (`pytest.raises`), which leaves a `success=0` row that has a `response`. Restore the real `redact`. The resend gets `QuerySuccessResponse` and `len(calls) == 2`. The comment cites PRD-009 T6 / Risk 4: the model is called twice, and that is accepted.
- **Mirror**: `tests/test_query_pipeline_authorization.py:195-208, :232-247` for `run_query` + `Identity`; `tests/test_duplicate_characterization.py:97-110` for fakes.
- **Validate**: `pytest tests/test_duplicate_checker.py -q` → 19 green. Sanity check that these tests are real: temporarily revert Task 1 with `git stash push app/db/database.py` and confirm 3 of the 4 new pipeline tests and 5 of the 7 store tests fail. The two suspicious-pattern tests and `test_first_query_at_skips_a_later_blocked_row_for_the_earlier_success` pass either way; the old SQL also returns the earliest row. Then `git stash pop`.

### Task 9: Regression and full suite

- **File**: none
- **Action**: VERIFY
- **Implement / Validate**:
  - `pytest tests/test_query_outcomes_regression.py -q` → green, and `git diff --stat tests/test_query_outcomes_regression.py` is empty (AC 5).
  - `pytest tests/test_query_router.py tests/test_integration.py tests/test_chat_state.py tests/test_pii_dedup_isolation.py tests/test_query_pipeline_authorization.py tests/test_two_instance_smoke.py tests/test_db.py tests/test_dedup_key.py -q` → green with no edits.
  - Full suite: `pytest tests/ -q`.

---

## End-to-End Tests

- [ ] libSQL dev server up (`docker start harness-libsql-dev`). `pytest tests/test_duplicate_characterization.py -v`: 5 pass, the 4 STORY-004 tests assert `SUCCESS`, and the cross-user test still asserts `BLOCKED`.
- [ ] `POST /query` returns 502 on an `OpenRouterError`, then the same prompt returns 200 `SUCCESS` and the model fake is called once (Task 2).
- [ ] `POST /query` returns 500 on an input `PiiRedactorError`, then the same prompt returns 200 `SUCCESS` (Task 3).
- [ ] `POST /query` with a disallowed model is `BLOCKED` with `required_permission`, then the same prompt with `gpt-4` returns `SUCCESS` (Task 4).
- [ ] A success seeded at −25h plus a blocked row at −2h, then `POST /query` returns `SUCCESS` (Task 5).
- [ ] `run_query`: a `query:submit` denial and a BYOK denial are each followed by a successful send; a suspicious-pattern block is followed by a duplicate block; an output-redaction failure is followed by a successful retry (Task 8).
- [ ] `tests/test_query_outcomes_regression.py` passes unmodified.

---

## Validation

```bash
docker start harness-libsql-dev
pytest tests/test_duplicate_checker.py tests/test_duplicate_characterization.py tests/test_query_outcomes_regression.py -v
git diff --stat tests/test_query_outcomes_regression.py   # must be empty
git diff main...HEAD -- app/services/                     # no STORY-004 change under app/services
pytest tests/ -q
```

No linter or formatter is configured in this repo, and there is no frontend change. Validation is pytest against the libSQL dev server.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| A flipped test still wires `_fail_if_called`, so it fails with a 500 or `AssertionError` that looks like a product bug. | Tasks 2–5 swap in `_counting_success` explicitly and assert `len(calls)`. |
| The existing checker tests are edited by accident while the helper is added. | Task 7 appends a new `_seed_row` and does not change `_seed`. Validate with `git diff` (additions only). |
| New tests pass even without the fix, which makes them vacuous. | Task 8's stash-revert check proves the exclusion tests fail on the old SQL. |
| `= ''` or a bound parameter used for `denied_permission`. | Task 1 spells out `IS NULL`. The `query:submit` store test seeds a real non-NULL value. |
| The cross-user test is flipped by mistake. | Task 6 validates that no diff hunk falls in its line range. |
| libSQL dev server degrades after repeated runs (mass fixture errors). | Restart the container and re-run. Don't bisect. |

---

## Acceptance Criteria

(Copied from story `STORY-004`)

- [ ] Given `find_duplicate_timestamp` in `app/db/database.py`, when it is read, then its `WHERE` adds `success = 1 AND was_duplicate_blocked = 0 AND denied_permission IS NULL` to the existing `prompt_hash` and `timestamp` predicates. `ORDER BY timestamp ASC LIMIT 1` is kept, and the signature is unchanged.
- [ ] Given an `OpenRouterError` send followed by the same prompt, and separately an input `PiiRedactorError` send followed by the same prompt, when the retry is posted to `/query`, then it reaches the model (`200 SUCCESS`).
- [ ] Given a model-allowlist denial, a BYOK denial and a missing-`query:submit` denial (each a `success=1` row with `denied_permission`), when the same prompt is sent by an identity that passes authorization, then it reaches the model. Given a suspicious-pattern block row, when the same prompt is sent again, then it is still `BLOCKED` as a duplicate (D1: content checks count).
- [ ] Given a success at −25h and a duplicate-blocked row at −2h, when the same prompt is sent, then it reaches the model. Given a success at −10h and a blocked row at −2h, then `first_query_at` is the success's timestamp.
- [ ] Given the STORY-001 characterization tests for failures, denials and chaining, when this story lands, then each assertion is **flipped in place** (not deleted, not moved) with a comment citing PRD-009 D1 or D3 and this story. The cross-user characterization is untouched, and `tests/test_query_outcomes_regression.py` passes unmodified.
- [ ] Output-redaction failure arm pinned as excluded (Technical Notes; T6 / Risk 4)
- [ ] All tasks completed
- [ ] Full test suite green (`pytest tests/ -q`)
- [ ] Follows existing patterns
