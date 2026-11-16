"""The tool-call adapter layer: a tool call in, the operations it performs out (PRD-016 Sections 4, 6.2, F1).

`map_tool_call` reads one OpenAI `tool_calls[i]` (a name and a JSON-string
`arguments`) and returns one of four `MappingResult`s: the `Operations` the call
performs, `Opaque` for a tool the policy allows without reading its arguments,
`Unknown` for a name no mapping covers, or `Malformed` when the arguments
cannot be read as the mapping says. `action_policy.evaluate()` (STORY-014)
turns `Unknown` into `tool.unknown`, `Malformed` into `tool.malformed` and
`Opaque` into `tool.opaque`; `Operations` go to the classifiers.

A `ToolMapping` is **data**, not code (PRD F1): a kind, a key-path expression
into the arguments, and four optional fields (`default`, `format`,
`extra_targets`, `optional_targets`). The expression syntax and the four value shapes exist because
the real tools do not fit "one key, one string": `tests/corpora/actions/SOURCES.md`
(STORY-001), section *Implications for STORY-004*, lists the shapes, and the
threat model's findings S1, S2, S4, S6, S7 and S8
(`.agents/spikes/PRD-016-action-policy-rules/threat-model.md`) are answered
in the helpers below. `BUILT_IN_TOOLS` is the mapping for OpenCode, Cline and
the generic SQL names; STORY-006 places it in the built-in policy unchanged.

Fail closed throughout: `map_tool_call` never returns zero operations, and
every ambiguity -- an absent key, an empty array, a patch with no header, two
spellings of one key in the same call, a line break in a path -- is
`Malformed`, which denies. It never raises for any input a model can produce
(PRD F7).

`Operation` and `OperationKind` are imported from `action_classifiers` and
re-exported, not redefined (STORY-003 decision: the import graph is one-way,
`action_adapters -> action_classifiers`). `ToolCall` is defined here.

Pure on purpose (PRD-016 Section 6.12): no I/O, no settings, no pydantic,
nothing read at import, and the only `app` import is `action_classifiers`. The
argument cap and the policy's `tools` / `opaque_tools` arrive as parameters
from `action_config` (STORY-006/007) via `action_policy` (STORY-014).
"""

import json
import re
import shlex
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Literal, Mapping, Optional, Union, get_args

from app.services.action_classifiers import (
    OPERATION_KINDS,
    Decision,
    Operation,
    OperationKind,
)

__all__ = [
    "BUILT_IN_TOOLS",
    "Malformed",
    "MappingResult",
    "Opaque",
    "Operation",
    "OperationKind",
    "Operations",
    "TARGET_FORMATS",
    "TargetFormat",
    "ToolCall",
    "ToolMapping",
    "ToolMappingError",
    "Unknown",
    "map_tool_call",
]

#: How the value at a target path is read (STORY-004):
#: `text` -- a string, the target as is;
#: `command` -- a shell line, or a `{command, args[]}` argv object joined with
#: `shlex.join` so the POSIX classifier recovers exactly that argv (S4);
#: `patch` -- patch text whose `*** Add/Update/Delete File:` and `*** Move to:`
#: headers each name one target (S1).
TargetFormat = Literal["text", "command", "patch"]
TARGET_FORMATS: tuple[str, ...] = get_args(TargetFormat)


@dataclass(frozen=True)
class ToolCall:
    """One tool call as the model emitted it (PRD-016 Section 6.2)."""

    id: str
    name: str
    #: The raw JSON string, exactly as the model emitted it.
    arguments: str


class ToolMappingError(ValueError):
    """Raised by `ToolMapping(...)` for a bad kind, format, target expression
    or default.

    The message names the field and the value, and the closed vocabulary where
    there is one. It deliberately does not name a file or a tool: this module
    is pure and cannot know where the mapping came from. `action_config`
    (STORY-006/007) catches this and re-raises `ActionConfigError` with the
    file and the `tools.<name>` node attached -- the `PatternCompileError`
    seam of `pattern_detector`."""


