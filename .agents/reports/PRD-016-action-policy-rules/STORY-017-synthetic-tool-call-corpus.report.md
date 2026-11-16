---
story: STORY-017
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-017-synthetic-tool-call-corpus.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: e67fd27
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-017: Synthetic tool-call corpus, its suite end to end through record(), and evaluate() latency

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-017-synthetic-tool-call-corpus.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `e67fd27`

## Summary

`tests/corpora/actions/synthetic/` holds 70 YAML files, one tool call each: 11 `brief-*`, 32 `rule-*` and 27 `ordinary-*`. They use the OpenCode, Cline 4.x, Cline 3.x and MCP SQL tool names and keys pinned in `tests/corpora/actions/SOURCES.md`. Each file names the policy it runs under (`built_in` or `example`, which is `examples/action_policy.yaml` loaded through the real `action_config.load()`), the decision for `user`, `dba` and `admin`, the reported rule, and optionally `granted_by` and `includes`. `arguments` is the raw JSON string (F12).

`tests/test_action_corpus.py` loads every file at import with `strict_yaml.safe_load`. A malformed file raises `CorpusError("<file>: <node>: <problem>")`, so it fails collection. The module then checks the corpus criteria, every declared decision, rule and `granted_by` per role under a test RBAC matrix (`dba` holding `action:sql:write`), the two-part T11 reason check, a round trip through `record()` and `GET /audit/actions`, and a benchmark-marked `evaluate()` p95. No application code changed.

## `evaluate()` latency (PRD-016 Section 11, quality indicator)

```
STORY-017 evaluate() over 210 calls x 50 rounds: min 0.0666 ms / p50 0.1912 ms / p95 0.4151 ms / max 38.9847 ms
```

