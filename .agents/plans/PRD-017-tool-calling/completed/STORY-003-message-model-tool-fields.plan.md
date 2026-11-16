---
story: STORY-003
prd: PRD-017
slug: message-model-tool-fields
title: "ToolCallSpec, Message.tool_calls / tool_call_id, and the normalizer"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-017-tool-calling        # all stories commit here, no per-story branch
created: 2026-11-15
---

# Plan: ToolCallSpec, Message.tool_calls / tool_call_id, and the normalizer

## Summary

Widen the one internal message shape in `app/models/messages.py` (PRD-017 Section 6.2, D5). Add a frozen `ToolCallSpec(id, name, arguments)`, and give `Message` two defaulted trailing fields: `tool_calls: tuple[ToolCallSpec, ...] = ()` and `tool_call_id: Optional[str] = None`. Every existing `Message(role, content)` keeps working unchanged. `normalize_message` stops refusing `tool_calls`. It now accepts them on `assistant` turns and requires `tool_call_id` on `tool` turns, checking shape only. Each error is a `MessageNormalizationError` that names the location (`tool_calls[1].function.arguments`) and the rule, never a value. `arguments` is carried as the exact input string: it is never parsed, stripped or re-serialized (PRD-012's contract). `/v1` behaviour does not change, because `v1_translate.translate_messages` still refuses tool calls and tool turns *before* the normalizer (STORY-008 lifts that). Tests: `tests/test_messages.py` only. No test function is renamed or removed.

## User Story

As the PRD-017 implementer
I want the one internal message shape to carry an assistant turn's tool calls and a tool turn's call id
So that every pipeline step can see tool traffic without a second message type

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-003-message-model-tool-fields.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md`: Section 4 lines 53-56, Section 6.2 lines 161-186, D5 line 514
- Client shapes: `.agents/spikes/PRD-017-tool-calling/client-survey.md` lines 42-45 (OpenCode history), 63-65 (Cline history), 104-105 (notes for STORY-003/008)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/models/messages.py`, `tests/test_messages.py` |
| Story | STORY-003 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design`. This story has no UI, and the story's `skills: []` agrees. `chat_ui/AGENTS.md` (Reflex skills) does not apply: no `chat_ui/` file changes. | - |

---

## Patterns to Follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| NAMING | `app/models/messages.py:42-62` | Private `_normalize_<thing>` helpers. Each returns the normalized value or raises `MessageNormalizationError`. |
| ERRORS | `app/models/messages.py:53,56` | Location then rule, never the value: `f"content[{index}] is not a text part"`. `normalize_messages` prefixes `messages[i]: ` (`:86-90`). |
| ERRORS | `app/models/messages.py:33-39` | Docstring rule: name the location and the rule, never the offending value (content is untrusted PII). |
| SCHEMAS | `app/models/messages.py:21-30` | `@dataclass(frozen=True)` with a docstring that says why it is unvalidated. |
| SCHEMAS | `app/services/action_adapters.py:80-86` | `ToolCall(id, name, arguments: str)`, frozen, with the comment "The raw JSON string, exactly as the model emitted it." Mirror the field names and the comment. |
| TESTS | `tests/test_messages.py:69-91,94-131` | Parametrized accept/refuse tables with `ids=[...]` and `pytest.raises(..., match=rule)`. |
| TESTS | `tests/test_messages.py:237-267` | Canary test: the single and the listed forms both lack `CANARY` in `str(exc)` and in `repr(exc.__cause__)`. |
| TESTS | `tests/test_action_adapters.py:651-652` | The field-name assertion `tuple(f.name for f in dataclasses.fields(ToolCall)) == ("id", "name", "arguments")`. The alignment test compares against this. |

### Naming / error handling
```python
# SOURCE: app/models/messages.py:49-57
    if isinstance(content, list):
        texts = []
        for index, part in enumerate(content):
            if not isinstance(part, Mapping) or part.get("type") != "text":
                raise MessageNormalizationError(f"content[{index}] is not a text part")
            text = part.get("text")
            if not isinstance(text, str):
                raise MessageNormalizationError(f"content[{index}] text part has no string text")
```

### Tests
```python
# SOURCE: tests/test_messages.py:129-131
def test_refuses_table_row(raw, rule):
    with pytest.raises(MessageNormalizationError, match=rule):
        normalize_message(raw)
```

---

## Caller and construction inventory (orchestrator note 2)

The orchestrator asked for this list so the implementer can see that widening `Message` is safe. The new fields are **trailing and defaulted**, so every positional `Message(role, content)` call still binds the same two fields. `Message` is a dataclass, not a tuple, so no code can unpack it positionally. A grep for `astuple`, `asdict`, `dataclasses.fields`, `dataclasses.replace`, `__match_args__`, `case Message`, `Message(*` and `**` over `app/ chat_ui/ scripts/ tests/` found **no use on `Message`**. The only `fields(Message)` is `tests/test_messages.py:54`, which this story updates. Equality and hashing still work: both new defaults are equal on every legacy instance, and `tuple[ToolCallSpec]` with frozen items is hashable.

**`normalize_message` / `normalize_messages` callers:**
- `app/services/v1_translate.py:27,231`. This is the only production caller. Its pre-check at `:216-223` refuses `tool_calls`, `function_call` and `role == "tool"` **before** `normalize_message`, so the new accept paths are unreachable from `/v1`. It is not touched here; STORY-008 changes it.
- `tests/test_messages.py`: throughout.
- `tests/test_v1_translate_request.py:33,92` (`test_equals_the_normalizer`: its cases contain no tool fields) and `:239` (wraps the error type).

**`Message` constructed directly (all positional `(role, content)`, none sets the new fields):**
- `app/services/chat_history.py:116-117`: history rows rebuilt as `Message("user", ...)` / `Message("assistant", ...)`.
- `app/services/query_pipeline.py:661`: `Message(message.role, redacted_content)`. **It would drop `tool_calls` / `tool_call_id`** once they can reach step 6. Nothing reaches it with them in this story. STORY-007 must carry them (`dataclasses.replace(message, content=...)`). This plan only flags it; it does not change it.
- `app/services/query_pipeline.py:819`: `[Message("user", prompt)]` (`/query`).
- `chat_ui/chat_ui/state.py:1116`: `Message("user", text)` (chat UI, D17: unchanged).
- `scripts/measure_history_latency.py:498-570`, `scripts/measure_pii_latency.py:538,567`, `scripts/spike_pii_placeholders.py:661-696`.
- Around 30 test files import `Message` (`tests/test_chat_history*.py`, `test_query_pipeline_*.py`, `test_pattern_*.py`, `test_pii_characterization.py`, `test_openrouter_client.py`, `test_v1_query_isolation.py`, `test_two_instance_smoke.py:166`, and more). All construct with two positional arguments.

**`Message` read structurally (role / content only; extra fields are invisible to them):**
- `app/services/duplicate_checker.py:42-44` `DedupTurn` Protocol. `dedup_key` `:59-60` still raises for `tool` (STORY-006).
- `app/services/pattern_detector.py:266-270` `_Turn` Protocol.
- `app/services/conversation_key.py:40-44`.
- `app/services/openrouter_client.py:161`: serializes `{"role", "content"}` only. A tool field would be dropped silently here. STORY-004 owns the serialization.

**Comments that become stale (flagged, not edited here, outside this story's lines):**
- `app/services/pii_redactor.py:523-526`: "`Message` has no `tool_calls` field, `normalize_message` refuses `tool_calls`". That stays true of `/v1` until STORY-008, and STORY-007 owns the redaction contract, so STORY-007 should reword it.

## /v1 tests: expectations do not change (orchestrator note 3)

`tests/test_v1_translate_request.py` and `tests/test_v1_router.py` need **no edits**, because the translator checks for tools first (`app/services/v1_translate.py:214-223`):
- `test_v1_translate_request.py:149-170` (tool turn, `tool_calls` with and without items, `tool_calls: []`) all expect `TOOLS_NOT_SUPPORTED` from that pre-check, never from the normalizer.
- `:244-257` `test_first_failure_wins_tool_turn_before_last_not_user` and `test_tool_calls_are_checked_before_the_normalizer` exercise the same pre-check.
- `:279` (canary with `tool_calls`) is refused by the pre-check.
- `:360-418`: the seeded property test generates `role: "tool"` and `tool_calls: []`, and the translator refuses both before normalizing. The set of accepted lists is therefore identical, and `test_property_generator_is_not_degenerate`'s ratio does not move.
- `:340-347` `test_is_pure` lists `app.models.messages` as an allowed import. That is unchanged.
- `test_v1_router.py:257-261` asserts the `tools` *request field* refusal (`tools: tool calling is not supported (PRD-017)`), a top-level check that does not depend on the normalizer.

The implementer runs both files to prove this (Task 3).

## Client shapes that must normalize (orchestrator note 4)

From `client-survey.md:42-45,63-65`:
- **OpenCode 2.0.10 assistant**: `content` is one string, or **`null` when there are tool calls and no text**. `tool_calls` is present only with calls. Extra keys are `reasoning_details`, `cache_control` and a provider reasoning string.
- **OpenCode tool turn**: `{role: "tool", tool_call_id, content: <string>, cache_control?}`.
- **Cline 3.0.74 assistant**: `content: text || null`; `tool_calls: [{id, type: "function", function: {name, arguments}}]`; the key is omitted when there are no calls; optional `reasoning_content`.
- **Cline tool turn**: `{role: "tool", tool_call_id, content: <string>}`. The content can be `JSON.stringify(value)`, which is just a string here.
- Cline re-stringifies `arguments` in history (`:104`). The normalizer keeps whatever string arrives.

The existing rule at `messages.py:189-191` (extra keys ignored) already covers `cache_control` / `reasoning_*`. Task 2 pins one acceptance case per client shape, extra keys included.

---

## Design

### Model (`app/models/messages.py`)

```python
@dataclass(frozen=True)
class ToolCallSpec:
    """One tool call on an assistant turn (PRD-017 Section 6.2, D5). ..."""
    id: str
    name: str
    #: The raw JSON string, exactly as written; never parsed, stripped or re-serialized.
    arguments: str

@dataclass(frozen=True)
class Message:
    role: Role
    content: str
    tool_calls: tuple[ToolCallSpec, ...] = ()   # assistant only
    tool_call_id: Optional[str] = None          # tool only
```

`ToolCallSpec` is defined above `Message`. `from typing import Any, Literal, Mapping, Optional, Sequence, get_args`: still only `dataclasses` and `typing`, so `test_no_import_in_either_direction` (`tests/test_messages.py:343`) holds. The `Message` docstring adds that the tool fields are also unvalidated in the constructor: per-message shape is the normalizer's job, and cross-message shape (D6) is STORY-005's helper.

### Normalizer check order (inside `normalize_message`)

1. Object check and role check (unchanged, `:66-72`).
2. **`tool_calls`** (before content, as today, so the comment at `:73-74` keeps its reason):
   - If the key is present and role is not `assistant`: `"tool_calls are only allowed on assistant messages"`.
   - If present on assistant: `_normalize_tool_calls(raw["tool_calls"])`. If absent: `()`.
3. **`tool_call_id`**:
   - If role is `tool`: the value must be a non-empty `str`, else `"tool_call_id is required on tool messages and must be a non-empty string"` (this covers missing, `None`, `""` and non-string values).
   - If role is not `tool` and the key is present: `"tool_call_id is only allowed on tool messages"`.
4. Content: `_normalize_content(role, raw.get("content"))`, unchanged. Assistant `null` gives `""` (Section 6.2 row 3: "already allowed").
5. `return Message(role, content, tool_calls, tool_call_id)`.

`_normalize_tool_calls(calls) -> tuple[ToolCallSpec, ...]`. Each item is checked in this order, and the first failure wins:

| Check | Message (location + rule, no value) |
|---|---|
| `isinstance(calls, list)` else | `tool_calls must be a list` |
| `[]` | returns `()` (OpenAI SDKs send it; PRD 6.2) |
| item is a `Mapping` else | `tool_calls[i] is not an object` |
| `id` is a non-empty `str` else | `tool_calls[i].id must be a non-empty string` |
| `type == "function"` else (missing too) | `tool_calls[i].type must be "function"` |
| `function` is a `Mapping` else | `tool_calls[i].function is not an object` |
| `function.name` is a non-empty `str` else | `tool_calls[i].function.name must be a non-empty string` |
| `function.arguments` is a `str` else (missing, `None`, dict) | `tool_calls[i].function.arguments must be a string` |
| `id` not seen earlier in this turn else | `tool_calls[i].id repeats an earlier id in this turn` |

The result is `tuple(ToolCallSpec(id, name, arguments))` in input order. `arguments` is the input object itself, never touched. `""` and non-JSON strings are accepted, because the normalizer never parses (D13). Extra keys on an item or on `function` (`index`, provider fields) are ignored, as at the message level.

**Why `isinstance(list)`, not `Sequence`:** it mirrors `_normalize_content` (`:49`). JSON gives lists, and a `str` would otherwise pass as a `Sequence`.

### Design decisions / deviations to note

- **DD1. `tool_calls: null` and `tool_call_id: null` on the wrong role are refused** ("not a list" / "only allowed on tool messages"). The rule is a key-presence test, which follows AC4 to the letter. The client survey shows both clients *omit* the key when there are no calls, so neither client is affected. Some OpenAI-SDK `model_dump()` echoes emit `"tool_calls": null`. If STORY-008 needs to tolerate that, it can strip `None` at the edge or relax this rule there, with a test. Flagged as an open question below.
- **DD2. Empty `id` / `name` are refused, while empty `arguments` is accepted.** An id must be answerable by a `tool_call_id`, which itself must be non-empty (PRD 6.2), so `""` cannot be an id. An empty name could never match a mapping. Empty arguments are a legitimate model output for a tool that takes no arguments.
- **DD3. The D6 cross-message helper is STORY-005's** (orchestrator note 1). It is not planned or written here.
- **DD4. Role comment reword**: `messages.py:14-15` says "so PRD-016 does not have to widen the type". Reword it to PRD-017, and note that tool turns now normalize while the pipeline still refuses them at step 0 until STORY-005. The module docstring gains one sentence on the PRD-017 D5 tool fields. The PRD-016 numbering lines in `tests/test_messages.py:109,146` are removed along with their cases.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/messages.py` | UPDATE | `ToolCallSpec`; two `Message` fields; `_normalize_tool_calls`; the new checks in `normalize_message`; comment and docstring rewording |
| `tests/test_messages.py` | UPDATE | Replace the two refusal cases with acceptance cases; update the fields assertion and the two `tool`-role cases; add acceptance, refusal, canary and alignment tests |

No file is created. No `app/services/*`, `chat_ui/*` or `/v1` test changes.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Model and normalizer

- **File**: `app/models/messages.py`
- **Action**: UPDATE
- **Implement**: the design above. Add `Optional` to the `typing` import. Add `ToolCallSpec` (frozen, docstring citing PRD-017 Section 6.2 / D5, saying it is deliberately not `action_adapters.ToolCall` because this module imports nothing from `app`, and that a test keeps the field names aligned). Add the two trailing defaulted `Message` fields with `# assistant only` / `# tool only` comments. Add `_normalize_tool_calls` below `_normalize_content`. In `normalize_message`, replace `:73-77` with steps 2-5 and keep the "Before content" comment, reworded to say why the order still matters: a `tool` turn without an id must fail on the id, and tool shape is checked before content. Reword the Role comment (`:14-15`) and add the module docstring sentence (DD4). Error strings never interpolate a value, only `i`.
- **Mirror**: `app/models/messages.py:42-62` (helper shape, messages), `app/services/action_adapters.py:80-86` (field comment).
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"` prints OK.

### Task 2: Tests

- **File**: `tests/test_messages.py`
- **Action**: UPDATE. Keep every existing `def test_*`; rename or remove none, so `_DELIBERATELY_SUPERSEDED_TESTS` (`tests/test_pii_redaction_integration.py:476`) needs **no** entry (`_TEST_DEF` at `:331` matches function names, not parametrize ids). If the implementer does rename or remove a function, register it there.
- **Implement**:
  1. **Modified assertions** (each with a comment `# PRD-017 D5 (STORY-003): ...`):
     - `:54`: fields become `["role", "content", "tool_calls", "tool_call_id"]`.
     - `:79` `tool-role-with-string-content`: the raw gains `"tool_call_id": "c1"`, and the expected value becomes `Message("tool", "ls output", tool_call_id="c1")`.
     - `:106` `null-on-tool`: the raw gains `"tool_call_id": "c1"`, so it still tests the null-content rule rather than the missing id.
     - `:107-117` `tool-calls-key` (refused with `PRD-017`): removed from the refusal table. That exact shape becomes the AC2 acceptance case.
     - `:146-147` `tool-calls-empty-list` (refused): removed from the malformed table. It becomes an acceptance case giving `()`, with content `"x"`.
     - Update the docstring at `:1-9`: one line saying PRD-017 STORY-003 adds the tool fields (Section 6.2).
  2. **New `test_tool_call_spec_is_frozen_with_the_specified_fields`**: the fields are `("id", "name", "arguments")`, frozen, and `Message("user", "x").tool_calls == ()` / `.tool_call_id is None` (legacy construction unchanged, AC1).
  3. **New `test_tool_call_spec_fields_match_action_adapters_tool_call`**: `from app.services.action_adapters import ToolCall`, then compare `dataclasses.fields` names (AC5, PRD 6.2 line 178).
  4. **New parametrized `test_normalizes_tool_shape`** (ids in brackets):
     - [assistant-null-content-one-call] the exact AC2 input gives `Message("assistant", "", (ToolCallSpec("c1", "bash", "{\"command\":\"ls\"}"),))`.
     - [empty-tool-calls-becomes-empty-tuple] `tool_calls: []` gives `tool_calls == ()`.
     - [assistant-text-and-calls] string content is kept alongside the calls.
     - [two-calls-in-order]
     - [tool-turn-string] `{"role": "tool", "tool_call_id": "c1", "content": "ok"}` gives `Message("tool", "ok", tool_call_id="c1")` (AC3).
     - [tool-turn-text-parts] `content: [_text("ok")]` gives the same result (AC3).
     - [opencode-assistant] `content: None`, calls, plus `reasoning_details` / `cache_control` extra keys (survey `:42`).
     - [opencode-tool-turn] with `cache_control` (survey `:43`).
     - [cline-assistant] `content: None`, calls, `reasoning_content` (survey `:63`).
     - [cline-tool-turn-json-string-content] (survey `:65`).
     - [extra-keys-on-call-and-function-ignored] (`index`).
  5. **New `test_arguments_are_carried_byte_for_byte`**: parametrize over `""`, `"{"` (invalid JSON), `' { "a" : 1 } \n'` (whitespace), a non-ASCII `"{\"q\":\"acentuación 🙂\"}"` and a nested JSON string. Assert `spec.arguments == raw_arguments` and `type(spec.arguments) is str`. This proves the value is not parsed, stripped or re-serialized (D13).
  6. **New parametrized `test_refuses_tool_shape`** (one case per AC4 rule; `match` on the location and rule, regex-escaped):
     - `tool_calls` on `user`, on `system` and on `tool`: `only allowed on assistant`
     - `tool_calls` as a dict, a string and `None`: `tool_calls must be a list`
     - item not an object: `tool_calls\[0\] is not an object`
     - missing `id`, and `id` set to `""` or `3`: `tool_calls\[0\]\.id must be a non-empty string`
     - `type` missing or `"custom"`: `tool_calls\[0\]\.type must be "function"`
     - `function` missing or a string: `tool_calls\[0\]\.function is not an object`
     - name missing or empty: `tool_calls\[0\]\.function\.name`
     - arguments missing, a dict or `None`, on the *second* call: `tool_calls\[1\]\.function\.arguments must be a string` (the AC4 example location)
     - duplicate ids: `tool_calls\[1\]\.id repeats an earlier id`
     - `tool` turn with `tool_call_id` missing, `""`, `None` or `7`: `tool_call_id is required on tool messages`
     - `tool_call_id` on `user`, `assistant` or `system`: `tool_call_id is only allowed on tool messages`
  7. **New `test_tool_shape_error_names_message_index`**: `normalize_messages([user, bad])` starts with `messages[1]: tool_calls[0].function.arguments`.
  8. **Extend `test_error_never_echoes_content`** (`:237-267`). Add cases with the comment `# PRD-017 D5 (STORY-003): tool-shape errors withhold values too`: canary in a duplicate id; canary as a non-string `arguments` (`{"x": _CANARY}`); canary as `name` with the wrong `type`; canary `tool_call_id` on a `user` turn; a `tool` turn with canary content and no id; canary `tool_calls` value as a string. The existing `tool-calls-with-canary-content` case stays and is still refused (now by the `type` rule).
  9. **New `test_normalize_messages_accepts_a_client_tool_loop`**: `[system, user, assistant(null, calls c1,c2), tool(c1), tool(c2)]` normalizes, in order, to the expected `Message`s. Its comment says the normalizer does not check the D6 cross-message rules (STORY-005).
- **Mirror**: `tests/test_messages.py:69-131,237-267`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_messages.py -q`

### Task 3: Targeted regression run (one pytest call, foreground)

- **Validate**:
  `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_messages.py tests/test_v1_translate_request.py tests/test_v1_router.py tests/test_action_adapters.py tests/test_dedup_key.py tests/test_pii_redaction_integration.py tests/test_untouched_app.py tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py -q`
  - `test_v1_*` prove that `/v1` expectations did not change (note 3), with no edits to those files.
  - `test_pii_redaction_integration.py` is the superseded-name guard. `test_untouched_app.py` is required because an `app/` file changed.
  - The `*_outcomes_regression` files prove D17 (`/query` and chat unchanged).
  - Full suite: deferred to the orchestrator (user decision).

---

## End-to-End Tests

- [ ] `from app.main import app` imports (Task 1).
- [ ] No HTTP-level change is possible in this story: `/v1` still refuses tools before the normalizer. The proof is that `tests/test_v1_router.py` stays green and unedited.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest <Task 3 file list> -q
git diff --stat -- tests/test_v1_translate_request.py tests/test_v1_router.py   # must be empty
```

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| A `tool` turn now needs `tool_call_id`, so a direct normalizer caller that sent `{"role": "tool", "content": ...}` would start failing | The only production caller (`v1_translate`) refuses `tool` before normalizing. The two tests that sent it are updated (Task 2.1). |
| `query_pipeline.py:661` and `openrouter_client.py:161` silently drop the new fields | Nothing carrying them reaches those lines until STORY-008 opens `/v1`. Flagged for STORY-007 / STORY-004 (inventory above). |
| SDK echoes with `"tool_calls": null` | DD1: refused per AC4. Open question for STORY-008. |
| Someone later "cleans" `arguments` | `test_arguments_are_carried_byte_for_byte`, and the `ToolCallSpec` field comment. |

## Open questions for the orchestrator

1. DD1: should `tool_calls: null` (and `tool_call_id: null` on non-tool roles) count as absent? This plan refuses both, per AC4. Neither surveyed client sends them. Decide in STORY-008 if needed.
2. `pii_redactor.py:523-526`'s docstring ("`Message` has no `tool_calls` field") is outdated after this story, but it lies outside this story's lines. Suggest STORY-007 rewords it.

---

## Acceptance Criteria

(Copied from story `STORY-003`)

- [ ] AC1: `ToolCallSpec(id: str, name: str, arguments: str)` (frozen); `Message` gains `tool_calls: tuple[ToolCallSpec, ...] = ()` and `tool_call_id: Optional[str] = None`; every existing `Message(role, content)` works unchanged; the module still imports nothing from `app`. Covered by Task 1, Task 2.1 (`:54`), 2.2, and the existing `test_no_import_in_either_direction` / `test_is_pure`, plus the Task 3 run over the suites that construct `Message`.
- [ ] AC2: the assistant `content: null` + `tool_calls` input normalizes to `Message("assistant", "", (ToolCallSpec("c1", "bash", "{\"command\":\"ls\"}"),))` with byte-identical arguments, and `tool_calls: []` gives `()`. Covered by Task 2.4 and 2.5.
- [ ] AC3: a `tool` turn (string content or text parts) gives `Message("tool", "ok", tool_call_id="c1")`. Covered by Task 2.4.
- [ ] AC4: each invalid shape raises `MessageNormalizationError` naming the location and the rule, never the value. Covered by Task 2.6, 2.7 and 2.8.
- [ ] AC5: the old `PRD-017` refusal assertions are replaced and commented with PRD-017 D5; renamed or removed functions are registered (none planned); `ToolCallSpec` fields equal `action_adapters.ToolCall`'s. Covered by Task 2.1 and 2.3.
- [ ] All tasks completed
- [ ] Backend imports without error
- [ ] `tests/test_v1_translate_request.py` and `tests/test_v1_router.py` unedited and green
- [ ] Follows existing patterns
