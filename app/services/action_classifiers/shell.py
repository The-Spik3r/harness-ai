"""The shell classifier, part 1: what a command line runs (PRD-016 Sections 6.3, 6.4, 6.8, F3).

`parse_shell(command)` runs Section 6.8 steps 1-4 and returns a `ShellParse`:
the simple commands the line runs (`Segment`s), each with the operator that
joined it, its redirections, the wrappers and assignments stripped in front of
it, and its head. `classify_shell(command)` flattens that into
classifications. Anything the tokenizer cannot fully read is
`shell.unclassifiable` (Section 6.3, non-grantable, D5): quoting, chaining and
substitution must not hide what runs (threat T2). Neither function raises.

1. **Reject-scan** of the raw string, quote-aware, *before* shlex, because
   shlex removes the quotes that make `$(` visible. Rejected, as the whole
   input: `$(` and backtick (also inside `"..."`); outside quotes `<(`,
   `>(`, `<<<`, a here-document `<<` (its body is data a head would read and
   shlex would read as commands), `$'...'` / `$"..."` (`$'\\x72m'` is `rm`)
   and brace expansion (`{rm,-rf,/}` is `rm -rf /`); NUL anywhere; an open
   quote or a trailing backslash at the end. Text in single quotes is
   literal to bash and is not rejected (`awk '{print $(NF)}'`, the S4
   `shlex.join` of an argv holding `$(x)`); a single-quoted script that a
   shell later runs (`bash -c '...'`) is scanned again by the recursion.
2. **Tokenize** with `shlex.shlex(posix=True, punctuation_chars=";&|<>\\n",
   whitespace_split=True)`, `commenters=""` and `\\n` taken out of
   `whitespace`, so a newline is a separator token.
3. **Segment** on `; && || | |& &` and newline (`SEPARATORS`); redirections
   (`REDIRECTS`) leave argv and are kept on the segment.
4. **Head**: leading `NAME=value` words and wrappers (`sudo`, `env`,
   `nohup`, `time`, `xargs`, `doas`, `command`, `builtin`, `exec`, `nice`,
   `timeout`, `stdbuf`, `setsid`) are stripped, then the head is the
   basename of the next word (split on `/` and `\\`, one trailing `.exe`
   removed). A segment is unclassifiable when the head is `eval`, `source`
   or `.`, holds a `$` (a variable head), has a character outside
   `[A-Za-z0-9_.+:@,~-]` (a glob, a subshell `(`, a brace group, cmd's `^`
   and `%VAR%`; `[` and `[[` are allowed), or is an unquoted Windows path
   whose backslashes posix shlex ate (`C:\\Windows\\cmd.exe` arrives as
   `C:Windowscmd.exe`, D16). A wrapper option outside its table is
   unclassifiable too (`sudo --bogus rm`): guessing whether it takes a value
   could hide the head. `env -S` re-splits a string into argv and is
   unclassifiable.

Inline interpreters (D3, T12): for a POSIX shell head (`sh`, `bash`, `zsh`,
`dash`, `ksh`, any case) with `-c`, the script is parsed again at `depth + 1`
into `Segment.inline`; text at depth > `MAX_DEPTH` (3) is unclassifiable
without being read. What `-c` *means* (`shell.inline_interpreter`), and `pwsh
-Command`, `cmd /c`, `python -c`, are the head rules' (below).

What the real library forced (shlex, Python 3.12), each one failing closed:

- **Comments.** shlex's default `commenters="#"` starts a comment mid-word
  (`echo a#b; rm -rf /` loses the `rm`) and swallows the newline after one
  (`ls # c<LF>rm x` makes `rm` an argument of `ls`). shlex runs with
  `commenters=""`; the scanner drops a `#` comment that starts a word
  outside quotes, up to but not including the newline.
- **Quoted operators.** After shlex, a quoted `';'` cannot be told from the
  operator `;`, and `rm -r ';' -f /` would split into `rm -r` and `-f /`.
  The scanner swaps every quoted or backslash-escaped `; & | < >` and
  newline for a Private Use Area sentinel (U+E000-U+E005) and each word maps
  it back after shlex. Input that already holds one is unclassifiable.
- **Operator runs.** shlex returns a run of punctuation as one token
  (`&&\\n`, `\\n\\n`, `;;`). Trailing newlines after a separator are a
  continuation; any other run outside `SEPARATORS | REDIRECTS` is
  unclassifiable, and so are an empty segment (`a ; ; b`), an `&&`, `||`,
  `|` or `|&` at the end, and a redirection with no word after it.
- **Line endings.** CRLF and a lone CR become LF first; backslash-newline
  outside single quotes is removed (bash's line continuation).
- **fd adjacency is lost**: `echo 2 > x` reads as `echo 2>x`. Only an
  all-digit word directly before a redirection becomes `Redirect.fd`; it
  cannot be a head or a flag.

The interface STORY-010 (head rules) and STORY-013 (embedded SQL, URLs,
secret reads) consumed is `parse_shell`, `ShellParse`, `Segment` and
`Redirect` as defined below.

Head rules (STORY-010; Sections 6.3, 6.6, 6.8, D16). Per segment, left to
right (`_segment_rules`): the `-c` script's classifications; the
`shell.destructive` and `iex` found in PowerShell/cmd inner text; the
embedded SQL/URL/secret/write classifications (STORY-013, below, PRD 6.4);
then, for a readable segment, every danger rule that fires, non-grantable first:
`shell.destructive`, `shell.pipe_to_interpreter`, `shell.unclassifiable`
(`Invoke-Expression`/`iex`, D16), `shell.inline_interpreter`,
`shell.package_install`, `shell.service_control`. Only when none fires is
the segment `shell.allowlisted` (6.6: the head and the first N-1 args equal
a `shell.allow` entry's N whitespace-split tokens, exactly) or the floor
`shell.unlisted`. So an allowlisted `npm` still makes `npm install x` an
install, and a chain keeps one result per segment for STORY-014 to fold.

- **Heads** are matched case-folded for the danger rules (folding only adds
  denies; D16 wants PowerShell and cmd heads matched in any case) and
  exactly for the allowlist. A segment with `sudo`/`doas` or leading
  assignments is never allowlisted (`GIT_SSH_COMMAND=... git fetch`).
- **Flags** are normalized into sets, not matched as strings (6.8): GNU
  short clusters (`-rf`, `-fr`, `-Rf`), long options and their unambiguous
  prefixes (`--rec`), cmd switches (`/s/q`) and PowerShell parameter
  prefixes (`-Rec`, `-fo`, `-Recurse:$true`). An ambiguous prefix counts as
  all its matches (stricter).
- **PowerShell/cmd inner text** (`pwsh -Command`, `powershell -c`, `cmd /c`)
  is not POSIX shell: it is parsed one level down and only its
  `shell.destructive` and `iex` are kept; its other unclassifiable results
  are dropped (PowerShell's `$(...)` is not a substitution to hide). The
  code of `python -c`, `node -e`, `perl -e`, `ruby -e`, `php -r`,
  `-EncodedCommand` and `-File` is not read: `shell.inline_interpreter`
  only. `python -m MODULE` is not inline (an installed module, like a head).
- **Raw-text checks** only ever add `shell.destructive`: the fork bomb
  (`NAME(){ NAME|NAME& }`) anywhere in the text, appended last; and, for
  text the tokenizer rejected as a whole (`Remove-Item -Recurse -Force C:\\`
  ends in a backslash), a whitespace-split best-effort `_destructive` scan
  after its `shell.unclassifiable`. Both add a non-grantable deny to input
  that is already denied, so neither can loosen anything.

What the head rules do not read (STORY-018 and STORY-020 list them): code
in another language (`python -c "os.system(...)"`, `awk 'BEGIN{system()}'`),
`find -exec`/`-delete`, `git -c alias.x='!...'`, `trap`, PowerShell
scriptblocks, `Start-Process`, `Invoke-Command`, heads outside the 6.3/D16
tables (`format`, `diskpart`, `winget`, `dnf`, `halt`), and PowerShell
`rm -r X` without force (read as POSIX `rm`, 6.3). They stay
`shell.unlisted` (deny, grantable), or `shell.allowlisted` when a deployment
allowlists their head: an allowlist entry is trust in the whole head.

Embedded targets (STORY-013; PRD 6.4, 6.8 step 5, F3, F6). Step 3 of
`_segment_rules` (`_embedded`) classifies what a readable segment reaches
with the classifier that owns it, before the head's rule, in this order
(PRD 6.4 "SQL, network, secret"; argv order within each group):

1. **SQL** (decision D-H): the text of `psql -c`/`--command`, `mysql` and
   `mariadb -e`/`--execute`/`--init-command`, and `sqlite3 DB SQL...` /
   `-cmd SQL`, through `sql.classify_sql` in the client's own dialect
   (`postgres`, `mysql`, `sqlite`), not `ACTION_SQL_DIALECT`, which
   describes the SQL tool's database, not the binary on the line. psql
   meta-commands and sqlite dot-commands are `sql.unparsed`.
2. **Network** (decision D-L): the URLs of `curl`, `wget`, `http` and
   `https` (HTTPie), through `network.classify_url`. A small GNU-style
   option walker over per-head tables finds them: every positional (HTTPie:
   the one after an optional upper-case METHOD; the rest are request
   items), and the value of a URL-valued option (`-x`/`--proxy`,
   `--preproxy`, `--url`). A word with no `scheme://` gets `http://` (curl's
   default, STORY-012 decision; `https://` for the `https` head, and
   HTTPie's `:3000/x` is `http://localhost:3000/x`). Options that move the
   real destination out of sight (`curl --resolve`, `--connect-to`,
   `-K`/`--config`, `--unix-socket`; `wget -e`/`--execute`,
   `-i`/`--input-file`, `--config`) are `net.unparsed` with the option as
   the detail (T8). A `http_proxy` / `https_proxy` / `all_proxy`
   assignment on the segment is a URL too.
3. **Secret** (F4, F6; decisions D-I, D-J, D-K): the path arguments of a
   reader head (`_READ_HEADS`: `cat`, `less`, `more`, `head`, `tail`, and
   the other content readers an allowlist plausibly holds), every option
   value of a fetcher together with its text after `@` or `<` (`-d @.env`,
   `-F f=<.env`, `-T .env`), and `<`/`<>`/`<&` targets, through
   `paths.classify_read` (only a `secret.read` is kept, so `cat src/a.ts`
   adds nothing, decision D-G); then every `$NAME`/`${NAME}`/`$env:NAME`/
   `%NAME%` reference in any word of the segment and its redirect targets,
   for any head (`curl -d "$OPENROUTER_API_KEY"`), against `secrets.env`;
   then a whole-environment dump, always `secret.read`: `env` with no
   command, `printenv` with no names, bare `set`, `export` / `export -p`,
   `declare`/`typeset` with no names. `printenv NAME` and `declare -p NAME`
   check each name. A PowerShell `env:NAME` / `env:` word is an environment
   reference too (STORY-018; `secrets.env_references`).
4. **Writes** (decision D-B): output-redirect targets (`>`, `>>`, `>|`,
   `&>`, `&>>`, `<>`, and `>&` to a file) and a fetcher's output options
   (`curl -o`/`-D`/`-c`, `wget -O`/`-o`/`-a`/`-P`), through
   `paths.classify_write`, every result kept, so `ls > ~/.bashrc` under an
   allowlisted `ls` is `fs.write_outside_workspace`. Devices are exempt:
   `/dev/null`, `/dev/stdout`, `/dev/stderr`, `/dev/tty` exactly, `NUL` and
   `CON` in any case, `-` for a fetcher's stdout, and a descriptor target of
   `>&`/`<&` (`2>&1`, `>&-`).

Embedded results are not dangers: they never stop a head from being
`shell.allowlisted` (`psql` allowlisted gives `sql.ddl, shell.allowlisted`),
which STORY-014 folds by severity. Each carries the operation of the
classifier that produced it (`Operation("sql", text)`, `("http", url)`,
`("fs_read"|"fs_write", word)`, decision D-E); an env reference or a dump
carries the shell's own operation. All carry the shell's `source_tool`.

What the embedding does not read (STORY-018 and STORY-020 list them): SQL
from `-f`, `-init`, `<` or a pipe (the head's rule stands, and an
allowlisted `psql` is trust in the head); `tee`, `cp` destinations, `dd
of=` and other heads' own writes; PowerShell/cmd inner text (it is
`shell.inline_interpreter` anyway); reader heads outside `_READ_HEADS`; shell globs in arguments
(`cat .e*`) and glob wildcards that could only name a secret; a single-quoted
`'$X'` cannot be told from `$X` and over-matches; an unknown curl option's
value is read as a URL (over-blocks); `sqlcmd`, `clickhouse-client` and
other SQL clients are not read.

Every classification the head rules produce has `operation`
`Operation("shell", command, source_tool)` with the **whole input** as the
target, as `sql.py` does it. The `detail` is the matched fragment of the
call (`$(`, `eval`, `rm -rf`, `| sh`, the head, the variable name), never a
configured value, at most 32 characters (T11).

Pure (PRD-016 Section 6.12): no settings, no I/O. The policy's data
(`shell_allow`, `network_allow`, the compiled secret and protected globs,
the workspace roots) arrives as arguments from the caller, never through
`settings` or `action_config`; the sibling classifiers (`network`, `paths`,
`secrets`, `sql`) are the only `app` imports besides the vocabulary.
"""

import re
import shlex
from dataclasses import dataclass, field
from typing import Optional

from app.services.action_classifiers import Classification, Operation, RuleId
from app.services.action_classifiers import network, paths, secrets, sql

#: Operators that join segments (PRD-016 Section 6.8 step 3). `"\n"` is a newline.
SEPARATORS: frozenset[str] = frozenset({";", "&&", "||", "|", "|&", "&", "\n"})
#: Redirection operators (taken out of argv, kept on the segment).
REDIRECTS: frozenset[str] = frozenset({">", ">>", "<", ">&", "<&", "&>", "&>>", ">|", "<>"})
#: Inline-interpreter recursion limit (D3, T12): text at depth > 3 is unclassifiable.
MAX_DEPTH = 3

# Longest `detail` (and unclassifiable reason) for one fragment.
_HEAD_MAX = 32

# Separators after which the input cannot end (bash would wait for more).
_CONTINUING = frozenset({"&&", "||", "|", "|&"})

# The characters shlex treats as punctuation, and each one's sentinel for when
# it is quoted or escaped (decision 3a of the plan).
_OPERATOR_CHARS = ";&|<>\n"
_SENTINELS = {ch: chr(0xE000 + i) for i, ch in enumerate(_OPERATOR_CHARS)}
_UNSENTINEL = str.maketrans({v: k for k, v in _SENTINELS.items()})
_SENTINEL_CHARS = frozenset(_SENTINELS.values())

# Characters that end a word outside quotes: a `#` after one starts a comment,
# and a brace expansion cannot span one.
_WORD_BREAKS = frozenset(" \t\n;&|<>()")

_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
_HEAD_CHARS = re.compile(r"[A-Za-z0-9_.+:@,~-]+")
_DRIVE = re.compile(r"[A-Za-z]:")
_ALLOWED_ODD_HEADS = frozenset({"[", "[["})
# Section 6.3: a head that reads code from somewhere the classifier cannot see.
_EVAL_HEADS = frozenset({"eval", "source", "."})
_POSIX_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})


def _cap(text: str) -> str:
    return text[:_HEAD_MAX]


@dataclass(frozen=True)
class Redirect:
    """One redirection taken out of a segment's argv."""

    #: One of `REDIRECTS`.
    op: str
    #: The word after it (`/dev/null`, `1` for `>&1`, `.env` for `< .env`).
    target: str
    #: The all-digit word before it (`2` in `2>&1`), else None.
    fd: Optional[str]


@dataclass(frozen=True)
class Segment:
    """One simple command, as Section 6.8 steps 3-4 read it."""

    #: The whole simple command, redirections removed, as shlex resolved it.
    argv: tuple[str, ...]
    #: Index of argv[0] of the command that runs, after assignments and
    #: wrappers; `len(argv)` when there is none.
    head_index: int
    #: Basename of `argv[head_index]` split on `/` and `\`, one trailing
    #: `.exe` (any case) removed. `""` for an assignments-only (or
    #: redirections-only) segment; the last wrapper when the wrapper has no
    #: command (`env`, `sudo -l`) or an option outside its table (`sudo
    #: --bogus rm`, unclassifiable). Not case-folded (PowerShell is STORY-010's).
    head: str
    #: Leading `NAME=value` words (also those after a wrapper, `env FOO=1 rm`).
    assignments: tuple[str, ...]
    #: Stripped wrapper names, in order (`("sudo", "env")`).
    wrappers: tuple[str, ...]
    redirects: tuple[Redirect, ...]
    #: The `SEPARATORS` entry before this segment; None for the first.
    joined_by: Optional[str]
    #: This segment's reason (a detail fragment, <= 32 chars), else None.
    unclassifiable: Optional[str]
    #: The parsed `-c` script of a POSIX shell head, at depth + 1.
    inline: Optional["ShellParse"]

    @property
    def args(self) -> tuple[str, ...]:
        """argv after the head: what STORY-010 normalizes flags from and matches allowlist tokens against."""
        return self.argv[self.head_index + 1:]


@dataclass(frozen=True)
class ShellParse:
    """A command line read into segments (PRD-016 Section 6.8)."""

    #: The input as given (`""` for a non-string).
    text: str
    depth: int
    #: `()` when `unclassifiable` is set.
    segments: tuple[Segment, ...]
    #: A whole-input reason (scan hit, shlex error, operator error, empty,
    #: depth), else None.
    unclassifiable: Optional[str]


# --- Step 1: the reject-scan -------------------------------------------------


def _brace_expands(text: str, start: int) -> bool:
    """Whether the unquoted `{` at `start` opens a brace expansion (a `,` or `..` before its `}`).

    Bash brace-expands only within one word, so an unquoted blank or
    metacharacter before the closing `}` means no expansion (`{ ls; }` is a
    brace group, whose head `{` the head check rejects anyway).
    """
    depth = 1
    found = False
    i = start + 1
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "'":
            end = text.find("'", i + 1)
            if end < 0:
                return False
            i = end + 1
            continue
        if ch == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
            continue
        if ch in _WORD_BREAKS:
            return False
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return found
        elif depth == 1 and (ch == "," or text.startswith("..", i)):
            found = True
        i += 1
    return False


def _scan(text: str) -> tuple[str, Optional[str]]:
    """Normalize the raw line and find the first construct it cannot read (decisions 2-4).

    Returns (normalized text for shlex, reject detail or None). One pass,
    three states: outside quotes, in `'...'` (nothing special), in `"..."`
    (`$(` and backtick live, a backslash escapes the next character).
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    state = ""  # "", "'" or '"'
    word_start = True
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "\x00":
            return "", "NUL"
        if ch in _SENTINEL_CHARS:
            return "", f"U+{ord(ch):04X}"

        if state == "'":
            if ch == "'":
                state = ""
                out.append(ch)
            else:
                out.append(_SENTINELS.get(ch, ch))
            i += 1
            continue

        if state == '"':
            if ch == '"':
                state = ""
                out.append(ch)
                i += 1
            elif ch == "\\":
                if not nxt:
                    return "", '"'
                if nxt == "\n":
                    pass  # line continuation: both removed
                elif nxt in "$`":
                    out.append(nxt)  # literal to bash; shlex would keep the backslash
                elif nxt in _SENTINELS:
                    out.append("\\" + _SENTINELS[nxt])  # bash keeps `\;` in "..."
                elif nxt == "\x00" or nxt in _SENTINEL_CHARS:
                    i += 1
                    continue  # reported on the next iteration
                else:
                    out.append(ch + nxt)
                i += 2
            elif ch == "$" and nxt == "(":
                return "", "$("
            elif ch == "`":
                return "", "`"
            else:
                out.append(_SENTINELS.get(ch, ch))
                i += 1
            continue

        # Outside quotes.
        if ch == "\\":
            if not nxt:
                return "", "\\"
            if nxt == "\n":
                pass  # line continuation: both removed
            elif nxt in _SENTINELS:
                out.append(_SENTINELS[nxt])
            elif nxt == "\x00" or nxt in _SENTINEL_CHARS:
                i += 1
                continue
            else:
                out.append(ch + nxt)
            word_start = False
            i += 2
            continue
        if ch == "'" or ch == '"':
            state = ch
            out.append(ch)
            word_start = False
            i += 1
            continue
        if ch == "#" and word_start:
            end = text.find("\n", i)
            i = n if end < 0 else end
            continue
        if ch == "`":
            return "", "`"
        if ch == "$":
            if nxt == "(":
                return "", "$("
            if nxt in ("'", '"'):
                return "", "$" + nxt
            if nxt == "{":
                out.append("${")  # parameter expansion, not a brace expansion
                word_start = False
                i += 2
                continue
        if ch == "<":
            if text.startswith("<<<", i):
                return "", "<<<"
            if nxt == "<":
                return "", "<<"
            if nxt == "(":
                return "", "<("
        if ch == ">" and nxt == "(":
            return "", ">("
        if ch == "{" and _brace_expands(text, i):
            end = text.find("}", i)
            return "", _cap(text[i:end + 1] if end >= 0 else text[i:])
        out.append(ch)
        word_start = ch in _WORD_BREAKS
        i += 1

    if state:
        return "", state
    return "".join(out), None


# --- Steps 2-3: tokens and segments -----------------------------------------


def _tokens(normalized: str) -> list[str]:
    """shlex with every comment and quote hole closed (see the module docstring). Raises ValueError."""
    lex = shlex.shlex(normalized, posix=True, punctuation_chars=_OPERATOR_CHARS)
    lex.whitespace_split = True
    lex.commenters = ""
    lex.whitespace = lex.whitespace.replace("\n", "")
    return list(lex)


def _is_operator(token: str) -> bool:
    # Correct only because quoted operator characters are sentinels by now.
    return bool(token) and set(token) <= set(_OPERATOR_CHARS)


def _normalize_operator(token: str) -> Optional[str]:
    """A shlex punctuation run as one operator, or None when it is not one."""
    if set(token) == {"\n"}:
        return "\n"
    core = token.rstrip("\n")
    if core in SEPARATORS:
        return core  # `&&<LF>` is a continuation; `;<LF>` is `;`
    if core == token and core in REDIRECTS:
        return core
    return None


@dataclass
class _Raw:
    """A segment while it is being collected."""

    joined_by: Optional[str]
    words: list = field(default_factory=list)
    redirects: list = field(default_factory=list)


def _split(tokens: list[str]) -> tuple[list[_Raw], Optional[str]]:
    """Group tokens into segments (decision 9). Returns (segments, whole-input reason)."""
    segments: list[_Raw] = []
    current = _Raw(joined_by=None)
    prev_was_word = False
    k = 0
    while k < len(tokens):
        token = tokens[k]
        if not _is_operator(token):
            current.words.append(token.translate(_UNSENTINEL))
            prev_was_word = True
            k += 1
            continue
        op = _normalize_operator(token)
        if op is None:
            return [], _cap(token)
        if op in SEPARATORS:
            if not current.words and not current.redirects:
                if op == "\n":
                    # A blank line, a leading newline, or a newline after a
                    # separator (`a &&<LF>b`): nothing to split.
                    prev_was_word = False
                    k += 1
                    continue
                return [], op  # an empty segment: `a ; ; b`, `| a`
            segments.append(current)
            current = _Raw(joined_by=op)
            prev_was_word = False
            k += 1
            continue
        # A redirection: the next token must be a word.
        if k + 1 >= len(tokens) or _is_operator(tokens[k + 1]):
            return [], op
        fd = None
        if prev_was_word and current.words and current.words[-1].isdigit():
            fd = current.words.pop()
        current.redirects.append(Redirect(op, tokens[k + 1].translate(_UNSENTINEL), fd))
        prev_was_word = False
        k += 2
    if current.words or current.redirects:
        segments.append(current)
    elif current.joined_by in _CONTINUING:
        return [], current.joined_by
    if not segments:
        return [], ""  # whitespace or comments only: nothing to vouch for
    return segments, None


# --- Step 4: wrappers, head, inline -----------------------------------------


@dataclass(frozen=True)
class _Wrapper:
    """A wrapper's option table (decision 7). An option outside it is unclassifiable."""

    #: Options that take no value.
    flags: frozenset = frozenset()
    #: Options that take a value, attached (`-uroot`, `--user=root`) or as the next word.
    valued: frozenset = frozenset()
    #: Options whose value is optional and only ever attached (`xargs -i{}`, `--preserve-env=X`).
    optional: frozenset = frozenset()
    #: Positional words before the command (`timeout DURATION`).
    positionals: int = 0
    #: Options that change what the rest of argv means (`env -S`, `sudo -e`).
    rejects: frozenset = frozenset()


_GNU = frozenset({"--help", "--version"})

_WRAPPERS: dict[str, _Wrapper] = {
    "sudo": _Wrapper(
        flags=frozenset({
            "-A", "--askpass", "-b", "--background", "-B", "--bell",
            "-E", "-H", "--set-home", "-i", "--login", "-K", "--remove-timestamp",
            "-k", "--reset-timestamp", "-l", "--list", "-N", "--no-update",
            "-n", "--non-interactive", "-P", "--preserve-groups", "-S", "--stdin",
            "-s", "--shell", "-V", "--version", "-v", "--validate", "--help",
        }),
        valued=frozenset({
            "-C", "--close-from", "-D", "--chdir", "-g", "--group", "--host",
            "-p", "--prompt", "-R", "--chroot", "-r", "--role", "-T",
            "--command-timeout", "-t", "--type", "-U", "--other-user", "-u", "--user",
        }),
        optional=frozenset({"--preserve-env"}),
        # `-e` is sudoedit (the rest are files); `-h` is both --help and -h HOST.
        rejects=frozenset({"-e", "--edit", "-h"}),
    ),
    "doas": _Wrapper(flags=frozenset({"-n", "-s", "-L"}), valued=frozenset({"-C", "-u"})),
    "env": _Wrapper(
        flags=_GNU | frozenset({"-", "-i", "--ignore-environment", "-0", "--null", "-v", "--debug", "--list-signal-handling"}),
        valued=frozenset({"-u", "--unset", "-C", "--chdir"}),
        optional=frozenset({"--block-signal", "--default-signal", "--ignore-signal"}),
        rejects=frozenset({"-S", "--split-string"}),
    ),
    "nohup": _Wrapper(flags=_GNU),
    "time": _Wrapper(
        flags=_GNU | frozenset({"-p", "--portability", "-a", "--append", "-v", "--verbose", "-q", "--quiet"}),
        valued=frozenset({"-f", "--format", "-o", "--output"}),
    ),
    "xargs": _Wrapper(
        flags=_GNU | frozenset({
            "-0", "--null", "-r", "--no-run-if-empty", "-t", "--verbose",
            "-p", "--interactive", "-x", "--exit", "-o", "--open-tty", "--show-limits",
        }),
        valued=frozenset({
            "-a", "--arg-file", "-d", "--delimiter", "-E", "-I", "-L", "-n",
            "--max-args", "-P", "--max-procs", "-s", "--max-chars", "--process-slot-var",
        }),
        optional=frozenset({"-i", "--replace", "-e", "--eof", "-l", "--max-lines"}),
    ),
    # `command -v NAME` only looks NAME up; reading NAME as the head is stricter, not looser.
    "command": _Wrapper(flags=frozenset({"-p", "-v", "-V"})),
    "builtin": _Wrapper(),
    "exec": _Wrapper(flags=frozenset({"-c", "-l"}), valued=frozenset({"-a"})),
    "nice": _Wrapper(flags=_GNU, valued=frozenset({"-n", "--adjustment"})),
    "timeout": _Wrapper(
        flags=_GNU | frozenset({"--preserve-status", "--foreground", "-v", "--verbose"}),
        valued=frozenset({"-s", "--signal", "-k", "--kill-after"}),
        positionals=1,
    ),
    "stdbuf": _Wrapper(flags=_GNU, valued=frozenset({"-i", "--input", "-o", "--output", "-e", "--error"})),
    "setsid": _Wrapper(flags=_GNU | frozenset({"-c", "--ctty", "-f", "--fork", "-w", "--wait"})),
}


def _skip_wrapper_options(spec: _Wrapper, argv: tuple[str, ...], i: int) -> tuple[int, Optional[str]]:
    """Step over a wrapper's options and positionals. Returns (next index, reason or None)."""
    n = len(argv)
    while i < n:
        word = argv[i]
        if word == "--":
            i += 1
            break
        if word == "-":
            if "-" in spec.flags:
                i += 1
                continue
            break
        if not word.startswith("-"):
            break
        if word.startswith("--"):
            name, eq, _ = word.partition("=")
            if name in spec.rejects:
                return i, _cap(word)
            if name in spec.valued:
                i += 1 if eq else 2
            elif name in spec.optional or (name in spec.flags and not eq):
                i += 1
            else:
                return i, _cap(word)
            continue
        # A short cluster: `-in`, `-uroot`, `-n1`.
        k = 1
        step = 1
        while k < len(word):
            opt = "-" + word[k]
            if opt in spec.rejects:
                return i, _cap(word)
            if opt in spec.valued:
                step = 1 if k + 1 < len(word) else 2
                break
            if opt in spec.optional:
                break  # the rest of the cluster is its value
            if opt not in spec.flags:
                return i, _cap(word)
            k += 1
        i += step
    if i > n:
        return n, _cap(argv[-1])  # a valued option with no value
    for _ in range(spec.positionals):
        if i >= n:
            return n, _cap(argv[-1])
        i += 1
    return i, None


def _basename(word: str) -> str:
    base = re.split(r"[/\\]", word)[-1]
    if base.lower().endswith(".exe"):
        base = base[:-4]
    return base


def _head_reason(word: str, head: str) -> Optional[str]:
    """Why this command word cannot be read as a head (decision 6), else None."""
    if "$" in word:
        return _cap(word)  # a variable head (`$CMD`, `"$CMD"`, `r$x`)
    if _DRIVE.match(word) and "/" not in word and "\\" not in word:
        return _cap(word)  # `C:\Windows\cmd.exe` unquoted: shlex ate the backslashes
    if head in _EVAL_HEADS:
        return head
    if head in _ALLOWED_ODD_HEADS:
        return None
    if not _HEAD_CHARS.fullmatch(head):
        return _cap(word)  # glob, `(`, `{`, `^`, `%VAR%`, the empty word
    return None


def _shell_options(argv: tuple[str, ...], head_index: int) -> tuple[int, Optional[str]]:
    """Walk a POSIX shell head's options: (index of the first word after them, the word that set `-c` or None).

    Without `-c`, a word at that index is the script file the shell runs
    (`bash x.sh`), which STORY-010 reads as `shell.inline_interpreter`.
    """
    n = len(argv)
    j = head_index + 1
    c_word: Optional[str] = None
    while j < n:
        word = argv[j]
        if word in ("--", "-"):
            j += 1
            break
        if word.startswith("--"):
            j += 2 if word in ("--rcfile", "--init-file") else 1
            continue
        if len(word) > 1 and word[0] in "-+":
            cluster = word[1:]
            if "c" in cluster and c_word is None:
                c_word = word
            j += 1 + sum(1 for ch in cluster if ch in "oO")
            continue
        break
    return j, c_word


