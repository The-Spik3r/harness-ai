---
story: STORY-002
prd: PRD-016
slug: retarget-tool-calling-runtime-strings
title: Retarget the six "(PRD-016)" tool-calling runtime strings to "(PRD-017)"
type: REFACTOR
complexity: LOW
epic_branch: epic/PRD-016-action-policy-rules        # all stories commit here, no per-story branch
created: 2026-11-15
---

# Plan: Retarget the six "(PRD-016)" tool-calling runtime strings to "(PRD-017)"

## Summary

The code calls tool calling "PRD-016" because the briefs numbered it that way; PRD-015 took the endpoint, this PRD is action policy, and tool calling is now PRD-017 (PRD Numbering note, D14). Six runtime string literals under `app/` carry `(PRD-016)`, and two of them reach a `/v1` client verbatim. This story changes the token `PRD-016` to `PRD-017` in exactly those strings and nothing else in them, updates every test that asserts them (each with a `PRD-016 D14` comment), and fixes the two user-facing "tool calling ships (PRD-016)" sentences in `docs/features.md`. Comments and docstrings that say PRD-016 stay as they are. One seventh runtime string, in `duplicate_checker.py`, means tool calling too but is not written `(PRD-016)`; this plan retargets it as well (see Deviations).

## User Story

As an integrating developer reading a `/v1` error
I want "tool calling is not supported" to point at the PRD that will actually enable tools
So that I am not sent to the action-policy document when I look up why my request was refused

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-002-retarget-tool-calling-runtime-strings.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md` (Numbering note line 12; Section 10 line 439; Section 15 / API line 573; D14 line 737)

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (string-only; no behaviour change, error codes unchanged) |
| Complexity | LOW |
| Systems Affected | `/v1` translator, message normalizer, OpenRouter client, query pipeline step 0, dedup key, `docs/features.md` |
| Story | STORY-002 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI aesthetics). This story has no UI; story frontmatter `skills: []` agrees. | none |

---

## Inventory (verified by grep and by opening each line)

### Runtime strings under `app/` containing `(PRD-016)`: six, as the story says

`grep -rn "(PRD-016)" app/ --include=*.py` returns exactly these six; no comment under `app/` contains the literal `(PRD-016)`.

| # | File:line | Literal today | Reaches |
|---|-----------|---------------|---------|
| 1 | `app/services/v1_translate.py:120` | `"tool calling is not supported (PRD-016)"` (`_REJECTED_RULES[TOOLS_NOT_SUPPORTED]`) | `/v1` 400 body as `"<key>: tool calling is not supported (PRD-016)"` |
| 2 | `app/services/v1_translate.py:218` | `f"{location}: tool calls are not supported (PRD-016)"` | `/v1` 400 body for a message with `tool_calls` / `function_call` |
| 3 | `app/services/v1_translate.py:222` | `f"{location}: tool turns are not supported (PRD-016)"` | `/v1` 400 body for a `role: tool` message |
| 4 | `app/models/messages.py:76` | `"tool_calls are not supported (PRD-016)"` (`MessageNormalizationError`) | `/query` / chat paths via the normalizer |
| 5 | `app/services/openrouter_client.py:199` | `"; tool calls are not supported (PRD-016)"` appended to `OpenRouterError` | upstream-failure message |
| 6 | `app/services/query_pipeline.py:73` | `"tool turns are not supported (PRD-016)"` (`InvalidConversationError`) | programming error, no ingress produces it |

### A seventh runtime string that means tool calling, not written `(PRD-016)`

| # | File:line | Literal today |
|---|-----------|---------------|
| 7 | `app/services/duplicate_checker.py:60` | `"dedup_key has no rule for this role (tool turns: PRD-016)"` (`ValueError`) |

The story's AC4 search for `(PRD-016)` does not find it, and no client can read it (the translator and step 0 refuse tool turns first). It is still a runtime string naming tool calling as PRD-016, and its test asserts the token. Retargeted in Task 6; see Deviations.

### PRD-016 mentions under `app/` that stay (comments/docstrings, read through the Numbering note)

`app/db/models.py:113`, `app/models/messages.py:14`, `app/services/audit_logger.py:52`, `app/services/pii_redactor.py:527` and `:530` (docstring), `app/services/query_pipeline.py:557`, `:639`, `:775`. Not changed (AC4, PRD line 12).

### Tests asserting each string

| String | Test file:line | Assertion today | Change |
|--------|----------------|-----------------|--------|
| 1 | `tests/test_v1_translate_request.py:633` (`test_tool_use_is_tools_not_supported`, 8 params) | `exc.message == f"{key}: tool calling is not supported (PRD-016)"` | `(PRD-017)` |
| 1 | `tests/test_v1_router.py:257` (`test_translation_refusal_is_400_without_row`) | `"message": "tools: tool calling is not supported (PRD-016)"`; `code` `tools_not_supported` at :260 stays | `(PRD-017)` |
| 1 | `tests/e2e/test_continue.py:444` | substring `"400 tools: tool calling is not supported"` (no PRD token) | none; still passes |
| 2, 3 | `tests/test_v1_translate_request.py:151, 160, 166, 172` | `match` on `"tool turns are not supported"` / `"tool calls are not supported"` (no PRD token) | none; still passes |
| 3 | `tests/test_v1_translate_request.py:247-257` | code/param only | none |
| 4 | `tests/test_messages.py:115` (`test_refuses_table_row`, id `tool-calls-key`; comment at :107-108) | `match="PRD-016"` | `"PRD-017"`, comment updated |
| 4 | `tests/test_messages.py:145` (second refusal table) | `match="PRD-016"` | `"PRD-017"` |
| 5 | `tests/test_openrouter_client.py:326` (`test_null_content_with_tool_calls_names_prd_016`) | `match=r"tool calls are not supported \(PRD-016\)"` | `\(PRD-017\)`; rename test `..._names_prd_017` |
| 5 | `tests/test_openrouter_client.py:336` (`test_null_content_without_tool_calls_omits_prd_016_note`) | `assert "PRD-016" not in str(...)` | **must** become `"PRD-017"`, or it passes vacuously after the change; rename `..._omits_prd_017_note` |
| 6 | `tests/test_query_pipeline_run_conversation.py:158`, `tests/test_query_pipeline_multiturn.py:857` | `pytest.raises(InvalidConversationError)` with no `match` | none |
| 7 | `tests/test_dedup_key.py:202` (`test_tool_turn_anywhere_is_refused_naming_prd_016`) | `match="PRD-016"` | `"PRD-017"`; rename `..._naming_prd_017` |

Other `PRD-016` hits in `tests/` are comments/docstrings or this PRD's own corpus and stay: `tests/corpora/actions/SOURCES.md:3` (genuinely this PRD), `tests/test_audit_characterization.py:532`, `tests/test_pattern_corpus.py:500`, `tests/test_pii_code_corpus.py:296`, `tests/test_query_pipeline_patterns.py:32, 379`.

### `docs/features.md`

The file uses the briefs' numbering throughout (PRD-014 = endpoint, PRD-015 = action policy, PRD-016 = tool calling). `grep -n "PRD-01[4-7]" docs/features.md`:

| Line | Text | Means | This story |
|------|------|-------|------------|
| 82 | "the pipeline refuses `tool` turns until tool calling ships (PRD-016)" | tool calling | change to `(PRD-017)` |
| 151 | "The pipeline refuses `tool` turns until tool calling ships (PRD-016), so this cell is tested at the function level only." | tool calling | change to `(PRD-017)` |
| 82 | "[Action policy rules](roadmap.md#action-policy-rules) (PRD-015)" | action policy (now PRD-016) | not tool calling; leave, flag for STORY-020 |
| 82, 153 | "[OpenAI-compatible endpoint](roadmap.md#openai-compatible-endpoint) (PRD-014)" | endpoint (actually PRD-015, already shipped) | not tool calling; leave, flag for STORY-020 |
| 220 | "the OpenAI-compatible endpoint PRD-014 will add" | endpoint | not tool calling; leave, flag |
| 31 | "since PRD-013 every account..." | PRD-013 usage limits | correct; leave |

`README.md`, `docs/api.md`, `docs/roadmap.md`: no `PRD-016` mention (grep). `docs/api.md:200` ("Always `false` until tool calling exists") names no PRD; leave.

---

## Patterns to Follow

### Naming / string shape (keep every other character identical)
```
# SOURCE: app/services/v1_translate.py:119-122
_REJECTED_RULES = {
    TOOLS_NOT_SUPPORTED: "tool calling is not supported (PRD-016)",
    UNSUPPORTED_PARAMETER: "only the default value is supported on this endpoint",
}
```

### Error handling (unchanged; codes stay)
```
# SOURCE: app/services/v1_translate.py:216-223
if "tool_calls" in item or "function_call" in item:
    raise V1RequestError(
        TOOLS_NOT_SUPPORTED, f"{location}: tool calls are not supported (PRD-016)", location
    )
