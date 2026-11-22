---
story: STORY-018
prd: PRD-022
slug: docs-examples-latency
title: Docs, example chains/providers files, latency check, PRD done
type: ENHANCEMENT
complexity: small
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: Docs, examples, latency check, PRD done

## Summary

Docs and examples only; no `app/` or `chat_ui/` change. (1) Extend `examples/providers.yaml` with an `anthropic-direct` provider and F3's first chain in `examples/chains.yaml`, and extend the existing example-loading test. (2) Write the PRD-022 doc sections as built. (3) Run `scripts/measure_v1_latency.py` on the tree before PRD-022 and on HEAD and record both. (4) Close the PRD.

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-018-docs-examples-latency.md`
- PRD sections used: 6.2, 6.8, 9.3, F3, F7-F10, 10, 11 "Quality indicators", Phase 4, Appendix "Not verified"
- Systems affected: `examples/`, `docs/`, `README.md`, `.env.example`, 2 tests, PRD/story frontmatter

## Design Decisions

none beyond the tasks (not critical). Docs state what is BUILT (facts verified below), including the PRD amendments.

## Skills In Use

None (`.agents/skills/` has only `frontend-design`; no UI work).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Existing example test | `tests/test_chain_config.py:423-431` (`test_example_file_loads`) | Already loads `examples/providers.yaml` + `chains.yaml` through `provider_file` + `chains_file` (real `provider_registry.load` + `chain_config.load`). EXTEND it; no parallel test |
| Providers example test | `tests/test_providers_docs.py:92-105` | Asserts provider set `== {"openrouter","ollama","gpu-box"}` and exactly 1 warning; must change when `anthropic-direct` is added |
| Docs-as-tests | `tests/test_providers_docs.py:76-90,117-` | Settings named in docs checked against `Settings.model_fields`; every yaml block under `### Providers` loaded through `tests/_providers.py` |
| Doc style | `docs/features.md:411-583` (`### Providers`, `#### What it does not do`), `docs/api.md:324` (`GET /storage/status`), `docs/deployment.md:131` | "What it is / bold warning / table" prose, one section per feature |

## Facts to state, verified in code (cite when writing)

