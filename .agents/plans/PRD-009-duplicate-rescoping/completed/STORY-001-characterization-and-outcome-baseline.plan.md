---
story: STORY-001
prd: PRD-009
slug: characterization-and-outcome-baseline
title: "Characterization tests of today's duplicate lookup and the six-outcome /query baseline, on untouched production code"
type: REFACTOR
complexity: MEDIUM
epic_branch: epic/PRD-009-duplicate-rescoping        # all stories commit here, no per-story branch
created: 2026-09-16
---

# Plan: Characterization tests of today's duplicate lookup and the six-outcome /query baseline

## Summary

Add two new test modules and change nothing else. `tests/test_duplicate_characterization.py` pins five behaviours of today's global `prompt_hash` lookup (`app/db/database.py:758-769`), each observed end to end through `POST /query`. The five are: an `OpenRouterError` row blocks the retry, an input `PiiRedactorError` row blocks the retry, a policy-denial row blocks the allowed resend, user A's row blocks user B, and a duplicate-blocked row chains the window. Each test is named and documented as **pre-PRD-009 behaviour**, together with the decision and story that will flip it. `tests/test_query_outcomes_regression.py` pins the six `/query` outcomes of PRD Section 11 (status code, body, audit-row count). The inputs are chosen so that the module stays green through every later story without edits. Both modules reuse the existing fixture, seeding, spy and fake-OpenRouter idioms from `tests/test_query_router.py` and `tests/test_pii_dedup_isolation.py`. `app/` and every existing test file stay untouched.

The story's `type` is `technical`. It maps to REFACTOR here because it adds test-only safety scaffolding before a behaviour change.

## User Story

As a security admin
I want today's duplicate behaviour pinned by tests before any production line changes
So that each behaviour change later in PRD-009 shows up as a deliberate, cited edit to an existing assertion, never as a test that silently started passing

## Story Reference

- Story file: `.agents/stories/PRD-009-duplicate-rescoping/STORY-001-characterization-and-outcome-baseline.md`
- PRD: `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md` (Sections 4, 6.3, 6.4, 7 F1, 11, 12 Phase 1)

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (story type: technical, test-only) |
| Complexity | MEDIUM |
| Systems Affected | `tests/` only (two new files). No `app/` change |
| Story | STORY-001 |
| PRD | PRD-009 |
| Epic Branch | `epic/PRD-009-duplicate-rescoping` (does not exist yet: create from `main` in Task 0, then commit directly on it) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design` (UI visual design). This story changes no UI surface, and its frontmatter lists `skills: []`. No skill rule applies. | — |

---

## Patterns to Follow

### Module prologue, fixture override, row counting
```python
# SOURCE: tests/test_query_router.py:1-49
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
...
_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}

client = TestClient(app, headers=_AUTH_HEADERS)

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's authenticated user."""
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return temp_db


def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]
```

### Two users (cross-user case)
```python
# SOURCE: tests/test_pii_dedup_isolation.py:32-57
_JUAN_TOKEN = "juan-token"
_MARIA_TOKEN = "maria-token"
_JUAN_HEADERS = {"Authorization": f"Bearer {_JUAN_TOKEN}"}
_MARIA_HEADERS = {"Authorization": f"Bearer {_MARIA_TOKEN}"}

client = TestClient(app)

@pytest.fixture
def temp_db(temp_db):
    insert_user(User(user_id="juan@empresa.com", role="user", token_hash=hash_token(_JUAN_TOKEN)))
    insert_user(User(user_id="maria@empresa.com", role="user", token_hash=hash_token(_MARIA_TOKEN)))
    return temp_db
```

### Seeding a backdated row (ageing / chaining case)
```python
# SOURCE: tests/test_query_router.py:52-63  (and tests/test_duplicate_checker.py:21-35)
def _seed_duplicate(prompt: str, hours_ago: float = 2) -> str:
    timestamp = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
        _TIMESTAMP_FORMAT
    )
    insert_audit_log(
        AuditLog(timestamp=timestamp, user_id="juan@empresa.com", prompt_hash=hash_prompt(prompt))
    )
    return timestamp
