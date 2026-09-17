---
story: STORY-008
prd: PRD-009
slug: end-to-end-duplicate-scope-tests
title: "End-to-end /query tests for every row of the what-counts table: two users, retry after failure, denial, chaining"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-009-duplicate-rescoping
created: 2026-09-17
---

# Plan: End-to-end /query tests for every row of the what-counts table: two users, retry after failure, denial, chaining

## Summary

This story adds one new test module, `tests/test_duplicate_scope.py`. It proves PRD Section 6.3's "what counts as a prior query" table through the real HTTP boundary: `POST /query` with bearer tokens, then `require_permission`, the router, `run_query` and the lookup. Each row of the table gets one named end-to-end test. Each test asserts the HTTP outcome and the audit rows it left: `dedup_key`, `prompt_hash`, `success`, `was_duplicate_blocked` and the flag columns.

The PRD Section 5 examples 1–4 (Juan and María) are the test names. The module also carries the end-to-end Section 11 items that no STORY-002 or STORY-003 test covers:
- boundary at 24h ± 1 minute
- whitespace sensitivity
- a non-NULL key on all seven `log_query` call sites
- `prompt_hash == hash_prompt(prompt)`

No production code changes. The story report records the Section 11 → named-test mapping (AC 5).

## User Story

As a security admin
I want the rescoped control proven through the real HTTP boundary for every kind of prior row
So that "what counts as a prior query" is one readable test module, not an inference spread across unit tests

## Story Reference

- Story file: `.agents/stories/PRD-009-duplicate-rescoping/STORY-008-end-to-end-duplicate-scope-tests.md`
- PRD: `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md` (Sections 4 Tests, 5 stories 1–4, 6.3, 6.4, 9.1, 11, 12 Phase 3)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (tests only; story `type: technical`) |
| Complexity | MEDIUM |
| Systems Affected | `tests/` only. The subject under test is `app/routers/query.py`, `app/services/query_pipeline.py`, `app/services/duplicate_checker.py` and `app/db/database.py::find_duplicate_timestamp` |
| Story | STORY-008 |
| PRD | PRD-009 |
| Epic Branch | `epic/PRD-009-duplicate-rescoping` (commit directly on this branch) |
| Dependencies | STORY-007 ✅ done (`c734df9`) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | I scanned `.agents/skills/`. Its only skill is `frontend-design` (UI visual design). The story's `skills: []` is empty, and this story touches no UI surface, so no rule applies. | — |

---

## Patterns to Follow

### Module prologue, two authenticated identities
```python
# SOURCE: tests/test_duplicate_characterization.py:28-83
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
...
_JUAN_ID = "juan@empresa.com"
_MARIA_ID = "maria@empresa.com"
_JUAN_TOKEN = "juan-token"
_MARIA_TOKEN = "maria-token"
_JUAN_HEADERS = {"Authorization": f"Bearer {_JUAN_TOKEN}"}
_MARIA_HEADERS = {"Authorization": f"Bearer {_MARIA_TOKEN}"}

client = TestClient(app)

@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's two authenticated users."""
    insert_user(User(user_id=_JUAN_ID, role="user", token_hash=hash_token(_JUAN_TOKEN)))
    insert_user(User(user_id=_MARIA_ID, role="user", token_hash=hash_token(_MARIA_TOKEN)))
    return temp_db
```
The same override appears in `tests/test_pii_dedup_isolation.py:62-71`, which the story names. conftest has no client, user or LLM-stub fixture. Each module builds its own.

### Naming: the test-side key helper
```python
# SOURCE: tests/test_duplicate_characterization.py:65-73
@dataclass(frozen=True)
class _Turn:
    role: str
    content: str


def _key(user_id: str, prompt: str) -> str:
    """The single-turn key run_query derives for this caller and raw prompt."""
    return dedup_key(user_id, [_Turn("user", prompt)])
```
Never import the pipeline's private `_UserTurn`.

