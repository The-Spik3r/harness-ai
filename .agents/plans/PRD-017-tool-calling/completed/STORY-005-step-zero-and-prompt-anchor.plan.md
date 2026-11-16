---
story: STORY-005
prd: PRD-017
slug: step-zero-and-prompt-anchor
title: "Step 0 accepts tool turns under the D6 shape rules; the audit prompt is the final turn"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-017-tool-calling
created: 2026-11-15
---

# Plan: Step 0 accepts tool turns under the D6 shape rules; the audit prompt is the final turn

## Summary

Move the PRD-017 D6 conversation-shape rule into one pure helper,
`conversation_shape_violation(messages) -> Optional[tuple[int, str]]`, in
`app/models/messages.py`. It returns the first violation as `(index, rule)` or
`None`. Step 0 (`_validate_conversation`) keeps its own empty check, drops the
blanket "tool turns are not supported (PRD-017)" refusal, and raises
`InvalidConversationError(f"messages[{i}]: {rule}")` from the helper's result.
STORY-008's `/v1` edge will call the same helper and raise `V1RequestError`.

The audit `prompt` local stays `messages[-1].content`. It is now the final turn,
user or tool (D7), and every `log_query` / `_deny` site already receives that one
local, so only the comment changes. Step 6's PII-entity rule already keys on
`index == last_index`, so it only needs its comment generalized from "the last
user turn" to "the final turn" (PRD-010 D7). The rebuild at `:661` is STORY-007's
and does not change here.

Tests: the helper is tested directly in `tests/test_messages.py`. The pipeline
ACs are tested in a new `tests/test_query_pipeline_tools.py`, which
**monkeypatches `query_pipeline.dedup_key`** to get past step 1 with tool turns
(`dedup_key` still raises for tool turns until STORY-006).

## User Story

As the PRD-017 implementer
I want `run_conversation` to accept a conversation that ends in a tool result, and to refuse one whose tool turns do not answer a call
So that an agent's tool loop can run through the pipeline and a malformed one is still a programming error

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-005-step-zero-and-prompt-anchor.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md` (Sections 6.1, 6.3, 7/F4, 15/D6, D7)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/models/messages.py`, `app/services/query_pipeline.py`, comments in `app/services/conversation_key.py` and `app/services/pii_policy.py`, tests |
| Story | STORY-005 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| _(none)_ | `.agents/skills/` holds only `frontend-design` (UI aesthetics). This story has no UI, and the story's `skills: []` agrees. | — |

---

## Current state (verified on `epic/PRD-017-tool-calling` @ f0ff56a)

