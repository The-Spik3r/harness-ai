---
story: STORY-003
prd: PRD-013
slug: split-token-counts
title: "OpenRouter client returns input and output tokens separately"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-013-audit-and-usage-limits        # all stories commit here, no per-story branch
created: 2026-10-12
---

# Plan: OpenRouter client returns input and output tokens separately

## Summary

`call_openrouter` starts returning the provider's prompt and completion token counts next to the total. Nothing reads them yet: `run_conversation` passes them on in STORY-005 and `charge` uses them in STORY-012.

- **Dataclass.** `OpenRouterResult` gains `input_tokens: Optional[int] = None` and `output_tokens: Optional[int] = None` after `tokens_used`.
- **Parsing.** After `total_tokens` is read exactly as today, `usage.prompt_tokens` and `usage.completion_tokens` are read with `.get` and passed through one private helper. The helper returns the value when it is a non-negative `int` that is not a `bool`, and `None` otherwise. It never raises.
- **Tests.** A new section in `tests/test_openrouter_client.py`, 23 cases. No existing test is edited in any file.

Two things in the story do not match the code, and neither blocks it:

- **AC 5 and PRD F3 say the suite's stubs build `OpenRouterResult` positionally. None does** (F-2). All 64 construction sites use the three keywords. They keep working either way. The plan adds one test that does construct positionally, so the guarantee the AC describes is covered by something.
- **`"usage": null` still escapes as an uncaught `TypeError`** (F-3). STORY-001's report left this story free to wrap it. The plan does not, because AC 4 says the missing-total behaviour stays "exactly as before" and the story lists no such change. It is recorded for the report.

## User Story

