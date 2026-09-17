---
id: STORY-001
prd: PRD-009
slug: characterization-and-outcome-baseline
title: "Characterization tests of today's duplicate lookup and the six-outcome /query baseline, on untouched production code"
type: technical
priority: high
complexity: medium
phase: "1 - Pin and prepare"
status: done
labels: [backend, tests, security]
epic_branch: epic/PRD-009-duplicate-rescoping
plan: .agents/plans/PRD-009-duplicate-rescoping/completed/STORY-001-characterization-and-outcome-baseline.plan.md
report: .agents/reports/PRD-009-duplicate-rescoping/STORY-001-characterization-and-outcome-baseline.report.md
commit: 9abef61
depends_on: []
blocks: [STORY-002, STORY-003, STORY-004]
skills: []
created: 2026-09-16
updated: 2026-09-16
---

# STORY-001: Characterization tests of today's duplicate lookup and the six-outcome /query baseline, on untouched production code

## Description

As a security admin, I want today's duplicate behaviour pinned by tests before any production line changes, so that each behaviour change later in this PRD shows up as a deliberate, cited edit to an existing assertion, never as a test that silently started passing.

## Acceptance Criteria

- [ ] Given a new `tests/test_duplicate_characterization.py` and **no change under `app/`**, when it runs against `main`, then it passes and pins each of today's behaviours with one test apiece. Each behaviour is observed through `POST /query` (or `run_query`) and not only through `check_duplicate`:
  - a `success=0` row from an `OpenRouterError` blocks the same prompt's retry
  - a `success=0` row from an input `PiiRedactorError` blocks the retry
  - a policy-denial row (`denied_permission` set, `success=1`) blocks the same prompt from the same user with an allowed model
  - a row written by user A blocks the same prompt from user B
  - a duplicate-blocked row keeps the window alive once the original has aged out (A at −25h, B blocked at −2h, new send → `BLOCKED`, `first_query_at == B.timestamp`; PRD Section 6.4)
- [ ] Given each characterization test, when it is read, then its name or docstring states it pins **pre-PRD-009 behaviour** and names the decision or story expected to flip it (D1/D3 → STORY-004, cross-user → STORY-005). Nobody should mistake a pinned defect for a requirement.
- [ ] Given a new `tests/test_query_outcomes_regression.py`, when it runs on `main`, then it pins the six outcomes of PRD Section 11 through `POST /query`: status code, body `status`/`reason`/`required_permission` (or `detail` for 5xx), and the audit-row count for each. It pins outcome 6 in both forms: redactor failure (1 row) and duplicate-lookup storage failure, with the row count the existing `test_duplicate_check_storage_failure_returns_500` observes.
- [ ] Given outcome 2 in the regression module, when it seeds its prior query, then the prior is a **same-user, successful** send, so the test stays green through every later story without modification.
- [ ] Given the full suite, when it runs, then everything passes and no pre-existing test file is modified.

## Technical Notes

- **No production code changes.** If a characterization test cannot pass on `main`, the test is wrong or the PRD's premise is. Stop and record it rather than touching `app/`.
- Seed rows the way [tests/test_duplicate_checker.py](../../../tests/test_duplicate_checker.py) does (`insert_audit_log(AuditLog(...))` with a backdated `timestamp`) for the ageing cases. Drive the live arms through `fastapi.testclient.TestClient(app)` with `app.routers.query.call_openrouter` monkeypatched, as [tests/test_query_router.py](../../../tests/test_query_router.py) does.
- Force an `OpenRouterError` with a fake `call_openrouter` that raises it. Force an input `PiiRedactorError` by monkeypatching `query_pipeline.redact` to raise. Force a denial with a model outside `MODEL_ALLOWLIST`; [tests/test_query_pipeline_authorization.py](../../../tests/test_query_pipeline_authorization.py) has working setups for all three denial arms.
- The two-user case needs two tokens. [tests/test_pii_dedup_isolation.py](../../../tests/test_pii_dedup_isolation.py) already registers `juan`/`maria` users with headers; reuse its approach.
- Outcome 4 must use a *policy* refusal (`200 BLOCKED` with `required_permission`), not the router's 401/403.
- Environment: per the project's libSQL dev-server note, mass fixture errors across a run mean restarting the container, not bisecting code.
- Skills: none applicable (`frontend-design` only covers UI visual design).

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-002, STORY-003, STORY-004

## PRD Reference

Source: [`PRD-009-duplicate-rescoping/PRD.md`](../../PRDs/PRD-009-duplicate-rescoping/PRD.md) — sections 4 (Threat reasoning & characterization), 6.4, 7 (F1), 11 (six outcomes), 12 (Phase 1)
