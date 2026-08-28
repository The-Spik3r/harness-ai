---
story: STORY-002
prd: PRD-006
slug: verdict-derivation-formatting
title: "admin_formatting.py: verdict derivation, relative time, device and shares"
type: technical
complexity: MEDIUM
epic_branch: epic/PRD-006-admin-console
created: 2026-08-28
---

# Plan: admin_formatting.py — verdict derivation, relative time, device and shares

## Summary

Create `chat_ui/chat_ui/admin_formatting.py`: the pure-Python module that turns an `app/db/models.py:AuditLog` into a fully-populated `chat_ui/chat_ui/admin_models.py:AuditRow`, computing every displayed value **once, when the row is built** (PRD Section 6, "derived-once row model"). It owns four things: the four verdict constants plus `derive_verdict(log)` with the PRD's fixed precedence (`held` → `denied` → `fault` → `cleared`), `to_audit_row(log, now)` which populates the row and is the boundary at which both previews are dropped (Risk 2), `format_share(count, total)` for the summary's blocked-count shares with a defined placeholder at `total == 0`, and the compact relative time (`"2m ago"`) the register's time column shows. The relative-time thresholds are **not** re-implemented: `chat_ui/chat_ui/formatting.py:_humanize` already owns them for the chat's duplicate card, so this story lifts the bucket table into one shared helper there and adds a compact renderer beside the existing long one — one set of thresholds, two spellings. No file under `app/` is touched, and no Reflex API is used.

## User Story

As an integrating developer
I want every displayed value on a register row computed once in Python when the row is built
So that components read plain fields instead of computing over Reflex Vars (PRD Section 6, "derived-once row model").

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-002-verdict-derivation-formatting.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 6 (verdict derivation table, derived-once row model), Section 6.1 (the time column and the `—` absent-value mark in the register mockup), Section 12 Phase 1, Risk 2, Risk 3

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/` (one new module, one refactored helper), `tests/` (one new test file) |
| Story | STORY-002 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

**Dependency check**: `depends_on: [STORY-001]` — STORY-001 is `status: done`, commit `577a285`, `chat_ui/chat_ui/admin_models.py` present on the branch. Cleared to proceed.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `reflex-docs` (**NOT AVAILABLE**) | `chat_ui/AGENTS.md` mandates it for any Reflex API used. **This story uses none** — `admin_formatting.py` imports only `datetime` and the two plain models. See the note below. | none |
| `reflex-process-management` (**NOT AVAILABLE**) | `chat_ui/AGENTS.md` mandates it for any compile/run/reload cycle. **This story needs none** — nothing renders, so validation is `pytest` only. | none |
| `.agents/skills/frontend-design` | Read in full. It governs visual and structural decisions; this module renders nothing. Two of its *copy* rules do bind the strings this module emits — see below. | Task 2 |

**Skill availability.** `reflex-docs` and `reflex-process-management` ship in the `reflex-dev/agent-skills` Claude Code *plugin*, which is not installed here (`~/.claude/plugins` absent; `.agents/skills/` holds only `frontend-design`). Same gap as STORY-001, same resolution: verify against the installed package rather than from memory. This story needs no such verification, because it touches no Reflex API — the deliberate consequence of PRD Section 6 putting the computation in plain Python. `/implement` must not import `reflex` into `admin_formatting.py`; the module must stay importable without it, exactly as `admin_models.py` is (STORY-001 report: "pulls in neither `reflex` nor `app`" — note this story does add a light `app.db.models` import, see Risk 4 below).

**`frontend-design` rules that do bind Task 2.** The module emits three literal display strings (the absent-value mark, the share placeholder, the truncation ellipsis). The skill's copy section applies: *"let each element do exactly one job"* and *"being specific is always better than being clever"*. Hence a single `—` for "this column has no value on this row", reused rather than varied per column, and no invented prose in a data cell.

---

## Patterns to Follow

### Pure-Python formatting module, computed in the backend

```python
# SOURCE: chat_ui/chat_ui/formatting.py:1-8
"""Pure-Python formatting helpers for chat_ui bubbles.

These run in the backend when a message is built, never at component render
time: component functions receive Reflex Vars (JS references), not concrete
values, so Python control flow (`if`, `try`, datetime math) cannot be applied
to them. Anything needing real Python is computed here and stored on the
ChatMessage as a plain string field.
"""
```

### Relative time — the thresholds that already exist

```python
# SOURCE: chat_ui/chat_ui/formatting.py:20-33
def _humanize(seconds: int) -> str:
    if seconds < 1:
        return "just now"
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''} ago"
    if seconds < 3600:
        m = seconds // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if seconds < 86400:
        h = seconds // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = seconds // 86400
    return f"{d} day{'s' if d != 1 else ''} ago"
