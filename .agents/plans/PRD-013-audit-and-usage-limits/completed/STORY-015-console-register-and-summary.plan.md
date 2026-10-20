---
story: STORY-015
prd: PRD-013
slug: console-register-and-summary
title: "Admin console: Register fields, verdict, search and summary figures"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-013-audit-and-usage-limits   # all stories commit here, no per-story branch
created: 2026-10-19
---

# Plan: Admin console: Register fields, verdict, search and summary figures

## Summary

This story puts STORY-005/006/011's audit fields on the admin console. It adds no column and no visual direction. **Register:** the tokens cell shows `2,140 / 312` when the row recorded a split, the total when it did not, and the absent mark when it recorded neither. The disclosure gains six labelled facts: Usage limit, Conversation, Ingress, Messages, Streamed and Tool calls. The free-text search also matches `conversation_key` and `ingress`, so pasting a key isolates one conversation. `derive_verdict` gains one line, `limit_exceeded` → **denied**. **Summary:** the three figures STORY-006 already reads and commits (`input_tokens`, `output_tokens`, `blocked_usage_limits`) are rendered. The usage-limit count joins the two blocked counts indented under the total, with a share. The two token totals get their own ruled block with a scope line that says what the sum covers. Everything is pre-formatted in Python: `to_audit_row` builds the strings and `AdminState` builds the figures. Components only read fields. `load()` is not changed. Its fault arm already names any of the thirteen reads by its own `READ_LABEL_*` and leaves the last good record on screen. This story proves that for the three new figures.

## User Story

As a compliance admin
I want the Register and summary to show the new audit fields and to find a conversation by its key
So that I can read an agent's work as one thing and see what was refused for usage

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-015-console-register-and-summary.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md` (Sections 6.2, 6.3, 6.10, 7 F15, 11 Surfaces, 14 Risk 6)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/` (admin_formatting, admin_models, admin_copy, admin_state, components/register, components/summary), tests |
| Story | STORY-015 |
| PRD | PRD-013 |
| Depends on | STORY-006 (✅ `eb77e8a`), STORY-011 (✅ `8dc6b4d`) |
| Blocks | STORY-016, STORY-018 |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch) |

No `app/` file changes. `AuditLog` already carries all eight fields (`app/db/models.py:384-391`), and `_row_to_audit_log` maps them (`app/db/database.py:927-930`, with the flags as `bool(...)`). `summary_snapshot()` already returns all thirteen figures, and `load()` already commits them by name (`admin_state.py:1095-1135`).

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `frontend-design` | *"Structure is information. Structural devices, numbering, eyebrows, dividers, labels, should encode something true about the content, not decorate it."* The usage-limit count is a subset of the total, so it is indented with the other two blocked counts. The token totals are not counts of queries, so they get their own ruled block instead of sitting with Traffic. The Register gains no column. The `/` in the tokens cell is the split itself. | Task 4, Task 6, Task 7 |
| `frontend-design` | *"Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built."* The labels are "Ingress", "Messages", "Conversation", "Usage limit", "Streamed" and "Tool calls". They are not the column names `message_count`, `conversation_key`, `limit_exceeded` or `has_tool_calls`. | Task 3 |
| `frontend-design` | *"Spend your boldness in one place… keep everything around it quiet."* PRD 6.10 forbids a new visual direction. The work reuses `_detail_field`, `_figure`, `_indented_figure` and `_block`. It adds no colour, fill, chart or motion. `test_summary.py`'s colour, tint and card guards must stay green unchanged. | Task 6, Task 7 |
| `frontend-design` | *"Let each element do exactly one job. A label labels, an example demonstrates."* The tokens head keeps its one word. The order (input / output) is stated once in the head cell's `title`, not repeated on every row. | Task 6 |
| `frontend-design` | Quality floor: *"responsive down to mobile"*. The tokens track widens and `_MIN_WIDTH` grows by the same amount, so the table keeps scrolling sideways in its own container instead of crushing. | Task 6, E2E |

---

## Design Decisions

**D-A: the tokens cell keeps the field name `tokens_used`, and its content changes.** `AuditRow.tokens_used` is "the tokens cell" in every test and in `_row_line`. The rules, in order:
1. Both `input_tokens` and `output_tokens` are non-`None`: `f"{format_count(i)} / {format_count(o)}"`.
2. `tokens_used` is non-`None`: `format_count(tokens_used)`.
3. Otherwise: `VALUE_ABSENT`.

A half split (one side `None`) falls to rule 2. The PRD has the client set both or neither, and showing one side would imply the other was 0. The total now uses `format_count`, so values of 1,000 or more get the thousands separator the split uses. Two formats in one column would read as two kinds of value. The existing assertions (`"412"`, `"0"`, `VALUE_ABSENT`) are all under 1,000 and keep passing unmodified. The separator `TOKENS_SPLIT_SEPARATOR = " / "` is a format constant in `admin_formatting.py`, beside `DEVICE_ELLIPSIS`, not copy.

