---
story: STORY-018
prd: PRD-013-audit-and-usage-limits
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-018-regression-and-docs.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: af85840
status: COMPLETE
completed: 2026-10-20
---

# Implementation Report — STORY-018: Regression sweep, README and .env docs

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-018-regression-and-docs.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `af85840`

## Summary

This is the last story of PRD-013: one regression sweep plus the documentation, in one commit. **No `app/`, `chat_ui/` or `scripts/` file changed.**

**Prove**
- The full suite is green after one shared-DB flake was triaged (see Validation).
- The four protected test files are shown, with git evidence against the epic base `b184614`, to have no changed assertion.
- A per-hunk audit of the 32 modified pre-existing test files found 8 hunks with no PRD-013 citation. Each now has a comment, and nothing else changed.

**Document**
- `README.md` gains:
  - a `### Usage limits` section;
  - a `### POST /query — blocked (usage limit)` API section;
  - the eight `/audit` fields and three `/stats` fields;
  - four env rows, and the `ADMIN_TOKEN` `/v1` refusal;
  - three Troubleshooting entries and a Roadmap line.
- Stale README statements now read as shipped: "planned as PRD-013", "All four tables", `audit_logs` "exactly one column", and the round-trip count.
- `.env.example` gains the four settings in field order, and its stale `ADMIN_TOKEN` comment is corrected. `tests/test_config.py` gains a five-test guard group.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Protected-file git evidence | none (evidence below) | ✅ |
| 2 | Per-hunk PRD-013 citation audit; comment-only fixes | `tests/test_admin_models.py`, `tests/test_identity.py`, `tests/test_manage_users_cli.py`, `tests/test_summary.py` | ✅ |
| 3 | Usage group and `ADMIN_TOKEN` comment | `.env.example` | ✅ |
| 4 | `.env.example` guard group | `tests/test_config.py` | ✅ |
| 5 | `### Usage limits` section | `README.md` | ✅ |
| 6 | API reference: usage-limit body, `/audit` fields, `/stats` fields | `README.md` | ✅ |
| 7 | Replacements: Features, architecture prose, duplicate scope, persistence, env table, Troubleshooting, Roadmap | `README.md` | ✅ |
| 8 | Link and anchor check (throwaway) | scratchpad | ✅ |
| 9 | Full sweep and scope checks | none | ✅ |

## Task 1: protected-file evidence (D1)

`git merge-base HEAD main` = `b18461408c…` (the PRD-012 merge, PR #15).

```
git diff --stat b184614 HEAD -- tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py tests/test_duplicate_scope.py tests/test_pii_characterization.py
 tests/test_chat_outcomes_regression.py  |  3 +-
 tests/test_query_outcomes_regression.py | 56 +++++++++++++++++++++++++++++++++
```

- **`test_query_outcomes_regression.py`** (commit `8dc6b4d`, STORY-011) has **0 removed lines**. The diff adds:
  - two docstring lines;
  - a `datetime` import;
  - `test_outcome_8_usage_limit`, appended after outcome 7.

  Rows 1–7 are byte-identical.
- **`test_chat_outcomes_regression.py`** (commit `1ab83f2`, STORY-005) has one hunk. The fake `_fake(...)` in `_capturing_run_conversation` gains `ingress=None`, under the comment `# \`ingress\` accepted since PRD-013 STORY-005; ChatState passes "chat".` That is a test double's parameter list, not an assertion.
- **`test_duplicate_scope.py`, `test_pii_characterization.py`**: no commits in the epic, so the diff is empty.

This story touched none of the four files. `git diff --stat HEAD` over them was empty before the commit.

## Task 2: per-hunk citation audit (D2)

A throwaway script walked `git diff -U0 b184614` for every `M` file under `tests/`. For each hunk that removed or replaced a line, it looked for `PRD-013` in two places:
- the hunk's added lines;
- the enclosing `def`/`class`, including the comments and decorators directly above it.

**Before:** `files=32 modified_hunks=63 uncited=8`

| Hunk | Introduced by | Comment added |
|---|---|---|
| `test_admin_models.py:93`: `*AUDIT_FIELD_NAMES` in the default-field loop | `b6085a4` STORY-015 | `# PRD-013 STORY-015 (Section 6.10): the Register's new disclosure fields default to "" too.` |
| `test_identity.py:13`: import `set_user_limits` | `162820c` STORY-008 | `# set_user_limits: PRD-013 STORY-008 (D1), per-user overrides on the users row.` |
| `test_identity.py:63`: `break_glass=True` in the expected `Identity` | `162820c` STORY-008 | `# PRD-013 STORY-008 (D4, Section 6.8): only the ADMIN_TOKEN path sets break_glass.` |
| `test_identity.py:80`: same | `162820c` STORY-008 | same |
| `test_manage_users_cli.py:10`: import `resolve` | `162820c` STORY-008 | `# resolve: PRD-013 STORY-008 (D1), set-limits overrides reach the resolved Identity.` |
| `test_summary.py:272, :274`: docstring "nine" → "twelve" | `b6085a4` STORY-015 | `# PRD-013 STORY-015 (Section 6.10): nine figures became twelve (token totals, usage-limit count).` |
| `test_summary.py:374`: same | `b6085a4` STORY-015 | same |

**After:** `files=32 modified_hunks=63 uncited=0`.

The diff of `tests/` outside `test_config.py`, filtered to lines that are neither headers nor added comments, is **empty**: 7 insertions, all `#` lines, and 0 deletions.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`import app.main`) | ✅ |
| Frontend lint | n/a. No UI change and no linter configured (STORY-017 precedent) |
| `tests/test_config.py` | ✅ 165 passed (160 + 5 new) |
| Full suite | ✅ 3,825 passed, 27 skipped; 2 shared-DB flakes, both green on rerun (below) |
| E2E | ✅ 10/10 |