```

`tests/test_copy.py:87-107` pins this function **by name** at every unit boundary, and `test_copy.py` is on PRD Section 15's "must pass unmodified" list. The refactor in Task 1 therefore keeps `_humanize` as a symbol with byte-identical output.

### Degrade, never raise, on a bad timestamp

```python
# SOURCE: chat_ui/chat_ui/formatting.py:36-59
    if not first_query_at:
        return DUPLICATE_FALLBACK_TEXT, ""
    try:
        dt = datetime.fromisoformat(first_query_at.replace("Z", "+00:00"))
        ...
    except Exception:
        return DUPLICATE_UNPARSEABLE_TEMPLATE.format(absolute=first_query_at), ""
```

### `pii_entities` parsing — the existing format, not a second one

```python
# SOURCE: app/routers/admin.py:40
            pii_entities=log.pii_entities.split(",") if log.pii_entities else [],
```

Confirmed against the writer: `app/services/audit_logger.py:43` stores `",".join(pii_entities) if pii_entities else None` — comma, no space. `app/db/database.py:214` splits the same way. Three call sites, one format.

### Share formatting — the shape `/stats` already returns

```python
# SOURCE: app/routers/admin.py:57
    success_rate = f"{(successful / total * 100):.1f}%" if total > 0 else "0.0%"
```

One decimal place and a trailing `%`. `format_share` matches the *number* format exactly so the console and `curl /stats` never disagree on rounding — but **not** the `total == 0` arm, which returns a placeholder rather than the false `"0.0%"` (AC 5; see decision 5).

### Typed model construction with every field named

```python
# SOURCE: chat_ui/chat_ui/admin_models.py:29-56
class AuditRow(pydantic.BaseModel):
    audit_id: int = 0
    timestamp_absolute: str = ""
    timestamp_relative: str = ""
    ...
```

### Test file style — module docstring states what the file is defending

```python
# SOURCE: tests/test_admin_models.py:1-18
"""The admin row model's missing fields are the feature.
...
"""
import sys
from pathlib import Path