### Reading rows back by id, never by timestamp
```python
# SOURCE: tests/test_duplicate_characterization.py:86-102
def _count_audit_rows() -> int: ...

def _latest_entry() -> AuditLog:
    # By id, not timestamp: timestamps have one-second resolution, so two rows
    # written by one test routinely share one.
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    return get_audit_log(row["id"])

def _timestamp(hours_ago: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.strftime(_TIMESTAMP_FORMAT)
```

### Stubbing the model (the router is the patch point)
```python
# SOURCE: tests/test_duplicate_characterization.py:105-126, 139-149
monkeypatch.setattr("app.routers.query.call_openrouter", _raise_openrouter_error)
failed = client.post("/query", headers=_JUAN_HEADERS, json={"prompt": prompt})
assert failed.status_code == 502
...
calls = []
monkeypatch.setattr("app.routers.query.call_openrouter", _counting_success(calls))
```
Input redactor failure: `monkeypatch.setattr(query_pipeline, "redact", _boom)`. Output redactor failure: `_boom_on_second_call()` from `tests/test_query_pipeline_dedup_key.py:80-91` (copy it; do not import across test modules).

### Seeded backdated row (only where the age is the point)
```python
# SOURCE: tests/test_duplicate_characterization.py:311-331
insert_audit_log(
    AuditLog(
        timestamp=a_timestamp,
        user_id=_JUAN_ID,
        prompt_hash=hash_prompt(prompt),
        dedup_key=_key(_JUAN_ID, prompt),
        success=True,
    )
)
```

### Foreign session (router refusal, `dedup_key=None`)
```python
# SOURCE: tests/test_query_session_id.py:98-103, 356-376
def _session_owned_by(user_id: str) -> str:
    identity = Identity(user_id=user_id, role="user")
    session_id = chat_sessions.create(identity, "the quarterly close", lambda text: text)
    assert session_id is not None
    return session_id
...
assert response.status_code == 403
assert _last_audit_row().dedup_key is None
```

### Error handling: the HTTP mapping under test (do not change)
```python
# SOURCE: app/routers/query.py:99-106 (per Explore pass)
# DuplicateCheckError -> 500, PiiRedactorError -> 500, OpenRouterError -> 502, body {"detail": str(exc)}
# _deny -> 200 {"status": "BLOCKED", "reason": ..., "required_permission": ...}, row success=1, denied_permission set
# duplicate -> 200 {"status":"BLOCKED","reason":"Duplicate query within 24 hours","first_query_at": ...}
# pattern -> 200 {"status":"BLOCKED","reason":"Suspicious pattern detected","pattern": p}
```

### Flip-citation comment style
```python
# SOURCE: tests/test_duplicate_characterization.py:152-154
# PRD-009 STORY-004 (Section 6.3, F4): failed rows no longer count -- was
# BLOCKED with first_query_at = failed_entry.timestamp.
```
In this module, cite the Section 6.3 row and decision, for example `# Section 6.3 row "OpenRouterError" (F4)`.

---

## Facts the design depends on (verified in Explore)

