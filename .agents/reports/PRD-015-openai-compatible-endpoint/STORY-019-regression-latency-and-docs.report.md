---
story: STORY-019
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-019-regression-latency-and-docs.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: d294e59
status: COMPLETE
completed: 2026-10-30
---

# Implementation Report — STORY-019: Regression sweep, translation latency, README API reference and per-client setup, .env.example

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-019-regression-latency-and-docs.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `d294e59`

## Summary

This is the last story of PRD-015. No file under `app/` changed.

- **Measurement.** `scripts/measure_v1_latency.py` sends the same one-turn conversation through `POST /query` and `POST /v1/chat/completions` in an in-process `TestClient(app)`, so the lifespan, real bearer auth and the real pipeline all run. The real `call_openrouter` calls the stub upstream (`scripts/stub_openrouter.make_server`, port 0, loopback HTTP), and the audit rows are written to the local libSQL. The two arms are interleaved. A third arm times only the translation. The script asserts nothing.
  - **Translation p95: 0.05 ms, which meets the PRD's 10 ms target.**
  - End to end, `/v1` adds +2.17 ms at p95 and −1.90 ms at p50 over `/query`, with PII off. That is inside the jitter of the five database statements both doors make.
- **README.** It now describes `/v1` as shipped: the section moved from Roadmap > Planned to Features, and it covers per-client setup, what `/v1` does not do, operations, cost, the API Reference, `ignored_params` in `/audit`, and opt-in client E2E. The Pattern policy, PII, Usage limits, `/stats` and Environment Variables sections were brought up to date.
- **`.env.example`** documents the three new settings, each pinned by a test.
- **Regression sweep.** Green before and after. The only assertion changes in scope are STORY-008's.
- **PRD closure.** The PRD is `done` and pre-PRD Milestone 1 is reached.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Baseline sweep, plus an audit of assertion changes on the epic | none | ✅ |
| 2 | `/query` vs `/v1` latency script | `scripts/measure_v1_latency.py` | ✅ |
| 3 | Tests for the script | `tests/test_measure_v1_latency.py` | ✅ |
| 4 | Register the in-process db tests | `tests/conftest.py`, `scripts/test-db-in-network.sh`, `tests/test_db_in_network_script.py` | ✅ |
| 5 | Take the measurement (50 runs, PII off and on) | none (README + this report) | ✅ |
| 6 | `.env.example` | `.env.example` | ✅ |
| 6b | Pin it | `tests/test_config.py` | ✅ |
| 7 | README | `README.md` | ✅ |
| 8 | Close the PRD | `pre-prds/README.md`, `PRD.md`, `index.md`, story | ✅ |
| 9 | Final sweep | none | ✅ |

## Regression sweep (AC 1)

Both legs ran on the epic before any change (baseline) and on the finished tree (final). Command: `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -m pytest tests/ ...` under a `SetThreadExecutionState` keep-awake wrapper.

| Run | Database | Baseline | Final |
|---|---|---|---|
| `-m "not db"` | none: `HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9` (dead port) and no libSQL container running | 3,508 passed / 62 skipped, 93 s | 3,527 passed / 62 skipped, 97 s |
| full | throwaway `ghcr.io/tursodatabase/libsql-server:latest` on `:8086` | 4,932 passed / 63 skipped, 338 s | 4,953 passed / 63 skipped, 635 s |

- **Deltas.** The final not-db leg has +19 tests: 16 non-db tests in `test_measure_v1_latency.py` and 3 in `test_config.py`. The full leg has +21: all 18 new script tests and the 3 config tests.
- **No flakes.** Neither final log has a `libsql verdict` line, because no `db` test failed.
- **Why the final full run took 635 s.** It ran while the README E2E below used a separate libSQL (`:8087`), a stub and uvicorn on the same host.

**Pre-existing assertions changed on the epic.** Checked with `git diff -U0 $(git merge-base main HEAD) HEAD -- tests/`, reading every removed line:

