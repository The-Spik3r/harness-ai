---
story: STORY-011
prd: PRD-017
slug: completion-shape
title: "Completion shape: tool_calls, content null, finish_reason tool_calls, harness.actions"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-017-tool-calling
created: 2026-11-16
---

# Plan: Completion shape (tool_calls, content null, finish_reason tool_calls, harness.actions)

## Summary

`translate_result` (`app/services/v1_translate.py:554-594`) starts consuming the pipeline
result's private `tool_outcome` (STORY-010, `app/models/schemas.py:86-97`). When an outcome
exists, meaning the upstream returned calls and every one was decided, the non-streamed
completion carries the released calls as `message.tool_calls` (taken from
`outcome.release.tool_calls`, never from `upstream.tool_calls`, T1), `content: null` when
the content is `""` and at least one call is released, `finish_reason` from
`outcome.release.finish_reason`, and `harness.actions`, one
`{tool_call_id, tool_name, decision, rule, reason}` per decision in model order (D14). When
there is no outcome (every text-only response, with the flag on or off), the body stays
PRD-015's byte for byte: the two new keys are omitted by their own serializers, the same way
Section 7.6's two omitted keys already are (`v1_schemas.py:138-142`, `:167-172`). The SSE writer
is not touched. STORY-012 owns the streamed tool-call deltas. A text-only stream stays
byte-identical, and a denied-only stream is already final. An allowed call in a stream is
decided but not streamed until STORY-012, which an interim pin covers.

## User Story

As an integrating developer
I want the non-streamed `/v1` completion to carry the released tool calls in the standard shape
So that the OpenAI SDK and my agent parse it like any provider's response

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-011-completion-shape.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md` (Section 6.6 lines 230-248, Section 10 lines 397-410, D14 line 526, F8 lines 331-332)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/models/v1_schemas.py`, `app/services/v1_translate.py`, `app/routers/v1.py` (docstring only), tests |
| Story | STORY-011 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

---

## Key decisions (read first)

**DD-1. The new keys appear only when calls were evaluated. Recorded deviation from AC3 and AC5.**
Story AC5 says a text-only body gains `tool_calls: null` and `harness.actions: []`, and AC3 says
a text-only response has `harness.actions == []`. Both conflict with D10 and the shared brief
("Flag off means PRD-015, byte for byte; no existing `/v1` test expectation may change"). With
the flag off nothing can carry tool calls, so the outcome is always `None`. Adding the keys there
would change `test_builds_the_section_7_4_example` (`tests/test_v1_translate_result.py:90-106`),
`test_completion_matches_section_7_4` (`tests/test_v1_schemas.py:249-251`), every PRD-015 router
and SSE fixture, and the E2E clients' bytes. The orchestrator asked us to prefer omitting keys.
So the rule is:

| Outcome | `message.tool_calls` | `harness.actions` |
|---|---|---|
| `None` (no call evaluated: every text-only response, flag on or off) | **key absent** | **key absent** |
| present, at least one call released | list of calls | list, one per decision |
| present, every call denied | `null` (**key kept**, PRD Section 10 lines 402 and 410) | list, one per decision |

Readers of `harness.actions` use `.get("actions", [])`. An absent key means "no call evaluated",
which is what `[]` would have said. So D14's meaning is kept and only the spelling for text-only
responses differs. This also answers the client-safety question without guessing what strict
clients do: Aider/litellm, Continue and the SDK see the exact PRD-015 body on every response
they can provoke today. Only flag-on responses that carry calls gain keys. For those, PRD
Section 10 fixes `tool_calls: null` on an all-denied response. The OpenAI SDK model declares
`tool_calls` Optional with default None (AC4 test below), and litellm and Continue handle
OpenAI's own `null`. The E2E stories (STORY-016/017) verify the target agents.

Mechanism: `AssistantMessage.tool_calls` is omitted when it is not in `model_fields_set` (unset),
and kept as `null` when it was passed explicitly as `None`. `HarnessCompletionInfo.actions` is
omitted when it is `None`. Both are wrap `model_serializer`s, the pattern
`ChunkDelta._drop_unset` / `ChatCompletionChunk._drop_absent_usage` use
(`app/models/v1_schemas.py:138-142`, `:167-172`). `model_dump(mode="json")` stays the only
serialization path, and `exclude_none` is still never used (module docstring `:9-12`). That
docstring gets one more sentence naming the two new conditional keys.

