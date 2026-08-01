---
story: STORY-004
prd: PRD-003
slug: audit-logger-pii-telemetry
title: "Audit logger records PII telemetry (raw preview unchanged)"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-003-pii-redaction        # all stories commit here, no per-story branch
created: 2026-07-31
---

# Plan: Audit logger records PII telemetry (raw preview unchanged)

## Summary

Extend `log_query()` in `app/services/audit_logger.py` with three optional parameters — `pii_detected_input: bool = False`, `pii_detected_output: bool = False`, `pii_entities: Optional[list[str]] = None` — and pass them through to the `AuditLog` columns [[STORY-003]] already added, joining the entity list into the comma-separated string that column expects. This is the thin write-side bridge between the redactor (which produces `list[str]`) and the DB layer (which stores `Optional[str]`); it is the *only* place in the codebase that owns that join.

Everything else about the function is deliberately frozen: `prompt_hash`, `prompt_preview`, `response_hash`, and `response_preview` (lines 28-31) keep deriving from the **raw** `prompt`/`response` arguments, which is the explicit "audit log stays raw" decision in PRD Section 9 / RF-7. `log_query()` gains no Presidio import and no knowledge of how the booleans were computed — it accepts already-decided values, keeping the adapter boundary in `pii_redactor.py` intact (PRD Section 6, adapter pattern). All three parameters are appended last with defaults, so the four existing call sites in `app/services/query_pipeline.py` (lines 29, 43, 58, 68) and the whole existing `tests/test_audit_logger.py` suite keep working byte-for-byte unmodified.

## User Story

As a compliance admin
I want `log_query()` to record whether PII was detected on the input/output and which entity types, while still storing the raw unmasked previews
So that I can investigate what was actually attempted, not just that "something" was masked (PRD Section 4, User Story 3, RF-7, RF-8)

## Story Reference

- Story file: `.agents/stories/PRD-003-pii-redaction/STORY-004-audit-logger-pii-telemetry.md`
- PRD: `.agents/PRDs/PRD-003-pii-redaction/PRD.md` — Section 6 (Changes to existing modules — `app/services/audit_logger.py`), Section 9 (Why the audit log stays raw), Section 10 (`GET /audit` additions), User Story 3

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `app/services/audit_logger.py`, `tests/test_audit_logger.py` |
| Story | STORY-004 |
| PRD | PRD-003 |
| Epic Branch | `epic/PRD-003-pii-redaction` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` does not exist in this repository (confirmed by directory listing — `ls .agents/skills/` returns nothing), the story's `skills:` frontmatter field is `[]`, and PRD Section 15 states this explicitly ("Skills referenced: None"). Same finding as the [[STORY-001]], [[STORY-002]], and [[STORY-003]] plans.

---

## Patterns to Follow

### Optional parameters appended last, all defaulted

```python
# SOURCE: app/services/audit_logger.py:12-23
def log_query(
    user_id: str,
    prompt: str,
    device: Optional[str] = None,
    response: Optional[str] = None,
    model_used: Optional[str] = None,
    tokens_used: Optional[int] = None,
    was_duplicate_blocked: bool = False,
    suspicious_pattern: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None,
) -> int:
```

Two required positional params, then every optional param with a default. `bool` params default to their "nothing happened" value (`was_duplicate_blocked: bool = False`); nullable params default to `None`. New params go **after `error_message`**, which mirrors how [[STORY-003]] appended the same three fields to the `AuditLog` dataclass and the SQL table.

### Inline conditional for "derive only when the source is present"

```python
# SOURCE: app/services/audit_logger.py:30-31
        response_hash=hash_prompt(response) if response is not None else None,
        response_preview=response[:_PREVIEW_LENGTH] if response is not None else None,
```

This file already expresses "transform-or-`None`" as an inline conditional directly inside the `AuditLog(...)` construction rather than a helper. The `list[str]` → `"A,B"` join follows the identical shape (see Design Note 3).

### Raw-text derivation that must NOT change

```python
# SOURCE: app/services/audit_logger.py:28-31
        prompt_hash=hash_prompt(prompt),
        prompt_preview=prompt[:_PREVIEW_LENGTH],
        response_hash=hash_prompt(response) if response is not None else None,
        response_preview=response[:_PREVIEW_LENGTH] if response is not None else None,
