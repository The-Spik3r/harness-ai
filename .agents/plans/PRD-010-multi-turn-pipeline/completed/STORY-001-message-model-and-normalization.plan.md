---
story: STORY-001
prd: PRD-010
slug: message-model-and-normalization
title: "Message model, Role type and OpenAI content normalization"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-010-multi-turn-pipeline        # all stories commit here, no per-story branch
created: 2026-09-17
---

# Plan: Message model, Role type and OpenAI content normalization

## Summary

Add a new pure module, `app/models/messages.py`. It holds the internal conversation currency for the PRD-010 track:
- `Role`, a `Literal` alias
- `Message(role, content: str)`, a frozen dataclass
- `MessageNormalizationError`
- `normalize_message` and `normalize_messages`, which turn OpenAI message shapes (string content, a list of text parts, or `null`) into `Message`s, or refuse them with an error that names the location and the rule and never echoes content

The module uses only `dataclasses` and `typing`: no I/O, no `settings`, no pydantic, no `app.*` import. Its only importer in this story is the new `tests/test_messages.py`. That file pins every row of PRD Section 6.2's table, the index-naming error contract, and structural compatibility with PRD-009's `dedup_key`. No production file changes.

## User Story

As a PRD-011/012/014 implementer
I want to have one internal `Message(role, content: str)` and one normalizer for OpenAI message shapes
So that nothing past the edge ever handles a content-part list or a `None`

## Story Reference

- Story file: `.agents/stories/PRD-010-multi-turn-pipeline/STORY-001-message-model-and-normalization.md`
- PRD: `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md` (Sections 4, 6.2, 7 F1, 10, 11)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/models` (new module), `tests` (new file) |
| Story | STORY-001 |
| PRD | PRD-010 |
| Epic Branch | `epic/PRD-010-multi-turn-pipeline` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | The only skill in `.agents/skills/` is `frontend-design`, which covers UI and copy. This story is a backend module with no UI surface, and the story's `skills: []` field and Technical Notes agree ("Skills: none applicable"). | — |

---

## Patterns to Follow

### Frozen dataclass that satisfies `DedupTurn` structurally
```python
# SOURCE: app/services/query_pipeline.py:32-37  (STORY-007 deletes this in favour of Message)
@dataclass(frozen=True)
class _UserTurn:
    """The one turn `/query` has: satisfies `DedupTurn` structurally (PRD-009 Section 6.2)."""

    content: str
    role: str = field(default="user", init=False)
```
```python
# SOURCE: app/services/duplicate_checker.py:43-52
class DedupTurn(Protocol):
    role: str
    content: str

DEDUP_KEY_VERSION = "v1"
_KEYED_ROLES = frozenset({"system", "user", "assistant"})
```

### Naming and typing
```python
# SOURCE: app/models/schemas.py:1-4 / app/services/duplicate_checker.py:5
from typing import List, Literal, Optional, Union
from typing import Optional, Protocol, Sequence
```
- `typing` generics (`Optional`, `Sequence`, `Mapping`), never `X | None`. No `from __future__ import annotations` (only `reports.py` uses it).
- Private module constants are `_UPPER` frozensets (`_KEYED_ROLES`).
- `Literal` is used inline in `schemas.py`, so this story adds the codebase's first module-level `Literal` alias. `get_args(Role)` derives the valid-role set, which keeps a single source of truth.

### Error handling
```python
# SOURCE: app/db/errors.py:17 / app/services/reports.py:80  (newer style: docstring, no bare pass)
class ReportsReadError(Exception):
    """The record exists but could not be read (permissions, not a directory)."""
```
```python
# SOURCE: app/services/duplicate_checker.py:57-63  (message names the rule, never the offending value)
raise ValueError("dedup_key needs at least one turn")
raise ValueError("dedup_key has no rule for this role (tool turns: PRD-016)")
raise ValueError("dedup_key keys on a final user turn")
```

### Tests
```python
# SOURCE: tests/test_dedup_key.py:1-13, 31-35  (header, env guard, local _Turn)
"""PRD-009 STORY-003: `dedup_key(user_id, turns)`, the one definition of "duplicate". ..."""
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
...
@dataclass(frozen=True)
class _Turn:
    role: str
    content: str