def _inline_script(argv: tuple[str, ...], head_index: int) -> tuple[Optional[str], Optional[str]]:
    """For a POSIX shell head: (the `-c` script or None, reason or None) (decision 8)."""
    j, c_word = _shell_options(argv, head_index)
    if c_word is None:
        return None, None
    if j >= len(argv):
        return None, "-c"  # `-c` with no script
    return argv[j], None


def _segment(raw: _Raw, depth: int) -> Segment:
    argv = tuple(raw.words)
    n = len(argv)
    assignments: list[str] = []
    wrappers: list[str] = []
    reason: Optional[str] = None
    i = 0
    while True:
        while i < n and _ASSIGNMENT.match(argv[i]):
            assignments.append(argv[i])
            i += 1
        if i >= n:
            break
        if "$" in argv[i]:
            break  # the head check below rejects it
        name = _basename(argv[i])
        spec = _WRAPPERS.get(name)
        if spec is None:
            break
        wrappers.append(name)
        i, reason = _skip_wrapper_options(spec, argv, i + 1)
        if reason is not None:
            break

    inline: Optional[ShellParse] = None
    if reason is not None:
        # A wrapper option outside its table: where the command starts is
        # unknown, so no word is named as the head.
        head_index, head = n, wrappers[-1]
    elif i >= n:
        head_index, head = n, (wrappers[-1] if wrappers else "")
    else:
        head_index = i
        head = _basename(argv[i])
        reason = _head_reason(argv[i], head)
        # Folded (STORY-010 decision 7): `BASH -c 'rm -rf /'` must be read too.
        if reason is None and head.lower() in _POSIX_SHELLS:
            script, reason = _inline_script(argv, head_index)
            if script is not None:
                inline = parse_shell(script, depth + 1)
    return Segment(
        argv=argv,
        head_index=head_index,
        head=head,
        assignments=tuple(assignments),
        wrappers=tuple(wrappers),
        redirects=tuple(raw.redirects),
        joined_by=raw.joined_by,
        unclassifiable=reason,
        inline=inline,
    )


def _parse(text: str, depth: int) -> ShellParse:
    if depth > MAX_DEPTH:
        return ShellParse(text, depth, (), f"depth > {MAX_DEPTH}")
    normalized, reason = _scan(text)
    if reason is not None:
        return ShellParse(text, depth, (), _cap(reason))
    try:
        tokens = _tokens(normalized)
    except ValueError as exc:
        return ShellParse(text, depth, (), _cap(str(exc)))
    raws, reason = _split(tokens)
    if reason is not None:
        return ShellParse(text, depth, (), reason)
    return ShellParse(text, depth, tuple(_segment(raw, depth) for raw in raws), None)


def parse_shell(command: str, depth: int = 0) -> ShellParse:
    """Read `command` into segments (PRD-016 Section 6.8 steps 1-4). Never raises.

    `depth` is the inline-interpreter nesting level of `command` (0 for a
    tool call's own command line). Any exception becomes a `ShellParse`
    whose `unclassifiable` is `""`.
    """
    text = command if isinstance(command, str) else ""
    try:
        if not isinstance(command, str):
            return ShellParse(text, depth, (), "")
        return _parse(command, depth)
    except Exception:
        return ShellParse(text, depth, (), "")




# --- Head rules (STORY-010): tables -------------------------------------------

#: `rm`'s recursive and force flags (6.3 `shell.destructive`, 6.8 "matched
#: after normalization"): `-rf`, `-fr`, `-r -f`, `-Rf`, `--recursive --force`.
_RM_SHORT = {"r": "recursive", "R": "recursive", "f": "force"}
_RM_LONG = {"recursive": "recursive", "force": "force"}
#: `chmod`/`chown -R` (6.3). Lowercase `-r` is chmod's "remove read", not recursive.
_CH_SHORT = {"R": "recursive"}
_CH_LONG = {"recursive": "recursive"}
#: 6.3 `shell.destructive`: `rm -r` on one of `/ ~ * .`. The extras close
#: trivial spellings of the same targets (`..`, `$HOME`, a bare drive `C:`);
#: trailing `/`, `\`, `/*` and `\*` are stripped first (`~/`, `/*`, `C:\`).
_DANGEROUS_TARGETS = frozenset({"~", ".", "..", "*", "$HOME", "${HOME}"})
#: Heads destructive with any arguments (6.3 `mkfs`, `shred`; D16 `Format-Volume`).
_ALWAYS_DESTRUCTIVE = frozenset({"mkfs", "shred", "format-volume"})
#: D16: PowerShell's `Remove-Item` and its alias `ri`, destructive with `-Recurse`.
_PS_REMOVE = frozenset({"remove-item", "ri"})
#: D16: cmd's `rd`/`rmdir`/`del`/`erase` with `/s` (in PowerShell they alias
#: `Remove-Item`, so `-Recurse` counts too). POSIX `rmdir` has neither option.
_CMD_REMOVE = frozenset({"rd", "rmdir", "del", "erase"})

#: 6.3 `shell.pipe_to_interpreter` / `shell.inline_interpreter`: heads that
#: run code they read. `powershell` and `cmd` are D16's shells. `python`,
#: `python3`, `python3.11` match `_PYTHON`.
_INTERPRETERS = frozenset(_POSIX_SHELLS | {"node", "perl", "ruby", "php", "pwsh", "powershell", "cmd"})
_PYTHON = re.compile(r"python(\d+(\.\d+)*)?")
_PIPES = frozenset({"|", "|&"})
#: Redirections through which an interpreter reads its script (`sh < x.sh`).
_STDIN_REDIRECTS = frozenset({"<", "<>"})
#: D16: `pwsh`/`powershell` parameters that take code (a prefix of one binds,
#: so `-c`, `-Com`, `-f`, `-enc` count), plus the alias `-ec`.
_PS_INLINE_PARAMS = ("command", "commandwithargs", "encodedcommand", "file")
#: The ones whose value is readable PowerShell text (scanned, decision 5).
_PS_TEXT_PARAMS = frozenset({"command", "commandwithargs"})
#: pwsh parameters that take a value, so the value is not read as a script positional.
_PS_VALUED_PARAMS = (
    "executionpolicy", "workingdirectory", "outputformat", "inputformat",
    "windowstyle", "configurationname", "settingsfile",
)
#: STORY-018: heads an allowlist plausibly holds that run code named in one of
#: their OWN options (the corpus found `git -c alias.x='!cmd' x`, `rg --pre cmd`,
#: `pytest -p plugin` and `npm test --script-shell=cmd` all `shell.allowlisted`).
#: `_code_option` reads the options below as `shell.inline_interpreter`, before
#: the allowlist is consulted, so an allowlist entry can no longer vouch for
#: them. Deny-only: it can only add a rule. Every other option of these heads
#: stays trust in the head (6.6). Closed on purpose; a new head is a new row.
_CODE_OPTION_HEADS = frozenset({"git", "rg", "pytest", "npm", "npx"})
#: `git` subcommands whose `-u` is `--upload-pack` (`git clone -u CMD`).
_GIT_UPLOAD_PACK_SUBCOMMANDS = frozenset({"clone", "fetch", "pull"})
#: Global `git` options whose value is the next word, so it is not the subcommand.
_GIT_GLOBAL_VALUED = frozenset({"-C", "--git-dir", "--work-tree", "--namespace"})
#: `git` long options that name a program, matched by an unambiguous prefix
#: (`--upload-p`, as getopt matches) down to three letters.
_GIT_PROGRAM_OPTIONS = ("upload-pack", "receive-pack", "exec")
#: D16: `Invoke-Expression` runs a string the classifier cannot see.
_IEX = frozenset({"invoke-expression", "iex"})

#: 6.3 `shell.package_install`: head -> subcommands, any of which as a
#: positional (before `--`) is an install; None is any arguments (6.3's
#: `apt*`). npm's list is npm's own aliases of `install`, typos included.
_PACKAGE_INSTALL: dict[str, Optional[frozenset]] = {
    "npm": frozenset({
        "install", "i", "in", "ins", "inst", "insta", "instal",
        "isnt", "isnta", "isntal", "isntall", "add",
    }),
    "pnpm": frozenset({"add"}),
    "yarn": frozenset({"add", "global"}),
    "pip": frozenset({"install"}),
    "uv": frozenset({"add"}),
    "apt": None,
    "apt-get": None,
    "aptitude": None,
    "brew": frozenset({"install"}),
    "gem": frozenset({"install"}),
    "cargo": frozenset({"install"}),
    "go": frozenset({"install"}),
}
#: `pip3`, `pip3.12` read as `pip`.
_PIP = re.compile(r"pip(\d+(\.\d+)*)?")

#: 6.3 `shell.service_control`, the same shape as `_PACKAGE_INSTALL`.
_SERVICE_CONTROL: dict[str, Optional[frozenset]] = {
    "systemctl": None,
    "service": None,
    "launchctl": None,
    "reboot": None,
    "shutdown": None,
    "docker": frozenset({"run", "rm", "kill", "stop"}),
    "podman": frozenset({"run", "rm", "kill", "stop"}),
    "kubectl": frozenset({"delete", "apply"}),
}

#: A segment with one of these wrappers is never `shell.allowlisted`
#: (STORY-010 decision 5): an allowlist entry vouches for the head, not root.
_PRIVILEGE_WRAPPERS = frozenset({"sudo", "doas"})

#: The classic fork bomb, any function name (orchestrator note): the parse
#: reads it as `shell.unclassifiable` only (its head holds `(`). A function
#: whose body pipes the function into itself: `NAME(){ ... NAME|NAME`. The
#: lookbehind starts a name only at a word start, and the match ends at the
#: self-pipe (no trailing `[^}]*}`), so a long body cannot make it quadratic.
_FORK_BOMB = re.compile(r"(?<![^\s;&|(){}])([^\s(){}|&;<>]+)\s*\(\s*\)\s*\{[^}]*?\1\s*\|\s*\1")
_FALLBACK_SPLIT = re.compile(r"[;&|\r\n]+")


# --- Head rules: flag normalizers (Section 6.8) --------------------------------


