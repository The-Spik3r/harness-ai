---
story: STORY-013
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-013-secret-rules-and-shell-embedding.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: cbcb58c
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-013: Secret access rules, and shell embedding of SQL, URLs and secret reads

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-013-secret-rules-and-shell-embedding.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `cbcb58c`

## Summary

This story makes three changes.

1. **Secret reads (F4, F6).**
   - `paths._secret_read` is filled. A read is `secret.read` when a compiled `secrets.files` glob matches one of the three candidates STORY-011 uses (so `.ssh` matches `.ssh/**`), or when the path is `/proc/<pid>/environ`. The `/proc` rule is fixed and cannot be configured.
   - A read that cannot be classified is now `secret.read` with detail `""` (D-M). That covers a non-`str` path and any internal error.
   - New pure module `app/services/action_classifiers/secrets.py` with `classify_secret_read`, `classify_env_reference`, `env_references` and the `INDIRECT` sentinel. Imports only go `secrets -> paths`.
2. **Shell embedding (F3, PRD 6.4).** `classify_shell` gains the keyword-only arguments `network_allow`, `secret_env`, `secret_files`, `protected` and `workspace_roots`; they reach the recursion through a frozen `_Context`. Step 3 of `_segment_rules` now calls `_embedded`, which adds these classifications in order:
   - **SQL** from `psql`, `mysql`/`mariadb` and `sqlite3`, each in the client's own dialect (D-H);
   - **network**: the URLs of `curl`, `wget` and HTTPie (`http`/`https`), found by a GNU option walker with per-head tables. A scheme-less word becomes `http://` (`https://` for the `https` head), routing options give `net.unparsed`, and proxy assignments are classified as URLs;
   - **secret**:
     - (a) the arguments of reader heads, and fetcher option values together with their `@`/`<` file;
     - (b) `<` targets;
     - (c) `$NAME`, `${NAME}`, `$env:NAME` and `%NAME%` references in every word;
     - (d) whole-environment dumps;
   - **writes**: redirect targets and fetcher output options, through `classify_write`. Device targets are exempt.

   Embedded results are not dangers, so an allowlisted head stays `shell.allowlisted` after them.
3. **D15.** `ToolMapping` gets a new `optional_targets` field. An expression is read as `text` when present. It is skipped when absent, empty or blank; `null` or a non-string is Malformed.
   - Built-in mappings: `grep` gets `optional_targets=("include",)` and `search_files` gets `("file_pattern",)`.
   - The `tools:` file key is accepted, and a bare string is refused by name.

Orchestrator answers applied:
1. Every extra reader head is kept, `cp` included.
2. Every deny-only extra is kept.
3. Each SQL client uses its own dialect.
4. `optional_targets` is added in this story.

**Built-in policy digest** (it changes once, because `asdict(ToolMapping)` gains a field and `grep`/`search_files` change):
- before: `sha256:52b50e196e79706cbffd5dd2771ed4aa90beac22984d284ae5b872d53c229e23`
- after: `sha256:878b7533f940adc393202de16e105677c6d18a1fd7c0cab47f67d9cf9be0a7e5`