# Repo root, not chat_ui/ — putting the inner package on sys.path[0] shadows
# the namespace package every other test module imports through.
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.models import AuditLog
from chat_ui.chat_ui.admin_models import AuditRow, SummaryFigure
```

---

## Design Decisions

1. **Verdict precedence is a total order over overlapping conditions, not a set of independent flags.** A row can be duplicate-blocked *and* pattern-flagged *and* failed. PRD Section 6's table is read top-to-bottom: `was_duplicate_blocked` → **held**, then `suspicious_pattern is not None` → **denied**, then `success` falsy → **fault**, else **cleared**. Implemented as sequential early returns — the only structure in which the precedence is visible in the code — with the ordering stated in a module comment (AC 2). Justification for `held` winning over `denied`: `app/services/query_pipeline.py:33-39` returns at the duplicate check *before* `detect_suspicious_pattern` runs at line 42, so a duplicate-blocked row never has a pattern recorded by the current pipeline; the precedence makes the console deterministic anyway, for legacy rows and for any future reordering.

2. **`derive_verdict` never reads `model_used`** (AC 6, Risk 3). Verified in the pipeline rather than taken on trust: `app/services/query_pipeline.py:91-93` logs `model_used=openrouter_result.model_used` together with `success=False` on the output-side `PiiRedactorError` arm, so a model *is* recorded on an internal fault. The reasoning goes in a module comment above `derive_verdict` so the "improvement" is not reintroduced. A dedicated test constructs exactly that row (`success=False`, `model_used="gpt-4"`) and asserts **fault**.

3. **The four verdicts are module constants** (`VERDICT_CLEARED`, `VERDICT_HELD`, `VERDICT_DENIED`, `VERDICT_FAULT`) plus a `VERDICTS` tuple in display order. STORY-011's `rx.match` keys, STORY-013's filter values and STORY-006's assertions all import these rather than repeating string literals. They are *values*, not user-facing copy, so they stay here and do **not** move to `admin_copy.py` (STORY-008) — the register's human-readable tag text (`DENIED` vs `cleared` casing, per the Section 6.1 mockup) is copy and belongs there.

4. **Relative time: one threshold table, two renderings.** The story requires reuse rather than "a second implementation with different thresholds", and the register needs `"2m ago"` (Section 6.1 mockup) while the chat needs `"2 minutes ago"` (`copy.py:78`, pinned by `test_copy.py`). Task 1 extracts the bucket table from `_humanize` into a shared `_bucket(seconds)` in `formatting.py` and adds `humanize_compact(seconds)` beside it; `_humanize` keeps its name, signature and exact output. **Verified equivalence**: the refactored `_humanize` was run against all ten parametrized cases from `tests/test_copy.py:88-99` in a scratch script — all pass; `humanize_compact` yields `just now / 1s / 45s / 1m / 2m / 1h / 2h / 1d / 2d ago`. This is the one deviation from PRD Section 6's file list, which does not mark `formatting.py` as CHANGED — see Risk 1.

5. **`format_share(count, total)` returns `SHARE_UNDEFINED = "—"` when `total == 0`**, not `"0.0%"`. `app/routers/admin.py:57` returns `"0.0%"` for the empty table, which asserts that 0% of queries succeeded when in truth nothing has been recorded — the exact class of overstatement PRD Risk 4 is about. The register's own absent-value mark is the honest answer. `format_share` also guards `count` and `total` being `None` and a negative `total`, all through the same placeholder, so it can never raise into a page render.

6. **One absent-value mark, `VALUE_ABSENT = "—"` (em dash).** The Section 6.1 mockup uses `—` in both the model and the token columns of a denied row. Used for `model_used`, `tokens_used`, `device_short`/`device_full`, `error_message`, `suspicious_pattern` and `prompt_hash` when the source column is NULL. This is why `AuditRow` types those as `str` and not `Optional[...]` (STORY-001: "`Optional[int]` would force an `rx.cond` over None at render, which is exactly what the derived-once rule forbids").

7. **`to_audit_row` names every field explicitly and reads no preview attribute** (AC 4). Construction is a single `AuditRow(...)` call with one keyword per field; `prompt_preview`/`response_preview` appear nowhere in the module. There is no `**log.__dict__` shortcut and no field-copy loop — a projection that enumerates its fields is the mitigation. `tests/test_admin_models.py:120+` already proves this in miniature for a hand-built row; the new test proves it for the real function, including a source `AuditLog` carrying distinctive preview text that must appear nowhere in the produced row's dump.

8. **Device truncation: `DEVICE_TRUNCATE_LENGTH = 32`, ellipsis `…`, full string preserved.** User-Agent strings run 100–150 characters and would blow out a fixed-width monospace column; the disclosure (STORY-012) shows `device_full`. Truncation happens only when it buys something — a string of exactly 32 characters is left alone rather than becoming 31 characters plus an ellipsis.

9. **`now` is an explicit parameter** typed `datetime | None = None`, defaulting to `datetime.now(timezone.utc)`. The AC calls `to_audit_row(log, now)`; the default exists so STORY-004 can call it in a loop without repeating the clock read, and the parameter exists so tests are deterministic. A naive `now` would raise on subtraction with the parsed aware timestamp — that raise is caught by the same degrade arm as an unparseable timestamp (decision 10), so a caller's mistake yields a placeholder, never a 500 on the page.

10. **A bad timestamp degrades, matching `format_duplicate_info`.** Missing → `VALUE_ABSENT` for both the relative and absolute cells. Unparseable → the raw string as `timestamp_absolute` (it is still evidence) and `VALUE_ABSENT` as the relative. A future timestamp (clock skew) gives negative seconds, which the existing `< 1` arm already renders as `"just now"`.

11. **Tests live at `tests/test_admin_formatting.py`**, following the repo's flat `tests/` layout and `test_admin_models.py`'s `sys.path` preamble. There is no `tests/test_formatting.py` — the chat's formatting is tested inside `tests/test_copy.py` — but that file is pinned as unmodifiable by PRD Section 15, so the new `humanize_compact` is covered in the new file instead.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/formatting.py` | UPDATE | Extract the relative-time bucket table into `_bucket`; add `humanize_compact` for the register's `"2m ago"`. `_humanize` output unchanged. |
| `chat_ui/chat_ui/admin_formatting.py` | CREATE | Verdict constants + `derive_verdict`, `to_audit_row`, `format_share`, the display placeholders and the private helpers. |
| `tests/test_admin_formatting.py` | CREATE | The four verdicts, the precedence, Risk 3, the preview absence at the boundary, `format_share` at `total == 0`, the relative-time and device formatting. |