- Provenance on buffered JSON only: `app/routers/v1.py:384-388` (`X-Harness-Provider` set only when `harness.provider is not None`); a stream carries only `model` (PRD F10 amendment).
- Exhaustion: `app/services/v1_translate.py:692-717` (`translate_exhausted`): no attempt and only capability/forbidden/byok skips -> 502 `upstream_error`, message `no provider can serve this request: <sorted reasons>`, `x-should-retry: false` (`v1.py:281`); else 502 `upstream_unavailable` "all providers unavailable" + `retry-after` only when `retry_after_seconds` is not None (`v1.py:282-284`), no `x-should-retry`. Call site `v1.py:357`. `/query`: 502 `all providers unavailable`.
- Breaker: `app/services/upstream/health.py:42-47` (threshold 5, open 10 s, misconfigured 300 s; constants, no setting), per provider, per process (so per instance behind the balancer); 429 uses `max(retry_after, 10)` at `health.py:179`. `last_failure_class` = `UpstreamError.kind` (e.g. `status` for a 503).
- `/providers/status`: `app/routers/admin.py:235`, in the Caddy matcher `Caddyfile:5`; in memory, no DB/network call; `since` never null (PRD amendment); `stats:read`.
- `/stats`: `admin.py:331-333` (`fallback_answers` = answers with attempt > 1, `failed_attempts`, `answers_by_provider`).
- `/audit?request_id=`: `admin.py:50,65`. Columns per PRD F8 (`request_id, attempt, route_model, fallback_reason, skipped_providers, cache_read_tokens, cache_write_tokens`); confirm the names in `AUDIT_LOGS_ADDED_COLUMNS` (`app/db/database.py`) before writing.
- Anthropic fields: `app/services/provider_registry.py:82,88-89,122-123,347` (`default_max_tokens` required for `type: anthropic`; `prompt_cache: off|auto`; capabilities `forced_tool_choice`, `sampling_params`, both default false).
- Non-leading system turn: `app/services/upstream/anthropic.py:97,203` (system turns hoisted to top-level `system`, joined by `\n\n`; a non-leading one loses its position).
- Admin console: Providers view `/admin/providers` (`chat_ui/chat_ui/chat_ui.py:132-133,214`), admin-token gated like Storage; Register `attempt` column and request_id search cover the loaded window only (STORY-016 report).
- Streaming: fallback only before the first release to the client, never after (STORY-014; PRD 6.6, D9).
- Settings rows already exist: `docs/configuration.md:59-62`, `.env.example:92-106` (STORY-009). Verify the four are covered and what `PROVIDER_CHAIN_DEADLINE_SECONDS` defaults to in `app/config.py`; add nothing duplicate.
- "Not verified" items (STORY-001 report, "Unverifiable offline" table, `.agents/reports/PRD-022-provider-fallback-and-native-adapters/STORY-001-foundations-spike.report.md:85-96`): 7 items with safe defaults. Copy them as a "Known limitations" list in features.md.

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `examples/providers.yaml` | UPDATE | Add provider `anthropic-direct` (`type: anthropic`, `base_url: https://api.anthropic.com`, `key_env: ANTHROPIC_API_KEY`, trust external) with model `anthropic-direct/claude-sonnet-4-6` (`upstream: claude-sonnet-4-6`, `default_max_tokens`, `prompt_cache: auto`, capabilities tools/streaming/forced_tool_choice); add `anthropic/claude-sonnet-4.6` under `openrouter` |
| `examples/chains.yaml` | UPDATE | Add F3's first chain `anthropic/claude-sonnet-4.6` -> `anthropic-direct/claude-sonnet-4-6` (external -> external, no opt-in). Keep the two existing chains |
| `tests/test_chain_config.py` | UPDATE | Extend `test_example_file_loads`: env gets `ANTHROPIC_API_KEY`; assert the new chain's candidate order and `anthropic-direct` has type `anthropic` |
| `tests/test_providers_docs.py` | UPDATE | Provider set now 4 names (comment `# PRD-022 STORY-018: anthropic-direct added to the example`), env gets `ANTHROPIC_API_KEY`; single-warning assertion stays. New test: every yaml block in the new features.md section loads through `provider_file` + `chains_file`; docs name the four settings, `X-Harness-Provider`, `request_id` |
| `docs/features.md` | UPDATE | New `### Provider fallback and Anthropic` section after `### Providers`; fix the `:576` bullet ("No native Anthropic ... belong to PRD-022" is now false) |
| `docs/api.md` | UPDATE | New `### GET /providers/status`; `/stats` figures (`:287`); `/audit` columns + `?request_id=` (`:158`); `/v1` errors (`:455+`): exhaustion rows, `retry-after`, success `harness.provider/attempts` + `X-Harness-Provider` (JSON only) |
| `docs/deployment.md` | UPDATE | New `### Provider outages` beside `### What a database outage does` (`:131`): per-process breaker, no setting, `/providers/status` in memory and proxied by Caddy, chains file needs restart, deploy checklist |
| `docs/roadmap.md` | UPDATE | `:30,:34`: tick the second-provider fallback item (PRD-022), fix the "single upstream" sentence |
| `README.md` | UPDATE | `:403` "Next up" paragraph; link the new sections |
| `docs/configuration.md`, `.env.example` | UPDATE only if a gap is found | e.g. an `ANTHROPIC_API_KEY` note |
| PRD.md, story files, `index.md` | UPDATE | Task 6 |

## Tasks

