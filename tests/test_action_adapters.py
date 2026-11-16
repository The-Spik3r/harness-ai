"""The tool-call adapter layer (PRD-016 Sections 4, 6.2, 6.12, F1; STORY-004).

`tests/corpora/actions/SOURCES.md` (STORY-001) is read on purpose: its own
header says "STORY-004's parametrized test reads the per-client tables", so a
row added to the survey fails here until `BUILT_IN_TOOLS` and `_REALISTIC`
cover it. It is a test corpus file, not the PRD. The realistic argument
objects and every expected target are hardcoded below.
"""

import dataclasses
import inspect
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

import app.services.action_adapters as action_adapters
import app.services.action_classifiers as action_classifiers
from app.services.action_adapters import (
    BUILT_IN_TOOLS,
    TARGET_FORMATS,
    Malformed,
    Opaque,
    Operation,
    Operations,
    ToolCall,
    ToolMapping,
    ToolMappingError,
    Unknown,
    map_tool_call,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SOURCES = Path(__file__).resolve().parent / "corpora" / "actions" / "SOURCES.md"
_CAP = 100_000
_RESULT_TYPES = (Operations, Opaque, Unknown, Malformed)


def _map(name, arguments, tools=BUILT_IN_TOOLS, opaque=None, cap=_CAP):
    return map_tool_call(ToolCall(id="c1", name=name, arguments=arguments), tools, opaque or {}, cap)


def _args(obj):
    return json.dumps(obj)


def _targets(result):
    assert isinstance(result, Operations), result
    return tuple(op.target for op in result.operations)


# --- SOURCES.md ----------------------------------------------------------------


def _sources_rows():
    """(client, tool, kind, key, multi) for every row of the four per-client tables."""
    rows = []
    in_table = False
    for line in _SOURCES.read_text(encoding="utf-8").splitlines():
        if line.startswith("| Client | Tool | Operation kind | Target key |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            in_table = False
            continue
        if line.startswith("|---"):
            continue
        cells = [cell.strip().replace("`", "") for cell in line.strip().strip("|").split("|")]
        rows.append((cells[0], cells[1], cells[2], cells[3], cells[4]))
    return rows


_ROWS = _sources_rows()
_MAPPED_ROWS = [row for row in _ROWS if row[2] != "none"]


def _row_id(row):
    return f"{row[0]}-{row[1]}-{row[3]}"


def _row_key(key):
    return key.replace(" (in patch text)", "").rstrip("?")


def _alternatives(expr):
    return expr.split("|")


def test_sources_parser_reads_every_row():
    # 16 OpenCode + 13 OpenCode 2.x + 9 Cline 4.x + 12 Cline 3.x + 4 SQL; a broken parser fails here.
    # PRD-017 STORY-001: the OpenCode 2.0.10 rows were added (SOURCES.md "OpenCode 2.x"): 41 -> 54.
    assert len(_ROWS) == 54
    assert [row[0] for row in _ROWS].count("OpenCode") == 16
    assert [row[0] for row in _ROWS].count("OpenCode 2.x") == 13
    assert [row[0] for row in _ROWS].count("Cline 4.x") == 9
    assert [row[0] for row in _ROWS].count("Cline 3.x") == 12


# Shape 5: `url?` is recorded optional, but there is no sensible default URL, so
# `browser_action` keeps `url` required (a non-`launch` action is Malformed).
_OPTIONAL_KEPT_REQUIRED = {"browser_action"}


@pytest.mark.parametrize("row", _ROWS, ids=_row_id)
def test_every_sources_row_is_mapped_as_recorded(row):
    client, tool, kind, key, multi = row
    if kind == "none":
        assert tool not in BUILT_IN_TOOLS
        assert _map(tool, "{}") == Unknown()
        return
    mapping = BUILT_IN_TOOLS[tool]
    assert mapping.kind == kind
    assert _row_key(key) in _alternatives(mapping.target)
    if tool not in _OPTIONAL_KEPT_REQUIRED:
        assert key.endswith("?") == (mapping.default == ".")
    else:
        assert mapping.default is None
    assert ("(in patch text)" in key) == (mapping.format == "patch")
    is_multi = mapping.format == "patch" or any("[]" in alt for alt in _alternatives(mapping.target))
    assert (multi == "yes") == is_multi


def test_built_in_tools_are_exactly_the_sources_rows():
    assert set(BUILT_IN_TOOLS) == {row[1] for row in _MAPPED_ROWS}
    # PRD-017 STORY-001: 24 -> 26, OpenCode 2.0 added `shell` (was `bash`) and `patch` (was `apply_patch`).
    assert len(BUILT_IN_TOOLS) == 26


_PATCH = (
    "*** Begin Patch\n"
    "*** Add File: src/new.ts\n"
    "+export const x = 1;\n"
    "*** Update File: src/old.ts\n"
    "*** Move to: src/renamed.ts\n"
    "@@\n"
    "-a\n"
    "+b\n"
    "*** Delete File: src/gone.ts\n"
    "*** End Patch\n"
)
_PATCH_TARGETS = ("src/new.ts", "src/old.ts", "src/renamed.ts", "src/gone.ts")

#: (client, tool, key) -> (arguments object, expected targets). Sibling keys are
#: copied from each schema so the sample looks like what the client sends.
_REALISTIC = {
    ("OpenCode", "bash", "command"): (
        {"command": "ls -la", "description": "List files", "timeout": 1000},
        ("ls -la",),
    ),
    ("OpenCode", "write", "filePath"): (
        {"filePath": "/work/app/main.py", "content": "print(1)\n"},
        ("/work/app/main.py",),
    ),
    ("OpenCode", "edit", "filePath"): (
        {"filePath": "/work/app/main.py", "oldString": "1", "newString": "2"},
        ("/work/app/main.py",),
    ),
    ("OpenCode", "apply_patch", "patchText (in patch text)"): ({"patchText": _PATCH}, _PATCH_TARGETS),
    ("OpenCode", "read", "filePath"): ({"filePath": "/work/README.md", "offset": 0, "limit": 200}, ("/work/README.md",)),
    ("OpenCode", "webfetch", "url"): ({"url": "https://example.com/docs", "format": "markdown"}, ("https://example.com/docs",)),
    ("OpenCode", "glob", "path?"): ({"pattern": "**/*.ts", "path": "/work/src"}, ("/work/src", "**/*.ts")),
    # PRD-016 D15 (STORY-013): include/file_pattern is an optional second fs_read
    ("OpenCode", "grep", "path?"): ({"pattern": "TODO", "path": "/work/src", "include": "*.py"}, ("/work/src", "*.py")),
    ("OpenCode", "lsp", "filePath"): ({"operation": "hover", "filePath": "src/a.ts", "line": 1, "character": 2}, ("src/a.ts",)),
    # PRD-017 STORY-001: OpenCode 2.0.10 (SOURCES.md "OpenCode 2.x"); sibling keys copied from its schemas.
    ("OpenCode 2.x", "shell", "command"): ({"command": "npm test", "workdir": "/work", "timeout": 120000}, ("npm test",)),
    ("OpenCode 2.x", "read", "path"): ({"path": "/work/README.md", "offset": 1, "limit": 200}, ("/work/README.md",)),
    ("OpenCode 2.x", "write", "path"): ({"path": "/work/app/main.py", "content": "print(1)\n"}, ("/work/app/main.py",)),
    ("OpenCode 2.x", "edit", "path"): (
        {"path": "/work/app/main.py", "oldString": "1", "newString": "2", "replaceAll": False},
        ("/work/app/main.py",),
    ),
    ("OpenCode 2.x", "patch", "patchText (in patch text)"): ({"patchText": _PATCH}, _PATCH_TARGETS),
    ("OpenCode 2.x", "webfetch", "url"): ({"url": "https://example.com/docs", "format": "markdown"}, ("https://example.com/docs",)),
    ("OpenCode 2.x", "glob", "path?"): ({"pattern": "**/*.ts", "path": "src", "hidden": False}, ("src", "**/*.ts")),
    ("OpenCode 2.x", "grep", "path?"): ({"pattern": "TODO", "path": "src", "include": "*.py", "literal": True}, ("src", "*.py")),
    ("Cline 4.x", "run_commands", "commands[]"): (
        {"commands": ["npm test", {"command": "git", "args": ["commit", "-m", "fix: a; b"]}]},
        ("npm test", "git commit -m 'fix: a; b'"),
    ),
    ("Cline 4.x", "read_files", "files[].path"): (
        {"files": [{"path": "/work/a.py"}, {"path": "/work/b.py", "start_line": 1, "end_line": 9}]},
        ("/work/a.py", "/work/b.py"),
    ),
    ("Cline 4.x", "editor", "path"): (
        {"command": "str_replace", "path": "/work/a.py", "old_str": "1", "new_str": "2"},
        ("/work/a.py",),
    ),
    ("Cline 4.x", "apply_patch", "input (in patch text)"): ({"input": _PATCH}, _PATCH_TARGETS),
    ("Cline 4.x", "fetch_web_content", "requests[].url"): (
        {"requests": [{"url": "https://a.example", "prompt": "x"}, {"url": "https://b.example", "prompt": "y"}]},
        ("https://a.example", "https://b.example"),
    ),
    ("Cline 3.x", "execute_command", "command"): ({"command": "npm run build", "requires_approval": False}, ("npm run build",)),
    ("Cline 3.x", "write_to_file", "absolutePath"): ({"absolutePath": "/work/a.txt", "content": "x"}, ("/work/a.txt",)),
    ("Cline 3.x", "write_to_file", "path"): ({"path": "a.txt", "content": "x"}, ("a.txt",)),
    ("Cline 3.x", "replace_in_file", "absolutePath"): ({"absolutePath": "/work/a.txt", "diff": "<<<<<<< SEARCH"}, ("/work/a.txt",)),
    ("Cline 3.x", "replace_in_file", "path"): ({"path": "a.txt", "diff": "<<<<<<< SEARCH"}, ("a.txt",)),
    ("Cline 3.x", "read_file", "path"): ({"path": "src/a.py", "start_line": 1, "end_line": 50}, ("src/a.py",)),
    ("Cline 3.x", "list_files", "path"): ({"path": "src", "recursive": True}, ("src",)),
    # PRD-016 D15 (STORY-013): include/file_pattern is an optional second fs_read
    ("Cline 3.x", "search_files", "path"): ({"path": "src", "regex": "TODO", "file_pattern": "*.py"}, ("src", "*.py")),
    ("Cline 3.x", "browser_action", "url?"): ({"action": "launch", "url": "https://example.com"}, ("https://example.com",)),
    ("Cline 3.x", "apply_patch", "input (in patch text)"): ({"input": _PATCH}, _PATCH_TARGETS),
    ("MCP postgres (reference server, archived)", "query", "sql"): ({"sql": "SELECT 1"}, ("SELECT 1",)),
    ("MCP supabase", "execute_sql", "query"): ({"project_id": "p1", "query": "SELECT * FROM t"}, ("SELECT * FROM t",)),
    ("MCP supabase", "apply_migration", "query"): (
        {"project_id": "p1", "name": "add_t", "query": "CREATE TABLE t (id int)"},
        ("CREATE TABLE t (id int)",),
    ),
    ("MCP timeplus", "run_sql", "query"): ({"query": "SELECT count() FROM s"}, ("SELECT count() FROM s",)),
}


def test_every_mapped_sources_row_has_a_realistic_sample():
    assert {(row[0], row[1], row[3]) for row in _MAPPED_ROWS} == set(_REALISTIC)


@pytest.mark.parametrize("row", _MAPPED_ROWS, ids=_row_id)
def test_realistic_call_yields_documented_kind_and_targets(row):
    client, tool, kind, key, _ = row
    arguments, expected = _REALISTIC[(client, tool, key)]
    result = _map(tool, _args(arguments))
    assert result == Operations(tuple(Operation(kind, target, tool) for target in expected))


# --- AC1 -----------------------------------------------------------------------


def test_bash_ls_maps_to_one_shell_operation():
    result = map_tool_call(
        ToolCall(id="c1", name="bash", arguments='{"command": "ls"}'), BUILT_IN_TOOLS, {}, _CAP
    )
    assert result == Operations((Operation(kind="shell", target="ls", source_tool="bash"),))


# --- AC2 shapes ----------------------------------------------------------------


def test_apply_patch_names_one_fs_write_per_header():
    patch = "*** Begin Patch\r\n  *** Add File: a.py\r\n+x\r\n*** Delete File: b.py\r\n*** End Patch"
    result = _map("apply_patch", _args({"patchText": patch}))
    assert result == Operations(
        (Operation("fs_write", "a.py", "apply_patch"), Operation("fs_write", "b.py", "apply_patch"))
    )


def test_patch_with_no_header_is_malformed():
    assert _map("apply_patch", _args({"input": "*** Begin Patch\n+x\n*** End Patch"})) == Malformed(
        "patch text names no file"
    )


def test_patch_header_with_empty_path_is_malformed():
    assert _map("apply_patch", _args({"input": "*** Add File:   \n+x"})) == Malformed(
        "patch header names no path"
    )


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("write_to_file", {"absolutePath": "/work/a.txt", "path": "/x/.env", "content": ""}),
        ("apply_patch", {"patchText": "*** Add File: a", "input": "*** Add File: b"}),
        ("run_commands", {"commands": ["ls"], "cmd": "rm -rf /"}),
        ("read_files", {"files": [{"path": "a"}], "file_paths": ["/x/.env"]}),
        ("read_files", {"file_paths": ["a"], "paths": ["b"]}),
        ("read_files", {"files": [{"path": "a", "filePath": "/x/.env"}]}),
        ("read_files", {"files": [{"path": "a"}, {"file_path": "b", "filePath": "c"}]}),
    ],
    ids=["write_to_file", "apply_patch", "run_commands", "files+file_paths", "file_paths+paths",
         "per-entry", "per-entry-second"],
)
def test_two_spellings_of_one_key_are_malformed(tool, arguments):
    # Orchestrator decision 3 (STORY-004): which spelling an executor prefers
    # is undocumented, so two present in one call fail closed.
    result = _map(tool, _args(arguments))
    assert isinstance(result, Malformed)
    assert result.detail.startswith("more than one spelling of the target is present")


