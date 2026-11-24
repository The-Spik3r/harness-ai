---
story: STORY-019
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-019-mcp-corpus-and-latency.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: 3903631
status: COMPLETE
completed: 2026-11-24
---

# Implementation Report - STORY-019: MCP decision corpus and the gateway latency measurement

**Plan**: `.agents/plans/PRD-023-mcp-and-skills/completed/STORY-019-mcp-corpus-and-latency.plan.md`
**Epic Branch**: `epic/PRD-023-mcp-and-skills`
**Commit**: `3903631`

## Summary

33 gateway calls in `tests/corpora/mcp/calls/*.yaml` (brief 5, outcome 8, visibility 8, alias 5, correlation 7), a shared loader and fixed setup (`tests/mcp_corpus.py`, also for STORY-020), the runners (`tests/test_mcp_corpus.py`) and the latency script (`scripts/measure_mcp_latency.py`, with `tests/test_measure_mcp_latency.py`). No `app/` change, no PRD-016 file change. The format is documented in `tests/corpora/mcp/SOURCES.md` ("Decision corpus format").

## Latency (AC3), `--runs 200`, embedded libSQL file, stub subprocess, Windows 11, Python 3.12.10

Overhead = request time minus time in `mcp_upstream.call_tool` / `list_tools`. p95 is nearest-rank. M0-M9 goes through `TestClient` (adds about 1-2 ms of its own); M3-M9 is `mcp_gateway.call` alone.

| arm | figure | n | min ms | p50 ms | p95 ms |
|---|---|---|---|---|---|
| denied (DROP TABLE, not forwarded) | M0-M9 | 200 | 11.43 | 12.23 | 13.63 |
| denied | M3-M9 | 200 | 10.67 | 11.50 | 12.85 |
| allowed (SELECT, forwarded) | M0-M9 | 200 | 16.92 | 17.97 | 18.93 |
| allowed | M3-M9 | 200 | 15.93 | 17.18 | 18.88 |

- Target (Section 11): p95 <= 25 ms. Worst M0-M9 arm 18.93 ms: **MET** on this machine. One local run on a laptop; CI hardware may differ, and the script asserts no latency.
- Database round trips per call (every `get_connection()` open): denied **2** (`admit_usage`, `insert_action_decisions`), allowed **3** (`admit_usage`, `insert_mcp_decision_linked`, `update_action_outcome`). Limit 3: **MET**. Statements: denied 2, allowed 3 (one each).
- The allowed arm takes the claim path (alias prefix `harness_` configured), the one the three-trip budget is about.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Loader, vocabularies, fixed setup (`configure`), `normalise_flags` | `tests/mcp_corpus.py` | done |
| 2 | 33 corpus files; format section | `tests/corpora/mcp/calls/*.yaml`, `tests/corpora/mcp/SOURCES.md` | done |
| 3 | Loader tests, non-DB runner, alias runner, `db` twin, correlation runner | `tests/test_mcp_corpus.py` | done |
| 4 | Latency script | `scripts/measure_mcp_latency.py` | done |
| 5 | Script tests | `tests/test_measure_mcp_latency.py` | done |
| 6 | `--runs 200` run, numbers above | n/a | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | OK |
| Targeted tests, `-m "not db"` | 680 passed, 1 skipped, 30 deselected (`test_mcp_corpus.py`, `test_measure_mcp_latency.py`, `test_action_corpus.py`, `test_stub_mcp_server.py`, `test_untouched_app.py`) |
| `db` tests (twin runner 21, correlation 7) | Docker is down. Run locally against an **embedded libSQL file** by pointing `HARNESS_TEST_LIBSQL_URL` at a temp file (with `DATABASE_URL=http://127.0.0.1:8080` for the import-time check): `-m db tests/test_mcp_corpus.py` gave 28 passed. CI runs them on the real server. |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

| File | Action |
|------|--------|
| `tests/corpora/mcp/calls/*.yaml` (33) | CREATE |
| `tests/corpora/mcp/SOURCES.md` | UPDATE (+ "Decision corpus format") |
| `tests/mcp_corpus.py` | CREATE |
| `tests/test_mcp_corpus.py` | CREATE |
| `scripts/measure_mcp_latency.py` | CREATE |
| `tests/test_measure_mcp_latency.py` | CREATE |

## Deviations from Plan

- The skill of the matrix lists 8 tools, not 6 (`huge` and `inject` added: the outcome cases need them).
- `outcome-tool-error` uses `fault: tool_error` (the plan allowed the fallback): a bad argument makes the stub answer `isError` before the tool body runs, so the stub counter does not move.
- `rbac: enabled|disabled` instead of `on|off` (YAML reads `off` as false). `rbac: disabled` keeps the built-in matrix, as PRD Section 11 words it; with a matrix that grants the skill, `held_skills` still shows it with RBAC off (it reads the matrix, not `authorize`). The first draft of the file used the custom matrix and failed; that was the corpus configuration, not the gateway.
- `prior.decision` (seed override) added so the "denied alias row" case really exercises the `decision IN ('allow','flag')` condition: the same user and arguments cannot naturally yield a denied `/v1` row and an allowed gateway call.
- The `db` twin groups the roles of one file in one test (21 resets, not about 45).
- `test_a_denied_call_never_reaches_the_stub` runs the brief's denied calls in one world; the per-call counter and "row before forward" checks are inside every runner.
- No disagreement with PRD Section 11 and no `app/` change.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_mcp_corpus.py` | corpus size and coverage; four MVP calls verbatim; naming and `e2e` invariants; bad-file table (25 documents naming file and node); valid template; duplicate key; `normalise_flags` (both shapes); gateway runner (per file and role); denied-never-reaches-stub; alias runner (`v1`); `db` twin (21); correlation (7) |
| `tests/test_measure_mcp_latency.py` | import has no side effect; nearest-rank p95; MET/MISSED verdicts; round-trip verdict; ASCII report; zero runs refused; subprocess short run (both arms, units, stub port closed) |

## Acceptance Criteria

- [x] AC1: >= 30 calls, declared decision and outcome per role: `test_call_decides_as_declared`, `test_call_decides_as_declared_db`, `test_alias_case_decides_as_declared`, `test_correlation_case_db`, `test_the_corpus_holds_at_least_30_calls_covering_every_class` (the `db` ones ran on embedded libSQL locally, on the server in CI)
- [x] AC2: denied calls leave the stub counter unchanged, forwarded calls have their row first: assertions in `_run_role`, `test_a_denied_call_never_reaches_the_stub`
- [x] AC3: p95 recorded (above, 18.93 ms vs 25 ms target) and at most three round trips (2 and 3): `test_a_short_run_reports_both_arms_and_at_most_three_units`
