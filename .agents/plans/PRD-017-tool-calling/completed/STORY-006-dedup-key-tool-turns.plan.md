---
story: STORY-006
prd: PRD-017
slug: dedup-key-tool-turns
title: "dedup_key over tool turns: never the anchor, in the prefix, tool-free keys unchanged"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-017-tool-calling
created: 2026-11-15
---

# Plan: dedup_key over tool turns: never the anchor, in the prefix, tool-free keys unchanged

## Summary

`dedup_key` (`app/services/duplicate_checker.py:56-68`) learns tool turns (PRD-017 D4,
Section 6.4). It keeps two framings in one function:

- **Tool-free** (no `tool` turn, no assistant `tool_calls`): today's code path, unchanged.
  It still requires a final `user` turn, so the key is
  `sha256_json(["v1", user_id, hash_prompt(last.content), "" | sha256_json([[role, content], ...])])`
  and every key an existing row holds still matches. No 24-hour window resets.
- **Tool-shaped** (any `tool` turn or any non-empty `tool_calls`): the anchor is the **last
  `user` turn**. The prefix is **every** turn in order. The anchor's slot holds a JSON `null`
  marker, and every other turn holds its frame: `[role, content]`, or
  `[role, content, [[id, name, arguments], ...]]` for an assistant with calls, or
  `[role, content, tool_call_id]` for a tool turn. The key is
  `sha256_json(["v1", user_id, hash_prompt(anchor.content), sha256_json(prefix)])`.
  This is the PRD 6.4 formula word for word, with the same four outer fields.

`DEDUP_KEY_VERSION` stays `"v1"`. The tool-free keys are pinned as literals, computed from
today's code before any change (below). `tests/test_query_pipeline_tools.py` drops its
`_keyed` stub and uses the real key. Its duplicate-arm test stays meaningful, because the
real key is deterministic, so a byte-identical resend gets the same key.

### Framing decision (why `null` in the prefix, not a 5-element key or a tag string)

- **Unforgeable from tool-free framing.** A tool-free prefix payload is always a JSON list
  whose elements are all 2-element lists of strings, or it is `""` when there is no prefix.
  A tool-shaped prefix payload always contains exactly one `null` element. Turn content is a
  `str`, so it can only appear inside a string; JSON escaping means no content can produce a
  bare `null` element. The two payloads are therefore always different JSON texts, and a
  collision would need a SHA-256 collision. The outer list is the same 4-field shape in both
  cases. A tool-shaped `prefix_hash` is never `""`, because a tool field means at least one
  non-anchor turn.
- **Marks the anchor's position** (PRD 6.4, AC3). `[u1, A, T, u2]` gives
  `[f(u1), f(A), f(T), null]` and `[u1, u2, A, T]` gives `[f(u1), null, f(A), f(T)]`.
- **Injective among tool frames.** The role is the first element. A calls frame has a
  *list* third element, and a tool frame has a *string* third element (or `null` when the
  field is absent, which step 0 makes impossible). An assistant whose `tool_calls == ()`
  frames as `[role, content]`, exactly as today.
- **Why not a 5-element outer key.** That would also be unforgeable, but it departs from the
  PRD 6.4 formula, which keeps four fields and puts the marking inside `prefix`. The `null`
  slot already marks the position, so a separate index is redundant.
- **Why not a tag string such as `"tools"` as the first prefix element.** A tag would still
  need a separate anchor index. The `null` slot does both jobs in one element.
- **`arguments` is framed as the raw string** (D13). It is never `json.loads`-ed. `"{}"` and
  `"{ }"` therefore key differently, which is the byte-for-byte semantics PRD-009 wants.

### Domain (refusals), matched to step 0's D6 rules

`dedup_key` stays a pure function that raises `ValueError` for programming errors. Its
domain becomes exactly what `conversation_shape_violation` admits (`app/models/messages.py:61-104`):

- `[]` → `"dedup_key needs at least one turn"` (unchanged).
- Unknown role → `"dedup_key has no rule for this role"`. The `"(tool turns: PRD-017)"` tail
  is dropped, and `_KEYED_ROLES` gains `"tool"`.
