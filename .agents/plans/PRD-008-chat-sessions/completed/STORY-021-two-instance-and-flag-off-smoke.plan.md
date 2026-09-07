---
story: STORY-021
prd: PRD-008
slug: two-instance-and-flag-off-smoke
title: "Two instances serve one session, and CHAT_HISTORY_ENABLED=false writes nothing -- proven, not assumed"
type: TECHNICAL
complexity: MEDIUM
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-07
---

# Plan: Two instances serve one session, and CHAT_HISTORY_ENABLED=false writes nothing — proven, not assumed

## Summary

Two claims PRD-008 Section 11 lists as functional requirements are currently made only in prose, and this story turns both into tests. The first — "Two instances against one database serve the same session" — is an extension of `tests/test_two_instance_smoke.py`, whose two long-lived `subprocess.Popen` children already *are* the "separate, freshly constructed client" PRD-007 STORY-006 demanded: a transcript written through instance A's client and read back through instance B's is the strongest available form of that proof, because the two clients live in different processes. The second — "`CHAT_HISTORY_ENABLED=false` writes no row, reads no row … and leaves the chat fully working" — becomes a new integration module that drives the *application* with the flag off, asserting absence of **calls** (a `_Tripwire` standing in for `app.db.database`) rather than absence of rows. No production code changes.

## User Story

As an employee reconnecting to a different instance
I want my conversations to be there anyway, and the security admin's "history off" switch to be provably off
So that the two-instance deployment PRD-007 shipped is invisible to me, and the off state is a test rather than a docstring.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-021-two-instance-and-flag-off-smoke.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 5 (stories 6, 7), Section 9, Section 11, Section 12 Phase 4, Risk 1

## Metadata

| Field | Value |
|-------|-------|
| Type | TECHNICAL |
| Complexity | MEDIUM |
| Systems Affected | Test suite only (`tests/`) — no application code |
| Story | STORY-021 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

---

## Dependencies checked

All four are `status: done`: STORY-007 (`c2b093b`), STORY-010 (`27c7716`), STORY-015 (`f096f2f`), STORY-016 (`310ac02`). Nothing blocks this story.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | none | — |

`.agents/skills/` holds exactly one skill, `frontend-design`, whose `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story asserts data behaviour across two processes and a configuration flag; it renders nothing and runs no compiler. The story's own frontmatter agrees (`skills: []`) and its Technical Notes record the same scan. `reflex-docs` is not listed on this story and is not needed — `ChatState` is driven the way `tests/test_chat_state.py` already drives it, by calling the handler function directly.

---

## Patterns to Follow

### The child instance and its protocol

```python
# SOURCE: tests/test_two_instance_smoke.py:98-300 (_INSTANCE_SCRIPT)
def emit(payload):
    _out.write(json.dumps(payload) + "\n")
    _out.flush()

HANDLERS = {
    "init_db": lambda command: {"ok": database.init_db() is None},
    "schema": lambda command: schema(),
    "query": do_query,
    "authenticate": do_authenticate,
    "plant_audit_row": do_plant_audit_row,
    "rows": do_rows,
    "audit_ids": do_audit_ids,
    "console_load": do_console_load,
}
```

One JSON object per line, one reply per command, `HANDLERS` keyed by `cmd`. New capability is a new handler and a new key — nothing else in the file changes shape.

### The tripwire that makes "no call" assertable

```python
# SOURCE: tests/test_chat_sessions.py:1011-1030
class _Tripwire:
    """A stand-in for `app.db.database` on which every access is a failure."""

    def __getattr__(self, name: str):
        raise AssertionError(
            f"chat_sessions reached database.{name} with CHAT_HISTORY_ENABLED off"
        )
```

`__getattr__` fires on the attribute lookup, *before* the call, so a result that is never used is still caught. Deliberately not a `Mock`: a forgotten `assert_not_called()` is a green test.

### Driving ChatState without Reflex's event machinery

```python
# SOURCE: tests/test_chat_state.py:106-118
def _make_state(user_id=_AUTH_USER_ID, token=_AUTH_TOKEN) -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = user_id
    state._token = token
    return state


