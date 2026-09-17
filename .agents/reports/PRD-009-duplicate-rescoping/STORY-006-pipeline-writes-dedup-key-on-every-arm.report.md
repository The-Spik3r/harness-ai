---
story: STORY-006
prd: PRD-009
plan: .agents/plans/PRD-009-duplicate-rescoping/completed/STORY-006-pipeline-writes-dedup-key-on-every-arm.plan.md
epic_branch: epic/PRD-009-duplicate-rescoping
commit: d56f2c3
status: COMPLETE
completed: 2026-09-17
---

# Implementation Report — STORY-006: run_query computes dedup_key once and log_query writes it on all seven arms

**Plan**: `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-006-pipeline-writes-dedup-key-on-every-arm.plan.md`
**Epic Branch**: `epic/PRD-009-duplicate-rescoping`
**Commit**: `d56f2c3`

## Summary

Every audit row `run_query` writes now carries its duplicate key. `run_query` derives `key = dedup_key(identity.user_id, [_UserTurn(prompt)])` once, as its first statement, before the first `authorize(...)`. `_UserTurn` is a private frozen dataclass: `content: str`, and `role` fixed to `"user"` with `init=False`.

Where the key goes:
- **`log_query`:** gained `dedup_key: Optional[str] = None` and writes it onto `AuditLog`.
- **`_deny`:** takes `dedup_key` as a required parameter with no default, placed next to `session_id`, with a comment citing PRD-009 Risk 6.
- **Pipeline call sites:** all seven `log_query` calls pass it.
- **Router:** the foreign-session refusal passes `dedup_key=None` explicitly. Point 5 of the router's numbered rationale comment explains why.

The lookup is untouched: `check_duplicate(user_id, prompt)` still matches on `prompt_hash` until STORY-007.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `log_query` accepts and writes `dedup_key` | `app/services/audit_logger.py` | ✅ |
| 2 | `log_query` round-trip + default tests | `tests/test_audit_logger.py` | ✅ |
| 3 | `_UserTurn`; key computed once before authorization; required on `_deny`; all seven call sites | `app/services/query_pipeline.py` | ✅ |
| 4 | Refusal passes `dedup_key=None`, commented | `app/routers/query.py` | ✅ |
| 5 | Refusal row NULL-key test | `tests/test_query_session_id.py` | ✅ |
| 6 | Hash-order contract test gains the leading key-derivation entry (Section 6.5) | `tests/test_pii_dedup_isolation.py` | ✅ |
| 7 | Per-arm, signature, census, once-before-authorization and `prompt_hash` tests | `tests/test_query_pipeline_dedup_key.py` | ✅ |
| 8 | Regression sweep, unmodified-file check, full suite | — | ✅ (see Validation) |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`python -c "from app.main import app"`) | ✅ |
| Frontend lint | N/A (no `frontend/`; no UI change) |
| `grep -n "log_query(" app/services/query_pipeline.py` | ✅ 7 call sites; `dedup_key=` appears 10 times (7 + 3 `_deny` calls) |
| After Task 3, before Task 6 | ✅ exactly one predicted failure (`test_hash_prompt_only_ever_receives_raw_text`), nothing else |
| `tests/test_query_pipeline_dedup_key.py` | ✅ 13 passed (9 arms + 4) |
| Mutation check | ✅ removing `dedup_key=key` from the OpenRouter arm fails both the `openrouter-failure` case and the census test (reverted) |
| Regression / characterization / integration | ✅ 26 passed; `git diff --stat` on regression, characterization, integration and router suites is empty |
| Chat state, authorization, session passthrough, two-instance smoke, dedup_key, checker, db, audit session id | ✅ 387 passed, no edits |
| `test_forbidden_identity_blocked_before_check_duplicate` | ✅ |
| `/health` on a live app | ✅ `{"status":"ok"}` |
| Full suite `pytest tests/ -q` | ⚠️ 1927 passed, 25 skipped, 1 failed. The failure predates this story; see below. |
| E2E | ✅ 5/5 |