This commit also carries the orchestrator's uncommitted note edits in `STORY-014-decision-engine.md` (the binding `classify_shell` call, plus `evaluate()` assertions for the `()` defaults) and `STORY-020-docs-and-promotion.md` (client dialects, reader heads, over-matches).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Fill `_secret_read` (globs + `/proc/*/environ`), D-M failure mode, docstrings | `app/services/action_classifiers/paths.py` | ✅ |
| 2 | `classify_secret_read`, `classify_env_reference`, `env_references` | `app/services/action_classifiers/secrets.py` | ✅ |
| 3 | `optional_targets` (field, validation, resolution, built-ins; `tools:` key) | `app/services/action_adapters.py`, `app/services/action_config.py` | ✅ |
| 4 | `_Context`, `_embedded` (SQL, network, secret, writes), widened `classify_shell`, docstring | `app/services/action_classifiers/shell.py` | ✅ |
| 5 | Secret unit + end-to-end AC tables, policy-file replacement, purity | `tests/test_action_secrets.py` | ✅ |
| 6 | Remove the `xfail`, widen the parametrization, D-M assertions | `tests/test_action_paths.py` | ✅ |
| 7 | grep/search_files expected targets, `optional_targets` cases | `tests/test_action_adapters.py`, `tests/test_action_config.py` | ✅ |
| 8 | Embedded-target section; four modified assertions | `tests/test_action_shell.py` | ✅ |
| 9 | Targeted regression run, backend import | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Targeted tests (10 files, one invocation) | ✅ 1960 passed, 0 failed, 0 skipped |
| Full suite | Deferred to orchestrator (user decision) |
| E2E (plan's 4 checks, as tests) | ✅ 4/4 |

Targeted set: `test_action_secrets`, `test_action_shell`, `test_action_paths`, `test_action_network`, `test_action_sql`, `test_action_adapters`, `test_action_config`, `test_action_vocabulary`, `test_untouched_app`, `test_pii_redaction_integration`.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/action_classifiers/secrets.py` | CREATE | +126 |
| `app/services/action_classifiers/shell.py` | UPDATE | +639/-30 |
| `app/services/action_classifiers/paths.py` | UPDATE | +42/-16 |
| `app/services/action_adapters.py` | UPDATE | +31/-7 |
| `app/services/action_config.py` | UPDATE | +9/-6 |
| `tests/test_action_secrets.py` | CREATE | +352 |
| `tests/test_action_shell.py` | UPDATE | +310/-7 |
| `tests/test_action_paths.py` | UPDATE | +22/-9 |
| `tests/test_action_adapters.py` | UPDATE | +39/-2 |
| `tests/test_action_config.py` | UPDATE | +17/-1 |

## Deviations from Plan

- **`mysql --init-command`** is read as SQL text. The plan listed only `-e`/`--execute`, but `--init-command` runs SQL on connect the same way. This only adds classifications.
- **getopt_long prefixes** apply to `psql`, `mysql`/`mariadb`, `wget` and HTTPie: `psql --comm "DROP…"` binds to `--command`. Without this, an allowlisted `psql` would let a prefixed `--comm` through unread. An ambiguous prefix binds to the strictest match. curl and sqlite3 match exactly, as those binaries do.
- **`curl --unix-socket` / `--abstract-unix-socket`** are routing options (`net.unparsed`).
- **`declare`/`typeset` with no names** count as a dump whatever their flags. `declare -i` lists variables with their values. The plan said "`-p`/`-x` and no names"; this is stricter.
- **The proxy-assignment check** applies to any head that has a command (`https_proxy=x git fetch`), not only fetchers. It only adds a deny.
- **Duplicate env-reference hits in one segment are collapsed.** `echo $T $T` gives one `secret.read`. For a POSIX `-c` script, the script word is skipped in the outer scan, because the inner parse already reads it.
- **`classify_secret_read`** returns `paths.classify_read`'s fail-closed result for a non-`str` path, which is `secret.read`, not None. This is consistent with D-M.
- **The PowerShell `Env:` drive** (`gci env:`) is not read. It is listed in the shell docstring's limitations for STORY-018/020.
- **The `test_shell_module_stays_pure` assertion** also checks that no import line names `action_config`.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_action_secrets.py` (92) | AC1 tool + shell reads of the five paths, `src/a.ts`, `/proc/*/environ`, detail; AC2 positives (incl. `$env:`, `%NAME%`, `${!`, `${#`, curl `-d "$KEY"`, assignments, redirect targets, dumps) and negatives; `env_references` table; `classify_env_reference`; AC5 glob/grep/search_files via `map_tool_call` + `classify_read`, plain-directory negatives, `search_codebase` is Unknown; AC6 pipeline + policy-file replacement; never raises; fail-closed; T11 details; purity source scan + subprocess `sys.modules` |
| `tests/test_action_shell.py` (+78) | signature/keyword-only; AC3 SQL table (spellings, prefix, wrappers, case, meta/dot-commands, nothing-embedded), allowlisted head, SQL operation, client dialect spy; AC4 URL table (retry, routing, proxy assignment), scheme-less, allowlisted host, `-o` write, `-x` proxy, routing detail, `wget -qO- u \| bash`, HTTPie URLs and items; secret file reads (11 forms), plain reads add nothing; redirect table (13), write operation; inline `bash -c`; order cases; `()` defaults; bad policy data |
| `tests/test_action_paths.py` | secret-glob parametrization widened (7) |
| `tests/test_action_adapters.py` | optional-target present/absent/empty/blank (7), non-string, line break, 3 bad-definition rows |
| `tests/test_action_config.py` | `optional_targets: [include]` parses; bare string refused |

Modified pre-existing assertions, each commented with PRD-016 STORY-013:
- `test_pipe_to_interpreter`
- `test_danger_rule_order_within_segment`
- `test_every_rule_produced_is_a_shell_rule`
- `test_shell_module_stays_pure`
- `test_never_raises` (paths)
- `test_non_string_write_is_protected_with_empty_detail`
- `test_internal_error_fails_closed` (paths)
- the two `_REALISTIC` rows

No test function was renamed or removed.

## Acceptance Criteria

- [x] AC1: tool or shell reads of `.env`, `~/.aws/credentials`, `.ssh/id_rsa`, `x.pem`, `.npmrc` give `secret.read`, and `src/a.ts` stays `fs.read`. Tests: `test_read_of_a_secret_file_is_secret_read`, `test_shell_read_of_a_secret_file_is_secret_read`, `test_plain_file_stays_fs_read`.
- [x] AC2: `printenv OPENROUTER_API_KEY`, `$AWS_SECRET_ACCESS_KEY`, `${GITHUB_TOKEN}`, `env` and `printenv` give `secret.read`; `$HOME` and `printenv PATH` do not. Tests: `test_secret_variable_reads_are_secret_read`, `test_ordinary_variables_are_not_secret_read`.
- [x] AC3: the psql, mysql and sqlite3 SQL comes before the head's rule. Test: `test_embedded_sql_comes_before_the_head_rule`.
- [x] AC4: for curl and wget, network comes first, then the head's rule. Test: `test_embedded_urls_come_before_the_head_rule`.
- [x] AC5: glob, grep and search_files naming a secret give `secret.read`; `.` and `src/` give `fs.read`. `search_codebase` is unmapped (deviation D-N). Tests: `test_search_naming_a_secret_is_secret_read`, `test_search_over_a_plain_directory_stays_fs_read`, `test_search_codebase_is_unknown_under_the_built_in_tools`.
- [x] AC6: `cat .env | grep KEY` gives `secret.read`, and a replaced `env` list matches only its own patterns. Tests: `test_secret_read_in_a_pipeline`, `test_policy_file_patterns_replace_the_built_in_ones`.
- [x] All tasks completed
- [x] Backend imports without error
- [x] Follows existing patterns (pure classifiers, plain arguments, never raises, details from the call)