async def _send(state: ChatState, text: str) -> None:
    state.input_text = text
    handler = type(state).event_handlers["send"]
    await handler.fn(state)  # bypasses the background-task chain guard
```

### Statement recording, for the "no restart-time migration" claim

```python
# SOURCE: tests/test_two_instance_smoke.py:163-186 (class Recording), itself tests/test_db.py:967's proxy
def execute(self, sql, *parameters):
    self._statements.append(sql)
    return self._conn.execute(sql, *parameters)
```

`__enter__`/`__exit__` are load-bearing: `app/db/database.py:621`'s `_session()` does `with conn:`, so a proxy without them turns every measured write into an `AttributeError`.

### The flag read at call time, in one module only

```python
# SOURCE: app/services/chat_sessions.py:120-127
def create(identity, first_prompt, derive_title):
    if not settings.CHAT_HISTORY_ENABLED:
        return None
    with _wrapped("create"):
        return database.create_chat_session(identity.user_id, derive_title(first_prompt))
```

Ten functions, ten guards, each returning a value the caller can proceed with (`None` / `[]` / `False` / `0`, and `True` for `owns`). `monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)` therefore takes effect without a module reload — pinned by `tests/test_chat_sessions.py::test_the_flag_is_read_at_call_time_not_captured_at_import`, and the env-var → `Settings()` half is already pinned at `tests/test_config.py:297`. Neither needs re-proving here.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_two_instance_smoke.py` | UPDATE | Session/transcript handlers in the child script; four new tests (AC 1–3, AC 7); docstring and `_INVARIANTS` note |
| `tests/test_history_off_integration.py` | CREATE | The off state driven through the real application: AC 4, AC 5, AC 6 |

No file under `app/` or `chat_ui/` is touched. If a task appears to need one, stop — that is a defect this story found, not a change this story makes.

---

## Design notes

**Why instance B is the "separate, freshly constructed client".** PRD-007 STORY-006 required a durable write to be verified "through a separate, freshly constructed client, not through the writing one". The two children each build their own `_shared_client()` in their own interpreter (`app/db/database.py:72`), so a read on B cannot be served by anything A cached. This is a stronger instrument than the requirement asks for, and it already exists — which is exactly why the story says *extend* this file.

**Why the child imports `derive_title` from `chat_ui`.** `chat_sessions.create` takes the deriver as a parameter and refuses to own the rule (`app/services/chat_sessions.py:130-152`). The production caller that supplies it is `ChatState` (`chat_ui/chat_ui/state.py:995`), so the child supplying the same function is the honest reproduction; a lambda in the test would be a second title rule to drift. The import is cheap and Reflex-free: `chat_ui/chat_ui/__init__.py` is empty and `formatting.py` imports only stdlib and `.copy`.

**Why the flag-off module does not use subprocesses.** Its subject is what the *service and its callers* do with the flag, and every guard is read at call time from `settings`, so `monkeypatch` reaches all of them in-process — while a subprocess would not let `_Tripwire` observe the calls that AC 5 is about. The env-var parsing seam that a subprocess would cover is already closed by `tests/test_config.py:297`.

