---
story: STORY-007
prd: PRD-009
slug: lookup-matches-on-dedup-key
title: "check_duplicate(user_id, key) and the lookup match on dedup_key, with the pinned contract tests updated"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-009-duplicate-rescoping
created: 2026-09-17
---

# Plan: check_duplicate(user_id, key) and the lookup match on dedup_key, with the pinned contract tests updated

## Summary

This story switches the duplicate control from `prompt_hash` to `dedup_key`.
- `find_duplicate_timestamp(user_id, prompt_hash, since)` becomes `find_duplicate_timestamp(user_id, dedup_key, since)`, and its SQL becomes exactly PRD Section 6.3's: `user_id = ? AND dedup_key = ? AND timestamp >= ?`, STORY-004's three flag predicates, and `ORDER BY timestamp ASC LIMIT 1`.
- `check_duplicate(user_id, prompt)` becomes `check_duplicate(user_id, key)`. It stops calling `hash_prompt` and keeps its `StorageError -> DuplicateCheckError` translation.
- `run_query` passes the `key` it already computes at [query_pipeline.py:85](../../../app/services/query_pipeline.py) (STORY-006).

`prompt_hash` is still written but is no longer read by the control (D5).

Pre-PRD rows (NULL `dedup_key`) never match, which is D6. That needs no code, only a test named for Risk 3.

The test work is two things:
1. **Section 6.5 contract updates.** Update the signature pin, the `hash_prompt` census and call sequence, the three spy signatures, the `test_duplicate_checker.py` re-seed and the `test_audit_session_id.py` docstring.
2. **Seeds that relied on `prompt_hash` matching.** Three helpers insert rows with no `dedup_key` and expect a block. They will fail unless they seed the key. Only the helpers change. No outcome assertion changes.

## User Story

As a PRD-010 implementer
I want the duplicate check to take the key rather than a prompt
So that the conversation-shaped key is what the control actually enforces, and multi-turn only has to pass more turns to `dedup_key`

## Story Reference

- Story file: `.agents/stories/PRD-009-duplicate-rescoping/STORY-007-lookup-matches-on-dedup-key.md`
- PRD: `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md` (Sections 4 Lookup/Pipeline/Tests, 6.2, 6.3, 6.5, 10 internal API, 11, 14 Risks 3 and 5, 15 D5 and D6)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/db/database.py`, `app/services/duplicate_checker.py`, `app/services/query_pipeline.py`, tests |
| Story | STORY-007 |
| PRD | PRD-009 |
| Epic Branch | `epic/PRD-009-duplicate-rescoping` (commit directly on this branch) |
| Dependencies | STORY-005 ✅ done (`3d0c86b`), STORY-006 ✅ done (`d56f2c3`) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | I scanned `.agents/skills/`. Its only skill is `frontend-design` (UI visual design), the story's `skills: []` is empty, and no UI surface changes. `chat_ui/` calls `run_query`, not `check_duplicate`, so no rule applies. | — |

---

## Patterns to Follow

### The lookup (current shape: only the second predicate and parameter change)
```python
# SOURCE: app/db/database.py:769-792
def find_duplicate_timestamp(user_id: str, prompt_hash: str, since: str) -> Optional[str]:
    with _session() as conn:
        # Only a row with a real verdict is a prior query: ... (PRD-009 F4, D1) ...
        # Scoped to the caller (PRD-009 F5): ...
        # Still matches on prompt_hash until STORY-007.
        row = conn.execute(
            """
            SELECT timestamp FROM audit_logs
            WHERE user_id = ? AND prompt_hash = ? AND timestamp >= ?
              AND success = 1
              AND was_duplicate_blocked = 0
              AND denied_permission IS NULL
            ORDER BY timestamp ASC
            LIMIT 1
            """,
            (user_id, prompt_hash, since),
        ).fetchone()
        return row["timestamp"] if row is not None else None