def _flags(args: tuple[str, ...], short: dict, long: dict) -> dict[str, str]:
    """GNU-style options as canonical names -> the first word that gave each.

    A `-abc` cluster contributes each letter in `short`. A `--name[=v]`
    contributes every `long` option that `name` is a prefix of (getopt takes
    unambiguous prefixes; an ambiguous one counts as all its matches,
    stricter). Scanning stops at `--`.
    """
    found: dict[str, str] = {}
    for word in args:
        if word == "--":
            break
        if word.startswith("--"):
            name = word[2:].partition("=")[0]
            if name:
                for full, canon in long.items():
                    if full.startswith(name):
                        found.setdefault(canon, word)
        elif word.startswith("-") and len(word) > 1:
            for ch in word[1:]:
                if ch in short:
                    found.setdefault(short[ch], word)
    return found


def _positionals(args: tuple[str, ...], *, after_dashdash: bool = True) -> list[str]:
    """Words that are not options; everything after `--` too unless `after_dashdash` is False."""
    out: list[str] = []
    for k, word in enumerate(args):
        if word == "--":
            if after_dashdash:
                out.extend(args[k + 1:])
            break
        if not word.startswith("-"):
            out.append(word)
    return out


def _cmd_switches(args: tuple[str, ...]) -> dict[str, str]:
    """cmd `/x` switches, lowercased, -> the word (`/s/q` gives `s` and `q`)."""
    found: dict[str, str] = {}
    for word in args:
        if word.startswith("/"):
            for piece in word.lower().split("/"):
                if piece:
                    found.setdefault(piece, word)
    return found


def _ps_param(word: str, names, *, slash: bool = False) -> list[str]:
    """The `names` that the PowerShell parameter `word` (`-Rec`, `-Recurse:$true`) is a case-insensitive prefix of."""
    if word.startswith("--") or not (word.startswith("-") or (slash and word.startswith("/"))):
        return []
    name = word[1:].partition(":")[0].lower()
    if not name:
        return []
    return [full for full in names if full.startswith(name)]


def _ps_params(args: tuple[str, ...], names, *, slash: bool = False) -> dict[str, str]:
    """PowerShell parameters bound to `names` (D16: unambiguous prefixes bind; ambiguous count as all) -> word."""
    found: dict[str, str] = {}
    for word in args:
        if word == "--":
            break
        for full in _ps_param(word, names, slash=slash):
            found.setdefault(full, word)
    return found


def _is_dangerous_target(word: str) -> bool:
    w = word
    while True:
        for suffix in ("/*", "\\*", "/", "\\"):
            if w.endswith(suffix):
                w = w[: -len(suffix)]
                break
        else:
            break
    return w == "" or w in _DANGEROUS_TARGETS or bool(_DRIVE.fullmatch(w))


def _detail(head: str, args: tuple[str, ...], words) -> str:
    """The head plus the matched words, in argv order, as written (T11: from the call)."""
    picked = [w for w in dict.fromkeys(words)]
    picked.sort(key=lambda w: args.index(w) if w in args else len(args))
    return _cap(" ".join([head, *picked]))


# --- Head rules: the rules -----------------------------------------------------


def _destructive(head: str, args: tuple[str, ...]) -> Optional[str]:
    """`shell.destructive`'s detail when the head and its normalized flags are destructive, else None (6.3, D16)."""
    low = head.lower()
    if low == "rm":
        found = _flags(args, _RM_SHORT, _RM_LONG)
        # PowerShell's `rm` is `Remove-Item`: `-Recurse -Force` count too.
        for full, word in _ps_params(args, ("recurse", "force")).items():
            found.setdefault("recursive" if full == "recurse" else "force", word)
        if "recursive" not in found:
            return None
        if "force" in found:
            return _detail(head, args, [found["recursive"], found["force"]])
        targets = [w for w in _positionals(args) if _is_dangerous_target(w)]
        if targets:
            return _detail(head, args, [found["recursive"], targets[0]])
        return None
    if low in _ALWAYS_DESTRUCTIVE or low.startswith("mkfs."):
        return _cap(head)
    if low == "dd":
        for word in args:
            if word.lower().startswith("of="):
                return _detail(head, args, [word])
        return None
    if low in ("chmod", "chown"):
        found = _flags(args, _CH_SHORT, _CH_LONG)
        if "recursive" in found:
            targets = [w for w in _positionals(args) if _is_dangerous_target(w)]
            if targets:
                return _detail(head, args, [found["recursive"], targets[0]])
        return None
    if low in _PS_REMOVE:
        found = _ps_params(args, ("recurse",))
        return _detail(head, args, [found["recurse"]]) if found else None
    if low in _CMD_REMOVE:
        switches = _cmd_switches(args)
        if "s" in switches:
            return _detail(head, args, [switches["s"]])
        found = _ps_params(args, ("recurse",))
        return _detail(head, args, [found["recurse"]]) if found else None
    return None


def _is_interpreter(low: str) -> bool:
    return low in _INTERPRETERS or bool(_PYTHON.fullmatch(low))


def _python_inline(args: tuple[str, ...]) -> Optional[str]:
    """The word that makes `python` run code it was handed: a `-c` cluster or a script file. `-m` does not (decision 9)."""
    k = 0
    while k < len(args):
        word = args[k]
        if word == "--":
            return args[k + 1] if k + 1 < len(args) else None
        if word.startswith("--"):
            k += 2 if word == "--check-hash-based-pycs" else 1
            continue
        if word.startswith("-") and len(word) > 1:
            step = 1
            for i, ch in enumerate(word[1:], start=1):
                if ch == "c":
                    return word
                if ch == "m":
                    return None  # an installed module, like the `pytest` head itself
                if ch in "WX":
                    step = 1 if i + 1 < len(word) else 2
                    break
            k += step
            continue
        return word  # `python x.py`, or `python -` (stdin)
    return None


def _cluster_inline(args: tuple[str, ...], letters: str, extra_flags=()) -> Optional[str]:
    """A short cluster holding one of `letters` (`perl -ne`), a word in `extra_flags`, or the first positional."""
    for word in args:
        if word == "--":
            break
        if word in extra_flags:
            return word
        if word.startswith("-") and not word.startswith("--") and len(word) > 1:
            if any(ch in letters for ch in word[1:]):
                return word
            continue
        if word.startswith("--"):
            continue
        return word
    positionals = _positionals(args)
    return positionals[0] if positionals else None


def _ps_inline(args: tuple[str, ...], low: str) -> Optional[tuple[str, Optional[str]]]:
    """`pwsh`/`powershell`: (the triggering word, readable inner text or None) (D16)."""
    k = 0
    while k < len(args):
        word = args[k]
        if word.lower() in ("-ec", "/ec"):
            return word, None
        hits = _ps_param(word, _PS_INLINE_PARAMS, slash=True)
        if hits:
            text = " ".join(args[k + 1:]) if set(hits) & _PS_TEXT_PARAMS else None
            return word, text
        if _ps_param(word, _PS_VALUED_PARAMS, slash=True):
            k += 2
            continue
        if word.startswith("-"):
            k += 1
            continue
        # pwsh reads a positional as `-File`; Windows PowerShell as `-Command`.
        return word, (" ".join(args[k:]) if low == "powershell" else None)
    return None


def _cmd_inline(args: tuple[str, ...]) -> Optional[tuple[str, Optional[str]]]:
    """`cmd /c` and `/k` (any case, `/cdir` attached): (the word, the inner text)."""
    for k, word in enumerate(args):
        low = word.lower()
        if low.startswith("/c") or low.startswith("/k"):
            return word, " ".join([word[2:], *args[k + 1:]]).strip()
    return None


def _git_code_option(args: tuple[str, ...]) -> Optional[str]:
    """`git -c k=v`, `--config-env`, `-u`/`--upload-pack`/`--receive-pack`/`--exec`: the word, else None (STORY-018)."""
    subcommand: Optional[str] = None
    k = 0
    while k < len(args):
        word = args[k]
        k += 1
        if word == "--":
            break
        if word.startswith("--"):
            name = word[2:].split("=", 1)[0]
            if len(name) >= 3 and any(full.startswith(name) for full in _GIT_PROGRAM_OPTIONS):
                return word
            if subcommand is None:
                if "--config-env".startswith(word.split("=", 1)[0]) and len(name) >= 3:
                    return word
                if word in _GIT_GLOBAL_VALUED:
                    k += 1
            continue
        if word.startswith("-") and len(word) > 1:
            if subcommand is None:
                if word == "-C":
                    k += 1
                elif word.startswith("-c") or "u" in word[1:]:
                    return word
            elif subcommand in _GIT_UPLOAD_PACK_SUBCOMMANDS and "u" in word[1:]:
                return word
            continue
        if subcommand is None:
            subcommand = word
    return None


def _code_option(low: str, args: tuple[str, ...]) -> Optional[str]:
    """An option of an allowlistable head that names code to run (`_CODE_OPTION_HEADS`), else None (STORY-018)."""
    if low == "git":
        return _git_code_option(args)
    for word in args:
        if word == "--":
            break
        if low == "rg" and (word == "--pre" or word.startswith("--pre=")):
            return word
        if low == "pytest" and word.startswith("-") and not word.startswith("--") and "p" in word[1:]:
            return word
        if low in ("npm", "npx") and (word == "--script-shell" or word.startswith("--script-shell=")):
            return word
    return None


def _inline_interpreter(segment: Segment, low: str) -> Optional[tuple[str, Optional[str]]]:
    """`shell.inline_interpreter`: (detail, PowerShell/cmd inner text or None), else None (6.3, 6.8, D16)."""
    head, args = segment.head, segment.args
    word: Optional[str] = None
    inner: Optional[str] = None
    if low in _POSIX_SHELLS:
        j, c_word = _shell_options(segment.argv, segment.head_index)
        if c_word is not None:
            word = c_word
        elif j < len(segment.argv):
            word = segment.argv[j]  # a script file: its contents are unreadable
    elif _PYTHON.fullmatch(low):
        word = _python_inline(args)
    elif low == "node":
        word = _cluster_inline(args, "ep", ("--eval", "--print"))
        if word is None:
            for w in args:
                if w.startswith("--eval=") or w.startswith("--print="):
                    word = w
                    break
    elif low == "perl":
        word = _cluster_inline(args, "eE")
    elif low == "ruby":
        word = _cluster_inline(args, "e")
    elif low == "php":
        word = _cluster_inline(args, "rf")
    elif low in ("pwsh", "powershell"):
        hit = _ps_inline(args, low)
        if hit is not None:
            word, inner = hit
    elif low == "cmd":
        hit = _cmd_inline(args)
        if hit is not None:
            word, inner = hit
    elif low in _CODE_OPTION_HEADS:
        word = _code_option(low, args)  # STORY-018
    if word is None and _is_interpreter(low) and any(r.op in _STDIN_REDIRECTS for r in segment.redirects):
        word = "<"
    if word is None:
        return None
    return _cap(f"{head} {word}"), inner


