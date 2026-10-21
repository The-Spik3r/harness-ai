---
story: STORY-008
prd: PRD-014
plan: .agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-008-d5-follow-up.plan.md
epic_branch: epic/PRD-014-test-suite-db-isolation
commit: da96827
status: COMPLETE
completed: 2026-10-21
---

# Implementation Report — STORY-008: Act on the D5 result

**Plan**: `.agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-008-d5-follow-up.plan.md`
**Epic Branch**: `epic/PRD-014-test-suite-db-isolation`
**Commit**: `da96827`

## Summary

PRD Appendix "D5 result" reads **confirmed, on thin evidence** (STORY-006: 0 stall events in 143,461 in-network driver calls, 2 in 143,604 host calls). So this story took the confirmed branch of PRD Section 13 and nothing else. It adds `scripts/test-db-in-network.sh`, which:

- checks that `harness-libsql-dev` is running;
- creates `harness-test-net` and connects the server to it, both idempotently and left in place;
- builds the `harness-ai` image unless `--no-build` is passed;
- runs `python -m pytest tests/ -m db` with `docker run --network`, the three env overrides and no `.env`.

It deselects the three `tests/test_measure_usage_latency.py` tests that refuse a non-local host name by design.

`.gitattributes` keeps `*.sh` LF. README *Running Tests* now documents the script where it used to say "A documented recipe is to follow." A small non-`db` test module guards the script against drift.

Three in-network runs were green with 0 verdict lines. The full host suite matches the baseline plus the 3 new tests.

**No rerun policy.** The spike's Recommendation reads: "A scoped rerun policy is not needed for now." So D4's "no retry" stands and `requirements.txt` is unchanged.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | LF rule for shell scripts | `.gitattributes` | ✅ |
| 2 | In-network `db` test script | `scripts/test-db-in-network.sh` | ✅ |
| 3 | README *Running Tests* recipe | `README.md` | ✅ |
| 4 | Three in-network runs | (run) | ✅ 3/3 green |
| 5 | Diff scope check | (run) | ✅ |
| 6 | Full suite against the baseline | (run) | ✅ after one flake rerun |
| + | Tests for the new script (implement Phase 4) | `tests/test_db_in_network_script.py` | ✅ (deviation 1) |

## Validation Results

| Check | Result |
|-------|--------|
| `bash -n scripts/test-db-in-network.sh` | ✅ |
| `git check-attr eol` on the script | ✅ `eol: lf`. A fresh `git checkout` of the file has 0 CR bytes. Mode `100755` |
| Backend import (`from app.main import app`) | ✅ OK |
| `GET /health` (uvicorn :8000, after bootstrapping an RBAC user) | ✅ `{"status":"ok"}` 200 |
| Frontend lint | N/A: no `frontend/` in this repo, and no UI change |
| New tests | ✅ 3 passed, 0 of them `db` |
| E2E | ✅ 7/7 |
| Full suite (host) | ✅ 3,913 collected / 3,886 passing / 27 skipped, after one infrastructure flake that passed alone |

### In-network runs (AC 1)

Docker Desktop 29.9.1, image `harness-ai-harness-ai:latest` built by run 1 from the working tree. No other pytest process ran on the machine. Every run was wrapped in a `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` helper.

| Run | Command | Start-end | Network output | Result | pytest s | `libsql verdict` lines |
|---|---|---|---|---|---|---|
| 1 | `scripts/test-db-in-network.sh` | 12:30:30-12:36:06 | `created network harness-test-net`, `connected harness-libsql-dev to harness-test-net` | **1267 passed, 1 skipped, 2645 deselected**, exit 0 | 215.9 | 0 |
| 2 | `scripts/test-db-in-network.sh --no-build` | 12:36:23-12:39:30 | none (both reused) | **1267 passed, 1 skipped, 2645 deselected**, exit 0 | 183.5 | 0 |
| 3 | `scripts/test-db-in-network.sh --no-build` | 12:39:30-12:42:50 | none (both reused) | **1267 passed, 1 skipped, 2645 deselected**, exit 0 | 196.9 | 0 |

- Run 1's wall time was 336 s in all: about 120 s of image build (layer-cached `pip`/spaCy, with the builder's `reflex` stage rerun), then the test run.
- The counts equal the spike's in-network runs (1,267 passed + 1 skipped) minus the three failures it predicted, which are now deselected. The plan expected 2,642 deselected. The extra 3 are this story's own non-`db` tests.
- The one warning is the third-party Starlette `httpx` deprecation, also present on the host.
- **No in-network stall** in 3 × 1,268 tests, so D5 is not reopened. That adds to STORY-006's 3 clean in-network runs: 6 of 6 in-network runs without a stall event visible in a failure. This story ran no per-call recorder dump, so a stall that `_reset_database()`'s retry absorbed would not show here. The spike's count of 0 in 143,461 calls remains the per-call evidence.
- Run 1's 215.9 s is slower than the spike's 181-193 s and runs 2-3. It overlapped Docker Desktop settling right after its start and the image build. No call failed.

