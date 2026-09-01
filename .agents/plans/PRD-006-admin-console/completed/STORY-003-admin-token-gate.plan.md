---
story: STORY-003
prd: PRD-006
slug: admin-token-gate
title: "AdminState token gate: compare_digest, one generic error, sign-out clears state"
type: feature
complexity: MEDIUM
epic_branch: epic/PRD-006-admin-console
created: 2026-08-28
---

# Plan: AdminState token gate — compare_digest, one generic error, sign-out clears state

## Summary

Create `chat_ui/chat_ui/admin_state.py`: the console's session state, and in this story only its **access half**. It declares `AdminState` as a direct `rx.State` subclass — a *sibling* of `ChatState`, never a substate — holding `token_input`, `authenticated`, `gate_error`, plus the data fields the later stories populate. `authenticate()` compares the submitted token with `secrets.compare_digest` against `settings.ADMIN_TOKEN`, mirroring `app/middleware/auth.py:require_admin_token` exactly, over UTF-8 **bytes** so a length or encoding mismatch cannot raise; every refusal — empty, wrong length, wrong value — sets one identical message and leaves `authenticated` False, so the gate is not an oracle. A success clears the error and the typed token and returns the `load` event, which this story defines as a **guard only**: `load()` returns immediately unless `authenticated`, so an unauthenticated page holds no data regardless of what renders (Risk 1). `sign_out()` clears the whole state through `rx.State.reset()`, which empties the token, the rows, the summary fields and the refreshed stamp — and keeps doing so for every field STORY-004 and STORY-005 add later. Nothing under `app/` is touched; the read body of `load()` is [[STORY-004]] and the tests are [[STORY-006]].

## User Story

