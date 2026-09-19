---
story: STORY-011
prd: PRD-010
slug: chat-history-assemble-and-fit
title: "chat_history.assemble (answered exchanges only) and fit (drop oldest whole exchanges)"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-010-multi-turn-pipeline
created: 2026-09-18
---

# Plan: chat_history.assemble (answered exchanges only) and fit (drop oldest whole exchanges)

## Summary

Create `app/services/chat_history.py` with exactly two public functions and no state. `assemble(identity, session_id)` makes one call to `chat_sessions.messages_for`, keeps only `kind == "assistant"` rows, and emits `Message("user", row.prompt), Message("assistant", row.content)` per row — so D4 (no refused turn re-enters context) holds *by construction* rather than by a filter over blocked kinds, and PRD 6.4 fact 1 (the first user bubble of a new chat is never persisted) is satisfied because the pair is rebuilt from the assistant row's own `prompt`. `fit(history, new_turn, max_messages, max_characters)` is pure: it appends the new turn, and while either limit is broken it drops `history[:2]` — the oldest whole exchange — counting as it goes, with `[new_turn]` as the floor it never goes below. Nothing in production imports the module when this story lands; STORY-012 wires it into `ChatState`. That mirrors STORY-001, which shipped `app/models/messages.py` "imported only by its tests".

Exploration turned up eight facts that shape the design beyond what the story text says:

1. **`messages_for` already sorts, and already returns `[]` for all three refusals.** `app/services/chat_sessions.py:324-343` short-circuits on `not settings.CHAT_HISTORY_ENABLED` and otherwise delegates to `database.list_chat_messages(session_id, identity.user_id)`, whose docstring pins **`ORDER BY id ASC`, never by a timestamp** (`app/db/database.py:1778-1781`), and whose `WHERE` scopes by `user_id` — which is why a foreign and an unknown session are indistinguishable from each other and from an empty one. The story is right to say "rely on it and test it": `assemble` must **not** re-sort and must **not** re-check ownership. A defensive `sorted(rows, key=…)` in `assemble` would mask exactly the regression the transcript-order test at `tests/test_chat_sessions.py:645-667` exists to catch.
2. **`prompt` is nullable in the table; `content` is not — and the write path actively turns an empty prompt into `NULL`.** `chat_messages` declares `content TEXT NOT NULL` and `prompt TEXT` (`app/db/models.py:163,165`), and `StoredMessage` (`:261-294`) mirrors that with `content: str` and `prompt: Optional[str] = None`. `chat_ui/chat_ui/state.py:57` persists `prompt=bubble.prompt or None`, so `""` and `None` are the *same* fact arriving by two routes, which is exactly why the falsy test `if not row.prompt` is the right single branch rather than an `is None` check. The reverse case needs no guard: an assistant row with `content == ""` still emits its pair, because dropping half of a real exchange would break user/assistant alternation for every later turn. (`content` on an assistant row holds the **redacted** reply — the only form ever persisted, PRD-008 Section 9 — which is why re-redacting it in the pipeline is a no-op, per PRD 6.4.)
3. **`fit`'s arithmetic must mirror `_context_limit_exceeded` exactly, including its strictness.** `app/services/query_pipeline.py:88-97` counts `len(messages)` and `sum(len(message.content) for message in messages)` and compares with **strict `>`** ("a conversation exactly at the maximum is within the limit"). `fit` therefore has to accept on `<=` on both counts and use the identical character expression. If the two drifted by one, `fit` would hand the pipeline a conversation the pipeline then refuses — a context-limit bubble on a send that was trimmed *to fit*. Task 7 pins the pairing directly by asserting `_context_limit_exceeded(fitted) is None`, which is the only test that can catch the drift.
4. **`len(history) // 2` in AC 5 only means what it says if history is pair-shaped, so `fit` must reject an odd-length one — and `ValueError` is the established way.** `assemble` cannot produce an odd history, but `fit` is public and pure, and `history[:2]` slicing over an odd list would eventually leave an orphan message and pair it with the new turn — splitting an exchange, which AC 4 forbids outright. A `ValueError` guard is the smallest thing that keeps AC 4 unconditionally true and keeps AC 5's `// 2` exact, and it is precisely what the closest precedent does: `dedup_key` raises `ValueError("dedup_key needs at least one turn")` (`app/services/duplicate_checker.py:58-63`) rather than declaring a custom exception, because a pure function's structural precondition is a caller bug. This is a **plan decision the story does not state** (see Risks, R1): the alternative — documenting odd input as undefined — leaves the "never splits a pair" guarantee resting on caller discipline, which is what this module exists to remove. The guard must not fire on `[]`.
5. **There is no `hypothesis` in this project.** `grep -rn hypothesis requirements*.txt pyproject.toml tests/` returns nothing, and `requirements.txt` holds no property-testing library. AC 5's "property tests over random histories" is therefore implemented with a seeded `random.Random(seed)` and `@pytest.mark.parametrize("seed", range(…))`, so a failure names the seed and reproduces exactly. Adding a dependency is not in PRD Section 8's stack and would touch the container build — out of scope for a story that ships one pure function.
6. **`context_limit` is not yet one of the persisted kinds, and that does not block AC 2.** `tests/test_chat_sessions.py:80-88` pins `SEVEN_KINDS` (`user`, `assistant`, `duplicate`, `injection`, `forbidden`, `upstream_error`, `internal_error`); the `context_limit` bubble arrives in STORY-013. At the storage layer `kind` is an unconstrained `TEXT`, so the AC 2 fixture can write a `context_limit` row today and prove `assemble` ignores it — which is the point: `assemble` filters on `kind == "assistant"`, so it is closed over kinds that do not exist yet, and STORY-013 needs no change here.
7. **Two existing AST architecture tests already constrain this file, and both are satisfied by the design above — but only if it is written exactly this way.** `tests/test_chat_sessions.py:1352`, `test_no_module_outside_the_service_branches_on_chat_history_enabled`, walks the AST of **every** module under `app/` and `chat_ui/`: a single mention of `CHAT_HISTORY_ENABLED` in `chat_history.py` fails it. `tests/test_chat_sessions.py:1225`, `test_no_module_outside_the_service_calls_the_store_session_functions`, fails any module outside `chat_sessions` that calls the store's session/message functions: `assemble` must go through `chat_sessions.messages_for` and must never touch `database.list_chat_messages`. So the two "do not re-check" rules in the story's Technical Notes are not merely advice — they are already enforced, and an implementer who "helpfully" adds a flag check will see a failure in a test module they never opened. Both are cited in Task 1 so the failure is predicted rather than discovered.
8. **No production code references the module yet, and the tests have every helper this story needs.** `grep` for `assemble(` returns zero hits repo-wide, and the only `chat_history` reference in production is the forward-looking comment at `app/db/models.py:284` describing `fit`'s count. `tests/conftest.py:197` gives `temp_db` (schema built); `tests/test_chat_sessions.py:105-114` seeds two *real* users (`ana`, `bob`) so a foreign id is a foreign id that exists; `:552-561` is `_stored(...)`, `:563-566` `_seeded_session(...)`, `:1059-1067` `_identity(...)`. Most valuable of all, `:1070-1090` defines a `_Tripwire` whose `__getattr__` raises, and `:1253-1263` the `history_off` fixture that installs it over `chat_sessions.database` alongside the flag — so "history off issued no statement" is *asserted*, not inferred from an empty list. `tests/test_chat_history.py` seeds its own copies of the small helpers rather than importing across test modules, matching how the suite is organized.

