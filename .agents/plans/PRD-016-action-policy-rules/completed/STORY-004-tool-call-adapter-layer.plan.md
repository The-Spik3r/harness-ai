---
story: STORY-004
prd: PRD-016
slug: tool-call-adapter-layer
title: ToolCall, Operation, the tool mapping layer and built-in OpenCode/Cline/SQL mappings
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-016-action-policy-rules        # all stories commit here, no per-story branch
created: 2026-11-15
---

# Plan: ToolCall, Operation, the tool mapping layer and built-in OpenCode/Cline/SQL mappings

## Summary

One new pure module, `app/services/action_adapters.py`, and one new test file. The module defines `ToolCall` (PRD 6.2), re-exports `Operation` / `OperationKind` from `app.services.action_classifiers` (orchestrator decision, STORY-003), and adds a `ToolMapping` that can express every shape in `tests/corpora/actions/SOURCES.md` *Implications for STORY-004*. That covers key paths into arrays (`commands[]`, `files[].path`), aliases (`absolutePath|path`), an optional target with a default (`default="."`), a second target key (`extra_targets=("pattern",)`), and three closed value formats: `text`, `command` (a shell string or a `{command, args[]}` argv object, joined with `shlex.join`) and `patch` (header paths extracted from `*** Add/Update/Delete File:` / `*** Move to:` lines). It also adds the four `MappingResult` variants (`Operations`, `Opaque`, `Unknown`, `Malformed`), `map_tool_call(call, tools, opaque_tools, max_argument_characters)` and `BUILT_IN_TOOLS`, which is module data that STORY-006 places in the built-in policy unchanged. Everything ambiguous fails closed to `Malformed`: zero operations, an empty array, a patch with no header, an empty target, a line break in a path or URL, a duplicate JSON key, or JSON nested deep enough to raise `RecursionError`. `tests/test_action_adapters.py` parses the per-client tables of `SOURCES.md` and parametrizes over every row.

## User Story

As a security admin
I want every tool call mapped to the operation it performs, with unknown and malformed calls named as such
So that classification starts from what the call does rather than what the tool is called

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-004-tool-call-adapter-layer.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md`. Section 4 *Operations and adapters* (lines 54-62), 6.2 (lines 184-218), 6.3 `tool.*` rows (lines 248-250), 6.4 (`tool.opaque` ends classification, line 258), 6.6 sample `tools:` / `opaque_tools:` (lines 305-315), 6.12 purity (line 473), F1 (line 482).
- STORY-001 outputs:
  - `tests/corpora/actions/SOURCES.md:41-58` (OpenCode), `:89-99` (Cline 4.x), `:129-142` (Cline 3.x), `:191-196` (SQL). These are the four tables with the fixed header `| Client | Tool | Operation kind | Target key | Multi-target | Paths | ...`, and the test parses them. Conventions are at `:17-29`. *Implications for STORY-004* is at `:243-258`.
  - `.agents/spikes/PRD-016-action-policy-rules/threat-model.md:58-66`, findings S1, S2, S4, S6, S7 and S8 for STORY-004. Each is answered in *Design / Shape decisions* below.
- STORY-003 outputs: `app/services/action_classifiers/__init__.py:31` (`OperationKind`), `:36` (`Decision`), `:84-85` (`OPERATION_KINDS`, `DECISIONS`), `:107-119` (`Operation`), `:11-16` (the one-way import decision).

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | new `app/services/action_adapters.py`; new `tests/test_action_adapters.py` |
| Story | STORY-004 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | The story frontmatter has `skills: []`. `.agents/skills/` holds only `frontend-design` (UI aesthetics), and this story has no UI. | none |

---

## Verified invariants (read in the code, not assumed)

- `Operation(kind, target, source_tool)` is frozen and positional in that order (`action_classifiers/__init__.py:107-119`), so `Operation("shell", "ls", "bash")` equals AC1's keyword form. `Operation` has **no** argv flag, so the structured `{command, args[]}` form must become a shell line that tokenizes back to the same argv (S4). `shlex.join` does that. Checked in the venv (Python 3.12.10): `shlex.split(shlex.join(["rm","-rf","a;b","$(x)"])) == [...]` is True, and `;` and `$(x)` come out single-quoted.
- `json.loads("[" * 100000)` raises **`RecursionError`**, not `ValueError` (checked in the venv). 100,000 characters is exactly the PRD's default cap, so `map_tool_call` must catch `RecursionError` as well as `ValueError` (`JSONDecodeError` is a `ValueError`, and so is CPython's int-digit-limit error). Otherwise a model-produced input raises through `evaluate()`. F7 says "neither raises for any input a model can produce". STORY-014 would catch it as `tool.malformed` anyway, but with an ERROR log that blames a classifier.
- `app/__init__.py` and `app/services/__init__.py` are empty, so importing `app.services.action_classifiers` pulls in no `app.config`. The import-graph test can therefore assert `app.config not in sys.modules` after a fresh `import app.services.action_adapters`.
- Only one tool name is shared between clients: `apply_patch` (OpenCode key `patchText`, Cline 4.x/3.x key `input`; `SOURCES.md:46`, `:94`, `:140`). Exact-name matching therefore needs one mapping with the alias `patchText|input`. Every other built-in name is unique.
- No pre-existing test references `action_adapters`. The only test importing `action_classifiers` is `tests/test_action_vocabulary.py`. No pre-existing test assertion changes.

---

## Patterns to Follow

### Pure-module docstring citing the PRD, closed `Literal` + `get_args`
```python
# SOURCE: app/services/action_classifiers/__init__.py:18-31, 80-85
Pure on purpose (PRD-016 Section 6.12): no I/O, no settings, no pydantic, no
`app` import, nothing read at import. ...
OperationKind = Literal["shell", "sql", "fs_write", "fs_read", "http"]
...
OPERATION_KINDS: tuple[str, ...] = get_args(OperationKind)
```
`TargetFormat = Literal["text", "command", "patch"]` and `TARGET_FORMATS = get_args(TargetFormat)` follow the same shape, so STORY-007 can enumerate them in an error message.

### Frozen dataclasses with `#:` field comments
```python
# SOURCE: app/services/action_classifiers/__init__.py:107-119
@dataclass(frozen=True)
class Operation:
    """One thing a tool call does, as the adapter layer maps it (PRD-016 Section 6.2). ..."""
    kind: OperationKind
    #: The command, statement, path or URL the rule is about.
    target: str
```

