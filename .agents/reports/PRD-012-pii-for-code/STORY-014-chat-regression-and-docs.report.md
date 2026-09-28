---
story: STORY-014
prd: PRD-012
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-014-chat-regression-and-docs.plan.md
epic_branch: epic/PRD-012-pii-for-code
commit: 6b0e956
status: COMPLETE
completed: 2026-09-25
---

# Implementation Report — STORY-014: chat regression sweep, README and .env docs, pre-PRD promoted

**Plan**: `.agents/plans/PRD-012-pii-for-code/completed/STORY-014-chat-regression-and-docs.plan.md`
**Epic Branch**: `epic/PRD-012-pii-for-code` (plan commit `4a07476`)
**Commit**: `6b0e956`

## Summary

This is the last story of PRD-012. It re-proves `chat` and documents what `code` does and gives up. **No `app/`, `chat_ui/` or `scripts/` file changed.**

- **Regression sweep:**
  - full suite green: 3,330 passed, 27 skipped;
  - the latency-budget benchmark passes at 505.93 ms against 1,500 ms;
  - the five protected test files have no assertion removed or weakened since the epic base `e10d191`. One expected key was added by STORY-011; see Deviation 1.
- **README:**
  - a new `### PII redaction` section under Features, covering both profiles, the Section 6.3 role table, the trade-offs one by one, the audit's `profile` semantics, and a `chat`-vs-`code` latency table beside the ~0.93 s history figure;
  - replacements and pointers elsewhere: the Features row, the diagram note, the history cost, 10 `PII_*` env rows (4 reworded, 6 new), `redaction_characters` in the context-limit API section, `profile` in `GET /audit`, `GET /stats`, Troubleshooting, Roadmap, and the OpenAI-compatible endpoint sentence.
- **`.env.example`:** the six settings in field order with the shipped defaults. The four existing `PII_*` comments now say which profile each governs.
- **Tests:** four `.env.example` guard tests in `tests/test_config.py`.
- **Pre-PRD:** `PRE-PRD-012` is `promoted`, and its row in `pre-prds/README.md` links PRD-012.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Protected-file baseline recorded against `e10d191` | — | ✅ |
| 2 | Six settings plus profile scope on the four existing comments | `.env.example` | ✅ |
| 3 | `.env.example` guard group; 5 guard-bites observed and reverted | `tests/test_config.py` | ✅ |
| 4 | `### PII redaction` section | `README.md` | ✅ |
| 5 | Replacements and pointers (Features, diagram note, cost pointer, env table, API, `/audit`, `/stats`, Troubleshooting, Roadmap, OpenAI endpoint) | `README.md` | ✅ |
| 6 | Pre-PRD promoted, table row updated | `pre-prds/PRE-PRD-012-pii-for-code.md`, `pre-prds/README.md` | ✅ |
| 7 | Throwaway link and anchor check (scratchpad, not committed) | — | ✅ |
| 8 | Full sweep, benchmark, scope checks | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| App boot + `GET /health` (local libSQL, port 8765) | ✅ `{"status":"ok"}`, no errors in the log |
| Frontend lint | n/a (no UI change, no linter configured) |
| `tests/test_config.py` | ✅ 121 passed |
| Full suite | ✅ **3,330 passed, 27 skipped** (STORY-013: 3,326 + the 4 new tests; skips unchanged: 25 `REPORTS_E2E_URL`, 1 `HARNESS_SLOW_SMOKE`, 1 benchmark). 2 warnings, both pre-existing Starlette/httpx deprecations |
| Benchmark `pytest tests/test_pii_code_corpus.py -m benchmark --run-benchmark -s` | ✅ `code p95 at 200000 chars: 505.93 ms (min 458.11, p50 486.93, n=20; budget 1500 ms)` |
| `git diff --stat HEAD -- app/ chat_ui/ scripts/` | ✅ empty |
| Protected files touched by this story | ✅ none |
| Link and anchor check | ✅ no new failures; the only miss is the pre-existing `SECURITY.md` (also on `HEAD`) |
| E2E | ✅ 7/7 |

### Task 1: protected-file evidence (AC 1)

