---
story: STORY-012
prd: PRD-013
slug: charge-after-upstream
title: "Charge tokens after the upstream call; BYOK and counter-failure rules"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-013-audit-and-usage-limits
created: 2026-10-19
---

# Plan: Charge tokens after the upstream call; BYOK and counter-failure rules

## Summary

Add step 7b to `run_conversation`: one call to `usage_limits.charge(...)` placed right after the step 7 `try/except OpenRouterError` block and before step 8's output redaction. It runs only when the gate admitted the request (`admission is not None`, so `USAGE_LIMITS_ENABLED` was on at step 2c) and the request is not BYOK (`openrouter_api_key is None`). It charges the `admission.day` the gate returned. The work is mostly done already. STORY-010's `charge()` handles the split/unsplit choice and fails open, logging at `ERROR`. STORY-009's `charge_usage` is the single `UPDATE`. STORY-011 kept `admission` in a local for this purpose. What remains is the call site, the module binding (so tests can spy on it), the tests for each AC plus the documented overshoot, and one statement-count guard in the two-instance smoke test (four statements become five).

## User Story

As a platform operator
I want every token the provider reports charged to the user's day as soon as it is reported
So that the budget reflects real spend even when the response is then lost

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-012-charge-after-upstream.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md` (Sections 6.1, 6.5; D8; F11; T3, T6, T8, T14; Section 11 Limits)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/services/query_pipeline.py` (step 7b); tests |
| Story | STORY-012 |
| PRD | PRD-013 |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`. This story has no UI surface (story Technical Notes: "Skills: none applicable"). | — |

---

## What already exists (do not rebuild)

| Piece | Where | State |
|---|---|---|
| `charge(user_id, day, input_tokens, output_tokens, total_tokens)` | `app/services/usage_limits.py:191-238` | Done (STORY-010). Charges the split when both halves are present, otherwise charges `total_tokens` to `unsplit_tokens`. It catches `StorageError` and logs one `ERROR` line with user, day and counts. It also logs `ERROR` when no row matched. It never raises for storage. |
| `charge_usage(...)` → `bool` | `app/db/database.py:1721-1743` | Done (STORY-009). One `UPDATE usage_daily … WHERE user_id = ? AND day = ?`. |
| `Admission.day` | `app/services/usage_limits.py:66-82` | Set on every admission. It is the day to charge. |
| `admission` local | `app/services/query_pipeline.py:338-340` | `None` when the switch is off. The STORY-011 comment says STORY-012 reads `None` as "charge nothing". |
| Unit tests of `charge` | `tests/test_usage_limits.py:310-380` | Fail-open, no-row, split, unsplit and half-split behaviour are all pinned. Do not duplicate them. The pipeline tests below assert the call site, not `charge`'s internals. |

---

## Patterns to Follow

### Binding by name into `query_pipeline` (so the suite can spy on it)
```python
# SOURCE: app/services/query_pipeline.py:35-38
# By name into this module, not `usage_limits.admit`: the suite replaces
# `query_pipeline.admit` to spy on the gate or fail it, the binding rule
# `_redact` documents for `redact`.
from app.services.usage_limits import admit
```
→ becomes `from app.services.usage_limits import admit, charge`. Extend the comment to name `charge`.

### Gate arm, reading the switch through `admission`
```python
# SOURCE: app/services/query_pipeline.py:338-340
admission = None
if settings.USAGE_LIMITS_ENABLED:
    admission = admit(identity, charges_budget=openrouter_api_key is None)
```
Step 7b does **not** re-read `settings.USAGE_LIMITS_ENABLED`. It reads `admission is not None`. If the switch flipped mid-request, the request is charged or not according to how it was admitted, and there is always a row to charge.

### Upstream error arm (must stay uncharged)
```python
# SOURCE: app/services/query_pipeline.py:599-630
try:
    ...openrouter_result = call_openrouter(...)
except OpenRouterError as exc:
    log_query(...success=False...)
    raise