# --- The target expression --------------------------------------------------
#
#   expr := path ("|" path)*          alternatives: spellings of one target
#   path := seg ("." seg)*
#   seg  := key | key "[]"            `[]`: every element of an array
#   key  := [A-Za-z_][A-Za-z0-9_-]*
#
# `files[].path|files[].filePath` reads `path` or `filePath` of every element
# of `files`, choosing per element. Alternatives are resolved together, level
# by level, so two spellings present at the same level is an ambiguity
# (`Malformed`), never a silent choice. The same key may appear as an array
# and as a scalar (`commands[]|commands`): the value's type picks one.
# Optionality is spelled `default=`, not `?`, so there is one way to say it.

_SEGMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)(\[\])?")

#: (key, is_array) per segment.
_Segment = tuple[str, bool]
_Path = tuple[_Segment, ...]


def _parse_target(expr: str) -> tuple[_Path, ...]:
    """Parse a target expression into its alternatives, or raise ToolMappingError."""
    if not isinstance(expr, str) or not expr:
        raise ToolMappingError(f"target expression must be a non-empty string, got {expr!r}")
    return _parse_target_cached(expr)


@lru_cache(maxsize=None)
def _parse_target_cached(expr: str) -> tuple[_Path, ...]:
    """Cached, so `ToolMapping.__post_init__` and `map_tool_call` share one
    parse per expression without the frozen dataclass carrying a derived field.
    Only reached with a non-empty `str` (hashable)."""
    alternatives: list[_Path] = []
    for alternative in expr.split("|"):
        if not alternative:
            raise ToolMappingError(f"target expression {expr!r} has an empty alternative")
        segments: list[_Segment] = []
        for segment in alternative.split("."):
            match = _SEGMENT.fullmatch(segment)
            if match is None:
                raise ToolMappingError(
                    f"target expression {expr!r} has an invalid segment {segment!r} "
                    "(expected a key [A-Za-z_][A-Za-z0-9_-]*, optionally followed by [])"
                )
            segments.append((match.group(1), match.group(2) is not None))
        alternatives.append(tuple(segments))
    _check_alternatives(expr, alternatives)
    return tuple(alternatives)


def _check_alternatives(expr: str, rests: list[_Path]) -> None:
    """Refuse alternatives that overlap: a duplicate (`a|a`), or one key read
    both as a value and as an object (`a|a.b`, `files[]|files[].path`).

    Either would make "which spelling is present" undecidable at resolution
    time, and an undecidable mapping is a startup error rather than a
    per-call guess.
    """
    if any(not rest for rest in rests):
        if len(rests) > 1:
            raise ToolMappingError(
                f"target expression {expr!r} has overlapping alternatives "
                "(the same key path read twice, or read both as a value and as an object)"
            )
        return
    groups: dict[tuple[str, bool], list[_Path]] = {}
    for rest in rests:
        groups.setdefault(rest[0], []).append(rest[1:])
    for group in groups.values():
        _check_alternatives(expr, group)


# --- The mapping ------------------------------------------------------------