There is no linter or formatter in this repo. "Validate" means pytest against the local libSQL dev server (`tests/conftest.py:132-152`). Per the recorded libSQL note, **mass fixture errors mean restart the dev-server container, not bisect the code**.

## User Story

As an **end user**
I want my chat history rebuilt from the exchanges that actually got an answer, and trimmed from the oldest end when it is too long
So that a refused turn never re-enters context and a long chat still sends.

## Story Reference

- Story file: `.agents/stories/PRD-010-multi-turn-pipeline/STORY-011-chat-history-assemble-and-fit.md`
- PRD: `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md` — Sections 4 (History), 5 (stories 1–3), 6.4 (D3, D4, D5), 6.5 (D2), 7 (F7, F8), 9.1, 10, 11
- Depends on: STORY-001 (`done`, `a41155f`) — supplies `Message`
- Blocks: STORY-012 (`ChatState` calls `assemble` via `run_in_pipeline`, then `fit`)
- Precedent: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-001-message-model-and-normalization.plan.md` (a new pure module, imported only by its tests)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (new service module + new test module; no existing file changes) |
| Complexity | MEDIUM |
| Systems Affected | `app/services/chat_history.py` (new), `tests/test_chat_history.py` (new) |
| Story | STORY-011 |
| PRD | PRD-010 |
| Epic Branch | `epic/PRD-010-multi-turn-pipeline` (commit directly on this branch) |

---

## Skills In Use

I listed `.agents/skills/` in full. It holds exactly one skill:

| Skill | Applies? | Reason |
|-------|----------|--------|
| `frontend-design` | **No** | Its `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story adds one backend service module and one test module, imports nothing from `chat_ui/`, and renders nothing. STORY-013 owns the footer that displays `fit`'s count. |

The story's `skills:` frontmatter is `[]` and its Technical Notes end with "Skills: none applicable." **No skill constrains any task below.**

---

## Patterns to Follow

### Module docstring: name the PRD rule the module holds, and what it deliberately is not

```python
# SOURCE: app/services/chat_sessions.py:1-43 (abridged)
"""Whose row this is, and whether history is on at all -- in one place.

PRD-008 Section 6 names this module and what it holds, verbatim: ...

Two rules live here and nowhere else. ...

What this module is *not* is an authorization check. `authz.py` answers what a
role may do; this answers whose row this is. ...

It imports nothing from `chat_ui/`. The dependency runs one way in this
repository -- `chat_ui/chat_ui/state.py` imports `app.services`, never the
reverse ...
"""
```

### Pure module: no I/O, no settings, no pydantic, stated as an intent

```python
# SOURCE: app/models/messages.py:1-9
"""The one internal message shape (PRD-010 Section 6.2).
...
Pure on purpose: no I/O, no settings, no pydantic, no `app` import. The
pipeline (STORY-004/007), chat history (STORY-011) and PRD-011..014 build on
this module; PRD-014 is the first ingress that calls the normalizer.
"""
```

`chat_history.py` is *half* pure: `assemble` does one read, `fit` does none. The docstring says which is which, because STORY-012 calls one through `run_in_pipeline` and the other inline on the event loop.

### Limit arithmetic and strictness, to be mirrored exactly

```python
# SOURCE: app/services/query_pipeline.py:86-97
    The comparison is strict `>`: a conversation exactly at the maximum is
    within the limit, not over it.
    """
    message_count = len(messages)
    if message_count > settings.CONTEXT_MAX_MESSAGES:
        return "messages", settings.CONTEXT_MAX_MESSAGES, message_count

    character_count = sum(len(message.content) for message in messages)
    if character_count > settings.CONTEXT_MAX_CHARACTERS:
        return "characters", settings.CONTEXT_MAX_CHARACTERS, character_count
```

### Provisional/decision-bearing docstring: say which PRD decision, and who replaces it

```python
# SOURCE: app/services/query_pipeline.py:60-67
def _inspection_target(messages: Sequence[Message]) -> str:
    """PROVISIONAL (PRD-010 D6): the last user turn. PRD-011 replaces this.

    Sufficient for chat history: every earlier user turn was itself the last
    user turn of a send that already passed inspection (D4). Not sufficient
    for caller-supplied history -- no ingress in this PRD accepts one.
    """
```

### Service exception: declared in the module, wrapping the layer below

```python
# SOURCE: app/services/chat_sessions.py:54-63
class ChatSessionError(Exception):
    """A session or transcript operation failed at the storage layer.

    The same move `app/services/duplicate_checker.py` makes with
    `DuplicateCheckError`: a `StorageError` is a fact about the database, and
    letting it travel into `ChatState` would make the caller import
    `app.db.errors` to catch it ...
    """
```

`chat_history` declares **no** exception of its own for storage: `assemble` lets `chat_sessions.ChatSessionError` propagate unchanged, because re-wrapping it would make `ChatState` catch two names for one fact. The only exception `fit` raises is a `ValueError` for a structurally impossible history (Fact 4).

### Tests: parametrized so a failure names the case, with the vacuity trap closed

```python
# SOURCE: tests/test_chat_sessions.py:689-698
@pytest.mark.parametrize("kind,metadata", SEVEN_KINDS, ids=[k for k, _ in SEVEN_KINDS])
def test_each_of_the_seven_kinds_round_trips_unchanged(temp_db, kind, metadata):
    """AC 7 and AC 8.

    Parametrized rather than looped so that a failure names the kind that broke.
    A single representative kind would pass while `pattern`, `required_permission`
    or `first_query_at` were silently dropped ...
    """
```