```

### Error arms: fakes and spies
```python
# SOURCE: tests/test_query_router.py:66-67, 239-259, 295-296, 405-416
def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")

def _raise_openrouter_error(prompt, model="gpt-4", api_key=None):
    raise OpenRouterError("boom")
monkeypatch.setattr("app.routers.query.call_openrouter", _raise_openrouter_error)
# -> 502, one row, entry.success is False, entry.error_message == "boom"

def _boom(text):
    raise PiiRedactorError("PII analysis failed: analyzer exploded")
monkeypatch.setattr(query_pipeline, "redact", _boom)
# -> 500, _count_audit_rows() == before + 1

# Reading the latest row
with get_connection() as conn:
    row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
entry = get_audit_log(row["id"])
```

### Policy refusal over HTTP (outcome 4, not the router's 401/403)
```python
# SOURCE: tests/test_rbac.py:202-231
response = client.post("/query", headers=..., json={"prompt": ..., "model": "not-a-real-model"})
assert response.status_code == 200
assert body["status"] == "BLOCKED"
assert body["required_permission"] == "query:model:not-a-real-model"
# audit row: denied_permission == "query:model:not-a-real-model"
```

### Storage failure (outcome 6b)
```python
# SOURCE: tests/test_query_router.py:191-218
monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
with get_connection() as conn:
    conn.execute("DROP TABLE audit_logs")
response = client.post("/query", json={"user_id": "juan@empresa.com", "prompt": "hello world"})
assert response.status_code == 500
assert "Duplicate lookup failed" in response.json()["detail"]
# NOTE: asserts no row count. With audit_logs dropped, no row can exist.
```

### Error handling (production, observed, not changed)
```python
# SOURCE: app/routers/query.py (except chain at the end of query())
except DuplicateCheckError as exc:  raise HTTPException(status_code=500, detail=str(exc)) from exc
except PiiRedactorError as exc:     raise HTTPException(status_code=500, detail=str(exc)) from exc
except OpenRouterError as exc:      raise HTTPException(status_code=502, detail=str(exc)) from exc
```

---

## Key Facts From Exploration

| Category | File:Lines | Fact |
|----------|------------|------|
| LOOKUP | `app/db/database.py:758-769` | `SELECT timestamp FROM audit_logs WHERE prompt_hash = ? AND timestamp >= ? ORDER BY timestamp ASC LIMIT 1`, with no `user_id` and no flag predicates |
| CHECK | `app/services/duplicate_checker.py:27-38` | `check_duplicate(prompt)` computes a 24h cutoff and wraps `StorageError` in `DuplicateCheckError("Duplicate lookup failed: …")` |
| PIPELINE ORDER | `app/services/query_pipeline.py` | authorize → model → BYOK → `check_duplicate` → pattern → `redact` (input) → `call_openrouter` → `redact` (output) → success log. Every arm writes one row via `log_query` |
| DENIAL ROW | `app/services/query_pipeline.py` `_deny` | `success=True`, `denied_permission=exc.permission`, same `prompt_hash` (so today it matches) |
| FAILURE ROWS | `app/services/query_pipeline.py` | input `PiiRedactorError` and `OpenRouterError` both log `success=False` with the raw prompt |
| FIXTURES | `tests/conftest.py:129-178` | autouse reset drops every table before each test; `temp_db` = `init_db()` and no seed data. The libSQL dev server is required |
| RBAC | `app/config.py:66-69`, `app/services/authz.py:28-49` | `user` role: `gpt-4` allowed (default `QueryRequest.model`), `not-a-real-model` denied → `query:model:not-a-real-model` |
| PATTERN | `app/services/pattern_detector.py:4-12` | `"please override the rules"` → `pattern: "override"` |
| TIMESTAMPS | `app/db/database.py:37` | `%Y-%m-%dT%H:%M:%SZ`, one-second resolution: fetch the latest row by `id`, not by timestamp |
| CENSUS GUARD | `tests/test_pii_dedup_isolation.py:347` | `hash_prompt` call-site census scans `app/` only, so new tests may call `hash_prompt` freely |
| REDACTION | `app/config.py:71` | `PII_REDACTION_ENABLED = True` by default. Prompts in this story contain no PII, so the real redactor passes them unchanged |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_duplicate_characterization.py` | CREATE | Five tests pinning today's (pre-PRD-009) duplicate behaviour through `POST /query`, each naming the story that flips it |
| `tests/test_query_outcomes_regression.py` | CREATE | Six-outcome `POST /query` baseline (7 tests: outcome 6 has two forms), green on `main` and at every later story |