**D-B: all six disclosure fields are plain `str`, including the two flags.** The story says "plain pre-formatted string fields". `streamed` and `has_tool_calls` go through a new `_flag(value: Optional[bool]) -> str`. `True` becomes `admin_copy.DETAIL_FLAG_YES_LABEL` ("yes"), `False` becomes `DETAIL_FLAG_NO_LABEL` ("no"), and `None` becomes `VALUE_ABSENT`. The `None` arm cannot come from the mapper today (`bool(row[...])`, NOT NULL DEFAULT 0). It exists so a hand-built `AuditLog(streamed=None)` cannot render "no", which would be a false claim. This adds one import, `admin_formatting` → `admin_copy`. `admin_copy` imports nothing, so no cycle is possible. `message_count` uses `format_count`, and the other three use `_text`.

**D-C: disclosure order is evidence-first, the existing rule (`register.py:_detail` docstring).** A usage-limit row is opened to read its limit, so **Usage limit** goes directly under Pattern action, with the other "why was this not cleared" lines. Next comes the hash, then **Conversation** right under it, because both are hashes that identify what was sent. Then **Ingress**, **Messages**, **Streamed** and **Tool calls**, which describe the request. Then User agent, Profile and the PII lines, unchanged. Profile stays directly above the PII lines (`test_the_profile_precedes_the_pii_lines`).

**D-D: `derive_verdict` gets one line after the pattern line and before `if not log.success`.** The story says "after `was_duplicate_blocked` and before the `success` check". The pattern line also sits there, and both arms return **denied**, so their order relative to each other cannot change a verdict. Putting it after the pattern line keeps the existing four lines byte-identical, so `test_admin_formatting.py`'s verdict tests pass unmodified. The test is `if log.limit_exceeded is not None` and not truthiness, matching `_BLOCKED_USAGE_LIMITS_WHERE = "limit_exceeded IS NOT NULL"` (`app/db/database.py:1118`). The console and `/stats` then agree on which rows count. The precedence comment above the constants gains the line `limit_exceeded -> denied (PRD-013 D6)`. The PRD's note that a permission refusal reads **cleared** is left alone and noted in the comment as out of scope.

**D-E: the summary layout.**

```
TRAFFIC
  Queries recorded                         3,180
      Held as duplicates                     412   13.0% of all queries
      Denied on a pattern                     37    1.2% of all queries
      Denied at a usage limit                  9    0.3% of all queries   ← new, indented
  Completed without error (…)              3,100
  (note)
TOKENS                                                                   ← new block
  Input tokens                         1,204,331
  Output tokens                          188,020
WHO AND WHAT
  …
PERSONAL DATA
  …
```

- `blocked_figures` gains a third entry. A usage-limit row is `success=1` and one row of `audit_logs`, so it is a subset of the total, which is what the indent claims. Its label is "Denied at a usage limit", the verdict word the Register shows for these rows, next to "Denied on a pattern".
- New computed var `token_figures` with two `_count_figure`s and no share. A share of a token sum over a query count is meaningless, and `_figure_value` already omits an empty share.
- `_count_figure` gains a keyword `scope: str = SUMMARY_SCOPE_ALL_TIME`, so every existing call site is unchanged. The token figures pass `SUMMARY_SCOPE_TOKENS = "All time, rows that recorded an input and output split"`. "Every recorded row" would be false: pre-PRD rows and upstream-error rows count as 0 (PRD 6.10, "`NULL` as 0").
- Block order is Traffic, Tokens, Who and what, Personal data. Tokens measure the same traffic in another unit, so they follow it directly.

**D-F: copy must not say "refused".** `tests/test_admin_copy.py::test_exactly_one_refusal_constant_exists` allows only `GATE_REFUSED_MESSAGE` to contain `refus`. STORY-006 already worded `READ_LABEL_USAGE_LIMITS = "the usage-limit blocks"` for this reason (`admin_copy.py:174-182`). Every new string here uses "denied" or "limit" instead. The AC's word "refusal" describes the figure, not its label.

**D-G: AC 5 ("names that figure and leaves the others rendered") is met by the existing `load()` contract, with no change to `load()`.** When one figure fails to decode, `summary_snapshot()` puts that figure in `errors` and the rest in `figures`. `load()` walks `_READS` in order and sets `error = LOAD_FAILED_MESSAGE.format(read=<that figure's READ_LABEL>, …)`. It commits nothing, so the previous figures stay on screen. `summary_state` returns `read_failed`, and `_sheet_body`'s fault arm renders **the sheet**, not a panel (`summary.py:421-427`). The existing tests pin that "Nothing on screen has changed" promise (`test_a_figure_that_failed_to_decode_is_named_by_its_own_label`). Committing the other twelve and blanking only the failed one would break those tests and the promise in `FAULT_MESSAGE_TEMPLATE`. Task 5 adds a parametrized test over the three new fields instead. Each failure is named by its own label, the loaded record is unchanged, and the sheet still renders every figure label. STORY-016's usage table is a separate read with its own label (F16). This story does not touch it.