### Two-exception seam: the pure module raises, the config module re-raises with the file and node
```python
# SOURCE: app/services/pattern_detector.py:36-44
class PatternCompileError(Exception):
    """Raised by compile_pattern() when a pattern cannot become a regex: ...
    It deliberately does not name a list or a file: this module is pure
    and cannot know where the pattern came from. `pattern_config.load()`
    (STORY-005) catches this and re-raises `PatternConfigError` with the list
    name attached, which is the error an operator actually reads at startup."""
```
`ToolMappingError` follows this. `ToolMapping.__post_init__` raises it for a bad kind, format, target expression or default. STORY-006/007 catch it and re-raise `ActionConfigError` with the file and `tools.<name>` node attached.

### Constructor-time validation in a frozen dataclass
```python
# SOURCE: app/services/openrouter_client.py:61-66
    def __post_init__(self) -> None:
        if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
            raise UnsupportedParameterError(
                f"temperature must be between 0.0 and 2.0, got {self.temperature!r}"
            )
```

### Error messages that enumerate the closed vocabulary
```python
# SOURCE: app/services/pattern_detector.py:105-108
    raise PatternCompileError(
        f"unknown match mode {match!r} for pattern {pattern!r} "
        "(expected one of: word, regex)"
    )
```

### Tests: purity by source inspection (the "import-graph test pattern")
```python
# SOURCE: tests/test_pattern_matching.py:303-323 (and tests/test_action_vocabulary.py:141-153)
    source = inspect.getsource(pattern_detector)
    assert "settings" not in vars(pattern_detector)
    assert "open(" not in source
    assert "Path(" not in source
    imports = [line for line in source.splitlines()
               if line.startswith("import ") or line.startswith("from ")]
    assert not [line for line in imports if " app." in line or line.startswith("from app")]
```
Adapted. The single permitted `app` import is `from app.services.action_classifiers import ...` (the decided one-way edge). The test asserts the import lines' `app` targets are exactly `{"app.services.action_classifiers"}`. It also adds a subprocess check of `sys.modules`.

### Tests: reading a checked-in corpus file next to the tests
```python
# SOURCE: tests/test_pattern_corpus.py:77-80, 101-103
_CORPORA = Path(__file__).resolve().parent / "corpora"
_NOT_SAMPLES = frozenset({"SOURCES.md"})
...
    return path.read_text(encoding="utf-8")
```

### Tests: hardcoded expectations with the source named in the module docstring
`tests/test_action_vocabulary.py:1-8`: "The expected values are transcribed from the PRD and hardcoded on purpose: no test in this repo reads a PRD file." SOURCES.md is a test corpus file, not the PRD, and `SOURCES.md:7-10` says "STORY-004's parametrized test reads the per-client tables". So the test reads SOURCES.md. The realistic argument samples are hardcoded in the test.

---

## Design

### Public surface of `app/services/action_adapters.py`

```python
from app.services.action_classifiers import Decision, OPERATION_KINDS, Operation, OperationKind

__all__ = [...]   # ToolCall, Operation, OperationKind, TargetFormat, TARGET_FORMATS, ToolMapping,
                  # ToolMappingError, Operations, Opaque, Unknown, Malformed, MappingResult,
                  # BUILT_IN_TOOLS, map_tool_call

TargetFormat = Literal["text", "command", "patch"]
TARGET_FORMATS: tuple[str, ...] = get_args(TargetFormat)

@dataclass(frozen=True)
class ToolCall:            # PRD 6.2 verbatim
    id: str
    name: str
    #: The raw JSON string, exactly as the model emitted it.
    arguments: str

class ToolMappingError(ValueError): ...   # raised by ToolMapping.__post_init__; no file/node (pure)

@dataclass(frozen=True)
class ToolMapping:
    kind: OperationKind
    #: Key-path expression: `path ("|" path)*`, path := seg ("." seg)*, seg := key | key"[]",
    #: key := [A-Za-z_][A-Za-z0-9_-]*. `|` separates spellings of one target (aliases).
    target: str
    #: The target when every spelling is absent (`glob.path?` -> "."). None = required.
    default: Optional[str] = None
    #: How the value at the path is read: text | command | patch.
    format: TargetFormat = "text"
    #: Further key-path expressions in the same call, each required, read as `text`,
    #: each yielding operations of the same kind (OpenCode `glob.pattern`, S7).
    extra_targets: tuple[str, ...] = ()
    def __post_init__(self) -> None: ...   # validates kind, format, every expression, default rules

@dataclass(frozen=True)
class Operations:
    operations: tuple[Operation, ...]      # never empty (invariant, checked in map_tool_call)

@dataclass(frozen=True)
class Opaque:
    decision: Decision

@dataclass(frozen=True)
class Unknown:
    pass

@dataclass(frozen=True)
class Malformed:
    #: A fixed phrase naming the problem and at most a key path from the mapping,
    #: never an argument value (PRD-016 T11; it may reach the agent via `reason`).
    detail: str

MappingResult = Union[Operations, Opaque, Unknown, Malformed]

BUILT_IN_TOOLS: Mapping[str, ToolMapping] = MappingProxyType({...})

def map_tool_call(call: ToolCall, tools: Mapping[str, ToolMapping],
                  opaque_tools: Mapping[str, Decision],
                  max_argument_characters: int) -> MappingResult: ...
```

