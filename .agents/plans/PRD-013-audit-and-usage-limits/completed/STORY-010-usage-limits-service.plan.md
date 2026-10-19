---
story: STORY-010
prd: PRD-013
slug: usage-limits-service
title: "usage_limits: limit resolution and the rate and budget checks"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-013-audit-and-usage-limits   # all stories commit here, no per-story branch
created: 2026-10-19
---

# Plan: usage_limits: limit resolution and the rate and budget checks

## Summary

Create `app/services/usage_limits.py`, a thin decision layer over the primitives STORY-007/008/009 already shipped. It has four parts:

- `limits_for(identity) -> UsageLimits` resolves each limit independently: the per-user override on `Identity`, else the role's entry in the parsed settings map, else `*`. Settings are read per call.
- `admit(identity, charges_budget) -> Admission` makes one `admit_usage()` call (one statement, one round trip), then compares in Python. The rate is checked first, the budget only if the rate passed. `resets_at` is derived from the `window_start`/`day` the database returned. `StorageError` is wrapped in `UsageLimitError` (fail closed, T7).
- `charge(user_id, day, input_tokens, output_tokens, total_tokens)` charges the split when both halves are present, otherwise charges `total_tokens` to `unsplit_tokens`. It catches `StorageError`, logs at `ERROR` and returns (fail open, T8).
- `UsageLimitError` is the named exception for STORY-011 to map to `500`.

The module does not read `USAGE_LIMITS_ENABLED` and is not wired into the pipeline yet; that is STORY-011 and STORY-012. Tests stub `admit_usage`/`charge_usage` at the module boundary, so every acceptance criterion is deterministic and never races a minute boundary. One real-database test proves the wiring.

## User Story

As a platform operator
I want one function that says whether an identity is admitted and why not
So that the pipeline enforces limits without knowing how they are configured or stored

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-010-usage-limits-service.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md` (sections 6.1, 6.5, 6.6 / D1, 6.7, 7 F9 + F11, 9.2 T7/T8)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/services/usage_limits.py` (new), `tests/test_usage_limits.py` (new) |
| Story | STORY-010 |
| PRD | PRD-013 |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch) |
| Depends on | STORY-007 ✅, STORY-008 ✅, STORY-009 ✅ |
| Blocks | STORY-011 |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | The only skill is `frontend-design`. This story has no UI surface. | — |

---

## What already exists (inputs to this story)

| Primitive | Location | Contract |
|---|---|---|
| `settings.usage_daily_token_budget_map` / `usage_requests_per_minute_map` | `app/config.py:548-553` | `dict[str, Optional[int]]`, `None` = unlimited, `*` guaranteed by the validator. **Properties that parse on each access**, so `monkeypatch.setattr(settings, "USAGE_REQUESTS_PER_MINUTE", "*=3")` takes effect immediately. |
| `Identity.role`, `.token_budget_daily`, `.requests_per_minute`, `.break_glass` | `app/services/identity.py:19-46` | Overrides are `None` = "use the role's". Break-glass has `role="admin"` and no overrides, so it resolves through `admin` with no special case. |
| `admit_usage(user_id) -> UsageAdmission` | `app/db/database.py:1693-1711` | One `RETURNING` statement. Returns `day` (`'YYYY-MM-DD'`), `window_start` (unix minute, int), `window_requests`, `tokens_today`. Raises `StorageError`. |
| `charge_usage(user_id, day, input, output, unsplit) -> bool` | `app/db/database.py:1714-1735` | One `UPDATE`. Returns `False` when no `(user_id, day)` row exists. Raises `StorageError`. |
| `UsageAdmission` | `app/db/models.py:409-423` | Frozen dataclass, no defaults. |
| `StorageError` | `app/db/errors.py:17` | Base storage exception. |

---

## Patterns to Follow

### Naming: wrap `StorageError` in a named service exception
```python
# SOURCE: app/services/duplicate_checker.py:13-14, 29-35
class DuplicateCheckError(Exception):
    pass
...
    try:
        match = find_duplicate_timestamp(user_id, key, cutoff)
    except StorageError as exc:
        raise DuplicateCheckError(f"Duplicate lookup failed: {exc}") from exc
```
`UsageLimitError` mirrors this exactly: `raise UsageLimitError(f"Usage admission failed: {exc}") from exc`.