# --- PRD-017 STORY-001: OpenCode 2.0 (SOURCES.md "OpenCode 2.x") ---------------


@pytest.mark.parametrize("tool", ["read", "write", "edit"])
def test_opencode_filepath_and_path_together_are_malformed(tool):
    # OpenCode 2.0 renamed `filePath` to `path`; v1.19.5 still sends `filePath`.
    # A client sends one spelling, so both present is Malformed (S2): an
    # executor's preference is undocumented, so neither choice is safe.
    result = _map(tool, _args({"filePath": "/work/a.txt", "path": "/x/.env", "content": ""}))
    assert isinstance(result, Malformed)
    assert result.detail.startswith("more than one spelling of the target is present")


@pytest.mark.parametrize("tool", ["read", "write", "edit"])
@pytest.mark.parametrize("key", ["filePath", "path"])
def test_opencode_both_key_spellings_are_one_operation(tool, key):
    kind = "fs_read" if tool == "read" else "fs_write"
    assert _map(tool, _args({key: "/work/a.txt"})) == Operations((Operation(kind, "/work/a.txt", tool),))


def test_opencode_2_read_of_a_directory_is_one_fs_read():
    # 2.0 `read` lists a directory: still one fs_read of `path` (SOURCES.md, OpenCode 2.x notes).
    assert _map("read", _args({"path": "/work/src", "offset": 1, "limit": 50})) == Operations(
        (Operation("fs_read", "/work/src", "read"),)
    )


