---
story: STORY-004
prd: PRD-010
slug: openrouter-client-sends-messages
title: "call_openrouter takes a list of Messages; the pipeline passes one user message"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-010-multi-turn-pipeline        # all stories commit here, no per-story branch
created: 2026-09-17
---

# Plan: call_openrouter takes a list of Messages; the pipeline passes one user message

## Summary

`call_openrouter` currently takes a bare `prompt: str` and always builds `[{"role": "user", "content": prompt}]`. This story changes its signature to `messages: Sequence[Message]` and the payload to `[{"role": m.role, "content": m.content} for m in messages]`, so a conversation can reach OpenRouter without a second client (PRD-010 F3, in scope only for the messages/payload half — `GenerationParams`, the configurable timeout and `null`-content handling stay STORY-005's). `run_query` in `query_pipeline.py` becomes the one production caller, adapting by passing `[Message("user", redacted_prompt)]`; because that list of one `Message("user", …)` produces the exact same JSON body as today, STORY-003's characterization tests keep passing once their inputs are adapted to the new argument shape. Roughly 90 injected `call_openrouter` stubs across ~17 test files take a first positional argument named `prompt`; almost all ignore its value and need no change (a list passed positionally into an unused parameter is harmless). Only the handful that actually read the value — `seen.append(prompt)` / `calls.append(prompt)` used in three test files, plus the `/query`-upstream characterization test's recording stub — are updated to read `messages[-1].content`, each with a comment citing this story.

## User Story

As the multi-turn pipeline
I want the OpenRouter client to send the conversation I give it rather than wrapping one string
So that history can reach the model without a second client

## Story Reference

- Story file: `.agents/stories/PRD-010-multi-turn-pipeline/STORY-004-openrouter-client-sends-messages.md`
- PRD: `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/services/openrouter_client.py`, `app/services/query_pipeline.py`, ~5 test files |
| Story | STORY-004 |
| PRD | PRD-010 |
| Epic Branch | `epic/PRD-010-multi-turn-pipeline` (commit directly on this branch) |

---

## Skills In Use

None. Story frontmatter lists `skills: []`; the only skill in the repo (`frontend-design`) governs chat-UI copy and bubble components, neither of which this backend-only, client-signature story touches.

---

## Patterns to Follow

### The `Message` model (already shipped, STORY-001)
```python
// SOURCE: app/models/messages.py:16-30
Role = Literal["system", "user", "assistant", "tool"]

@dataclass(frozen=True)
class Message:
    role: Role
    content: str
```
Import `Message` from `app.models.messages` in both the client and the pipeline — the client depends on the model, never the reverse (story Technical Notes).

### Existing client shape (payload construction, error ordering)
```python
// SOURCE: app/services/openrouter_client.py:24-43
def call_openrouter(
    prompt: str,
    model: str = _DEFAULT_MODEL,
    api_key: Optional[str] = None,
    client: Optional[httpx.Client] = None,
) -> OpenRouterResult:
    resolved_key = api_key or settings.OPENROUTER_API_KEY
    if not resolved_key:
        raise OpenRouterError(...)
    ...
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
```
Keep `OpenRouterResult`, `_DEFAULT_MODEL`, the try/except/finally structure and the `OpenRouterError` wrapping exactly as-is — only the input parameter and the `"messages"` list comprehension change.

### Existing pipeline call site
```python
// SOURCE: app/services/query_pipeline.py:163-166
try:
    openrouter_result = call_openrouter(
        redacted_prompt, model=model, api_key=openrouter_api_key
    )
except OpenRouterError as exc:
```
Only the first positional argument changes, to `[Message("user", redacted_prompt)]`.

### Test pattern: fake client + payload assertion (STORY-003 characterization)
```python
// SOURCE: tests/test_openrouter_client.py:121-131
def test_characterization_payload_shape_is_byte_identical():
    client = _FakeClient(response=_response())
    call_openrouter("hello", model="gpt-4", api_key="k", client=client)
    payload = client.requests[0]["json"]
    expected = {"model": "gpt-4", "messages": [{"role": "user", "content": "hello"}]}
    assert json.dumps(payload, sort_keys=False) == json.dumps(expected, sort_keys=False)
```
Every direct call in this file changes its first argument from `"hello"` to `[Message("user", "hello")]`; the `expected` payload dict is untouched (AC1/AC2).

### Test pattern: a stub that reads the value (needs the story's comment)
```python
// SOURCE: tests/test_pii_dedup_isolation.py:84-89
def _capturing_openrouter(seen: list, response: str = "ok"):
    def _call(prompt, model="gpt-4", api_key=None):
        seen.append(prompt)
        return OpenRouterResult(response=response, model_used=model, tokens_used=5)
    return _call
```
Becomes `seen.append(prompt[-1].content)  # PRD-010 STORY-004: upstream now receives list[Message]`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/openrouter_client.py` | UPDATE | New signature `call_openrouter(messages: Sequence[Message], model, api_key, client)`; payload from `messages`; empty-list guard raising `OpenRouterError` before any HTTP call |
| `app/services/query_pipeline.py` | UPDATE | Import `Message`; call site passes `[Message("user", redacted_prompt)]` |
| `tests/test_openrouter_client.py` | UPDATE | Import `Message`; adapt all 13 direct `call_openrouter("hello", …)` calls to `call_openrouter([Message("user", "hello")], …)`; add two new tests (AC3, AC4) |
| `tests/test_query_outcomes_regression.py` | UPDATE | Import `Message`; adapt `_recording_success` + its assertion (the `/query`-upstream characterization test, AC2) |
| `tests/test_pii_redaction_integration.py` | UPDATE | `_capturing_openrouter`'s `_call` reads `prompt[-1].content`, with STORY-004 comment |
| `tests/test_pii_dedup_isolation.py` | UPDATE | Same fix to its `_capturing_openrouter`'s `_call` |
| `tests/test_query_router.py` | UPDATE | Same fix to its `_capturing_openrouter`'s `_call` (line ~304) and the inline `_call` in `test_both_directions_redacted_in_one_request` (line ~576) |

No other file among the ~90 injected-stub call sites needs a change: their stubs ignore the first positional argument's value entirely (verified by grepping every test file for `prompt.`-attribute/string-method use, `len(prompt)`, f-string interpolation of `prompt`, and equality assertions against it — the only hits besides the six sites above were `len(calls)` / emptiness checks, which are shape-agnostic).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Change `call_openrouter`'s signature and payload

- **File**: `app/services/openrouter_client.py`
- **Action**: UPDATE
- **Implement**:
  1. Add `from app.models.messages import Message` and `Sequence` to the `typing` import.
  2. Replace the `prompt: str` parameter with `messages: Sequence[Message]` as the first parameter.
  3. As the first statement in the function body, guard: `if not messages: raise OpenRouterError("messages must not be empty")` — before resolving the API key or touching `client`, so it never makes an HTTP call (AC4).
  4. Replace `payload["messages"]` construction with `[{"role": m.role, "content": m.content} for m in messages]`.
  5. Leave everything else (`OpenRouterResult`, `_DEFAULT_MODEL`, `_TIMEOUT_SECONDS`, key resolution, headers, try/except/finally, response parsing) untouched — this story does not touch `params` or the timeout (Technical Notes).
- **Mirror**: existing structure at `app/services/openrouter_client.py:24-66`
- **Validate**: `python -c "import app.services.openrouter_client"` (module imports without error; no circular import between `app.models.messages` and `app.services.openrouter_client`)

### Task 2: Update `run_query`'s call site to pass one `Message`

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  1. Add `from app.models.messages import Message` to the imports.
  2. Change the call at line ~164 from `call_openrouter(redacted_prompt, model=model, api_key=openrouter_api_key)` to `call_openrouter([Message("user", redacted_prompt)], model=model, api_key=openrouter_api_key)`.
  3. Do not touch `_UserTurn`, `dedup_key`, or any audit arm — those are STORY-007's.
- **Mirror**: `app/services/query_pipeline.py:163-166`
- **Validate**: `python -c "import app.services.query_pipeline"`

### Task 3: Adapt `tests/test_openrouter_client.py`'s direct calls and add the two new ACs

- **File**: `tests/test_openrouter_client.py`
- **Action**: UPDATE
- **Implement**:
  1. Add `from app.models.messages import Message` to imports.
  2. In every one of the 13 `call_openrouter("hello", …)` call sites (lines 44, 54, 64, 73, 82, 89, 96, 103, 110, 124, 137, 164, plus the characterization tests at 124/137/164 already listed), replace `"hello"` with `[Message("user", "hello")]`. Leave every other argument and every assertion (including the byte-identical `expected` payload dict at line 127 and the headers/URL/timeout assertions) unchanged — the whole point is that the JSON body does not move (AC1, AC2, "no change to the payload assertion").
  3. Add a new test for AC3, mirroring `test_characterization_payload_shape_is_byte_identical`'s `_FakeClient` pattern:
     ```python
     def test_multi_message_conversation_preserves_order_roles_and_content():
         client = _FakeClient(response=_response())
         messages = [
             Message("system", "be terse"),
             Message("user", "hi"),
             Message("assistant", "hello"),
             Message("user", "and now?"),
         ]

         call_openrouter(messages, model="gpt-4", api_key="k", client=client)

         payload = client.requests[0]["json"]
         assert payload["messages"] == [
             {"role": "system", "content": "be terse"},
             {"role": "user", "content": "hi"},
             {"role": "assistant", "content": "hello"},
             {"role": "user", "content": "and now?"},
         ]
     ```
  4. Add a new test for AC4:
     ```python
     def test_empty_messages_raises_before_any_http_call():
         client = _FakeClient(response=_response())

         with pytest.raises(OpenRouterError):
             call_openrouter([], api_key="k", client=client)

         assert client.requests == []
     ```
- **Mirror**: `tests/test_openrouter_client.py:41-167` (existing test bodies and `_FakeClient`)
- **Validate**: `cd /g/coding/harness-ai && python -m pytest tests/test_openrouter_client.py -q`

### Task 4: Adapt the `/query`-upstream characterization test (AC2)

- **File**: `tests/test_query_outcomes_regression.py`
- **Action**: UPDATE
- **Implement**:
  1. Add `from app.models.messages import Message` to imports.
  2. In `test_characterization_query_upstream_receives_prompt_model_and_no_api_key`, change `_recording_success(prompt, model="gpt-4", api_key=None)` — the parameter now receives a `list[Message]`, not a string. Update the body: `received["messages"] = prompt` (or rename the parameter to `messages` for clarity) and the final assertion from
     `assert received == {"prompt": prompt, "model": "gpt-4", "api_key": None}`
     to
     `assert received == {"messages": [Message("user", prompt)], "model": "gpt-4", "api_key": None}`
     (rename the `received` dict key from `"prompt"` to `"messages"` and the local `received["prompt"] = prompt` line to `received["messages"] = messages` to match).
  3. Add a one-line comment above the change: `# PRD-010 STORY-004: upstream now receives list[Message]`.
- **Mirror**: `tests/test_query_outcomes_regression.py:222-241`
- **Validate**: `cd /g/coding/harness-ai && python -m pytest tests/test_query_outcomes_regression.py -q`

### Task 5: Fix the three stubs that read the prompt's string value

- **File**: `tests/test_pii_redaction_integration.py`
- **Action**: UPDATE
- **Implement**: In `_capturing_openrouter`'s inner `_call(prompt, model="gpt-4", api_key=None)` (line ~64), change `seen.append(prompt)` to `seen.append(prompt[-1].content)  # PRD-010 STORY-004: upstream now receives list[Message]`. No assertion in this file changes — `seen` still ends up holding the same strings (`_REDACTED_PROMPT`, `_PII_PROMPT`) it always did, because `run_query` sends exactly one message.
- **Mirror**: pattern from story Technical Notes (`tests/test_pii_dedup_isolation.py` example)
- **Validate**: `cd /g/coding/harness-ai && python -m pytest tests/test_pii_redaction_integration.py -q`

- **File**: `tests/test_pii_dedup_isolation.py`
- **Action**: UPDATE
- **Implement**: Same fix in `_capturing_openrouter`'s `_call` (line ~85): `seen.append(prompt)` → `seen.append(prompt[-1].content)  # PRD-010 STORY-004: upstream now receives list[Message]`.
- **Validate**: `cd /g/coding/harness-ai && python -m pytest tests/test_pii_dedup_isolation.py -q`

- **File**: `tests/test_query_router.py`
- **Action**: UPDATE
- **Implement**: Same fix in two places: `_capturing_openrouter`'s `_call` (line ~304, `seen.append(prompt)` → `seen.append(prompt[-1].content)  # PRD-010 STORY-004: upstream now receives list[Message]`) and the inline `_call` inside `test_both_directions_redacted_in_one_request` (line ~576, same change).
- **Validate**: `cd /g/coding/harness-ai && python -m pytest tests/test_query_router.py -q`

### Task 6: Full suite green

- **Action**: VALIDATE ONLY (no file changes)
- **Implement**: Run the complete test suite once all edits are in place. Per the repo's libSQL dev-server note, if the run shows mass, unrelated fixture errors, restart the local Turso/libSQL dev server rather than treating it as a code regression.
- **Validate**: `cd /g/coding/harness-ai && python -m pytest -q`

---

## End-to-End Tests

- [ ] `python -m pytest tests/test_openrouter_client.py -q` — all pass, including the two new AC3/AC4 tests
- [ ] `python -m pytest tests/test_query_outcomes_regression.py -q` — all pass, including the adapted `/query`-upstream characterization test
- [ ] `python -m pytest tests/test_pii_redaction_integration.py tests/test_pii_dedup_isolation.py tests/test_query_router.py -q` — all pass; outbound-payload assertions (`seen == [_REDACTED_PROMPT]`, etc.) are unchanged in value
- [ ] `python -m pytest tests/test_chat_state.py tests/test_query_pipeline_session_passthrough.py -q` — green with no assertion changes (AC5's named examples)
- [ ] Full suite: `python -m pytest -q` — green

---

## Validation

```bash
cd /g/coding/harness-ai
python -c "import app.services.openrouter_client; import app.services.query_pipeline"
python -m pytest -q
```

---

## Acceptance Criteria

(Copied from story STORY-004)

- [ ] `app/services/openrouter_client.py`'s `call_openrouter` signature is `call_openrouter(messages: Sequence[Message], model: str = _DEFAULT_MODEL, api_key: Optional[str] = None, client: Optional[httpx.Client] = None)`, and the payload is `{"model": model, "messages": [{"role": m.role, "content": m.content} for m in messages]}`
- [ ] `run_query` in `app/services/query_pipeline.py` passes `[Message("user", redacted_prompt)]` to `call_openrouter`; STORY-003's characterization tests (client and `/query`) pass with the input argument adapted (`[Message("user", "hello")]`), with no change to the payload assertion
- [ ] A four-message list `[system, user, assistant, user]` called through `call_openrouter` with a fake client preserves order, roles and content exactly in the recorded `json["messages"]`
- [ ] An empty `messages` list raises `OpenRouterError` before any HTTP call
- [ ] Every test that injects a fake `call_openrouter` is green; only stubs that read their first argument as a string are updated, each with a `# PRD-010 STORY-004: upstream now receives list[Message]` comment; no outcome assertion changes
- [ ] All tasks completed
- [ ] Full suite passes
- [ ] Follows existing patterns