**DD-2. `finish_reason`.** `FinishReason` (`v1_schemas.py:83`) gains `"tool_calls"`. In
`translate_result`, `outcome.release.finish_reason` wins when the outcome exists and the value is
not `None`. Otherwise the upstream's value is mapped as today. `_FINISH_REASONS`
(`v1_translate.py:105`) **does not** gain `"tool_calls"`: an upstream that says `tool_calls`
with no outcome (no call parsed, or flag off) is still sent as `"stop"`. Otherwise the client
would get `finish_reason: "tool_calls"` with no calls, and
`test_any_other_finish_reason_is_stop["tool_calls"]` (`tests/test_v1_translate_result.py:114-116`)
stays green unedited. The comment at `:103-104` is reworded to say that `"tool_calls"` comes only
from the release.

**DD-3. `content`.** `AssistantMessage.content: str` becomes `Optional[str]`. It is `None` only
when the outcome exists, `outcome.release.tool_calls` is non-empty and `result.response == ""`
(PRD 6.6 line 246; `tool_release.content_with_notes` docstring `:121-126` hands this mapping to
us). An outcome with every call denied always has notes, so its content is non-empty. A text-only
`""` stays `""`, as in PRD-015. Notes are already joined into `response` by the pipeline
(`query_pipeline.py:884-889`), and we do not join again.

**DD-4. Pure module, no new imports.** `translate_result` reads `result.tool_outcome` (a
property, `schemas.py:95-97`) and duck-types `ToolOutcome` / `ActionDecision` /
`ToolCallSpec`. No `app.services.tool_release` or `action_policy` import is added, so
`test_is_pure` (`tests/test_v1_translate_request.py:333-349`) passes unedited.
`HarnessAction.decision` is a written-out `Literal["allow", "flag", "deny"]`, because
`v1_schemas` imports nothing from `app`. A new test pins it to `action_classifiers.DECISIONS`,
the same way `tests/test_tool_release.py:178` pins `tool_release._DECISIONS`. `rule` is `str`:
the rule vocabulary belongs to PRD-016, and the wire schema only carries it.

**DD-5. SSE is unchanged in this story (STORY-012 owns it).** `v1_sse.completion_events`
(`app/services/v1_sse.py:45-70`) reads only `message.content` and `finish_reason`.
- Text-only stream: the outcome is `None`, so the completion is identical and the events are
  byte-identical. No SSE test changes.
- Denied-only stream: content is the note and `finish_reason` is `"stop"`, the same as today and
  already PRD 6.6's final shape. `ChunkDelta` has no `tool_calls` field, so nothing leaks.
- Stream with released calls (interim): the content chunk's delta is `{"role": "assistant"}`
  (content `None` is dropped by `_drop_unset`) and the finish chunk says `"tool_calls"`. The
  calls themselves are not streamed until STORY-012. T1 holds, because no undecided call is
  sent and decided calls are simply held back. An interim test pins "no call data in the
  stream", and its docstring says STORY-012 replaces it. `ChunkChoice.finish_reason`
  (`v1_schemas.py:149`) accepts `"tool_calls"` once `FinishReason` gains it. The flag is off
  by default, so this window exists only on the epic branch between two consecutive stories.

**DD-6. OpenAI SDK is not installed in `.venv`.** `pip show openai` in `.venv` reports
"not found", contrary to the orchestrator note, so `tests/test_v1_schemas.py:331-354` currently
skip. AC4 needs the installed SDK. The implementer installs the version `requirements-e2e.txt:7`
pins into the repo's git-ignored `.venv` (not a global install):
`.venv/Scripts/python -m pip install openai==3.40.0`, and records the exact command in the report.
The new SDK tests use `pytest.importorskip("openai")` like the existing ones (`:332`), and the
implementer must report them as **passed, not skipped**. If the install is refused, stop and tell
the orchestrator; do not claim AC4.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI). No UI here; story `skills: []`. | none |

---

## Patterns to Follow