```
Step 7b goes **after** this block. The `except` re-raises, so code below it never runs on an upstream error. That is how "upstream error → nothing charged" is guaranteed.

### Output-redaction error arm (must be charged)
```python
# SOURCE: app/services/query_pipeline.py:639-662
if policy.output:
    try:
        redacted_response, output_entities = _redact(openrouter_result.response, policy)
    except PiiRedactorError as exc:
        log_query(... input_tokens=openrouter_result.input_tokens, ... success=False ...)
        raise
```
Step 7b goes **before** this block, so this arm cannot skip it (PRD 6.1, "Why the charge is at 7b").

### Tests: helpers, stubbed admission, failing collaborators
```python
# SOURCE: tests/test_query_pipeline_usage_limits.py:67-133
def _limits(monkeypatch, *, rpm="*=60", budget="*=1000000"): ...
def _usage(window_requests=1, tokens_today=0) -> UsageAdmission: ...
def _returns(monkeypatch, *usages): ...   # fakes usage_limits.admit_usage
def _fail_if_called(*args, **kwargs): raise AssertionError(...)
def _answer(messages, model="gpt-4", api_key=None):
    return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)
def _run(identity=_JUAN, prompt=..., *, upstream=_answer, api_key=None, **kwargs): ...
```

### Spy fixture on a pipeline binding
```python
# SOURCE: tests/test_query_pipeline_usage_limits.py:135-147
@pytest.fixture
def admit_calls(monkeypatch):
    calls: list = []
    real_admit = query_pipeline.admit
    def _spy_admit(identity, charges_budget):
        calls.append((identity.user_id, charges_budget))
        return real_admit(identity, charges_budget=charges_budget)
    monkeypatch.setattr(query_pipeline, "admit", _spy_admit)
    return calls
```

### Seeding today's counter row through real storage
```python
# SOURCE: tests/test_query_outcomes_regression.py:273-279
with get_connection() as conn:
    conn.execute(
        "INSERT INTO usage_daily "
        "(user_id, day, requests, window_start, window_requests, input_tokens) "
        "VALUES (?, date('now'), 0, strftime('%s','now') / 60, 0, 100)",
        (_AUTH_USER_ID,),
    )
```

### Forcing the output-redaction error
```python
# SOURCE: tests/test_audit_characterization.py:269-277
def _redact_stub(entities: dict, fail_on: Optional[str] = None):
    def _redact(text, *args):
        if text == fail_on:
            raise PiiRedactorError("PII analysis failed: boom")
        return text, list(entities.get(text, []))
    return _redact
# used as: monkeypatch.setattr(query_pipeline, "redact", _redact_stub({}, fail_on="Hi there!"))
```
The default profile is `chat` (`app/config.py:260`), whose policy has `output` on, so step 8 redacts the response.

### Log assertion
```python
# SOURCE: tests/test_usage_limits.py:45-46, 310-326
def _records(caplog):
    return [r for r in caplog.records if r.name == _LOGGER]   # "app.services.usage_limits"