def test_opencode_2_patch_ignores_the_environment_id_line():
    # 2.0 allows `*** Environment ID: <id>` right after `*** Begin Patch`; it names no file.
    text = "*** Begin Patch\n*** Environment ID: env-1\n*** Add File: src/new.ts\n+x\n*** End Patch\n"
    assert _targets(_map("patch", _args({"patchText": text}))) == ("src/new.ts",)


def test_opencode_2_patch_does_not_read_the_cline_input_key():
    # `patch` is OpenCode 2.0 only (`patchText`); `input` stays `apply_patch`'s (Cline).
    assert isinstance(_map("patch", _args({"input": _PATCH})), Malformed)


@pytest.mark.parametrize("name", ["execute", "subagent"])
def test_opencode_2_codemode_and_subagent_are_unknown(name):
    # `execute` runs JavaScript that can `fetch` and call MCP tools (CodeMode), so it
    # is `tool.unknown` and never `opaque_tools`; `subagent` is a `none` row.
    assert _map(name, _args({"code": "await fetch('https://x')", "agent": "general", "prompt": "p"})) == Unknown()


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({"cmd": "ls -la"}, ("ls -la",)),
        ({"commands": "npm test"}, ("npm test",)),
        ({"commands": {"command": "git", "args": ["status"]}}, ("git status",)),
        ({"commands": [{"command": "ls"}]}, ("ls",)),
    ],
    ids=["cmd", "commands-one-string", "commands-one-argv", "argv-without-args"],
)
def test_run_commands_lenient_aliases_are_classified(arguments, expected):
    assert _targets(_map("run_commands", _args(arguments))) == expected


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({"files": [{"file_path": "/a"}, {"filePath": "/b"}, {"path": "/c"}]}, ("/a", "/b", "/c")),
        ({"files": {"path": "/a"}}, ("/a",)),
        ({"files": {"filePath": "/a"}}, ("/a",)),
        ({"file_paths": ["/a", "/b"]}, ("/a", "/b")),
        ({"file_paths": "/a"}, ("/a",)),
        ({"paths": ["/a", "/b"]}, ("/a", "/b")),
        ({"paths": "/a"}, ("/a",)),
    ],
    ids=["per-entry-aliases", "files-one-object", "files-one-object-alias", "file_paths",
         "file_paths-string", "paths", "paths-string"],
)
def test_read_files_lenient_aliases_are_classified(arguments, expected):
    assert _targets(_map("read_files", _args(arguments))) == expected