1. **Timestamps are whole seconds, and `log_query` has no timestamp parameter.** Two live sends in one test usually share a timestamp, so `first_query_at == success_at` alone cannot tell "the success" from "the blocked row" (AC 4). → Add `_backdate(audit_id, hours_ago)`, which runs `UPDATE audit_logs SET timestamp = ? WHERE id = ?` on a row that a real `/query` send wrote. The row's `dedup_key`, `prompt_hash` and flags all stay pipeline-written. Only its age is synthetic. This is the story's "backdated timestamp" exception, applied to a real row instead of a fabricated one.
2. **A missing `query:submit` never reaches `_deny` over HTTP.** `require_permission` returns 403 and writes no row (`app/middleware/auth.py:23-31`). The other two `_deny` arms (disallowed model, BYOK for role `user`) are reachable live. The three denials share one `_deny` call site, so all seven `log_query` call sites are reachable over HTTP.
3. **The duplicate check runs before pattern detection.** A resend of a pattern-blocked prompt returns the *duplicate* body, not the pattern body.
4. **`insert_audit_log(AuditLog(...))` accepts `timestamp` and `dedup_key`.**
5. **The suite needs the libSQL dev server** (`conftest._libsql_endpoint`). The memory note applies: mass fixture errors mean restart the container, not bisect the code.
6. **The working tree has uncommitted edits** to `tests/conftest.py`, `tests/test_conftest_fixtures.py`, `tests/test_pii_redaction_integration.py` and `tests/test_query_session_id.py` (a dead-stream retry in `_reset_database`). They are not part of this story. Do not stage them in the STORY-008 commit.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_duplicate_scope.py` | CREATE | One end-to-end test per Section 6.3 row, PRD Section 5 examples 1–4 as named tests, and the Section 11 end-to-end items (boundary, whitespace, seven call sites, `prompt_hash`) |
| `.agents/reports/PRD-009-duplicate-rescoping/STORY-008-end-to-end-duplicate-scope-tests.report.md` | CREATE (during `/implement`) | AC 5: the Section 11 → named-test mapping |

No production files change. No existing test changes. `tests/test_duplicate_characterization.py` overlaps deliberately and is left alone (story Technical Notes).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Module skeleton, fixtures and helpers

- **File**: `tests/test_duplicate_scope.py`
- **Action**: CREATE
- **Implement**:
  - **Module docstring.** Cite PRD-009 STORY-008, Section 6.3, and say this is the HTTP proof of the table. Say why it overlaps with `test_duplicate_checker.py` (that proves the SQL, this proves the wiring through `require_permission`, the router and `run_query`, where a forgotten `identity.user_id` or key would break). Add a short index: Section 6.3 row → test name.
  - **Env `setdefault`s and imports** as in the characterization prologue. Also import `SUSPICIOUS_PATTERNS` from `app.services.pattern_detector`, `chat_sessions` from `app.services`, `Identity`, and `import app.services.query_pipeline as query_pipeline`.
  - **Constants:** `_JUAN_*` / `_MARIA_*`, `_DUPLICATE_REASON`, `_DISALLOWED_MODEL = "not-a-real-model"`, `_PATTERN = SUSPICIOUS_PATTERNS[0]`, `_FOREIGN_SESSION_DETAIL = "session_id does not belong to the authenticated identity"`.
  - **`temp_db` override** that inserts Juan and María (pattern above).
  - **Helpers:** `_Turn`, `_key`, `_count_audit_rows`, `_latest_entry`, `_timestamp`, `_fail_if_called`, `_fake_success`, `_counting_success(calls)`, `_raise_openrouter_error`, `_boom`, `_boom_on_second_call`, `_session_owned_by`.
  - **New `_backdate(audit_id: int, hours_ago: float) -> str`.** It runs `UPDATE audit_logs SET timestamp = ? WHERE id = ?` with `_timestamp(hours_ago)` and returns the new timestamp. Docstring: timestamps are whole seconds and `log_query` stamps `now`, so aging a real `/query` row is the only way to give two live rows distinguishable times. The key, hash and flags stay pipeline-written.
  - **New `_assert_row_keyed(entry, user_id, prompt)`.** It asserts `entry.user_id == user_id`, `entry.dedup_key == _key(user_id, prompt)` (non-NULL), and `entry.prompt_hash == hash_prompt(prompt)`.
- **Mirror**: `tests/test_duplicate_characterization.py:1-126`, `tests/test_query_pipeline_dedup_key.py:80-91`, `tests/test_query_session_id.py:98-103`
- **Validate**: `pytest tests/test_duplicate_scope.py -q` collects with no errors (0 tests is fine at this step)

### Task 2: Row "Success" — counts (PRD Section 5 story 3, AC 4, D3)

- **File**: `tests/test_duplicate_scope.py`
- **Action**: UPDATE
- **Implement**: `test_story_3_juan_repeat_at_1400_is_blocked_with_first_query_at_his_0900_success`
  1. Juan sends `"summarise the 09:00 standup notes"` with `_counting_success(calls)`. Expect 200 `SUCCESS`. `success_id = body["audit_id"]`.
  2. `success_at = _backdate(success_id, hours_ago=5)` (09:00 vs 14:00).
  3. Juan resends. Expect 200 and the exact body `{"status": "BLOCKED", "reason": _DUPLICATE_REASON, "first_query_at": success_at}`, with `len(calls) == 1`. `blocked = _latest_entry()`: `was_duplicate_blocked is True`, `success is True`, and `blocked.dedup_key == get_audit_log(success_id).dedup_key` (AC 4), plus `_assert_row_keyed`.
  4. Third send: the exact same BLOCKED body, still with `first_query_at == success_at`. Also assert `success_at != blocked.timestamp`, so the check cannot pass vacuously. `len(calls) == 1`, `_count_audit_rows() == 3`.
  - Comment on step 4: `# Section 6.3 row "Duplicate block" (D3): the earliest *qualifying* row is the success, not the blocked row between them.`