with caplog.at_level(logging.DEBUG, logger=_LOGGER): ...
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/query_pipeline.py` | UPDATE | Import `charge` by name. Add the step 7b call site between step 7 and step 8. Update the STORY-011 forward-reference comments at 2c. |
| `tests/test_query_pipeline_usage_limits.py` | UPDATE | Add the STORY-012 tests (AC 1-5, step order, midnight day, overshoot). Extend the module docstring. |
| `tests/test_two_instance_smoke.py` | UPDATE | Raise `test_round_trip_cost_is_measured_and_reported` from four statements to five (`UPDATE usage_daily` before the audit `INSERT`), with a STORY-012 comment. |

No schema, router, settings or UI changes. `charge()` and `charge_usage()` are not modified.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Bind `charge` into the pipeline module

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: Change line 38 to `from app.services.usage_limits import admit, charge`. Extend the comment at 35-37 so it covers both names: the suite replaces `query_pipeline.admit` and `query_pipeline.charge` to spy on them or fail them.
- **Mirror**: `app/services/query_pipeline.py:35-38`
- **Validate**: `python -c "import app.services.query_pipeline as q; assert q.charge.__module__ == 'app.services.usage_limits'"`

### Task 2: Step 7b, the charge

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: Insert directly after the `except OpenRouterError … raise` block (currently ending at line 630) and before the `# Step 8:` comment:
  ```python
  # Step 7b: charge (PRD-013 Sections 6.1, 6.5; D8; F11; T3, T8).
  #
  # Here, as soon as the provider has reported usage and before step 8, so
  # the output-redaction error arm below cannot skip it: tokens spent on a
  # response the user never receives are still spent (PRD-009 Risk 4, T3).
  # The upstream-error arm above re-raises before reaching this line, so a
  # call that reported nothing charges nothing.
  #
  # `admission` is None exactly when the switch was off at step 2c; reading
  # it rather than the setting means a request is charged by the rule it was
  # admitted under, and always has a row to charge. BYOK spends the caller's
  # own key, so it is rate-limited at 2c but charges nothing here (D8, T14);
  # its audit row still records the tokens.
  #
  # The admitted `day`, not today: a request straddling midnight is charged
  # to the day it was admitted. charge() fails open (T8) -- a storage error
  # is logged at ERROR with the user, day and counts and the caller still
  # gets the answer; the audit row's token columns are the record.
  if admission is not None and openrouter_api_key is None:
      charge(
          identity.user_id,
          admission.day,
          openrouter_result.input_tokens,
          openrouter_result.output_tokens,
          openrouter_result.tokens_used,
      )
  ```
  - Pass positionally, to match `charge`'s signature (`user_id, day, input_tokens, output_tokens, total_tokens`).
  - Do not wrap it in `try`. `charge` already swallows `StorageError` by design, and `test_charge_does_not_swallow_errors_that_are_not_storage_errors` pins that anything else propagates. A programming error should surface, not vanish.
  - Do not add a `log_query` call. Every `log_query` call-site counter in the suite (STORY-011 Deviation 1) stays where it is.
- **Also**: In the step 2c comment block (lines ~322-325 and ~337), reword the "STORY-012 charges…" / "which STORY-012 reads as…" forward references into present tense pointing at step 7b. Example: "`admission` is kept in a local: step 7b charges the `day` it was counted against…" and "None when the switch is off, which step 7b reads as 'charge nothing'."
- **Mirror**: comment density and citation style of the step 2c block, `app/services/query_pipeline.py:304-337`
- **Validate**: `python -m py_compile app/services/query_pipeline.py && python -c "from app.main import app"`

### Task 3: Tests: the charge in the pipeline

