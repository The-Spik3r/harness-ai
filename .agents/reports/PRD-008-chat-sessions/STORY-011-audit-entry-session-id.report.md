---
story: STORY-011
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-011-audit-entry-session-id.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: c69055e
status: COMPLETE
completed: 2026-09-04
---

# Implementation Report — STORY-011: AuditQueryEntry.session_id so GET /audit reports the conversation

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-011-audit-entry-session-id.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `c69055e`

## Summary

`GET /audit` now reports the conversation a row came from. `AuditQueryEntry` gains `session_id: Optional[str] = None` and `app/routers/admin.py` projects `log.session_id` — two lines of production code, because STORY-008 through STORY-010 had already built everything underneath: the column is written by `insert_audit_log`, hydrated by `_row_to_audit_log` on both read shapes, threaded to all seven `log_query` call sites, and accepted at the API boundary as a validated UUID4. The value was in hand at the projection and simply went unprojected. This is where it becomes readable, so that three rows that were one conversation are visibly one conversation instead of a guess.

No validator was added on the read model, deliberately: the value is checked at the write end by `QueryRequest` (STORY-010), and revalidating on the way out would refuse to report rows the database legitimately holds. `GET /stats` and `StatsResponse` are untouched, as are `success` and `error_message` — the projection defect PRD-006 Section 13 parked stays parked rather than being smuggled into this commit.

The real work was in the three assertions that pinned the old response shape. See **Deviations**.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `AuditQueryEntry.session_id`, appended last, no validator | `app/models/schemas.py` | ✅ |
| 2 | `session_id=log.session_id` in the `GET /audit` projection | `app/routers/admin.py` | ✅ |
| 3 | Expected-dict entry + optional/default assertion | `tests/test_schemas.py` | ✅ |
| 4 | Key-set literal + present/absent test | `tests/test_audit_router.py` | ✅ |
| 5 | Contract key list + docstring record | `tests/test_pii_redaction_integration.py` | ✅ |
| 6 | End-to-end suite: three sends, one session, read back | `tests/test_audit_session_id.py` | ✅ |
| 7 | Boundary proved by diff; full suite | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Full suite `pytest -q` | ✅ 1393 passed |
| Pinned suites (`test_audit_router`, `test_stats_router`, `test_admin_auth`, `test_db`, `test_route_reservations`, `test_chat_state`) | ✅ |
| `tests/test_untouched_app.py` census | ✅ |
| `tests/test_integration.py`, `test_route_reservations.py`, `test_query_router.py` — run, not edited | ✅ |
| E2E against a live server | ✅ 11/11 |
| `git diff -- chat_ui/` empty (AC 7) | ✅ |
| Frontend lint | n/a — no frontend file changed |

The full suite was run against the local libSQL dev container, not the remote Turso endpoint in `.env`.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/models/schemas.py` | UPDATE | +16 |
| `app/routers/admin.py` | UPDATE | +5 |
| `tests/test_audit_session_id.py` | CREATE | +166 |
| `tests/test_audit_router.py` | UPDATE | +32 / -0 |
| `tests/test_schemas.py` | UPDATE | +19 / -0 |
| `tests/test_pii_redaction_integration.py` | UPDATE | +7 / -0 |

Every test-file change is an insertion. No line was deleted from any suite.

## Deviations from Plan

**One, anticipated by the plan and carried out as specified: AC 5's "passes unmodified" could not hold literally.**

Three assertions enumerated the `/audit` entry's keys exactly, and an additive field makes each of them unequal. There is no implementation of AC 1 and AC 2 that leaves them passing:

| Assertion | Suite | Change |
|---|---|---|
| `set(entry.keys()) == {...}` in `test_valid_token_returns_expected_shape` | `tests/test_audit_router.py:75` | `"session_id"` added |
| `response.model_dump() == {...}` in `test_audit_response_shape` | `tests/test_schemas.py:99` | `"session_id": None` added |
| `sorted(entry) == [...]` in `test_audit_endpoint_contract_has_no_preview_fields` | `tests/test_pii_redaction_integration.py:190` | `"session_id"` added |

What AC 5 still binds was honoured in full and proved by diff: **no test function was deleted, renamed, or had an assertion removed or weakened.** `git diff --stat tests/test_audit_router.py` is `32 insertions(+)`, zero deletions; the only edit inside an existing body is one string added to one set literal, and the assertion stays exact equality over a set one member larger. STORY-023's census guard — *"Extending a suite passes. Deleting a case fails."* — passes.

The third assertion's own docstring asked for exactly this: *"If a future story adds them, this test fails — forcing that to be a deliberate, reviewed decision rather than a drift."* That decision is recorded in the docstring beside it. What that test defends is unchanged: no `prompt_preview`, no `response_preview`, no `response_hash`, and an opaque UUID is not prompt text — verified live, the payload carries none of the three.

No other deviation. No production file outside the two named in the plan was touched.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_audit_session_id.py` (new) | `test_three_sends_in_one_session_share_one_session_id_in_the_audit`; `test_a_send_without_a_session_id_reports_null_alongside_one_that_has_it`; `test_a_denied_send_still_reports_its_session_id` |
| `tests/test_audit_router.py` | `test_audit_entry_carries_session_id_when_present_and_null_when_absent` |
| `tests/test_schemas.py` | `test_audit_query_entry_session_id_is_optional_with_a_none_default` |