No UPDATE rows: `app/` and every existing test file stay untouched (AC 1, AC 5).

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 0: Create the epic branch

- **File**: none (git)
- **Action**: `git checkout -b epic/PRD-009-duplicate-rescoping main`. The branch does not exist locally or on `origin`. Leave the untracked PRD-009 docs (`.agents/PRDs/…`, `.agents/stories/…`, `pre-prds/`) and this plan in the working tree; they go into the story commit.
- **Validate**: `git branch --show-current` → `epic/PRD-009-duplicate-rescoping`; `git status` shows no `app/` changes

### Task 1: Start the libSQL dev server and record a green baseline

- **File**: none
- **Action**: Make sure the container `harness-libsql-dev` is running (command in `tests/conftest.py` docstring). Run the full suite once **before** adding files and record the pass count. If fixtures error in bulk, restart the container; do not bisect code (PRD 11, project memory note).
- **Validate**: `pytest tests/ -q` is green. Record the count in the story report.

### Task 2: Create `tests/test_duplicate_characterization.py` scaffolding

- **File**: `tests/test_duplicate_characterization.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring. It states that the module pins **pre-PRD-009 behaviour** of `find_duplicate_timestamp` (`WHERE prompt_hash = ? AND timestamp >= ?`), that these are known defects rather than requirements, and that later stories flip them deliberately with a comment citing PRD-009 Section 6.3/6.4: D1/D3 and failure rows → STORY-004; cross-user → STORY-005.
  - Prologue exactly as `tests/test_query_router.py:1-4`.
  - Imports: `TestClient`, `app.main.app`, `import app.services.query_pipeline as query_pipeline`, `get_audit_log`, `get_connection`, `insert_audit_log`, `insert_user`, `AuditLog`, `User`, `hash_prompt`, `hash_token`, `OpenRouterError`, `OpenRouterResult`, `PiiRedactorError`.
  - Two users, mirroring `tests/test_pii_dedup_isolation.py:32-57` (juan/maria, `role="user"`, `client = TestClient(app)`, per-request headers). A `temp_db` override seeds both.
  - Private helpers: `_count_audit_rows()`, `_latest_entry()` (by `id DESC`), `_timestamp(hours_ago)`, `_fail_if_called`, a `_fake_success(prompt, model="gpt-4", api_key=None)` returning `OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)`, and a `_counting_success(calls: list)` factory so a test can assert the model was reached exactly once.
  - Every test uses a **distinct** prompt so no test depends on another's rows (the autouse reset already isolates them; this is belt and braces for readers).
- **Mirror**: `tests/test_query_router.py:1-67`, `tests/test_pii_dedup_isolation.py:1-66`
- **Validate**: `pytest tests/test_duplicate_characterization.py -q` collects with 0 tests and no import error

### Task 3: Pin "OpenRouterError row blocks the retry"

- **File**: `tests/test_duplicate_characterization.py`
- **Action**: UPDATE (new file from Task 2)
- **Implement**: `test_pre_prd009_openrouter_failure_row_blocks_same_prompt_retry`. Docstring: *"Pins pre-PRD-009 behaviour (defect #1, PRD Section 1). Flipped by STORY-004: failed rows stop counting."*
  1. Patch `app.routers.query.call_openrouter` with a raiser of `OpenRouterError("boom")`. POST as juan → assert `502`. Read `_latest_entry()`: `success is False`, capture `failed_at = entry.timestamp`.
  2. Re-patch `call_openrouter` with `_fail_if_called`. POST the same prompt as juan → assert `200` and body `== {"status": "BLOCKED", "reason": "Duplicate query within 24 hours", "first_query_at": failed_at}`.
  3. `_latest_entry().was_duplicate_blocked is True`; total rows == 2.
- **Mirror**: `tests/test_query_router.py:239-259`
- **Validate**: `pytest tests/test_duplicate_characterization.py -k openrouter -q` passes on untouched `main`

### Task 4: Pin "input PiiRedactorError row blocks the retry"

- **File**: `tests/test_duplicate_characterization.py`
- **Action**: UPDATE
- **Implement**: `test_pre_prd009_input_redactor_failure_row_blocks_same_prompt_retry`. Docstring cites defect #1 and says it flips in STORY-004.
  1. `monkeypatch.setattr(query_pipeline, "redact", _boom)`, where `_boom` raises `PiiRedactorError`, and `call_openrouter` = `_fail_if_called`. POST → `500`. `_latest_entry().success is False`; capture its timestamp.
  2. Restore the real redactor via `monkeypatch.setattr(query_pipeline, "redact", real_redact)`, with `real_redact` captured before step 1, and keep `_fail_if_called`. POST the same prompt → `200` BLOCKED duplicate with `first_query_at` == the failed row's timestamp.
  - Restoring the redactor proves the block comes from the duplicate check, not from a second redactor failure (the check runs before `redact`, but the test should not rely on the reader knowing that).
- **Mirror**: `tests/test_query_router.py:295-296, 405-416`
- **Validate**: `pytest tests/test_duplicate_characterization.py -k redactor -q` passes

### Task 5: Pin "policy-denial row blocks the allowed resend"

- **File**: `tests/test_duplicate_characterization.py`
- **Action**: UPDATE
- **Implement**: `test_pre_prd009_policy_denial_row_blocks_same_user_resend_with_allowed_model`. Docstring cites D1 and says it flips in STORY-004.
  1. `call_openrouter` = `_fail_if_called`. POST as juan with `"model": "not-a-real-model"` → `200`, `status == "BLOCKED"`, `required_permission == "query:model:not-a-real-model"`. `_latest_entry()`: `denied_permission == "query:model:not-a-real-model"`, `success is True`; capture its timestamp.
  2. POST the same prompt as juan with `"model": "gpt-4"` → `200` BLOCKED duplicate with `first_query_at` == the denial row's timestamp. Rows == 2.
- **Mirror**: `tests/test_rbac.py:202-231`
- **Validate**: `pytest tests/test_duplicate_characterization.py -k denial -q` passes

### Task 6: Pin "user A's row blocks user B"

- **File**: `tests/test_duplicate_characterization.py`
- **Action**: UPDATE
- **Implement**: `test_pre_prd009_row_from_one_user_blocks_same_prompt_from_another_user`. Docstring cites defect #2 / T2 and says it flips in **STORY-005**.
  1. `calls = []`; patch `call_openrouter` with `_counting_success(calls)`. POST as juan → `200 SUCCESS`; `juan_at = get_audit_log(body["audit_id"]).timestamp`.
  2. POST the identical prompt with maria's headers → `200` BLOCKED duplicate, `first_query_at == juan_at`. `len(calls) == 1`. `_latest_entry().user_id == "maria@empresa.com"` and `was_duplicate_blocked is True`.
- **Mirror**: `tests/test_pii_dedup_isolation.py` (juan/maria headers), `tests/test_query_router.py:114` (`audit_id` → `get_audit_log`)
- **Validate**: `pytest tests/test_duplicate_characterization.py -k another_user -q` passes

### Task 7: Pin "a duplicate-blocked row chains the window" (PRD 6.4)

- **File**: `tests/test_duplicate_characterization.py`
- **Action**: UPDATE
- **Implement**: `test_pre_prd009_duplicate_blocked_row_keeps_window_alive_after_original_ages_out`. Docstring reproduces the 6.4 timeline (A success at −25h, B duplicate-blocked at −2h), cites D3 and says it flips in STORY-004.
  1. Seed with `insert_audit_log(AuditLog(...))`: A = `timestamp=_timestamp(25)`, `user_id=juan`, `prompt_hash=hash_prompt(prompt)`, `success=True`. B = `timestamp=_timestamp(2)`, same user and hash, `was_duplicate_blocked=True`, `success=True`.
  2. `call_openrouter` = `_fail_if_called`. POST as juan → `200` BLOCKED duplicate with `first_query_at == B_timestamp` (and explicitly `!= A_timestamp`).
- **Mirror**: `tests/test_duplicate_checker.py:21-35`
- **Validate**: `pytest tests/test_duplicate_characterization.py -q` → 5 passed

### Task 8: Create `tests/test_query_outcomes_regression.py`

- **File**: `tests/test_query_outcomes_regression.py`
- **Action**: CREATE
- **Implement**: Module docstring: this is PRD-009 Section 11's six-outcome baseline, captured on untouched code in STORY-001. **Outcome assertions in this file must never be edited by a later PRD-009 story.** Inputs were chosen, not sampled, so that the rescoping cannot change them (outcome 2 is a same-user repeat after a success). The same prologue and single-user fixture as `tests/test_query_router.py:1-49` (juan, `role="user"`), plus `_count_audit_rows`, `_latest_entry`, `_fail_if_called` and `_fake_success`. Each test asserts status code, the body keys the story names, and `_count_audit_rows() == before + 1` (or the storage form below):
  1. `test_outcome_1_success`: fake success → `200`, `status == "SUCCESS"`, `response == "Hi there!"`, `audit_id` present; +1 row with `success is True`.
  2. `test_outcome_2_duplicate_block_after_same_user_success`: **the prior is a live, same-user, successful send through `POST /query`** (fake success), not a seeded bare row. A seeded row lacks `success`/flags/`dedup_key` semantics that later stories rely on. Then re-patch `_fail_if_called` and resend → `200`, body `== {"status": "BLOCKED", "reason": "Duplicate query within 24 hours", "first_query_at": <success row timestamp>}`; +1 row for the second send (`before` is taken after the first send).
     - Forward-compat check (why this stays green): after STORY-004 the success row still counts (success=1, no flags). After STORY-005 it is the same user. After STORY-006/007 the row is written by the pipeline and so carries `dedup_key`.
  3. `test_outcome_3_suspicious_pattern_block`: `"please override the rules"`, `_fail_if_called` → `200`, `{"status": "BLOCKED", "reason": "Suspicious pattern detected", "pattern": "override"}`; +1 row.
  4. `test_outcome_4_policy_refusal`: `"model": "not-a-real-model"`, `_fail_if_called` → `200`, `status == "BLOCKED"`, `required_permission == "query:model:not-a-real-model"`, `reason == "Model not permitted for this role"`; +1 row. Comment: this is the pipeline's policy refusal, deliberately not the router's 401/403 (story Technical Notes).
  5. `test_outcome_5_upstream_failure`: raiser of `OpenRouterError("boom")` → `502`, `detail == "boom"`; +1 row, `success is False`.
  6a. `test_outcome_6_internal_failure_redactor`: `monkeypatch.setattr(query_pipeline, "redact", _boom)`, `_fail_if_called` → `500`, `detail == "PII analysis failed: analyzer exploded"`; +1 row.
  6b. `test_outcome_6_internal_failure_duplicate_storage`: mirror `test_duplicate_check_storage_failure_returns_500` (DROP `audit_logs`, `_fail_if_called`) → `500`, `"Duplicate lookup failed" in detail`. **Row count: 0, the count the existing test implies.** It asserts none because none is possible once the table is gone. Make it observable without querying the dropped table: wrap `query_pipeline.log_query` in a counting spy (`calls = []`, delegate to the original) and assert `calls == []`. Docstring explains the choice and records the Appendix discrepancy (README:329 says "lets the query through"; the tested behaviour is 500).
  - Use distinct prompts per test.
- **Mirror**: `tests/test_query_router.py:191-259, 405-416`; `tests/test_rbac.py:202-231`
- **Validate**: `pytest tests/test_query_outcomes_regression.py -q` → 7 passed

### Task 9: Prove no production or pre-existing test file changed

- **File**: none
- **Action**: Verify the diff is exactly two new test files.
- **Validate**:
  - `git status --porcelain -- app/ tests/` lists only `?? tests/test_duplicate_characterization.py` and `?? tests/test_query_outcomes_regression.py`
  - `git diff --stat main -- app/ tests/` is empty (tracked files unchanged)

### Task 10: Full suite green

- **File**: none
- **Action**: Run the full suite. Mass fixture errors mean restarting `harness-libsql-dev`, not changing code. If a characterization test cannot pass on `main`, **stop**: do not touch `app/`. Record the finding in the story report (the test or the PRD premise is wrong).
- **Validate**: `pytest tests/ -q` → baseline count from Task 1 + 12, 0 failed

---

## End-to-End Tests

For `/implement` to execute. All go through `POST /query` via `TestClient`, which is this story's E2E surface; there is no UI change.

- [ ] `pytest tests/test_duplicate_characterization.py -v`: 5 passed, each name contains `pre_prd009`, and each docstring names STORY-004 or STORY-005
- [ ] `pytest tests/test_query_outcomes_regression.py -v`: 7 passed (outcomes 1–5, 6 redactor, 6 storage)
- [ ] Sanity (mutation) check, **reverted before commit and never committed**: temporarily add `AND success = 1` to `find_duplicate_timestamp` locally. The OpenRouter and redactor characterization tests must go red, and outcome 2 must stay green. Revert with `git checkout -- app/db/database.py` and confirm `git diff -- app/` is empty. This shows the tests would detect STORY-004's change and that outcome 2 is correctly chosen.
- [ ] `pytest tests/ -q`: full suite green

---

## Validation

```bash
docker start harness-libsql-dev   # or the docker run command in tests/conftest.py
pytest tests/test_duplicate_characterization.py tests/test_query_outcomes_regression.py -v
pytest tests/ -q
git status --porcelain -- app/ tests/
git diff --stat main -- app/ tests/
```

(No frontend and no server-start change: the template's `npm run lint` / `uvicorn` checks don't apply. Nothing under `app/` or `chat_ui/` moves.)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| One-second timestamp resolution makes "latest row" ambiguous | Read rows by `ORDER BY id DESC` or by `audit_id`, never by timestamp (`list_audit_logs` sorts by timestamp) |
| Real Presidio redactor adds latency or flakiness to success paths | Prompts contain no PII. The existing suite already runs the real redactor on success paths (`tests/test_query_router.py`) |
| Chaining test is sensitive to the 24h boundary | Uses −25h and −2h, well clear of the ±1 min boundary already covered in `tests/test_duplicate_checker.py` |
| Outcome 6b row count cannot be read from a dropped table | Assert through a `log_query` spy (0 calls), documented in the docstring |
| A characterization test fails on `main` | Stop and record it; never edit `app/` (story Technical Notes) |
| libSQL dev server degrades across repeated runs | Restart the container; do not bisect code |

---

## Acceptance Criteria

(Copied from story `STORY-001`)

- [ ] Given a new `tests/test_duplicate_characterization.py` and **no change under `app/`**, when it runs against `main`, then it passes and pins each of today's behaviours with one test apiece, observed through `POST /query`:
  - a `success=0` row from an `OpenRouterError` blocks the same prompt's retry
  - a `success=0` row from an input `PiiRedactorError` blocks the retry
  - a policy-denial row (`denied_permission` set, `success=1`) blocks the same prompt from the same user with an allowed model
  - a row written by user A blocks the same prompt from user B
  - a duplicate-blocked row keeps the window alive once the original has aged out (A at −25h, B blocked at −2h, new send → `BLOCKED`, `first_query_at == B.timestamp`)
- [ ] Each characterization test's name or docstring states it pins **pre-PRD-009 behaviour** and names the decision or story expected to flip it (D1/D3 → STORY-004, cross-user → STORY-005)
- [ ] `tests/test_query_outcomes_regression.py` pins the six outcomes through `POST /query` (status, body `status`/`reason`/`required_permission` or `detail`, audit-row count), with outcome 6 in both forms (redactor: 1 row; duplicate storage: the count the existing test observes)
- [ ] Outcome 2 seeds its prior as a **same-user, successful** send
- [ ] Full suite passes; no pre-existing test file modified
- [ ] All tasks completed
- [ ] No `app/` change (replaces "backend server starts" / "frontend lint": neither surface is touched)
- [ ] Follows existing patterns
