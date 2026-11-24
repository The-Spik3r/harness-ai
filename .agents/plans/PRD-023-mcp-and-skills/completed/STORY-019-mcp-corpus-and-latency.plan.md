---
story: STORY-019
prd: PRD-023
slug: mcp-corpus-and-latency
title: "`tests/corpora/mcp/` decision corpus and the gateway latency measurement"
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-24
---

# Plan: MCP decision corpus and gateway latency measurement

## Summary

Add a YAML corpus of >= 30 gateway calls (`tests/corpora/mcp/calls/*.yaml`, one call per file, PRD-016 shape plus `server:`), a loader/setup module that STORY-020 also imports (`tests/mcp_corpus.py`), a runner test (`tests/test_mcp_corpus.py`) that drives each call through the real `/mcp` router and the stub, and a latency script (`scripts/measure_mcp_latency.py` + `tests/test_measure_mcp_latency.py`) that runs on an embedded libSQL file. No `app/` change, no PRD-016 file or loader change.

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-019-mcp-corpus-and-latency.md`
- PRD sections: 6.3 (M0-M9), 6.8, 6.9, 11, F12
- Skills: `.agents/skills/` holds only `frontend-design` (UI); none applies.
- The stub launcher is `tests/mcp_stub.py` (not under `tests/corpora/mcp/`); the stub itself is `scripts/stub_mcp_server.py`.

## Design Decisions

- **One call per file, roles inside it** (as `tests/corpora/actions/synthetic/*.yaml`). The loader imports `CorpusError`, `_one_of`, `_tool_call` from `tests/test_action_corpus.py:188,224,230` (precedent: line 125 imports `_sources_rows` from another test module). Do NOT reuse `_load_case`, `_ROLES`, `_corpus` (hard-wired to `actions/` and roles user/dba/admin); the new vocabularies live in `tests/mcp_corpus.py`. `test_action_corpus.py` and `tests/corpora/actions/` get no diff.
- **Format** (documented in `tests/corpora/mcp/SOURCES.md`, new section "Decision corpus format", about one screen):
  - required: `tool_call: {name, arguments}` (both strings; `arguments` is JSON-object text; `name` is the northbound name `stub__query`, or the raw `/v1` name for `via: v1`), `server` (`stub`, or `null` for unresolvable names), `category` (`brief|outcome|visibility|alias|correlation`), `expect: {role: decision}` (roles `user|dev|dba`), `outcome: {role: null|ok|tool_error|upstream_error|timeout|result_too_large|result_blocked}` (same roles as `expect`), `rule` (string, or role-to-string map), `note`.
  - optional: `via: mcp|v1` (default mcp; v1 = decision at step 7c only, no forward), `client` (PRD-016 vocabulary, E2E hint), `granted_by: {role: perm}`, `flags: [..]` (expected `result_flags`), `patterns: flag|block` (default flag), `rbac: on|off`, `fault: tool_error|upstream_error|image_result` (in-process fake of `mcp_upstream.call_tool`, as `spy.fake_call_tool`, `tests/test_mcp_tools_call.py:142,190`), `prior: {role, name, arguments, age_seconds, audit}` + `window_seconds` + `linked: bool` (correlation), `e2e: false` (not replayable by real clients: faults, timeouts, alias, correlation).
  - Reply shape is derived, not declared: rule `tool.not_in_skill` => JSON-RPC `-32602` + `UNKNOWN_TOOL_MESSAGE`; any other deny => `isError` with `DENIAL_NOTE_TEMPLATE`; timeout, upstream_error, too_large, blocked => the harness error text.
  - The fixed setup (server `stub`, skill `open-pull-request` with its 6 tools, policy `mcp_tools` + `mcp_opaque_tools`, roles) is constants and a `configure()` in `tests/mcp_corpus.py`, written afresh from `tests/test_mcp_tools_call.py:48-77` (those are private to a test module; do not edit it). Roles: `user` {mcp:connect}; `dev` {skill:open-pull-request, mcp:connect}; `dba` = dev + `authz.PERMISSION_ACTION_SQL_DDL`. Server timeout 2 s, `max_result_bytes` 2048 (so `huge size=5000` is too large).
- **Result-flags shapes**: one `normalise_flags()` accepts BOTH `{"list": "injection", "pattern_id": N}` (`mcp_gateway._inspect_result`, `app/services/mcp_gateway.py:281-331`) and `{"uninspected": N}` (`_screen_result`, :334-381), plus plain strings (the `record_outcome` signature, `app/services/action_audit.py:407`). It works on the recorded list (non-DB) and on `json.loads(row["result_flags"])` (DB). A file with `flags: []` asserts empty.
- **Evidence before effect, per call**: the runner wraps `mcp_upstream.call_tool` (wrapper style of `tests/test_mcp_tools_call.py:187-192`). On entry it asserts the decision row for this JSON-RPC id already exists (backend-specific, below). After the request it asserts the stub counter delta (`StubHandle.calls(tool)`, `tests/mcp_stub.py:77`) is 1 if forwarded (allow/flag, not a fault) else 0. A denied call also asserts `call_tool` was never entered.
- **Two backends, one corpus**: (a) non-DB (`-m "not db"`, runs locally): the `spy` of `tests/test_mcp_tools_call.py:147-208` (recorders for `usage_limits.admit`, `action_audit.record`, `record_outcome`); "row exists" = `record` came before `call_tool` in `order` and `tool_call_id` is `mcp:<id>`. (b) `db`-marked (CI only): `temp_db` + `real_rows` (`:564-574`); "row exists" = `SELECT ... WHERE tool_call_id = ?` inside the wrapper; outcome, flags and `granted_by` read from the row. Correlation cases run only in (b).
- **Alias cases** (`via: v1`, non-DB, so they run locally): `McpConfig(v1_prefixes=("harness_", "harness__"))` (`app/services/mcp_config.py:155`), `settings.MCP_ENABLED=True`, `query_pipeline._alias_input(identity)` (`app/services/query_pipeline.py:158`), then `action_policy.evaluate_all([ToolCall(..)], identity, policy, aliases=)` (`action_policy.py:526`). Assert decision and rule, `d.mcp_server`, and, via `action_audit.decision_rows` (`:233`, pure), `surface == 'v1'`, `mcp_server`, `arguments_canonical_hash == arguments_canonical_hash(args)`.
- **Correlation cases** (db): seed the alias row as `tests/test_mcp_correlation.py:49-58` does (`decision_rows` + `dataclasses.replace(row, timestamp=..)` + `insert_action_decisions`), with `prior.audit: true` also inserting an `audit_logs` row (`:94-99`). Monkeypatch `mcp_gateway._link_clock` (`mcp_gateway.py:385`) to a fixed time and `settings.MCP_LINK_WINDOW_SECONDS` (default 300, `app/config.py:464`). Then POST the gateway call and assert the new row's `linked_decision_id` and `audit_id`. Lesson: read a row back only after the insert that creates it.
- **Latency on a local file (checked, it works)**: `Settings` rejects a file URL at import (`app/config.py:531-555`) but does not validate on assignment. The script sets `os.environ["DATABASE_URL"] = "http://127.0.0.1:8080"` (a placeholder, never connected) before the `app.` imports, then assigns `settings.DATABASE_URL = "<tmp>/mcp-latency.db"`. `database._shared_client` (`app/db/database.py:197-203`) then calls `libsql.connect(path, auth_token=...)`, i.e. embedded libSQL. Probed today: `init_db()` and a SELECT on `action_decisions` succeed on such a file. Script-only override, never in `app/`; say so in its docstring. The suite's `conftest` refuses storage in non-`db` tests, so the script is tested through a **subprocess** (as `tests/test_measure_v1_latency.py:130-150`), which runs locally without Docker.
- **Counting DB round trips**: wrap `database.get_connection` with the `Recording` proxy of `scripts/measure_usage_latency.py:152-193` (`_statements_of`; copy it, as that script copies from the history one). Each `get_connection()` open is one unit of work (`_session`). Also wrap `database._unit_of_work` (`database.py:1174`, as `tests/test_mcp_correlation.py:149-161`) to see unit names: expected `admit_usage`, `insert_mcp_decision_linked`, `update_action_outcome`. Report per call: units (gate <= 3) and statements (informational). Time is not asserted (pattern: `scripts/measure_v1_latency.py` docstring); the unit count is deterministic, so the subprocess test asserts it.
- **Upstream excluded**: wrap `mcp_upstream.call_tool` and accumulate its elapsed per call; overhead = request time - upstream time. Report two figures: M0-M9 through `TestClient` on a bare `FastAPI` + `mcp_router.router` with `app.middleware.auth.resolve` patched to the bench identity (`tests/test_mcp_tools_call.py:111-122`), and `mcp_gateway.call` alone (M3-M9). p95 is nearest-rank (`Samples.summary`, `measure_usage_latency.py:196-220`). Two arms: denied (`DROP TABLE`, no forward) and allowed (`SELECT`, forwarded, upstream subtracted). Target <= 25 ms printed MET or MISSED. Identity `Identity(user_id, "dev", requests_per_minute=10**9, token_budget_daily=None)` (`measure_usage_latency.py:238`) with `USAGE_LIMITS_ENABLED=True`, so `admit` does its real write.
- **Stub for the script**: `tests.mcp_stub.start_stub` (`tests/mcp_stub.py:103`) and `StubHandle.stop()`. No new stub. One discarded warm-up call per arm.

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Corpus file and loader | `tests/corpora/actions/synthetic/brief-drop-table-users.yaml`, `tests/test_action_corpus.py:246-308` | key checks; `CorpusError(name, node, problem)`; loaded at import so a bad file fails collection |
| Bad-file tests | `tests/test_action_corpus.py:361-436` | `_BAD_DOCUMENTS` table naming file and node |
| Gateway harness | `tests/test_mcp_tools_call.py:90-127,147-232` | `_fresh`, `client`, `spy`, `_post` |
| DB rows | `tests/test_mcp_tools_call.py:564-598` | `real_rows`, `_rows()` |
| Correlation seeding | `tests/test_mcp_correlation.py:49-84` | `_v1_row`, `_gateway_row` |
| Script bootstrap | `scripts/measure_usage_latency.py:75-116` | env before `app.` imports, `Recording` |
| Script tests | `tests/test_measure_v1_latency.py:1-40,130-150` | import with env restored; subprocess; ASCII report |
| Flag facts | `tests/test_mcp_results.py:206-262` | default `inject` = flag `pattern_id 0`; block policy gives `result_blocked` with id 1 |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/corpora/mcp/calls/*.yaml` | CREATE (>= 33) | the corpus |
| `tests/corpora/mcp/SOURCES.md` | UPDATE | append "Decision corpus format" |
| `tests/mcp_corpus.py` | CREATE | `load_corpus()`, `load_case`, vocabularies, `configure()`, `normalise_flags` (shared with STORY-020) |
| `tests/test_mcp_corpus.py` | CREATE | loader tests, non-DB runner, alias runner, `db` runner and correlation |
| `scripts/measure_mcp_latency.py` | CREATE | the measurement |
| `tests/test_measure_mcp_latency.py` | CREATE | script tests |

## Corpus inventory (one file each)

The implementer runs each file and compares with PRD 11. A disagreement is a finding for the report, not a silent `expect` edit.

- brief (5): `hidden-tool` (create_branch, dev: not_in_skill); `drop-table` (dev deny `sql.ddl`; dba allow, `granted_by action:sql:ddl`, ok; user not_in_skill); `push-files-workflow` (deny `fs.write_protected`, outcome null); `push-files-clean` (allow, ok); `create-pull-request-opaque` (flag `tool.opaque`, ok).
- outcome (8): `select-ok`; `tool-error` (try real `create_branch {"branch": 5}` first, else `fault`); `upstream-error` (fault); `timeout` (`slow` 20 s, stub counter 1); `too-large`; `blocked` (`patterns: block`); `inject-flagged` (flags `{list, pattern_id}`); `image-uninspected` (fault `image_result`, flags `{uninspected: 1}`).
- visibility (8): `user-holds-no-skill`, `poisoned-withheld`, `skill-lists-absent-upstream-tool` (`stub__nope`), `unknown-server`, `no-separator`, `rbac-off`, `dev-sees-query`, `dba-sees-push-files`.
- alias (5): `harness_stub__query` with DROP (deny `sql.ddl`, was `tool.unknown`), with SELECT (allow), Cline `harness__stub__query`, alias to a hidden tool, a hashed or sanitised Cline name (`tool.unknown`).
- correlation (7): inside window (with `audit: true`), exactly 300 s, 301 s, different arguments, denied alias row, other user, no prior (audit_id NULL).

## Tasks

1. **`tests/mcp_corpus.py`**: setup constants and `configure(monkeypatch, url, ...)`, vocabularies, `load_case(path)`, `load_corpus()` (sorted `calls/*.yaml`; a missing directory raises), `normalise_flags`. Validate: `.venv/Scripts/python -c "import tests.mcp_corpus"`.
2. **Corpus files and the SOURCES.md section.** Start with the 5 brief files, run them, then the rest. Every denied role has `outcome: null`.
3. **`tests/test_mcp_corpus.py`**:
   - loader tests: every file loads; >= 30 files; every category, decision and outcome value is present; the four MVP calls are present verbatim; a bad-file table naming file and node; the valid template loads; every `granted_by` role expects allow;
   - non-DB runner parametrised by (file, role) for `via: mcp`, with the per-call evidence and counter assertions;
   - alias runner (non-DB);
   - `@pytest.mark.db` twin of the runner using `real_rows`, plus the correlation runner.
   One module-scoped stub (`start_stub` via `tmp_path_factory`, `reset()` per test, stopped in `finally`) rather than one per case. Timeout case: deadline loop on the stub counter (`test_mcp_tools_call.py:454-459`). No `asyncio.all_tasks()` snapshot assertions.
4. **`scripts/measure_mcp_latency.py`**: `--runs` (default 50), `--target-ms` (25). It takes no database URL (always a temp file, removed on exit). ASCII report with stable lines: `units per call`, `statements per call`, `p95 ms (M0-M9, upstream excluded)`, `p95 ms (M3-M9, upstream excluded)`, verdict `MET|MISSED`.
5. **`tests/test_measure_mcp_latency.py`**: importing has no side effect (fresh interpreter: no stub, `database._client is None`); p95 nearest-rank; a miss prints as MISSED; report is ASCII; a subprocess short run (`--runs 3`) prints both arms with units == 3 for the allowed arm and <= 3 for the denied; the stub port is closed afterwards.
6. **Run the script once with `--runs 200`** and put the numbers in the story report, honest if the target is missed (story Technical Notes).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider -m "not db" tests/test_mcp_corpus.py tests/test_measure_mcp_latency.py tests/test_action_corpus.py tests/test_stub_mcp_server.py tests/test_untouched_app.py
PYTHONUTF8=1 .venv/Scripts/python scripts/measure_mcp_latency.py --runs 200
```

`db` tests (twin runner, correlation) run in CI only (Docker is down). `tests/test_action_corpus.py` is in the run to show PRD-016 is unchanged.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 >= 30 calls, declared decision and outcome per role | 1-3 | `test_mcp_corpus.py::test_the_corpus_holds_at_least_30_calls_covering_every_class`, `::test_call_decides_as_declared` (non-DB), `::test_call_decides_as_declared_db`, `::test_correlation_case_db`, `::test_alias_case_decides_as_declared` |
| AC2 denied: stub counter unchanged; forwarded: row first | 3 | assertions inside the runners (wrapper at `call_tool` entry, counter delta) and `::test_a_denied_call_never_reaches_the_stub` |
| AC3 p95 recorded (<= 25 ms target), <= 3 round trips | 4-6 | `test_measure_mcp_latency.py::test_a_short_run_reports_both_arms_and_at_most_three_units`; numbers in the report |

## Risks and open points

- `tool_error` and `upstream_error` have no natural stub trigger (the stub has no failing tool, `scripts/stub_mcp_server.py:158-200`). `fault:` is in-process only (hence `e2e: false`); STORY-020 gets the other calls.
- Roles `dev` and `dba` exist only in the corpus matrix (monkeypatched `authz.ROLE_PERMISSIONS`); STORY-020 must create equivalent roles.
- TestClient adds about 1-2 ms to "M0-M9"; the report says so and also gives M3-M9.
- Per-(file, role) `db` tests reset the DB each time (about 45 resets in CI); group the roles of one file in one test if CI is slow.
- Exploration was done with Grep/Read (no Explore agents).
