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
`dash`, `ksh`) with `-c`, the script is parsed again at `depth + 1` into
`Segment.inline`; text at depth > `MAX_DEPTH` (3) is unclassifiable without
being read. What `-c` *means* (`shell.inline_interpreter`), and `pwsh
-Command`, `cmd /c`, `python -c`, are STORY-010's.

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
secret reads) consume is `parse_shell`, `ShellParse`, `Segment` and
`Redirect` as defined below. Until STORY-010, every readable segment
classifies as the placeholder `shell.unlisted` (deny by default, grantable):
nothing here is looser than the head rules will be.

Every classification's `operation` is `Operation("shell", command,
source_tool)` with the **whole input** as the target, as `sql.py` does it.
The `detail` is the matched fragment of the call (`$(`, `eval`, the head),
at most 32 characters (T11).

Pure (PRD-016 Section 6.12): no settings, no I/O. The `shell_allow` list
STORY-010 needs will arrive as an argument from the caller, never through
`settings` or `action_config`.
"""

import re
import shlex
from dataclasses import dataclass, field
from typing import Optional

from app.services.action_classifiers import Classification, Operation, RuleId

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


def _inline_script(argv: tuple[str, ...], head_index: int) -> tuple[Optional[str], Optional[str]]:
    """For a POSIX shell head: (the `-c` script or None, reason or None) (decision 8)."""
    n = len(argv)
    j = head_index + 1
    has_c = False
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
            if "c" in cluster:
                has_c = True
            j += 1 + sum(1 for ch in cluster if ch in "oO")
            continue
        break
    if not has_c:
        return None, None
    if j >= n:
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
        if reason is None and head in _POSIX_SHELLS:
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


def _flatten(parse: ShellParse, op: Operation) -> list[Classification]:
    """Per segment, left to right: its inline script's classifications, then its own (PRD 6.4)."""
    if parse.unclassifiable is not None:
        return [Classification("shell.unclassifiable", op, parse.unclassifiable)]
    out: list[Classification] = []
    for segment in parse.segments:
        if segment.inline is not None:
            out.extend(_flatten(segment.inline, op))
        if segment.unclassifiable is not None:
            out.append(Classification("shell.unclassifiable", op, segment.unclassifiable))
        else:
            # Placeholder until STORY-010's head rules replace it: the deny-by-
            # default floor for a head nobody has listed (plan decision 1).
            rule: RuleId = "shell.unlisted"
            out.append(Classification(rule, op, _cap(segment.head)))
    return out


def _first_word(text) -> str:
    if not isinstance(text, str):
        return ""
    parts = text.split(None, 1)
    return _cap(parts[0]) if parts else ""


def classify_shell(command: str, *, source_tool: str = "") -> tuple[Classification, ...]:
    """Classify every simple command in `command`, in order (PRD-016 F3). Never raises.

    One `shell.unclassifiable` for a line that cannot be read as a whole;
    otherwise one or more classifications per segment (see `_flatten`).
    `source_tool` names the tool the command came from, for the audit. Any
    exception becomes one `shell.unclassifiable` whose detail is the input's
    first word. `BaseException` (KeyboardInterrupt) is deliberately not caught.
    """
    target = command if isinstance(command, str) else ""
    op = Operation(kind="shell", target=target, source_tool=source_tool)
    try:
        if not isinstance(command, str):
            return (Classification("shell.unclassifiable", op, ""),)
        return tuple(_flatten(parse_shell(command), op))
    except Exception:
        return (Classification("shell.unclassifiable", op, _first_word(command)),)
