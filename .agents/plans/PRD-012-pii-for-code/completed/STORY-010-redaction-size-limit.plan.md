---
story: STORY-010
prd: PRD-012
slug: redaction-size-limit
title: "Size limit and the redaction_characters refusal arm"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-012-pii-for-code        # all stories commit here, no per-story branch
created: 2026-09-25
---

# Plan: Size limit and the redaction_characters refusal arm

## Summary

This story adds one fail-closed arm to `run_conversation` in `app/services/query_pipeline.py`, at the head of step 6. It goes directly after `policy = get_pii_policy(profile_name)` and before the redaction loop.

The arm measures the **analyzable characters** of the conversation under the resolved policy:

- only messages whose role is in `policy.input_roles` count;
- a message is measured as `strip_fenced_blocks(content)` when `policy.skip_fenced_blocks` is set, and as `content` otherwise;
- every `\n` is excluded, so blanked fences (which are all newlines) cost nothing.

When that count is over `policy.max_characters`, the arm writes one audit row and returns `QueryBlockedContextLimitResponse(reason="Conversation exceeds redaction limit", limit="redaction_characters", ...)`. The row has `success=False`, `error_message="redaction limit: characters {actual} > {maximum}"`, the explicit `session_id` and the non-NULL `dedup_key`. Nothing is analyzed and nothing goes upstream.

`chat` has `max_characters=None`, so the arm cannot fire for `/query` or the chat UI.

The schema's `limit` literal gains `"redaction_characters"`. The chat UI's context-limit bubble maps each `limit` to a unit word through a new `copy.CONTEXT_LIMIT_UNITS`, so the new value reads as a phrase and not as an identifier. The existing two units map to themselves, so every existing bubble string stays byte-identical.

No new response class, no new setting, no skip-and-flag (D4).

## User Story

As a security admin
I want a `code` request too large to analyze refused rather than forwarded unmasked
So that size is never a way past redaction

## Story Reference

- Story file: `.agents/stories/PRD-012-pii-for-code/STORY-010-redaction-size-limit.md`
- PRD: `.agents/PRDs/PRD-012-pii-for-code/PRD.md` (Sections 6.1, 6.7 / D4, 9.2 T5, 10, 11)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | query pipeline (step 6), response schema, chat UI copy + state |
| Story | STORY-010 |
| PRD | PRD-012 |
| Epic Branch | `epic/PRD-012-pii-for-code` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` has only `frontend-design`. The story's `skills: []` and its Technical Notes say none applies: the only UI change is one copy string on an existing bubble, with no new component, layout or pigment. The existing copy rules (no "context"/"limit"/"token", no apology) come from `frontend-design` via PRD-010 and are enforced by `tests/test_copy.py`; Task 5 keeps to them. | — |

---

## Findings (measured before planning)

- **F-1: the slot is marked.** [query_pipeline.py:333-337](../../../app/services/query_pipeline.py#L333-L337) resolves `policy` and says "PRD-012 STORY-010's size arm belongs directly below". The STORY-009 plan's handoff says the same.
- **F-2: the setting and the policy field already exist.** `PII_MAX_CHARACTERS_CODE: int = 200_000` with bounds in `_RESOURCE_BOUNDS` ([config.py:25](../../../app/config.py#L25), [config.py:227](../../../app/config.py#L227)). `PiiPolicy.max_characters` is set from it in `_build_code_policy` and is `None` for `chat` ([pii_policy.py:118-145](../../../app/services/pii_policy.py#L118-L145)).
- **F-3: the policy is built at `load()`, not per call.** A test that patches `PII_MAX_CHARACTERS_CODE` must call `pii_policy.load()` afterwards. The existing `_set(monkeypatch, name, value)` helper in `tests/test_query_pipeline_pii_profiles.py` does both.
- **F-4: `strip_fenced_blocks` preserves length and emits only newlines for fenced content** ([pattern_detector.py:161-190](../../../app/services/pattern_detector.py#L161-L190)). So "count the non-newline characters of the blanked text" is exactly "prose characters, fences free".
- **F-5: the bubble prints `result.limit` raw.** [state.py:1248-1252](../../../chat_ui/chat_ui/state.py#L1248-L1252) formats `CONTEXT_LIMIT_DETAIL_TEMPLATE` with `unit=result.limit`. Without a change, the new value would render as "redaction_characters 231554 of 200000".
- **F-6: the copy rules are enforced.** `tests/test_copy.py:996-1030` forbids "context", "limit" and "token" and any apology in the context-limit vocabulary. `test_copy.py` and `test_chat_state.py` are census-pinned by `tests/test_untouched_app.py`: tests may be **appended**, and none may be removed or changed.
- **F-7: the schema test stays green unchanged.** `tests/test_schemas.py:115` parametrizes rejected values `["tokens", "MESSAGES", "", "bytes"]`. The new value is not among them.
- **F-8: the master switch lives in the redactor, not the policy** ([pii_policy.py:26-29](../../../app/services/pii_policy.py#L26-L29); `redact_for_policy` returns early when `PII_REDACTION_ENABLED` is false). See D-2.

---

## Patterns to Follow

### Naming and shape: the existing limit helper

```python
# SOURCE: app/services/query_pipeline.py:67-94
def _context_limit_exceeded(
    messages: Sequence[Message],
) -> Optional[Tuple[ContextLimit, int, int]]:
    """The limit this conversation breaks as (limit, maximum, actual), or None.
    ...
    The comparison is strict `>`: a conversation exactly at the maximum is
    within the limit, not over it.
    """