### Conditional key omission (wrap serializer)
```python
# SOURCE: app/models/v1_schemas.py:134-142, 167-172
class ChunkDelta(BaseModel):
    role: Optional[Literal["assistant"]] = None
    content: Optional[str] = None

    @model_serializer(mode="wrap")
    def _drop_unset(self, handler):
        # Section 7.6: the finish chunk's delta is `{}`, not
        # `{"role": null, "content": null}`.
        return {key: value for key, value in handler(self).items() if value is not None}
...
    @model_serializer(mode="wrap")
    def _drop_absent_usage(self, handler):
        data = handler(self)
        if data.get("usage") is None:
            data.pop("usage", None)
        return data
```

### Translator mapping (pure, inputs passed in)
```python
# SOURCE: app/services/v1_translate.py:570-594
reported = upstream.finish_reason
finish_reason = reported if reported in _FINISH_REASONS else "stop"
...
choices=[Choice(message=AssistantMessage(content=result.response), finish_reason=finish_reason)],
```

### Outcome on the success result (STORY-010)
```python
# SOURCE: app/services/query_pipeline.py:826-836, 956-959
outcome: Optional[tool_release.ToolOutcome] = None
if openrouter_result.tool_calls:
    ...
    outcome = tool_release.ToolOutcome(release=tool_release.apply_decisions(...), decisions=decisions)
...
if outcome is not None:
    success._tool_outcome = outcome
```

### Tests: whole-body pins, router stubs, AST guard
```python
# SOURCE: tests/test_v1_translate_result.py:57-85 (_success / _upstream / _dump helpers)
# SOURCE: tests/test_v1_tools.py:595-604 (_ToolUpstream stub, accepts tools=)
# SOURCE: tests/test_v1_tools.py:859-863 (_denial_note from the real engine's verdict)
# SOURCE: tests/test_v1_tools.py:1032-1044 (AST guard: no `<x>.result.tool_calls` in the router)
# SOURCE: tests/test_v1_schemas.py:331-342 (openai SDK model_validate, importorskip)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/v1_schemas.py` | UPDATE | `FinishReason` + `"tool_calls"`; `ToolCallFunction`, `CompletionToolCall`, `HarnessAction` models; `AssistantMessage.content` Optional + `tool_calls` with the unset-omits serializer; `HarnessCompletionInfo.actions` with the None-omits serializer; docstring |
| `app/services/v1_translate.py` | UPDATE | `translate_result` consumes `result.tool_outcome`: calls, content null, finish_reason, actions; `_FINISH_REASONS` comment; module docstring line |
| `app/routers/v1.py` | UPDATE | Module docstring `:22-26` only (STORY-011 now releases from `tool_outcome`, non-streamed; SSE deltas STORY-012). No code change: `translate_result` reads the outcome itself |
| `tests/test_v1_schemas.py` | UPDATE | New schema/serializer tests and SDK parse; one parametrize value changed (`"tool_calls"` is now a valid finish reason) |
| `tests/test_v1_translate_result.py` | UPDATE | New `translate_result` tests with an outcome: AC1, AC2, AC3, AC4, AC5 no-outcome pin, T1 AST guard on `translate_result` |
| `tests/test_v1_tools.py` | UPDATE | Replace the three interim pins with real assertions; adjust `_assert_no_call_released` and the json branch of `test_drop_table_via_shell...`; new router tests (mixed, flag-on text-only body equals flag-off, interim streamed allow) |

No new files. `v1_sse.py` is not touched.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Wire shapes in `v1_schemas.py`