- Final turn not `user` or `tool` → `"dedup_key keys on a final user turn or a final tool turn"`.
  This still matches the existing `match="final user turn"` test, which needs no edit.
- No `user` turn at all (only possible when tool-shaped, e.g. `[A(calls), T]`) →
  `"dedup_key needs a user turn to anchor on (PRD-017 D4)"`. Step 0's rule 4 makes this
  unreachable from the pipeline.

Tool fields are read with `getattr(turn, "tool_calls", ())` and `getattr(turn, "tool_call_id", None)`.
`DedupTurn` stays the `role`/`content` Protocol, and `app.models.messages` is **not** imported.
There would be no cycle, because `messages.py` imports nothing from `app`
(`app/models/messages.py:1-13`). The reason is that the structural contract
(`test_any_object_with_role_and_content_works`, a `SimpleNamespace` with role/content only)
must keep working, and `Message`'s docstring promises "no import in either direction"
(`app/models/messages.py:38-41`).

## User Story

As an integrating developer
I want the duplicate key to tell apart each step of an agent's tool loop
So that running `npm test` twice in one session is not refused, while a byte-identical resend still is

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-006-dedup-key-tool-turns.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md` (Sections 5 story 4, 6.4, 11, 15 D4)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/services/duplicate_checker.py` (step 1 key); tests |
| Story | STORY-006 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| none | `.agents/skills/` holds only `frontend-design` (UI aesthetics). This story has no UI. Story frontmatter `skills: []`. | - |

---

## Patterns to Follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| KEY FRAMING | `app/services/duplicate_checker.py:51-53` | `_sha256_json`: `json.dumps(ensure_ascii=False, separators=(",", ":"))` → sha256 hex. Reuse it and never copy it. `conversation_key.py:33-35` imports it by name. |
| ERRORS | `app/services/duplicate_checker.py:57-63` | A pure function raises `ValueError` whose message names the function and the rule, never a value. |
| STRUCTURAL TYPING | `app/services/duplicate_checker.py:42-44`, `app/models/messages.py:38-50` | `DedupTurn` Protocol; `Message` satisfies it without imports. Optional tool fields read via `getattr`. |
| TOOL FIELDS | `app/models/messages.py:23-50` | `ToolCallSpec(id, name, arguments: str)`; `Message.tool_calls: tuple = ()`, `tool_call_id: Optional[str] = None` |
| PIPELINE CALL | `app/services/query_pipeline.py:297-305` | Step 1 `key = dedup_key(identity.user_id, messages)`, once, before authorization. Unchanged. |
| PINNED DIGESTS | `tests/test_dedup_key.py:68-83` | Literal hex pins, with a comment "never fix a constant to match the code" |
| INDEPENDENT REBUILD | `tests/test_dedup_key.py:49-52, 156-160` | `_framed_sha256` rebuilds the formula outside the module |
| SPY ON FRAMING | `tests/test_query_pipeline_multiturn.py:313-345` | Spies on `duplicate_checker._sha256_json`; `framed[0]` is the prefix payload. Tool-free stays two calls with `[[role, content], ...]`. |
| PIPELINE TOOL TESTS | `tests/test_query_pipeline_tools.py:53-82, 115-121, 198-204` | `_u/_a/_t` builders; `_keyed` stub to drop; duplicate arm |
| SUPERSEDED REGISTRY | `tests/test_pii_redaction_integration.py:465-485` | Comment `old -> new`, plus the old name added to `_DELIBERATELY_SUPERSEDED_TESTS["tests/test_dedup_key.py"]` |

### Naming / code shape (today)
```python
# SOURCE: app/services/duplicate_checker.py:47-68
DEDUP_KEY_VERSION = "v1"
_KEYED_ROLES = frozenset({"system", "user", "assistant"})
...
def dedup_key(user_id: str, turns: Sequence[DedupTurn]) -> str:
    if not turns:
        raise ValueError("dedup_key needs at least one turn")
    if any(t.role not in _KEYED_ROLES for t in turns):
        raise ValueError("dedup_key has no rule for this role (tool turns: PRD-017)")
    *prefix, last = turns
    if last.role != "user":
        raise ValueError("dedup_key keys on a final user turn")
    prefix_hash = "" if not prefix else _sha256_json([[t.role, t.content] for t in prefix])
    return _sha256_json([DEDUP_KEY_VERSION, user_id, hash_prompt(last.content), prefix_hash])
```

