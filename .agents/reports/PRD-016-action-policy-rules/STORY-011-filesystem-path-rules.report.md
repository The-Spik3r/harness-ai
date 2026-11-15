---
story: STORY-011
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-011-filesystem-path-rules.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: pending
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-011: Filesystem path rules — normalization, workspace containment, protected paths

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-011-filesystem-path-rules.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `pending`

## Summary

New pure module `app/services/action_classifiers/paths.py` (PRD-016 F4, Section 6.5, D11, T6, Risk 4):

- `normalize_path(path) -> NormalizedPath`: a lexical rewrite. It turns `\` into `/` and lowercases only the drive letter. The anchor is one of `""`, `/`, `//` (UNC), `c:/` or `c:`. It collapses `/`, drops `.`, and resolves `..`, clamping at an absolute anchor and keeping a leading `..` on a relative path (which then escapes). A `~` first segment stays literal and is never popped. It touches no filesystem.
- `classify_write(path, protected, workspace_roots=(), *, source_tool="") -> Classification`: protection is checked first. Each compiled glob is `.search()`ed on three candidates: the normalized text, the Windows-folded text (NTFS stream suffix and trailing `.`/space removed), and the directory probe `text + "/\x00"`. Containment comes second and compares segments (case-exact except the drive letter, so it fails closed). It returns exactly one `fs.write_protected`, `fs.write_in_workspace` or `fs.write_outside_workspace`.
- `classify_read(path, secret_files=(), *, source_tool="") -> Classification`: returns `fs.read`, through a named `_secret_read` hook that returns `None` until STORY-013 fills it in.
- Nothing raises. A non-`str` write, or an internal error on a write, gives `fs.write_protected` with detail `""`. The detail is taken from the call and capped at 32 characters, keeping the tail (T11).