`ToolMapping.__post_init__` rules (each raises `ToolMappingError` naming the field and value, and lists the closed vocabulary where there is one):
- `kind` is in `OPERATION_KINDS`. `format` is in `TARGET_FORMATS`.
- `target` and each `extra_targets` entry parse under the grammar above. Rejected: an empty expression, an empty alternative (`a||b`), an empty segment (`a..b`), a bad key character, `[]` not at the end of a segment, and the `?` suffix (optionality is spelled `default=`, so there is only one way to say it).
- `default`, if set, is a non-empty string, only with `format="text"`, and only when no alternative of `target` contains `[]`. An array has no sensible "absent" value.
- `extra_targets` is a tuple. An empty tuple is fine.

The parsed expression is cached in a module-level `functools.lru_cache` helper `_parse_target(expr)`, so `__post_init__` and `map_tool_call` share one parser and the frozen dataclass needs no derived field.

### `map_tool_call` algorithm (order matters; each step cites its source)

1. `mapping = tools.get(call.name)`, exact and case-sensitive (S6, `SOURCES.md:256` "exact-name matching ... is the fail-closed default").
2. If `mapping is None`: `return Opaque(opaque_tools[call.name])` if the name is in `opaque_tools`, else `return Unknown()`. An opaque tool's arguments are "not ours to read" (PRD 6.4, line 258), so the length cap and the JSON parse are skipped for it. The tools mapping is checked **first**, so a name in both is classified rather than waved through. STORY-007 refuses that overlap at startup anyway (its AC2).
3. If `arguments` is not a `str`, return `Malformed("arguments is not a string")`. This is defensive, since PRD-017 builds `ToolCall`.
4. If `len(call.arguments) > max_argument_characters`, return `Malformed(f"arguments exceed {max_argument_characters} characters")` **before** `json.loads` (AC3). The detail names the configured limit. That number is not a secret, and it tells the operator which setting to raise. If the orchestrator prefers a fixed phrase, drop the number.
5. `json.loads(call.arguments, object_pairs_hook=_reject_duplicate_keys)`, catching `ValueError` and `RecursionError` and returning `Malformed("arguments is not valid JSON")`. A duplicate key returns `Malformed("arguments has a duplicate key")`. The module calls `json.loads` through `import json`, so the test can monkeypatch `json.loads`.
6. If the value is not a `dict`, return `Malformed("arguments is not a JSON object")` (PRD Section 4, line 61; S9 bare string or array).
7. Resolve `mapping.target` with `mapping.format`, then each `extra_targets` entry as `text`. Each yields target strings in order. An internal `_MalformedArguments(detail)` exception is raised and caught at the `map_tool_call` boundary.
   - **Aliases**: every alternative that is present is read, in the declared order. If none is present, fall back to `default` if set, else `Malformed("missing target key '<expr>'")`. Reading every present spelling, rather than the first, is deliberate. Which spelling the executor prefers when two are sent is undocumented, so classifying both covers either (fail closed, no evasion via `{"path": "a.ts", "absolutePath": "/x/.env"}`).
   - **Present but `null`** counts as present: it is not a string, so the call is `Malformed`. The default applies only to an absent key.
   - **Key paths**: `seg[]` requires a list (`Malformed("'files' is not an array")`). An **empty list** is `Malformed("'files' is empty")`, because zero operations would mean `allow` (the S1 rule generalised). An intermediate step requires a dict (`Malformed("'files[]' element is not an object")`), and a missing nested key is `Malformed("missing target key 'files[].path'")`.
   - **`text`**: the leaf must be a `str` (`Malformed("target 'command' is not a string")`, AC3 `{"command": 3}`).
   - **`command`**: the leaf is a `str` (a shell line, taken as is) or a dict with `command: str` and optional `args: list[str]`. That becomes `shlex.join([command, *args])`, which the POSIX classifier tokenizes back to exactly that argv (S4; `SOURCES.md:249`). Other keys in the dict are ignored. Anything else is `Malformed`.
   - **`patch`**: the leaf must be a `str`. `_patch_paths(text)` returns, in order, the path after each line that, `strip()`ped, starts with `*** Add File: `, `*** Update File: `, `*** Delete File: ` or `*** Move to: ` (`SOURCES.md:70`, `:113`, `:220-221`). `Begin`/`End Patch` markers are not required, so over-matching costs a false deny, never an allow. No header gives `Malformed("patch text names no file")`, and an empty path after a header gives `Malformed("patch header names no path")` (S1, F1).
   - **Every target string**: empty or whitespace-only gives `Malformed("target '<expr>' is empty")`. For kinds `fs_write`, `fs_read` and `http`, a target containing `\n`, `\r` or `\x00` gives `Malformed("target '<expr>' contains a line break")`. No real path or URL holds one, and it closes the hole where a patch mapped **without** `format: patch` (as in the PRD 6.6 sample, see Risks) would reach the path classifier as one relative "path" and be allowed. `shell` and `sql` targets keep their newlines, which are legitimate segment and statement separators.