### Task 1: Example files
Edit the two YAMLs (comments in the files' existing style). Validate: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_chain_config.py -k example`.

### Task 2: Docs
Cover every item of AC2: `type: anthropic` fields and capabilities; chain file rules (F3 validation list; trust, capability coverage with `capability_scoped`, BYOK skip, per-candidate RBAC and per-route redaction); eligibility as PRD 6.2's table (as built: `fallback_eligible = retryable or kind == misconfigured`; refusal, other 4xx, `shape`, `incompatible` never fall back); breaker; `/providers/status` example body (PRD Section 10 shape, `since` always a string); `/stats`; audit columns; `/v1` surfaces; the exhaustion table; stream fallback only before first release; system-turn caveat; four settings; "Not verified" limitations. State `PROVIDER_CHAINS_FILE` empty = PRD-020/021 unchanged.

### Task 3: Run every doc example (AC2 "was run")
- YAML blocks: the new `test_providers_docs.py` test loads each through the real loaders (`provider_file` then `chains_file`); the example files through the extended `test_example_file_loads`.
- curl/JSON bodies: a throwaway script in the scratchpad (not committed) using `TestClient(app)` and the stub (`scripts/stub_openrouter.py`, Anthropic mode + scripted faults, as STORY-017's failover E2E test does; find it with `grep -ln "breaker" tests/test_*failover*`) to produce a real `/v1` fallback response, `/providers/status`, `/stats`, `/audit?request_id=` and an exhaustion 502. Paste the real headers and fields into the docs and list what was run in the report. Where STORY-017's test already asserts a shape, cite it instead of re-running.

### Task 4: Latency (AC3)
- Script: `scripts/measure_v1_latency.py` (`--runs N` default 50, `--pii off|on`, `--database-url` default `http://127.0.0.1:8080`, refuses a non-local DB). It NEEDS the libSQL dev server `harness-libsql-dev` on :8080: it drives `TestClient(app)` against an in-process stub, writes real audit rows and creates and deactivates its own bench user. It prints arms `query`, `v1`, `translate` (min/p50/p95) and asserts nothing. Its built-in target is PRD-015's 10 ms, not PRD-022's 0.5 ms.
- No PRD-021 baseline figure is stored in the repo (the only recorded run is PRD-015's: translation p95 0.05 ms, +2.17 ms end to end, `.agents/reports/PRD-015-openai-compatible-endpoint/STORY-019-regression-latency-and-docs.report.md:22-23`). So record a fresh baseline: `git worktree add <scratchpad>/base 6ad98d3` (main with PRD-021 merged; creates no branch, switches nothing; remove it afterwards), run the script from there with the repo `.venv` python (confirm `app.__file__` resolves inside the worktree), then from the repo root on HEAD. `PROVIDER_CHAINS_FILE` empty in both. Same command both: `--runs 200 --pii off`, three alternating pairs. DB jitter (5 round trips, about +-2 ms) exceeds 0.5 ms, so compare medians of the three p95s of the `query` arm and of `translate` (pure, DB-free: the cleaner figure).
- Report: both tables, per-pair deltas, and whether the p95 delta is < 0.5 ms; if noise-limited say so. Do not edit the script. A miss is recorded as a miss. One sentence of the result goes in the features.md section.

### Task 5: Docs tests
`PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_providers_docs.py tests/test_chain_config.py`, plus `tests/test_config.py -k "readme or example or env"` (it reads README/examples at `:643`). Grep `tests/` for other readers of `examples/providers.yaml` or README text and run the hits.

### Task 6: Close the PRD (AC4)
Last, in the follow-up `chore(PRD-022): STORY-018 report; update status + index` commit: STORY-018 frontmatter `status: done`; set `status: done` and `updated: 2026-11-20` in the PRD frontmatter (`.agents/PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md:5`, now `draft`); check `grep -h "^status:" .agents/stories/PRD-022-*/*.md | sort | uniq -c` shows all `done`; run `PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-022` -> `errors: none`.

## End-to-End Tests
- [ ] Task 3's TestClient run reproduces every response shown in the docs.
- [ ] Both example files load through the real loaders (extended `test_example_file_loads`).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_chain_config.py tests/test_providers_docs.py
```
`tests/test_untouched_app.py` only if an `app/` file is touched (it should not be). No test renamed or removed.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 examples + loader test | 1 | `tests/test_chain_config.py::test_example_file_loads` (extended); `tests/test_providers_docs.py::test_example_registry_loads_with_only_the_insecure_http_warning` |
| AC2 docs coverage; examples run | 2, 3, 5 | new yaml-block and required-substring tests in `tests/test_providers_docs.py`; Task 3 run listed in the report |
| AC3 latency < 0.5 ms vs baseline | 4 | recorded numbers in the report (script asserts nothing) |
| AC4 PRD done | 6 | `gen_index.py` prints `errors: none`; PRD frontmatter `status: done` |

## Open risks
- No stored PRD-021 baseline: re-measured in a worktree. The 0.5 ms bound is below DB jitter; expect an indicative result.
- Docs must follow built code, not PRD text (provenance JSON-only, `since` never null); re-check audit column names in `database.py`.
