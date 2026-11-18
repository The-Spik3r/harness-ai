# Shared brief for PRD-020 subagents (read fully before starting)

You are one subagent in an orchestrated run. An orchestrator verifies your output after you finish. It checks the files, the diff and the tests, so report only what you actually did and saw.

## Repository and branch
- Repo: `G:\coding\harness-ai`. Branch: `epic/PRD-020-provider-registry`. It is checked out. **Never** switch or create branches, push, merge, rebase, amend or force anything. **Never run `git checkout <branch>` or `git switch`, not even to read another PRD's files**: read them from the working tree, or with `git show <ref>:<path>`. (Learned during story creation: a checkout to another branch left the tree on `main` and a commit landed there.) Run `git branch --show-current` before you commit; it must print `epic/PRD-020-provider-registry`.
- PRD: `.agents/PRDs/PRD-020-provider-registry/PRD.md`. Stories: `.agents/stories/PRD-020-provider-registry/`. Board: `.agents/PRDs/PRD-020-provider-registry/index.md`.
- Today's date for every `created` / `updated` / `completed` field: **2026-11-18**.

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
- Pre-existing failures (from the orchestrator's baseline, CI run 44236342646 on `main` @ 3a41985, green): none.

## Commits (implement subagent)
- Stage files explicitly; never `git add -A` / `git add .`. Never `--no-verify`; if a hook fails, fix the cause and make a new commit. Never push: the orchestrator pushes after it verifies the story.
- End every commit message with the `Co-Authored-By:` attribution line from your own session's instructions (it names the model that wrote the commit, e.g. `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`).
- Order: commit code + tests + archived plan + report (with `commit: pending`) as `<type>(PRD-020): {STORY-ID} <summary>`. Capture the SHA. Then make one small follow-up `chore(PRD-020): {STORY-ID} report; update status + index` that fills the SHA into the report and story frontmatter.

## Editing files
- Use the Edit/Write tools for code. Git Bash heredocs on this machine mangle `\\` escapes inside Python edit scripts.

## Regenerating index.md
After any story frontmatter change, run from the repo root:
`PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-020`
It must print `errors: none`.

## Code conventions (non-negotiable)
- Match the surrounding code: comment density, docstring style (they cite PRD sections and decisions, e.g. "PRD-020 D7"), naming, frozen dataclasses for config models, closed vocabularies, and error messages that name the file, the node and the rule.
- Every modified pre-existing test assertion gets a comment citing PRD-020 and the decision.
- Do not implement work that belongs to a later story. If the story text conflicts with the PRD or the real code, follow the code's reality, document the deviation in the plan or report, and tell the orchestrator.
- **No file, no change (D1).** Without `PROVIDERS_FILE` every byte the harness sends upstream and returns to clients is today's. `tests/fixtures/prd020_legacy/` (STORY-001) pins it; never edit those fixtures to make a test pass — report it instead.
- **Legacy mode reads settings live (OD1).** The suite monkeypatches `settings.MODEL_ALLOWLIST`, `V1_TOOL_MODELS`, `OPENROUTER_BASE_URL`, `OPENROUTER_API_KEY`, `OPENROUTER_TIMEOUT_SECONDS` per test. With no file loaded, the registry derives the implicit `openrouter` provider from the current settings on each access (memoizing on those values is fine). The immutable snapshot exists only in file mode.
- **File-mode tests use `tests/_providers.py`** (OD2, from STORY-003): it writes a registry YAML under `tmp_path`, loads it, and restores legacy mode on teardown, also on failure. Never leave a file-mode registry loaded after a test.
- **Keys never leak (T1, T6).** A key value never appears in a repr, log line, exception message, audit row or fixture. Validator messages quote scheme and host only, never a whole URL. Key dataclass fields use `field(repr=False)`.
- **Pure modules**: `provider_registry` resolution (after `load()`), `usage_estimate` and `upstream.collect` do no I/O and import no HTTP client.
- **`openrouter_client.py` is an alias-only shim after STORY-005**; nothing new imports it. Existing imports and injected `call_openrouter` stubs with signature `(messages, model, api_key, **kw)` keep working (D12).
- **No new runtime dependency** in `requirements.txt`. No LiteLLM, no tokenizer.
- **Census guards**: a new public function in `app/db/database.py`, or any new caller of `get_connection()` / `_session()` there, must be registered in `tests/test_db_resilience_retry.py` (`_EXPECTED_KINDS` or `_EXEMPT`, and the caller sets in `test_nothing_opens_a_session_outside_the_unit_and_the_boot_path`). Run that file when you touch `database.py`.
- **Registry API (STORY-003, `app/services/provider_registry.py`)**: `current() -> Registry` (file snapshot, or the legacy registry derived live from settings), `api_key_for(provider)` (legacy: `settings.OPENROUTER_API_KEY or None` at call time; file: resolved at load, None = keyless), `classify_base_url(url)`, `load()`, `reset()`. `Registry(default_model, providers, models_by_id, passthrough_provider, is_legacy)`; `Provider`/`CatalogModel`/`Capabilities` are frozen and hold no key. Build on these; do not duplicate them. File-mode tests use `tests/_providers.py`.
- Tests that start stubs or servers use free ports picked at runtime, deadline loops instead of bare `sleep`, and stop every child on teardown. They must work on Windows (local) and Linux (CI).
- **Upstream API (STORY-005, `app/services/upstream/`)**: `call_upstream` (call_openrouter's signature; resolves the route, D10 key choice, returns `model_used` = the requested id), `UpstreamError`/`UpstreamResult`/`UpstreamRequest` in `upstream/types.py`, params in `upstream/params.py`, `OpenAICompatibleAdapter(provider, client).complete(request, api_key)`. `openrouter_client.py` is aliases only; app modules import the package under their old names (`call_openrouter`, `OpenRouterError`, …) so test monkeypatch targets keep working. A **pure** module (e.g. `v1_translate.py`, purity tests on the AST) imports `upstream.params` / `upstream.types`, never the package (its `__init__` pulls httpx and the registry).
- **Targeted runs on this machine**: run them in the foreground, in small sequential batches (`tests/test_db.py` alone; it takes ~12 min — split with `-k` if needed). A run killed for memory (exit 137, no output) is environmental: report it, do not loop. If `harness-libsql-dev` is unreachable and `docker` cannot reach the engine, Docker Desktop is down: report it, do not start it yourself.

## What to return (your final message, at most ~30 lines)
- PLAN subagent: the plan path, a 3–5 line summary, the files to CREATE/UPDATE, one line per AC saying how it is covered, open risks/questions, and confirmation that the story frontmatter (`plan`, `status: in-progress`) and the index were updated.
- IMPLEMENT subagent: the commit SHA(s), the files changed, the exact targeted test counts, each AC with pass/fail and the test that proves it, deviations, and anything left undone. If something failed or you stopped early, say so plainly. Do not report success you did not verify.

## Checkpoint
- Done and pushed: 001 (130bbee), 002 (6586c45), 003 (5dc69fe), 004 (acc101e), 005 (6015bab upstream package + adapter; fix 4756605 purity), 006 (581f7af five audit columns). Next: STORY-007 (pipeline routing + BYOK + per-row provider audit, large, CRITICAL), then 008, 009, 010.
- CI: run 44298089117 at ffa6090 failed only `test_v1_translate_request.py::test_is_pure` (STORY-005 carried-over, fixed in 4756605). The run at 5a83e04 (STORY-006 + fix) is the one to read on resume; `tests/test_db.py` was not re-run in full locally after 006's last two assertion fixes, so check it there. Pre-existing failures: none.
- Orchestrator decisions: OD1 legacy live settings; OD2 `tests/_providers.py`, no 2nd CI job; OD3 passthrough only for wildcard roles; OD4 key_env from os.environ then `.env`; OD5 O1–O8 as proposed; OD6 D9 estimate; roles validated against RBAC (PRD F1 amended); per-model commit trailer. 005: extra `upstream/types.py`; stub gained `redirect_status`/`location` and in-process `require_key`; `model_used` restored to the requested id. 006: columns at the table tail (after `write_id`); `log_query` takes the five before `journal_decisions`.
- STORY-007 design points to give: audit `provider`/`upstream_model`/`provider_trust` from the `Route` (not the result; `model_used` stays the requested id), also on the upstream-error arm; NULL on step 0–2 rows and denials; D10 verdict label `query:byok:{provider}` when BYOK is sent for a `byok: false` provider; legacy rows/verdicts byte-identical (STORY-001 fixtures green, unedited).
- STORY-009 must know: `"usage": null` raises a bare `TypeError` in `openai_compatible.complete` today (story note added).
- STORY-011 must know: legacy allowlist de-dup (story note); `supports_tools` differs from the v1 rule only for a V1_TOOL_MODELS id outside MODEL_ALLOWLIST.
- STORY-014: decided by the user — `http://localhost:1235/v1`, `google/gemma-4-e4b` (story note added).
- Planner escalations: none. Plans corrected at 3.2: 001, 003. Over 12 KB accepted: 001, 003, 005 (15.6 KB).
- For Phase 6: story-creation run left the tree on `main` (d14f97c moved to the epic branch, local main restored before any push). `.gitattributes` gained `tests/fixtures/prd020_legacy/** -text`. Mid-run (006) a pytest was killed for memory (user's llama-server held 17 GB) and Docker Desktop was down; the orchestrator started Docker Desktop and `harness-libsql-dev`.
