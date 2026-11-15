---
story: STORY-003
prd: PRD-016
slug: rule-vocabulary-and-action-permissions
title: Rule ids, operation kinds, the six action permissions and authz.holds()
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-016-action-policy-rules        # all stories commit here, no per-story branch
created: 2026-11-15
---

# Plan: Rule ids, operation kinds, the six action permissions and authz.holds()

## Summary

Two small, pure additions that every later PRD-016 story names. First, `app/services/authz.py` gains the six `action:*` permission constants (PRD Section 6.7), an `ACTION_PERMISSIONS` frozenset, the six folded into `_KNOWN_PERMISSIONS` (so `RBAC_ROLES_FILE` can grant them through the existing unknown-permission check, F9), and `holds(identity, permission) -> bool`, a matrix lookup that ignores `RBAC_ENABLED` (D7). No built-in role gains any of them (D6); `authorize()`, `authorize_model()` and `load()` are not edited. Second, a new package `app/services/action_classifiers/` whose `__init__.py` holds the closed vocabulary: `RuleId` (the 25 ids of Section 6.3), `OperationKind`, `Decision`, the frozen `Operation` and `Classification` dataclasses (Section 6.2), and `NON_GRANTABLE_RULES` (the ten of T5). It imports nothing from `app`. Tests: extend `tests/test_authz.py`; new `tests/test_action_vocabulary.py`.

## User Story