Orchestrator decisions applied:
1. Single `Classification` return.
2. Plain arguments, with `protected` required.
3. The hook belongs to STORY-013.
4. Both the Windows fold and the directory probe are kept.
5. A failed write is `fs.write_protected`.
6. Containment is case-exact except the drive letter.
7. Device targets are left to STORY-013.
8. Neither `PurePosixPath` nor the filesystem is used, and the residual gaps are in the docstring.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `NormalizedPath`, `normalize_path`, `classify_write`, `classify_read`, helpers, STORY-013 hook, module docstring | `app/services/action_classifiers/paths.py` | ✅ |
| 2 | Table-driven tests: AC1-5, T6 rows, detail/T11, vocabulary walk, never-raises, purity, import census | `tests/test_action_paths.py` | ✅ |
| 3 | Guard runs, backend import, E2E | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | n/a (no frontend) |
| `tests/test_action_paths.py` | ✅ 218 passed, 2 xfailed (strict; STORY-013's pending secret-read cases) |
| Targeted set (`test_action_paths.py test_action_vocabulary.py test_untouched_app.py`) | ✅ 236 passed, 2 xfailed, 0 failed, 0 skipped (1.42s) |
| Full suite | Deferred to the orchestrator (user decision) |
| E2E | ✅ 2/2 (below) |

E2E:
- `classify_write("C:\\Repo\\.env", BUILT_IN_POLICY.protected_paths.compiled, ("C:/Repo",), source_tool="editor")` returned `Classification(rule='fs.write_protected', operation=Operation(kind='fs_write', target='C:\\Repo\\.env', source_tool='editor'), detail='.env')`.
- `classify_write("~/.bashrc", P, (), source_tool="bash").rule` returned `fs.write_outside_workspace`.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/action_classifiers/paths.py` | CREATE | +271 |
| `tests/test_action_paths.py` | CREATE | +412 |
| `.agents/plans/PRD-016-action-policy-rules/completed/STORY-011-filesystem-path-rules.plan.md` | CREATE (archived plan) | +312 |
| `.agents/stories/PRD-016-action-policy-rules/STORY-011-filesystem-path-rules.md` | UPDATE (frontmatter, ACs ticked, orchestrator's AC4 fix) | small |
| `.agents/stories/PRD-016-action-policy-rules/STORY-013-*.md`, `STORY-014-*.md`, `STORY-018-*.md`, `STORY-020-*.md` | UPDATE (orchestrator's notes, committed as instructed) | +1 each |
| `.agents/PRDs/PRD-016-action-policy-rules/index.md` | UPDATE (regenerated) | small |

## Deviations from Plan

- **`~` is never popped by `..`.** This addition is not in the plan. `~/../x` normalizes to `~/x` instead of `x`. Without it, a lexical pop would turn a home-relative path into the in-workspace relative `x`, which is a containment bypass. It is pinned by test rows in `test_normalize_path` and `test_containment`.
- **Purity test:** the sibling assertion `"Path(" not in source` is replaced by a regex that allows this module's own `NormalizedPath(` but refuses `Path(`/`PurePosixPath(`, plus `"pathlib" not in source`. The pinned app import line is `from app.services.action_classifiers import Classification, Operation`, because `RuleId` is not used.
- Extra test rows beyond the plan: `.git./config`, `.gitlab-ci.yml`, `deploy/server.key`, `\\?\C:\Repo\.env`, `/HOME/dev/projects/x`, `//srv/share/x` against the root `//srv/share`, the near miss `.github/README.md`, and `protected` being a required argument.

## Residual gaps (in the module docstring, for STORY-018 / STORY-020)

The classifier cannot see symlinks, hard links, 8.3 short names, mount points or the agent's working directory. Containment also does not fold Win32 traversal oddities (`a/.../b`, `.. /x` stay literal names, so they count as relative and inside). A cheap fail-closed option would be to treat a relative path with an all-dots/spaces segment as outside. That was not implemented, to stay with the plan, and is left for the orchestrator to decide. `id_*` over-matches `src/id_utils.py`, inherited from the PRD and pinned by a test row.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_action_paths.py` | `test_normalize_path`, `test_anchor_and_parts`, `test_tilde_stays_a_literal_segment`, `test_absolute_and_escape_flags`, `test_normalize_and_classify_touch_no_filesystem`, `test_containment`, `test_bad_root_entries_are_skipped`, `test_protected_paths`, `test_near_misses_are_not_protected`, `test_protection_is_checked_before_containment`, `test_protected_detail_is_the_matched_tail`, `test_detail_is_never_a_root`, `test_detail_is_capped_keeping_the_tail`, `test_write_operation_carries_the_input_as_given`, `test_read_is_fs_read`, `test_read_of_a_secret_glob_is_secret_read` (xfail strict), `test_every_rule_produced_is_a_path_rule`, `test_never_raises`, `test_non_string_write_is_protected_with_empty_detail`, `test_bad_protected_entries_are_skipped`, `test_protected_is_a_required_argument`, `test_internal_error_fails_closed`, `test_paths_module_stays_pure`, `test_importing_paths_loads_no_settings` |

## Acceptance Criteria

- [x] AC1: `normalize_path` gives the AC's outputs and touches no filesystem. Tests: `test_normalize_path`, `test_tilde_stays_a_literal_segment`, `test_normalize_and_classify_touch_no_filesystem`.
- [x] AC2: containment with no roots and with `/home/dev/projects`. Test: `test_containment`.
- [x] AC3: the nine paths are `fs.write_protected` with and without a root, and protection is checked before containment. Tests: `test_protected_paths`, `test_protection_is_checked_before_containment`.
- [x] AC4: a read is `fs.read`. The secret hook is a placeholder, and its test is `xfail(strict=True)` for STORY-013. Tests: `test_read_is_fs_read`, `test_read_of_a_secret_glob_is_secret_read`.
- [x] AC5: the module reads no settings and does no I/O. Tests: `test_paths_module_stays_pure`, `test_importing_paths_loads_no_settings`.