**D-H: search reads two more fields, still in memory.** `_matches` adds `row.conversation_key.casefold()` and `row.ingress.casefold()` to its tuple. `filter_rows` is unchanged, and `visible_rows` still performs no database read. The existing `test_evaluating_visible_rows_performs_no_database_read` covers that, and Task 5 extends the fixture. The placeholder becomes `"user, model, id, ingress or conversation"` so the field states what it matches.

---

## Patterns to Follow

### Naming / projection (one named field per value, no `__dict__` copy)
```python
# SOURCE: chat_ui/chat_ui/admin_formatting.py:202-224
    return AuditRow(
        ...
        pattern_role=_text(log.pattern_role),
        pattern_action=_text(log.pattern_action),
        profile=_text(log.profile),
    )
```

### Verdict precedence
```python
# SOURCE: chat_ui/chat_ui/admin_formatting.py:85-97
    if log.was_duplicate_blocked:
        return VERDICT_HELD
    if log.suspicious_pattern is not None and log.pattern_action != "flag":
        return VERDICT_DENIED
    if not log.success:
        return VERDICT_FAULT
    return VERDICT_CLEARED
```

### Disclosure field (the PRD-012 `profile` precedent)
```python
# SOURCE: chat_ui/chat_ui/components/register.py:441-443
            # PRD-012 D9: directly above the PII lines it qualifies -- under
            # `code`, no output PII means the response was not analyzed.
            _detail_field(admin_copy.DETAIL_PROFILE_LABEL, row.profile),
```

### Summary figure built in state, read by the component
```python
# SOURCE: chat_ui/chat_ui/admin_state.py:762-781 (blocked_figures)
        return [
            _count_figure(
                FIGURE_BLOCKED_DUPLICATES_LABEL,
                self.blocked_duplicates,
                _share_line(self.blocked_duplicates, self.total_recorded),
            ),
            ...
        ]
```

### Error handling (fault names the read, commits nothing)
```python
# SOURCE: chat_ui/chat_ui/admin_state.py:1095-1111
            for field, label, _read, _kwargs in _READS:
                if field in snapshot.errors:
                    async with self:
                        self.error = LOAD_FAILED_MESSAGE.format(
                            read=label, detail=snapshot.errors[field]
                        )
                    return
```

### Tests
```python
# SOURCE: tests/test_admin_formatting.py:170-178 (profile reaches the row), 41-58 (make_log)
# SOURCE: tests/test_admin_state.py:847-875 (_fixed_snapshot + one figure in errors)
# SOURCE: tests/test_register.py:703-714 (disclosure order by index in the rendered output)
# SOURCE: tests/test_summary.py:265-316 (every figure var reaches the sheet; only blocked figures indent)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/admin_models.py` | UPDATE | `AuditRow` + 6 `str` fields: `ingress`, `message_count`, `conversation_key`, `streamed`, `has_tool_calls`, `limit_exceeded` |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | `derive_verdict` limit line + precedence comment; `TOKENS_SPLIT_SEPARATOR`; `_format_tokens`; `_flag`; `to_audit_row` populates the 6 fields |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | 6 `DETAIL_*_LABEL`s, 2 flag words, `COLUMN_TOKENS_TITLE`, `FILTER_SEARCH_PLACEHOLDER`, `SUMMARY_TOKENS_HEADING`, `SUMMARY_SCOPE_TOKENS`, 3 `FIGURE_*_LABEL`s; "nine figures" comments → twelve |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | `_matches` + 2 fields; `_count_figure(scope=…)`; `blocked_figures` + 1; new `token_figures` var; docstrings |
| `chat_ui/chat_ui/components/register.py` | UPDATE | 6 disclosure lines; tokens track 5rem → 7rem, `_MIN_WIDTH` 61.25rem → 63.25rem; tokens head `title`; search docstring |
| `chat_ui/chat_ui/components/summary.py` | UPDATE | Tokens block in `_sheet`; docstrings "nine" → "twelve" |
| `tests/test_admin_models.py` | UPDATE | `AUDIT_ROW_FIELDS` + 6; types test asserts the 6 are `str` |
| `tests/test_admin_formatting.py` | UPDATE (extend only) | Tokens cell three ways, the 6 fields, absent marks, limit → denied, precedence with a duplicate |
| `tests/test_admin_state.py` | UPDATE | Search by key/ingress; summary figure inventory 9 → 12; blocked trio; token scope; AC 5 fault per new figure |
| `tests/test_register.py` | UPDATE | `DETAIL_LABELS`/`DETAIL_ROW_FIELDS` + 6; order test; tokens head title |
| `tests/test_summary.py` | UPDATE | `FIGURE_VARS` + `token_figures`; `COPY_NAMES` + `SUMMARY_TOKENS_HEADING`; four headings |