8. Build `Operation(kind=mapping.kind, target=t, source_tool=call.name)` per target. If none were built (unreachable given the rules above, but asserted), return `Malformed("no target")`. Otherwise return `Operations(tuple(...))`.

`map_tool_call` itself never raises for any `ToolCall` (property-tested in Task 3 with a fuzz-ish parametrized set).

### Shape decisions (one per *Implications for STORY-004* item, `SOURCES.md:247-256`)

| # | Shape | Decision |
|---|---|---|
| 1 | array of strings `commands[]` | Supported: `target="commands[]"`, one `Operation` per element |
| 2 | array of objects `files[].path`, `requests[].url` | Supported: `target="files[].path"` |
| 3 | mixed string / `{command, args[]}` | Supported: `format="command"`, argv joined with `shlex.join` (S4). `Operation` is unchanged (no argv flag needed) |
| 4 | paths in patch text | Supported: `format="patch"`. No header or an empty path gives `Malformed` (S1) |
| 5 | optional target with a default | Supported: `default="."` for OpenCode `glob.path` and `grep.path` (S8, F1). Cline 3.x `browser_action.url` stays **required**: there is no sensible default URL, so a non-`launch` action (`click`, `scroll_*`) is `tool.malformed` (deny). Fail closed, stated in the `BUILT_IN_TOOLS` comment |
| 6 | a second target key | Supported: `extra_targets=("pattern",)` on `glob`, a second `fs_read` operation (S7). How a secret glob matches a *glob pattern* target is STORY-013's. `*** Move to:` is covered by shape 4. `grep.include` (a filename glob) is **not** read. Directory-scoped searches returning secrets are S9, deferred to STORY-013 as the threat model says |
| 7 | Cline 4.x lenient aliases | The grammar supports `|`. The built-ins read the **advertised** keys only (`commands`, `files[].path`, `requests[].url`), so `{cmd}`, `{command}` at the top level of `run_commands`, `file_paths`, `paths`, and per-element `file_path`/`filePath` are `tool.malformed` (fail closed, S2). Reason: top-level `{command, args}` in `run_commands` is argv while `{command}` in other tools is a shell line, so the aliases are not uniform enough to add without per-alias tests that a deployment can't see. A deployment that wants them writes, for example, `target: "files[].path|files[].filePath|file_paths[]"` |
| 8 | one name, two spellings | Supported: `write_to_file` and `replace_in_file` use `target="absolutePath|path"`. `apply_patch` uses `"patchText|input"` (OpenCode and Cline share the name) |
| 9 | non-object arguments | `Malformed("arguments is not a JSON object")`. Tested with `"[]"`, `'"rm -rf /"'`, `"3"` and `"null"` |
| 10 | prefixed MCP names | Exact-name match only. `postgres_query`, `supabase__execute_sql` and `<uid>0mcp0query` are `Unknown()` (S6). Tested |

### `BUILT_IN_TOOLS` (24 entries; source row in `SOURCES.md`)

| Name | kind | target | default | format | extra | Source |
|---|---|---|---|---|---|---|
| `bash` | shell | `command` | | text | | :43 |
| `write` | fs_write | `filePath` | | text | | :44 |
| `edit` | fs_write | `filePath` | | text | | :45 |
| `apply_patch` | fs_write | `patchText\|input` | | patch | | :46, :94, :140 |
| `read` | fs_read | `filePath` | | text | | :47 |
| `webfetch` | http | `url` | | text | | :48 |
| `glob` | fs_read | `path` | `.` | text | `("pattern",)` | :49, :72 |
| `grep` | fs_read | `path` | `.` | text | | :50, :72 |
| `lsp` | fs_read | `filePath` | | text | | :51 |
| `run_commands` | shell | `commands[]` | | command | | :91, :107 |
| `read_files` | fs_read | `files[].path` | | text | | :92 |
| `editor` | fs_write | `path` | | text | | :93 |
| `fetch_web_content` | http | `requests[].url` | | text | | :95 |
| `execute_command` | shell | `command` | | text | | :131 |
| `write_to_file` | fs_write | `absolutePath\|path` | | text | | :132-133 |
| `replace_in_file` | fs_write | `absolutePath\|path` | | text | | :134-135 |
| `read_file` | fs_read | `path` | | text | | :136 |
| `list_files` | fs_read | `path` | | text | | :137 |
| `search_files` | fs_read | `path` | | text | | :138 |
| `browser_action` | http | `url` | | text | | :139, :166 (required, see shape 5) |
| `query` | sql | `sql` | | text | | :193 |
| `execute_sql` | sql | `query` | | text | | :194 |
| `apply_migration` | sql | `query` | | text | | :195 |
| `run_sql` | sql | `query` | | text | | :196 |