```

These four lines are the subject of AC3 and PRD Section 9. They must be left **byte-for-byte identical**. `git diff app/services/audit_logger.py` must show zero changes on lines 28-31.

### Comma-joined entity storage format (the inverse of this join)

```python
# SOURCE: app/config.py:20-22
    @property
    def pii_entities_list(self) -> list[str]:
        return [item.strip() for item in self.PII_ENTITIES.split(",") if item.strip()]
```

The codebase's existing convention for an entity-type list in a single string is bare comma-joined, no spaces, no JSON. [[STORY-003]]'s plan (Design Note 1) pinned `pii_entities` to this same format and left the join to this story.

### Entity list producer (what will be handed in)

```python
# SOURCE: app/services/pii_redactor.py:73-74
    entities_found = sorted({result.entity_type for result in results})
    return anonymized.text, entities_found
```

`redact()` already returns a de-duplicated, sorted `list[str]` — and `[]` (not `None`) when nothing is found or redaction is disabled. This is what [[STORY-006]] will combine and pass in, and it is why `log_query()` does not need to sort or dedupe (Design Note 2).

### Tests: temp-DB fixture + write-then-read-back assertion

```python
# SOURCE: tests/test_audit_logger.py:18-23
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```

```python
# SOURCE: tests/test_audit_logger.py:26-52
def test_success_case_writes_expected_row(temp_db):
    audit_id = log_query(
        user_id="juan@empresa.com",
        prompt="hello",
        ...
    )

    fetched = get_audit_log(audit_id)

    assert fetched is not None
    assert fetched.prompt_preview == "hello"
    assert fetched.was_duplicate_blocked is False
```

Every test takes `temp_db`, calls `log_query(...)`, fetches with `get_audit_log(audit_id)`, then asserts field-by-field on the persisted row. Booleans are asserted with `is True` / `is False` (identity, not truthiness) — that is what proves the `int()`→`bool()` conversion at the DB boundary rather than a raw `1`/`0` leaking through.

### Tests: raw-text guarantee assertion style

```python
# SOURCE: tests/test_audit_logger.py:42-45
    assert fetched.prompt_hash == hash_prompt("hello")
    assert fetched.prompt_preview == "hello"
    assert fetched.response_hash == hash_prompt("hi there")
    assert fetched.response_preview == "hi there"
```

Previews/hashes are asserted against the literal input text and against `hash_prompt(...)` recomputed from that same raw text. The new AC3 test reuses this exact shape with PII-bearing text.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/audit_logger.py` | UPDATE | Add 3 optional params to `log_query()`; pass them to `AuditLog(...)`, joining `pii_entities` to a comma-separated string |
| `tests/test_audit_logger.py` | UPDATE | Add tests for: values persisted (AC1), defaults when omitted (AC2), raw previews with PII-bearing text (AC3), empty-list → `None`, order preserved |

**Explicitly NOT touched:**

- `app/services/pii_redactor.py` — no import from here; `log_query()` must stay Presidio-unaware (story Technical Notes line 40, PRD Section 6 adapter pattern)
- `app/services/query_pipeline.py` — wiring the new params is [[STORY-005]]/[[STORY-006]]'s scope. This story only makes the parameters *available*; nothing calls them yet
- `app/services/duplicate_checker.py` — untouched, and `hash_prompt(prompt)` keeps being called on raw text (PRD Section 9, RF-6)
- `app/db/models.py`, `app/db/database.py` — already done in [[STORY-003]]; this story stores into columns that exist
- `app/routers/admin.py`, `app/models/schemas.py` — reading these fields back out is [[STORY-009]]'s scope
- Lines 28-31 of `audit_logger.py` — the raw preview/hash derivation (AC3)

---

## Design Notes (decisions worth stating up front)

1. **Empty/absent entity list is stored as `None`, not `""`.** [[STORY-003]]'s report explicitly deferred this decision to this story ("An empty list should join to `""`, not `None` — decide explicitly ... since STORY-009's split needs to handle whichever is chosen"). **Decision: `None`.** Rationale: (a) it makes the column behave exactly like `suspicious_pattern` — `NULL` means "nothing to report" — which is the pattern the column was modeled on; (b) [[STORY-009]]'s read side must split the column, and `"".split(",")` returns `[""]`, a one-element list of an empty string that would silently pollute `top_pii_entities`, whereas `None` is unambiguously "skip this row"; (c) it makes the no-PII row indistinguishable from a pre-[[STORY-003]] row, so historical rows and new no-PII rows read identically. The implementation is `",".join(pii_entities) if pii_entities else None`, so both `None` and `[]` land as `None` — a single truthiness test covers the two "nothing detected" shapes `redact()` and the default can produce.