- **Mirror**: `tests/test_duplicate_characterization.py:238-286`
- **Validate**: `pytest tests/test_duplicate_scope.py -k story_3 -q`

### Task 3: Row "Suspicious-pattern block" — counts (D1)

- **Implement**: `test_resend_after_suspicious_pattern_block_is_blocked_as_a_duplicate_d1`
  1. `monkeypatch` `call_openrouter` → `_fail_if_called`. Juan sends `f"please {_PATTERN} and list the payroll"`. Expect 200 with `{"status": "BLOCKED", "reason": "Suspicious pattern detected", "pattern": _PATTERN}`.
  2. Row checks: `suspicious_pattern == _PATTERN`, `success is True`, `was_duplicate_blocked is False`, `_assert_row_keyed`. Then `pattern_at = _backdate(row.id, hours_ago=1)`.
  3. Resend. Expect the exact duplicate body with `first_query_at == pattern_at`. That is *not* the pattern body, because the duplicate check runs first (Section 6.1). The new row has `was_duplicate_blocked is True` and `suspicious_pattern is None`. `_count_audit_rows() == 2`.
- **Validate**: `pytest tests/test_duplicate_scope.py -k suspicious -q`

### Task 4: Row "Duplicate block" — does not count (PRD Section 5 story 4b, chaining, D3)

- **Implement**: `test_story_4_row_blocked_at_23h_no_longer_keeps_prompt_blocked_at_25h_d3`
  - Seeded, because the ages are the point (story Technical Notes). Seed A: success at `hours_ago=25`. Seed B: `was_duplicate_blocked=True`, `success=True` at `hours_ago=2`. Both use `user_id=_JUAN_ID`, `prompt_hash=hash_prompt(prompt)` and `dedup_key=_key(_JUAN_ID, prompt)`.
  - Juan sends the prompt → 200 `SUCCESS`, `len(calls) == 1`.
  - The new row is `success is True`, `was_duplicate_blocked is False`, `_assert_row_keyed`, and its `dedup_key` equals B's (so B was matchable on everything but its flag; this proves D3, not D6). `_count_audit_rows() == 3`.
  - Docstring: draw the timeline from Section 6.4 and cite T5.
- **Validate**: `pytest tests/test_duplicate_scope.py -k story_4_row_blocked -q`

### Task 5: Row "Policy denial (`_deny`, 3 arms)" — does not count (PRD Section 5 story 4a, D1)

