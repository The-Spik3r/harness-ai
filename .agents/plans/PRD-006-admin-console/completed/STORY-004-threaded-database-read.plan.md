---
story: STORY-004
prd: PRD-006
slug: threaded-database-read
title: "AdminState.load(): all ten read functions via asyncio.to_thread, with a catch-all fault arm"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-006-admin-console
created: 2026-08-28
---

# Plan: AdminState.load() — ten reads on a worker thread, one catch-all fault arm

## Summary

Fill in the body of `AdminState.load()`, which [[STORY-003]] shipped as a guard and nothing else. The method becomes: re-assert the gate inside the lock, claim the in-flight slot (`loading = True`), then run all ten of `app/db/database.py`'s read functions — `list_audit_logs(limit=100)`, `count_audit_logs`, `count_blocked_duplicates`, `count_blocked_suspicious`, `count_unique_users`, `count_successful_queries`, `count_pii_detected_queries`, `top_models`, `top_users`, `top_pii_entities` — each through `asyncio.to_thread(...)`, collecting every result into **locals**. Only after all ten have returned does a single `async with self` block commit them to state: `rows` (projected through `to_audit_row`, newest first, previews dropped at the boundary), `total_recorded`, the six other figures and `last_refreshed`. Because nothing is written to state until every read has succeeded, the failure path cannot leave a half-updated register — a catch-all `except Exception` sets one `error` string naming *which* read failed and returns, and a `finally` clears `loading` on both paths. The reads are driven from a module-level `_READS` table of `(field, label, function, kwargs)` so "all ten, each on a thread" is one structure a test can count rather than ten hand-written awaits that can quietly become nine. Nothing under `app/` is touched: no new database function, no query parameter. The refresh control and the fault panel that render this state are [[STORY-017]]; turning the seven counts into `SummaryFigure` objects is [[STORY-015]]; the tests are [[STORY-006]].

## User Story