```
```python
# SOURCE: tests/test_dedup_key.py:193-203  (parametrize with ids + raises(match=))
@pytest.mark.parametrize(
    "turns",
    [[_Turn("tool", "ls output"), _user("x")], [_user("x"), _Turn("tool", "ls output")]],
    ids=["tool-in-prefix", "tool-as-final-turn"],
)
def test_tool_turn_anywhere_is_refused_naming_prd_016(turns):
    with pytest.raises(ValueError, match="PRD-016"):
        dedup_key(_JUAN, turns)
```
```python
# SOURCE: tests/test_dedup_key.py:217-228  (purity test via monkeypatch + inspect.getsource)
source = inspect.getsource(dedup_key)
assert "settings" not in source
```
```python
# SOURCE: tests/test_chat_sessions.py:1170-1186  (ast-based boundary scan with an offenders list)
assert offenders == [], ...
```

### Comment density
- `duplicate_checker.py` has sparse, *why*-only `#` comments that cite the PRD section.
- `query_pipeline.py` has short class docstrings that cite the PRD.
- Follow that: a module docstring naming PRD-010 6.2 and the consumers, one-line docstrings on the public names, and a `#` comment on the `\n` join with the reason the story requires.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/messages.py` | CREATE | `Role`, `Message`, `MessageNormalizationError`, `normalize_message`, `normalize_messages` |
| `tests/test_messages.py` | CREATE | Table rows from 6.2, edge cases, index-naming and no-echo errors, `dedup_key` structural equivalence, purity and import-direction checks |

No UPDATE. `app/models/__init__.py` stays empty (the codebase imports `app.models.schemas` directly, never re-exports).

---

## Design Decisions (fixed by this plan)

1. **Field order `role, content`.** `Message("user", prompt)` is the positional form used throughout PRD 6.1, 7 F5 and F8. It is the opposite of `_UserTurn`'s order, which never mattered because `_UserTurn` has only one init field.
2. **`Message` does not validate in `__post_init__`.** `run_query` (STORY-007) constructs `Message("user", prompt)` directly, and `/query` accepts any string prompt today, including `""`. Validation lives only in the normalizer, the edge.
3. **Check order inside `normalize_message`:**
   1. `raw` is a `Mapping`, otherwise "message is not an object"
   2. `role` is a str in `get_args(Role)`, otherwise "unknown role (expected one of: system, user, assistant, tool)". A missing `role` or a non-str `role` falls into the same rule.
   3. The `tool_calls` key is present (any value, including `None` or `[]`), otherwise "tool_calls are not supported (PRD-016)". This is checked **before** content, because OpenAI's tool-call assistant turn is `content: null` + `tool_calls`. Checking content first would accept it as `""`.
   4. Content, read as `raw.get("content")` (a missing key is treated as `null`):
      - `str`: returned unchanged (no strip, no trimming; whitespace is significant to `dedup_key`)
      - `None`: `""` for `assistant`; for any other role, "null content is only allowed on assistant messages"
      - `list`: every element must be a `Mapping` with `type == "text"` and a `str` `text`, otherwise "content[i] is not a text part" or "content[i] text part has no string text". The texts are joined with `"\n"`.
      - Anything else (int, dict, bytes): "content must be a string, a list of text parts, or null"
4. **No values are echoed in any error message**: no content, no role value, no part type. Errors name only a location (`messages[3]`, `content[1]`) and a rule. This matches `dedup_key`'s "no rule for this role" style and stops untrusted strings of any length reaching logs or 400 bodies in PRD-014.
5. **`normalize_messages`**:
   - It refuses `str`/`bytes` and non-`Sequence` input ("messages must be a list").
   - It wraps each element error as `MessageNormalizationError(f"messages[{i}]: {exc}") from exc`. The chained cause carries no content either.
   - An empty sequence returns `[]`. Cross-message structure (non-empty, last is user) belongs to STORY-007, per the Technical Notes.
6. **`MessageNormalizationError(Exception)`** with a docstring, not `ValueError`. Every sibling service error subclasses `Exception` directly, and PRD-014 maps it explicitly to a 400. Subclassing `ValueError` would let it be swallowed by `dedup_key`-style `ValueError` handling by accident.
7. **Empty text** (`""` content, or `[]` parts, on a `user` turn) **normalizes to `""` and is not refused.** The 6.2 table only refuses `null`, and `/query` accepts an empty prompt today. The `content: str  # "" is legal only for assistant` comment in PRD 6.2 is ambiguous about whether it is a normalizer rule; see Risk 2.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 0: Branch precondition (no code)