@dataclass(frozen=True)
class ToolMapping:
    """How one tool's arguments become operations (PRD-016 F1; STORY-004).

    Every field is validated at construction, so a `BUILT_IN_TOOLS` entry or
    a policy file's `tools.<name>` that cannot be resolved fails at startup,
    not on the first call.
    """

    kind: OperationKind
    #: Key-path expression into the arguments (see the grammar above).
    target: str
    #: The target when no spelling of `target` is present at the top level
    #: (OpenCode `glob.path?` -> "."). None means the target is required.
    default: Optional[str] = None
    #: How the value at the path is read: text | command | patch.
    format: TargetFormat = "text"
    #: Further expressions in the same call, each required and read as `text`,
    #: each yielding operations of the same kind (OpenCode `glob.pattern`, S7).
    extra_targets: tuple[str, ...] = ()
    #: Further expressions read as `text` when present and skipped when
    #: absent, each yielding operations of the same kind (OpenCode
    #: `grep.include`, Cline 3.x `search_files.file_pattern`; PRD-016 D15,
    #: STORY-013). A present `null` or non-string is Malformed, like every
    #: target; a present empty or blank string counts as absent (an empty
    #: filter searches the whole directory, the target already read).
    optional_targets: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in OPERATION_KINDS:
            raise ToolMappingError(
                f"unknown operation kind {self.kind!r} "
                f"(expected one of: {', '.join(OPERATION_KINDS)})"
            )
        if self.format not in TARGET_FORMATS:
            raise ToolMappingError(
                f"unknown target format {self.format!r} "
                f"(expected one of: {', '.join(TARGET_FORMATS)})"
            )
        alternatives = _parse_target(self.target)
        if not isinstance(self.extra_targets, tuple):
            raise ToolMappingError(
                f"extra_targets must be a tuple of target expressions, got {self.extra_targets!r}"
            )
        for extra in self.extra_targets:
            _parse_target(extra)
        if not isinstance(self.optional_targets, tuple):
            raise ToolMappingError(
                f"optional_targets must be a tuple of target expressions, got {self.optional_targets!r}"
            )
        for optional in self.optional_targets:
            _parse_target(optional)
        if self.default is not None:
            if not isinstance(self.default, str) or not self.default.strip():
                raise ToolMappingError(f"default must be a non-empty string, got {self.default!r}")
            if self.format != "text":
                raise ToolMappingError(
                    f"default is only allowed with format 'text', not {self.format!r}"
                )
            if any(is_array for alt in alternatives for _, is_array in alt):
                raise ToolMappingError(
                    f"default is not allowed on an array target {self.target!r} "
                    "(an absent array has no sensible single value)"
                )


# --- The four results -------------------------------------------------------


@dataclass(frozen=True)
class Operations:
    """The operations a call performs, in argument order. Never empty."""

    operations: tuple[Operation, ...]


@dataclass(frozen=True)
class Opaque:
    """A tool named in `opaque_tools`: its arguments are not read (PRD 6.4)."""

    decision: Decision


@dataclass(frozen=True)
class Unknown:
    """A tool name in neither `tools` nor `opaque_tools` (`tool.unknown`)."""


@dataclass(frozen=True)
class Malformed:
    """Arguments that cannot be read as the mapping says (`tool.malformed`)."""

    #: A fixed phrase naming the problem and at most a key path from the
    #: mapping, never an argument value (PRD-016 T11: it may reach the agent).
    detail: str


MappingResult = Union[Operations, Opaque, Unknown, Malformed]


# --- Resolution -------------------------------------------------------------


class _MalformedArguments(Exception):
    """Internal: raised anywhere below, caught only at the map_tool_call boundary."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def _reject_duplicate_keys(pairs: list) -> dict:
    """`object_pairs_hook` that refuses a repeated key at any nesting level.

    `{"command": "ls", "command": "rm -rf /"}` is valid JSON; Python keeps the
    last value, another parser may keep the first. Classifying one while the
    executor runs the other is an evasion, so the call is `Malformed`.
    """
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise _MalformedArguments("arguments has a duplicate key")
        result[key] = value
    return result


#: Patch headers that name a file, in OpenCode's and Cline's shared grammar
#: (SOURCES.md, OpenCode notes and Cline 4.x `apply-patch-parser.ts`). A
#: `Delete File` is a write too; `Move to` is the second path of an update.
_PATCH_HEADERS = ("*** Add File:", "*** Update File:", "*** Delete File:", "*** Move to:")


def _patch_paths(text: str) -> list[str]:
    """Every path a patch's headers name, in order (S1).

    `Begin Patch` / `End Patch` markers are not required, and a header-shaped
    context line is counted: over-matching adds an `fs_write`, which can only
    add a deny, never an allow. A patch with no header would otherwise be zero
    operations, i.e. `allow`, so it is `Malformed`.
    """
    paths: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        for header in _PATCH_HEADERS:
            if stripped.startswith(header):
                path = stripped[len(header):].strip()
                if not path:
                    raise _MalformedArguments("patch header names no path")
                paths.append(path)
                break
    if not paths:
        raise _MalformedArguments("patch text names no file")
    return paths


def _read_leaf(value: object, path: str, fmt: str) -> list[str]:
    """Read the value at a resolved path under the mapping's format."""
    if fmt == "patch":
        if not isinstance(value, str):
            raise _MalformedArguments(f"target '{path}' is not a string")
        return _patch_paths(value)
    if fmt == "command":
        if isinstance(value, str):
            return [value]
        # S4: `{command, args[]}` is argv run with no shell. `shlex.join`
        # quotes each element, so the shell classifier tokenizes the line back
        # to exactly this argv -- `;` or `$(x)` inside an argument stays an
        # argument. Other keys of the object are not targets and are ignored.
        if isinstance(value, dict):
            command = value.get("command")
            args = value.get("args", [])
            if (
                isinstance(command, str)
                and isinstance(args, list)
                and all(isinstance(arg, str) for arg in args)
            ):
                return [shlex.join([command, *args])]
        raise _MalformedArguments(
            f"target '{path}' is neither a command string nor a {{command, args}} object"
        )
    if not isinstance(value, str):
        raise _MalformedArguments(f"target '{path}' is not a string")
    return [value]