As a compliance admin
I want the console to load the recorded traffic and the summary figures without blocking the event loop or silently swallowing a failure
So that a failed read is visible as a fault instead of an empty table (PRD Section 6 read path, Section 4 data access).

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-004-threaded-database-read.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 4 (data access & failure handling), Section 6 (read path diagram, "thread-offloaded blocking work"), Section 9 (read-only by construction), Section 12 Phase 1, Risks 1 and 2

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/admin_state.py` (UPDATE), `chat_ui/chat_ui/admin_formatting.py` (UPDATE, one helper). No `app/` change, no component, no test file (that is STORY-006). |
| Story | STORY-004 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

**Dependency check**: `depends_on: [STORY-001, STORY-002, STORY-003]` — all three are `status: done` on this branch (`577a285`, `0fe6c69`, `048a873`). `AuditRow` exists, `to_audit_row` exists, and `AdminState.load()` exists as a guard with every field this story populates already declared. Cleared to proceed.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `reflex-docs` (**NOT INSTALLED** — substituted, see below) | `chat_ui/AGENTS.md` mandates it for any Reflex API. This story uses three: `@rx.event(background=True)`, the `async with self` mutation contract, and the stale-read rule for state accessed outside the lock. | Task 2 |
| `reflex-process-management` (**NOT INSTALLED**) | Mandated for any compile/run/reload cycle. This story renders nothing and starts no server; validation is import + a direct state drive with patched read functions. | none |
| `.agents/skills/frontend-design` | Read in full. Governs the one user-facing string this story emits (the fault message). | Task 1, Task 3 |

**Skill availability and the substitution.** `reflex-docs` and `reflex-process-management` ship in the `reflex-dev/agent-skills` Claude Code *plugin*, which is not installed here — `~/.claude/plugins` is absent and `.agents/skills/` holds only `frontend-design`. This is the same gap STORY-001, STORY-002 and STORY-003 recorded; it is a tooling gap, not a decision to work from memory. `chat_ui/AGENTS.md`'s rule is *"rather than relying on memory"*, so every Reflex API below was verified against current Reflex documentation (context7 `/websites/reflex_dev`) before being written into a task. What was verified for **this** story:

1. **The background-task state contract**, verbatim: *"To interact with the state safely, background tasks must enter an `async with self` context block. This block refreshes the state and acquires an exclusive lock, preventing concurrent modifications. Accessing state variables outside of this block may result in stale data, and attempting to modify state outside the context block will raise an error."* Two consequences, both binding on Task 2: (a) the guard STORY-003 left at the top of `load()` is a read outside the lock and is therefore **possibly stale**, so it must be re-asserted inside the first `async with self` — `sign_out()` can land between the trigger and the first lock acquisition; (b) every one of the ten results must be assigned inside a lock block, never at the point it is awaited.
2. **Blocking work is awaited *outside* the lock.** The documented `run_in_thread` example holds the lock only to mutate, and awaits the thread between two `async with self` blocks. Holding the lock across a 10-read round trip would serialize the session against every other event for the duration — the opposite of what the offload is for.
3. **`rx.run_in_thread(func)` exists** in the pinned `reflex==0.9.6.post1` and is Reflex's own wrapper for exactly this. It is **not** used here, deliberately: AC 1 names `asyncio.to_thread(...)` explicitly, PRD Section 6 names it (*"SQLite reads go through `asyncio.to_thread(...)`"*), and `chat_ui/chat_ui/state.py:110` already establishes it as this codebase's offload. Introducing a second mechanism for the same job on the second surface would leave the repo with two. Recorded here so the "improvement" is not made later without the reason.
4. **Background tasks are triggered by `return`/`yield`, never called.** Already satisfied — `authenticate()` returns `AdminState.load` (`admin_state.py:118`). This story adds no new trigger; STORY-017's refresh button binds `AdminState.load` directly.

**The `frontend-design` rules that bind the fault string.** *"Treat failure and emptiness as moments for direction, not mood. Explain what went wrong and how to fix it, in the interface's voice rather than a person's. Errors don't apologize, and they are never vague about what happened."* The message therefore names the read that failed, states that nothing on screen changed (which is the fact the admin most needs — a stale register is not a wrong one), and points at the retry. It does not apologize and does not say "something went wrong". *"An action keeps the same name through the whole flow"* — the message says **Refresh**, which is the word STORY-017's control must carry.

---

## Patterns to Follow

### The offload, the `finally`-reset of the in-flight flag, and the catch-all — all three already exist on the chat surface

```python
# SOURCE: chat_ui/chat_ui/state.py:76-88, 108-146, 178-180
    async def _do_send(self, text: str):
        # Claim the in-flight slot first and on its own, so everything that can
        # raise afterwards is inside the try/finally that clears `pending`
        # (PRD-004 Risk 3: a stuck flag locks the composer permanently).
        async with self:
            ...
            if self.pending:
                return
            self.pending = True

        try:
            ...
            try:
                result = await asyncio.to_thread(
                    run_query,
                    user_id=user_id,
                    ...
                )
            except OpenRouterError as exc:
                ...
            except Exception as exc:
                async with self:
                    self.messages.append(ChatMessage(kind="internal_error", ...))
                return
            ...
        finally:
            async with self:
                self.pending = False
```

Four properties carried over verbatim: the in-flight flag is claimed in its own lock block *before* anything that can raise; the blocking call is awaited **outside** the lock; the last exception arm is a bare `except Exception`; and the flag is cleared in a `finally` so the failure path cannot strand it. AC 3 and AC 4 are the same two requirements PRD-004 Risk 3 and "no silent drops" already produced here.

### The guard, and the note STORY-003 left for this story

```python
# SOURCE: chat_ui/chat_ui/admin_state.py:136-148
    @rx.event(background=True)
    async def load(self):
        """Loads the register and the summary. The read body is STORY-004.
        ...
        STORY-004 adds the reads BELOW this guard and must re-assert
        `self.authenticated` inside its first `async with self` block — a
        background task's read outside the lock can be stale, and
        `sign_out()` may land mid-read.
        """
        if not self.authenticated:
            return