- **Action**: VERIFY
- **Implement**: `epic/PRD-010-multi-turn-pipeline` does not exist yet. PRD-010 depends on PRD-009, whose epic (`epic/PRD-009-duplicate-rescoping` @ `7156251`) is **not merged into `main`**, and the PRD's evidence was verified against that commit. `/implement` must confirm with the user whether to cut the PRD-010 epic from `epic/PRD-009-duplicate-rescoping` HEAD or from `main` after the PRD-009 merge. It must not branch from today's `main`, which lacks `dedup_key`. The uncommitted PRD-010 docs (`.agents/PRDs/…`, `.agents/stories/…`, `pre-prds/PRE-PRD-010…`) carry over on checkout.
- **Validate**: `git branch --show-current` → `epic/PRD-010-multi-turn-pipeline`, and `python -c "from app.services.duplicate_checker import dedup_key"` succeeds.

### Task 1: Create the message model

- **File**: `app/models/messages.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring: PRD-010 Section 6.2. This is the one internal message shape. Nothing past `normalize_*` sees a part list or `None`. It is pure on purpose, and its consumers are STORY-004/007/011 and PRD-011–014.
  - Imports: `from dataclasses import dataclass` and `from typing import Any, Literal, Mapping, Sequence, get_args`. Nothing else.
  - `Role = Literal["system", "user", "assistant", "tool"]`. Add a comment that `tool` is valid on purpose (PRD-016 must not have to widen the type), and that the pipeline refuses it structurally in STORY-007.
  - `_ROLES = frozenset(get_args(Role))`
  - `@dataclass(frozen=True) class Message:` with the docstring "satisfies PRD-009's `DedupTurn` structurally; no import in either direction", then `role: Role` and `content: str`.
  - `class MessageNormalizationError(Exception):` with a docstring. It must name that messages identify a location and rule, never content.
  - `def normalize_message(raw: Mapping[str, Any]) -> Message:`, following Design Decision 3. Use a private `_normalize_content(role, content) -> str` helper to keep the branches flat. Put a `#` comment on `"\n".join(...)`: "Parts are joined with a newline, not '': it keeps part boundaries visible to pattern detection, so a part ending `ignore` and one starting `previous` cannot fuse into one token (PRD-010 6.2)".
  - `def normalize_messages(raw: Sequence[Mapping[str, Any]]) -> list[Message]:`, following Design Decision 5.
- **Mirror**: `app/services/duplicate_checker.py:43-63` (Protocol-shaped fields, rule-only error strings), `app/services/identity.py:19-29` (frozen dataclass with a *why* docstring), `app/services/reports.py:80` (exception with docstring)
- **Validate**: `.venv\Scripts\python -c "from app.models.messages import Role, Message, MessageNormalizationError, normalize_message, normalize_messages; print(normalize_message({'role':'user','content':[{'type':'text','text':'a'},{'type':'text','text':'b'}]}))"` → `Message(role='user', content='a\nb')`

### Task 2: Test the module surface and the 6.2 table

