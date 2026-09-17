---
story: STORY-009
prd: PRD-009
slug: outcome-regression-and-reporting-invariance
title: "Six-outcome regression and /audit, /stats and admin-console invariance verified on the finished epic"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-009-duplicate-rescoping
created: 2026-09-17
---

# Plan: Six-outcome regression and /audit, /stats and admin-console invariance verified on the finished epic

## Summary

This is a verification story. It checks that PRD-009 left the `POST /query` outcomes and every reporting surface unchanged. It proves this in three ways:

- **Git evidence.** The regression module is unmodified since STORY-001. The diffs of `tests/test_query_router.py` and `tests/test_integration.py` since the epic base are listed hunk by hunk.
- **Existing modules, run unmodified.** `tests/test_query_outcomes_regression.py` and `tests/test_two_instance_smoke.py` run on the epic head without edits.
- **One new test module, `tests/test_reporting_invariance.py`.** It seeds a fixed set of pipeline-written rows through real `POST /query` requests: successes, both kinds of block, a denial, both kinds of failure, and two users. It then asserts:
  - `GET /stats` and `summary_snapshot()` report the same figures, and `blocked_duplicates` counts exactly the `was_duplicate_blocked = 1` rows.
  - `GET /audit` and the console's `AuditRow` expose no `dedup_key`.
  - Every new row's `prompt_hash == hash_prompt(prompt)`.
  - A successful `/query` issues exactly one lookup and one audit insert.

No production code changes are expected. If one turns out to be needed, an earlier story regressed. Fix it in a separate commit and name it in the report.

## User Story

As an integrating developer and a compliance admin
I want proof that `POST /query`'s outcomes and every reporting surface are unchanged by the rescoping
So that nothing built against the API and no historical figure moved

## Story Reference

- Story file: `.agents/stories/PRD-009-duplicate-rescoping/STORY-009-outcome-regression-and-reporting-invariance.md`
- PRD: `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md` (Sections 5 stories 6–7, 6.5, 10, 11 six outcomes + quality indicators, 12 Phase 4)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (tests + verification only; story `type: technical`) |
| Complexity | LOW |
| Systems Affected | `tests/` only. Subjects under test: `app/routers/admin.py` (`/audit`, `/stats`), `app/db/database.py` (`summary_snapshot`, `_SUMMARY_SQL`, `find_duplicate_timestamp`, `insert_audit_log`), `app/models/schemas.py::AuditQueryEntry`, `chat_ui/chat_ui/admin_models.py::AuditRow`, `app/services/query_pipeline.py` |
| Story | STORY-009 |
| PRD | PRD-009 |
| Epic Branch | `epic/PRD-009-duplicate-rescoping` (commit directly on this branch) |
| Dependencies | STORY-008 ✅ done (`7302bd9`) |
| Epic base | `57f2d67` (`git merge-base main HEAD`); STORY-001 commit `9abef61` |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | I scanned `.agents/skills/` and read `frontend-design/SKILL.md` in full. It covers UI visual design. The story's `skills: []` is empty, and this story changes no UI surface; it only reads `AuditRow.model_fields`. No rule applies. | — |

---

## Facts the design depends on (verified during planning)

1. **AC 1 already holds on git.** `git log -- tests/test_query_outcomes_regression.py` shows only `9abef61`. `git diff 9abef61..HEAD -- tests/test_query_outcomes_regression.py` is empty.
2. **AC 2 has a deviation to report, not fix.**
   - `git diff 57f2d67..HEAD -- tests/test_integration.py` is **empty**.
   - `tests/test_query_router.py` has **4 hunks**, and only the last one is a spy wrapper signature:
     1. `+from dataclasses import dataclass` (import).
     2. `dedup_key` added to the `duplicate_checker` import.
     3. New `_Turn` dataclass and `_key()` helper.
     4. `_seed_duplicate()` now seeds `dedup_key=_key(...)`, with a STORY-007 / D6 comment. This is a **seed-helper change**: a seeded prior without a key is a pre-PRD row and would no longer match.
     5. `_spy_duplicate(prompt)` → `_spy_duplicate(user_id, key)`, with a PRD-009 Section 6.5 comment. This is the spy signature change.

     Hunks 1–4 support hunk 5 and the seed. None changes a status-code, body or row-count assertion. The report lists each hunk verbatim and names hunk 4 as outside the literal wording "only spy wrapper signatures". The rationale: the seed has to carry the key the pipeline now writes, so the test keeps asserting the same outcome. Hunk 4 is **not** reverted, because reverting it would turn the duplicate tests red.