def _resolve_object(
    obj: dict, rests: list[_Path], prefix: str, fmt: str
) -> Optional[list[str]]:
    """Resolve alternatives (all non-empty) against one JSON object.

    Returns None when no alternative's key is present here; the caller decides
    whether that is a default or `Malformed`. A key present with `null` counts
    as present (and then fails as "not a string").
    """
    groups: dict[str, list[tuple[bool, _Path]]] = {}
    for rest in rests:
        (key, is_array), tail = rest[0], rest[1:]
        groups.setdefault(key, []).append((is_array, tail))
    present = [key for key in groups if key in obj]
    if len(present) > 1:
        # Which spelling the executor prefers when it gets two is not
        # documented, so neither choice is safe (S2, orchestrator decision).
        names = " and ".join(f"'{prefix}{key}'" for key in present)
        raise _MalformedArguments(f"more than one spelling of the target is present: {names}")
    if not present:
        return None
    key = present[0]
    value = obj[key]
    array_tails = [tail for is_array, tail in groups[key] if is_array]
    scalar_tails = [tail for is_array, tail in groups[key] if not is_array]
    if isinstance(value, list) and array_tails:
        if not value:
            # Zero operations would mean `allow` (the S1 rule, generalised).
            raise _MalformedArguments(f"'{prefix}{key}' is empty")
        targets: list[str] = []
        for element in value:
            targets.extend(_resolve_value(element, array_tails, f"{prefix}{key}[]", fmt))
        return targets
    if scalar_tails:
        return _resolve_value(value, scalar_tails, f"{prefix}{key}", fmt)
    raise _MalformedArguments(f"'{prefix}{key}' is not an array")


def _resolve_value(value: object, tails: list[_Path], path: str, fmt: str) -> list[str]:
    """Resolve the remaining segments below one value (a leaf or an object)."""
    if tails == [()]:
        return _read_leaf(value, path, fmt)
    # `_check_alternatives` guarantees a leaf never shares a level with a
    # deeper path, so here every tail is non-empty.
    if not isinstance(value, dict):
        raise _MalformedArguments(f"'{path}' is not an object")
    targets = _resolve_object(value, tails, f"{path}.", fmt)
    if targets is None:
        raise _MalformedArguments(f"missing target key under '{path}'")
    return targets


def _resolve_expression(
    arguments: dict, expr: str, fmt: str, default: Optional[str]
) -> list[str]:
    targets = _resolve_object(arguments, list(_parse_target(expr)), "", fmt)
    if targets is None:
        if default is None:
            raise _MalformedArguments(f"missing target key '{expr}'")
        targets = [default]
    return targets


#: Kinds whose target is a path or a URL: no real one contains a line break or
#: NUL. Refusing them closes the hole where patch text mapped without
#: `format: patch` would reach the path classifier as one relative "path".
#: `shell` and `sql` keep their newlines, which separate commands/statements.
_SINGLE_LINE_KINDS = frozenset({"fs_write", "fs_read", "http"})
_LINE_BREAKS = ("\n", "\r", "\x00")


