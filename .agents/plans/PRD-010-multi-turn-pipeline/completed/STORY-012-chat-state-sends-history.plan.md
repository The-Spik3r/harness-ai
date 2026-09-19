---
story: STORY-012
prd: PRD-010
slug: chat-state-sends-history
title: "ChatState sends session history through run_conversation; flag-off path unchanged"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-010-multi-turn-pipeline
created: 2026-09-18
---

# Plan: ChatState sends session history through run_conversation; flag-off path unchanged

## Summary

Wire the three pieces STORY-006, STORY-010 and STORY-011 already shipped into `ChatState._do_send`, and nothing else. One branch selects the **pipeline input**: with history on and a chat that existed *before this send*, `_do_send` awaits `run_in_pipeline(chat_history.assemble, identity, session_id)`, calls the pure `chat_history.fit(...)` inline with `settings.CONTEXT_MAX_MESSAGES` / `settings.CONTEXT_MAX_CHARACTERS`, and awaits `run_in_pipeline(run_conversation, messages=…)`; otherwise it awaits `run_in_pipeline(run_query, prompt=text, …)` with today's exact keyword arguments. `fit`'s dropped count rides to the assistant bubble as a new `ChatMessage.history_trimmed: int = 0`, which `_to_stored_message` persists into the column STORY-010 added and `_to_chat_message` restores on reload. A `ChatSessionError` out of `assemble` degrades to sending *without* history and sets `sessions_error` — the composer is never blocked (PRD-004 Risk 3), mirroring the failed-`create` arm three lines above it.

The production diff is small. The work in this story is in the **six facts exploration turned up**, four of which are load-bearing and none of which the story text states:

1. **Two AST tripwires forbid exactly the line PRD F8 requires, and both must be amended in this story.** `tests/test_chat_sessions.py:1352` (`test_no_module_outside_the_service_branches_on_chat_history_enabled`) walks every module under `app/` and `chat_ui/` and fails on any reference to the `CHAT_HISTORY_ENABLED` identifier outside a three-file allowlist; `tests/test_chat_state.py:1212` (`test_chat_state_never_names_the_history_flag`) pins the same for `state.py` alone, and its own docstring says "`ChatState` remains barred entirely". PRD-010 F8 overrides both by name and with a stated reason: "the branch on `CHAT_HISTORY_ENABLED` is explicit because it selects the pipeline input, not persistence… reading the flag keeps the off path provably identical: same function, same arguments, no extra read." So the allowlist gains `chat_ui/chat_ui/state.py` and the narrow guard is **repurposed, not deleted** — it becomes "named exactly once, and only inside `_do_send`", which is the shape `tests/test_session_rail.py:717` already uses for the rail's own exemption (`test_the_flag_is_named_once_and_only_at_the_surface`). That precedent is what makes this an amendment rather than a hole. **This is the one decision in this plan that contradicts a shipped test, and it is made because the PRD makes it** (see Risks, R1). The other three flag tripwires — `tests/test_chat_shell.py:721`, `tests/test_session_rail.py:717`, `tests/test_query_session_id.py:543` — scope `shell.py`, `session_rail.py` and `app/routers/query.py` and are untouched by this story.

2. **The branch must test the session id as it stood *before* the lazy create, not after it.** `_do_send` reads `session_id = self.active_session_id` under the lock (`state.py:964`), then — on the first send of a new chat — replaces it with the id `chat_sessions.create` returns (`:986-1000`), *before* the pipeline call. F8's sketch `if session_id and settings.CHAT_HISTORY_ENABLED` is written against the pre-create value; evaluated after the create it is always true, and the first send of every new chat would go through `run_conversation` with an empty `assemble` result. AC 2 forbids that in as many words — "the **first** send of a new chat (no `session_id` before send) … `run_query` is called through `run_in_pipeline` with exactly today's keyword arguments … and `chat_history.assemble` is **never** called". Behaviourally the two are identical (`run_query` *is* the one-message adapter, STORY-007), so only a tripwire can tell them apart, and AC 2 asks for exactly that tripwire. The fix is one local captured at the same moment as `model` and `device`: `had_session = bool(session_id)` (Task 2).