3. **`GET /stats` reads `summary_snapshot(row_limit=0)`** (`app/routers/admin.py:101`). `blocked_duplicates` is `(SELECT COUNT(*) FROM audit_logs WHERE was_duplicate_blocked = 1)` (`app/db/database.py:1164`). `app/routers/admin.py`, `app/models/` and `chat_ui/` have **no diff** since `57f2d67`.
4. **`_SUMMARY_SQL`'s `rows` JSON gained `'dedup_key', dedup_key`** in STORY-002 (`c8b303b`, `database.py:1160`). The rows decode to `AuditLog` (`_decode_rows`), which has carried `dedup_key` since STORY-002. This keeps `summary_snapshot().rows` equal to `list_audit_logs()`. No figure reads the column, and `grep -rn dedup_key chat_ui/` finds nothing, so the console renders nothing new. `AuditRow` is the console's row model and has no such field. The report records this as the one reporting-path diff, and explains why it is not a change to reporting.
5. **`AuditQueryEntry`** (`app/models/schemas.py:110-139`) has 14 fields and no `dedup_key`. `tests/test_audit_router.py:75-90` already pins the exact key set of the `/audit` response. The new test also names the missing field explicitly.
6. **Statements on a successful `/query`** with a user token and no `session_id`:
   - `users` token lookup (`identity.resolve`)
   - `SELECT timestamp FROM audit_logs ... LIMIT 1` (`find_duplicate_timestamp`)
   - `INSERT INTO audit_logs` (`insert_audit_log`)

   `authorize`, pattern detection and `redact` do no DB work. At the base `57f2d67`, `find_duplicate_timestamp` was also a single `SELECT ... FROM audit_logs` in one `_session()`, and the success arm made one `log_query` call. So "same as before the epic" is 1 + 1, confirmed with `git show 57f2d67:app/db/database.py`.
7. **The spy idiom patches `app.db.database.get_connection`, not the libSQL client object** (`tests/test_stats_router.py:240-270`). `_session()` resolves `get_connection` from module globals at call time. The story's Technical Notes say to follow that test, so "a spy on the libSQL client's `execute`" is met through that proxy. The report says so.
8. **`tests/test_two_instance_smoke.py` has no skip path.** conftest's `_libsql_endpoint` calls `pytest.exit` when the dev server is unreachable, and the file is unmodified since the base. `test_a_prompt_outside_the_window_is_not_blocked_by_the_other_instance` plants a row with no `dedup_key`. That row could never match now (D6), so the test passes without exercising the 24h window. AC 4 forbids modifying the file. Record this in the report as a follow-up observation, and leave the file alone.
9. **The admin console treats denials as `success=True`.** `_deny` logs `success=True` (`app/services/query_pipeline.py:59-68`), and `completion_figure` (`chat_ui/chat_ui/admin_state.py:760-783`) uses `successful_queries` as its numerator. The seeded denial must therefore count in `successful_queries`.
10. **The suite needs the libSQL dev server.** Mass fixture errors mean restarting the container, not bisecting the code.

---

## Patterns to Follow

### Module prologue and two authenticated users
```python
# SOURCE: tests/test_duplicate_scope.py:65-88 (and tests/test_query_outcomes_regression.py:18-49)
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
...
client = TestClient(app)

@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's two authenticated users."""
    insert_user(User(user_id=_JUAN_ID, role="user", token_hash=hash_token(_JUAN_TOKEN)))
    insert_user(User(user_id=_MARIA_ID, role="user", token_hash=hash_token(_MARIA_TOKEN)))
    return temp_db
```