| What | Where | Note |
|------|-------|------|
| `_validate_conversation` | `app/services/query_pipeline.py:69-75` | empty → `"messages must not be empty"`; any `tool` → `"tool turns are not supported (PRD-017)"`; last ≠ user → `"the last message must be a user turn"` |
| `InvalidConversationError` docstring | `app/services/query_pipeline.py:58-66` | "Unreachable from any ingress in this PRD", raised before dedup_key / authz / any log_query |
| Step 0 call + prompt anchor | `app/services/query_pipeline.py:279-284` | comment `# Guaranteed by validation: the last message is always role == "user".` |
| Step 1 | `app/services/query_pipeline.py:301-303` | `dedup_key(...)` (raises on tool, `duplicate_checker.py:59-60`), `conversation_key(...)` |
| `conversation_key` | `app/services/conversation_key.py:40-45` | `next(m.content for m in messages if m.role == "user")` **with no default**; comment at `:42-43` relies on step 0's "last is user" |
| `prompt=prompt` sites | `query_pipeline.py:234` (`_deny`), `:402, :447, :478, :527, :562, :603, :647, :681, :739, :768`; `_deny(identity, prompt, ...)` at `:310, :321, :333, :354` | 11 `log_query(` calls, all pass the one `prompt` local. No change needed (D7) |
| Step 5 flag comment | `query_pipeline.py:553-557` | "Its `tool` cell stays unreachable: step 0 refuses `tool` turns until PRD-016." |
| Step 6 loop + comments | `query_pipeline.py:621-663` | `last_index = len(messages) - 1`; `if index == last_index: input_entities = entities`. Comments at `:627-631` ("Only the last user turn's entities ... The last message is always a `user` turn (step 0)") and `:638-639` ("A `tool` turn cannot get here; step 0 refuses it until PRD-016.") |
| Rebuild (STORY-007's, do not touch) | `query_pipeline.py:661` | `Message(message.role, redacted_content)` drops `tool_call_id` |
| `has_tool_calls=False` comment | `query_pipeline.py:775-778` | "PRD-016 sets this ... step 0 refuses `tool` turns" |
| `chat` policy note | `app/services/pii_policy.py:84-87` | "`chat` lists `tool` for completeness only: step 0 refuses `tool` turns, so no `chat` request carries one." |
| `code` covers `tool` | `app/services/pii_policy.py:130`; patterns `app/services/pattern_config.py:249` (`"tool": "flag"`) | so a final tool turn's PII is redacted and counted under `code` with no code change |
| messages.py pointers to STORY-005 | `app/models/messages.py:15-17`, `:43-45`, `:123` | to be reworded |
| Existing step-0 tests | `tests/test_query_pipeline_run_conversation.py:141-166` (param `tool-turn-present` = `[tool("x"), user]`); `tests/test_query_pipeline_multiturn.py:835-863` (param `tool-turn` = `[tool("{}"), user]`) | They assert only `pytest.raises(InvalidConversationError)` and zero rows, **not** the message text. Both inputs still violate D6 (a tool turn first), so they stay green unchanged |
| `/v1` edge strings | `app/services/v1_translate.py:220-238` | `"tool turns are not supported (PRD-017)"` and `"the last message must be a user turn"` are the **edge's** strings, pinned by `tests/test_v1_translate_request.py:151,178,184` and `tests/e2e/test_aider.py:443`. STORY-008's, flag-off byte-identical (D10). **Not touched here.** |

---

## Patterns to Follow

### Naming / pure helper style (location + rule, never a value)
```python
# SOURCE: app/models/messages.py:161-170
def normalize_messages(raw: Sequence[Mapping[str, Any]]) -> list[Message]:
    ...
    for index, item in enumerate(raw):
        try:
            messages.append(normalize_message(item))
        except MessageNormalizationError as exc:
            raise MessageNormalizationError(f"messages[{index}]: {exc}") from exc
```
```python
# SOURCE: app/models/messages.py:113-115 (rule names the field, not the id)
        if call_id in seen:
            raise MessageNormalizationError(f"{where}.id repeats an earlier id in this turn")
```

### Error handling (step 0)
```python
# SOURCE: app/services/query_pipeline.py:69-75
def _validate_conversation(messages: Sequence[Message]) -> None:
    if not messages:
        raise InvalidConversationError("messages must not be empty")
    if any(m.role == "tool" for m in messages):
        raise InvalidConversationError("tool turns are not supported (PRD-017)")
    if messages[-1].role != "user":
        raise InvalidConversationError("the last message must be a user turn")
```

### Tests: zero audit rows on InvalidConversationError
```python
# SOURCE: tests/test_query_pipeline_run_conversation.py:154-166
def test_invalid_conversation_raises_before_any_audit_row(temp_db, monkeypatch, messages):
    monkeypatch.setattr(query_pipeline, "authorize", _fail_if_called)
    monkeypatch.setattr(query_pipeline, "dedup_key", _fail_if_called)
    before = _count_audit_rows()
    with pytest.raises(query_pipeline.InvalidConversationError):
        query_pipeline.run_conversation(...)
    assert _count_audit_rows() == before
```

### Tests: audit prompt on an arm
```python
# SOURCE: tests/test_query_pipeline_run_conversation.py:196-213
    assert isinstance(result, QueryBlockedDuplicateResponse)
    row = _last_audit_entry()
    assert row.prompt_preview == "second"
    assert row.prompt_hash == hash_prompt("second")
```

### Tests: PII fields under `code` (final-turn entities only)
```python
# SOURCE: tests/test_query_pipeline_pii_profiles.py:83-90 (shipped code policy fixture)
#         tests/test_query_pipeline_pii_profiles.py:362-382 (final-turn entities, history masked not recorded)
#         tests/test_query_pipeline_pii_profiles.py:145-153 (_pii_fields helper)
```

### Tests: every log_query call site
```python
# SOURCE: tests/test_query_pipeline_dedup_key.py:206-228  (_log_query_call_sources, importable)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/messages.py` | UPDATE | Add pure `conversation_shape_violation`. Reword the STORY-005 pointers (`:15-17`, `:43-45`, `:123`) |
| `app/services/query_pipeline.py` | UPDATE | `_validate_conversation` uses the helper. Reword the `InvalidConversationError` docstring, the `:283` anchor comment, the `:553-557` and `:627-639` comments, and the false clause in the `:775-778` comment (PRD-016 → PRD-017) |
| `app/services/conversation_key.py` | UPDATE (comment only) | `:42-43`: the user turn's existence is now guaranteed by the helper's user-turn rule, not by "last is user" |
| `app/services/pii_policy.py` | UPDATE (docstring only) | `:84-87`: `tool` is no longer refused at step 0. It stays unreachable under `chat` because only `/v1` (profile `code`) can send one |
| `tests/test_messages.py` | UPDATE (add tests only) | Helper: accept cases, each violation's `(index, rule)`, no value echoed, purity |
| `tests/test_query_pipeline_tools.py` | CREATE | Step 0 refusals (zero rows), D7 prompt anchor on several arms, PII final-turn rule under `code`, one-prompt-local source check |
| `tests/test_query_pipeline_run_conversation.py` | UPDATE (comment only) | Comment on the `tool-turn-present` param: still refused, now by D6 (a tool turn first) |
| `tests/test_query_pipeline_multiturn.py` | UPDATE (comment only) | Same for its `tool-turn` param |

No test function is renamed or removed, so `_DELIBERATELY_SUPERSEDED_TESTS` (`tests/test_pii_redaction_integration.py:476`) needs no entry (see AC5 below).

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: The pure D6 helper

- **File**: `app/models/messages.py`
- **Action**: UPDATE
- **Implement**: add after `Message` / before `MessageNormalizationError` (or at the end of the module; the implementer chooses, matching flow):
  ```python
  def conversation_shape_violation(messages: Sequence[Message]) -> Optional[tuple[int, str]]:
  ```
  Docstring: PRD-017 Section 6.3 / D6. It is shared by step 0 (`InvalidConversationError`) and the `/v1` edge (STORY-008, `V1RequestError`) so the two cannot drift. It returns the **first** violation in walk order as `(index, rule)`, or `None`. The rule strings name the rule only, never a role's content or an id (PRD-015 T6). The caller formats `messages[{index}]: {rule}`. **Non-empty is the caller's check** (its location is `messages`, not `messages[i]`), so `[]` returns `None`. Say this in the docstring and pin it in a test.

  Algorithm (one pass):
  - `open_ids: Optional[frozenset[str]] = None` (the ids of the nearest preceding assistant turn with `tool_calls`, while only `tool` turns have followed it), and `answered: set[str]`.
  - For each `index, m`:
    - `m.role == "tool"`:
      - `open_ids is None` → `(index, "a tool turn must follow an assistant turn with tool_calls, with only tool turns between")`. This covers a tool turn first, and one separated by `user`, `system` or a call-less `assistant`.
      - `m.tool_call_id not in open_ids` → `(index, "tool_call_id is not an id of the preceding assistant turn's tool_calls")`. This also catches `None`, since `Message` is unvalidated.
      - already in `answered` → `(index, "tool_call_id answers a call that was already answered")`.
      - else add it to `answered`.
    - `m.role == "assistant" and m.tool_calls` → `open_ids = frozenset(c.id for c in m.tool_calls)`; `answered = set()`.
    - any other turn → `open_ids = None`.
  - After the loop: `messages[-1].role not in ("user", "tool")` → `(len-1, "the last message must be a user or tool turn")`.
  - Then: no `user` turn anywhere → `(len-1, "the conversation must contain a user turn")`. **This is a deviation, see Risks R1.**

  "Answered once" is scoped to its assistant turn, which matches rule 2's "nearest preceding" binding. Some providers reuse ids like `call_0` on every round, and a later round may answer `call_0` again. Comment this.

  Module docstring and comments:
  - `:15-17` (Role comment) → tool turns normalize (D5), and the pipeline accepts them under D6 (`conversation_shape_violation`).
  - `Message` docstring `:43-45` → "cross-message shape (D6) is `conversation_shape_violation`'s".
  - `normalize_message` docstring `:123` → same.
  - `normalize_messages` comment `:162-163` may stay ("the pipeline's to check"); optionally add "(and the `/v1` edge's, via `conversation_shape_violation`)".

  Keep the module pure: no new import beyond `dataclasses` / `typing` (`tests/test_messages.py:612-626` enforce this).
- **Mirror**: `app/models/messages.py:86-117` (`_normalize_tool_calls`: walk, `seen` set, location/rule messages)
- **Validate**: `.venv/Scripts/python -c "from app.models.messages import conversation_shape_violation; print('OK')"`

### Task 2: Step 0 uses the helper; the prompt anchor and comments

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  - Import `conversation_shape_violation` from `app.models.messages` (the `Message` import is already there).
  - `_validate_conversation` (`:69-75`):
    ```python
    if not messages:
        raise InvalidConversationError("messages must not be empty")
    violation = conversation_shape_violation(messages)
    if violation is not None:
        index, rule = violation
        raise InvalidConversationError(f"messages[{index}]: {rule}")
    ```
    Add a one-line docstring or comment citing PRD-017 D6, Section 6.3: the same helper as the `/v1` edge, so step 0 is the programming-error guard behind it (PRD-010 Section 6.1). The message text for an assistant-final conversation changes from `"the last message must be a user turn"` to `"messages[N]: the last message must be a user or tool turn"`. No pipeline test asserts the old text (grep verified). The `/v1` edge string in `v1_translate.py:238` is separate and unchanged.
  - `InvalidConversationError` docstring (`:58-66`): keep "raised before dedup_key, authorization, or any log_query call, so it writes no audit row". Say that `/v1` checks the same D6 rules at the edge first (STORY-008), so it is still unreachable from an ingress.
  - `:283` comment → `# PRD-017 D7: the audit prompt is the final turn, user or tool -- what this request added. Validation guarantees it is one of the two.` The code stays `prompt = messages[-1].content`. **Do not add a second prompt local.** Every `log_query(prompt=prompt, ...)` and `_deny(identity, prompt, ...)` site (listed under Current state) already reads it.
  - `:553-557` comment: the `code` `tool` cell becomes reachable once `/v1` forwards tool turns (STORY-008). Until then only tests reach it. Reword "PRD-016" → PRD-017.
  - `:627-631` comment: "Only the **final** turn's entities count toward the audit's PII fields (PRD-010 D7, generalized by PRD-017 D7 from 'the last user turn'): it is what this request added. The final turn is `user` or `tool` (step 0), and both policies cover both roles (`pii_policy.py:113, :130`)." Keep the re-redacting-history rationale.
  - `:638-639` comment: drop "A `tool` turn cannot get here; step 0 refuses it until PRD-016." Every policy covers `tool`, so a `tool` turn never takes this branch. (State it as a fact; no code change.)
  - **Do not touch `:661`** (`Message(message.role, redacted_content)`, STORY-007's) or `:662` (`if index == last_index:`, already the final-turn rule).
  - `:775-778` comment: replace "PRD-016 sets this ... no row can carry tool calls -- step 0 refuses `tool` turns --" with "PRD-017 STORY-010 sets this from the request and the response; until then it is False". Keep the PRD-013 F5 sentence.
- **Mirror**: `app/models/messages.py:168-169` (`messages[{index}]: ...` formatting)
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 3: Comment-only corrections elsewhere

- **Files**: `app/services/conversation_key.py:42-43`, `app/services/pii_policy.py:84-87`
- **Action**: UPDATE (comments/docstrings only, no behaviour)
- **Implement**:
  - conversation_key: "No default: step 0 (`conversation_shape_violation`, PRD-017 D6) guarantees the conversation contains a user turn." This is the rule added in Task 1 (R1).
  - pii_policy: "`chat` lists `tool` for completeness: only `/v1`, under `code`, can send a `tool` turn (PRD-017), so no `chat` request carries one." Keep the rest.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 4: Helper tests

- **File**: `tests/test_messages.py`
- **Action**: UPDATE (append a `# --- PRD-017 STORY-005: conversation shape (D6) ---` section; do not edit existing assertions)
- **Implement** (local builders: `_u(text)`, `_a(text, *ids)` → `Message("assistant", text, tuple(ToolCallSpec(i, "ls", "{}") for i in ids))`, `_t(id, text="out")` → `Message("tool", text, tool_call_id=id)`):
  - `test_shape_accepts` parametrized, each → `None`:
    - user-only;
    - `[system, user, assistant, user]`;
    - AC1's `[user, assistant(c1,c2), tool(c1), tool(c2)]`;
    - partial answer `[user, assistant(c1,c2), tool(c2)]` (not every call need be answered, Section 6.3);
    - two rounds `[u, a(c1), t(c1), a(c2), t(c2)]`;
    - an id reused across rounds `[u, a(c1), t(c1), a(c1), t(c1)]`;
    - a tool loop then a user turn `[u, a(c1), t(c1), a("done"), u]`;
    - `[]` (precondition, comment that non-empty is the caller's).
  - `test_shape_refuses` parametrized `(messages, (index, rule))`:
    - last `assistant` → `(1, last-turn rule)`;
    - last `system` → `(1, ...)`;
    - tool first `[t(c1), u]` → `(0, follow rule)`;
    - unknown id `[u, a(c1), t(c9)]` → `(2, id rule)`;
    - separated by user `[u, a(c1), u, t(c1)]` → `(3, follow rule)`;
    - separated by a call-less assistant `[u, a(c1), a("x"), t(c1)]` → `(3, follow rule)`;
    - answered twice `[u, a(c1), t(c1), t(c1)]` → `(3, answered rule)`;
    - `tool_call_id=None` after a calls turn → `(2, id rule)`;
    - no user turn `[a(c1), t(c1)]` → `(1, user-turn rule)` (R1);
    - first violation wins `[t(c1), u, a("x")]` → `(0, ...)`.
  - `test_shape_rule_never_echoes_values`: content and ids set to a sentinel such as `"SECRET-7f3a"` across each refusal case. Assert the sentinel is not in the rule.
  - `test_shape_helper_signature`: `list(inspect.signature(conversation_shape_violation).parameters) == ["messages"]`. Added as a new test so the existing `test_exports_the_specified_names_and_signatures` assertions stay unedited.
  - `test_no_import_in_either_direction` / `test_is_pure` already cover purity (unchanged).
- **Mirror**: `tests/test_messages.py:398-520` (tool-shape parametrized tables)
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_messages.py -q`

### Task 5: Pipeline tests (new file)

- **File**: `tests/test_query_pipeline_tools.py`
- **Action**: CREATE
- **Implement**: module docstring: PRD-017 STORY-005, D6/D7, with the dedup decision stated: *"`dedup_key` still raises for tool turns until STORY-006, so every test here that passes step 0 with a tool turn monkeypatches `query_pipeline.dedup_key` with a stub. The end-to-end key over tool turns is STORY-006's; the upstream message shape (tool fields kept through step 6) is STORY-007's, and nothing here asserts it."* Use the same env setdefaults and helpers as `tests/test_query_pipeline_run_conversation.py:14-55`. For the `code` policy, copy the `_SHIPPED_CODE_SETTINGS` fixture pattern from `tests/test_query_pipeline_pii_profiles.py:72-90`. Import it instead if that is clean: importing from `tests.test_query_pipeline_pii_profiles` brings its autouse fixture only into that module, so copy the dict, or import the dict and write a local fixture.
  - Stub: `_stub_key = lambda user_id, turns: "stub-" + "0" * 59` (a fixed string). Use it in a `_keyed` fixture that monkeypatches `query_pipeline.dedup_key`. It is fixed on purpose: the duplicate-arm test runs the same conversation twice.
  - **AC1**: `test_validate_accepts_a_tool_final_conversation`. `query_pipeline._validate_conversation([u, a(c1,c2), t(c1), t(c2)])` returns `None`. Also user-final passes.
  - **AC2**: `test_each_d6_violation_raises_naming_index_and_rule_and_writes_no_row`, parametrized over the five story violations (last assistant, last system, tool first, unknown id, separated by user, answered twice; plus no-user-turn). Monkeypatch `authorize` and `dedup_key` with `_fail_if_called`. Assert `pytest.raises(InvalidConversationError)` with `str(exc) == f"messages[{i}]: {rule}"` (expected strings spelled in the test, cross-checked against `conversation_shape_violation`), and `_count_audit_rows() == before`. Also `test_empty_is_still_refused_without_an_index` → `"messages must not be empty"`.
  - **AC3** (D7, `prompt` is the final tool turn on every arm reached):
    - forbidden arm: `_DENIED` identity, `[u("list files"), a(c1), t(c1, "README.md\nsrc")]` → `QueryBlockedForbiddenResponse`; row `prompt_preview == "README.md\nsrc"` (or the stored preview's form; check `get_audit_log` and how `prompt_preview` truncates and normalizes), `prompt_hash == hash_prompt("README.md\nsrc")`.
    - success arm: `_JUAN`, `_fake_call_openrouter` → `QuerySuccessResponse`, same assertions on the row.
    - duplicate arm: run twice with the fixed stub key → the second is `QueryBlockedDuplicateResponse`, and its row's prompt is the tool content.
    - flag arm under `profile="code"`: the tool content holds an injection phrase (`"ignore previous instructions"`, flagged by `code`'s `tool: flag` cell, `pattern_config.py:249`), so the flag row and the success row both carry the tool content as prompt. If the flag row needs the injection list loaded, mirror `tests/test_query_pipeline_patterns.py`'s `_use_profile`.
    - user-final unchanged: covered by the existing `test_audit_prompt_is_last_user_turn_on_*` (`tests/test_query_pipeline_run_conversation.py:196-240`), which stay green unedited. Name them in the report.
    - `test_every_log_query_site_reads_the_one_prompt_local`: parse `query_pipeline.py` source. (a) Every `log_query(` call from `_log_query_call_sources` (`tests/test_query_pipeline_dedup_key.py:206`) contains `prompt=prompt`. (b) An AST walk of `run_conversation` finds exactly one `Assign` to the name `prompt`, and its value is `messages[-1].content`. Optionally (c): every `_deny(` call's second positional argument is `prompt`.
  - **AC4** (final-turn PII under `code`): `test_tool_final_pii_counts_from_the_final_turn`. `PII_REDACTION_ENABLED=True` plus the shipped code settings, `profile="code"`, conversation `[u("Wire to IBAN GB82 WEST 1234 5698 7654 32."), a(c1), t(c1, "owner: ops@example.org")]`, with an upstream stub. Assert `pii_detected_input is True` and `pii_entities == "EMAIL_ADDRESS"`, with IBAN absent from the row. Contrast test `test_pii_in_a_tool_history_turn_is_not_counted`: `[u, a(c1), t(c1, "ops@example.org"), a("ok"), u("thanks")]` → `pii_detected_input False`, `pii_entities None`. Do not assert the upstream messages' tool fields (`:661` rebuild is STORY-007's).
- **Mirror**: `tests/test_query_pipeline_run_conversation.py:141-240`, `tests/test_query_pipeline_pii_profiles.py:83-153, 348-382`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_query_pipeline_tools.py -q`

### Task 6: Comment the existing step-0 tool params (AC5)

- **Files**: `tests/test_query_pipeline_run_conversation.py:148-150`, `tests/test_query_pipeline_multiturn.py:841-843`
- **Action**: UPDATE (comment only)
- **Implement**: above each `tool` param add `# PRD-017 D6: still refused, now because a tool turn comes first (it answers no assistant tool_calls turn), not because tool turns are unsupported.` Keep the ids (`tool-turn-present`, `tool-turn`) and the test function names unchanged, so nothing is superseded. If the implementer judges the id now misleading, it may rename the **param id** only (not the function). Param ids are not tracked by `_DELIBERATELY_SUPERSEDED_TESTS`.
- **Validate**: part of Task 7

### Task 7: Targeted test run (one pytest call; no full suite)

```bash
PYTHONUTF8=1 .venv/Scripts/python -m pytest \
  tests/test_messages.py tests/test_query_pipeline_tools.py \
  tests/test_query_pipeline_run_conversation.py tests/test_query_pipeline_multiturn.py \
  tests/test_query_pipeline_pii_profiles.py tests/test_query_pipeline_dedup_key.py \
  tests/test_conversation_key.py tests/test_pii_policy.py \
  tests/test_v1_translate_request.py \
  tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py \
  tests/test_pii_redaction_integration.py tests/test_untouched_app.py -q
```
Drop any listed file that does not exist (check `tests/test_conversation_key.py`, `tests/test_pii_policy.py` first). Full suite: deferred to orchestrator (user decision).

---

## End-to-End Tests

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` prints OK
- [ ] `/query` and chat regression suites green and unedited (D17)
- [ ] `tests/test_v1_translate_request.py` green and unedited (the edge still refuses tool turns with flag off; D10)
- [ ] No live E2E: tool turns cannot reach the pipeline from an ingress until STORY-008

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest <Task 7 list> -q
```

---

## Risks / open questions

- **R1 (deviation, needs orchestrator ack): a "contains a user turn" rule beyond PRD Section 6.3.** D6's three rules accept `[system?, assistant(tool_calls=[c1]), tool(c1)]`, a conversation with no user turn. Then step 1 crashes: `conversation_key` does `next(... if m.role == "user")` with no default (`app/services/conversation_key.py:44`) → `StopIteration`. STORY-006's dedup anchor is also "the last user turn" (PRD 6.4), with none to pick. Once STORY-008 lands, that would be an uncaught 500 from `/v1`. The plan puts the rule **in the shared helper**, so the edge refuses it as a 400 `invalid_messages` at `messages[len-1]` and step 0 guards it. Alternative: leave D6 exact and give `conversation_key` a `""` default plus a STORY-006 anchor rule. Rejected, because it changes two keys' semantics in other stories. Record in the report and the PRD's decisions if accepted.
- **R2: wording of the last-turn rule.** The helper says "user or tool turn". The `/v1` edge's flag-off string "the last message must be a user turn" (`v1_translate.py:238`, `tests/e2e/test_aider.py:443`) must stay byte-identical (D10). STORY-008 must keep the edge's own flag-off check and use the helper only under the flag, or keep the old text for flag-off. Flag this to STORY-008's planner.
- **R3: the step-6 rebuild drops `tool_call_id`.** Pipeline tests with a tool turn send `Message("tool", redacted)` upstream. The stubs ignore it, and STORY-007 fixes it. AC4's test asserts only row fields.
- **R4: the `prompt_preview` form.** Multi-line tool content may be normalized or truncated in the preview. Assert against what `log_query` stores (read `app/db/database.py`'s preview rule) or use single-line tool content.
- **R5: AC5's premise.** The story says existing step-0 tests "assert `tool turns are not supported (PRD-017)`". On this branch they assert only the exception type (`tests/test_query_pipeline_run_conversation.py:158`, `tests/test_query_pipeline_multiturn.py:857`), and their inputs still violate D6. So they are kept and commented, not replaced. No function is renamed, so there is no `_DELIBERATELY_SUPERSEDED_TESTS` entry. The only `"tool turns are not supported"` assertion is the `/v1` edge's (`tests/test_v1_translate_request.py:151`), which is STORY-008's.

---

## Acceptance Criteria

(Copied from story `STORY-005`)

- [ ] Given `[user, assistant(tool_calls=[c1, c2]), tool(c1), tool(c2)]`, when `_validate_conversation` runs, then it passes; a conversation ending in `user` passes as today. *(Task 4 `test_shape_accepts`; Task 5 `test_validate_accepts_a_tool_final_conversation`)*
- [ ] Given each D6 violation — last turn `assistant` or `system`; a `tool` turn first; a `tool` turn whose id is not among the nearest preceding assistant `tool_calls` turn's ids; a `tool` turn separated from that assistant turn by a `user` turn; one id answered twice — when validated, then `InvalidConversationError` names the rule (and the index), and no row is written. *(Task 4 `test_shape_refuses`; Task 5 `test_each_d6_violation_raises_naming_index_and_rule_and_writes_no_row`)*
- [ ] Given a conversation ending in a `tool` turn, when the pipeline writes any row, then `prompt` (and so `prompt_hash` / `prompt_preview`) is that tool turn's content; for a `user`-final conversation it is unchanged (D7). *(Task 5 forbidden/success/duplicate/flag arms + one-prompt-local source test; existing `test_audit_prompt_is_last_user_turn_on_*`)*
- [ ] Given a `tool`-final conversation with PII in the tool turn under `code`, when step 6 runs, then the row's `pii_detected_input` / `pii_entities` come from that final turn. *(Task 5 `test_tool_final_pii_counts_from_the_final_turn` + history contrast)*
- [ ] Existing step-0 tool tests replaced/commented with PRD-017 D6; superseded names registered. *(Task 6; R5: none superseded)*
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns (location + rule messages, pure `messages.py`)
