"""The secret classifier: credential files and secret environment variables (PRD-016 Sections 6.3, 6.6, F4, F6).

Section 6.3's secret row has one rule, `secret.read` (deny, grantable through
`action:secret:read`). Three things produce it:

- **A read of a secret file** (F4): `classify_secret_read(path,
  secret_files)` returns `secret.read` when a compiled `secrets.files` glob
  matches the path, else None. It delegates to `paths.classify_read`, which
  owns the match (the three candidates of `paths`'s docstring, so `.ssh`
  matches `.ssh/**`) and the fixed `/proc/<pid>/environ` rule. The import
  runs `secrets -> paths` only (STORY-013 plan, decision D-D). OpenCode
  `glob.pattern`, `grep.include` and Cline 3.x `search_files.file_pattern`
  reach the same check as `fs_read` operations (D15): a glob target is
  matched *literally* (`../../**/.env*` matches `.env*`); a wildcard that
  could only name a secret (`**/.e*`) is not resolved, the same limitation
  D15 accepts for a directory search (`grep path=.`).
- **A reference to a secret variable** (F6): `env_references(word)` finds the
  names a word expands (`$NAME`, `${NAME...}`, `${#NAME}`, PowerShell
  `$env:NAME` / `${env:NAME}`, cmd `%NAME%`), and
  `classify_env_reference(name, secret_env, operation=...)` returns
  `secret.read` when a compiled `secrets.env` glob matches the name. An
  indirect expansion `${!x}` names a variable nobody can see, so it is
  always `secret.read` (detail `${!`). The shell classifier scans every
  word of a readable segment (decision D-I): the exfiltration is `curl -d
  "$OPENROUTER_API_KEY" ...`, not only `echo`.
- **The whole environment** (F6: "always `secret.read`", whatever
  `secrets.env` says): `env` / `printenv` with no names and their relatives
  are recognized by the shell classifier (decision D-J); `/proc/*/environ`
  by `paths`.

The globs arrive compiled from `action_config` (`Globs.compiled`, STORY-006
plan decision 6): name globs `^<body>$`, path globs `(?:^|/)<body>$`, both
IGNORECASE. This module never translates a glob (decision D-C); an entry
without `.search` is skipped.

What the shell cannot tell apart: a single-quoted `'$X'` is literal to bash,
but after shlex it looks like `$X`, so it over-matches. Over-matching only
adds a grantable deny (T10's "fails closed" direction), and the built-in
`*KEY*` already matches `$KEYBOARD`.

Every classification's `detail` comes from the call (the matched path tail
or the variable name, at most 32 characters), never from a configured glob
(T11). Never raises: any `Exception` is `secret.read` with detail `""`.
`BaseException` is not caught.

Pure (PRD-016 Section 6.12): no settings, no I/O. The only `app` imports are
the vocabulary and `paths`.
"""

import re
from typing import Iterable, Optional

from app.services.action_classifiers import Classification, Operation, paths

_DETAIL_MAX = 32
#: The sentinel `env_references` returns for an indirect expansion `${!x}`.
INDIRECT = "${!"

# One pass over a word, in order: `${!` (indirection), `${#NAME` / `${NAME` /
# `${env:NAME`, `$env:NAME` / `$NAME`, `%NAME%`. Special parameters (`$1`,
# `$?`, `$$`, `$@`) do not start with a name character, so they never match.
_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_REFERENCE = re.compile(
    r"(?P<indirect>\$\{!)"
    r"|\$\{#?(?:(?i:env):)?(?P<braced>" + _NAME + r")"
    r"|\$(?:(?i:env):)?(?P<plain>" + _NAME + r")"
    r"|%(?P<cmd>" + _NAME + r")%"
)


def env_references(word: str) -> tuple[str, ...]:
    """The variable names `word` expands, in order; `INDIRECT` for each `${!` (F6, decision D-I).

    `"$AWS_KEY/x"` -> `("AWS_KEY",)`; `"${x,,}"` -> `("x",)`; `"$env:Path"`
    -> `("Path",)`; `"%GITHUB_TOKEN%"` -> `("GITHUB_TOKEN",)`; `"$1 $$"` ->
    `()`. A non-`str` has no references.
    """
    if not isinstance(word, str) or ("$" not in word and "%" not in word):
        return ()
    out: list[str] = []
    for match in _REFERENCE.finditer(word):
        if match.group("indirect"):
            out.append(INDIRECT)
        else:
            out.append(match.group("braced") or match.group("plain") or match.group("cmd"))
    return tuple(out)


def classify_env_reference(
    name: str, secret_env: Iterable = (), *, operation: Operation
) -> Optional[Classification]:
    """`secret.read` when a `secrets.env` glob matches the variable `name`, else None (F6). Never raises.

    `secret_env` is `policy.secrets.env.compiled` (anchored, IGNORECASE:
    `*TOKEN*` matches `github_token`). `INDIRECT` is always `secret.read`.
    `operation` is the operation the reference was found in (the shell's,
    decision D-E). A non-`str` name is None; any exception is `secret.read`
    with detail `""`.
    """
    try:
        if not isinstance(name, str):
            return None
        if name == INDIRECT:
            return Classification("secret.read", operation, INDIRECT)
        for pattern in secret_env or ():
            if hasattr(pattern, "search") and pattern.search(name) is not None:
                return Classification("secret.read", operation, name[:_DETAIL_MAX])
        return None
    except Exception:
        return Classification("secret.read", operation, "")


def classify_secret_read(path: str, secret_files: Iterable = (), *, source_tool: str = "") -> Optional[Classification]:
    """`secret.read` for a read of `path` that names a secret file, else None (F4). Never raises.

    `secret_files` is `policy.secrets.files.compiled`. The result is
    `paths.classify_read`'s, kept only when it is `secret.read`; its
    operation is `Operation("fs_read", path, source_tool)`. A non-`str` path
    is `secret.read` (`classify_read`'s fail-closed branch).
    """
    try:
        hit = paths.classify_read(path, secret_files, source_tool=source_tool)
    except Exception:
        target = path if isinstance(path, str) else ""
        return Classification("secret.read", Operation("fs_read", target, source_tool), "")
    return hit if hit.rule == "secret.read" else None