def _subcommand(table: dict, low: str, args: tuple[str, ...]) -> Optional[str]:
    """The subcommand of `table[low]` found among the positionals before `--`, `""` for any-arguments heads, else None."""
    if low not in table:
        return None
    wanted = table[low]
    if wanted is None:
        return ""
    for word in _positionals(args, after_dashdash=False):
        if word in wanted:
            return word
    return None


def _package_install(head: str, low: str, args: tuple[str, ...]) -> Optional[str]:
    """`shell.package_install`'s detail (6.3), else None."""
    key = "pip" if _PIP.fullmatch(low) else low
    sub = _subcommand(_PACKAGE_INSTALL, key, args)
    if sub is None and low == "uv":
        positionals = _positionals(args, after_dashdash=False)
        if "pip" in positionals and "install" in positionals:
            sub = "pip install"
    if sub is None and _PYTHON.fullmatch(low):
        # `python -m pip install x` (decision 9: not inline, but an install).
        for k, word in enumerate(args):
            module = args[k + 1] if word == "-m" and k + 1 < len(args) else (word[2:] if word.startswith("-m") else "")
            if _PIP.fullmatch(module):
                rest = args[k + 2:] if word == "-m" else args[k + 1:]
                if "install" in _positionals(rest, after_dashdash=False):
                    sub = "-m pip install"
                break
    if sub is None:
        return None
    return _cap(f"{head} {sub}" if sub else head)


def _service_control(head: str, low: str, args: tuple[str, ...]) -> Optional[str]:
    """`shell.service_control`'s detail (6.3), else None."""
    sub = _subcommand(_SERVICE_CONTROL, low, args)
    if sub is None:
        return None
    return _cap(f"{head} {sub}" if sub else head)


def _allowlisted(segment: Segment, allow: tuple[tuple[str, ...], ...]) -> bool:
    """6.6 `shell.allow`: the head and the first N-1 args equal an entry's tokens, exactly (case-sensitive).

    Never for a segment run through `sudo`/`doas` or with assignments in
    front (`GIT_SSH_COMMAND=... git fetch`, `LD_PRELOAD=x ls`): those run
    other code under an allowlisted head (decision 5).
    """
    if segment.assignments or _PRIVILEGE_WRAPPERS.intersection(segment.wrappers):
        return False
    args = segment.args
    return any(t[0] == segment.head and args[: len(t) - 1] == t[1:] for t in allow)


# --- Embedded targets (STORY-013): tables ----------------------------------------


@dataclass(frozen=True)
class _Context:
    """The policy's data for one `classify_shell` call (STORY-013 decision D-A), passed down the recursion."""

    allow: tuple[tuple[str, ...], ...] = ()
    network_allow: object = ()
    secret_env: object = ()
    secret_files: object = ()
    protected: object = ()
    workspace_roots: object = ()
    source_tool: str = ""


@dataclass(frozen=True)
class _Opts:
    """An embedding head's option table (decision D-L). Names carry their dashes (`-c`, `--command`).

    An option in none of the valued sets is a flag; one outside the table is
    read as a flag too (for a fetcher, its value then reads as a URL:
    over-blocking, never under-blocking).
    """

    #: Options that take a value, attached (`-ofile`, `--output=f`) or as the next word.
    valued: frozenset = frozenset()
    #: SQL clients: valued options whose value is SQL text.
    text: frozenset = frozenset()
    #: Fetchers: valued options whose value is a URL.
    url: frozenset = frozenset()
    #: Fetchers: valued options whose value is a file the head writes.
    write: frozenset = frozenset()
    #: Fetchers: options that move the real destination out of sight (`net.unparsed`).
    route: frozenset = frozenset()
    #: Options whose value is only ever attached (`mysql -pSECRET`, `--password=x`).
    optional: frozenset = frozenset()
    #: getopt_long: an unambiguous prefix of a long option binds (`--comm` is `--command`).
    prefixes: bool = True
    #: sqlite3: long options take one dash (`-cmd`); `--cmd` is accepted too.
    single_dash_long: bool = False

    def takes_value(self, name: str) -> bool:
        return any(name in table for table in (self.valued, self.text, self.url, self.write, self.route))

    def long_names(self) -> frozenset:
        everything = self.valued | self.text | self.url | self.write | self.route | self.optional
        return frozenset(name for name in everything if name.startswith("--") or self.single_dash_long)


@dataclass(frozen=True)
class _SqlClient:
    """A SQL client head (decision D-H): its dialect, and where its SQL text is."""

    dialect: str
    opts: _Opts
    #: sqlite3: the first positional is the database, every further one is SQL.
    positional_sql: bool = False


_PSQL = _SqlClient(
    "postgres",
    _Opts(
        valued=frozenset({
            "-d", "-f", "-h", "-p", "-U", "-v", "-o", "-L", "-T", "-F", "-R", "-P",
            "--dbname", "--host", "--port", "--username", "--set", "--variable",
            "--output", "--log-file", "--file", "--pset", "--table-attr",
            "--field-separator", "--record-separator",
        }),
        text=frozenset({"-c", "--command"}),
    ),
)
_MYSQL = _SqlClient(
    "mysql",
    _Opts(
        valued=frozenset({
            "-D", "-h", "-P", "-S", "-u", "--database", "--host", "--port", "--socket",
            "--user", "--defaults-file", "--defaults-extra-file", "--login-path",
            "--default-character-set", "--protocol", "--tee", "--pager", "--prompt",
            "--delimiter", "--connect-timeout", "--ssl-ca", "--ssl-cert", "--ssl-key",
        }),
        # `--init-command` runs its SQL on connect, like `-e`.
        text=frozenset({"-e", "--execute", "--init-command"}),
        optional=frozenset({"-p", "--password"}),
    ),
)
_SQL_CLIENTS: dict[str, _SqlClient] = {
    "psql": _PSQL,
    "mysql": _MYSQL,
    "mariadb": _MYSQL,
    "sqlite3": _SqlClient(
        "sqlite",
        _Opts(
            valued=frozenset({
                "-init", "-separator", "-newline", "-nullvalue", "-vfs", "-mmap",
                "-heap", "-lookaside", "-pagecache", "-maxsize",
            }),
            text=frozenset({"-cmd"}),
            prefixes=False,
            single_dash_long=True,
        ),
        positional_sql=True,
    ),
}


@dataclass(frozen=True)
class _Fetcher:
    """An HTTP client head (decision D-L)."""

    opts: _Opts
    #: Prepended to a URL word with no `scheme://`.
    default_scheme: str = "http://"
    #: HTTPie: an optional upper-case METHOD, one URL, then request items.
    httpie: bool = False


_CURL = _Fetcher(
    _Opts(
        valued=frozenset({
            "-A", "-b", "-C", "-d", "-e", "-E", "-F", "-H", "-m", "-P", "-Q", "-r",
            "-T", "-t", "-u", "-U", "-w", "-X", "-y", "-Y", "-z",
            "--user-agent", "--cookie", "--continue-at", "--data", "--data-raw",
            "--data-binary", "--data-ascii", "--data-urlencode", "--json", "--referer",
            "--cert", "--cert-type", "--key", "--key-type", "--pass", "--cacert",
            "--capath", "--form", "--form-string", "--header", "--proxy-header",
            "--max-time", "--connect-timeout", "--retry", "--retry-delay",
            "--retry-max-time", "--max-redirs", "--range", "--upload-file", "--user",
            "--proxy-user", "--write-out", "--request", "--limit-rate",
            "--max-filesize", "--interface", "--dns-servers", "--oauth2-bearer",
            "--speed-time", "--speed-limit", "--time-cond", "--noproxy", "--variable",
            "--url-query", "--proto", "--proto-redir", "--proto-default", "--ciphers",
            "--aws-sigv4", "--netrc-file", "--quote", "--ftp-port", "--local-port",
            "--keepalive-time", "--expect100-timeout", "--parallel-max", "--rate",
            "--mail-from", "--mail-rcpt", "--mail-auth", "--login-options",
            "--hsts", "--alt-svc", "--etag-compare", "--create-file-mode",
            "--telnet-option", "--tls-max", "--service-name", "--sasl-authzid",
        }),
        url=frozenset({
            "-x", "--proxy", "--preproxy", "--url", "--doh-url",
            "--socks4", "--socks4a", "--socks5", "--socks5-hostname",
        }),
        write=frozenset({
            "-o", "--output", "-D", "--dump-header", "-c", "--cookie-jar", "--trace",
            "--trace-ascii", "--stderr", "--libcurl", "--etag-save", "--output-dir",
        }),
        route=frozenset({
            "--resolve", "--connect-to", "-K", "--config", "--unix-socket",
            "--abstract-unix-socket",
        }),
        # curl matches long options exactly.
        prefixes=False,
    )
)
_WGET = _Fetcher(
    _Opts(
        valued=frozenset({
            "-t", "-T", "-w", "-U", "-l", "-A", "-R", "-D", "-X", "-I", "-Q",
            "--tries", "--timeout", "--dns-timeout", "--connect-timeout",
            "--read-timeout", "--wait", "--waitretry", "--user-agent", "--level",
            "--accept", "--reject", "--domains", "--exclude-domains",
            "--exclude-directories", "--include-directories", "--quota", "--header",
            "--user", "--password", "--http-user", "--http-password", "--proxy-user",
            "--proxy-password", "--post-data", "--post-file", "--body-data",
            "--body-file", "--method", "--referer", "--load-cookies", "--limit-rate",
            "--bind-address", "--ca-certificate", "--certificate", "--private-key",
            "--default-page", "--local-encoding", "--remote-encoding",
            "--restrict-file-names", "--ftp-user", "--ftp-password", "--cut-dirs",
            "--progress", "--secure-protocol", "--ciphers", "--max-redirect",
            "--accept-regex", "--reject-regex", "--regex-type", "--backups",
            "--hsts-file", "--ca-directory",
        }),
        url=frozenset({"-B", "--base"}),
        write=frozenset({
            "-O", "--output-document", "-o", "--output-file", "-a", "--append-output",
            "-P", "--directory-prefix", "--save-cookies", "--warc-file", "--rejected-log",
        }),
        route=frozenset({"-e", "--execute", "-i", "--input-file", "--config"}),
    )
)
_HTTPIE_OPTS = _Opts(
    valued=frozenset({
        "-a", "-A", "-p", "-s", "-P", "--auth", "--auth-type", "--session",
        "--session-read-only", "--verify", "--cert", "--cert-key", "--cert-key-pass",
        "--timeout", "--max-redirects", "--max-headers", "--print", "--pretty",
        "--style", "--format-options", "--response-charset", "--response-mime",
        "--ssl", "--ciphers", "--boundary", "--raw", "--default-scheme",
        "--history-print",
    }),
    url=frozenset({"--proxy"}),
    write=frozenset({"-o", "--output"}),
)
_FETCHERS: dict[str, _Fetcher] = {
    "curl": _CURL,
    "wget": _WGET,
    "http": _Fetcher(_HTTPIE_OPTS, "http://", httpie=True),
    "https": _Fetcher(_HTTPIE_OPTS, "https://", httpie=True),
}

