---
story: STORY-003
prd: PRD-001
slug: request-response-schemas
title: Pydantic request/response schemas
type: technical
complexity: small
epic_branch: epic/PRD-001-harness-ia
created: 2026-07-04
---

# Plan: Pydantic request/response schemas

## Summary

Add `app/models/schemas.py` — the Pydantic v2 request/response models that every remaining story in this PRD depends on. `QueryRequest` models the `POST /query` payload (`user_id`, `prompt` required; `device` optional; `model` defaulting to `"gpt-4"`; `openrouter_api_key` optional, falling back to the env var at the service layer in a later story). The three documented `/query` response shapes become three distinct, non-overlapping models — `QuerySuccessResponse`, `QueryBlockedDuplicateResponse`, `QueryBlockedSuspiciousResponse` — rather than one model with optional fields, so each serializes to exactly the JSON shape in PRD Section 10 with no null leakage. `AuditResponse`/`AuditQueryEntry` and `StatsResponse` mirror the `/audit` and `/stats` shapes field-for-field. No business logic, no DB access, no router wiring — pure shape + validation, consumed by STORY-004 through STORY-011.

## User Story

As an integrating developer
I want strongly-typed request/response models matching the PRD's API specification
So that `/query`, `/audit`, and `/stats` validate input and produce consistent, documented output shapes

## Story Reference

- Story file: `.agents/stories/PRD-001-harness-ia/STORY-003-request-response-schemas.md`
- PRD: `.agents/PRDs/PRD-001-harness-ia/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | small |
| Systems Affected | API contract layer (`app/models/`) |
| Story | STORY-003 |
| PRD | PRD-001 |
| Epic Branch | `epic/PRD-001-harness-ia` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` does not exist in this repo, and the story's `skills:` frontmatter field is empty — same situation as STORY-001 and STORY-002.

---

## Codebase State

`app/` currently has `config.py` (typed `Settings` singleton), `db/` (STORY-002: `models.py` with the `AuditLog` dataclass + `CREATE_AUDIT_LOGS_TABLE` DDL, `database.py` repository functions), and `main.py` (bare `FastAPI` app with `lifespan` calling `init_db()`, one `/health` route, and a comment block noting `app.routers.query`/`app.routers.admin` are added by STORY-008/010/011). There is no `app/models/` package yet — the PRD's Section 6 directory tree reserves `app/models/schemas.py` for exactly this story. No router imports these schemas yet (routers don't exist until STORY-008+), so this story only needs to produce importable, independently testable Pydantic models — nothing wires them into `main.py`.

---

## Design Decisions

1. **Three distinct response models for `/query`, not one model with optional fields.** PRD Section 10 documents three non-overlapping JSON shapes (`SUCCESS`; `BLOCKED` duplicate; `BLOCKED` suspicious). Modeling them as `QuerySuccessResponse`, `QueryBlockedDuplicateResponse`, `QueryBlockedSuspiciousResponse` — each with only the fields that shape has — means `model_dump()` never leaks a null `pattern` into a duplicate-block response or vice versa, which a single model with `Optional` fields would risk unless every caller remembered `exclude_none=True`. A `QueryResponse = Union[...]` alias is exported for router type hints in STORY-008, satisfying the story's own naming suggestion ("QueryBlockedResponse") as a type alias rather than a concrete class.

2. **`status` fields use `Literal`, not bare `str`.** `Literal["SUCCESS"]` / `Literal["BLOCKED"]` make each model self-documenting and let FastAPI's OpenAPI schema (and any `Union` response-model discrimination in STORY-008) distinguish shapes without extra logic here.

3. **`audit_id` is typed `int`, matching `audit_logs.id` (`INTEGER PRIMARY KEY AUTOINCREMENT`, STORY-002), not `str`.** PRD Section 10's JSON examples use placeholder strings like `"abc123"` for `audit_id` the same way they use `"abc123def456"` for `prompt_hash` — illustrative placeholders, not a type spec. Since `insert_audit_log()` (STORY-002) returns `cursor.lastrowid` (a real `int`), typing `audit_id: int` here means STORY-008 can pass that return value straight through with no cast. This is a deliberate deviation from the example's literal string and is called out here so downstream stories don't "fix" it back to `str`.

4. **`model` (in `AuditQueryEntry`) and `model_used` (in `QuerySuccessResponse`) are kept as separate, literally-named fields**, even though both ultimately come from the same `audit_logs.model_used` column. The PRD uses different key names in the two JSON shapes (Section 10: `/query` success → `"model_used"`, `/audit` entry → `"model"`); this story matches the documented API contract exactly and leaves the DB-column-to-field mapping to STORY-008/STORY-010.

5. **`first_query_at` and `timestamp` are typed `str`, not `datetime`.** `audit_logs.timestamp` is stored as `TEXT` (ISO-8601 UTC string, per STORY-002's `AuditLog.timestamp: str`). Keeping these fields as `str` in the schemas means no implicit datetime parsing/formatting step exists between the DB and the API response — consistent with STORY-002's existing convention.

6. **No emptiness/whitespace validation on `user_id`/`prompt`.** The story's only testable AC is "missing `user_id` or `prompt` → 422" — Pydantic's default required-field behavior already covers that (no default value = required). Adding `min_length=1` or a strip-and-check validator would be enforcing a rule (RF-14's "non-empty" pipeline check) that belongs to the request-pipeline story, not this shape-only story — avoids scope creep per the story's own note ("no business logic here, just shape + validation").

7. **`success_rate` stays `str` (e.g. `"98.4%"`), not `float`.** PRD Section 10's `/stats` example quotes it as a string; matching the literal example type avoids STORY-011 having to decide/document a formatting convention this story doesn't own.

8. **`device` and `openrouter_api_key` are `Optional[str] = None`.** Both are documented as optional in PRD Section 10 ("`openrouter_api_key` optional, falls back to `OPENROUTER_API_KEY` env var") and Section 7 ("optional per-request `openrouter_api_key`"); `device` has no default value documented but is never listed as required, so it follows the same optional convention as the `AuditLog.device` column (STORY-002).

---

## Patterns to Follow

### Package structure
```python
// SOURCE: app/db/__init__.py
```
Empty file, package marker only. `app/models/__init__.py` mirrors this exactly.

### Typed dataclass/model field style
```python
// SOURCE: app/db/models.py:24-39
@dataclass
class AuditLog:
    timestamp: str
    user_id: str
    prompt_hash: str
    device: Optional[str] = None
    ...
    id: Optional[int] = None
```
Same field-naming and `Optional[...] = None` convention carries over to the new Pydantic models (`BaseModel` instead of `@dataclass`), keeping field names identical to the DB layer where they refer to the same concept.

### Tests
```python
// SOURCE: tests/test_db.py:1-21
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.config import settings
...
```
New schema tests don't strictly need the env vars (schemas don't read `settings`), but follow the same plain-`pytest`-`assert`, no-unittest-class style as `tests/test_db.py` and `tests/test_main.py`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/__init__.py` | CREATE | Marks `app/models/` as a package |
| `app/models/schemas.py` | CREATE | `QueryRequest`, `QuerySuccessResponse`, `QueryBlockedDuplicateResponse`, `QueryBlockedSuspiciousResponse`, `QueryResponse` (Union alias), `AuditQueryEntry`, `AuditResponse`, `StatsResponse` |
| `tests/test_schemas.py` | CREATE | Validation + shape tests for every model |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `app/models/__init__.py`

- **File**: `app/models/__init__.py`
- **Action**: CREATE
- **Implement**: Empty file — marks `app/models/` as a package.
- **Mirror**: `app/db/__init__.py` (STORY-002 empty-package-marker pattern).
- **Validate**: `python -c "import app.models"` succeeds from repo root.

### Task 2: Create `app/models/schemas.py`

- **File**: `app/models/schemas.py`
- **Action**: CREATE
- **Implement**: Using `pydantic.BaseModel` and `typing.Literal`/`Optional`/`Union`/`List`:
  - `QueryRequest`: `user_id: str`, `prompt: str` (both required — no default), `device: Optional[str] = None`, `model: str = "gpt-4"`, `openrouter_api_key: Optional[str] = None`.
  - `QuerySuccessResponse`: `status: Literal["SUCCESS"] = "SUCCESS"`, `response: str`, `audit_id: int`, `model_used: str`, `tokens_used: int`.
  - `QueryBlockedDuplicateResponse`: `status: Literal["BLOCKED"] = "BLOCKED"`, `reason: str`, `first_query_at: str`.
  - `QueryBlockedSuspiciousResponse`: `status: Literal["BLOCKED"] = "BLOCKED"`, `reason: str`, `pattern: str`.
  - `QueryResponse = Union[QuerySuccessResponse, QueryBlockedDuplicateResponse, QueryBlockedSuspiciousResponse]` — type alias for router use in STORY-008.
  - `AuditQueryEntry`: `audit_id: int`, `user_id: str`, `timestamp: str`, `model: Optional[str] = None`, `prompt_hash: str`, `was_duplicate_blocked: bool`, `suspicious_pattern_detected: bool`, `device: Optional[str] = None`.
  - `AuditResponse`: `total: int`, `queries: List[AuditQueryEntry]`.
  - `StatsResponse`: `total_queries: int`, `blocked_duplicates: int`, `blocked_suspicious: int`, `unique_users: int`, `success_rate: str`, `top_models: List[str]`, `top_users: List[str]`.
- **Mirror**: `app/db/models.py:24-39` field-naming/`Optional[...]` convention; PRD Section 10 for exact field names and shapes per response.
- **Validate**: `python -c "from app.models.schemas import QueryRequest, QuerySuccessResponse, QueryBlockedDuplicateResponse, QueryBlockedSuspiciousResponse, QueryResponse, AuditQueryEntry, AuditResponse, StatsResponse"` succeeds with no import error.

### Task 3: Create `tests/test_schemas.py`

- **File**: `tests/test_schemas.py`
- **Action**: CREATE
- **Implement**: Plain-`assert` pytest tests (no unittest classes):
  1. `test_query_request_missing_user_id_raises` — `QueryRequest(prompt="hi")` raises `pydantic.ValidationError`.
  2. `test_query_request_missing_prompt_raises` — `QueryRequest(user_id="juan@empresa.com")` raises `pydantic.ValidationError`.
  3. `test_query_request_defaults` — `QueryRequest(user_id="juan@empresa.com", prompt="hi")` → `model == "gpt-4"`, `openrouter_api_key is None`, `device is None`.
  4. `test_query_success_response_shape` — construct with sample values, `model_dump()` keys/values == `{"status": "SUCCESS", "response": ..., "audit_id": ..., "model_used": ..., "tokens_used": ...}` exactly (5 keys, matching PRD Section 10 success example field names).
  5. `test_query_blocked_duplicate_response_shape` — `model_dump()` == exactly `{"status": "BLOCKED", "reason": ..., "first_query_at": ...}` (3 keys, no `pattern` key present).
  6. `test_query_blocked_suspicious_response_shape` — `model_dump()` == exactly `{"status": "BLOCKED", "reason": ..., "pattern": ...}` (3 keys, no `first_query_at` key present).
  7. `test_audit_response_shape` — build one `AuditQueryEntry` + wrap in `AuditResponse(total=1, queries=[...])`, assert `model_dump()` matches PRD Section 10's `/audit` example keys exactly (`total`, `queries[0]` has `audit_id`, `user_id`, `timestamp`, `model`, `prompt_hash`, `was_duplicate_blocked`, `suspicious_pattern_detected`, `device`).
  8. `test_stats_response_shape` — build one, assert `model_dump()` matches PRD Section 10's `/stats` example keys exactly (`total_queries`, `blocked_duplicates`, `blocked_suspicious`, `unique_users`, `success_rate`, `top_models`, `top_users`).
- **Mirror**: `tests/test_db.py:1-21` / `tests/test_main.py:1-16` style (plain `assert`, no unittest classes); use `import pytest` + `pytest.raises(ValidationError)` from `pydantic`.
- **Validate**: `pytest tests/test_schemas.py -v` passes.

---

## End-to-End Tests

No router exists yet to exercise these schemas over HTTP (that's STORY-008/010/011). For this story, "end-to-end" means the full schema module is importable and self-consistent:

- [ ] `python -c "import app.models.schemas"` succeeds with no error (AC 1 precondition)
- [ ] `QueryRequest(prompt="hi")` and `QueryRequest(user_id="x")` both raise `pydantic.ValidationError` (AC 1)
- [ ] `QuerySuccessResponse`, `QueryBlockedDuplicateResponse`, `QueryBlockedSuspiciousResponse` each serialize to exactly the PRD Section 10 field set with no extra/missing keys (AC 2)
- [ ] `QueryRequest(user_id="x", prompt="hi").model == "gpt-4"` and `.openrouter_api_key is None` when omitted (AC 3)
- [ ] `AuditResponse` and `StatsResponse` serialize to exactly the PRD Section 10 field sets (AC 4)
- [ ] `pytest tests/` (full suite, including existing `test_main.py`/`test_db.py`) passes green

---

## Validation

```bash
python -c "from app.models.schemas import QueryRequest, QuerySuccessResponse, QueryBlockedDuplicateResponse, QueryBlockedSuspiciousResponse, QueryResponse, AuditQueryEntry, AuditResponse, StatsResponse"
pytest tests/ -v
```

---

## Acceptance Criteria

(Copied from story STORY-003)

- [ ] Given the `POST /query` request schema, when a payload is missing `user_id` or `prompt`, then Pydantic validation rejects it with a 422 before any business logic runs.
- [ ] Given the `POST /query` response schemas, when serialized, then they match the three shapes in PRD Section 10 exactly: `SUCCESS` (`status`, `response`, `audit_id`, `model_used`, `tokens_used`), `BLOCKED` duplicate (`status`, `reason`, `first_query_at`), `BLOCKED` suspicious (`status`, `reason`, `pattern`).
- [ ] Given `model` and `openrouter_api_key` are omitted from a request, then the schema applies the documented defaults/optionality (`model` defaults to `"gpt-4"`; `openrouter_api_key` is optional).
- [ ] Given the `/audit` and `/stats` response schemas, when serialized, then they match the shapes in PRD Section 10 field-for-field.
- [ ] All tasks completed
- [ ] Frontend lint passes — N/A, no frontend in this MVP; substitute `pytest tests/ -v` passes
- [ ] Backend server starts without error
- [ ] Follows existing patterns (`app/db/models.py` field-naming convention, `tests/test_db.py`/`tests/test_main.py` test style, PRD Section 10 field names verbatim)
