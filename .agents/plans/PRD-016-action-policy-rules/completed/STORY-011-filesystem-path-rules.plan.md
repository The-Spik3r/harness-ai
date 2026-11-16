---
story: STORY-011
prd: PRD-016
slug: filesystem-path-rules
title: Filesystem path rules — normalization, workspace containment, protected paths
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-016-action-policy-rules
created: 2026-11-15
---

# Plan: Filesystem path rules — normalization, workspace containment, protected paths

## Summary

Add the pure path classifier `app/services/action_classifiers/paths.py`, which implements PRD-016 F4 and Section 6.5. `normalize_path(path)` rewrites a path lexically into a `NormalizedPath`: it turns `\` into `/`, lowercases the drive letter, keeps a literal `~` as the first segment, collapses repeated `/`, drops `.`, and resolves `..`. It reads no filesystem and resolves no symlinks. `classify_write(path, protected, workspace_roots=(), *, source_tool="")` checks the protected globs first. If none matches, it checks containment by comparing normalized segments. It returns exactly one `fs.write_protected`, `fs.write_in_workspace` or `fs.write_outside_workspace`. `classify_read(path, secret_files=(), *, source_tool="")` returns `fs.read`. It also has a named secret hook that returns `None` until STORY-013 fills it in. That story also routes shell output redirects through `classify_write`. The globs arrive already compiled from `action_config` (`policy.protected_paths.compiled`), and the module does not translate them again. Roots and globs are plain arguments, as `classify_shell`'s `shell_allow` is. No function raises. New tests in `tests/test_action_paths.py` cover one case per T6 trick, the five ACs, purity, and never-raises.

## User Story

As a security admin
I want every write classified against the workspace and the protected-path list after the path is normalized
So that `..`, mixed separators and case cannot reach `.env`, credentials or CI config.

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-011-filesystem-path-rules.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md` sections 6.3 (filesystem rows, lines 240-243), 6.5 (lines 260-268), 7 F4 (line 490), 9.2 T6 (line 548), 14 Risk 4 (line 708), 15 D11 (line 734)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/services/action_classifiers/` (new module), tests |
| Story | STORY-011 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design`. This story has no UI, and the story's `skills: []` agrees | — |

---

## Patterns to Follow

### Module shape: docstring cites PRD and decisions, pure, never raises, keyword-only `source_tool`
```python
# SOURCE: app/services/action_classifiers/sql.py:314-336
def classify_sql(
    statement: str, dialect: Optional[str], *, source_tool: str = ""
) -> tuple[Classification, ...]:
    """Classify every statement in `statement`, in order (PRD-016 F2). Never raises.
    ...
    """
    target = statement if isinstance(statement, str) else ""
    op = Operation(kind="sql", target=target, source_tool=source_tool)
    try:
        if not isinstance(statement, str):
            return (Classification("sql.unparsed", op, ""),)
        return tuple(_classify_text(statement, dialect, op, 0))
    except Exception:
        return (Classification("sql.unparsed", op, _head(statement)),)
```

### Policy data as plain arguments, not the policy object or settings
```python
# SOURCE: app/services/action_classifiers/shell.py:1286-1297
def classify_shell(command: str, shell_allow=(), *, source_tool: str = "") -> tuple[Classification, ...]:
    """... `shell_allow` is the policy's `shell.allow` entries (6.6); the default `()`
    allowlists nothing, the built-in policy's value. ..."""
```
`shell.py:126-128` states it: "The `shell_allow` list arrives as an argument from the caller, never through `settings` or `action_config`." `action_config` imports `settings` (`action_config.py:47`), so a classifier cannot import `ActionPolicy` without breaking purity.