**Why absence of rows is not enough.** A service that called the database and discarded the result would pass every `COUNT(*) == 0` assertion and would still be reading under a flag that says it does not. `_Tripwire` is the whole of AC 5, and it is also what makes the AC 4 write assertions mean something.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Teach the child instance the session surface

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE — inside `_INSTANCE_SCRIPT` only
- **Implement**:
  - Add `import dataclasses` to the child's first line of imports (currently `import json, os, sys, time`).
  - Inside the child's `try` block, add: `from app.services import chat_sessions`, `from app.services.identity import Identity`, `from app.db.models import StoredMessage`, `from chat_ui.chat_ui.formatting import derive_title`.
  - Add `def _identity(command): return Identity(user_id=command["user_id"], role=command.get("role", "user"))` — constructed directly, the way `tests/test_chat_sessions.py:1000` does, because credential resolution is `tests/test_identity.py`'s subject and `do_authenticate` already covers it here.
  - Add handlers, each going through `app/services/chat_sessions.py` and never through `database.py` directly (the rule `tests/test_chat_sessions.py` enforces across `app/`; the child holds itself to it so the smoke test reproduces the real call path):
    - `do_create_session` → `{"session_id": chat_sessions.create(_identity(command), command["prompt"], derive_title)}`
    - `do_append` → `{"row_id": chat_sessions.append_message(_identity(command), command["session_id"], StoredMessage(**command["message"]))}`
    - `do_transcript` → `{"messages": [dataclasses.asdict(row) for row in chat_sessions.messages_for(_identity(command), command["session_id"])]}`
    - `do_sessions` → `{"sessions": [dataclasses.asdict(row) for row in chat_sessions.list_for(_identity(command))]}`
    - `do_delete_session` → `{"deleted": chat_sessions.delete(_identity(command), command["session_id"])}`
    - `do_transcript_row_counts` → one `get_connection()`, two `SELECT COUNT(*) AS n` reads, returning `{"sessions": n, "messages": n}` — the raw-table half of AC 3 ("gone from both tables"), which `messages_for` alone cannot show because it is scoped by owner.
    - `do_audit_count` → `{"count": database.count_audit_logs()}`
  - Register all seven in `HANDLERS`.
- **Mirror**: `tests/test_two_instance_smoke.py:196-278` (`do_rows`, `do_audit_ids`) for handler shape; `tests/test_two_instance_smoke.py:280-289` for the `HANDLERS` table.
- **Validate**: `python -m pytest tests/test_two_instance_smoke.py -x -q` — the existing eight tests still pass, which proves the children still boot with the new imports.

### Task 2: Let a query carry a session_id, and let a row report one

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE — inside `_INSTANCE_SCRIPT` only
- **Implement**:
  - In `do_query`, build the request body as a dict and add `"session_id": command["session_id"]` only when the command carries one. The omission must stay a genuine omission: `app/routers/query.py:68`'s `is not None` guard is what keeps `owns()` from issuing a statement for the requests that do not name a session, and `test_round_trip_cost_is_measured_and_reported` asserts exactly three statements on that path. Sending `"session_id": None` explicitly would not change the count, but building the body conditionally keeps the two call shapes visibly distinct.
  - `do_query`'s reply shape is unchanged.
  - In `do_rows`' projection, add `"session_id": row.session_id`.
- **Mirror**: `tests/test_query_session_id.py:134` for the request shape.
- **Validate**: `python -m pytest tests/test_two_instance_smoke.py::test_round_trip_cost_is_measured_and_reported -x -q` — the three-statement assertion still holds, proving the no-session path is unchanged.

### Task 3: AC 1 and AC 2 — a transcript written on A is read back whole on B

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE — new section after the AC 5 block, headed `PRD-008 -- one session, two instances`
- **Implement**: `test_a_transcript_written_on_one_instance_reads_back_whole_on_the_other(instances, smoke_user)`.
  - Parent builds a list of seven `StoredMessage`-shaped dicts, one per bubble kind — `user`, `assistant`, `duplicate`, `injection`, `forbidden`, `upstream_error`, `internal_error` — with **every** optional field populated to a distinct, non-default value: `prompt`, `model_used`, `tokens_used`, `audit_id`, `pii_redacted=True`, `pii_entities="EMAIL_ADDRESS,PERSON"`, `pattern`, `required_permission`, `first_query_at`, `detail`. Defaults are what a field-by-field comparison cannot see through: a column dropped on the wire and a column defaulting to `False` are the same observation unless the written value is not the default.
  - Instance A: `create_session`, then one `append` per message, in order.
  - Instance B: `sessions` — the row is listed, with the title `derive_title` produced from the first prompt.
  - Instance B: `transcript` — assert `len(...) == 7`, assert `[m["kind"] for m in ...]` equals the written order, and assert each returned dict equals the written dict field-for-field, excluding only `created_at` and `id`, which the store stamps (`app/db/database.py:1614`).
  - Assert `id` is present and strictly ascending, and that `created_at` is a non-empty string on every row — `list_chat_messages` orders `BY id`, and an assertion over the order needs the ordering key to exist.
  - Failure messages name the instance, per this module's convention.