```

The outer guard stays exactly as written (AC 6 and `tests/test_admin_state.py:245-268` pin it: `load()` on an unauthenticated state must read nothing and leave `loading` False and `error` empty — so the early return must happen **before** `loading` is ever set). The re-assertion is added inside the first lock, not in place of it.

### The projection to route every row through — and the one that must not be bypassed

```python
# SOURCE: chat_ui/chat_ui/admin_formatting.py:143-152
def to_audit_row(log: AuditLog, now: Optional[datetime] = None) -> AuditRow:
    """Projects one `AuditLog` onto the register's row model.

    `now` is a parameter so the relative time is deterministic under test and
    so a hundred rows share one clock read. Every field is named explicitly;
    neither preview is read (Risk 2).
    """
```

`now` is passed explicitly for the whole batch — one clock read for up to a hundred rows, and the same instant that becomes `last_refreshed`, so the register's relative times and its refresh stamp can never disagree. Constructing an `AuditRow` any other way in `load()` would route around Risk 2's mitigation.

### The order the database already returns, which this story must not re-impose

```python
# SOURCE: app/db/database.py:125-133
def list_audit_logs(limit: int = 100) -> list[AuditLog]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
```

`ORDER BY timestamp DESC` is already newest-first, so AC 2's ordering is satisfied by *preserving* the returned order. `load()` must not sort — sorting is [[STORY-005]]'s computed var, and a sort here would fight it.

### The per-call connection that makes the offload safe

```python
# SOURCE: app/db/database.py:17-21, 119-123
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def count_audit_logs() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]
```

Every read function opens and closes its own connection inside its own call. A `sqlite3.Connection` is not shareable across threads, so the offload must be **per call** — one `asyncio.to_thread` per read function, with the connection created and destroyed on the worker thread. Do not hoist a connection out and pass it in, and do not wrap all ten in a single thread call that shares one.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/admin_state.py` | UPDATE | Import the ten read functions and `to_audit_row`; add the `_READS` table and the fault-message constant; fill in `load()`'s body. |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | Add `format_refreshed_at(now)` — the refresh stamp is a rendered string, and this module is where "computed once in Python, never at render" lives. |

No file is created. Nothing under `app/`, `tests/`, or `chat_ui/chat_ui/components/` is touched.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: The refresh stamp gets a formatter, in the module that owns formatting

- **File**: `chat_ui/chat_ui/admin_formatting.py`
- **Action**: UPDATE
- **Implement**:
  - Add a module constant beside `DEVICE_TRUNCATE_LENGTH`:
    ```python
    # The refresh stamp's format. Seconds included deliberately: two refreshes a
    # minute apart must produce two visibly different stamps, or the control
    # reads as broken. UTC to match the audit table's own timestamps, which
    # `app/services/audit_logger.py` writes in UTC — a local-time stamp beside
    # UTC row times would be two clocks on one screen.
    REFRESHED_AT_FORMAT = "%Y-%m-%d %H:%M:%S UTC"
    ```
  - Add, after `_format_timestamps`:
    ```python
    def format_refreshed_at(now: Optional[datetime] = None) -> str:
        """The moment of the read, as the stamp the console shows beside refresh.

        Here rather than in `admin_state.py` for the reason at the top of this
        module: it is a rendered string, and components receive Vars, so it is
        computed once in Python when the read completes. STORY-017 renders it.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        return now.strftime(REFRESHED_AT_FORMAT)
    ```
- **Mirror**: `chat_ui/chat_ui/admin_formatting.py:126-141` (`_format_timestamps` — same `now`-as-parameter shape, same defensive default)
- **Validate**: `python -c "from datetime import datetime, timezone; from chat_ui.chat_ui.admin_formatting import format_refreshed_at; print(format_refreshed_at(datetime(2026,8,28,14,22,7,tzinfo=timezone.utc)))"` → `2026-08-28 14:22:07 UTC`

