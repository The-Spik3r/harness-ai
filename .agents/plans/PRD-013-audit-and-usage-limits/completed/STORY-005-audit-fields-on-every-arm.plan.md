---
story: STORY-005
prd: PRD-013
slug: audit-fields-on-every-arm
title: "log_query and every pipeline arm write the new fields; ingress at every call site"
type: ENHANCEMENT
complexity: HIGH
epic_branch: epic/PRD-013-audit-and-usage-limits        # all stories commit here, no per-story branch
created: 2026-10-17
---

# Plan: log_query and every pipeline arm write the new fields; ingress at every call site

## Summary

STORY-002 gave `audit_logs` eight columns that nothing writes. This story makes the pipeline write them.

- **`log_query`** gains eight keyword parameters after `profile`: `ingress`, `message_count`, `input_tokens`, `output_tokens`, `streamed`, `has_tool_calls`, `conversation_key`, `limit_exceeded`. They are defaulted (`None`, or `False` for the two flags), with a comment in the `profile` style saying the pipeline never omits the ones it owns.
- **`run_conversation`** gains keyword-only `ingress=None` and `streamed=False`. It computes `message_count = len(messages)` and `conv_key = conversation_key(identity.user_id, messages)` once, at step 1 beside `key`, and passes `ingress`, `message_count`, `conversation_key` and `streamed` on all ten `log_query` calls. The success row and the output-redaction-error row also pass `input_tokens` and `output_tokens` from `OpenRouterResult`. The upstream-error row passes neither, because there is no result. `has_tool_calls=False` is passed at one call, the success row, with a comment naming PRD-016.
- **`_deny`** gains four required parameters: `ingress`, `message_count`, `conversation_key` and `streamed` (see F-1).
- **`run_query`** gains keyword-only `ingress="query"` and forwards it. **`/query`'s foreign-session refusal** passes `ingress="query"`, `message_count=1` and an explicit `conversation_key=None`. **`ChatState._do_send`** passes `ingress="chat"` on both branches.
- **Tests.** There is one new module, `tests/test_query_pipeline_audit_fields.py`. It covers every arm, `/query`, chat `2N-1`, the 50-turn MVP case and the source scan. `tests/test_audit_logger.py` gets persist and default tests for the eight parameters. Five existing test files need small edits because they pin a signature or use a fixed-signature stub that would reject `ingress=` (F-2).

**Nothing below was run.** The expected values come from reading the code at `51a8e8b`.

## User Story

