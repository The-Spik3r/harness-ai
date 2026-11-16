"""The path classifier: normalization, workspace containment, protected paths (PRD-016 Sections 6.3, 6.5, F4).

`classify_write(path, protected, workspace_roots)` returns exactly one of
`fs.write_protected`, `fs.write_in_workspace` or `fs.write_outside_workspace`;
`classify_read(path, secret_files)` returns `secret.read` or `fs.read` (F4,
STORY-013). Both take the policy's data as plain arguments, the way
`classify_shell` takes `shell_allow` (STORY-011 plan, decision 1), and each
returns one `Classification`, as F5's `classify_url` does: a path has one
outcome. STORY-014 wraps it in a tuple.

Normalization (Section 6.5 item 1, `normalize_path`), lexical only:

- `\\` becomes `/`; a drive letter is lowercased (`C:\\Repo\\x` ->
  `c:/Repo/x`) and nothing else changes case.
- The anchor: `""` (relative), `/` (POSIX absolute), `//` (UNC: exactly two
  leading separators are kept, three or more collapse to `/`), `c:/` (drive
  absolute) or `c:` (drive relative, `C:x`).
- Repeated `/` collapse, `.` segments drop, `..` pops a segment. On an
  absolute anchor `..` clamps at the anchor (`/../etc` -> `/etc`); on a
  relative path a `..` with nothing to pop is kept, and the path *escapes*.
- A first segment starting with `~` (`~`, `~user`) stays literal, the home
  directory the harness cannot see. A `..` never pops it: `~/../x` is
  `~/x`, still under `~`, so it cannot become the in-workspace `x`.

Protection comes **before** containment (Section 6.5 item 5): `.env` inside
a root is still `fs.write_protected`. Each compiled glob is `.search()`ed on
three candidates, and any match protects. Every candidate can only add a
non-grantable denial (T6):

1. the normalized text (`config/../.env` -> `.env`, `.ENV.local` through the
   globs' IGNORECASE, an absolute path at any depth);
2. the Windows-folded text: each segment cut at its first `:` (an NTFS
   stream, `x.pem::$DATA`) and stripped of trailing `.` and space, which
   Win32 drops when it opens the file (`x.pem.` is `x.pem`, `.git./config`
   is `.git/config`); a segment that folds to empty is dropped;
3. the text plus `/\\x00`: the directory itself, so a write targeting `.git`
   or `.github/workflows` matches `.git/**`. `\\x00` cannot be in a real
   target (the adapters refuse NUL), and no glob matches it alone.

The globs arrive compiled from `action_config` (`Globs.compiled`, STORY-006
plan decision 6: `(?:^|/)<body>$`, IGNORECASE, for `.search()` on a
normalized `/`-separated path). This module never translates a glob.

Containment (Section 6.5 items 2-4, D11), only when nothing is protected:

- a relative path that does not escape is inside (the agent runs in the
  repository); one that escapes is outside;
- a path with a segment of only dots and spaces (`...`, `. .`, `.. `) is
  outside, relative or under a root: Win32 reads it as a name that can
  traverse (STORY-018);
- a `~` path is outside (no root contains `~`), and so is a drive-relative
  `c:x`, whose meaning depends on a per-drive directory nobody here sees;
- an absolute path is inside only when, for some root normalized the same
  way, the anchors are equal and the root's segments are a prefix of the
  path's. Segments, not strings: `/home/dev/projects2/x` is not under
  `/home/dev/projects`. UNC `//srv/share/x` is not under `/srv/share`, and
  `\\\\?\\C:\\x` (anchor `//`) is not under `C:/`. A root of `/` contains
  every POSIX absolute path: the operator's choice. A root that is not a
  `str` or does not normalize to an absolute path is skipped (the loader
  already refuses one, `action_config._check_workspace_root`).

The case policy: protection is case-insensitive (the globs, T6);
containment is exact except the drive letter. Folding there would let
`/HOME/dev/projects/x` count as inside on a case-sensitive disk; being exact
can only deny a Windows path written in another case than its root, which is
the grantable `fs.write_outside_workspace`, so it fails closed.

**Symlinks are not resolved** (PRD-016 Risk 4), and neither is anything else
that needs the client's disk: hard links, 8.3 short names (`GITHUB~1`), a
mount point under a root, the agent's working directory (Section 6.5's
opening sentence). STORY-018 and STORY-020 list these. A Win32 traversal
oddity, a segment of only dots and spaces (`a/.../b`, `. ./x`, `.. /x`), is
not one of them: it is outside the workspace (STORY-018).

Secret reads (STORY-013, F4). A read is `secret.read` when a compiled
`secrets.files` glob matches one of the same three candidates protection
uses (so a directory target `.ssh` matches `.ssh/**`, and `~/.aws/credentials`
matches `.aws/**`), or when the path is `/proc/<pid>/environ`: a fixed rule,
the whole environment of a process (PRD F6 "the whole environment: always
`secret.read`"), not configurable. A read that cannot be classified (a
non-`str`, any internal `Exception`) is `secret.read` with detail `""`, the
strictest read outcome, as the write side's is `fs.write_protected`
(STORY-013 plan, decision D-M). The shell classifier (STORY-013) routes its
output-redirect targets through `classify_write` and its `<` targets and
reader-head arguments through `classify_read`; `secrets.classify_secret_read`
wraps `classify_read` (the import runs `secrets -> paths`, never back).

Every classification's `operation` is `Operation("fs_write" | "fs_read",
path, source_tool)` with the **whole input** as the target. The `detail` is
taken from the call's normalized path, never from a root or a glob (T11):
the protected match without its leading `/` (`.env.local`), otherwise the
normalized text, at most 32 characters, keeping the **end**, since the tail
of a path is what names it.

Never raises: a non-`str` path, a bad glob or root entry and any internal
`Exception` fail closed (a write becomes `fs.write_protected`, a read
`secret.read`: the strictest outcomes, as there is no `fs.unparsed`).
`BaseException` is not caught.

Pure (PRD-016 Section 6.12): no settings, no I/O, no filesystem; roots and
globs are arguments.
"""

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from app.services.action_classifiers import Classification, Operation