- **File**: `tests/test_messages.py`
- **Action**: CREATE
- **Implement**:
  - Header: a module docstring ("PRD-010 STORY-001: …; the normalizer has no production caller in this PRD, so these tests are the whole contract until PRD-014"), then the `os.environ.setdefault` guard, then the imports. The file follows `tests/test_dedup_key.py:1-25`.
  - `test_exports_the_specified_names_and_signatures`:
    - `get_args(Role) == ("system", "user", "assistant", "tool")`
    - `inspect.signature` parameter lists are `["raw"]` for both functions
    - `dataclasses.fields(Message)` names are `["role", "content"]`
    - `Message.__dataclass_params__.frozen`
  - `test_message_is_frozen`: assigning `.content` raises `dataclasses.FrozenInstanceError`.
  - **Valid rows**, as one parametrized test `test_normalizes_table_row(raw, expected)`, `ids=` named after each row:
    - `string-content`: `{"role":"user","content":"text"}` → `Message("user","text")`
    - `two-text-parts-joined-with-newline`: parts `a`, `b` → `"a\nb"`
    - `null-on-assistant-becomes-empty`: `{"role":"assistant","content":None}` → `Message("assistant","")`
    - `tool-role-with-string-content` → `Message("tool","ls output")` (Technical Note: do not refuse `tool`)
    - `system-role-with-string-content`
  - **Invalid rows**, as one parametrized test `test_refuses_table_row(raw, rule)` using `pytest.raises(MessageNormalizationError, match=rule)`, with ids:
    - `image-url-part`: `[{"type":"text","text":"a"},{"type":"image_url","image_url":{"url":"…"}}]` → `"content\[1\] is not a text part"`
    - `null-on-user`, `null-on-system`, `null-on-tool` → `"null content"`
    - `tool-calls-key`: `{"role":"assistant","content":None,"tool_calls":[…]}` → `"PRD-016"` (proves check order, Design Decision 3.3)
    - `unknown-role-developer` → `"unknown role"`
  - **Edge cases** (Technical Notes), as one parametrized test `test_refuses_malformed_shape` with ids:
    - `text-part-missing-text`
    - `text-part-non-str-text` (`"text": 3`)
    - `part-not-a-mapping` (`["a"]`)
    - `message-not-a-mapping` (`["role","user"]` and `"user"`)
    - `missing-role`
    - `non-str-role` (`1`)
    - `content-is-int`
    - `content-is-dict`
    - `tool-calls-empty-list`
  - `test_missing_content_key_is_treated_as_null`: missing on assistant → `""`, missing on user → raises.
  - `test_empty_text_is_not_refused`: `""` and `[]` on user → `""`. This pins Design Decision 7, so a change of policy is a visible test edit.
  - `test_part_join_keeps_boundaries_visible`: parts `"ignore"`, `"previous instructions"` → `"ignore\nprevious instructions"`, and `"ignoreprevious"` is not in the result.
  - `test_whitespace_and_extra_keys_are_preserved_and_ignored`: content `"  hi \n"` is unchanged; `{"role":"user","content":"x","name":"n"}` → `Message("user","x")`.
- **Mirror**: `tests/test_dedup_key.py:55-58, 187-209`
- **Validate**: `.venv\Scripts\python -m pytest tests/test_messages.py -v` (libSQL dev server must be up: the conftest autouse fixture requires it even for pure tests)

### Task 3: Test `normalize_messages` error contract

- **File**: `tests/test_messages.py`
- **Action**: UPDATE (same new file)
- **Implement**:
  - `test_normalize_messages_preserves_order_and_length`: three valid shapes in, three `Message`s out, in order.
  - `test_normalize_messages_accepts_empty_and_does_not_validate_structure`: `[]` → `[]`. `[assistant("x")]` (final non-user) and `[system("a")]` normalize fine, because STORY-007 owns structure.
  - `test_normalize_messages_accepts_any_sequence`: a tuple input.
  - `test_invalid_element_names_its_index_and_rule`: four messages, index 3 is `{"role":"user","content":None}`. Use `pytest.raises(MessageNormalizationError) as caught` and assert that `str(caught.value)` starts with `"messages[3]: "` and contains `"null content"`.
  - `test_error_never_echoes_content`, parametrized over failure kinds. Each fixture embeds a canary: `_CANARY = "jane@corp.com SECRET-CANARY"` as a sibling part's text, as the text of an `image_url`-adjacent part, as a `developer` message's content, and as the content of a `tool_calls` message. Also use `"developer-CANARY"` as the role value and `"CANARY_type"` as a part type. Assert that `"CANARY"` is not in `str(exc)` or in `repr(exc.__cause__)`, for both `normalize_message` and `normalize_messages`.
  - `test_normalize_messages_refuses_a_string_or_non_sequence`: `"hello"`, `b"hi"`, `None`, `{"role":"user"}` → raises `"messages must be a list"`.