---

## Tasks

Execute in order. Each task is atomic and verifiable. `PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe`, run from the repo root. Start the libSQL container first (`docker start harness-libsql-dev`).

### Task 0: Inventory before editing

- **Action**: READ only
- **Implement**: Run `grep -rn -E "nine|NINE|== 9\b|_two_that_indent|blocked_figures|DETAIL_LABELS|DETAIL_ROW_FIELDS|AUDIT_ROW_FIELDS|FIGURE_VARS|COPY_NAMES|FILTER_SEARCH_PLACEHOLDER|_MIN_WIDTH|_GRID" tests/` and reconcile the hits against the test tasks below. Known hits that must move, extended and never weakened:
  - `test_admin_state.py:2091` `_NINE_FIGURE_LABELS` and the `len == 9` assertions at `:2132` and `:2263`. They become twelve. Rename the set to `_FIGURE_LABELS`.
  - `test_admin_state.py:2162` `test_the_blocked_figures_are_the_two_that_indent`. It becomes `…_three_that_indent`.
  - `test_admin_state.py:2146` unpacks `duplicates, suspicious = state.blocked_figures`. It gains `usage`.
  - `test_admin_state.py:2136-2143` asserts every figure's scope `== SUMMARY_SCOPE_ALL_TIME`. It must exempt exactly the two token figures and assert `SUMMARY_SCOPE_TOKENS` on them.
  - `test_admin_state.py:2267` asserts the blocked shares on a zero total. Add the third.
  - `test_register.py:124-153` and `test_summary.py:57-75` inventories.

  Every `derive_verdict` test in `test_admin_formatting.py:60-148` stays byte-identical (AC 4).
- **Validate**: `$PY -m pytest tests/test_admin_formatting.py tests/test_admin_models.py tests/test_admin_state.py tests/test_register.py tests/test_summary.py tests/test_admin_copy.py -q` is green before any edit. Record the count.

### Task 1: `AuditRow` gains six fields

- **File**: `chat_ui/chat_ui/admin_models.py`
- **Action**: UPDATE
- **Implement**: After `profile` (line 285), add a commented group: `# PRD-013 (STORY-015): disclosure-only, pre-formatted; the absent mark on every pre-PRD-013 row.` Then `ingress: str = ""`, `message_count: str = ""`, `conversation_key: str = ""`, `streamed: str = ""`, `has_tool_calls: str = ""`, `limit_exceeded: str = ""`. Add no preview field. Extend the module docstring by one sentence noting `tokens_used` is now "input / output or the total" (D-A).
- **Mirror**: `admin_models.py:278-285`
- **Validate**: update `tests/test_admin_models.py` first. Add the six to `AUDIT_ROW_FIELDS` with a `# PRD-013 (STORY-015)` comment, add the six to the `str` check in `test_audit_row_types`, and add them to the field-population test at `:125-164`. Then `$PY -m pytest tests/test_admin_models.py -q`. `test_audit_row_has_no_preview_fields` must pass untouched (AC 2).

### Task 2: Formatting: verdict line, tokens cell, six fields

- **File**: `chat_ui/chat_ui/admin_formatting.py`
- **Action**: UPDATE
- **Implement**:
  - Precedence comment (`:32-39`): insert `#     limit_exceeded          -> denied  (PRD-013 D6: a usage-limit refusal, success=1)` after the pattern line. Add one line noting that a permission refusal still reads cleared, as recorded in the PRD-013 Evidence, and is not changed here.
  - `derive_verdict`: after the pattern `if` (`:93-94`), add a two-line comment and `if log.limit_exceeded is not None: return VERDICT_DENIED` (D-D). Docstring unchanged except one sentence naming the new arm.
  - `TOKENS_SPLIT_SEPARATOR = " / "` beside `DEVICE_ELLIPSIS`, with a comment saying it is the split itself and that the order (input first) is stated once by `COLUMN_TOKENS_TITLE`.
  - `_format_tokens(log) -> str`, implementing D-A's three rules. It replaces the inline expression at `:209-211`. Keep the "0 is a recorded fact" comment.
  - `_flag(value: Optional[bool]) -> str` (D-B). Import `DETAIL_FLAG_YES_LABEL`, `DETAIL_FLAG_NO_LABEL` from `.admin_copy`. Update the `format_count` docstring's "the summary's nine figures" to name the tokens cell as a third caller.
  - `to_audit_row`: `ingress=_text(log.ingress)`, `message_count=format_count(log.message_count)`, `conversation_key=_text(log.conversation_key)`, `streamed=_flag(log.streamed)`, `has_tool_calls=_flag(log.has_tool_calls)`, `limit_exceeded=_text(log.limit_exceeded)`. Neither preview is read.
- **Mirror**: `admin_formatting.py:85-97`, `:133-137`, `:202-224`
- **Validate**: Task 2b.

