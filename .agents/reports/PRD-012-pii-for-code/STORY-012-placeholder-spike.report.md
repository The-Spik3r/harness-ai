---
story: STORY-012
prd: PRD-012
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-012-placeholder-spike.plan.md
epic_branch: epic/PRD-012-pii-for-code
commit: 970f16a
status: COMPLETE
completed: 2026-09-25
---

# Implementation Report — STORY-012: Placeholder spike and decisions/D5-placeholders.md

**Plan**: `.agents/plans/PRD-012-pii-for-code/completed/STORY-012-placeholder-spike.plan.md`
**Epic Branch**: `epic/PRD-012-pii-for-code`
**Commit**: `970f16a`

## Summary

This story adds `scripts/spike_pii_placeholders.py`, a live-model spike. It drives three scripted multi-turn agent tasks through the real `run_conversation(profile="code")` under four arms:
- **(a) fixed** `<TYPE>`: production, unpatched;
- **(b) indexed per request** `<TYPE_n>`;
- **(c) reversible**, with an in-memory mapping;
- **control**, with redaction off.

The tasks are: edit `seed-users.json`, write a test for `billing_seed.py`, and rename keys in `staging-values.yaml`. For each arm and task, the script reports placeholders sent to the model, placeholders in model output, placeholders in the artifact, and correctness. It then computes the decision rules R0–R5 that the plan fixed before any measurement.

The spike ran on two model families. Both produced **R4**:

| Model | control | (a) | (b) | (c) |
|---|---|---|---|---|
| `anthropic/claude-sonnet-5` (primary) | 9/9 | 3/9 | 3/9 | 9/9 |
| `openai/gpt-5.6-sol` | 9/9 | 6/9 | 6/9 | 9/9 |

Fixed and indexed placeholders break agent tasks. On both models, every (a) and (b) test file asserted a placeholder. Only reversible placeholders match the control. `decisions/D5-placeholders.md` records the method, the raw results, both models and the decision. The decision is that (c) is **justified but not adopted in PRD-012**, because its mapping is PII at rest, and fixed placeholders stay the default. The record also says what a later PRD must build before adopting (c). No production code changed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Preflight: branch, dev DB, green baseline (3152 passed / 26 skipped), each target file yields `code` entities at the lines the tasks touch | — | ✅ |
| 1 | Script skeleton: env bootstrap (no key default, DB URL never from `.env`), CLI, guards (local DB, dummy key, redaction off, transcripts outside the repo) | `scripts/spike_pii_placeholders.py` | ✅ |
| 2 | Schemes: `FixedScheme`, `ControlScheme`, `IndexedScheme(persistent)` reusing `pii_redactor`'s span pipeline; `restore`; `placeholder_pattern`; `scheme_installed` | `scripts/spike_pii_placeholders.py` | ✅ |
| 3 | Agent loop: tool protocol + parser, `Workspace`, `Upstream` wrapper, `run_task` with per-task-run identity | `scripts/spike_pii_placeholders.py` | ✅ |
| 4 | Three tasks and checkers, reading `tests/corpora/pii/code/` at run time | `scripts/spike_pii_placeholders.py` | ✅ |
| 5 | Report: per arm × task, per arm, incorrect runs, validity warning, computed decision; `--json` raw counts | `scripts/spike_pii_placeholders.py` | ✅ |
| 6 | Not-collected guard + side-effect-free import probe (AC 5) | `tests/test_spike_pii_placeholders.py` | ✅ |
| 7 | Offline tests of the pure parts, parity, rules, stubbed end-to-end loop | `tests/test_spike_pii_placeholders.py` | ✅ |
| 8 | Live runs: primary `anthropic/claude-sonnet-5` (36 task-runs, 598,962 tokens), robustness `openai/gpt-5.6-sol` (36 task-runs, 425,740 tokens); no task `INVALID` | — | ✅ |
| 9 | Decision record; PRD Section 15 D5 row + *Related documents* linked; Section 13 bullet updated (decision was not (a)) | `decisions/D5-placeholders.md`, `PRD.md` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | n/a (no frontend change) |
| Tests | ✅ 3234 passed, 26 skipped (baseline 3152 + 82 new) |
| `pytest --collect-only -q scripts` | ✅ exit 5 (no tests collected) |
| `git status -- app chat_ui` | ✅ empty |
| E2E | ✅ 7/7 |

