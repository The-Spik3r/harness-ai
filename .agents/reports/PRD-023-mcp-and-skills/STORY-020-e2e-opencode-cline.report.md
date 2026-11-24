---
story: STORY-020
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-020-e2e-opencode-cline.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: pending
status: COMPLETE
completed: 2026-11-24
---

# Implementation Report - STORY-020: E2E OpenCode and Cline through `/mcp`

**Commit**: `pending`

## Summary

`tests/e2e/test_mcp_clients.py` (opt-in, `pytestmark = pytest.mark.e2e`) drives the real OpenCode 2.3.2 and Cline CLI 3.0.74 against a live `uvicorn app.main:app` (`MCP_ENABLED=true`) and the real MCP stub. The model is the scripted fake provider reached directly by the clients; the harness is only their MCP server (static `Authorization` header). Per client: the tools offered to the model, one allowed `stub__query` SELECT and one denied DROP TABLE (corpus cases `outcome-select-ok` and `brief-drop-table`, role `dev`), then the `action_decisions` rows and the stub's call counter. No Docker needed: an embedded libSQL file reached by every child through a test-only launcher (`_embedded_db.py`); `HARNESS_E2E_LIBSQL_URL` still works. No `app/` change.

## Local E2E run (exact)

`PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider --run-e2e tests/e2e/test_mcp_clients.py` (with `HARNESS_E2E_OPENCODE` set): **6 passed in 37.5 s**. `-k opencode`: 3 passed; `-k cline`: 3 passed.

Observed (from `mcp-e2e-run.json`, kept in pytest's tmp dir, not committed):
- Both clients connected with the static Authorization header (R2 does not apply). Cline needed no `autoApprove`.
- OpenCode offered 19 tools including `harness_stub__create_pull_request, __huge, __inject, __push_files, __query, __slow`; Cline offered 10 including `harness__stub__*` (same six). `create_branch`, `poisoned`, `nope` never offered.
- Allow rows (both clients): `surface=mcp, mcp_server=stub, tool_name=query` (the row keeps the bare name), `operation_kind=sql, decision=allow, rule=sql.read, outcome=ok`, `skills=["open-pull-request@1.0.0"]`; the stub counted `query` +1.
- Deny rows: same surface/server/tool, `decision=deny, rule=sql.ddl, outcome=NULL`; the stub counted no call. The fake provider's last rule was the after-call one (the client sent the denial back and the script ended the run).
- Fake-provider rule labels: allow runs `['2','0']`, drop runs `['1','0']`.
- After the run `tasklist` showed no opencode, cline, uvicorn or stub process.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Embedded DB probe: real uvicorn (health 200) plus a second launcher process reading the file | probe | done, passed |
| 2 | Launcher | `tests/e2e/_embedded_db.py` | done |
| 3 | `start_harness(..., launcher=None)` | `tests/e2e/_live.py` | done |
| 4 | Pure helpers and scripts | `tests/e2e/_mcp.py`, `scripts/opencode_mcp.json`, `scripts/cline_mcp.json` | done |
| 5 | The E2E | `tests/e2e/test_mcp_clients.py` | done |
| 6 | CI-side unit test | `tests/test_e2e_mcp_clients_script.py` | done |
| - | Script docs | `tests/e2e/scripts/README.md` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted run (`-m "not db"`: script test, test_e2e_live, test_e2e_marker, opencode/cline script tests, test_mcp_corpus, new E2E module) | 128 passed, 6 skipped (the new E2E without `--run-e2e`), 28 deselected |
| Local E2E with `--run-e2e` | 6 passed |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- `policy_yaml()` is the corpus policy plus `nope: allow` and `poisoned: allow` (opaque), not verbatim: a real `mcp_config.load()` cross-validates every skill tool against the policy, which `mcp_corpus.configure()` skips by assigning the config. Both tools are never offered or called.
- The row's `tool_name` is the bare `query` (server in `mcp_server`), not the corpus's `stub__query`; the test derives it from the corpus name.
- The stub scripts' `arguments` placeholders are inside JSON strings (`"@ARGS_ALLOW@"`), so both committed files stay valid JSON; each `after_call` rule carries `role: tool` and `regex: ""` (the stub requires a matcher).
- The Docker (`HARNESS_E2E_LIBSQL_URL`) path is supported but was not run (Docker is down locally).

## Acceptance Criteria

- [x] OpenCode lists the skill's tools, one allowed and one denied call, matching rows: `test_opencode_lists_the_skills_tools`, `_allowed_call`, `_denied_call` (6/6 local run)
- [x] Cline, same: `test_cline_*`
- [x] Skipped without `--run-e2e` (6 skipped), mechanism pinned by `tests/test_e2e_marker.py`