```
$ git diff --stat e10d191 HEAD -- tests/test_pii_redactor.py tests/test_pii_redaction_integration.py \
    tests/test_pii_characterization.py tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py
 tests/test_pii_characterization.py      | 369 ++++++++++++++++++++++++++++++++
 tests/test_pii_redaction_integration.py |   2 +
$ git diff 5e93b18 HEAD -- tests/test_pii_characterization.py | wc -l
0
$ git diff e10d191 HEAD -- tests/test_pii_redaction_integration.py
@@ -203,6 +203,8 @@ def test_audit_endpoint_contract_has_no_preview_fields(temp_db, monkeypatch):
         "pii_detected_input",
         "pii_detected_output",
         "pii_entities",
+        # PRD-012 D9: additive, nullable (STORY-011).
+        "profile",
         "prompt_hash",
$ git diff e10d191 HEAD -- tests/test_pii_redaction_integration.py | grep -E '^-[^-]'
(no output)
$ git log --oneline e10d191..HEAD -- tests/test_pii_redaction_integration.py
faaa4be feat(PRD-012): STORY-011 audit_logs.profile on every arm; /audit and the Register show it
```

- `test_pii_redactor.py`, `test_query_outcomes_regression.py` and `test_chat_outcomes_regression.py` are byte-identical to the base.
- `test_pii_characterization.py` was created inside the epic (`5e93b18`, STORY-002) and is unchanged since.

### Guard-bites (Task 3; each reverted, `git diff .env.example` identical afterwards)

| Mutation to `.env.example` | Test that failed |
|---|---|
| `PII_CODE_REDACT_OUTPUT` / `PII_CODE_REDACT_SYSTEM` lines swapped | `test_env_example_pii_code_vars_appear_in_settings_field_order` |
| `chat` removed from the `PII_ENTITIES` comment | `test_env_example_existing_pii_comments_name_their_profile` |
| `code` removed from the `PII_REDACTION_ENABLED` comment | `test_env_example_existing_pii_comments_name_their_profile` |
| `PII_SCORE_THRESHOLD_CODE=0.45` | `test_env_example_pii_code_defaults_match_settings` |
| Comment above `PII_CODE_SKIP_CODE_BLOCKS` removed | `test_env_example_documents_every_pii_code_var_with_a_comment` |

### E2E checklist

- [x] `pytest tests/ -q` green, counts recorded above.
- [x] `--run-benchmark` passes; p95 505.93 ms < 1,500 ms.
- [x] Task 1 evidence recorded; the D1 deviation is stated with the hunk quoted.
- [x] Task 3 guard-bites fail as expected, then reverted.
- [x] README `### PII redaction` read against AC 2. Each item is present: `chat` and `code` described; the 6.3 table reproduced verbatim; fenced blocks unmasked; names and places not detected by default; output not masked; number tokens quoted in JSON; over-limit refused; `profile` in the audit.
- [x] Env table read against `app/config.py:216-240`: 10 `PII_*` rows, defaults match row for row, all four existing rows name `chat`, and the master switch also names `code`.
- [x] Link checker: no new failures. `#pii-redaction` (9 uses), `#post-query--blocked-context-limit`, `#get-audit-requires-auditreadall-or-auditreadown`, `#openai-compatible-endpoint` and `.agents/PRDs/PRD-012-pii-for-code/PRD.md` all resolve.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `README.md` | UPDATE | +77/-12 |
| `.env.example` | UPDATE | +41/-4 |
| `tests/test_config.py` | UPDATE | +72 |
| `pre-prds/PRE-PRD-012-pii-for-code.md` | UPDATE | +2/-2 |
| `pre-prds/README.md` | UPDATE | +1/-1 |
| `.agents/plans/PRD-012-pii-for-code/completed/STORY-014-chat-regression-and-docs.plan.md` | MOVE (archived) | 0 |
| `.agents/reports/PRD-012-pii-for-code/STORY-014-chat-regression-and-docs.report.md` | CREATE | this file |

## Deviations from Plan

1. **AC 1 is met at the "no assertion removed or weakened" level, not literally (plan D1, anticipated).**
   - STORY-011 (`faaa4be`) added `"profile"` to the expected key set of `test_audit_endpoint_contract_has_no_preview_fields`, with a `PRD-012 D9` comment.
   - That makes the assertion stricter, and PRD Section 11 *Quality indicators* requires exactly such a comment on a modified pre-existing test.
   - Reverting it would fail the test against the shipped `/audit` shape.
   - This report does not claim byte-identity for that file.