### Task 2: `admin_state.py` imports the ten reads — and only reads

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**:
  - Add `import asyncio` and `from datetime import datetime, timezone` to the imports.
  - Import the ten read functions **by name** from `app.db.database`. Not `from app.db import database as db`: PRD Section 9 is verbatim *"`AdminState` imports only the read functions from `app/db/database.py`. `insert_audit_log` is not imported, and there is no write path from any admin page"* — a module import makes `insert_audit_log` reachable as an attribute and gives back the write path the named imports deny. `tests/test_admin_state.py:281-287` asserts against the module namespace.
  - **Three of the ten collide with state field names** (`top_models`, `top_users`, `top_pii_entities` are declared as `list[str]` vars on `AdminState`). Alias exactly those three at import, and only those three, with a comment saying why:
    ```python
    from app.db.database import (
        count_audit_logs,
        count_blocked_duplicates,
        count_blocked_suspicious,
        count_pii_detected_queries,
        count_successful_queries,
        count_unique_users,
        list_audit_logs,
        # Aliased because the state declares fields of these three names. The
        # module global and the class attribute live in different namespaces
        # and Python resolves each correctly, but a reader of `load()` cannot
        # tell which one a bare `top_models` is — and a future edit that moves
        # the read into the class body would silently call a list.
        top_models as read_top_models,
        top_pii_entities as read_top_pii_entities,
        top_users as read_top_users,
    )
    ```
  - Add `from .admin_formatting import format_refreshed_at, to_audit_row` beside the existing `from .admin_models import AuditRow`.
  - Add two module constants below `GATE_REFUSED_MESSAGE`:
    ```python
    # The register's window, and the only ceiling there is: PRD-006 Section 4
    # puts pagination past 100 rows out of scope, and `list_audit_logs` is the
    # only listing query. Named so the register can state the cap it renders
    # against the true total (Risk 4) rather than re-typing 100.
    REGISTER_ROW_LIMIT = 100

    # The fault message. Names the read that failed and states that nothing on
    # screen changed — a stale register is not a wrong one, and that is the
    # fact the admin needs before deciding whether to trust what is displayed.
    # "Refresh" is the same word STORY-017's control must carry.
    # STORY-008 moves this string to admin_copy.py; this module then imports it.
    LOAD_FAILED_MESSAGE = (
        "Could not read {read}. Nothing on screen has changed. Refresh to try "
        "again. ({detail})"
    )
    ```
  - Add the read table at module level — **not** inside the class body, where the three colliding field names would shadow the imported functions:
    ```python
    # The ten reads, as data: (state field, what to call it in a fault message,
    # the read function, its keyword arguments). A table rather than ten
    # hand-written awaits because "all ten" is then one countable structure —
    # ten separate `await` lines can become nine in a refactor with nothing to
    # notice it, and STORY-006 asserts `len(_READS) == 10`. The label is the
    # only user-facing string here and moves to admin_copy.py with STORY-008.
    #
    # Order is the read order and is deliberate: the rows come first so the
    # slowest query fails fast, and `total_recorded` follows them because it is
    # the denominator the register states its 100-row cap against.
    _READS: tuple[tuple[str, str, object, dict], ...] = (
        ("rows", "the audit rows", list_audit_logs, {"limit": REGISTER_ROW_LIMIT}),
        ("total_recorded", "the recorded total", count_audit_logs, {}),
        ("blocked_duplicates", "the blocked duplicates", count_blocked_duplicates, {}),
        ("blocked_suspicious", "the blocked patterns", count_blocked_suspicious, {}),
        ("unique_users", "the user count", count_unique_users, {}),
        ("successful_queries", "the completed count", count_successful_queries, {}),
        (
            "pii_detected_queries",
            "the PII detection count",
            count_pii_detected_queries,
            {},
        ),
        ("top_models", "the model ranking", read_top_models, {}),
        ("top_users", "the user ranking", read_top_users, {}),
        ("top_pii_entities", "the PII entity ranking", read_top_pii_entities, {}),
    )
    ```