2. **`log_query()` does not sort, dedupe, or validate the entity list.** It joins exactly what it is handed, in the order given. Rationale: `pii_redactor.redact()` already returns `sorted({...})` (`pii_redactor.py:73`), and [[STORY-006]]'s Technical Notes (line 40) explicitly assign de-duplication of the combined input+output list to the *caller*. Adding a second dedupe here would duplicate that contract in two places and, worse, would silently reorder the caller's list — AC1 says the values passed in are "persisted", which reads most literally as store-what-you-were-given. A test pins order preservation so a later "helpful" `sorted()` cannot creep in unnoticed.

3. **Inline conditional, not a `_join_entities()` helper.** The file already expresses transform-or-`None` inline inside the `AuditLog(...)` constructor (lines 30-31), and the module's only other private members are two constants. A one-line join does not earn a helper, and inlining keeps the whole "what gets written" story readable in one construction block. The inverse operation (split) deliberately lives in [[STORY-009]]'s read layer, not here — the two directions are owned by the layers that need them, exactly as [[STORY-003]] structured it.

4. **`Optional[list[str]]`, not `Optional[List[str]]`.** `app/config.py:21` already uses the builtin generic `list[str]`, and this file imports only `Optional` from `typing` (line 2). No import change is needed. (`pii_redactor.py` uses `typing.List` because its `Tuple` return annotation was written in that style; `audit_logger.py` follows `config.py`.)

5. **The three params are appended after `error_message`, matching [[STORY-003]]'s dataclass ordering.** All four existing call sites in `query_pipeline.py` (lines 29, 43, 58, 68) pass every argument by keyword, so ordering could not break them — but appending keeps the parameter list, the dataclass field order (`models.py:41-44`), and the SQL column order (`models.py:19-22`) reading identically top-to-bottom, which is what makes the three files easy to diff against each other.

6. **Nothing calls the new parameters after this story — that is expected, not incomplete.** [[STORY-005]] captures `input_entities`, [[STORY-006]] captures `output_entities` and wires both into the `log_query()` call. Until then the parameters sit unused with their defaults, and every audit row is written with `pii_detected_input=False`, `pii_detected_output=False`, `pii_entities=None` — i.e. behavior on `main` is bit-identical. The verification for that is AC2 and Task 5's full-suite gate.

7. **Risk: a stale local `harness_ai.db` still lacks the [[STORY-003]] columns.** `init_db()` is `CREATE TABLE IF NOT EXISTS` with no migration framework. [[STORY-003]]'s report confirms the repo-root DB was recreated during that story, so this should already be resolved — but if `uvicorn` startup or a manual `log_query()` raises `sqlite3.OperationalError: table audit_logs has no column named pii_detected_input`, delete `harness_ai.db` and restart. The automated suite is structurally immune: `temp_db` builds a fresh DB under `tmp_path` per test (`tests/test_audit_logger.py:18-23`).

8. **Use `.venv/Scripts/python.exe` for every command in this plan.** [[STORY-003]]'s report (Deviation 1) recorded that bare `python` on this machine resolves to a global Python 3.13 without `presidio-analyzer`, producing 8 collection errors in every module that transitively imports `app.main` → `app.services.pii_redactor`. That is an environment mismatch, not a code defect. All validation commands below are written against the venv interpreter explicitly.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add the three optional parameters to `log_query()`'s signature

- **File**: `app/services/audit_logger.py`
- **Action**: UPDATE
- **Implement**: Append three parameters after `error_message: Optional[str] = None` (line 22), before the closing `) -> int:`:
  ```python
      error_message: Optional[str] = None,
      pii_detected_input: bool = False,
      pii_detected_output: bool = False,
      pii_entities: Optional[list[str]] = None,
  ) -> int:
  ```
  Do not reorder or re-default any existing parameter. No import changes — `Optional` is already imported (line 2) and `list[str]` is a builtin generic.
