---
story: STORY-011
prd: PRD-019
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-011-multi-instance-docs.plan.md
epic_branch: epic/PRD-019-multi-instance-deployment
commit: pending
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report — STORY-011: Multi-instance docs, PRD close-out

## Summary

Docs only. `docs/deployment.md` "Multiple instances" rewritten from the shipped files (topology, affinity and failover, probes, timeouts, balancer errors, rolling restart with exit codes, TLS and port, not supported / not verified, security). Four settings added to `docs/configuration.md` and `.env.example`; roadmap item ticked; README and `docs/testing.md` updated; PRD frontmatter set to `done`.

## Files Changed

`docs/deployment.md`, `docs/configuration.md`, `.env.example`, `docs/roadmap.md`, `README.md`, `docs/testing.md`, PRD.md frontmatter, story, index, plan (archived), this report.

## Validation Results

| Check | Result |
|---|---|
| Backend import | OK |
| `tests/test_config.py` + `tests/test_caddyfile_routes.py` | 254 passed |
| gen_index | errors: none, 11/11 |
| Full suite | GitHub CI on push (user decision) |

AC4 grep (setting -> file naming it): DRAIN_FILE app/config.py + rolling_restart.sh; READY_DB_TIMEOUT_SECONDS app/config.py; OPENROUTER_TIMEOUT_SECONDS app/config.py + script; DRAIN_SECONDS, POLL_SECONDS, DRAIN_WAIT_SECONDS, READY_TIMEOUT_SECONDS script; LB_COOKIE_SECRET docker-compose.lb.yml; PORT all three. REFLEX_REDIS_URL is Reflex's own, documented as "leave unset". All referenced files exist.

## Deviations from Plan

- The `/ready` draining body is documented as the code returns it (`{"status":"not_ready","reason":"draining"}`, `app/main.py:55-75`), not as the plan paraphrased it.
- `REFLEX_REDIS_URL` and `LB_COOKIE_SECRET` are commented-out lines in `.env.example` (no active empty assignment), per orchestrator notes.
- No docstring pointer added to `tests/test_two_instance_smoke.py` (as the plan decided).

## Acceptance Criteria

- [x] AC1 deployment.md rewritten (no "unblocked")
- [x] AC2 settings documented (test_config green)
- [x] AC3 roadmap ticked, README links `#multiple-instances`
- [x] AC4 settings exist in code (grep above)
- [x] AC5 PRD done, board 100%