```

### Error arm: the step-3 refusal (mirror it exactly, changing only the strings)

```python
# SOURCE: app/services/query_pipeline.py:222-239
exceeded = _context_limit_exceeded(messages)
if exceeded is not None:
    limit, maximum, actual = exceeded
    log_query(
        user_id=identity.user_id,
        prompt=prompt,
        device=device,
        success=False,
        error_message=f"context limit: {limit} {actual} > {maximum}",
        session_id=session_id,
        dedup_key=key,
    )
    return QueryBlockedContextLimitResponse(
        reason="Conversation exceeds context limit",
        limit=limit,
        maximum=maximum,
        actual=actual,
    )
```

### Tests: pipeline, audit rows, no upstream

```python
# SOURCE: tests/test_query_pipeline_pii_profiles.py:88-130, 398-418
def _set(monkeypatch, name, value) -> None:
    monkeypatch.setattr(settings, name, value)
    pii_policy.load()
...
before = _last_audit_id()
with pytest.raises(PiiRedactorError, match="^PII analysis failed: boom$"):
    _run(messages, call_openrouter=_fail_if_called, profile=profile)
(row,) = _audit_rows_since(before)
assert row.success is False
assert row.dedup_key is not None
```

### Tests: the refusal row

```python
# SOURCE: tests/test_query_pipeline_context_limit.py:208-237
assert row.success is False
assert row.error_message == "context limit: characters 12 > 10"
assert row.session_id == _SESSION_ID
assert row.dedup_key == dedup_key(_JUAN.user_id, messages)
```

### Chat UI state test

```python
# SOURCE: tests/test_chat_state.py:306-350
def _fake_run_query(identity, prompt, device, model, openrouter_api_key, call_openrouter, session_id=None):
    return QueryBlockedContextLimitResponse(reason=..., limit="characters", maximum=10, actual=12)
_stub_pipeline(monkeypatch, _fake_run_query)
state = _make_state()
await _send(state, "hello world")
assert state.messages[-1].detail == "characters 12 of 10"
```

---

## Design

### D-1: What is counted

```python
def _analyzable_characters(messages, policy) -> int:
    total = 0
    for message in messages:
        if message.role not in policy.input_roles:
            continue
        text = strip_fenced_blocks(message.content) if policy.skip_fenced_blocks else message.content
        total += len(text) - text.count("\n")
    return total