- **Mirror**: `chat_ui/chat_ui/state.py:4-12` (named imports from `app/`, no module-level import of the write path)
- **Validate**:
  ```bash
  python -c "import chat_ui.chat_ui.admin_state as m; assert not hasattr(m, 'insert_audit_log'); assert len(m._READS) == 10; assert len({r[0] for r in m._READS}) == 10; print('ok')"
  ```

### Task 3: `load()` — the ten offloaded reads, one commit, one fault arm

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**: replace the body of `load()` below the existing guard. Keep the existing outer guard and its docstring intent; extend the docstring to describe the read. The shape:
  ```python
      @rx.event(background=True)
      async def load(self):
          """Reads the register and the summary, off the event loop.

          ... (keep STORY-003's Risk 1 paragraph about the read being gated) ...

          Three structural properties, each one a requirement rather than a
          style choice:

          The gate is asserted **twice**. The first check is a read outside the
          lock, which Reflex documents as possibly stale, and `sign_out()` can
          land between the trigger and the first lock acquisition. The second
          check, inside the lock, is the one that holds.

          Every result is collected into a **local** and committed in one block
          at the end. That is what makes the fault arm's "rows and figures
          untouched" true by construction rather than by discipline: there is
          no point in this method at which some fields are new and others old,
          so a read that fails on the eighth of ten cannot leave a register
          that half agrees with its own summary.

          The `finally` clears `loading` on **both** paths. A flag stranded True
          locks STORY-017's refresh control permanently — PRD-004 Risk 3, the
          same failure the chat's composer already guards against.
          """
          if not self.authenticated:
              return

          async with self:
              # Re-asserted under the lock: the check above may be stale.
              if not self.authenticated:
                  return
              # A second in-flight read would race the first one's commit and
              # could publish the older of two results.
              if self.loading:
                  return
              self.loading = True
              self.error = ""

          try:
              # One clock read for the whole batch, so the rows' relative times
              # and the refresh stamp cannot disagree by a straggling second.
              now = datetime.now(timezone.utc)
              results: dict[str, object] = {}
              for field, label, read, kwargs in _READS:
                  try:
                      # Per call, never hoisted: each read function opens its
                      # own sqlite3 connection, and a connection cannot cross
                      # threads (app/db/database.py:17).
                      results[field] = await asyncio.to_thread(read, **kwargs)
                  except Exception as exc:
                      # Catch-all, matching PRD-004's "no silent drops": a read
                      # that fails is a fault panel naming what failed, never a
                      # silently empty table (PRD-006 Section 4).
                      async with self:
                          self.error = LOAD_FAILED_MESSAGE.format(
                              read=label, detail=exc
                          )
                      return

              # Order preserved from `list_audit_logs`' ORDER BY timestamp DESC
              # — newest first already. Sorting is STORY-005's computed var.
              rows = [to_audit_row(log, now) for log in results.pop("rows")]

              async with self:
                  # One commit. Until this block nothing on screen has moved.
                  self.rows = rows
                  for field, value in results.items():
                      setattr(self, field, value)
                  self.last_refreshed = format_refreshed_at(now)
                  self.error = ""
          finally:
              async with self:
                  self.loading = False
  ```
  Points the implementation must not drift on:
  - The **outer** guard returns before `loading` is touched — `tests/test_admin_state.py:245-268` asserts `loading is False` and `error == ""` after an unauthenticated `load()`.
  - The `to_audit_row` projection happens **outside** the lock (pure CPU over ≤100 rows) but **inside** the `try`, so a malformed row is caught by the same arm.
  - `setattr` over `results` is what keeps the ten reads a single table; the field names in `_READS` are exactly the vars STORY-003 declared, and a typo surfaces immediately as a new dynamic var rather than silently — STORY-006 asserts every `_READS` field name is in `AdminState.base_vars`.
  - `self.error = ""` on the success path clears a previous fault, so a recovered read does not keep showing the panel STORY-017 renders.