Files explicitly **not** changed: anything under `app/`, `chat_ui/chat_ui/admin_models.py`, `chat_ui/chat_ui/copy.py`, and every file in PRD Section 15's pinned list.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Share the relative-time thresholds instead of duplicating them

- **File**: `chat_ui/chat_ui/formatting.py`
- **Action**: UPDATE
- **Implement**:
  - Add a module-level bucket table and a `_bucket(seconds: int) -> tuple[int, str, str]` helper returning `(count, long_unit, short_unit)`:
    ```python
    # One threshold table, two spellings. The chat's duplicate card reads
    # "2 minutes ago"; the admin register's time column is a monospace cell
    # and reads "2m ago" (PRD-006 Section 6.1). They must never drift into
    # two different ideas of when an hour becomes a day.
    _BUCKETS = (
        (60, 1, "second", "s"),
        (3600, 60, "minute", "m"),
        (86400, 3600, "hour", "h"),
    )
    ```
    with the day case as the fallthrough (`seconds // 86400, "day", "d"`).
  - Rewrite `_humanize` over `_bucket`, keeping the `< 1 → "just now"` arm first and the exact same output string.
  - Add `humanize_compact(seconds: int) -> str` — public, since another module imports it — returning `"just now"` or `f"{n}{short_unit} ago"`.
- **Mirror**: `chat_ui/chat_ui/formatting.py:20-33` — the thresholds and the `< 1` arm come from there verbatim.
- **Do not**: rename `_humanize`, change its output, or touch `format_duplicate_info`. `tests/test_copy.py:105` imports `_humanize` by that exact name and is pinned unmodifiable.
- **Validate**: `python -m pytest tests/test_copy.py -q` → all pass, file unmodified (`git diff --stat -- tests/test_copy.py` empty).

### Task 2: Create `admin_formatting.py`

- **File**: `chat_ui/chat_ui/admin_formatting.py`
- **Action**: CREATE
- **Implement**, in this order:
  1. **Module docstring** stating the derived-once rule in `formatting.py`'s voice (Vars, not values), naming PRD Section 6 and the fact that this module is the boundary at which the previews are dropped (Risk 2).
  2. **Verdict constants + precedence comment** (AC 2):
     ```python
     VERDICT_CLEARED = "cleared"
     VERDICT_HELD = "held"
     VERDICT_DENIED = "denied"
     VERDICT_FAULT = "fault"
     VERDICTS = (VERDICT_CLEARED, VERDICT_HELD, VERDICT_DENIED, VERDICT_FAULT)
     ```
     Above them, the precedence as a comment: a row may satisfy several conditions at once, so the order is fixed — held, denied, fault, cleared — and two rows with identical fields therefore never render differently.
  3. **Display placeholders**: `VALUE_ABSENT = "—"`, `SHARE_UNDEFINED = "—"` (defined separately even though equal today: one is a NULL column, the other an undefined ratio, and STORY-008 may re-home only the latter), `DEVICE_TRUNCATE_LENGTH = 32`, `DEVICE_ELLIPSIS = "…"`.
  4. **`derive_verdict(log: AuditLog) -> str`** — sequential early returns in PRD Section 6's table order. Above it, the Risk 3 comment, verbatim from the PRD: *"The obvious way to separate an upstream failure from an internal one is to check whether a model was recorded — and it is wrong, because the output-side `PiiRedactorError` arm logs one"*, with the `app/services/query_pipeline.py:91-93` citation and the instruction that `model_used` must never appear in this function.
  5. **`format_share(count: int, total: int) -> str`** — `SHARE_UNDEFINED` when `total` is falsy, `None` or negative, or when `count` is `None`; otherwise `f"{count / total * 100:.1f}%"`, matching `app/routers/admin.py:57`.
  6. **Private helpers**: `_parse_pii_entities(raw)` (mirror `app/routers/admin.py:40`, dropping empty segments), `_truncate_device(device)` → `(short, full)`, `_format_timestamps(raw, now)` → `(relative, absolute)` with the degrade arms from decision 10, `_text(value)` → the value or `VALUE_ABSENT`.
  7. **`to_audit_row(log: AuditLog, now: datetime | None = None) -> AuditRow`** — one `AuditRow(...)` call naming all 16 fields. `audit_id=log.id or 0`; `tokens_used` formatted as `str(log.tokens_used)` or `VALUE_ABSENT` (note `0` is a real value and must not fall to the placeholder); `pii_indicator=bool(log.pii_detected_input or log.pii_detected_output)`; `verdict=derive_verdict(log)`.