### Settings read per call, one limit reported
```python
# SOURCE: app/services/query_pipeline.py:68-94  (_context_limit_exceeded)
    Both maxima are read off `settings` **here, per call** rather than captured
    at import. ... every test in this suite sets them with
    `monkeypatch.setattr(settings, ...)`, which a module-level constant would
    silently ignore (STORY-008 Technical Notes).
    ...
    message_count = len(messages)
    if message_count > settings.CONTEXT_MAX_MESSAGES:
        return "messages", settings.CONTEXT_MAX_MESSAGES, message_count
```
Import `from app.config import settings` (the object), never the map values.

### Timestamp format
```python
# SOURCE: app/services/audit_logger.py:8, app/db/database.py:42
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
```
Every service module re-declares this constant locally (audit_logger, duplicate_checker). Do the same.

### Logging
```python
# SOURCE: app/services/query_pipeline.py:1, 45, 383-388
import logging
logger = logging.getLogger(__name__)
...
        logger.warning(
            "pattern scan truncated: user_id=%s message_index=%d length=%d scanned=%d",
            identity.user_id, index, ...
```
`key=value` pairs, `%`-style lazy args.

### Tests
```python
# SOURCE: tests/test_usage_storage.py:1-12, tests/test_duplicate_checker.py:1-4
"""usage_daily and its two statements (PRD-013 STORY-009, Section 6.5). ..."""
import os
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```
```python
# SOURCE: tests/test_pii_policy.py:60-61, 228-233  (caplog filtered by logger name)
def _records(caplog):
    return [r for r in caplog.records if r.name == _LOGGER]
...
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
```
`tests/conftest.py:192-220`: an autouse fixture gives every test an empty, isolated database, so the one real-DB test needs no setup beyond `init_db()` (check `test_usage_storage.py` for whether it calls `init_db()` itself or relies on a fixture, and do the same).

---

## Design decisions

1. **`Admission` shape: one frozen dataclass with a nested refusal.** This makes the two cases impossible to confuse:
   ```python
   UsageLimit = Literal["requests", "tokens"]

   @dataclass(frozen=True)
   class UsageRefusal:
       limit: UsageLimit
       maximum: int
       actual: int
       resets_at: str          # _TIMESTAMP_FORMAT, UTC

   @dataclass(frozen=True)
   class Admission:
       day: str                               # the day admit_usage counted against
       refusal: Optional[UsageRefusal] = None

       @property
       def admitted(self) -> bool:
           return self.refusal is None
   ```
   The refusal fields cannot be read off an admitted result by accident (they live on `refusal`, which is `None`). `day` is present in both cases, because STORY-011 charges by it and an audit row may want it. `UsageRefusal` maps 1:1 onto `QueryBlockedUsageLimitResponse` (PRD 6.7), so STORY-011 builds the response from it field by field.
2. **`limits_for` resolution, per limit:**
   ```python
   def _resolve(override, role, table):  # table = settings.<map>, read per call
       if override is not None:
           return override
       if role in table:
           return table[role]   # may be None = unlimited; an explicit role entry wins over '*'
       return table["*"]
   ```
   `role in table` is a membership test, not `.get(role) or …`. This is so that `admin=unlimited` (value `None`) is honoured and does not fall through to `*`. This is the subtle bug to guard against, and it gets a test.
3. **Checks** (PRD 6.5, verbatim semantics):
   - rate: `rpm is not None and adm.window_requests > rpm` → `UsageRefusal("requests", rpm, adm.window_requests, _end_of_minute(adm.window_start))`
   - budget (only if rate passed): `charges_budget and budget is not None and adm.tokens_today >= budget` → `UsageRefusal("tokens", budget, adm.tokens_today, _next_utc_midnight(adm.day))`
   - Rate uses strict `>`: the 3rd of 3 is admitted. Budget uses `>=`: at the budget you are out.
4. **`resets_at` from DB values only** (no `datetime.now()` anywhere in the module):
   - `_end_of_minute(window_start)` = `datetime.fromtimestamp((window_start + 1) * 60, tz=timezone.utc).strftime(_TIMESTAMP_FORMAT)`. "End of the current minute" is the instant the next window opens, `HH:MM+1:00Z`. That is when the user can send again.
   - `_next_utc_midnight(day)` = `(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)).strftime(_TIMESTAMP_FORMAT)`.
