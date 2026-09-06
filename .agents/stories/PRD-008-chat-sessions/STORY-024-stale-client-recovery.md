---
id: STORY-024
prd: PRD-008
slug: stale-client-recovery
title: "Recover the shared libSQL client when its stream dies, so an idle process is not a dead one"
type: technical
priority: high
complexity: medium
phase: "4 - Surface and hardening"
status: done
labels: [database, reliability, tech-debt, deployment]
epic_branch: epic/PRD-008-chat-sessions
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-024-stale-client-recovery.plan.md
report: .agents/reports/PRD-008-chat-sessions/STORY-024-stale-client-recovery.report.md
commit: null
depends_on: []
blocks: []
skills: []
created: 2026-09-06
updated: 2026-09-06
---

# STORY-024: Recover the shared libSQL client when its stream dies, so an idle process is not a dead one

## Description

As an employee, I want the chat to still work after nobody has used it for a while, so that being the first person to open it in the morning is not the same as it being broken.

`app/db/database.py` builds **one** libSQL client per process and caches it in a module global for the life of that process. That client holds a Hrana stream. When the stream dies — the server expires it after inactivity, or the server restarts — **nothing invalidates the cached client**, so it is not one failed query: it is every query from that moment until the process is restarted.

This was found during [[STORY-014]], whose live-boot E2E step could not be run because of it. The sequence is reproducible and takes under two minutes: boot the Reflex server, wait out the production build without touching the app, then sign in. The result is a `StorageError` from `find_user_by_token_hash` and a toast that says *"An error occurred."* The same failure was reproduced at commit `237226b` with all of STORY-014's changes stashed, so it predates that story and belongs to neither.

**The test suite cannot see this defect, by construction.** Every `pytest` run is a fresh process that queries continuously, so the stream is never idle long enough to expire. 1472 tests pass against the same endpoint that fails the running application. That is the gap this story closes, and it is why the acceptance criteria below are written against a *simulated* dead stream rather than against a wall clock.

## Acceptance Criteria

- [ ] Given a cached client whose stream has expired, when any function in `app/db/database.py` is called, then the call **succeeds** — the dead client is discarded, a new one is built, and the caller sees a normal result rather than a `StorageError`.
- [ ] Given the same, when the recovery is observed, then the reconnect happens **at most once per call**. A second consecutive connection-level failure surfaces as `StorageError` and is not retried again — a broken endpoint must stay visible, not become an infinite loop against a database that is genuinely down.
- [ ] Given a **query-level** failure — `UNIQUE constraint failed`, `no such table` — when it is raised, then **no reconnect is attempted and the cached client is not discarded**, and the exception is still `IntegrityError` / `MissingRelationError` exactly as today. Reconnecting on a constraint violation would retry a write that the database correctly refused.
- [ ] Given `tests/test_db.py`, when it runs, then a test drives the recovery with a stand-in client that raises the connection error on its first call and succeeds on the second, asserting both the successful result and that a new client was constructed.
- [ ] Given the two connection-level messages this defect actually produces, when each is fed to the classifier, then both are recognised: `STREAM_EXPIRED` (*"The stream has expired due to inactivity"*) and the post-restart *"Received an invalid baton"*. Both strings were captured from the live driver during STORY-014 and belong in the test as literals, the way `_MISSING_RELATION` and `_CONSTRAINT` already pin the driver's text.
- [ ] Given a write that has already been issued inside an open transaction, when the connection dies mid-transaction, then the operation is **not** silently retried — a partial transaction that gets replayed is a worse defect than the one being fixed. Either the retry is confined to the point before any statement runs, or the story documents in the code why the chosen seam cannot replay partial work.
- [ ] Given `app/db/errors.py`, when the story is complete, then it is **unchanged** — no new exception type. This is a recovery that callers must never have to handle; a `StaleConnectionError` for consumers to catch would be this module's job leaking upward, the same argument `chat_sessions.py` makes for not raising `HistoryDisabled`.
- [ ] Given the existing error-surface tests in `tests/test_db.py` and `tests/test_chat_sessions.py`, when they run, then they pass **unmodified** — the degraded arms that STORY-014 built on top of `StorageError` still fire for real storage failures.
- [ ] Given a manual verification, when the app is booted and left idle past the stream timeout and a user then signs in, then the sign-in succeeds. This is the E2E step STORY-014 could not complete, and it is the only assertion here that a fresh-process test suite cannot make.

## Technical Notes