```

The AC says "newline runs not counted". Excluding **every** `\n` is the simplest rule that meets it:

- A blanked fence is nothing but newlines, so it counts zero.
- A single newline in prose is a run of length one. Excluding it undercounts by at most one character per line, and newlines cost the analyzer nothing anyway.
- The rule is monotone, has no parameters, and is easy to state in the docstring and the README (STORY-014).

It is applied the same way when `skip_fenced_blocks=False`, so the only switch-dependent part is which text is measured.

`system` is not counted under the default `code` policy, because it is not in `input_roles`. It is counted when `PII_CODE_REDACT_SYSTEM=true`. This follows directly from "measure what the analyzer will process" (PRD Section 6.7).

### D-2: The master switch turns the arm off

With `PII_REDACTION_ENABLED=false`, nothing is analyzed under any policy, so there is no redaction for size to bypass. A refusal that says "exceeds redaction limit" would be false. The arm is therefore guarded by `settings.PII_REDACTION_ENABLED`, read per call, in the style of the step-3 helper. A test pins it.

This is a judgement call the PRD does not spell out. It follows Section 9.3: "`PII_REDACTION_ENABLED=false` still turns off every policy. It is the master switch." **Flag it in the report.**

### D-3: The helper and its signature

`_redaction_limit_exceeded(messages, policy) -> Optional[Tuple[int, int]]` returns `(maximum, actual)` or `None`. It returns `None` without counting when `policy.max_characters is None` or the master switch is off. The comparison is strict `>`, as at step 3.

The `ContextLimit` alias stays `Literal["messages", "characters"]`: it types step 3's helper, which can never return the new value. The arm passes `limit="redaction_characters"` literally.

### D-4: Position

The arm sits after patterns (step 5) and after the flag arm, before the redaction loop. Therefore:

- A conversation that is both over the size limit and blocked by a pattern gets the pattern refusal.
- A flagged over-limit conversation leaves two rows, flag then refusal. This is the documented flag-then-continue shape (PRD-011 Section 6.7).
- The duplicate check already ran. The refusal row is `success=0`, so it is never a prior query (PRD-009 Section 6.3). An identical request sent after the operator raises the limit goes through.

### D-5: The chat UI copy

A new constant in `copy.py`:

```python
CONTEXT_LIMIT_UNITS = {
    "messages": "messages",
    "characters": "characters",
    "redaction_characters": "characters to check for personal data",
}
```

`state.py` uses `unit=CONTEXT_LIMIT_UNITS[result.limit]`. Indexing, not `.get`: a test pins that the keys equal the schema's literal, so a fourth value added without copy fails the suite and not a user's send.

- The detail becomes "characters to check for personal data 231554 of 200000". It names what is too large in the reader's terms and uses none of the three banned words.
- The headline ("This chat is too long to send."), the tag and the new-chat notice are shared and unchanged. The bubble branches on `limit` only through the unit word, per the Technical Notes.
- The two existing units map to themselves, so "characters 12 of 10" and every persisted `detail` stay byte-identical.

The chat UI runs `chat`, so it cannot receive this value today. It renders correctly anyway, for PRD-014 and for any future call site that shares `ChatState`.

### Risks

| Risk | Mitigation |
|------|------------|
| A test patches `PII_MAX_CHARACTERS_CODE` and forgets `pii_policy.load()`, so the old limit applies silently | Use the existing `_set` helper for every setting change. The boundary test (exactly at the maximum → not refused; one over → refused) fails loudly if the limit did not move |
| An existing `code` test in the profile suite starts refusing | Shipped limit is 200,000; every existing `code` conversation there is far below it. Run the whole file |
| The shared bubble copy drifts | Append-only tests in `test_copy.py`; no existing constant is edited |
| The master-switch choice (D-2) is contested at review | One-line guard plus one test. Reversing it is deleting both |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/schemas.py` | UPDATE | `limit: Literal["messages", "characters", "redaction_characters"]`; docstring names the third maximum and its source (`PII_MAX_CHARACTERS_CODE` via the policy) |
| `app/services/query_pipeline.py` | UPDATE | import `strip_fenced_blocks`; `_analyzable_characters`, `_redaction_limit_exceeded`; the arm at the head of step 6; replace the "belongs directly below" comment |
| `chat_ui/chat_ui/copy.py` | UPDATE | `CONTEXT_LIMIT_UNITS`, with a comment in the existing block's voice |
| `chat_ui/chat_ui/state.py` | UPDATE | import `CONTEXT_LIMIT_UNITS`; `unit=CONTEXT_LIMIT_UNITS[result.limit]`; comment |
| `tests/test_query_pipeline_pii_profiles.py` | UPDATE (append) | STORY-010 section: the arm, the row, fences, roles, newlines, boundary, dedup, master switch, position, chat cannot fire |
| `tests/test_schemas.py` | UPDATE (append) | the new literal is accepted and serializes |
| `tests/test_copy.py` | UPDATE (append only; census-pinned) | unit map covers the literal exactly, existing units are identities, the new unit obeys the vocabulary rules |
| `tests/test_chat_state.py` | UPDATE (append only; census-pinned) | a `redaction_characters` result renders a `context_limit` bubble with the new detail |

