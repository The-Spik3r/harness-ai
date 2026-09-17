---
story: STORY-005
prd: PRD-009
slug: lookup-scoped-by-user
title: "Duplicate lookup scoped by the authenticated user_id"
type: BUG_FIX
complexity: LOW
epic_branch: epic/PRD-009-duplicate-rescoping
created: 2026-09-17
---

# Plan: Duplicate lookup scoped by the authenticated user_id

## Summary

This story adds `user_id = ?` to `find_duplicate_timestamp`'s `WHERE` clause. The signature becomes `find_duplicate_timestamp(user_id, prompt_hash, since)`, and `check_duplicate` becomes `check_duplicate(user_id, prompt)`. `run_query` passes `identity.user_id`, which is resolved from the bearer credential. The router has already refused any body `user_id` that differs from it (`app/routers/query.py:25-29`).

The lookup still matches on `prompt_hash`, and all four STORY-004 flag predicates stay. `dedup_key` isn't read yet; that happens in STORY-007.

The tests change in four ways:

1. The STORY-001 cross-user characterization is flipped in place.
2. The contract test is re-pinned to `["user_id", "prompt"]`.
3. The three `check_duplicate` spies change their wrapper signature only.
4. `tests/test_duplicate_checker.py` passes the seeded user explicitly and gains cross-user store and pipeline tests.

Exploration also found **three pre-existing tests that relied on the global scope with different users.** The story's Technical Notes asked for these to be reasoned about one at a time, and each gets its own task (Tasks 6–7):

- `tests/test_pii_dedup_isolation.py::test_identical_pii_prompt_is_still_blocked_as_duplicate` **breaks**. María's identical send now reaches the model, and `_fail_if_called` raises.
- `tests/test_pii_dedup_isolation.py::test_distinct_pii_prompts_are_never_duplicates_of_each_other` still **passes, but proves nothing**. Two users now go through regardless of what gets hashed, so the test no longer shows that dedup hashes raw text rather than redacted text.
- `tests/test_duplicate_checker.py::test_retry_after_missing_submit_permission_denial_reaches_model` also still **passes, but proves nothing**. A reviewer's denial followed by Ana's send succeeds under per-user scope alone, so D1 is no longer exercised on that arm.

## User Story

As an end user
I want my prompt not to be blocked by someone else's identical prompt
So that a common question works for everyone who asks it, and nobody can poison a colleague's window by sending their prompt first.

## Story Reference

- Story file: `.agents/stories/PRD-009-duplicate-rescoping/STORY-005-lookup-scoped-by-user.md`
- PRD: `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md`, Sections 4 (Lookup), 5 (story 2), 6.5, 7 (F5), 9.1, 9.2 (T1, T2), 12 (Phase 2)
- Depends on: STORY-004 (`dde39d9`, **done**)
- Blocks: STORY-007

## Metadata

| Field | Value |
|-------|-------|
| Type | BUG_FIX |
| Complexity | LOW |
| Systems Affected | `app/db/database.py` (`find_duplicate_timestamp`), `app/services/duplicate_checker.py` (`check_duplicate`), `app/services/query_pipeline.py` (one call), 5 test modules |
| Story | STORY-005 |
| PRD | PRD-009 |
| Epic Branch | `epic/PRD-009-duplicate-rescoping` (commit directly on this branch) |

### Exploration findings the story text doesn't state