**Flake triage.** The full run (354 s) ended with 2 failures, both in DB fixtures:
- `test_db.py::test_init_db_migration_is_idempotent_across_repeated_calls`, with Hrana `STREAM_EXPIRED`;
- `test_manage_users_cli.py::test_set_limits_unknown_user_exits_nonzero_and_writes_nothing`.

Rerunning both files passed both tests, but a *different* `test_db.py` test then errored at setup. That is the moving-target signature of the known shared-DB flake (PRE-PRD-017).

I ran `docker restart harness-libsql-dev`, then reran `test_db.py`, `test_manage_users_cli.py` and the four files this story touched (`test_config`, `test_identity`, `test_admin_models`, `test_summary`): **535 passed, 0 failed**. This story's changes to those files are comments and `.env.example` guards, which open no database connection.

The total of 3,825 + 2 = 3,827 is STORY-017's 3,822 plus the 5 new guard tests.

## E2E Results

| Check | Result |
|-------|--------|
| Full suite green; counts recorded | ✅ (above) |
| Task 1 git evidence recorded | ✅ |
| Task 2 audit: 0 uncited hunks; non-comment test diff empty | ✅ |
| Guard-bites | ✅ Each fails exactly its own test, then the file is restored (`cmp` identical):<ul><li>swap the two limit-map lines → `…_appear_in_settings_field_order`</li><li>remove `/v1` from the `ADMIN_TOKEN` comment → `…_admin_token_comment_names_v1_and_the_setting`</li><li>publish `*=60,admin=120` → `…_usage_defaults_match_settings`</li><li>drop "counter" → `…_says_what_disabling_usage_limits_does`</li></ul> |
| `Settings(_env_file='.env.example')` | ✅ `True {'*': 1000000} {'*': 60} ['chat', 'query']`, with the usage env vars unset. Because those equal the defaults, `dotenv_values('.env.example')` was also checked: it returns `'*=1000000'`, `'*=60'`, `'query,chat'` intact (the `=` inside the value survives) |
| Read `### Usage limits` against AC 2 | ✅ Covers: two limits; defaults as starting points, with "upgraded deployment gets them without opting in"; role maps (examples labelled as examples); overrides with the five `manage_users.py` commands; fixed window; overshoot; BYOK; fail-closed gate and fail-open charge; STORY-017 figures |
| Read API reference against AC 3 | ✅ Usage-limit body, eight `/audit` fields with a meaning table and the three `conversation_key` limits, three `/stats` fields |
| Read env table and `.env.example` against AC 4 | ✅ Four rows in each; `ADMIN_TOKEN` README row and `.env.example` comment both say "never accepted on `/v1`" |
| Read *Duplicate detection scope*, *The database is a hard dependency*, Roadmap against AC 5 | ✅ |
| Link checker | ✅ The only failure is `SECURITY.md`, which is also the only failure at `HEAD`. New anchors resolve: `#usage-limits`, `#post-query--blocked-usage-limit`, `#the-database-is-a-hard-dependency-of-every-request`, `#get-audit-requires-auditreadall-or-auditreadown`, `#post-query--200-refused-by-policy`, `#openai-compatible-endpoint` |
| Scope | ✅ `git diff --stat HEAD -- app/ chat_ui/ scripts/` empty; protected files empty |
| Remote latency run (optional) | Not run. No remote endpoint is configured: `.env` `DATABASE_URL` is `http://127.0.0.1…`, `TURSO_AUTH_TOKEN` is empty, and there is no Turso CLI. The README says no remote endpoint has been measured and gives the command (D6) |