#: Decision D-K: heads whose path arguments are read (STORY-013's five plus
#: the content readers an allowlist plausibly holds; `cp .env /tmp/x` is
#: exfiltration). Matched case-folded; `type` is cmd's, `get-content`/`gc`
#: PowerShell's.
_READ_HEADS = frozenset({
    "cat", "less", "more", "head", "tail",
    "grep", "egrep", "fgrep", "rg", "sed", "awk", "base64", "xxd", "od",
    "strings", "cp", "type", "get-content", "gc",
})

#: Decision D-J: heads that print the whole environment with no names.
_ENV_DUMP_HEADS = frozenset({"env", "printenv", "set", "export", "declare", "typeset"})

#: `http_proxy=...` on a segment routes the head's requests (decision D-L).
_PROXY_VARIABLES = frozenset({"http_proxy", "https_proxy", "all_proxy"})

#: Decision D-B: redirections that write their target, and those that read it.
_WRITE_REDIRECTS = frozenset({">", ">>", ">|", "&>", "&>>", "<>"})
_READ_REDIRECTS = frozenset({"<", "<>"})
#: Exempt from the path rules, exactly; Windows device names in any case.
_DEVICE_TARGETS = frozenset({"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty"})
_WINDOWS_DEVICES = frozenset({"NUL", "CON"})
#: A descriptor after `>&` / `<&` (`2>&1`, `>&-`, `>&2-`): a duplication, not a file.
_FD_TARGET = re.compile(r"\d+-?|-")

_URL_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
_HTTP_METHOD = re.compile(r"[A-Z]+")
#: HTTPie's `--proxy PROTOCOL:URL`.
_HTTPIE_PROXY = re.compile(r"[A-Za-z]+:(?=[A-Za-z][A-Za-z0-9+.-]*://)")


# --- Embedded targets: helpers ----------------------------------------------------


def _resolve_long(opts: _Opts, name: str) -> str:
    """The table option `name` binds to (getopt_long prefixes, decision D-L); `name` when none or not allowed.

    An ambiguous prefix binds to its strictest match: SQL text, routing, URL,
    write, then any valued option.
    """
    known = opts.long_names()
    if name in known or not opts.prefixes or len(name) < 3:
        return name
    matches = sorted(full for full in known if full.startswith(name))
    if not matches:
        return name
    for table in (opts.text, opts.route, opts.url, opts.write, opts.valued):
        for full in matches:
            if full in table:
                return full
    return matches[0]


def _walk_options(opts: _Opts, args: tuple[str, ...]) -> list[tuple[Optional[str], Optional[str]]]:
    """GNU-style options in argv order: (option, value or None), or (None, positional) (decision D-L).

    Handles clusters (`-sSLo out`, `-qO-`), attached values (`-ofile`,
    `--output=f`) and `--`. A flag yields (option, None), as does a valued
    option with no word after it.
    """
    out: list[tuple[Optional[str], Optional[str]]] = []
    n = len(args)
    k = 0
    rest = False
    while k < n:
        word = args[k]
        if rest or word == "-" or not word.startswith("-"):
            out.append((None, word))
            k += 1
            continue
        if word == "--":
            rest = True
            k += 1
            continue
        if word.startswith("--") or opts.single_dash_long:
            raw = word[1:] if opts.single_dash_long and word.startswith("--") else word
            name, eq, attached = raw.partition("=")
            name = _resolve_long(opts, name)
            if name in opts.optional or not opts.takes_value(name):
                out.append((name, attached if eq else None))
                k += 1
            elif eq:
                out.append((name, attached))
                k += 1
            else:
                out.append((name, args[k + 1] if k + 1 < n else None))
                k += 2
            continue
        step = 1
        for j in range(1, len(word)):
            opt = "-" + word[j]
            if opt in opts.optional:
                out.append((opt, word[j + 1:] or None))
                break
            if opts.takes_value(opt):
                if j + 1 < len(word):
                    out.append((opt, word[j + 1:]))
                else:
                    out.append((opt, args[k + 1] if k + 1 < n else None))
                    step = 2
                break
            out.append((opt, None))
        k += step
    return out


def _sql_texts(client: _SqlClient, args: tuple[str, ...]) -> list[str]:
    """The SQL a client head runs from its own argv (decision D-H)."""
    texts: list[str] = []
    positionals: list[str] = []
    for name, value in _walk_options(client.opts, args):
        if name is None:
            positionals.append(value)
        elif name in client.opts.text and value is not None:
            texts.append(value)
    if client.positional_sql:
        texts.extend(positionals[1:])
    return texts


def _with_scheme(word: str, fetcher: _Fetcher) -> str:
    """A URL word as the head reads it: `http://` for a scheme-less word (STORY-012 decision)."""
    if _URL_SCHEME.match(word):
        return word
    if fetcher.httpie and word.startswith(":"):
        return fetcher.default_scheme + "localhost" + word  # HTTPie's `:3000/x`
    return fetcher.default_scheme + word


def _fetch_targets(fetcher: _Fetcher, args: tuple[str, ...]):
    """(network items, values read, values written) of a fetcher's argv, in argv order (decision D-L).

    A network item is ("url", url) or ("route", option).
    """
    pairs = _walk_options(fetcher.opts, args)
    positionals = [value for name, value in pairs if name is None]
    method_index = -1
    if fetcher.httpie and len(positionals) >= 2 and _HTTP_METHOD.fullmatch(positionals[0]):
        method_index = 0
    url_index = method_index + 1
    net: list[tuple[str, str]] = []
    reads: list[str] = []
    writes: list[str] = []
    index = -1
    for name, value in pairs:
        if name is None:
            index += 1
            if index == method_index:
                continue
            if fetcher.httpie and index != url_index:
                reads.append(value)  # an HTTPie request item (`f=@.env`, `h:v`)
            else:
                net.append(("url", _with_scheme(value, fetcher)))
            continue
        if name in fetcher.opts.route:
            net.append(("route", name))
        elif value is None:
            continue
        elif name in fetcher.opts.url:
            if fetcher.httpie:
                value = _HTTPIE_PROXY.sub("", value, count=1)
            net.append(("url", _with_scheme(value, fetcher)))
        elif name in fetcher.opts.write:
            writes.append(value)
        else:
            reads.append(value)
    return net, reads, writes


def _reader_words(args: tuple[str, ...]) -> list[str]:
    """A reader head's path arguments (decision D-K): positionals, everything after `--`, `--opt=value` values."""
    out: list[str] = []
    rest = False
    for word in args:
        if rest:
            out.append(word)
        elif word == "--":
            rest = True
        elif word.startswith("--"):
            name, eq, value = word.partition("=")
            if eq and value:
                out.append(value)
        elif not (word.startswith("-") and len(word) > 1):
            out.append(word)
    return out


def _read_candidates(value: str) -> list[str]:
    """A fetcher option value and the file it names after `@` or `<` (`-d @.env`, `-F f=<.env`)."""
    out = [value]
    for mark in ("@", "<"):
        if mark in value:
            out.append(value.split(mark, 1)[1])
    return out


def _exempt(target: str) -> bool:
    return target in _DEVICE_TARGETS or target.upper() in _WINDOWS_DEVICES


def _env_dump(segment: Segment, low: str, op: Operation, ctx: _Context) -> list[Classification]:
    """Decision D-J: the whole environment is always `secret.read`; `printenv NAME`, `declare -p NAME` check NAME."""
    args = segment.args
    if low == "env":
        # Only the wrapper with no command (`env`, `sudo env`, `env -u X`).
        return [Classification("secret.read", op, _cap(segment.head))] if segment.head_index >= len(segment.argv) else []
    if segment.head_index >= len(segment.argv):
        return []
    names = [w for w in args if not w.startswith("-")]
    flags = "".join(w[1:] for w in args if w.startswith("-") and not w.startswith("--"))
    dump = False
    check: list[str] = []
    if low == "printenv":
        dump = not names
        check = names
    elif low == "set":
        dump = not args
    elif low == "export":
        dump = all(w == "-p" for w in args)
    elif low in ("declare", "typeset"):
        dump = not names
        if "p" in flags:
            check = [w.partition("=")[0] for w in names]
    if dump:
        return [Classification("secret.read", op, _cap(segment.head))]
    out: list[Classification] = []
    for name in check:
        hit = secrets.classify_env_reference(name, ctx.secret_env, operation=op)
        if hit is not None:
            out.append(hit)
    return out


