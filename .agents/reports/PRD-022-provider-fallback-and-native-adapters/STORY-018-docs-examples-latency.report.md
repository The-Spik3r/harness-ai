---
story: STORY-018
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-018-docs-examples-latency.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: cf9349a
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report - STORY-018: Docs, examples, latency check, PRD done

**Plan**: `.agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-018-docs-examples-latency.plan.md`
**Epic Branch**: `epic/PRD-022-provider-fallback-and-native-adapters`
**Commit**: `cf9349a`

## Summary

Docs and examples only (no `app/` or `chat_ui/` change). `examples/providers.yaml` gains an `anthropic-direct` provider and `examples/chains.yaml` F3's first chain. `docs/features.md` has a new `### Provider fallback and Anthropic` section (as built, including the PRD amendments); `docs/api.md`, `docs/deployment.md`, `docs/roadmap.md`, `README.md` and `.env.example` are updated. Latency was measured against `main@6ad98d3` and HEAD.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Example provider and chain | `examples/providers.yaml`, `examples/chains.yaml` | done |
| 2 | Docs | `docs/features.md`, `docs/api.md`, `docs/deployment.md`, `docs/roadmap.md`, `README.md`, `.env.example` | done |
| 3 | Run the doc examples | scratchpad script (not committed) | done, see below |
| 4 | Latency | no file (script not edited) | done, see below |
| 5 | Docs tests | `tests/test_chain_config.py`, `tests/test_providers_docs.py` | done |
| 6 | Close the PRD | PRD frontmatter, story, index | in the chore commit |

## Doc examples that were run (Task 3)

A throwaway script (`scratchpad/doc_examples.py`, not committed) started the two stubs (`scripts/stub_openrouter.py`, chat mode as OpenRouter and Messages mode as Anthropic, scripts from `tests/e2e/scripts/failover_*.json`) and a real `uvicorn app.main:app` with the STORY-017 registry/chains, against the dev libSQL on :8080, using `httpx`. Responses pasted into the docs were produced by it:

- `POST /v1/chat/completions` fallback: 200, `X-Harness-Provider: anthropic-direct`, `harness.provider`, `harness.attempts: 2` (api.md success section).
- `GET /audit?request_id=`: two rows, attempt 1 (`openrouter`) and attempt 2 (`anthropic-direct`, `fallback_reason: status_503`, `cache_*_tokens: 0`); the new audit fields in api.md come from it.
- Breaker open: 200 with `attempts: 1` (OpenRouter skipped).
- Exhaustion: 502 `upstream_unavailable`, `retry-after: 5`, `all providers unavailable`, no `x-should-retry`.
- `GET /providers/status`: both breakers open, counters (`breaker_opens: 2`, `fallback_answers: 5`, `skipped`).
- `GET /stats`: `fallback_answers: 5`, `failed_attempts: 10`, `answers_by_provider`.
- Not re-run (cited from code): the `no provider can serve this request: ...` 502 (`v1_translate.translate_exhausted`; asserted by its unit tests) and the `/query` 502 text.
- YAML blocks: the two blocks of the new features.md section load through `provider_file` + `chains_file` (`test_fallback_section_yaml_blocks_load_through_the_real_loaders`); both example files load through `test_example_file_loads` and `test_example_registry_loads_with_only_the_insecure_http_warning`.