### Tests
```python
# SOURCE: tests/test_dedup_key.py:193-205 (to be replaced)
def test_tool_turn_anywhere_is_refused_naming_prd_017(turns):
    with pytest.raises(ValueError, match="PRD-017"):
        dedup_key(_JUAN, turns)
```

---

## Pinned tool-free keys (computed 2026-11-15 from the CURRENT implementation, before any change)

User `juan@empresa.com`. Computed with `.venv/Scripts/python` against `dedup_key` at HEAD `5e53560`:

| Case | Turns | Key |
|---|---|---|
| single (already pinned, `:71-74`) | `user "summarise this week's incidents"` | `0b206c744aa7f9f63562d512657e199713e403130a76a0eda9f75c0743484652` |
| multi (already pinned, `:77-83`) | `user "list files"`, `assistant "README.md app tests"`, `user "yes"` | `c63baa9722eff55aed5b2e29db3316b4972843bb43dfb7f7f38cc7068ada4705` |
| system_user | `system "be brief"`, `user "list files"` | `d30f177a22197275c34ef46081e0a8a974b5ec0acac53b9591e2163fa2bcb53f` |
| system_multi | `system "be brief"`, `user "list files"`, `assistant "README.md app tests"`, `user "yes"` | `de4af3dcb032b0eb30e0bae5980b11946cadc744894e0c2b8ea14bebf60fb930` |
| user_user | `user "npm test"`, `user "npm test"` | `e368c79de34837cbf74126494e6128150557d9bd53dcdd691d302a972d63a226` |
| non_ascii | `user "acentuación y emoji 🙂"`, `assistant "sí"`, `user "¿y ahora?"` | `f7d83fc4992bd88707566e207147f7a74ac64fe842198b12abf94939f7364234` |

Expected tool-shaped keys. These were computed from the **proposed** formula, independently
of the module (a `hashlib`/`json` script, not `dedup_key`), so the implementation must
reproduce them. With `A = assistant "" calls [["c1","ls","{}"]]` and `T = tool "README.md\nsrc" id "c1"`:

| Case | Turns | Key |
|---|---|---|
| anchor_last | `user "list files"`, A, T, `user "now run the tests"` | `46ac98f59e93155d3117663c87639de6dd96cc5ca179f5b13dda234142f28762` |
| tool_final | `user "list files"`, A, T | `2d0429e076c98d694359db9c9faef08a1b3aa98db13c54f8c1443f53523b0d36` |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/duplicate_checker.py` | UPDATE | Tool-shaped framing; `_KEYED_ROLES` + `tool`; refusals matched to D6; docstring citing PRD-009 D4 and PRD-017 D4 / 6.4 |
| `tests/test_dedup_key.py` | UPDATE | Pins (AC1); framing and anchor tests (AC2, AC3); agent loop + resend (AC4 unit); replace `:193-205` (AC5) |
| `tests/test_query_pipeline_dedup_key.py` | UPDATE | Pipeline: tool conversation keyed with the new key (AC5); agent loop through `run_conversation`, none held, then resend held (AC4) |
| `tests/test_query_pipeline_tools.py` | UPDATE | Drop the `_keyed` stub fixture and its 6 uses; update the module docstring (lines 8-11) |
| `tests/test_pii_redaction_integration.py` | UPDATE | Register the renamed `test_tool_turn_anywhere_is_refused_naming_prd_017` in `_DELIBERATELY_SUPERSEDED_TESTS` plus the `old -> new` comment |

No file is created. `app/services/conversation_key.py` and `app/services/query_pipeline.py`
are not changed.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 0: Re-confirm the pins before touching code

- **Action**: Before editing `duplicate_checker.py`, rerun the pin script and confirm the six
  tool-free keys in the table above, using
  `types.SimpleNamespace(role=..., content=...)` turns and `dedup_key("juan@empresa.com", ...)`.
  If any differs, STOP and report: HEAD moved.
- **Validate**: six hex values printed, all equal to the table.

### Task 1: `dedup_key` over tool turns

- **File**: `app/services/duplicate_checker.py`
- **Action**: UPDATE (lines 42-68)
- **Implement**:
  - `_KEYED_ROLES = frozenset({"system", "user", "assistant", "tool"})`.
  - Add `_ANCHOR = None` with a comment: the anchor's slot in a tool-shaped prefix. A
    tool-free prefix never contains `null`, so the two framings cannot collide
    (PRD-017 Section 6.4).
  - Add `_frame(turn) -> list`:
    - `role == "tool"` → `[role, content, getattr(turn, "tool_call_id", None)]`
    - else, when `calls := getattr(turn, "tool_calls", ())` is non-empty →
      `[role, content, [[c.id, c.name, c.arguments] for c in calls]]`
    - else → `[role, content]`

    `arguments` is the raw string, never parsed (D13). Say so in a comment.
  - Add `_has_tool_fields(turns) -> bool`: `any(t.role == "tool" or getattr(t, "tool_calls", ()) for t in turns)`.
  - `dedup_key`:
    1. Keep the empty check.
    2. Keep the role check, with the message `"dedup_key has no rule for this role"`.
    3. `if turns[-1].role not in ("user", "tool"): raise ValueError("dedup_key keys on a final user turn or a final tool turn")`.
    4. If not `_has_tool_fields(turns)`: run **today's lines 61-68 verbatim** (`*prefix, last`,
       `prefix_hash = "" if not prefix else _sha256_json([[t.role, t.content] for t in prefix])`).
       Note: here the final turn is necessarily `user`, because a final `tool` turn is a tool field.
    5. Otherwise: `anchor_index = max(i for i, t in enumerate(turns) if t.role == "user")`. Use a
       loop or `next(reversed(...), None)`, and if there is none raise
       `ValueError("dedup_key needs a user turn to anchor on (PRD-017 D4)")`. Then
       `prefix_hash = _sha256_json([_ANCHOR if i == anchor_index else _frame(t) for i, t in enumerate(turns)])`
       and `return _sha256_json([DEDUP_KEY_VERSION, user_id, hash_prompt(turns[anchor_index].content), prefix_hash])`.
  - Call `_sha256_json` by its module-global name, exactly twice per key (prefix, then outer).
    The `_sha256_json` spy in `tests/test_query_pipeline_multiturn.py:313-345` monkeypatches
    the module attribute, so it keeps working.
  - Docstring on `dedup_key`. The function has none today; follow the module style, which
    cites sections. It must cover: PRD-009 Section 6.2 / D4 (tool turns were left to "PRD-016",
    meaning this PRD); PRD-017 D4 / Section 6.4 (anchor = last user turn, never a tool turn;
    the prefix holds every other turn with the anchor's slot marked `null`; the three frames);
    that tool-free keys are byte-identical to PRD-009's (no window reset, pinned in
    `tests/test_dedup_key.py`); and why `npm test` twice is not a duplicate (each loop request
    carries a longer prefix) while a byte-identical resend is.
  - Update the existing comment at `:65-67`. Its "The last turn contributes the prompt_hash
    value" holds for the tool-free branch only. For a tool-final conversation the audit
    `prompt_hash` is the tool turn (D7), while the key's anchor is the last user turn.
  - Update `DedupTurn` (`:42-44`) with a one-line comment: optional `tool_calls` /
    `tool_call_id` are read with `getattr` (PRD-017 D5), so `Message` and any
    role/content object both satisfy it.
- **Mirror**: `app/services/conversation_key.py:40-45` (pure, `_sha256_json`, docstring citing decisions)
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`, then rerun the
  Task 0 script. The six values must be unchanged, and the two tool-shaped values must equal the
  second table.

### Task 2: Unit tests in `tests/test_dedup_key.py`