```python
# SOURCE: tests/test_chat_sessions.py:645-652
def test_twenty_messages_appended_in_one_second_read_back_in_order(temp_db):
    """AC 4. Twenty messages sharing one `created_at` to the second.

    This is the case a timestamp sort gets wrong, and the reason AC 3 is written
    as a statement inspection *and* a behavioural test: a sort on a tied column
    is not deterministic, so a passing run proves nothing on its own.
    """
```

### Purity asserted structurally — the two idioms already in this suite

```python
# SOURCE: tests/test_dedup_key.py:212-229 (abridged) -- tripwire + source scan
class _Untouchable:
    def __getattr__(self, name):
        raise AssertionError(...)
...
assert "settings" not in source
assert "datetime" not in source
```

```python
# SOURCE: tests/test_messages.py:345-352 -- AST walk over the module's names
assert not names & {"settings", "open", "httpx", "pydantic", "log_query", "redact"}
```

Task 9 uses the AST walk (it generalizes to the Reflex/`chat_ui` check in the same pass); Task 6 uses the behavioural counterpart for `fit`'s limits.

### Test fixtures and helpers available

```python
# SOURCE: tests/test_chat_sessions.py:105-114
def _seed_users() -> None:
    """Two real users, so a foreign id in a test is a foreign id that exists."""
    insert_user(User(user_id="ana", role="user", token_hash="hash-ana"))
    insert_user(User(user_id="bob", role="user", token_hash="hash-bob"))

# SOURCE: tests/test_chat_sessions.py:1059-1067
    return Identity(user_id=user_id, role="user")

# SOURCE: tests/test_chat_sessions.py:1253-1263 -- the flag AND a tripwire, together
@pytest.fixture
def history_off(monkeypatch):
    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)
    monkeypatch.setattr(chat_sessions, "database", _Tripwire())
```

`temp_db` comes from `tests/conftest.py:196-204` (schema built); `_never_the_configured_database` (`:155`) is autouse and resets every table before every test, so no teardown is needed. `_stored(...)` is at `tests/test_chat_sessions.py:552-561` and `_seeded_session(...)` at `:563-566`.

### Signature pinning, the house form

```python
# SOURCE: tests/test_dedup_key.py:57
assert list(inspect.signature(dedup_key).parameters) == ["user_id", "turns"]
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/chat_history.py` | CREATE | `assemble()` (one read, assistant rows only) and `fit()` (pure, drops oldest whole exchanges) |
| `tests/test_chat_history.py` | CREATE | All five ACs, plus the module-shape and limit-pairing invariants |

No existing file is modified. `app/config.py` is **not** touched: `fit` takes its limits as arguments (story Technical Notes), and `assemble` must not read `settings.CONTEXT_MAX_*` at all — STORY-012 passes `settings.CONTEXT_MAX_MESSAGES` / `settings.CONTEXT_MAX_CHARACTERS` in from the call site.

---

## Tasks

Execute in order. Tasks 1–2 are production code; Tasks 3–9 are tests; Task 10 is whole-suite verification.

### Task 1: Create the module with `assemble`

