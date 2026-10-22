---
story: STORY-005
prd: PRD-015
slug: message-translation
title: "Request translation: messages, the developer role and edge structure checks"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-22
---

# Plan: Request translation: messages, the developer role and edge structure checks

## Summary

This story adds a new pure module, `app/services/v1_translate.py`. It defines `V1RequestError(code, message, param)`, the two code constants `INVALID_MESSAGES` and `TOOLS_NOT_SUPPORTED`, and `translate_messages(raw)`. The function takes the raw `messages` list from `ChatCompletionRequest.messages` and returns `(list[Message], frozenset[str])`: the normalized messages and the ignored names (`{"messages[].name"}` or empty).

It works in one pass over the list. For each message it:

1. refuses `tool_calls` / `function_call` keys and the `tool` role as `tools_not_supported`,
2. records a `name` key as ignored,
3. maps `developer` to `system` in a copy of the message (the input is never changed),
4. calls `normalize_message` and wraps any `MessageNormalizationError` as `invalid_messages` with the same text.

After the loop it runs the edge structure checks: the list is not empty and the last turn is `user`. These duplicate `query_pipeline._validate_conversation` on purpose, so `InvalidConversationError` cannot be reached from `/v1`.

Tests go in `tests/test_v1_translate_request.py`. They need no DB. They include a seeded random property test (hypothesis is not installed, and the plan adds no dependency) that feeds every accepted output to `_validate_conversation`.

## User Story

As an integrating developer
I want my client's `messages` array accepted in every text shape the standard allows and refused with a precise 400 when it is not text
So that my conversation reaches the pipeline intact and a bad one never becomes an unaudited 500

## Story Reference

- Story file: `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-005-message-translation.md`
- PRD: `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` (Sections 4 "Request translation", 6.3, 7.1, 7.5, 9.2 T6/T9)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/services/v1_translate.py` (new), `tests/test_v1_translate_request.py` (new) |
| Story | STORY-005 |
| PRD | PRD-015 |
| Epic Branch | `epic/PRD-015-openai-compatible-endpoint` (commit directly on this branch) |
| Depends on | STORY-004 (done, `0be7da0`) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | The only skill in `.agents/skills/` is `frontend-design`, which does not apply to a pure backend module. The story lists `skills: []`. | — |

---

## Patterns to Follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| PURE MODULE | `app/models/messages.py:1-9` | A docstring names the PRD section and says what the module is not: no I/O, no settings, no logging |
| ERROR CLASS | `app/models/messages.py:33-39` | An `Exception` subclass whose docstring states the rule: location and rule, never the value |
| WRAP AND KEEP TEXT | `app/models/messages.py:86-90` | `raise X(f"messages[{index}]: {exc}") from exc` |
| STRUCTURE RULES | `app/services/query_pipeline.py:69-75` | The three rules being mirrored: empty, `tool` role, last role not `user` |
| TABLE TESTS | `tests/test_messages.py:69-91, 94-130` | `pytest.mark.parametrize` with `ids=[...]`, one named case per rule |
| CANARY TESTS | `tests/test_messages.py:235-264` | A `_CANARY` string in every bad input, asserting that it is absent from `str(exc)` and `repr(exc.__cause__)` |
| PURITY TEST | `tests/test_messages.py:327-352` | An AST scan of the module's imports and names, not a substring search |
| ENV BOOTSTRAP | `tests/test_messages.py:11-14` | `os.environ.setdefault(...)` before any `app` import (the test imports `query_pipeline`, which imports `app.config`) |

### Wrap, keep the text
```python
# SOURCE: app/models/messages.py:85-90
    messages = []
    for index, item in enumerate(raw):
        try:
            messages.append(normalize_message(item))
        except MessageNormalizationError as exc:
            raise MessageNormalizationError(f"messages[{index}]: {exc}") from exc
