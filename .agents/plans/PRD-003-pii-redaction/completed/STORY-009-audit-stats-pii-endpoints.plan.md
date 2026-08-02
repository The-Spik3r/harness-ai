---
story: STORY-009
prd: PRD-003
slug: audit-stats-pii-endpoints
title: "GET /audit and GET /stats: PII telemetry fields"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-003-pii-redaction        # all stories commit here, no per-story branch
created: 2026-08-02
---

# Plan: GET /audit and GET /stats — PII telemetry fields

## Summary

`app/services/audit_logger.py` and the `audit_logs` schema have carried `pii_detected_input`, `pii_detected_output`, and `pii_entities` since [[STORY-003]]/[[STORY-004]] — every query already writes them. Nothing reads them back out through the admin API yet: `AuditQueryEntry` and `StatsResponse` in `app/models/schemas.py` don't declare the fields, so `app/routers/admin.py`'s `get_audit()`/`get_stats()` silently drop them even though `app/db/database.py` returns fully-populated `AuditLog` rows. This story closes that gap — three new response fields (`pii_detected_input`, `pii_detected_output`, `pii_entities` on `/audit`; `pii_detected_queries`, `top_pii_entities` on `/stats`) and two new aggregate query helpers (`count_pii_detected_queries`, `top_pii_entities`) — with no change to how telemetry is written, only to how it's exposed.

**Scope correction against the story's literal AC wording (read this before Task 1):** AC1 says the new fields go "alongside the existing unchanged `prompt_preview` field." Measured against this branch, that clause is false today — `AuditQueryEntry` has never included `prompt_preview` (see `app/models/schemas.py:41-49`), and `tests/test_audit_router.py:120-146` (`test_response_never_includes_ip_or_raw_text`, from PRD-001) actively asserts `"prompt_preview" not in entry`. Adding `prompt_preview` to `/audit` would require deleting or rewriting that guard test, would contradict the story's own Technical Notes (which list only `pii_detected_input`/`pii_detected_output`/`pii_entities` as the fields to add — no `prompt_preview` mention), and is not something the PRD requires this story to do: PRD Section 10's example JSON is describing target shape loosely, and PRD Section 3's "still needs the raw text available via `/audit`" is satisfied today by the DB row itself (`get_audit_log`, used internally and by [[STORY-010]]'s planned assertions), not by a promise that the *admin HTTP response* must carry it. **Decision: this story adds only the three PII telemetry fields to `AuditQueryEntry`; `prompt_preview`/`response_preview` exposure over `/audit` is out of scope and the existing guard test is left untouched.** This is called out again in Design Notes and must be named in the story report as a deviation from the AC's literal text, not silently resolved.

## User Story

As a compliance admin
I want `/audit` and `/stats` to expose PII redaction telemetry (whether PII was detected, which entity types, and aggregate counts)
So that I can monitor redaction activity without those endpoints exposing the masked values as a new leak surface (PRD Section 10, RF-8)

## Story Reference

- Story file: `.agents/stories/PRD-003-pii-redaction/STORY-009-audit-stats-pii-endpoints.md`
- PRD: `.agents/PRDs/PRD-003-pii-redaction/PRD.md` — Section 10 (`GET /audit`, `GET /stats` additions), RF-8

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/models/schemas.py`, `app/db/database.py`, `app/routers/admin.py`, `tests/test_db.py`, `tests/test_audit_router.py`, `tests/test_stats_router.py` |
| Story | STORY-009 |
| PRD | PRD-003 |
| Epic Branch | `epic/PRD-003-pii-redaction` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` does not exist in this repository (verified — `ls .agents/skills/` returns nothing), the story's `skills:` frontmatter field is `[]`, and PRD Section 15 states it explicitly ("Skills referenced: None"). Same finding as every prior PRD-003 plan.

---

## Dependency Check

| Dependency | Status | Verified |
|---|---|---|
| [[STORY-004]] — Audit logger records PII telemetry (raw preview unchanged) | ✅ done (`1347e53`) | `app/services/audit_logger.py:23-25,41-43` writes `pii_detected_input`/`pii_detected_output`/`pii_entities` on every `log_query()` call; `app/db/models.py:20-22,42-44` and `app/db/database.py:36,55,91-93` already persist and round-trip all three columns |

Single `depends_on` entry is `done` — no blocker, no user confirmation needed. This story `blocks: [STORY-010]` (end-to-end PII integration suite) — [[STORY-010]]'s AC references `GET /audit` returning raw preview fields for assertions unrelated to this story's telemetry fields, so the prompt_preview scope decision above does not block it.

Baseline measured on this branch immediately before planning: **175 passed** (`.venv/Scripts/python.exe -m pytest -q`), matching [[STORY-008]]'s report. Target after this story: **181 passed** (175 + 6 new test functions; see Task breakdown).

---

## Patterns to Follow

### Schema fields already flowing through the pipeline, unread by the admin API

```python
# SOURCE: app/db/models.py:27-45
@dataclass
class AuditLog:
    ...
    pii_detected_input: bool = False
    pii_detected_output: bool = False
    pii_entities: Optional[str] = None   # comma-joined, e.g. "EMAIL_ADDRESS,PERSON"
    id: Optional[int] = None
```

```python
# SOURCE: app/routers/admin.py:24-39 (current — no PII fields read)
def get_audit() -> AuditResponse:
    total = count_audit_logs()
    queries = [
        AuditQueryEntry(
            audit_id=log.id,
            user_id=log.user_id,
            timestamp=log.timestamp,
            model=log.model_used,
            prompt_hash=log.prompt_hash,
            was_duplicate_blocked=log.was_duplicate_blocked,
            suspicious_pattern_detected=log.suspicious_pattern is not None,
            device=log.device,
        )
        for log in list_audit_logs(limit=100)
    ]
    return AuditResponse(total=total, queries=queries)
```

### The comma-join / split convention already proven elsewhere

```python
# SOURCE: app/services/audit_logger.py:43
pii_entities=",".join(pii_entities) if pii_entities else None,
```

```python
# SOURCE: tests/test_query_router.py:571 — the split-back precedent this story mirrors
assert body["pii_entities_masked"] == entry.pii_entities.split(",")
```

`AuditLog.pii_entities` is `None` when no entities were found (not `""`), so the split must guard on falsiness, not just `None` — `entry.pii_entities.split(",") if entry.pii_entities else []`.

### Simple boolean-aggregate query helper

```python
# SOURCE: app/db/database.py:130-135
def count_blocked_suspicious() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_logs WHERE suspicious_pattern IS NOT NULL"
        ).fetchone()
        return row["n"]
```

`count_pii_detected_queries()` follows this shape exactly, with an OR condition (Task 2).

### Ranked-list aggregate helper — and why `top_pii_entities` can't reuse it directly

```python
# SOURCE: app/db/database.py:154-166
def top_models(limit: int = 5) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT model_used FROM audit_logs
            WHERE model_used IS NOT NULL
            GROUP BY model_used
            ORDER BY COUNT(*) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [row["model_used"] for row in rows]
```

`top_models`/`top_users` can `GROUP BY` directly because each row holds exactly one value. `pii_entities` holds a comma-joined *set* of values per row (a single query can carry both `PERSON` and `EMAIL_ADDRESS`), so ranking by raw-column `GROUP BY` would count `"EMAIL_ADDRESS,PERSON"` and `"PERSON,EMAIL_ADDRESS"` as different groups even though they're the same two entities. `top_pii_entities` fetches the raw column and re-aggregates per individual entity in Python (Task 2) — the SQL layer stays a single simple `SELECT`, the counting logic lives where the comma-join is already understood (mirroring how `audit_logger.py` owns the join, this function owns the split).

### Route handlers stay thin — all counting logic lives in `database.py`

```python
# SOURCE: app/routers/admin.py:42-60 (current)
@router.get("/stats", response_model=StatsResponse, dependencies=[Depends(require_admin_token)])
def get_stats() -> StatsResponse:
    total = count_audit_logs()
    successful = count_successful_queries()
    success_rate = f"{(successful / total * 100):.1f}%" if total > 0 else "0.0%"

    return StatsResponse(
        total_queries=total,
        blocked_duplicates=count_blocked_duplicates(),
        blocked_suspicious=count_blocked_suspicious(),
        unique_users=count_unique_users(),
        success_rate=success_rate,
        top_models=top_models(),
        top_users=top_users(),
    )
```

`get_stats()` gains two more keyword args from two more imported helpers — no branching, no new logic in the router itself (Task 3).

### Env-var preamble every test module opens with

```python
# SOURCE: tests/test_audit_router.py:1-4
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```

Must precede any `app.*` import in every test file touched (Tasks 4-6).

### `temp_db` fixture — locally redefined in every test module (no `conftest.py` in this repo)

```python
# SOURCE: tests/test_stats_router.py:17-22
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```

All three test files already define this locally; no shared fixture file to touch or create.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/schemas.py` | UPDATE | Add `pii_detected_input`, `pii_detected_output`, `pii_entities` to `AuditQueryEntry`; add `pii_detected_queries`, `top_pii_entities` to `StatsResponse` |
| `app/db/database.py` | UPDATE | Add `count_pii_detected_queries()` and `top_pii_entities(limit=5)` |
| `app/routers/admin.py` | UPDATE | Import the two new helpers; map the three new `AuditQueryEntry` fields in `get_audit()`; pass the two new `StatsResponse` fields in `get_stats()` |
| `tests/test_db.py` | UPDATE | New tests for the two new query helpers; extend the empty-db aggregate test |
| `tests/test_audit_router.py` | UPDATE | Extend the expected-shape test with the three new keys; new test asserting PII field values round-trip correctly |
| `tests/test_stats_router.py` | UPDATE | Extend the expected-keys assertions (populated + zero-state tests); new test asserting `pii_detected_queries`/`top_pii_entities` aggregate correctly across multi-entity rows |

**Explicitly NOT touched:**

- `app/services/audit_logger.py`, `app/services/query_pipeline.py`, `app/services/pii_redactor.py`, `app/db/models.py` — telemetry is already written correctly by [[STORY-004]]/[[STORY-005]]/[[STORY-006]]; this story only reads it back out
- `prompt_preview`/`response_preview` exposure on `/audit` — explicitly out of scope, see Summary and Design Note 1
- `tests/test_pii_dedup_isolation.py` — [[STORY-008]]'s isolation-proof file, no PII-telemetry-endpoint content belongs there
- `POST /query`'s response shape — that's [[STORY-007]], already done
- `chat_ui/` — the chat UI does not call `/audit` or `/stats`; no consumer to update

---

## Design Notes (decisions worth stating up front)

1. **`prompt_preview` stays out of `/audit`.** See Summary. This is the single most important decision in this plan — it resolves a real contradiction between the story's AC prose and both (a) the current schema and (b) an existing PRD-001 security-motivated test. Do not "fix" `test_response_never_includes_ip_or_raw_text` to make room for `prompt_preview`; that test's purpose (raw text never leaves `/audit` over HTTP) is unrelated to and predates this story, and loosening it is a scope decision no single story should make unilaterally.

2. **`pii_entities` splits to `[]`, never `None`, when nothing was detected.** `AuditLog.pii_entities` is `Optional[str]` and stores `None` for "no entities" (`audit_logger.py:43`). The Pydantic field must be `List[str]` (not `Optional[List[str]]`) so the JSON response always has a list, matching the `pii_entities_masked` convention already shipped on `POST /query` (`schemas.py:21`) rather than introducing a `null` case the client has to special-case.

3. **`top_pii_entities` counts entities, not rows.** A single audit row can list multiple entities (`"EMAIL_ADDRESS,PERSON"`); PRD Section 10's `top_pii_entities` describes "most frequent entity types across all rows," which means each entity in a multi-entity row must count once toward its own tally, not once toward a `"EMAIL_ADDRESS,PERSON"` compound bucket. Verified this is a real hazard, not hypothetical: `audit_logger.py:43` will happily write `"PERSON,EMAIL_ADDRESS"` and `"EMAIL_ADDRESS,PERSON"` for the same underlying pair depending on Presidio's detection order, so a naive `GROUP BY pii_entities` would fragment identical entity sets into different buckets. Task 2's implementation fetches raw rows and tallies with a plain dict in Python — deliberately not `collections.Counter` (no precedent for it elsewhere in this codebase; a plain dict matches the file's existing style, which uses no `collections` imports anywhere in `app/`).

4. **Tie-breaking in `top_pii_entities` is insertion-order, not alphabetical.** Same non-guarantee as `top_models`/`top_users`, which have no secondary `ORDER BY` and thus no defined tie-break either. Tests must use counts that don't tie, mirroring how `test_top_models_ranked_by_count_desc` uses 3-vs-1 rather than 2-vs-2.

5. **`get_audit()`'s existing 100-row cap (`list_audit_logs(limit=100)`) is untouched and applies to the PII fields too.** `count_pii_detected_queries()`/`top_pii_entities()` for `/stats` deliberately query the *whole table*, not the last 100 rows — same as every other `/stats` aggregate (`count_blocked_duplicates`, `top_models`, etc., none of which are capped). This asymmetry (`/audit` capped, `/stats` uncapped) already exists in the codebase today; this story doesn't change or comment on it further, just follows it.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Extend response schemas

- **File**: `app/models/schemas.py`
- **Action**: UPDATE
- **Implement**:

  ```python
  class AuditQueryEntry(BaseModel):
      audit_id: int
      user_id: str
      timestamp: str
      model: Optional[str] = None
      prompt_hash: str
      was_duplicate_blocked: bool
      suspicious_pattern_detected: bool
      device: Optional[str] = None
      pii_detected_input: bool = False
      pii_detected_output: bool = False
      pii_entities: List[str] = []
  ```

  ```python
  class StatsResponse(BaseModel):
      total_queries: int
      blocked_duplicates: int
      blocked_suspicious: int
      unique_users: int
      success_rate: str
      top_models: List[str]
      top_users: List[str]
      pii_detected_queries: int = 0
      top_pii_entities: List[str] = []
  ```

  `List` is already imported at the top of the file (`schemas.py:1`, used by `QuerySuccessResponse.pii_entities_masked`) — no new import needed.
- **Mirror**: `app/models/schemas.py:14-21` (`QuerySuccessResponse.pii_entities_masked: List[str] = []` — identical default-empty-list convention).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -c "from app.models.schemas import AuditQueryEntry, StatsResponse; print(AuditQueryEntry.model_fields.keys()); print(StatsResponse.model_fields.keys())"
  ```
  → both key lists include the new fields; no import error.

### Task 2: Add the two aggregate query helpers

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Append after `top_users` (end of file):

  ```python
  def count_pii_detected_queries() -> int:
      with get_connection() as conn:
          row = conn.execute(
              """
              SELECT COUNT(*) AS n FROM audit_logs
              WHERE pii_detected_input = 1 OR pii_detected_output = 1
              """
          ).fetchone()
          return row["n"]


  def top_pii_entities(limit: int = 5) -> list[str]:
      with get_connection() as conn:
          rows = conn.execute(
              "SELECT pii_entities FROM audit_logs WHERE pii_entities IS NOT NULL"
          ).fetchall()

      counts: dict[str, int] = {}
      for row in rows:
          for entity in row["pii_entities"].split(","):
              counts[entity] = counts.get(entity, 0) + 1

      ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
      return [entity for entity, _ in ranked[:limit]]
  ```

  Notes for the implementer:
  - `count_pii_detected_queries` follows the `count_blocked_suspicious` shape (Patterns) with an `OR` instead of a single condition.
  - `top_pii_entities` cannot be pure SQL (Design Note 3) — fetch then tally in Python, same connection-scoping style (`with get_connection() as conn:`) as every other helper in this file.
  - Empty table → `rows == []` → `counts == {}` → `ranked == []` → returns `[]`. No special-casing needed (mirrors `top_models`'s empty-table behavior).
- **Mirror**: `app/db/database.py:130-135` (`count_blocked_suspicious`), `app/db/database.py:154-166` (`top_models`).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -c "
  import os
  os.environ.setdefault('OPENROUTER_API_KEY','k'); os.environ.setdefault('ADMIN_TOKEN','t')
  from app.config import settings
  settings.DATABASE_URL = 'sqlite:///:memory:'
  " 2>&1 | tail -5
  ```
  (Smoke-check only that the module imports without syntax errors; functional behavior is proven by Task 4's tests against a real temp DB — SQLite `:memory:` doesn't persist across separate connections, so it isn't used for the real assertions.)

### Task 3: Wire the new fields into the admin router

- **File**: `app/routers/admin.py`
- **Action**: UPDATE
- **Implement**:

  ```python
  from app.db.database import (
      count_audit_logs,
      count_blocked_duplicates,
      count_blocked_suspicious,
      count_pii_detected_queries,
      count_successful_queries,
      count_unique_users,
      list_audit_logs,
      top_models,
      top_pii_entities,
      top_users,
  )
  ```

  ```python
  def get_audit() -> AuditResponse:
      total = count_audit_logs()
      queries = [
          AuditQueryEntry(
              audit_id=log.id,
              user_id=log.user_id,
              timestamp=log.timestamp,
              model=log.model_used,
              prompt_hash=log.prompt_hash,
              was_duplicate_blocked=log.was_duplicate_blocked,
              suspicious_pattern_detected=log.suspicious_pattern is not None,
              device=log.device,
              pii_detected_input=log.pii_detected_input,
              pii_detected_output=log.pii_detected_output,
              pii_entities=log.pii_entities.split(",") if log.pii_entities else [],
          )
          for log in list_audit_logs(limit=100)
      ]
      return AuditResponse(total=total, queries=queries)
  ```

  ```python
  def get_stats() -> StatsResponse:
      total = count_audit_logs()
      successful = count_successful_queries()
      success_rate = f"{(successful / total * 100):.1f}%" if total > 0 else "0.0%"

      return StatsResponse(
          total_queries=total,
          blocked_duplicates=count_blocked_duplicates(),
          blocked_suspicious=count_blocked_suspicious(),
          unique_users=count_unique_users(),
          success_rate=success_rate,
          top_models=top_models(),
          top_users=top_users(),
          pii_detected_queries=count_pii_detected_queries(),
          top_pii_entities=top_pii_entities(),
      )
  ```

  Note: `log.pii_entities.split(",") if log.pii_entities else []` — guard on falsiness, not `is not None` (Design Note 2); an empty string is not a realistic DB value here (`audit_logger.py:43` writes `None`, never `""`) but the falsy guard is correct either way.
- **Mirror**: `app/routers/admin.py:24-39` and `:47-60` (existing handler bodies, unchanged shape).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -c "from app.main import app; print('ok')"
  ```
  → imports cleanly, no circular-import or name errors.

### Task 4: Unit-test the two new `database.py` helpers

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: Add import of the two new functions to the existing `from app.db.database import (...)` block (alphabetical, matching the file's current ordering), then append:

  ```python
  def test_count_pii_detected_queries_counts_input_or_output(temp_db):
      insert_audit_log(
          AuditLog(
              timestamp="2026-07-01T10:00:00Z",
              user_id="a",
              prompt_hash="h1",
              pii_detected_input=True,
          )
      )
      insert_audit_log(
          AuditLog(
              timestamp="2026-07-02T10:00:00Z",
              user_id="a",
              prompt_hash="h2",
              pii_detected_output=True,
          )
      )
      insert_audit_log(
          AuditLog(
              timestamp="2026-07-03T10:00:00Z",
              user_id="a",
              prompt_hash="h3",
          )
      )

      assert count_pii_detected_queries() == 2


  def test_top_pii_entities_ranked_by_frequency_desc(temp_db):
      insert_audit_log(
          AuditLog(
              timestamp="2026-07-01T10:00:00Z",
              user_id="a",
              prompt_hash="h1",
              pii_entities="EMAIL_ADDRESS,PERSON",
          )
      )
      insert_audit_log(
          AuditLog(
              timestamp="2026-07-02T10:00:00Z",
              user_id="a",
              prompt_hash="h2",
              pii_entities="EMAIL_ADDRESS",
          )
      )
      insert_audit_log(
          AuditLog(
              timestamp="2026-07-03T10:00:00Z",
              user_id="a",
              prompt_hash="h3",
              pii_entities="PHONE_NUMBER",
          )
      )

      # EMAIL_ADDRESS: 2, PERSON: 1, PHONE_NUMBER: 1 -- no tie at the top
      assert top_pii_entities()[0] == "EMAIL_ADDRESS"
      assert set(top_pii_entities()) == {"EMAIL_ADDRESS", "PERSON", "PHONE_NUMBER"}


  def test_top_pii_entities_respects_limit(temp_db):
      for i in range(3):
          insert_audit_log(
              AuditLog(
                  timestamp=f"2026-07-0{i + 1}T10:00:00Z",
                  user_id="a",
                  prompt_hash=f"e{i}",
                  pii_entities="EMAIL_ADDRESS",
              )
          )
      for i in range(2):
          insert_audit_log(
              AuditLog(
                  timestamp=f"2026-07-0{i + 4}T10:00:00Z",
                  user_id="a",
                  prompt_hash=f"p{i}",
                  pii_entities="PERSON",
              )
          )
      insert_audit_log(
          AuditLog(
              timestamp="2026-07-06T10:00:00Z",
              user_id="a",
              prompt_hash="l1",
              pii_entities="LOCATION",
          )
      )

      assert top_pii_entities(limit=2) == ["EMAIL_ADDRESS", "PERSON"]
  ```

  Then extend the existing empty-db test:

  ```python
  def test_aggregates_on_empty_db_return_zero_or_empty(temp_db):
      assert count_blocked_duplicates() == 0
      assert count_blocked_suspicious() == 0
      assert count_unique_users() == 0
      assert count_successful_queries() == 0
      assert count_pii_detected_queries() == 0
      assert top_models() == []
      assert top_users() == []
      assert top_pii_entities() == []
  ```

  Notes for the implementer:
  - `test_top_pii_entities_ranked_by_frequency_desc` calls `top_pii_entities()` twice deliberately — once for the deterministic top item, once via `set()` for full membership — because default `limit=5` returns all three entities here and list order beyond index 0 isn't asserted (no tie-break guarantee, Design Note 4).
  - `test_top_pii_entities_respects_limit` uses 3-vs-2-vs-1 counts (mirroring `test_top_models_respects_limit`'s 3-vs-2-vs-1 shape) so `limit=2` has an unambiguous expected result.
- **Mirror**: `tests/test_db.py:227-253` (`test_count_blocked_duplicates_counts_only_flagged_rows`), `tests/test_db.py:350-380` (`test_top_models_respects_limit`), `tests/test_db.py:399-405` (`test_aggregates_on_empty_db_return_zero_or_empty`).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_db.py -v
  ```
  → all pass, including the 3 new functions and the extended empty-db test.

### Task 5: Extend `/audit` router tests

- **File**: `tests/test_audit_router.py`
- **Action**: UPDATE
- **Implement**: Extend the expected-keys set in `test_valid_token_returns_expected_shape`:

  ```python
  for entry in body["queries"]:
      assert set(entry.keys()) == {
          "audit_id",
          "user_id",
          "timestamp",
          "model",
          "prompt_hash",
          "was_duplicate_blocked",
          "suspicious_pattern_detected",
          "device",
          "pii_detected_input",
          "pii_detected_output",
          "pii_entities",
      }
  ```

  Then append a dedicated PII-values test:

  ```python
  def test_pii_telemetry_fields_reflect_audit_log_values(temp_db):
      insert_audit_log(
          AuditLog(
              timestamp="2026-07-05T10:00:00Z",
              user_id="juan@empresa.com",
              prompt_hash="hash-pii",
              pii_detected_input=True,
              pii_detected_output=True,
              pii_entities="EMAIL_ADDRESS,PERSON",
          )
      )
      insert_audit_log(
          AuditLog(
              timestamp="2026-07-06T10:00:00Z",
              user_id="maria@empresa.com",
              prompt_hash="hash-clean",
          )
      )

      response = client.get(
          "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
      )

      body = response.json()
      by_hash = {q["prompt_hash"]: q for q in body["queries"]}

      flagged = by_hash["hash-pii"]
      assert flagged["pii_detected_input"] is True
      assert flagged["pii_detected_output"] is True
      assert flagged["pii_entities"] == ["EMAIL_ADDRESS", "PERSON"]

      clean = by_hash["hash-clean"]
      assert clean["pii_detected_input"] is False
      assert clean["pii_detected_output"] is False
      assert clean["pii_entities"] == []
  ```

  `test_response_never_includes_ip_or_raw_text` is left unmodified — it already asserts `"prompt_preview" not in entry`, which stays true (Design Note 1).
- **Mirror**: `tests/test_audit_router.py:47-97` (`test_valid_token_returns_expected_shape` — same insert-then-assert-shape pattern), `tests/test_audit_router.py:120-146` (import of `settings`/`AuditLog` already present at top of file, no new imports needed).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_audit_router.py -v
  ```
  → all pass, including the modified shape test and the 1 new test.

### Task 6: Extend `/stats` router tests

- **File**: `tests/test_stats_router.py`
- **Action**: UPDATE
- **Implement**: Extend the expected-keys set in `test_valid_token_returns_expected_shape_and_values`:

  ```python
  assert set(body.keys()) == {
      "total_queries",
      "blocked_duplicates",
      "blocked_suspicious",
      "unique_users",
      "success_rate",
      "top_models",
      "top_users",
      "pii_detected_queries",
      "top_pii_entities",
  }
  ```

  None of the four rows inserted in that test set PII fields, so immediately after the existing assertions add:

  ```python
  assert body["pii_detected_queries"] == 0
  assert body["top_pii_entities"] == []
  ```

  Extend the zero-rows test's expected dict:

  ```python
  def test_zero_rows_returns_zeroed_stats_without_error(temp_db):
      response = client.get(
          "/stats", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
      )

      assert response.status_code == 200
      assert response.json() == {
          "total_queries": 0,
          "blocked_duplicates": 0,
          "blocked_suspicious": 0,
          "unique_users": 0,
          "success_rate": "0.0%",
          "top_models": [],
          "top_users": [],
          "pii_detected_queries": 0,
          "top_pii_entities": [],
      }
  ```

  Then append a dedicated PII-aggregate test:

  ```python
  def test_pii_detected_queries_and_top_pii_entities_reflect_flagged_rows(temp_db):
      insert_audit_log(
          AuditLog(
              timestamp="2026-07-01T10:00:00Z",
              user_id="a",
              prompt_hash="h1",
              pii_detected_input=True,
              pii_entities="EMAIL_ADDRESS",
          )
      )
      insert_audit_log(
          AuditLog(
              timestamp="2026-07-02T10:00:00Z",
              user_id="b",
              prompt_hash="h2",
              pii_detected_output=True,
              pii_entities="EMAIL_ADDRESS,PERSON",
          )
      )
      insert_audit_log(
          AuditLog(
              timestamp="2026-07-03T10:00:00Z",
              user_id="c",
              prompt_hash="h3",
          )
      )

      response = client.get(
          "/stats", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
      )

      body = response.json()
      assert body["pii_detected_queries"] == 2
      assert body["top_pii_entities"][0] == "EMAIL_ADDRESS"
      assert set(body["top_pii_entities"]) == {"EMAIL_ADDRESS", "PERSON"}
  ```
- **Mirror**: `tests/test_stats_router.py:58-117` (`test_valid_token_returns_expected_shape_and_values`), `tests/test_stats_router.py:120-134` (`test_zero_rows_returns_zeroed_stats_without_error`).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_stats_router.py -v
  ```
  → all pass, including both modified tests and the 1 new test.

### Task 7: Full-suite regression and scope check

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - Full suite green at **181 passed** (175 baseline + 6 new: 3 in `test_db.py`, 1 in `test_audit_router.py`, 1 in `test_stats_router.py` — wait, recount: Task 4 adds 3 new functions, Task 5 adds 1, Task 6 adds 1 → 5 new. Confirm the actual collected count via `-v` output rather than trusting this arithmetic; a mismatch means a task added an unplanned test or a parametrization multiplied one.
  - `git diff --name-only` lists exactly: `app/models/schemas.py`, `app/db/database.py`, `app/routers/admin.py`, `tests/test_db.py`, `tests/test_audit_router.py`, `tests/test_stats_router.py`. No other file touched.
  - `tests/test_query_router.py`, `tests/test_integration.py`, `tests/test_pii_dedup_isolation.py`, and every other pre-existing test file pass unmodified.
- **Mirror**: [[STORY-008]] plan Task 6 — same scope gate.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai
  .venv/Scripts/python.exe -m pytest -v | tail -30
  .venv/Scripts/python.exe -m pytest -q
  git status --porcelain
  git diff --name-only
  ```
  → full suite green; `git status --porcelain` shows only the 6 files listed above as modified (plus the pre-existing unrelated `.agents/commands/prime.md` change already in the working tree, not touched by this story); `git diff --name-only` matches the Files to Change table.

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `.venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_audit_router.py tests/test_stats_router.py -v` → all pass, 0 skipped
- [ ] `.venv/Scripts/python.exe -m pytest -q` → full suite green (175 baseline + new tests from Tasks 4-6)
- [ ] `git status --porcelain` → only the 6 files in "Files to Change" (plus the pre-existing, unrelated `prime.md` change already present before this story started)
- [ ] `.venv/Scripts/python.exe -c "from app.main import app; print('ok')"` → backend imports cleanly
- [ ] `.venv/Scripts/python.exe -m uvicorn app.main:app` → server starts without error; `curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] Against the running server, with a real `ADMIN_TOKEN` and at least one PII-flagged row inserted (e.g. via a `POST /query` containing an email address, mirroring [[STORY-007]]'s manual check): `curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/audit` → each entry includes `pii_detected_input`, `pii_detected_output`, `pii_entities` (a JSON array); `curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/stats` → response includes `pii_detected_queries` (int ≥ 1) and `top_pii_entities` (non-empty array)
- [ ] `curl http://localhost:8000/audit` (no `Authorization` header) → still 401/403, unchanged from PRD-001 — this story adds no new unauthenticated surface
- [ ] If any command raises `sqlite3.OperationalError: table audit_logs has no column named pii_detected_input`, the local `harness_ai.db` predates [[STORY-003]] — delete it and re-run

---

## Validation

```bash
cd f:/AI/harness-ai
.venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_audit_router.py tests/test_stats_router.py -v
.venv/Scripts/python.exe -m pytest -q
git status --porcelain
git diff --name-only
.venv/Scripts/python.exe -c "from app.main import app; print('ok')"
.venv/Scripts/python.exe -m uvicorn app.main:app
curl http://localhost:8000/health
```

Frontend lint: N/A — this repo has no npm frontend (Reflex/Python project, no `package.json`), consistent with every prior PRD-003 report.

---

## Acceptance Criteria

(Copied from story STORY-009, with the `prompt_preview` clause of AC1 annotated per Design Note 1)

- [ ] Given `GET /audit` (admin token required, unchanged auth), when called, then each entry includes `pii_detected_input`, `pii_detected_output`, and `pii_entities` (list of entity type strings). **`prompt_preview` is explicitly out of scope for this story** — see Summary/Design Note 1 for why the AC's literal "alongside the existing unchanged `prompt_preview` field" clause does not apply on this branch.
- [ ] Given `GET /stats` (admin token required), when called, then the response includes `pii_detected_queries` (count of audit rows where either input or output PII was detected) and `top_pii_entities` (most frequent entity types across all rows).
- [ ] Given no query has ever triggered PII detection, when `GET /stats` is called, then `pii_detected_queries` is `0` and `top_pii_entities` is `[]` (no errors on empty data).
- [ ] Given the existing `tests/test_audit_router.py` and `tests/test_stats_router.py`, when run, then they still pass, extended with assertions for the new fields.
- [ ] All tasks completed
- [ ] Full test suite (`.venv/Scripts/python.exe -m pytest`) passes — 175 baseline + new tests from this story, zero regressions
- [ ] Backend server starts without error
- [ ] `top_pii_entities` counts individual entity types across multi-entity rows, not comma-joined strings as opaque buckets (Design Note 3)
- [ ] `pii_entities` in `/audit` responses is always a JSON list, never `null`, even when no PII was detected (Design Note 2)
- [ ] Follows existing patterns (env-var preamble before `app.*` imports, locally-defined `temp_db` fixture per file, thin router handlers with all aggregation logic in `database.py`, comma-join/split convention shared with `POST /query`'s `pii_entities_masked`)