```
Line 218 is 100 characters with indentation; `PRD-017` is the same length, so the line length does not change.

### Modified-test comment convention
```
# SOURCE: tests/test_audit_router.py:91, tests/test_admin_models.py:39
# PRD-011 D6: two additive, nullable fields (STORY-010).
```
Use the same shape, e.g. `# PRD-016 D14 (STORY-002): tool calling is PRD-017; was (PRD-016).`

### Tests
```
# SOURCE: tests/test_openrouter_client.py:321-336
def test_null_content_with_tool_calls_names_prd_016():
    ...
    with pytest.raises(OpenRouterError, match=r"tool calls are not supported \(PRD-016\)"):
...
def test_null_content_without_tool_calls_omits_prd_016_note():
    ...
    assert "PRD-016" not in str(exc_info.value)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/v1_translate.py` | UPDATE | strings 1-3 (lines 120, 218, 222) |
| `app/models/messages.py` | UPDATE | string 4 (line 76) |
| `app/services/openrouter_client.py` | UPDATE | string 5 (line 199) |
| `app/services/query_pipeline.py` | UPDATE | string 6 (line 73) |
| `app/services/duplicate_checker.py` | UPDATE | string 7 (line 60), deviation |
| `tests/test_v1_translate_request.py` | UPDATE | line 633 |
| `tests/test_v1_router.py` | UPDATE | line 257 |
| `tests/test_messages.py` | UPDATE | lines 107-108 comment, 115, 145 |
| `tests/test_openrouter_client.py` | UPDATE | lines 321, 326, 329, 336 (names + assertions) |
| `tests/test_dedup_key.py` | UPDATE | lines 201-202 |
| `docs/features.md` | UPDATE | lines 82, 151 (tool-calling token only) |

