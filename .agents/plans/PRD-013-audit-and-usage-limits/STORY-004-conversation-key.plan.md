---
story: STORY-004
prd: PRD-013
slug: conversation-key
title: "conversation_key derivation"
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-013-audit-and-usage-limits        # all stories commit here, no per-story branch
created: 2026-10-14
---

# Plan: conversation_key derivation

## Summary

A new pure module, `app/services/conversation_key.py`, exposes `CONVERSATION_KEY_VERSION = "c1"` and `conversation_key(user_id, messages) -> str`. The key is `_sha256_json([CONVERSATION_KEY_VERSION, user_id, first_system, first_user])` over raw text, exactly as PRD Section 6.3 writes it. Nothing calls it yet: STORY-005 computes it in `run_conversation` and writes it on every audit arm.

- **Hashing.** `_sha256_json` is imported from `app.services.duplicate_checker` by name. It is not copied and not renamed (see Decision 1).
- **Missing `system`.** The first `system` turn defaults to `""`. The first `user` turn uses a bare `next(...)`, with a comment that `_validate_conversation` guarantees one.
- **Docstring.** It states the three documented limits from Section 6.3 (same-start conversations merge, identical `/query` prompts merge, a rewritten first message starts a new key), plus the chat-UI caveat that `session_id` is authoritative for chat rows.
- **Tests.** A new module, `tests/test_conversation_key.py`. No existing test or production file is edited.

### Decisions

1. **Import `_sha256_json` by name; do not make it public and do not move it.** The story allows either importing or making it public. Importing by name is the smaller change, and it matters for STORY-005. `tests/test_query_pipeline_multiturn.py:323-340` spies on `duplicate_checker._sha256_json` with `monkeypatch.setattr` and asserts `framed[0]` is `dedup_key`'s prefix payload. A name bound at import (`from app.services.duplicate_checker import _sha256_json`) is not affected by that monkeypatch, so the spy keeps seeing only `dedup_key`'s calls once STORY-005 computes `conversation_key` beside it. A call through the module attribute would add a call to the spy's list and could break `framed[0]`.
2. **"Imports no settings and no database module" is checked on the file's own imports.** `duplicate_checker` itself imports `app.db.database`, which imports `app.config.settings` (`app/services/duplicate_checker.py:7`, `app/db/database.py:14`). So importing `conversation_key` still loads both modules indirectly. AC 5 says "when it is read", so the test parses the file's `import` statements with `ast`. The module does no I/O and reads no setting. The indirect import is recorded for the report as F-1. Removing it would mean moving `_sha256_json` into a new dependency-free module, which the story does not list.
3. **Keyword names follow the PRD signature**: `conversation_key(user_id: str, messages: Sequence[Message])`. `Message` is imported from `app.models.messages`, which is pure (`app/models/messages.py:1-8`).

## User Story

As a compliance admin
I want a key derived from how a conversation starts
So that an external client's turns can be grouped without a harness session

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-004-conversation-key.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md` (Sections 6.3 D2, 7 F4, 9.2 T13 and invariants)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (story type `feature`) |
| Complexity | LOW (story `small`) |
| Systems Affected | New service module `app/services/conversation_key.py` and its test module |
| Story | STORY-004 |
| PRD | PRD-013 |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch; it is checked out, HEAD `398bfdc`) |
| Depends on | none |
| Blocks | STORY-005 |

---

## Skills In Use

None. `.agents/skills/` holds one skill, `frontend-design`. The story sets `skills: []` and says "No UI surface changes in this story".

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

---

## Patterns to Follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| HASHING | `app/services/duplicate_checker.py:51-53` | `_sha256_json`: JSON framing, `ensure_ascii=False`, compact separators, SHA-256 hex |
| VERSIONED KEY | `app/services/duplicate_checker.py:47,56-68` | Module-level `*_KEY_VERSION` string as the first element of the hashed list |
| PURE MODULE | `app/models/messages.py:1-8` | Module docstring says what it does not touch: no I/O, no settings |
| INPUT GUARANTEE | `app/services/query_pipeline.py:58-64` | `_validate_conversation`: non-empty, no `tool`, last turn `user` |
| TESTS | `tests/test_dedup_key.py:1-60` | Story docstring, env `setdefault`, local frozen `_Turn` + `_user/_assistant/_system` builders, independent `_framed_sha256` |

### Naming / versioned key
```python
# SOURCE: app/services/duplicate_checker.py:47-53
DEDUP_KEY_VERSION = "v1"
_KEYED_ROLES = frozenset({"system", "user", "assistant"})


def _sha256_json(value) -> str:
    framed = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(framed.encode("utf-8")).hexdigest()