- **Mirror**: `app/services/audit_logger.py:19-22` — `bool` params default `False`, nullable params default `None`, all optional params trail the two required positionals. Also `app/db/models.py:42-44`, where [[STORY-003]] declared the same three fields in the same order with the same defaults.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -c "import inspect; from app.services.audit_logger import log_query; p = inspect.signature(log_query).parameters; print(list(p)[-3:]); print(p['pii_detected_input'].default, p['pii_detected_output'].default, p['pii_entities'].default)"
  ```
  → prints `['pii_detected_input', 'pii_detected_output', 'pii_entities']` then `False False None`.

### Task 2: Pass the new values into the `AuditLog` construction

- **File**: `app/services/audit_logger.py`
- **Action**: UPDATE
- **Implement**: Add three keyword arguments to the `AuditLog(...)` call after `error_message=error_message` (line 37), before the closing `)`:
  ```python
          error_message=error_message,
          pii_detected_input=pii_detected_input,
          pii_detected_output=pii_detected_output,
          pii_entities=",".join(pii_entities) if pii_entities else None,
      )
      return insert_audit_log(entry)
  ```
  - The booleans pass straight through — `int()` conversion happens at the DB boundary in `insert_audit_log()` (`app/db/database.py`), not here.
  - `",".join(...)` with a bare comma and **no space** — this is the format `settings.pii_entities_list` parses (`app/config.py:22`) and the format [[STORY-003]] pinned.
  - The `if pii_entities else None` guard makes both `None` and `[]` store as `None` (Design Note 1). Do not write `if pii_entities is not None` — that would store `""` for an empty list.
  - **Leave lines 28-31 completely untouched.** `prompt_hash`/`prompt_preview`/`response_hash`/`response_preview` must keep deriving from the raw `prompt`/`response` arguments (AC3, PRD Section 9).
- **Mirror**: `app/services/audit_logger.py:30-31` — inline conditional inside the constructor for transform-or-`None`; `app/config.py:22` — comma-with-no-space entity-list format.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_audit_logger.py -v
  ```
  → all 5 pre-existing tests still pass, **with zero edits to the test file** (this is AC4; the file is not touched until Task 3).
  ```bash
  cd f:/AI/harness-ai && git diff -U0 app/services/audit_logger.py
  ```
  → the diff must contain **only** additions (`+` lines): 3 in the signature, 3 in the constructor. Any `-` line other than the two whose trailing context shifted means something was rewritten that should not have been; in particular no `-` line may touch lines 28-31.

### Task 3: Add tests for the new telemetry fields

- **File**: `tests/test_audit_logger.py`
- **Action**: UPDATE
- **Implement**: Append four new tests at the end of the file. Add **no** new imports — `log_query`, `get_audit_log`, `hash_prompt`, and the `temp_db` fixture are all already in scope (lines 11-13, 18-23). Do **not** modify any of the five existing tests.
  ```python
  def test_pii_telemetry_persisted_when_supplied(temp_db):
      audit_id = log_query(
          user_id="juan@empresa.com",
          prompt="my email is juan@empresa.com",
          response="sure, I'll reply to juan@empresa.com",
          model_used="gpt-4",
          tokens_used=45,
          pii_detected_input=True,
          pii_detected_output=True,
          pii_entities=["EMAIL_ADDRESS", "PERSON"],
      )

      fetched = get_audit_log(audit_id)

      assert fetched is not None
      assert fetched.pii_detected_input is True
      assert fetched.pii_detected_output is True
      assert fetched.pii_entities == "EMAIL_ADDRESS,PERSON"


  def test_pii_telemetry_defaults_when_omitted(temp_db):
      audit_id = log_query(
          user_id="juan@empresa.com",
          prompt="hello",
          response="hi there",
      )

      fetched = get_audit_log(audit_id)

      assert fetched.pii_detected_input is False
      assert fetched.pii_detected_output is False
      assert fetched.pii_entities is None


  def test_empty_entity_list_stored_as_none(temp_db):
      audit_id = log_query(
          user_id="juan@empresa.com",
          prompt="hello",
          pii_detected_input=False,
          pii_detected_output=False,
          pii_entities=[],
      )

      fetched = get_audit_log(audit_id)

      assert fetched.pii_entities is None


  def test_previews_and_hashes_stay_raw_when_pii_detected(temp_db):
      prompt = "my email is juan@empresa.com"
      response = "sure, I'll draft a reply to juan@empresa.com"

      audit_id = log_query(
          user_id="juan@empresa.com",
          prompt=prompt,
          response=response,
          model_used="gpt-4",
          tokens_used=45,
          pii_detected_input=True,
          pii_detected_output=True,
          pii_entities=["EMAIL_ADDRESS"],
      )

      fetched = get_audit_log(audit_id)

      assert fetched.prompt_preview == prompt
      assert fetched.response_preview == response
      assert fetched.prompt_hash == hash_prompt(prompt)
      assert fetched.response_hash == hash_prompt(response)
      assert "<EMAIL_ADDRESS>" not in fetched.prompt_preview
      assert "<EMAIL_ADDRESS>" not in fetched.response_preview
  ```
  - `test_previews_and_hashes_stay_raw_when_pii_detected` is the AC3 guard and the single most important test in this story: it proves that flagging PII does not change what is stored, and that no masked placeholder reached the preview columns.
  - Assert booleans with `is True` / `is False`, never `== True` — identity assertions are what prove the `int()`→`bool()` round-trip.