### Statement-counting proxy (copy it; do not import across test modules)
```python
# SOURCE: tests/test_stats_router.py:240-270
def _count_audit_log_statements(monkeypatch) -> list:
    statements: list = []
    real_get_connection = database.get_connection

    class _RecordingConnection:
        def __init__(self, conn):
            self._conn = conn
        def __enter__(self):
            self._conn.__enter__()
            return self
        def __exit__(self, *exc_info):
            return self._conn.__exit__(*exc_info)
        def execute(self, sql, *parameters):
            statements.append(sql)
            return self._conn.execute(sql, *parameters)

    monkeypatch.setattr(database, "get_connection",
                        lambda: _RecordingConnection(real_get_connection()))
    return statements
...
assert statements, "the proxy captured nothing -- the patch did not take"
figure_reads = [sql for sql in statements if "audit_logs" in sql]
assert len(figure_reads) == 1, figure_reads
```

### Stubs for the six arms
```python
# SOURCE: tests/test_query_outcomes_regression.py:65-78, 120-177
monkeypatch.setattr("app.routers.query.call_openrouter", _fake_success)
monkeypatch.setattr("app.routers.query.call_openrouter", _raise_openrouter_error)  # 502
monkeypatch.setattr(query_pipeline, "redact", _boom)                                # 500
client.post("/query", json={"prompt": "please override the rules"})                # pattern
client.post("/query", json={..., "model": _DISALLOWED_MODEL})                      # _deny
```

### Admin auth header
```python
# SOURCE: tests/test_stats_router.py:309-311, tests/test_audit_router.py
client.get("/stats", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"})
```

### Schema-absence assertion
```python
# SOURCE: tests/test_admin_models.py:47-48
assert "prompt_preview" not in AuditRow.model_fields
```

