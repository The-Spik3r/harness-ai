# Shared brief for PRD-019 subagents (read fully before starting)

You are one subagent in an orchestrated run. An orchestrator verifies your output after you finish. It checks the files, the diff and the tests, so report only what you actually did and saw.

## Repository and branch
- Repo: `G:\coding\harness-ai` (Git Bash path `/g/coding/harness-ai`). Branch: `epic/PRD-019-multi-instance-deployment`. It is checked out. **Never** switch or create branches, push, merge, rebase, amend or force anything.
- PRD: `.agents/PRDs/PRD-019-multi-instance-deployment/PRD.md`. Stories: `.agents/stories/PRD-019-multi-instance-deployment/`. Board: `.agents/PRDs/PRD-019-multi-instance-deployment/index.md`.
- Today's date for every `created` / `updated` / `completed` field: **2026-11-17**.

## Commands you follow
- PLAN subagent: follow `.agents/commands/plan.md` phase by phase, skipping nothing (including SCAN SKILLS and UPDATE STORY FILE + index). PLAN ONLY: no application code, tests or docs, and no commits. If you cannot spawn Explore agents, explore with Grep/Glob/Read yourself. The plan must cite real `file:line` references that you opened.
  - **Do not read the whole PRD** (this overrides plan.md's "Read parent PRD"). Read the story, its Technical Notes, and only the PRD sections the orchestrator names in your prompt: find them with `grep -n "^#" <PRD>` and read them with offset/limit. Read the PRD frontmatter if you need it.
  - **Design decisions in your prompt are binding.** If the code makes one impossible, say so in your final message instead of choosing another design.
  - **Keep the plan under ~12 KB.** Cite patterns as `file:line` with an excerpt of at most 5 lines; never paste whole functions or files (the implementer opens them anyway).
- IMPLEMENT subagent: follow `.agents/commands/implement.md` phase by phase, skipping nothing.
  - The working tree will contain this story's plan plus the story/index edits the planner made. They belong to this story; do not stop for them.
  - Validation for this repo: there is no `frontend/` and no npm lint. Use:
    - `.venv/Scripts/python -c "from app.main import app; print('OK')"`
    - Only if you touched `chat_ui/`: the probe form from `tests/test_chat_ui_startup_guard.py` (cwd `chat_ui/`, `PYTHONPATH="<repo>/chat_ui;<repo>"`, env `DATABASE_URL`, `OPENROUTER_API_KEY`, `ADMIN_TOKEN` set, then `import chat_ui.chat_ui`). Running that test file is usually enough.
  - **Do NOT run the full suite** (user decision: it runs in GitHub CI on every push; the orchestrator reads it). Wherever implement.md or the plan says "full suite", this rule wins. **Never run two pytest processes at once**: every DB test shares the one libSQL server, and concurrent runs fail each other with `no such table`. Leave no background process or timer behind when you finish. Run instead, in one pytest call: every new or modified test file, the existing `tests/test_<module>.py` of every pre-existing module you changed, the tests the plan names, and the guard tests (`test_pii_redaction_integration.py` when you rename or remove a test; `test_untouched_app.py` when you touch app files). Do not add every file that merely imports a changed module. Aim for under ~10 minutes. Record the exact pass/fail/skip counts. In the report write "Full suite: GitHub CI on push (user decision)".
  - Renaming or removing a pre-existing test function: register the old name in `_DELIBERATELY_SUPERSEDED_TESTS` in `tests/test_pii_redaction_integration.py`.
- **Always prefix pytest with `PYTHONUTF8=1`** (the Spanish Windows locale breaks `test_db_isolation_harness.py` otherwise).
- DB tests need the libSQL dev server `harness-libsql-dev` on :8080. If many `db` tests error at fixture setup, run `docker restart harness-libsql-dev` and rerun before suspecting the code. Do not start a second one.
- Pre-existing failures (from the orchestrator's baseline, CI run 44206177245 on `main` @ `46f55ae`, green; `68fa28a` changed only `.agents/commands/`): none.

## Commits (implement subagent)
- Stage files explicitly; never `git add -A` / `git add .`. Never `--no-verify`; if a hook fails, fix the cause and make a new commit. Never push: the orchestrator pushes after it verifies the story.
- End every commit message with exactly: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
- Order: commit code + tests + archived plan + report (with `commit: pending`) as `<type>(PRD-019): {STORY-ID} <summary>`. Capture the SHA. Then make one small follow-up `chore(PRD-019): {STORY-ID} report; update status + index` that fills the SHA into the report and story frontmatter.

## Editing files
- Use the Edit/Write tools for code. Git Bash heredocs on this machine mangle `\\` escapes inside Python edit scripts.

## Regenerating index.md
After any story frontmatter change, run from the repo root:
`PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-019`
It must print `errors: none`.

## Code conventions (non-negotiable)
- Match the surrounding code: comment density, docstring style (they cite PRD sections and decisions, e.g. "PRD-019 D5"), naming, frozen dataclasses for config models, closed vocabularies, and error messages that name the file, the node and the rule.
- Every modified pre-existing test assertion gets a comment citing PRD-019 and the decision.
- Do not implement work that belongs to a later story. If the story text conflicts with the PRD or the real code, follow the code's reality, document the deviation in the plan or report, and tell the orchestrator.
- **`/ready` never moves PRD-018's breaker** (D5): no `_unit_of_work`, no retry, no `record_success` / `record_failure`, no driver call while the breaker is not `closed`. `/health` stays byte-identical (D3).
- **Single instance unchanged**: `docker-compose.yml`, the in-container `Caddyfile`'s routing (beyond adding `/ready`) and the image start command keep working exactly as now.
- **No new Python dependency.** Caddy is a binary, never a pip package; never commit a binary.
- Tests that start processes (uvicorn, caddy, stub) use free ports picked at runtime, deadline loops instead of bare `sleep`, and kill every child on teardown, also on failure. They must work on Windows (local) and Linux (CI).
- `tests/test_two_instance_smoke.py` is untouched apart from a docstring pointer (PRD Section 11).
- **Census guards** (learned in STORY-001, CI run 44213079565): a new public function in `app/db/database.py`, or any new caller of `get_connection()` / `_session()` there, must be registered in `tests/test_db_resilience_retry.py` (`_EXPECTED_KINDS` or `_EXEMPT`, and the caller sets in `test_nothing_opens_a_session_outside_the_unit_and_the_boot_path`), and any new reference to `_storage_breaker` in `tests/test_db_resilience_breaker.py`. Run those files when you touch `database.py`.
- **Local Caddy**: Caddy 2.11.7 for Windows is at `C:\Users\nahue\AppData\Local\Temp\claude\3538ad6943244944\ae048d09-ec22-4488-b3cf-ef6f7307e3c6\scratchpad\caddy_spike\caddy\caddy.exe` (never commit it; tests find it via `CADDY_BIN` or `PATH`). Each `caddy run` child needs env `CADDY_ADMIN=localhost:<free port>`. STORY-004's report has every verified Caddy behaviour; read its Findings before writing balancer code or tests.

## What to return (your final message, at most ~30 lines)
- PLAN subagent: the plan path, a 3–5 line summary, the files to CREATE/UPDATE, one line per AC saying how it is covered, open risks/questions, and confirmation that the story frontmatter (`plan`, `status: in-progress`) and the index were updated.
- IMPLEMENT subagent: the commit SHA(s), the files changed, the exact targeted test counts, each AC with pass/fail and the test that proves it, deviations, and anything left undone. If something failed or you stopped early, say so plainly. Do not report success you did not verify.

- **Balancer test harness** (STORY-007): reuse `tests/_balancer_stack.py` (`Balancer`, `Instance`, `Child`, `wait_until`, `_upstream_port(i)` hook) and `tests/_lb_instance.py` (per-path counters, `/__test__/counters|reset-counters|init-db|breaker/open|breaker/reset`). Children run `RBAC_ENABLED=false`, `PII_REDACTION_ENABLED=false`, own `DRAIN_FILE`/`AUDIT_BUFFER_DIR` under tmp. On Windows kill with `kill_tree` + `port_closed_within` (`tests/e2e/_live.py`); `Popen.kill()` orphans the venv launcher's child. `/query` usage refusals are `200 BLOCKED`, `/v1` ones `403` (no 429).
- **No leftover background tasks**: before your final message, stop every Monitor/background task you started (TaskStop). Waiting is a deadline loop inside the test or command, not a Monitor of `sleep`.
- **Shell shims in tests must be executable** (STORY-009 CI fix ffa10df): `chmod(0o755)` every fake `docker`/`sleep` written to a PATH dir. Git Bash ignores the exec bit, Linux does not: without it CI runs the runner's real `docker`. Tests that drive bash scripts must pass on both.

## Checkpoint
- Done and pushed: STORY-001..007 (see git log), 008 (a366a81), 009 (2159d19; CI fix ffa10df shims chmod), 010 (64a148c). Next: STORY-011 (docs, small, not critical).
- CI: run 44226260037 at 62938d5 failed (009 shims not executable on Linux, fixed in ffa10df); run 44230413375 at ffa10df is the one to read on resume.
- Pre-existing failures: none (main baseline green).
- STORY-008: balancer module ~6.8 min locally / ~5 min CI (100 s calls, no `slow` marker exists). `FrontedBalancer` proves lb -> repo Caddyfile (gzip) -> uvicorn; gzip on text/event-stream asserted.
- STORY-009/010: `scripts/rolling_restart.sh [-f FILE]... [-p PROJECT]`; drain window = 2*health_interval (parsed from deploy/lb/Caddyfile) + DRAIN_SECONDS (default OPENROUTER_TIMEOUT_SECONDS+10, read shell env > first instance container > 120). Exit codes 1 config, 2 refusal (incl. other instance not ready before each drain), 3 drain never took effect (undone), 4 replacement never ready. Script does not build: operator builds first.
- STORY-010: opt-in `tests/e2e/test_lb_docker.py` + overlay `tests/e2e/docker/compose.lb-e2e.yml` (project `harness-lb-e2e`, stub inside each instance, overlay restates the image CMD; guard `tests/test_lb_e2e_overlay.py`). Ran locally: 4 passed, 350 s cached / 762 s cold; 75 /query calls, 0 failures during the rolling restart. Not in CI.
- STORY-005: `docker-compose.lb.yml` has `name: harness-ai-lb` (own project + own audit volume, so `down -v` of one stack cannot destroy the other journal); lb publishes `${PORT:-8000}`.
- STORY-011 must document: build before rolling restart; OPENROUTER_TIMEOUT_SECONDS resolution; cookie has no `Secure`/is a session cookie (STORY-004); `docker compose config` prints .env secrets; how to run the E2E (`--run-e2e`, ~6-13 min).
- Planner escalations: none. Plans corrected at 3.2: 1/10 (009: timeout read from container). Plans over 12 KB accepted: 005, 007, 008, 010.
- For Phase 6: check_ready's runtime WARNING reuses the boot classifier's text (cosmetic); STORY-003 skipped `docker build` (010 built the image); carried-over error 009 shims (ffa10df).
