---
story: STORY-014
prd: PRD-013
slug: chat-usage-limit-bubble
title: "Chat UI usage-limit bubble"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-013-audit-and-usage-limits   # all stories commit here, no per-story branch
created: 2026-10-19
---

# Plan: Chat UI usage-limit bubble

## Summary

Replace STORY-011's interim arm in `ChatState._do_send` (`chat_ui/chat_ui/state.py:1273-1284`), which renders a `QueryBlockedUsageLimitResponse` as an `internal_error` bubble, with a real `usage_limit` bubble. The bubble is one more arm of the `rx.match` in `components/chat.py`, drawn by a new `render_usage_limit` in `components/bubbles.py` and modeled on `render_context_limit`: the `INK_HELD`/`TINT_HELD` pair, a panel, one sentence, no recovery action. The sentence is built in Python when the bubble is built, by a new `formatting.format_usage_limit_notice(limit, resets_at)`, and stored whole in `detail`. `content` keeps the pipeline's `reason`, as `context_limit` does. Persistence needs no new code: `_to_stored_message` and `_to_chat_message` already round-trip `content` and `detail` for every kind, so this story proves it with tests rather than editing the mappers. History exclusion holds by construction (`chat_history.assemble` reads only `assistant` rows), and the new test proves it end to end through the real pipeline. `UsageLimitError` already routes to `internal_error` (`state.py:1170`). This story keeps that route and pins it again in the new test file.

## User Story

As an end user
I want to be told plainly when I have reached a usage limit and when I can send again
So that I do not keep retrying

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-014-chat-usage-limit-bubble.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md` (Sections 5 story 8, 6.7, 6.10, F14)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui` (state, models, copy, formatting, bubbles, chat), tests |
| Story | STORY-014 |
| PRD | PRD-013 |
| Depends on | STORY-011 (✅ done, `8dc6b4d`) |
| Blocks | STORY-018 |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `frontend-design` | *"Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built."* The copy says "usage limit" and "sending too fast", never "rate limit", "quota", "tokens" or "requests". | Task 1, Task 6 |
| `frontend-design` | *"Treat failure and emptiness as moments for direction, not mood… Errors don't apologize, and they are never vague about what happened."* Each sentence says what happened and when the person can continue, with no apology. | Task 1, Task 6 |
| `frontend-design` | *"Spend your boldness in one place… keep everything around it quiet."* PRD 6.10 forbids a new visual direction. The bubble reuses `_entry`/`_rail`/`_tag`/`_panel`/`_prose` and a contrast-covered ink pair. It adds no colour, no motion and no layout. | Task 4 |
| `frontend-design` | *"Let each element do exactly one job."* One prose line, no detail line, no action button. The sentence already carries the reset time. | Task 4 |

---

## Design Decisions

**D-A: the finished sentence lives in `detail`, and `content` keeps `result.reason`.** The story allows either "the finished sentence, or the limit plus the formatted time". The finished sentence wins for three reasons:
- It is what the second AC compares ("the same bubble is restored with the same text").
- It needs no render-time branching on a Var.
- It mirrors `context_limit`, where `content` holds the pipeline reason so that the row and the audit agree, and `detail` holds the reader-facing text built at send time (`state.py:1243-1272`).

No column is added.

**D-B: `INK_HELD` / `TINT_HELD`.** These are the same pigments, and the same reasoning, as `render_context_limit` (`bubbles.py:353-369`). `INK_FORBIDDEN` is below AA on the light ground and is absent from `_INK_ON_TINT` (`tests/test_contrast.py:140-146`). "Held, not rejected" is also the true meaning: nothing is wrong with the prompt, and the person waits.

**D-C: no Retry action.** A Retry button is the "keep retrying" invitation the user story exists to remove. On `tokens`, retrying cannot succeed before 00:00 UTC. On `requests`, the sentence already tells the person what to do. The composer is always on screen. This is `render_context_limit`'s "no bubble-local duplicate of a control" argument.