def _check_target(kind: str, target: str, expr: str) -> None:
    if not target.strip():
        raise _MalformedArguments(f"target '{expr}' is empty")
    if kind in _SINGLE_LINE_KINDS and any(ch in target for ch in _LINE_BREAKS):
        raise _MalformedArguments(f"target '{expr}' contains a line break")


def map_tool_call(
    call: ToolCall,
    tools: Mapping[str, ToolMapping],
    opaque_tools: Mapping[str, Decision],
    max_argument_characters: int,
) -> MappingResult:
    """Map one tool call to what it does (PRD-016 Sections 4, 6.2, F1).

    Order matters: the tool name is matched exactly and case-sensitively
    (S6; prefixed MCP names are `Unknown` unless a deployment maps them), and
    `tools` is checked before `opaque_tools`, so a name in both is classified
    rather than waved through. An opaque tool's arguments are not read at all
    (PRD 6.4), so the cap and the parse apply only to mapped tools. The cap is
    checked before `json.loads`, so an oversized payload is never parsed.
    """
    if not isinstance(call.name, str):
        return Malformed("tool name is not a string")
    mapping = tools.get(call.name)
    if mapping is None:
        if call.name in opaque_tools:
            return Opaque(opaque_tools[call.name])
        return Unknown()
    if not isinstance(call.arguments, str):
        return Malformed("arguments is not a string")
    if len(call.arguments) > max_argument_characters:
        # The configured limit is not a secret, and it names the setting to raise.
        return Malformed(f"arguments exceed {max_argument_characters} characters")
    try:
        try:
            arguments = json.loads(call.arguments, object_pairs_hook=_reject_duplicate_keys)
        except (ValueError, RecursionError):
            # `"[" * 100000` raises RecursionError, not ValueError; a 5000-digit
            # int raises ValueError (the int-digit limit). Both are model input.
            return Malformed("arguments is not valid JSON")
        if not isinstance(arguments, dict):
            return Malformed("arguments is not a JSON object")
        targets: list[tuple[str, str]] = []
        expressions = [(mapping.target, mapping.format, mapping.default)]
        expressions += [(extra, "text", None) for extra in mapping.extra_targets]
        for expr, fmt, default in expressions:
            for target in _resolve_expression(arguments, expr, fmt, default):
                _check_target(mapping.kind, target, expr)
                targets.append((expr, target))
        # D15 (STORY-013): present -> read; absent, empty or blank -> skipped.
        for expr in mapping.optional_targets:
            found = _resolve_object(arguments, list(_parse_target(expr)), "", "text")
            for target in found or ():
                if not target.strip():
                    continue
                _check_target(mapping.kind, target, expr)
                targets.append((expr, target))
    except _MalformedArguments as exc:
        return Malformed(exc.detail)
    if not targets:
        return Malformed("no target")  # unreachable by construction; asserted anyway
    return Operations(
        tuple(
            Operation(kind=mapping.kind, target=target, source_tool=call.name)
            for _, target in targets
        )
    )


# --- The built-in mappings --------------------------------------------------
#
# One entry per non-`none` row of `tests/corpora/actions/SOURCES.md`; the test
# parses those tables and fails on any drift. Names are exact: a client that
# renames a tool gets `tool.unknown`, a renamed key `tool.malformed` (PRD Risk 5).