- **File**: `app/services/chat_history.py`
- **Action**: CREATE
- **Implement**:
  1. Module docstring in the `chat_sessions.py` voice (`:1-43`). It must state, in prose:
     - What the module holds: PRD-010 Section 6.4's two facts, and that they are *why* `assemble` reads only `kind == "assistant"` rows rather than pairing `user` rows with the rows after them. Quote fact 1 in substance: the first user bubble of a new chat is never persisted (`_append_and_persist` runs with `session_id == ""` before `chat_sessions.create`), so rebuilding pairs from `user` rows would lose every session's first question.
     - **D4 holds by construction, not by exclusion.** `duplicate`, `injection`, `forbidden`, `upstream_error`, `internal_error` and `context_limit` rows are never *read*, and neither are the user bubbles that preceded them. Say explicitly that there is no deny-list of kinds to keep in sync, which is why a kind added later (STORY-013's `context_limit`) needs no change in this file.
     - **This module does not redact (D5).** Stored `prompt` is raw; the pipeline redacts every message on every send (STORY-007, PRD 6.4). Redacting here would double-mask and would hash a redacted string into `dedup_key`, which PRD 9.2 forbids.
     - **This module does not check ownership and does not read the flag.** `chat_sessions.messages_for` already returns `[]` for history-off, unknown and foreign sessions (PRD 9.1); a second check here would be a second place to get it wrong. Name the two tests that already enforce this (Fact 7), so the constraint is visible to whoever next edits the file: `tests/test_chat_sessions.py:1352` fails on any mention of `CHAT_HISTORY_ENABLED` under `app/` or `chat_ui/`, and `:1225` fails any module outside the service that calls the store's session functions — so `database.list_chat_messages` is not an option even as an optimization.
     - **`identity.role` is never read.** `chat_sessions.py:29-36` states the rule for the service; `assemble` takes the whole `Identity` and passes it straight down, which is also what `tests/test_chat_sessions.py:1190` (`identity` first and undefaulted) expects of a service function.
     - **It imports nothing from `chat_ui/` and nothing from Reflex** (story Technical Notes), and `fit` reads no `settings`, so it is testable without them.
     - Which half is pure: `assemble` does one read and is sync (STORY-012 calls it through `run_in_pipeline`); `fit` is pure and is called inline.
  2. Imports, in the repo's order (stdlib, then `app.*`):
     ```python
     from typing import List, Sequence, Tuple

     from app.models.messages import Message
     from app.services import chat_sessions
     from app.services.identity import Identity
     ```
     Match `chat_sessions.py:45-51` for grouping. Import the module `chat_sessions`, not its function, so Task 5 can spy on the attribute.
  3. ```python
     def assemble(identity: Identity, session_id: str) -> List[Message]:
     ```
     Body:
     ```python
     history: List[Message] = []
     for row in chat_sessions.messages_for(identity, session_id):
         if row.kind != "assistant":
             continue
         if not row.prompt:
             continue
         history.append(Message("user", row.prompt))
         history.append(Message("assistant", row.content))
     return history
     ```
     Exactly one call to `messages_for`, and **no `sorted(...)`** — the read is already `ORDER BY id ASC` (`app/db/database.py:1778-1781`) and a re-sort here would hide a regression in that clause.
  4. Docstring for `assemble`:
     - One line: "This session's answered exchanges as a conversation, oldest first."
     - `[]` for history off, an unknown session and a foreign one — all three from `messages_for`, named as the single place that rule lives.
     - Why `row.prompt` and not the preceding `user` row (fact 1), with the STORY-012 consequence: send 2 of a brand-new chat still carries send 1.
     - Why a falsy `prompt` is skipped rather than emitting `Message("user", "")`: `prompt` is nullable (`app/db/models.py:165`) and an empty user turn is not a turn — it would make the last-user-turn inspection target (`_inspection_target`) and `dedup_key` see a blank prefix, and `fit` would count an exchange that carries nothing. Pre-PRD-008 rows and any future writer that omits `prompt` land here.
     - Why an assistant row with `content == ""` is **not** skipped: the user half is real, and dropping one message of a pair breaks alternation for every later turn. `content` is `NOT NULL` at the table (`:163`), so `""` is the only degenerate value possible.
     - That `ChatSessionError` propagates unchanged, and why (no second name for one fact).
     - That it does not redact, with the D5 pointer.
- **Mirror**: `app/services/chat_sessions.py:324-343` (the read + short-circuit contract it relies on), `app/models/messages.py:1-9` (purity statement), `app/services/query_pipeline.py:60-67` (decision-bearing docstring)
- **Validate**:
  ```bash
  python -c "import inspect, app.services.chat_history as h; src = inspect.getsource(h.assemble); assert src.count('messages_for') == 1, 'exactly one read'; assert 'sorted' not in src; assert 'CHAT_HISTORY_ENABLED' not in inspect.getsource(h); assert 'list_chat_messages' not in inspect.getsource(h); assert list(inspect.signature(h.assemble).parameters) == ['identity', 'session_id']; print('ok')"
  ```
  Then the two pre-existing architecture tests, which must stay green now that a new module exists under `app/`:
  ```bash
  pytest tests/test_chat_sessions.py -q -k "branches_on_chat_history_enabled or calls_the_store_session_functions or takes_an_identity_first or bare_user_id"
  ```

### Task 2: Add `fit`

- **File**: `app/services/chat_history.py`
- **Action**: UPDATE (same file, second function)
- **Implement**:
  1. ```python
     def fit(
         history: Sequence[Message],
         new_turn: Message,
         max_messages: int,
         max_characters: int,
     ) -> Tuple[List[Message], int]:
     ```
  2. Body:
     ```python
     if len(history) % 2:
         raise ValueError(
             "history must be whole exchanges (an even number of messages); "
             f"got {len(history)}"
         )

     kept = list(history)
     dropped = 0
     while True:
         candidate = kept + [new_turn]
         if len(candidate) <= max_messages and _characters(candidate) <= max_characters:
             return candidate, dropped
         if not kept:
             return [new_turn], dropped
         kept = kept[2:]
         dropped += 1
     ```
     with a module-private helper directly above `fit`:
     ```python
     def _characters(messages: Sequence[Message]) -> int:
         """The same count `query_pipeline._context_limit_exceeded` makes."""
         return sum(len(message.content) for message in messages)
     ```
     Points that must hold and be commented, not just written:
     - `<=`, mirroring the pipeline's strict `>` (Fact 3). A conversation exactly at a maximum fits.
     - `kept[2:]` drops the **oldest whole exchange**; nothing ever slices by one, which is what makes AC 4's "never splits a pair" structural.
     - `list(history)` copies, so `fit` never mutates a caller's list. `new_turn` is appended last on every path, so AC 4's "the new turn is always last" holds including the floor path.
     - The `if not kept` floor returns `([new_turn], dropped)`, and because each iteration drops exactly one exchange, `dropped == len(history) // 2` there — which is AC 5's stated return value, arrived at by the loop rather than by a special case. Do **not** write a separate `if _characters([new_turn]) > max_characters` branch: it would duplicate the arithmetic and could disagree with the loop.
     - The floor is also what a `max_messages` below 1 or a `max_characters` below the new turn's length hits, so `fit` never returns `[]` and never returns a conversation without its new turn. A caller that wants "refuse" gets it from the pipeline, which re-checks the limits (D2) and refuses `[new_turn]` when it is still over.
  3. Docstring for `fit`:
     - One line: "History plus the new turn, trimmed from the oldest end until it fits, and how many whole exchanges that cost."
     - The pairing with `_context_limit_exceeded`: same two counts, same expression, opposite strictness, so a fitted conversation is never refused for the limits it was fitted to — and the named test that pins it (Task 7).
     - Pure on purpose: limits are arguments, not `settings` reads, so the tests do not need `monkeypatch.setattr(settings, ...)` and STORY-012 owns the choice of limits (story Technical Notes).
     - The `ValueError` and why it is a `ValueError` and not a refusal: `assemble` cannot produce an odd history, so an odd one is a programming error at the call site — the same posture `run_conversation` takes with `InvalidConversationError` for an empty or non-user-final conversation. `[]` is even and legal.
     - `dropped` counts **exchanges**, not messages, because that is what STORY-013's footer says ("3 earlier exchanges were not sent to the model") and what STORY-010's `history_trimmed` column stores.
- **Mirror**: `app/services/query_pipeline.py:72-98` (the arithmetic and the strictness paragraph)
- **Validate**:
  ```bash
  python -c "
  from app.models.messages import Message
  from app.services.chat_history import fit
  h = [Message('user', 'a'), Message('assistant', 'b'), Message('user', 'c'), Message('assistant', 'd')]
  n = Message('user', 'e')
  assert fit(h, n, 100, 100) == (h + [n], 0)
  assert fit(h, n, 3, 100) == (h[2:] + [n], 1)
  assert fit(h, n, 100, 2) == ([n], 2)
  assert fit([], n, 100, 100) == ([n], 0)
  assert h == [Message('user','a'), Message('assistant','b'), Message('user','c'), Message('assistant','d')]
  try:
      fit([Message('user','a')], n, 100, 100)
  except ValueError as exc:
      assert 'even' in str(exc)
  else:
      raise AssertionError('odd history must raise')
  print('ok')
  "
  ```

### Task 3: `assemble` builds pairs from assistant rows, in `id` order (AC 1)

- **File**: `tests/test_chat_history.py`
- **Action**: CREATE
- **Implement**: module header and shared helpers first, then the AC 1 block.
  - Header: module docstring naming the story and the PRD sections, then the env bootstrap prologue that every suite touching `app` imports uses (`os.environ.setdefault("OPENROUTER_API_KEY", "test-key")`, `os.environ.setdefault("ADMIN_TOKEN", "test-token")`, mirroring `tests/test_dedup_key.py:11-14`), then imports (`pytest`, `Message`, `chat_history`, `chat_sessions`, `Identity`, `settings`, and from `app.db.database` the `insert_user` / `append_chat_message` / `create_chat_session` names the helpers need). Section-comment banners in the `tests/test_chat_sessions.py:634-687` style, one per AC.
  - Local helpers, seeded per test rather than imported across test modules:
    - `_seed_users()` — copy of `tests/test_chat_sessions.py:105-114` (`ana`, `bob`, both real), with its reason restated in one line.
    - `_identity(user_id="ana")` → `Identity(user_id=user_id, role="user")` (`:1059-1067`).
    - `_session(owner="ana")` → creates a session through `chat_sessions.create` and returns its id.
    - `_row(session_id, kind="assistant", *, prompt=None, content="", **metadata)` → writes one `chat_messages` row through `append_chat_message` and returns the new row id.
    - `_exchange(session_id, question, answer)` → one assistant row with `prompt=question, content=answer`.
  - Tests:
    - `test_assemble_returns_one_user_assistant_pair_per_assistant_row`: three exchanges → six messages, `[("user", q1), ("assistant", a1), ("user", q2), …]` asserted as a list of `(role, content)` tuples so the *order within* the pair is pinned, not just the multiset.
    - `test_assemble_reads_the_transcript_in_id_order_not_by_timestamp`: twenty exchanges all written with the same `created_at` to the second, contents `f"q{index:02d}"` / `f"a{index:02d}"`. Mirrors `tests/test_chat_sessions.py:645-667` and its reasoning: a sort on a tied column is not deterministic, so ordering needs the tie to be real. Assert the full forty-message sequence.
    - `test_assemble_emits_exactly_two_messages_per_answered_exchange`: `len(assemble(...)) == 2 * exchanges` for 0, 1, 5 (parametrized), which is the invariant `fit`'s `ValueError` depends on.
- **Mirror**: `tests/test_chat_sessions.py:105-113`, `:645-667`, `:1067`
- **Validate**: `pytest tests/test_chat_history.py -q -k "pair or id_order or exactly_two"`

### Task 4: Nothing but answered exchanges contributes, and the first exchange survives (AC 2)

- **File**: `tests/test_chat_history.py`
- **Action**: UPDATE
- **Implement**:
  - `test_no_unanswered_kind_contributes_a_message` — parametrized over the seven non-assistant kinds **plus `context_limit`**:
    ```python
    UNANSWERED_KINDS = (
        ("user", {"prompt": "what is the retention policy?"}),
        ("duplicate", {"first_query_at": "2026-09-03T09:58:00Z"}),
        ("injection", {"pattern": "ignore previous instructions"}),
        ("forbidden", {"required_permission": "query:submit"}),
        ("upstream_error", {"detail": "502 from openrouter"}),
        ("internal_error", {"detail": "unhandled in run_query"}),
        ("context_limit", {"detail": "context limit: characters 250000 > 200000"}),
    )
    ```
    Comment that `context_limit` is written directly as a `TEXT` kind because STORY-013 has not added the bubble yet, and that `assemble` filters on `kind == "assistant"` rather than on a deny-list, so it is already closed over kinds that do not exist (Fact 6). Each case writes the noise row **with a `prompt` set** where the kind carries one, so the test cannot pass merely because the fixture left `prompt` empty.
    **Vacuity trap closed**: each case sandwiches the noise row between two real exchanges and asserts the result is *exactly* those two exchanges' four messages. A test that only asserted "the noise content is absent" would pass against an `assemble` that returned `[]` for everything.
  - `test_a_transcript_of_every_unanswered_kind_assembles_to_nothing`: all seven noise kinds in one transcript, no assistant row → `[]`. Paired with the sandwich test above, this is the "all" half of AC 2.
  - `test_the_first_exchange_survives_a_missing_first_user_bubble` (PRD 6.4 fact 1): write the transcript the way the app really writes a new chat — **no** `user` row for exchange 1, one `assistant` row carrying `prompt="first question"`, then a normal `user` + `assistant` pair for exchange 2. Assert four messages, first one `Message("user", "first question")`. Docstring cites PRD 6.4 fact 1 and PRD 11's functional requirement "the first exchange of a new chat appears in the history of send 2 (built from the assistant row's `prompt`, not a missing user row)".
  - `test_assemble_does_not_redact` (D5, story Technical Notes): an assistant row whose `prompt` holds `jane@corp.com` comes back **verbatim**; assert the raw string is present and `<EMAIL_ADDRESS>` is not. Docstring: D5 is the pipeline's (STORY-007), and redacting here would also feed a redacted string into `dedup_key`, which PRD 9.2 forbids.