### Task 2b: Formatting tests (extend only)

- **File**: `tests/test_admin_formatting.py`
- **Action**: UPDATE (append; no existing assertion edited)
- **Implement**:
  1. `test_tokens_cell_reads_input_slash_output_when_split`: `make_log(input_tokens=2140, output_tokens=312, tokens_used=2452)` gives `"2,140 / 312"`.
  2. `test_tokens_cell_falls_back_to_the_total`: `input_tokens=None, output_tokens=None, tokens_used=2452` gives `"2,452"`. Half split `input_tokens=10, output_tokens=None, tokens_used=12` gives `"12"`.
  3. `test_tokens_cell_absent_when_neither`: all three `None` gives `VALUE_ABSENT`. Also `input_tokens=0, output_tokens=0` gives `"0 / 0"`, because 0 is a fact.
  4. `test_to_audit_row_carries_the_audit_fields`: `ingress="v1", message_count=1234, conversation_key="ab"*32, streamed=False, has_tool_calls=True, limit_exceeded="tokens"` gives `"v1"`, `"1,234"`, the key, `DETAIL_FLAG_NO_LABEL`, `DETAIL_FLAG_YES_LABEL`, `"tokens"`.
  5. `test_pre_prd013_row_shows_the_absent_mark`: `make_log()` with defaults (the five nullable fields `None`) gives `VALUE_ABSENT` on `ingress`, `message_count`, `conversation_key`, `limit_exceeded`. The flags read `DETAIL_FLAG_NO_LABEL`, and `_flag(None) == VALUE_ABSENT`.
  6. `test_a_usage_limit_row_is_denied`: `make_log(limit_exceeded="requests")` gives `VERDICT_DENIED`. The same for `"tokens"`.
  7. `test_a_duplicate_still_outranks_a_usage_limit`: `was_duplicate_blocked=True, limit_exceeded="tokens"` gives `VERDICT_HELD`. `limit_exceeded="tokens", success=False` gives `VERDICT_DENIED` (before the success check).
  8. `test_a_flag_row_with_no_limit_is_still_cleared`: guards against the new line widening, since `limit_exceeded=None` must not change any existing verdict.
  9. Extend `test_to_audit_row_carries_no_preview_value`'s sentinel check over the six new fields by iterating `AuditRow.model_fields`, if it doesn't already. Read the test first. If it already iterates, leave it alone.
- **Validate**: `$PY -m pytest tests/test_admin_formatting.py tests/test_admin_models.py -q`. Then `git diff --stat tests/test_admin_formatting.py` shows only additions (`git diff tests/test_admin_formatting.py | grep '^-[^-]'` is empty), which proves AC 4's "unmodified".

### Task 3: Copy

- **File**: `chat_ui/chat_ui/admin_copy.py`
- **Action**: UPDATE
- **Implement** (none may contain `refus`, D-F):
  - Under the PRD-012 profile label (`:290`): a `# PRD-013 (STORY-015)` comment block, then `DETAIL_LIMIT_LABEL = "Usage limit"`, `DETAIL_CONVERSATION_LABEL = "Conversation"`, `DETAIL_INGRESS_LABEL = "Ingress"`, `DETAIL_MESSAGE_COUNT_LABEL = "Messages"`, `DETAIL_STREAMED_LABEL = "Streamed"`, `DETAIL_TOOL_CALLS_LABEL = "Tool calls"`, `DETAIL_FLAG_YES_LABEL = "yes"`, `DETAIL_FLAG_NO_LABEL = "no"`. Comment: the values are shown as recorded (`query`/`chat`/`v1`, `requests`/`tokens`), like `DETAIL_PATTERN_ACTION_LABEL`; a flag's "no" is a recorded fact, as with `DETAIL_PII_ABSENT_LABEL`.
  - Beside `COLUMN_TOKENS` (`:93`): `COLUMN_TOKENS_TITLE = "Input / output tokens, or the total where no split was recorded"`.
  - `FILTER_SEARCH_PLACEHOLDER = "user, model, id, ingress or conversation"` (D-H).
  - Summary: `SUMMARY_TOKENS_HEADING = "Tokens"` after `SUMMARY_COUNTS_HEADING`; `FIGURE_BLOCKED_USAGE_LIMITS_LABEL = "Denied at a usage limit"` after `FIGURE_BLOCKED_SUSPICIOUS_LABEL`; `FIGURE_INPUT_TOKENS_LABEL = "Input tokens"`, `FIGURE_OUTPUT_TOKENS_LABEL = "Output tokens"`; `SUMMARY_SCOPE_TOKENS = "All time, rows that recorded an input and output split"` beside `SUMMARY_SCOPE_ALL_TIME`, with a comment on why it is not "every recorded row" (D-E).
  - Update the STORY-006 comment over the `READ_LABEL_*` trio (`:174-176`). It says "nothing renders the figures until STORY-015", and the figures now render. Change "nine" in the empty-summary comment (`:200`) to "twelve".