- **File**: `tests/test_query_pipeline_usage_limits.py`
- **Action**: UPDATE
- **Implement**:
  - Docstring: retitle to "PRD-013 STORY-011 and STORY-012: the usage gate (step 2c) and the charge (step 7b)". Add bullets: charged on success and on the output-redaction-error arm, never on the upstream-error arm; unsplit tokens go to `unsplit_tokens`; BYOK charges nothing; the charge fails open; the overshoot is documented, not hidden.
  - New imports: `logging`, `OpenRouterError` (from `app.services.openrouter_client`) and `PiiRedactorError` (from `app.services.pii_redactor`).
  - New helpers, under the `# --- helpers` section:
    - `_split_answer(messages, model="gpt-4", api_key=None)` → `OpenRouterResult(response="Hi there!", model_used=model, tokens_used=150, input_tokens=120, output_tokens=30)`.
    - `_unsplit_answer` → same, but `tokens_used=150` and no split.
    - `_failing_upstream` → raises `OpenRouterError("upstream unavailable")`.
    - `_today(user_id)` → `SELECT input_tokens, output_tokens, unsplit_tokens FROM usage_daily WHERE user_id = ?` as a tuple, `None` when there is no row. Real storage only. Use `SUM` across days, as `_requests_today` does, so a midnight rollover mid-test cannot split the reading.
    - `charge_calls` fixture → a spy on `query_pipeline.charge` that records `(user_id, day, input, output, total)` and delegates to the real function. Mirror `admit_calls`.
  - Section `# --- STORY-012 AC 1: charged on success` (all real storage, no `_returns` stub):
    - `test_a_successful_request_charges_its_split_to_the_admitted_day`: run with `_split_answer`. `_today(_JUAN.user_id) == (120, 30, 0)`.
    - `test_a_later_request_sees_tokens_today_increased_by_the_charge`: wrap `usage_limits.admit_usage` in a recorder that delegates to the real one. Send two prompts. The second recorded `tokens_today` equals the first plus 150.
  - Section `# --- STORY-012 AC 2: which arms are charged`:
    - `test_an_output_redaction_failure_is_still_charged`: patch `query_pipeline.redact` with a stub that raises `PiiRedactorError` on `"Hi there!"` (mirror `_redact_stub`). Run with `_split_answer` and assert `pytest.raises(PiiRedactorError)`. Then `_today == (120, 30, 0)`, and the last audit row has `success == False`, `input_tokens == 120` and `output_tokens == 30`.
    - `test_an_upstream_error_charges_nothing`: monkeypatch `query_pipeline.charge` with `_fail_if_called`. `pytest.raises(OpenRouterError)`. `_today == (0, 0, 0)`, because the row exists from admit with nothing charged.
    - `test_check_order_ends_with_the_charge`: a short spy trace over `call_openrouter`, `charge` and `redact` (the response call). Assert the order `upstream, charge, redact_output`. The existing order test stays as it is. This one adds the PRD 9.2 invariant "… → upstream → charge". Keep the trace to these three: the existing test already pins everything earlier.
  - Section `# --- STORY-012 AC 3: no split`:
    - `test_a_response_without_the_split_charges_unsplit_tokens`: run with `_unsplit_answer`. `_today == (0, 0, 150)`.
    - `test_unsplit_tokens_count_toward_the_budget`: real storage, `_limits(budget="*=100")`. The first send (`_unsplit_answer`, 150 tokens) succeeds. The second send, with `upstream=_fail_if_called`, returns `QueryBlockedUsageLimitResponse` with `limit == "tokens"` and `actual == 150`.
  - Section `# --- STORY-012 AC 4: BYOK`:
    - `test_byok_consumes_a_unit_is_not_budget_refused_and_charges_nothing`: seed today's row at the budget (the outcome-8 seeding pattern, `input_tokens=100`), with `_limits(budget="*=100")` and `monkeypatch.setattr(query_pipeline, "charge", _fail_if_called)`. Run `_ROOT` with `api_key="sk-caller-supplied"` and `_split_answer`. The result is `QuerySuccessResponse`, `_requests_today("root") == 1`, `_today("root") == (100, 0, 0)` (unchanged), and the last audit row has `input_tokens == 120` and `output_tokens == 30`.
    - `test_the_harness_key_is_charged_and_byok_is_not` (with `charge_calls`): send `_ROOT` once without a key and once with one. `charge_calls` holds exactly one entry, for the first.
  - Section `# --- STORY-012 AC 5: the charge fails open`:
    - `test_a_charge_storage_failure_still_returns_success_with_its_row`: patch `usage_limits.charge_usage` to raise `StorageError("counter unreachable")`. Run with `_split_answer` under `caplog.at_level(logging.DEBUG, logger="app.services.usage_limits")`. The result is `QuerySuccessResponse`. The last audit row has `success == True` and `id == result.audit_id`. Exactly one record from that logger, at `ERROR`, whose message contains `_JUAN.user_id`, the admitted day (read `SELECT day FROM usage_daily WHERE user_id = ?`), `input_tokens=120` and `output_tokens=30`.
  - Section `# --- STORY-012: the admitted day, and the switch`:
    - `test_the_charge_goes_to_the_day_the_gate_returned` (with `charge_calls`): `_returns(monkeypatch, _usage())` returns `day=_DAY`. Patch `usage_limits.charge_usage` with a recorder that returns `True`, so no real row is needed. Assert the recorded day is `_DAY`. This is the straddle-midnight rule: the charge uses the admission's day, not the clock's.
    - `test_with_limits_off_nothing_is_charged`: `USAGE_LIMITS_ENABLED=False` and `query_pipeline.charge = _fail_if_called`. A success with `_split_answer` writes zero `usage_daily` rows. The existing `test_with_limits_off_no_statement_touches_usage_daily` already patches `charge_usage` to fail. It now guards a real call site, so leave it unchanged.
  - Section `# --- STORY-012: the overshoot is check-then-charge (PRD 6.5, T6)`:
    - `test_two_requests_admitted_under_a_nearly_spent_budget_both_complete`: real storage. `_limits(budget="*=1000")`. Seed today's row with `input_tokens=999`. Make request A's upstream run request B (a different prompt, `upstream=_split_answer`) inside A's `call_openrouter` and then return `_split_answer(...)`. B is then admitted while A is in flight, before A charges. This reproduces two concurrent admissions deterministically, with no threads. Assert that both results are `QuerySuccessResponse` and that `sum(_today) == 999 + 150 + 150`, which is over the budget. The docstring states that this documents the accepted overshoot (bounded by rate × one response, PRD 6.5, T6), that it is not a bug, and that reserving `max_tokens` is the Future Consideration that would close it. A third send is then refused with `limit == "tokens"`.