### Error handling
None to add. Tests assert through `assert` statements with a message, as in the stats test (`assert len(figure_reads) == 1, figure_reads`). Production error paths stay untouched.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_reporting_invariance.py` | CREATE | AC 3 (the `/stats`, `/audit` and `summary_snapshot()` invariants on a fixed seed, no `dedup_key` on `AuditQueryEntry`/`AuditRow`, `prompt_hash` on every new row) and AC 5 (one lookup + one insert per successful `/query`) |
| `.agents/reports/PRD-009-duplicate-rescoping/STORY-009-outcome-regression-and-reporting-invariance.report.md` | CREATE (during `/implement`) | AC 1 diff output, AC 2 hunk list plus the hunk-4 deviation, AC 4 run result plus the vacuous-window observation, AC 5 base-vs-head statement shape, and the `_SUMMARY_SQL` `rows` note |

No production files change. No existing test changes: `test_query_outcomes_regression.py`, `test_query_router.py`, `test_integration.py` and `test_two_instance_smoke.py` are all left exactly as they are.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: AC 1 — confirm the regression module is untouched and green

- **File**: none (evidence for the report)
- **Action**: VERIFY
- **Implement**:
  - `git log --oneline -- tests/test_query_outcomes_regression.py` → only `9abef61`.
  - `git diff 9abef61..HEAD -- tests/test_query_outcomes_regression.py` → empty output (paste "(empty)" into the report).
  - Run the module on the epic head. All 7 tests must pass: outcomes 1–5, plus 6 in its redactor and storage forms.
  - If any test fails, stop. That is an earlier story's regression. Fix it in production code in a separate commit that names the story. Never edit the test.
- **Validate**: `pytest tests/test_query_outcomes_regression.py -v`

### Task 2: AC 2 — list every hunk in the router/integration diffs since the epic base

- **File**: none (evidence for the report)
- **Action**: VERIFY
- **Implement**:
  - `git diff 57f2d67..HEAD -- tests/test_integration.py` → empty.
  - `git diff 57f2d67..HEAD -- tests/test_query_router.py` → the 4 hunks in Fact 2. Copy each into the report with a one-line classification:
    - imports (supports the helper)
    - `_Turn`/`_key` helper (supports the seed and the spy)
    - `_seed_duplicate` seeds `dedup_key` (**deviation**: a seed-helper change rather than a spy signature, required by STORY-007/D6; asserts nothing new)
    - `_spy_duplicate(user_id, key)` (spy signature, Section 6.5)
  - Mechanical check that no assertion moved: `git diff 57f2d67..HEAD -U0 -- tests/test_query_router.py tests/test_integration.py | grep -E '^[-+].*(assert|status_code|json\(\))'` must print nothing.
- **Validate**: the grep above is empty; `pytest tests/test_query_router.py tests/test_integration.py -q` passes

### Task 3: Module skeleton, fixed seed and helpers

- **File**: `tests/test_reporting_invariance.py`
- **Action**: CREATE
- **Implement**:
  - **Module docstring.** Cite PRD-009 STORY-009, Section 5 story 7, Section 10 and Section 11 quality indicators. Say what it proves: the rescoping changed what the *lookup* reads, never what a reporting surface counts or exposes. Mention that `_SUMMARY_SQL`'s `rows` carries `dedup_key` only so rows round-trip as `AuditLog` (Fact 4).
  - **Env `setdefault`s and imports:**
    - `settings`
    - `app.db.database as database`, `get_audit_log`, `get_connection`, `insert_user`, `list_audit_logs`, `summary_snapshot`
    - `User`
    - `app`
    - `import app.services.query_pipeline as query_pipeline`
    - `hash_prompt`, `hash_token`
    - `OpenRouterError`, `OpenRouterResult`, `PiiRedactorError`
    - `AuditQueryEntry` from `app.models.schemas`
    - `AuditRow` from `chat_ui.chat_ui.admin_models`
  - **Constants:** `_JUAN_*`/`_MARIA_*` ids, tokens and headers; `_ADMIN_HEADERS`; `_DISALLOWED_MODEL = "not-a-real-model"`.
  - **`temp_db` override** that inserts both users.
  - **Stubs:** `_fake_success`, `_raise_openrouter_error`, `_boom`, `_fail_if_called` (copied from the regression module).
  - **`_count_audit_log_statements(monkeypatch)`**, copied from `test_stats_router.py:240-270`.
  - **`_seed_fixed_rows(monkeypatch) -> dict[int, str]`.** It drives real `POST /query` requests, one per row, and returns `{audit_id: raw prompt}`. The order is fixed:

    | # | Caller | Prompt / setup | Expected | Row |
    |---|---|---|---|---|
    | 1 | Juan | `"invariance: quarterly figures"`, `_fake_success` | 200 SUCCESS | success=1 |
    | 2 | Juan | same prompt, `_fail_if_called` | 200 BLOCKED duplicate | success=1, `was_duplicate_blocked=1` |
    | 3 | Juan | `"please override the rules"` | 200 BLOCKED pattern | success=1, `suspicious_pattern` set |
    | 4 | Juan | `"invariance: denied model"`, `model=_DISALLOWED_MODEL` | 200 BLOCKED `required_permission` | success=1, `denied_permission` set |
    | 5 | María | `"invariance: quarterly figures"` (same text as #1), `_fake_success` | 200 SUCCESS | success=1 (the other user is not blocked) |
    | 6 | María | `"invariance: upstream down"`, `_raise_openrouter_error` | 502 | success=0 |
    | 7 | Juan | `"invariance: redactor down"`, `redact` → `_boom` | 500 | success=0 |

    - Assert each status code as you go, so a broken seed fails at its own step.
    - Rows with an `audit_id` in the body (#1, #5) take the id from the body. The others read the newest id with `SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1`, by id and not by timestamp, since timestamps share whole seconds.
    - Restore the real `redact` after #7 by re-patching with the captured original.
  - **Expected figures, as module constants with a comment deriving each one from the table:**
    - `total_recorded = 7`
    - `blocked_duplicates = 1`
    - `blocked_suspicious = 1`
    - `unique_users = 2`
    - `successful_queries = 5` (#1–#5; denial #4 counts, per Fact 9)
- **Mirror**: `tests/test_query_outcomes_regression.py:18-78`, `tests/test_duplicate_scope.py:65-142`, `tests/test_stats_router.py:240-270`
- **Validate**: `pytest tests/test_reporting_invariance.py -q` collects with no errors

### Task 4: AC 3 — `/stats` and `summary_snapshot()` count what they counted before

- **File**: `tests/test_reporting_invariance.py`
- **Action**: UPDATE
- **Implement**:
  - **`test_blocked_duplicates_counts_exactly_the_duplicate_blocked_rows`**
    1. `ids = _seed_fixed_rows(monkeypatch)`.
    2. Count independently with raw SQL: `SELECT COUNT(*) FROM audit_logs WHERE was_duplicate_blocked = 1`. That count is `== 1`.
    3. `GET /stats` with `_ADMIN_HEADERS` → 200, and `body["blocked_duplicates"] == 1 == raw count`.
    4. Show the figure is not a proxy for "anything blocked" or "anything duplicate-shaped": María's row #5 has the same `prompt_hash` as #1 and is not blocked, and the pattern (#3) and denial (#4) rows are not counted. Assert the ids of `was_duplicate_blocked` rows `== [id of #2]`.
  - **`test_stats_and_summary_snapshot_report_the_same_figures_on_the_fixed_seed`**
    1. Seed, then `GET /stats` and `summary_snapshot()` (defaults).
    2. `snapshot.errors == {}`.
    3. Each of `total_recorded`, `blocked_duplicates`, `blocked_suspicious`, `unique_users` and `successful_queries` equals its expected constant.
    4. The `/stats` fields agree: `total_queries`, `blocked_duplicates`, `blocked_suspicious`, `unique_users`, and `success_rate == f"{5 / 7 * 100:.1f}%"`.
    5. `set(body) == {"total_queries", "blocked_duplicates", "blocked_suspicious", "unique_users", "success_rate", "top_models", "top_users", "pii_detected_queries", "top_pii_entities"}`. The `StatsResponse` shape is unchanged; `app/models/` has no epic diff.
    6. `snapshot.rows == list_audit_logs(limit=len(snapshot.rows))`, as `test_db.py::test_summary_snapshot_agrees_with_the_individual_reads` checks. If `list_audit_logs`'s signature differs, mirror that test.
  - **`test_console_completion_numerator_still_counts_denials_as_success`**
    - Seed, then assert `summary_snapshot().successful_queries == 5`, and that the denial row (#4) has `success is True` and `denied_permission == f"query:model:{_DISALLOWED_MODEL}"`.
    - Docstring: cite `chat_ui/chat_ui/admin_state.py::completion_figure`, and note that PRD-009 rewrote no row, so the console figure keeps its meaning.
- **Mirror**: `tests/test_stats_router.py:291-320`, `tests/test_db.py:1301-1340`
- **Validate**: `pytest tests/test_reporting_invariance.py -k "blocked_duplicates or summary_snapshot or completion" -q`

### Task 5: AC 3 — `/audit` exposes no `dedup_key`, and `prompt_hash` keeps its meaning

- **File**: `tests/test_reporting_invariance.py`
- **Action**: UPDATE
- **Implement**:
  - **`test_audit_query_entry_has_no_dedup_key_d5`**
    1. `"dedup_key" not in AuditQueryEntry.model_fields`.
    2. `"dedup_key" not in AuditRow.model_fields` (the console's row model).
    3. Seed, then `GET /audit` with `_ADMIN_HEADERS` → 200, `body["total"] == 7`, and for every entry `"dedup_key" not in entry`.
    4. Show the column is populated underneath, so the absence is a choice (D5) and not an empty value: `get_audit_log(id).dedup_key is not None` for every seeded id.
  - **`test_every_new_row_prompt_hash_is_the_raw_prompt_hash`**
    - For each `audit_id, prompt` in the seed, `get_audit_log(audit_id).prompt_hash == hash_prompt(prompt)`, and the `/audit` entry with that `audit_id` carries the same `prompt_hash`.
    - Also `rows[#1].prompt_hash == rows[#5].prompt_hash` while their `dedup_key`s differ. `prompt_hash` stayed global evidence; only the key is per caller.
- **Mirror**: `tests/test_admin_models.py:47-48`, `tests/test_audit_router.py:40-90`
- **Validate**: `pytest tests/test_reporting_invariance.py -k "audit_query_entry or prompt_hash" -q`

### Task 6: AC 5 — one lookup and one insert per successful `/query`

- **File**: `tests/test_reporting_invariance.py`
- **Action**: UPDATE
- **Implement**: **`test_successful_query_issues_one_duplicate_lookup_and_one_audit_insert`**
  1. `monkeypatch` `call_openrouter` → `_fake_success`. Warm the analyzer first with `query_pipeline.redact("warm up")`, as in `test_query_router.py:287`. That call does no DB work, but it keeps the timing clean.
  2. `statements = _count_audit_log_statements(monkeypatch)`, then Juan posts `"invariance: counted round trips"` → 200 SUCCESS.
  3. `assert statements, "the proxy captured nothing -- the patch did not take"`.
  4. `audit = [s for s in statements if "audit_logs" in s]`, then `len(audit) == 2, audit`.
  5. `lookups = [s for s in audit if s.lstrip().upper().startswith("SELECT")]` and `inserts = [s for s in audit if s.lstrip().upper().startswith("INSERT INTO AUDIT_LOGS")]`. Assert `len(lookups) == 1`, `len(inserts) == 1`, and `"dedup_key = ?" in lookups[0]`, so the one lookup is the rescoped one.
  - Docstring:
    - Only `audit_logs` statements are counted. The `users` token lookup comes from `require_identity` and was always there (same reasoning as the stats test).
    - At the base `57f2d67`, the success path was also one `find_duplicate_timestamp` SELECT plus one `insert_audit_log` INSERT. `dedup_key()` is computed in-process, so PRD Section 11's "no added round trip" holds.
    - The instrument is the `get_connection` proxy, the only hook the libSQL connection allows (Fact 7).
- **Mirror**: `tests/test_stats_router.py:291-320`
- **Validate**: `pytest tests/test_reporting_invariance.py -k one_duplicate_lookup -v`

### Task 7: AC 4 — two-instance smoke, unmodified

- **File**: none (evidence for the report)
- **Action**: VERIFY
- **Implement**:
  - `git diff 57f2d67..HEAD -- tests/test_two_instance_smoke.py` → empty.
  - Run the module. It has no skip path (Fact 8), so every test must pass, including `test_concurrent_queries_from_both_instances_lose_no_rows`, which asserts `prompt_hash == hash_prompt(prompt_preview)` at line 793.
  - Record in the report: `test_a_prompt_outside_the_window_is_not_blocked_by_the_other_instance` plants a NULL-key row and now passes whatever the window is. It is left unmodified per AC 4, and proposed as a follow-up outside this epic's "unmodified" constraint.
- **Validate**: `pytest tests/test_two_instance_smoke.py -v`

### Task 8: Full suite, change audit and report

- **File**: `.agents/reports/PRD-009-duplicate-rescoping/STORY-009-outcome-regression-and-reporting-invariance.report.md`
- **Action**: CREATE
- **Implement**:
  - Run the full suite. On mass fixture errors, restart the `harness-libsql-dev` container and re-run; don't bisect.
  - `git status --short` shows only `tests/test_reporting_invariance.py` and the report as new (plus the pre-existing untracked `pre-prds/`, which is not staged). `git diff --stat -- app/ chat_ui/` is empty.
  - Report sections:
    - AC 1 output (Task 1)
    - AC 2 hunk list and deviation (Task 2)
    - AC 3 test names
    - AC 4 run result and observation (Task 7)
    - AC 5 statement shape, base vs head (Task 6, Fact 6)
    - the `_SUMMARY_SQL` `rows` note (Fact 4)
    - "Production changes: none", or the separate commit with the regressing story named
    - full suite count
- **Validate**:
  ```bash
  pytest -q
  git status --short
  git diff --stat -- app/ chat_ui/
  ```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| **AC 2's wording ("only spy wrapper signatures") is not literally true.** `_seed_duplicate` changed too. | Report it as a deviation with the reason and the grep proving no assertion changed. Do not revert: the seed must carry the key the lookup matches on (D6). |
| **The `_SUMMARY_SQL` `rows` column list changed in STORY-002**, which reads like a reporting change. | Assert that no figure changed and `AuditRow` has no `dedup_key`. Show that `snapshot.rows == list_audit_logs(...)`. Explain the change in the report. |
| **Statement filter too loose or too strict** (the proxy also sees `users` reads, and `PRAGMA`/`init_db` statements run before the patch). | Patch after the fixture's `init_db()` and count only `audit_logs` statements, split by `SELECT`/`INSERT` prefix. The `assert statements` guard proves the patch took. |
| **Denial counted in `successful_queries` looks like a bug.** | It is pre-existing and deliberate (Fact 9). The test pins it with a docstring citation, and nothing changes it. |
| **Seed step fails midway and the figure asserts give confusing messages.** | Assert the status code at every seed step. |
| **Smoke test's window test is vacuous.** | Observation in the report only. AC 4 forbids modifying the file. |
| **libSQL dev server degrades across the full suite + smoke.** | Restart the container on mass fixture errors (memory note). |
| **A real regression surfaces.** | Fix it in production in a separate commit on the epic branch, named in the report. Never weaken an assertion. |

---

## End-to-End Tests

- [ ] `pytest tests/test_query_outcomes_regression.py -v`: 7 pass, file unchanged since `9abef61`
- [ ] `pytest tests/test_query_router.py tests/test_integration.py -q`: pass; assertion-grep over the epic diff is empty
- [ ] Fixed 7-row seed through `POST /query` (2 users, success ×2, duplicate block, pattern block, denial, 502, 500) → `GET /stats`: `blocked_duplicates == 1`, `total_queries == 7`, `unique_users == 2`, `success_rate == "71.4%"`
- [ ] Same seed → `summary_snapshot()` figures equal `/stats`, `errors == {}`
- [ ] Same seed → `GET /audit`: 7 entries, none has `dedup_key`; `prompt_hash == hash_prompt(prompt)` for each
- [ ] One successful `POST /query` → exactly one `SELECT ... dedup_key = ?` and one `INSERT INTO audit_logs`
- [ ] `pytest tests/test_two_instance_smoke.py -v`: pass, file unchanged
- [ ] Full suite green

---

## Validation

```bash
docker ps --filter name=harness-libsql-dev      # dev server up (conftest exits otherwise)
git diff 9abef61..HEAD -- tests/test_query_outcomes_regression.py      # empty
git diff 57f2d67..HEAD -- tests/test_query_router.py tests/test_integration.py tests/test_two_instance_smoke.py
pytest tests/test_query_outcomes_regression.py tests/test_reporting_invariance.py tests/test_two_instance_smoke.py -v
pytest -q
git diff --stat -- app/ chat_ui/                # empty
```

---

## Acceptance Criteria

(Copied from story `STORY-009`)

- [ ] Given `tests/test_query_outcomes_regression.py`, when `git diff <STORY-001 commit>..HEAD -- tests/test_query_outcomes_regression.py` is run, then it is empty, and the module passes on the epic branch head.
- [ ] Given the same diff over `tests/test_query_router.py` and `tests/test_integration.py` since the epic's base, when it is reviewed, then the only changes are spy wrapper signatures (PRD Section 6.5). No status-code, body or row-count assertion changed. The report lists each hunk.
- [ ] Given a fixed set of seeded rows (successes, both blocks, denials, failures, two users), when `GET /stats`, `GET /audit` and `summary_snapshot()` are read, then a new invariance test asserts `blocked_duplicates` counts exactly the `was_duplicate_blocked = 1` rows. `AuditQueryEntry` has no `dedup_key` field, and every new row's `prompt_hash == hash_prompt(prompt)`.
- [ ] Given `tests/test_two_instance_smoke.py`, when it runs (or is skipped under its own documented conditions), then it passes **unmodified**, including `prompt_hash == hash_prompt(prompt_preview)`.
- [ ] Given a spy on the libSQL client's `execute` during one successful `/query`, when the statements are counted, then there is exactly one duplicate-lookup statement and one audit insert, the same as before the epic (no added round trip, per the PRD Section 11 quality indicators). The full suite is green.
- [ ] All tasks completed
- [ ] Full pytest suite passes
- [ ] No production code changed (or a regression fix in a separate, named commit)
- [ ] Follows existing patterns