### Claims and the tests that prove them (Task 5's bold-claim check)

| README claim | Test |
|---|---|
| A second instance does not double the limits | `test_two_instance_smoke.py::test_a_rate_limit_of_five_admits_five_of_ten_alternating_requests`, `…_budget_exhausted_through_instance_a_is_refused_on_instance_b` |
| Override, then role, then `*`; unknown role gets `*`; break-glass gets `admin`'s | `test_usage_limits.py::test_limits_for_*` |
| `0` is a startup error naming the off switch | `test_config.py::test_a_zero_limit_names_the_real_off_switch` |
| Duplicate, pattern and context-limit refusals each consume a unit | `test_query_pipeline_usage_limits.py::test_a_duplicate_blocked_attempt_consumes_one_unit`, `…_pattern_block_…`, `…_context_limit_refusal_…` |
| Authorization refusals never reach the gate | `…::test_a_caller_without_query_submit_never_reaches_the_gate`, `…_disallowed_model_…`, `…_byok_denial_…` |
| Charged on success and on output-redaction failure, not on upstream error; total charged without a split | `…::test_an_output_redaction_failure_is_still_charged`, `…::test_an_upstream_error_charges_nothing`, `…::test_a_response_without_the_split_charges_unsplit_tokens` |
| Rate reported when both are broken | `…::test_when_both_limits_are_broken_the_rate_is_reported` |
| BYOK is rate-limited, not budget-refused, charges nothing | `…::test_byok_consumes_a_unit_is_not_budget_refused_and_charges_nothing` |
| Gate fails closed (`500`, no upstream); charge fails open | `…::test_query_maps_a_usage_limit_error_to_500_with_no_upstream_call`, `…::test_a_charge_storage_failure_still_returns_success_with_its_row`, `test_usage_limits.py::test_charge_fails_open_and_logs_at_error_on_a_storage_error` |
| Refused prompt answered after the reset, not held as a duplicate | `…::test_a_prompt_refused_for_a_limit_is_answered_after_the_reset` |
| Overshoot: two requests admitted under a nearly spent budget both complete | `…::test_two_requests_admitted_under_a_nearly_spent_budget_both_complete` |
| `USAGE_LIMITS_ENABLED=false` touches no `usage_daily` | `…::test_with_limits_off_no_statement_touches_usage_daily` |
| Break-glass refusal body and audit; console still signs in | `test_query_pipeline_break_glass.py::test_setting_chat_only_refuses_post_query_with_the_200_body`, `…::test_admin_console_gate_still_accepts_admin_token` |
| Five statements per request | `test_two_instance_smoke.py::test_round_trip_cost_is_measured_and_reported` |

The only claim with no dedicated test is that the rate window is fixed rather than sliding. It is the shape of the `admit` statement (`strftime('%s','now') / 60`), and `test_usage_storage.py::test_admit_usage_resets_the_window_on_a_new_minute` covers it.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `README.md` | UPDATE | +119/−11 |
| `.env.example` | UPDATE | +27/−1 |
| `tests/test_config.py` | UPDATE | +71 |
| `tests/test_identity.py` | UPDATE (comments) | +3 |
| `tests/test_summary.py` | UPDATE (comments) | +2 |
| `tests/test_admin_models.py` | UPDATE (comment) | +1 |
| `tests/test_manage_users_cli.py` | UPDATE (comment) | +1 |