- **Mirror**: `tests/test_query_pipeline_usage_limits.py:135-147` (spy fixture), `:479-491` (switch-off), `tests/test_query_outcomes_regression.py:273-279` (seeding), `tests/test_audit_characterization.py:269-277` (redact stub), `tests/test_usage_limits.py:310-326` (caplog)
- **Validate**: `python -m pytest tests/test_query_pipeline_usage_limits.py -q`

### Task 4: Raise the round-trip guard from four statements to five

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE
- **Implement**: In `test_round_trip_cost_is_measured_and_reported` (~line 1425-1438), extend the PRD-013 comment: "STORY-012: five. The charge (step 7b) is one `UPDATE usage_daily` between the duplicate read and the audit insert, the second round trip Risk 1 accepts. USAGE_LIMITS_ENABLED=false still restores the three above." Then change the expected verbs to `["SELECT", "INSERT", "SELECT", "UPDATE", "INSERT"]`, add `assert "usage_daily" in query_statements[3]`, and move the `INTO audit_logs` assertion to index 4. Keep the assertions by name, as the existing comment requires.
- **Mirror**: STORY-011's edit of the same test (`tests/test_two_instance_smoke.py:1425-1438`)
- **Validate**: `python -m pytest tests/test_two_instance_smoke.py -q -k round_trip`

### Task 5: Mutation check

- **Action**: Verify only. Make no committed change.
- **Implement**:
  1. Temporarily move the step 7b block below the `if policy.output:` block. The output-redaction-error test and `test_check_order_ends_with_the_charge` must fail.
  2. Temporarily drop `and openrouter_api_key is None`. Both BYOK tests must fail.
  3. Temporarily change `admission.day` to a literal other day. `test_the_charge_goes_to_the_day_the_gate_returned` and the AC 1 real-storage tests must fail (no matched row, so nothing is charged).

  Restore after each step. Record the counts in the report.
- **Validate**: `python -m pytest tests/test_query_pipeline_usage_limits.py -q` (red under each mutation, green after restoring)

### Task 6: Full-suite sweep