- **File**: `tests/test_dedup_key.py`
- **Action**: UPDATE
- **Implement** (add a `# --- PRD-017 STORY-006 ---` section; use `app.models.messages.Message`
  / `ToolCallSpec` for tool turns, which is what the pipeline passes):
  - **AC1** `test_tool_free_keys_are_pinned_from_prd_009` (parametrized over the four new rows:
    system_user, system_multi, user_user, non_ascii). Assert each key equals its literal from
    the table, with a comment saying the literals were computed from the pre-PRD-017
    implementation (2026-11-15) and must never be refreshed to match the code (PRD-017 D4,
    "unchanged keys"). Also add
    `test_message_instances_key_like_role_content_turns`: the same conversations built from
    `Message(...)` (default `tool_calls=()`, `tool_call_id=None`) give the same keys. That
    proves the real model takes the tool-free branch.
  - **AC2** `test_tool_shaped_key_is_the_section_6_4_formula`: rebuild with `_framed_sha256`
    for anchor_last and tool_final, and assert equality **and** the literal (second table).
    `test_tool_turn_is_never_the_anchor`: for `[u1, A, T]` the outer third field is
    `hash_prompt(u1)`, not `hash_prompt(T.content)`. Show this by asserting the key equals the
    rebuild with `hash_prompt("list files")`. `test_assistant_with_empty_tool_calls_frames_as_today`:
    `[u, Message("assistant", "x", ()), u2]` equals the tool-free key.
    `test_arguments_are_framed_as_the_raw_string`: `"{}"` vs `"{ }"` give different keys.
    `test_call_order_and_each_call_field_are_keyed`: change id, name or arguments, or swap two
    calls, and the key differs.
  - **AC3** `test_anchor_position_is_marked`: `[u1, A(calls), T, u2]` vs `[u1, u2, A(calls), T]`,
    identical texts, give different keys. Also `test_tool_framing_cannot_be_forged_by_tool_free_content`:
    the same texts with `A` and `T` replaced by plain `assistant`/`user` turns whose content is
    the JSON text of a frame (e.g. `'["tool","README.md\\nsrc","c1"]'`, `'null'`) give a different
    key.
  - **AC4 (unit)** `test_npm_test_twice_in_one_loop_never_shares_a_key`: build the loop
    - `r1 = [s, u("run the tests, fix the failure, run them again")]`
    - `r2 = r1 + [A("", call("call_0","bash",'{"command":"npm test"}')), T("call_0", OUT)]`
    - `r3 = r2 + [A("", call("call_0","edit",'{"path":"src/a.ts"}')), T("call_0", "ok")]`
      (id reuse, as some providers do; PRD-017 6.3 rule 3)
    - `r4 = r3 + [A("", call("call_0","bash",'{"command":"npm test"}')), T("call_0", OUT)]`
      (identical command and output to r2)
    - `r5 = r4 + [Message("assistant", "All tests pass."), u(<same text as r1's user turn>)]`

    Assert `len({dedup_key(J, r) for r in loop}) == len(loop)`. Then
    `test_byte_identical_resend_shares_its_key`: `dedup_key(J, r4) == dedup_key(J, copy.deepcopy(r4))`,
    and the same for a list rebuilt from fresh `Message` objects with equal fields.
  - **AC5** Replace `test_tool_turn_anywhere_is_refused_naming_prd_017` (`:193-205`) with
    `test_tool_turns_are_keyed_not_refused` (same two parametrized cases, but the second, as a
    `Message` tool-final, becomes `[_user("x"), A(calls c1), T(c1)]` so it has a call to answer;
    the first, `[tool, user]`, is keyed too, since the pure function does not re-run D6 rule 1).
    It asserts a 64-hex key is returned. Comment it:
    `# PRD-017 D4 (STORY-006): tool turns are keyed in the prefix, never the anchor; this replaces the PRD-017 refusal (was test_tool_turn_anywhere_is_refused_naming_prd_017).`
    Add `test_tool_shaped_conversation_without_a_user_turn_is_refused` (`[A(calls), T]` →
    `match="needs a user turn"`). `test_final_turn_that_is_not_user_is_refused` (`:187-190`) and
    `test_unknown_role_is_refused` (`:208-211`) stay **unedited** and must pass. Check that
    `test_is_pure` (`:219-230`) still passes: the new helpers live outside `dedup_key`, and
    `inspect.getsource(dedup_key)` must not contain `settings`/`datetime`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_dedup_key.py -q`

### Task 3: Register the superseded test name

- **File**: `tests/test_pii_redaction_integration.py`
- **Action**: UPDATE (`:473-485`)
- **Implement**: in the `test_dedup_key.py` comment block, add
  `test_tool_turn_anywhere_is_refused_naming_prd_017 -> test_tool_turns_are_keyed_not_refused (PRD-017 D4, STORY-006)`,
  and add the old name to the `"tests/test_dedup_key.py"` set.
- **Validate**: included in Task 6's run.

### Task 4: Pipeline tests in `tests/test_query_pipeline_dedup_key.py`

- **File**: `tests/test_query_pipeline_dedup_key.py`
- **Action**: UPDATE (append a PRD-017 STORY-006 section; import `Message`, `ToolCallSpec`)
- **Implement**:
  - **AC5** `test_tool_conversation_row_carries_the_tool_shaped_key(temp_db)`:
    `run_conversation` with `[u, A(calls c1), T(c1)]`. No monkeypatch of `dedup_key` (step 1
    must not raise). The result is `QuerySuccessResponse`, and
    `row.dedup_key == dedup_key(_JUAN.user_id, messages)`. Also assert it equals the
    independently rebuilt §6.4 value: build it inline with `hashlib`/`json`, or import
    `_framed_sha256` from `tests.test_dedup_key`, since cross-test-module helper imports are
    already used (`tests/test_query_pipeline_tools.py:36-37`). It must differ from the
    tool-free key of `[u]`.
  - **AC4 (pipeline)** `test_npm_test_twice_is_not_held_but_a_resend_is(temp_db)`: run r1..r5
    from Task 2 in order through `run_conversation`, all with the same identity and
    `_fake_call_openrouter`. Every result is a `QuerySuccessResponse`, so none is held as a
    duplicate, and the five rows' `dedup_key` values are pairwise distinct. Then resend r4 byte
    for byte with `call_openrouter=_fail_if_called`: the result is a
    `QueryBlockedDuplicateResponse` and its row's `dedup_key` equals r4's row's. Keep the loop
    builder in one place: define it in `tests/test_dedup_key.py` as `_npm_test_loop()` and
    import it here. Run it with no `profile` argument; under the default profile the tool
    content (`npm test` output, e.g. `"FAIL src/a.test.ts"` / `"PASS"`) must not trip a pattern.
    Use bland text.
- **Mirror**: `tests/test_query_pipeline_tools.py:77-82` (`_run`), `:198-204` (duplicate arm).
- **Validate**: Task 6.

### Task 5: Drop the `_keyed` stub in `tests/test_query_pipeline_tools.py`

- **File**: `tests/test_query_pipeline_tools.py`
- **Action**: UPDATE
- **Implement**:
  - Delete the `_keyed` fixture (`:115-121`), and remove `_keyed` from the parameters of the
    six tests at `:184, :191, :198, :207, :254, :268`. Their names are unchanged, so nothing
    needs registering.
  - Rewrite the module docstring lines 8-11. Since STORY-006, step 1 keys tool turns with the
    real `dedup_key` (PRD-017 D4), so no stub is needed. The duplicate-arm test is held by the
    real key, because the resend is byte-identical. The upstream message shape is still
    STORY-007's.
  - In `test_duplicate_arm_prompt_is_the_tool_turn` (`:198-204`), add
    `assert _last_row().dedup_key == dedup_key(_JUAN.user_id, _tool_final())`, with a comment
    citing PRD-017 D4. This keeps the arm meaningful: it is held by the real tool-shaped key,
    not by a constant.
  - Keep `monkeypatch.setattr(query_pipeline, "dedup_key", _fail_if_called)` in the D6-violation
    test (`:163`). It proves step 0 runs before step 1.
- **Validate**: Task 6.

### Task 6: Targeted run (one pytest call, foreground)

```bash
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q \
  tests/test_dedup_key.py \
  tests/test_query_pipeline_dedup_key.py \
  tests/test_query_pipeline_tools.py \
  tests/test_query_pipeline_multiturn.py \
  tests/test_pii_redaction_integration.py \
  tests/test_untouched_app.py \
  tests/test_duplicate_scope.py