- **Validate**: `$PY -m pytest tests/test_admin_copy.py -q`. The single-refusal and non-empty sweeps pick up the new constants automatically.

### Task 4: State: search, figures

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**:
  - `_matches` (`:355-381`): add `row.conversation_key.casefold()` and `row.ingress.casefold()` to the tuple. Docstring: one paragraph naming PRD-013 6.10 ("pasting a key shows a conversation"), and noting the match is still against the loaded window with no database read. Update the `filter_rows` docstring's "three fields" to five.
  - `_count_figure(label, count, share="", *, scope=SUMMARY_SCOPE_ALL_TIME)`: docstring says the default is what keeps every existing figure's scope unchanged. A figure only passes another scope when "all time, every row" would be false.
  - `blocked_figures`: append `_count_figure(FIGURE_BLOCKED_USAGE_LIMITS_LABEL, self.blocked_usage_limits, _share_line(self.blocked_usage_limits, self.total_recorded))`. Update the docstring from "two" to "three", ordered as `_READS` and `StatsResponse` order them.
  - New `@rx.var def token_figures(self) -> list[SummaryFigure]`, placed after `completion_figure`, with `self.input_tokens`/`self.output_tokens` read in the body (auto-dependency rule). Two `_count_figure`s with `scope=SUMMARY_SCOPE_TOKENS` and no share. The docstring states D-E's reason for having no share and its own block.
  - The `# --- The summary sheet` comment block (`:740-755`): "Five vars" becomes six, and add the Tokens block to the structure it describes. The `_READS` STORY-006 comment (`:148-150`, "rendering them is STORY-015") becomes past tense.
  - Do **not** touch `load()`, `sign_out()` or `_READS` (D-G). No new declared var. `token_figures` is computed, so `test_sign_out_clears_every_declared_var` is unaffected.
- **Mirror**: `admin_state.py:762-781`, `:784-806`
- **Validate**: `$PY -c "import sys; sys.path.insert(0,'.'); import chat_ui.chat_ui.admin_state"` imports cleanly. Then Task 5.

### Task 5: State tests

- **File**: `tests/test_admin_state.py`
- **Action**: UPDATE
- **Implement**:
  1. **AC 3, search.** Give two rows of the `_FILTER_ROWS` fixture a `conversation_key` (one shared key across rows 127 and 129, one other on 128) and `ingress` values `v1`/`chat`/`query`. Keep model and user values free of the words `chat`, `query` and `v1` so the expected sets are exact (see Risks). New parametrized test `test_free_text_matches_conversation_key_and_ingress`: the full key gives exactly the two rows sharing it. An upper-cased key gives the same. `"v1"` gives exactly the v1 rows. A key prefix (first 12 hex chars) gives the same two rows, because pasting part of a hash must still work. The existing `test_free_text_matches_user_model_and_id_case_insensitively` expectations must stay as they are. If adding fields to the fixture would change one, put the new fields on fresh fixture rows instead.
  2. **AC 3, no read.** Extend `test_evaluating_visible_rows_performs_no_database_read` by setting `state.search` to a conversation key before evaluating.
  3. **Inventory** (Task 0): `_FIGURE_LABELS` gains the three new labels, and `len == 12` in both places. `_figures(state)` adds `*state.token_figures` after `completion_figure`, in render order. `_SUMMARY_COUNTS` gains `input_tokens=1204331`, `output_tokens=188020`, `blocked_usage_limits=9`.
  4. `test_every_figure_states_its_scope`: the token figures carry `SUMMARY_SCOPE_TOKENS`, and every other figure `SUMMARY_SCOPE_ALL_TIME`.
  5. `test_the_blocked_figures_are_a_count_and_a_share`: unpack three, and assert the usage figure's value is `format_count(9)` with share `SHARE_TEMPLATE.format(share=format_share(9, 3180))`.
  6. `test_the_blocked_figures_are_the_three_that_indent`: three labels, in order.
  7. New `test_the_token_figures_are_thousands_separated_and_unshared`: values `"1,204,331"` and `"188,020"`, both `share == ""`.
  8. Zero-total test (`:2252-2272`): the third blocked share is `SHARE_UNDEFINED`, and the token figures read `"0"`, not the absent mark.
  9. **AC 5.** New `test_a_failed_new_figure_is_named_and_the_sheet_stays_standing`, parametrized over `input_tokens`, `output_tokens`, `blocked_usage_limits`. Mirror `:847-875`: a good load, then `_fixed_snapshot` with that one figure popped into `errors`. Assert `_label_for(field) in state.error`, that no *other* `READ_LABEL_*` is in the error, `_loaded_record(state) == before`, `state.summary_state == SUMMARY_STATE_FAULT`, and that `_figures(state)` still yields all twelve labels with the last good values.
- **Validate**: `$PY -m pytest tests/test_admin_state.py -q`

### Task 6: Register component

- **File**: `chat_ui/chat_ui/components/register.py`
- **Action**: UPDATE
- **Implement**:
  - `_GRID` (`:116-119`): the tokens track (6th, `5rem`) becomes `7rem`, which fits `"999,999 / 99,999"` at `TEXT_DATA` in the data face. `_MIN_WIDTH` grows by the same 2rem: `"61.25rem"` → `"63.25rem"`, with the comment updated to say why. `_cell` still truncates beyond that, which is the existing rule.
  - `_head_cell` (`:127-144`) gains a keyword `title: str = ""`. It already sets `custom_attrs={"role": "columnheader"}`, so merge `title` into that dict only when non-empty. A `**props` passthrough would collide with the existing `custom_attrs`. `_column_head` passes `title=admin_copy.COLUMN_TOKENS_TITLE` on the tokens head. The head text stays `COLUMN_TOKENS`.
  - `_detail` (`:430-470`), D-C order: after `DETAIL_PATTERN_ACTION_LABEL`, add `_detail_field(admin_copy.DETAIL_LIMIT_LABEL, row.limit_exceeded)`. After `DETAIL_PROMPT_HASH_LABEL`, add the Conversation, Ingress, Messages, Streamed and Tool calls lines, each `_detail_field(label, row.<field>)`. There is no `rx.cond`, because all six are pre-formatted strings (D-B). Update the docstring's list of fields `_text` already filled. Add a `# PRD-013 (STORY-015)` comment on each group.
  - `_row_line` docstring: add the six to the disclosure-only list. The row stays at ten children (AC: no new column).
  - `_search_field` docstring: "`user_id` / `model_used` / `audit_id`" becomes all five, with one sentence on the conversation-key paste.
- **Mirror**: `register.py:430-443`, `:546-560`
- **Validate**: Task 6b.

### Task 6b: Register tests

- **File**: `tests/test_register.py`
- **Action**: UPDATE
- **Implement**: `DETAIL_LABELS` and `DETAIL_ROW_FIELDS` gain the six (D-C order) with `# PRD-013 (STORY-015)` comments. The stub row class around `:600-625` gains the six attributes. New `test_the_usage_limit_follows_the_pattern_lines_and_the_conversation_follows_the_hash` asserts the index order in the rendered detail, mirroring `:703-714`. The existing profile-before-PII test must still pass. New `test_the_row_gains_no_column`: `_row_line`'s source still has exactly ten grid children (count `_cell(`/`_verdict_tag(`/`_stamp_margin(`/`_time_cell(`/`rx.cond(`/`_disclosure_toggle(` the way the existing grid test reads source), and none of the six field names appears in `_row_line`'s body. New `test_the_tokens_head_states_the_split_order`: `COLUMN_TOKENS_TITLE` is in the rendered head.
- **Validate**: `$PY -m pytest tests/test_register.py -q`

### Task 7: Summary component

- **File**: `chat_ui/chat_ui/components/summary.py`
- **Action**: UPDATE
- **Implement**: In `_sheet`, insert `_block(admin_copy.SUMMARY_TOKENS_HEADING, rx.foreach(AdminState.token_figures, _figure))` between the Traffic and Who blocks. It is not indented, because tokens are not a subset of anything on the sheet. The `blocked_figures` foreach already renders the third figure indented, so no change there. Docstrings: "nine figures" becomes "twelve" and "three blocks" becomes "four". In the module docstring's indentation paragraph, add `blocked_usage_limits` to the indented subset. `_sheet`'s docstring explains why Tokens follows Traffic (D-E).
- **Mirror**: `summary.py:386-403`
- **Validate**: Task 7b.

### Task 7b: Summary tests

- **File**: `tests/test_summary.py`
- **Action**: UPDATE
- **Implement**: `FIGURE_VARS` gains `"token_figures"`. `COPY_NAMES` gains `"SUMMARY_TOKENS_HEADING"`. `test_the_three_blocks_are_headed` → `test_the_four_blocks_are_headed`. Change "nine" in comments. `test_only_the_blocked_figures_are_indented` must still pass, and it now also proves the token figures are not indented. All colour, tint, card and literal guards (`:383-516`) must pass unchanged.
- **Validate**: `$PY -m pytest tests/test_summary.py -q`

### Task 8: Full suite and the regression gates

- **Action**: RUN
- **Validate**: `$PY -m pytest tests/ -q`. If fixture errors appear across the suite, restart the libSQL container rather than bisecting. `tests/test_chat_sessions.py` has a known intermittent flake (PRE-PRD-017), so rerun it before blaming the change. These must show no assertion changed: `git diff` on `test_admin_formatting.py` is additions only (AC 4), and `test_query_outcomes_regression.py`, `test_chat_outcomes_regression.py` and `test_untouched_app.py` are untouched by this story.