3. **~34 existing tests stub `chat_state_mod.run_query` and send twice into one session; with history on, their second send would now miss the stub and run the real pipeline against the real `call_openrouter`.** Enumerated by AST walk: 33 in `tests/test_chat_state.py` (`:350, :579, :613, :917, :1129, :1275, :1313, :1337, :1405, :1431, :1523, :1577, :1775, :1829, :1853, :1900, :1943, :1980, :2011, :2058, :2086, :2106, :2336, :2357, :2425, :2463, :2513, :2566, :2595, :2633, :2671, :2987, :3010`) and one in `tests/test_rbac.py:311` (single send — safe, listed for completeness). Most of those 33 do **not** patch `call_openrouter`, so the failure mode is not a red assertion but an outbound HTTP attempt. AC 5 ("the full suite, including `tests/test_chat_state.py` and `tests/test_session_rail.py`, is green") is therefore most of this story's work. The fix is one helper, `_stub_pipeline(monkeypatch, fake)`, that installs the test's own stub on **both** `run_query` and `run_conversation` (the latter through a shim that forwards `messages[-1].content` as `prompt`), plus a mechanical rewrite of those call sites — intent preserved, one line each (Task 6). An autouse fixture was considered and rejected: it would silently strip history from the new STORY-012 tests that exist to prove history is sent.

4. **`tests/test_chat_state.py::test_the_rehydration_reads_every_stored_field` (`:2219`) is designed to fail on this story, and the failure is the handshake.** Its excused-field literal is `{"session_id", "created_at", "id", "history_trimmed"}` and its docstring says so outright: "the moment STORY-012 adds `ChatMessage.history_trimmed`, the derived set shrinks, this assertion fails, and the mapping becomes required rather than remembered." Task 5 drops `history_trimmed` from that literal; the same test then *requires* `_to_chat_message` to read the column, so the round-trip half of AC 3 is enforced by a test that was already written for it.

5. **`history_trimmed` is the one optional column that must not be written with `or None`, and `app/db/database.py` already says why twice.** `:1722`: "`history_trimmed` gets no `or None` and no `int()` … `0` and `NULL` say different things — 'this send dropped nothing' against 'written before the feature existed'". `_to_stored_message` converts every other optional field with `or None` (`state.py:57-67`); this one is passed straight through as an `int`. The read side takes `row.history_trimmed or 0`, because a Reflex Var cannot be `None` on the wire — the same `or 0` `tokens_used` and `audit_id` already use (`state.py:105-107`). Both halves round-trip through storage that STORY-010 already proved (`tests/test_chat_sessions.py:746-801`).

6. **`tests/test_untouched_app.py` does not block any of this, and that was checked rather than assumed.** `test_chat_state.py` is one of the six pinned suites, but the census compares against `_BASE = d3e6279` (pre-PRD-006) and its `_TEST_DEF` regex matches `^def test_` only. `test_chat_state_never_names_the_history_flag` arrived with PRD-008, long after the baseline, so renaming it removes nothing the census knows about. Verified by reading `tests/test_untouched_app.py:66-161`, not inferred.