- **Mirror**: `tests/test_chat_sessions.py:80-88` (the kinds tuple), `:689-698` (parametrize + why-not-one-case docstring)
- **Validate**: `pytest tests/test_chat_history.py -q -k "unanswered or first_exchange or not_redact"`

### Task 5: The three empty cases, the skipped prompt, and the single read (AC 3)

- **File**: `tests/test_chat_history.py`
- **Action**: UPDATE
- **Implement**:
  - `test_assemble_is_empty_when_history_is_off`: seed a session with two exchanges, then apply a local copy of the `history_off` fixture (`tests/test_chat_sessions.py:1253-1263`) -- which sets the flag **and** installs the `_Tripwire` (`:1070-1090`) over `chat_sessions.database`, so a read that got issued raises instead of returning rows. Assert `[]`, and in the same test assert the flag-on call on that session is non-empty. Asserting the empty list alone would pass against a module that read the transcript and threw it away; the tripwire makes it prove **no statement was issued**, which is the property PRD 7 F8 relies on when it says the off path costs "no extra read". Docstring: the flag is read in `chat_sessions` and nowhere else; `chat_history` must not branch on it (`app/services/chat_sessions.py:19-27`).
  - `test_assemble_is_empty_for_a_foreign_session`: ana's session, bob's identity → `[]`, with the assertion that ana's own `assemble` on the same session is **non-empty** in the same test. That is the vacuity trap: without it the test passes against a broken read that returns nothing for anyone. Docstring cites PRD 9.1 — a tampered `active_session_id` cannot pull another user's transcript into context.
  - `test_assemble_is_empty_for_an_unknown_session`: a syntactically valid id that was never created → `[]`.
  - `test_assemble_skips_an_assistant_row_without_a_usable_prompt` — parametrized over `None` and `""`: one good exchange, one assistant row with the unusable `prompt`, one good exchange → exactly four messages, and assert no message has `content == ""` on the `user` side. Docstring: `prompt` is nullable (`app/db/models.py:165`); an empty user turn would blank `_inspection_target` and the `dedup_key` prefix.
  - `test_assemble_keeps_an_exchange_whose_answer_is_empty`: assistant row with `prompt="q"`, `content=""` → both messages present, `Message("assistant", "")` second. The deliberate asymmetry with the test above, named so a future reader does not "fix" it.
  - `test_assemble_makes_exactly_one_transcript_read`: monkeypatch `chat_history.chat_sessions.messages_for` with a counting spy returning a fixed two-row transcript; assert the counter is `1` and the result has two messages. Docstring: story Technical Notes ("does one read"); STORY-012 runs this inside `run_in_pipeline` and PRD 11 budgets "one `messages_for` read" per send.
  - `test_assemble_propagates_a_storage_failure`: spy raises `chat_sessions.ChatSessionError("boom")`; `pytest.raises(chat_sessions.ChatSessionError)`. Docstring: no second exception name for one fact; STORY-012's degraded arm catches this type.