- **Mirror**: `tests/test_audit_logger.py:26-52` (call `log_query` → `get_audit_log` → field-by-field asserts), `tests/test_audit_logger.py:42-45` (preview/hash asserted against the literal raw text and recomputed `hash_prompt(...)`), `tests/test_db.py:77,79` (`is True` / `is False` identity style).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_audit_logger.py -v
  ```
  → 9 passed (5 pre-existing unmodified + 4 new).

### Task 4: Add an order-preservation test pinning Design Note 2

- **File**: `tests/test_audit_logger.py`
- **Action**: UPDATE
- **Implement**: Append one more test at the end of the file:
  ```python
  def test_entity_list_joined_in_caller_order_without_reordering(temp_db):
      audit_id = log_query(
          user_id="juan@empresa.com",
          prompt="hello",
          pii_detected_input=True,
          pii_entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"],
      )

      fetched = get_audit_log(audit_id)

      assert fetched.pii_entities == "PERSON,EMAIL_ADDRESS,PHONE_NUMBER"
  ```
  The input list is deliberately **not** alphabetical, so a stray `sorted()` added later fails this test loudly. Dedup/ordering is the caller's contract ([[STORY-006]] Technical Notes line 40); this test pins that `log_query()` never second-guesses it.
- **Mirror**: `tests/test_audit_logger.py:55-68` — a short single-assertion test isolating one behavior.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_audit_logger.py -v
  ```
  → 10 passed.

### Task 5: Full-suite regression + changed-file scope check (AC2, AC4)

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - Run the full suite. It must be green with the same count as [[STORY-003]]'s baseline plus this story's 5 new tests (122 → 127).
  - Confirm `git diff --name-only` lists **exactly two** files: `app/services/audit_logger.py` and `tests/test_audit_logger.py`. Anything else — especially `app/services/query_pipeline.py` — means scope leaked into [[STORY-005]]/[[STORY-006]] territory.
  - Confirm `app/services/duplicate_checker.py` is absent from the diff (RF-6, PRD Section 9).
  - Confirm no `-` line in `git diff app/services/audit_logger.py` touches the preview/hash derivation (AC3).
  - Confirm no test in `tests/test_audit_logger.py` was *modified*, only appended to — `git diff tests/test_audit_logger.py` must be additions only (AC4).
