---
story: STORY-009
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-009-shell-tokenizer-and-unclassifiable.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: 4b220ce
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-009: Shell classifier, part 1: reject-scan, shlex tokenization, segments, wrappers and shell.unclassifiable

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-009-shell-tokenizer-and-unclassifiable.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `4b220ce`

## Summary

New pure module `app/services/action_classifiers/shell.py` with two functions that never raise:

- `parse_shell(command, depth=0) -> ShellParse` runs PRD Section 6.8 steps 1–4:
  1. A quote-aware reject-scan of the raw string, which also normalizes it. CR/CRLF become LF, `#` comments and backslash-newline are removed, and quoted or escaped operator characters become Private Use Area sentinels.
  2. shlex tokenization (`posix=True`, `punctuation_chars=";&|<>\n"`, `whitespace_split=True`, `commenters=""`, `\n` out of `whitespace`).
  3. Segmentation on `SEPARATORS`, with redirections pulled out of argv into `Redirect`s.
  4. Assignment and wrapper stripping with strict per-wrapper option tables, head extraction and checks, and `-c` recursion for POSIX shell heads up to `MAX_DEPTH = 3`.
- `classify_shell(command, *, source_tool="")` flattens the parse. For each segment it emits the inline script's classifications first, then the segment's own: `shell.unclassifiable`, or the placeholder `shell.unlisted` (detail = head), which STORY-010 replaces.

The `Redirect` / `Segment` / `ShellParse` interface and the `SEPARATORS` / `REDIRECTS` / `MAX_DEPTH` constants are exactly as the plan's interface section specifies. A test pins the field lists and the constants.

Orchestrator decisions applied (all six as the plan states them):
1. The extended wrapper set (`command`, `builtin`, `exec`, `nice`, `timeout`, `stdbuf`, `setsid`) with strict option tables.
2. A here-document `<<` is unclassifiable.
3. The placeholder `shell.unlisted`.
4. The extra triggers: brace expansion, `$'`/`$"`, glob/paren/`^`/`%`, and unquoted drive-letter heads.
5. The fork bomb is unclassifiable here.
6. The accepted limits.

### shlex verification