```

- `test_query_pipeline_multiturn.py`: the `_sha256_json` spy plus row-key equality.
- `test_pii_redaction_integration.py`: a test function was renamed.
- `test_untouched_app.py`: an app file was touched.
- `test_duplicate_scope.py`: duplicate semantics on tool-free rows. It uses `dedup_key`
  indirectly; drop it if the time budget is tight.

Full suite: deferred to orchestrator (user decision).

---

## End-to-End Tests

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` prints OK.
- [ ] Task 0's pin script, rerun after Task 1, prints the same six tool-free keys, and the two
  tool-shaped keys equal the table.
- [ ] Task 6's run is green, with exact pass/fail/skip counts recorded.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q <Task 6 file list>
```

---

## Acceptance Criteria

(Copied from story `STORY-006`)

- [ ] **AC1**: tool-free keys equal values pinned from today's implementation → Task 2 `test_tool_free_keys_are_pinned_from_prd_009` (+ existing `:71-83` pins, unedited), `test_message_instances_key_like_role_content_turns`.
- [ ] **AC2**: anchor = last user turn; every other turn in the prefix in order with the anchor's position marked; the three frames → `test_tool_shaped_key_is_the_section_6_4_formula`, `test_tool_turn_is_never_the_anchor`, `test_assistant_with_empty_tool_calls_frames_as_today`, `test_arguments_are_framed_as_the_raw_string`, `test_call_order_and_each_call_field_are_keyed`.
- [ ] **AC3**: `[u1, A(calls), T, u2]` ≠ `[u1, u2, A(calls), T]` → `test_anchor_position_is_marked` (+ forgery test).
- [ ] **AC4**: `npm test` twice: pairwise-distinct keys over the loop; byte-identical resend gives the same key and is held → `test_npm_test_twice_in_one_loop_never_shares_a_key`, `test_byte_identical_resend_shares_its_key`, `test_npm_test_twice_is_not_held_but_a_resend_is`.
- [ ] **AC5**: through `run_conversation`, step 1 no longer raises and the row carries the new key; `:202-204`'s PRD-017 assertion replaced with a PRD-017 D4 comment → `test_tool_conversation_row_carries_the_tool_shaped_key`, `test_tool_turns_are_keyed_not_refused`, and the `_keyed`-free `tests/test_query_pipeline_tools.py`.
- [ ] All tasks completed.
- [ ] Backend imports (`from app.main import app`) without error.
- [ ] Follows existing patterns (pure function, `ValueError` naming the rule, pinned literals, independent rebuild).
- [ ] D10 / D17: no `/query`, chat or flag-off `/v1` expectation changes, because tool-free keys are byte-identical.

## Risks / Notes

- **Pins must come from today's code.** They are in the table above, computed at HEAD
  `5e53560`. Task 0 re-confirms them. Never regenerate them from the new code.
- **`_sha256_json` spy** (`tests/test_query_pipeline_multiturn.py:339-344`) indexes
  `framed[0]` as the prefix payload. The tool-free branch keeps that order (prefix, then
  outer) and the `[[role, content], ...]` payload.
- **Deviation from the story's literal "every other turn goes into the prefix"**: the anchor's
  slot is in the prefix too, as `null`. That slot *is* the mark PRD 6.4 asks for. The anchor's
  content enters only through `hash_prompt`, as before.
- **The pure function does not re-check D6 rules 1-3.** For example `[tool, user]` is keyed,
  not refused. Step 0 is the guard (`app/services/query_pipeline.py:70-78`). Only the rules the
  key itself needs (final user/tool, a user turn exists) raise.
- **Audit `prompt_hash` vs the key's anchor** differ for tool-final conversations (D7 vs D4).
  This is intended, and documented in the comment at `duplicate_checker.py:65-67`.
- STORY-008 (`/v1` edge) depends on this. Nothing here touches `/v1`.