@pytest.mark.parametrize(
    "tool, arguments",
    [
        # Top-level argv: reading `command` alone would drop `args`.
        ("run_commands", {"command": "git", "args": ["push", "--force"]}),
        ("run_commands", {"command": "ls"}),
        # Not expressible: one key both a value and an object.
        ("read_files", {"files": ["/a"]}),
        ("read_files", {"files": "/a"}),
        ("read_files", {"paths": {"path": "/a"}}),
    ],
    ids=["run_commands-argv-top", "run_commands-command-top", "files-strings", "files-string",
         "paths-object"],
)
def test_inexpressible_cline_4_shapes_are_malformed(tool, arguments):
    assert isinstance(_map(tool, _args(arguments)), Malformed)


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("run_commands", {"commands": []}),
        ("read_files", {"files": []}),
        ("fetch_web_content", {"requests": []}),
    ],
)
def test_empty_array_is_malformed_not_zero_operations(tool, arguments):
    result = _map(tool, _args(arguments))
    assert isinstance(result, Malformed)
    assert result.detail.endswith("is empty")


@pytest.mark.parametrize(
    "args",
    [["-rf", "a;b"], ["$(x)", "`id`"], ["two words", "it's \"quoted\""], []],
)
def test_argv_element_round_trips_through_shlex(args):
    result = _map("run_commands", _args({"commands": [{"command": "rm", "args": args}]}))
    (target,) = _targets(result)
    assert shlex.split(target) == ["rm", *args]