### Full suite (AC 4)

`python -m pytest tests/ -q -p no:cacheprovider` on the host, 12:43:24-12:49:12, keep-awake: **1 failed, 3,885 passed, 27 skipped in 346.5 s** (3,913 collected).

| Test | Phase | Error | Verdict | Alone |
|---|---|---|---|---|
| `tests/test_db.py::test_init_db_migrates_a_pre_user_limits_database` | call | `StorageError: Hrana: api error: status=400 ... "STREAM_EXPIRED"` | `libsql verdict: likely infrastructure -- execute took 15.05 s and ended in STREAM_EXPIRED` | 1 passed in 0.23 s |

Once the flake counts as a pass, the result is 3,913 / 3,886 / 27. That is STORY-007's 3,910 / 3,883 / 27 (STORY-001's 3,854 / 3,827 / 27 plus the epic's 56 harness tests) plus this story's 3. It is the port-forwarding stall this story works around, on the host path, and its verdict line classified it without a rerun. `tests/test_untouched_app.py` passed inside the run. `git status -- app/ chat_ui/` is empty.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `scripts/test-db-in-network.sh` | CREATE | +84 |
| `tests/test_db_in_network_script.py` | CREATE | +46 |
| `.gitattributes` | CREATE | +2 |
| `README.md` | UPDATE | +14/-1 |

## Deviations from Plan

1. **A test module was added** (`tests/test_db_in_network_script.py`, 3 non-`db` tests). The plan said no test would be added. But `/implement` Phase 4 requires tests for new code, and the plan's own Risk P7, a deselect nodeid gone stale, is cheapest to catch in the suite. The tests check three things: that each `--deselect` names a function that still exists and is declared by `_DB_NODEIDS`; that the three overrides stay and no `--env-file` is passed; and that the script is LF with the `.gitattributes` rule in place. As a result, the full-suite count is the baseline + 3, recorded the way STORY-007 recorded the epic's harness tests, and `tests/` is no longer untouched. `app/` and `chat_ui/` are untouched as required.
2. **E2E 1 used the real stopped server.** Docker Desktop had just started and `harness-libsql-dev` was `Exited`, so the "server stopped" case needed no stopping of the shared container and no stand-in container.
3. **README line.** The paragraph the plan placed at line 910 was at line 919, because the plan had counted from an excerpt. Same paragraph, replaced as planned.
4. **Bootstrapped an RBAC user** (`e2e-bootstrap`, token discarded) for the `/health` check. The test runs leave the shared dev DB empty, so a live start fails otherwise.

## E2E Checklist

- [x] Server stopped: exit 2, the `docker start harness-libsql-dev` hint, and `harness-test-net` not created (`docker network ls` count 0)
- [x] First run from a clean state (no network) created the network, connected the server, built and ran green (run 1)
- [x] Second run with the network present: no "already exists" or error output, green (run 2, and run 3)
- [x] Three runs at 1,267 passed / 1 skipped, 0 `libsql verdict` lines. Deselected was 2,645, not 2,642 (see above)
- [x] Pass-through: `--no-build -k test_init_db` gave 46 passed, 3,867 deselected, exit 0
- [x] Server networks afterwards: `bridge` + `harness-test-net`, still `8080/tcp -> 0.0.0.0:8080`. A host-side `pytest tests/test_conftest_fixtures.py -m db` gave 16 passed
- [x] Full host suite: 3,913 / 3,886 / 27 after one verdict-labelled flake

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db_in_network_script.py` | `test_every_deselected_test_exists_and_is_a_db_test`, `test_the_run_overrides_every_inherited_database_setting`, `test_the_script_is_lf_only_and_kept_so_by_gitattributes` |

## State Left Behind

- `harness-test-net` exists, and `harness-libsql-dev` is connected to it, on purpose: the script reuses both. Remove them with `docker network disconnect harness-test-net harness-libsql-dev && docker network rm harness-test-net`.
- Image `harness-ai-harness-ai:latest` was rebuilt from the working tree.
- `harness-libsql-dev` is running. Its data was reset by the `db` runs, and it holds the `e2e-bootstrap` user.
- Scratch logs: `in-net-{1,2,3}.log`, `full-1.log` and `keepawake-run.ps1` in the session scratchpad. Not committed.

## Acceptance Criteria

- [x] Given D5 **confirmed**: `scripts/test-db-in-network.sh` runs `-m db` from the `harness-ai` image on `harness-test-net` and creates the network idempotently. README *Running Tests* documents it. Three runs are recorded green above.
- [x] Given D5 **refuted** / stalls unavoidable: N/A. D5 is confirmed, and the spike says "A scoped rerun policy is not needed for now." `requirements.txt` is unchanged and D4 stands.
- [x] Given **inconclusive**: N/A. D5 is confirmed.
- [x] Full-suite counts equal STORY-001's baseline as carried by STORY-007 (3,910 / 3,883 / 27), plus this story's 3 tests. No file under `app/` or `chat_ui/` changed.
- [x] All tasks completed
- [x] Follows existing patterns