def _embedded(segment: Segment, op: Operation, ctx: _Context) -> list[Classification]:
    """Step 3 of `_segment_rules`: SQL, network, secret, then writes (PRD 6.4; module docstring)."""
    low = segment.head.lower()
    args = segment.args
    has_command = segment.head_index < len(segment.argv)
    st = ctx.source_tool
    sql_out: list[Classification] = []
    net_out: list[Classification] = []
    secret_out: list[Classification] = []
    write_out: list[Classification] = []
    write_targets: list[str] = []

    def secret_file(word: str) -> bool:
        hit = secrets.classify_secret_read(word, ctx.secret_files, source_tool=st)
        if hit is not None:
            secret_out.append(hit)
        return hit is not None

    # 1. SQL.
    client = _SQL_CLIENTS.get(low) if has_command else None
    if client is not None:
        for text in _sql_texts(client, args):
            sql_out.extend(sql.classify_sql(text, client.dialect, source_tool=st))

    # 2. Network: proxy assignments, then the fetcher's argv.
    if has_command:
        for assignment in segment.assignments:
            name, _, value = assignment.partition("=")
            if name.rstrip("+").lower() in _PROXY_VARIABLES and value.strip():
                net_out.append(network.classify_url(_with_scheme(value, _CURL), ctx.network_allow, source_tool=st))
    fetcher = _FETCHERS.get(low) if has_command else None
    fetch_reads: list[str] = []
    if fetcher is not None:
        items, fetch_reads, fetch_writes = _fetch_targets(fetcher, args)
        for kind, value in items:
            if kind == "url":
                net_out.append(network.classify_url(value, ctx.network_allow, source_tool=st))
            else:
                net_out.append(Classification("net.unparsed", Operation("http", value, st), _cap(value)))
        write_targets.extend(w for w in fetch_writes if w != "-")

    # 3. Secret: (a) files a reader or fetcher reads, (b) `<` targets,
    #    (c) env references in any word, (d) whole-environment dumps.
    if has_command and low in _READ_HEADS:
        for word in _reader_words(args):
            secret_file(word)
    for value in fetch_reads:
        for candidate in _read_candidates(value):
            if secret_file(candidate):
                break
    for r in segment.redirects:
        if r.op in _READ_REDIRECTS or (r.op == "<&" and not _FD_TARGET.fullmatch(r.target)):
            if not _exempt(r.target):
                secret_file(r.target)
    script = segment.inline.text if segment.inline is not None else None
    words = [w for w in segment.argv if w != script] + [r.target for r in segment.redirects]
    references: dict[Classification, None] = {}
    for word in words:
        for name in secrets.env_references(word):
            hit = secrets.classify_env_reference(name, ctx.secret_env, operation=op)
            if hit is not None:
                references.setdefault(hit)
    secret_out.extend(references)
    if low in _ENV_DUMP_HEADS:
        secret_out.extend(_env_dump(segment, low, op, ctx))

    # 4. Writes: output redirects, then the fetcher's output options.
    redirect_writes = [
        r.target
        for r in segment.redirects
        if r.op in _WRITE_REDIRECTS or (r.op == ">&" and not _FD_TARGET.fullmatch(r.target))
    ]
    for target in redirect_writes + write_targets:
        if not _exempt(target):
            write_out.append(paths.classify_write(target, ctx.protected, ctx.workspace_roots, source_tool=st))

    return sql_out + net_out + secret_out + write_out


# --- Flattening ------------------------------------------------------------------


def _fallback_destructive(text: str, op: Operation) -> list[Classification]:
    """Best-effort `shell.destructive` for text the tokenizer rejected as a whole (decision 6).

    Split on `; & |` and newlines, then on whitespace, quotes stripped,
    leading assignments and wrapper names skipped. Only ever adds a
    non-grantable deny to input that is already a non-grantable
    `shell.unclassifiable`, so it cannot loosen anything.
    """
    out: list[Classification] = []
    for piece in _FALLBACK_SPLIT.split(text):
        words = [w.strip("'\"") for w in piece.split()]
        k = 0
        while k < len(words) and (_ASSIGNMENT.match(words[k]) or words[k] in _WRAPPERS):
            k += 1
        if k < len(words):
            detail = _destructive(_basename(words[k]), tuple(words[k + 1:]))
            if detail is not None:
                out.append(Classification("shell.destructive", op, detail))
    return out


def _inner_dangers(parse: ShellParse, op: Operation) -> list[Classification]:
    """PowerShell/cmd inner text, read as shell only for `shell.destructive` and `iex` (decision 5).

    Its other `shell.unclassifiable`s are dropped: PowerShell's `$(...)` and
    `{ }` are not POSIX, and the outer `shell.inline_interpreter` stands. Text
    past `MAX_DEPTH` is unread, so that one is kept (D3, T12).
    """
    if parse.unclassifiable is not None:
        if parse.depth > MAX_DEPTH:
            return [Classification("shell.unclassifiable", op, parse.unclassifiable)]
        return _fallback_destructive(parse.text, op)
    out: list[Classification] = []
    for segment in parse.segments:
        if segment.inline is not None:
            out.extend(_inner_dangers(segment.inline, op))
        if segment.unclassifiable is not None:
            continue
        low = segment.head.lower()
        if low in ("pwsh", "powershell", "cmd"):
            hit = _inline_interpreter(segment, low)
            if hit is not None and hit[1] is not None:
                out.extend(_inner_dangers(parse_shell(hit[1], parse.depth + 1), op))
        detail = _destructive(segment.head, segment.args)
        if detail is not None:
            out.append(Classification("shell.destructive", op, detail))
        if low in _IEX:
            out.append(Classification("shell.unclassifiable", op, _cap(segment.head)))
    return out


def _segment_rules(segment: Segment, depth: int, op: Operation, ctx: _Context) -> list[Classification]:
    """One segment's classifications, in decision 2's order (PRD 6.4: what is embedded comes first)."""
    out: list[Classification] = []
    # 1. The POSIX `-c` script, read by STORY-009's recursion.
    if segment.inline is not None:
        out.extend(_flatten(segment.inline, op, ctx))
    if segment.unclassifiable is not None:
        out.append(Classification("shell.unclassifiable", op, segment.unclassifiable))
        return out
    head, args = segment.head, segment.args
    low = head.lower()
    inline = _inline_interpreter(segment, low)
    # 2. PowerShell/cmd inner text (decision 5).
    if inline is not None and inline[1] is not None:
        out.extend(_inner_dangers(parse_shell(inline[1], depth + 1), op))
    # 3. The embedded SQL / URL / secret / write classifications of this
    #    segment (STORY-013), before the head's own rule (PRD 6.4). They are
    #    not dangers: the allowlist below still applies (decision D-F).
    out.extend(_embedded(segment, op, ctx))
    # 4. The head's danger rules, non-grantable first (decision 2).
    dangers: list[Classification] = []
    detail = _destructive(head, args)
    if detail is not None:
        dangers.append(Classification("shell.destructive", op, detail))
    if segment.joined_by in _PIPES and _is_interpreter(low):
        dangers.append(Classification("shell.pipe_to_interpreter", op, _cap(f"{segment.joined_by} {head}")))
    if low in _IEX:
        dangers.append(Classification("shell.unclassifiable", op, _cap(head)))
    if inline is not None:
        dangers.append(Classification("shell.inline_interpreter", op, inline[0]))
    detail = _package_install(head, low, args)
    if detail is not None:
        dangers.append(Classification("shell.package_install", op, detail))
    detail = _service_control(head, low, args)
    if detail is not None:
        dangers.append(Classification("shell.service_control", op, detail))
    out.extend(dangers)
    # 5. Only when no other rule fired (PRD 6.3): the allowlist, else the floor.
    if not dangers:
        rule: RuleId = "shell.allowlisted" if _allowlisted(segment, ctx.allow) else "shell.unlisted"
        out.append(Classification(rule, op, _cap(head)))
    return out


def _flatten(parse: ShellParse, op: Operation, ctx: _Context) -> list[Classification]:
    """Per segment, left to right, `_segment_rules`; one `shell.unclassifiable` (plus the fallback) for a parse that failed."""
    if parse.unclassifiable is not None:
        return [Classification("shell.unclassifiable", op, parse.unclassifiable)] + (
            _fallback_destructive(parse.text, op) if parse.depth <= MAX_DEPTH else []
        )
    out: list[Classification] = []
    for segment in parse.segments:
        out.extend(_segment_rules(segment, parse.depth, op, ctx))
    return out


def _first_word(text) -> str:
    if not isinstance(text, str):
        return ""
    parts = text.split(None, 1)
    return _cap(parts[0]) if parts else ""


def _allow_tokens(shell_allow) -> tuple[tuple[str, ...], ...]:
    """Each `shell.allow` entry split on whitespace; a non-`str` or blank entry is skipped."""
    out = []
    for entry in shell_allow or ():
        if isinstance(entry, str) and entry.split():
            out.append(tuple(entry.split()))
    return tuple(out)


def classify_shell(
    command: str,
    shell_allow=(),
    *,
    network_allow=(),
    secret_env=(),
    secret_files=(),
    protected=(),
    workspace_roots=(),
    source_tool: str = "",
) -> tuple[Classification, ...]:
    """Classify every simple command in `command`, in order (PRD-016 F3). Never raises.

    One `shell.unclassifiable` for a line that cannot be read as a whole
    (plus the fallback's `shell.destructive`, decision 6); otherwise one or
    more classifications per segment (see `_segment_rules`). `shell_allow` is
    the policy's `shell.allow` entries (6.6); the default `()` allowlists
    nothing, the built-in policy's value.

    The keyword arguments feed the embedded targets (STORY-013, decision
    D-A): `network_allow` is `policy.network_allow`, `secret_env` and
    `secret_files` are `policy.secrets.env.compiled` and
    `policy.secrets.files.compiled`, `protected` is
    `policy.protected_paths.compiled`, `workspace_roots` is
    `policy.workspace_roots`. Their `()` defaults match no secret and protect
    no path, so the engine must pass every one: STORY-014 calls
    `classify_shell(op.target, policy.shell_allow,
    network_allow=policy.network_allow,
    secret_env=policy.secrets.env.compiled,
    secret_files=policy.secrets.files.compiled,
    protected=policy.protected_paths.compiled,
    workspace_roots=policy.workspace_roots, source_tool=op.source_tool)`.
    They are passed to the sibling classifiers as given. A fork bomb anywhere in the text
    adds `shell.destructive` last. `source_tool` names the tool the command
    came from, for the audit. Any exception becomes one
    `shell.unclassifiable` whose detail is the input's first word.
    `BaseException` (KeyboardInterrupt) is deliberately not caught.
    """
    target = command if isinstance(command, str) else ""
    op = Operation(kind="shell", target=target, source_tool=source_tool)
    try:
        if not isinstance(command, str):
            return (Classification("shell.unclassifiable", op, ""),)
        ctx = _Context(
            allow=_allow_tokens(shell_allow),
            network_allow=network_allow,
            secret_env=secret_env,
            secret_files=secret_files,
            protected=protected,
            workspace_roots=workspace_roots,
            source_tool=source_tool,
        )
        out = _flatten(parse_shell(command), op, ctx)
        normalized = command.replace("\r\n", "\n").replace("\r", "\n")
        if "(" in normalized and "|" in normalized:
            match = _FORK_BOMB.search(normalized)
            if match is not None:
                out.append(Classification("shell.destructive", op, _cap(match.group(0))))
        return tuple(out)
    except Exception:
        return (Classification("shell.unclassifiable", op, _first_word(command)),)