```

### Naming: the key parameter is `key`, not `dedup_key`, in `duplicate_checker.py`
`dedup_key` is a module-level function in `duplicate_checker.py`, so a parameter with that name would shadow it. STORY-006 hit the same problem in `_deny` and documented it ([query_pipeline.py:53](../../../app/services/query_pipeline.py)). The PRD's internal API (Section 10) already says `check_duplicate(user_id: str, key: str)`. In `database.py` there is no such function, so `find_duplicate_timestamp(user_id, dedup_key, since)` keeps the PRD name.

### Error handling (unchanged, keep it)
```python
# SOURCE: app/services/duplicate_checker.py:31-34
    try:
        match = find_duplicate_timestamp(user_id, prompt_hash, cutoff)
    except StorageError as exc:
        raise DuplicateCheckError(f"Duplicate lookup failed: {exc}") from exc
```
`test_query_router.py:191-218` and `test_query_outcomes_regression.py:180-211` assert the `"Duplicate lookup failed"` message and the 500.

### Contract test with a PRD citation (update in place, never delete)
```python
# SOURCE: tests/test_pii_dedup_isolation.py:233-242
def test_check_duplicate_public_contract_is_stable():
    signature = inspect.signature(check_duplicate)

    # PRD-009 Section 6.5 (STORY-005): was ["prompt"]. user_id comes first so
    # STORY-007 only swaps the second parameter, prompt -> key.
    assert list(signature.parameters) == ["user_id", "prompt"]
```

### Test-side turn for computing a key
```python
# SOURCE: tests/test_dedup_key.py:31-38
@dataclass(frozen=True)
class _Turn:
    role: str
    content: str


def _user(content):
    return _Turn("user", content)
```
Tests never import the pipeline's private `_UserTurn`. Each module that needs a key defines this small local helper, as `test_dedup_key.py` does:
```python
def _key(user_id: str, prompt: str) -> str:
    return dedup_key(user_id, [_Turn("user", prompt)])
```

### Query-plan test
```python
# SOURCE: tests/test_db.py:2322-2338 (named by the story) and tests/test_db.py:1931-1959 (the dedup instance)
    with get_connection() as conn:
        plan = " ".join(
            row["detail"]
            for row in conn.execute("EXPLAIN QUERY PLAN " "SELECT ...", (...))
        )
    assert "idx_audit_logs_dedup" in plan, plan
    assert "SCAN" not in plan.upper(), plan
```

### Seeded lookup test
```python
# SOURCE: tests/test_duplicate_checker.py:51-61, 70-76
def _seed_row(prompt_hash: str, hours_ago: float, **fields) -> str:
    timestamp = _timestamp(hours_ago)
    fields.setdefault("user_id", _SEEDED_USER)
    insert_audit_log(AuditLog(timestamp=timestamp, prompt_hash=prompt_hash, **fields))
    return timestamp

def test_duplicate_detected_within_24h(temp_db):
    timestamp = _seed(hash_prompt("hello world"), hours_ago=2)
    result = check_duplicate(_SEEDED_USER, "hello world")
    assert result.is_duplicate is True
    assert result.first_query_at == timestamp
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | `find_duplicate_timestamp(user_id, dedup_key, since)`; SQL matches `dedup_key`; comment cites D5/D6 |
| `app/services/duplicate_checker.py` | UPDATE | `check_duplicate(user_id, key)`; no `hash_prompt` call |
| `app/services/query_pipeline.py` | UPDATE | `check_duplicate(identity.user_id, key)` |
| `tests/test_duplicate_checker.py` | UPDATE | Re-seed every case with `user_id` + `dedup_key`; keep window/boundary/whitespace/earliest/F4/F5 cases; add D5 and D6 (Risk 3) cases |
| `tests/test_pii_dedup_isolation.py` | UPDATE | Contract pin `["user_id", "key"]`; census `duplicate_checker.py: 1`; raw-text sequence drops one entry; spy signature |
| `tests/test_query_router.py` | UPDATE | `_seed_duplicate` seeds `dedup_key`; spy signature. Assertions untouched |
| `tests/test_query_pipeline_authorization.py` | UPDATE | Spy signature only |
| `tests/test_chat_state.py` | UPDATE | `_seed_duplicate` seeds `dedup_key` (otherwise two duplicate-bubble tests fail). Assertions untouched |
| `tests/test_duplicate_characterization.py` | UPDATE | D3 test's two seeded rows carry `dedup_key` so the test still proves the exclusion rather than passing vacuously |
| `tests/test_db.py` | UPDATE | Index-plan test: docstring no longer says "until STORY-007"; add a test tying the spelled-out SQL to the function's source |
| `tests/test_query_pipeline_dedup_key.py` | UPDATE | Stale "lookup still matches on prompt_hash" docstring/comment corrected |
| `tests/test_audit_session_id.py` | UPDATE | ":94" docstring: no longer "global 24h exact-match" |