As a platform operator
I want action permissions to be ordinary RBAC permissions that `RBAC_ROLES_FILE` can grant, checked without the `RBAC_ENABLED=false` escape hatch
So that one file says which roles may do what, and turning RBAC off never opens every action

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-003-rule-vocabulary-and-action-permissions.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md`: Section 4 *RBAC* (lines 79-82), 6.2 (lines 184-220), 6.3 (lines 222-252), 6.7 (lines 328-353), 6.11 (lines 425, 431), 6.12 (line 474), 9.2 T4/T5 (lines 546-547), 15 D5/D6/D7 (lines 728-730)
- STORY-001 outputs, as far as they bear on this story:
  - `.agents/spikes/PRD-016-action-policy-rules/threat-model.md:26-27` maps T4 and T5 to STORY-003; `:41` says T4's proof is a STORY-003/STORY-014 unit test (the corpus runs with RBAC on, so it cannot prove it).
  - `threat-model.md:49`: Section 6.3 defines `tool.malformed` only as bad arguments / over-length, but F7 also produces it when a classifier raises (T9). "STORY-003's `RuleId` docstring or STORY-014 should state the extra trigger." This plan puts it in the `RuleId` docstring (Task 3).
  - `tests/corpora/actions/SOURCES.md:19-21` uses a sixth table value `none` for "Operation kind". It is a survey label meaning "no classified operation; STORY-004 decides `tool.unknown` vs `opaque_tools`", **not** an `OperationKind`. `OperationKind` stays the five of Section 6.2 and the story AC. Noted in the `OperationKind` comment so STORY-004 does not widen it.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | `app/services/authz.py` (constants + one new function), new package `app/services/action_classifiers/`, tests |
| Story | STORY-003 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI aesthetics; its SKILL.md description is visual design for new UI). This story has no UI; story frontmatter `skills: []` agrees. | none |

---

## Verified invariants (against the PRD text, not the orchestrator summary)

All of the orchestrator's invariants match the PRD.

- **25 rule ids** (Section 6.3 table, lines 226-250): SQL 6 (`sql.read`, `sql.write`, `sql.unscoped_write`, `sql.ddl`, `sql.dcl`, `sql.unparsed`), Shell 8 (`shell.allowlisted`, `shell.unlisted`, `shell.destructive`, `shell.pipe_to_interpreter`, `shell.inline_interpreter`, `shell.package_install`, `shell.service_control`, `shell.unclassifiable`), Filesystem 4 (`fs.read`, `fs.write_in_workspace`, `fs.write_outside_workspace`, `fs.write_protected`), Network 3 (`net.allowlisted`, `net.unlisted`, `net.unparsed`), Secret 1 (`secret.read`), Tool 3 (`tool.unknown`, `tool.opaque`, `tool.malformed`). 6+8+4+3+1+3 = 25.
- **10 non-grantable** (T5, line 547): `sql.unscoped_write`, `sql.dcl`, `sql.unparsed`, `shell.destructive`, `shell.pipe_to_interpreter`, `shell.unclassifiable`, `fs.write_protected`, `net.unparsed`, `tool.unknown`, `tool.malformed`. Cross-check against 6.3: these are exactly the rows with default `deny` and grant `—`. The other six `—` rows (`sql.read`, `shell.allowlisted`, `fs.read`, `fs.write_in_workspace`, `net.allowlisted`, `tool.opaque`) default to `allow` / per-entry, so there is nothing to lift and they are not in the set. D5's four "unclassifiable" rules (`shell.unclassifiable`, `sql.unparsed`, `net.unparsed`, `tool.malformed`) are a subset.
- **Six permissions** (Section 6.7, lines 332-337): `action:sql:write`, `action:sql:ddl`, `action:shell:exec`, `action:fs:write`, `action:net:egress`, `action:secret:read`. Every one is the grant of at least one 6.3 rule (`sql.write`; `sql.ddl`; `shell.unlisted`/`inline_interpreter`/`package_install`/`service_control`; `fs.write_outside_workspace`; `net.unlisted`; `secret.read`), and 6.3 names no other grant.
- **`holds()` ignores `RBAC_ENABLED`** (D7, line 730; 6.7 lines 341-344 and 351).
- **No built-in role holds an action permission, `admin` included** (D6, line 729; 6.7 line 353).

---

## Patterns to Follow

### Permission constants and the closed set
```python
# SOURCE: app/services/authz.py:8-22
# Permission constants (PRD-005 Section 7). No caller uses a string literal
# for a permission name -- always one of these.
PERMISSION_QUERY_SUBMIT = "query:submit"
...
_KNOWN_PERMISSIONS = {
    PERMISSION_QUERY_SUBMIT,
    ...
}
```

### Deny-by-default matrix lookup (the body `holds()` mirrors, minus the bypass)
```python
# SOURCE: app/services/authz.py:126-136
def authorize(identity: Identity, permission: str) -> None:
    """Deny-by-default authorization check. ... The
    RBAC_ENABLED=false bypass is the one explicit exception (PRD-005
    Section 9's documented escape hatch)."""
    if not settings.RBAC_ENABLED:
        return

    role_permissions = ROLE_PERMISSIONS.get(identity.role)
    if role_permissions is None or permission not in role_permissions:
        raise PermissionDenied(permission)
```
`holds()` must read the module global `ROLE_PERMISSIONS` at call time (as `authorize()` does), because `load()` rebinds it (`authz.py:73`, `:97`).

### Error handling (unchanged; AC3 relies on it as is)
```python
# SOURCE: app/services/authz.py:90-95
granted = {permission for permissions in matrix.values() for permission in permissions}
unknown = sorted(granted - _KNOWN_PERMISSIONS)
if unknown:
    raise AuthzConfigError(
        f"RBAC_ROLES_FILE '{path_str}' grants unrecognized permission(s): {', '.join(unknown)}"
    )
```
The message names the file and the permission, so `action:sql:writ` is reported verbatim with no change to `load()`.

### Closed `Literal` vocabularies and their tuple form
```python
# SOURCE: app/services/pattern_config.py:39, 86-94
from typing import Literal, Mapping, get_args
_ROLES = get_args(Role)
#: What a profile does with a hit in a role it inspects: ...
Action = Literal["block", "flag"]
```
```python
# SOURCE: app/models/messages.py:12-18
Role = Literal["system", "user", "assistant", "tool"]
_ROLES = frozenset(get_args(Role))
```

### Frozen dataclasses with `#:` field comments and PRD-citing docstrings
```python
# SOURCE: app/services/pattern_config.py:97-115
@dataclass(frozen=True)
class PatternList:
    """One named list of patterns sharing a match mode and a scope (PRD-011 Section 6.2).
    ...
    """
    name: str
    match: Literal["word", "regex"]
    ...
    #: Built at load, never at request time (PRD-011 Section 6.2).
    compiled: tuple[re.Pattern, ...]
```