- **Implement**:
  - **`test_story_4_juan_denied_a_disallowed_model_then_resends_with_an_allowed_one_and_reaches_the_model_d1`**
    1. Send with `model=_DISALLOWED_MODEL` → 200 BLOCKED, `required_permission == f"query:model:{_DISALLOWED_MODEL}"`. The row has `denied_permission` set, `success is True`, and `_assert_row_keyed` (a denial row carries the real key, Section 6.1).
    2. Resend with `"gpt-4"` → `SUCCESS`, `len(calls) == 1`. The new row's `dedup_key` equals the denial row's, which proves the exclusion comes from the flag and not from a key mismatch.
  - **`test_retry_after_byok_denial_reaches_the_model_d1`**
    1. Send with `openrouter_api_key="sk-caller-supplied"` (role `user` lacks `query:byok`) → 200 BLOCKED. The row has `denied_permission` set and is keyed.
    2. Resend without the key → `SUCCESS`, same key.
  - **`test_missing_query_submit_is_refused_at_the_router_and_leaves_no_prior_query_d1`** (third arm)
    1. Insert `User("reviewer@empresa.com", role="auditor", token_hash=hash_token("auditor-token"))`. Post → **403**, `_count_audit_rows() == 0`. Over HTTP this arm never writes a row, so there is nothing that could count.
    2. Seed exception, documented in the docstring: `_deny`'s `query:submit` row is reachable only when `run_query` is called directly, not through `/query`. To still prove the table row through the HTTP lookup, seed one row for **Juan** 1h ago with `denied_permission="query:submit"`, `success=True`, his real key and `prompt_hash`. Juan sends the prompt → `SUCCESS`, `len(calls) == 1`.
    3. Record this extra seed in the story report as a deviation, with the reason: the AC's exception list did not anticipate an arm the router makes unreachable.
- **Mirror**: `tests/test_duplicate_characterization.py:196-235`; BYOK from `tests/test_query_pipeline_dedup_key.py:114-119`
- **Validate**: `pytest tests/test_duplicate_scope.py -k "denied or denial or query_submit" -q`

### Task 6: Rows "Input `PiiRedactorError`", "`OpenRouterError`", "Output `PiiRedactorError`" — do not count (PRD Section 5 story 1, F4)

- **Implement**:
  - **`test_story_1_juan_retries_draft_the_q3_vendor_summary_after_a_502_and_reaches_the_model`**
    1. Prompt `"draft the Q3 vendor summary"`. `_raise_openrouter_error` → 502. The row has `success is False` and `error_message == "boom"`, and is keyed.
    2. Retry with `_counting_success` → 200 `SUCCESS`, `len(calls) == 1`. The retry row has the same key, `was_duplicate_blocked is False`. `_count_audit_rows() == 2`.
  - **`test_retry_after_input_redactor_failure_reaches_the_model`**
    1. Patch `query_pipeline.redact` with `_boom` → 500. The row has `success is False` and is keyed.
    2. Restore the real `redact`, retry → `SUCCESS`, same key.
  - **`test_retry_after_output_redactor_failure_reaches_the_model_again_risk_4`**
    1. Patch `redact` with `_boom_on_second_call()` and `_counting_success(calls)` → 500. The row has `success is False` and is keyed. `len(calls) == 1`: the model *was* called.
    2. Restore `redact`, retry → `SUCCESS`, `len(calls) == 2` (T6 / Risk 4: the second model call is accepted).
- **Validate**: `pytest tests/test_duplicate_scope.py -k "retr" -q`

### Task 7: Row "Router foreign-session refusal" — does not count

- **Implement**: `test_retry_after_foreign_session_refusal_reaches_the_model`
  1. `foreign = _session_owned_by(_MARIA_ID)`. Juan sends the prompt with `session_id=foreign` → 403 with `detail == _FOREIGN_SESSION_DETAIL`. `len(calls) == 0`.
  2. The row has `success is False`, `dedup_key is None` and `user_id == _JUAN_ID`. `prompt_hash == hash_prompt(prompt)`: the evidence is still written.
  3. Juan resends without `session_id` → `SUCCESS`, `len(calls) == 1`. That row carries `_key(_JUAN_ID, prompt)`.
  - Row count before the resend: `chat_sessions.create` writes no audit row, but assert on a `before` delta anyway, not an absolute count.
- **Mirror**: `tests/test_query_session_id.py:356-376`
- **Validate**: `pytest tests/test_duplicate_scope.py -k foreign_session -q`