- **Mirror**: [[STORY-003]] plan's Task 6 — same "prove the change is invisible to existing callers" gate.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai
  .venv/Scripts/python.exe -m pytest
  git diff --name-only
  git diff --stat tests/test_audit_logger.py
  git diff app/services/audit_logger.py
  ```

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `.venv/Scripts/python.exe -m pytest tests/test_audit_logger.py -v` → 10 passed (5 pre-existing untouched + 5 new)
- [ ] `.venv/Scripts/python.exe -m pytest tests/test_query_router.py tests/test_integration.py tests/test_audit_router.py tests/test_stats_router.py tests/test_chat_state.py -v` → every existing `log_query()` consumer passes **unmodified** (AC2 — the four call sites in `query_pipeline.py` never pass the new args)
- [ ] `.venv/Scripts/python.exe -m pytest` → full suite green, 127 passed
- [ ] `git diff --name-only` → exactly `app/services/audit_logger.py` and `tests/test_audit_logger.py`; `duplicate_checker.py` and `query_pipeline.py` are **not** listed
- [ ] `git diff tests/test_audit_logger.py` → additions only, no modified or deleted lines (AC4)
- [ ] Behavioral proof that the default path is unchanged — write a row the old way and confirm the telemetry columns are inert:
  ```bash
  .venv/Scripts/python.exe -c "from app.services.audit_logger import log_query; from app.db.database import get_audit_log, init_db; init_db(); i = log_query(user_id='e2e', prompt='hello', response='hi'); r = get_audit_log(i); print(r.prompt_preview, r.response_preview, r.pii_detected_input, r.pii_detected_output, r.pii_entities)"
  ```
  → `hello hi False False None`
- [ ] Behavioral proof of the raw-preview guarantee with PII present (AC1 + AC3 against the real DB, not a `tmp_path` fixture):
  ```bash
  .venv/Scripts/python.exe -c "from app.services.audit_logger import log_query; from app.db.database import get_audit_log, init_db; init_db(); i = log_query(user_id='e2e', prompt='my email is juan@empresa.com', response='ok juan@empresa.com', pii_detected_input=True, pii_detected_output=True, pii_entities=['EMAIL_ADDRESS','PERSON']); r = get_audit_log(i); print(repr(r.prompt_preview)); print(repr(r.pii_entities), r.pii_detected_input, r.pii_detected_output)"
  ```
  → prints the **raw** `'my email is juan@empresa.com'` (no `<EMAIL_ADDRESS>` placeholder) and `'EMAIL_ADDRESS,PERSON' True True`.
  Then delete the two E2E rows so the DB is left as found:
  ```bash
  .venv/Scripts/python.exe -c "import sqlite3; c = sqlite3.connect('harness_ai.db'); print(c.execute(\"DELETE FROM audit_logs WHERE user_id='e2e'\").rowcount); c.commit()"
  ```
- [ ] If either command above raises `sqlite3.OperationalError: table audit_logs has no column named pii_detected_input`, the local `harness_ai.db` predates [[STORY-003]] — delete it and re-run (Design Note 7)
- [ ] `.venv/Scripts/python.exe -c "from app.main import app; print('ok')"` → backend imports cleanly
- [ ] `.venv/Scripts/python.exe -m uvicorn app.main:app` → server starts without error; `curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] `curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/audit` → still HTTP 200 with the **same response shape as before** — this story adds no API fields; exposing them is [[STORY-009]]

---

## Validation

```bash
cd f:/AI/harness-ai
.venv/Scripts/python.exe -m pytest tests/test_audit_logger.py -v
.venv/Scripts/python.exe -m pytest
git diff --name-only
git diff app/services/audit_logger.py
.venv/Scripts/python.exe -c "from app.main import app; print('ok')"
.venv/Scripts/python.exe -m uvicorn app.main:app
curl http://localhost:8000/health
```

Frontend lint: N/A — this repo has no npm frontend (Reflex/Python project, no `package.json`), consistent with [[STORY-003]]'s report.

---

## Acceptance Criteria

(Copied from story STORY-004)

- [ ] Given `log_query()` is called with `pii_detected_input=True`, `pii_detected_output=True`, `pii_entities=["EMAIL_ADDRESS", "PERSON"]`, when the audit row is written, then those values are persisted via the new `AuditLog` columns from [[STORY-003]].
- [ ] Given `log_query()` is called without the new PII arguments (existing call sites), when it runs, then it behaves identically to today — defaults to no PII detected, and `prompt_preview`/`response_preview` are computed from the raw text exactly as before.
- [ ] Given `log_query(prompt=..., response=...)` is called, when the audit row is written, then `prompt_preview`/`response_preview`/`prompt_hash`/`response_hash` are still derived from the **raw** prompt/response passed in — this function must never receive already-redacted text for those fields.
- [ ] Given the existing `tests/test_audit_logger.py` suite, when run, then all existing tests pass unmodified.
- [ ] All tasks completed
- [ ] Full test suite (`.venv/Scripts/python.exe -m pytest`) passes
- [ ] Backend server starts without error
- [ ] Lines 28-31 of `app/services/audit_logger.py` (preview/hash derivation) unchanged — verified in the diff
- [ ] No Presidio import in `app/services/audit_logger.py` (adapter boundary intact, PRD Section 6)
- [ ] `app/services/duplicate_checker.py` untouched (PRD Section 9, RF-6)
- [ ] Only `app/services/audit_logger.py` and `tests/test_audit_logger.py` changed
- [ ] Follows existing patterns (optional params appended last with defaults, inline transform-or-`None` conditional in the `AuditLog(...)` constructor, comma-joined entity format matching `app/config.py:22`, `temp_db` fixture and `is True`/`is False` assertions in tests)