### Pure-module docstring and the purity test
- Module docstring that states purity and where I/O lives instead: `app/services/pattern_detector.py:1-27` ("Pure on purpose: no I/O, no settings, no pydantic, no `app` import ...").
- Purity assertion: `tests/test_pattern_matching.py:303-323` (`test_pattern_detector_stays_a_pure_module`: `"settings" not in vars(module)`, no `open(` / `Path(` in source, no `from app` / `import app.` lines).

### Tests
```python
# SOURCE: tests/test_authz.py:1-4, 11-27 -- env defaults before import, module alias + named imports
# SOURCE: tests/test_authz.py:112-116 -- RBAC off via monkeypatch.setattr(settings, "RBAC_ENABLED", False)
# SOURCE: tests/test_authz.py:122-126 -- _reset_role_permissions fixture restores the rebound global
# SOURCE: tests/test_authz.py:143-150 -- write roles.json to tmp_path, monkeypatch RBAC_ROLES_FILE, load()
# SOURCE: tests/test_authz.py:187-195 -- unknown permission: AuthzConfigError, name in str(exc)
```
Section headers in the test file are `# --- STORY-NNN: ... ---` comments (`tests/test_authz.py:119`, `:219`); the new block uses `# --- PRD-016 STORY-003: action permissions and holds() ---`.

---

## Design

### Placement of `Operation` (story Technical Notes give a choice)

`Classification.operation` is `Optional[Operation]`. The story allows a forward reference to STORY-004's `Operation` or moving `Operation` here and re-exporting it from `action_adapters`. **Decision: define `Operation` (and `OperationKind`) in `action_classifiers/__init__.py`.** Reason: `action_adapters` (STORY-004) needs `OperationKind` and `Operation`, and every classifier (STORY-008..013) takes an `Operation`. If `Operation` lived in `action_adapters`, `action_classifiers` would import `action_adapters`, which imports `action_classifiers` for `OperationKind`: a cycle. With both here, the graph is one-way, `action_adapters -> action_classifiers`, and the classifiers never import the adapters. A forward reference string to a module that does not exist yet would also leave `typing.get_type_hints(Classification)` broken until STORY-004. STORY-004 then does `from app.services.action_classifiers import Operation, OperationKind` and re-exports them; its AC `Operation(kind="shell", target="ls", source_tool="bash")` holds unchanged. `ToolCall` stays in STORY-004 (no classifier needs it).

### Contents of `action_classifiers/__init__.py`

- `OperationKind = Literal["shell", "sql", "fs_write", "fs_read", "http"]`
- `Decision = Literal["allow", "flag", "deny"]`
- `RuleId = Literal[...25 ids, in Section 6.3 table order...]`
- `RULE_IDS: tuple[str, ...] = get_args(RuleId)`, `OPERATION_KINDS = get_args(OperationKind)`, `DECISIONS = get_args(Decision)`: the tuple forms STORY-006/007's validator enumerates in its error messages (Section 6.12, "closed vocabularies validated explicitly"; mirrors `pattern_config._ROLES = get_args(Role)`). Public, because they cross module boundaries. Order is significant only for readable error messages.
- `NON_GRANTABLE_RULES: frozenset[RuleId]`: the ten of T5.
- `@dataclass(frozen=True) class Operation: kind: OperationKind; target: str; source_tool: str`
- `@dataclass(frozen=True) class Classification: rule: RuleId; operation: Optional[Operation]; detail: str`