5. **`charge`** — signature `charge(user_id, day, input_tokens: Optional[int], output_tokens: Optional[int], total_tokens: int) -> None`:
   - split present (both not `None`) → `charge_usage(user_id, day, input_tokens, output_tokens, 0)`
   - otherwise → `charge_usage(user_id, day, 0, 0, total_tokens)`
   - `except StorageError` → `logger.error("usage charge failed: user_id=%s day=%s input_tokens=%s output_tokens=%s total_tokens=%s error=%s", ...)` and return.
   - `charge_usage` returning `False` (no row, which a successful admit rules out) → also `logger.error("usage charge matched no row: …")` with the same fields, then return. STORY-009 deferred this choice to the caller. Logging is the fail-open rule applied consistently, and it costs one line.
   - Never raises for storage. It does not catch broader exceptions: a `TypeError` from a bad call is a bug and should surface.
6. **`admit` catches only `StorageError`**, the same breadth as `duplicate_checker`.
7. **No `USAGE_LIMITS_ENABLED` read, no BYOK logic.** `charges_budget` is the caller's statement of BYOK (STORY-011/012). A test asserts that the module source does not reference `USAGE_LIMITS_ENABLED`, so the boundary cannot drift.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/usage_limits.py` | CREATE | `UsageLimits`, `UsageRefusal`, `Admission`, `UsageLimitError`, `limits_for`, `admit`, `charge`, two private `resets_at` helpers |
| `tests/test_usage_limits.py` | CREATE | Unit tests for all five ACs (stubbed storage) + one real-DB wiring test |

No changes to `app/config.py`, `identity.py`, `database.py` or `models.py`: every input already exists with the contract this story needs.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Types, exception and `limits_for`