The `none` rows (`websearch`, `task`, `todowrite`, `question`, `skill`, `plan_exit`, `invalid`, `search_codebase`, `skills`, `ask_question`, `submit_and_exit`, `use_mcp_tool`, `access_mcp_resource`) are **not** mapped, so they are `Unknown()` unless `opaque_tools` names them. Whether the built-in policy's `opaque_tools` lists any is STORY-006's decision (the built-in policy), not this story's. The test asserts they map to `Unknown()` with an empty `opaque_tools` and to `Opaque(d)` when named.

`apply_migration` is not in the PRD's three generic SQL names, but it is a `SOURCES.md` table row, and AC2 says "each built-in mapping recorded in SOURCES.md". Mapping it gives Supabase's DDL tool `sql.ddl` (grantable via `action:sql:ddl`) instead of `tool.unknown`. Both deny by default. Flagged as a small deviation, so the orchestrator can drop it.

### Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/action_adapters.py` | CREATE | `ToolCall`, re-exported `Operation`/`OperationKind`, `TargetFormat`, `ToolMapping`, `ToolMappingError`, the four result types, `MappingResult`, `BUILT_IN_TOOLS`, `map_tool_call` and private helpers (`_parse_target`, `_resolve`, `_patch_paths`, `_reject_duplicate_keys`) |
| `tests/test_action_adapters.py` | CREATE | AC1-AC5, parametrized over the `SOURCES.md` tables |

No other file changes. `app/config.py` (`ACTION_MAX_ARGUMENT_CHARACTERS`) is STORY-005's. The built-in policy is STORY-006's.

### Dependency order

Task 1 (types, grammar, `ToolMapping` validation) -> Task 2 (`map_tool_call` + patch extractor) -> Task 3 (`BUILT_IN_TOOLS`) -> Task 4 (tests).

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Module skeleton, types, target grammar, `ToolMapping` validation