2. **The `.env.example` guard group reuses STORY-005's `_PII_CODE_VARS`** instead of defining a second tuple. The field-order test still derives its order from `Settings.model_fields`, as planned, and also asserts that the tuple and the fields name the same six.
3. **The context-limit API section's "This is the only outcome this release adds" was re-scoped** to "the multi-turn release (PRD-010) added". The plan allowed this if the sentence read as false after this release, and it did: PRD-012 adds no `/query` outcome, because `redaction_characters` is unreachable there. "`limit` is `messages` or `characters`" became three values, and "only one is ever reported" now applies explicitly to the first two.
4. **The benchmark rerun measured 505.93 ms, not STORY-013's 463.23 ms.** That is about 9% run-to-run variance, and both are about a third of the budget. The README therefore says "runs have measured 463–506 ms" instead of quoting one run. The latency table keeps STORY-013's `code` rows and STORY-003's `chat` rows, as planned.
5. **The concurrency bullet names the arm that was measured.** STORY-003's throughput figures (`chat` 0.70×, 1.00×) are for `chat` and `pattern-blank`; STORY-013 did not add `code` to the throughput run. The README therefore says "the pattern-only analyzer `code` uses stays at 1.00×", not "`code` stays at 1.00×".
6. **The JSON post-condition is worded by where the 500 comes from.** `run_conversation` audits the failure and re-raises `PiiRedactorError` (`query_pipeline.py:458-469`), and `POST /query` turns that into a `500`. `code` has no ingress yet, so the README says the error is "raised to the ingress — the path `POST /query` answers with a `500`" and does not promise a `500` from `code` directly.
7. **The trade-off list's lead-in was changed** from "each has its lever" to "Where a setting changes one of these, it is named". Fixed placeholders, structure-safety and escapes have no setting.
8. **The plan was committed before implementation** (`4a07476`, `docs(PRD-012): STORY-014 plan`), matching STORY-013's `00bfd9b`, so this story's commit starts from a clean tree.
9. **Test runner.** The `python` on `PATH` (3.11 system) has no pytest, so every run used `.venv/Scripts/python.exe`.

## Observations (recorded, not fixed)

- **The libSQL dev server degraded mid-session again.** A baseline run before any test change (it overlapped only the `.env.example` edits, which no failing test reads) had 4 failures and 7 errors in session, chat-state, identity and query-session tests. All were `STREAM_EXPIRED` or `no such table` from Hrana. `docker restart harness-libsql-dev` cleared them, and the post-change run was fully green. This is the PRD Section 11 rule ("restart the container, not bisect code"), and it still lives only in the PRD and in test docstrings, not in README *Running Tests* (STORY-003 observation, unchanged).
- **`LOG_LEVEL` is still read by nothing** (STORY-007 finding). The README therefore does not say that the fallback of an unknown profile to `chat` shows up in the logs. It only says the fallback happens.
- **The README's pre-existing `SECURITY.md` link is broken** (the file does not exist). It was already broken on `HEAD` and is out of scope.
- **The source-code escape gap stays open** (STORY-013 F-4, non-JSON half). It is now documented in the README as "Escape sequences can hide a number in source code … Recorded, not fixed."

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` (+4) | `test_env_example_documents_every_pii_code_var_with_a_comment`, `test_env_example_pii_code_vars_appear_in_settings_field_order`, `test_env_example_pii_code_defaults_match_settings`, `test_env_example_existing_pii_comments_name_their_profile` |

## Acceptance Criteria

- [x] Given the full suite, when it runs, then it is green, and `git diff` since the epic's base shows no changed assertion in `test_pii_redactor.py`, `test_pii_redaction_integration.py`, `test_pii_characterization.py`, `test_query_outcomes_regression.py` or `test_chat_outcomes_regression.py`. *(Green: 3,330 passed. One additive expected key from STORY-011, with nothing removed or weakened: Deviation 1.)*
- [x] Given the README PII section, when it is read, then it describes the `chat` and `code` profiles, reproduces the Section 6.3 role table, and states plainly: fenced blocks unmasked, names and places not detected by default, output not masked, number tokens quoted in JSON, over-limit refused, `profile` in the audit.
- [x] Given the README, when it quotes latency, then it gives the STORY-003 / STORY-013 figures for both profiles beside the existing ~0.93 s history figure, and names `scripts/measure_pii_latency.py`.
- [x] Given `.env.example` and the README configuration table, when they are read, then all six new settings appear with defaults and one-line purposes, and the four existing `PII_*` rows say they apply to `chat`.
- [x] Given `pre-prds/PRE-PRD-012-pii-for-code.md` and `pre-prds/README.md`, when they are read, then the brief is `status: promoted` with `prd:` set, and its table row links PRD-012 with status `promoted`.
- [x] All tasks completed
- [x] Backend imports without error; no `app/`, `chat_ui/` or `scripts/` change
- [x] Follows existing patterns (PRD-011 STORY-013 shape)