- **Mirror**: `tests/test_schemas.py:271` (`pytest.raises(...) as caught`)
- **Validate**: `.venv\Scripts\python -m pytest tests/test_messages.py -v`

### Task 4: Test structural compatibility with `dedup_key` and purity

- **File**: `tests/test_messages.py`
- **Action**: UPDATE (same new file)
- **Implement**:
  - `test_message_list_keys_like_the_pipeline_user_turn_today`, which covers AC 4.
    - Assert `dedup_key(_JUAN, [Message("user", p)]) == dedup_key(_JUAN, [query_pipeline._UserTurn(p)])` for a few prompts: ASCII, non-ASCII with emoji, and `""`.
    - Add a comment: `# STORY-007 deletes _UserTurn: replace this reference with the pinned digest from test_dedup_key.py:74, never delete the assertion.`
    - Also assert the pinned constant: `dedup_key(_JUAN, [Message("user", "summarise this week's incidents")]) == "0b206c74…4652"` (copied from `tests/test_dedup_key.py:74`). The test then survives STORY-007 unchanged apart from dropping the `_UserTurn` line.
  - `test_multi_turn_message_list_matches_structural_turns`: `Message` user/assistant/user equals the local `_Turn` equivalent, plus the pinned multi-turn digest `c63baa97…4705` (from `tests/test_dedup_key.py:83`).
  - `test_normalized_output_feeds_dedup_key`: `dedup_key(_JUAN, normalize_messages([...]))` runs, and equals the key of the directly constructed list.
  - `test_no_import_in_either_direction`, which covers AC 4 and uses `ast`.
    - Parse `app/models/messages.py` and collect every `Import`/`ImportFrom` module. Assert the set ⊆ `{"dataclasses", "typing"}`. That covers no `app.*`, no `pydantic` and no `settings`.
    - Parse `app/services/duplicate_checker.py` and assert that no import names `app.models.messages`.
  - `test_is_pure`: `inspect.getsource(messages_module)` contains none of `"settings"`, `"pydantic"`, `"open("`, `"httpx"`. Mirror `tests/test_dedup_key.py:217-228`.
- **Mirror**: `tests/test_dedup_key.py:163-167, 217-228`; `tests/test_chat_sessions.py:1170-1186` (ast walk)
- **Validate**: `.venv\Scripts\python -m pytest tests/test_messages.py -v`

### Task 5: Prove no production caller changed

- **Action**: VERIFY
- **Implement**:
  - `git diff --stat` for this story must list only `app/models/messages.py` and `tests/test_messages.py` (plus the story/index/plan docs).
  - A grep for importers must return only the test file.
  - Do **not** add a permanent "imported only by tests" test: STORY-004 legitimately imports `Message` into the client, and such a test would have to be deleted two stories later.
- **Validate**:
  - `git grep -n "models.messages\|models import messages" -- app chat_ui tests` → only `tests/test_messages.py`
  - `.venv\Scripts\python -m pytest -q` → full suite green

---

## End-to-End Tests

This story has no HTTP or UI surface. Its end-to-end check is the module contract exercised from a clean interpreter.

- [ ] `.venv\Scripts\python -c "from app.models.messages import normalize_messages; from app.services.duplicate_checker import dedup_key; print(dedup_key('juan@empresa.com', normalize_messages([{'role':'user','content':[{'type':'text','text':'hi'}]}])))"` prints a 64-hex key
- [ ] The same interpreter: `normalize_messages([{'role':'user','content':'a'},{'role':'user','content':None}])` raises `MessageNormalizationError: messages[1]: null content is only allowed on assistant messages`
- [ ] `python -m pytest tests/test_messages.py -v` is green, with every 6.2 row visible as a named parametrize id
- [ ] The full suite is green. If fixture errors appear en masse, restart the libSQL dev container before bisecting (known dev-server degradation)
- [ ] `git grep` shows no production importer of `app.models.messages`