- **The suites the AC names have no change at all:** `test_query_outcomes_regression.py`, `test_chat_outcomes_regression.py`, the console suites (`test_admin_*.py`, `test_register.py`, `test_usage_view.py`, `test_reports_*.py`) and `test_v1_query_isolation.py`.
- **STORY-008's changes are exactly the ones its report lists:** `test_pattern_profiles.py` (the `code`/`assistant` cell, and the exact-map assertion) and `test_pattern_config.py` (`test_the_built_in_profiles_carry_the_section_6_4_matrix`).
- **Other removed lines on the epic are outside the AC's suites**, and each is its own story's deliberate schema or client change:
  - `test_db.py`: column counts and order, from STORY-007's `ignored_params` column.
  - `test_openrouter_client.py`: field list; `test_pipeline_concurrency.py`: `_API_URL` became the base URL. Both STORY-002.
  - `test_query_pipeline_audit_fields.py`, `test_query_pipeline_break_glass.py`: STORY-007 and -009 scans.
  - `test_pii_redaction_integration.py`: the untouched-file list, STORY-009.
  - `conftest.py`: the `--run-e2e` option, STORY-015.
- **This story changed one pre-existing assertion:** `test_db_in_network_script.py`'s deselect count, 3 → 5 (see Deviations).

## Latency measurement (AC 2)

The command was `python scripts/measure_v1_latency.py --runs 50 --database-url http://127.0.0.1:8087` (throwaway libSQL), then the same with `--pii on`. The host was `cocacola`, Windows, Python 3.11.17. The model was `gpt-4`, the first `MODEL_ALLOWLIST` entry. Each arm got 1 discarded warm-up, and query/v1 alternated order every run.

| PII | arm | n | min ms | p50 ms | p95 ms |
|---|---|---|---|---|---|
| off | query | 50 | 33.06 | 39.80 | 58.69 |
| off | v1 | 50 | 33.11 | 37.90 | 60.85 |
| off | translate | 50 | 0.01 | 0.02 | 0.05 |
| on | query | 50 | 42.11 | 48.80 | 70.27 |
| on | v1 | 50 | 34.14 | 37.19 | 58.33 |
| on | translate | 50 | 0.02 | 0.02 | 0.02 |

- **PII off** (the reported figure): added p95 +2.17 ms and p50 −1.90 ms. **Translation p95 is 0.05 ms, so the target is met.** The end-to-end added p95 is within 10 ms.
- **PII on**: `/v1` is 11.6 ms faster at p50 and 11.9 ms faster at p95, because `code` doesn't run the named-entity model and `chat` does. This is why PII is off for the comparison.
- **Where the end-to-end difference lives** (a scratchpad probe, not committed):
  - Each request on either door issues the same 5 statements: `SELECT * FROM` (users), `INSERT INTO usage_daily`, `SELECT timestamp FROM`, `UPDATE usage_daily SET`, `INSERT INTO audit_logs`.
  - Over 20 interleaved runs, the p50 for the whole HTTP request was 39.6 ms on `/query` and 43.9 ms on `/v1`. The pipeline call alone was 35.9 ms and 40.0 ms.
  - So in that sample the gap was inside the pipeline, not in routing or translation. In the 50-run measurement the p50 gap reversed sign. Both readings are noise around a shared database round-trip cost.
  - A first 3-run smoke showed +20 ms at p50, which was also noise. It is why the probe was run.