### Task 8: Row "Any row by another `user_id`" — does not count (PRD Section 5 story 2, AC 3, T1/T2)

- **Implement**: `test_story_2_maria_at_0900_and_juan_at_0905_both_reach_the_model_with_different_keys`
  1. María sends `"summarise this week's incidents"` → `SUCCESS`. `maria_at = _backdate(maria_id, hours_ago=5 + 5/60)`.
  2. Juan sends the identical text → `SUCCESS`, `len(calls) == 2`.
  3. AC 3 checks:
     - `maria_row.dedup_key != juan_row.dedup_key`
     - `maria_row.prompt_hash == juan_row.prompt_hash == hash_prompt(prompt)` (D5)
     - each row satisfies `_assert_row_keyed` for its own user
  4. Window poisoning closed (T2). Juan resends → BLOCKED with `first_query_at == juan_row.timestamp`, and assert `first_query_at != maria_at`. This is non-vacuous because María's row was aged.
- **Validate**: `pytest tests/test_duplicate_scope.py -k story_2 -q`

### Task 9: Row "Pre-PRD row (`dedup_key` NULL)" — does not count (D6, Risk 3)

- **Implement**: `test_pre_prd009_row_with_null_dedup_key_does_not_block_the_same_prompt_risk_3`
  1. `would_be = _key(_JUAN_ID, prompt)`.
  2. Seed a success for Juan at `hours_ago=2` with `prompt_hash=hash_prompt(prompt)` and **no** `dedup_key`. Read it back: `get_audit_log(seed_id).dedup_key is None`, and `would_be is not None`.
  3. Juan sends → `SUCCESS`, `len(calls) == 1`. The new row's `dedup_key == would_be`, and its `prompt_hash` equals the seeded row's. The rows share evidence but only the new one has a key.
- **Validate**: `pytest tests/test_duplicate_scope.py -k pre_prd009 -q`

### Task 10: Section 11 end-to-end items no other allowed module covers

AC 5 lets a Section 11 item map only to this module, STORY-003's `tests/test_dedup_key.py`, or STORY-002's schema tests in `tests/test_db.py`. Today boundary, whitespace, seven-arm and `prompt_hash` are covered only in `test_duplicate_checker.py` / `test_query_pipeline_dedup_key.py`, so this module adds them end to end.

- **Implement**:
  - **`test_success_at_23h59m_still_blocks_the_same_prompt`**
    - Live success, then `_backdate(id, 23 + 59/60)`, then resend → BLOCKED with `first_query_at` equal to the backdated time.
  - **`test_success_at_24h01m_no_longer_blocks_the_same_prompt`**
    - `_backdate(id, 24 + 1/60)`, then resend → `SUCCESS`.
  - **`test_trailing_whitespace_is_a_different_prompt`**
    - `"hello world"` then `"hello world "` → both `SUCCESS`.
    - The two keys differ, and so do the two `prompt_hash` values.
  - **`test_every_call_site_writes_the_credentials_key_and_the_raw_prompt_hash`**
    - `pytest.mark.parametrize` over the seven `log_query` call sites reached through HTTP: `deny-model`, `duplicate`, `pattern`, `input-redactor`, `openrouter`, `output-redactor`, `success`.
    - Each param: request json, a monkeypatch setup callable, the expected status code, and `seed_first` for `duplicate` (a prior live success).
    - Assert `_count_audit_rows() == before + 1`, `row.dedup_key is not None`, and `_assert_row_keyed(row, _JUAN_ID, prompt)`.
    - Docstring: the key comes from the credential, never the body (Section 9.1). Send the `duplicate` case with `json={"user_id": _JUAN_ID, ...}` to show the deprecated body field does not change it.
- **Mirror**: `tests/test_query_pipeline_dedup_key.py:103-176` (arm table), `tests/test_duplicate_checker.py` boundary cases
- **Validate**: `pytest tests/test_duplicate_scope.py -k "23h59m or 24h01m or whitespace or call_site" -q`