No files to CREATE. `tests/test_duplicate_scope.py` (the end-to-end table) belongs to STORY-008.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Pin the new contract first (tests fail red)

- **File**: `tests/test_pii_dedup_isolation.py`
- **Action**: UPDATE
- **Implement**:
  - `test_check_duplicate_public_contract_is_stable` (:233-246): `["user_id", "key"]`, both `str` with no default. Replace the comment with: `# PRD-009 Section 6.5 (STORY-007): was ["user_id", "prompt"] (STORY-005), ["prompt"] before that. check_duplicate takes the key run_query derives; hashing moved into dedup_key.` The return annotation and `DuplicateCheckResult` field assertions stay unchanged.
  - `test_hash_prompt_call_sites_are_exactly_the_three_audited_ones` (:361-381): `"app/services/duplicate_checker.py": 1`. Rewrite the comment to say the one remaining site is `dedup_key`'s last turn, and that it gets raw text only: the caller's own turn content, which `run_query` passes before any redaction. Remove the stale "No production caller exists yet" sentence. Update the docstring's "Four sites since STORY-003" to say the count is back to three as of STORY-007. Keep the test name (the diff stays visible).
  - `test_hash_prompt_only_ever_receives_raw_text` (:348-356): drop the second `("duplicate_checker", _PROMPT_A)` entry. Update the comment: `# PRD-009 Section 6.5 (STORY-007): one duplicate_checker entry -- dedup_key's last turn. check_duplicate receives the key and hashes nothing.` Update the binding-site comment at :328-329 ("check_duplicate and dedup_key use the global" becomes "dedup_key uses the global"). The `all("<" not in text ...)` assertion stays.
  - `test_pipeline_runs_both_checks_before_any_redaction` spy (:278-280): change its signature to `(user_id, key)`. The `calls[0][1] == _PROMPT_A` assertion must stay byte-identical. To do that, the spy maps the key back to the raw prompt it was derived from: `calls.append(("check_duplicate", _RAW_FOR_KEY.get(key, key)))`, where `_RAW_FOR_KEY = {_key("juan@empresa.com", _PROMPT_A): _PROMPT_A}` is built inside the test. A key derived from anything other than the raw prompt (e.g. redacted text) stays unmapped, and the unchanged assertion fails. Comment: `# PRD-009 Section 6.5 (STORY-007): signature only. check_duplicate now receives the key; mapping it back proves the key was derived from the raw prompt.`
- **Mirror**: `tests/test_pii_dedup_isolation.py:236-238` (citation style)
- **Validate**: `pytest tests/test_pii_dedup_isolation.py`. Expect the contract, census and raw-text tests to FAIL at this point (red before green).

### Task 2: Rewrite `tests/test_duplicate_checker.py` onto the key (red)

