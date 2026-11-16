---
story: STORY-018
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-018-evasion-corpus.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: 5efc769
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-018: Evasion corpus

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-018-evasion-corpus.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `5efc769`

## Summary

`tests/corpora/actions/evasion/` holds 216 YAML files, each an obfuscated variant of a denied synthetic file (`of:`), with a technique, the rule the engine reports and a note. `tests/test_action_corpus.py` loads them at import (a bad `of:` fails collection) and asserts, for `user`, `dba` and `admin`, that no file is `allow` and that each gets its declared decision and rule. 212 files are `deny` with their declared rule; 4 are `flag` (see finding 3). Zero rows are `allow` for any role.

## Findings (classifier fixes made in this commit, AC 4)

1. **Win32 dots-and-spaces segment** (`a/.../b`, `. ./x`, `.. /x`) was `allow` / `fs.write_in_workspace`. Exposed by `path-dots-segment-win`, `path-dots-space-segment`, `dots-segment-absolute-in-root`. Fix in `paths._contained`: a segment of only dots and spaces is outside the workspace (deny-only).
2. **PowerShell `Env:` drive** (`ls env:`, `cat env:AWS_SECRET_ACCESS_KEY`) was `allow` / `shell.allowlisted` under the example policy, and only floor-denied under the built-in one. Exposed by the six `envdrive-*` rows. Fix in `secrets.env_references` (`ENV_DRIVE` sentinel): `env:NAME` is the variable, `env:` or `env:*` is the whole environment, `secret.read`.
3. **Code-carrying options of allowlisted heads** (orchestrator decision 3a) were `allow` under the example policy: `git -c alias.x='!cmd' x`, `git --config-env`, `--upload-pack`, `--receive-pack`, `git clone -u`, `rg --pre`, `pytest -p`, `npm ... --script-shell`. Fix in `shell.py`: a small closed table (`_CODE_OPTION_HEADS`, `_code_option`, `_git_code_option`) makes them `shell.inline_interpreter`, emitted with the other danger rules before the allowlist. Covered by 14 corpus rows (`codeopt-*`) and unit tests in `tests/test_action_shell.py`.
4. **Whole-`git` on the example allowlist** (decision 3b): `examples/action_policy.yaml` now allows `git status`, `git diff`, `git log`, `git show`. `git clean`, `git reset --hard`, `git push --force` and `git clone <url>` are `shell.unlisted`, which the example sets to `flag` (never allow). Four corpus rows (`git-*-unlisted`, technique `unlisted_head`, `decision: flag`).

## Corpus counts by technique

windows_shell 23, inline_code 21, path_tricks 21, unlisted_head 19, wrappers 19, secret_access 18, url_tricks 18, sql_comments_casing 15, chaining 12, quoting_escapes 11, flag_permutations 7, nested_bash_c 7, base64_interpreter 6, substitution 6, tool_names 6, eval_source 4, redirect_write 3 (216 total). Every one of PRD Section 11's 11 groups has a file.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Fix A (dots-and-spaces segment) | `app/services/action_classifiers/paths.py` | done |
| 2 | Fix B (`Env:` drive) + docstring | `app/services/action_classifiers/secrets.py`, `shell.py` | done |
| 3 | Code-carrying options (decision 3a) | `app/services/action_classifiers/shell.py` | done |
| 4 | Example `git` entry narrowed (decision 3b) | `examples/action_policy.yaml` | done |
| 5 | Unit tests for 1-3 | `tests/test_action_paths.py`, `test_action_secrets.py`, `test_action_shell.py` | done |
| 6 | 216 corpus files (198 from the plan's row table + 18 added for decision 3) | `tests/corpora/actions/evasion/*.yaml` | done |
| 7 | Loader, tests, evasion round trip in batches of 150, docstring | `tests/test_action_corpus.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Frontend lint | N/A (no `frontend/`) |
| Targeted: `test_action_corpus.py test_action_shell.py test_action_paths.py test_action_secrets.py test_action_config.py test_untouched_app.py` (`PYTHONUTF8=1`) | 1772 passed, 1 skipped (the benchmark), 0 failed |
| `tests/test_action_policy.py` (extra) | 63 passed |
| Full suite | deferred to orchestrator (user decision) |

## Deviations from Plan

- F12 shape extended: required `rule` (and `note`), plus an optional `decision: deny | flag` (default `deny`, `allow` rejected). Needed for the 4 `git-*-unlisted` rows, which are `flag` under the example policy for all three roles. Orchestrator decision 1 accepted `rule`; `decision` is new.
- 18 rows added beyond the plan's 198 (14 `codeopt-*`, 4 `git-*-unlisted`) because decision 3 closed two stated limitations.
- Two ordinary synthetic files (`ordinary-opencode-git-diff`, `ordinary-opencode-git-status`) only had their `note` text updated; they use `git diff` and `git status`, so their `allow` expectation is unchanged. No digest pin changed (no test pins the example digest).
- Rows were generated by a throwaway scratchpad script from the plan's row table.

## Stated limitations (for the corpus docstring and STORY-020)

- `cat .e*` (shell glob on a reader head)
- `SELECT pg_terminate_backend(...)` (side-effecting function in a read)
- 8.3 short names and symlinks (`GITHUB~1`)
- `psql -f` and SQL on stdin
- data piped into `tee` / `xargs`
- `Microsoft.PowerShell.Core\Environment::` (POSIX tokenizing eats the backslash)
- `echo env:` is over-blocked as `secret.read` (fails closed)
- heads outside the tables (the 15 plan `unlisted_head` rows) are `shell.unlisted`: `allow` once a deployment allowlists them
- README note for STORY-020: an allowlist entry is trust in the whole head, except the closed table of code-carrying options.

## Acceptance Criteria

- [x] 216 files (>= 30), each with `of:`, all 11 PRD groups covered: `test_the_evasion_corpus_holds_at_least_30_files`, `test_every_prd_technique_group_has_a_file`.
- [x] Never `allow` for user, dba, admin, message names file, decision and rule: `test_no_evasion_variant_is_ever_allowed`; the declared rule: `test_an_evasion_variant_is_decided_by_its_declared_rule`.
- [x] Bad `of:` fails collection: `test_a_malformed_evasion_file_is_a_corpus_error_naming_the_file_and_the_node` (missing, nonexistent, allow target, dba-allow target, non-string).
- [x] Allowed variants fixed in the classifier, not the corpus: findings 1 to 4 above.