No file created. No migration, setting or dependency.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Widen the `limit` literal

- **File**: `app/models/schemas.py`
- **Action**: UPDATE
- **Implement**:
  - `limit: Literal["messages", "characters", "redaction_characters"]`.
  - Extend the class docstring by one paragraph. `redaction_characters` is the PII redaction limit, reported only under a policy with `max_characters` set (`code`; PRD-012 Section 6.7, D4). It is checked at step 6, after the two context limits, so it is never reported together with them. `maximum` is the policy's `max_characters` for that call.
- **Mirror**: the existing docstring's "`maximum` is the configured limit as read for *that call*" paragraph.
- **Validate**: `pytest tests/test_schemas.py -q` (unchanged tests still green)

### Task 2: The measuring helpers

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  - `from app.services.pattern_detector import inspect, strip_fenced_blocks`.
  - `_analyzable_characters(messages, policy) -> int` as in D-1.
  - `_redaction_limit_exceeded(messages, policy) -> Optional[Tuple[int, int]]` as in D-3.
  - Place both after `_context_limit_exceeded`.
  - The docstrings state:
    - what is counted: covered roles, blanked fences, no `\n`;
    - that the function never calls the analyzer, only measures lengths;
    - the strict `>`;
    - that the master switch is read per call (D-2);
    - that `chat` returns `None` because `max_characters is None`.