- **File**: `app/models/v1_schemas.py`
- **Action**: UPDATE
- **Implement**:
  1. `:81-83`: `FinishReason = Literal["stop", "length", "content_filter", "tool_calls"]`. Reword the comment: `"tool_calls"` is the release's (PRD-017 Section 6.6, DD-2), never an upstream value passed through.
  2. Before `AssistantMessage`, add:
     - `class ToolCallFunction(BaseModel)`: `name: str`, `arguments: str`. Add a comment that `arguments` is the model's string, byte for byte, never parsed (D13).
     - `class CompletionToolCall(BaseModel)`: `id: str`, `type: Literal["function"] = "function"`, `function: ToolCallFunction`. Docstring: PRD-017 Section 6.6/10 shape, the OpenAI SDK's `ChatCompletionMessageFunctionToolCall`.
  3. `AssistantMessage` (`:100-102`): `content: Optional[str]`, `tool_calls: Optional[List[CompletionToolCall]] = None`, and a wrap `model_serializer` `_drop_unset_tool_calls` that pops `"tool_calls"` when `"tool_calls" not in self.model_fields_set`. Docstring: absent when no call was evaluated (PRD-015's body, D10). An explicit `None` is kept as `null`, as when every call was denied (PRD-017 Section 10, DD-1). `content` is `null` only when calls are released and there is no text or note (Section 6.6).
  4. `class HarnessAction(BaseModel)`: `tool_call_id: str`, `tool_name: str`, `decision: Literal["allow", "flag", "deny"]`, `rule: str`, `reason: str`. Add a comment that the decision vocabulary is written out because this module imports nothing from `app`, and that a test pins it to `action_classifiers.DECISIONS` (D14).
  5. `HarnessCompletionInfo` (`:112-121`): `actions: Optional[List[HarnessAction]] = None`, and a wrap serializer `_drop_absent_actions` (mirror `_drop_absent_usage` `:167-172`). Extend the docstring: one entry per evaluated call, released or not, in model order (D14); absent when no call was evaluated (DD-1).
  6. Module docstring `:9-12`: change "the only keys that disappear are the two Section 7.6 omits" to also name `message.tool_calls` (absent unless a call was evaluated) and `harness.actions` (same rule), PRD-017 D10/D14.
- **Mirror**: `app/models/v1_schemas.py:138-142`, `:167-172`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: `translate_result` consumes the outcome

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**:
  1. Imports: add `CompletionToolCall`, `HarnessAction`, `ToolCallFunction` from `app.models.v1_schemas`. No other `app` import (DD-4).
  2. `:103-105` comment: `_FINISH_REASONS` stays the three. Explain that `"tool_calls"` comes only from the release, so an upstream `tool_calls` with nothing evaluated is still `"stop"` (DD-2).
  3. `translate_result` (`:554-594`):
     ```python
     outcome = result.tool_outcome
     reported = upstream.finish_reason
     finish_reason = reported if reported in _FINISH_REASONS else "stop"
     message = AssistantMessage(content=result.response)   # no tool_calls kwarg: key absent
     actions = None
     if outcome is not None:
         release = outcome.release
         if release.finish_reason is not None:
             finish_reason = release.finish_reason
         released = [CompletionToolCall(id=c.id, function=ToolCallFunction(name=c.name, arguments=c.arguments))
                     for c in release.tool_calls]
         content = None if released and not result.response else result.response
         # explicit tool_calls=None keeps the key as null (all denied, Section 10)
         message = AssistantMessage(content=content, tool_calls=released or None)
         actions = [HarnessAction(tool_call_id=d.tool_call_id, tool_name=d.tool_name,
                                  decision=d.decision, rule=d.rule, reason=d.reason)
                    for d in outcome.decisions]
     ```
     Then pass `harness=HarnessCompletionInfo(..., actions=actions)`. `actions=None` is omitted by
     the serializer. Pass `actions` only as a keyword, which is equivalent and keeps one constructor
     call. Never read `upstream.tool_calls` (T1). Never touch `arguments` (D13): the
     `ToolCallSpec.arguments` object is passed straight through.
  4. Docstring: add a paragraph (PRD-017 Section 6.6, D2, D14, T1). The calls come from
     `result.tool_outcome` (step 7c's release), never from the upstream. `finish_reason` comes from
     the release when calls were evaluated. Content `""` with released calls is `null`. With no
     outcome the completion is PRD-015's (D10). Streamed deltas are STORY-012's.
  5. Module docstring (`:12-16`): one line: STORY-011 builds the non-streamed release shape from
     the pipeline's `tool_outcome`.
- **Mirror**: `app/services/v1_translate.py:570-594`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 3: Router docstring

- **File**: `app/routers/v1.py`
- **Action**: UPDATE (docstring `:22-26` only)
- **Implement**: Replace "The response is still built from `response` ... until STORY-011 releases ..." with:
  STORY-011 releases the allowed calls on the non-streamed body. `translate_result` reads them
  from the pipeline result's `tool_outcome`, never from `upstream.result` (T1). STORY-012 streams
  them. `_Upstream` docstring `:137-138` stays true; leave it.
- **Validate**: `test_router_never_reads_raw_upstream_tool_calls` (`tests/test_v1_tools.py:1032-1044`) stays green.

### Task 4: Install the pinned OpenAI SDK into `.venv` (DD-6)

- **Action**: environment, no repo file
- **Implement**: `.venv/Scripts/python -m pip install openai==3.40.0` (version from `requirements-e2e.txt:7`). Record the command and the resulting `openai.__version__` in the report. Do not edit any requirements file (`test_untouched_app.py::test_no_new_dependency_in_either_requirements_file`).
- **Validate**: `.venv/Scripts/python -c "import openai; print(openai.__version__)"`, then confirm `tests/test_v1_schemas.py::test_openai_sdk_validates_the_completion` now **passes** (it skipped before).

### Task 5: Schema tests

- **File**: `tests/test_v1_schemas.py`
- **Action**: UPDATE
- **Implement**:
  1. `test_completion_refuses_an_unknown_finish_reason` (`:259-263`): change the parametrize list `["tool_calls", "error", ""]` to `["function_call", "error", ""]`. Comment: `# PRD-017 Section 6.6 (DD-2): "tool_calls" is now a FinishReason the release sets; "function_call" (the deprecated API's) is still refused.` Keep the function name, so no registration is needed. This changes a schema-level PRD-015 expectation, not a wire one; tell the orchestrator.
  2. New tests (module docstring gains a PRD-017 STORY-011 line):
     - `test_text_only_message_has_no_tool_calls_key`: `AssistantMessage(content="x")` dumps (all three `_all_dumps`) to `{"role": "assistant", "content": "x"}`; `HarnessCompletionInfo(audit_id=1)` has no `actions` key. `test_completion_matches_section_7_4` already pins the whole body; leave it unedited.
     - `test_explicit_null_tool_calls_is_kept`: `AssistantMessage(content="note", tool_calls=None)` dumps to `{"role", "content": "note", "tool_calls": None}` in all three dumps.
     - `test_released_calls_serialize_in_the_section_10_shape`: two `CompletionToolCall`s with `content=None` dump to `{"role": "assistant", "content": None, "tool_calls": [{"id", "type": "function", "function": {"name", "arguments"}}, ...]}`. `arguments` is a string with escapes (for example `'{"path":"a\\"b.py"}'`) and stays equal (`==` and `in model_dump_json()` raw).
     - `test_harness_actions_serialize_one_entry_per_decision`: `HarnessCompletionInfo(audit_id=412, actions=[...])` equals PRD Section 10's `harness` object (lines 405-407) verbatim.
     - `test_harness_action_decisions_are_the_policy_vocabulary`: `set(get_args(HarnessAction.model_fields["decision"].annotation)) == set(action_classifiers.DECISIONS)`. Mirror `tests/test_tool_release.py:178`.
     - `test_openai_sdk_parses_released_calls` (importorskip): `openai.types.chat.ChatCompletion.model_validate(json.loads(completion.model_dump_json()))` for a two-call completion. `message.tool_calls[i].function.arguments` equals the source strings, `.id` and `.function.name` match, `message.content is None`, `finish_reason == "tool_calls"`, and `model_extra["harness"]["actions"]` has two entries.
     - `test_openai_sdk_parses_null_tool_calls` (importorskip): the all-denied shape parses, with `message.tool_calls is None` and content equal to the note.
- **Mirror**: `tests/test_v1_schemas.py:168-170`, `:331-342`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_schemas.py -q`

### Task 6: `translate_result` tests

- **File**: `tests/test_v1_translate_result.py`
- **Action**: UPDATE (append; no existing expectation edited, see AC5)
- **Implement**: helper `_with_outcome(result, calls, decisions)`. It builds `tool_release.ToolOutcome(tool_release.apply_decisions(calls, decisions), tuple(decisions))` and sets `result._tool_outcome`, as `tests/test_v1_tools.py:1052` does. `decisions` are small stand-ins with the five fields (`types.SimpleNamespace(tool_call_id=..., tool_name=..., decision=..., rule=..., reason=...)`): `apply_decisions` reads only `tool_call_id` and `decision`, and `translate_result` reads the five. Importing `tool_release` in a test is fine, because purity is about the module under test. Tests:
  - `test_two_released_calls_and_no_text` (AC1): `_success(response="")`, two allowed calls, upstream `finish_reason="tool_calls"`. Assert the message is exactly `{"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "read", "arguments": ARGS1}}, {... ARGS2}]}`, `finish_reason == "tool_calls"`, and the arguments are the *same objects* (`is`) as the specs' (D13).
  - `test_every_call_denied_is_the_notes_with_tool_calls_null` (AC2): response = the note text, decision deny. `"tool_calls" in message and message["tool_calls"] is None`, content is the note, `finish_reason == "stop"` even with upstream `"tool_calls"`.
  - `test_text_plus_released_calls_carries_both` (AC2): response `"Reading it."`, allowed call. Content is the text, tool_calls has one entry, finish `tool_calls`.
  - `test_mixed_release_keeps_the_note_and_the_allowed_call`: allow and deny, response = note. Content is the note, one call (the allowed one), finish `tool_calls`.
  - `test_harness_actions_list_every_decision_in_model_order` (AC3): allow, flag, deny. `harness["actions"]` is the three dicts in order, released or not.
  - `test_release_finish_reason_wins_over_the_upstream`: upstream `"length"` with a released call gives `"tool_calls"`; with every call denied it gives `"stop"`.
  - `test_without_an_outcome_the_body_is_prd_015s` (AC5, DD-1): for `_success()` and `_success(response="")`, `"tool_calls" not in message`, `"actions" not in harness`, and `_dump()` still equals `test_builds_the_section_7_4_example`'s dict (reuse it via a module constant only if this does not edit that test; otherwise assert key sets).
  - `test_translate_result_never_reads_upstream_tool_calls` (T1): AST over `inspect.getsource(translate_result)`, with no `Attribute(attr="tool_calls")` whose value is `Name(id="upstream")`. Mirror `tests/test_v1_tools.py:1032-1044`.
  - `test_completion_with_calls_parses_in_the_openai_sdk` (AC4, importorskip): the translator's output, not a hand-built model, through `openai.types.chat.ChatCompletion.model_validate`. Arguments are equal and `finish_reason == "tool_calls"`.
- **Mirror**: `tests/test_v1_translate_result.py:57-116`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_translate_result.py -q`

### Task 7: Router tests, replacing the interim pins

- **File**: `tests/test_v1_tools.py` (created in PRD-017 STORY-008, so it is not pre-epic. Renaming its functions needs no `_DELIBERATELY_SUPERSEDED_TESTS` entry; `_epic_base` is `merge-base main HEAD`, `tests/test_pii_redaction_integration.py:357-359`.)
- **Action**: UPDATE
- **Implement**:
  1. Section header `:840` "Interim T1 pin" becomes "STORY-011: the release on the wire". Keep `_calling_upstream` and `_denial_note`.
  2. `_assert_no_call_released` (`:851-856`): drop the `'"tool_calls"'` substring check, because the JSON body now legitimately carries `"tool_calls": null`. Keep the argument-string and `"arguments"` checks. Comment: PRD-017 Section 10, STORY-011: `tool_calls: null` is kept on an all-denied body; the arguments must still never appear.
  3. `test_interim_upstream_tool_calls_are_dropped_not_released` (`:866-885`) becomes
     **`test_denied_call_is_the_note_with_tool_calls_null_and_stop`**. Assert `choice["message"] == {"role": "assistant", "content": <note>, "tool_calls": None}`, `finish_reason == "stop"`, `body["harness"]["actions"] == [{"tool_call_id": "call_2", "tool_name": "bash", "decision": "deny", "rule": <row["rule"]>, "reason": <row["reason"]>}]` (read from `action_decisions` so the rule text is not hard-coded), `_assert_no_call_released(response.text)`, and one upstream call.
  4. `test_interim_streamed_tool_calls_are_dropped_not_released` (`:888-901`) becomes
     **`test_streamed_denied_call_is_the_note_and_stop`**. Keep the content assertion, and add that the finish chunk's `finish_reason == "stop"`, `'"tool_calls"' not in response.text` (SSE has no such key, DD-5), and `"harness"` is not in any chunk (PRD 6.6 line 248).
  5. `test_interim_allowed_call_is_decided_but_not_yet_released` (`:904-921`) becomes
     **`test_allowed_call_is_released_with_content_null_and_finish_tool_calls`**. Assert the
     message is exactly `{"role": "assistant", "content": None, "tool_calls": [{"id": "call_r", "type": "function", "function": {"name": "read", "arguments": '{"path":"src/a.py"}'}}]}`, `finish_reason == "tool_calls"`, `json.dumps('{"path":"src/a.py"}')` is a substring of `response.text` (byte-identical, D13), `harness.actions` is one `allow` entry, and the decision row assertion is kept.
  6. `test_drop_table_via_shell_is_denied_and_recorded_with_the_audit_id` (`:941-964`): the
     unconditional `assert '"tool_calls"' not in response.text` (`:955`) becomes a branch. For SSE
     it stays. For JSON, assert `response.json()["choices"][0]["message"]["tool_calls"] is None`
     and `"arguments" not in response.text`. Comment: `# PRD-017 Section 10 (STORY-011): the JSON body keeps tool_calls: null when every call is denied; no call data appears.`
  7. New tests:
     - `test_mixed_response_releases_the_allowed_call_and_notes_the_denied_one`: `_ToolUpstream(response="Reading.", tool_calls=(_READ_CALL, _DROP_TABLE), finish_reason="tool_calls")`. Content == `"Reading.\n\n" + note`, one released call (`call_r`), finish `tool_calls`, and actions `[allow, deny]` in that order.
     - `test_flag_on_text_only_body_is_the_flag_off_body` (AC5, DD-1): the same text-only request with the flag off and then on (two distinct prompts to avoid the duplicate checker, or reset the db between them). The JSON bodies are equal except `id`, `created` and `harness.audit_id`, and neither has `tool_calls` or `actions` keys.
     - `test_interim_streamed_allowed_call_is_not_yet_streamed` (DD-5; docstring: "Interim (STORY-011): calls are decided and the finish reason is the release's, but deltas are STORY-012's; STORY-012 replaces this test"): stream with `_READ_CALL`. `'{"path":"src/a.py"}'` and `"arguments"` are not in the text, `[DONE]` is present, and one `allow` row exists. Do not pin the finish reason.
     - `test_router_sdk_round_trip` (AC4, importorskip): the JSON body of the allowed-call request, parsed with `openai.types.chat.ChatCompletion.model_validate(response.json())`. Arguments equal and `finish_reason == "tool_calls"`.
  8. Module docstring `:13`: update the sentence "no call is sent until STORY-011" to say that STORY-011 releases them non-streamed and STORY-012 streams them.
  9. `test_router_never_reads_raw_upstream_tool_calls` is unedited and must stay green.
- **Mirror**: `tests/test_v1_tools.py:866-921`, `:941-964`
- **Validate**: see Validation below.

---

## End-to-End Tests

- [ ] In-process (TestClient), via Task 7. Flag on, upstream returns an allowed `read` call: `200`, the body has the call with byte-identical arguments, `content: null`, `finish_reason: "tool_calls"`, and `harness.actions[0].decision == "allow"`.
- [ ] Flag on, all denied: `tool_calls: null`, the note as content, `finish_reason: "stop"`.
- [ ] Flag off, or flag on with text only: the body has no `tool_calls` or `actions` keys, and every PRD-015 `/v1` test passes unedited (`tests/test_v1_router.py`, `tests/test_v1_sse.py`, `tests/test_v1_errors.py` are run, not edited).
- [ ] OpenAI SDK 3.40.0 parses the released-call body (AC4), reported as passed, not skipped.
- Live clients (OpenCode/Cline) are STORY-016/017. No live E2E in this story.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
.venv/Scripts/python -c "import openai; print(openai.__version__)"   # 3.40.0 after Task 4
PYTHONUTF8=1 .venv/Scripts/python -m pytest \
  tests/test_v1_schemas.py tests/test_v1_translate_result.py tests/test_v1_tools.py \
  tests/test_v1_translate_request.py tests/test_v1_sse.py tests/test_v1_router.py \
  tests/test_untouched_app.py -q
```
(One pytest call, in the foreground. `test_v1_translate_request.py` covers `test_is_pure`.
`test_v1_sse.py` and `test_v1_router.py` prove the text-only body and stream are unchanged.
`test_untouched_app.py` runs because app files change. `test_pii_redaction_integration.py` is
not needed, because no pre-epic test function is renamed or removed. If `tests/test_v1_router.py`
does not exist under that name, use the PRD-015 router test file that `Glob tests/test_v1_*.py`
shows.) Full suite: deferred to orchestrator (user decision).

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| DD-1 diverges from AC3/AC5's literal text (`[]` / `null` on text-only) | Recorded here and in the report. It is the orchestrator's stated preference and the only reading compatible with D10. If the orchestrator wants the literal AC, it is a two-line change: always pass `tool_calls=None, actions=[]` when the flag is on (the router would pass `tools_enabled`). |
| `model_fields_set` semantics: `AssistantMessage(content=x, tool_calls=None)` vs `AssistantMessage(content=x)` | The schema tests pin both dumps in all three serializations (`_all_dumps`). `model_validate` of a dict containing `tool_calls: null` also marks it set, which is the right behaviour. |
| A nested wrap serializer not applied under `model_dump_json` | `_all_dumps` checks python, json-mode and JSON-string dumps for each new shape. |
| Interim SSE says `finish_reason: "tool_calls"` without deltas | Flag off by default. The next story (STORY-012) replaces the pin. No call data leaks (T1). |
| SDK 3.x `tool_calls` union is discriminated on `type` | `type: "function"` is always emitted (the default is a Literal, not None), and the SDK test proves it. |
| `test_completion_refuses_an_unknown_finish_reason["tool_calls"]` changes | Schema-level, not wire: no flag-off response can carry `"tool_calls"` (DD-2). Reported to the orchestrator. |

---

## Acceptance Criteria

(Copied from story STORY-011)

- [ ] AC1. Given a release with two calls and no text, when `translate_result` builds the completion, then `choices[0].message` is `{"role": "assistant", "content": null, "tool_calls": [...]}` with arguments byte-identical to the upstream's, and `finish_reason == "tool_calls"`. Covered by `test_two_released_calls_and_no_text` and `test_allowed_call_is_released_with_content_null_and_finish_tool_calls`.
- [ ] AC2. Every call denied: `content` is the notes, `tool_calls` is `null` (key kept), `finish_reason == "stop"`. Text plus released calls: both present. Covered by `test_every_call_denied_is_the_notes_with_tool_calls_null`, `test_text_plus_released_calls_carries_both`, `test_denied_call_is_the_note_with_tool_calls_null_and_stop` and `test_mixed_response_releases_the_allowed_call_and_notes_the_denied_one`.
- [ ] AC3. `harness.actions` lists one `{tool_call_id, tool_name, decision, rule, reason}` per evaluated call in model order. **Deviation (DD-1):** on a text-only response the key is absent rather than `[]`. Covered by `test_harness_actions_list_every_decision_in_model_order`, `test_harness_actions_serialize_one_entry_per_decision` and `test_without_an_outcome_the_body_is_prd_015s`.
- [ ] AC4. The installed `openai` SDK parses it: arguments equal, `finish_reason == "tool_calls"`. Covered by `test_openai_sdk_parses_released_calls`, `test_completion_with_calls_parses_in_the_openai_sdk` and `test_router_sdk_round_trip`, after Task 4's pinned install. They must be reported as passed, not skipped.
- [ ] AC5. No tool calls: the body is PRD-015's. **Deviation (DD-1):** no keys are added, so `tests/test_v1_translate_result.py`'s existing expectations are **not** edited at all. Covered by `test_without_an_outcome_the_body_is_prd_015s`, `test_flag_on_text_only_body_is_the_flag_off_body`, and the unedited `test_builds_the_section_7_4_example` / `test_completion_matches_section_7_4`.
- [ ] T1. Calls come only from `tool_outcome`. Covered by `test_translate_result_never_reads_upstream_tool_calls` and the unedited `test_router_never_reads_raw_upstream_tool_calls`.
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns
