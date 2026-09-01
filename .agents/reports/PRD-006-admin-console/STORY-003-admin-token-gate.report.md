---
story: STORY-003
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-003-admin-token-gate.plan.md
epic_branch: epic/PRD-006-admin-console
commit: 048a873
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-003: AdminState token gate

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-003-admin-token-gate.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `048a873`

## Summary

`chat_ui/chat_ui/admin_state.py` now exists, holding the console's access half. `AdminState` subclasses `rx.State` directly — a sibling of `ChatState`, asserted in a test rather than left to review — and declares the sixteen session vars, from the three gate fields to the record fields STORY-004 will populate.

`authenticate()` mirrors `app/middleware/auth.py:require_admin_token`: `secrets.compare_digest`, never `==`, with both operands encoded to UTF-8 bytes first so a non-ASCII character from a browser field cannot raise `TypeError`. All three failure modes route through one `_refuse()` helper, so there is a single assignment site for the refusal message and no oracle distinguishes an empty token from a wrong one of the right length. `sign_out()` clears the session with `reset()`, which keeps the guarantee true for fields later stories add. `load()` is the authentication guard and nothing else — the read body is STORY-004 — which is the half of PRD-006 Risk 1 that makes an unauthenticated page hold no data regardless of what renders.

Nothing under `app/` changed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Module docstring, imports, refusal constant, field set, `set_token_input` | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 2 | `_refuse()`, `authenticate()`, `sign_out()`, `load()`'s guard | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 3 | Drive the state directly, one assertion per AC (scratchpad) | — | ✅ 8/8 |
| 4 | Prove the blast radius | — | ✅ |
| 5 | *(added)* Commit that evidence as a test file | `tests/test_admin_state.py` | ✅ 15 passed |

## Validation Results

| Check | Result |
|-------|--------|
| Module imports, `__bases__ == (rx.State,)` | ✅ |
| `compare_digest` call sites | ✅ exactly 1 |
| `gate_error` assignment sites | ✅ 2 — the message (one, inside `_refuse`) and the clear on success |
| No `insert_audit_log`, no import from `state.py` | ✅ (only the docstring naming the absence) |
| New tests | ✅ 15 passed |
| Full suite | ✅ 312 passed |
| PRD Section 15's eight pinned test files | ✅ 108 passed, `git diff` empty |
| `git diff --stat -- app/` | ✅ empty |
| E2E state-machine checklist | ✅ 6/6 |

### Task 3 evidence (scratchpad drive, run against the final module)

```
  PASS: default state: authenticated=False, rows=[], gate_error='' OK
  PASS: AC3 correct token: authenticated=True, gate_error cleared, token_input cleared, returned event=load OK
  PASS: AC2 three refusals -> one identical message: 'Access refused. That token was not accepted.' (distinct values: 1) OK
  PASS: AC5 non-ASCII token of differing byte length: refused, no TypeError OK
  PASS: decision 3 blank ADMIN_TOKEN + blank submission: refused OK
  PASS: AC4 sign_out cleared all 16 declared fields to their defaults OK
  PASS: AC6 load() unauthenticated: returned immediately, rows=[], no state written OK
  PASS: post sign_out load(): still gated, rows=[] OK

8/8 checks passed.
```

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/admin_state.py` | CREATE | +157 |
| `tests/test_admin_state.py` | CREATE | +290 |
| `.agents/plans/.../completed/STORY-003-admin-token-gate.plan.md` | CREATE (archived) | +410 |

## Deviations from Plan

1. **A test file was committed, against plan decision 12.** The plan deferred all tests to STORY-006, which owns `tests/test_admin_state.py`. `/implement` Phase 4 makes tests non-optional for new code ("every new function needs ≥1 test"), and three stories is a long time for a security gate to have no CI coverage — the scratchpad script proves the ACs once, at implementation time, and then proves nothing. So the script's assertions were committed as `tests/test_admin_state.py`, scoped to STORY-003's surface only. **STORY-006 extends this file rather than creating it**; its remaining ACs (the load path, the fault arm, the four verdicts, the filter vars, the preview-absence check) are untouched here and still need STORY-004 and STORY-005 to exist. The file's docstring says so, so the next story does not have to rediscover it.

2. **One test beyond the plan's list**: `test_gate_uses_constant_time_comparison` spies `secrets.compare_digest` the way `tests/test_admin_auth.py:87-108` does for the API's gate, and additionally asserts both operands arrive as `bytes`. The plan named this as STORY-006's assertion; it was cheap to bring forward and it pins decision 2's encoding, which is otherwise only visible in a comment.

Everything else matched the plan: the field names, the `_refuse()` helper, the `reset()`-based sign-out, the guard-only `load()`, and the `return AdminState.load` chain are as designed. The `chat_ui/reflex.lock/` churn the plan anticipated (STORY-001 Deviation 5) appeared and was reverted before staging.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_state.py` | `test_admin_state_is_a_sibling_of_chat_state_not_a_substate`, `test_gate_fields_exist_with_refusing_defaults`, `test_correct_token_authenticates_clears_the_error_and_triggers_the_load`, `test_every_wrong_token_is_refused` (×3: empty, wrong-length, wrong-same-length), `test_the_three_refusals_produce_the_identical_message`, `test_non_ascii_token_of_differing_byte_length_is_refused_without_raising`, `test_blank_configured_token_does_not_open_the_console`, `test_gate_uses_constant_time_comparison`, `test_sign_out_clears_the_token_the_rows_and_the_figures`, `test_sign_out_clears_every_declared_var`, `test_load_on_an_unauthenticated_state_reads_nothing`, `test_load_is_still_gated_after_sign_out`, `test_admin_state_has_no_write_path_to_the_audit_log` |

## Acceptance Criteria

- [x] `AdminState` holds `token_input`, `authenticated: bool = False` and `gate_error: str`, and `authenticate()` compares with `secrets.compare_digest` against `settings.ADMIN_TOKEN` — the same comparison `require_admin_token` uses.
- [x] An empty token, a wrong-length token and a wrong token of the correct length produce the **identical** `gate_error` and leave `authenticated` False — asserted as `len(set(messages)) == 1`, not merely as non-empty.
- [x] A correct token sets `authenticated` True, clears `gate_error`, and triggers the load (`authenticate()` returns the `load` event).
- [x] `sign_out()` clears the token, the rows, the summary figures and the last-refreshed stamp from state — all 16 declared vars restored to their defaults, verified field by field.
- [x] `compare_digest` does not raise on operands of differing byte length or on non-ASCII input — both are encoded to UTF-8 first.
- [x] `load()` on an unauthenticated state returns without reading the database; the row list stays empty (Risk 1).
- [x] `app/config.py` and `app/middleware/auth.py` are unmodified — `git diff --stat -- app/` is empty.
- [x] All tasks completed.
- [x] Full suite passes (312); PRD Section 15's eight pinned test files unmodified.
- [x] Follows existing patterns (`chat_ui/chat_ui/state.py`, `app/middleware/auth.py`).

## Notes for the next stories

- **STORY-004** adds the reads *below* `load()`'s existing guard and must re-assert `self.authenticated` inside its first `async with self` block — a background task's read outside the lock can be stale, and `sign_out()` can land mid-read. The field names it populates are fixed in `admin_state.py` and listed in the plan's decision 9.
- **STORY-006** extends `tests/test_admin_state.py`; it does not create it.
- **STORY-008** re-homes `GATE_REFUSED_MESSAGE` into `admin_copy.py`, and `admin_state.py` then imports it. The constant name is the grep target.