- **File**: `tests/test_duplicate_checker.py`
- **Action**: UPDATE
- **Implement**:
  - Add a module comment block after the imports: `# PRD-009 Section 6.5 (STORY-007): re-seeded with user_id + dedup_key. The lookup matches on the key; prompt_hash is written but no longer read (D5).`
  - Import `dedup_key` and add `_Turn` / `_key(user_id, prompt)` as in the pattern above.
  - `_seed(prompt, hours_ago)` and `_seed_row(prompt, hours_ago, **fields)` now take the **prompt**. They derive `user_id = fields.setdefault("user_id", _SEEDED_USER)` and write both `prompt_hash=hash_prompt(prompt)` (a realistic row) and `dedup_key=_key(user_id, prompt)`. Every call site passes `"hello world"`, not `hash_prompt(...)`.
  - Every call `check_duplicate(_SEEDED_USER, "hello world")` becomes `check_duplicate(_SEEDED_USER, _key(_SEEDED_USER, "hello world"))`.
  - Keep every case and its assertions: no match, within 24h, older than 24h, boundary ±1 min, whitespace, earliest, malformed DB, the four F4 cases, the three flag-ordering cases, and the two F5 cases.
  - Whitespace case: keep `hash_prompt("hello world") != hash_prompt("hello world ")` and add `_key(_SEEDED_USER, "hello world") != _key(_SEEDED_USER, "hello world ")`.
  - `test_malformed_db_raises_duplicate_check_error`: pass `_key(_SEEDED_USER, "anything")`.
  - Line 405 (`maria_at = _seed_row(...)`): seed with `"summarise this week's incidents"` and `user_id="maria@empresa.com"`. Her row now carries *her* key, so it proves T2 through the key and not only through the NULL.
  - **New section** `# PRD-009 STORY-007 (D5, D6)`:
    - `test_lookup_matches_on_dedup_key_not_prompt_hash`: seed a row with `dedup_key=_key(user, "hello world")` and `prompt_hash="unrelated"`. It is a duplicate, with `first_query_at` equal to that row's timestamp.
    - `test_same_prompt_hash_with_a_different_key_is_not_a_prior_query`: seed `prompt_hash=hash_prompt("hello world")` with `dedup_key=_key(user, "something else")`. Not a duplicate. This is the D5 half: `prompt_hash` is evidence, not the control.
    - `test_pre_prd009_row_with_null_dedup_key_is_not_a_prior_query_risk_3`: seed a success row for the same user and same prompt 2h ago with `prompt_hash=hash_prompt(prompt)` and no `dedup_key`. `check_duplicate` returns not-duplicate. Docstring: D6/T8, `NULL = ?` is never true; Risk 3's fallback is a follow-up story, not a change here.
    - `test_pre_prd009_row_does_not_block_the_same_prompt_through_run_query_risk_3`: seed the same NULL-key success row for `juan@empresa.com`. `run_query` with `Identity("juan@empresa.com", "user")` and `_counting_success(calls)` returns `QuerySuccessResponse` with `len(calls) == 1`. This is the AC 5 "reaches the model" check.
  - The run_query end-to-end block (:239-431) keeps its assertions. Only the `maria_at` seed changes.
- **Mirror**: `tests/test_duplicate_checker.py:51-61, 208-231`; `tests/test_dedup_key.py:31-38`
- **Validate**: `pytest tests/test_duplicate_checker.py`. Expect failures (signature/SQL still old).

### Task 3: Switch the lookup SQL

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  - Signature: `def find_duplicate_timestamp(user_id: str, dedup_key: str, since: str) -> Optional[str]:`.
  - WHERE clause: `WHERE user_id = ? AND dedup_key = ? AND timestamp >= ?`, with the three flag lines, `ORDER BY` and `LIMIT` unchanged. Params: `(user_id, dedup_key, since)`.
  - Replace `# Still matches on prompt_hash until STORY-007.` with: `# Matches on dedup_key (PRD-009 STORY-007, Section 6.3), served by idx_audit_logs_dedup. prompt_hash is still written but no longer read here: it is /audit's evidence column (D5). A pre-PRD row has a NULL key and never matches, since NULL = ? is never true; that one-off gap is accepted (D6, T8, Risk 3).`
  - `prompt_hash` must not appear in this function.
- **Mirror**: `app/db/database.py:769-792`
- **Validate**: `python -c "import app.db.database"`

### Task 4: `check_duplicate(user_id, key)`

- **File**: `app/services/duplicate_checker.py`
- **Action**: UPDATE
- **Implement**:
  - `def check_duplicate(user_id: str, key: str) -> DuplicateCheckResult:`.
  - Delete `prompt_hash = hash_prompt(prompt)`.
  - Call `find_duplicate_timestamp(user_id, key, cutoff)`.
  - Keep the `try/except StorageError -> DuplicateCheckError("Duplicate lookup failed: ...")` block and the result construction unchanged.
  - One-line comment above the def: `# key is dedup_key(user_id, turns) (PRD-009 Section 6.2); hashing happens there, from raw text. Named key, not dedup_key, so it does not shadow that function.`
  - `hash_prompt` stays defined here (audit_logger and dedup_key use it).