### Task 11: Full module + full suite + Section 11 mapping

- **Implement**:
  - Run the module, then the full suite. If fixture errors appear across many tests at once, restart the `harness-libsql-dev` container and re-run; don't bisect.
  - Check that `git diff --stat` touches only `tests/test_duplicate_scope.py`. Also confirm the pre-existing uncommitted conftest edits are still unstaged and not part of this story's commit.
  - Draft the Section 11 mapping for the report (AC 5):

    | Section 11 item | Named test |
    |---|---|
    | Retry after `OpenRouterError` | `test_duplicate_scope.py::test_story_1_juan_retries_draft_the_q3_vendor_summary_after_a_502_and_reaches_the_model` |
    | Retry after input `PiiRedactorError` | `::test_retry_after_input_redactor_failure_reaches_the_model` |
    | Retry after policy denial (model, BYOK, `query:submit`) | `::test_story_4_juan_denied_a_disallowed_model_...`, `::test_retry_after_byok_denial_reaches_the_model_d1`, `::test_missing_query_submit_is_refused_at_the_router_and_leaves_no_prior_query_d1` |
    | Two users not blocked | `::test_story_2_maria_at_0900_and_juan_at_0905_both_reach_the_model_with_different_keys` |
    | Same user after success blocked, `first_query_at` = success | `::test_story_3_juan_repeat_at_1400_is_blocked_with_first_query_at_his_0900_success` |
    | After suspicious-pattern block blocked | `::test_resend_after_suspicious_pattern_block_is_blocked_as_a_duplicate_d1` |
    | Only duplicate-blocked in window → not blocked | `::test_story_4_row_blocked_at_23h_no_longer_keeps_prompt_blocked_at_25h_d3` |
    | Boundary 24h ± 1 min | `::test_success_at_23h59m_still_blocks_the_same_prompt`, `::test_success_at_24h01m_no_longer_blocks_the_same_prompt` |
    | Whitespace sensitivity | `::test_trailing_whitespace_is_a_different_prompt`; `test_dedup_key.py::test_whitespace_is_significant` |
    | Non-NULL key on all seven arms | `::test_every_call_site_writes_the_credentials_key_and_the_raw_prompt_hash` |
    | `prompt_hash == hash_prompt(prompt)` | same parametrized test; `::test_story_2_...` |
    | `init_db()` convergence (fresh / pre-PRD / race / no ALTER) | `test_db.py::test_init_db_adds_a_nullable_dedup_key_column`, `::test_init_db_creates_the_dedup_index_with_its_columns_in_order`, `::test_init_db_migrates_a_pre_dedup_key_database`, `::test_init_db_creates_the_dedup_index_after_adding_the_column`, `::test_two_init_db_calls_racing_on_dedup_key_both_converge`, `::test_init_db_issues_no_alter_when_schema_is_current` |
    | `ValueError` on empty / non-user final / tool turn | `test_dedup_key.py::test_empty_conversation_is_refused`, `::test_final_turn_that_is_not_user_is_refused`, `::test_tool_turn_anywhere_is_refused_naming_prd_016` |
    | Single-turn key ≠ multi-turn key with same last turn | `test_dedup_key.py::test_single_turn_differs_from_multi_turn_with_same_last_turn` |

  - Re-verify every name in the table with `pytest --collect-only -q` before writing the report.
- **Validate**:
  ```bash
  pytest tests/test_duplicate_scope.py -v
  pytest -q
  pytest --collect-only -q tests/test_duplicate_scope.py tests/test_dedup_key.py tests/test_db.py | grep -E "story_|retry|pattern|foreign|pre_prd009|23h59m|24h01m|whitespace|call_site|dedup|refused|differs"
  git diff --stat
  ```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| **Whole-second timestamps make `first_query_at` assertions vacuous** (success and block share a second). | `_backdate` ages the real success row before the repeat. Tasks 2, 3 and 8 also assert that `first_query_at` differs from the blocked / other-user timestamp. |