- **Mirror**: `tests/test_chat_sessions.py:1595-1680` (foreign/unknown/admin sameness tests), `:1307` (the `("messages_for", [])` flag-off table)
- **Validate**: `pytest tests/test_chat_history.py -q -k "empty or skips or answer_is_empty or one_transcript_read or propagates"`

### Task 6: `fit`'s stated behaviours (AC 4 and AC 5, the non-random half)

- **File**: `tests/test_chat_history.py`
- **Action**: UPDATE
- **Implement**: a `_history(n)` helper building `n` exchanges as `[Message("user", f"q{i}"), Message("assistant", f"a{i}"), …]`, then:
  - `test_fit_returns_everything_and_zero_when_it_all_fits`: `fit(h, n, 100, 100_000) == (h + [n], 0)`, and the returned list is a **different object** from `h` (`result is not h`).
  - `test_fit_drops_the_oldest_whole_exchange_for_the_message_limit` — parametrized over a table of `(exchanges, max_messages, expected_kept_exchanges, expected_dropped)` covering an even and an odd `max_messages` (e.g. `max_messages=5` keeps two exchanges + the new turn; `max_messages=6` also keeps two, because the total is always odd). The odd/even row is the one that catches an off-by-one in the `<=`.
  - `test_fit_drops_the_oldest_whole_exchange_for_the_character_limit`: exchanges with known lengths, a `max_characters` that admits exactly the last two plus the new turn.
  - `test_fit_never_splits_an_exchange`: for every `max_messages` in `range(1, 2 * 5 + 2)` over a five-exchange history, the output minus its last element has **even** length and alternates `user, assistant, user, assistant, …`. This is AC 4's "never splits a pair" as a swept property rather than one example.
  - `test_the_new_turn_is_always_last` — swept over the same range plus tight `max_characters` values, including the floor.
  - `test_fit_reports_the_limit_it_was_given_not_the_settings`: `monkeypatch.setattr(settings, "CONTEXT_MAX_MESSAGES", 1)` and `CONTEXT_MAX_CHARACTERS` to `1`, then a `fit(..., 100, 100_000)` that fits everything and returns `0`. Proves `fit` reads no settings behaviourally, backing Task 9's static check.
  - `test_fit_returns_only_the_new_turn_when_it_alone_exceeds_the_characters` — parametrized over `1, 2, 5` exchanges: `fit(h, big_turn, 100, small) == ([big_turn], len(h) // 2)`. The `// 2` is asserted as the literal expression from AC 5.
  - `test_fit_returns_only_the_new_turn_when_the_message_limit_admits_nothing_else`: `max_messages=1` → `([new_turn], len(h) // 2)`. Docstring: the same floor, reached by the other limit; `fit` never returns `[]`, and refusal is the pipeline's job (D2).
  - `test_fit_does_not_mutate_its_input` — a deep equality check on `h` after a trimming call, plus `fit([], n, …)` on an empty history returning `([n], 0)`.
  - `test_fit_rejects_a_history_that_is_not_whole_exchanges` — parametrized over lengths 1, 3, 5: `pytest.raises(ValueError, match="even")`. Docstring: `assemble` cannot produce one, so this is a call-site programming error, the same posture `run_conversation` takes with `InvalidConversationError`; `[]` is legal and covered above.
- **Mirror**: `tests/test_query_pipeline_context_limit.py` (limit-table parametrization), `tests/test_chat_sessions.py:689-698` (parametrize rationale)
- **Validate**: `pytest tests/test_chat_history.py -q -k "fit"`

### Task 7: Pin `fit` against the pipeline's limit check

- **File**: `tests/test_chat_history.py`
- **Action**: UPDATE
- **Implement**: `test_a_fitted_conversation_is_never_refused_for_the_limits_it_was_fitted_to`. Import the private `_context_limit_exceeded` from `app.services.query_pipeline`. For a table of `(exchanges, max_messages, max_characters)` cases — including ones that trim on messages, on characters, on both, and the floor — call `fit`, `monkeypatch.setattr(settings, "CONTEXT_MAX_MESSAGES", max_messages)` and `CONTEXT_MAX_CHARACTERS` to `max_characters`, then assert `_context_limit_exceeded(fitted) is None`, **except** in the floor case, where the new turn alone is over and the assertion flips to a non-`None` naming `"characters"` — which is AC 5's "so the pipeline refuses it (D2)", asserted rather than asserted-about.
  Docstring: why this test reaching into a private function is the right call — the two counts and their strictness are one contract split across two modules (Fact 3), and nothing else in the suite would notice if `fit` counted `len(content)` while the pipeline counted something else. Name the failure it prevents: a context-limit bubble on a send that was trimmed to fit.
- **Mirror**: `app/services/query_pipeline.py:72-98`
- **Validate**: `pytest tests/test_chat_history.py -q -k "never_refused"`

### Task 8: Randomized property tests for `fit` (AC 5, "fit is pure")