The verification was done during planning on the repo's `.venv` (Python 3.12.10). The table is in the plan's "shlex verification" section. The holes it found are each pinned by a test in the "Evasion seeds" section:
- the default `commenters` swallows a newline, and starts a comment mid-word;
- a quoted `;` cannot be told from the operator after shlex;
- an unquoted Windows path loses its backslashes.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Scanner `_scan` (reject + normalize + sentinels), `_brace_expands` | `app/services/action_classifiers/shell.py` | ✅ |
| 2 | `_tokens`, operator normalization, `_split` (segments, redirects, operator errors) | same | ✅ |
| 3 | `_WRAPPERS` tables, `_skip_wrapper_options`, `_basename`, `_head_reason`, `_inline_script`, `_segment`, `parse_shell` | same | ✅ |
| 4 | `classify_shell`, `_flatten` (inline before own; placeholder `shell.unlisted`) | same | ✅ |
| 5 | Tests | `tests/test_action_shell.py` | ✅ |
| 6 | Targeted regression + backend import | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | n/a (no frontend) |
| New tests `tests/test_action_shell.py` | ✅ 232 passed |
| Targeted set (`test_action_shell.py test_action_vocabulary.py test_action_adapters.py test_untouched_app.py`) | ✅ 768 passed, 0 failed, 0 skipped (3.10s) |
| Full suite | deferred to orchestrator (user decision) |
| E2E | ✅ 2/2: the backend import passes, and `classify_shell('npm test && rm -rf build; ls $(x)')` gives one `shell.unclassifiable` with detail `$(` |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/action_classifiers/shell.py` | CREATE | +739 |
| `tests/test_action_shell.py` | CREATE | +574 |
| `.agents/stories/PRD-016-action-policy-rules/STORY-009-*.md` | UPDATE | frontmatter + AC checkboxes |
| `.agents/stories/PRD-016-action-policy-rules/STORY-010-*.md`, `STORY-020-*.md` | UPDATE | orchestrator note edits, committed with this story |
| `.agents/PRDs/PRD-016-action-policy-rules/index.md` | UPDATE | regenerated |
| `.agents/plans/PRD-016-action-policy-rules/completed/STORY-009-*.plan.md` | CREATE (archived) | |

## Deviations from Plan

- **The `_Wrapper` table has an `optional` field** beyond the plan's `flags` / `valued` / `positionals` / `rejects`. It holds options whose value is optional and only ever attached: xargs `-i[R]`, `-e[E]`, `-l[N]`, `--replace[=R]`, sudo `--preserve-env[=list]`, env `--block-signal[=SIG]`. Without it, those options would either eat the command word or be rejected.
- **Wrapper option failure leaves no head.** On `sudo --bogus rm`, the segment has `head = "sudo"` (the last wrapper) and `head_index = len(argv)`, so no word after the bad option is named as the head. The segment stays unclassifiable.
- **`command -v` and `-V` are flags**, so in `command -v NAME`, NAME is read as the head. That is stricter than what bash runs, never looser, and it avoids a non-grantable deny of a common lookup idiom.
- **`sudo -e`/`--edit` (sudoedit) and `sudo -h` are rejected.** sudoedit treats the rest of argv as files, and `-h` is both `--help` and `-h HOST`.
- **Other unclassifiable heads, beyond the plan's list:** `!` (pipeline negation; the head-character check rejects it) and `nice -10` (the legacy numeric form, not in the table). Both fail closed and are listed for STORY-020.
- **Explicit ids for `test_never_raises`.** pytest puts the test id in an environment variable, and Windows refuses one over 32767 characters. The nesting-depth input there is 8, because `shlex.quote` grows the text exponentially and 30 ran out of memory.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_action_shell.py` | AC 1 segments (both story strings, continuations, CR/CRLF, `\|&`, trailing separators), quoted/escaped operators staying arguments (`echo ';'`, `find -exec rm {} \;`, `rm -r ';' -f /`), redirects (fd, `&>`, `>\|`, `< .env`, redirect-only segment); AC 2 head forms incl. quoted Windows path and `.EXE`; AC 3 wrappers/assignments (story's seven + option forms + chained wrappers), wrapper with no command; AC 4 unclassifiable list + detail fragments + depth 3 vs 4; evasion seeds (comment holes, continuation, brace expansion, glob/paren/brace-group heads, `$'…'`, unquoted `C:\…`, `^`, `%VAR%`, bad wrapper options, `env -S`, `-c` with no script, here-docs, operator errors, empty/comment-only, NUL, raw sentinels, fork bomb, `!`); not over-blocked (awk `$(NF)`, backtick in single quotes, `$HOME`, `${GITHUB_TOKEN}`, `find -exec {} +`, `[`/`[[`, trailing comment, continuation, escaped `$(`); S4 join round trips; AC 5 interface field lists/constants/frozen, `args`, inline at depth 1 + option forms, placeholder, ordering, whole-input failure, rule/operation/detail walk, never raises (None, bytes, int, 200 000 chars, 10 001 quotes, 5 000 segments, depth 8), internal error → unclassifiable, purity |

## Acceptance Criteria

- [x] AC 1 segments + joining operators: `test_story_line_segments_with_semicolon`, `test_story_line_segments_with_newline`
- [x] AC 2 head is `rm` for every form: `test_head_is_rm`
- [x] AC 3 wrappers and assignments stripped: `test_wrappers_and_assignments_are_stripped`
- [x] AC 4 unclassifiable, never raises: `test_unclassifiable`, `test_depth_three_is_readable_and_four_is_not`, `test_never_raises`
- [x] AC 5 pure, exposes segments: `test_shell_module_stays_pure`, `test_interface_fields`, `test_parse_shell_returns_segments_and_args`

## Notes for later stories

- STORY-010: fork bomb `:(){ :|:& };:` is `shell.unclassifiable` here (head `:(){`); add the raw-text check for `shell.destructive` as noted in STORY-010.
- STORY-020 README: unclassifiable triggers beyond PRD 6.3's list — `<<` here-documents, brace expansion, `$'…'`/`$"…"`, glob/paren/brace-group/`^`/`%VAR%`/`!` heads, unquoted drive-letter heads, wrapper options outside the tables (`sudo --bogus`, `sudo -e`, `env -S`, `nice -10`).