- **File**: `app/services/usage_limits.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring: what it is (PRD-013 F9, Sections 6.5–6.7), what it is *not* (it does not read `USAGE_LIMITS_ENABLED`, which is the pipeline's switch, STORY-011), and the fail-closed admit / fail-open charge rule (T7/T8).
  - Imports: `logging`, `dataclass`, `datetime, timedelta, timezone`, `Literal, Optional`. `from app.config import settings`, `from app.db.database import admit_usage, charge_usage`, `from app.db.errors import StorageError`, `from app.services.identity import Identity`.
  - `_TIMESTAMP_FORMAT`, `logger`.
  - `class UsageLimitError(Exception)`, mirroring `DuplicateCheckError`.
  - `@dataclass(frozen=True) class UsageLimits: token_budget_daily: Optional[int]; requests_per_minute: Optional[int]`, exactly as in PRD 6.6.
  - `UsageLimit` literal, `UsageRefusal`, `Admission` per Design decision 1.
  - `_resolve(override, role, table)` per Design decision 2. `limits_for(identity)` calls it twice, reading `settings.usage_daily_token_budget_map` and `settings.usage_requests_per_minute_map` inside the function body. The docstring cites the `_context_limit_exceeded` note and says break-glass resolves through `admin` without a special case (Section 6.6).
- **Mirror**: `app/services/duplicate_checker.py:1-20` (module shape, exception), `app/services/query_pipeline.py:68-94` (per-call settings docstring)
- **Validate**: `python -c "import app.services.usage_limits"` (with `OPENROUTER_API_KEY`/`ADMIN_TOKEN` set)

### Task 2: `admit`

- **File**: `app/services/usage_limits.py`
- **Action**: UPDATE
- **Implement**: `admit(identity: Identity, charges_budget: bool) -> Admission`:
  1. `limits = limits_for(identity)`, resolved **before** the storage call. So if settings are broken, nothing is counted, though the validators make that unreachable.
  2. `try: adm = admit_usage(identity.user_id) except StorageError as exc: raise UsageLimitError(f"Usage admission failed: {exc}") from exc`
  3. Rate check, then budget check, per Design decision 3. Return `Admission(day=adm.day, refusal=...)`.
  - `_end_of_minute(window_start: int) -> str` and `_next_utc_midnight(day: str) -> str`, per Design decision 4.
  - Docstring: one statement, one round trip. The attempt is counted even when refused (PRD 6.5 "A refused attempt still counts"). Only one limit is reported, rate first.
- **Mirror**: `app/services/duplicate_checker.py:29-35`
- **Validate**: Task 4 tests

### Task 3: `charge`

- **File**: `app/services/usage_limits.py`
- **Action**: UPDATE
- **Implement**: per Design decision 5. The docstring states PRD F11 (split vs `unsplit_tokens`) and T8 (fail open: the user already has the answer, and the audit row's token columns are the record). It also explains why `day` is a parameter: it is the admitted day, so a request that straddles midnight is charged to that day.
- **Mirror**: logging style `app/services/query_pipeline.py:383-388`
- **Validate**: Task 4 tests

### Task 4: Unit tests (stubbed storage)

- **File**: `tests/test_usage_limits.py`
- **Action**: CREATE
- **Implement**: Module docstring + env preamble per `tests/test_usage_storage.py:1-12`. Helpers:
  - `_adm(window_requests=1, tokens_today=0, day="2026-10-19", window_start=<fixed int>)` builds a `UsageAdmission`.
  - A fixture that monkeypatches `usage_limits.admit_usage` with a fake counter keyed by user, which increments `window_requests` per call in a fixed `window_start`. This simulates "four calls in one minute" without the clock.
  - Settings are set with `monkeypatch.setattr(settings, "USAGE_REQUESTS_PER_MINUTE", "...")` / `"USAGE_DAILY_TOKEN_BUDGET"`.

  Tests (AC numbers from the story):
  - **AC1 resolution**: settings `rpm "*=60,admin=120,analyst=30"`, budget `"*=1000000,analyst=5000"`.
    - `Identity("u","analyst", requests_per_minute=7)` → rpm 7 (override), budget 5000 (role). This also shows the two limits resolve independently.
    - `Identity("u","analyst")` → 30 / 5000.
    - `Identity("u","nobody")` → 60 / 1000000 (`*`).
    - `Identity("u","analyst", token_budget_daily=9)` → rpm 30, budget 9.
    - **Explicit unlimited role beats `*`**: budget `"*=1000000,admin=unlimited"` → `Identity("u","admin").token_budget_daily is None`.
    - **Break-glass**: `Identity("admin","admin", break_glass=True)` resolves to the `admin` entry.
    - **Per-call read**: call `limits_for`, change the setting with monkeypatch, call again, and the value changes.
  - **AC2 rate**: `rpm "*=3"`, four `admit(..., charges_budget=True)` calls. The first three have `admitted is True` and `refusal is None`. The fourth has `refusal == UsageRefusal("requests", 3, 4, <end of minute>)`, with the expected value computed as a literal from the fixed `window_start` (e.g. `window_start = 29_000_000` → assert the exact `"...Z"` string, hand-computed), plus `re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:00Z", ...)`.
  - **AC3 budget**: stub returns `tokens_today == budget` (at) and `budget + 1` (above), `charges_budget=True` → refused `limit="tokens"`, `maximum=budget`, `actual=tokens_today`, `resets_at == "2026-10-20T00:00:00Z"` for `day="2026-10-19"`. A month-end case: `day="2026-10-31"` → `"2026-11-01T00:00:00Z"`. Same stub with `charges_budget=False` → admitted. `tokens_today == budget - 1` → admitted.
  - **AC4 precedence + unlimited**: the stub breaks both (`window_requests=4`, rpm 3, tokens over budget) → `limit == "requests"`. Then `rpm "*=unlimited"` with `window_requests=10_000` → admitted. Then budget `"*=unlimited"` with huge `tokens_today` → admitted.
  - **AC5 admit fail-closed**: the stub raises `StorageError("boom")` → `pytest.raises(UsageLimitError)`, and `__cause__` is the `StorageError`.
  - **AC5 charge fail-open**: `charge_usage` stub raises `StorageError` → `charge("u1","2026-10-19",10,20,30)` returns `None` and does not raise. `caplog` has exactly one `ERROR` record from logger `app.services.usage_limits` whose message contains `u1`, `2026-10-19` and the counts.
  - **Charge routing (F11)**: record the stub's args. Split `(10, 20, total=30)` → `(u, day, 10, 20, 0)`. No split `(None, None, 30)` → `(u, day, 0, 0, 30)`. Half split `(10, None, 30)` → unsplit path.
  - **Charge no-row**: the stub returns `False` → one `ERROR` record, no raise.
  - **Admission shape**: `Admission` and `UsageRefusal` are frozen (assigning raises `FrozenInstanceError`). An admitted result has `refusal is None` and a `day`.
  - **Boundary**: `"USAGE_LIMITS_ENABLED" not in inspect.getsource(usage_limits)`.