1. **`run_query` already holds the credential-resolved id.** `identity: Identity` is a required parameter. The router builds it via `Depends(require_permission(...))` and returns 403 on a body mismatch before `run_query` runs; `test_body_user_id_mismatch_returns_403_without_overriding` (`tests/test_query_router.py:94`) pins that. `ChatState.send()` also goes through `run_query` with its authenticated identity. Passing `identity.user_id` at `app/services/query_pipeline.py:90` is therefore the only production caller change.
2. **All three spies call the original positionally with one argument.** They are `def _spy…(prompt): …; return real(prompt)`, at `tests/test_pii_dedup_isolation.py:~270`, `tests/test_query_router.py:315`, and `tests/test_query_pipeline_authorization.py:47`. The pipeline call must stay **positional** (`check_duplicate(identity.user_id, prompt)`) so that a `(user_id, prompt)` wrapper receives it, and each wrapper still records `prompt`. That keeps `calls[0][1] == _PROMPT_A`, `seen_duplicate == [_PII_PROMPT]` and `duplicate_calls == []` byte-identical.
3. **The `hash_prompt` census and sequence tests are unaffected.** No `hash_prompt(` call is added or moved (`tests/test_pii_dedup_isolation.py:322-369`).
4. **`tests/test_two_instance_smoke.py:91, :709` cite `duplicate_checker.py:28`,** which is the line holding `prompt_hash = hash_prompt(prompt)` and the cutoff next to it. Keep the new `check_duplicate` signature on **one line**, so line 28 doesn't move and the smoke test needs no edit.
5. **`tests/test_dedup_key.py:221` stubs `find_duplicate_timestamp` with `*args, **kwargs`,** so the new parameter doesn't affect it.
6. **Stale docstrings are left to their owners.**
   - `tests/test_db.py:1931-1933` says the lookup "does not take this shape until STORY-007". That stays true, because it still matches on `prompt_hash`, so it gets **no edit**.
   - The "global 24h exact-match" docstring in `tests/test_audit_session_id.py:94` is assigned to STORY-007 (story file line 40). **Not touched here.** The test itself uses distinct prompts and stays green.
7. **The other same-prompt tests use one user for both sends and stay green unmodified.** They were checked individually:
   - `test_integration.py:72` (juan, twice)
   - `test_query_router.py:171`: `_seed_duplicate` seeds `juan@empresa.com`, and the client's default token is juan's
   - `test_query_outcomes_regression.py:91` (default client, twice)
   - `test_chat_state.py` at `~143`, `~226`, `~480` (juan for both seed and identity)
   - `test_query_pipeline_session_passthrough.py:150` (same `juan` identity)
   - `test_two_instance_smoke.py:671` (`smoke_user` on both instances)
   - In `test_duplicate_checker.py`, the BYOK, suspicious-resend and output-redaction `run_query` tests use `ana` both times
8. **Timestamps have one-second resolution** (`%Y-%m-%dT%H:%M:%SZ`). Two HTTP sends in one test can share a timestamp, so `first_query_at == own_at` can't by itself prove "his own, not María's". AC 2's distinguishing proof therefore seeds María's row hours earlier (Task 5), and the HTTP flip (Task 4) asserts the observable behaviour.

---

## Skills In Use

I listed `.agents/skills/` in full. It contains one skill, and the story's `skills` field is `[]`.

| Skill | Applies? | Reason |
|-------|----------|--------|
| `frontend-design` | **No** | Its `description` covers "visual design when building new UI or reshaping an existing one". This story changes one SQL predicate, two signatures and some tests, and renders nothing. |

No task depends on a skill.

---

## Patterns to Follow

### The function being changed (after STORY-004)
```python
# SOURCE: app/db/database.py:769-789
def find_duplicate_timestamp(prompt_hash: str, since: str) -> Optional[str]:
    with _session() as conn:
        # Only a row with a real verdict is a prior query: ...
        # Still global on prompt_hash until STORY-005 / STORY-007.
        row = conn.execute(
            """
            SELECT timestamp FROM audit_logs
            WHERE prompt_hash = ? AND timestamp >= ?
              AND success = 1
              AND was_duplicate_blocked = 0
              AND denied_permission IS NULL
            ORDER BY timestamp ASC
            LIMIT 1
            """,
            (prompt_hash, since),
        ).fetchone()
        return row["timestamp"] if row is not None else None
```
The target column order is the index's order, `(user_id, …, timestamp)`: `tests/test_db.py:1943-1949` and `idx_audit_logs_dedup` in `app/db/models.py:73`.

### Naming: `user_id` first, matching `dedup_key`
```python
# SOURCE: app/services/duplicate_checker.py:55
def dedup_key(user_id: str, turns: Sequence[DedupTurn]) -> str:
```

### Error Handling: unchanged, callers translate
```python
# SOURCE: app/services/duplicate_checker.py:27-38
def check_duplicate(prompt: str) -> DuplicateCheckResult:
    prompt_hash = hash_prompt(prompt)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(_TIMESTAMP_FORMAT)

    try:
        match = find_duplicate_timestamp(prompt_hash, cutoff)
    except StorageError as exc:
        raise DuplicateCheckError(f"Duplicate lookup failed: {exc}") from exc
```
The new predicate adds no failure mode. `test_malformed_db_raises_duplicate_check_error` and `test_outcome_6_internal_failure_duplicate_storage` keep covering the error path.