**D-D: tag `TAG_USAGE_LIMIT = "PAUSED"`.** Tags are the interface's verdict vocabulary, upper case and short. The existing tags are YOU, CLEARED, HELD, DENIED, FORBIDDEN, UPSTREAM, FAULT and TOO LONG. HELD is already the duplicate kind. "PAUSED" describes the state the person is in, in their terms, and fits both limits. It names no mechanism such as LIMIT, QUOTA or RATE. It is the one word this plan chooses rather than the PRD, so Task 6 pins it in one assertion. If review prefers another word, the change is one line plus that assertion.

**D-E: the copy map is indexed, not `.get()`.** `USAGE_LIMIT_NOTICES = {"tokens": …, "requests": …}`. A test pins the keys to `QueryBlockedUsageLimitResponse.limit`'s `Literal`, so a third limit added later without copy fails CI and does not fail silently. This mirrors `CONTEXT_LIMIT_UNITS` and `test_every_limit_value_has_a_unit_and_nothing_else_does` (`tests/test_copy.py:1076-1090`).

**D-F: the reset time is formatted, not hard-coded.** PRD F14 asks for "`resets_at` formatted in UTC by the existing formatting helpers". The `tokens` template carries `{reset}`. `format_usage_limit_notice` parses `resets_at` (`_TIMESTAMP_FORMAT`, `"%Y-%m-%dT%H:%M:%SZ"`, so it can reuse the `fromisoformat(… .replace("Z", "+00:00"))` idiom from `format_duplicate_info`) and renders `%H:%M`. By construction (`usage_limits._next_utc_midnight`) that is always `00:00`, so the AC text holds exactly. An unparseable value falls back to `"00:00"`, the only value the gate can produce, so a bad timestamp never costs the bubble. The `requests` notice has no placeholder. Passing `reset=` to its `.format()` is harmless, so one code path serves both.

**D-G: `UsageLimitError` keeps the existing route.** It stays in `except (DuplicateCheckError, PiiRedactorError, UsageLimitError)` at `state.py:1170`, and that already satisfies AC 4. The `finally` already clears `pending`. No code change is needed. The existing pin `test_chat_state_send_usage_limit_error_appends_internal_error_bubble` stays, and the new file restates it against the AC.

**D-H: the interim test is deleted, not edited.** `test_chat_state_send_usage_limit_renders_the_interim_internal_error_bubble` (`tests/test_chat_state.py:476-511`) says in its docstring that STORY-014 "is expected to delete this test and assert the `usage_limit` bubble instead". It is an `async def`, so `tests/test_untouched_app.py`'s census regex `^def (test_\w+)` never counted it, and removing it does not trip the census. Its replacement goes in the same place under the PRD-010 STORY-013 precedent (`tests/test_chat_state.py:309-350`, "replaces STORY-008's interim … pin").

---

## Patterns to Follow

### Naming / the precedent arm
```python
# SOURCE: chat_ui/chat_ui/state.py:1243-1272
elif isinstance(result, QueryBlockedContextLimitResponse):
    bubble = ChatMessage(
        kind="context_limit",
        # The pipeline's reason, stored but not shown: ...
        content=result.reason,
        prompt=text,
        detail=CONTEXT_LIMIT_DETAIL_TEMPLATE.format(
            unit=CONTEXT_LIMIT_UNITS[result.limit],
            actual=result.actual,
            maximum=result.maximum,
        ),
    )
```

### The interim arm this story removes
```python
# SOURCE: chat_ui/chat_ui/state.py:1273-1284
elif isinstance(result, QueryBlockedUsageLimitResponse):
    # Interim (PRD-013 STORY-011): routed through the existing
    # internal-error bubble ... STORY-014 replaces this arm ...
    bubble = ChatMessage(
        kind="internal_error",
        content="internal_error",
        prompt=text,
        detail=f"{result.reason}: {result.limit}, resets at {result.resets_at}",
    )
```