## Deviations from Plan

1. **The architecture paragraph says the diagram predates the gate**, instead of only adding "usage limit" to the short-circuit list. The old sentence said blocks "short-circuit at step 0, 3, or 4", and that step list has no place for the gate. The diagram is not redrawn (PRD-012 precedent).
2. **The Troubleshooting `500` entry quotes the real message**, `Usage admission failed: …` (`usage_limits.py:162`), instead of the plan's paraphrase "naming the usage counter". A third entry was added for `"required_permission": "ingress:break_glass"`, which an operator who narrows `BREAK_GLASS_INGRESSES` will meet.
3. **The Features table also gained a *Usage limits* row.** The plan named it, and this records that it went in above *Admin endpoints*. The *Full audit logging* and *Admin endpoints* rows were extended as planned.
4. **Two unrelated working-tree changes were left unstaged.** `pre-prds/README.md` (an "Other briefs" table) and the untracked `pre-prds/PRE-PRD-017-test-suite-db-isolation.md` are the user's pending PRE-PRD-017 draft, dated 2026-10-17, and were already present during STORY-017. `/implement` Phase 2 says to stop on a dirty tree. Since they touch no file of this story, they were kept out of the commit by staging files by name, not stashed.
5. **The README `### Usage limits` §3 command block lists all five `manage_users.py` commands** (D5). No user-management command list existed to put `set-limits` beside.

## Follow-ups (not done here)

- `app/config.py:315-338` still says "no production code reads these yet" and "Consumed by STORY-0xx" above the usage fields. That has been stale since STORY-011/012/013. It was left alone under the no-app-change rule (plan D9), as PRD-012 left its own equivalents.
- Remote latency figure: run `TURSO_AUTH_TOKEN=<token> PYTHONPATH=. python scripts/measure_usage_latency.py --database-url libsql://<db>-<org>.turso.io --allow-remote-database --runs 50` before deployment, and add it to *Usage limits* → *What it costs*.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` | `test_env_example_documents_every_usage_var_with_a_comment`, `test_env_example_usage_vars_appear_in_settings_field_order`, `test_env_example_usage_defaults_match_settings`, `test_env_example_admin_token_comment_names_v1_and_the_setting`, `test_env_example_says_what_disabling_usage_limits_does` |

## Acceptance Criteria

- [x] Given the full suite, when it runs, then it is green, and `git diff main` shows no changed assertion in `test_query_outcomes_regression.py` rows 1-7, `test_chat_outcomes_regression.py`, `test_duplicate_scope.py` or `test_pii_characterization.py`; every other modified pre-existing test carries a comment citing PRD-013 and the decision. *(Green after flake triage. Rows 1–7: 0 removed lines. The chat file's one hunk is a fake's signature, not an assertion. 63/63 modified hunks cited.)*
- [x] Given the README, when it is read, then it has a *Usage limits* section covering the two limits, their defaults, role maps and per-user overrides, the fixed window, the possible budget overshoot, the BYOK rule, fail-closed gate and fail-open charge, and the measured round trips from STORY-017.
- [x] Given the README's API reference, when it is read, then it documents the usage-limit `BLOCKED` body, the eight new `/audit` fields with their meanings (including the three limits of `conversation_key`) and the three new `/stats` fields.
- [x] Given the README's environment table and `.env.example`, when they are read, then both list `USAGE_LIMITS_ENABLED`, `USAGE_DAILY_TOKEN_BUDGET`, `USAGE_REQUESTS_PER_MINUTE` and `BREAK_GLASS_INGRESSES`, and the `ADMIN_TOKEN` row says it is refused on `/v1`.
- [x] Given the README's *Duplicate detection scope*, *The database is a hard dependency of every request* and roadmap sections, when they are read, then the PRD-013 note reads as shipped, the per-request round trips are updated, and the roadmap lists this PRD under shipped.
- [x] All tasks completed
- [x] Backend imports without error; no `app/`, `chat_ui/` or `scripts/` change
- [x] Follows existing patterns (PRD-012 STORY-014 shape)
