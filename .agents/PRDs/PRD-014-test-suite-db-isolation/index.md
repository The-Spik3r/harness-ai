# PRD-014-test-suite-db-isolation: Test Suite Database Isolation — Only the Tests That Need Storage Touch It, and Their Failures Say Why — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-014-test-suite-db-isolation` (base: `main`)
**Status**: active

## Progress

2/8 stories done — 25%

## Stories

All stories commit on the epic branch `epic/PRD-014-test-suite-db-isolation`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Characterize the suite's storage use: baseline run, driver calls per test, census and undeclared-storage list | technical | ✅ done | small | [plan](../../plans/PRD-014-test-suite-db-isolation/completed/STORY-001-storage-characterization.plan.md) | `398e60e` |
| STORY-002 | db marker: registered, applied from the storage fixtures and _DB_NODEIDS, independent of --run-benchmark | technical | ✅ done | small | [plan](../../plans/PRD-014-test-suite-db-isolation/completed/STORY-002-db-marker.plan.md) | `6628c25` |
| STORY-003 | Reset only db tests, refuse storage in every other test, and declare every test the guard catches | technical | ⬜ todo | medium | — | — |
| STORY-004 | Lazy _libsql_endpoint: pytest -m "not db" passes with Docker stopped | technical | ⬜ todo | small | — | — |
| STORY-005 | Driver recorder and a libsql diagnostics section with a verdict on every failing db test | feature | ⬜ todo | medium | — | — |
| STORY-006 | Spike: run the db tests from inside the Docker network vs the host to test the port-forwarding hypothesis (D5) | spike | ⬜ todo | small | — | — |
| STORY-007 | README and conftest docstring for the db split, plus a three-run regression sweep | technical | ⬜ todo | small | — | — |
| STORY-008 | (Conditional on D5) Act on the spike: in-network test recipe, or a rerun policy scoped to infrastructure failures | technical | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-002 blocked by STORY-001
- STORY-003 blocked by STORY-001, STORY-002
- STORY-004 blocked by STORY-003
- STORY-005 blocked by STORY-002, STORY-003
- STORY-006 blocked by STORY-005
- STORY-007 blocked by STORY-003, STORY-004, STORY-005, STORY-006
- STORY-008 blocked by STORY-006
