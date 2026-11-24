# Shared brief for PRD-023 subagents (read fully before starting)

You are one subagent in an orchestrated run. An orchestrator verifies your output after you finish. It checks the files, the diff and the tests, so report only what you actually did and saw.

## Repository and branch
- Repo: `G:/coding/harness-ai`. Branch: `epic/PRD-023-mcp-and-skills`. It is checked out. **Never** switch or create branches, push, merge, rebase, amend or force anything.
- PRD: `.agents/PRDs/PRD-023-mcp-and-skills/PRD.md`. Stories: `.agents/stories/PRD-023-mcp-and-skills/`. Board: `.agents/PRDs/PRD-023-mcp-and-skills/index.md`.
- Today's date for every `created` / `updated` / `completed` field: **2026-11-24**.

## Commands you follow
- PLAN subagent: follow `.agents/commands/plan.md` phase by phase, skipping nothing (including SCAN SKILLS and UPDATE STORY FILE + index). PLAN ONLY: no application code, tests or docs, and no commits. If you cannot spawn Explore agents, explore with Grep/Glob/Read yourself. The plan must cite real `file:line` references that you opened.
  - **Do not read the whole PRD** (this overrides plan.md's "Read parent PRD"). Read the story, its Technical Notes, and only the PRD sections the orchestrator names in your prompt: find them with `grep -n "^#" <PRD>` and read them with offset/limit. Read the PRD frontmatter if you need it.
  - **Design decisions in your prompt are binding.** If the code makes one impossible, say so in your final message instead of choosing another design.
  - **Keep the plan under ~12 KB.** Cite patterns as `file:line` with an excerpt of at most 5 lines; never paste whole functions or files (the implementer opens them anyway).
  - The PRD's `file:line` evidence was read on `main` @ `2253871`, before PRD-018/020/021/022 landed. Line numbers and some signatures have moved: always cite what you opened today, not the PRD's numbers.
- IMPLEMENT subagent: follow `.agents/commands/implement.md` phase by phase, skipping nothing.
  - The working tree will contain this story's plan plus the story/index edits the planner made. They belong to this story; do not stop for them.
  - Validation for this repo: there is no `frontend/` and no npm lint. Use:
    - `.venv/Scripts/python -c "from app.main import app; print('OK')"`
    - Only if you touched `chat_ui/`: the probe form from `tests/test_chat_ui_startup_guard.py` (cwd `chat_ui/`, `PYTHONPATH="<repo>/chat_ui;<repo>"`, env `DATABASE_URL`, `OPENROUTER_API_KEY`, `ADMIN_TOKEN` set, then `import chat_ui.chat_ui`). Running that test file is usually enough.
  - **Do NOT run the full suite** (user decision: it runs in GitHub CI on every push; the orchestrator reads it). Wherever implement.md or the plan says "full suite", this rule wins. **Never run two pytest processes at once**: every DB test shares the one libSQL server, and concurrent runs fail each other with `no such table`. Leave no background process or timer behind when you finish. Run instead, in one pytest call: every new or modified test file, the existing `tests/test_<module>.py` of every pre-existing module you changed, the tests the plan names, and the guard tests (`test_pii_redaction_integration.py` when you rename or remove a test; `test_untouched_app.py` when you touch app files). Do not add every file that merely imports a changed module. Aim for under ~10 minutes. Record the exact pass/fail/skip counts. In the report write "Full suite: GitHub CI on push (user decision)".
  - Renaming or removing a pre-existing test function: register the old name in `_DELIBERATELY_SUPERSEDED_TESTS` in `tests/test_pii_redaction_integration.py`.
- SPIKE stories (STORY-001/002): the plan/implement split still applies; the "implementation" is the research, `tests/corpora/mcp/SOURCES.md` and the report. Pin every external link to a revision, tag or commit. Mark anything you could not verify as "not verified" with the safe default, never as fact.
- **Always prefix pytest with `PYTHONUTF8=1`** (the Spanish Windows locale breaks `test_db_isolation_harness.py` otherwise).
- DB tests need the libSQL dev server `harness-libsql-dev` on :8080. If many `db` tests error at fixture setup, run `docker restart harness-libsql-dev` and rerun before suspecting the code. Do not start a second one. If `docker` cannot reach the engine, Docker Desktop is down: report it, do not start it yourself.
- Pre-existing failures (from the orchestrator's baseline, CI run 45029831315 on `main@b96139d`): none.

## Commits (implement subagent)
- Stage files explicitly; never `git add -A` / `git add .`. Never `--no-verify`; if a hook fails, fix the cause and make a new commit. Never push: the orchestrator pushes after it verifies the story.
- End every commit message with the `Co-Authored-By:` line your harness's attribution reminder gives for your own model (e.g. `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`); if you have none, use `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never amend to change it.
- Order: commit code + tests + archived plan + report (with `commit: pending`) as `<type>(PRD-023): {STORY-ID} <summary>`. Capture the SHA. Then make one small follow-up `chore(PRD-023): {STORY-ID} report; update status + index` that fills the SHA into the report and story frontmatter.

## Editing files
- Use the Edit/Write tools for code. Git Bash heredocs on this machine mangle `\\` escapes inside Python edit scripts.

## Regenerating index.md
After any story frontmatter change, run from the repo root:
`PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-023`
It must print `errors: none`.

## Code conventions (non-negotiable)
- Match the surrounding code: comment density, docstring style (they cite PRD sections and decisions, e.g. "PRD-023 D9"), naming, frozen dataclasses for config models, closed vocabularies, and error messages that name the file, the node and the rule.
- Every modified pre-existing test assertion gets a comment citing PRD-023 and the decision.
- Do not implement work that belongs to a later story. If the story text conflicts with the PRD or the real code, follow the code's reality, document the deviation in the plan or report, and tell the orchestrator.
- **Off means PRD-017 (D20).** With `MCP_ENABLED=false`, `/mcp` is not mounted, `mcp_config.load()` opens no file, step 7c behaves exactly as today, and every existing test passes unmodified (apart from the rule-count assertions 25→26 / 10→11, STORY-005, and new audit columns). Never edit a PRD-016/017/021 test to make it pass — report it instead.
- **One engine.** Gateway calls go through `action_policy.evaluate()` unchanged in its rules, grants, fold and fail-closed boundary (D4). `action_policy` stays pure: no I/O, no settings reads; callers compute the visible set and pass it in. No new operation kind or classifier.
- **Evidence before effect (D9, T9).** No `tools/call` is forwarded until its decision row has committed. The pre-forward write calls `action_audit.record()` **without** an `audit_ref` (or `database.insert_action_decisions` directly), so it commits or raises and never journals (PRD-018 O8, documented at `app/services/action_audit.py` `record()`). `record_outcome` is best effort and never raises into the response path.
- **Credentials and secrets (D10, T2, T16).** Upstream credentials come only from env names in `MCP_CONFIG_FILE`; their values never appear in a log line, exception, digest, API field or audit row. Southbound headers are built only from config; no inbound header is forwarded. Messages to the agent name the tool and the server id, never a URL, header name or env name. Results are never stored (hash, size, flags only).
- **The harness runs no tool code (T17).** `mcp` (the SDK) is imported only by `app/services/mcp_upstream.py`. No `app/` module imports `subprocess` from `mcp_*` modules, `mcp.client.stdio` or `mcp.server`. Test infrastructure (`scripts/stub_mcp_server.py`) may use `mcp.server`; `app/` never imports it.
- **Runtime dependency**: only `mcp` is added (STORY-003 pins it exactly). No other new runtime dependency.
- **Census guards**: a new public function in `app/db/database.py`, or any new caller of `get_connection()` / `_session()` there, must be registered in `tests/test_db_resilience_retry.py` (`_EXPECTED_KINDS` or `_EXEMPT`, and the caller sets in `test_nothing_opens_a_session_outside_the_unit_and_the_boot_path`). Audit fields have a field-order guard (grep `usage_estimated` in `tests/`). Adding a field to `GET /audit` means updating `tests/test_pii_redaction_integration.py::test_audit_endpoint_contract_has_no_preview_fields`. Changing a `database.py` reader signature means `tests/test_db.py`'s signature snapshot. Changing a public pipeline signature (`run_query`, `run_conversation`): grep `tests/` for `inspect.signature(` and `kwargs == {` guards. A new `copy`/`admin_copy` constant goes into `tests/test_copy.py`'s census; admin modules must not mention chat-only inks (`tests/test_admin_palette.py`). Grep `tests/` for any function/field/constant you change and run the hits.
- **New route or `/stats` key**: a new HTTP route (`/mcp`, `/skills`) must be added to the `@backend_routes` matcher in `Caddyfile` and to `EXPECTED_MATCHER` in `tests/test_caddyfile_routes.py`. Run that file.
- **Async teardown assertions** (lesson from CI 45199692297): after `mcp_upstream.aclose_all()`, SDK/httpx helper tasks may still be finishing on a slow runner. A test that asserts no task is left must first `await asyncio.wait(others, timeout=5)` and then assert none is pending, never snapshot `asyncio.all_tasks()` immediately.
- Tests that start stubs or servers use free ports picked at runtime, deadline loops instead of bare `sleep`, and stop every child on teardown. They must work on Windows (local) and Linux (CI). Timing assertions get generous margins on CI. Cache/idle/window tests use an injected clock, never real sleeps.
- **Targeted runs on this machine**: foreground, small sequential batches; prefer `-k` over whole DB-heavy guard files (`tests/test_db.py` alone takes ~12 min). A run killed for memory (exit 137, no output) is environmental: report it, do not loop.
- **Python versions differ**: CI runs Python 3.11, the local venv 3.12. On 3.11 `asyncio.wait_for` wraps the coroutine in a child task, so a test counting `asyncio.all_tasks()` must diff against a snapshot taken at its start. Do not rely on 3.12-only stdlib behaviour.
- **Never dodge a guard test**: if a source-scanning guard (e.g. "never reads the clock") blocks your design, change the design (inject the value from the caller), not the spelling.
- Chat UI: Reflex APIs are checked against the pinned version (installed package source), not from memory (`chat_ui/AGENTS.md`). Every user-facing string goes in `chat_ui/chat_ui/copy.py` / `admin_copy`, in English.

## What to return (your final message, at most ~30 lines)
- PLAN subagent: the plan path, a 3–5 line summary, the files to CREATE/UPDATE, one line per AC saying how it is covered, open risks/questions, and confirmation that the story frontmatter (`plan`, `status: in-progress`) and the index were updated.
- IMPLEMENT subagent: the commit SHA(s), the files changed, the exact targeted test counts, each AC with pass/fail and the test that proves it, deviations, and anything left undone. If something failed or you stopped early, say so plainly. Do not report success you did not verify.

- Lesson (STORY-016/017, db tests seen only in CI): read a row back only after the insert that creates it (`_by_id()[_insert()]` evaluates `_by_id()` first); seed rows must not inherit gateway defaults they do not mean; a fixture borrowed from another test module needs its own fixture dependencies imported too.

## Checkpoint
- Done and pushed: STORY-001 to STORY-018. CI run 45240157760 @ `5a103cd`: 2 failed / 12514 passed, both STORY-017 db-test bugs, fixed in `24ace2c` (pushed). Read the run of the latest HEAD first; expect green.
- Docker Desktop is down on the dev machine: run `-m "not db"` locally; CI covers DB and lifespan tests. CI is Python 3.11, local 3.12. Embedded `libsql.connect(":memory:")` works locally for SQL probes.
- Epic-wide decisions: see the PRD and stories' Technical Notes; previous checkpoint facts for 001-015 hold (handshakes, `mcp==2.3.0`, gateway M3-M9, `_screen_result`, prompts).
- STORY-016: `action_policy.resolve_v1_alias` / `AliasInput` / `evaluate_all(..., aliases=)`; step 7c builds aliases via `query_pipeline._alias_input` (MCP on + prefixes; config-only, no DB). `ActionDecision.mcp_server`; alias rows hash computed in `action_audit._row_of`. Claim = one `INSERT ... SELECT ... LEFT JOIN` in `database.insert_mcp_decision_linked` (McpRecord `link_candidates/link_window_seconds/link_now`); `_correlate` gone.
- STORY-017: `/audit/actions` filters `surface, server, outcome, linked` (linked=false = `surface='mcp' AND linked_decision_id IS NULL`); entry +8 fields; `GET /skills` (`stats:read`, MCP off -> 200 `{skills:[], mcp_config_digest:null}`); `authz.roles_holding`.
- STORY-018: console Actions MCP chips/toggle/4 columns (`components/actions_mcp.py`), Skills page only when MCP on at import; linked column = in-page anchor `#action-<id>` (works only within the 500-row window).
- Ahead: 019 corpus+latency (must read both `result_flags` shapes; alias + correlation cases), 020 E2E OpenCode/Cline, 021 docs (+ rule counts left by STORY-005). None critical by design; 019 touches the corpus format consumed by 020.
- Planner escalations: none. Plans corrected at 3.2: 2/18 (plans over 12 KB accepted: 016 14.8 KB, 018 12.4 KB).
- For Phase 6 (in addition to the previous list): carried-over errors fixed in `5a103cd` (STORY-016 correlation tests read before insert; missing `provider_file` fixture import; STORY-014 `hash_prompt` census site in mcp_gateway) and `24ace2c` (STORY-017 kwargs recorder, v1b seed). Deviations: 016 hash in `_row_of`, new `insert_mcp_decision_linked` (census 45); 017 omits `result_hash`/`arguments_canonical_hash`/`mcp_config_digest` from entries; 018 linked anchor, narrowed scope line, unlinked toggle sets decision=all, MCP-on grid min 101rem.