As a compliance admin
I want every row to say which door the request came through, how many messages it carried, what it cost and which conversation it belongs to
So that multi-turn traffic can be reconstructed from the audit alone

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-005-audit-fields-on-every-arm.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md` (Sections 6.1, 6.2, 6.9, 7/F5, 11 *MVP definition* and *Audit*)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (story type `feature`) |
| Complexity | HIGH (story: `large`) |
| Systems Affected | `app/services/audit_logger.py`, `app/services/query_pipeline.py`, `app/routers/query.py`, `chat_ui/chat_ui/state.py`, eight test modules |
| Story | STORY-005 |
| PRD | PRD-013 |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch; checked out, HEAD `51a8e8b`) |
| Depends on | STORY-001 (`126f0da`), STORY-002 (`3c61b53`), STORY-003 (`9ede5a1`), STORY-004 (`99845b5`). All done |
| Blocks | STORY-006, STORY-011, STORY-013 |

---

## Skills In Use

None. `.agents/skills/` holds only `frontend-design`, and the story sets `skills: []` with no UI surface change.

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

---

## Findings and Decisions

**F-1. `_deny` also needs `streamed`.** The Technical Notes list three new required parameters for `_deny`: `ingress`, `message_count` and `conversation_key`. AC 1 also requires `streamed` (as passed) on every row, and that includes the three permission-refusal rows. So `_deny` takes `streamed` as a fourth required parameter, for the same reason as the other three. A defaulted `streamed=False` would silently write `0` on a PRD-014 SSE refusal.

**F-2. Existing tests that must change, and why each change is not a weakened assertion.** None of these pins behaviour. Each one pins a signature this story is required to change, or uses a stub whose fixed signature would raise `TypeError` on the new keyword.

| File | Line | Change |
|---|---|---|
| `tests/test_query_pipeline_run_conversation.py` | 70-83 | `run_conversation` parameter list gains `"ingress", "streamed"` after `"profile"`. Assert both are `KEYWORD_ONLY` and assert their defaults (`None`, `False`) |
| same | 85-93 | `run_query` parameter list gains `"ingress"`. Assert it is keyword-only with default `"query"` |
| same | 96-112 | Delegation kwargs gain `"ingress": "query"` |
| `tests/test_chat_history_send.py` | 103-104, 238-246 | `_capturing_run_conversation._fake` takes `ingress=None` and records it. `_RUN_QUERY_KWARGS` gains `"ingress"` |
| `tests/test_chat_outcomes_regression.py` | 142-143 | `_fake` takes `ingress=None`. This is a stub signature only, no assertion changes, so the PRD's "no assertion changed" rule for this file holds |
| `tests/test_chat_state.py` | 1001-1041 | `_stub_pipeline` installs a `run_query` shim that drops `ingress` before calling `fake`, instead of installing `fake` directly. `_via_conversation` takes `ingress=None`. The 8+ fixed-signature `_fake_run_query` stubs then stay untouched |
| `tests/test_rbac.py` | 311 | `_fake_run_query` takes `ingress=None` |

Fakes taking `**kwargs` need no change: `tests/test_pipeline_concurrency.py:404`, `test_chat_history_send.py:125`, the `log_query` spies in `test_query_outcomes_regression.py:200`, `test_query_router.py:806-812` and `test_query_pipeline_patterns.py:480`.

These need no change and still pass:
- The three "`_deny` requires X" tests (`test_query_pipeline_dedup_key.py:191`, `test_query_pipeline_pii_profiles.py:871`) use `pytest.raises(TypeError, match=...)`. Python's message lists every missing positional argument, so it still contains the name each test looks for.
- The `len(calls) == 10` call-site counts (`session_passthrough.py:507`, `dedup_key.py`, `pii_profiles.py:891`, `patterns.py:612`) stay at ten, because this story adds no `log_query` call.
- `tests/test_audit_characterization.py::test_no_arm_sets_these_prd013_fields` still passes. `_drive` passes no `ingress` or `streamed`, and its `_Upstream` reports no token split, so all six values it pins stay at their defaults. STORY-002 left `message_count` and `conversation_key` out of that dict for this story to set.

**F-3. The scan must see calls made through `run_in_pipeline`.** `ChatState._do_send` never calls the pipeline directly. It calls `run_in_pipeline(run_conversation, identity=..., ...)` (`state.py:1113`, `1129`). A scan that only looks at `Call` nodes whose callee is `run_conversation` would find zero chat sites and pass without checking anything. So the scan treats a `Call` as a pipeline call in two cases: its callee is named `run_conversation` or `run_query`, or its first positional argument is a `Name` with one of those ids. In both cases it checks that call's keywords. It also asserts the exact set of sites it found, so a renamed dispatcher fails loudly. The expected set is: router `run_query` ×1, state `run_conversation` ×1, state `run_query` ×1, pipeline delegation ×1.

**F-4. `has_tool_calls=False` goes on the success row only.** The note says "passed from one place". Taken literally, that is one `log_query` call. The success row is the only one that has both a request and a response to inspect, so PRD-016 starts there. Every other row gets the column default `0`, which is true until PRD-016. Spreading the value to every arm is PRD-016's job.

**F-5. Chat `2N-1` is checked against what the pipeline received.** `chat_history.assemble` (`app/services/chat_history.py:109-114`) emits a `user`/`assistant` pair only for `kind == "assistant"` rows with a non-empty `prompt`. `fit` (`:130`) appends the new turn last and drops nothing within the limits. So on the Nth send of a session with every prior send answered and nothing trimmed, the pipeline receives `2(N-1)+1 = 2N-1` messages. The first send goes through `run_query` (`had_session` is false), so it receives 1. The test wraps the real `run_conversation` and `run_query` in `chat_state_mod` and records `len(messages)`. It asserts `row.message_count == received == 2N-1`, so the formula and the measurement are each checked against the other.

**F-6. `conversation_key` is computed before authorization.** It is pure, like `dedup_key`, so this does not change the check order (PRD 6.1 step 1b). `conversation_key()` relies on a `user` turn existing, and step 0 has already guaranteed one. The local is named `conv_key` because `conversation_key` is the imported function, and `_deny`'s parameter of that name shadows it only inside the helper, which is the same as the existing `dedup_key` precedent at `query_pipeline.py:175`.

**F-7. `scripts/` is out of the scan.** `scripts/measure_history_latency.py:459` and `scripts/spike_pii_placeholders.py:668` call `run_conversation` with no `ingress`. AC 5 scopes the scan to `app/` and `chat_ui/`, and NULL is the honest record for a measurement script (PRD 6.9). They are left alone.

---

## Patterns to Follow

### A defaulted `log_query` parameter the pipeline never omits

```python
# SOURCE: app/services/audit_logger.py:35-43
    # PRD-012 STORY-011 (D9). Defaulted here but never omitted in the
    # pipeline: every row run_conversation writes passes it explicitly --
    # _deny requires it, and tests/test_query_pipeline_pii_profiles.py scans
    # every direct call site -- because a forgotten arm must not write a NULL
    # ...
    profile: Optional[str] = None,