@pytest.mark.parametrize(
    "element",
    [{"command": "rm", "args": ["-rf", 3]}, {"command": "rm", "args": "-rf /"}, {"command": 3}, {"args": ["x"]}, 7, None],
)
def test_argv_element_with_non_string_parts_is_malformed(element):
    assert isinstance(_map("run_commands", _args({"commands": [element]})), Malformed)


@pytest.mark.parametrize("tool", ["glob", "grep"])
def test_optional_target_defaults_to_dot(tool):
    result = _map(tool, _args({"pattern": "TODO"}))
    assert _targets(result)[0] == "."


def test_optional_target_present_but_null_is_malformed():
    assert _map("grep", _args({"pattern": "x", "path": None})) == Malformed("target 'path' is not a string")


def test_glob_pattern_is_a_second_operation():
    result = _map("glob", _args({"pattern": "../../**/.env*"}))
    assert result == Operations(
        (Operation("fs_read", ".", "glob"), Operation("fs_read", "../../**/.env*", "glob"))
    )


@pytest.mark.parametrize(
    "tool, arguments, expected",
    [
        ("grep", {"pattern": "x"}, (".",)),
        ("grep", {"pattern": "x", "include": ""}, (".",)),
        ("grep", {"pattern": "x", "include": "  "}, (".",)),
        ("grep", {"pattern": "x", "path": "src", "include": ".env*"}, ("src", ".env*")),
        ("search_files", {"path": "src", "regex": "x"}, ("src",)),
        ("search_files", {"path": "src", "regex": "x", "file_pattern": ""}, ("src",)),
        ("search_files", {"path": "src", "regex": "x", "file_pattern": "*.pem"}, ("src", "*.pem")),
    ],
    ids=["absent", "empty", "blank", "present", "sf-absent", "sf-empty", "sf-present"],
)
def test_optional_target_is_read_when_present_and_skipped_when_absent(tool, arguments, expected):
    """PRD-016 D15 (STORY-013): an absent, empty or blank optional target adds no operation."""
    assert _targets(_map(tool, _args(arguments))) == expected