**The one full-suite failure** is `tests/test_pii_redaction_integration.py::test_no_pre_epic_test_function_was_removed_or_renamed`. It happens in this Windows environment, not in this story's code:
- `git show` output of `tests/reports_fixture.py` from the epic base is decoded as `cp1252` and hits byte `0x9d` (`UnicodeDecodeError` in subprocess's reader thread).
- It fails identically on clean `HEAD` (`2f840d8`) with this story's changes stashed.
- It passes with `PYTHONUTF8=1`: the whole module, 19 passed.

This story does not touch that file or that test.

## E2E

- [x] `pytest tests/test_query_pipeline_dedup_key.py -v` shows 9 arm ids. Each writes exactly one row, with a non-NULL key equal to `dedup_key(user_id, [user(prompt)])`.
- [x] `POST /query` with a foreign `session_id` → 403, one row, `dedup_key IS NULL` (`test_the_403_refusal_row_carries_no_dedup_key`).
- [x] `POST /query` success through `TestClient` (`tests/test_integration.py`, unmodified) → green. The pipeline success row's `prompt_hash == hash_prompt(prompt)` (`test_prompt_hash_is_unchanged_by_the_key`).
- [x] **Manual smoke** against a live `uvicorn app.main:app`:
  - **Setup:** `DATABASE_URL` pointed at the local libSQL dev container, not the Turso URL in `.env`. A throwaway `smoke-story-006@local` user was bootstrapped with `scripts/manage_users.py`.
  - **Request:** a pattern-blocked prompt, so OpenRouter was not called. The response was `BLOCKED` / `Suspicious pattern detected`.
  - **Row:** `prompt_hash` and `dedup_key` are both non-NULL and differ. `prompt_hash == sha256(prompt)`, and `dedup_key` equals the key recomputed from the stored `user_id` and prompt.
- [x] Six-outcome regression (`tests/test_query_outcomes_regression.py`) green and unmodified.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/audit_logger.py` | UPDATE | +2 |
| `app/services/query_pipeline.py` | UPDATE | +31/-5 |
| `app/routers/query.py` | UPDATE | +8 |
| `tests/test_audit_logger.py` | UPDATE | +31 |
| `tests/test_pii_dedup_isolation.py` | UPDATE | +6/-1 |
| `tests/test_query_session_id.py` | UPDATE | +21 |
| `tests/test_query_pipeline_dedup_key.py` | CREATE | +279 |

## Deviations from Plan

- **Router comment placement:** the rationale went in as point 5 of the existing numbered comment block, with a short `# see 5. above` on the argument. The plan allowed either placement.
- **New router test position:** `test_the_403_refusal_row_carries_no_dedup_key` sits inside the file's AC 6 section, next to the other refusal-row tests, rather than at the end of the file. No existing test was edited.
- **Extra smoke-test setup:** the app refuses to start with no active users (`RbacNotBootstrappedError`), so a throwaway user was created in the local dev database. The Turso database configured in `.env` was not touched.
- **Full suite:** there is one failure that predates this story and depends on the environment (see Validation). It was not fixed here because it is unrelated to this story.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_dedup_key.py` | `test_every_arm_writes_one_row_carrying_the_single_turn_key` with nine cases: `permission-denied`, `model-not-permitted`, `byok-denied`, `duplicate-blocked`, `pattern-blocked`, `input-redactor-failure`, `openrouter-failure`, `output-redactor-failure`, `success`. Also `test_prompt_hash_is_unchanged_by_the_key`, `test_deny_requires_dedup_key_with_no_default`, `test_every_log_query_call_site_in_the_pipeline_passes_dedup_key`, `test_key_is_computed_once_before_authorization`. |
| `tests/test_audit_logger.py` | `test_dedup_key_persisted_when_supplied`, `test_dedup_key_defaults_to_none_when_omitted` |
| `tests/test_query_session_id.py` | `test_the_403_refusal_row_carries_no_dedup_key` |
| `tests/test_pii_dedup_isolation.py` | `test_hash_prompt_only_ever_receives_raw_text` updated with the leading `("duplicate_checker", _PROMPT_A)` and a Section 6.5 comment |

## Acceptance Criteria

- [x] `run_query` computes `key = dedup_key(identity.user_id, [_UserTurn(prompt)])` exactly once, before the first `authorize(...)`, using a private frozen dataclass that satisfies `DedupTurn`.
- [x] `log_query` accepts `dedup_key: Optional[str] = None` and puts it on the `AuditLog`. `_deny`'s `dedup_key` is required with no default, like `session_id`, with a comment citing PRD-009 Risk 6.
- [x] Each pipeline arm driven once writes exactly one row whose `dedup_key` equals `dedup_key(identity.user_id, [user(prompt)])`, non-NULL. There is one parametrized case per arm.
- [x] The router's foreign-session refusal passes `dedup_key=None` explicitly, with the required comment. A test asserts that row's `dedup_key is None`.
- [x] `test_hash_prompt_only_ever_receives_raw_text` gains the leading `("duplicate_checker", _PROMPT_A)` with a Section 6.5 comment, and every hashed text is still raw. The lookup is unchanged, and the regression and characterization modules pass unmodified.
- [x] `tests/test_chat_state.py` passes with no change to `chat_ui/chat_ui/state.py`.
- [x] All tasks completed.
- [ ] Full test suite green. **Not fully met:** 1 failure that predates this story and depends on the environment (cp1252), documented above. It passes with `PYTHONUTF8=1`.
- [x] Follows existing patterns (PRD-008 STORY-009 `session_id` threading).