- **File**: `app/services/action_adapters.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring in the style of `action_classifiers/__init__.py:1-21`. State what it does (PRD-016 Sections 4, 6.2, F1), the one-way import edge (`action_adapters -> action_classifiers`, STORY-003 decision), that `Operation` is re-exported and not redefined, the purity rule (Section 6.12, the only `app` import being `action_classifiers`), the fail-closed rule ("zero operations is never returned; every ambiguity is `Malformed`"), and pointers to `tests/corpora/actions/SOURCES.md` and threat-model findings S1/S2/S4/S6/S7/S8.
  - Imports: `json`, `re`, `shlex`, `dataclasses.dataclass`, `functools.lru_cache`, `types.MappingProxyType`, `typing` (`Literal`, `Mapping`, `Optional`, `Union`, `get_args`). From `app.services.action_classifiers`: `Decision`, `OPERATION_KINDS`, `Operation`, `OperationKind`. No `os`, `pathlib`, `io` or `app.config`.
  - `ToolCall`, `TargetFormat`/`TARGET_FORMATS`, `ToolMappingError(ValueError)` with a docstring mirroring `pattern_detector.py:36-44` ("does not name a file or a tool: STORY-006/007 re-raise `ActionConfigError` with the node attached"), `ToolMapping` with `__post_init__`, `_parse_target(expr) -> tuple[tuple[tuple[str, bool], ...], ...]` (alternatives -> segments -> (key, is_array)), `lru_cache`d.
  - `Operations`, `Opaque`, `Unknown`, `Malformed`, `MappingResult`, `__all__`.
- **Mirror**: `app/services/action_classifiers/__init__.py:80-119`; `app/services/openrouter_client.py:61-66`; `app/services/pattern_detector.py:105-108`
- **Validate**: `.venv/Scripts/python -c "import app.services.action_adapters as a; print(a.ToolMapping('shell','command'))"`

### Task 2: `map_tool_call` and the patch extractor

- **File**: `app/services/action_adapters.py`
- **Action**: UPDATE (same new file)
- **Implement**: the eight steps in *Design / `map_tool_call` algorithm*. Private `_MalformedArguments(Exception)` is caught only at the `map_tool_call` boundary. `_reject_duplicate_keys(pairs)` raises `_MalformedArguments` on a repeated key (any nesting level). `_patch_paths(text) -> list[str]`. Each helper's docstring cites the S-finding it answers.
- **Mirror**: comment density and PRD citations of `action_classifiers/__init__.py:38-46`
- **Validate**: `.venv/Scripts/python -c "from app.services.action_adapters import *; print(map_tool_call(ToolCall('c1','bash','{\"command\": \"ls\"}'), {'bash': ToolMapping('shell','command')}, {}, 100000))"`

### Task 3: `BUILT_IN_TOOLS`

- **File**: `app/services/action_adapters.py`
- **Action**: UPDATE
- **Implement**: the 24 entries of the table above as `MappingProxyType({...})`, grouped by client with a comment header per group naming the version and commit from `SOURCES.md` (OpenCode v1.19.5 `810c0eba`, Cline 4.x v4.1.26 `a459f1d0`, Cline 3.x v3.89.2 `e1bdeeff`, SQL servers). A comment above each non-obvious entry: `apply_patch` shared name and S1; `glob` S7/S8; `grep` S8 and S9 deferred to STORY-013; `run_commands` S4 and S2 (aliases not read); `write_to_file`/`replace_in_file` per-variant spellings; `browser_action` required `url`; the SQL names arrive prefixed through both clients (S6), so these match only an unprefixed caller or a deployment's own `tools:`; `apply_migration` not in the PRD's list. A closing comment says this is **data** that STORY-006 places in the built-in policy (PRD F1 "data in `action_config`, not code") and that `ToolMapping.__post_init__` already validated every entry at import.
- **Validate**: `.venv/Scripts/python -c "from app.services.action_adapters import BUILT_IN_TOOLS as t; print(len(t))"` prints `24`

### Task 4: `tests/test_action_adapters.py`

- **File**: `tests/test_action_adapters.py`
- **Action**: CREATE
- **Implement** (module docstring: PRD-016 Sections 4, 6.2, F1; STORY-004; says `SOURCES.md` is read on purpose (`SOURCES.md:7-10`) while samples and expectations are hardcoded):
  - **SOURCES.md parser** `_sources_rows()`: reads `tests/corpora/actions/SOURCES.md` (UTF-8). For every table whose header row starts `| Client | Tool | Operation kind | Target key |`, it yields `(client, tool, kind, key, multi)` with backticks stripped, skipping the `|---|` separator row. A sanity test asserts 41 rows (16 OpenCode, 9 Cline 4.x, 12 Cline 3.x, 4 SQL), so a silently broken parser cannot pass vacuously.
  - **AC1** `test_bash_ls_maps_to_one_shell_operation`: the exact expression of the AC with `BUILT_IN_TOOLS`, `{}`, `100_000`.
  - **AC2**:
    - `test_every_sources_row_is_mapped_as_recorded[<client>-<tool>-<key>]`, parametrized over `_sources_rows()`. For `kind == "none"`: the tool is not in `BUILT_IN_TOOLS`, and `map_tool_call(...)` is `Unknown()`. Otherwise: `BUILT_IN_TOOLS[tool].kind == kind`. The row's key, with `?` and ` (in patch text)` stripped, is one of the mapping's `target` alternatives. `?` holds iff `default == "."`, except for the one named exception `_OPTIONAL_KEPT_REQUIRED = {"browser_action"}` (shape 5: `url?` is recorded optional but kept required, and the exception's comment says why). `(in patch text)` holds iff `format == "patch"`. Multi-target `yes` holds iff an alternative contains `[]` or `format == "patch"`.
    - `_REALISTIC: dict[tuple[str, str, str], tuple[str, tuple[str, ...]]]`, keyed by `(client, tool, key)`, value `(arguments_json, expected_targets)`. Realistic objects are copied from each schema's sibling keys. Examples: `run_commands` `{"commands": ["npm test", {"command": "git", "args": ["commit", "-m", "fix: a; b"]}]}` gives `("npm test", "git commit -m 'fix: a; b'")`. `read_files` with two files gives two ops. `apply_patch` (OpenCode, `patchText`) has Add + Update + Move to + Delete and gives 4 `fs_write` in header order. `write_to_file` `absolutePath` and `path` rows each map. `glob` `{"pattern": "**/*.ts"}` gives `(".", "**/*.ts")`. `browser_action` `{"action": "launch", "url": "https://example.com"}` maps. `query` `{"sql": "SELECT 1"}` maps. `test_every_mapped_sources_row_has_a_realistic_sample` asserts every non-`none` row has a `_REALISTIC` entry, so a new SOURCES row fails until a sample is added. `test_realistic_call_yields_documented_kind_and_targets[...]` asserts `Operations` with the expected `(kind, target, source_tool)` tuples.
    - `test_built_in_tools_are_exactly_the_sources_rows`: `set(BUILT_IN_TOOLS) == {tool for rows with kind != "none"}`, so no unprovenanced mapping exists.
    - Shape tests: `test_apply_patch_names_one_fs_write_per_header` (multi-file, CRLF, leading whitespace), `test_patch_with_no_header_is_malformed`, `test_patch_header_with_empty_path_is_malformed`, `test_both_aliases_present_are_both_classified` (`write_to_file` with `path` and `absolutePath` gives 2 ops), `test_empty_array_is_malformed_not_zero_operations` (`commands: []`, `files: []`), `test_argv_element_round_trips_through_shlex` (`shlex.split(target) == [command, *args]` for args holding `;`, `$(x)`, spaces and quotes), `test_argv_element_with_non_string_args_is_malformed`, `test_optional_target_defaults_to_dot` (`glob`/`grep` without `path`), `test_optional_target_present_but_null_is_malformed`, `test_glob_pattern_is_a_second_operation` (`../../**/.env*`), `test_browser_action_without_url_is_malformed`, `test_cline_4_lenient_aliases_are_malformed` (parametrized: `{"cmd": "ls"}`, `{"command": "ls"}` for `run_commands`; `{"file_paths": ["a"]}`, `{"files": [{"filePath": "a"}]}`, `{"files": ["a"]}` for `read_files`), `test_prefixed_mcp_names_are_unknown` (`postgres_query`, `supabase__execute_sql`, `abc0mcp0query`), `test_path_with_line_break_is_malformed` (an `fs_write` text mapping on a patch string, which is the PRD 6.6 sample's `apply_patch` without `format`), `test_shell_and_sql_targets_keep_newlines`, `test_empty_target_is_malformed`.
  - **AC3** `test_malformed_arguments[...]`, parametrized: `"not json"`, `"[]"`, `"{}"`, `'{"command": 3}'`, plus `'"ls"'`, `"null"`, `'{"command": null}'`, `'{"command": "ls", "command": "rm -rf /"}'` (duplicate key), and `"[" * 100_000` with the cap at 200_000 (`RecursionError` caught). Each gives `isinstance(result, Malformed)` and a non-empty `detail`. `test_detail_never_echoes_argument_values` checks that the detail strings of these cases contain none of the argument values (T11). `test_over_length_is_malformed_without_parsing`: `monkeypatch.setattr(json, "loads", _boom)` (raises `AssertionError`), `arguments = '{"command": "' + "a" * 50 + '"}'`, cap 10, gives `Malformed`. A control case with the cap at 1000 shows `_boom` really is reached, which proves the patch is live (the call raises the `AssertionError`). The boundary `len == cap` is accepted and `cap + 1` is refused.
  - **AC4** `test_unmapped_name_is_unknown` (`"frobnicate"`, case variant `"Bash"`), `test_opaque_tool_returns_configured_decision[allow/flag/deny]` (`opaque_tools={"todowrite": d}` gives `Opaque(d)`, even with non-JSON and over-length arguments, since PRD 6.4 says its arguments are not read), `test_mapped_name_wins_over_opaque` (a name in both is classified).
  - **ToolMapping validation** `test_tool_mapping_rejects_bad_definitions[...]`: unknown kind (`"none"`, `"exec"`, whose message lists `OPERATION_KINDS`), unknown format, `""`, `"a||b"`, `"a..b"`, `"a[]b"`, `"path?"`, `default=""`, `default` with `format="patch"`, `default` with an array target, and an `extra_targets` bad expression. Each raises `ToolMappingError`. `test_built_in_tools_is_read_only` (`MappingProxyType`: item assignment raises `TypeError`). `test_tool_call_is_the_frozen_dataclass_of_section_6_2` (fields `("id","name","arguments")`, frozen). `test_operation_is_re_exported_not_redefined` (`action_adapters.Operation is action_classifiers.Operation`, same for `OperationKind`).
  - **Never raises** `test_map_tool_call_never_raises[...]`: a parametrized list of hostile `arguments` (deep nesting, huge ints `"{\"command\": " + "9"*5000 + "}"`, lone surrogate escapes `"\\ud800"`, `NaN`, nested arrays in `commands`, dict as patch text) against every `BUILT_IN_TOOLS` name. Every result is one of the four types.
  - **AC5** `test_action_adapters_stays_pure` (docstring cites PRD-016 Section 6.12): source inspection as in `tests/test_pattern_matching.py:303-323`, where `settings` is not in vars and `open(`, `Path(` and `os.` are absent from the source, and the `app` import targets are exactly `{"app.services.action_classifiers"}`. Also `test_importing_action_adapters_loads_no_settings`: `subprocess.run([sys.executable, "-c", "import sys, app.services.action_adapters; print(sorted(m for m in sys.modules if m == 'app' or m.startswith('app.')))"], cwd=<repo root>, capture_output=True, text=True, check=True)`, asserting the printed list is exactly `['app', 'app.services', 'app.services.action_adapters', 'app.services.action_classifiers']`. That proves no `app.config` (settings) and no other app module is imported.
- **Mirror**: `tests/test_action_vocabulary.py:1-30, 125-153`; `tests/test_pattern_corpus.py:77-103`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_adapters.py -q -p no:cacheprovider`

---

## End-to-End Tests

No route, UI or startup change: nothing calls `map_tool_call` until STORY-014, and nothing in the request path until PRD-017. The implementer runs:

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` (backend import still clean)
- [ ] `chat_ui/` is not touched, so no chat import check is needed.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest \
  tests/test_action_adapters.py \
  tests/test_action_vocabulary.py \
  tests/test_untouched_app.py \
  -q -p no:cacheprovider
```

Why this set (kept narrow, per the brief): `test_action_adapters.py` is the story's own. `test_action_vocabulary.py` guards the vocabulary this module imports (unchanged, but it is the one module depended on). `test_untouched_app.py` runs because a file under `app/` is added. No pre-existing module is modified, so no other existing test file exercises changed behaviour. No test is renamed or removed, so no `_DELIBERATELY_SUPERSEDED_TESTS` entry is needed. Full suite: deferred to orchestrator (user decision).

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| **Downstream contract for STORY-006/007.** STORY-007's story text says "inside a tool mapping both `kind` and `target` are required". This plan adds three **optional** fields (`default`, `format`, `extra_targets`) | Optional fields keep `{kind, target}` valid. STORY-007's YAML parser must accept the three extra keys and construct `ToolMapping(...)`, wrapping `ToolMappingError` in `ActionConfigError` with the file and `tools.<name>` node (the `PatternCompileError` seam). Recorded here for the orchestrator to carry into STORY-006/007 |
| **PRD 6.6 sample's `apply_patch: { kind: fs_write, target: patchText }` has no `format: patch`.** Loaded as written, the whole patch would be one `fs_write` "path" | Defense in depth in this story: an `fs_*`/`http` target containing a line break is `Malformed` (deny), so the sample fails closed rather than open (`test_path_with_line_break_is_malformed`). **The orchestrator should have the PRD 6.6 sample and `examples/action_policy.yaml` (STORY-020) say `format: patch`**, and STORY-007 could reject `target: patchText`/`input` without it. Not edited here (PRD/doc changes are out of scope for a plan) |
| Cline 4.x lenient aliases denied (S2) | Fail closed and documented in the `BUILT_IN_TOOLS` comment and the test. The grammar lets a deployment add them. Over-blocking is Risk 2's, and the README (STORY-020) should name it |
| `browser_action` non-`launch` actions are denied as `tool.malformed` | Fail closed. Cline 3.x is legacy. Documented. Alternative (exclude it so it is `tool.unknown`) is equivalent in effect. Kept mapped so `launch` URLs reach the network classifier |
| Patch header over-matching (a context line ` *** Add File: x` inside a hunk) | Over-matching yields an extra `fs_write`, so it can only add a deny, never an allow. Accepted |
| `extra_targets` on `glob` makes a plain `glob` two `fs_read`s | Reads are `allow` unless they hit a secret glob, so there is no over-blocking for ordinary patterns. A secret enumeration via `pattern` becomes classifiable (S7), and how STORY-013 matches globs against a glob target is its decision |
| `shlex.join` for argv on Windows Cline | The quoted line is classified by the POSIX classifier, which recovers the exact argv. The executor runs argv with no shell, so the classification describes what runs |
| `apply_migration` beyond the PRD's three SQL names | It is a `SOURCES.md` row (AC2) and both outcomes deny by default. The orchestrator can drop it with one line and one test-row exclusion |
| Built-in `opaque_tools` for the `none` tools (`todowrite`, `question`, ...) | Out of scope: `opaque_tools` is a parameter here. STORY-006 decides the built-in list. Until then every `none` tool is `tool.unknown` (deny), which would deny OpenCode's `todowrite`. Flagged for STORY-006 |
| The SOURCES.md parser breaks on a table edit | Header-match parsing plus a row-count sanity assert (41). A changed count fails loudly and is updated with the survey |

---

## Acceptance Criteria

(Copied from story `STORY-004`)

- [ ] Given `ToolCall(id="c1", name="bash", arguments='{"command": "ls"}')` and the built-in mappings, when `map_tool_call` runs, then it returns `Operations((Operation(kind="shell", target="ls", source_tool="bash"),))`.
- [ ] Given each built-in mapping recorded in `SOURCES.md` (STORY-001), when a call with a realistic argument object is mapped, then it yields the documented kind and target; a tool STORY-001 found to name several paths yields one `fs_write` per path.
- [ ] Given `arguments` equal to `"not json"`, `"[]"`, `"{}"` (target key missing), `'{"command": 3}'` (non-string target), or a string longer than the `max_argument_characters` argument, when mapped, then the result is `Malformed(detail)`, and for the over-length case `json.loads` is never called.
- [ ] Given a tool name in no mapping, when mapped, then the result is `Unknown()`; given the name in the `opaque_tools` mapping passed in, then `Opaque(decision)` with the configured decision.
- [ ] Given the module, when imported, then it imports no `settings` and performs no I/O (asserted with the import-graph test pattern used for `pattern_detector`).
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns (pure-module docstring, `Literal` + `get_args`, frozen dataclasses, two-exception seam, purity test)

| AC | Covered by |
|----|-----------|
| AC1 | Tasks 2-3; `test_bash_ls_maps_to_one_shell_operation` |
| AC2 | Task 3; `test_every_sources_row_is_mapped_as_recorded`, `test_realistic_call_yields_documented_kind_and_targets`, `test_every_mapped_sources_row_has_a_realistic_sample`, `test_built_in_tools_are_exactly_the_sources_rows`, `test_apply_patch_names_one_fs_write_per_header` |
| AC3 | Task 2; `test_malformed_arguments`, `test_over_length_is_malformed_without_parsing` |
| AC4 | Task 2; `test_unmapped_name_is_unknown`, `test_opaque_tool_returns_configured_decision` |
| AC5 | Task 1; `test_action_adapters_stays_pure`, `test_importing_action_adapters_loads_no_settings` |

---

## Addendum: orchestrator decisions applied at implementation (2026-11-15)

- **Shape 7 changed (decision 3).** The built-ins now read Cline 4.x's documented lenient aliases wherever the grammar expresses them: `run_commands` = `commands[]|commands|cmd`; `read_files` = `files[].path|files[].file_path|files[].filePath|files.path|files.file_path|files.filePath|file_paths[]|file_paths|paths[]|paths`. Still `Malformed`: top-level `{command, args?}` / `{command}` for `run_commands`, `files[]` of strings, `files` as a string, `paths` as an object, bare strings/arrays.
- **Alias resolution changed (decision 3).** Two spellings of one key present at the same level (top level or per array element) is `Malformed("more than one spelling of the target is present: ...")`, replacing "read every present spelling". This applies to every `|` expression, including `absolutePath|path` and `patchText|input`; `test_both_aliases_present_are_both_classified` became `test_two_spellings_of_one_key_are_malformed`.
- **Grammar refinement.** Alternatives resolve level by level, so per-element aliases work (`files[].path|files[].filePath` chooses per element). The same key may be both an array and a scalar (`commands[]|commands`), picked by the value's type. `ToolMapping` refuses overlapping alternatives (`a|a`, `a|a.b`, `files[]|files[].path`) as undecidable.
- Decisions 1, 2, 4, 5, 6 and 7 accepted as planned.