```

### A required `_deny` parameter

```python
# SOURCE: app/services/query_pipeline.py:178-182
    # Required for the same reason as session_id and dedup_key: a forgotten
    # arm is a TypeError, not a NULL that makes a `code` row's
    # pii_detected_output = 0 read as clean (PRD-012 D9). `str`, not Optional:
    # after run_conversation's resolution it is never None.
    profile: str,
```

### A trailing keyword-only call-site argument

```python
# SOURCE: app/services/query_pipeline.py:209-214
    *,
    # Chosen by the call site, never by a request field: no schema carries it,
    # ... Keyword-only so no positional caller can pass it by accident; run_query passes nothing.
    profile: Optional[str] = None,
```

### Computed once at step 1

```python
# SOURCE: app/services/query_pipeline.py:230-234
    # Step 1: computed once, before authorization, on purpose (PRD-009
    # Section 6.1): it is pure, so it cannot change the check order, and
    # every row this function writes -- denials included -- carries it.
    key = dedup_key(identity.user_id, messages)
```

### An explicit `None` on the foreign-session row, numbered in the comment block

```python
# SOURCE: app/routers/query.py:92-95, 114-115
    # 6. `profile=None`, explicitly (PRD-012 D9). ...
            dedup_key=None,  # see 5. above
            profile=None,  # see 6. above
```

### Source scan over `app/` and `chat_ui/`

```python
# SOURCE: tests/test_chat_sessions.py:1230-1245
    root = pathlib.Path(__file__).resolve().parents[1]
    for path in sorted(list((root / "app").rglob("*.py")) + list((root / "chat_ui").rglob("*.py"))):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                called = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
