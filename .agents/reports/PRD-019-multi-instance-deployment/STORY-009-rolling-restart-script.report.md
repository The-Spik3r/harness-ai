---
story: STORY-009
prd: PRD-019
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-009-rolling-restart-script.plan.md
epic_branch: epic/PRD-019-multi-instance-deployment
commit: pending
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report - STORY-009: Rolling restart script

## Summary
`scripts/rolling_restart.sh` (LF, mode 100755) restarts `harness-a` then `harness-b` of `docker-compose.lb.yml`: refuses unless every instance's in-container `/ready` is 200; per instance re-checks the others (never drains the last healthy one), touches the container's `$DRAIN_FILE`, waits for its own 503, sleeps `health_interval*2 + DRAIN_SECONDS`, recreates with `up -d --force-recreate --no-deps`, waits for 200. `health_interval` is parsed from `deploy/lb/Caddyfile`. `DRAIN_SECONDS` = env, else `OPENROUTER_TIMEOUT_SECONDS + 10` where the timeout is the shell env, else the value inside the first instance, else 120; fractions round up. No `app/` change. Live run is STORY-010.

## Validation Results
| Check | Result |
|-------|--------|
| `bash -n`, `git ls-files -s` | OK, 100755 |
| Backend import | OK |
| Targeted tests (`test_rolling_restart_script.py`, `test_lb_caddyfile.py`) | 28 passed, 1 skipped (the skip is in test_lb_caddyfile; new file: 18 passed, 0 skipped) |
| E2E | shim cases only; live Docker run belongs to STORY-010 |
| Full suite | GitHub CI on push (user decision) |

## Files Changed
| File | Action |
|------|--------|
| `scripts/rolling_restart.sh` | CREATE |
| `tests/test_rolling_restart_script.py` | CREATE |

## Deviations from Plan
- Orchestrator correction applied: container-value step in the timeout resolution (plan risk note updated).
- Fallback literal is `timeout="${timeout:-120}"` (not `: "${OPENROUTER_TIMEOUT_SECONDS:=120}"`) because of the container step; the test asserts it equals the Settings default.
- Shim `sleep` is injected via `BASH_ENV` as a function: on Git Bash `/usr/bin` precedes a prepended PATH entry, so a PATH shim was ignored (first run hung on real sleeps).
- Test bash selection on Windows prefers Git Bash, skips without a usable bash.

## Tests Written
Static: LF + exec bit, strict mode, `bash -n`, service list vs compose, in-container python/urllib (no curl/wget), 120 and DRAIN_FILE literals vs Settings, health_interval parsed not restated, `+ 10` formula. Shim: refuse at start, happy path order + drain window = `2*HEALTH_INTERVAL_S + 7`, replacement never ready, last-healthy recheck, drain undo, container timeout (30.5 -> 31, empty -> 120), operator env beats container, DRAIN_SECONDS beats all, unknown flag.

## Acceptance Criteria
- [x] AC1 refusal naming the instance: `test_refuses_when_an_instance_is_not_ready`
- [x] AC2 order, sleep formula, defaults, flags: `test_happy_path_order_and_drain_window`, `test_drain_window_uses_the_container_timeout`, static literals
- [x] AC3 never-ready replacement stops, other untouched: `test_stops_when_replacement_never_ready`
- [x] AC4 static checks: `test_bash_syntax`, `test_service_list_matches_compose`, `test_readiness_runs_in_container_with_python_urllib`, `test_strict_mode`