- File: [app/db/database.py](../../../app/db/database.py). No consumer changes, no `app/services/` changes, no `chat_ui/` changes.
- **The exact mechanism.** [`_shared_client()`](../../../app/db/database.py) rebuilds only when the `(DATABASE_URL, TURSO_AUTH_TOKEN)` key changes, and its own docstring says the key *"only changes under test"*. So in production it is built once and never again. [`_translated()`](../../../app/db/database.py) classifies the driver's `ValueError` into the `app/db/errors.py` surface and re-raises; there is no branch that treats a *connection* failure differently from a *statement* failure, and no code path anywhere sets `_client = None`.
- **This is not only a local-dev problem, and that is the part worth deciding deliberately.** The local libSQL container is where it was found, but the idle-expiry behaviour is Hrana's, not the container's, and a low-traffic production deployment that goes quiet overnight is the same shape. STORY-014's report called it "pre-existing infrastructure"; that was half right — the trigger is the server's, the *permanence* is ours. Whether the hosted Turso endpoint expires idle streams on the same schedule was **not** verified, and verifying it against the real endpoint is the first task of this story rather than an assumption to build on.
- **The seam matters more than the retry.** `_session()` is a `@contextmanager` that yields a connection into a `with conn:` transaction, so it cannot wrap the caller's body in a retry — by the time a statement fails, the generator has already yielded. Three candidate placements, and the plan should choose one with its reasoning recorded:
  - **Validate on acquire, gated by idle time.** `_shared_client()` tracks when it was last used; past a threshold it proves the client with a cheap `SELECT 1` (or rebuilds outright) *before* handing it to the caller. Fixes the exact failure mode, costs nothing on a busy path, and cannot replay a partial transaction because it runs before the transaction opens. Currently the most promising.
  - **Invalidate-and-retry inside `_translated()`.** Closest to the error, and the most exposed to the partial-transaction hazard AC 6 names.
  - **A decorator on each public function.** Safe and explicit, and thirty-odd decorators is thirty-odd places for the thirty-first to be forgotten — the failure mode [`_wrapped()`](../../../app/services/chat_sessions.py) in the sessions service was written to avoid.
- **`_client_lock` is already held while the client is built**, and `_shared_client()` is reached from `asyncio.to_thread(...)` worker threads in both `chat_ui/chat_ui/state.py` and `chat_ui/chat_ui/admin_state.py`. Any invalidation must happen under that same lock, or two threads discover the dead client together and build two clients — which is precisely the *client-per-thread* configuration STORY-006 measured losing **169 of 200 writes** to `TRANSACTION_TIMEOUT`. The docstring records that measurement; this story must not undo it.
- **Do not close the discarded client.** `_shared_client()` already declines to, and says why: `close()` discards uncommitted work rather than flushing it (STORY-001 §2.2). A dead stream needs dropping, not closing.
- `check_database_reachable()` is deliberately outside `_translated()` and must stay that way — it classifies *boot* failures for an operator, and a boot against a dead endpoint should still fail loudly rather than retry into a green start.
- Both boot paths call `init_db()` — [app/main.py:13](../../../app/main.py#L13) and [chat_ui/chat_ui/chat_ui.py:33](../../../chat_ui/chat_ui/chat_ui.py#L33) at import time — so the stream is opened at boot and then sits idle for the whole production build. That is why the failure reproduces so easily in dev and would take an overnight quiet period in production.
- Running the suite needs the local libSQL dev server (`docker start harness-libsql-dev`), per `tests/conftest.py`'s autouse session fixture.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches one storage module and renders nothing. No skill applies.

## Dependencies

- **Blocked by**: none. It touches one module, below every consumer.
- **Blocks**: nothing formally. It should land **before [[STORY-021]]**, whose two-instance smoke test drives long-lived processes and is the story most likely to hit this defect next, and before the PRD-008 → `main` PR.

## PRD Reference

Not sourced from PRD-008's own sections, and carried here the way [[STORY-023]] was.

The decision it revisits is PRD-007's: Section 6 Pattern 1 ("the process-wide libSQL client, constructed once and reused") and Section 7.2's error surface. PRD-007's epic branch is merged and closed, and the cost is being paid inside this PRD — [[STORY-014]] lost an E2E step to it, and [[STORY-021]] is aimed straight at it. Landing the fix on `epic/PRD-008-chat-sessions` is what makes this PRD's own hardening phase honest: PRD-008 Section 12 Phase 4's goal is *"the rail on screen, and the whole thing holds under failure"*, and a process that cannot survive its own idleness does not hold under failure.

Evidence: [`PRD-008/STORY-014`](../../reports/PRD-008-chat-sessions/STORY-014-transcript-persistence-write.report.md), Deviations — the reproduction at baseline `237226b`.