- **File**: `tests/test_chat_history.py`
- **Action**: UPDATE
- **Implement**: a `_random_case(seed)` helper using `random.Random(seed)` to build an even-length history of 0–30 messages with contents of random length 0–50, a random `new_turn`, and random `max_messages` in 1–40 / `max_characters` in 1–600. Then `@pytest.mark.parametrize("seed", range(200))` over one test that asserts all five properties for every case, each with its own message so a failure says which property broke:
  1. **Fits or is the floor**: either both limits hold for the output, or the output is exactly `[new_turn]`.
  2. **The new turn is last**, always.
  3. **Order preserved**: the output minus its last element is a **contiguous suffix** of `history` (`history[len(history) - (len(out) - 1):] == out[:-1]`), which pins both "oldest end dropped" and "nothing reordered" in one assertion.
  4. **Whole exchanges only**: `(len(out) - 1) % 2 == 0`.
  5. **The count is exact**: `dropped == (len(history) - (len(out) - 1)) // 2` when the output kept a suffix, and `dropped == len(history) // 2` on the floor path.
  Plus `test_fit_is_deterministic_for_a_given_case`: the same random case called twice returns equal results, and the input history is unchanged after both calls.
  Docstring must say why `random.Random` and not `hypothesis`: there is no property-testing library in `requirements.txt` and PRD Section 8's stack does not add one (Fact 5); the seed is parametrized, not drawn at collection time, so the suite is deterministic and a failure reproduces with `-k "seed<N>"` — an unseeded `random` would make this test the flakiest thing in the repo.
- **Validate**: `pytest tests/test_chat_history.py -q -k "property or deterministic"` (all 200 cases green, and the run is repeatable — run it twice and diff the summary line)

### Task 9: Module-shape invariants

- **File**: `tests/test_chat_history.py`
- **Action**: UPDATE
- **Implement**:
  - `test_the_module_exports_exactly_assemble_and_fit`: the public names (`not name.startswith("_")` and defined in this module) are exactly `{"assemble", "fit"}`, so a helper does not become API by accident.
  - `test_chat_history_imports_nothing_from_reflex_or_the_chat_ui`: `ast`-walk `inspect.getsource(chat_history)` for `Import` / `ImportFrom` and assert no module name starts with `reflex` or `chat_ui` (story Technical Notes). Mirror the AST-inspection style already used in `tests/test_chat_sessions.py:91-102`.
  - `test_assemble_and_fit_never_read_the_context_settings`: AST-walk the module's names in the `tests/test_messages.py:345-352` form and assert `not names & {"settings", "CONTEXT_MAX_MESSAGES", "CONTEXT_MAX_CHARACTERS", "CHAT_HISTORY_ENABLED", "database", "httpx", "log_query", "redact"}`; and assert `"app.config"` is not imported. Docstring: story Technical Notes -- `assemble` must not read `settings.CONTEXT_MAX_*`, and `fit` takes its limits as arguments so it stays testable without settings. The `CHAT_HISTORY_ENABLED` and `database` entries duplicate what `tests/test_chat_sessions.py:1352` and `:1225` already enforce repo-wide (Fact 7); keeping them here too means a failure names *this* module rather than a sessions test, and the docstring says so rather than leaving the overlap to look accidental. Complements Task 6's behavioural version.
  - `test_no_production_module_imports_chat_history_yet`: grep the source tree (`app/`, `chat_ui/`, `scripts/`) for `chat_history` and assert the only hits are `app/services/chat_history.py` itself and comments. Docstring: STORY-012 is the first caller; this test is **deleted by STORY-012**, and saying so here is what keeps it from being read as a prohibition. Mirrors STORY-001's "`messages.py` is imported only by its tests" criterion.
- **Mirror**: `tests/test_messages.py:345-352` (AST name walk), `tests/test_dedup_key.py:212-229` (tripwire + source scan), `tests/test_chat_sessions.py:91-102` (`_statements_of`), `tests/test_chat_sessions.py:1225,1352` (the repo-wide architecture walks this mirrors)
- **Validate**: `pytest tests/test_chat_history.py -q -k "module or imports or never_read or no_production"`

### Task 10: Whole-suite verification and the commit

- **File**: — (verification only)
- **Action**: VERIFY
- **Implement**:
  1. `pytest tests/test_chat_history.py -q` — the new module green on its own.
  2. `pytest -q` — the **full** suite. Nothing existing should change: this story creates two files and edits none. If the run shows mass fixture errors, restart the libSQL dev-server container and re-run before reading any failure as a code defect.
  3. Confirm the diff is exactly two new files: `git status --short` shows only `?? app/services/chat_history.py` and `?? tests/test_chat_history.py`.
  4. Commit on `epic/PRD-010-multi-turn-pipeline` (no per-story branch), message in the epic's style: `feat(chat): STORY-011 chat_history.assemble and fit`.
- **Validate**: `pytest -q` green; `git status --short` shows no modified pre-existing file

---

## End-to-End Tests

There is no ingress for this module yet — STORY-012 wires it into `ChatState` — so the end-to-end checks here are at the module boundary, driven against a real transcript in the dev database:

- [ ] Seed a session as `ana` with three exchanges through the real write path (`chat_sessions.append_message`), then `assemble(_identity("ana"), session_id)` → six messages, oldest first, `[("user", q1), ("assistant", a1), …]`
- [ ] Insert a `duplicate` and an `injection` row between exchanges 2 and 3, re-assemble → still six messages, unchanged (PRD 5 story 3: a refused prompt cannot come back in through history)
- [ ] `assemble` for `bob` on ana's session → `[]`, while ana's own call on the same session is non-empty in the same run
- [ ] `fit(assembled, Message("user", "and shorter"), 5, 100_000)` → two exchanges kept plus the new turn, `dropped == 1`; the new turn is last
- [ ] With `settings.CONTEXT_MAX_MESSAGES = 5` and `CONTEXT_MAX_CHARACTERS` generous, `query_pipeline._context_limit_exceeded(fitted)` is `None` — the fitted conversation would not be refused
- [ ] `fit(assembled, Message("user", "x" * 10_000), 100, 5_000)` → `([that turn], 3)`, and with the same limits on `settings` the pipeline's check **does** report `"characters"` (D2 refusal path)
- [ ] With `CHAT_HISTORY_ENABLED=false` in the environment, `assemble` on the same seeded session → `[]`

## Validation

```bash
# the new module
pytest tests/test_chat_history.py -q

# the neighbours whose contracts this story leans on, unchanged
pytest tests/test_chat_sessions.py tests/test_messages.py tests/test_query_pipeline_context_limit.py -q

# everything
pytest -q

# the diff is two new files and nothing else
git status --short
```

Mass fixture errors across unrelated modules mean the libSQL dev server has degraded under repeated suites — restart the container and re-run before bisecting.

---

## Acceptance Criteria

(Copied from story `STORY-011`)