---

## Validation

```powershell
# libSQL dev server must be running (tests/conftest.py autouse fixture)
docker ps --filter name=harness-libsql-dev
.venv\Scripts\python -m pytest tests/test_messages.py -v
.venv\Scripts\python -m pytest tests/test_dedup_key.py tests/test_query_pipeline_dedup_key.py -q
.venv\Scripts\python -m pytest -q
git grep -n "models.messages" -- app chat_ui
```

There is no linter or type checker configured in the repo (no ruff, mypy, pyproject or pytest.ini), so none runs. CI runs `pytest -q`.

---

## Risks & Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| 1 | The AC 4 test references `query_pipeline._UserTurn`, which STORY-007 deletes. | The same test also asserts the pinned digests from `test_dedup_key.py`, and a comment tells STORY-007 to drop only the `_UserTurn` line. |
| 2 | Ambiguity: PRD 6.2's field comment says `""` is "legal only for assistant", but the table refuses only `null`. | This plan follows the table and the ACs (Design Decision 7), pinned by `test_empty_text_is_not_refused`. If the user wants the stricter rule, it is a normalizer-only change plus one test flip. `Message` itself must stay unvalidated because `/query` accepts `""`. |
| 3 | An OpenAI tool-call assistant turn (`content: null` + `tool_calls`) silently normalizes to `""` if content is checked first. | Check order is fixed in Design Decision 3, and the `tool-calls-key` row uses exactly that shape. |
| 4 | Error messages leak prompt text into logs or future 400 bodies. | Rule-and-location-only messages; the canary test covers `str(exc)` and the chained cause. |
| 5 | The conftest autouse fixture needs libSQL even for these pure tests, so a stopped container looks like a failure in this story. | Validation lists the container check first. Per the project note, mass fixture errors mean restarting the container. |
| 6 | The epic branch is missing, and `main` lacks PRD-009. | Task 0 blocks implementation until the branch base is confirmed with the user. |

---

## Acceptance Criteria

(Copied from story `STORY-001`)

- [ ] Given the new `app/models/messages.py`, when it is imported, then it exports `Role = Literal["system", "user", "assistant", "tool"]`, a `@dataclass(frozen=True) Message(role: Role, content: str)`, `MessageNormalizationError`, `normalize_message(raw: Mapping[str, Any]) -> Message` and `normalize_messages(raw: Sequence[Mapping[str, Any]]) -> list[Message]`.
- [ ] Given each row of PRD Section 6.2's table, when it is passed to `normalize_message`, then the result matches the table. `"text"` → `"text"`. Two text parts `a`, `b` → `"a\nb"`. An `image_url` part raises. `null` on `assistant` → `""`. `null` on `user`/`system`/`tool` raises. A `tool_calls` key raises. An unknown role such as `"developer"` raises. There is one parametrized test per row in `tests/test_messages.py`.
- [ ] Given `normalize_messages` with an invalid element at index 3, when it raises `MessageNormalizationError`, then the message names the index (`messages[3]`) and the rule that failed, and never echoes the content.
- [ ] Given a `list[Message]` ending in a user turn, when it is passed to `dedup_key(user_id, messages)` from `app/services/duplicate_checker.py`, then it returns the same key as the equivalent private `_UserTurn` list does today. This proves `Message` structurally satisfies `DedupTurn` with no import in either direction.
- [ ] Given the full test suite, when this story lands, then it is green with **no production caller changed**. `messages.py` is imported only by its tests.
- [ ] All tasks completed
- [ ] Full pytest suite passes (no frontend lint or server start applies: no UI, no route change)
- [ ] Follows existing patterns (typing generics, rule-only error strings, PRD-citing docstrings, parametrize ids)