- **Action**: Run the full suite. Follow the `harness-ai-test-env` memory: the venv, the libSQL container, and known `os error 10060` connection-timeout flakes that pass on rerun.
- **Watch for**: any other test that counts statements on a success path, and any success-path test using `_returns` with a stubbed `day` but no real row. Those now log one `ERROR` "matched no row" from `usage_limits`. That is harmless unless a test asserts no `ERROR` records from that logger. `tests/test_query_pipeline_patterns.py` filters on the `query_pipeline` logger, so it is unaffected. If a guard trips, raise it with a comment citing PRD-013 STORY-012, as STORY-011 did. Do not weaken it.
- **Validate**: `python -m pytest -q` → all pass (the known flakes pass on rerun)

---

## End-to-End Tests

- [ ] `uvicorn app.main:app` against the dev libSQL, with a placeholder OpenRouter key (nothing spent) and one user from `manage_users.py create-user`. `POST /query` → `502` (the upstream fails). Then `SELECT input_tokens, output_tokens, unsplit_tokens FROM usage_daily` shows `0, 0, 0`, with `requests` incremented. This confirms an upstream error charges nothing on the real server.
- [ ] If a real key is available and the user agrees to a tiny spend: one `POST /query` → `200`. The `usage_daily` row gains the `input_tokens`/`output_tokens` that `GET /audit` shows on the row. Otherwise rely on the automated real-storage AC 1 tests. Note the reason in the report.
- [ ] With `USAGE_LIMITS_ENABLED=false`: `POST /query` creates no `usage_daily` row.

---

## Validation

```bash
python -m py_compile app/services/query_pipeline.py
python -c "from app.main import app"
python -m pytest tests/test_query_pipeline_usage_limits.py tests/test_usage_limits.py tests/test_query_outcomes_regression.py -q
python -m pytest tests/test_two_instance_smoke.py -q -k round_trip
python -m pytest -q
```

There is no npm frontend (the UI is Reflex) and no Python linter configured. `py_compile` stands in for lint, as in STORY-011.

---

## Risks

| Risk | Mitigation |
|---|---|
| A test that stubs `admit_usage` (`_returns`) and then succeeds now calls the real `charge_usage` with a fake day, which matches no row and logs `ERROR`. | Harmless (fail-open by design). No existing test asserts zero `ERROR` from `usage_limits` on the pipeline path. Task 6 watches for it. |
| Statement-count guards break (smoke test, possibly others). | Task 4 raises the known one. Task 6 sweeps for the rest, and each is raised with a citation rather than loosened. |
| Re-reading `USAGE_LIMITS_ENABLED` at 7b would charge a request admitted with the switch off, on a row that may not exist. | Gate on `admission is not None`, not on the setting (Task 2). |
| Wrapping `charge` in `try/except Exception` would hide programming errors. | No wrapper. `charge` owns the fail-open rule for `StorageError` only. |
| The overshoot test could be read as a bug report. | Its docstring cites PRD 6.5 / T6 as accepted behaviour and names the Future Consideration. |

---

## Acceptance Criteria

(Copied from story `STORY-012`)

- [ ] Given a successful request reporting 120 input and 30 output tokens, when it completes, then the user's `usage_daily` row for the admitted day has those amounts added, and a later request sees `tokens_today` increased by 150.
- [ ] Given an output-redaction failure after the provider answered, when the request fails, then the tokens are still charged; given an upstream error, then nothing is charged.
- [ ] Given a provider response with no split, when the request completes, then `tokens_used` is charged to `unsplit_tokens` and counts toward the budget.
- [ ] Given a BYOK request (`openrouter_api_key` supplied), when it completes, then it consumed one unit of the rate window, was not refused for budget even with the budget exhausted, and charged nothing, while its audit row still records the tokens.
- [ ] Given `charge_usage` raising `StorageError` after a successful upstream call, when the request completes, then the caller receives the normal success response, the success audit row is written, and one `ERROR` log line names the user, day and counts.
- [ ] All tasks completed
- [ ] Backend imports / server starts without error
- [ ] Full suite passes (known libSQL timeout flakes pass on rerun)
- [ ] Follows existing patterns
