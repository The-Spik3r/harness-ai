---
story: STORY-009
prd: PRD-016
slug: shell-tokenizer-and-unclassifiable
title: "Shell classifier, part 1: reject-scan, shlex tokenization, segments, wrappers and shell.unclassifiable"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-016-action-policy-rules
created: 2026-11-15
---

# Plan: Shell classifier, part 1: reject-scan, shlex tokenization, segments, wrappers and shell.unclassifiable

## Summary

Add a pure module, `app/services/action_classifiers/shell.py`, with two public functions, both of which never raise. `parse_shell(command, depth=0) -> ShellParse` runs PRD Section 6.8 steps 1–4. Step 1 is a quote-aware reject-scan of the raw string, which also normalizes it: CRLF and lone CR become LF, comments and backslash-newline continuations are removed, and quoted or escaped operator characters are swapped for sentinels so shlex cannot mistake them for operators. Step 2 tokenizes with `shlex.shlex(posix=True, punctuation_chars=";&|<>\n", whitespace_split=True)`, with `commenters=""` and `\n` taken out of `whitespace`. Step 3 splits the tokens into segments on `; && || | |& & \n`, keeping the operator that joined each one, and pulls redirections out of argv. Step 4 strips leading `NAME=value` assignments and wrappers, then extracts the head as the basename of argv[0] (split on `/` and `\`, one trailing `.exe` removed). For a POSIX shell head with `-c`, the parse also recurses into the script string, up to depth 3. `classify_shell(command, *, source_tool="") -> tuple[Classification, ...]` flattens that parse. Every unreadable construct becomes `shell.unclassifiable`. Until STORY-010 adds the head rules, every readable segment becomes a placeholder `shell.unlisted`, which is the deny-by-default floor (decision 1). STORY-010 and STORY-013 consume the `Segment` / `ShellParse` dataclasses, specified exactly below.

## User Story

As a security admin
I want every shell command split into the commands it actually runs, with anything the tokenizer cannot fully read denied
So that quoting, chaining and substitution cannot hide what runs.

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-009-shell-tokenizer-and-unclassifiable.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md`, sections 6.3 shell rows (lines 232–239, `shell.unclassifiable` at 239), 6.4 (254–258, the ordering rule), 6.8 (355–377), F3 (487–488), 9.2 T2/T12 (539–556), 14 Risk 1/3 (705, 707), 15 D3/D5/D16 (725, 727, 738)
- Threat model: `.agents/spikes/PRD-016-action-policy-rules/threat-model.md`, T2 (line 25), T12 (line 35, "STORY-010 should test it explicitly", line 50), S3 (line 59), S4 (line 60)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/services/action_classifiers/shell.py` (new), `tests/test_action_shell.py` (new) |
| Story | STORY-009 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch) |

Dependency STORY-006 is `status: done`. STORY-007 and STORY-008 are done too, and so is the sibling pattern `sql.py`. No new dependency: `shlex`, `re`, `dataclasses` and `typing` are all stdlib.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI aesthetics; description read). No UI here; story frontmatter `skills: []`. | — |

---

## shlex verification (done during planning on the repo's `.venv`, Python 3.12.10; record it in the story report)

Probe scripts: `C:/Users/nahue/AppData/Local/Temp/claude/G--coding-harness-ai/20d13059-18e1-4943-818b-68572342f8ca/scratchpad/shlex_probe.py` and `.../shlex_probe2.py`.

| Input | `shlex` result | Consequence |
|---|---|---|
| `npm test && rm -rf build; ls \| wc -l & echo x` | `npm test && rm -rf build ; ls \| wc -l & echo x` as separate tokens | punctuation splitting works with `whitespace_split=True` (AC 1) |
| same with `\n` for `;`, `\n` in `punctuation_chars`, removed from `whitespace` | `'\n'` is its own token | newline is a separator (AC 1) |
| `r''m -rf /`, `"rm" -rf /`, `\rm -rf /` | `['rm', '-rf', '/']` | quoting resolved by shlex (AC 2) |
| **`ls # c\nrm x` with the default `commenters='#'`** | **`['ls', 'rm', 'x']`**: the comment swallows the newline, and `rm` becomes an argument of `ls` | **a hole: `commenters` must be `""`**, and comments are removed by the scanner instead (decision 3) |
| **`echo a#b` with the default commenters** | **`['echo', 'a']`**: shlex starts a comment in the middle of a word, which bash does not, so `echo a#b; rm -rf /` loses the `rm` | the same fix |
| `a &&\nb`, `a\n\nb` | `'&&\n'`, `'\n\n'` (a run of punctuation is one token) | operator tokens are normalized: trailing `\n` dropped from `&& \|\| \| \|&` (a continuation), `\n\n` → `\n` |
| `a ;; b`, `a \|& b` | `';;'`, `'\|&'` | `\|&` is a valid pipe; any token outside the operator sets is unclassifiable |
| `npm test 2>&1 \| tee log`, `a 2>>err`, `cmd &>/dev/null &`, `x >\| y` | `'2' '>&' '1'`, `'2' '>>' 'err'`, `'&>' '/dev/null' '&'`, `'>\|'` | with `<>` in `punctuation_chars`, redirections are operator tokens. An all-digit word before one is the fd (adjacency is lost, a limit stated below) |
| `cat <<EOF\nx\nEOF` | the body lines come back as commands | a here-document is unclassifiable (decision 5) |
| `diff <(a) <(b)` | `'<' '(a)'` | `<(` is caught only by the raw scan, never after shlex |
| `echo 'unbalanced`, `x C:\` | `ValueError` ("No closing quotation", "No escaped character") | the scanner sees these first; the `ValueError` is still caught |
| `C:\Windows\cmd.exe /c x` (unquoted) | `'C:Windowscmd.exe'` | posix shlex drops the backslashes, so the head cannot be read (decision 6) |
| `"C:\Windows\cmd.exe" /c x` | `'C:\\Windows\\cmd.exe'` | the backslashes survive, and the basename on `\` gives `cmd` |
| `{rm,-rf,/}`, `(rm -rf /)`, `:(){ :\|:& };:` | `'{rm,-rf,/}'`, `'(rm' … '/)'`, `':(){' ':' '\|' ':' '&' '}' ';' ':'` | brace expansion and subshells are not shell-parsed by shlex (decisions 4, 7) |
| `$'\x72m' -rf /` | `'$\\x72m'` | bash ANSI-C quoting runs `rm`; shlex cannot see it (decision 4) |
| `shlex.join(["echo","$(x)","a'b","a;b"])` | `echo '$(x)' 'a'"'"'b' 'a;b'` | the adapter's S4 join puts substitution text in single quotes, so a quote-aware scan treats it as literal (decision 2) |
| `bash -c` nested with `shlex.quote` | levels 1–4 build cleanly | the depth tests are generated, not hand-quoted |
| **`echo ';'`, `echo ";"`, `echo \;`, `find . -exec rm {} \;`** | **`';'` comes back as `;`**, and `lex.state` is the same as for a real operator (probe 3) | **a quoted or escaped operator cannot be told from a real one after shlex.** `rm -r ';' -f /` would over-split into `rm -r` and `-f /`, which hides a destructive `rm` under a grantable `shell.unlisted`. Fixed by sentinels (decision 3a) |

---

## Patterns to Follow

### Naming / module docstring (cites PRD sections and decisions, lists what the real library forced)
```
// SOURCE: app/services/action_classifiers/sql.py:1-60
"""The SQL classifier: one statement string in, one classification per statement out (PRD-016 Sections 6.3, 6.9, F2).
...
What the real library forced, each one narrow and failing closed:
...
Pure (PRD-016 Section 6.12): the dialect is an argument. ...
"""
```

### Never raises; whole input as the operation target
```
// SOURCE: app/services/action_classifiers/sql.py:314-336
def classify_sql(
    statement: str, dialect: Optional[str], *, source_tool: str = ""
) -> tuple[Classification, ...]:
    ...
    target = statement if isinstance(statement, str) else ""
    op = Operation(kind="sql", target=target, source_tool=source_tool)
    try:
        if not isinstance(statement, str):
            return (Classification("sql.unparsed", op, ""),)
        return tuple(_classify_text(statement, dialect, op, 0))
    except Exception:
        return (Classification("sql.unparsed", op, _head(statement)),)
```
Mirror it exactly: the keyword-only `source_tool=""`, a non-str input gives one `shell.unclassifiable` with detail `""`, any `Exception` gives one `shell.unclassifiable`, and `BaseException` is not caught. The detail is capped at 32 characters (`_HEAD_MAX`, `sql.py:133-150`).

### Vocabulary types
```
// SOURCE: app/services/action_classifiers/__init__.py:107-131
@dataclass(frozen=True)
class Operation: kind / target / source_tool
@dataclass(frozen=True)
class Classification: rule: RuleId / operation / detail  # detail: the matched fragment of the call, never a configured value (T11)
```

### How shell targets arrive (S4)
```
// SOURCE: app/services/action_adapters.py:71-73, 325-340
#: `command` -- a shell line, or a `{command, args[]}` argv object joined with
#: `shlex.join` so the POSIX classifier recovers exactly that argv (S4);
...
                return [shlex.join([command, *args])]
```
`app/services/action_adapters.py:413-417`: shell targets keep their newlines (they separate commands), and an empty target is already `Malformed` upstream.

### Tests
```
// SOURCE: tests/test_action_sql.py:1-47 (docstring, env setdefaults, _rules/_details helpers, AC-sectioned tables)
// SOURCE: tests/test_action_sql.py:311-326 (every rule produced is in RULE_IDS and the right class; operation == Operation(kind, whole input, source_tool); detail <= 32)
// SOURCE: tests/test_action_sql.py:375-388 (purity: no settings, no open(/Path(, the only app import is the vocabulary line)
// SOURCE: tests/test_action_adapters.py:335-342 (S4 argv round trip through shlex)
```

### Pure-module constraint
`app/services/action_config.py:49` imports `settings`, so `shell.py` must not import `action_config` (or `ActionPolicy`). STORY-010 receives `shell_allow` as a plain argument. This mirrors `sql.py`'s `dialect` argument.

---

## The interface STORY-010 and STORY-013 consume (state this in the module docstring)

```python
#: Operators that join segments (PRD-016 Section 6.8 step 3). `"\n"` is a newline.
SEPARATORS: frozenset[str] = frozenset({";", "&&", "||", "|", "|&", "&", "\n"})
#: Redirection operators (taken out of argv, kept on the segment).
REDIRECTS: frozenset[str] = frozenset({">", ">>", "<", ">&", "<&", "&>", "&>>", ">|", "<>"})
#: Inline-interpreter recursion limit (D3, T12): text at depth > 3 is unclassifiable.
MAX_DEPTH = 3

@dataclass(frozen=True)
class Redirect:
    op: str                 # one of REDIRECTS
    target: str             # the word after it (`/dev/null`, `1` for `>&1`, `.env` for `< .env`)
    fd: Optional[str]       # the all-digit word before it (`2` in `2>&1`), else None

@dataclass(frozen=True)
class Segment:
    argv: tuple[str, ...]           # the whole simple command, redirections removed, as shlex resolved it
    head_index: int                 # index of argv[0] of the command that runs, after assignments and wrappers; len(argv) when none
    head: str                       # basename of argv[head_index] split on "/" and "\", one trailing ".exe" (any case) removed;
                                    # "" for an assignments-only segment; the last wrapper when the wrapper has no command (`env`, `sudo -l`)
    assignments: tuple[str, ...]    # leading NAME=value words (also those after a wrapper, `env FOO=1 rm`)
    wrappers: tuple[str, ...]       # stripped wrapper names, in order (`("sudo", "env")`)
    redirects: tuple[Redirect, ...]
    joined_by: Optional[str]        # the SEPARATOR before this segment; None for the first
    unclassifiable: Optional[str]   # this segment's reason (a detail fragment, <= 32 chars), else None
    inline: Optional["ShellParse"]  # the parsed `-c` script of a POSIX shell head (sh, bash, zsh, dash, ksh), at depth+1

    @property
    def args(self) -> tuple[str, ...]:  # argv after the head: what STORY-010 normalizes flags from and matches allowlist tokens against
        return self.argv[self.head_index + 1:]

@dataclass(frozen=True)
class ShellParse:
    text: str                       # the input as given
    depth: int
    segments: tuple[Segment, ...]   # () when `unclassifiable` is set
    unclassifiable: Optional[str]   # a whole-input reason (scan hit, shlex error, operator error, empty, depth), else None

def parse_shell(command: str, depth: int = 0) -> ShellParse: ...      # never raises
def classify_shell(command: str, *, source_tool: str = "") -> tuple[Classification, ...]: ...  # never raises
```

How the later stories use it:
- **STORY-010**: adds `shell_allow` to `classify_shell` (`classify_shell(command, shell_allow, *, source_tool="")`, the F3 `policy` reduced to what this pure module may take). For each segment it replaces the placeholder `shell.unlisted` with its head rules, reading `head`, `args`, `joined_by in {"|", "|&"}` (pipe-to-interpreter) and `inline` (emit `shell.inline_interpreter` and then the flattened inner classifications). For `pwsh -Command`, `cmd /c` and `python -c` it calls `parse_shell(inner, segment_depth + 1)` only where the inner text is shell. PowerShell heads are case-folded there, not here. A segment or a whole parse that is `unclassifiable` stays so. STORY-010 adds rules next to it and never removes it. The fork bomb is unclassifiable here (its head `:(){` holds `(`), so STORY-010 needs a raw-text check for it if its AC wants `shell.destructive` present too (deny either way).
- **STORY-013**: reads `head`, `args`, `assignments` and `redirects` (`cat < .env` is a read through a redirect target) to route embedded SQL, URLs and secret reads. Its classifications go **before** the head's own rule in the same segment (PRD 6.4). `echo $AWS_SECRET_ACCESS_KEY` and `echo ${GITHUB_TOKEN}` are **not** unclassifiable here: only a `$` in the head is.

Ordering emitted by `classify_shell`: one classification for a whole-input failure. Otherwise, per segment left to right: the flattened `inline` classifications first (embedded before the head, PRD 6.4), then the segment's own (`shell.unclassifiable` if set, else the placeholder `shell.unlisted` with detail = head). Every classification's `operation` is `Operation("shell", <the top-level input>, source_tool)`, the whole input, as `sql.py` does it.

---

## Design decisions (for the implementer and the orchestrator)

1. **Placeholder `shell.unlisted` for every readable segment** (needs orchestrator confirmation). The alternative is `()` for a clean command. That reads as "no rule fired", and STORY-014 could fold it to allow. `shell.unlisted` is the PRD's deny-by-default floor for an unlisted head, and it is grantable, so nothing is stricter than STORY-010 will be. It also mirrors the adapters' "never zero operations" rule (`action_adapters.py:21-24`). STORY-010 replaces it, and the module docstring and one test say so.
2. **The reject-scan is quote-aware, not a substring search.** It runs on the raw string before shlex (PRD 6.8 step 1, story note), with three states: outside quotes, in `'…'` (nothing is special), and in `"…"` (`$(` and backtick are still live, a backslash escapes the next character). Outside quotes, a backslash escapes the next character. Why: `awk '{print $(NF)}'`, `git commit -m 'use `x`'`, and the adapter's own S4 join `rm '$(x)'` (`tests/test_action_adapters.py:336-342`) are literal to bash. A substring scan would deny them all, which is Risk 2. A single-quoted string that a shell later runs (`bash -c '…'`) is covered by the recursion in decision 8. The ones no shell parse reaches (`ssh h '…'`, `watch '…'`) are already opaque under a grantable rule, and substitution inside them adds nothing.
3. **The scanner also normalizes. shlex never sees `#`.** CRLF and lone CR become LF before anything else (story note). Outside single quotes, backslash-newline is removed (the bash line continuation; otherwise `r\<LF>m` would be head `r\nm`). A `#` at word start outside quotes (at the start, or after whitespace or one of `;&|<>()`) starts a comment that runs to, but not including, the newline. shlex runs with `commenters=""`. This closes the two holes found in planning, where shlex's comment handling swallows the next command.
3a. **Quoted and escaped operator characters become sentinels before shlex.** The scanner already knows the quote state, so it replaces each `;`, `&`, `|`, `<`, `>` and `\n` that is inside quotes, or escaped by a backslash outside quotes (the backslash is dropped), with its own Private Use Area character (U+E000–U+E005). After shlex, every token maps the sentinels back. shlex therefore only ever treats unquoted characters as operators, and `find . -exec rm {} \;` keeps `;` as an argument. If the raw input already contains a character in U+E000–U+E005, it is unclassifiable (detail `U+E000`…), so the mapping cannot be confused. A token is an operator iff it is non-empty and made only of `;&|<>\n`.
4. **What the reject-scan rejects** (whole input, the first hit in scan order, detail = the fragment). In double quotes and outside quotes: `$(` (covers `$((`) and backtick. Outside quotes only: `<(`, `>(`, `<<<`, `<<` (decision 5), `$'` and `$"` (ANSI-C and locale quoting, which shlex cannot decode; `$'\x72m'` is `rm`), and brace expansion (a `{` not preceded by `$` with an unquoted `,` or `..` before its matching unquoted `}`; `{rm,-rf,/}` is `rm -rf /`; `{}` from `find -exec` passes). Anywhere: NUL (detail `NUL`). At end of input: an open quote (detail `'` or `"`) or a trailing backslash (detail `\`). Not rejected: `${NAME}`, `$NAME` and globs in arguments. STORY-010 handles `*` in `rm -r *`, and STORY-013 needs `${GITHUB_TOKEN}`.
5. **A here-document `<<` is unclassifiable.** This goes beyond the 6.3 list (which names `<<<`), for 6.8's stated reason: it "feeds data the classifier cannot inspect into a head it can", and without it shlex reads the body lines as commands. The cost: agents that write files with `cat <<'EOF' > f` get denied. That is acceptable because they have a write tool. Open question 2.
6. **Head checks (per segment, after wrapper stripping).** The segment is unclassifiable when: the head is `eval`, `source` or `.` (6.3); argv[0] contains `$` (6.3 "a head that is a variable", also covering `r$x`); the head (basename) is not in the character set `[A-Za-z0-9_.+:@,~-]`, with the exact heads `[` and `[[` allowed. That rejects glob heads (`/bin/r?`, which bash expands to `rm`), parens (`(rm`, a subshell), braces (`{`), cmd's `^` (`de^l`) and `%VAR%`, and the empty word `""`. The last check: argv[0] starts with a drive letter (`[A-Za-z]:`) and has no `/` or `\` left, which means posix shlex ate the backslashes of an unquoted Windows path (`C:\Windows\cmd.exe` → `C:Windowscmd.exe`). Without that check, D16's `cmd /c` would hide under a grantable `shell.unlisted`. The detail is argv[0] truncated to 32.
7. **Wrappers**, stripped with a strict per-wrapper option table. The story's set: `sudo`, `doas`, `env`, `nohup`, `time`, `xargs`. Added, because an unstripped wrapper turns a non-grantable `shell.destructive` into a grantable `shell.unlisted`: `command`, `builtin`, `exec`, `nice`, `timeout`, `stdbuf`, `setsid` (open question 1). For each wrapper: known flags, known options that take a value (attached `-uroot` or as the next word), a count of leading positionals (`timeout DURATION`), and `--` ends the options. An option **not** in the table makes the segment unclassifiable (`sudo --bogus rm`). Guessing that it takes no value could hide the head. `env -S` / `--split-string` is unclassifiable, because it re-splits a string into argv. `NAME=value` words are stripped before and after wrappers, in a loop. If nothing is left after a wrapper, the head is the wrapper (`env` with no arguments is `env`, which STORY-013 needs). A segment with only assignments has head `""`.
8. **Inline recursion lives here (story note, AC 4); what `-c` *means* is STORY-010's.** For a head in `{sh, bash, zsh, dash, ksh}`, the parser scans the shell's options: short clusters (`-c`, `-lc`, `-ec`), `-o`/`+o NAME` and `-O NAME` take a value, `--rcfile`/`--init-file` take a value, other `--long` options take none, and `--` ends the options. If `c` appears in any cluster, the first positional is the script, and `Segment.inline = parse_shell(script, depth + 1)`. `-c` with no script is unclassifiable. `parse_shell(text, depth)` with `depth > MAX_DEPTH` returns `unclassifiable="depth > 3"` without scanning. Four nested `bash -c` are unclassifiable; three are not.
9. **Operators.** Operator tokens are normalized as the verification table shows. A token outside `SEPARATORS ∪ REDIRECTS` is unclassifiable (`;;`, `;&`, a newline left inside a non-separator). Also unclassifiable: a segment that is empty between two separators (`a ; ; b`, a leading `| a`); `&&`, `||`, `|` or `|&` at the end of input (bash would wait for more); and a redirection with no word after it. A trailing `;`, `&` or newline is fine. Zero segments (whitespace or comments only) is unclassifiable with detail `""`, because nothing can be vouched for (`sql.py:308-310`).
10. **Never raises.** `classify_shell` wraps everything in `except Exception` → one `shell.unclassifiable`. `parse_shell` does the same, returning `ShellParse(text, depth, (), "")`. The cost is linear: one scan and one shlex pass per level, at most four levels, and input already bounded by `ACTION_MAX_ARGUMENT_CHARACTERS` upstream (T12).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/action_classifiers/shell.py` | CREATE | scanner, tokenizer, segmenter, wrapper/head extraction, inline recursion, `parse_shell`, `classify_shell`, the dataclasses above |
| `tests/test_action_shell.py` | CREATE | AC-sectioned tables, the seed of STORY-018's evasion corpus |

No pre-existing file changes. `action_classifiers/__init__.py` already has `shell.unclassifiable` (line 62) and `shell.unlisted` (line 56). No re-export is needed: `sql.py` is imported by module path too (`action_config.py:59`).

---

## Tasks

### Task 1: `shell.py`, the scanner
- **File**: `app/services/action_classifiers/shell.py`
- **Action**: CREATE
- **Implement**: a module docstring in the `sql.py:1-60` style. It cites PRD 6.3, 6.4, 6.8, F3, D3, D5, D16, T2, T12 and S3/S4, and lists "what the real library forced" (the shlex comment holes, operator runs, lost backslashes, here-doc bodies). Imports: `shlex`, `re`, `dataclasses.dataclass`, `typing`, and the single line `from app.services.action_classifiers import Classification, Operation, RuleId`. Write `_scan(text) -> tuple[str, Optional[str]]`, which returns (normalized text, reject detail), per decisions 2–4. One left-to-right pass with an explicit state and word-start tracking. No regex over the raw string for quote state.
- **Mirror**: `sql.py:133-150` (`_HEAD_MAX = 32`, a small helper per concern)
- **Validate**: `.venv/Scripts/python -c "import app.services.action_classifiers.shell"`

### Task 2: `shell.py`, tokenize and segment
- **Implement**: `_tokens(normalized)` → `shlex.shlex(normalized, posix=True, punctuation_chars=";&|<>\n")`, `whitespace_split=True`, `commenters=""`, `whitespace` without `\n`. Then build segments: operator normalization, separators, redirections (fd word, target word), and the error cases (decision 9). A token is an operator iff `token and set(token) <= set(";&|<>\n")`. Correct only because of decision 3a's sentinels (planning probe 3 proved shlex alone returns `';'` as `;`). After classification as word/operator, map the sentinels back in each word token. Pin with tests: `echo ';'`, `echo ";"`, `echo \;`, `find . -exec rm {} \; -print` (one segment each, `;` in argv), `rm -r ';' -f /` (one segment, args `-r ; -f /`), `echo '<newline>'` (one segment), and a raw U+E000 → unclassifiable.
- **Validate**: the AC 1 tests

### Task 3: `shell.py`, wrappers, head, inline
- **Implement**: a `_WRAPPERS` table (a frozen dataclass per wrapper: `flags`, `valued`, `positionals`, `rejects`), `_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")`, `_HEAD_CHARS`, the drive-letter check, `_basename` (split on `/` and `\`, strip one `.exe` in any case), the head checks (decision 6), and `_POSIX_SHELLS` with the `-c` option scan (decision 8). Assemble `Segment`, `ShellParse` and `parse_shell`.
- **Validate**: the AC 2–4 tests

### Task 4: `shell.py`, `classify_shell`
- **Implement**: flatten in the order stated in the interface section, with the placeholder `shell.unlisted` (decision 1; a comment cites "replaced by STORY-010"). Wrap it in never-raise the way `sql.py:329-336` does.
- **Validate**: the AC 4 and 5 tests

### Task 5: Tests, `tests/test_action_shell.py` (new)
- **File**: `tests/test_action_shell.py`
- **Action**: CREATE
- **Implement**: a module docstring like `tests/test_action_sql.py:1-16`, with `os.environ.setdefault` lines and `_segments(cmd)` / `_heads(cmd)` / `_rules(cmd)` helpers. Sections:
  - **AC 1, segments**: both story strings (`;` and newline) → `[(argv, joined_by)]` exactly: `("npm","test")/None, ("rm","-rf","build")/"&&", ("ls",)/";" (or "\n"), ("wc","-l")/"|", ("echo","x")/"&"`. Also `a &&\nb` (continuation), `a\n\nb`, `a\r\nb`, `a\rb`, a trailing `;`/`&`, `a |& b`, `echo ';'` (one segment), `npm test 2>&1 | tee log` (redirect `Redirect(">&","1","2")`, argv `npm test`).
  - **AC 2, head**: the four story forms → `rm`. Also `"C:\\Program Files\\x\\rm.exe" x` → `rm`.
  - **AC 3, wrappers**: the seven story forms → head `rm`, plus `wrappers`/`assignments` asserted. Also `sudo -u root rm x`, `sudo -uroot rm x`, `env -i FOO=1 rm x`, `xargs -I{} -n1 rm`, `timeout -s KILL 5 rm x`, `nice -n 10 rm x`, `command rm x`, `exec rm x`, `env` alone → head `env`, `FOO=1` alone → head `""`.
  - **AC 4, unclassifiable** (parametrized; each asserts `"shell.unclassifiable" in _rules(cmd)` and no exception): `ls $(cat x)`, `` ls `cat x` ``, `echo "$(x)"`, `eval "$C"`, `source x.sh`, `. x.sh`, `diff <(a) <(b)`, `tee >(x)`, `cat <<< x`, `$CMD arg`, `"$CMD" arg`, `echo 'x`, `echo "x`, `echo x\`, nesting depth 4 (built with `shlex.quote` in a loop), and for the inner script `bash -c 'ls $(x)'` and `bash -c "eval x"`.
  - **Evasion seeds found in planning** (each unclassifiable or correctly segmented; a comment names the shlex hole): `ls # c\nrm x` → segments `ls`, `rm x`; `echo a#b; rm -rf /` → two segments; `r\<LF>m -rf /` → head `rm`; `{rm,-rf,/}`; `rm {-rf,/}`; `/bin/r? -rf /`; `(rm -rf /)`; `$'\x72m' -rf /`; `C:\Windows\System32\cmd.exe /c x` (unquoted); `de^l /s x`; `sudo --bogus rm`; `env -S 'rm -rf /'`; `bash -c`; `cat <<EOF\nx\nEOF`; `a ;; b`; `a ; ; b`; `| a`; `a &&`; `ls >`; `""`; `# only a comment`; `"a\x00b"`.
  - **Not over-blocked** (no `shell.unclassifiable`, exact segments): `awk '{print $(NF)}' f`, `git commit -m 'use `x`'`, `echo $HOME`, `echo ${GITHUB_TOKEN}`, `find . -name '*.py' -exec grep x {} +`, `[ -f x ] && rm x`, `ls -la # list`, multi-line with continuation, and depth 3 nesting. Also the S4 join `shlex.join(["rm", "$(x)", "`id`"])` → one segment, argv exactly `("rm", "$(x)", "`id`")`, mirroring `tests/test_action_adapters.py:336-342`.
  - **AC 5, interface and purity**: `parse_shell` returns `ShellParse` with the field set above; `Segment.args`; `inline` is set for `bash -c 'ls'` (depth 1, segment head `ls`); the placeholder test (`classify_shell("ls")` gives `(Classification("shell.unlisted", Operation("shell","ls",""), "ls"),)`, a comment says STORY-010 replaces it); the ordering test (inner before own: `bash -c 'ls $(x)'` → `("shell.unclassifiable", "shell.unlisted")`); a walk over every case (every rule in `RULE_IDS` and starting with `shell.`, `operation == Operation("shell", whole input, "bash")`, detail a `str` of at most 32); never raises on `None`, `b"ls"`, `123`, a 200 000-character string and `"'" * 10001`; purity, mirroring `tests/test_action_sql.py:375-388` (the only app import line is the vocabulary one; no `settings`, `open(` or `Path(`).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_shell.py -q -p no:cacheprovider`

### Task 6: Targeted regression
- Run in one invocation: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_shell.py tests/test_action_vocabulary.py tests/test_action_adapters.py tests/test_untouched_app.py -q -p no:cacheprovider` (new file, the vocabulary package purity test, the S4 source, and the app guard because an `app/` file is added), plus the backend import check. Full suite: deferred to the orchestrator (user decision).

---

## End-to-End Tests

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"`. The new module is not yet imported by the app (no consumer until STORY-014), so this only proves nothing broke.
- [ ] `.venv/Scripts/python -c "from app.services.action_classifiers.shell import classify_shell as c; print(c('npm test && rm -rf build; ls \$(x)'))"` prints one `shell.unclassifiable` (whole input, `$(`).
- No UI, no HTTP surface.

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
| The quote-aware scanner has a bug that lets `$(` through | A table of substitutions in each quote context (unquoted, double, after an escaped quote, adjacent to single-quoted text); recursion covers `-c` scripts; STORY-018's evasion corpus grows from these tests |
| shlex cannot distinguish a quoted `;` from an operator `;` (verified in probe 3) | Decision 3a's sentinels. Over-splitting is **not** fail-closed: `rm -r ';' -f /` would lose its flags. The tests in Task 2 pin it |
| fd adjacency is lost (`echo 2 > x` reads as `2>`) | Only an all-digit word is dropped into `Redirect.fd`. It cannot be a head or a flag. Stated in the docstring |
| Over-blocking: subshells `( … )`, here-docs, `{a,b}` in arguments, `#` mid-word is fine | Each is a deliberate, tested deny (D5, "deny when not classifiable with confidence"); listed for STORY-020's README |
| Wrapper table too strict (an unlisted real option makes it unclassifiable) | A non-grantable deny, but visible in the Actions view. The tables cover the documented GNU/sudo options; open question 1 |
| Interpreter-string tricks no shell parse reaches (`find -exec sh -c`, `awk 'BEGIN{system(…)}'`, `trap '…' EXIT`, `git -c alias.x='!…'`, PowerShell `{ … }` scriptblocks) | Out of this story. They fall to `shell.unlisted` (deny, grantable), as PRD Section 6.3 and Risk 3 accept. Listed for STORY-010/018 (`trap`, `xargs sh -c` already recursed via the wrapper strip) |
| PowerShell backtick escapes, and `$(…)` subexpressions | Both are unclassifiable here (deny); D16's full handling is STORY-010 |

---

## Open questions for the orchestrator

1. **Wrapper set.** Is it OK to strip `command`, `builtin`, `exec`, `nice`, `timeout`, `stdbuf` and `setsid` beyond the story's seven? (Recommended: yes. Otherwise `command rm -rf /` is grantable `shell.unlisted`.)
2. **Here-document `<<`.** Is it OK to make it unclassifiable? 6.3 lists only `<<<`, and 6.8's reasoning covers both. (Recommended: yes.)
3. **Placeholder `shell.unlisted`** for readable segments until STORY-010 (decision 1). The alternative is an empty tuple. (Recommended: the placeholder.)
4. **Extra triggers beyond 6.3's list** (decisions 4 and 6): brace expansion, `$'`/`$"`, glob/paren/`^` heads and unquoted drive-letter heads. Each closes a path where bash runs something the tokenizer cannot see. STORY-020 should list them in the README.

---

## Acceptance Criteria

(Copied from story `STORY-009`)

- [ ] Given `npm test && rm -rf build; ls | wc -l & echo x` (and the same with a newline), when segmented, then the segments are `npm test`, `rm -rf build`, `ls`, `wc -l`, `echo x`, each with the operator that joined it, in order. (Task 2, Task 5 AC 1)
- [ ] Given `r''m -rf /`, `"rm" -rf /`, `\rm -rf /` and `/usr/bin/rm -rf /`, when tokenized and the head is extracted, then the head is `rm` in every case. (Task 3, Task 5 AC 2)
- [ ] Given `sudo rm x`, `env FOO=1 rm x`, `FOO=1 rm x`, `nohup rm x`, `time rm x`, `xargs rm`, `doas rm x`, when the head is extracted, then the wrappers and assignments are stripped and the head is `rm`. (Task 3, Task 5 AC 3)
- [ ] Given any of `ls $(cat x)`, a backtick substitution, `eval "$C"`, `source x.sh`, `. x.sh`, `diff <(a) <(b)`, `cat <<< x`, `$CMD arg`, an unbalanced quote, or nesting of `bash -c` deeper than three levels, when classified, then the result contains `shell.unclassifiable` and the function never raises. (Tasks 1, 3, 4; Task 5 AC 4)
- [ ] Given the module, when imported, then it reads no settings and performs no I/O; `classify_shell` exposes the segment list for STORY-010 to apply head rules to. (`parse_shell` / `Segment` / `ShellParse`, the interface section; Task 5 AC 5 purity + interface tests)
- [ ] All tasks completed
- [ ] Backend import passes (no frontend in this repo)
- [ ] Follows existing patterns (`sql.py` purity, never-raise, `source_tool` keyword-only, test layout)