**p95 = 0.4151 ms.** That covers 210 (file, role) pairs, each under its own policy, with one warm-up pass and then 50 timed passes, using the nearest-rank p95. The command was `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_corpus.py -m benchmark --run-benchmark -s -q -p no:cacheprovider`, run on the dev machine. No threshold is asserted. The max is a single outlier (GC or first-touch) and is not representative.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | 70 corpus files (generated from the plan's table, then checked: every non-malformed `arguments` parses as JSON) | `tests/corpora/actions/synthetic/*.yaml` | ✅ |
| 2 | Module docstring, env header, constants | `tests/test_action_corpus.py` | ✅ |
| 3 | `_load_example_policy()` (save/restore `ACTION_POLICY_FILE` and `_policy`), `_POLICIES`, autouse `_corpus_matrix` | `tests/test_action_corpus.py` | ✅ |
| 4 | `CorpusError`, `_Case`, `_tool_call`, `_load_case`, `_corpus`, `_SYNTHETIC`, `_SYNTHETIC_BY_NAME`, `_evaluate` | `tests/test_action_corpus.py` | ✅ |
| 5 | Corpus-shape tests (AC 1) | `tests/test_action_corpus.py` | ✅ |
| 6 | Decision tests (AC 2) and the two-part reason check (AC 4) | `tests/test_action_corpus.py` | ✅ |
| 7 | Loader guard tests on `tmp_path` (18 bad documents), plus `test_every_corpus_file_loads` | `tests/test_action_corpus.py` | ✅ |
| 8 | Round trip through `record()` and `GET /audit/actions` (AC 3, `db`) | `tests/test_action_corpus.py` | ✅ |
| 9 | `evaluate()` p95 benchmark (AC 5) | `tests/test_action_corpus.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A (no `frontend/`) |
| `tests/test_action_corpus.py` (the targeted set; no app file changed, so `test_untouched_app.py` is not needed) | ✅ 111 passed, 1 skipped (the benchmark), 0 failed |
| Benchmark run (`-m benchmark --run-benchmark -s`) | ✅ 1 passed, 111 deselected |
| Negative check: `expect: {root: allow, ...}` in `brief-select-scoped.yaml` | ✅ collection error `CorpusError: brief-select-scoped.yaml: expect: 'root' is not one of admin, dba, user` (reverted) |
| Negative check: `rule: sql.write` in the same file | ✅ `test_synthetic_call_decides_as_declared[brief-select-scoped.yaml]` fails, naming the file, role, policy, decision, rule and reason (reverted) |
| AC 4 exemption exercised | ✅ 24 (case, role) reasons echo a configured entry that the call itself sent (for example `registry.npmjs.org`, `ls`, `/home/dev/projects/...`). None echo an entry the call did not send. |
| Full suite | deferred to orchestrator (user decision) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/corpora/actions/synthetic/*.yaml` (70 files) | CREATE | about 10-11 each |
| `tests/test_action_corpus.py` | CREATE | +654 |
| `.agents/PRDs/PRD-016-action-policy-rules/PRD.md` | UPDATE (orchestrator edit, line 632: the `curl \| sh` rule line) | +1/-1 |
| `.agents/stories/PRD-016-action-policy-rules/STORY-020-docs-and-promotion.md` | UPDATE (orchestrator note: Cline deployments need their own `tools:` and `shell.allow`) | +1 |
| `.agents/stories/PRD-016-action-policy-rules/STORY-017-synthetic-tool-call-corpus.md` | UPDATE (frontmatter) | |
| `.agents/PRDs/PRD-016-action-policy-rules/index.md` | UPDATE (regenerated) | |
| `.agents/plans/PRD-016-action-policy-rules/completed/STORY-017-synthetic-tool-call-corpus.plan.md` | CREATE (archived plan) | |

## Deviations from Plan

1. **AC 4 part 1 matches whole words, not substrings.** The plan's literal check is `entry.lower() in reason.lower()`. The example shell allowlist has two-letter entries (`ls`, `rg`), and a substring check would hit them inside ordinary words of a template or a call's detail (`tools`, `arguments`) and report a leak where none exists. `_names()` matches each entry with `(?<!\w)` / `(?!\w)` boundaries, case-insensitively, and the exemption ("the call sent it") uses the same matching. Part 2, the sentinels, uses plain substring checks, as planned.
2. **The loader guard set is a little wider than the plan's list.** It adds an empty `expect`, a missing required key, an extra `tool_call` key, an unknown `includes` entry and a non-mapping document, for 18 cases in all. A `test_the_valid_template_loads` test also proves that the base document the guards mutate is valid, so each bad case fails for its own reason only.
3. **More round-trip assertions.** The round trip also asserts `entry["user_id"]`, and that `tool_call_id`s are unique (`len(by_id) == len(entries)`).
4. **The corpus files were generated** by a scratch script from the plan's table, with a one-line header, the pinned SOURCES.md version and a note per file. The script is not committed. The files are the artifact.
5. Orchestrator decision 1 is applied: `brief-curl-pipe-sh.yaml` records `rule: net.unlisted`, `includes: [shell.pipe_to_interpreter, shell.unlisted]`. `rule-shell-pipe-allowlisted-host-to-sh.yaml` records `shell.pipe_to_interpreter` as the reported rule. The PRD line 632 correction is in this commit.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_action_corpus.py` | `test_every_corpus_file_loads`, `test_the_example_policy_is_the_loaded_file_not_the_built_in_one`, `test_the_test_matrix_grants_dba_and_not_admin`, `test_a_malformed_file_is_a_corpus_error_naming_the_file_and_the_node` (x18), `test_the_valid_template_loads`, `test_the_synthetic_corpus_holds_at_least_40_calls`, `test_every_rule_id_is_reported_by_some_file`, `test_ordinary_agent_work_is_never_denied`, `test_the_brief_criteria_are_present_verbatim` (x11), `test_the_scoped_delete_records_its_grant`, `test_every_tool_name_comes_from_sources_md`, `test_synthetic_call_decides_as_declared` (x70), `test_no_reason_names_a_configured_value_the_call_did_not_contain`, `test_sentinel_configuration_never_reaches_a_reason`, `test_every_decision_round_trips_through_record_and_the_audit_api` (`db`), `test_evaluate_p95_over_the_synthetic_corpus` (`benchmark`) |

## Acceptance Criteria

- [x] AC 1: 70 files (at least 40). All 25 rule ids are reported. 26 ordinary files are allowed for every role (at least 15), with each of OpenCode, Cline 4.x and Cline 3.x represented, and no ordinary file is denied. The brief's criteria are present verbatim. Proven by `test_the_synthetic_corpus_holds_at_least_40_calls`, `test_every_rule_id_is_reported_by_some_file`, `test_ordinary_agent_work_is_never_denied` and `test_the_brief_criteria_are_present_verbatim`.
- [x] AC 2: every declared decision, rule and `granted_by` holds for `user`, `dba` and `admin`, under the built-in and the example policy, with `dba` holding `action:sql:write`. Proven by `test_synthetic_call_decides_as_declared` (70 cases).
- [x] AC 3: `decision`, `rule` and `granted_by` (plus `role`, `user_id`, `policy_digest` and `reason`) survive `record()` and `GET /audit/actions` for all 210 pairs. Proven by `test_every_decision_round_trips_through_record_and_the_audit_api`.
- [x] AC 4: no reason names a configured entry that the call did not contain, and sentinel entries change no decision and reach no reason. Proven by `test_no_reason_names_a_configured_value_the_call_did_not_contain` and `test_sentinel_configuration_never_reaches_a_reason`.
- [x] AC 5: the `evaluate()` p95 is recorded above (0.4151 ms). Proven by `test_evaluate_p95_over_the_synthetic_corpus`, which is benchmark-marked and skipped without `--run-benchmark`.