- **Mirror**: `tests/test_chat_state.py:1680-1770` for the seven-kind table; `tests/test_two_instance_smoke.py:527-560` for the cross-instance assertion style.
- **Validate**: `python -m pytest tests/test_two_instance_smoke.py -k transcript_written -x -q`

### Task 4: AC 3 — deleted on B, gone on A, and the audit trail untouched

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE — same new section
- **Implement**: `test_a_session_deleted_on_one_instance_is_gone_from_both_tables_on_the_other(instances, smoke_user)`.
  - Instance A: `create_session`, then run one real `query` carrying that `session_id`, so `audit_logs` holds a row that *names* the session — without it, "`count_audit_logs()` is unchanged" would be a comparison of zero with zero.
  - Append two messages on A. Record `audit_count` from A.
  - Instance B: `delete_session` → `{"deleted": True}`.
  - Instance A (the writer, now reading after someone else's delete): `sessions` is empty, `transcript` is empty, `transcript_row_counts` is `{"sessions": 0, "messages": 0}` — the raw tables, not the owner-scoped view.
  - `audit_count` on A is identical to the recorded value, and `rows` still contains the row whose `session_id` names the deleted session. PRD Section 9: "deleting a conversation deletes a conversation, it does not edit the record of what was asked." Asserting only the count would pass against an implementation that deleted the audit row and inserted a tombstone.
- **Mirror**: `app/services/chat_sessions.py:296-308` (`delete`'s docstring states the `audit_logs` invariant); `tests/test_two_instance_smoke.py:520-535`.
- **Validate**: `python -m pytest tests/test_two_instance_smoke.py -k deleted_on_one_instance -x -q`

### Task 5: AC 7 — a foreign session is 403 on the second instance

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE — same new section
- **Implement**: `test_a_session_owned_by_another_user_is_refused_on_the_other_instance(instances, smoke_user)`.
  - The second credential is written **inside the test** by the parent, with `insert_user(User(user_id=_OTHER_USER_ID, role="user", token_hash=hash_token(_OTHER_TOKEN)))` — the same move `smoke_user` makes, deliberately not a second fixture: the story asks for no new harness, and one more identity is two lines rather than a shared surface. Add `_OTHER_USER_ID` / `_OTHER_TOKEN` beside `_USER_ID` / `_USER_TOKEN` at module scope.
  - Instance A: `create_session` for `_USER_ID`.
  - Instance B: `query` as `_OTHER_TOKEN` carrying that `session_id` → `status_code == 403`.
  - Instance B: `query` as `smoke_user` carrying the same `session_id` → `200`. Without this arm the 403 could equally mean "instance B has never heard of that id", which is the *opposite* of what the story claims; this is what makes the refusal about ownership and about shared state at once.
  - Assert the refusal was audited on the shared trail — `rows` from A contains a row with `success is False` and that `session_id` — closing across instances the loop STORY-010 opened (`app/routers/query.py:71-80`).
- **Mirror**: `tests/test_query_session_id.py:236-249` for the 403; `tests/test_two_instance_smoke.py:724-750` for the both-instances assertion shape.
- **Validate**: `python -m pytest tests/test_two_instance_smoke.py -k owned_by_another_user -x -q`

### Task 6: Say what the module now covers

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE — module docstring and `_INVARIANTS`
- **Implement**:
  - Add a paragraph to the module docstring: the file was PRD-007 STORY-016's exit criterion and is now also PRD-008 STORY-021's, and the reason it could absorb the second epic without a second harness is that two processes are already two clients — which is the "separate, freshly constructed client" PRD-007 STORY-006 named as Risk 1's mitigation. A lost transcript row has the same shape and the same invisibility as a lost `insert_audit_log()`.
  - Extend `_INVARIANTS`' numbered list with a sixth: every session command goes through `app/services/chat_sessions.py`, never through `database.py`, so the child exercises the ownership rule rather than routing around it.
- **Validate**: `python -m pytest tests/test_two_instance_smoke.py -q` — twelve tests pass.

### Task 7: The flag-off module's frame

- **File**: `tests/test_history_off_integration.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring: what this file claims that `tests/test_chat_sessions.py` does not. That module proves the *service* issues no statement with the flag off; this one drives the **application** — a full send through `ChatState`, and `POST /query` through `TestClient` — and asserts the same absence one layer out, where a caller that branched on the flag or reached past the service would show up. PRD Section 11, verbatim: "`CHAT_HISTORY_ENABLED=false` writes no row, reads no row, renders no rail, and leaves the chat fully working." The rail's half is `tests/test_session_rail.py`'s (STORY-018); this is the data half, and both are needed for Risk 1's mitigation to be real.
  - Prologue: `os.environ.setdefault` for `OPENROUTER_API_KEY` / `ADMIN_TOKEN`, then the imports, following `tests/test_chat_state.py:1-58` — `settings`, `chat_sessions`, `chat_state_mod`, `ChatState`, `get_connection`, `count_audit_logs`, `list_audit_logs`, `create_chat_session`, `insert_user`, `User`, `hash_token`, `OpenRouterResult`, `TestClient`, `app`.
  - `temp_db` fixture overriding conftest's to seed the authenticated user — `tests/test_chat_state.py:66-72` verbatim in shape.
  - Helpers: `_make_state`, `_send`, `_fake_call_openrouter`, `_count(table)`, and `_Tripwire` restated locally with a docstring crediting `tests/test_chat_sessions.py:1011`. Restated rather than imported: cross-importing between test modules is not this suite's idiom, and the copy is nine lines whose failure message this module wants to word for itself.
  - `history_off` fixture: `monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)` **only** — the tripwire is installed per-test here, because the AC 4 tests need the real database to count rows on while the AC 5 tests need it replaced.
- **Mirror**: `tests/test_chat_state.py:1-118`
- **Validate**: `python -m pytest tests/test_history_off_integration.py -q --collect-only`

### Task 8: AC 4 — a full send writes no transcript, and the response is unchanged

- **File**: `tests/test_history_off_integration.py`
- **Action**: UPDATE
- **Implement**:
  - `test_a_full_send_with_history_off_writes_no_session_and_no_message(temp_db, monkeypatch, history_off)` — the **real** `run_query` (only `call_openrouter` is faked, as `tests/test_chat_state.py:1580` does), driven through `_send`. Assert `_count("chat_sessions") == 0` and `_count("chat_messages") == 0`; assert `count_audit_logs() == 1`; assert the bubbles reached the screen (`[m.kind for m in state.messages] == ["user", "assistant"]`), `state.transcript_error == ""`, `state.sessions_error == ""`, `state.pending is False`. A faked `run_query` would write no audit row and the test would prove half of nothing.
  - `test_the_audit_row_and_the_response_are_what_they_were_with_history_on(temp_db, monkeypatch)` — the "unchanged" claim as one comparison rather than two literals. Send the same prompt twice: first with the flag off, capturing the `POST /query` body and the single audit row; then `DELETE FROM audit_logs` (so the duplicate detector's 24-hour window does not turn the second send into a `BLOCKED`, which would make the comparison meaningless); then flip the flag on and send again. Assert the two bodies are equal once `audit_id` is dropped, and the two audit rows are equal once `id` and `timestamp` are dropped. `dataclasses.asdict` on the two `AuditLog`s makes that one `==` rather than twenty.
  - `test_post_query_with_history_off_writes_no_transcript_row(temp_db, history_off)` — the API ingress never wrote transcript rows and must not start; both counts stay `0` and the response is `SUCCESS`.
- **Mirror**: `tests/test_chat_state.py:1549-1573`, `tests/test_query_session_id.py:121-160` (the field-by-field audit comparison).
- **Validate**: `python -m pytest tests/test_history_off_integration.py -k "full_send or unchanged or post_query" -q`

### Task 9: AC 5 — the read paths call nothing at all

- **File**: `tests/test_history_off_integration.py`
- **Action**: UPDATE
- **Implement**: each test seeds real rows with the flag **on** first — a tripwire over an empty database proves nothing, since there would be nothing to read either way — then installs `monkeypatch.setattr(chat_sessions, "database", _Tripwire())` together with the flag off.
  - `test_login_reads_no_session_and_no_transcript_when_history_is_off` — `ChatState.login()` with a real token; `state.sessions == []`, `state.messages == []`, `state.active_session_id == ""`, `state.sessions_error == ""`. The tripwire is the assertion; the empty values are the "leaves the chat fully working" half.
  - `test_selecting_a_session_reads_nothing_when_history_is_off` — `select_session(seeded_id)` under the tripwire.
  - `test_retry_sessions_reads_nothing_when_history_is_off` — the rail's explicit retry, the one read path a user can trigger repeatedly.
  - `test_post_query_consults_no_row_for_a_supplied_session_id_when_history_is_off` — `POST /query` carrying a valid UUID4 under the tripwire: `200`, and the audit row carries the supplied id. This is `app/routers/query.py:68`'s `owns()` call, and STORY-010 AC 7's rule that "the flag governs the transcript, not the audit column". It is the only AC 5 path that does not run through `ChatState`, and the only one where a `403` regression would be silent.
  - `test_no_read_path_touches_the_database_module_when_history_is_off` — the four above driven in one test, so a fifth read path added later fails here even if nobody adds a case above. The tripwire's `AssertionError` names the attribute, so the failure says which call appeared.
- **Mirror**: `tests/test_chat_sessions.py:1195-1272` (the `history_off` fixture and its parametrized read tests); `tests/test_chat_state.py:2146-2161`.
- **Validate**: `python -m pytest tests/test_history_off_integration.py -k history_is_off -q`

### Task 10: AC 6 — flipping the flag back resumes persistence, with no migration

- **File**: `tests/test_history_off_integration.py`
- **Action**: UPDATE
- **Implement**: `test_persistence_resumes_when_the_flag_is_flipped_back(temp_db, monkeypatch)`.
  - Send with the flag off; assert both transcript tables are empty.
  - Flip `settings.CHAT_HISTORY_ENABLED` to `True` **without** calling `init_db()` and without rebuilding anything — that omission is the "no restart-time migration" claim, and doing it in the same process is what makes it a claim at all.
  - Wrap `database.get_connection` in the `Recording` proxy (Task 1's pattern, restated here for one process) and send again. Assert: a session row exists, its transcript holds the turn, `state.transcript_error == ""` and `state.sessions_error == ""` — no error about missing rows — and **no statement issued during the resumed send begins with `ALTER`, `CREATE` or `DROP`**. `tests/test_db.py:125::test_init_db_issues_no_alter_when_schema_is_current` makes the steady-state claim for `init_db()`; this makes it for the flag flip, which is the path this story is about.
  - Add a closing `_INVARIANTS`-style note to the module: nothing here names a hosted database, no test sleeps, and the only endpoint is conftest's — so `HARNESS_TEST_LIBSQL_URL` redirects this module with the rest of the suite (AC 8).
- **Mirror**: `tests/test_chat_sessions.py:1281-1291` (the flag flipped both ways in one test); `tests/test_two_instance_smoke.py:163-186` (`Recording`).
- **Validate**: `python -m pytest tests/test_history_off_integration.py -q`

### Task 11: AC 8 — the whole suite, offline

- **File**: — (no file)
- **Action**: verify
- **Implement**: run the full suite against the local libSQL dev server with no `TURSO_AUTH_TOKEN` in the environment, confirming both new modules pass and nothing else regressed. `tests/test_untouched_app.py`'s coverage census (STORY-023) and `tests/test_chat_sessions.py`'s AST guards are the two most likely to notice a stray change.
- **Validate**: `python -m pytest tests/ -q`

---

## End-to-End Tests

- [ ] Local libSQL dev server running: `docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67`
- [ ] `python -m pytest tests/test_two_instance_smoke.py -q` → 12 passed, and the STORY-016 round-trip cost line still prints
- [ ] `python -m pytest tests/test_history_off_integration.py -q` → all passed
- [ ] `python -m pytest tests/ -q` → no regression; `TURSO_AUTH_TOKEN` unset throughout
- [ ] Negative control for AC 1: temporarily make `list_chat_messages` drop `pii_entities` from its projection → the transcript round-trip test fails, naming the field. Revert.
- [ ] Negative control for AC 5: temporarily remove the `if not settings.CHAT_HISTORY_ENABLED` guard from `chat_sessions.list_for` → `test_login_reads_no_session_and_no_transcript_when_history_is_off` fails with `chat_sessions reached database.list_chat_sessions`. Revert.
- [ ] Negative control for AC 3: temporarily make `delete_chat_session` leave `chat_messages` behind → the raw-table count assertion fails while the owner-scoped `transcript` read still returns empty, confirming both reads are earning their place. Revert.

## Validation

```bash
docker start harness-libsql-dev
python -m pytest tests/test_two_instance_smoke.py tests/test_history_off_integration.py -q
python -m pytest tests/ -q
git diff --stat -- app chat_ui   # must be empty: this story changes no production code
```

---

## Risks + Mitigations

| Risk | Mitigation |
|------|-----------|
| The suite degrades under repeated runs against one long-lived dev server — mass fixture errors that look like a code defect. | Restart the container (`docker restart harness-libsql-dev`) and re-run before investigating. This story adds more per-test round trips against two long-lived children, so it makes the symptom likelier, not the bug. Do not bisect the diff first. |
| The children are long-lived, and a libSQL stream is server-side state the server expires. | STORY-024 (`9fa2e67`) landed `_proved()` and `_invalidate_client()` for exactly this; the new handlers inherit it because they go through `get_connection()` like everything else. If a child fails on its first command after an idle stretch, that recovery is what regressed. |
| `dataclasses.asdict` on `StoredMessage` must survive JSON. | Every field is `str`, `int`, `bool` or `None` (`app/db/models.py:205-228`). A field of another type added later fails loudly at `json.dumps` in the child, which is the right place. |
| The duplicate detector turns a second identical prompt into `BLOCKED` and quietly changes what a test measures. | Every prompt in the new tests is unique, and the one test that deliberately repeats a prompt empties `audit_logs` in between and says why. |
| The child now imports `chat_ui`, coupling the smoke test to the Reflex package. | Only `chat_ui.chat_ui.formatting.derive_title`, whose module imports stdlib and `.copy` alone and whose package `__init__` is empty. No Reflex import, no compile step. The alternative — a title rule written in the test — is the drift the injection was designed to prevent. |
| Adding `session_id` to `do_rows`' projection changes a reply shape three existing tests read. | They read by key and assert on the keys they name; a new key is additive. Task 2's validation runs the cost test specifically to confirm the request path is unchanged. |

---

## Acceptance Criteria

(Copied from story `STORY-021`)

- [ ] Given the pattern in `tests/test_two_instance_smoke.py`, when it is extended, then a session created and written through one client is read back in full through a **separate, freshly constructed** client — not through the writing one.
- [ ] Given that round trip, when the transcript is compared, then every message matches in order and in every field, including the metadata that drives the verdict rendering.
- [ ] Given a session created on instance A and deleted on instance B, when instance A reads it, then it is gone from both tables and `count_audit_logs()` is unchanged.
- [ ] Given `CHAT_HISTORY_ENABLED=false`, when a full send is driven end to end, then `chat_sessions` and `chat_messages` are both **empty**, the audit row is written as normal, and the response is unchanged.
- [ ] Given `CHAT_HISTORY_ENABLED=false`, when the read paths are driven, then the database module is not called at all — asserted by patching it and observing no call, per STORY-006's criterion.
- [ ] Given `CHAT_HISTORY_ENABLED` flipped back to `true`, when a send runs, then persistence resumes with no restart-time migration and no error about missing rows.
- [ ] Given a `session_id` created by user A, when user B sends it to `POST /query` against the second instance, then the response is `403` — the ownership check is not instance-local state.
- [ ] Given the suite, when it runs offline with no Turso account, then it passes — the property every test in this repository holds since PRD-007 STORY-006.
- [ ] All tasks completed
- [ ] No production code changed (`git diff -- app chat_ui` is empty)
- [ ] Full suite passes
- [ ] Follows existing patterns