```

### Reusing the characterization arms without copying them

```python
# SOURCE: tests/test_audit_characterization.py:33-36 (module docstring)
# It may import `ARM_CASES` and `_drive` (the `tests.test_pii_characterization` import
# precedent); it must not copy them.
```

`_drive` calls `query_pipeline.run_conversation` by module attribute (`test_audit_characterization.py:280-284`). So a test can `monkeypatch.setattr(query_pipeline, "run_conversation", wrapper)`, where the wrapper adds `ingress=`/`streamed=` and wraps `call_openrouter` so its result carries a token split (`dataclasses.replace(result, input_tokens=30, output_tokens=12)`, with 30+12 equal to `_TOKENS` = 42). Every arm then runs through the frozen `_drive` with nothing copied.

### Persist/default tests for a `log_query` field

```python
# SOURCE: tests/test_audit_logger.py:330-347
def test_profile_persisted_when_supplied(temp_db): ...
def test_profile_defaults_to_none_when_omitted(temp_db): ...
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/audit_logger.py` | UPDATE | Eight keyword parameters, passed into `AuditLog` |
| `app/services/query_pipeline.py` | UPDATE | `ingress`/`streamed` arguments; `message_count`/`conv_key` at step 1; all ten arms; `_deny` +4; `run_query` forwards `ingress` |
| `app/routers/query.py` | UPDATE | Foreign-session row gets `ingress`, `message_count`, `conversation_key=None` (comment item 7) |
| `chat_ui/chat_ui/state.py` | UPDATE | `ingress="chat"` on both `run_in_pipeline` calls |
| `tests/test_query_pipeline_audit_fields.py` | CREATE | AC 1-5 |
| `tests/test_audit_logger.py` | UPDATE | Persist and default tests for the eight parameters |
| `tests/test_query_pipeline_run_conversation.py` | UPDATE | Signature and delegation pins (F-2) |
| `tests/test_chat_state.py`, `tests/test_chat_history_send.py`, `tests/test_chat_outcomes_regression.py`, `tests/test_rbac.py` | UPDATE | Stub signatures accept `ingress` (F-2) |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Baseline

- **Action**: none
- **Implement**: Record the pass/fail count of `python -m pytest -q` on `51a8e8b`. Make sure the `harness-libsql-dev` container is up first.
- **Validate**: The figure is noted for Task 9.

### Task 2: `log_query` gains eight parameters

- **File**: `app/services/audit_logger.py`
- **Action**: UPDATE
- **Implement**: After `profile`, add `ingress: Optional[str] = None`, `message_count: Optional[int] = None`, `input_tokens: Optional[int] = None`, `output_tokens: Optional[int] = None`, `streamed: bool = False`, `has_tool_calls: bool = False`, `conversation_key: Optional[str] = None`, `limit_exceeded: Optional[str] = None`. Put one comment above the group, in the `profile` style. It should say:
  - The pipeline passes `ingress`, `message_count`, `conversation_key` and `streamed` on every row it writes. `_deny` requires them, and `tests/test_query_pipeline_audit_fields.py` scans every direct call.
  - `ingress` defaults to `None` for the hundreds of direct test calls, where NULL is the honest record (PRD-013 6.9).
  - The token pair is set only on the two arms that have an upstream result.
  - `has_tool_calls` and `limit_exceeded` are accepted now and first set by PRD-016 and STORY-011.

  Pass all eight into `AuditLog(...)`.
- **Mirror**: `app/services/audit_logger.py:35-43`, `:68`
- **Validate**: `python -m pytest tests/test_audit_logger.py -q` passes unchanged.

### Task 3: `log_query` persist/default tests

- **File**: `tests/test_audit_logger.py`
- **Action**: UPDATE
- **Implement**: `test_prd013_fields_persisted_when_supplied` passes all eight with non-default values and reads them back through `get_audit_log`. Use `streamed=True`, `has_tool_calls=True` and `limit_exceeded="tokens"`. `test_prd013_fields_default_when_omitted` checks six `None` values and two `False`.
- **Mirror**: `tests/test_audit_logger.py:330-347`
- **Validate**: `python -m pytest tests/test_audit_logger.py -q`

### Task 4: The pipeline writes the fields on every arm

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  1. Import `from app.services.conversation_key import conversation_key`.
  2. Add `ingress: Optional[str] = None` and `streamed: bool = False` to `run_conversation`, keyword-only, after `profile`. Give each a comment. `ingress` is chosen by the call site and never by a request field. `None` is for direct callers: tests and scripts (PRD 6.9). `streamed` stays `False` until PRD-014.
  3. At step 1, beside `key`, compute `message_count = len(messages)` (as received, before redaction; PRD 6.2) and `conv_key = conversation_key(identity.user_id, messages)` (step 1b; raw text; F-6). Extend the step-1 comment instead of writing a new one.
  4. `_deny`: after `profile`, add required `ingress: Optional[str]`, `message_count: int`, `conversation_key: Optional[str]` and `streamed: bool`. Use one comment that cites the same rule as the three above it (F-1). Pass all four to `log_query`. `conversation_key` is `Optional[str]` only for type symmetry with `log_query`; the pipeline always passes a string.
  5. Update all three `_deny(...)` calls and all nine direct `log_query(...)` calls to pass `ingress=ingress, message_count=message_count, conversation_key=conv_key, streamed=streamed`.
  6. Output-redaction-error arm (`:512`) and success arm (`:534`): add `input_tokens=openrouter_result.input_tokens, output_tokens=openrouter_result.output_tokens`. Upstream-error arm (`:488`): add nothing. Give it a one-line comment that there is no result, so no split (PRD 6.2).
  7. Success arm only: `has_tool_calls=False,  # PRD-016 sets this from the request and response; until then no row can carry tool calls (step 0 refuses them)` (F-4).
  8. `run_query`: add `*, ingress: Optional[str] = "query"` after `session_id`, and forward `ingress=ingress`. Comment: `/query` is the adapter's caller and the default names it. ChatState passes `"chat"` (PRD 6.9 table).
- **Mirror**: `query_pipeline.py:166-182` (`_deny`), `:209-214` (keyword-only), `:230-234` (step 1)
- **Validate**: `python -m pytest tests/test_audit_characterization.py tests/test_query_pipeline_session_passthrough.py tests/test_query_pipeline_dedup_key.py tests/test_query_pipeline_pii_profiles.py tests/test_query_pipeline_patterns.py -q`, all green with no edits (F-2). `tests/test_query_pipeline_run_conversation.py` fails exactly the three signature/delegation tests, which Task 7 fixes.

### Task 5: `/query`'s foreign-session refusal

- **File**: `app/routers/query.py`
- **Action**: UPDATE
- **Implement**: Add comment item 7 to the numbered block at `:54-102`. This row has `ingress="query"` and `message_count=1`: the router knows both, since `/query` is the door and the request is one prompt. `conversation_key=None` is explicit, like 5 and 6: no key is derived before `run_query`. `streamed` takes its default. Pass `ingress="query", message_count=1, conversation_key=None,  # see 7. above`.
- **Mirror**: `app/routers/query.py:85-96`, `:114-115`
- **Validate**: `python -m pytest tests/test_query_router.py tests/test_query_outcomes_regression.py -q`

### Task 6: ChatState passes `ingress="chat"`

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Add `ingress="chat",` to the `run_in_pipeline(run_conversation, ...)` call (`:1113-1122`) and to the `run_in_pipeline(run_query, ...)` call (`:1129-1146`). Put one short comment on the first (PRD-013 6.9): the chat UI names its own door, and the history-off branch passes the same value so the two branches differ only in input.
- **Validate**: Covered by Task 7.

### Task 7: Existing stubs and signature pins (F-2)

- **Files**: `tests/test_query_pipeline_run_conversation.py`, `tests/test_chat_state.py`, `tests/test_chat_history_send.py`, `tests/test_chat_outcomes_regression.py`, `tests/test_rbac.py`
- **Action**: UPDATE
- **Implement**: Make exactly the edits in the F-2 table. In `_stub_pipeline`, the `run_query` shim is `def _via_query(*args, ingress=None, **kwargs): return fake(*args, **kwargs)`. It accepts `ingress` and drops it. Do not assert `ingress == "chat"` inside the shim: the stub's job is to stand in, and the new module asserts the value. Add one sentence to each touched docstring or comment citing PRD-013 STORY-005.
- **Validate**: `python -m pytest tests/test_query_pipeline_run_conversation.py tests/test_chat_state.py tests/test_chat_history_send.py tests/test_chat_outcomes_regression.py tests/test_rbac.py tests/test_pipeline_concurrency.py -q`