- **Mirror**: `chat_ui/chat_ui/state.py:76-180` (`_do_send` — claim-flag / offload / catch-all / `finally`-reset, in that order)
- **Validate**:
  ```bash
  grep -c "asyncio.to_thread" chat_ui/chat_ui/admin_state.py   # 1 (in the loop over all ten)
  grep -n "except Exception" chat_ui/chat_ui/admin_state.py    # present
  grep -n "finally" chat_ui/chat_ui/admin_state.py             # present
  python -m pytest tests/test_admin_state.py -q                # STORY-003's suite still green
  ```

### Task 4: Drive the state directly and assert every AC

- **File**: `<scratchpad>/drive_admin_load.py` (scratchpad only — the committed test file is [[STORY-006]])
- **Action**: CREATE (not committed)
- **Implement**: a script mirroring `tests/test_admin_state.py`'s direct-drive helpers (`AdminState(_reflex_internal_init=True)`, `type(state).event_handlers["load"].fn(state)`), monkeypatching the ten functions in the `chat_ui.chat_ui.admin_state` namespace. Assert:
  1. Every one of the ten is called exactly once, and each call happens on a **different thread than the caller** — record `threading.get_ident()` inside each stub and assert none equals the event loop's thread id (this is the assertion that actually proves AC 1; a `grep` for `to_thread` does not).
  2. `rows` holds `AuditRow` objects built by `to_audit_row`, in the order returned, and `total_recorded` equals `count_audit_logs`' return.
  3. `loading` is True during the read (observe it from inside one of the stubs) and False afterwards — on both the success and the failure path.
  4. With the eighth read patched to raise, `error` contains that read's label, `rows` and every figure keep their **pre-existing** values (populate them first), and `loading` is False.
  5. `last_refreshed` is non-empty after a success and unchanged after a failure.
  6. An unauthenticated `load()` calls **none** of the ten.
- **Mirror**: `tests/test_admin_state.py:44-95` (the `_state`, `_load` and `_populate` helpers)
- **Validate**: `python <scratchpad>/drive_admin_load.py` → all assertions pass

### Task 5: Prove nothing under `app/` moved

- **File**: none
- **Action**: verification only
- **Implement**: run the full suite and the diff check. `app/db/database.py` is read from and not edited: no eleventh function, no `limit`/`offset` parameter, no query change.
- **Validate**: `git diff main --stat -- app/` → empty output (AC 7)

---

## End-to-End Tests