### Renderer
```python
# SOURCE: chat_ui/chat_ui/components/bubbles.py:353-402
def render_context_limit(message) -> rx.Component:
    ink, tint = theme.INK_HELD, theme.TINT_HELD
    return _entry(
        message,
        _rail(ink),
        _tag(copy.TAG_CONTEXT_LIMIT, ink),
        _panel(ink, tint, _prose(copy.CONTEXT_LIMIT_HEADLINE), ...),
    )
```

### Dispatcher
```python
# SOURCE: chat_ui/chat_ui/components/chat.py:32-43
return rx.match(
    message.kind,
    ...
    ("context_limit", render_context_limit(message)),
    ("upstream_error", render_upstream_error(message)),
    ("internal_error", render_internal_error(message)),
    render_fallback(message),
)
```

### Formatting helper (pure, runs at build time)
```python
# SOURCE: chat_ui/chat_ui/formatting.py:64-80
def format_duplicate_info(first_query_at: str) -> tuple[str, str]:
    if not first_query_at:
        return DUPLICATE_FALLBACK_TEXT, ""
    try:
        dt = datetime.fromisoformat(first_query_at.replace("Z", "+00:00"))
        ...
```

### Copy block, appended with its rationale comment
```python
# SOURCE: chat_ui/chat_ui/copy.py:114-137 (CONTEXT_LIMIT_* and CONTEXT_LIMIT_UNITS)
```

### Error handling
```python
# SOURCE: chat_ui/chat_ui/state.py:1166-1180 -- named exceptions to internal_error, unchanged
except (DuplicateCheckError, PiiRedactorError, UsageLimitError) as exc:
    await self._append_and_persist(ChatMessage(kind="internal_error", ...), identity, session_id)
    return
```

### Tests
```python
# SOURCE: tests/test_context_limit_bubble.py:56-133 -- source-text assertions on chat.py/bubbles.py/state.py,
#   no in-process import of chat_ui.components.* (the module docstring says why)
# SOURCE: tests/test_chat_state.py:3268-3313 -- restored bubble keeps copy and restored=True, via _restore()
# SOURCE: tests/test_chat_history_send.py:55-133, 390-447 -- _make_state/_send/_capturing_run_conversation;
#   refused turn absent from the next send's messages, real pipeline, only call_openrouter faked
# SOURCE: tests/test_copy.py:970-1120 -- appended vocabulary block; non-empty first, then absence checks
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/copy.py` | UPDATE | `TAG_USAGE_LIMIT`, `USAGE_LIMIT_TOKENS_TEMPLATE`, `USAGE_LIMIT_REQUESTS_NOTICE`, `USAGE_LIMIT_NOTICES` |
| `chat_ui/chat_ui/formatting.py` | UPDATE | `format_usage_limit_notice(limit, resets_at) -> str` |
| `chat_ui/chat_ui/models.py` | UPDATE | Comment-only: `usage_limit` uses `content` (reason) and `detail` (finished sentence). No new field, because `kind` is a free `str` |
| `chat_ui/chat_ui/state.py` | UPDATE | Replace the interim arm with `kind="usage_limit"`, and update the catch-all comment |
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | `render_usage_limit`; module docstring kind count |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | Import, plus a `("usage_limit", render_usage_limit(message))` arm above the default; update the docstring |
| `app/services/chat_history.py` | UPDATE | Docstring only: add `usage_limit` to the D4 list of kinds that are never read |
| `tests/test_usage_bubble.py` | CREATE | The story's test file (ACs 1–5) |
| `tests/test_chat_state.py` | UPDATE | Delete the interim pin (D-H) and add the replacement. Extend both round-trip parametrizations with a `usage_limit` case. Extend only, never edit existing assertions |
| `tests/test_copy.py` | UPDATE | Append the STORY-014 vocabulary block. Appended only (census suite) |
| `tests/test_chat_components_import.py` | UPDATE | Add `render_usage_limit` and `usage_limit` to the probe's lists |
| `tests/test_chat_history.py` | UPDATE | Add `("usage_limit", {"detail": …})` to `UNANSWERED_KINDS` |

No change to `_to_stored_message`, `_to_chat_message` or `_append_and_persist`, because they are kind-agnostic for `content` and `detail` (`state.py:42-130`). The story's "persistence through `_append_and_persist` and the stored-message mappers" is satisfied because the new arm ends at the shared `await self._append_and_persist(bubble, …)` at `state.py:1301`. Tasks 7 and 8 prove it.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

Python: `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe` (aliased below as `$PY`). The DB-backed tests need the `harness-libsql-dev` container running on `127.0.0.1:8080`.

### Task 1: Copy

- **File**: `chat_ui/chat_ui/copy.py`
- **Action**: UPDATE
- **Implement**:
  - In the verdict-tags block after `TAG_CONTEXT_LIMIT`, add `TAG_USAGE_LIMIT = "PAUSED"`.
  - Add a new `# --- Usage limits ---` block right after the context-limit block (after line 137), with a rationale comment in the file's voice. The comment should cite PRD-013 Section 6.10 and the two `frontend-design` rules verbatim, and say why neither sentence says "rate limit", "quota", "tokens" or "requests" (the names of settings, not of the problem) or apologizes.
    ```python
    USAGE_LIMIT_TOKENS_TEMPLATE = (
        "You've reached today's usage limit. You can send again after {reset} UTC."
    )
    USAGE_LIMIT_REQUESTS_NOTICE = "You're sending too fast. Wait a minute, then send again."
    # Keyed by QueryBlockedUsageLimitResponse.limit; indexed, never .get(), and a
    # test pins the keys to the schema's Literal (the CONTEXT_LIMIT_UNITS rule).
    USAGE_LIMIT_NOTICES = {
        "tokens": USAGE_LIMIT_TOKENS_TEMPLATE,
        "requests": USAGE_LIMIT_REQUESTS_NOTICE,
    }
    ```
  - The apostrophes are straight ASCII `'`, because the AC quotes them that way.
- **Mirror**: `copy.py:114-137`
- **Validate**: `$PY -c "import sys; sys.path.insert(0,'.'); from chat_ui.chat_ui import copy; print(copy.USAGE_LIMIT_NOTICES)"`

### Task 2: Formatting helper

- **File**: `chat_ui/chat_ui/formatting.py`
- **Action**: UPDATE
- **Implement**: `format_usage_limit_notice(limit: str, resets_at: str) -> str`.
  - Parse `resets_at` with `datetime.fromisoformat(resets_at.replace("Z", "+00:00"))`.
  - Convert to UTC and format `"%H:%M"`.
  - On `ValueError`/`AttributeError`, or an empty string, use `"00:00"` (D-F). Write the comment: the gate only ever produces next-midnight for `tokens`, so the fallback is that value, never a vaguer sentence.
  - Return `USAGE_LIMIT_NOTICES[limit].format(reset=reset)`. Index it so an unknown limit raises `KeyError`, which `_do_send`'s bare `except` would not see, because this runs after the `try`. That is acceptable only because Task 6 pins the keys to the schema. Say so in the docstring.
  - Import the two new names from `.copy`.
  - Module docstring: one sentence adding this helper to the list.
- **Mirror**: `formatting.py:64-94` (`format_duplicate_info`'s parse and fallback shape)
- **Validate**: `$PY -m pytest tests/test_copy.py -q` (unchanged suite still green)

### Task 3: State arm

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**:
  - Replace lines 1273-1284 with:
    ```python
    elif isinstance(result, QueryBlockedUsageLimitResponse):
        bubble = ChatMessage(
            kind="usage_limit",
            # The pipeline's reason, stored but not shown -- the context_limit split.
            content=result.reason,
            prompt=text,
            # The finished sentence, built here because components receive Vars
            # (admin_models.py's note), and stored whole so a restored bubble
            # reads exactly as the live one did (PRD-013 Section 6.10, D-A).
            detail=format_usage_limit_notice(result.limit, result.resets_at),
        )
    ```
  - Import `format_usage_limit_notice` on the existing `.formatting` import line (`state.py:39`).
  - Rewrite the catch-all comment at 1286-1293. Remove "routed to an interim bubble until STORY-014", keep "six members", and credit PRD-013 STORY-011 with the sixth member and STORY-014 with its bubble.
  - Leave the `except (…, UsageLimitError)` arm at 1170 and its comment as they are (D-G).
- **Validate**: `grep -n "Interim (PRD-013 STORY-011)" chat_ui/chat_ui/state.py` returns nothing, and `$PY -m pytest tests/test_chat_state.py -q -k "usage"` runs. Expect the interim pin to fail until Task 7.

### Task 4: Renderer

- **File**: `chat_ui/chat_ui/components/bubbles.py`
- **Action**: UPDATE
- **Implement**:
  - Add `render_usage_limit(message)` directly after `render_context_limit`:
    ```python
    ink, tint = theme.INK_HELD, theme.TINT_HELD
    return _entry(
        message,
        _rail(ink),
        _tag(copy.TAG_USAGE_LIMIT, ink),
        _panel(ink, tint, _prose(message.detail)),
    )
    ```
  - Docstring:
    - D-B: the pigment and its contrast reason, with a pointer to `render_context_limit`.
    - D-C: why there is no action.
    - Why it renders `message.detail` where `render_context_limit` renders a constant: the sentence depends on the limit and the reset, so it is built at send time, and every word in it still comes from `copy.py`.
  - Write no string literal.
  - Module docstring line 1: "The six ledger entries" is already stale. Leave it, or correct it to the real count only if the reviewer wants that. This is not required.
- **Mirror**: `bubbles.py:353-402`
- **Validate**: covered by Task 5's probe.

### Task 5: Dispatcher

- **File**: `chat_ui/chat_ui/components/chat.py`
- **Action**: UPDATE
- **Implement**:
  - Add `render_usage_limit,` to the import block in alphabetical position (after `render_upstream_error`, before `render_user`).
  - Add `("usage_limit", render_usage_limit(message)),` right after the `context_limit` arm, with the blocks and above `render_fallback`.
  - Extend the docstring: the eighth outcome is one more arm, and `usage_limit` sits with the blocks because it is a `BLOCKED` refusal, not a fault.
- **Mirror**: `chat.py:21-43`
- **Validate**: update `tests/test_chat_components_import.py` first. Add `"render_usage_limit"` to the renderer tuple (lines 31-41) and `"usage_limit"` to the kinds tuple (around line 53), each with a `# PRD-013 STORY-014` comment. Then run `$PY -m pytest tests/test_chat_components_import.py -q`.

### Task 6: Copy tests (append-only)

- **File**: `tests/test_copy.py`
- **Action**: UPDATE (append a `# --- PRD-013 STORY-014: the usage-limit bubble ---` banner at the end, stating that nothing above changes, as the STORY-013 banner at line 970 does)
- **Implement**:
  - `_USAGE_LIMIT_VOCABULARY = (TAG_USAGE_LIMIT, USAGE_LIMIT_TOKENS_TEMPLATE, USAGE_LIMIT_REQUESTS_NOTICE)`.
  - `test_every_usage_limit_string_exists_and_is_not_empty`.
  - `test_the_usage_limit_copy_is_the_wording_the_prd_fixed`: `USAGE_LIMIT_TOKENS_TEMPLATE.format(reset="00:00") == "You've reached today's usage limit. You can send again after 00:00 UTC."`, `USAGE_LIMIT_REQUESTS_NOTICE == "You're sending too fast. Wait a minute, then send again."`, and `TAG_USAGE_LIMIT == "PAUSED"` (D-D).
  - `test_the_usage_limit_copy_names_no_mechanism_and_does_not_apologize`. Assert non-empty first. Then, lower-cased, assert none of `"rate limit"`, `"quota exceeded"`, `"quota"`, `"sorry"`, `"oops"`, `"apolog"`, `"unfortunately"`, `"token"`, `"request"` appear (the AC's four words plus the mechanism names), and that none of the vague phrases from `test_the_context_limit_copy_names_no_mechanism_and_does_not_apologize` appear. Prose is sentence case. The tag is upper case.
  - `test_every_usage_limit_value_has_a_notice_and_nothing_else_does`: `set(USAGE_LIMIT_NOTICES) == set(get_args(QueryBlockedUsageLimitResponse.model_fields["limit"].annotation))` (D-E).
  - `test_the_usage_limit_tokens_notice_formats_the_reset_in_utc`: `format_usage_limit_notice("tokens", "2026-10-20T00:00:00Z")` equals the AC string. An unparseable `"garbage"` and `""` return the same string (D-F). `"requests"` with any `resets_at` returns the requests notice exactly.
- **Mirror**: `tests/test_copy.py:970-1120`
- **Validate**: `$PY -m pytest tests/test_copy.py tests/test_untouched_app.py -q`

### Task 7: ChatState tests (extend `test_chat_state.py`)

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**:
  1. Delete `test_chat_state_send_usage_limit_renders_the_interim_internal_error_bubble` (lines 476-511, D-H). In its place add `test_chat_state_send_usage_limit_renders_a_usage_limit_bubble`, parametrized over `tokens` and `requests`. It stubs `QueryBlockedUsageLimitResponse(reason="Usage limit reached", limit=…, maximum=…, actual=…, resets_at=…)` and asserts `kind == "usage_limit"`, `content == "Usage limit reached"`, `detail ==` the exact AC sentence, `prompt == "hello world"` and `pending is False`. Its docstring: "PRD-013 STORY-014: replaces STORY-011's interim `internal_error` pin", in the style of `:310-330`.
  2. Add a `usage_limit` case (the `tokens` variant) to both parametrized round-trip tests, `test_every_bubble_kind_is_persisted` (`:1530-1556`) and `test_every_bubble_kind_survives_the_round_trip` (`:1905-1932`). Add the entry to both the tuple list and `ids`, with a `# PRD-013 STORY-014` comment. Extend only, and change no existing case.
  3. Leave `test_chat_state_send_usage_limit_error_appends_internal_error_bubble` (`:455-474`) untouched (AC 4 is already pinned).
- **Mirror**: `tests/test_chat_state.py:309-350`, `:3268-3313`
- **Validate**: `$PY -m pytest tests/test_chat_state.py tests/test_untouched_app.py -q`

### Task 8: The story's test file

- **File**: `tests/test_usage_bubble.py`
- **Action**: CREATE
- **Implement**: The module docstring maps each test to its AC and repeats the reason for using source-text assertions with no in-process `chat_ui.components` import (copy it from `tests/test_context_limit_bubble.py:19-26`). Use local helpers (`_make_state`, `_send`, `temp_db` fixture inserting the auth user, `_stub_pipeline`), copied from `tests/test_chat_history_send.py:55-133`, as that file does, rather than imported from another test module.
  - **AC 1, live text.** Parametrize over `("tokens", "2026-10-20T00:00:00Z", <AC sentence 1>)` and `("requests", "2026-10-19T14:23:00Z", <AC sentence 2>)`. Stub the pipeline to return the refusal. After one send, `state.messages[-1]` has `kind == "usage_limit"` and `detail == expected`. Exactly one `usage_limit` bubble is in `state.messages`, and no `internal_error` bubble is.
  - **AC 2, reload.** Make two sends (the first one's user bubble predates the lazy create, as `tests/test_chat_state.py:1934-1945` explains), each refused with the same limit. Then rebuild a fresh `ChatState` and restore the session (mirror `_restore` at `tests/test_chat_state.py:1850`). Every restored `usage_limit` bubble has the identical `detail` and `content`, and `restored is True`. Run it for both limits.
  - **AC 3, history, through the real pipeline.** Use the **token budget**, not the rate. The rate window is derived from the database clock in `admit_usage`'s SQL (`app/db/database.py:1680-1700`), so it cannot be frozen, and a minute boundary between two sends would flake the test. The budget only rolls at 00:00 UTC.
    1. Set `settings.USAGE_LIMITS_ENABLED=True` and `settings.USAGE_DAILY_TOKEN_BUDGET="*=1"` with `monkeypatch.setattr` (read per call, per PRD 6.12).
    2. Fake only `call_openrouter`. `_fake_call_openrouter` returns `tokens_used=12`, which STORY-012 charges.
    3. Send "an answered question". It is admitted and charged 12 tokens, which is over the budget of 1.
    4. Send "the refused question". Assert the last bubble is `usage_limit` and its `detail` is the `tokens` sentence.
    5. Swap in `_capturing_run_conversation` (from `tests/test_chat_history_send.py:92-112`) and send "a fresh question". The stub bypasses the gate.
    6. Assert "the refused question" is in no captured message, and that the bubble's sentence is in none either.
    7. Assert "an answered question" appears exactly once, and that the last pair is `("user", "a fresh question")`.

    The docstring states why the budget and not the rate, and that the test is safe except at 00:00 UTC exactly.
  - **AC 4, counter failure.** Stub the pipeline to raise `UsageLimitError("Usage admission failed: counter unreachable")`. Assert the last bubble is `internal_error` with that `detail`, `pending is False`, and no `usage_limit` bubble.
  - **AC 5, structure and residue.** These are source-text assertions in the `test_context_limit_bubble.py` shape, over `chat.py`, `bubbles.py` and `state.py`:
    - `("usage_limit", render_usage_limit(message))` is in `chat.py` and comes before `rindex("render_fallback(message)")`.
    - `render_usage_limit,` is in the import block.
    - The `render_usage_limit` body, sliced to the next top-level `def`, draws exactly `{"INK_HELD", "TINT_HELD"}`, and that pair is in `tests.test_contrast._INK_ON_TINT`.
    - The body names `copy.TAG_USAGE_LIMIT`, and no `USAGE_LIMIT_*`/`TAG_USAGE_LIMIT` value appears as a literal in `bubbles.py`.
    - `kind="usage_limit"` appears in `state.py`.
    - **Interim gone:** `"Interim (PRD-013 STORY-011)"` is not in `state.py`. The source of the `QueryBlockedUsageLimitResponse` arm, sliced from its `elif isinstance(result, QueryBlockedUsageLimitResponse)` to the next `else:`/`elif`, contains no `"internal_error"`. `"until STORY-014"` is not in `state.py`.
    - **Rendered copy:** for both limits, `format_usage_limit_notice(...)`, lower-cased, contains none of `"rate limit"`, `"quota exceeded"`, `"sorry"`, `"oops"`.
- **Mirror**: `tests/test_context_limit_bubble.py`, `tests/test_chat_history_send.py:390-447`
- **Validate**: `$PY -m pytest tests/test_usage_bubble.py -q`

### Task 9: History docs and fixture

- **Files**: `app/services/chat_history.py`, `tests/test_chat_history.py`, `chat_ui/chat_ui/models.py`
- **Action**: UPDATE
- **Implement**:
  - Docstring lines 21-27: add `usage_limit` to the list of kinds that are never read (PRD-013 STORY-014). This changes no code.
  - Append `("usage_limit", {"detail": "You're sending too fast. Wait a minute, then send again."})` to `UNANSWERED_KINDS` (`tests/test_chat_history.py:52-60`), with a comment.
  - `models.py`: one comment line by `detail` saying it also carries the usage-limit sentence (D-A).
- **Validate**: `$PY -m pytest tests/test_chat_history.py -q`

### Task 10: Full regression

- **Validate**: `$PY -m pytest tests/ -q`. If fixture errors appear across the suite, restart the libSQL container rather than bisecting (PRD 11, Quality indicators). `tests/test_chat_sessions.py` has a known intermittent flake (PRE-PRD-017), so rerun it before blaming the change. No assertion may change in `test_chat_outcomes_regression.py`, `test_query_outcomes_regression.py` rows 1–7 or `test_untouched_app.py`.

---

## End-to-End Tests

- [ ] `$PY -m pytest tests/test_usage_bubble.py tests/test_copy.py tests/test_chat_state.py tests/test_chat_components_import.py tests/test_chat_history.py tests/test_context_limit_bubble.py tests/test_contrast.py tests/test_untouched_app.py -q` all pass
- [ ] Run the chat UI (`cd chat_ui && reflex run`) with `USAGE_REQUESTS_PER_MINUTE=*=1`. Sign in and send twice within a minute. The second send shows one PAUSED bubble reading "You're sending too fast. Wait a minute, then send again." in the HELD ink, with no Retry button. Reload, reopen the chat, and the same bubble is there and does not animate in
- [ ] With `USAGE_DAILY_TOKEN_BUDGET=*=1`, after one answered send, the next send shows "You've reached today's usage limit. You can send again after 00:00 UTC."
- [ ] After either bubble, a fresh send that is admitted does not repeat the refused prompt back. Check via the audit `message_count`, or by asking the model what was said before
- [ ] Both themes: the bubble's text is legible on the light and dark grounds (covered by `_INK_ON_TINT`, eyeball once)

OpenRouter is unreachable from this machine (TLS/401), so the browser E2E can only reach the refusal paths. That is enough here, because both bubbles are produced before the upstream call. The admitted "fresh send" check in the fourth item can only be confirmed through the test in Task 8.

---

## Validation

```bash
PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
docker start harness-libsql-dev
$PY -m pytest tests/test_usage_bubble.py -q
$PY -m pytest tests/ -q
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| The real-pipeline history test (AC 3) flakes on a window boundary | It uses the token budget (`*=1`), which rolls only at 00:00 UTC. The rate window follows the DB clock and cannot be frozen (Task 8) |
| `format_usage_limit_notice` raises `KeyError` after the `try` in `_do_send` for a future third limit | D-E: the keys are pinned to the schema `Literal` in `test_copy.py`, so CI fails first |
| A pinned or census suite is tripped | `test_chat_state.py` and `test_copy.py` are only extended. The one deletion is an `async def` the census regex never counted (D-H). Run `test_untouched_app.py` in Tasks 6 and 7 |
| Importing `chat_ui.components` in-process breaks other modules | Source-text assertions only, plus the existing subprocess probe (`test_chat_components_import.py`) |
| The tag word "PAUSED" is a plan choice, not PRD copy | One constant and one assertion (D-D). Flag it in the report |

---

## Acceptance Criteria

(Copied from story `STORY-014`)

- [ ] Given a send refused with `limit="tokens"`, when the result arrives, then the thread shows one bubble reading "You've reached today's usage limit. You can send again after 00:00 UTC."; given `limit="requests"`, then it reads "You're sending too fast. Wait a minute, then send again."
- [ ] Given either bubble in a saved chat, when the page is reloaded and the chat reopened, then the same bubble is restored with the same text.
- [ ] Given a chat containing a usage-limit bubble, when the next send assembles history, then neither the bubble nor the user turn that caused it is sent to the model.
- [ ] Given `UsageLimitError` raised during a send, when it is handled, then the thread shows the existing internal-error bubble and `pending` is cleared.
- [ ] Given the bubble's rendered copy, when `tests/test_copy.py` and the render-invariant tests run, then the strings contain no "rate limit", "quota exceeded", "sorry" or "oops", and the temporary routing STORY-011 added is gone.
- [ ] All tasks completed
- [ ] Full suite green
- [ ] Follows existing patterns (`context_limit` bubble, `copy.py`/`formatting.py` split, append-only test suites)