0 files to CREATE (besides this plan), 11 to UPDATE.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: `/v1` translator strings (1-3)

- **File**: `app/services/v1_translate.py`
- **Action**: UPDATE
- **Implement**: in lines 120, 218 and 222 replace `(PRD-016)` with `(PRD-017)`. Nothing else in the strings, no comment added on these lines (the Numbering note covers them), the `TOOLS_NOT_SUPPORTED` code untouched.
- **Mirror**: the existing literals.
- **Validate**: `grep -n "PRD-01" app/services/v1_translate.py` shows only `(PRD-017)` at 120/218/222.

### Task 2: Normalizer, OpenRouter client, pipeline step 0 (strings 4-6)

- **Files**: `app/models/messages.py:76`, `app/services/openrouter_client.py:199`, `app/services/query_pipeline.py:73`
- **Action**: UPDATE
- **Implement**: `(PRD-016)` to `(PRD-017)` in each literal. Leave `messages.py:14` and `query_pipeline.py:557, 639, 775` comments alone.
- **Validate**: `grep -rn "(PRD-016)" app/ --include=*.py` returns nothing.

### Task 3: Tests for string 1

- **Files**: `tests/test_v1_translate_request.py:633`, `tests/test_v1_router.py:257`
- **Action**: UPDATE
- **Implement**: assert `(PRD-017)`; add above each changed line `# PRD-016 D14 (STORY-002): tool calling is PRD-017.` Keep `"code": "tools_not_supported"` (router :260) and `exc.code == TOOLS_NOT_SUPPORTED` (:631) as they are; they prove AC1's "code is still `tools_not_supported`".
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_translate_request.py tests/test_v1_router.py -q -p no:cacheprovider`

### Task 4: Tests for string 4

- **File**: `tests/test_messages.py`
- **Action**: UPDATE
- **Implement**: `match` values at :115 and :145 become `"PRD-017"`; the comment at :107-108 ("must hit the PRD-016 rule") becomes "must hit the tool-calling (PRD-017) rule" and gains the `PRD-016 D14` citation; add a `# PRD-016 D14` comment at :145.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_messages.py -q -p no:cacheprovider`

### Task 5: Tests for string 5

- **File**: `tests/test_openrouter_client.py`
- **Action**: UPDATE
- **Implement**: :326 regex to `\(PRD-017\)`; :336 to `assert "PRD-017" not in ...` (otherwise the negative test is vacuous); rename the two tests `test_null_content_with_tool_calls_names_prd_017` and `test_null_content_without_tool_calls_omits_prd_017_note`; one `# PRD-016 D14 (STORY-002)` comment on each changed assertion.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_openrouter_client.py -q -p no:cacheprovider`

### Task 6: dedup_key string (7) and its test (deviation)

- **Files**: `app/services/duplicate_checker.py:60`, `tests/test_dedup_key.py:201-202`
- **Action**: UPDATE
- **Implement**: `(tool turns: PRD-016)` to `(tool turns: PRD-017)`; test `match="PRD-017"`, rename `test_tool_turn_anywhere_is_refused_naming_prd_017`, add the `PRD-016 D14` comment noting it is the seventh string the PRD's count of six omits because no client reads it.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_dedup_key.py -q -p no:cacheprovider`
- If the orchestrator rules this out of scope, skip Task 6 entirely; AC4 still holds, because the literal is not `(PRD-016)`.