_DETAIL_MAX = 32
# A drive letter at the start of the slashed text: `C:/x` (absolute) or `C:x`.
_DRIVE = re.compile(r"([A-Za-z]):(/?)(.*)", re.DOTALL)
# Candidate 3 above: the path as a directory. NUL never occurs in a target.
_DIR_PROBE = "/\x00"
# A process's environment (D-J): `/proc/self/environ`, `/proc/1234/environ`.
_PROC_ENVIRON = re.compile(r"/proc/[^/]+/environ")


@dataclass(frozen=True)
class NormalizedPath:
    """A path after Section 6.5 item 1's lexical rewrite (see the module docstring).

    | anchor | meaning                | example in -> text        |
    |--------|------------------------|---------------------------|
    | `""`   | relative               | `src\\a.ts` -> `src/a.ts`  |
    | `/`    | POSIX absolute         | `/../etc` -> `/etc`        |
    | `//`   | UNC                    | `\\\\srv\\s\\x` -> `//srv/s/x` |
    | `c:/`  | drive absolute         | `C:\\Repo\\x` -> `c:/Repo/x` |
    | `c:`   | drive relative         | `C:x` -> `c:x`             |

    `parts` holds no `""` or `.`; a `..` appears only at the front of a
    non-absolute path (it escapes).
    """

    anchor: str
    parts: tuple[str, ...]

    @property
    def text(self) -> str:
        if not self.anchor and not self.parts:
            return "."
        return self.anchor + "/".join(self.parts)

    @property
    def is_absolute(self) -> bool:
        return self.anchor in ("/", "//") or self.anchor.endswith(":/")

    @property
    def escapes(self) -> bool:
        return not self.is_absolute and bool(self.parts) and self.parts[0] == ".."

    @property
    def home(self) -> bool:
        return self.anchor == "" and bool(self.parts) and self.parts[0].startswith("~")

    def __str__(self) -> str:
        return self.text


def normalize_path(path: str) -> NormalizedPath:
    """Rewrite `path` lexically (PRD-016 Section 6.5 item 1). Touches no filesystem.

    A non-`str` becomes the empty relative path; its only callers are the
    classifiers below, which handle a non-`str` themselves first.
    """
    if not isinstance(path, str):
        return NormalizedPath("", ())
    slashed = path.replace("\\", "/")
    drive = _DRIVE.match(slashed)
    if drive is not None:
        anchor = drive.group(1).lower() + ":" + drive.group(2)
        rest = drive.group(3)
    elif slashed.startswith("//") and not slashed.startswith("///"):
        anchor, rest = "//", slashed[2:]
    elif slashed.startswith("/"):
        anchor, rest = "/", slashed
    else:
        anchor, rest = "", slashed
    absolute = anchor in ("/", "//") or anchor.endswith(":/")
    parts: list[str] = []
    for segment in rest.split("/"):
        if segment in ("", "."):
            continue
        if segment != "..":
            parts.append(segment)
        elif parts and parts[-1] != "..":
            # `~` is not popped: `~/..` stays under the home it names.
            if not (anchor == "" and len(parts) == 1 and parts[0].startswith("~")):
                parts.pop()
        elif not absolute:
            parts.append("..")
        # else: `..` at an absolute anchor clamps, as POSIX does.
    return NormalizedPath(anchor, tuple(parts))


def _cap_tail(text: str) -> str:
    return text[-_DETAIL_MAX:]