- **Mirror**: `chat_ui/chat_ui/formatting.py:1-8` (module voice + backend-computation rule), `app/routers/admin.py:40` (entity parsing), `app/routers/admin.py:57` (share number format), `chat_ui/chat_ui/admin_models.py:29-56` (the field list, in the model's own order).
- **Do not**: import `reflex`; reference `prompt_preview` or `response_preview` anywhere; branch on `model_used` inside `derive_verdict`.
- **Validate**:
  ```bash
  python -c "from chat_ui.chat_ui.admin_formatting import to_audit_row, derive_verdict, format_share; print(format_share(3, 0), format_share(13, 100))"
  grep -n "preview" chat_ui/chat_ui/admin_formatting.py   # only inside the docstring explaining the absence
  ```

### Task 3: Write `tests/test_admin_formatting.py`

- **File**: `tests/test_admin_formatting.py`
- **Action**: CREATE
- **Implement** — one test per acceptance criterion, plus the boundaries:
  - `test_each_verdict_derives_from_its_condition` — four `AuditLog`s, one per verdict (AC 1).
  - `test_verdict_precedence_is_deterministic_when_conditions_overlap` — duplicate + pattern → `held`; duplicate + pattern + `success=False` → `held`; pattern + `success=False` → `denied` (AC 2).
  - `test_fault_does_not_branch_on_model_used` — `success=False` with `model_used="gpt-4"` → `fault`, and with `model_used=None` → `fault` (AC 6, Risk 3).
  - `test_to_audit_row_populates_every_field` — relative `"2m ago"`, absolute preserved, both device strings, `pii_indicator` true from either side alone, `pii_entities == ["EMAIL_ADDRESS", "PHONE_NUMBER"]` from the stored `"EMAIL_ADDRESS,PHONE_NUMBER"` (AC 3).
  - `test_to_audit_row_carries_no_preview_value` — source log with `prompt_preview="SECRET-PROMPT"` / `response_preview="SECRET-RESPONSE"`; assert neither string appears in `row.model_dump()` rendered to text, and no attribute exists (AC 4).
  - `test_format_share_placeholder_and_value` — `format_share(3, 0)` returns `SHARE_UNDEFINED` and does not raise; `format_share(13, 100) == "13.0%"`; `format_share(1, 3) == "33.3%"` (AC 5).
  - `test_relative_time_compact_at_every_boundary` — parametrized over the same boundaries `tests/test_copy.py:88-99` pins for the long form.
  - `test_missing_and_unparseable_timestamp_degrade` — no raise, placeholder relative, raw string kept as absolute.
  - `test_null_columns_render_the_absent_mark` and `test_tokens_used_zero_is_not_the_absent_mark`.
  - `test_verdict_constants_are_the_registers_four` — `VERDICTS` set equality, guarding STORY-011/013 against a fifth arriving silently.
- **Mirror**: `tests/test_admin_models.py:1-20` (docstring + `sys.path` preamble + import style), `tests/test_copy.py:87-107` (parametrized boundary table).
- **Validate**: `python -m pytest tests/test_admin_formatting.py -q` → all pass.

### Task 4: Prove the blast radius

- **File**: — (verification only)
- **Action**: verify
- **Implement**: run the full suite, confirm no pinned test file and no `app/` file moved.
- **Validate**:
  ```bash
  python -m pytest tests/ -q                                    # 270 + the new tests, 0 failures
  git status --short                                            # only the 3 files in the table above
  git diff --stat -- app/                                       # empty
  git diff --stat -- tests/test_admin_auth.py tests/test_audit_router.py tests/test_stats_router.py tests/test_db.py tests/test_route_reservations.py tests/test_chat_state.py tests/test_copy.py tests/test_contrast.py   # empty
  ```
- **Note**: importing the `chat_ui` package can make Reflex rewrite `chat_ui/reflex.lock/`, `bun.lock` and `package.json` (STORY-001 report, Deviation 5). That is an interpreter side effect, not part of this story — `git checkout --` those paths and keep them out of the commit.

---

## End-to-End Tests

No page renders in this story; the "end to end" here is the boundary from a database row to a register row.

- [ ] Construct an `AuditLog` matching each row in PRD Section 6's verdict table → `derive_verdict` returns `held` / `denied` / `fault` / `cleared` respectively.
- [ ] Round-trip real rows: `python -c "from app.db.database import list_audit_logs; from chat_ui.chat_ui.admin_formatting import to_audit_row; print([to_audit_row(l) for l in list_audit_logs(limit=5)])"` against the repo's `harness_ai.db` → prints five populated `AuditRow`s, no exception, no preview text in the output.
- [ ] `format_share(count, total)` over a summary's worth of numbers → each is a `"NN.N%"` string, and `total=0` yields the placeholder rather than a traceback.
- [ ] `python -m pytest tests/test_copy.py -q` → the chat's duplicate card still reads `"2 minutes ago"`, unchanged by the shared-threshold refactor.

---

## Validation

```bash
python -m pytest tests/test_admin_formatting.py tests/test_admin_models.py tests/test_copy.py -q
python -m pytest tests/ -q
python -c "import chat_ui.chat_ui.admin_formatting; import sys; assert 'reflex' not in sys.modules, 'admin_formatting must not pull in reflex'"
git diff --stat -- app/    # must be empty
```

No frontend lint step applies (`chat_ui` is Reflex/Python, no JS package) and no backend start is needed — this story adds no route, component or FastAPI wiring.

---

## Acceptance Criteria

(Copied from story `STORY-002`)

- [ ] Given `chat_ui/chat_ui/admin_formatting.py`, when `derive_verdict(log)` is called with an `AuditLog`, then it returns exactly one of `cleared`, `held`, `denied`, `fault`, following PRD Section 6's table in that precedence: `was_duplicate_blocked` → **held**, `suspicious_pattern is not None` → **denied**, `success = 0` → **fault**, otherwise **cleared**.
- [ ] Given a row that is both duplicate-blocked and pattern-flagged, when the verdict is derived, then the outcome is deterministic and the precedence is stated in a module comment, so two rows with identical fields never render differently.
- [ ] Given an `AuditLog`, when `to_audit_row(log, now)` is called, then it returns a fully-populated `AuditRow` with the relative time ("2m ago"), the absolute timestamp, the truncated and full device strings, the combined PII indicator (`pii_detected_input or pii_detected_output`) and `pii_entities` parsed from its stored TEXT form into `list[str]`.
- [ ] Given `to_audit_row`, when the returned object is inspected, then neither preview value from the source `AuditLog` is present on it.
- [ ] Given `format_share(count, total)`, when `total` is 0, then it returns a defined placeholder rather than raising `ZeroDivisionError`; when `total` is non-zero it returns the share of `total_queries` the summary renders beside each blocked count.
- [ ] Given a failed row that also carries a `model_used` value, when `derive_verdict` runs, then the verdict is still **fault** — the function never branches on `model_used` (Risk 3).
- [ ] All tasks completed
- [ ] Backend/app untouched: `git diff --stat -- app/` empty
- [ ] Full suite passes; PRD Section 15's eight pinned test files unmodified
- [ ] Follows existing patterns (`chat_ui/chat_ui/formatting.py`, `chat_ui/chat_ui/admin_models.py`, `app/routers/admin.py`)

---

## Risks & Mitigations

1. **Touching `formatting.py` is a deviation from PRD Section 6's file list**, which marks only `chat_ui.py`, `theme.py` and the new admin modules as changed. *Mitigation*: the story text overrides it explicitly — *"reuse or lift that helper rather than writing a second implementation with different thresholds"* — and the change is additive: one extracted private helper, one new public function, `_humanize` byte-identical and pinned green by an unmodified `tests/test_copy.py`. The alternative (importing the private `_humanize` and string-rewriting its output, or copying the thresholds) is what the story forbids.
2. **The precedence could be re-derived "more cleanly" later** as independent flags or a dict lookup, losing the order. *Mitigation*: sequential returns, the order stated in a module comment (AC 2), and an overlap test that fails if the order changes.
3. **Risk 3 reintroduced by a well-meaning refactor.** *Mitigation*: the PRD's sentence quoted verbatim in a comment above `derive_verdict`, plus `test_fault_does_not_branch_on_model_used`.
4. **`admin_formatting.py` imports `app.db.models`**, where `admin_models.py` deliberately imports nothing. *Mitigation*: acceptable and intended — this module's job is to consume `AuditLog`, and PRD Section 6 names the in-process read of `app/db/` as the console's architecture. `app/db/models.py` imports only `dataclasses` and `typing`, so it pulls in no FastAPI, no config and no database connection. Keep it a direct import (`from app.db.models import AuditLog`) rather than a `TYPE_CHECKING` guard, so a shape change fails loudly at import.
5. **Legacy rows with a non-ISO timestamp** (older fixtures, hand-inserted rows). *Mitigation*: decision 10's degrade arm, tested.