| **`query:submit` denial is unreachable over HTTP**, which conflicts with AC 1's "no seeded fakes". | Assert the reachable fact (403, zero rows). Seed exactly one documented denial row for the lookup half. Record it in the report as a deviation. Do not change production code to make it reachable. |
| **`_backdate`'s `UPDATE` counts as a "seeded fake".** | It only moves `timestamp` on a row `/query` wrote; key, hash and flags stay real. The docstring says so. If the reviewer rejects it, fall back to seeded rows for Tasks 2/3/8/10 and state the vacuity limit. |
| **An expected outcome fails** (for example, the resend after a pattern block returns the pattern body). | That would be a real wiring defect, which is what this story exists to catch. Stop and report it. Do not weaken the assertion. |
| **Shared `TestClient` and module-level `monkeypatch` leakage between tests.** | Always patch through the `monkeypatch` fixture. Restore `redact` by re-patching with the real function captured before the boom, as in characterization :172-182. |
| **libSQL dev server degradation over a long suite.** | Restart the container on mass fixture errors (memory note). |
| **Stale uncommitted conftest edits get committed with this story.** | Task 11 checks `git diff --stat`. `/implement` stages only `tests/test_duplicate_scope.py`, plus the report and the story/index updates. |

---

## End-to-End Tests

- [ ] `POST /query` as Juan, success aged 5h, then the same prompt twice: both BLOCKED with `first_query_at` = the success; the blocked row carries the success's `dedup_key`
- [ ] Juan's pattern-blocked prompt resent: duplicate BLOCKED with `first_query_at` = the pattern row
- [ ] Seeded 25h success + 2h blocked row, live send: SUCCESS
- [ ] Disallowed model / BYOK denial, then allowed resend: SUCCESS; auditor token: 403, no row
- [ ] 502, input-redactor 500, output-redactor 500, then retry each: SUCCESS
- [ ] Foreign `session_id` 403 (row `dedup_key` NULL), then resend: SUCCESS
- [ ] María then Juan, same prompt: both SUCCESS, different keys, same `prompt_hash`
- [ ] NULL-key pre-PRD success 2h ago, live send: SUCCESS with the would-be key
- [ ] Success aged 23h59m blocks; aged 24h01m does not
- [ ] Every `log_query` call site reached over HTTP writes the credential's key

---

## Validation

```bash
docker ps --filter name=harness-libsql-dev      # dev server up (conftest exits otherwise)
pytest tests/test_duplicate_scope.py -v
pytest -q
git diff --stat                                  # only tests/test_duplicate_scope.py for this story
```

---

## Acceptance Criteria

(Copied from story `STORY-008`)

- [ ] Given a new `tests/test_duplicate_scope.py`, when it runs, then it has one end-to-end test per row of PRD Section 6.3's table, each driving real `POST /query` requests with bearer tokens (no seeded fakes, except for rows that need a backdated timestamp or a pre-PRD NULL key). Each test asserts both the HTTP outcome and the resulting audit rows.
- [ ] Given PRD Section 5 stories 1–4 and their examples, when the module is read, then each example exists as a named test. The names match the Juan/María scenarios closely enough that a reader of the PRD can find them.
- [ ] Given two users sending the same prompt, when both succeed, then their rows carry **different** `dedup_key` values and the **same** `prompt_hash` (D5: evidence unchanged).
- [ ] Given a same-user repeat after a success, when it is blocked, then the blocked row's `dedup_key` equals the success row's, and `was_duplicate_blocked=1`. A third send is still `BLOCKED` with `first_query_at` = the success, not the blocked row (D3).
- [ ] Given the full suite, when it runs, then everything passes. Given the Section 11 functional-requirement checklist, when each item is checked against a test in this module, STORY-003's module or STORY-002's schema tests, then every item maps to a named test, and the mapping is recorded in the story report.
- [ ] All tasks completed
- [ ] Full pytest suite passes
- [ ] No production code changed
- [ ] Follows existing patterns