As a platform operator
I want the provider's prompt and completion token counts kept apart
So that cost can be read as input versus output and not only as a total

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-003-split-token-counts.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md` (Sections 4 *OpenRouter client*, 7/F3, 11 *Audit*)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (story type `feature`) |
| Complexity | LOW (story `small`) |
| Systems Affected | OpenRouter client (`app/services/openrouter_client.py`) and its test module |
| Story | STORY-003 |
| PRD | PRD-013 |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch; it is checked out, HEAD `cbf8278`) |
| Depends on | STORY-001 (done, `126f0da`) |
| Blocks | STORY-005, STORY-012 |

---

## Skills In Use

None. `.agents/skills/` holds one skill, `frontend-design`. The story sets `skills: []` and says "No UI surface changes in this story".

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

---

## Findings from Exploration

Read on `epic/PRD-013-audit-and-usage-limits` @ `cbf8278`. The working tree is clean.

### F-1: One place reads `usage`, one place builds the result

| Place | File:Lines | Today |
|---|---|---|
| `OpenRouterResult` | `app/services/openrouter_client.py:85-89` | `@dataclass`, three fields, no defaults |
| The `usage` read | `app/services/openrouter_client.py:148-153` | `data["usage"]["total_tokens"]`, with `KeyError`, `IndexError` and `ValueError` wrapped in `OpenRouterError` |
| The return | `app/services/openrouter_client.py:158` | three keywords |

`app/` constructs `OpenRouterResult` nowhere else. `prompt_tokens` and `completion_tokens` are read nowhere in `app/`.

### F-2: No stub constructs `OpenRouterResult` positionally

A search for `OpenRouterResult(` finds 64 sites outside the client: 62 in `tests/` and 2 in `scripts/`. Every one passes `response=`, `model_used=` and `tokens_used=` by keyword. AC 5 and PRD F3 describe them as positional.

**Consequence.** Appending two defaulted fields keeps all 64 working, keyword or positional. Since no existing test would notice if the new fields were declared before `tokens_used` or made keyword-only, Task 2 adds a test that builds the result with three positional arguments and one that pins the field order.

`scripts/spike_pii_placeholders.py:622` rebuilds a result from another with three keywords, which drops the split. It is a spike script and no production path uses it. Not changed.

### F-3: What the client does today with odd `usage` shapes (measured)

Run against the current code with a stub HTTP client:

| `usage` | Result today |
|---|---|
| `null`, `[]`, `"abc"`, `5` | uncaught `TypeError` |
| `{"total_tokens": "45"}` | succeeds, `tokens_used == "45"` |
| `{"total_tokens": null}` | succeeds, `tokens_used is None` |
| no `usage` key, `{}`, split without total | `OpenRouterError`, "unexpected response shape" (pinned by STORY-001) |

Two consequences for this story:

- **`.get` is safe after the total is read.** `resp.json()` yields only `dict`, `list`, `str`, numbers, `bool` and `None`. Of those, only a `dict` survives `usage["total_tokens"]`. So once the existing read succeeds, `usage` is a `dict` and `usage.get(...)` cannot raise. The new reads go after it and need no `try`.
- **`total_tokens` is not validated, and stays that way.** PRD F3: "`total_tokens` keeps today's strictness". The helper is applied to the two new fields only.

### F-4: The characterization module needs no edit

`tests/test_audit_characterization.py:648-680` pins that `tokens_used` is the reported total in three cases, including one where the split disagrees with it, and that a missing total raises. STORY-001's report (line 117): "The module asserts the three attribute values of `OpenRouterResult`, never its field list, so adding two fields does not touch it."

`_UNSET_THROUGH_DRIVE` (added by STORY-002) pins `input_tokens` and `output_tokens` as `None` on rows written through `_drive`. That still holds: `_drive`'s stub builds the result with three fields, and the pipeline does not pass the split until STORY-005.

`AuditLog` gains no field here, so `FIELDS_ADDED_SINCE` is not touched.

### F-5: The `bool` precedent the story names

`app/services/openrouter_client.py:47-52` rejects `bool` for `max_tokens` with an explicit `isinstance(..., bool)` check and a one-line comment. The helper uses the same check and the same comment style. The difference is the outcome: `GenerationParams` raises because the caller sent a bad value, and the helper returns `None` because a provider's odd `usage` must not fail a call that produced an answer.

### F-6: Environment

- Python: `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe`. There is no virtual environment in the repo.
- `harness-libsql-dev` was up when this plan was written. `tests/test_openrouter_client.py` does not use the database; `tests/test_audit_characterization.py` does.
- **Measured for this plan:** `pytest tests/test_openrouter_client.py tests/test_audit_characterization.py -q` gives 69 passed (30 + 39).
- **Not run for this plan:** the full suite. STORY-002's report gives 3391 passed, 27 skipped at `3c61b53`, with an occasional libSQL connection timeout in an unrelated test.

---

## Patterns to Follow

### Naming: the `bool` guard and its comment
```python
# SOURCE: app/services/openrouter_client.py:47-52
        if self.max_tokens is not None:
            # bool is a subclass of int: True/False must not slip past >= 1.
            if isinstance(self.max_tokens, bool) or self.max_tokens < 1:
                raise UnsupportedParameterError(
                    f"max_tokens must be an integer >= 1, got {self.max_tokens!r}"
                )
```

### Naming: optional dataclass fields with a trailing default
```python
# SOURCE: app/services/openrouter_client.py:37-40
    temperature: Optional[float] = None   # 0.0 <= t <= 2.0
    max_tokens: Optional[int] = None       # >= 1
```

### Error Handling: the one wrapped failure, which this story leaves as it is
```python
# SOURCE: app/services/openrouter_client.py:148-153
        try:
            tokens_used = data["usage"]["total_tokens"]
        except (KeyError, IndexError, ValueError) as exc:
            raise OpenRouterError(
                f"OpenRouter returned an unexpected response shape: {exc}"
            ) from exc
```

### Tests: a section header, a custom body, a parametrized table
```python
# SOURCE: tests/test_openrouter_client.py:227, 35-41, 242-255
# --- PRD-010 STORY-005: GenerationParams allowlist and range validation ---

def _response(content="Hello!", tokens=45, status_code=200, body=None):
    request = httpx.Request("POST", _API_URL)
    payload = body if body is not None else {
        "choices": [{"message": {"content": content}}],
        "usage": {"total_tokens": tokens},
    }
    return httpx.Response(status_code, request=request, json=payload)

@pytest.mark.parametrize(
    "kwargs",
    [
        {"temperature": 3},
        {"max_tokens": True},
    ],
)
def test_out_of_range_params_raise_naming_field_and_range(kwargs):
```

### Tests: `pytest.param(..., id=...)` for usage shapes
```python
# SOURCE: tests/test_audit_characterization.py:648-661
@pytest.mark.parametrize(
    "usage",
    [
        pytest.param(
            {"total_tokens": 45, "prompt_tokens": 30, "completion_tokens": 15}, id="with-split"
        ),
        pytest.param({"total_tokens": 45}, id="total-only"),
    ],
)
```

---

## Design

### D-1: The helper

A module-level private function, placed above `OpenRouterResult`:

```python
def _token_count(value: Any) -> Optional[int]:
    """A provider-reported token count, or None when it is not usable (PRD-013 F3)."""
    # bool is a subclass of int: True/False must not be recorded as 1/0.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
```

| Input | Output | Why |
|---|---|---|
| `120` | `120` | |
| `0` | `0` | Zero is a real count. It must not collapse to `None`, which means "not reported" |
| absent (`None` from `.get`) | `None` | AC 2 |
| `"120"`, `-1`, `True`, `False` | `None` | AC 3 |
| `120.0`, `[120]`, `{}` | `None` | PRD F3: "accepted only when they are non-negative integers". A float is not coerced |

### D-2: Each field is judged on its own

A bad `prompt_tokens` beside a good `completion_tokens` gives `input_tokens=None, output_tokens=30`. AC 3 says "that field is `None`", not "both". Whether a half split counts as "the split is present" for charging is STORY-010's decision (`charge` in PRD Section 9), and the report says so.

### D-3: The split is not reconciled with the total

`tokens_used` stays `usage["total_tokens"]` as reported, and the two new fields are reported as given even when they do not add up to it. STORY-001 pins the first half (`split-disagrees-with-total`). Task 2 adds a case for the second.

### D-4: Where the reads go

```python
        try:
            usage = data["usage"]
            tokens_used = usage["total_tokens"]
        except (KeyError, IndexError, ValueError) as exc:
            raise OpenRouterError(
                f"OpenRouter returned an unexpected response shape: {exc}"
            ) from exc
        # PRD-013 F3: optional, and never a reason to fail a call that answered.
        input_tokens = _token_count(usage.get("prompt_tokens"))
        output_tokens = _token_count(usage.get("completion_tokens"))
```

Binding `usage` inside the existing `try` raises the same exceptions from the same statements as today, so every case in F-3's table is unchanged.

### D-5: What is not done

- No change to `query_pipeline.py`, `log_query` or any caller. STORY-005 owns that.
- No validation of `total_tokens` and no `TypeError` in the `except` clause (F-3).
- No edit to `tests/test_audit_characterization.py` (F-4) or to any of the 64 stubs (F-2).
- `OpenRouterResult` stays a plain `@dataclass`, not frozen.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/openrouter_client.py` | UPDATE | `_token_count`; two fields on `OpenRouterResult`; two reads and two keywords in `call_openrouter` |
| `tests/test_openrouter_client.py` | UPDATE | New PRD-013 STORY-003 section, 23 cases, additions only |
| `.agents/stories/PRD-013-audit-and-usage-limits/STORY-003-split-token-counts.md` | UPDATE | Plan link and status (this command). Report and commit later (`/implement`) |
| `.agents/PRDs/PRD-013-audit-and-usage-limits/index.md` | UPDATE | Status and plan link (this command). Commit SHA later (`/implement`) |
| `.agents/reports/PRD-013-audit-and-usage-limits/STORY-003-split-token-counts.report.md` | CREATE (by `/implement`) | Task 5 |

---

## Tasks

Execute in order. Each task is atomic and verifiable. `python` below means `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe`.

### Task 0: Preflight

- **Action**: environment and branch only.
- **Implement**:
  1. Confirm the branch is `epic/PRD-013-audit-and-usage-limits` and `docker ps` lists `harness-libsql-dev`.
  2. Commit this plan and the story and index updates as `docs(PRD-013): STORY-003 plan`, so the story commit holds code and tests only (precedent: `d43055f`).
  3. Run the full suite once and record the counts and any failure names. STORY-002's figure was 3391 passed, 27 skipped.
- **Validate**: `python -m pytest -q`. A failure with `StorageError ... tcp connect error` in a test that passes alone is the known libSQL flakiness. On mass fixture errors, restart the container before looking at code (PRD Section 11).

### Task 1: The helper, the fields and the reads

- **File**: `app/services/openrouter_client.py`
- **Action**: UPDATE
- **Implement**:
  - Add `_token_count` (D-1) above `OpenRouterResult`. `Any` and `Optional` are already imported.
  - `OpenRouterResult` (lines 85-89): add the two fields after `tokens_used`, in the order `input_tokens`, `output_tokens`, under one comment: PRD-013 STORY-003; `usage.prompt_tokens` and `usage.completion_tokens`; `None` when the provider omitted or malformed the field; declared after `tokens_used` with defaults so three-argument construction keeps working.
  - `call_openrouter` (lines 148-158): the change of D-4, and `input_tokens=input_tokens, output_tokens=output_tokens` on the return.
  - Do not touch the `except` tuple, the error message, the payload or the headers.
- **Mirror**: `app/services/openrouter_client.py:37-40` and `:47-52`
- **Validate**:
  - `python -c "from app.services.openrouter_client import OpenRouterResult as R; print(R('r','m',3))"` prints `OpenRouterResult(response='r', model_used='m', tokens_used=3, input_tokens=None, output_tokens=None)`.
  - `python -m pytest tests/test_openrouter_client.py tests/test_audit_characterization.py -q` gives 69 passed, the figure measured before the change.

### Task 2: The PRD-013 STORY-003 section in `tests/test_openrouter_client.py`

- **File**: `tests/test_openrouter_client.py`
- **Action**: UPDATE (additions only, appended after line 343)
- **Implement**: a section headed `# --- PRD-013 STORY-003: the token split ---`. Add `OpenRouterResult` to the import at lines 12-17 and `import dataclasses` at the top. These two import lines are the only changes above the new section.
  - `_usage_call(usage) -> OpenRouterResult`: calls `call_openrouter` with `_FakeClient(response=_response(body={"choices": [{"message": {"content": "Hello!"}}], "usage": usage}))`.
  - `_UNUSABLE_COUNTS`: a list of eight `pytest.param` values with ids: `"120"` (`string`), `-1` (`negative`), `True` (`true`), `False` (`false`), `120.0` (`float`), `None` (`null`), `[120]` (`list`), `{}` (`object`).
  - **AC 1** `test_split_is_returned_beside_the_total()`: usage `{"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}`. Asserts `(result.input_tokens, result.output_tokens, result.tokens_used) == (120, 30, 150)`.
  - **AC 2** `test_total_only_succeeds_with_no_split()`: usage `{"total_tokens": 45}`. Asserts `input_tokens is None`, `output_tokens is None`, `tokens_used == 45` and `response == "Hello!"`.
  - **AC 3** `test_an_unusable_prompt_count_is_none_and_the_call_succeeds(value)`, parametrized over `_UNUSABLE_COUNTS` (×8): usage `{"prompt_tokens": value, "completion_tokens": 30, "total_tokens": 150}`. Asserts `input_tokens is None`, `output_tokens == 30` and `tokens_used == 150`.
  - **AC 3** `test_an_unusable_completion_count_is_none_and_the_call_succeeds(value)` (×8): the mirror, asserting `input_tokens == 120` and `output_tokens is None`.
  - `test_a_zero_count_is_kept_as_zero()`: usage `{"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}`. Asserts `result.input_tokens == 0 and result.input_tokens is not None`, and the same for `output_tokens`. A comment says why: zero is a count, `None` is "not reported".
  - `test_the_split_is_reported_as_given_when_it_disagrees_with_the_total()`: usage `{"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 45}`. Asserts `(100, 100, 45)` (D-3).
  - **AC 4** `test_a_split_without_a_total_still_raises()`: usage `{"prompt_tokens": 120, "completion_tokens": 30}`. Asserts `pytest.raises(OpenRouterError, match=r"^OpenRouter returned an unexpected response shape: ")`. The same pin lives in the characterization module; this one keeps the client's own module complete.
  - **AC 5** `test_three_positional_arguments_still_construct_a_result()`: `OpenRouterResult("r", "m", 3)` has `response == "r"`, `model_used == "m"`, `tokens_used == 3` and both new fields `None`. A second assertion builds it with the three keywords, the way the suite's stubs do, and checks equality with the first.
  - **AC 5** `test_the_split_fields_are_declared_last_and_in_order()`: `[f.name for f in dataclasses.fields(OpenRouterResult)] == ["response", "model_used", "tokens_used", "input_tokens", "output_tokens"]`.
- **Mirror**: `tests/test_openrouter_client.py:242-255`, `:300-316`; `tests/test_audit_characterization.py:648-680`
- **Validate**: `python -m pytest tests/test_openrouter_client.py -q` gives 53 passed (30 + 23). `git diff tests/test_openrouter_client.py` shows two import lines and additions.

### Task 3: Prove the tests bite

- **Action**: temporary edits only, each reverted before commit. Use a script that restores the file in a `finally` block, as STORY-001 and STORY-002 did.
- **Implement**: each change must fail the named tests.
  1. `call_openrouter`: swap `"prompt_tokens"` and `"completion_tokens"`. The AC 1 test fails, and so do both AC 3 tables.
  2. `_token_count`: drop `isinstance(value, bool) or`. The `true` and `false` cases fail in both AC 3 tables.
  3. `_token_count`: drop `or value < 0`. The `negative` cases fail.
  4. `_token_count`: replace the condition with `if not value:` followed by the `isinstance` checks, so `0` returns `None`. `test_a_zero_count_is_kept_as_zero` fails.
  5. `call_openrouter`: replace `usage.get("prompt_tokens")` with `usage["prompt_tokens"]`. The AC 2 test fails with `KeyError`, and the characterization module's `total-only` case fails too.
  6. `OpenRouterResult`: swap the two new declarations. `test_the_split_fields_are_declared_last_and_in_order` fails.
  7. `OpenRouterResult`: declare the two new fields with `field(default=None, kw_only=True)` and move them above `tokens_used`. `test_the_split_fields_are_declared_last_and_in_order` fails. This is the reordering that no existing stub would catch (F-2).
- **Validate**: `git status` shows only the two files of Tasks 1-2.

### Task 4: Full suite and commit

- **Implement**:
  - `python -m pytest -q`. Expected: the Task 0 pass count plus 23.
  - `git diff cbf8278 -- tests/test_audit_characterization.py` is empty (F-4).
  - `git diff --stat $(git merge-base HEAD main)..HEAD -- tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py tests/test_duplicate_scope.py tests/test_pii_characterization.py` is empty (PRD Section 11).
  - Commit: `feat(PRD-013): STORY-003 OpenRouter client returns the input and output token split`.
- **Validate**: any failing test is re-run in isolation and named in the report. A failure in a test that passes alone is recorded as flakiness, not ignored.

### Task 5: Report

- **File**: `.agents/reports/PRD-013-audit-and-usage-limits/STORY-003-split-token-counts.report.md` (written by `/implement`, in the shape of the STORY-002 report)
- **Must contain**:
  - **AC 5 as it was met:** no stub in the suite constructs positionally (F-2); the positional guarantee is covered by the two added tests.
  - The seven bite checks and what failed for each.
  - **For STORY-005:** `result.input_tokens` and `result.output_tokens` are ready to pass to `log_query` on the success and output-redaction-error arms. Stubs that build the result with three fields give `None` for both, which is why `_UNSET_THROUGH_DRIVE` still holds.
  - **For STORY-010 and STORY-012:** the two fields are independent, so one can be `None` while the other is set (D-2). `charge` must decide what "the split is present" means in that case. They are also not reconciled with `tokens_used` (D-3).
  - **Observation, not fixed:** `"usage": null` and any non-object `usage` still raise an uncaught `TypeError`, and `total_tokens` is still returned unvalidated, so a string or `null` total reaches the caller (F-3).

---

## End-to-End Tests

Nothing user-visible changes, and no caller reads the new fields yet. The checks are at the client boundary:

- [ ] `pytest tests/test_openrouter_client.py -q` gives 53 passed.
- [ ] `pytest tests/test_audit_characterization.py -q` gives 39 passed and the file has no diff against `cbf8278`.
- [ ] `python -c "from app.main import app"` imports.
- [ ] By hand, with a stub client returning `{"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}`: `call_openrouter` returns `input_tokens=120, output_tokens=30, tokens_used=150`.
- [ ] Start the API with a dummy key and the dev database, send one `POST /query` with `call_openrouter` unreachable or stubbed as the existing E2E setup does, and confirm the response body and the audit row have the same shape as before the story (`input_tokens` and `output_tokens` are still `NULL` on the row until STORY-005).
- [ ] All seven Task 3 bite checks fail as described and pass after revert.
- [ ] The full suite matches the Task 0 baseline plus 23.

---

## Validation

```bash
# libSQL dev server must be up for the characterization module and the full suite
PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
$PY -c "from app.main import app"
$PY -m pytest tests/test_openrouter_client.py -q
$PY -m pytest tests/test_openrouter_client.py tests/test_audit_characterization.py -q
$PY -m pytest -q
git diff cbf8278 -- tests/test_audit_characterization.py
```

There is no frontend lint: the UI is Reflex (Python) and this story does not touch it.

---

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| A malformed split fails a call that produced an answer | The helper has no raising path and is applied after the total is read. `.get` cannot raise there (F-3). The two AC 3 tables cover eight shapes per field |
| `True` is recorded as 1 token | The explicit `bool` check, mirrored from `GenerationParams`. Bite check 2 |
| `0` is turned into `None` by a truthiness shortcut | `test_a_zero_count_is_kept_as_zero`. Bite check 4 |
| The two keys are transposed, so input and output are swapped in every later story | The AC 1 test uses different values (120 and 30). Bite check 1 |
| The missing-total behaviour drifts while the `try` block is edited | D-4 keeps the same statements in the same `try`. STORY-001's three pinned cases and the added AC 4 test cover it. The characterization file must show no diff |
| A later edit reorders the dataclass and no stub notices, because none is positional | The two AC 5 tests. Bite checks 6 and 7 |
| A reader takes the story to cover non-object `usage` | F-3 and D-5 state that it does not. The report records it as an observation |
| libSQL flakiness hides a real failure in the full run | Every failing test is re-run in isolation and named in the report (Task 4) |

---

## Acceptance Criteria

(Copied from story `STORY-003`)

- [ ] Given a provider response whose `usage` has `prompt_tokens=120`, `completion_tokens=30`, `total_tokens=150`, when `call_openrouter` returns, then `OpenRouterResult` has `input_tokens=120`, `output_tokens=30` and `tokens_used=150`.
- [ ] Given a response whose `usage` has only `total_tokens`, when `call_openrouter` returns, then it succeeds with `input_tokens=None` and `output_tokens=None`.
- [ ] Given `prompt_tokens` that is a string, a negative number or a `bool`, when `call_openrouter` returns, then that field is `None` and no error is raised.
- [ ] Given a response with no `total_tokens`, when `call_openrouter` runs, then it raises `OpenRouterError` exactly as before (STORY-001's assertion unchanged).
- [ ] Given the existing suite's stubs that build `OpenRouterResult(response, model_used, tokens_used)` positionally, when the suite runs, then every one still constructs and passes. **Note:** the stubs use keywords, not positions (F-2). They are unedited and pass; positional construction is covered by an added test.
- [ ] All tasks completed
- [ ] Backend imports and the server starts without error
- [ ] Follows existing patterns (the `bool` guard and its comment, defaulted trailing fields, section header and parametrized table in the client's test module)