Two smaller facts that shape tasks: `assemble` propagates `ChatSessionError` unchanged and declares no twin (`tests/test_chat_history.py:409-418` pins it, and its docstring names STORY-012's degraded arm as the catcher); and `QueryBlockedContextLimitResponse` is already in the union `_do_send`'s `isinstance` chain walks, so an over-limit conversation currently lands in the chain's `else` and renders an `internal_error` bubble — **that is STORY-013's, not this story's**, and Task 4 leaves the chain untouched rather than half-solving it.

There is no linter or formatter in this repo. "Validate" means pytest against the local libSQL dev server (`tests/conftest.py:131-152`). <cc-memory filenames="libsql-dev-server-degrades-under-repeated-suites.md">Per the recorded libSQL note, mass fixture errors across a repeated suite mean restart the dev-server container, not bisect the code.</cc-memory>

## User Story

As an **end user**
I want each send in an existing chat to carry that chat's earlier answered exchanges
So that the model can answer "what did I just ask?" and follow-ups like "shorten that".

## Story Reference

- Story file: `.agents/stories/PRD-010-multi-turn-pipeline/STORY-012-chat-state-sends-history.md`
- PRD: `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md` — Sections 4 (Chat UI), 5 (stories 1, 3), 6.1, 6.4, 7 (F8), 9.3, 11 (MVP definition, functional requirements)
- Depends on (all `done`): STORY-006 `d265843` (`run_in_pipeline`), STORY-007 `0096e2e` (`run_conversation`), STORY-010 `113633c` (the column), STORY-011 `a3eccae` (`assemble`/`fit`)
- Blocks: STORY-013 (footer + `context_limit` bubble), STORY-014, STORY-015, STORY-017
- Precedent plan: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-006-dedicated-pipeline-executor.plan.md` (the last story to edit `_do_send`)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (new send path in an existing handler; two mappers extended) |
| Complexity | HIGH — the production diff is ~40 lines; the test surface is ~34 amended call sites plus two amended tripwires |
| Systems Affected | `chat_ui/chat_ui/state.py`, `chat_ui/chat_ui/models.py`, `tests/test_chat_state.py`, `tests/test_chat_sessions.py`, `tests/test_chat_history_send.py` (new) |
| Story | STORY-012 |
| PRD | PRD-010 |
| Epic Branch | `epic/PRD-010-multi-turn-pipeline` (commit directly on this branch) |

---

## Skills In Use

`.agents/skills/` was listed in full. It holds exactly one skill:

| Skill | Applies? | Reason |
|-------|----------|--------|
| `frontend-design` | **No** | Its `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story renders nothing new: `ChatMessage.history_trimmed` is carried, not displayed. PRD Section 8's "Skill constraints" paragraph assigns the two visual surfaces (the `context_limit` bubble and the trimmed-history footer note) to **STORY-013**, and the story's own Technical Notes repeat it: "The footer copy and the `context_limit` bubble are STORY-013. This story only carries the number." |

The story's `skills:` frontmatter is `[]` and its Technical Notes end with "Skills: none applicable." **No skill constrains any task below.**

---

## Patterns to Follow

### Reading state into locals under the lock, then releasing it before awaiting

```python
# SOURCE: chat_ui/chat_ui/state.py:958-968
            async with self:
                self.input_text = ""
                model = self.selected_model
                # Read through the lock into a local, like `model` above: a
                # background task has no exclusive access outside the block.
                session_id = self.active_session_id
                device = None
```

`had_session` (Task 2) joins `model`, `session_id` and `device` in this block. Nothing in the history path holds the lock across an `await` — the story's Technical Notes make that explicit, and `_append_and_persist`'s docstring explains why nesting `async with self` raises `ImmutableStateError`.

### Degrading a broken rail into a notice instead of a refusal

```python
# SOURCE: chat_ui/chat_ui/state.py:988-995
                except ChatSessionError as exc:
                    # A broken rail does not block the composer: the turn is
                    # sent unattached rather than refused.
                    session_id = None
                    async with self:
                        self.sessions_error = str(exc)
```

The `assemble` arm is this arm's twin one screen down: `history = []` replaces `session_id = None`, and the same `sessions_error` slot carries the same kind of fact. Same shape, same error type, same slot — so a reader who has understood one has understood both.

### Every pipeline call goes through the dedicated executor

```python
# SOURCE: chat_ui/chat_ui/state.py:1020-1027
                # PRD-010 STORY-006: the pipeline call runs on the dedicated
                # pipeline executor, not the event loop's default executor --
                # the same pool session-rail reads and admin snapshots use via
                # asyncio.to_thread, and the one this change stops starving.
                result = await run_in_pipeline(
                    run_query,
                    identity=identity,
                    prompt=text,
```

`assemble` is a synchronous one-read function (`app/services/chat_history.py:77`, and its module docstring: "STORY-012 calls it through `run_in_pipeline` and it never touches the event loop"), so it goes through the same door. `fit` is pure and is called inline.

### The two mappers, written as each other's inverse

```python
# SOURCE: chat_ui/chat_ui/state.py:53-67 and :100-112 (abridged)
        prompt=bubble.prompt or None,       # write: the column means *absent*
        tokens_used=bubble.tokens_used or None,
...
        prompt=row.prompt or "",            # read: a Var cannot be None
        tokens_used=row.tokens_used or 0,
```

`history_trimmed` breaks the `or None` half of that symmetry on purpose, and the docstring must say so, quoting `app/db/database.py:1722`. It keeps the `or 0` half.

### An AST tripwire that permits exactly one reference, in one named function

```python
# SOURCE: tests/test_session_rail.py:717-744 (abridged)
def test_the_flag_is_named_once_and_only_at_the_surface(source):
    """The exemption is one question asked in one place, not a licence."""
    ...
    assert len(named) == 1, f"the flag is named {len(named)} times"
    entry = next(node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef) and node.name == "session_rail")
    assert any(isinstance(n, ast.Attribute) and n.attr == "CHAT_HISTORY_ENABLED"
               for n in ast.walk(entry)), "the flag is not read in session_rail() itself"
```

Task 7 rewrites `test_chat_state_never_names_the_history_flag` into this exact shape, with `_do_send` (an `ast.AsyncFunctionDef`) in place of `session_rail`.

### Tests: a stub that captures what the pipeline was handed

```python
# SOURCE: tests/test_chat_state.py:996-1010
def _capturing_run_query(result=None, captured=None):
    """A run_query stand-in that records the session_id it was handed."""
    ...
    def _fake(identity, prompt, device, model, openrouter_api_key,
              call_openrouter, session_id=None):
        if captured is not None:
            captured["session_id"] = session_id
            captured["called"] = captured.get("called", 0) + 1
        return result
    return _fake
```

`_capturing_run_conversation` (Task 8) mirrors it field for field, capturing `messages` instead of `prompt`.

### Tests: proving a call did *not* happen, with a tripwire rather than an empty result

```python
# SOURCE: tests/test_history_off_integration.py:507-513 (the module's recorded invariants)
#  3. Every "nothing was read" claim is carried by `_Tripwire`, never by an
#     empty return value alone -- an empty database returns empty either way.
```

AC 2's "`assemble` is **never** called" is asserted with a stub that raises, not with an empty history — `assemble` returns `[]` on the off path anyway, so an empty result proves nothing.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/models.py` | UPDATE | `ChatMessage.history_trimmed: int = 0` (AC 5) |
| `chat_ui/chat_ui/state.py` | UPDATE | imports; the history branch in `_do_send`; `trimmed` onto the assistant bubble; both mappers |
| `tests/test_chat_history_send.py` | CREATE | AC 1–4: the sent conversation, the off-path tripwire, trimming and persistence, D4 end to end |
| `tests/test_chat_state.py` | UPDATE | `_stub_pipeline` helper + ~33 call sites; repurpose the flag tripwire; shrink the excused-field literal |
| `tests/test_chat_sessions.py` | UPDATE | add `chat_ui/chat_ui/state.py` to the flag allowlist, with the PRD F8 reason recorded in the docstring |

Not changed, deliberately: `app/services/chat_history.py` and `app/services/query_pipeline.py` (both shipped and tested), `chat_ui/chat_ui/components/bubbles.py` and `copy.py` (STORY-013), `tests/test_history_off_integration.py` (AC 2 requires it to pass **unmodified**), `README.md` (STORY-018).

---

## Tasks

Execute in order. Tasks 1–5 are the production change; 6–8 make the suite green and pin the new behaviour. Each is atomic and verifiable.

### Task 1: `ChatMessage.history_trimmed`

- **File**: `chat_ui/chat_ui/models.py`
- **Action**: UPDATE
- **Implement**: add `history_trimmed: int = 0` to `ChatMessage`, declared after `detail` and before `restored`, so the field order mirrors `StoredMessage` and the table. Comment it with what the number is (whole earlier exchanges `chat_history.fit` dropped from the send this bubble answers) and why the bubble's type is `int` where the column's is `Optional[int]`: a Reflex Var cannot be `None` on the wire, so the bubble's `0` covers both "dropped nothing" and "written before the feature existed", and only the column keeps the two apart (`app/db/models.py:290-292`).
- **Mirror**: `app/db/models.py:284-292` — the field it pairs with, and the comment there that predicted this one ("STORY-012 adds the matching ChatMessage field and the two mappers").
- **Validate**: `python -m pytest tests/test_chat_state.py::test_the_rehydration_reads_every_stored_field` — **expected to fail** now, naming `history_trimmed`. That failure is the handshake described in Summary fact 4; Task 5 clears it.

### Task 2: the branch, and the local it turns on

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**:
  - Imports: `from app.config import settings`, `from app.models.messages import Message`, `from app.services import chat_history`, and widen `from app.services.query_pipeline import run_query` to `run_conversation, run_query`. Import the module `chat_history` (not `assemble`) so a test can monkeypatch `chat_state_mod.chat_history.assemble` and so the call site reads `chat_history.assemble`, matching how `chat_sessions` is already used in this file.
  - In the `async with self` block that reads `model`/`session_id`/`device` (`:958-968`), add `had_session = bool(session_id)`. Comment it with Summary fact 2: the create below replaces `session_id`, so the question "did this chat exist before this send?" has to be captured here or it cannot be asked later; AC 2 requires the first send of a new chat to take the `run_query` path.
  - Replace the single `run_in_pipeline(run_query, …)` call (`:1024-1039`) with the F8 branch:
    ```python
    if had_session and settings.CHAT_HISTORY_ENABLED:
        try:
            history = await run_in_pipeline(
                chat_history.assemble, identity, session_id
            )
        except ChatSessionError as exc:
            history = []
            async with self:
                self.sessions_error = str(exc)
        messages, trimmed = chat_history.fit(
            history,
            Message("user", text),
            settings.CONTEXT_MAX_MESSAGES,
            settings.CONTEXT_MAX_CHARACTERS,
        )
        result = await run_in_pipeline(
            run_conversation,
            identity=identity,
            messages=messages,
            device=device,
            model=model,
            openrouter_api_key=None,
            call_openrouter=call_openrouter,
            session_id=session_id or None,
        )
    else:
        trimmed = 0
        result = await run_in_pipeline(run_query, …)   # byte-for-byte today's call
    ```
    The `else` arm is **moved, not rewritten**: same function, same keyword arguments in the same order, same `session_id or None` and its comment. That is what makes AC 2's "exactly today's keyword arguments" checkable by reading the diff.
  - Keep the whole branch inside the existing `try:` whose `except OpenRouterError / (DuplicateCheckError, PiiRedactorError) / Exception` arms follow, so a failure in `run_conversation` produces the same bubbles a failure in `run_query` does. `ChatSessionError` is caught *inside* the history arm, before those, because it is not a pipeline failure and must not become an `internal_error` bubble.
- **Mirror**: `state.py:986-1000` (the `create` arm this degrades like) and `state.py:1020-1039` (the call this replaces). PRD Section 7, F8.
- **Validate**: `python -m pytest tests/test_history_off_integration.py` — the whole module, unmodified, must stay green (AC 2's first half; with the flag off the branch is never entered).

### Task 3: `settings` reads, and why they are reads and not captures

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE (docstring/comment only; the code lands in Task 2)
- **Implement**: comment the two `settings.CONTEXT_MAX_*` arguments with the reason `query_pipeline._context_limit_exceeded` gives for its own per-call reads (`app/services/query_pipeline.py:83-87`): every test in this suite sets them with `monkeypatch.setattr(settings, …)`, which a module-level constant would silently ignore, and a process that read them once could not be reconfigured without a restart. Note the pairing `fit` documents (`app/services/chat_history.py:150-158`): `fit` accepts on `<=` where the pipeline refuses on `>`, over the identical two counts, so a conversation trimmed to these limits is never then refused for them — which is only true while **these** are the settings passed.
- **Mirror**: `app/services/query_pipeline.py:83-97`.
- **Validate**: `python -m pytest tests/test_chat_history.py` (the STORY-011 suite, including `test_a_fitted_conversation_is_never_refused_for_the_limits_it_was_fitted_to`) stays green.

### Task 4: `trimmed` onto the assistant bubble — and onto nothing else

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: in the `isinstance(result, QuerySuccessResponse)` arm, add `history_trimmed=trimmed`. Leave the `duplicate`, `injection`, `forbidden` and fallback arms alone: they keep the field's `0` default, which is honest — no exchange was dropped *from an answer*, because there was no answer. Comment it with AC 3's last sentence: a send with no trimming stores `0`, never a misleading positive number. Do **not** touch the `isinstance` chain's `else` arm for `QueryBlockedContextLimitResponse`; that bubble is STORY-013's (Summary, closing paragraph).
- **Mirror**: `state.py:1070-1082` — the success arm as it stands.
- **Validate**: `python -m pytest tests/test_chat_state.py -k "bubble or persist"`.

### Task 5: both mappers

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**:
  - `_to_stored_message`: `history_trimmed=bubble.history_trimmed` — **no `or None`**. Extend the docstring with the exception and its reason, quoting `app/db/database.py:1722`: this is the one optional field where `0` and `NULL` say different things ("this send dropped nothing" against "written before the feature existed"), so the `or None` every other field takes would destroy information rather than tidy it.
  - `_to_chat_message`: `history_trimmed=row.history_trimmed or 0`, with the existing "a Var cannot be None on the wire" reason; the `or 0` matches `tokens_used` and `audit_id` directly above it. Note in the docstring that the asymmetry with the write side is deliberate and one-directional.
- **Mirror**: `state.py:53-67` / `:100-112`; `app/db/database.py:1644-1657` and `:1722-1727`.
- **Validate**: `python -m pytest tests/test_chat_state.py::test_the_rehydration_reads_every_stored_field` — still failing on the literal, which Task 7 fixes; and `python -m pytest tests/test_chat_sessions.py -k history_trimmed` (STORY-010's storage round-trip) green.

### Task 6: `_stub_pipeline`, and the ~33 call sites

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: add next to `_capturing_run_query` (`:996`):
  ```python
  def _stub_pipeline(monkeypatch, fake):
      """Install one stub on both pipeline entry points.

      PRD-010 STORY-012: with history on, a send into an existing chat goes
      through `run_conversation`, and the first send of a new chat through
      `run_query`. A test that stubs only `run_query` therefore stubs only the
      first send of each chat -- and its second send would reach the real
      pipeline and the real `call_openrouter`. Every test here that patched
      `run_query` meant "stub the pipeline", so this says that instead.

      The shim forwards `messages[-1].content` as `prompt`, which is exactly
      `run_query`'s own adapter (`app/services/query_pipeline.py:359-376`), so a
      stub written against the single-turn signature keeps working unchanged.
      """
      monkeypatch.setattr(chat_state_mod, "run_query", fake)

      def _via_conversation(identity, messages, device, model, openrouter_api_key,
                            params=None, call_openrouter=None, session_id=None):
          return fake(identity, messages[-1].content, device, model,
                      openrouter_api_key, call_openrouter, session_id)

      monkeypatch.setattr(chat_state_mod, "run_conversation", _via_conversation)
  ```
  Then rewrite each `monkeypatch.setattr(chat_state_mod, "run_query", X)` in this module as `_stub_pipeline(monkeypatch, X)` — the 33 sites listed in Summary fact 3. Two need care rather than a mechanical swap:
  - `:613 test_chat_state_concurrent_send_guard` patches `run_in_pipeline` itself (`:626`), which sits above both entry points and already covers the new path; check it and leave it if so.
  - `:579 test_chat_state_pending_resets_on_all_outcomes` installs several one-line lambdas in sequence (`:597-607`); each becomes its own `_stub_pipeline` call.
  Tests whose stub raises (`_raise_pii_error`, `_raise_openrouter_error`, …) work unchanged through the shim, which is the point of forwarding rather than returning a canned result.
- **Mirror**: `tests/test_chat_state.py:996-1010`.
- **Validate**: `python -m pytest tests/test_chat_state.py` — green except the two tripwires Task 7 owns. **No test may reach the network**: if a run hangs, a call site was missed.

### Task 7: the two tripwires

- **Files**: `tests/test_chat_state.py`, `tests/test_chat_sessions.py`
- **Action**: UPDATE
- **Implement**:
  - `tests/test_chat_sessions.py:1391-1395`: add `root / "chat_ui" / "chat_ui" / "state.py"` to `allowed`, and extend the docstring with a fourth-entry paragraph in the voice of the third (STORY-018's). It must say what was granted and what was not: PRD-010 F8 grants `ChatState` **one** read, and only to select the pipeline *input* — "the branch on `CHAT_HISTORY_ENABLED` is explicit because it selects the pipeline input, not persistence… reading the flag keeps the off path provably identical: same function, same arguments, no extra read." The data path is untouched: persistence still cannot tell "off" from "none yet", because `_append_and_persist` still branches on `session_id` alone and never on the flag. Point at the narrow guard below as the thing that holds the grant to its scope.
  - `tests/test_chat_state.py:1212-1226`: rename `test_chat_state_never_names_the_history_flag` → `test_chat_state_names_the_history_flag_once_and_only_in_do_send`, and rewrite its body in the shape of `tests/test_session_rail.py:717-744`: exactly one reference in the module, and that reference inside the `_do_send` node (an `ast.AsyncFunctionDef`). The docstring records the reversal and its authority — PRD-008 Section 6 said "no caller branches on the flag"; PRD-010 F8 grants this one caller one branch, for a reason it states, and this test is what keeps the grant to one line. A second reference — in `login`, in `select_session`, in `_append_and_persist` — fails here, which is the original rule still doing its job everywhere it was not lifted.
  - `tests/test_chat_state.py:2264` (inside `test_the_rehydration_reads_every_stored_field`): drop `"history_trimmed"` from the excused literal, and update the docstring paragraph that called it temporary to say it has landed. Leave the assertion mechanism untouched; it now *requires* the Task 5 read.
- **Mirror**: `tests/test_session_rail.py:717-744`.
- **Validate**: `python -m pytest tests/test_chat_sessions.py tests/test_chat_state.py tests/test_chat_shell.py tests/test_session_rail.py tests/test_query_session_id.py` — all five flag tripwires green, three of them unmodified.

### Task 8: `tests/test_chat_history_send.py` — the four behavioural ACs

- **File**: `tests/test_chat_history_send.py`
- **Action**: CREATE
- **Implement**: a new module rather than more of `test_chat_state.py`, matching how `test_chat_history.py` and `test_history_off_integration.py` each seeded their own small helpers rather than importing across test modules. Seed local `_make_state`, `_send`, `_identity` and `_capturing_run_conversation` (mirroring `_capturing_run_query`, capturing `messages`). Tests, one per acceptance criterion:
  - **AC 1 — what the model is handed.** With `temp_db` and a real first send (`call_openrouter` faked, pipeline real, so the assistant row is genuinely written), send "What is 2+2?" then "what did I just ask?" with `run_conversation` captured. Assert the captured `messages` are exactly `[("user", "What is 2+2?"), ("assistant", <the stored redacted reply>), ("user", "what did I just ask?")]` — the assistant content read back from `chat_sessions.messages_for`, not a literal, so the test states "what was stored is what was sent".
  - **AC 1, second half — the route.** Spy on `chat_state_mod.run_in_pipeline` to record the functions it was handed; assert `chat_history.assemble` and `run_conversation` both went through it, and that `fit` did not (it is pure and runs inline).
  - **AC 2 — the off path, twice.** (a) flag on, **first** send of a new chat; (b) `CHAT_HISTORY_ENABLED=False`, second send into an existing chat. In both: `assemble` replaced by a stub that raises `AssertionError`, `run_conversation` replaced by one that raises, `run_query` captured. Assert the captured keyword arguments are exactly today's set — `identity`, `prompt`, `device`, `model`, `openrouter_api_key`, `call_openrouter`, `session_id` — with `prompt == text`. `tests/test_history_off_integration.py` carries the rest of the off-path claim and stays unmodified.
  - **AC 3 — the trimmed count, stored and restored.** `monkeypatch.setattr(settings, "CONTEXT_MAX_MESSAGES", 3)` after three real exchanges, then send: assert the live assistant bubble's `history_trimmed` equals the count `fit` returned for the same input, that the `chat_messages` row carries it (read back through `chat_sessions.messages_for`), and that `_to_chat_message` restores it. A second test sends with generous limits and asserts the stored value is `0`.
  - **AC 4 — D4, end to end.** Drive real sends that produce a `duplicate` bubble (send the same text twice) and an `injection` bubble (a prompt matching a shipped pattern), then send a fresh prompt with `run_conversation` captured, and assert neither held turn's text appears in any captured message content. Through `temp_db` and the real pipeline, as the AC requires.
  - **The degraded arm.** `chat_history.assemble` monkeypatched to raise `ChatSessionError("messages_for failed: boom")`: assert the send still completes, `run_conversation` received `[Message("user", text)]` only, `state.sessions_error` carries the message, `state.pending is False`, and the assistant bubble reached the screen. This is the story's Technical Note ("Test it") and PRD-004 Risk 3.
- **Mirror**: `tests/test_chat_history.py:390-418` (spy/raising-stub idioms), `tests/test_chat_state.py:996-1010` (capturing stub), `tests/test_history_off_integration.py:198-231` (a real send with only `call_openrouter` faked).
- **Validate**: `python -m pytest tests/test_chat_history_send.py -v`.

---

## End-to-End Tests

For `/implement` to execute:

- [ ] `python -m pytest tests/test_chat_history_send.py -v` — all ACs pass
- [ ] `python -m pytest tests/test_history_off_integration.py` — green with a **zero-line diff** in that file (`git diff --stat tests/test_history_off_integration.py` is empty)
- [ ] `python -m pytest tests/test_chat_state.py tests/test_session_rail.py` — green (AC 5)
- [ ] `python -m pytest` — the full suite green, including `test_untouched_app.py`, `test_rbac.py` and the four flag tripwires in other modules
- [ ] Manual, with the app running and history on: send "What is 2+2?", then "what did I just ask?" — the second answer names the first question (PRD Section 11, *MVP definition*). Record the two upstream payloads in the story report.
- [ ] Manual: reload the page onto that session — the transcript restores, and no bubble shows a trimmed note it did not show live (STORY-013 renders the note; this checks the number survives the round trip)

## Validation

```bash
# the libSQL dev server the suite requires (tests/conftest.py:131-152)
docker start harness-libsql-dev

python -m pytest tests/test_chat_history_send.py -v
python -m pytest tests/test_chat_state.py tests/test_chat_sessions.py tests/test_history_off_integration.py
git diff --stat tests/test_history_off_integration.py   # must be empty
python -m pytest
```

Mass fixture errors across a repeated suite mean restart `harness-libsql-dev`, not bisect the code.

## Risks + Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| R1 | **Amending two shipped tripwires looks like dodging them.** `test_no_module_outside_the_service_branches_on_chat_history_enabled` and `test_chat_state_never_names_the_history_flag` were written by PRD-008 to forbid exactly this line. | The grant is PRD-010 F8's, in writing, with its reason. It is recorded in both docstrings, and it is *narrowed* rather than removed: one reference, inside `_do_send`, enforced by the repurposed guard in the shape `session_rail.py`'s exemption already uses. Any second reference still fails. If the implementer finds the PRD ambiguous, **stop and raise it** rather than widening the allowlist further. |
| R2 | **A missed `run_query` stub site reaches the network** and hangs CI instead of failing. | Task 6 enumerates all 33 sites by line. After Task 6, run `grep -n 'setattr(chat_state_mod, "run_query"' tests/*.py` — the only hits left should be inside `_stub_pipeline` and `tests/test_rbac.py:311` (a single send, first-send path, safe). |
| R3 | **Branching after the create** sends the first turn of every new chat through `run_conversation`, passing every behavioural test and failing only AC 2's tripwire. | `had_session` is captured under the lock (Task 2) and AC 2(a) tests it directly with a raising `assemble` stub. |
| R4 | **`fit`'s limits drift from the pipeline's**, producing a context-limit refusal on the very send trimming was meant to rescue. | The call site passes `settings.CONTEXT_MAX_MESSAGES` / `CONTEXT_MAX_CHARACTERS` and nothing derived from them; STORY-011's `test_a_fitted_conversation_is_never_refused_for_the_limits_it_was_fitted_to` holds the pairing, and Task 3 is where the reason is written down. |
| R5 | **`history_trimmed` written with `or None`** by reflex, conflating "dropped nothing" with "pre-feature". | Task 5 states the exception and quotes `app/db/database.py:1722`; STORY-010's round-trip tests (`tests/test_chat_sessions.py:746-801`) already distinguish `0`, `3` and `None`. |
| R6 | **Two tabs on one session see each other's writes on the next send.** | Accepted and already documented (README *Limitations*, story Technical Notes). No mitigation in this story. |
| R7 | **An over-limit conversation renders `internal_error`** because the `isinstance` chain has no `context_limit` arm. | Out of scope by the story's own text; STORY-013 owns it and is blocked by this story. Task 4 leaves the chain untouched rather than half-solving it. Note it in the story report so STORY-013 inherits a known state, not a surprise. |

## Acceptance Criteria

(Copied from story `STORY-012`)

- [ ] Given `CHAT_HISTORY_ENABLED=true` and an active session with one prior answered exchange ("What is 2+2?"), when the user sends "what did I just ask?", then the injected upstream records `[user("What is 2+2?"), assistant(<stored redacted reply>), user("what did I just ask?")]`, via `run_in_pipeline(chat_history.assemble, …)`, `fit(...)` with `settings.CONTEXT_MAX_*`, and `run_in_pipeline(run_conversation, …)`
- [ ] Given the **first** send of a new chat (no `session_id` before send), or `CHAT_HISTORY_ENABLED=false`, when the user sends, then `run_query` is called through `run_in_pipeline` with exactly today's keyword arguments (`prompt=text`, …) and `chat_history.assemble` is **never** called; `tests/test_history_off_integration.py` passes unmodified, and a tripwire on `assemble` proves the off path
- [ ] Given a session whose history must be trimmed (limits monkeypatched small), when a send succeeds, then the assistant `ChatMessage` carries `history_trimmed=<dropped count>`, `_to_stored_message` persists it, and `_to_chat_message` restores it on reload; a send with no trimming stores `0` or `None`, never a misleading positive number
- [ ] Given a prior turn that was held as duplicate, blocked as suspicious or failed upstream, when the next send is made, then that turn's text is absent from the upstream messages (end to end through `temp_db`, D4)
- [ ] Given `ChatMessage` in `chat_ui/chat_ui/models.py`, when it is read, then it has `history_trimmed: int = 0`; the full suite, including `tests/test_chat_state.py` and `tests/test_session_rail.py`, is green
- [ ] All tasks completed
- [ ] The composer is never blocked: a `ChatSessionError` from `assemble` sends without history and sets `sessions_error` (PRD-004 Risk 3)
- [ ] Follows existing patterns