### Identity in the pipeline
```python
# SOURCE: app/services/query_pipeline.py:90-95
    duplicate_result = check_duplicate(prompt)

    if duplicate_result.is_duplicate:
        log_query(
            user_id=identity.user_id,
```

### Tests: flip-in-place convention (docstring paragraph + inline cited comment)
```python
# SOURCE: tests/test_duplicate_characterization.py:~195-222 (STORY-004 flip)
    Flipped in **STORY-004** (D1: a policy denial is not a prior query): the
    resend reaches the model.
    ...
    assert resend.status_code == 200
    # PRD-009 STORY-004 (D1): a policy denial is not a prior query -- was
    # BLOCKED with first_query_at = denial_entry.timestamp.
    assert resend.json()["status"] == "SUCCESS"
    assert len(calls) == 1
```

### Tests: the spy shape that changes
```python
# SOURCE: tests/test_query_pipeline_authorization.py:43-50
    real_check_duplicate = query_pipeline.check_duplicate
    def _spy_check_duplicate(prompt):
        duplicate_calls.append(prompt)
        return real_check_duplicate(prompt)
    monkeypatch.setattr(query_pipeline, "check_duplicate", _spy_check_duplicate)
```

### Tests: store-level seeding
```python
# SOURCE: tests/test_duplicate_checker.py:37-60
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

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | `find_duplicate_timestamp(user_id, prompt_hash, since)`, add `user_id = ? AND` first in the `WHERE`, and update the "still global" comment |
| `app/services/duplicate_checker.py` | UPDATE | `check_duplicate(user_id: str, prompt: str)`, forwarding `user_id` |
| `app/services/query_pipeline.py` | UPDATE | `check_duplicate(identity.user_id, prompt)`, positional, with a one-line comment (credential-resolved id, PRD-009 9.1) |
| `tests/test_pii_dedup_isolation.py` | UPDATE | Re-pin the contract test; change one spy's wrapper signature; make the two PII dedup tests same-user (Task 6) |
| `tests/test_query_router.py` | UPDATE | Spy wrapper signature only |
| `tests/test_query_pipeline_authorization.py` | UPDATE | Spy wrapper signature only |
| `tests/test_duplicate_characterization.py` | UPDATE | Flip the cross-user pin in place; module docstring records that STORY-005 has landed |
| `tests/test_duplicate_checker.py` | UPDATE | Pass the seeded user to `check_duplicate`; add store-level and `run_query`-level cross-user tests; make the `query:submit` denial test same-user (Task 7) |

No files are created. `tests/test_query_outcomes_regression.py`, `tests/test_integration.py`, `tests/test_two_instance_smoke.py`, `tests/test_db.py`, `tests/test_dedup_key.py` and `tests/test_audit_session_id.py` stay **unmodified**.

---

## Tasks

Execute in order. **Before any task:** `docker start harness-libsql-dev` (or the `docker run` in `tests/conftest.py`). On mass fixture errors, run `docker restart harness-libsql-dev` and re-run rather than bisecting.

Tasks 1–3 form one atomic signature change. The suite doesn't go green again until the spies are updated in Task 3.

### Task 1: Scope the lookup by user_id

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  - **Signature:** `def find_duplicate_timestamp(user_id: str, prompt_hash: str, since: str) -> Optional[str]:`
  - **WHERE:** `WHERE user_id = ? AND prompt_hash = ? AND timestamp >= ?`, with the three flag predicates, `ORDER BY timestamp ASC` and `LIMIT 1` unchanged. The params become `(user_id, prompt_hash, since)`.
  - **Comment:** replace the last line, `# Still global on prompt_hash until STORY-005 / STORY-007.`, with two points:
    - Scoped to the caller (PRD-009 F5; T2: nobody can poison another user's window; T1: N accounts may each repeat once, which is accepted and mitigated by PRD-013).
    - Still matches on `prompt_hash` until STORY-007.
- **Mirror**: column order of `tests/test_db.py:1943-1949` / `idx_audit_logs_dedup`.
- **Validate**: `python -c "import app.db.database"`. The suite is run after Task 3.

### Task 2: `check_duplicate(user_id, prompt)` and the pipeline call

- **File**: `app/services/duplicate_checker.py`, `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  - **`duplicate_checker.py`:** change the signature to `def check_duplicate(user_id: str, prompt: str) -> DuplicateCheckResult:`. It must stay **one line** so `prompt_hash = hash_prompt(prompt)` stays at line 28 (Finding 4). Call `find_duplicate_timestamp(user_id, prompt_hash, cutoff)`. Nothing else changes: no `pii`/`redact` text is added (`test_duplicate_checker_has_no_redaction_dependency`).
  - **`query_pipeline.py:90`:** change the call to `duplicate_result = check_duplicate(identity.user_id, prompt)`, **positional**. Above it, add a short comment: `identity.user_id` is the credential-resolved id, never the request body's, so a caller can't choose whose window they are checked against (PRD-009 9.1, F5).
- **Mirror**: `dedup_key(user_id, turns)` parameter order (`app/services/duplicate_checker.py:55`).
- **Validate**: `git diff -U0 app/services/duplicate_checker.py`. Line 28 is still `prompt_hash = hash_prompt(prompt)`.

### Task 3: Re-pin the contract test and adapt the three spies (AC 1, AC 3)

- **File**: `tests/test_pii_dedup_isolation.py`, `tests/test_query_router.py`, `tests/test_query_pipeline_authorization.py`
- **Action**: UPDATE
- **Implement**:
  - **`test_check_duplicate_public_contract_is_stable`** (`tests/test_pii_dedup_isolation.py:229-239`):
    - **Comment:** add one above the signature assertions: `# PRD-009 Section 6.5 (STORY-005): was ["prompt"]. user_id comes first so STORY-007 only swaps the second parameter, prompt -> key.`
    - **Parameters:** assert `list(signature.parameters) == ["user_id", "prompt"]`. For **both** names, assert `.annotation is str` and `.default is inspect.Parameter.empty`.
    - **Unchanged:** keep the return-annotation and dataclass-fields assertions byte-identical.
  - **Spies:** in each of the three below, change the wrapper to `def _spy…(user_id, prompt):`, keep what it records (`prompt`), and `return real…(user_id, prompt)`. Nothing else in those tests changes, assertions included.
    - `test_pipeline_runs_both_checks_before_any_redaction` (`tests/test_pii_dedup_isolation.py:~265-307`)
    - `test_duplicate_and_pattern_checks_still_receive_the_raw_prompt` (`tests/test_query_router.py:312-336`)
    - `test_forbidden_identity_blocked_before_check_duplicate` (`tests/test_query_pipeline_authorization.py:43-66`)
- **Validate**:
  - `pytest tests/test_pii_dedup_isolation.py tests/test_query_router.py tests/test_query_pipeline_authorization.py -q` → everything green except `test_identical_pii_prompt_is_still_blocked_as_duplicate`, which Task 6 fixes.
  - `git diff tests/test_query_router.py tests/test_query_pipeline_authorization.py` shows only the two wrapper lines per file (`def` + `return`).

### Task 4: Flip the cross-user characterization in place (AC 2, AC 4)

- **File**: `tests/test_duplicate_characterization.py`
- **Action**: UPDATE, in place (same function name, same position)
- **Implement**:
  - **In `test_pre_prd009_row_from_one_user_blocks_same_prompt_from_another_user` (`:225-256`):**
    - **Docstring:** keep the "Pins pre-PRD-009 behaviour (defect #2 ...; threat T2)" paragraph as history. Replace "Expected to flip in **STORY-005** ..." with "Flipped in **STORY-005** (PRD-009 T1/T2, F5): the lookup is scoped by the authenticated `user_id`, so María's send reaches the model, and only her own resend is blocked, against her own row." As STORY-004 did, add that the name is kept because it describes the pre-PRD pin.
    - **Juan's send:** unchanged.
    - **María's send:** keep `status_code == 200`. Above the rewritten assertions, add `# PRD-009 STORY-005 (T1/T2): another user's row is no longer a prior query -- was BLOCKED with first_query_at = juan_at.` Then assert `maria.json()["status"] == "SUCCESS"` and `len(calls) == 2`. Replace the `was_duplicate_blocked is True` check with `maria_entry.user_id == _MARIA_ID` (kept) and `maria_entry.was_duplicate_blocked is False`, and set `maria_at = maria_entry.timestamp`.
    - **Append María's resend** of the same prompt. Assert `200` and `== {"status": "BLOCKED", "reason": _DUPLICATE_REASON, "first_query_at": maria_at}`, plus `len(calls) == 2`, and check that `_latest_entry()` has `user_id == _MARIA_ID` and `was_duplicate_blocked is True`. Add a comment that her own success is the prior. Timestamps have one-second resolution, so the "not Juan's" proof lives in `test_duplicate_checker.py` (Task 5).
  - **Module docstring (`:14-16`):** mark the STORY-005 line as landed, like STORY-004's: "(flipped; assertions now pin PRD-009 behaviour, each cited in place)". Replace "The module therefore mixes pre-PRD pins (STORY-005's) with flipped ones" with a sentence saying that every test in the module is now flipped, and each docstring records the pre-PRD pin it started as.
- **Mirror**: STORY-004's flip of `test_pre_prd009_policy_denial_row_blocks_same_user_resend_with_allowed_model` (`:183-222`).
- **Validate**:
  - `pytest tests/test_duplicate_characterization.py -q` → 5 green.
  - `git diff tests/test_duplicate_characterization.py` has hunks only in the module docstring and in `:225-256`.

### Task 5: Store and pipeline tests in `test_duplicate_checker.py` (AC 1, AC 2, Technical Notes)

- **File**: `tests/test_duplicate_checker.py`
- **Action**: UPDATE
- **Implement**:
  1. **Constant:** add `_SEEDED_USER = "juan@empresa.com"` beside `_TIMESTAMP_FORMAT`. `_seed` and `_seed_row` use it instead of the literal, which is a behaviour-neutral change.
  2. **Existing calls:** every existing `check_duplicate("…")` call becomes `check_duplicate(_SEEDED_USER, "…")`. That is one-line edits at the ~15 call sites (`:64-201`). Test names, seeds and assertions are otherwise unchanged. This is the Technical Notes instruction: "callers now pass the same id".
  3. **New section comment:** `# PRD-009 STORY-005 (F5; T1/T2): the lookup is scoped by the authenticated user_id.` Under it, add two store-level tests.
     - `test_row_from_a_different_user_is_not_a_prior_query`:
       - Seed a success row at −2h with `user_id="maria@empresa.com"` via `_seed_row(hash_prompt("hello world"), 2, user_id=…)`. `_seed_row` must let `user_id` be overridden: build `AuditLog(**{"user_id": _SEEDED_USER, **fields}, ...)`, or pop it from `fields`.
       - Assert that `check_duplicate(_SEEDED_USER, "hello world").is_duplicate is False`.
     - `test_own_row_is_found_when_another_users_row_is_earlier`:
       - Seed María's success at −10h and Juan's at −3h.
       - `check_duplicate(_SEEDED_USER, "hello world")` is a duplicate with `first_query_at` equal to the −3h timestamp, not −10h. This pins that `ORDER BY ASC` applies inside the user's own rows.
  4. **New pipeline test** `test_same_prompt_from_two_users_reaches_model_and_each_is_blocked_only_by_their_own_success`, which follows AC 2 literally:
     - **María's prior:** `insert_audit_log` a success row for `maria@empresa.com` at −3h with `prompt_hash=hash_prompt(prompt)`. Seeding it well in the past makes the timestamps provably distinct (Finding 8).
     - **Juan's first send:** `run_query(identity=Identity(user_id="juan@empresa.com", role="user"), prompt=prompt, ..., call_openrouter=_counting_success(calls))` returns `QuerySuccessResponse`, with `len(calls) == 1`. Record `juan_at = get_audit_log(_last_audit_id()).timestamp`.
     - **Juan's resend:** with `_fail_if_called`, it returns `QueryBlockedDuplicateResponse`. Assert `first_query_at == juan_at` and `!= maria_at`.
     - The comment cites PRD-009 T2: María's send cannot poison Juan's window, and Juan's block points at his own success.
- **Mirror**: `test_earliest_qualifying_row_wins_over_an_earlier_failed_row` and `test_retry_after_byok_denial_reaches_model` in the same file.
- **Validate**:
  - `pytest tests/test_duplicate_checker.py -q` → all green (22 tests).
  - **Vacuity check:** `git stash push app/db/database.py app/services/duplicate_checker.py app/services/query_pipeline.py` and confirm the three new tests fail (they would TypeError or assert on the old code). Then `git stash pop`.

### Task 6: Reason about the two PII dedup tests individually (Technical Notes)

- **File**: `tests/test_pii_dedup_isolation.py`
- **Action**: UPDATE (the sender only; assertions unchanged)
- **Implement**:
  - **`test_identical_pii_prompt_is_still_blocked_as_duplicate` (`:122-141`):**
    - **Why it changes:** the test exists to show that "dedup is not simply broken in the presence of PII". It used María as the second sender only because the lookup was global. With per-user scope, María's identical send reaches the model, so the unchanged test would fail on `_fail_if_called`.
    - **Change:** the second send uses `json={"user_id": "juan@empresa.com", ...}` and `headers=_JUAN_HEADERS`.
    - **Comment:** add `# PRD-009 STORY-005 (T1/T2): dedup is per caller, so the control repeats the same user's send -- was María, which only blocked while the lookup was global.`
    - **Unchanged:** the `BLOCKED` and reason assertions.
  - **`test_distinct_pii_prompts_are_never_duplicates_of_each_other` (`:99-119`):**
    - **Why it changes:** it still passes, but no longer proves RF-6. Two different users now go through whatever is hashed, including a hash over redacted text, where both prompts collide as `_REDACTED_BOTH`.
    - **Change:** make the second send Juan's as well, so a redacted-text hash **would** block it and the test regains its meaning.
    - **Comment:** add `# PRD-009 STORY-005 (T1/T2): same sender, so a redacted-text hash would collide and block -- two users would pass regardless of what is hashed.`
    - **Unchanged:** all assertions, including `seen == [_REDACTED_BOTH, _REDACTED_BOTH]` and `_count_audit_rows() == 2`.
    - **Also update** the trailing inline comment ("-- and dedup still let both through.") only if it now reads wrong. It doesn't, so leave it.
- **Validate**:
  - `pytest tests/test_pii_dedup_isolation.py -q` → all green.
  - **Vacuity check for the distinct test:** temporarily hash the redacted prompt in `check_duplicate` (a local, unstaged edit such as `hash_prompt("contact me at <EMAIL_ADDRESS>")`). Confirm the test now fails, then revert with `git checkout app/services/duplicate_checker.py`, re-applying Task 2's edit if it was lost. A simpler alternative: reason in the report that Juan → Juan with colliding redacted text would block. The stash check is preferred.

### Task 7: Keep the `query:submit` denial test meaningful (Technical Notes)

- **File**: `tests/test_duplicate_checker.py`
- **Action**: UPDATE
- **Implement**:
  - **Target:** `test_retry_after_missing_submit_permission_denial_reaches_model` (`:~230`).
  - **The problem:** a reviewer's denial followed by Ana's send now passes on scope alone, so it no longer exercises D1 on the `query:submit` arm.
  - **The fix:** use one `user_id` with two roles. The denied send is `Identity(user_id="ana", role="auditor")`, which lacks `query:submit`. The resend is `Identity(user_id="ana", role="user")`, the same person after an admin grants the role.
  - **Comment:** replace the stale one ("The lookup is still global on prompt_hash in this story ...") with `# PRD-009 STORY-005: same user_id, role changed between sends -- per-user scope alone would let a different user through, so only D1 (a denial is not a prior query) explains the success.`
  - **Unchanged:** the assertions.
- **Validate**:
  - `pytest tests/test_duplicate_checker.py -q -k missing_submit` → green.
  - **Vacuity check:** temporarily remove `AND denied_permission IS NULL` from the lookup and confirm this test fails, then restore it.

### Task 8: Regression and full suite (AC 5)

- **File**: none
- **Action**: VERIFY
- **Implement / Validate**:
  - Run `pytest tests/test_query_outcomes_regression.py tests/test_integration.py -q` → green. `git diff --stat tests/test_query_outcomes_regression.py tests/test_integration.py` must be empty.
  - Run `pytest tests/test_two_instance_smoke.py tests/test_chat_state.py tests/test_query_pipeline_session_passthrough.py tests/test_dedup_key.py tests/test_db.py tests/test_audit_session_id.py -q` → green, with no edits.
  - Run `grep -rn "check_duplicate(\|find_duplicate_timestamp(" app/ tests/` → every call passes a user id. The only exceptions are the `def` lines, the `*args` stub, and docstrings.
  - Full suite: `pytest tests/ -q`.

---

## End-to-End Tests

- [ ] libSQL dev server is up. `pytest tests/test_duplicate_characterization.py -v` → 5 pass. The cross-user test asserts that María gets `SUCCESS`, and her resend gets `BLOCKED` with `first_query_at` equal to her own row.
- [ ] `POST /query`: Juan sends P and gets `SUCCESS`. María sends P and gets `SUCCESS`; the model is called twice. María sends P again and gets `BLOCKED` (Task 4).
- [ ] `run_query`: María's success is seeded at −3h. Juan's P gets `SUCCESS`, then Juan's P again gets `BLOCKED`, with `first_query_at == juan_at != maria_at` (Task 5).
- [ ] `POST /query` with a body `user_id` that differs from the token → 403, unchanged (`test_body_user_id_mismatch_returns_403_without_overriding`).
- [ ] `tests/test_query_outcomes_regression.py` and `tests/test_integration.py` pass unmodified.

---

## Validation

```bash
docker start harness-libsql-dev
pytest tests/test_duplicate_checker.py tests/test_duplicate_characterization.py tests/test_pii_dedup_isolation.py tests/test_query_router.py tests/test_query_pipeline_authorization.py -v
git diff --stat tests/test_query_outcomes_regression.py tests/test_integration.py tests/test_two_instance_smoke.py   # must be empty
pytest tests/ -q
```

No linter or formatter is configured in this repo, and there is no frontend change. Validation is pytest against the libSQL dev server.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| A spy changes more than its signature and hides a regression (PRD Risk 5). | Task 3's diff check allows only the `def` and `return` lines per spy. The pipeline call stays positional, so wrappers need no keyword handling. |
| A different-user test keeps passing but no longer proves anything. | Tasks 6 and 7 re-point three tests at a single user, and each has a vacuity check. |
| `first_query_at` "his own, not María's" is asserted with equal same-second timestamps, so the assertion is vacuous. | Task 5 seeds María's row at −3h and asserts `!=` explicitly. |
| `duplicate_checker.py:28`, cited by the smoke test, drifts. | Task 2 keeps the signature on one line and checks line 28. |
| The body `user_id` is used instead of the credential's. | The pipeline only receives `identity`. The router's 403 on a mismatch is already pinned. The Task 2 comment states the rule. |
| libSQL dev server degrades after repeated runs (mass fixture errors). | Restart the container and re-run. Don't bisect. |

---

## Acceptance Criteria

(Copied from story `STORY-005`)

- [ ] Given `find_duplicate_timestamp(user_id: str, prompt_hash: str, since: str)` and `check_duplicate(user_id: str, prompt: str)`, when they are read, then the lookup adds `user_id = ?` and `run_query` passes `identity.user_id`, the credential-resolved id and never the request body's.
- [ ] Given María's successful send of a prompt, when Juan sends the identical prompt within 24h, then Juan's request reaches the model. Given Juan then sends it again, then Juan is `BLOCKED` with `first_query_at` equal to **his own** success's timestamp, not María's.
- [ ] Given `test_check_duplicate_public_contract_is_stable`, when this story lands, then it pins `["user_id", "prompt"]` (both `str`, no defaults) with a comment citing PRD-009 Section 6.5 and noting that STORY-007 changes the second parameter to `key`. The spies wrapping `check_duplicate` in `tests/test_pii_dedup_isolation.py`, `tests/test_query_router.py` and `tests/test_query_pipeline_authorization.py` change their wrapper signature only, and every assertion in those tests is unchanged.
- [ ] Given the STORY-001 cross-user characterization test, when this story lands, then it is flipped in place with a comment citing PRD-009 T1/T2 and this story.
- [ ] Given the full suite, then `tests/test_query_outcomes_regression.py` and `tests/test_integration.py` pass unmodified.
- [ ] Different-user reliance was reasoned about per test (Tasks 6–7), not bulk-edited
- [ ] All tasks completed
- [ ] Full test suite green (`pytest tests/ -q`)
- [ ] Follows existing patterns