- **Mirror**: `app/services/duplicate_checker.py:27-38`
- **Validate**: `pytest tests/test_duplicate_checker.py tests/test_dedup_key.py`. Green except the run_query end-to-end block, which needs Task 5.

### Task 5: The pipeline passes the key

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: line 115 becomes `duplicate_result = check_duplicate(identity.user_id, key)`. Extend the comment above it (:112-114) with one line: `# The key derived above, once (PRD-009 STORY-007): the control checks exactly what every row records.` Nothing else moves, so the check order is preserved (Section 6.1).
- **Mirror**: `app/services/query_pipeline.py:85, 112-115`
- **Validate**: `pytest tests/test_duplicate_checker.py tests/test_pii_dedup_isolation.py tests/test_query_pipeline_dedup_key.py`. All green.

### Task 6: Adapt the remaining spies (signature only)

- **Files**: `tests/test_query_router.py`, `tests/test_query_pipeline_authorization.py`
- **Action**: UPDATE
- **Implement**:
  - `test_query_router.py:318-320`: `def _spy_duplicate(user_id, key):` appends `_RAW_FOR_KEY.get(key, key)` and returns `real_check_duplicate(user_id, key)`. `_RAW_FOR_KEY = {_key("juan@empresa.com", _PII_PROMPT): _PII_PROMPT}`. The assertion `seen_duplicate == [_PII_PROMPT]` stays byte-identical. Add a PRD-009 Section 6.5 (STORY-007) signature-only comment, as in Task 1.
  - `test_query_pipeline_authorization.py:47-49`: `def _spy_check_duplicate(user_id, key):` appends `key` and calls `real_check_duplicate(user_id, key)`. `assert duplicate_calls == []` is unchanged. Add the same citation comment.
- **Mirror**: Task 1 spy
- **Validate**: `pytest tests/test_query_pipeline_authorization.py -k before_check_duplicate` and `pytest tests/test_query_router.py -k raw_prompt`

### Task 7: Seed helpers that expected a `prompt_hash` match

- **Files**: `tests/test_query_router.py` (:52-63), `tests/test_chat_state.py` (:88-99), `tests/test_duplicate_characterization.py` (:299-315)
- **Action**: UPDATE
- **Implement**:
  - Both `_seed_duplicate(prompt, hours_ago=2)` helpers add `dedup_key=_key("juan@empresa.com", prompt)` beside `prompt_hash`. Comment: `# PRD-009 STORY-007: the lookup matches on dedup_key, so a seeded prior query carries the key /query derives for this user and prompt. A row without one is a pre-PRD row and never matches (D6).`
  - `test_duplicate_prompt_blocked_before_openrouter_call`, `test_run_query_duplicate_blocked_before_openrouter_call` and `test_chat_state_send_duplicate_blocked_appends_system_bubble` keep every assertion.
  - Characterization D3 test: both seeded rows get `dedup_key=_key(_JUAN_ID, prompt)`, with a docstring line saying the key makes the blocked row matchable, so SUCCESS proves D3 and not D6.
  - First confirm that `test_query_router.py`'s default client authenticates as `juan@empresa.com`. The key must use the credential's `user_id`, not the body's (Section 9.1).
- **Mirror**: `tests/test_duplicate_checker.py` `_seed_row` after Task 2
- **Validate**: `pytest tests/test_query_router.py tests/test_chat_state.py tests/test_duplicate_characterization.py`