```

### Error handling
The function raises nothing of its own. The one way it can fail is `StopIteration` from the bare `next(...)` when there is no `user` turn. That input cannot reach it: `_validate_conversation` runs first and raises `InvalidConversationError` (`app/services/query_pipeline.py:58-64`). The comment on the `next(...)` says so, as the story asks.

```python
# SOURCE: app/services/query_pipeline.py:58-64
def _validate_conversation(messages: Sequence[Message]) -> None:
    if not messages:
        raise InvalidConversationError("messages must not be empty")
    if any(m.role == "tool" for m in messages):
        raise InvalidConversationError("tool turns are not supported (PRD-016)")
    if messages[-1].role != "user":
        raise InvalidConversationError("the last message must be a user turn")
```

### Tests
```python
# SOURCE: tests/test_dedup_key.py:11-53
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
...
def _framed_sha256(value, ensure_ascii=False):
    """Section 6.2's framing, rebuilt here independently of the module."""
    framed = json.dumps(value, ensure_ascii=ensure_ascii, separators=(",", ":"))
    return hashlib.sha256(framed.encode("utf-8")).hexdigest()
```

The env `setdefault` lines are needed: importing the module loads `app.config` through `duplicate_checker` (Decision 2). The tests use `Message` from `app.models.messages` directly, not a local `_Turn`, because that is the type the PRD signature names.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/conversation_key.py` | CREATE | `CONVERSATION_KEY_VERSION` and `conversation_key(user_id, messages)` |
| `tests/test_conversation_key.py` | CREATE | The five ACs, plus the framing and version checks |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Baseline

- **Action**: none (measure only)
- **Implement**: Confirm the branch is `epic/PRD-013-audit-and-usage-limits` and the tree is clean. Run the suite once and record the figure.
- **Validate**: `python -m pytest -q`. A failure with `StorageError ... tcp connect error` in a test that passes alone is the known libSQL flakiness. On mass fixture errors, restart the `harness-libsql-dev` container before looking at code.

### Task 2: Create `app/services/conversation_key.py`