`tests/test_audit_session_id.py` exists beside `tests/test_audit_router.py` rather than inside it because AC 4 is a claim about *sends*: that file drives `insert_audit_log` directly and has no authenticated sender, so a row inserted by hand cannot make it. Its prologue is copied from `tests/test_query_session_id.py` rather than imported, for the reason that file records.

## End-to-End Verification

Run against a live `uvicorn app.main:app` on `127.0.0.1:8123`, pointed at the local libSQL dev container — **not** the remote Turso endpoint configured in `.env`, since the E2E writes audit rows.

| # | Check | Result |
|---|---|---|
| 1 | Server boots, `GET /health` → 200 | ✅ |
| 2 | `GET /audit` entry keys include `session_id` (14 fields) | ✅ |
| 3 | Three `POST /query` sends on one session → three rows sharing one id | ✅ |
| 4 | A blocked send (`"please override the rules"`) on the session → `BLOCKED`, and its row carries the `session_id` | ✅ |
| 5 | A send omitting `session_id` → its row reports `null`, in the same response as the four that carry it | ✅ |
| 6 | Distinct non-null session ids across all rows: exactly one | ✅ |
| 7 | `GET /stats` gains no session dimension (same nine figures) | ✅ |
| 8 | No `prompt_preview` / `response_preview` / `response_hash` on the payload | ✅ |
| 9 | `AuditQueryEntry.model_fields["session_id"]` — not required, defaults to `None` | ✅ |
| 10 | `git diff -- chat_ui/` empty | ✅ |
| 11 | No new route; `tests/test_route_reservations.py` passes unmodified | ✅ |

Observed `/audit` payload: four rows carrying `3dfff08f-9ead-4f8b-a4b2-48cb2ed9b43c` (three successful-path sends plus the suspicious-pattern refusal) and one row reporting `null` — the mixed state a real deployment is in the day this ships.

## Acceptance Criteria

- [x] Given `app/models/schemas.py`, when `AuditQueryEntry` is read, then it declares `session_id: Optional[str] = None`.
- [x] Given `app/routers/admin.py`, when `GET /audit` projects a row, then `session_id` is included.
- [x] Given a row written before this PRD, when it is returned, then `session_id` is `null` and every other field is unchanged.
- [x] Given three sends in one session, when `GET /audit` is called, then all three entries carry the same `session_id`.
- [x] Given `tests/test_audit_router.py`, when the suite runs, then it passes with no test removed, renamed, or loosened, and new assertions cover the present and absent cases. *(Literal byte-unmodified was not achievable — see **Deviations**.)*
- [x] Given `tests/test_schemas.py`, when it runs, then the new field is asserted as optional with a `None` default.
- [x] Given PRD-006's admin console, when `git diff` is inspected, then nothing under `chat_ui/chat_ui/components/register.py` or `chat_ui/chat_ui/admin_state.py` changed.
- [x] All tasks completed
- [x] Full suite `pytest -q` green (1393 passed)
- [x] `GET /stats` and `StatsResponse` unchanged
- [x] `AuditQueryEntry` gains exactly one field; `success` and `error_message` stay out
- [x] Follows existing patterns