def test_optional_target_present_but_not_a_string_is_malformed():
    assert _map("grep", _args({"pattern": "x", "include": None})) == Malformed("target 'include' is not a string")
    assert _map("search_files", _args({"path": "s", "regex": "x", "file_pattern": 3})) == Malformed(
        "target 'file_pattern' is not a string"
    )


def test_optional_target_with_a_line_break_is_malformed():
    assert _map("grep", _args({"pattern": "x", "include": "a\nb"})) == Malformed(
        "target 'include' contains a line break"
    )


def test_glob_without_pattern_is_malformed():
    assert _map("glob", _args({"path": "."})) == Malformed("missing target key 'pattern'")


def test_browser_action_without_url_is_malformed():
    assert isinstance(_map("browser_action", _args({"action": "click", "coordinate": "1,2"})), Malformed)


def test_nested_missing_key_is_malformed():
    result = _map("fetch_web_content", _args({"requests": [{"prompt": "x"}]}))
    assert result == Malformed("missing target key under 'requests[]'")


def test_array_element_that_is_not_an_object_is_malformed():
    result = _map("fetch_web_content", _args({"requests": ["https://a.example"]}))
    assert result == Malformed("'requests[]' is not an object")


def test_scalar_where_an_array_is_required_is_malformed():
    result = _map("fetch_web_content", _args({"requests": {"url": "https://a.example"}}))
    assert result == Malformed("'requests' is not an array")


@pytest.mark.parametrize("name", ["postgres_query", "supabase__execute_sql", "abc0mcp0query", "supabase__run_sql_1a2b3c4d"])
def test_prefixed_mcp_names_are_unknown(name):
    assert _map(name, _args({"query": "SELECT 1", "sql": "SELECT 1"})) == Unknown()


def test_path_with_line_break_is_malformed():
    # The PRD 6.6 sample's `apply_patch` before `format: patch` was added: the
    # whole patch read as one path. Fails closed instead of reaching the path
    # classifier as one relative "path".
    tools = {"apply_patch": ToolMapping("fs_write", "patchText")}
    result = _map("apply_patch", _args({"patchText": _PATCH}), tools=tools)
    assert result == Malformed("target 'patchText' contains a line break")
    assert isinstance(_map("read", _args({"filePath": "a\x00b"})), Malformed)
    assert isinstance(_map("webfetch", _args({"url": "https://a\r\nHost: b"})), Malformed)


def test_shell_and_sql_targets_keep_newlines():
    assert _targets(_map("bash", _args({"command": "ls\nrm -rf /"}))) == ("ls\nrm -rf /",)
    assert _targets(_map("run_sql", _args({"query": "SELECT 1;\nDROP TABLE t"}))) == ("SELECT 1;\nDROP TABLE t",)


@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_empty_target_is_malformed(value):
    assert _map("bash", _args({"command": value})) == Malformed("target 'command' is empty")


# --- AC3 -----------------------------------------------------------------------

_MALFORMED_CASES = [
    ("not json", _CAP),
    ("[]", _CAP),
    ("{}", _CAP),
    ('{"command": 3}', _CAP),
    ('"ls"', _CAP),
    ("null", _CAP),
    ("3", _CAP),
    ('{"command": null}', _CAP),
    ('{"command": "ls", "command": "rm -rf /"}', _CAP),
    ('{"x": {"a": 1, "a": 2}, "command": "ls"}', _CAP),
    ("[" * 100_000, 200_000),
    ('{"command": ' + "9" * 5000 + "}", _CAP),
    ('{"command": "' + "a" * 50 + '"}', 10),
]