def _windows_fold(parts: tuple[str, ...]) -> tuple[str, ...]:
    """Each segment as Win32 opens it: cut at an NTFS stream `:`, trailing `.`/space stripped."""
    folded = (part.split(":", 1)[0].rstrip(". ") for part in parts)
    return tuple(part for part in folded if part)


def _protected_match(p: NormalizedPath, protected: Iterable) -> Optional[str]:
    """The detail of the first protected glob that matches a candidate (module docstring), else None."""
    candidates = (p.text, p.anchor + "/".join(_windows_fold(p.parts)), p.text + _DIR_PROBE)
    for pattern in protected or ():
        if not hasattr(pattern, "search"):
            continue
        for candidate in candidates:
            match = pattern.search(candidate)
            if match is not None:
                detail = match.group(0).replace(_DIR_PROBE, "").lstrip("/")
                return _cap_tail(detail or p.text)
    return None


def _contained(p: NormalizedPath, workspace_roots: Iterable) -> bool:
    """Section 6.5 items 2-4 (module docstring): segment-wise, exact except the drive letter."""
    # PRD-016 STORY-018: Win32 opens `...`, `. .` and `.. ` as names that can traverse, which
    # the lexical rewrite cannot follow. A segment of only dots and spaces is outside.
    if any(part.strip(". ") == "" for part in p.parts):
        return False
    if not p.is_absolute:
        return p.anchor == "" and not p.escapes and not p.home
    for root in workspace_roots or ():
        if not isinstance(root, str):
            continue
        r = normalize_path(root)
        if r.is_absolute and r.anchor == p.anchor and p.parts[: len(r.parts)] == r.parts:
            return True
    return False


def classify_write(path: str, protected, workspace_roots=(), *, source_tool: str = "") -> Classification:
    """Classify a write of `path` (PRD-016 F4, Section 6.5). Never raises.

    `protected` is the compiled protected-path globs
    (`policy.protected_paths.compiled`) and is required: a default would
    silently protect nothing. `workspace_roots` is `policy.workspace_roots`;
    the default `()` is the built-in value, with which every absolute path is
    outside. STORY-014 calls `classify_write(op.target,
    policy.protected_paths.compiled, policy.workspace_roots,
    source_tool=op.source_tool)`; STORY-013 the same for each shell output
    redirect target. A non-`str` path or any exception is
    `fs.write_protected` with detail `""`.
    """
    op = Operation(kind="fs_write", target=path if isinstance(path, str) else "", source_tool=source_tool)
    try:
        if not isinstance(path, str):
            return Classification("fs.write_protected", op, "")
        p = normalize_path(path)
        detail = _protected_match(p, protected)
        if detail is not None:
            return Classification("fs.write_protected", op, detail)
        if _contained(p, workspace_roots):
            return Classification("fs.write_in_workspace", op, _cap_tail(p.text))
        return Classification("fs.write_outside_workspace", op, _cap_tail(p.text))
    except Exception:
        return Classification("fs.write_protected", op, "")


def _secret_read(p: NormalizedPath, secret_files, op: Operation) -> Optional[Classification]:
    """`secret.read` for a process environment or a `secrets.files` match (F4, F6; STORY-013), else None.

    The glob match is `_protected_match`'s, inline here rather than in
    `secrets.py`, so the import runs `secrets -> paths` only (STORY-013 plan,
    decision D-D).
    """
    if p.anchor == "/" and _PROC_ENVIRON.fullmatch(p.text):
        return Classification("secret.read", op, _cap_tail(p.text))
    detail = _protected_match(p, secret_files)
    if detail is not None:
        return Classification("secret.read", op, detail)
    return None


def classify_read(path: str, secret_files=(), *, source_tool: str = "") -> Classification:
    """Classify a read of `path` (PRD-016 F4). Never raises.

    `secret_files` is `policy.secrets.files.compiled`. `secret.read` when a
    glob matches (the three candidates of the module docstring) or the path
    is `/proc/<pid>/environ`; otherwise `fs.read`. The default `()` matches
    no glob, so a caller must pass the policy's: STORY-014 calls
    `classify_read(op.target, policy.secrets.files.compiled,
    source_tool=op.source_tool)`, and STORY-013's shell embedding the same
    for each reader-head argument and `<` target. A non-`str` path or any
    exception is `secret.read` with detail `""` (decision D-M).
    """
    op = Operation(kind="fs_read", target=path if isinstance(path, str) else "", source_tool=source_tool)
    try:
        if not isinstance(path, str):
            return Classification("secret.read", op, "")
        p = normalize_path(path)
        hit = _secret_read(p, secret_files, op)
        if hit is not None:
            return hit
        return Classification("fs.read", op, _cap_tail(p.text))
    except Exception:
        # Unreachable for a `str` input. A read nobody can classify might be
        # of a secret: the strictest read outcome (STORY-013, decision D-M).
        return Classification("secret.read", op, "")