- **Mirror**: `_context_limit_exceeded` ([query_pipeline.py:67-94](../../../app/services/query_pipeline.py#L67-L94)) for docstring voice and the per-call settings read.
- **Validate**: `python -c "import app.services.query_pipeline"`

### Task 3: The refusal arm

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: directly after `policy = get_pii_policy(profile_name)`:
  ```python
  over = _redaction_limit_exceeded(messages, policy)
  if over is not None:
      maximum, actual = over
      log_query(
          user_id=identity.user_id,
          prompt=prompt,
          device=device,
          success=False,
          error_message=f"redaction limit: characters {actual} > {maximum}",
          session_id=session_id,
          dedup_key=key,
      )
      return QueryBlockedContextLimitResponse(
          reason="Conversation exceeds redaction limit",
          limit="redaction_characters",
          maximum=maximum,
          actual=actual,
      )
  ```
  - Replace the "STORY-010's size arm belongs directly below" sentence with a block comment giving the arm's reasons:
    - position after patterns, because what it measures depends on the policy (PRD Section 6.1);
    - fail closed with no skip-and-flag (D4, T5);
    - `success=False` for the step-3 reason, so the row is never a prior query;
    - unreachable under `chat`.
  - STORY-011 will add `profile=` to this call along with every other arm. Do not add it here.
- **Mirror**: the step-3 arm ([query_pipeline.py:204-239](../../../app/services/query_pipeline.py#L204-L239)).
- **Validate**: `pytest tests/test_query_pipeline_pii_profiles.py tests/test_query_pipeline_context_limit.py -q` (existing tests green)

### Task 4: Pipeline tests

- **File**: `tests/test_query_pipeline_pii_profiles.py`
- **Action**: UPDATE (append a `# --- STORY-010: the redaction_characters arm ---` section; add AC lines to the module docstring)
- **Implement**: all under `temp_db`; settings via `_set`.
  1. **Refused, counts, no analyzer, no upstream** (AC 1): `_set PII_MAX_CHARACTERS_CODE=20`; `user` turn of 21 prose characters; patch `query_pipeline.redact_for_policy` and `pii_redactor._get_analyzer` to `_fail_if_called`. Assert the response equals `QueryBlockedContextLimitResponse(reason="Conversation exceeds redaction limit", limit="redaction_characters", maximum=20, actual=21)`, with `call_openrouter=_fail_if_called`.
  2. **Exactly one row** (AC 2): the same case with `session_id="s-010"`. `(row,) = _audit_rows_since(before)`. Assert:
     - `success is False`;
     - `error_message == "redaction limit: characters 21 > 20"`;
     - `session_id == "s-010"`;
     - `dedup_key == dedup_key(_JUAN.user_id, messages)`;
     - `was_duplicate_blocked is False`.
  3. **Not held as a duplicate** (AC 2): refuse once. Then `_set PII_MAX_CHARACTERS_CODE=200_000` and send the identical conversation with an `_Upstream()` stub. Assert `QuerySuccessResponse` and one upstream call.
  4. **Fences do not count** (AC 3): limit 50. A `user` turn of short prose plus a fenced block of ~500 characters. Not refused, and the upstream receives the fenced block byte-identical. Companion: `_set PII_CODE_SKIP_CODE_BLOCKS=False` with the same input → refused. This proves the fence is what was excluded.
  5. **Newline runs not counted**: limit 5; content `"ab\n\n\n\n\ncd"` → not refused (actual would be 4). `"abc\n\n\ndef"` → refused with `actual=6`.
  6. **Boundary**: content of exactly `maximum` characters → not refused; `maximum + 1` → refused.
  7. **Only covered roles count**: a 500-character `system` turn plus a short `user` turn under limit 50 → not refused. With `_set PII_CODE_REDACT_SYSTEM=True` → refused. A 500-character `assistant` history turn → refused, because `assistant` is covered.
  8. **Master switch** (D-2): `monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)`, over the limit → not refused, upstream called.
  9. **Patterns first** (D-4): an over-limit conversation whose last `user` turn matches a pattern the built-in `code` profile **blocks** on `user` → `QueryBlockedSuspiciousResponse`, one row, no `redaction limit` row. Pick the prompt from an existing blocking case in `tests/test_pattern_*` for the `code` profile rather than inventing one.
  10. **Chat cannot fire** (AC 5): assert `pii_policy.get_pii_policy("chat").max_characters is None`. Then:
      - `_set PII_MAX_CHARACTERS_CODE=1`;
      - `monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 60)`;
      - stub `query_pipeline.redact` as the identity (`lambda text: (text, [])`), so no model is needed.

      Send a conversation of exactly 60 characters through `run_conversation` with no profile, and through `query_pipeline.run_query`. Both return `QuerySuccessResponse`. Parametrize over two shapes, one prose turn and one that is mostly a fenced block, so "any input" is not a single sample.
- **Mirror**: the existing helpers `_run`, `_Upstream`, `_audit_rows_since`, `_set`, `_fail_if_called` in the same file; `tests/test_query_pipeline_context_limit.py:208-237` for the row assertions.
- **Validate**: `pytest tests/test_query_pipeline_pii_profiles.py -v`

### Task 5: Chat UI copy and state

- **Files**: `chat_ui/chat_ui/copy.py`, `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**:
  - `copy.py`: add `CONTEXT_LIMIT_UNITS` (D-5) directly under `CONTEXT_LIMIT_DETAIL_TEMPLATE`. The comment says:
    - the keys are the schema's `limit` values;
    - the values are what the reader recognizes;
    - `redaction_characters` counts only what gets checked for personal data (code blocks excluded), so the phrase says that and not "limit".
  - `state.py`: add `CONTEXT_LIMIT_UNITS` to the `from .copy import (...)` block and use `unit=CONTEXT_LIMIT_UNITS[result.limit]`. Extend the adjacent comment by one line on why the unit goes through the map.
  - No change to `bubbles.py`: the renderer draws `message.detail`.
- **Validate**: `pytest tests/test_copy.py tests/test_context_limit_bubble.py tests/test_chat_state.py tests/test_chat_components_import.py -q` (existing tests green)

### Task 6: Schema, copy and state tests (append only)

- **Files**: `tests/test_schemas.py`, `tests/test_copy.py`, `tests/test_chat_state.py`
- **Action**: UPDATE, append only. `test_copy.py` and `test_chat_state.py` are census-pinned (F-6), so edit nothing above the new section and add a `# --- PRD-012 STORY-010 ---` banner.
- **Implement**:
  - `test_schemas.py`: `QueryBlockedContextLimitResponse(reason="Conversation exceeds redaction limit", limit="redaction_characters", maximum=200000, actual=231554).model_dump()` equals the PRD Section 6.7 JSON body.
  - `test_copy.py`:
    - `set(CONTEXT_LIMIT_UNITS) == set(get_args(QueryBlockedContextLimitResponse.model_fields["limit"].annotation))`;
    - `CONTEXT_LIMIT_UNITS["messages"] == "messages"` and `["characters"] == "characters"` (existing detail strings unchanged);
    - every value is non-empty, and none contains "context", "limit", "token" or an apology word (the same lists as `test_the_context_limit_copy_names_no_mechanism_and_does_not_apologize`, restated);
    - the `redaction_characters` value contains "personal data".
  - `test_chat_state.py`: copy the shape of `test_chat_state_send_context_limit_renders_a_context_limit_bubble`. The fake returns `limit="redaction_characters", maximum=200000, actual=231554`. Assert:
    - `kind == "context_limit"`;
    - `content == "Conversation exceeds redaction limit"`;
    - `detail == "characters to check for personal data 231554 of 200000"`.
- **Validate**: `pytest tests/test_schemas.py tests/test_copy.py tests/test_chat_state.py tests/test_untouched_app.py -q`

---

## End-to-End Tests

`code` has no HTTP ingress until PRD-014, so E2E is at the `run_conversation` level against a real `temp_db`, plus the chat UI's bubble through `ChatState`:

- [ ] `run_conversation(profile="code")` over the limit → `BLOCKED` / `redaction_characters`, one audit row as AC 2 describes, upstream stub never called (Task 4, cases 1–2)
- [ ] The same request after the limit is raised → success, not a duplicate (Task 4, case 3)
- [ ] A fence-heavy `code` conversation whose raw size is over the limit → answered (Task 4, case 4)
- [ ] `POST /query` path (`run_query`) and no-profile `run_conversation` at `CONTEXT_MAX_CHARACTERS` → answered, whatever `PII_MAX_CHARACTERS_CODE` is (Task 4, case 10)
- [ ] `ChatState` given a `redaction_characters` result → `context_limit` bubble with the new detail (Task 6)
- [ ] Optional manual check: run the chat UI and force a `characters` refusal with a tiny `CONTEXT_MAX_CHARACTERS`. The bubble still reads "characters N of M"

---

## Validation

```bash
python -c "import app.services.query_pipeline"
pytest tests/test_query_pipeline_pii_profiles.py tests/test_query_pipeline_context_limit.py tests/test_schemas.py -v
pytest tests/test_copy.py tests/test_context_limit_bubble.py tests/test_chat_state.py tests/test_untouched_app.py -q
pytest tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py tests/test_pii_characterization.py -q
pytest tests/ -q          # mass fixture errors = restart the libSQL dev container, not bisect code
git diff --stat tests/    # only the four appended suites; no existing assertion changed
```

---

## Handoff (for later stories)

- **STORY-011**: the new `log_query` call in the size arm is one more arm that needs `profile=profile_name`. It sits between the flag arm and the step-6 redaction-error arm.
- **STORY-013**: the round-trip suite's large inputs must stay under `PII_MAX_CHARACTERS_CODE`, or set it explicitly. Fenced bulk does not count.
- **STORY-014**: the README documents the refusal body, the error message, what is counted (covered roles, fences and newlines excluded) and the master-switch behaviour (D-2).

---

## Acceptance Criteria

(Copied from story `STORY-010`)

- [ ] Given `profile="code"` and analyzable characters (covered roles, fenced blocks blanked, newline runs not counted) above `PII_MAX_CHARACTERS_CODE`, when `run_conversation` runs, then it returns `QueryBlockedContextLimitResponse(reason="Conversation exceeds redaction limit", limit="redaction_characters", maximum=..., actual=...)` and `call_openrouter` is not called.
- [ ] Given that refusal, when the audit is read, then exactly one row was written by the arm: `success=0`, `error_message="redaction limit: characters {actual} > {maximum}"`, explicit `session_id`, non-NULL `dedup_key`; and a later identical request is not held as a duplicate.
- [ ] Given a conversation whose raw size exceeds the limit only because of fenced blocks, when it runs under `code`, then it is not refused.
- [ ] Given `app/models/schemas.py`, when it is read, then `limit` is `Literal["messages", "characters", "redaction_characters"]`, and the chat UI's context-limit bubble renders the new value with copy that names it.
- [ ] Given `/query` or the chat UI (`chat`, `max_characters=None`), when any input within `CONTEXT_MAX_CHARACTERS` is sent, then this arm cannot fire, which a test pins.
- [ ] All tasks completed
- [ ] Full suite green; no existing assertion changed in the four named PII/regression suites
- [ ] Follows existing patterns (step-3 arm shape, `_set` + `load()`, append-only census suites)