E2E checklist (from the plan):
- [x] `--help` exits 0. A dummy `OPENROUTER_API_KEY` exits 1 with a message naming the variable.
- [x] A non-local `--database-url` without `--allow-remote-database` is refused (exit 1).
- [x] Offline `tests/test_spike_pii_placeholders.py` passes against the libSQL dev server with no network access (82 passed).
- [x] `pytest --collect-only -q scripts` collects nothing (exit 5), and `pytest -q` is green.
- [x] The live run completed all four arms × three tasks × three runs on both models. `sent > 0` holds for every (a), (b) and (c) row. The report printed placeholders in output, correctness and a computed decision.
- [x] `D5-placeholders.md` records method, raw results, model, decision and the (c) at-rest reasoning, and PRD Section 15 links it.
- [x] No `app/` or `chat_ui/` path changed.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `scripts/spike_pii_placeholders.py` | CREATE | +1023 |
| `tests/test_spike_pii_placeholders.py` | CREATE | +549 |
| `.agents/PRDs/PRD-012-pii-for-code/decisions/D5-placeholders.md` | CREATE | +235 |
| `.agents/PRDs/PRD-012-pii-for-code/PRD.md` | UPDATE | +3/-2 |
| `.agents/PRDs/PRD-012-pii-for-code/index.md` | UPDATE | status + plan link |
| `.agents/stories/PRD-012-pii-for-code/STORY-012-placeholder-spike.md` | UPDATE | frontmatter |
| `.agents/plans/PRD-012-pii-for-code/completed/STORY-012-placeholder-spike.plan.md` | CREATE (archived) | plan |
| `.agents/reports/PRD-012-pii-for-code/STORY-012-placeholder-spike.report.md` | CREATE | this report |

## Deviations from Plan

1. **`read_file` returns the raw file content with no header line.** The plan's `[tool_result read_file path=…]` header made a JSON file's turn start with `[` and fail `json.loads`. That turned off production's JSON-aware mode for the fixture read, which a real agent's tool turn (file content only) would get. The model still knows which file it read, because it asked for it.
2. **An aborted task-run is forced incorrect.** The plan states this rule. The first implementation still let the checker's verdict stand when the workspace happened to pass before the abort, and the first debug run caught it. A test pins the fix.
3. **An upstream abort records the exception message**, not only its type, so failures can be diagnosed. `OpenRouterError` messages carry the HTTP failure or finish reason, never request content.
4. **Live-run environment, not code:**
   - (a) This machine's Kaspersky Anti-Virus intercepts about half of the TLS connections to openrouter.ai with its own root certificate, which certifi does not trust. The live runs set `SSL_CERT_FILE` to a scratchpad bundle of certifi plus the Windows root store. Verification stayed on, and `app/` is unchanged. This is recorded in the D5 limitations.
   - (b) The spike and the test suite share the libSQL dev server, and the suite drops every table. The first live attempt ran alongside the suite and lost `audit_logs`. The two were run one after the other from then on. That attempt's results were discarded.
5. **Tests beyond the plan's list:** DB-URL-never-from-`.env`, guard tests, dummy-key refusal, `chat` policy never renumbered, redaction-disabled, instructions carry no PII, the R2 Future-Considerations branch, the blocked-send abort (duplicate), and the aborted-is-incorrect case.
6. **Decision branch:** R4, not (a) or (b). No STORY-015 was created, because the plan creates one only for decision (b). The PRD's Section 13 bullet was updated, as the plan requires for any decision other than (a).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_spike_pii_placeholders.py` | **Guards and collection:** not collected; import builds no analyzer and opens no connection; DB URL never from `.env`; local-DB and transcripts guards; dummy key refused. **Schemes:** fixed == `redact_for_policy` over 11 corpus samples; indexed minus suffix == `redact_for_policy` (×2 schemes × 11 samples); `chat` never renumbered; control and redaction-off mask nothing. **Numbering and restore:** first-appearance numbering; prefix stability over a growing conversation; (b) restarts per send and (c) does not; (c) restores and counts unknowns; (b) never restores; JSON number quoted then restored bare. **Tools:** placeholder counting; each tool parses; placeholder inside content stays content; content may contain its own closing tag; 4 malformed calls; workspace read, replace hit/miss/ambiguous, write, done. **Checkers:** fixture, test, rename; the corpus first-customer values; instructions carry no PII. **Rules:** R0, R1 (every-run task), R2 (with and without the Future Considerations note), R3, R4, R5, invalid, needs all four arms, exact fractions, report rendering. **End to end** (real `run_conversation`, stub model): control/a/b/c outcomes; patch removed after the run; duplicate block aborts; upstream error aborts and is incorrect |

## Acceptance Criteria

- [x] Given `scripts/spike_pii_placeholders.py`, when it runs with an OpenRouter key, it drives three scripted multi-turn agent tasks (edit a fixture, write a test, rename a field) through `run_conversation(profile="code")`, feeding each response back as history, for (a) fixed `<TYPE>`, (b) indexed per request `<TYPE_n>` numbered by first appearance across the conversation, and (c) reversible with an in-memory mapping. A control arm is added as the baseline.
- [x] Given each run, when it completes, the script reports per option the number of placeholders in model output and whether each task's final artifact is correct.
- [x] Given `decisions/D5-placeholders.md`, it records the method, the raw results, the models used, the decision, and why (c) is not adopted given that a stored mapping is PII at rest.
- [x] Given the decision, no production code changed. The decision is R4, which keeps (a) as the default, so no follow-up story is named. The (b) branch did not apply.
- [x] Given CI, the spike script is not collected as a test (pinned by `test_the_spike_is_not_collected`).
- [x] All tasks completed.
- [x] Full suite passes.
- [x] No file under `app/` or `chat_ui/` changed.
- [x] Follows existing patterns (`scripts/measure_*` spike shape, `tests/test_measure_pii_latency.py` test shape).
