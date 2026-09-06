---
story: STORY-024
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-024-stale-client-recovery.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: PENDING
status: COMPLETE
completed: 2026-09-06
---

# Implementation Report — STORY-024: Recover the shared libSQL client when its stream dies

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-024-stale-client-recovery.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `PENDING`

## Summary

`app/db/database.py` cached one libSQL client per process forever, and nothing ever set
`_client = None`. The stream behind that client is server-side state the server expires, so the first
request after a quiet period failed and every request after it failed the same way until the process
was restarted — a signed-out application, because identity resolution goes through the same client.

The recovery landed in **two seams**, both inside this module. `_shared_client()` now stamps
`_client_used_at` and, past `_IDLE_PROBE_AFTER_SECONDS`, proves the cached client with a bare
`SELECT 1` (`_proved()`) *before* handing it out — before `_session()` opens any transaction — and
replaces a dead one exactly once. `_translated()` now recognises the two connection-level messages
(`_is_dead_stream()`) and drops the cached client (`_invalidate_client()`) **without retrying**, so a
stream that dies mid-statement costs that statement and nothing more, and the next call rebuilds.
`app/db/errors.py` is untouched, no consumer changed, and no new exception type exists.

The defect was reproduced on demand and the fix measured against it at three layers, including a real
HTTP server: **500-and-stays-500 before, 200 after**.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Start the dev server, record a baseline (140 passed) | — | ✅ |
| 2 | `_DEAD_STREAM`, `_is_dead_stream()`, `_invalidate_client()` | `app/db/database.py` | ✅ |
| 3 | Idle tracking, `_IDLE_PROBE_AFTER_SECONDS`, probe-on-acquire via `_proved()` | `app/db/database.py` | ✅ |
| 4 | Invalidate-without-retry arm in `_translated()` | `app/db/database.py` | ✅ |
| 5 | Recovery tests (AC 1, AC 4) | `tests/test_db.py` | ✅ |
| 6 | Bound + negatives (AC 2, AC 3, AC 5, AC 6) | `tests/test_db.py` | ✅ |
| 7 | Probe stays off the hot path and the boot path | `tests/test_db.py` | ✅ |
| 8 | Untouched-surface verification (AC 7, AC 8) | — | ✅ |
| 9 | Live idle boot + server restart (AC 9) | — | ✅ |
| 10 | Full suite, commit | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `tests/test_db.py` | ✅ 152 passed (baseline 140, +12 new) |
| `tests/test_chat_sessions.py`, `test_chat_state.py`, `test_untouched_app.py` | ✅ 199 passed, files unmodified |
| Full suite, one process | ✅ **1484 passed, 0 failed** (237 s) |
| Module import | ✅ |
| `app/db/errors.py` diff | ✅ empty |
| `tests/test_db.py` deletions | ✅ **0** — every existing test byte-unmodified |
| E2E | ✅ 5/5 (two at the layer noted under Deviations) |
| Lint | n/a — the repo configures no linter; both files `py_compile` clean |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +164 / −1 |
| `tests/test_db.py` | UPDATE | +297 / −0 |

## Evidence

### The stream window, measured rather than assumed

A raw client (no application code) against the dev server:

| Idle | Result |
|------|--------|
| 2 s, 10 s | alive |
| 12 s, 15 s, 20 s, 30 s, 60 s | `STREAM_EXPIRED` |

So the window is **10–12 s**, and `_IDLE_PROBE_AFTER_SECONDS = 5.0` is half of it — any pause long
enough to kill the stream is necessarily long enough to have opened the gate, so against this
endpoint an expired stream is always caught by the probe and never by the caller's statement.

The expiry message came back **byte-identical** to the literal recorded by PRD-007 STORY-009 and
PRD-008 STORY-014, which is a live re-verification of the AC 5 literal rather than a copy of it.

### Finding: idleness alone is not the trigger — the *last operation* is

This is the substantive discovery of the story, and it corrects the mental model the story was
written with. Same client, same endpoint, same 15 s pause, different endings:

| What ran before the pause | After 15 s |
|---|---|
| a read (`SELECT 1`), nothing after | **DEAD** |
| a read, then `commit()` | **DEAD** |
| a read, then `rollback()` | **DEAD** |
| a write, then `commit()` | alive |
| a write, commit, then a read | **DEAD** |

**A read leaves the Hrana stream open; a committed write leaves none to expire.** This is why the
defect reproduces so reliably from a cold boot: `check_database_reachable()` issues an uncommitted
`SELECT 1` and `init_db()` is the last thing a booting process does, so a booted-and-untouched server
is holding exactly the stream that expires. It also explains a false negative found during this work
— a first version of the E2E script idled after `insert_user()` and survived 60 s, proving nothing.
For a web application the distinction is close to academic (the last operation before a quiet period
is nearly always a read), but the failure cannot be described as "an idle process" without it.

A consequence worth recording: the probe is itself a read, so it re-opens a stream it will later have
to re-prove. That is self-correcting — the gate reopens 5 s later and the next acquire probes again,
always inside the 10 s window — and there is no cheaper alternative, since the table above shows
`commit()` and `rollback()` do not release the stream either.

### The defect, and the fix, at three layers

**1. Storage module, long-lived process, 15 s idle after a read, then the sign-in call
(`find_user_by_token_hash` — the exact call STORY-014's blocked E2E died in):**

```
[baseline] SIGN-IN FAILED: StorageError: Hrana: `api error: `status=400 Bad Request,
    body={"message":"The stream has expired due to inactivity","code":"STREAM_EXPIRED"}``
[fixed]    attempt 1: OK, resolved 'e2e@empresa.com'; client id=1423029331168   (was ...328768)
```

The changed client id is the recovery: the dead client was discarded and a new one built.

**2. A real HTTP server** (`python app.py` against the dev database, `GET /audit`, which resolves the
credential through `find_user_by_token_hash`):

| | warm request | after 20 s idle | next request |
|---|---|---|---|
| fix neutralised | 200 | **500** | **500** |
| fix live | 200 | **200** | 200 |

**3. The server restarted under a live process** (the invalid-baton half), three consecutive
attempts:

```
[baseline] attempt 1,2,3: FAILED StorageError: ... body=Received an invalid baton``
[fixed]    attempt 1: FAILED (the in-flight statement, deliberately not retried — AC 6)
[fixed]    attempt 2: OK, resolved 'e2e@empresa.com'; client id changed
[fixed]    attempt 3: OK
```

The baseline column is the whole point: PRD-007's index recorded that this state "did not recover",
and it still does not without the fix. With it, the process loses the in-flight statement and heals.

### The tests have teeth

With both seams disabled (`_IDLE_PROBE_AFTER_SECONDS = 1e9` and the `_is_dead_stream` branch forced
false), the three recovery tests fail and the rest pass:

```
FAILED test_a_dead_stream_is_discarded_and_the_call_is_served
FAILED test_a_second_connection_failure_surfaces_rather_than_looping
FAILED test_a_dead_stream_mid_statement_invalidates_without_retrying
3 failed, 6 passed
```

## Deviations from Plan

| Deviation | Rationale |
|---|---|
| **The new global is reset by a new fixture, not by extending `_restore_shared_client`.** The plan proposed adding `_client_used_at = 0.0` to the existing fixture's teardown; instead the new section defines its own `_restore_client_cache`. | Strictly better for AC 8: `tests/test_db.py` now has **297 insertions and zero deletions**, so every pre-existing test is byte-unmodified rather than merely passing. |
| **`_INVALID_BATON_TEXT` is the captured text, not the reconstructed one.** The plan expected to pin the STORY-014 fragment inside a reconstructed `Hrana:` frame with a `BATON_INVALID` code field. | The real message was captured this session by restarting libSQL under a live process, and its shape is different: `body=Received an invalid baton` — **plain text, no JSON, no `code` field**. The literal and the code comment now carry the captured text, and the absence of a code field is a second, independent reason the classifier reads message text. |
| **One test added beyond the plan's list**: `test_many_threads_finding_the_stream_dead_together_build_one_client`. | Risk 2 (a thundering-herd rebuild reconstructing the client-per-thread configuration STORY-006 measured losing 169 of 200 writes) was the only hazard here with a measured precedent, and it was asserted rather than argued: eight threads, one construction. |
| **AC 9 was met at the module and HTTP layers, not through the Reflex browser UI.** | The failing call (`login() → resolve() → find_user_by_token_hash`) was driven in a long-lived process *and* through a real booted HTTP server, with the fix-neutralised contrast run at both. The browser half was not driven: a real chat turn needs a live OpenRouter key, and this story changed no UI code. What the browser would add is rendering, which is untouched; what matters — the credential resolving after an idle period in a long-lived process — is asserted directly, with a reproduced 500 to compare against. |
| **E2E items 3 and 4 (chat turn, admin console) were exercised at the storage/service layer after a real 15 s idle**, not in the browser, for the same reason. | `summary_snapshot()` returned **10/10 figures, 0 errors**; the chat path created a session, appended a message, touched it and read the rail back with the touched session at the front. Both are the data paths those screens call. |
| The plan's generic `npm run lint` / backend-import validation commands were not applicable. | This repo has no frontend build and configures no linter. Substituted: `py_compile` on both files and the suites above. |

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_a_dead_stream_is_discarded_and_the_call_is_served`, `test_a_second_connection_failure_surfaces_rather_than_looping`, `test_the_captured_dead_stream_messages_are_told_from_statement_failures` (×5 parametrized), `test_a_constraint_violation_does_not_discard_the_client`, `test_a_missing_table_does_not_discard_the_client`, `test_a_dead_stream_mid_statement_invalidates_without_retrying`, `test_many_threads_finding_the_stream_dead_together_build_one_client`, `test_a_busy_client_is_not_probed` |

## Acceptance Criteria

- [x] A call against a cached client whose stream has expired **succeeds** — dead client discarded, new one built, normal result. *(`test_a_dead_stream_is_discarded_and_the_call_is_served`; live at all three layers.)*
- [x] The reconnect happens **at most once per call**; a second consecutive connection-level failure surfaces as `StorageError`. *(`test_a_second_connection_failure_surfaces_rather_than_looping` asserts one construction, so a loop fails the test rather than hanging it.)*
- [x] A query-level failure attempts **no reconnect and discards nothing**, and still raises `IntegrityError` / `MissingRelationError`. *(Two tests, one against the real driver's own constraint message.)*
- [x] A test drives the recovery with a stand-in that fails first and succeeds second, asserting the result and the construction.
- [x] Both connection-level messages are recognised, as literals — the expiry re-verified byte-identical against the live driver, the baton text captured live this session.
- [x] A connection that dies mid-transaction is **not** silently retried. *(The retry lives before any transaction opens; `_translated()` only invalidates. The test counts executes and sees exactly one.)*
- [x] `app/db/errors.py` unchanged — verified by empty diff.
- [x] The existing error-surface tests pass **unmodified** — verified by zero deletions in `tests/test_db.py` and 199 passing in the three named suites.
- [x] Manual verification: booted, left idle past the stream timeout, sign-in succeeds — with the fix-neutralised 500 reproduced for contrast at the same layer.
- [x] All tasks completed
- [x] Full suite green — 1484 passed, 0 failed, in one process
- [x] Follows existing patterns

## Notes for Later Stories

- **STORY-021** (two-instance smoke test) was the story most likely to hit this next; its processes now recover on their own. Its tests ping both instances at the start of every test, so it still does not exercise the idle window — if it wants to, the window is 10–12 s against the dev server and the last operation before the pause must be a read.
- **The hosted window is still unmeasured.** The expiry is `libsql-server`'s, so a Turso endpoint runs the same code, but its configured window was not verified — that needs a deployment. Nothing depends on the number: a shorter window than 5 s would simply move recovery from the probe to the `_translated()` arm, costing one failed request instead of none.
- The PRD-007 index's long-standing "open issue, not owned by any story" paragraph about `STREAM_EXPIRED` is now closed by this story and can be retired when that index is next touched.