### Task 8: Index plan tied to the function's real SQL

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**:
  - `test_dedup_lookup_shape_uses_the_dedup_index` (:1931-1959): the query and assertions stay the same (they already follow `test_find_user_by_token_hash_uses_the_index`). Rewrite the docstring: `PRD-009 STORY-007 AC 3: find_duplicate_timestamp's lookup (Section 6.3) is served by idx_audit_logs_dedup. The SQL is spelled out as test_find_user_by_token_hash_uses_the_index spells its own; test_find_duplicate_timestamp_sql_is_the_planned_shape keeps the two from drifting.`
  - Hoist the spelled-out SELECT into a module constant `_DEDUP_LOOKUP_SQL` placed right above the test.
  - New `test_find_duplicate_timestamp_sql_is_the_planned_shape()`: collapse whitespace in `inspect.getsource(database.find_duplicate_timestamp)`'s triple-quoted SQL and assert that `" ".join(_DEDUP_LOOKUP_SQL.split())` is contained in it, and that `"prompt_hash"` is not in the source. That covers AC 1 ("exactly Section 6.3's SQL; `prompt_hash` no longer appears"). Extract the SQL with a regex on `"""(.*?)"""` (re.S) over the function source, and compare whitespace-normalized strings.
  - Add one behavioural check in the plan test: `find_duplicate_timestamp("ana@empresa.com", "k", "2026-09-15T09:00:00Z") == "2026-09-16T09:00:00Z"`.
- **Mirror**: `tests/test_db.py:2322-2338`; source-scan style of `tests/test_query_pipeline_dedup_key.py:231-243`
- **Validate**: `pytest tests/test_db.py -k "dedup"`

### Task 9: Stale docstrings and comments

- **Files**: `tests/test_audit_session_id.py` (:94-97), `tests/test_query_pipeline_dedup_key.py` (:12-13, :158-159)
- **Action**: UPDATE
- **Implement**:
  - `test_audit_session_id.py`: replace "`check_duplicate` is a global 24h exact-match over the prompt hash (PRD Section 4, Out of Scope: this PRD does not rescope it)" with "`check_duplicate` blocks the same user's same prompt within 24h (PRD-009 rescoped it to a per-user `dedup_key`; the session is not part of a single-turn key)". The test logic is unchanged.
  - `test_query_pipeline_dedup_key.py`:
    - Module docstring: "This story only *writes* the key..." becomes a note that STORY-007 switched the lookup to the key, so the duplicate arm's seeded send blocks *because* its row carries the key.
    - Comment at :158-159: same correction.
    - No code change.
- **Validate**: `pytest tests/test_audit_session_id.py tests/test_query_pipeline_dedup_key.py`

### Task 10: Full-suite regression + residual grep

- **Implement**:
  - Run the full suite.
  - Confirm with `git diff` that `tests/test_integration.py`, `tests/test_query_outcomes_regression.py` and `tests/test_two_instance_smoke.py` are untouched, and that no assertion line in `test_query_router.py` changed (only `_seed_duplicate` and the spy).
  - Grep `app/` and `tests/` for `check_duplicate(` with a prompt argument, and for `"until STORY-007"` / `"Still matches on prompt_hash"`.
- **Validate**:
  ```bash
  pytest -q
  git diff --stat
  git diff tests/test_integration.py tests/test_query_outcomes_regression.py tests/test_two_instance_smoke.py   # must be empty
  ```
  Per memory: if many fixture errors appear at once, restart the libSQL dev container and re-run; don't bisect.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| **Seeded rows without a key silently stop matching** (router, chat_state, characterization). | Task 7 updates only the seed helpers. The census (Explore pass) found these three. Task 10's full run catches any missed seed as a failing duplicate-block assertion, not a silent pass. |
| **`test_two_instance_smoke.py::test_a_prompt_outside_the_window_is_not_blocked_by_the_other_instance` goes vacuous.** `do_plant_audit_row` plants a NULL-key row, so SUCCESS no longer depends on the window. | PRD Section 11 requires the file to pass *unmodified*, so this story leaves it alone. Record it in the report as a finding for STORY-009 (invariance pass) to decide on. The window itself stays covered by the boundary cases in `test_duplicate_checker.py`. |
| **A spy change hides a raw-text regression** (Risk 5). | The spy maps key back to prompt through a key built from the *raw* prompt, so the unchanged assertion still fails if the pipeline ever keys redacted text. The `hash_prompt` sequence test independently pins the single raw `dedup_key` hash. |
| **An outcome assertion "needs" to change.** | Story Technical Notes: stop and re-check the key wiring (credential `user_id`, single user turn). Do not edit the assertion. |
| **Shadowing `dedup_key` inside `duplicate_checker.py`.** | Parameter named `key` (Section 10). |
| **`test_chat_state.py:481-503` / `test_query_pipeline_session_passthrough.py:150-181` rely on the key ignoring `session_id`.** | This is true today (`query_pipeline.py:85` keys one user turn). No change here; they act as regression guards for exactly that. |

---

## End-to-End Tests

- [ ] `POST /query` twice with the same prompt as the same user: second is `BLOCKED`, `first_query_at` = first row's timestamp (`test_integration.py::test_duplicate_query_blocked_and_openrouter_never_called`, `test_query_outcomes_regression.py::test_outcome_2_*`, both unmodified)
- [ ] Pre-PRD NULL-key success row for the same user and prompt within 24h: the send reaches the model (Task 2, Risk 3 test)
- [ ] Row with matching `prompt_hash` but different `dedup_key`: not a duplicate (Task 2)
- [ ] `DROP TABLE audit_logs`, then `POST /query`: 500 with `"Duplicate lookup failed"` (`test_duplicate_check_storage_failure_returns_500`, unmodified)
- [ ] Chat UI send then API send of the same prompt: API send `BLOCKED` (`test_chat_state.py::test_duplicate_sent_via_chat_blocks_identical_prompt_via_api`, unmodified)
- [ ] `EXPLAIN QUERY PLAN` of the Section 6.3 lookup names `idx_audit_logs_dedup` with no `SCAN`

---

## Validation

```bash
pytest tests/test_duplicate_checker.py tests/test_pii_dedup_isolation.py tests/test_db.py -k "dedup or duplicate or hash_prompt or contract" -q
pytest -q
git diff tests/test_integration.py tests/test_query_outcomes_regression.py tests/test_two_instance_smoke.py   # empty
grep -n "prompt_hash" app/db/database.py | grep -n "find_duplicate" ; grep -rn "until STORY-007" app tests   # both empty
```

---

## Acceptance Criteria

(Copied from story `STORY-007`)

- [ ] Given `find_duplicate_timestamp(user_id: str, dedup_key: str, since: str)`, when it is read, then its SQL is exactly PRD Section 6.3's: `user_id = ? AND dedup_key = ? AND timestamp >= ?` plus the three flag predicates from STORY-004, `ORDER BY timestamp ASC LIMIT 1`. `prompt_hash` no longer appears in it.
- [ ] Given `check_duplicate(user_id: str, key: str) -> DuplicateCheckResult`, when `run_query` calls it, then it passes the key computed in STORY-006. `check_duplicate` itself no longer calls `hash_prompt`, and it still raises `DuplicateCheckError` on `StorageError` (the router's 500 is unchanged).
- [ ] Given `EXPLAIN QUERY PLAN` on the lookup against a `temp_db`, when it is inspected, then it uses `idx_audit_logs_dedup`. The assertion follows `test_find_user_by_token_hash_uses_the_index` in `tests/test_db.py`.
- [ ] Given the contract tests in PRD Section 6.5, when this story lands, then each is updated in place with a PRD-009 citation:
  - `test_check_duplicate_public_contract_is_stable` pins `["user_id", "key"]`
  - the `hash_prompt` census returns to `duplicate_checker.py: 1`
  - `test_hash_prompt_only_ever_receives_raw_text` drops the second `duplicate_checker` entry
  - the spies adapt their signature only
  - `tests/test_duplicate_checker.py` is re-seeded with `user_id` + `dedup_key`, keeping every window/boundary/whitespace/earliest case
  - `tests/test_audit_session_id.py`'s "global 24h exact-match" docstring is corrected
- [ ] Given a pre-PRD row (`dedup_key` NULL) for the same user and prompt within 24h, when the prompt is sent, then it reaches the model (D6, T8, pinned by a test naming Risk 3). The regression module and every non-contract assertion in `test_query_router.py` / `test_integration.py` pass unmodified.
- [ ] All tasks completed
- [ ] Full pytest suite passes
- [ ] Follows existing patterns