```

### The rules being mirrored
```python
# SOURCE: app/services/query_pipeline.py:69-75
def _validate_conversation(messages: Sequence[Message]) -> None:
    if not messages:
        raise InvalidConversationError("messages must not be empty")
    if any(m.role == "tool" for m in messages):
        raise InvalidConversationError("tool turns are not supported (PRD-016)")
    if messages[-1].role != "user":
        raise InvalidConversationError("the last message must be a user turn")
```

### Canary test
```python
# SOURCE: tests/test_messages.py:259-264
    assert str(listed.value).startswith("messages[1]: ")
    for exc in (single.value, listed.value):
        assert "CANARY" not in str(exc)
        assert "CANARY" not in repr(exc.__cause__)
```

---

## Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Return shape | `translate_messages(raw) -> Tuple[List[Message], FrozenSet[str]]` | AC 2 asks for "the ignored names this function returns". A frozenset lets STORY-006 take a union with its own names, so each name is listed once (its technical notes). No new class for two values |
| Normalizer call | A per-item loop over `normalize_message`, with the `messages[{index}]: ` prefix added here | The wrap needs the index for `param`, and `MessageNormalizationError` does not carry it (parsing its text would be fragile). The loop is `normalize_messages`' own body, so the text stays the same, and the AC 1 equality test pins that the two stay equal |
| `developer` → `system` | Done on a copy, `{**raw, "role": "system"}`, before `normalize_message` | Technical notes: `Role` is not widened, and the normalizer would refuse `developer`. The input list and its dicts are never changed (tested) |
| `param` | `"messages"` for list-level failures (not a list, empty). `"messages[i]"` for every per-message failure, including "last is not user" (`i = len - 1`) | One predictable rule that the tests pin. Section 7.1 says `"messages[i]..."`. A deeper path such as `content[1]` is already in the message text, so the client sees it without a second format |
| Message text | Always `"<location>: <rule>"`. Normalizer failures keep the normalizer's own text (`messages[2]: content[1] is not a text part`). The edge checks use the pipeline's rule wording, prefixed by location | Technical notes: "wrap it, keep its text". Using the same wording as `_validate_conversation` makes the duplicate easy to see. No message ever interpolates a value (T6) |
| Codes | Module constants `INVALID_MESSAGES = "invalid_messages"` and `TOOLS_NOT_SUPPORTED = "tools_not_supported"` | Technical notes: "Use one constant". STORY-006 imports `TOOLS_NOT_SUPPORTED` for the `tools` refusal, so the two refusals can never be spelled differently |
| `tools_not_supported` triggers | The role `tool`, or the keys `tool_calls` or `function_call` present on a message (any value, including `[]` / `null`) | The normalizer refuses `tool_calls` on presence (`messages.py:75`), so this keeps its rule. `function_call` is the deprecated form of the same thing. Without this check, `{"role":"assistant","content":null,"function_call":{...}}` would normalize to `""`, the exact silent case `messages.py:73-74` guards against. A `function` **role** stays an unknown role (`invalid_messages`), as the story says |
| Check order per message | Not a mapping → normalizer error. Then `tool_calls` / `function_call` → `role == "tool"` → record `name` → map `developer` → `normalize_message` | The tool checks must run before the normalizer, or `tool_calls` would come back as `invalid_messages` (the normalizer raises its own PRD-016 error). Non-mapping items go straight to the normalizer so its "message is not an object" text is kept |
| Check order across the list | The list-type check comes first and empty second, both before the loop. Then the per-message checks, in index order. "Last is not user" comes last | The first failure wins. A `tool` turn at index 0 is reported before a bad last turn, so the client fixes the more basic problem first |
| `name` recording | Recorded when the key is present, whatever its value | Presence is what the client sent. STORY-006 records top-level keys the same way. Values are never recorded |
| Other per-message extra keys (`refusal`, `audio`, ...) | Ignored silently, as the normalizer already does. Not recorded | Out of scope: the story and Section 4 name only `name`. Noted as a risk below |
| `V1RequestError` | `Exception` subclass. `__init__(self, code, message, param=None)` stores `code`, `message`, `param` and calls `super().__init__(message)` | STORY-009/010 map it to `ErrorDetail(message, type="invalid_request_error", param, code)`. `str(exc)` is the message, like every other error in the codebase. `param` is optional, so STORY-006 can raise without one if needed |
| Logging | None in this module | Pure (Section 6.3). T9's INFO log line belongs to the router (STORY-009) |
| Property test engine | `random.Random(seed)` over 500 seeds through `pytest.mark.parametrize`, with no new dependency | `hypothesis` is not installed and not in `requirements.txt`. A seeded generator is deterministic and reproducible from the failing test id. The generator is biased so that about half the cases are accepted. A guard test asserts that at least 25% are accepted, so the property cannot pass on an empty set |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/v1_translate.py` | CREATE | `V1RequestError`, the code constants, `translate_messages` |
| `tests/test_v1_translate_request.py` | CREATE | Table tests for every AC, canary tests, a purity test, a non-mutation test, the property test |