- **File**: `app/services/conversation_key.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring:
    - What the key is: a versioned SHA-256 over the user id, the first `system` message (`""` when there is none) and the first `user` message, framed as JSON (PRD-013 Section 6.3, D2).
    - Raw text only. No redacted string is ever passed in (Section 9.2 invariants; the PRD-003 rule extended in PRD-010).
    - Pure: no I/O, no settings, no database. It reaches `app.db` only through `duplicate_checker`'s own imports, to reuse `_sha256_json` rather than copy it.
    - **A grouping aid, not an identity**, with the three documented limits: (1) two conversations by one user that start with the same `system` and first `user` message share a key; (2) every identical `/query` prompt by one user shares a key; (3) a client that compacts its context and rewrites its first user message starts a new key.
    - The chat UI's key can change mid-session once `chat_history.fit` drops the first exchange, so `session_id` is the authoritative grouping for chat rows.
    - Unlike `dedup_key`, it is exposed on `/audit` and in the console (T13: a hash of data the same reader already sees).
  - Imports: `from typing import Sequence`, `from app.models.messages import Message`, `from app.services.duplicate_checker import _sha256_json`. Nothing else. Add a one-line comment on the last import pointing at Decision 1: it is bound by name so the `_sha256_json` spy in `tests/test_query_pipeline_multiturn.py` sees only `dedup_key`.
  - `CONVERSATION_KEY_VERSION = "c1"`.
  - The function, as in Section 6.3:
    ```python
    def conversation_key(user_id: str, messages: Sequence[Message]) -> str:
        first_system = next((m.content for m in messages if m.role == "system"), "")
        # No default: _validate_conversation (query_pipeline) runs first and
        # guarantees the last message is a user turn, so one always exists.
        first_user = next(m.content for m in messages if m.role == "user")
        return _sha256_json([CONVERSATION_KEY_VERSION, user_id, first_system, first_user])
    ```
- **Mirror**: `app/services/duplicate_checker.py:47-68`
- **Validate**: `python -c "from app.services.conversation_key import conversation_key, CONVERSATION_KEY_VERSION; from app.models.messages import Message; print(CONVERSATION_KEY_VERSION, conversation_key('u', [Message('user', 'a')]))"` prints `c1` and a 64-character hex string. Set `OPENROUTER_API_KEY` and `ADMIN_TOKEN` in the environment first if `.env` does not provide them.

### Task 3: Create `tests/test_conversation_key.py`

- **File**: `tests/test_conversation_key.py`
- **Action**: CREATE
- **Implement**: A module docstring naming PRD-013 STORY-004 and Section 6.3, saying nothing calls the function until STORY-005. Env `setdefault` lines as in `test_dedup_key.py`. Builders `_user`, `_assistant`, `_system` returning `Message`. An independent `_framed_sha256`. Constants `_JUAN = "juan@empresa.com"` and `_MARIA = "maria@empresa.com"`. Tests:
  1. `test_exports_version_c1_and_the_specified_signature`: `CONVERSATION_KEY_VERSION == "c1"`; parameters are `["user_id", "messages"]`.
  2. `test_key_is_the_framed_hash_of_version_user_system_and_first_user` (AC 5, "includes the version"): equals `_framed_sha256(["c1", _JUAN, "sys", "a"])` for `[system("sys"), user("a")]`. Also monkeypatch `conversation_key_module.CONVERSATION_KEY_VERSION` to `"c2"` and assert the key changes.
  3. `test_stable_across_fifty_growing_turns` (AC 1): start from `[system("S"), user("u0")]`; for `i` in `1..49` append `assistant(f"a{i}")`, `user(f"u{i}")`; compute the key after each user turn is added; assert 50 values and `len(set(keys)) == 1`.
  4. `test_differs_by_user` (AC 2): same messages, `_JUAN` vs `_MARIA`, keys differ.
  5. `test_differs_by_first_user_message` and `test_differs_by_first_system_message` (AC 3): one varied field each, everything else equal.
  6. `test_no_system_turn` (AC 4): `[user("a")]` gives a key without raising, and it equals the key of `[user("a"), assistant("b"), user("c")]`. Also assert it equals `_framed_sha256(["c1", _JUAN, "", "a"])`, which pins the `""` default.
  7. `test_only_the_first_system_and_first_user_count`: a later `system` turn and later `user` turns do not change the key. This states the "first" in the AC precisely.
  8. `test_field_boundaries_cannot_be_forged`: `(system="ab", user="c")` and `(system="a", user="bc")` give different keys; so do user ids that differ only by moving characters into the system text. This is the reason the story asks for JSON framing.
  9. `test_non_ascii_is_hashed_as_utf8`: `user("¿qué?")` equals `_framed_sha256` with `ensure_ascii=False` and differs from the `ensure_ascii=True` framing.
  10. `test_imports_no_settings_and_no_database_module` (AC 5): parse `app/services/conversation_key.py` with `ast`, collect every `Import`/`ImportFrom` module name, assert none is `app.config` or starts with `app.db`, and that `_sha256_json` is imported from `app.services.duplicate_checker` (reused, not copied). Also assert the source contains no `def _sha256_json` and no `json.dumps`.
  11. `test_docstring_states_the_three_documented_limits`: the module docstring mentions each limit. Match on short, stable phrases (`"same"`, `"/query"`, `"rewrit"`), case-insensitive, so the docstring can be reworded without breaking the test.
- **Mirror**: `tests/test_dedup_key.py:1-60`
- **Validate**: `python -m pytest tests/test_conversation_key.py -q`, all pass.

### Task 4: Full suite

- **Action**: none (verify)
- **Validate**: `python -m pytest -q` passes with the Task 1 figure plus the new tests. No existing test was edited.

---

## End-to-End Tests

No route or UI calls the function in this story, so there is no HTTP or browser check. The end-to-end proof is STORY-005's 50-turn `run_conversation(ingress="v1")` test.

- [ ] `python -m pytest tests/test_conversation_key.py -q` passes
- [ ] `python -m pytest tests/test_dedup_key.py tests/test_query_pipeline_multiturn.py -q` still passes (the helper this story reuses, and the spy Decision 1 protects)
- [ ] Full suite passes

---

## Validation

```bash
python -m pytest tests/test_conversation_key.py -q
python -m pytest -q
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| Indirect import of `app.db` / `app.config` through `duplicate_checker` (F-1) | AC 5 is checked on the file's own imports; recorded for the report. If a later story needs the module importable without settings, move `_sha256_json` to a dependency-free module then |
| STORY-005's `_sha256_json` spy counts `conversation_key`'s call and `framed[0]` shifts | Import bound by name (Decision 1), with a comment saying why |
| `StopIteration` if called with no user turn | Unreachable after `_validate_conversation`; comment on the `next(...)`. STORY-005 must compute the key after validation |
| libSQL dev-server flakiness in the full suite | New tests touch no database. Restart the container on mass fixture errors |

---

## Acceptance Criteria

(Copied from story `STORY-004`)

- [ ] Given a conversation that grows from 1 to 50 user turns with the same `system` and first `user` message, when `conversation_key(user_id, messages)` is computed at each step, then all 50 values are equal.
- [ ] Given the same messages and two different `user_id` values, when the key is computed, then the two values differ.
- [ ] Given two conversations whose first `user` messages differ, or whose first `system` messages differ, when the key is computed, then the values differ.
- [ ] Given a conversation with no `system` turn, when the key is computed, then it succeeds, and `[user("a")]` and `[user("a"), assistant("b"), user("c")]` give the same key.
- [ ] Given `app/services/conversation_key.py`, when it is read, then it imports no settings and no database module, defines `CONVERSATION_KEY_VERSION = "c1"`, and includes the version in the hashed value.
- [ ] All tasks completed
- [ ] Full test suite passes
- [ ] Follows existing patterns