- [ ] Given the new `app/services/chat_history.py`, when `assemble(identity, session_id)` reads a transcript through `chat_sessions.messages_for`, then it returns `[Message("user", row.prompt), Message("assistant", row.content), …]` for `kind == "assistant"` rows only, in `id` order. *(Tasks 1, 3)*
- [ ] Given a transcript containing `user`, `duplicate`, `injection`, `forbidden`, `upstream_error` and `internal_error` rows (and a `context_limit` row), when assembled, then none of them contributes a message. A session whose **first** user bubble was never persisted still yields its first exchange (built from the assistant row's `prompt`, PRD 6.4 fact 1). *(Task 4)*
- [ ] Given history off, a foreign session or an unknown session, when `assemble` runs, then it returns `[]`. An assistant row with `prompt` `NULL` or empty is skipped rather than emitting an empty user turn. *(Task 5)*
- [ ] Given `fit(history, new_turn, max_messages, max_characters)`, when history plus the new turn exceeds either limit, then it drops the **oldest whole exchange** repeatedly until both hold and returns `(messages, dropped_count)`. It never splits a pair, and the new turn is always last. When everything fits, it returns `(history + [new_turn], 0)`. *(Tasks 2, 6, 8)*
- [ ] Given a new turn that alone exceeds `max_characters`, when `fit` runs, then it returns `([new_turn], len(history) // 2)`, so the pipeline refuses it (D2). `fit` is pure (property tests over random histories: output length ≤ limit or only the new turn; order preserved; count equals exchanges removed). *(Tasks 2, 6, 7, 8)*
- [ ] All tasks completed
- [ ] Full test suite green (`pytest -q`)
- [ ] No pre-existing file modified — the diff is two new files
- [ ] `assemble` makes exactly one `messages_for` call, re-sorts nothing and re-checks no ownership
- [ ] `fit` reads no `settings` and mutates no input
- [ ] No Reflex or `chat_ui` import in `app/services/chat_history.py`
- [ ] The two pre-existing repo-wide architecture tests still pass with a new module under `app/`: `tests/test_chat_sessions.py:1352` (no `CHAT_HISTORY_ENABLED` outside the service) and `:1225` (no store session call outside the service)
- [ ] Follows existing patterns (module docstring names its PRD rule; parametrized tests with the vacuity trap closed)

---

## Risks + Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| R1 | **`fit`'s `ValueError` on an odd history is a plan decision the story does not state.** A future caller that legitimately holds a half exchange would now crash instead of degrading. | The only producer is `assemble`, which emits pairs by construction (Task 3 asserts `len % 2 == 0` for 0/1/5 exchanges). AC 4 forbids splitting a pair and AC 5's `len(history) // 2` is only exact on pair-shaped input, so silence here would mean an orphan message paired with the new turn — a *wrong* conversation instead of a loud one. Alternative considered and rejected: document odd input as undefined, which leaves the guarantee resting on caller discipline. Task 6 pins the message text; STORY-012 must pass `assemble`'s output through unchanged. |
| R2 | **Drift between `fit`'s counting and `query_pipeline._context_limit_exceeded`** would refuse sends that were trimmed to fit — the worst possible user-facing symptom, since trimming is what was supposed to prevent the refusal. | Task 7 asserts `_context_limit_exceeded(fitted) is None` across a table of trimming cases, and `fit` uses the identical `sum(len(message.content) for message in …)` expression with `<=` against the pipeline's `>`. Both strictnesses are commented with each other's file reference. |
| R3 | **A vacuous AC 2 or AC 3 test.** "The blocked content is absent" passes against an `assemble` that returns `[]` for everything, and "foreign → `[]`" passes against a read that is broken for everyone. | Every exclusion test sandwiches the excluded row between two real exchanges and asserts the exact surviving four messages; the foreign-session test asserts ana's own non-empty result in the same test. Called out explicitly in Tasks 4 and 5, following STORY-009's "both vacuity traps closed". |
| R4 | **No `hypothesis`, so AC 5's property tests could become flaky or shallow.** | Seeds are parametrized (`range(200)`), not drawn at collection, so the suite is deterministic and a failure reproduces by seed; the "order preserved" property is asserted as a **contiguous-suffix** identity rather than a weaker containment check, which is what actually pins "oldest end dropped". Adding a dependency is out of PRD Section 8's stack. |
| R5 | **`assemble` re-sorting or re-checking ownership** would look defensive and would hide regressions in `list_chat_messages`' `ORDER BY id ASC` and its `user_id` scope. | Task 1's validate command greps the source for `sorted` and for a second `messages_for`; Task 3 asserts order behaviourally against twenty rows with a tied `created_at`; Task 5 proves the foreign case through `messages_for` rather than a local check. |
| R6 | **An assistant row with an empty `content` treated inconsistently** with an empty `prompt`, by a later reader "fixing" the asymmetry. | Both branches are commented with their reason in Task 1, and the two tests in Task 5 are named for the asymmetry (`…skips_an_assistant_row_without_a_usable_prompt` / `…keeps_an_exchange_whose_answer_is_empty`). |
| R7 | **libSQL dev-server degradation** during repeated suite runs reads as a code defect and sends the implementer bisecting. | Stated in Validation and in Task 10 step 2: mass fixture errors mean restart the container, then re-run. |
| R8 | **`test_no_production_module_imports_chat_history_yet` becomes a false prohibition** once STORY-012 lands. | Its docstring says STORY-012 deletes it, and STORY-012's plan should name that deletion as a task step. |
| R9 | **A new module under `app/` silently trips a repo-wide architecture test** the implementer never opened — `tests/test_chat_sessions.py:1352` walks every `app/` and `chat_ui/` module for `CHAT_HISTORY_ENABLED`, and `:1225` for direct store session calls. A flag check added "to be safe" fails in a sessions test with no obvious connection to this story. | Both are named in Task 1's docstring requirements, asserted by Task 1's second validate command *before* any new test exists, and re-asserted from this module's side in Task 9 so the failure names `chat_history`. Fact 7 explains the coupling. |

## Dependency Order

1. Task 1 (`assemble`) — nothing depends on `fit`
2. Task 2 (`fit`) — independent of Task 1, but the module must exist first
3. Tasks 3–5 (`assemble` tests) — need Task 1
4. Task 6 (`fit` tests) — needs Task 2
5. Task 7 (limit pairing) — needs Task 2; the only task that imports `query_pipeline`
6. Task 8 (property tests) — needs Task 2
7. Task 9 (module shape) — needs Tasks 1 and 2
8. Task 10 (full suite, commit) — needs all of the above