Facts confirmed against code before writing: audit columns `request_id, attempt, route_model, fallback_reason, skipped_providers, cache_read_tokens, cache_write_tokens` (`AUDIT_LOGS_ADDED_COLUMNS`, `app/db/models.py`); `PROVIDER_CHAIN_DEADLINE_SECONDS` default is `None` (the primary's `timeout_seconds`).

## Latency (Task 4, AC3)

`scripts/measure_v1_latency.py --runs 200 --pii off`, three alternating baseline/HEAD pairs, run one at a time with no pytest running, `PROVIDER_CHAINS_FILE` empty in both. Baseline: detached worktree of `6ad98d3` (main with PRD-021), same repo `.venv`, the repo `.env` copied in so both trees saw the same settings; confirmed `app.__file__` resolved inside the worktree; removed afterwards, `git worktree list` shows only the repo. libSQL dev server at http://127.0.0.1:8080.

| Run | query p95 ms | v1 p95 ms | translate p95 ms |
|---|---|---|---|
| base 1 | 830.08 | 841.18 | 0.08 |
| HEAD 1 | 840.20 | 820.11 | 0.06 |
| base 2 | 841.31 | 841.28 | 0.08 |
| HEAD 2 | 818.77 | 818.91 | 0.05 |
| base 3 | 819.35 | 818.92 | 0.05 |
| HEAD 3 | 814.48 | 818.56 | 0.06 |

Medians of the three p95s: query base 830.08 / HEAD 818.77 (-11.31 ms); v1 base 841.18 / HEAD 818.91 (-22.27 ms); translate base 0.08 / HEAD 0.06 (-0.02 ms). Per-pair query deltas: +10.12, -22.54, -4.87 ms.

**Verdict: not resolvable.** Every request took about 760 ms on this host (p50 754-775 ms; the five database round trips dominate) and the p95 of the same tree moved by up to 22 ms between runs, about forty times the 0.5 ms bound. No regression is visible and the deltas are noise in both directions. The DB-free translation p95 (0.06 ms HEAD vs 0.08 ms baseline) shows the pure `/v1` work did not grow, but it does not include the chain code, which is inactive with no chains. A claim of "< 0.5 ms added end to end" is NOT made; features.md says so.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| `tests/test_providers_docs.py tests/test_chain_config.py` | 63 passed |
| `tests/test_config.py tests/test_measure_v1_latency.py tests/test_two_instance_smoke.py` | 314 passed + 1 error on the first run (`test_two_instance_smoke` DB fixture error, with `-x`); `tests/test_two_instance_smoke.py` alone: 16 passed. Treated as a DB-server hiccup, not code (no `app/` file changed) |
| Full suite | GitHub CI on push (user decision) |
| E2E | the Task 3 run above |

## Files Changed

| File | Action |
|------|--------|
| `examples/providers.yaml`, `examples/chains.yaml` | UPDATE |
| `docs/features.md`, `docs/api.md`, `docs/deployment.md`, `docs/roadmap.md`, `README.md`, `.env.example` | UPDATE |
| `tests/test_chain_config.py`, `tests/test_providers_docs.py` | UPDATE |

## Deviations from Plan

- Docs follow the code where the PRD text differs: a `401` from any provider and a `403` from an Anthropic provider are `misconfigured` and DO fall back (breaker 300 s); an `openai_compatible` `403` does not. The STORY-001 "Not verified" table says the Bearer-auth `401` is a "non-fallback auth error"; the code makes it fall back, so the limitation is worded that way.
- `.env.example` gets a comment about `ANTHROPIC_API_KEY`, not a `KEY=` line: it is not a `Settings` field and `test_documented_settings_exist_in_config` would fail.
- Doc examples were produced by a real `uvicorn` plus stubs (STORY-017's setup) rather than `TestClient`, because the failover path needs the Anthropic stub and breaker state in one process.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_chain_config.py` | `test_example_file_loads` extended: new chain order, no opt-in, `anthropic-direct` is `type: anthropic` |
| `tests/test_providers_docs.py` | exact-set assertion now 4 providers (approved); new `test_fallback_section_yaml_blocks_load_through_the_real_loaders`, `test_fallback_docs_name_the_settings_surfaces_and_limits` |

## Acceptance Criteria

- [x] AC1 examples extended and loaded by the real loaders (`test_example_file_loads`, `test_example_registry_loads_with_only_the_insecure_http_warning`)
- [x] AC2 docs cover every listed item; examples run (see above; new docs tests)
- [ ] AC3 latency < 0.5 ms: measured and recorded, NOT resolvable below DB jitter (stated plainly above)
- [x] AC4 PRD closed (in the chore commit: PRD `status: done`, all stories `done`, `gen_index.py` `errors: none`)