- [ ] Seed `harness_ai.db` via the existing pipeline (or point `DATABASE_URL` at the repo's `harness_ai.db`), authenticate an `AdminState` with the configured token, await `load()`, and confirm `len(state.rows) == min(100, total)` with `state.total_recorded` equal to `count_audit_logs()`.
- [ ] Confirm `state.rows[0].timestamp_absolute >= state.rows[-1].timestamp_absolute` — newest first, unsorted by the console.
- [ ] Confirm no row carries prompt or response preview text: `assert not any(hasattr(r, "prompt_preview") or hasattr(r, "response_preview") for r in state.rows)` (Risk 2 held across the new read path).
- [ ] Patch `list_audit_logs` to raise, `load()` again on a state that already holds rows → `error` names "the audit rows", the row list is byte-identical to before, `loading` is False.
- [ ] Un-patch and `load()` again → `error` is empty, rows refresh, `last_refreshed` advances (the recovery STORY-017's retry depends on).
- [ ] `load()` twice concurrently (`asyncio.gather`) → the second returns immediately on the `loading` guard; exactly ten reads run, not twenty.

---

## Validation

```bash
python -c "import chat_ui.chat_ui.admin_state as m; assert len(m._READS) == 10; assert not hasattr(m, 'insert_audit_log'); print('ok')"
grep -c "asyncio.to_thread" chat_ui/chat_ui/admin_state.py     # 1
grep -n "get_connection\|sqlite3" chat_ui/chat_ui/admin_state.py   # no output — no connection handling on this side
python <scratchpad>/drive_admin_load.py                        # every AC assertion passes
python -m pytest tests/ -q                                     # full suite, PRD-001/003/004 tests unmodified
git diff main --stat -- app/                                   # must be empty
```

No frontend lint step applies (`chat_ui` is Reflex/Python, no JS package) and no server start is needed — this story adds no route, component or FastAPI wiring.

---

## Risks + Mitigations

**1. The stale guard.** `load()`'s first `if not self.authenticated` runs outside the lock and Reflex documents such reads as possibly stale; `sign_out()` can land between `authenticate()` returning `AdminState.load` and the first lock acquisition. *Mitigation*: the check is repeated inside the first `async with self`, which is the one that decides. Task 3 makes it explicit; STORY-006 asserts a sign-out between trigger and read leaves the row list empty.

**2. A stranded `loading` flag locks the refresh control.** Exactly PRD-004 Risk 3 on a new surface. *Mitigation*: `loading` is claimed in its own lock block before anything that can raise, and cleared in a `finally` that runs on the success, fault and re-entrancy paths alike.

**3. A partially-committed read.** Ten reads means ten chances to fail after some state has already been written — a register whose rows and summary describe different moments. *Mitigation*: structural, not disciplinary — results go to locals and are committed in one lock block after all ten return, so there is no interval in which the state is half-new. This is what makes AC 4's "untouched" checkable.

**4. The three name collisions.** `top_models`, `top_users` and `top_pii_entities` are both database functions and state fields. Python resolves each correctly today, but a later edit that moves a read into the class body would call a list. *Mitigation*: the three are aliased at import with the reason in a comment, and the reads live in a module-level table where the class namespace cannot reach them.

**5. Detail in the fault message.** `LOAD_FAILED_MESSAGE` interpolates the exception, which for a SQLite failure can include the database path. *Mitigation*: the string is only ever rendered behind the token gate, to the same admin who already sees `error_message` on every fault row, and the alternative — a message that names no cause — is the vagueness `frontend-design` rules out. Flagged here so STORY-008 keeps the decision when it moves the string to `admin_copy.py`.

**6. Reaching for a "faster" concurrent read.** Ten sequential `to_thread` awaits look like an obvious `asyncio.gather`. *Mitigation*: not done, and recorded as a decision — the ten reads share one SQLite file, `gather` would open ten connections at once against a database the chat surface is concurrently writing to, and the whole batch is ten indexed counts over one small table. Sequential also gives the fault arm an unambiguous "which read failed"; gathered, a failure is one of ten in flight.

---

## Acceptance Criteria

(Copied from story `STORY-004`)

- [ ] Given an authenticated `AdminState`, when `load()` runs, then it calls all ten read functions from `app/db/database.py` — `list_audit_logs(limit=100)`, `count_audit_logs`, `count_blocked_duplicates`, `count_blocked_suspicious`, `count_unique_users`, `count_successful_queries`, `count_pii_detected_queries`, `top_models`, `top_users`, `top_pii_entities` — each inside `asyncio.to_thread(...)`, never on the event loop.
- [ ] Given the returned `AuditLog` list, when `load()` completes, then state holds `list[AuditRow]` built through `to_audit_row(...)`, newest first, and `total_recorded` from `count_audit_logs()` as the register's denominator.
- [ ] Given a read in flight, when the page is observed, then `loading` is True for its duration and False afterwards, including on the failure path.
- [ ] Given any read function raising, when `load()` runs, then a catch-all `except Exception` sets an `error` string naming the read that failed, leaves the previously loaded rows and figures **untouched**, and clears `loading`.
- [ ] Given a successful load, when it completes, then `last_refreshed` is set to the time of the read.
- [ ] Given an unauthenticated state, when `load()` is called, then it returns immediately and performs no database read (STORY-003's guard).
- [ ] Given `app/`, when `git diff main --stat` is inspected, then no file under it is modified — no new database function and no query parameter is added.
- [ ] All tasks completed
- [ ] Frontend lint passes (N/A — no JS package in `chat_ui`)
- [ ] Backend server starts without error (`python -c "import app.main"` and `python -c "import chat_ui.chat_ui.admin_state"` both clean)
- [ ] Follows existing patterns (`state.py:_do_send`'s offload/`finally` shape, `admin_formatting.py`'s compute-once rule, named read-only imports)