### Task 9: E2E in the running console (`frontend-design` quality floor)

- **Action**: RUN, see End-to-End Tests below. Revert `chat_ui/reflex.lock/package.json` and delete `chat_ui/package-lock.json` changes that `reflex run` produces before committing.

### Task 10: Commit, report, story status

- **Action**: Commit on `epic/PRD-013-audit-and-usage-limits` as `feat(admin-console): STORY-015 register fields, usage-limit verdict, search and summary figures`. Write the report like the earlier PRD-013 stories. Set the story's `report` and `commit`, set `status: done`, move this plan to `completed/`, and regenerate the index.

---

## End-to-End Tests

Seed through the real writer, because no live send can be answered here (OpenRouter TLS/401). From the repo root, with `.env` sourced, use `PYTHONPATH=. $PY` to call `app.db.database.insert_audit_log(AuditLog(user_id="e2e-story015", ...))` (`database.py:787`) and write four rows:
- (a) a success row with `input_tokens=2140, output_tokens=312, tokens_used=2452, ingress="v1", message_count=7, conversation_key=K`;
- (b) a second `v1` row with the same `K`;
- (c) a row with only `tokens_used=88` and no ingress (pre-PRD shape);
- (d) a usage-limit row with `success=True, limit_exceeded="tokens", ingress="chat"`.

Then `cd chat_ui && set -a; . ../.env; set +a; reflex.exe run --env prod`, open `http://localhost:3000/admin`, and sign in with `ADMIN_TOKEN`.

- [ ] Register: row (a)'s tokens cell reads `2,140 / 312` untruncated, row (c) reads `88`, row (d) reads `—`. Hovering the Tokens head shows the split-order title.
- [ ] Row (d) shows the **denied** stamp, and the verdict filter *denied* keeps it.
- [ ] Open row (a)'s disclosure: Usage limit `—`, Conversation `K` (wraps, not truncated), Ingress `v1`, Messages `7`, Streamed `no`, Tool calls `no`. Row (c)'s disclosure shows `—` for ingress, messages, conversation and limit. Row (d) shows Usage limit `tokens`.
- [ ] Paste `K` into Find: only rows (a) and (b) remain, and the filtered line reads "2 of N shown". Type `chat`: row (d) remains. Clear filters restores the window.
- [ ] Summary: Traffic shows "Denied at a usage limit" indented under the total with a share. A Tokens block shows Input and Output tokens with the "rows that recorded an input and output split" scope line. Values match `curl -H "Authorization: Bearer $ADMIN_TOKEN" localhost:8000/stats | jq '.input_tokens,.output_tokens,.blocked_usage_limits'`, or `summary_snapshot()` in-process if the API is not up.
- [ ] Narrow the window to 390px: the register scrolls sideways inside its container with no page scroll, and summary values wrap under their labels.
- [ ] Both themes: the new lines use only existing ink, so check legibility once.
- [ ] AC 5's failure arm is proved by Task 5 #9, not live. Injecting a decode failure into a running server is not worth a harness.

Clean up the four seeded rows afterwards (`DELETE FROM audit_logs WHERE user_id = 'e2e-story015'`, so seed them with that `user_id`).

---

## Validation

```bash
PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
docker start harness-libsql-dev
$PY -m pytest tests/test_admin_formatting.py tests/test_admin_models.py tests/test_admin_copy.py tests/test_admin_state.py tests/test_register.py tests/test_summary.py -q
$PY -m pytest tests/ -q
git diff tests/test_admin_formatting.py | grep '^-[^-]'   # must print nothing (AC 4)
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| Ingress words are substrings of user or model names (`chat` in a model id), so an ingress search keeps extra rows | Substring matching over all five fields is the register's existing behaviour, and AND-composition with the verdict filter narrows further. The test fixture keeps those words out of user and model values so AC 3's "only rows with that ingress" is asserted exactly. Noted in the `_matches` docstring. An ingress-only filter is Section 13 material |
| `format_count` on the total changes `1234` to `1,234` in the tokens cell | Intended (D-A). Every existing assertion is under 1,000. `/audit` and `/stats` are untouched |
| Widening the grid shifts the measured column alignment | One `_GRID` drives head and rows (`test_register.py:1302-1320`). `_MIN_WIDTH` moves by exactly the added 2rem |
| D-G reading of AC 5 is challenged ("leaves the others rendered" read as "commit the other twelve") | That would break `FAULT_MESSAGE_TEMPLATE`'s promise and four existing fault tests. The chosen reading keeps the last good sheet standing under a fault that names the figure. Flag it in the report so the reviewer can overrule it |
| A future `limit_exceeded` value that is not `requests`/`tokens` | The verdict tests `is not None`, the same predicate as `/stats`. The disclosure shows the stored value as recorded |
| Scope creep (PRD Risk 6) | No column, no chart, no new state var, no `load()` change. STORY-016 owns the Usage table |