`app/models/messages.py`, `app/services/query_pipeline.py` and `app/models/v1_schemas.py` are **not** changed. STORY-006 extends both new files later (`translate_request`, `V1Call`).

---

## Tasks

Execute in order. Each task is atomic and verifiable. Python is `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe` (below: `$PY`).

### Task 1: Module skeleton, error class and constants

- **File**: `app/services/v1_translate.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring: "Request translation for `/v1` (PRD-015 Sections 4 and 7.1)." Say that it is pure, like `app/models/messages.py`: no I/O, no settings reads, no logging. It turns the wire request into pipeline arguments, and every refusal is a `V1RequestError` that the router maps to a 400 (STORY-009/010). Say that STORY-006 adds parameter classification here.
  - Imports: `from typing import Any, FrozenSet, List, Mapping, Sequence, Tuple` and `from app.models.messages import Message, MessageNormalizationError, normalize_message`. Do **not** import `query_pipeline` (that would pull in settings and I/O).
  - `INVALID_MESSAGES = "invalid_messages"` and `TOOLS_NOT_SUPPORTED = "tools_not_supported"`. The comment on the second says that the `tools` parameter refusal (STORY-006) uses the same constant, so the client sees one code for both.
  - `IGNORED_MESSAGE_NAME = "messages[].name"`
  - `class V1RequestError(Exception)`. Its docstring says: a request this ingress refuses before the pipeline runs, so no audit row is written (T9). `message` names a location and a rule, never a value (T6). `param` is the OpenAI `param` field.
    ```python
    def __init__(self, code: str, message: str, param: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.param = param
    ```
- **Mirror**: `app/models/messages.py:1-9, 33-39`
- **Validate**: `$PY -c "from app.services.v1_translate import V1RequestError, INVALID_MESSAGES, TOOLS_NOT_SUPPORTED"`

### Task 2: `translate_messages`

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  def translate_messages(raw: Sequence[Any]) -> Tuple[List[Message], FrozenSet[str]]:
  ```
  - The docstring states the order of checks and that the edge checks deliberately duplicate `query_pipeline._validate_conversation`. The pipeline's copy is a programming-error guard that writes no row (PRD-010 Section 6.1). This copy is the client-facing 400 (PRD-015 Section 4), so `InvalidConversationError` cannot be reached from `/v1`.
  - `if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence)` → `V1RequestError(INVALID_MESSAGES, "messages must be a list", "messages")`. This uses the normalizer's wording; `ChatCompletionRequest` already guarantees a list, but the function is pure and is tested alone.
  - `if not raw` → `V1RequestError(INVALID_MESSAGES, "messages must not be empty", "messages")`
  - Loop `for index, item in enumerate(raw)`, with `location = f"messages[{index}]"`:
    - `if isinstance(item, Mapping):`
      - `if "tool_calls" in item or "function_call" in item` → `V1RequestError(TOOLS_NOT_SUPPORTED, f"{location}: tool calls are not supported (PRD-016)", location)`
      - `if item.get("role") == "tool"` → `V1RequestError(TOOLS_NOT_SUPPORTED, f"{location}: tool turns are not supported (PRD-016)", location)`
      - `if "name" in item: ignored.add(IGNORED_MESSAGE_NAME)`
      - `if item.get("role") == "developer": item = {**item, "role": "system"}`. Add a short comment: `developer` is a wire alias, not a pipeline role, so `Role` is not widened.
    - `try: messages.append(normalize_message(item))`, then `except MessageNormalizationError as exc: raise V1RequestError(INVALID_MESSAGES, f"{location}: {exc}", location) from exc`
  - After the loop: `if messages[-1].role != "user"` → `V1RequestError(INVALID_MESSAGES, f"messages[{len(messages) - 1}]: the last message must be a user turn", f"messages[{len(messages) - 1}]")`
  - `return messages, frozenset(ignored)`
- **Gotcha**: `item.get("role") == "tool"` must be checked **before** `normalize_message`, because the normalizer accepts `tool`. `tool_calls` must also come first, because the normalizer refuses it with its own error, which would be `invalid_messages`.
- **Mirror**: `app/models/messages.py:65-90`
- **Validate**: `$PY -c "from app.services.v1_translate import translate_messages as t; print(t([{'role':'developer','content':'x','name':'n'},{'role':'user','content':'y'}]))"` prints `([Message(role='system', content='x'), Message(role='user', content='y')], frozenset({'messages[].name'}))`

### Task 3: Table tests for AC 1-3

- **File**: `tests/test_v1_translate_request.py`
- **Action**: CREATE
- **Implement** (module docstring: "PRD-015 STORY-005: `translate_messages`." Use the env bootstrap from `tests/test_messages.py:11-14` and a `_text` helper):
  - **AC 1, equality with the normalizer**: parametrize over string content, a list of text parts, `assistant` with `content: None`, and a missing `content` on assistant. Each list ends with a `user` turn. Assert `translate_messages(raw)[0] == normalize_messages(raw)` and that the ignored names are `frozenset()`.
  - **AC 2, developer**: `[{"role":"developer","content":"be brief"},{"role":"user","content":"x"}]` gives `[Message("system","be brief"), Message("user","x")]`. Developer with text parts is joined like the normalizer joins them. Developer with `content: None` gives `invalid_messages` (the null rule applies to `system`).
  - **AC 2, name**: `name` on a user message and on an assistant message gives the ignored set `{"messages[].name"}` (listed once for two messages). The message content is unaffected. `name: None` is still recorded.
  - **AC 3, refusals**: one parametrized table of `(raw, code, param, rule_fragment)` with ids:
    - `empty-list`: `[]` → `invalid_messages`, `messages`, `"must not be empty"`
    - `tool-role`: `[user, {"role":"tool","content":"out"}, user]` → `tools_not_supported`, `messages[1]`
    - `tool-calls-key`: assistant with `content: None` and `tool_calls`, then user → `tools_not_supported`, `messages[0]`
    - `tool-calls-empty-list`: `tool_calls: []` → `tools_not_supported`
    - `function-call-key`: assistant with `function_call` → `tools_not_supported`
    - `last-not-user`: `[user, assistant]` → `invalid_messages`, `messages[1]`, `"last message must be a user turn"`
    - `only-system`: `[system]` → `invalid_messages`, `messages[0]`
    - `image-part`: user content `[_text("a"), {"type":"image_url",...}]` → `invalid_messages`, `messages[0]`, `r"content\[1\] is not a text part"`
    - `unknown-role`: `{"role":"function",...}` → `invalid_messages`, `"unknown role"`
    - `null-user-content` → `invalid_messages`, `"null content"`
    - `not-an-object`: `["hi"]` → `invalid_messages`, `"message is not an object"`
    - `not-a-list`: `"hi"` → `invalid_messages`, `messages`, `"must be a list"`
  - Assert `exc.code`, `exc.param`, `re.search(rule, exc.message)`, `str(exc) == exc.message` and `exc.message.startswith(f"{exc.param}: ")`. For the normalizer cases, also assert `isinstance(exc.__cause__, MessageNormalizationError)` and that `exc.message == f"{param}: {exc.__cause__}"` (the text is kept).
  - **Order tests**: `[{"role":"tool",...}, {"role":"assistant",...}]` → `tools_not_supported` at `messages[0]` (not last-not-user). `tool_calls` on a message that also has an image part → `tools_not_supported` (the tool check runs before the normalizer).
  - **Codes are the constants**: `TOOLS_NOT_SUPPORTED == "tools_not_supported"` and `INVALID_MESSAGES == "invalid_messages"`.
- **Mirror**: `tests/test_messages.py:69-130`
- **Validate**: `$PY -m pytest tests/test_v1_translate_request.py -q`

### Task 4: Canary, non-mutation and purity tests

- **File**: `tests/test_v1_translate_request.py`
- **Action**: UPDATE
- **Implement**:
  - **Canary (AC 3, T6)**: parametrize over refusals that each carry `_CANARY = "jane@corp.com SECRET-CANARY"`: an image part beside canary text, a tool role with canary content, `tool_calls` holding the canary, a canary role value, a canary `name` on a last-not-user list, and a developer with null content plus canary `name`. Assert that `"CANARY"` is not in `str(exc)`, `exc.param`, or `repr(exc.__cause__)`.
  - **No mutation**: deep-copy a list that has a developer message, run `translate_messages`, and assert the input still equals the copy (the role is still `"developer"`).
  - **Accepts any sequence**: a tuple input works like a list.
  - **Purity**: reuse the AST approach from `tests/test_messages.py:327-352` on `app/services/v1_translate.py`. The imports must be a subset of `{"typing", "app.models.messages"}`, and no name may be in `{"settings", "open", "httpx", "log_query", "logging", "logger", "query_pipeline"}`.
- **Mirror**: `tests/test_messages.py:235-264, 327-352`
- **Validate**: `$PY -m pytest tests/test_v1_translate_request.py -q`

### Task 5: Property test (AC 4)

- **File**: `tests/test_v1_translate_request.py`
- **Action**: UPDATE
- **Implement**:
  - Import `_validate_conversation` and `InvalidConversationError` from `app.services.query_pipeline` (the env bootstrap is already at the top of the file).
  - `_random_message(rng)`: pick the role from `["system", "developer", "user", "user", "assistant", "tool", "function", None]`. Pick the content from: a short string, `""`, a list of 0-3 text parts, `None`, a list with one `image_url` part, an int. With probability 0.1 add `name`, and with probability 0.05 add `tool_calls`.
  - `_random_messages(rng)`: a length of 0-6. With probability 0.6, force the last message to `{"role":"user","content":<str>}` so that the accepted set is not tiny.
  - `@pytest.mark.parametrize("seed", range(500))`, test `test_accepted_input_never_trips_the_pipeline_guard(seed)`: build `raw = _random_messages(random.Random(seed))`. On `V1RequestError`, `return`. Otherwise, call `_validate_conversation(messages)` with no `pytest.raises`, so any `InvalidConversationError` fails the test with the seed in the test id.
  - `test_property_generator_is_not_degenerate`: over the same 500 seeds, count the accepted inputs and the refused ones. Assert both are at least 25% of 500. This proves that the property runs on real accepted inputs and that the generator still produces refusals.
- **Gotcha**: keep the generator in this test file and don't make it a fixture. Parametrizing by seed gives each failure its own reproducible id (`[seed-137]`).
- **Validate**: `$PY -m pytest tests/test_v1_translate_request.py -q` (about 530 cases, under 2 s)

### Task 6: Regression around the touched surface

- **File**: —
- **Action**: run only
- **Implement**: run the normalizer, schema and pipeline-guard neighbours to show nothing moved.
- **Validate**: `$PY -m pytest tests/test_messages.py tests/test_v1_schemas.py tests/test_v1_translate_request.py -q -m "not db"`

---

## End-to-End Tests

There is no route yet (STORY-009 adds `POST /v1/chat/completions`), so no HTTP E2E applies. `/implement` runs these instead:

- [ ] `$PY -m pytest tests/test_v1_translate_request.py -v` — every AC case passes and is named by its id
- [ ] Property test: all 500 seeds pass, and the non-degenerate guard passes
- [ ] REPL check: `translate_messages` on an OpenAI SDK-shaped payload `[{"role":"developer","content":[{"type":"text","text":"sys"}]},{"role":"user","content":"hi","name":"bob"}]` returns `([Message('system','sys'), Message('user','hi')], frozenset({'messages[].name'}))`
- [ ] `git diff --stat` shows only the two new files (plus the story, plan and index bookkeeping)

---

## Validation

```bash
PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
$PY -m pytest tests/test_v1_translate_request.py -q
$PY -m pytest tests/test_messages.py tests/test_v1_schemas.py -q
$PY -m pytest tests/ -q -m "not db"   # Docker-free sweep
```

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| The per-item loop drifts from `normalize_messages` (for example, the normalizer gains a cross-message rule) | AC 1's equality test compares the outputs directly. The module docstring says the loop is the normalizer's own loop plus the index |
| The normalizer's unknown-role text lists `tool` as expected and does not mention `developer`. That misleads a `/v1` client sending `function` | Accepted: the story says "keep its text". It is a cosmetic 400 wording issue, with no wrong verdict. If needed, STORY-019's docs can list the accepted roles |
| Extra per-message keys other than `name` (`refusal`, `audio`) are ignored silently and not recorded | It matches the normalizer's existing behaviour, and the story scopes the recording to `name`. Section 7.3 records only top-level keys and `stream_options.*`. Raise it in STORY-006 if wanted |
| `function_call` on a message is refused although the story names only `tool_calls` | A deliberate extension, for the same reason as `messages.py:73-74` (the silent `""` case). It is a single-line removal if the reviewer disagrees. It is listed in Design Decisions |
| Importing `query_pipeline` in the test drags in `app.config` | The env bootstrap is at the top of the test file (the same pattern as `test_messages.py`). No storage fixture is used, so the PRD-014 storage guard keeps it DB-free |
| A property test without hypothesis has no shrinking | Inputs have at most 6 messages, and the failing seed is in the test id. That is enough to reproduce and minimize by hand |

---

## Acceptance Criteria

(Copied from story `STORY-005`)

- [ ] Given messages with string content, text-part lists and an assistant `content: null`, when `translate_messages` runs, then it returns `Message` objects equal to what `normalize_messages` returns for the same input.
- [ ] Given a `developer` message, when it is translated, then it becomes `Message("system", ...)`; given a per-message `name` field, then it is ignored and reported as `messages[].name` in the ignored names this function returns.
- [ ] Given an empty list, a `tool` role, a message carrying `tool_calls`, a last message that is not `user`, an image content part or an unknown role, when it is translated, then `V1RequestError(code="invalid_messages", param=<location>)` is raised, and its message names the location and rule but never the content. (Per the technical notes, the `tool` role and `tool_calls` raise `code="tools_not_supported"` instead.)
- [ ] Given any input this function accepts, when the result is passed to `query_pipeline._validate_conversation`, then it never raises `InvalidConversationError` (property test over generated message lists).
- [ ] All tasks completed
- [ ] `tests/test_v1_translate_request.py` passes, with no DB
- [ ] The `-m "not db"` sweep passes
- [ ] Follows existing patterns (pure module, location-and-rule messages, canary tests)