### Task 8: `tests/test_query_pipeline_audit_fields.py`

- **File**: `tests/test_query_pipeline_audit_fields.py`
- **Action**: CREATE
- **Implement**: Module docstring: PRD-013 STORY-005, which AC each section covers, and that rows are read through `get_audit_log` (the characterization rule). Sections:
  1. **AC 1, every arm.** Import `ARM_CASES`, `_drive`, `_audit_rows_since`, `_last_audit_id`, `_CONVERSATION`, `_INJECTED_CONVERSATION`, `_ANALYST`, `_AUDITOR` and `_TOKENS` from `tests.test_audit_characterization`. Add a fixture or helper that patches `query_pipeline.run_conversation` with a wrapper. The wrapper adds `ingress="v1", streamed=True` and wraps `call_openrouter` to `dataclasses.replace` the result with `input_tokens=30, output_tokens=12`. If the wrapped stub raises, the error propagates unchanged. `_fail_if_called` still fails. Write a table `_NEW_FIELDS[arm]` giving, per written row, `message_count` (3 for every arm), `conversation_key` (`conversation_key(user, msgs)` for the arm's identity and conversation), the token pair, and `has_tool_calls`. The token pair is `(30, 12)` on the success row, the output-redaction-error row and the seed success row of `duplicate`/`pattern-flag`, and `(None, None)` everywhere else, upstream-error included. `has_tool_calls` is `False` on all rows. Parametrize over `ARM_CASES`. For each row, assert `ingress == "v1"`, `streamed is True`, `limit_exceeded is None` and the per-row expectations. Also assert `len(_NEW_FIELDS) == len(ARM_CASES)`, so a 13th arm cannot be added silently.
  2. **AC 1, the default.** One parametrized test runs `_drive` unwrapped and asserts `ingress is None`, `streamed is False`, and `message_count`/`conversation_key` set. This covers the direct-call path PRD 6.9 calls honest.
  3. **`_deny` requires the four.** For each of `ingress`, `message_count`, `conversation_key` and `streamed`: `inspect.signature(query_pipeline._deny).parameters[name].default is inspect.Parameter.empty`.
  4. **AC 2, `/query`.** Use `TestClient` with `call_openrouter` patched as `test_query_router.py` does. A success and a pattern-blocked request each give `ingress == "query"`, `message_count == 1` and `conversation_key == conversation_key(uid, [Message("user", prompt)])`. The foreign-session refusal (canonical UUID4, as `test_query_router.py:819`) gives `ingress == "query"`, `message_count == 1` and `conversation_key is None`.
  5. **AC 3, chat.** Mirror `tests/test_chat_history_send.py`'s `temp_db` override, `_make_state` and `_send`, importing them from that module. Stub `query_pipeline.redact` with a pass-through so no model loads, and patch `chat_state_mod.call_openrouter`. Wrap the real `chat_state_mod.run_conversation` and `run_query` to record `len(messages)`, or 1 for `run_query`. Send four times. The rows give `ingress == "chat"` on all four and `message_count == [1, 3, 5, 7]`, equal to the recorded lengths (F-5). A second test: history off (`CHAT_HISTORY_ENABLED=False`), two sends, both rows `ingress == "chat"` and `message_count == 1`.
  6. **AC 4 / MVP.** Build 50 growing conversations: `system` + `user`, then `assistant` + `user` per turn. Turn 50 carries 100 messages, which is exactly the default `CONTEXT_MAX_MESSAGES` and so admitted under the strict `>`. Pin the setting to 100 in the test so a changed default cannot turn turn 50 into a context-limit row. Run each through `query_pipeline.run_conversation(..., ingress="v1")` with a pass-through `redact` and a stub upstream. Assert 50 new rows, `len({conversation_key}) == 1`, `len({dedup_key}) == 50`, every `ingress == "v1"`, every `success` true, and `message_count == len(that turn's conversation)` (2, 4, …, 100). Also assert each `prompt_hash == hash_prompt(that turn's last user content)` (PRD 11 MVP; 6.4).
  7. **AC 5, the scan.** An `ast` walk over `app/**/*.py` and `chat_ui/**/*.py` (F-3). (a) Every pipeline call has an `ingress` keyword. The only exemption is the call inside `run_query`'s own `FunctionDef`, matched by enclosing function name. Assert the found sites are exactly the four in F-3. (b) Every `Call` to `log_query`, by `Name` or `Attribute`, has `ingress`, `message_count` and `conversation_key` keywords. Assert the site count is 11: ten in the pipeline and one in the router.
- **Mirror**: `tests/test_audit_characterization.py:280-345` (arms), `tests/test_chat_history_send.py:51-90` (chat), `tests/test_chat_sessions.py:1225-1245` (scan), `tests/test_conversation_key.py:62-71` (50 turns)
- **Validate**: `python -m pytest tests/test_query_pipeline_audit_fields.py -q`

### Task 9: Full suite

- **Action**: none
- **Validate**: `python -m pytest -q` passes. The count is the Task 1 baseline plus the new tests. The only existing files edited are those in F-2 plus `tests/test_audit_logger.py`, which only had tests added. `git diff --stat tests/test_audit_characterization.py` is empty.

---

## End-to-End Tests

- [ ] Start the API, `POST /query` with a user token. In `GET /audit` the new row's raw DB values show `ingress='query'`, `message_count=1`, a 64-hex `conversation_key` and `streamed=0`, and `input_tokens`/`output_tokens` are set when the live provider reports them. `/audit` does not project these fields until STORY-006, so read them with `sqlite3`/libSQL shell on `audit_logs`.
- [ ] In the chat UI, send three times in one chat. The three rows have `ingress='chat'` and `message_count` 1, 3, 5.

---

## Validation

```bash
python -m pytest tests/test_audit_logger.py tests/test_query_pipeline_audit_fields.py -q
python -m pytest tests/test_audit_characterization.py tests/test_query_pipeline_run_conversation.py -q
python -m pytest -q
git diff --stat tests/test_audit_characterization.py   # empty
```

A `StorageError ... tcp connect error` in a test that passes on its own is the known libSQL flakiness. On mass fixture errors, restart `harness-libsql-dev` before looking at code.

---

## Acceptance Criteria

(Copied from story `STORY-005`)

- [ ] Given any arm of `run_conversation`, when it writes a row, then the row has `ingress` (as passed), `message_count == len(messages)`, a non-NULL `conversation_key` and `streamed` (as passed); the success and output-redaction-error rows also have `input_tokens` and `output_tokens`, and the upstream-error row has neither.
- [ ] Given `POST /query`, when it succeeds or is blocked, then its row has `ingress='query'` and `message_count=1`; given the foreign-session refusal, then its row has `ingress='query'`, `message_count=1` and `conversation_key` NULL.
- [ ] Given a chat send with history and one without, when each writes its row, then both have `ingress='chat'`, and the Nth send of a session with nothing trimmed has `message_count == 2N-1`.
- [ ] Given a 50-turn conversation run through `run_conversation(ingress="v1")`, when the audit is read, then there are 50 rows with one `conversation_key`, 50 distinct `dedup_key` values and `ingress='v1'` on each.
- [ ] Given the production sources under `app/` and `chat_ui/`, when the scan test runs, then every call to `run_conversation` or `run_query` passes `ingress` explicitly or is `run_query`'s own delegation, and every direct `log_query` call passes `ingress`, `message_count` and `conversation_key`.
- [ ] All tasks completed
- [ ] Full suite passes; `tests/test_audit_characterization.py` unedited
- [ ] Follows existing patterns