- **Mirror**: `tests/test_usage_storage.py:1-60`, `tests/test_pii_policy.py:60-61, 228-233`
- **Validate**: `pytest tests/test_usage_limits.py -v`

### Task 5: Real-database wiring test

- **File**: `tests/test_usage_limits.py`
- **Action**: UPDATE
- **Implement**: One test, no stubs. Set `rpm "*=1000"` so that the rate is never hit. Call `admit(Identity("real-user","user"), charges_budget=True)` and assert it is admitted, with `day` equal to the DB's `date('now')` (reuse the `_db_clock` idea from `tests/test_usage_storage.py:45-50`). Then `charge("real-user", day, 5, 7, 12)` and read the row: `input_tokens == 5`, `output_tokens == 7`, `unsplit_tokens == 0`. Then `charge("real-user", day, None, None, 4)` → `unsplit_tokens == 4`. A second `admit` gives the budget check `tokens_today == 16`, which proves the read-back sums all three columns (assert through a refusal with budget `"*=16"`). No assertions depend on the minute not rolling over.
- **Mirror**: `tests/test_usage_storage.py` (DB setup + `_row` helper)
- **Validate**: `pytest tests/test_usage_limits.py tests/test_usage_storage.py -v`

### Task 6: Full suite

- **Validate**: `pytest tests/ -q` is green. The module is not imported by the pipeline yet, so no existing test should change.

---

## End-to-End Tests

There is no HTTP surface in this story (STORY-011 wires the gate into `/query`). The E2E checks are:

- [ ] `pytest tests/test_usage_limits.py -v`: every AC test passes
- [ ] The real-DB test passes against the conftest libsql endpoint (admit → charge split → charge unsplit → read-back)
- [ ] `python -c "from app.services.usage_limits import admit, charge, limits_for, UsageLimitError, Admission, UsageLimits"` succeeds
- [ ] `uvicorn app.main:app` starts unchanged (the module is not imported on the request path yet)

---

## Validation

```bash
pytest tests/test_usage_limits.py -v
pytest tests/ -q
uvicorn app.main:app --port 8000 &  # starts without error; curl http://localhost:8000/health
```

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `admin=unlimited` (`None`) falls through to `*` via `.get() or` | Membership test in `_resolve`, with a dedicated test (Design decision 2) |
| A real-DB test for "4 in one minute" flakes at a minute boundary | The AC tests stub `admit_usage`. The real-DB test asserts nothing that depends on the minute |
| `resets_at` computed from the instance clock | No `datetime.now()` in the module. The helpers take only `window_start`/`day`, and the tests use fixed DB-shaped values |
| Charge failure escapes and turns a delivered answer into a 500 | `charge` catches `StorageError`, and the test asserts no raise and one `ERROR` record |
| STORY-011 needs fields this shape lacks | `UsageRefusal` maps 1:1 onto `QueryBlockedUsageLimitResponse` (PRD 6.7), and `day` is on every `Admission` |

---

## Acceptance Criteria

(Copied from story `STORY-010`)

- [ ] Given an identity with a per-user override, with only a role entry, and with a role that has no entry, when `limits_for(identity)` is called, then it returns the override, the role's value and the `*` value respectively, resolved independently for the budget and the rate.
- [ ] Given a rate limit of 3, when `admit` is called four times in one minute, then the first three are admitted and the fourth is refused with `limit="requests"`, `maximum=3`, `actual=4` and `resets_at` equal to the end of the current minute in the audit timestamp format.
- [ ] Given `tokens_today` at or above the budget and `charges_budget=True`, when `admit` is called, then it is refused with `limit="tokens"` and `resets_at` at the next 00:00 UTC; with `charges_budget=False` it is admitted.
- [ ] Given both limits broken, when `admit` is called, then `limit="requests"` is the one reported; given a limit of `unlimited`, then that check never refuses.
- [ ] Given `admit_usage` raising `StorageError`, when `admit` is called, then it raises `UsageLimitError`; given `charge_usage` raising `StorageError`, when `charge` is called, then it logs at `ERROR` with the user id, day and counts, and returns without raising.
- [ ] All tasks completed
- [ ] `pytest tests/ -q` passes
- [ ] Backend server starts without error
- [ ] Follows existing patterns (`DuplicateCheckError` wrapping, per-call settings, `_TIMESTAMP_FORMAT`)