BUILT_IN_TOOLS: Mapping[str, ToolMapping] = MappingProxyType(
    {
        # --- OpenCode v1.19.5 (`810c0eba`) -------------------------------------
        "bash": ToolMapping("shell", "command"),
        "write": ToolMapping("fs_write", "filePath"),
        "edit": ToolMapping("fs_write", "filePath"),
        # Shared name: OpenCode sends `patchText`, Cline 4.x and 3.x send
        # `input`. One fs_write per header (S1); both keys present is Malformed.
        "apply_patch": ToolMapping("fs_write", "patchText|input", format="patch"),
        "read": ToolMapping("fs_read", "filePath"),
        "webfetch": ToolMapping("http", "url"),
        # `path?` defaults to the working directory (S8), and `pattern` is
        # itself a path glob that can name `../` or `.env*`, so it is a second
        # fs_read (S7), matched literally against the secret globs (D15).
        "glob": ToolMapping("fs_read", "path", default=".", extra_targets=("pattern",)),
        # `include?` is a filename glob (`.env*`): an optional second fs_read,
        # so a secret-naming filter is `secret.read` (PRD-016 D15, STORY-013).
        # A search over a plain directory that returns a secret's contents
        # stays `fs.read`: the stated D15 limitation (S9).
        "grep": ToolMapping("fs_read", "path", default=".", optional_targets=("include",)),
        "lsp": ToolMapping("fs_read", "filePath"),
        # --- Cline 4.x v4.1.26 (`a459f1d0`) ------------------------------------
        # The advertised key plus the documented lenient-union aliases the
        # grammar can express (SOURCES.md, Cline 4.x notes; orchestrator
        # decision): `commands` as one entry, and `cmd`. Elements are a shell
        # line or `{command, args[]}` argv (S4). Not read, so Malformed: the
        # top-level `{command, args?}` / `{command}` (the arguments object
        # itself is the argv; reading `command` alone would drop `args`) and a
        # bare string or array (not a JSON object). Two spellings is Malformed.
        "run_commands": ToolMapping("shell", "commands[]|commands|cmd", format="command"),
        # `files[]` of objects (per-entry `path`, `file_path` or `filePath`),
        # `files` as one object, and `file_paths` / `paths` as an array or a
        # string. Not expressible, so Malformed: `files[]` of strings and
        # `files` as a string (the grammar cannot read one key both as a value
        # and as an object), `paths` as an object, a bare string.
        "read_files": ToolMapping(
            "fs_read",
            "files[].path|files[].file_path|files[].filePath"
            "|files.path|files.file_path|files.filePath"
            "|file_paths[]|file_paths|paths[]|paths",
        ),
        # Creates the file when missing, so always a write.
        "editor": ToolMapping("fs_write", "path"),
        "fetch_web_content": ToolMapping("http", "requests[].url"),
        # --- Cline 3.x v3.89.2 (`e1bdeeff`, legacy) ----------------------------
        "execute_command": ToolMapping("shell", "command"),
        # Native GPT-5 / next-gen variants send `absolutePath`, the GENERIC
        # spec (also native for gemini3 and xs) sends `path`.
        "write_to_file": ToolMapping("fs_write", "absolutePath|path"),
        "replace_in_file": ToolMapping("fs_write", "absolutePath|path"),
        "read_file": ToolMapping("fs_read", "path"),
        "list_files": ToolMapping("fs_read", "path"),
        # `file_pattern?` is read like OpenCode `grep.include` (D15, STORY-013).
        "search_files": ToolMapping("fs_read", "path", optional_targets=("file_pattern",)),
        # `url?` is recorded optional, but only `launch` carries one and there
        # is no sensible default URL: a `click` / `scroll_*` without `url` is
        # Malformed (deny). Fail closed; Cline 3.x is legacy.
        "browser_action": ToolMapping("http", "url"),
        # --- Generic SQL names (MCP servers; SOURCES.md "Generic SQL tools") --
        # These arrive prefixed through both clients (`postgres_query`,
        # `supabase__execute_sql`; S6), so they match only an unprefixed caller
        # or a deployment's own `tools:`. The key differs per name.
        "query": ToolMapping("sql", "sql"),
        "execute_sql": ToolMapping("sql", "query"),
        # Not in the PRD's three names, but a SOURCES.md row and Supabase's
        # DDL-bearing tool: mapped, it reaches `sql.ddl` instead of tool.unknown.
        "apply_migration": ToolMapping("sql", "query"),
        "run_sql": ToolMapping("sql", "query"),
    }
)
# Data, not code (PRD F1): STORY-006 places this in the built-in policy as is,
# and `ToolMapping.__post_init__` has already validated every entry at import.