Not in this story: rule defaults and grants (STORY-006's built-in policy), `ToolCall` / mappings (STORY-004), `ActionDecision` and reason templates (STORY-014), the "walk every classifier's outputs" test (each classifier story).

### Contents added to `authz.py`

- The six `PERMISSION_ACTION_*` constants in a new comment block after line 14, styled like lines 8-9, citing PRD-016 Section 6.7 and D6.
- `ACTION_PERMISSIONS = frozenset({...six...})`.
- `_KNOWN_PERMISSIONS` gains `*ACTION_PERMISSIONS` (stays a `set`, so `granted - _KNOWN_PERMISSIONS` at line 91 is unchanged).
- `ROLE_PERMISSIONS` is **not** edited. Its comment (lines 24-27) gains one sentence: no built-in role holds an action permission, `admin` included (PRD-016 D6).
- `holds()` placed directly after `authorize()` (after line 136, before `authorize_model()`), per the story Technical Note "beside `authorize()`".

### Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/authz.py` | UPDATE | Six constants, `ACTION_PERMISSIONS`, `_KNOWN_PERMISSIONS` widened, D6 comment on `ROLE_PERMISSIONS`, `holds()` |
| `app/services/action_classifiers/__init__.py` | CREATE | `RuleId`, `OperationKind`, `Decision`, tuple forms, `NON_GRANTABLE_RULES`, `Operation`, `Classification` |
| `tests/test_authz.py` | UPDATE | Append tests for AC1-AC4. No existing assertion changes (see Risks) |
| `tests/test_action_vocabulary.py` | CREATE | AC5 + purity |

Dependency order: Task 1 (authz) and Task 3 (package) are independent; tests follow each.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Action permission constants, `ACTION_PERMISSIONS`, `_KNOWN_PERMISSIONS`

- **File**: `app/services/authz.py`
- **Action**: UPDATE
- **Implement**:
  - After line 14, a second block:
    ```python
    # Action permissions (PRD-016 Section 6.7, D6). Each lifts one or more
    # grantable action rules from their default to `allow` for a role that
    # holds it; the action policy file names these, never a role. Granted
    # only through RBAC_ROLES_FILE -- no built-in role holds one.
    PERMISSION_ACTION_SQL_WRITE = "action:sql:write"
    PERMISSION_ACTION_SQL_DDL = "action:sql:ddl"
    PERMISSION_ACTION_SHELL_EXEC = "action:shell:exec"
    PERMISSION_ACTION_FS_WRITE = "action:fs:write"
    PERMISSION_ACTION_NET_EGRESS = "action:net:egress"
    PERMISSION_ACTION_SECRET_READ = "action:secret:read"

    # The closed vocabulary a rule's `grant` is validated against at startup
    # (PRD-016 Section 9.3, STORY-007).
    ACTION_PERMISSIONS = frozenset({ ...the six constants... })
    ```
  - `_KNOWN_PERMISSIONS` (lines 16-22): keep the five, add `*ACTION_PERMISSIONS`, with a one-line comment that this is what lets `RBAC_ROLES_FILE` grant them through the existing unknown-permission check (PRD-016 F9).
  - `ROLE_PERMISSIONS` comment (lines 24-27): append "No built-in role holds an action permission, `admin` included: an agent acting for an admin is not administering the harness (PRD-016 D6)." Do not touch the dict.
- **Mirror**: `app/services/authz.py:8-22`
- **Validate**: `.venv/Scripts/python -c "from app.services import authz; assert len(authz.ACTION_PERMISSIONS) == 6 and authz.ACTION_PERMISSIONS <= authz._KNOWN_PERMISSIONS and len(authz._KNOWN_PERMISSIONS) == 11; print('OK')"`

### Task 2: `holds()`

- **File**: `app/services/authz.py`
- **Action**: UPDATE (insert after `authorize()`, line 136)
- **Implement**:
  ```python
  def holds(identity: Identity, permission: str) -> bool:
      """Whether the identity's role holds `permission` in the loaded matrix,
      with **no** RBAC_ENABLED bypass (PRD-016 D7, Section 6.7, T4).

      Not a wrapper over authorize(): authorize() returns at once when
      RBAC_ENABLED=false (PRD-005's escape hatch for running without users).
      Reused for action grants, that hatch would hand all six action
      permissions to every caller and turn every grantable action rule into
      `allow`. This reads ROLE_PERMISSIONS and nothing else -- not settings.
      With RBAC off identities still carry a role, and that role holds what
      the matrix says, which in the built-in matrix is no action permission.

      Deny by default, as authorize(): a role absent from the matrix holds
      nothing. Returns a bool rather than raising because the caller
      (action_policy.evaluate(), STORY-014) chooses between a rule's grant and
      its default; a missing grant is not an error. authorize() is unchanged.
      """
      return permission in ROLE_PERMISSIONS.get(identity.role, ())
  ```
- **Mirror**: `app/services/authz.py:126-136`
- **Validate**: `.venv/Scripts/python -c "from app.services.authz import holds; from app.services.identity import Identity; assert holds(Identity('u','admin'),'action:sql:write') is False; print('OK')"`

### Task 3: The vocabulary package

- **File**: `app/services/action_classifiers/__init__.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring: what the package is (PRD-016 Sections 6.2, 6.3, 6.11), that this file only *names* the vocabulary and the rules' defaults and grants live in `action_config`'s built-in policy (STORY-006), why `Operation` is defined here and re-exported by `action_adapters` (the import graph is one-way, `action_adapters -> action_classifiers`), and the purity rule (Section 6.12: no I/O, no settings, no `app` import), in the voice of `pattern_detector.py:1-27`.
  - Imports: `from dataclasses import dataclass`, `from typing import Literal, Optional, get_args`. Nothing else.
  - `OperationKind` with a `#:` comment: the five kinds of Section 6.2; `SOURCES.md`'s `none` is a survey label for "no classified operation", resolved by STORY-004 to `tool.unknown` or `opaque_tools`, never a kind.
  - `Decision` with a `#:` comment: `flag` is allowed and recorded (D10); severity order `deny > flag > allow` is STORY-014's (D9).
  - `RuleId` as a `Literal` of the 25 ids, one per line, grouped by class with a short comment per class, in the 6.3 table order. Docstring/comment block above it: a closed vocabulary (Section 6.2, last paragraph: an id outside it cannot appear in a policy file or be produced by a classifier); plus the T9 note from `threat-model.md:49`: `tool.malformed` is also what `evaluate()` returns when a classifier raises (F7, T9), a trigger 6.3's "Produced when" column does not list.
  - `RULE_IDS`, `OPERATION_KINDS`, `DECISIONS` via `get_args`.
  - `NON_GRANTABLE_RULES: frozenset[RuleId]` with a comment citing T5 and Section 6.3's closing paragraph: a `grant` on any of these is refused at startup (STORY-007), their `default` can still be changed in the file. List the ten in 6.3 order.
  - `Operation` and `Classification` frozen dataclasses exactly as Section 6.2 (field order `kind, target, source_tool` and `rule, operation, detail`), with `#:` comments: `target` is the command, statement, path or URL; `operation` is `None` for `tool.unknown` / `tool.malformed`; `detail` is the matched fragment of the *call* (`DROP`, `rm -rf`, `.env`), never a configured value (T11).
- **Mirror**: `app/services/pattern_config.py:86-115`, `app/models/messages.py:16-18`, `app/services/pattern_detector.py:1-31`
- **Validate**: `.venv/Scripts/python -c "from typing import get_args; import app.services.action_classifiers as v; assert len(get_args(v.RuleId)) == 25 and len(v.NON_GRANTABLE_RULES) == 10; print('OK')"`

### Task 4: Extend `tests/test_authz.py` (AC1-AC4)

- **File**: `tests/test_authz.py`
- **Action**: UPDATE (append a new section; add the new names to the import block at lines 13-26)
- **Implement** under `# --- PRD-016 STORY-003: action permissions and holds() ---`:
  - `_ACTION_PERMISSION_VALUES` transcribed from PRD Section 6.7 (the six strings, literal, so the test checks the values and not just the names).
  - AC1 `test_action_permission_constants_match_prd_016_section_6_7`: each `PERMISSION_ACTION_*` equals its string; `ACTION_PERMISSIONS == frozenset(_ACTION_PERMISSION_VALUES)`, `isinstance(..., frozenset)`.
  - AC1 `test_known_permissions_are_the_original_five_plus_the_six`: `authz._KNOWN_PERMISSIONS == set(ALL_PERMISSIONS) | ACTION_PERMISSIONS`, length 11.
  - AC2 `@parametrize("role", ["admin", "auditor", "user"])` `test_no_built_in_role_holds_an_action_permission`: `ROLE_PERMISSIONS[role].isdisjoint(ACTION_PERMISSIONS)`; and `set(ROLE_PERMISSIONS) == {"admin", "auditor", "user"}` so a new built-in role cannot slip past the parametrization.
  - AC3 `test_load_accepts_an_action_permission_grant` (uses `_reset_role_permissions`): roles.json `{"dba": ["query:submit", "action:sql:write"]}`; `load()`; `authz.ROLE_PERMISSIONS["dba"] == {...}`; `holds(Identity("d", "dba"), PERMISSION_ACTION_SQL_WRITE) is True`.
  - AC3 `test_load_refuses_a_misspelled_action_permission`: `{"dba": ["action:sql:writ"]}` raises `AuthzConfigError`, `"action:sql:writ"` in the message, `str(roles_file)` in the message, and `authz.ROLE_PERMISSIONS` unchanged.
  - AC4, parametrized over `RBAC_ENABLED in (False, True)` so the no-bypass claim is shown for both settings (T4):
    - `test_holds_is_false_for_a_role_without_the_permission`: built-in `user` and `admin`, every action permission, `False`.
    - `test_holds_is_true_for_a_role_with_the_permission`: `monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {"dba": {PERMISSION_ACTION_SQL_WRITE}})`, `True` for `action:sql:write`, `False` for `action:sql:ddl`.
    - `test_holds_is_false_for_a_role_absent_from_the_matrix`: role `"superadmin"`, `False`.
  - D7 contrast `test_holds_does_not_inherit_authorize_rbac_off_bypass`: with `RBAC_ENABLED=False`, `authorize(Identity("u","user"), PERMISSION_ACTION_SQL_WRITE) is None` (the escape hatch, unchanged) while `holds(...) is False`. Docstring cites PRD-016 D7 and Section 6.7.
  - `test_holds_reads_the_matrix_load_installed` (`_reset_role_permissions`): after `load()` rebinds the global from a file granting `dba` `action:fs:write`, `holds` sees it. Proves `holds` reads the global at call time.
  - All new tests use `monkeypatch` for `RBAC_ENABLED` / `ROLE_PERMISSIONS` or the existing `_reset_role_permissions` fixture; none leak state.
- **Mirror**: `tests/test_authz.py:112-116`, `:122-126`, `:143-150`, `:187-195`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_authz.py -q -p no:cacheprovider`

### Task 5: `tests/test_action_vocabulary.py` (AC5)

- **File**: `tests/test_action_vocabulary.py`
- **Action**: CREATE
- **Implement** (module docstring citing PRD-016 Sections 6.2, 6.3, T5 and STORY-003):
  - `_PRD_6_3_RULE_IDS`: the 25 ids transcribed from the Section 6.3 table, in order. `_PRD_T5_NON_GRANTABLE`: the ten from T5. Hardcoded on purpose (PRD files are not read by any test in this repo, and later stories edit the PRD); the docstring names the PRD lines they came from.
  - `test_rule_id_is_exactly_the_25_ids_of_prd_section_6_3`: `get_args(RuleId) == _PRD_6_3_RULE_IDS` (order too), `len == 25`, no duplicates; `RULE_IDS == get_args(RuleId)`.
  - `test_every_rule_id_is_class_dot_name`: each id's prefix is in `{"sql", "shell", "fs", "net", "secret", "tool"}`; per-class counts 6/8/4/3/1/3.
  - `test_operation_kind_is_the_five_of_section_6_2`: `get_args(OperationKind) == ("shell", "sql", "fs_write", "fs_read", "http")`; `OPERATION_KINDS` equal.
  - `test_decision_is_allow_flag_deny`: `get_args(Decision) == ("allow", "flag", "deny")`; `DECISIONS` equal.
  - `test_non_grantable_rules_are_exactly_the_ten_of_t5`: `NON_GRANTABLE_RULES == frozenset(_PRD_T5_NON_GRANTABLE)`, `isinstance frozenset`, subset of `RULE_IDS`, and contains D5's four unclassifiable rules.
  - `test_classification_is_the_frozen_dataclass_of_section_6_2`: `dataclasses.is_dataclass`, field names `("rule", "operation", "detail")`; `Classification("tool.unknown", None, "x")` constructs; assigning `.rule` raises `dataclasses.FrozenInstanceError`; a `Classification` with an `Operation` is hashable and equal to an identical one.
  - `test_operation_is_the_frozen_dataclass_of_section_6_2`: fields `("kind", "target", "source_tool")`, frozen.
  - `test_type_hints_resolve`: `typing.get_type_hints(Classification)` succeeds and `operation` is `Optional[Operation]` (guards the "no dangling forward reference" decision).
  - `test_action_classifiers_package_stays_pure`: mirrors `tests/test_pattern_matching.py:303-323` on `inspect.getsource(app.services.action_classifiers)`: `"settings" not in vars(module)`, no `open(` / `Path(`, no `from app` / `import app.` import line. Docstring cites PRD-016 Section 6.12.
- **Mirror**: `tests/test_pattern_matching.py:303-323`; env-default header from `tests/test_authz.py:1-4` only if an `app.config` import ends up in the module (it should not: the package imports no settings).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_vocabulary.py -q -p no:cacheprovider`

---

## End-to-End Tests

No route, UI or startup sequence changes, so no live E2E. The end-to-end property is "a deployment's `RBAC_ROLES_FILE` granting an action permission boots": `test_load_accepts_an_action_permission_grant` covers it through `authz.load()`, the same function both lifespans call. The implementer also runs:

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` (backend import)
- [ ] `chat_ui/` is not touched, so the chat import check is not needed.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest \
  tests/test_authz.py \
  tests/test_action_vocabulary.py \
  tests/test_rbac.py \
  tests/test_main.py \
  "tests/test_query_pipeline_break_glass.py::test_ingress_break_glass_is_not_an_rbac_permission" \
  tests/test_untouched_app.py \
  -q -p no:cacheprovider
```

Why this set (kept narrow, per the brief): `test_authz.py` and `test_action_vocabulary.py` are the story's own; `test_rbac.py` parametrizes over `ROLE_PERMISSIONS` (`tests/test_rbac.py:40`, `:99-177`); `test_main.py:96-104` boots `authz.load()` in the lifespan; the break-glass test asserts a label is absent from `_KNOWN_PERMISSIONS` (`tests/test_query_pipeline_break_glass.py:181-183`), which widening the set must not break; `test_untouched_app.py` because an `app/` file changes. Full suite: deferred to orchestrator (user decision).

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| An existing test pins the matrix or the known set | Checked: `tests/test_authz.py:59-75` pins each built-in role's set; those stay true because no role gains a permission. No test asserts `len(_KNOWN_PERMISSIONS)` (grep for `_KNOWN_PERMISSIONS` in `tests/`: only `test_query_pipeline_break_glass.py:183`, which `ingress:break_glass` still passes). `tests/test_audit_characterization.py:129` holds its own copy of the five-permission matrix and is unaffected. So **no pre-existing assertion is modified** and no `_DELIBERATELY_SUPERSEDED_TESTS` entry is needed. |
| `_MATRIX_CASES` (`tests/test_authz.py:37-41`) only covers the original five | Left as is (it is PRD-005's matrix test); the new parametrized AC2/AC4 tests cover the action permissions. |
| `holds()` on a typo'd permission string silently returns `False` | Fails closed, and callers (STORY-014) pass `grant` values that STORY-007 validates against `ACTION_PERMISSIONS` at startup. Not validated inside `holds()` to keep it a lookup (Section 6.7). |
| Defining `Operation` here looks like STORY-004 work | The story's Technical Notes permit it and it is the only acyclic choice (see Design). STORY-004 must import and re-export it rather than redefine it. Flagged to the orchestrator below. |
| `SOURCES.md` uses an `Operation kind` value `none` | Not added to `OperationKind` (PRD 6.2 and AC5 say five). Documented in the `OperationKind` comment; STORY-004 resolves `none` tools. |
| `RULE_IDS` / `OPERATION_KINDS` / `DECISIONS` are not in the AC | Small, derived by `get_args`, and the form STORY-006/007 need for "closed vocabularies enumerated in error messages" (Section 6.12). If the orchestrator prefers strict AC scope, they can be dropped without affecting any AC. |

---

## Acceptance Criteria

(Copied from story `STORY-003`)

- [ ] Given `app/services/authz.py`, when imported, then it defines the six constants `PERMISSION_ACTION_SQL_WRITE` … `PERMISSION_ACTION_SECRET_READ` with the values in PRD Section 6.7, an `ACTION_PERMISSIONS` frozenset of exactly those six, and `_KNOWN_PERMISSIONS` contains the original five plus the six.
- [ ] Given the built-in `ROLE_PERMISSIONS`, when inspected, then no role (`admin`, `auditor`, `user`) holds any action permission.
- [ ] Given an `RBAC_ROLES_FILE` granting `dba` the permission `action:sql:write`, when `authz.load()` runs, then it loads; given one granting `action:sql:writ`, then it raises `AuthzConfigError` naming the permission.
- [ ] Given `holds(identity, "action:sql:write")` with `RBAC_ENABLED=false` and a role that does not hold it, when called, then it returns `False` (no bypass); with a role that holds it, then `True`; with a role absent from the matrix, then `False`.
- [ ] Given `app/services/action_classifiers/__init__.py`, when imported, then `RuleId` is a `Literal` of exactly the 25 rule ids in PRD Section 6.3, `OperationKind` is `Literal["shell", "sql", "fs_write", "fs_read", "http"]`, `Decision` is `Literal["allow", "flag", "deny"]`, `Classification` is the frozen dataclass of Section 6.2, and `NON_GRANTABLE_RULES` is exactly the ten deny rules of T5.
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns (`authz.py` comment blocks, `Literal` + `get_args`, frozen dataclasses, pure-module test)

| AC | Covered by |
|----|-----------|
| AC1 | Task 1; `test_action_permission_constants_match_prd_016_section_6_7`, `test_known_permissions_are_the_original_five_plus_the_six` |
| AC2 | Task 1 (matrix untouched); `test_no_built_in_role_holds_an_action_permission[admin/auditor/user]` |
| AC3 | Task 1 (no `load()` change needed); `test_load_accepts_an_action_permission_grant`, `test_load_refuses_a_misspelled_action_permission` |
| AC4 | Task 2; `test_holds_is_false_for_a_role_without_the_permission`, `test_holds_is_true_for_a_role_with_the_permission`, `test_holds_is_false_for_a_role_absent_from_the_matrix` (each with RBAC off and on), `test_holds_does_not_inherit_authorize_rbac_off_bypass` |
| AC5 | Task 3; `tests/test_action_vocabulary.py` (all tests) |