### Task 7: `docs/features.md`

- **File**: `docs/features.md`
- **Action**: UPDATE
- **Implement**: at lines 82 and 151, "until tool calling ships (PRD-016)" becomes "(PRD-017)". Do not touch line 82's `(PRD-015)` (action policy) or the `(PRD-014)` endpoint references at 82/153/220: they are not tool calling, and STORY-020 rewrites this file's action-policy content. Do not edit PRD-015's documents, plans or reports.
- **Validate**: `grep -n "PRD-016" docs/features.md` returns nothing; `grep -n "PRD-017" docs/features.md` returns 82 and 151.

### Task 8: Sweep and full suite

- **Validate**:
  - `grep -rn "(PRD-016)" app/ --include=*.py` returns nothing (AC4)
  - `grep -rn "PRD-016" app/ --include=*.py` returns only the comment/docstring lines listed in the Inventory
  - `grep -rn "PRD-016" tests/ --include=*.py` returns only the comment/docstring lines listed above (no assertion)
  - `.venv/Scripts/python -c "from app.main import app; print('OK')"`
  - targeted: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_translate_request.py tests/test_v1_router.py tests/test_messages.py tests/test_openrouter_client.py tests/test_dedup_key.py tests/test_query_pipeline_run_conversation.py tests/test_query_pipeline_multiturn.py -q -p no:cacheprovider`
  - full: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider` (background; record counts)

---

## End-to-End Tests

- [ ] `tests/test_v1_router.py::test_translation_refusal_is_400_without_row` proves the wire body: `"tools: tool calling is not supported (PRD-017)"`, `code: tools_not_supported`, 400, no audit row.
- [ ] `tests/e2e/test_continue.py:444` asserts a PRD-free prefix, so it is unaffected; it needs no run for this story (it drives the Continue CLI).
- [ ] No chat UI change: `chat_ui/` contains none of these strings (grep).

---

## Validation

```bash
grep -rn "(PRD-016)" app/ --include=*.py       # expect no output
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider
```

---

## Deviations and risks

1. **Seventh string.** `app/services/duplicate_checker.py:60` names tool calling as PRD-016 in a runtime `ValueError`, written `(tool turns: PRD-016)`. The PRD counts six because it counts strings a `/v1` client can read; this one is unreachable from any ingress. The plan retargets it (Task 6) because D14's reason applies to any reader and its test asserts the token. It can be dropped without breaking an AC.
2. **Vacuous negative test.** `tests/test_openrouter_client.py:336` asserts `"PRD-016" not in` the message. After the change it would pass whatever the code says. It must assert `"PRD-017"` to keep meaning something.
3. **features.md numbering is off by one throughout**: action policy as PRD-015, endpoint as PRD-014. Lines 82 and 153 also say `code` has no HTTP ingress "until the OpenAI-compatible endpoint", which PRD-015 has already shipped. Those are outside this story's tool-calling scope; STORY-020 owns the file's update and should fix them.
4. **Test renames.** Three test functions named `..._prd_016` are renamed to `..._prd_017` so the name matches the assertion. No code or config references them by name. Archived PRD-009/PRD-010 plans and reports do (for example `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-005-...plan.md:411`). Those are historical records: leave them unedited.

---

## Acceptance Criteria

(Copied from story `STORY-002`)

- [ ] Given a `/v1` request with `tools`, when it is refused, then the error message reads `tool calling is not supported (PRD-017)` and the code is still `tools_not_supported`. (Task 1, Task 3; `test_v1_router.py:257-260`, `test_v1_translate_request.py:631-633`)
- [ ] Given the six runtime strings listed in PRD Section 15 Evidence (`v1_translate.py` x3, `messages.py`, `openrouter_client.py`, `query_pipeline.py`), when the story is done, then each says `(PRD-017)` and nothing else in the string changed. (Tasks 1-2; `git diff` shows a one-token change per line)
- [ ] Given the test suite, when it runs, then every test asserting one of these strings asserts the new text, each change carries a comment citing PRD-016 D14, and the full suite is green. (Tasks 3-6, 8)
- [ ] Given a search of `app/` for string literals containing `(PRD-016)`, when run after the story, then it finds none; code comments mentioning PRD-016 are left unchanged. (Task 8 grep)
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns
