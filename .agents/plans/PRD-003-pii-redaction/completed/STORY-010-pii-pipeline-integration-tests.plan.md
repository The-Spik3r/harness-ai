---
story: STORY-010
prd: PRD-003
slug: pii-pipeline-integration-tests
title: "End-to-end PII redaction integration test suite"
type: REFACTOR
complexity: MEDIUM
epic_branch: epic/PRD-003-pii-redaction        # all stories commit here, no per-story branch
created: 2026-08-02
---

# Plan: End-to-end PII redaction integration test suite

## Summary

This story writes **no application code**. It is the epic's final gate before docs/rollout ([[STORY-012]]): one new file, `tests/test_pii_redaction_integration.py`, that walks a single `POST /query` request through the *whole* stack and proves the three promises PRD-003 makes to a compliance admin — **masked text is all OpenRouter ever sees, masked text is all the caller ever sees, and the audit trail stays raw** — plus the two guarantees that make those promises trustworthy: no PRD-001 test was sacrificed to get here, and `PII_REDACTION_ENABLED=false` still turns the whole thing off.

The distinction from every earlier PRD-003 test story matters, because 180 tests already exist and duplicating them would inflate the count while proving nothing. [[STORY-005]] through [[STORY-007]] proved each *pipeline step* in isolation at the router level (`tests/test_query_router.py`, 32 tests). [[STORY-008]] proved what redaction must **not** touch (`tests/test_pii_dedup_isolation.py`, 20 tests). [[STORY-009]] proved the two admin endpoints *serialize* the telemetry correctly (`tests/test_audit_router.py`, `tests/test_stats_router.py`). None of them asserts that **all four surfaces agree about the same single request** — the outbound OpenRouter payload, the HTTP response body, the persisted audit row, and what `/audit` + `/stats` report — which is precisely what "end-to-end" means here and the only thing an auditor actually cares about.

Every string in this plan was measured against this branch's real redactor (`en_core_web_lg`, shipped settings), not guessed:

```
redact("my name is Maria Gomez, my email is juan@empresa.com and my phone is 555-123-4567")
  -> ('my name is <PERSON>, my email is <EMAIL_ADDRESS> and my phone is <PHONE_NUMBER>',
      ['EMAIL_ADDRESS', 'PERSON', 'PHONE_NUMBER'])
redact("Please contact John Smith at john.smith@acme.com or 212-555-0199.")
  -> ('Please contact <PERSON> at <EMAIL_ADDRESS> or <PHONE_NUMBER>.',
      ['EMAIL_ADDRESS', 'PERSON', 'PHONE_NUMBER'])
```

A three-entity prompt **and** a three-entity response were chosen deliberately over the single-`EMAIL_ADDRESS` pairs used by earlier stories: an end-to-end test that only ever masks one entity type cannot detect a regression that drops `PERSON` or `PHONE_NUMBER` from the union while leaving `EMAIL_ADDRESS` working.

**One acceptance criterion cannot be satisfied as literally written** — AC3 asks for `prompt_preview`/`response_preview` via `GET /audit`, and that endpoint does not return those fields (measured; see Design Note 2). The plan satisfies AC3's *intent* — "the audit trail stays raw" — without expanding the admin API surface inside a test-only story, and pins the current contract so the decision is re-opened deliberately rather than drifted into.

## User Story

As a compliance admin
I want automated proof that the whole redaction feature works end-to-end — masked text never reaches OpenRouter, the caller only ever sees masked text, and the audit trail stays raw
So that the MVP's definition of done is verifiable in CI, not just by manual inspection (PRD Section 11, Section 12 Phase 3)

## Story Reference

- Story file: `.agents/stories/PRD-003-pii-redaction/STORY-010-pii-pipeline-integration-tests.md`
- PRD: `.agents/PRDs/PRD-003-pii-redaction/PRD.md` — Section 8 (Testing), Section 10 (API Specification), Section 11 (Success Criteria), Section 12 Phase 3 (Isolation Testing)

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (test-only; no application code changes) |
| Complexity | MEDIUM |
| Systems Affected | `tests/test_pii_redaction_integration.py` (new). **No `app/` file is modified by this story.** |
| Story | STORY-010 |
| PRD | PRD-003 |
| Epic Branch | `epic/PRD-003-pii-redaction` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` does not exist in this repository (verified — the directory is absent), the story's `skills:` frontmatter field is `[]`, and PRD Section 15 states it explicitly ("Skills referenced: None"). Same finding as the [[STORY-001]] through [[STORY-009]] plans.

---

## Dependency Check

| Dependency | Status | Verified on this branch |
|---|---|---|
| [[STORY-007]] — `pii_redacted` signal field | ✅ done (`61e402c`) | `pii_redacted` / `pii_entities_masked` on `QuerySuccessResponse` — `app/models/schemas.py:20-21`, populated at `app/services/query_pipeline.py:120-121` |
| [[STORY-008]] — dedup/pattern isolation tests | ✅ done (`58ee0a6`) | `tests/test_pii_dedup_isolation.py`, 20 collected, all passing |
| [[STORY-009]] — `/audit` + `/stats` telemetry | ✅ done (`fc4804f`) | `pii_detected_input/output` + `pii_entities` at `app/routers/admin.py:38-40`; `pii_detected_queries` + `top_pii_entities` at `:65-66` |

All three `depends_on` entries are `done` — no blocker, no user confirmation needed.

This story `blocks: [STORY-012]` (README / `.env.example` / roadmap). Division of labour: [[STORY-008]] proved what redaction must **not** touch; this story proves what it **does**, across every surface at once; [[STORY-012]] then documents a feature whose behaviour is already pinned.

---

## Patterns to Follow

### The four surfaces a single request must agree on

```python
# SOURCE: app/services/query_pipeline.py:69-122
        openrouter_result = call_openrouter(
            redacted_prompt, model=model, api_key=openrouter_api_key   # SURFACE 1: outbound = masked
        )
    ...
        redacted_response, output_entities = redact(openrouter_result.response)
    masked_entities = sorted(set(input_entities) | set(output_entities))
    audit_id = log_query(
        prompt=prompt,                      # SURFACE 3: audit = RAW
        response=openrouter_result.response, # SURFACE 3: audit = RAW
        pii_entities=masked_entities,
    )
    return QuerySuccessResponse(
        response=redacted_response,          # SURFACE 2: caller = masked
        pii_redacted=bool(masked_entities),
        pii_entities_masked=masked_entities,
    )
```

Surface 4 is `/audit` + `/stats`, reading that same row back (`app/routers/admin.py:26-67`). `masked_entities` is `sorted(set(...))` — **alphabetical**, so `["EMAIL_ADDRESS", "PERSON", "PHONE_NUMBER"]` is the exact expected order, not an arbitrary one.

### Env-var preamble every test module opens with

```python
# SOURCE: tests/test_query_router.py:1-4
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```

`app.config.Settings` requires both, so this must precede any `app.*` import — non-negotiable, and the reason imports in these files are not top-sorted.

### Local fixtures — this repo has no `tests/conftest.py`

```python
# SOURCE: tests/test_query_router.py:26-37
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path


def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]
```

Seven existing modules each redefine these locally. Follow that; do not introduce a conftest (Design Note 7).

### Capturing the outbound OpenRouter payload

```python
# SOURCE: tests/test_query_router.py:186-191
def _capturing_openrouter(seen: list):
    def _call(prompt, model="gpt-4", api_key=None):
        seen.append(prompt)
        return OpenRouterResult(response="drafted", model_used=model, tokens_used=9)

    return _call
```

Patched via `monkeypatch.setattr("app.routers.query.call_openrouter", ...)` — the string target is correct *here* because `app/routers/query.py:24` passes it explicitly into `run_query`. (Collaborators *inside* `query_pipeline` are patched on the module object instead — `tests/test_pii_dedup_isolation.py:242-244`.)

### Admin-endpoint requests

```python
# SOURCE: tests/test_integration.py:139-141
    admin_headers = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    audit = client.get("/audit", headers=admin_headers)
    stats = client.get("/stats", headers=admin_headers)
```

### Exact-shape response assertion

```python
# SOURCE: tests/test_query_router.py:615-623
    assert body == {
        "status": "SUCCESS",
        "response": "drafted",
        "audit_id": body["audit_id"],
        "model_used": "gpt-4",
        "tokens_used": 9,
        "pii_redacted": True,
        "pii_entities_masked": ["EMAIL_ADDRESS"],
    }
```

Whole-dict equality, with `audit_id` echoed back so the assertion stays exact without hard-coding a row id. This is how PRD Section 10's shape gets pinned — a field added or dropped fails the test.

### Git-history guard, with a skip when git is unavailable

```python
# SOURCE: tests/test_pii_dedup_isolation.py:134-172
def _epic_base():
    """Merge-base with `main`, or None when git/history is unavailable."""
    try:
        result = subprocess.run(
            ["git", "merge-base", "main", "HEAD"],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
```

[[STORY-008]] established this helper. Reuse its exact shape (Design Note 6 explains why it is copied rather than imported).

### Reading the persisted row directly

```python
# SOURCE: tests/test_query_router.py:238-250
def test_audit_row_keeps_raw_prompt_when_pii_redacted(temp_db, monkeypatch):
    ...
    entry = get_audit_log(audit_id)

    assert entry.prompt_preview == _PII_PROMPT
    assert entry.prompt_hash == hash_prompt(_PII_PROMPT)
    assert "<EMAIL_ADDRESS>" not in entry.prompt_preview
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_pii_redaction_integration.py` | CREATE | The entire story: 12 test functions (22 collected — three are parametrized) covering AC1–AC5 |

**Explicitly NOT touched:**

- Every file under `app/` — this story adds no application behaviour. If a test here fails, the correct response is to **report a real defect**, not to soften the test (Design Note 9)
- `tests/test_integration.py` — the story's Technical Notes offer "extend `test_integration.py` and/or add a new file". A new file is chosen (Design Note 1), and `test_integration.py` is one of the seven files AC4's git guard pins as untouched. Extending it would put the epic's fingerprints on a file this story asserts is clean
- `tests/test_query_router.py`, `tests/test_pii_dedup_isolation.py`, `tests/test_audit_router.py`, `tests/test_stats_router.py`, `tests/test_db.py`, `tests/test_schemas.py`, `tests/test_audit_logger.py`, `tests/test_main.py`, `tests/test_pii_redactor.py` — extended by earlier epic stories, unchanged by this one
- `tests/test_admin_auth.py`, `tests/test_chat_state.py`, `tests/test_duplicate_checker.py`, `tests/test_openrouter_client.py`, `tests/test_pattern_detector.py`, `tests/test_route_reservations.py` — untouched by the whole epic; this story *asserts* that
- `tests/conftest.py` — deliberately not created (Design Note 7)
- `harness_ai.db` at the repo root — every test uses the `temp_db` fixture; the checked-in DB must be byte-unchanged afterwards (Design Note 10)

---

## Design Notes (decisions worth stating up front)

1. **A new file, not an extension of `tests/test_integration.py`.** The story permits either. A new file wins on three counts: (a) AC4's git guard pins `test_integration.py` as unmodified since the epic base — extending it would make that assertion self-contradictory; (b) `test_integration.py` is the PRD-001 suite, and mixing PRD-003 assertions into it makes "the PRD-001 suite still passes" unfalsifiable; (c) the new file needs its own PII constants and capture helpers that no PRD-001 test wants. Naming follows `tests/test_pii_dedup_isolation.py` — the epic's other test-only story.

2. **AC3 cannot be satisfied literally; satisfy its intent and pin the gap.** AC3 says the audit row fetched *via `GET /audit`* must show raw `prompt_preview`/`response_preview`. Measured on this branch, `GET /audit` returns exactly these keys and no others:

   ```
   ['audit_id', 'device', 'model', 'pii_detected_input', 'pii_detected_output',
    'pii_entities', 'prompt_hash', 'suspicious_pattern_detected', 'timestamp', 'user_id',
    'was_duplicate_blocked']
   ```

   No previews — and that is not an oversight of [[STORY-009]]. PRD-001 Section 10's `/audit` contract never contained them, and PRD-003 Section 11 requires the endpoints to gain telemetry "**without exposing masked values as a distinct new leak surface**". Adding raw `prompt_preview`/`response_preview` to `AuditQueryEntry` would push the raw PII of the last 100 requests into a single admin JSON payload — a genuine expansion of the leak surface, decided inside a story whose declared type is `technical` and whose job is to *observe* the system, not change it.

   The plan therefore splits AC3 in two, and covers both halves:
   - **"The audit trail stays raw"** (the actual promise, PRD RF-7) — asserted against the persisted row via `get_audit_log()`, exactly as `tests/test_query_router.py:238-250` and `tests/test_pii_dedup_isolation.py:117-131` already do. Same source of truth `/audit` reads from.
   - **"`GET /audit` is the admin's window on it"** — asserted on the endpoint's real contract: telemetry fields correct, and no masked placeholder anywhere in the payload. Plus `test_audit_endpoint_contract_has_no_preview_fields`, which pins the current key set so that adding previews later fails a test and forces the decision to be made on purpose, with its own story and its own security review.

   **If the reviewer wants the literal AC instead**, that is a one-line schema change plus two lines in `admin.py` — but it belongs in its own story (it changes the API contract, `openapi.json`, and the PRD Section 10 example), and this plan should be revised rather than quietly widened. Flag raised, not swallowed.

3. **Do not restate coverage that already exists.** All 180 existing tests were reviewed against this story's ACs before a single new one was written:

   | Already covered | Where | This story adds |
   |---|---|---|
   | Masked prompt reaches OpenRouter (1 entity) | `test_query_router.py:198-208` | **3 entities**, plus per-fragment substring proof, plus the same request checked on all four surfaces |
   | Masked response returned to caller (2 entities) | `test_query_router.py:371-382` | whole-body PRD §10 shape equality in the same request |
   | Audit row keeps raw prompt / raw response | `test_query_router.py:238-250`, `:385-397` | both directions in one request, cross-checked against what `/audit` reports |
   | `/audit` serializes telemetry | `test_audit_router.py` | telemetry produced by a **real pipeline run** rather than a seeded row |
   | `/stats` counts PII queries | `test_stats_router.py` | same — driven end-to-end |
   | Analyzer loaded once at startup via `lifespan` | `test_main.py:29-63` | — (referenced, not duplicated) |
   | `PII_REDACTION_ENABLED=false` on prompt / on response | `test_query_router.py:292-302`, `:470-481` | the **full** off-path: outbound raw, body raw, audit telemetry all false, `/audit` telemetry all false |
   | Dedup/pattern isolation | `test_pii_dedup_isolation.py` (20) | — (referenced, not duplicated) |
   | No pre-epic test removed or renamed | **nowhere** | AC4 |
   | Four surfaces agree about one request | **nowhere** | the core of the story |

4. **Use three entity types in both directions.** Earlier stories used single-`EMAIL_ADDRESS` strings, which is right for unit-level asserts and wrong for an end-to-end gate: a regression that dropped `PERSON` from the union would sail past every existing test that only ever masks an email. Both constants here mask `PERSON` + `EMAIL_ADDRESS` + `PHONE_NUMBER` — measured, not assumed (see Summary). Deliberately avoided: `US_SSN` (`"ssn 123-45-6789"` is **not** detected at the shipped `PII_SCORE_THRESHOLD=0.35` — measured) and `LOCATION` (context-dependent). Do not add unmeasured PII strings to this file.

5. **AC4's "unmodified" needs an honest reading.** Taken literally, "the full existing PRD-001 test suite … passes unmodified" is already false in the trivial sense: this epic *extended* `test_query_router.py` (7 → 32 tests), `test_db.py` (17 → 22), and others by **adding** tests. What AC4 actually protects against is a PRD-001 test being deleted, renamed, or weakened to make redaction pass. So the guard is built in two layers, both verified green today:
   - **Untouched-file pin** — the six pre-epic test modules the epic never opened (`test_admin_auth`, `test_chat_state`, `test_duplicate_checker`, `test_integration`, `test_openrouter_client`, `test_pattern_detector`, plus `test_route_reservations`) must not appear in `git diff` against the epic base. Measured: all seven clean.
   - **Function-census pin** — for *every* test module present at the epic base, every `def test_*` name that existed then must still exist now. Measured: **86 pre-epic test functions across 14 files, zero missing**. This is the layer that catches a deletion inside a file the epic legitimately extended, which the file-level pin structurally cannot see.

6. **Copy the git helpers from [[STORY-008]]; do not import them.** `_epic_base()` / `_changed_since_epic_base()` exist in `tests/test_pii_dedup_isolation.py`. Importing across test modules would make that file an implicit dependency of this one and drag its module-level `TestClient(app)` and PII constants into this module's import graph. This repo's convention is standalone test modules (no conftest, fixtures redefined seven times over); ~25 duplicated lines is the cheaper cost. **Same skip-not-fail semantics**: a missing `git`, a shallow clone, or a tarball export skips the pin — a missing tool is not evidence of a violation.

7. **No `tests/conftest.py`.** Introducing one as a side effect of a test-only story would change collection behaviour for every module in the suite — including the seven files AC4 requires to be untouched. Same conclusion as [[STORY-008]] Design Note 8.

8. **Use `en_core_web_lg`, the configured default.** `tests/test_pii_redactor.py:13-18` and `tests/test_main.py:22-27` pin `en_core_web_sm` for speed; that is right for unit-testing the redactor and the lifespan, and wrong here. This story is the gate that says *the shipped configuration* works end-to-end. Cost is negligible: the model is a process-wide singleton already warmed by earlier modules, and the full suite runs in **8.9s** today.

9. **A failure in this file is a finding, not a flaky test.** These assertions are the mechanism by which PRD Section 11's checklist becomes executable. A failure means raw PII reached OpenRouter, reached the caller, or the audit trail stopped being raw — all ship-blocking for PRD-003, all to be reported in the story report rather than accommodated.

10. **Leave the repo-root `harness_ai.db` untouched.** Every test takes `temp_db`. Any manual E2E probe must point `settings.DATABASE_URL` at a temp path *before* `init_db()`, or clean up its rows afterwards. `git status --porcelain` at the end must not list `harness_ai.db`.

11. **Use `.venv/Scripts/python.exe` for every command.** Recorded in [[STORY-003]]'s report (Deviation 1) and re-confirmed while planning this story: bare `python` on this machine resolves to a global Python 3.13 with no `spacy`/`presidio-analyzer`, producing collection errors in every module that transitively imports `app.main`. Environment mismatch, not a code defect. Scripts run outside pytest also need `PYTHONPATH=F:/AI/harness-ai`.

12. **Baseline to preserve: 180 passed** (`.venv/Scripts/python.exe -m pytest -q`, measured on this branch immediately before planning — 180 collected, 8.9s). Target after this story: **202 passed** (180 + 22 collected — 12 test functions, of which three are parametrized ×3, ×3 and ×7). Zero existing tests modified.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create the module preamble, helpers, and measured constants

- **File**: `tests/test_pii_redaction_integration.py`
- **Action**: CREATE
- **Implement**: Header, fixtures, helpers, and the constants every later task depends on. No tests yet.

  ```python
  import os

  os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
  os.environ.setdefault("ADMIN_TOKEN", "test-token")

  import json
  import pathlib
  import re
  import subprocess

  import pytest
  from fastapi.testclient import TestClient

  from app.config import settings
  from app.db.database import get_audit_log, get_connection, init_db
  from app.main import app
  from app.services.duplicate_checker import hash_prompt
  from app.services.openrouter_client import OpenRouterResult

  client = TestClient(app)

  _REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

  # Every string below was measured against this branch's redactor with the shipped
  # settings (en_core_web_lg, PII_SCORE_THRESHOLD=0.35) -- see the plan's Summary.
  # Three entity types in BOTH directions: a single-entity fixture cannot catch a
  # regression that drops PERSON or PHONE_NUMBER from the union (Design Note 4).
  _PII_PROMPT = (
      "my name is Maria Gomez, my email is juan@empresa.com and my phone is 555-123-4567"
  )
  _REDACTED_PROMPT = (
      "my name is <PERSON>, my email is <EMAIL_ADDRESS> and my phone is <PHONE_NUMBER>"
  )
  _PII_RESPONSE = "Please contact John Smith at john.smith@acme.com or 212-555-0199."
  _REDACTED_RESPONSE = "Please contact <PERSON> at <EMAIL_ADDRESS> or <PHONE_NUMBER>."

  _PROMPT_PII_FRAGMENTS = ("Maria Gomez", "juan@empresa.com", "555-123-4567")
  _RESPONSE_PII_FRAGMENTS = ("John Smith", "john.smith@acme.com", "212-555-0199")
  _EXPECTED_ENTITIES = ["EMAIL_ADDRESS", "PERSON", "PHONE_NUMBER"]  # sorted(set(...)) union

  _ADMIN_HEADERS = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}


  @pytest.fixture
  def temp_db(tmp_path, monkeypatch):
      db_path = tmp_path / "test.db"
      monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
      init_db()
      return db_path


  def _count_audit_rows() -> int:
      with get_connection() as conn:
          row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
          return row["n"]


  def _capturing_openrouter(seen: list, response: str = _PII_RESPONSE):
      """Records the outbound prompt, then answers with PII of its own."""

      def _call(prompt, model="gpt-4", api_key=None):
          seen.append(prompt)
          return OpenRouterResult(response=response, model_used=model, tokens_used=9)

      return _call


  def _post_pii_query(monkeypatch, seen=None, user_id="juan@empresa.com"):
      """One full POST /query with PII in BOTH directions. Returns (response, seen)."""
      seen = [] if seen is None else seen
      monkeypatch.setattr(
          "app.routers.query.call_openrouter", _capturing_openrouter(seen)
      )
      response = client.post(
          "/query",
          json={"user_id": user_id, "prompt": _PII_PROMPT, "device": "Chrome/Windows"},
      )
      return response, seen
  ```

  Notes for the implementer:
  - The env-var preamble **must** precede every `app.*` import. Do not let an import-sorter hoist them.
  - Do **not** copy the `en_core_web_sm` autouse fixture from `tests/test_pii_redactor.py` — this file tests the shipped configuration (Design Note 8).
  - `_post_pii_query` is the spine of Tasks 2–4: one helper, one request shape, so every surface assertion is demonstrably about *the same request*.
  - `json`, `re`, `subprocess`, `pathlib`, `hash_prompt`, `_count_audit_rows` are used by Tasks 4–6; declare them now so the header is written once.
- **Mirror**: `tests/test_query_router.py:1-56` (preamble, `temp_db`, `_count_audit_rows`), `:186-191` (`_capturing_openrouter`), `tests/test_pii_dedup_isolation.py:36-48` (measured-constant block with a comment explaining *why* the values are what they are).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_pii_redaction_integration.py -q
  ```
  → `no tests ran` (collected 0, exit code 5) with **no collection error**. A collection error here means the preamble or an import is wrong; fix before continuing.

### Task 2: AC1 — masked text is all OpenRouter ever sees

- **File**: `tests/test_pii_redaction_integration.py`
- **Action**: UPDATE
- **Implement**: Append the two outbound tests.

  ```python
  def test_openrouter_receives_only_the_masked_prompt(temp_db, monkeypatch):
      """AC1: the mock's recorded call args contain only redacted text."""
      response, seen = _post_pii_query(monkeypatch)

      assert response.status_code == 200
      assert seen == [_REDACTED_PROMPT]


  @pytest.mark.parametrize("fragment", _PROMPT_PII_FRAGMENTS)
  def test_no_raw_pii_fragment_reaches_openrouter(temp_db, monkeypatch, fragment):
      """AC1, per entity: name, email and phone are each individually absent."""
      response, seen = _post_pii_query(monkeypatch)

      assert response.status_code == 200
      assert fragment in _PII_PROMPT          # the fragment really was in what the user sent
      assert fragment not in seen[0]          # ...and is not in what left the building
  ```

  Notes for the implementer:
  - The two tests are not redundant. The first pins the *exact* masked string, so a change in Presidio's placeholder format fails loudly. The second is the one that survives such a change and still proves the security property — and it names the offending entity type in the failure message rather than dumping an 80-character diff.
  - `assert fragment in _PII_PROMPT` looks tautological and is not: it fails if someone edits `_PROMPT_PII_FRAGMENTS` out of sync with `_PII_PROMPT`, which would otherwise make the second assertion vacuously true.
  - `seen[0]` is safe only because the first assertion in each test guarantees the request completed; keep `response.status_code == 200` above it.
- **Mirror**: `tests/test_query_router.py:198-208`, `tests/test_pii_dedup_isolation.py:89-100` (asserting on the captured outbound list).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_pii_redaction_integration.py -v
  ```
  → 4 passed (1 + 3 parametrized).

### Task 3: AC2 — masked text is all the caller ever sees, in PRD §10's shape

- **File**: `tests/test_pii_redaction_integration.py`
- **Action**: UPDATE
- **Implement**: Append the two response-body tests.

  ```python
  def test_response_body_matches_prd_section_10_shape(temp_db, monkeypatch):
      """AC2: masked response + pii_redacted/pii_entities_masked, exact field set."""
      response, _ = _post_pii_query(monkeypatch)
      body = response.json()

      assert response.status_code == 200
      assert body == {
          "status": "SUCCESS",
          "response": _REDACTED_RESPONSE,
          "audit_id": body["audit_id"],
          "model_used": "gpt-4",
          "tokens_used": 9,
          "pii_redacted": True,
          "pii_entities_masked": _EXPECTED_ENTITIES,
      }
      assert isinstance(body["audit_id"], int)


  @pytest.mark.parametrize("fragment", _RESPONSE_PII_FRAGMENTS)
  def test_no_raw_pii_fragment_reaches_the_caller(temp_db, monkeypatch, fragment):
      """AC2, per entity: nothing raw survives anywhere in the serialized body."""
      response, _ = _post_pii_query(monkeypatch)

      assert response.status_code == 200
      assert fragment in _PII_RESPONSE
      assert fragment not in json.dumps(response.json())
  ```

  Notes for the implementer:
  - Whole-dict equality is what pins PRD Section 10's shape (AC2's wording): a new field, a dropped field, or a renamed one fails here. Echoing `body["audit_id"]` back keeps it exact without hard-coding a row id — the convention at `tests/test_query_router.py:615-623`.
  - `_EXPECTED_ENTITIES` is alphabetical because `query_pipeline.py:100` builds it with `sorted(set(...))`. Do not reorder it to "look natural".
  - The second test scans `json.dumps(body)` rather than `body["response"]` — the point is that no *field whatsoever* leaks raw PII, including any future one.
- **Mirror**: `tests/test_query_router.py:605-625` (exact-body assertion alongside the outbound check), `:371-382` (masked response returned to caller).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_pii_redaction_integration.py -v
  ```
  → 8 passed.

### Task 4: AC3 — the audit trail stays raw, and the four surfaces agree

- **File**: `tests/test_pii_redaction_integration.py`
- **Action**: UPDATE
- **Implement**: Append the five audit/stats tests. Read Design Note 2 before writing these — `GET /audit` does not expose previews, and that is deliberate.

  ```python
  def test_audit_row_keeps_both_raw_previews_and_raw_hashes(temp_db, monkeypatch):
      """AC3 (the actual promise, PRD RF-7): the persisted row is never masked."""
      response, _ = _post_pii_query(monkeypatch)
      entry = get_audit_log(response.json()["audit_id"])

      assert entry.prompt_preview == _PII_PROMPT
      assert entry.response_preview == _PII_RESPONSE
      assert entry.prompt_hash == hash_prompt(_PII_PROMPT)
      assert entry.response_hash == hash_prompt(_PII_RESPONSE)
      assert "<" not in entry.prompt_preview
      assert "<" not in entry.response_preview
      assert _count_audit_rows() == 1


  def test_audit_endpoint_reports_telemetry_and_leaks_no_masked_values(temp_db, monkeypatch):
      """AC3 (the endpoint half): telemetry is exposed, placeholders are not."""
      _post_pii_query(monkeypatch)

      audit = client.get("/audit", headers=_ADMIN_HEADERS)
      payload = audit.json()

      assert audit.status_code == 200
      assert payload["total"] == 1
      entry = payload["queries"][0]
      assert entry["pii_detected_input"] is True
      assert entry["pii_detected_output"] is True
      assert entry["pii_entities"] == _EXPECTED_ENTITIES
      assert entry["was_duplicate_blocked"] is False
      assert entry["suspicious_pattern_detected"] is False
      # No masking placeholder anywhere in the admin payload...
      assert "<" not in json.dumps(payload)
      # ...and no raw PII either -- /audit reports ABOUT the PII, never the PII itself.
      for fragment in _PROMPT_PII_FRAGMENTS + _RESPONSE_PII_FRAGMENTS:
          assert fragment not in json.dumps(payload)


  def test_audit_endpoint_contract_has_no_preview_fields(temp_db, monkeypatch):
      """Pins the Design Note 2 decision: previews stay OUT of the admin API.

      PRD Section 11 requires telemetry "without exposing masked values as a distinct
      new leak surface", and PRD-001 Section 10's /audit contract never carried
      previews. If a future story adds them, this test fails -- forcing that to be a
      deliberate, reviewed decision rather than a drift.
      """
      _post_pii_query(monkeypatch)

      entry = client.get("/audit", headers=_ADMIN_HEADERS).json()["queries"][0]

      assert sorted(entry) == [
          "audit_id",
          "device",
          "model",
          "pii_detected_input",
          "pii_detected_output",
          "pii_entities",
          "prompt_hash",
          "suspicious_pattern_detected",
          "timestamp",
          "user_id",
          "was_duplicate_blocked",
      ]


  def test_stats_endpoint_counts_the_pii_query(temp_db, monkeypatch):
      """AC3 sibling: /stats telemetry produced by a real pipeline run."""
      _post_pii_query(monkeypatch)

      stats = client.get("/stats", headers=_ADMIN_HEADERS).json()

      assert stats["total_queries"] == 1
      assert stats["pii_detected_queries"] == 1
      assert sorted(stats["top_pii_entities"]) == _EXPECTED_ENTITIES
      assert stats["blocked_duplicates"] == 0
      assert stats["blocked_suspicious"] == 0
      assert stats["success_rate"] == "100.0%"


  def test_all_four_surfaces_agree_about_one_request(temp_db, monkeypatch):
      """The story in one test: outbound masked, caller masked, audit raw, /audit tells."""
      response, seen = _post_pii_query(monkeypatch)
      body = response.json()
      entry = get_audit_log(body["audit_id"])
      reported = client.get("/audit", headers=_ADMIN_HEADERS).json()["queries"][0]

      assert seen == [_REDACTED_PROMPT]                       # 1. outbound  -> masked
      assert body["response"] == _REDACTED_RESPONSE           # 2. caller    -> masked
      assert entry.prompt_preview == _PII_PROMPT              # 3. audit     -> raw
      assert entry.response_preview == _PII_RESPONSE          # 3. audit     -> raw
      assert reported["audit_id"] == body["audit_id"]         # 4. same row, and it agrees:
      assert reported["pii_entities"] == body["pii_entities_masked"] == _EXPECTED_ENTITIES
      assert body["pii_redacted"] is (
          reported["pii_detected_input"] or reported["pii_detected_output"]
      )
  ```

  Notes for the implementer:
  - `test_all_four_surfaces_agree_about_one_request` is the single test to read if you want to know what PRD-003 does. Keep the surface-numbering comments; they are the reason the test is legible.
  - `assert "<" not in json.dumps(payload)` is safe precisely because `/audit` returns hashes, flags, and entity **type names** — verified: no angle bracket appears in a real payload. If this fails, something started echoing masked text into the admin view.
  - The key-set assertion in `test_audit_endpoint_contract_has_no_preview_fields` is sorted-alphabetical to match `sorted(entry)`; it was measured, not transcribed from the schema.
  - `_count_audit_rows() == 1` guards the "exactly one row per request" property that `temp_db` makes assertable — a duplicated log write would otherwise pass every other assertion here.
- **Mirror**: `tests/test_query_router.py:238-250` + `:385-397` (raw preview/hash asserts), `tests/test_integration.py:121-160` (one scenario checked through both `/audit` and `/stats`), `tests/test_pii_dedup_isolation.py:117-131`.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_pii_redaction_integration.py -v
  ```
  → 13 passed.

### Task 5: AC5 — `PII_REDACTION_ENABLED=false` turns the whole thing off

- **File**: `tests/test_pii_redaction_integration.py`
- **Action**: UPDATE
- **Implement**: Append the toggle regression guard.

  ```python
  def test_redaction_disabled_passes_both_directions_through_unmasked(temp_db, monkeypatch):
      """AC5: the config toggle from STORY-001, proven on every surface at once."""
      monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)

      response, seen = _post_pii_query(monkeypatch)
      body = response.json()
      entry = get_audit_log(body["audit_id"])
      reported = client.get("/audit", headers=_ADMIN_HEADERS).json()["queries"][0]
      stats = client.get("/stats", headers=_ADMIN_HEADERS).json()

      assert response.status_code == 200
      assert seen == [_PII_PROMPT]                  # outbound: raw, nothing masked
      assert body["response"] == _PII_RESPONSE      # caller:   raw
      assert body["pii_redacted"] is False
      assert body["pii_entities_masked"] == []
      assert entry.prompt_preview == _PII_PROMPT    # audit:    unchanged either way
      assert entry.response_preview == _PII_RESPONSE
      assert entry.pii_detected_input is False
      assert entry.pii_detected_output is False
      assert entry.pii_entities is None
      assert reported["pii_detected_input"] is False
      assert reported["pii_entities"] == []
      assert stats["pii_detected_queries"] == 0
      assert stats["top_pii_entities"] == []
  ```

  Notes for the implementer:
  - `monkeypatch.setattr(settings, ...)` must come **before** `_post_pii_query`, since `redact()` reads `settings.PII_REDACTION_ENABLED` at call time (`app/services/pii_redactor.py:50`).
  - `entry.pii_entities is None` — not `== []`. The column stays `NULL` when the entity list is empty; `app/routers/admin.py:40` is what turns that into `[]` at the API boundary. Both are asserted, one line apart, on purpose.
  - The value over `test_query_router.py:292-302` and `:470-481` is coverage of the *telemetry* half of the toggle: with redaction off, `/stats` must not report phantom PII detections.
- **Mirror**: `tests/test_query_router.py:292-302` (toggle on the prompt), `:589-602` (toggle on the signal fields).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_pii_redaction_integration.py -v
  ```
  → 14 passed.

### Task 6: AC4 — no PRD-001 test was sacrificed to get here

- **File**: `tests/test_pii_redaction_integration.py`
- **Action**: UPDATE
- **Implement**: Append the two-layer regression pin described in Design Note 5.

  ```python
  _PRE_EPIC_UNTOUCHED_TESTS = [
      "tests/test_admin_auth.py",
      "tests/test_chat_state.py",
      "tests/test_duplicate_checker.py",
      "tests/test_integration.py",
      "tests/test_openrouter_client.py",
      "tests/test_pattern_detector.py",
      "tests/test_route_reservations.py",
  ]

  _TEST_DEF = re.compile(r"^def (test_\w+)", re.MULTILINE)


  def _git(*args):
      """Run a git command at the repo root; None when git/history is unavailable."""
      try:
          result = subprocess.run(
              ["git", *args], cwd=_REPO_ROOT, capture_output=True, text=True, timeout=30
          )
      except (OSError, subprocess.SubprocessError):
          return None
      return result.stdout if result.returncode == 0 else None


  def _epic_base():
      base = _git("merge-base", "main", "HEAD")
      return base.strip() if base and base.strip() else None


  @pytest.mark.parametrize("path", _PRE_EPIC_UNTOUCHED_TESTS)
  def test_pre_epic_test_files_are_unmodified_by_this_epic(path):
      """AC4, layer 1: the PRD-001 suites this epic never needed to open."""
      base = _epic_base()
      if base is None:
          pytest.skip("git history unavailable; the census pin below still applies")

      changed = _git("diff", "--name-only", base, "--", path)
      assert changed is not None, f"git diff failed for {path}"
      assert [line for line in changed.splitlines() if line.strip()] == []


  def test_no_pre_epic_test_function_was_removed_or_renamed():
      """AC4, layer 2: catches a deletion inside a file the epic legitimately extended."""
      base = _epic_base()
      if base is None:
          pytest.skip("git history unavailable")

      listing = _git("ls-tree", "-r", "--name-only", base, "tests/")
      assert listing is not None, "git ls-tree failed"

      missing = {}
      for path in listing.split():
          if not path.endswith(".py"):
              continue
          base_source = _git("show", f"{base}:{path}")
          assert base_source is not None, f"git show failed for {path}"
          current = _REPO_ROOT / path
          current_source = current.read_text(encoding="utf-8") if current.exists() else ""
          gone = sorted(set(_TEST_DEF.findall(base_source)) - set(_TEST_DEF.findall(current_source)))
          if gone:
              missing[path] = gone

      assert missing == {}
  ```

  Notes for the implementer:
  - **Skip, don't fail, when git is unavailable** — a tarball export or shallow clone is not evidence of a regression (Design Note 6). Both tests must nonetheless *run* (not skip) in this repo; verify with `-rs`.
  - Measured while planning: the epic base is `ca561879`, all seven listed files are clean, and the census covers **86 pre-epic test functions across 14 files with zero missing**. If layer 2 fails on a first run, the failure dict names the file and the vanished test — that is a real AC4 violation to report, not a test to relax.
  - `_git()` returns `None` on non-zero exit *and* on `OSError`, so every call site checks before using the output. `_epic_base()` deliberately does not assert — it is the one call allowed to come back empty.
  - The list is hard-coded rather than derived. That is intentional: if a future story legitimately extends `test_integration.py`, this test *should* fail and force the list to be updated with a note about why.
- **Mirror**: `tests/test_pii_dedup_isolation.py:134-172` (git guard + skip semantics + parametrized file list), `:304-316` (source-census assertion returning a dict so the failure message names the offender).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_pii_redaction_integration.py -v -rs
  ```
  → 22 passed, **0 skipped**. The file is complete: 12 test functions, 22 collected cases.

  Then prove layer 2 is not vacuous:
  ```bash
  cd f:/AI/harness-ai
  .venv/Scripts/python.exe -c "
  import pathlib
  p = pathlib.Path('tests/test_integration.py')
  s = p.read_text(encoding='utf-8')
  p.write_text(s.replace('def test_happy_path_returns_success_and_logs_exactly_one_row',
                         'def test_TRIPWIRE_renamed'), encoding='utf-8')
  "
  .venv/Scripts/python.exe -m pytest tests/test_pii_redaction_integration.py -k "pre_epic or removed_or_renamed" -q   # MUST FAIL (both layers)
  git checkout -- tests/test_integration.py
  .venv/Scripts/python.exe -m pytest tests/test_pii_redaction_integration.py -k "pre_epic or removed_or_renamed" -q   # MUST PASS
  git status --porcelain
  ```
  → fails while the tripwire is present, passes after restore, working tree clean apart from the new test file. A guard that cannot fail is not a guard.

### Task 7: Full-suite regression and scope check

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - Full suite green at **202 passed** (180 baseline + 22 new). A different number means a test was accidentally modified or a case was added beyond the plan.
  - `git status --porcelain` lists **exactly one** new file: `?? tests/test_pii_redaction_integration.py`. No `app/` entry (Design Note 9), no `tests/conftest.py` (Design Note 7), no `harness_ai.db` (Design Note 10).
  - The seven files in `_PRE_EPIC_UNTOUCHED_TESTS` are absent from `git diff` against the epic base — run once by hand as a cross-check on the test itself.
  - No test in the new file is `xfail`, `skip`, or commented out; `-rs` reports no skips in this repo.
  - PRD Section 11's MVP checklist can now be ticked from test output alone — note in the report which test covers each line.
- **Mirror**: [[STORY-008]] plan Task 6 — same scope gate, adjusted file list.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai
  .venv/Scripts/python.exe -m pytest -q
  .venv/Scripts/python.exe -m pytest tests/test_pii_redaction_integration.py -v -rs
  git status --porcelain
  git diff --name-only $(git merge-base main HEAD) -- tests/test_integration.py tests/test_duplicate_checker.py tests/test_pattern_detector.py tests/test_admin_auth.py tests/test_openrouter_client.py tests/test_chat_state.py tests/test_route_reservations.py
  ```
  → full suite green; the new file's 22 cases pass with no skips; `git status --porcelain` shows only `?? tests/test_pii_redaction_integration.py`; the `git diff` prints nothing.

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `.venv/Scripts/python.exe -m pytest tests/test_pii_redaction_integration.py -v -rs` → 22 passed, 0 skipped
- [ ] `.venv/Scripts/python.exe -m pytest -q` → full suite green, **202 passed** (baseline 180 in 8.9s + 22)
- [ ] `git status --porcelain` → only `?? tests/test_pii_redaction_integration.py`
- [ ] Tripwire check for AC4, both layers — see Task 6's second Validate block: rename a PRD-001 test, watch both guards fail, `git checkout --` to restore, watch them pass
- [ ] Behavioural proof against the real redactor and a real DB, driving the HTTP surface end-to-end (temp DB — never the repo-root `harness_ai.db`, Design Note 10):
  ```bash
  cd f:/AI/harness-ai && PYTHONPATH=f:/AI/harness-ai .venv/Scripts/python.exe -c "
  import os, tempfile, pathlib, json
  os.environ.setdefault('OPENROUTER_API_KEY','k'); os.environ.setdefault('ADMIN_TOKEN','t')
  from app.config import settings
  settings.DATABASE_URL = f'sqlite:///{pathlib.Path(tempfile.mkdtemp())}/e2e.db'
  from fastapi.testclient import TestClient
  from app.db.database import get_audit_log, init_db
  from app.main import app
  from app.services.openrouter_client import OpenRouterResult
  import app.routers.query as qr
  init_db()
  PROMPT = 'my name is Maria Gomez, my email is juan@empresa.com and my phone is 555-123-4567'
  ANSWER = 'Please contact John Smith at john.smith@acme.com or 212-555-0199.'
  seen = []
  qr.call_openrouter = lambda p, model='gpt-4', api_key=None: (seen.append(p), OpenRouterResult(response=ANSWER, model_used=model, tokens_used=9))[1]
  c = TestClient(app)
  r = c.post('/query', json={'user_id':'e2e@empresa.com','prompt':PROMPT,'device':'Chrome/Windows'})
  body = r.json()
  print('OUTBOUND :', seen[0])
  print('CALLER   :', body['response'], '|', body['pii_redacted'], body['pii_entities_masked'])
  entry = get_audit_log(body['audit_id'])
  print('AUDIT RAW:', entry.prompt_preview, '||', entry.response_preview)
  h = {'Authorization': f\"Bearer {settings.ADMIN_TOKEN}\"}
  audit = c.get('/audit', headers=h).json(); stats = c.get('/stats', headers=h).json()
  print('/audit   :', audit['queries'][0])
  print('/stats   :', stats['pii_detected_queries'], stats['top_pii_entities'])
  for frag in ('Maria Gomez','juan@empresa.com','555-123-4567'):
      assert frag not in seen[0], f'RAW PII REACHED OPENROUTER: {frag}'
  for frag in ('John Smith','john.smith@acme.com','212-555-0199'):
      assert frag not in json.dumps(body), f'RAW PII REACHED CALLER: {frag}'
  assert entry.prompt_preview == PROMPT and entry.response_preview == ANSWER, 'AUDIT WAS MASKED (RF-7 violation)'
  assert '<' not in json.dumps(audit), 'MASKED VALUE LEAKED INTO /audit'
  assert audit['queries'][0]['pii_entities'] == body['pii_entities_masked']
  print('OK')
  "
  ```
  → `OUTBOUND` and `CALLER` show only `<PERSON>` / `<EMAIL_ADDRESS>` / `<PHONE_NUMBER>`; `AUDIT RAW` shows both originals verbatim; `/audit` and `/stats` report the same three entity types; then `OK`
- [ ] `.venv/Scripts/python.exe -c "from app.main import app; print('ok')"` → backend imports cleanly
- [ ] `.venv/Scripts/python.exe -m uvicorn app.main:app` → server starts without error; `curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] Against the running server, `POST /query` with a clean prompt → HTTP 200, `"pii_redacted": false`, `"pii_entities_masked": []` — the additive fields are present on the no-PII path too (PRD Section 10)
- [ ] `git status --porcelain` after all probes → `harness_ai.db` **not** listed
- [ ] If any command raises `sqlite3.OperationalError: table audit_logs has no column named pii_detected_input`, the local `harness_ai.db` predates [[STORY-003]] — delete it and re-run

---

## Validation

```bash
cd f:/AI/harness-ai
.venv/Scripts/python.exe -m pytest tests/test_pii_redaction_integration.py -v -rs
.venv/Scripts/python.exe -m pytest -q
git status --porcelain
git diff --name-only $(git merge-base main HEAD) -- tests/test_integration.py tests/test_duplicate_checker.py tests/test_pattern_detector.py tests/test_admin_auth.py tests/test_openrouter_client.py tests/test_chat_state.py tests/test_route_reservations.py
.venv/Scripts/python.exe -c "from app.main import app; print('ok')"
.venv/Scripts/python.exe -m uvicorn app.main:app
curl http://localhost:8000/health
```

Frontend lint: N/A — this repo has no npm frontend (Reflex/Python project, no `package.json`), consistent with the [[STORY-003]] through [[STORY-009]] reports.

---

## Acceptance Criteria

(Copied from story `STORY-010`)

- [ ] Given a full `POST /query` request with PII in the prompt, when run against a mocked `call_openrouter`, then the mock's recorded call args contain only redacted text — never the raw PII. *(Task 2)*
- [ ] Given the mocked OpenRouter response also contains PII, when the request completes, then the HTTP response body's `response` field is the masked version, and `pii_redacted`/`pii_entities_masked` match PRD Section 10's shape. *(Task 3)*
- [ ] Given the same request, when the audit row is fetched via `GET /audit` (admin token), then `prompt_preview`/`response_preview` are the **raw**, unmasked originals. *(Task 4 — **satisfied in intent, not literally**: `GET /audit` exposes no preview fields by design. Raw previews are asserted against the persisted row via `get_audit_log()`; the endpoint's real contract is asserted separately and pinned. See Design Note 2 — this needs reviewer sign-off, or its own story if the literal API change is wanted.)*
- [ ] Given the full existing PRD-001 test suite (`tests/test_integration.py`, `tests/test_query_router.py`, etc.), when run alongside the new PII tests, then all pass unmodified — no regressions introduced by this epic. *(Task 6 + Task 7 — see Design Note 5 for how "unmodified" is read)*
- [ ] Given `PII_REDACTION_ENABLED=false`, when the same request runs, then prompt/response pass through unmasked (regression guard for the config toggle from [[STORY-001]]). *(Task 5)*
- [ ] All tasks completed
- [ ] Full test suite (`.venv/Scripts/python.exe -m pytest`) passes — 180 baseline + 22 new, zero existing tests modified
- [ ] Backend server starts without error
- [ ] Exactly one file added — `tests/test_pii_redaction_integration.py`; **no `app/` file changed** by this story
- [ ] All four surfaces (outbound payload, response body, audit row, `/audit`+`/stats`) asserted about **the same single request**
- [ ] Every PII constant used is a measured value from this branch's redactor, not a guess (Design Note 4)
- [ ] Both AC4 guard layers demonstrated to fail against a tripwire, then restored (Task 6)
- [ ] No test in the new file is skipped in this repo (`-rs` reports none)
- [ ] Repo-root `harness_ai.db` unchanged; `git status --porcelain` clean apart from the new test file
- [ ] Follows existing patterns (env-var preamble before `app.*` imports, locally-defined `temp_db`/`_count_audit_rows`, string-target patch for `app.routers.query.call_openrouter`, measured-constant block, no `conftest.py`)