As a security admin
I want the console to require the admin token and to hold nothing after sign-out
So that an open browser on a shared machine is not a standing disclosure (PRD Section 5, story 8).

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-003-admin-token-gate.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 4 (console shell & access), Section 6 (read path, "gate as state, not as route"), Section 9 (token handling, no oracle, read-only by construction), Section 12 Phase 1, Risk 1

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/` (one new module). No `app/` change, no test file (that is STORY-006), no component. |
| Story | STORY-003 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

**Dependency check**: `depends_on: []`. STORY-001 (`admin_models.py`, commit `577a285`) and STORY-002 (`admin_formatting.py`, commit `0fe6c69`) are both `status: done` on the branch, so the `AuditRow` type this state annotates its row list with already exists. Cleared to proceed.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `reflex-docs` (**NOT INSTALLED** — substituted, see below) | `chat_ui/AGENTS.md` mandates it for any Reflex API. This story uses four: `rx.State` subclassing, `@rx.event`, `@rx.event(background=True)`, and returning an event handler to chain. | Task 1, Task 2 |
| `reflex-process-management` (**NOT INSTALLED**) | Mandated for any compile/run/reload cycle. This story renders nothing and starts no server; validation is import + direct state drive. | none |
| `.agents/skills/frontend-design` | Read. Governs visual and structural decisions; this module renders nothing. One copy rule binds the single string it emits — see below. | Task 1 |

**Skill availability and the substitution.** `reflex-docs` and `reflex-process-management` ship in the `reflex-dev/agent-skills` Claude Code *plugin*, which is not installed here (`~/.claude/plugins` is absent; `.agents/skills/` holds only `frontend-design`) — the same gap STORY-001 and STORY-002 recorded. `chat_ui/AGENTS.md`'s rule is *"rather than relying on memory"*, so every Reflex API below was verified against current Reflex documentation (context7 `/websites/reflex_dev`) **and** against the pinned package (`reflex==0.9.6.post1`) before being written into a task. What was verified:

1. **Sibling states.** *"Defining Multiple Page States — create separate state classes by inheriting from `rx.State` for different pages"*. `AdminState(rx.State)` is therefore a peer of `ChatState`, exactly as PRD Section 4 requires (*"`ChatState` never reads admin state"*). Subclassing `ChatState` — or any other state — would make it a substate and violate that.
2. **Background tasks must be triggered by `yield`/`return`.** Verbatim: *"background tasks cannot be called directly from other handlers and must be triggered using yield or return."* So `authenticate()` must `return AdminState.load` — **not** `await self.load()`.
3. **Event handlers may return other event handlers** to chain (*"State > Events > Chaining Events > Returning Events From Event Handlers"*).
4. **Background tasks read state outside `async with self` (possibly stale) and may only *mutate* inside it.** This is why the `load()` guard is a plain read followed by an immediate `return` — it writes nothing — and why STORY-004 must re-assert the guard inside its lock (see Risk 3).
5. **`rx.State.reset()` exists in the pinned version** and resets every base var to its default, explicitly skipping the router (confirmed by `inspect.getsource(rx.State.reset)` against the installed package). Its recursion runs over `self.substates`, which for `AdminState` is empty — `ChatState` is a sibling, not a child, and is untouched.
6. **No reserved-name collision**: `load`, `error`, `rows`, `loading`, `authenticate`, `sign_out`, `token_input`, `authenticated`, `gate_error`, `last_refreshed` were each checked against `dir(rx.State)` — none is taken.

**The `frontend-design` rule that binds Task 1.** This module emits exactly one user-facing string, the gate refusal. The skill: *"errors don't apologize, and they are never vague about what happened"* — held here against PRD Section 9's *"The gate reports that access was refused, not why"*. The resolution is not a contradiction: the message is specific about **what happened** (access refused, the token was not accepted) and silent about **which** of three reasons produced it, because naming that reason is the oracle. It does not apologize and does not hedge.

---

## Patterns to Follow

### The comparison to mirror — exactly, and without modifying it

```python
# SOURCE: app/middleware/auth.py:11-18
def require_admin_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> None:
    if credentials is None or not secrets.compare_digest(
        credentials.credentials, settings.ADMIN_TOKEN
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")
```

Two properties to carry over: `secrets.compare_digest` (never `==`), and **one** outcome for every failure mode — the missing-credential arm and the wrong-token arm raise the identical `HTTPException`. That single-message discipline is the gate's no-oracle property, already present in the code being mirrored. `tests/test_admin_auth.py:87-108` pins the constant-time call by spying on `secrets.compare_digest`; the console's own equivalent assertion is STORY-006's.

### State class shape, docstring voice, and explicit `@rx.event` setters

```python
# SOURCE: chat_ui/chat_ui/state.py:15-45
class ChatState(rx.State):
    """Session state for the chat surface: the transcript, the composer, and
    who is sending.
    ...
    """

    messages: list[ChatMessage] = []
    input_text: str = ""
    user_id: str = ""
    user_id_error: str = ""
    pending: bool = False

    @rx.event
    def set_input_text(self, text: str):
        self.input_text = text
```

### The gate handler this one mirrors — validate, one error string, clear on success

```python
# SOURCE: chat_ui/chat_ui/state.py:57-65
    @rx.event
    def submit_user_id(self):
        text = self.user_id_input.strip()
        if not text:
            self.user_id_error = USER_ID_VALIDATION_ERROR
            return
        self.user_id_error = ""
        self.user_id = text
```

### Clearing state on the way out, deliberately rather than by hiding

```python
# SOURCE: chat_ui/chat_ui/state.py:67-77
    @rx.event
    def reset_user_id(self):
        """Ends the session. The transcript goes with it: the header names who
        is sending, so leaving one user's prompts on screen under another's ID
        would misattribute them in a surface people read as a record."""
        self.user_id = ""
        self.user_id_input = ""
        self.user_id_error = ""
        self.messages = []
        self.input_text = ""
```

`sign_out()` is the same idea with a stronger guarantee — see decision 5 for why it calls `reset()` instead of listing fields.

### Background event, and reading through the lock

```python
# SOURCE: chat_ui/chat_ui/state.py:203-213
    @rx.event(background=True)
    async def send(self):
        # Read through the lock: a background event has no exclusive access to
        # state outside an `async with self` block.
        async with self:
            text = self.input_text
        await self._do_send(text)
```

### Importing `app` from inside `chat_ui`

```python
# SOURCE: chat_ui/chat_ui/state.py:4-8
from app.models.schemas import QueryBlockedDuplicateResponse, QuerySuccessResponse
from app.services.query_pipeline import run_query
```

`chat_ui/chat_ui/chat_ui.py:4-7` puts the repo root on `sys.path` before any of these resolve; a plain top-level `from app.config import settings` is the established form.

---

## Design Decisions

1. **`AdminState(rx.State)` — a sibling, never a substate.** PRD Section 4: *"`ChatState` never reads admin state, and no admin page renders a chat component."* Reflex's documented multi-page pattern is one `rx.State` subclass per surface, so `AdminState` subclasses `rx.State` directly and imports nothing from `chat_ui/chat_ui/state.py`. The separation is checkable by grep, and STORY-009 repeats it at the component layer.

2. **`compare_digest` over UTF-8 bytes** (AC 5). `secrets.compare_digest` accepts two `str` only when *both* are ASCII-only; a non-ASCII character in either operand raises `TypeError` ("comparing strings with non-ASCII characters is not supported"), and the submitted token comes from a browser field, so it is arbitrary text. Both operands are therefore `.encode("utf-8")`d first. Differing byte *lengths* are fine — `compare_digest` handles unequal-length inputs by design (it leaks length, never content) and does not raise. This is an encoding change, not a comparison change: the function, its operands and its semantics are `require_admin_token`'s.

3. **A blank-token guard runs before the comparison, and produces the same message** (AC 2). `Settings.ADMIN_TOKEN` is a required field but `""` satisfies it, so a misconfigured deployment could reach `compare_digest(b"", b"")` → `True` and open the console with an empty token. `authenticate()` therefore refuses when the submitted token is empty *or* the configured token is empty, before comparing. This is additive to the mirrored comparison, not a deviation from it: the branch depends only on emptiness — which an attacker already knows about their own input — and it emits the **same** `gate_error` as a wrong token, so it adds no oracle. It also makes AC 2 hold unconditionally instead of only when `ADMIN_TOKEN` is non-empty. `app/middleware/auth.py` is not touched to match; hardening the console must not change the shipped API's behaviour (AC 7).

4. **The token is cleared from state on *both* arms of `authenticate()`.** On failure, so the gate does not re-render the field pre-filled (STORY-009 AC 3, verbatim: *"the token field is not repopulated"*). On success, because `authenticated` is the credential from that point on and there is no reason for the secret to stay resident — PRD Section 9's *"holds nothing"* read at its strongest. `token_input` is a transient input buffer, not the session.

5. **`sign_out()` calls `self.reset()`, rather than assigning eight fields to their defaults.** AC 4 requires the token, the rows, the summary figures and the refreshed stamp to be *cleared from state, not merely hidden from the view*. An explicit list satisfies that today and silently stops satisfying it the moment STORY-004 adds nine count fields or STORY-005 adds the filter vars — the failure mode is a field that survives sign-out and is invisible in review. `reset()` restores every base var to its declared default, so the guarantee holds for fields that do not exist yet, and the declared defaults are all safe (`authenticated=False`, `rows=[]`, `token_input=""`). Verified in the pinned package: it skips the router and recurses only into `self.substates`, which is empty here. The method still carries an explicit docstring naming what goes, in `reset_user_id`'s voice, so the intent survives even if the implementation is ever unrolled.

6. **`load()` is defined here as the guard and nothing else** (AC 6, Risk 1). The body is STORY-004's. The guard is the whole point of defining the method early: PRD Risk 1's mitigation is *"the read itself is gated, not just the view — `load()` returns immediately unless `authenticated` is true, so an unauthenticated page has no data in state to leak regardless of what renders."* A stub that returns before touching the lock is also directly drivable in a test (`await handler.fn(state)` — `tests/test_chat_state.py:80-84`), which is how STORY-006 asserts the spied database module was never called.

7. **`load()` is declared `@rx.event(background=True)` now, not later.** Two reasons it cannot wait for STORY-004: `authenticate()` must `return` it as an event to chain into (decision 8), and the decorator is what makes it an `EventHandler` rather than a coroutine. PRD Section 6's read path already fixes it as a Reflex background event, so this is the PRD's decision being recorded early, not a scope grab.

8. **`authenticate()` chains by returning `AdminState.load`.** Reflex's documented constraint is explicit — a background task *"cannot be called directly from other handlers and must be triggered using yield or return."* `await self.load()` would raise; `return AdminState.load` queues it after the state update flushes, which is also what makes the gate's transition visible before the read starts. Written as `AdminState.load`, not `type(self).load`, so a future subclass cannot silently retarget the chain.

9. **The state fields are declared in full here, populated later.** `rows`, `total_recorded`, the five other scalar counts, the three ranked lists, `last_refreshed`, `loading` and `error` are declared with defaults in this story even though STORY-004 fills them. AC 4 names "the loaded rows, the summary figures and the last-refreshed stamp" as things sign-out must clear, and a field that does not exist cannot be asserted cleared. The names in Task 1 are the contract STORY-004 populates and STORY-015 reads; changing one there means changing it here.

10. **The refusal string is a module constant, and STORY-008 re-homes it.** PRD Section 4 requires every admin string in `admin_copy.py`, but that module is STORY-008 and does not exist yet; STORY-003 is `depends_on: []` and must not block on it. So `GATE_REFUSED_MESSAGE` is defined at the top of `admin_state.py` with a comment naming its destination, and STORY-008 replaces the definition with an import from `admin_copy`. One line of churn, and the story stays independently shippable. Flagged in Risks so the move is not forgotten.

11. **No database import in this story.** `load()` reads nothing yet, so `admin_state.py` imports `settings` and `AuditRow` and nothing else. When STORY-004 adds imports they are read functions only — PRD Section 9, verbatim: *"`insert_audit_log` is not imported, and there is no write path from any admin page."* A `grep` for it is part of the validation so the invariant is asserted from the first commit of the file.

12. **No test file in this story.** `tests/test_admin_state.py` is STORY-006, which depends on 003/004/005 so it can assert the gate, the failure arm and the filters in one place. This story validates by driving the state directly from a throwaway script under the scratchpad (Task 3) and recording the output in the report — the same evidence, without pre-empting another story's file.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/admin_state.py` | CREATE | `AdminState`: the field set, the `compare_digest` gate, `sign_out()`, and `load()`'s authentication guard. |

Files explicitly **not** changed, and each verified in Task 4:

- `app/config.py`, `app/middleware/auth.py` — AC 7, asserted by an empty `git diff`.
- Anything else under `app/` — PRD Section 11's headline quality indicator.
- `chat_ui/chat_ui/state.py`, `chat_ui/chat_ui/chat_ui.py` — the chat surface is untouched; route registration is STORY-010.
- `chat_ui/chat_ui/admin_models.py`, `chat_ui/chat_ui/admin_formatting.py` — consumed as shipped by STORY-001/002.
- PRD Section 15's eight pinned test files.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `admin_state.py` — module docstring, imports, refusal constant, field set

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: CREATE
- **Implement**, in this order:
  1. **Module docstring** in `state.py`'s voice (`state.py:16-24` is the model: what the class is for, then the one invariant that makes the design structural rather than aspirational). State the three things a reader must not undo: `AdminState` is a **sibling** of `ChatState` and imports nothing from it (PRD Section 4); the module imports only `settings` and, later, read functions from `app/db/database.py` — never `insert_audit_log` (PRD Section 9); and the gate emits one message for every failure mode, so adding a "helpful" second one would build the oracle PRD Section 9 forbids.
  2. **Imports** — `secrets`, `reflex as rx`, `from app.config import settings`, `from .admin_models import AuditRow`. Nothing else. Do not import `app.db.database` yet (decision 11), do not import `chat_ui.chat_ui.state`.
  3. **The refusal constant**, with the re-homing comment from decision 10:
     ```python
     # One message for an empty token, a wrong-length token and a wrong token of
     # the right length. PRD-006 Section 9: "an empty, malformed or wrong token
     # produces the same message. The gate reports that access was refused, not
     # why." Splitting this into three would be the oracle.
     # STORY-008 moves this string to admin_copy.py; this module then imports it.
     GATE_REFUSED_MESSAGE = "Access refused. That token was not accepted."
     ```
  4. **`class AdminState(rx.State):`** with the class docstring and the field set. Gate fields first, then the data fields decision 9 fixes:
     ```python
     token_input: str = ""
     authenticated: bool = False
     gate_error: str = ""

     rows: list[AuditRow] = []
     total_recorded: int = 0
     blocked_duplicates: int = 0
     blocked_suspicious: int = 0
     unique_users: int = 0
     successful_queries: int = 0
     pii_detected_queries: int = 0
     top_models: list[str] = []
     top_users: list[str] = []
     top_pii_entities: list[str] = []
     last_refreshed: str = ""
     loading: bool = False
     error: str = ""
     ```
     Comment the second block as declared-here-populated-by-STORY-004, and note that every default must stay a safe empty value because `sign_out()` restores exactly these (decision 5).
  5. **`set_token_input`** as an explicit `@rx.event` setter, mirroring `state.py:41-43`.
- **Mirror**: `chat_ui/chat_ui/state.py:15-53` (class shape, field block, explicit setter), `chat_ui/chat_ui/admin_formatting.py:1-19` (module-docstring voice for an admin module).
- **Do not**: subclass `ChatState` or any state other than `rx.State`; import `app.db.database`; give any field a non-empty default.
- **Validate**:
  ```bash
  python -c "from chat_ui.chat_ui.admin_state import AdminState; import reflex as rx; assert AdminState.__bases__ == (rx.State,), AdminState.__bases__; print(sorted(AdminState.base_vars))"
  grep -n "insert_audit_log\|from .state import\|from chat_ui.chat_ui.state" chat_ui/chat_ui/admin_state.py   # no output
  ```

### Task 2: The gate — `authenticate()`, `sign_out()`, and `load()`'s guard

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE (same file, second pass — kept separate because this is the security surface and reviews on its own)
- **Implement**:
  1. **`authenticate()`** as `@rx.event`:
     ```python
     @rx.event
     def authenticate(self):
         """Compares the submitted token with app/middleware/auth.py's
         comparison, and refuses every failure identically.

         The bytes encoding is the one deviation from require_admin_token, and
         it is an encoding change rather than a comparison change:
         secrets.compare_digest raises TypeError on non-ASCII str operands, and
         this token arrives from a browser field. Encoded, unequal lengths are
         handled by compare_digest itself and cannot raise.
         """
         submitted = self.token_input
         configured = settings.ADMIN_TOKEN or ""
         # Emptiness on either side refuses before the comparison: ADMIN_TOKEN
         # is a required setting but "" satisfies it, and compare_digest(b"", b"")
         # is True — a blank configured token would otherwise open the console.
         # Same message as every other refusal, so this adds no oracle.
         if not submitted or not configured:
             self._refuse()
             return
         if not secrets.compare_digest(
             submitted.encode("utf-8"), configured.encode("utf-8")
         ):
             self._refuse()
             return
         self.authenticated = True
         self.gate_error = ""
         # The secret does not stay resident: `authenticated` is the credential
         # from here on (PRD-006 Section 9).
         self.token_input = ""
         return AdminState.load
     ```
     with a private `_refuse()` helper that sets `gate_error = GATE_REFUSED_MESSAGE`, `authenticated = False` and `token_input = ""` — one place, so the three refusal paths cannot drift into three messages.
  2. **`sign_out()`** as `@rx.event`, calling `self.reset()`, with a docstring in `reset_user_id`'s voice naming what goes and why the call is `reset()` rather than a field list (decision 5): the token, the loaded rows, the summary figures and the refreshed stamp — *cleared from state, not hidden from the view* — and every field a later story adds, by construction.
  3. **`load()`** as `@rx.event(background=True)`, guard only:
     ```python
     @rx.event(background=True)
     async def load(self):
         """Loads the register and the summary. The read body is STORY-004.

         The guard is the whole of this method today, and it is the load-bearing
         half of PRD-006 Risk 1: the read itself is gated, not just the view, so
         an unauthenticated page has no data in state to leak regardless of what
         any component chooses to render. STORY-004 fills in the reads BELOW this
         guard and must re-assert `self.authenticated` inside its first
         `async with self` block — a background task's read outside the lock can
         be stale, and sign_out() may land mid-read.
         """
         if not self.authenticated:
             return
     ```
- **Mirror**: `app/middleware/auth.py:11-18` (the comparison and its single-outcome discipline), `chat_ui/chat_ui/state.py:57-65` (gate handler shape: validate, one error, clear on success), `chat_ui/chat_ui/state.py:67-77` (clearing docstring voice), `chat_ui/chat_ui/state.py:203-213` (background-event declaration).
- **Do not**: use `==` or `!=` on the tokens anywhere; emit more than one distinct `gate_error` value; `await self.load()` from `authenticate()` (Reflex forbids calling a background task directly — return it); write to state inside `load()`.
- **Validate**:
  ```bash
  grep -n "compare_digest" chat_ui/chat_ui/admin_state.py           # exactly one call
  grep -n "gate_error = " chat_ui/chat_ui/admin_state.py            # only GATE_REFUSED_MESSAGE and ""
  python -c "from chat_ui.chat_ui.admin_state import AdminState; print(type(AdminState.load), AdminState.load.fn.__name__)"
  ```

### Task 3: Drive the state directly and record the evidence

- **File**: scratchpad only — `<scratchpad>/drive_admin_state.py`. **Nothing is committed by this task.**
- **Action**: verify
- **Implement**: a script that instantiates the state the way the existing tests do (`AdminState(_reflex_internal_init=True)`, `tests/test_chat_state.py:74-77`), monkeypatches `settings.ADMIN_TOKEN`, and asserts, one assertion per acceptance criterion:
  - the correct token → `authenticated is True`, `gate_error == ""`, `token_input == ""`, and the return value is the `load` event handler (AC 3);
  - `""`, a wrong token of a different length, and a wrong token of the **same** length as the configured one → three runs producing `gate_error` values asserted **equal to each other** and `authenticated is False` each time (AC 2);
  - a non-ASCII submitted token (e.g. `"ñ" * 12`) against an ASCII configured token → refused, and no `TypeError` (AC 5);
  - a configured token of `""` with a submitted `""` → refused (decision 3);
  - an authenticated state with `rows`, the count fields and `last_refreshed` hand-populated → after `sign_out()`, every one of them is back to its default and `authenticated is False` (AC 4);
  - an unauthenticated state → `await type(state).event_handlers["load"].fn(state)` returns with `rows == []` (AC 6).
- **Mirror**: `tests/test_chat_state.py:74-84` for the instantiation and the `handler.fn(state)` drive. No pytest wiring is needed for a script — use `asyncio.run`.
- **Note**: this is the same evidence STORY-006 will encode as `tests/test_admin_state.py`; running it here proves the ACs at the point they are implemented rather than three stories later. Paste the output into the story report.
- **Validate**: `python <scratchpad>/drive_admin_state.py` → every assertion passes, no traceback.

### Task 4: Prove the blast radius

- **File**: — (verification only)
- **Action**: verify
- **Implement**: run the full suite and confirm the diff is one new file.
- **Validate**:
  ```bash
  python -m pytest tests/ -q                                        # 0 failures
  python -m pytest tests/test_admin_auth.py -q                      # AC 7's suite, unmodified
  git diff --stat -- app/                                           # empty
  git diff --stat -- app/config.py app/middleware/auth.py           # empty (AC 7)
  git status --short                                                # only chat_ui/chat_ui/admin_state.py
  ```
- **Note**: importing the `chat_ui` package can make Reflex rewrite `chat_ui/reflex.lock/`, `bun.lock` and `package.json` (STORY-001 report, Deviation 5). That is an interpreter side effect, not part of this story — `git checkout --` those paths and keep them out of the commit.

---

## End-to-End Tests

Nothing renders in this story (the gate form is STORY-009, the routes are STORY-010), so the end-to-end here is the state machine an admin traverses.

- [ ] Fresh `AdminState` → `authenticated` False, `rows` empty, `gate_error` empty: the default is refused, not open.
- [ ] Submit `""` → refused; submit `"wrong"` → refused; submit a wrong token of exactly `len(ADMIN_TOKEN)` → refused. Collect the three `gate_error` values and assert `len(set(...)) == 1` — the no-oracle property, asserted as identity rather than as non-emptiness.
- [ ] Submit the configured token → `authenticated` True, `gate_error` cleared, `token_input` cleared, and the `load` event returned for chaining.
- [ ] Hand-populate `rows`, `total_recorded`, `top_models`, `last_refreshed` → `sign_out()` → every field back to its default, `authenticated` False, and a subsequent direct `load()` call returns with `rows` still empty.
- [ ] `await load()` on an unauthenticated state (the `/admin/stats`-reached-directly case) → returns immediately, `rows == []`, and — once STORY-004 lands — no read function called.
- [ ] `python -m pytest tests/test_admin_auth.py tests/test_chat_state.py -q` → green and unmodified: the console's gate did not disturb the API's.

---

## Validation

```bash
python -c "from chat_ui.chat_ui.admin_state import AdminState; import reflex as rx; assert AdminState.__bases__ == (rx.State,)"
grep -n "insert_audit_log" chat_ui/chat_ui/admin_state.py     # no output — read-only by construction
grep -c "compare_digest" chat_ui/chat_ui/admin_state.py       # 1
python <scratchpad>/drive_admin_state.py                      # every AC assertion passes
python -m pytest tests/ -q
git diff --stat -- app/                                       # must be empty
```

No frontend lint step applies (`chat_ui` is Reflex/Python, no JS package) and no server start is needed — this story adds no route, component or FastAPI wiring.

---

## Acceptance Criteria

(Copied from story `STORY-003`)

- [ ] Given `chat_ui/chat_ui/admin_state.py`, when it is created, then `AdminState` holds `token_input`, `authenticated: bool = False` and `gate_error: str`, and `authenticate()` compares the submitted token with `secrets.compare_digest` against `settings.ADMIN_TOKEN` — the same comparison `require_admin_token` uses.
- [ ] Given an empty token, a wrong-length token and a wrong token of the correct length, when each is submitted, then all three produce the **identical** `gate_error` string and leave `authenticated` False — no oracle distinguishes them.
- [ ] Given a correct token, when it is submitted, then `authenticated` becomes True, `gate_error` is cleared, and the load is triggered.
- [ ] Given an authenticated state with rows and figures populated, when `sign_out()` is called, then the token, the loaded rows, the summary figures and the last-refreshed stamp are all cleared from state — not merely hidden from the view.
- [ ] Given a submitted token and a configured token of differing byte lengths, when `compare_digest` is called, then it does not raise — both operands are encoded consistently first.
- [ ] Given `load()` on an unauthenticated state, when it is called directly, then it returns without reading the database and the row list stays empty (Risk 1).
- [ ] Given `app/config.py` and `app/middleware/auth.py`, when the diff is inspected, then neither is modified.
- [ ] All tasks completed
- [ ] Full suite passes; PRD Section 15's eight pinned test files unmodified
- [ ] Follows existing patterns (`chat_ui/chat_ui/state.py`, `app/middleware/auth.py`)

---

## Risks & Mitigations

1. **The refusal string lives in `admin_state.py` until STORY-008 exists**, against PRD Section 4's "every user-facing string lives in a copy module". *Mitigation*: decision 10 — one named constant with a comment naming `admin_copy.py` as its destination, and STORY-008 (which has no dependency on this story) replaces the definition with an import. STORY-008's plan must pick this up; the constant name `GATE_REFUSED_MESSAGE` is the grep target.

2. **The blank-token guard could be read as a second failure mode and later "improved" into its own message.** *Mitigation*: all three refusal paths route through one `_refuse()` helper, so there is one assignment site for `gate_error` in the file; Task 2's `grep` validates that, and STORY-006 asserts the three messages equal to each other rather than merely non-empty.

3. **A stale `authenticated` read inside the background `load()`.** Reflex background tasks read outside `async with self` without a lock, so a `sign_out()` landing mid-read could leave a task that has already passed the guard. *Mitigation*: the guard here is a pure early return that writes nothing, so a stale True costs nothing today; the obligation is carried into STORY-004 in `load()`'s own docstring — re-assert `self.authenticated` inside the first `async with self` before assigning `rows`. Recorded there rather than left implicit.

4. **`self.reset()` is a wider hammer than the AC asks for**, and would also clear a field a future story wants to survive sign-out (a remembered filter, say). *Mitigation*: nothing on this surface should survive sign-out — that is the story's premise, and PRD Section 9 states it — so the wide clear is the correct semantics rather than a convenient one. If a survivor is ever genuinely needed, it belongs outside `AdminState`, and the docstring says so.

5. **Field names fixed here must match what STORY-004 and STORY-015 expect.** *Mitigation*: decision 9 lists them explicitly as the contract, and STORY-004's plan mirrors the list. A mismatch fails loudly at attribute assignment rather than silently, because Reflex states reject unknown attributes.

6. **`AdminState` could drift into a substate** if a later story subclasses it from `ChatState` for convenience (to share `router`, for instance). *Mitigation*: the `__bases__` assertion in Task 1's validation and in the Validation block is cheap and exact; STORY-018's render-invariant tests are the natural place to make it permanent.