- **No remote Turso endpoint** is available on this machine, so no remote figure was taken.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`TestClient(app)` lifespan in the bench, every app test) | ✅ |
| Frontend lint | n/a (no frontend change) |
| Tests | ✅ 4,953 passed / 63 skipped (full); 3,527 / 62 (`-m "not db"`, Docker-free) |
| New tests | ✅ `test_measure_v1_latency.py` 18/18 against libSQL; 16/16 non-db with a dead DB URL; `test_config.py` 202/202 |
| README anchors | ✅ 95 in-page links, 53 headings, 0 broken, 0 duplicate (scratchpad checker; the same checker on `HEAD`'s README: 82/82, 0 broken) |
| README stale-wording sweep | ✅ every remaining hit of `PRD-014`, "reachable by tests only" and the like is intended (see Task 7 below) |
| E2E | ✅ 5/5 |

## E2E (plan's checklist)

- [x] **The 50-run measurement.** `measure_v1_latency.py --runs 50` exited 0 with three arms and both verdict lines. The figures above are copied verbatim into the README.
- [x] **Remote URL refused.** `measure_v1_latency.py --database-url https://example.turso.io` with an empty `TURSO_AUTH_TOKEN` exited 1 with "Refusing to write to a non-local database ...". There was no traceback.
- [x] **Bench users and rows.** `manage_users.py list-users` on `:8087` shows every `story019-bench-*` user inactive, with rate `1000000000`. Each 50-run user wrote 102 rows: 51 `(query, chat, streamed=False, success=True)` and 51 `(v1, code, False, True)`.
- [x] **README OpenAI SDK snippet, run as written.** Setup: `scripts/stub_openrouter.py --port 9100 --script tests/e2e/scripts/example.json`, then uvicorn on `:8765` with `OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1` and `DATABASE_URL=:8087`. The snippet ran on `openai` 3.40.0 with only the port and token substituted:
  - `answer.model_extra["harness"]` returned `{'audit_id': 207, ...}`, equal to the id suffix. STORY-015 had not exercised `model_extra`, so this verifies the README's claim.
  - The stream reassembled with `usage` set.
  - An injection prompt raised `BadRequestError` with `code == "suspicious_pattern"` after exactly **1** HTTP request (default `max_retries`), counted by an httpx event hook.
  - The Aider and Continue setups were not rerun. They are the STORY-016/017 commands and files, quoted from those reports.
- [x] **`curl` checks.** `curl -H "Authorization: Bearer <token>" localhost:8765/v1/models` matches the README's shape. Without a token the answer is `401` with `x-should-retry: false` and `"code":"invalid_api_key"`. `/health` returned `{"status":"ok"}`. Both servers were stopped, and ports 8765/9100 were confirmed closed (no orphan).

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `scripts/measure_v1_latency.py` | CREATE | +492 |
| `tests/test_measure_v1_latency.py` | CREATE | +206 |
| `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-019-regression-latency-and-docs.plan.md` | CREATE (archived) | +375 |
| `README.md` | UPDATE | +289/-47 |
| `.env.example` | UPDATE | +17 |
| `tests/test_config.py` | UPDATE | +37 |
| `tests/conftest.py` | UPDATE | +4 |
| `scripts/test-db-in-network.sh` | UPDATE | +6/-4 |
| `tests/test_db_in_network_script.py` | UPDATE | +1/-1 |
| `pre-prds/README.md` | UPDATE | +1/-1 |
| `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` | UPDATE | `status: done` (chore commit) |
| `.agents/PRDs/PRD-015-openai-compatible-endpoint/index.md` | UPDATE | regenerated (chore commit) |
| `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-019-regression-latency-and-docs.md` | UPDATE | `done`, plan/report/commit (chore commit) |

## README changes (Task 7)

- **Solution and Architecture.** The coding-agent / OpenAI SDK client now joins the same pipeline in the diagram through `POST /v1/*`.
- **Features table.**
  - New **OpenAI-compatible endpoint** row.
  - **Single entry point** now names both doors.
  - **Prompt-injection blocking** names the `assistant` flag.
  - **PII redaction** says `code` is reached through `/v1`.
- **New `### OpenAI-compatible endpoint` under Features.** It covers:
  - the translation-layer model;
  - errors as ordinary `400`/`403` with `x-should-retry`;
  - buffered SSE;
  - parameter classification and `ignored_params`;
  - **what `/v1` does not do**: tools, real streaming, BYOK, aliasing, the admin wildcard in `/v1/models`, break-glass, `n` / `logprobs` / JSON mode / images.
- **`#### Per-client setup`.**
  - **OpenAI SDK 3.40.0.** The snippet was run for this report.
  - **Aider 0.86.2.** `--model openai/openai/gpt-4o` and why. The `.aider.model.settings.yml` autoload. Two requests per `--message`. **Every `403` is retried for about 60 s**, while a `400` is sent once.
  - **Continue `cn` 1.5.47.** The `config.yaml` file. `--exclude "*"` is required. `model` is sent verbatim, and 400/403 are not retried. `cn` loads `.env` from its cwd. The VS Code extension is not verified.
  - `X-Harness-Device`.
- **`#### Operating it`.**
  - `V1_ENABLED`.
  - Caddy routes `/v1/*`, and gzip flushes SSE: keep-alives arrived at 10/20/30 s on Caddy v2.11.7 (STORY-018).
  - A queued streamed request gets no bytes before commit (STORY-018 finding).
  - A disconnect does not cancel the pipeline.
- **What it costs.** The figures above, with met/missed stated and the command.
- **PRD-014 note.** One sentence says earlier documents call this PRD "PRD-014".
- **Pattern policy.**
  - The `code` row now has `assistant` **flag** (D9), with the rationale.
  - The "reachable by tests only" sentence now applies only to the `tool` flag, which is still unreachable.
  - PRD numbers fixed: Action policy is the PRE-PRD-015 brief, tool calling the PRE-PRD-016 brief.
- **PII redaction.**
  - `/v1` runs `code`.
  - "Direct call only" is replaced with the shipped state.
  - New **rollout note** pointing at [PRD-012 D5-placeholders](../../PRDs/PRD-012-pii-for-code/decisions/D5-placeholders.md), with its measured 3/9 vs 9/9 result and the mitigations D5 lists.
- **Usage limits.**
  - Break-glass on `/v1` is `403 break_glass_not_permitted`, and the `/query` sentence after it is now scoped to `/query`.
  - `/v1`'s `403 usage_limit_exceeded`, never `429`.
- **Environment Variables.**
  - New rows: `OPENROUTER_BASE_URL` (with the T10 sentence), `V1_ENABLED`, `V1_SSE_KEEPALIVE_SECONDS`.
  - `ADMIN_TOKEN` row: "PRD-014 will add" replaced.
- **API Reference.**
  - `POST /v1/chat/completions`: success, streamed and errors. The errors table has all 20 rows, built from `v1_translate.py`'s constants and `_VERDICTS` / `_FAULTS`, plus `v1.py`'s `_HTTP_ERRORS`.
  - Notes on the retry rule, `message`, `param`, which rows are written, and the `/v1` 404/405.
  - `GET /v1/models` and `GET /v1/models/{id}`.
- **`GET /audit`.** `ignored_params` was added to the example and explained. The `ingress` row ("once it exists") and the `streamed` row ("always false until") are corrected.
- **`GET /stats`.** Two "no ingress runs `code`" / "no `tool` traffic" sentences corrected.
- **Running Tests.**
  - The in-network deselect sentence (three → five).
  - New opt-in **client end-to-end** paragraph and table: `HARNESS_E2E_LIBSQL_URL`, `HARNESS_E2E_AIDER`, `HARNESS_E2E_CONTINUE`, `HARNESS_E2E_DOCKER`. It notes that the Docker smoke skips rather than fails.
- **Troubleshooting.** The break-glass entry now covers `/v1`. New entries for `tools_not_supported` (Continue) and "the last message must be a user turn" (Aider).
- **Roadmap.**
  - The endpoint moved to Shipped.
  - The Planned item became "Tool calling on `/v1`".
  - The old future-tense `### OpenAI-compatible endpoint` subsection is deleted.
  - "The only ingress that exists today is `POST /query`" is corrected.

**Verified against the code, not only the PRD.**

- Every error `code`, status and `type`.
- `owned_by` (`partition("/")`).
- The `max_tokens` / `max_completion_tokens` conflict (`invalid_parameter`).
- Upstream 429 as `upstream_unavailable` (`_classify_http_error`).
- 404/405 under `/v1/` as `not_found` / `method_not_allowed`.
- Schema failures as `400 invalid_request` with `param`.
- The SSE framing (`KEEPALIVE`, `DONE`, `completion_events`).

**Where the shipped code differs from the PRD.**

- `resets_at` is `YYYY-MM-DDTHH:MM:SSZ`, not the PRD example's `YYYY-MM-DD 00:00:00`. The README example uses the shipped format.
- The PRD's Section 7.5 table has no 404/405 rows. The README documents the shipped `not_found` / `method_not_allowed`.

## Deviations from Plan

1. **No ToC entries were added.** The README's Table of Contents lists `##` sections only. The new section is a `###` under Features, the same level as Usage limits, and the API Reference entries are `###` under an `##` that is already listed. Adding them would break the ToC's convention. The plan's anchor requirement is met by the anchor check instead.
2. **A pre-existing assertion changed outside the AC's suites.** `tests/test_db_in_network_script.py::test_every_deselected_test_exists_and_is_a_db_test` pinned `len(nodeids) == 3`; it is now `5`. The new script refuses non-localhost hosts, as the usage script does, so its two in-process db tests must be deselected in-network. The plan said to deselect them but missed that this count pins the list.
3. **The stub's base URL is assigned to `settings` after it binds, not set in the bootstrap.** This was planned but is worth stating: importing the script starts no thread and no socket. A test pins this (`threading.active_count() == 1` in a fresh interpreter).
4. **Short-run test: the bench user id comes from the script's output.** The plan's "before/after" set difference doesn't work, because the suite resets each db test's database to an empty schema before `init_db()` runs.
5. **The PRD's `status` is `done`.** The workflow allows `draft | active | done | archived`, and the story asks for it. PRDs 010–014 still say `draft` (or `in-progress`) in frontmatter though their boards are done. That is pre-existing and was not touched here.
6. **Extra README fixes not in the plan, found while sweeping:**
  - the Architecture diagram and Solution sentence;
  - `/stats` and `/audit` "until it exists" sentences;
  - two Troubleshooting entries;
  - the PII rollout note rewritten to D5's measured result after reading the decision record.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_measure_v1_latency.py` | `test_importing_the_script_opens_no_connection_and_starts_no_stub`; `test_p95_is_nearest_rank` ×3; `test_the_guard_passes_a_local_endpoint` ×2; `test_the_guard_refuses_a_remote_endpoint_unless_allowed`; `test_run_as_a_program_a_remote_endpoint_is_refused_before_settings_load`; `test_zero_runs_is_refused`; `test_a_miss_against_the_target_is_printed_as_a_miss` ×3 (9.99 MET, 10.0 / 250 MISSED); `test_the_end_to_end_line_says_within_or_over` ×2; `test_a_negative_difference_keeps_its_sign`; `test_the_report_is_ascii`; **db**: `test_a_short_run_reports_every_arm_and_deactivates_the_bench_user` (three arms with n=3, both verdicts, user inactive, 8 rows: 4 `query/chat` + 4 `v1/code`, all success, none streamed); `test_a_blocked_request_ends_the_run_without_a_report` (a duplicate on `/v1` gives exit 1, the reason on stderr, no report, and the stub port closed) |
| `tests/test_config.py` | `test_env_example_documents_the_v1_vars_with_a_comment_in_field_order`; `test_env_example_v1_defaults_match_settings`; `test_env_example_base_url_comment_states_the_t10_rule` |

## Follow-ups (not done here)

- **Stale config comments.** `app/config.py:358-360` still says of the `V1_*` settings "Nothing reads these yet -- each field names the story that becomes its consumer". This story changes no `app/` file, so a later cleanup should fix it.
- **Merge.** PRD-015 is done on the epic branch and not yet merged to `main`. The `pre-prds/README.md` milestone line says so.

## Acceptance Criteria

- [x] Given the full suite (`-m "not db"` without Docker, then with the libSQL container), when it runs, then the `/query` outcome regression, chat UI regression, console suites and `tests/test_v1_query_isolation.py` pass with no pre-existing assertion changed except those listed in STORY-008's report.
- [x] Given a measurement script run against the stub upstream (50 runs, the same conversation via `/query` and via `/v1`), when it reports, then `/v1`'s added p95 overhead is recorded in the README; under 10 ms meets the PRD target, and a miss is recorded as such, not hidden. (Translation p95 0.05 ms: met. End to end +2.17 ms. A miss prints as `MISSED`, as pinned by a test.)
- [x] Given the README, when it is read, then "OpenAI-compatible endpoint" has moved from Roadmap > Planned to Features; the API Reference has `POST /v1/chat/completions` (success, streamed, every error code in PRD Section 7.5), `GET /v1/models`; per-client setup for the OpenAI SDK, Aider and Continue uses the settings proven in STORIES 015–017; and the "what `/v1` does not do" list (tools, real streaming, BYOK, aliasing, the admin wildcard in `/v1/models`) is stated plainly.
- [x] Given the README sections that say `code` or the `assistant`/`tool` flag are "reachable by tests only" or that `/v1` "will" exist (Pattern policy, PII redaction, Usage limits), when read, then they describe the shipped state, including `assistant: flag` (D9).
- [x] Given `.env.example`, when read, then `OPENROUTER_BASE_URL`, `V1_ENABLED` and `V1_SSE_KEEPALIVE_SECONDS` are present with defaults and one-line explanations, and `OPENROUTER_BASE_URL` notes the T10 rule.
- [x] All tasks completed
- [x] Backend server starts without error
- [x] Follows existing patterns