### The glob contract to consume (never re-translate)
```python
# SOURCE: app/services/action_config.py:134-160 (Globs docstring), 258-259
def _compile_path_glob(glob: str) -> re.Pattern:
    return re.compile("(?:^|/)" + _translate_glob(glob) + "$", re.IGNORECASE)
```
"Call `.search()` on a normalized, `/`-separated path. A glob therefore matches at any depth." The built-in protected list is at `action_config.py:303-317`. `ActionPolicy.workspace_roots` and `ActionPolicy.protected_paths` are at `action_config.py:192-193`. Roots are "stored as written; STORY-011 normalizes both sides for containment" (`action_config.py:594-612`, `_check_workspace_root`, which also defines "absolute" lexically: `/...`, UNC `//...`, or `C:/...` after `\` becomes `/`).

### Vocabulary
`app/services/action_classifiers/__init__.py:62-66` (the `fs.*` RuleIds), `:107-131` (`Operation(kind, target, source_tool)`, `Classification(rule, operation, detail)`; detail is the matched fragment of the *call*, never a configured value, T11).

### Detail cap
`shell.py:170-171` `_cap(text) -> text[:_HEAD_MAX]` (32), and `sql.py:134` `_HEAD_MAX = 32`.

### Tests
```python
# SOURCE: tests/test_action_shell.py:18-21 (env setdefaults before app imports), 897-911 (purity)
def test_shell_module_stays_pure():
    source = inspect.getsource(shell)
    assert "settings" not in vars(shell)
    assert "open(" not in source
    assert "Path(" not in source
    ...
    assert app_imports == ["from app.services.action_classifiers import Classification, Operation, RuleId"]
```
- Subprocess import census: `tests/test_action_adapters.py:623-640` (`sys.modules` filtered to `app.*` after a fresh import).
- Never-raises with explicit ids: `tests/test_action_shell.py:874-887`. Internal error via monkeypatch: `:897-903`.
- Every produced rule is in the vocabulary: `tests/test_action_shell.py:862-871`.
- The compiled built-in policy for real globs: `from app.services.action_config import BUILT_IN_POLICY`. Importing it in the *test* is fine. Only the module under test must stay pure.

---

## Design decisions (for the orchestrator to confirm)

1. **Signatures** (deviation from the story's `classify_write(path, policy)`). The roots and globs are plain arguments, following `classify_shell(command, shell_allow, ...)` (orchestrator instruction, and `shell.py:126-128`). Passing the `ActionPolicy` would need `action_config` imported, or duck typing:
   - `normalize_path(path: str) -> NormalizedPath`
   - `classify_write(path: str, protected, workspace_roots=(), *, source_tool: str = "") -> Classification`. `protected` is an iterable of compiled `re.Pattern` (`policy.protected_paths.compiled`), and it is **required**. A default of `()` would quietly protect nothing, and the built-in list cannot be imported here. `workspace_roots` defaults to `()`, the built-in value.
   - `classify_read(path: str, secret_files=(), *, source_tool: str = "") -> Classification`. `secret_files` is `policy.secrets.files.compiled`. It is accepted now and passed to the hook, so the signature does not change when STORY-013 fills it in.
   - STORY-014 calls them as `classify_write(op.target, policy.protected_paths.compiled, policy.workspace_roots, source_tool=op.source_tool)`. STORY-013 calls the same thing for each output-redirect target (the hook at `shell.py:1230-1232`).
2. **Return a single `Classification`, not a tuple.** A path write has exactly one outcome (protection before containment, Section 6.5 item 5), and F5's `classify_url` is also specified to return one `Classification` (PRD line 494). STORY-014 wraps the result in a tuple. The orchestrator may prefer `tuple[...]` for uniformity with sql and shell. The change is mechanical.
3. **`NormalizedPath`** is a frozen dataclass with `anchor: str` and `parts: tuple[str, ...]`, plus the properties `text`, `is_absolute`, `escapes` and `home`. `__str__` returns `text`.
   - `anchor`: `""` for a relative path, `"/"` for a POSIX absolute path, `"//"` for UNC (exactly two leading separators are kept, as `PurePosixPath` and POSIX do; three or more collapse to `/`), `"c:/"` for a drive-absolute path (letter lowercased), and `"c:"` for a drive-relative path `C:x`.
   - `parts`: the segments with `""` and `.` removed. `..` pops a segment. On an absolute anchor it clamps at the anchor (`/../etc` becomes `/etc`, lexically what POSIX does). On a relative path a `..` that cannot pop is kept as a leading `..`, which is what `escapes` means.
   - `text`: `anchor + "/".join(parts)`, or `"."` for an empty relative path, so `./` normalizes to `.`, the adapters' default target (S8).
   - `home`: a relative path whose first segment starts with `~` (`~`, `~user`). It is left literal, as Section 6.5 item 1 says. The AC expects `~/x` to have the first segment `~`.
   - This matches AC 1 exactly: `src\a.ts` becomes `src/a.ts`, `C:\Repo\x` becomes `c:/Repo/x`, `a//b/./c` becomes `a/b/c`, `a/b/../c` becomes `a/c`, and `~/x` has `parts[0] == "~"`.
4. **No `PurePosixPath`** (deviation from the story's technical note). It does not resolve `..`, it does not know drive letters, and its only work here would be the split and the `//` anchor, which take one line each by hand. Avoiding pathlib also means the sibling purity assertion `"Path(" not in source` (`tests/test_action_shell.py:902`) applies unchanged. If the orchestrator wants `PurePosixPath`, the purity test must allow it explicitly instead.
5. **Containment** (Section 6.5 items 2-4, D11), checked only when no protected glob matched:
   - A relative path, not home and not escaping, is in the workspace.
   - A relative path that escapes is outside.
   - A home (`~`) path is outside ("no workspace root contains `~`").
   - A drive-relative `c:` path is outside. Its meaning depends on a per-drive working directory the harness cannot see, so it fails closed.
   - An absolute path is inside only when, for some root `r = normalize_path(root)` with `r.is_absolute`, `p.anchor == r.anchor` and `p.parts[:len(r.parts)] == r.parts`. The segments are compared, not string prefixes, so `/home/dev/projects2/x` is not under `/home/dev/projects`. A root that normalizes to a non-absolute path, or that is not a `str`, is skipped (config already refuses it). A root of `/` contains every POSIX absolute path. That is the operator's choice and is written down as such.
   - **The comparison is case-sensitive except the drive letter.** Folding case would let `/HOME/dev/projects/x` count as inside on a case-sensitive Linux disk, which loosens the check. Being exact can only deny a Windows path written in another case (`c:/repo` against root `C:/Repo`), which is the grantable `fs.write_outside_workspace`, so it fails closed. Protection, by contrast, is case-insensitive (T6, from the compiled globs).
   - UNC against POSIX: `//srv/share/x` is not under the root `/srv/share`, because the anchors differ. The `\\?\C:\x` form becomes the anchor `//` with parts `("?", "C:", "x")`, so it is not under `C:/...` and is outside. That fails closed and still gets checked for protection.
6. **Protection** is checked first (Section 6.5 item 5), with `pattern.search(candidate)` for each compiled glob. There are three candidates, and any match makes the path `fs.write_protected`. Matching more only adds non-grantable denials, so every candidate can only make the result stricter:
   - (a) `p.text`. This alone covers the AC: `.env`, `./.env` and `config/../.env` all normalize to `.env`, `.ENV.local` matches through IGNORECASE, the absolute `.../app/.env.local` matches at any depth, and so do `.github/workflows/ci.yml`, `.git/config`, `id_rsa` and `x.pem`. Verified against `BUILT_IN_POLICY` in this session.
   - (b) **The Windows-folded text**: each segment with its NTFS stream suffix (`:...`) removed and trailing `.` and space stripped. Win32 opens `x.pem.`, `x.pem::$DATA` and `.git./config` as `x.pem` and `.git/config`, and without the fold `x.pem.` does not match `*.pem` (verified). Segments that fold to empty are dropped. The anchor's `c:` is not a segment and is left alone. This goes beyond the AC and is listed under T6.
   - (c) **`text + "/\x00"`**: the directory itself. `.git/**` needs at least one segment after `.git`, so a write targeting `.git` or `.github/workflows` (an `apply_patch` `*** Move to: .git`, or a redirect onto the directory) would otherwise miss (verified: `.git` matches nothing). `\x00` cannot be in a real target (the adapters refuse NUL, `action_adapters.py:416-425`), and no built-in glob matches a bare `\x00` segment. This also goes beyond the AC. Drop it if the orchestrator prefers the strict reading.
7. **`detail`** (T11) is always taken from the call's normalized path and never from a root or glob.
   - `fs.write_protected`: the matched text with its leading `/` stripped (`.env.local`, `.github/workflows/ci.yml`). For candidate (c) it is the path itself.
   - The other rules: `p.text`.
   - Capped at 32 characters, **keeping the end** (`text[-32:]`). The tail of a path is what identifies it. `shell._cap` keeps the head, because a command's head is what identifies a command.
   - `Operation(kind, target=path as given, source_tool)` with kind `"fs_write"` or `"fs_read"`: the whole input as the target, as in `sql.py:52-55` and `shell.py:121-123`.
8. **Never raises.** A non-`str` path, or any `Exception` inside, is handled as follows. `classify_write` returns `fs.write_protected` with detail `""`. That rule is non-grantable, which is the strictest outcome available, because there is no `fs.unparsed`. `classify_read` returns `fs.read`, and later whatever STORY-013's hook decides. `normalize_path` on a non-`str` returns `NormalizedPath("", ())`; its only callers are the classifiers above. `BaseException` is not caught (sibling convention). The adapters already guarantee a non-empty, single-line `str` (`action_adapters.py:416-425`), so these paths exist only for T9 hygiene.
9. **The secret hook** (AC 4). A module-private function `_secret_read(normalized, secret_files, op) -> Optional[Classification]` returns `None` and carries a named comment, `# STORY-013's hook: classify_secret_read(...) goes here (PRD F4: a read of a secret glob is secret.read, not fs.read)`, in the style of `shell.py:1230-1232`. `classify_read` returns the hook's result when it is not `None`, and `fs.read` otherwise. The test for `.env` is `pytest.mark.xfail(strict=True, reason="STORY-013 fills the secret hook")`. `strict` makes the suite fail once STORY-013 makes it pass, so STORY-013 has to remove the marker. **The story text says "STORY-012 fills in", but STORY-013 owns `secrets.py` and the hook** (STORY-013 AC 1 says "completing STORY-011's hook"). The plan follows STORY-013. Flag this to the orchestrator.
10. **Symlinks are not resolved** (Risk 4). The module docstring says so, together with the other things the module cannot see: 8.3 short names (`GITHUB~1`), hard links, a mount point under a root, and the agent's working directory (Section 6.5's opening sentence).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/action_classifiers/paths.py` | CREATE | `NormalizedPath`, `normalize_path`, `classify_write`, `classify_read`, the private helpers, and the STORY-013 hook |
| `tests/test_action_paths.py` | CREATE | ACs 1-5, one case per T6 trick, never-raises, the rule-vocabulary walk, purity, and the import census |
| `.agents/stories/PRD-016-action-policy-rules/STORY-011-filesystem-path-rules.md` | UPDATE (planner) | `plan`, `status: in-progress`, `updated` |
| `.agents/PRDs/PRD-016-action-policy-rules/index.md` | UPDATE (regenerated) | board |

No change to `action_config.py`, `__init__.py`, `shell.py` or `action_adapters.py`. The `action_classifiers/__init__.py` docstring already says STORY-008..013 add classifiers.

---

## Tasks

### Task 1: Create `app/services/action_classifiers/paths.py`

- **File**: `app/services/action_classifiers/paths.py`
- **Action**: CREATE
- **Implement**:
  - The module docstring, mirroring `sql.py:1-58` and `shell.py:1-128`. Title: "The path classifier: normalization, workspace containment, protected paths (PRD-016 Sections 6.3, 6.5, F4)". Content:
    - The normalization rules (decision 3) and the containment rules (decision 5, D11).
    - "protection before containment" (6.5 item 5) and the three protection candidates (decision 6, T6).
    - The case policy: protection is case-insensitive through the compiled globs, and containment is exact except the drive letter, failing closed.
    - The glob contract consumed from `action_config.Globs` (STORY-006 plan decision 6), and that this module does not translate globs.
    - **Symlinks are not resolved (Risk 4)**, and the other limits from decision 10.
    - The STORY-013 hook, and that STORY-013 routes output redirects here as `fs_write`.
    - `detail` and `Operation` (decision 7).
    - "Pure (PRD-016 Section 6.12): no settings, no I/O, no filesystem; roots and globs are arguments."
  - Imports: `re`, `from dataclasses import dataclass`, `from typing import Iterable, Optional`, and `from app.services.action_classifiers import Classification, Operation, RuleId`. Import `RuleId` only if it is used in an annotation. The purity test pins the exact line, so keep it the same as `shell.py`'s or adjust the test to match. No `os`, no `pathlib`, no `open`.
  - Constants: `_DETAIL_MAX = 32`; `_DRIVE = re.compile(r"([A-Za-z]):(/?)(.*)", re.DOTALL)` (match at the start of the slashed text); `_DIR_PROBE = "/\x00"`; and for the Windows fold, a strip of trailing `". "` and a split on the first `:`.
  - `@dataclass(frozen=True) class NormalizedPath` with `anchor`, `parts`, and the properties `text`, `is_absolute` (`anchor in ("/", "//") or anchor.endswith(":/")`; a drive-relative `c:` is not absolute), `escapes`, and `home`, plus `__str__`. Docstring with the anchor table.
  - `normalize_path(path)`:
    1. Non-`str` returns `NormalizedPath("", ())`.
    2. `s = path.replace("\\", "/")`.
    3. Anchor: if `_DRIVE` matches, the anchor is `letter.lower() + ":" + ("/" if slash else "")` and the rest is group 3. Otherwise, if `s` starts with exactly `//` and not `///`, the anchor is `//`. Otherwise, if it starts with `/`, the anchor is `/`. Otherwise it is `""`.
    4. Fold the rest: skip `""` and `.`; on `..`, pop when the last kept part is not `..` (and, for a relative path, not a leading `..`), clamp when anchored and empty, and append `..` when relative and empty or already escaping.
    5. Return the dataclass.
  - `_cap_tail(text) -> text[-_DETAIL_MAX:]`.
  - `_windows_fold(parts) -> tuple[str, ...]`: each part split on the first `:` (`part.split(":", 1)[0]`), then `rstrip(". ")`, with empty results dropped. `.` and `..` segments are already resolved, so `rstrip` cannot turn a real name into `..`. A part made only of dots and spaces (`...`) folds to empty and is dropped. That is only for protection matching; see the risk table.
  - `_protected_match(p, protected) -> Optional[str]`:
    1. Build the candidates `(p.text, folded_text, p.text + _DIR_PROBE)`, where `folded_text` uses the same anchor.
    2. For each compiled pattern and each candidate, if `m = pattern.search(candidate)`, return the detail. The detail is the matched text with its leading `/` stripped and the `\x00` probe removed; when stripping leaves it empty, use `p.text`.
    3. Return `None` when nothing matches.
    4. Skip a non-`re.Pattern` entry (`hasattr(pattern, "search")`) rather than raising.
  - `_contained(p, workspace_roots) -> bool`, per decision 5. Normalize the roots inside, skipping a non-`str` root or one that does not normalize to an absolute path.
  - `classify_write(path, protected, workspace_roots=(), *, source_tool="")`:
    1. `op = Operation("fs_write", path if isinstance(path, str) else "", source_tool)`.
    2. In a `try`: return `fs.write_protected` for a non-`str` path. Otherwise normalize, try `_protected_match` (which returns `fs.write_protected` with the detail), then return `fs.write_in_workspace` when `_contained`, else `fs.write_outside_workspace`, with detail `_cap_tail(p.text)`.
    3. `except Exception:` return `fs.write_protected` with detail `""`.
    4. Docstring "(PRD-016 F4, Section 6.5). Never raises." It names the STORY-014 and STORY-013 call shapes (decision 1).
  - `_secret_read(p, secret_files, op) -> Optional[Classification]`: `return None`, with the STORY-013 hook comment.
  - `classify_read(path, secret_files=(), *, source_tool="")`:
    1. `op = Operation("fs_read", ...)`.
    2. In a `try`: normalize, `hit = _secret_read(...)`, then return `hit` or `Classification("fs.read", op, _cap_tail(p.text))`.
    3. `except Exception:` return `fs.read` with detail `""`. Comment it: STORY-013 decides whether a failed read becomes `secret.read`, and the exception path cannot be reached for a `str` input.
- **Mirror**: `app/services/action_classifiers/sql.py:314-336`, `app/services/action_classifiers/shell.py:1286-1313`
- **Validate**: `OPENROUTER_API_KEY=x ADMIN_TOKEN=y .venv/Scripts/python -c "from app.services.action_classifiers.paths import normalize_path as n; print(n('C:\\\\Repo\\\\x'))"` prints `c:/Repo/x`

### Task 2: Create `tests/test_action_paths.py`

- **File**: `tests/test_action_paths.py`
- **Action**: CREATE
- **Implement**:
  - The header docstring: "PRD-016 STORY-011: the path classifier (Sections 6.3 filesystem rows, 6.5, F4; D11; T6; Risk 4)". It says the tests are table-driven, transcribed from the AC and T6, and are seeds for STORY-018's path-trick evasion group. Not covered: secret reads (STORY-013), redirects (STORY-013), and folding (STORY-014).
  - Env setdefaults before the app imports (`tests/test_action_shell.py:18-21`). `P = BUILT_IN_POLICY.protected_paths.compiled`, `ROOTS = ("/home/dev/projects",)`, `BS = "\\"`. Helper `_w(path, roots=())` returns `classify_write(path, P, roots).rule`.
  - **AC 1**, parametrized `test_normalize_path`: `src\a.ts` -> `src/a.ts`, `C:\Repo\x` -> `c:/Repo/x`, `a//b/./c` -> `a/b/c`, `a/b/../c` -> `a/c`. Plus `test_tilde_stays_a_literal_segment` (`normalize_path("~/x").parts[0] == "~"` and `.home`). Extra rows:
    - `./` -> `.`
    - `/../etc` -> `/etc`
    - `../../etc/passwd` -> escapes
    - `a/../../b` -> `../b`, escapes
    - `\\srv\share\x` -> anchor `//`
    - `///x` -> `/x`
    - `C:x` -> anchor `c:`
    - `c:/a/../../b` -> `c:/b`
    - a trailing `/` removed (`.git/config/` -> `.git/config`)
  - **AC 1 "touches no filesystem"** `test_normalize_and_classify_touch_no_filesystem`: monkeypatch `builtins.open`, `os.stat`, `os.lstat`, `os.path.realpath`, `os.path.exists`, `os.readlink`, `pathlib.Path.resolve` and `pathlib.Path.exists` to raise `AssertionError`. Then run normalize, write and read over the whole case table.
  - **AC 2**: `src/a.ts` -> `fs.write_in_workspace`; `../../etc/passwd` -> outside; `/etc/hosts` -> outside (no roots); with `ROOTS`, `/home/dev/projects/app/x.ts` -> in, and `/home/dev/projects2/x` -> outside. Extra rows (decision 5):
    - the root itself `/home/dev/projects` -> in
    - `/home/dev/projects/../other/x` -> outside
    - `~/x` -> outside
    - `C:x` -> outside
    - Windows: root `C:\Repo`, then `c:/Repo/src/a.ts` and `C:\Repo\src\a.ts` -> in, and `C:/RepoX/a` -> outside
    - `c:/repo/a` against root `C:/Repo` -> outside (case-exact, fails closed)
    - `//srv/share/x` against root `/srv/share` -> outside
    - `\\?\C:\Repo\a` against root `C:/Repo` -> outside
    - root `/` -> `/etc/hosts` in (the operator's choice)
    - a bad root entry (`None`, `"rel"`) is skipped without raising
  - **AC 3**, parametrized over `.env`, `./.env`, `config/../.env`, `.ENV.local`, `/home/dev/projects/app/.env.local`, `.github/workflows/ci.yml`, `.git/config`, `id_rsa`, `x.pem`, each with `roots=()` and `roots=ROOTS`, all `fs.write_protected`. Plus `test_protection_is_checked_before_containment`: `/home/dev/projects/app/.env.local` is protected with `ROOTS`, while `/home/dev/projects/app/x.ts` is in.
    - Extra T6 rows: `src\..\.ENV`, `C:\Repo\.git\config`, `.GitHub/Workflows/CI.yml`, `a/.ssh/id_ed25519`, `x.pem.` and `x.pem::$DATA` (the fold), `.git` and `.github/workflows` (the dir probe), `../.env`, `~/.ssh/config`, `.circleci/config.yml`, `Jenkinsfile`.
    - Not protected (stays in workspace): `src/env.ts`, `.gitignore`, `x.pem.txt`, `docs/github/workflows.md`.
  - **detail** (T11): the protected detail is `.env.local` for the absolute case. The detail is never the root (`"/home/dev/projects" not in detail` for the outside cases with `ROOTS`). The detail is at most 32 characters and keeps the tail (a 100-character path ending in `/x.ts` has detail ending `x.ts`). `operation == Operation("fs_write", <input as given>, "write")`.
  - **AC 4**: `classify_read("src/a.ts", BUILT_IN_POLICY.secrets.files.compiled, source_tool="read")` is `Classification("fs.read", Operation("fs_read", "src/a.ts", "read"), "src/a.ts")`. `test_read_of_a_secret_glob_is_secret_read` over `.env` and `~/.aws/credentials` is marked `@pytest.mark.xfail(strict=True, reason="PRD-016 STORY-013 fills classify_read's secret hook")`. Also `classify_read(".")` is `fs.read` (the S8 default target).
  - **Rule vocabulary walk** (`tests/test_action_shell.py:862-871` shape): over every case, write results are in `{fs.write_in_workspace, fs.write_outside_workspace, fs.write_protected}`, read results in `{fs.read, secret.read}`, all in `RULE_IDS`, and the detail is a `str` of at most 32 characters.
  - **Never raises**: `None`, `b".env"`, `123`, `"a/" * 100_000`, `"../" * 50_000`, `"\x00"`, with explicit ids (the Windows env-var length note, `tests/test_action_shell.py:880-882`). A non-`str` write is `fs.write_protected` with detail `""`. Bad `protected` entries (`[None, "x"]`) do not raise. Internal error: monkeypatch `paths.normalize_path` to raise, and then `classify_write("src/a.ts", P)` is `fs.write_protected` and `classify_read` is `fs.read`.
  - **AC 5**:
    - `test_paths_module_stays_pure`: copy of `tests/test_action_shell.py:897-911`, plus `"os." not in source` and `".resolve(" not in source`.
    - `test_importing_paths_loads_no_settings`: the subprocess census in the shape of `tests/test_action_adapters.py:623-640`. Expected: `["app", "app.services", "app.services.action_classifiers", "app.services.action_classifiers.paths"]`.
- **Mirror**: `tests/test_action_shell.py`, `tests/test_action_adapters.py:601-640`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_paths.py -q -p no:cacheprovider`

### Task 3: Guard runs

- Run in one invocation: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_paths.py tests/test_action_vocabulary.py tests/test_untouched_app.py -q -p no:cacheprovider`.
  - `test_action_vocabulary.py` is the package purity guard.
  - `test_untouched_app.py` is the brief's guard for touching `app/`. It pins test and theme suites, not `app/` paths, so it is expected to pass unchanged.
- `.venv/Scripts/python -c "from app.main import app; print('OK')"`
- Full suite: deferred to the orchestrator (user decision).

---

## End-to-End Tests

- [ ] The STORY-014 call shape works against the real built-in policy, in a REPL or a test: `classify_write("C:\\Repo\\.env", BUILT_IN_POLICY.protected_paths.compiled, ("C:/Repo",), source_tool="editor")` returns `fs.write_protected` with detail `.env`.
- [ ] The STORY-013 redirect shape: `classify_write("~/.bashrc", P, (), source_tool="bash").rule == "fs.write_outside_workspace"`.
- [ ] No UI and no endpoint. Nothing calls this module until STORY-013/014.

## Validation

```bash
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_paths.py tests/test_action_vocabulary.py tests/test_untouched_app.py -q -p no:cacheprovider
.venv/Scripts/python -c "from app.main import app; print('OK')"
```

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Symlinks, hard links and 8.3 short names (`GITHUB~1`) reach a protected path or leave the workspace without being seen | Not answerable without the client's disk (Risk 4, Section 9.4). Stated in the module docstring, and passed to STORY-020's README and STORY-018's "not read" list |
| `/dev/null`, `/dev/stderr` and `NUL` as redirect targets would be `fs.write_outside_workspace` once STORY-013 routes redirects here, so `cmd 2>/dev/null` would be denied | **Flag for STORY-013** (out of scope here): exempt the device targets, or treat `>&N` as not a file, before calling `classify_write`. This story does not special-case them, because the PRD 6.3 table does not name them |
| Case-exact containment denies a Windows path written in a different case than the root | It fails closed onto the grantable `fs.write_outside_workspace`, and the Actions view shows it. Folding would loosen on case-sensitive disks. Orchestrator may choose to fold for drive-anchored paths only. That loosens only Windows paths, which are case-insensitive anyway, so it is defensible. Open question |
| Win32 treats `...` or trailing-dot segments as other names during traversal (`a/.../b`) | Containment does not fold. Such a segment stays a literal name, so `.../etc` counts as relative inside the workspace. Protection folding covers the protected tails. Residual risk, listed for STORY-018's evasion corpus |
| `id_*` over-matches (`src/id_utils.py` is protected) | Inherited from the PRD's table and the STORY-006 plan decision 6. Over-matching only denies. Pinned by a test row so the behaviour is visible |
| A future caller forgets `protected` | It is a required positional argument, so leaving it out is a `TypeError` at the call site, not a silent "nothing protected" |
| The `\x00` directory probe or the Windows fold surprises a reviewer | Each is commented with its T6 reason and has its own test row. Both only add non-grantable denials. Either can be dropped (decision 6) |

## Open questions for the orchestrator

1. Return type: a single `Classification` (decision 2, matching F5) or a `tuple` like sql and shell?
2. Plain arguments `(path, protected, workspace_roots)` instead of the story's `(path, policy)` (decision 1). This follows the purity rule and `classify_shell`.
3. The story says STORY-012 fills the secret hook. It is STORY-013 (decision 9).
4. The two extensions beyond the AC, the Windows-fold candidate and the directory probe (decision 6): keep them or drop them?
5. Failure of a non-`str` or internal write: `fs.write_protected` (non-grantable, strictest) or `fs.write_outside_workspace` (decision 8)?
6. The device-target exemption for redirects, to be noted on STORY-013.
7. No `PurePosixPath` (decision 4).
8. The PRD does not ask for filesystem access, and the plan uses none.

---

## Acceptance Criteria

(Copied from story `STORY-011`)

- [ ] Given `normalize_path`, when called with `src\\a.ts`, `C:\\Repo\\x`, `a//b/./c`, `a/b/../c`, `~/x`, then it returns `src/a.ts`, `c:/Repo/x`, `a/b/c`, `a/c`, and a path whose first segment is the literal `~`; it touches no filesystem.
- [ ] Given no workspace roots, when `classify_write` runs on `src/a.ts`, then `fs.write_in_workspace`; on `../../etc/passwd`, then `fs.write_outside_workspace`; on `/etc/hosts`, then `fs.write_outside_workspace`; given a root of `/home/dev/projects`, then `/home/dev/projects/app/x.ts` is `fs.write_in_workspace` and `/home/dev/projects2/x` is not.
- [ ] Given `.env`, `./.env`, `config/../.env`, `.ENV.local`, `/home/dev/projects/app/.env.local`, `.github/workflows/ci.yml`, `.git/config`, `id_rsa`, `x.pem`, when classified as writes, then each is `fs.write_protected`, including inside a workspace root (protection is checked before containment).
- [ ] Given a read of `src/a.ts`, when `classify_read` runs, then `fs.read`; a read of a secret file glob returns the secret classifier's hook result, which STORY-012 fills in (until then a placeholder that tests mark as pending). (The plan reads "STORY-012" as STORY-013; see decision 9.)
- [ ] Given the module, when imported, then it reads no settings and performs no I/O.
- [ ] All tasks completed
- [ ] Backend imports without error
- [ ] Follows existing patterns