@pytest.mark.parametrize("arguments, cap", _MALFORMED_CASES, ids=range(len(_MALFORMED_CASES)))
def test_malformed_arguments(arguments, cap):
    result = _map("bash", arguments, cap=cap)
    assert isinstance(result, Malformed)
    assert result.detail


@pytest.mark.parametrize("arguments, cap", _MALFORMED_CASES, ids=range(len(_MALFORMED_CASES)))
def test_detail_never_echoes_argument_values(arguments, cap):
    detail = _map("bash", arguments, cap=cap).detail
    for value in ("rm -rf /", "not json", "ls", "a" * 50):
        assert value not in detail.replace("'command'", "")


def test_over_length_is_malformed_without_parsing(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("json.loads must not be called")

    monkeypatch.setattr(json, "loads", _boom)
    arguments = '{"command": "' + "a" * 50 + '"}'
    assert _map("bash", arguments, cap=10) == Malformed("arguments exceed 10 characters")
    assert _map("bash", arguments, cap=len(arguments) - 1) == Malformed(
        f"arguments exceed {len(arguments) - 1} characters"
    )
    # Control: under the cap the patched json.loads is really reached.
    with pytest.raises(AssertionError, match="must not be called"):
        _map("bash", arguments, cap=len(arguments))


def test_length_at_the_cap_is_accepted():
    arguments = '{"command": "ls"}'
    assert _targets(_map("bash", arguments, cap=len(arguments))) == ("ls",)
    assert isinstance(_map("bash", arguments, cap=len(arguments) - 1), Malformed)


# --- AC4 -----------------------------------------------------------------------


@pytest.mark.parametrize("name", ["frobnicate", "Bash", "BASH", " bash", ""])
def test_unmapped_name_is_unknown(name):
    assert _map(name, '{"command": "ls"}') == Unknown()


@pytest.mark.parametrize("decision", ["allow", "flag", "deny"])
@pytest.mark.parametrize(
    "arguments", ['{"todos": []}', "not json", "x" * (_CAP + 1)], ids=["json", "not-json", "over-cap"]
)
def test_opaque_tool_returns_configured_decision(decision, arguments):
    # PRD 6.4: an opaque tool's arguments are not read, so neither the parse
    # nor the cap applies.
    assert _map("todowrite", arguments, opaque={"todowrite": decision}) == Opaque(decision)


def test_mapped_name_wins_over_opaque():
    result = _map("bash", '{"command": "rm -rf /"}', opaque={"bash": "allow"})
    assert _targets(result) == ("rm -rf /",)


# --- ToolMapping validation ----------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "none", "target": "x"},
        {"kind": "exec", "target": "x"},
        {"kind": "shell", "target": "x", "format": "argv"},
        {"kind": "shell", "target": ""},
        {"kind": "shell", "target": "a||b"},
        {"kind": "shell", "target": "a|"},
        {"kind": "shell", "target": "a..b"},
        {"kind": "shell", "target": "a[]b"},
        {"kind": "shell", "target": "a[][]"},
        {"kind": "shell", "target": "path?"},
        {"kind": "shell", "target": "1a"},
        {"kind": "shell", "target": "a b"},
        {"kind": "shell", "target": ["command"]},
        {"kind": "shell", "target": "a|a"},
        {"kind": "shell", "target": "a|a.b"},
        {"kind": "shell", "target": "files[]|files[].path"},
        {"kind": "fs_read", "target": "path", "default": ""},
        {"kind": "fs_read", "target": "path", "default": "  "},
        {"kind": "fs_read", "target": "path", "default": 3},
        {"kind": "fs_write", "target": "patchText", "format": "patch", "default": "."},
        {"kind": "fs_read", "target": "files[].path", "default": "."},
        {"kind": "fs_read", "target": "path", "extra_targets": ("a..b",)},
        {"kind": "fs_read", "target": "path", "extra_targets": ["pattern"]},
        {"kind": "fs_read", "target": "path", "extra_targets": (3,)},
        # PRD-016 D15 (STORY-013): optional_targets is validated like extra_targets.
        {"kind": "fs_read", "target": "path", "optional_targets": ("a..b",)},
        {"kind": "fs_read", "target": "path", "optional_targets": ["x"]},
        {"kind": "fs_read", "target": "path", "optional_targets": (3,)},
    ],
)
def test_tool_mapping_rejects_bad_definitions(kwargs):
    with pytest.raises(ToolMappingError):
        ToolMapping(**kwargs)


def test_unknown_kind_message_lists_the_vocabulary():
    with pytest.raises(ToolMappingError, match="shell, sql, fs_write, fs_read, http"):
        ToolMapping("exec", "command")
    with pytest.raises(ToolMappingError, match=", ".join(TARGET_FORMATS)):
        ToolMapping("shell", "command", format="argv")


def test_tool_mapping_error_is_a_value_error():
    assert issubclass(ToolMappingError, ValueError)


def test_tool_mapping_accepts_the_grammar():
    ToolMapping("fs_read", "a.b_c-d[].e|x[]|x|_y")
    ToolMapping("fs_read", "path", default=".", extra_targets=("pattern", "q.r"))


def test_built_in_tools_is_read_only():
    with pytest.raises(TypeError):
        BUILT_IN_TOOLS["bash"] = ToolMapping("shell", "cmd")  # type: ignore[index]


def test_tool_call_is_the_frozen_dataclass_of_section_6_2():
    assert tuple(f.name for f in dataclasses.fields(ToolCall)) == ("id", "name", "arguments")
    call = ToolCall(id="c1", name="bash", arguments="{}")
    with pytest.raises(dataclasses.FrozenInstanceError):
        call.name = "x"
    with pytest.raises(dataclasses.FrozenInstanceError):
        BUILT_IN_TOOLS["bash"].target = "x"


def test_operation_is_re_exported_not_redefined():
    assert action_adapters.Operation is action_classifiers.Operation
    assert action_adapters.OperationKind is action_classifiers.OperationKind


# --- Never raises (PRD F7) -----------------------------------------------------

_HOSTILE = [
    "[" * 5000,
    "{" * 5000,
    '{"a":' * 3000 + "1" + "}" * 3000,
    '{"command": ' + "9" * 5000 + "}",
    '{"command": "\\ud800"}',
    '{"command": NaN, "path": Infinity}',
    '{"commands": [[["ls"]]], "files": [[{"path": "a"}]]}',
    '{"patchText": {"x": 1}, "input": ["*** Add File: a"]}',
    '{"filePath": ["a"], "url": {}, "sql": true, "query": 1.5}',
    "",
    " ",
    "\x00",
    '{"\\u0000": "\\u0000"}',
]


@pytest.mark.parametrize("arguments", _HOSTILE, ids=range(len(_HOSTILE)))
@pytest.mark.parametrize("name", sorted(BUILT_IN_TOOLS))
def test_map_tool_call_never_raises(name, arguments):
    assert isinstance(_map(name, arguments), _RESULT_TYPES)


def test_non_string_arguments_and_name_are_malformed():
    tools = BUILT_IN_TOOLS
    assert map_tool_call(ToolCall("c1", "bash", None), tools, {}, _CAP) == Malformed(  # type: ignore[arg-type]
        "arguments is not a string"
    )
    assert isinstance(map_tool_call(ToolCall("c1", ["bash"], "{}"), tools, {}, _CAP), Malformed)  # type: ignore[arg-type]


# --- AC5: purity ---------------------------------------------------------------


def test_action_adapters_stays_pure():
    """PRD-016 Section 6.12: no settings, no file I/O; the only `app` import is
    the vocabulary package (the one-way edge decided in STORY-003)."""
    source = inspect.getsource(action_adapters)

    assert "settings" not in vars(action_adapters)
    assert "open(" not in source
    assert "Path(" not in source
    assert "os." not in source
    imports = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    app_targets = {
        re.split(r"\s+", line)[1] for line in imports if re.match(r"(from|import) app(\.|\s|$)", line)
    }
    assert app_targets == {"app.services.action_classifiers"}


def test_importing_action_adapters_loads_no_settings():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, app.services.action_adapters; "
            "print(sorted(m for m in sys.modules if m == 'app' or m.startswith('app.')))",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.strip() == str(
        ["app", "app.services", "app.services.action_adapters", "app.services.action_classifiers"]
    )
