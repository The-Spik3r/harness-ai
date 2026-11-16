---
story: STORY-005
prd: PRD-016
slug: action-settings-and-strict-yaml
title: Three action settings; strict_yaml with duplicate-key rejection; pattern_config adopts it
type: REFACTOR
complexity: LOW
epic_branch: epic/PRD-016-action-policy-rules
created: 2026-11-15
---

# Plan: Three action settings; strict_yaml with duplicate-key rejection; pattern_config adopts it

## Summary

Declare the three PRD-016 settings in `app/config.py` (`ACTION_POLICY_FILE`, `ACTION_MAX_ARGUMENT_CHARACTERS`, `ACTION_SQL_DIALECT`). The integer joins the shared `_validate_positive_limit` validator, and its `_POSITIVE_LIMIT_DESCRIPTIONS` entry tells the operator what to set instead of 0. Add a new pure module, `app/services/strict_yaml.py`. It holds a `yaml.SafeLoader` subclass whose `construct_mapping` rejects a key written twice in any mapping, at any depth, with a `ConstructorError` (a `yaml.YAMLError`) that names the key and both lines. `strict_yaml.safe_load(text)` is the only public entry point. `pattern_config.load()` then swaps `yaml.safe_load` for `strict_yaml.safe_load`. It keeps its `except yaml.YAMLError` arm, so a duplicate key becomes `PatternConfigError("Failed to parse PATTERNS_FILE '<path>': ... found duplicate key 'lists' ...")`, and the docstring paragraph that recorded the limit is replaced by a note citing PRD-016 D13. Nothing reads the three settings yet: `action_config` (STORY-006/007/008) and `action_policy` (STORY-014) are the consumers. `.env.example` belongs to STORY-020, and the sqlglot dialect check to STORY-008.

## User Story

As a platform operator
I want the action policy's settings validated at startup and a YAML key written twice to stop the boot
So that neither a bad value nor a silently dropped section can change what is enforced

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-005-action-settings-and-strict-yaml.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md`: Sections 4 (Configuration, lines 84-89, 105), 6.6 (Strict YAML, line 326), 9.3 (lines 557-563), 10 (line 619 signature), 14 (Risk 8, line 712), 15 (D13, line 736)

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (configuration plumbing + one shared loader; story `type: technical`) |
| Complexity | LOW |
| Systems Affected | `app/config.py`, `app/services/strict_yaml.py` (new), `app/services/pattern_config.py`, tests |
| Story | STORY-005 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI aesthetics). This story has no UI, and its frontmatter has `skills: []`. | — |

---

## Patterns to Follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| SETTINGS BLOCK | `app/config.py:256-291` | A PRD block comment opens the group and says nothing reads the fields yet. Each field has its own comment that names the consuming story. |
| POSITIVE-INT VALIDATOR | `app/config.py:19-33`, `app/config.py:482-497` | `_POSITIVE_LIMIT_DESCRIPTIONS[field]` is quoted in `"{field} must be at least 1, got {value}. It is {description}."`, and the field is added to the `@field_validator(...)` name list. The comment above the dict records which PRD added which entry. |
| "SAY WHAT INSTEAD" MESSAGE | `app/config.py:131-136` (`zero_note`: "0 does not turn the limit off; set USAGE_LIMITS_ENABLED=false for that."), `app/config.py:613-628` (`Example: V1_SSE_KEEPALIVE_SECONDS=10.`) | When a 0 looks like "off" and is not, the message says so and names the value to set. |
| YAML LOAD + ERROR | `app/services/pattern_config.py:588-596` | `read_text` -> `yaml.safe_load` -> `except yaml.YAMLError as exc: raise PatternConfigError(f"Failed to parse PATTERNS_FILE '{path}': {exc}") from exc` |
| DOCSTRING TO REPLACE | `app/services/pattern_config.py:566-569` | The "One documented limit: PyYAML resolves duplicate mapping keys silently ..." paragraph |
| SAFE-ONLY NOTE | `app/services/pattern_config.py:561-564` | The `!!python/...` refusal note. It stays and is reworded to name `strict_yaml.safe_load` (still SafeLoader underneath). |
| PURE MODULE DOCSTRING | `app/services/action_adapters.py:1-35` | The module docstring cites PRD sections and decisions, states "Pure on purpose (PRD-016 Section 6.12): no I/O, no settings ..." and names its callers by story. |
| SETTINGS TESTS | `tests/test_config.py:95-97` (`_settings(**overrides)` with `_env_file=None`), `tests/test_config.py:373-431` (defaults, parametrized `0/-1/"0"` startup errors, boundary of one), `tests/test_config.py:517-539` (message names field, value and purpose) | |
| PATTERN_CONFIG TESTS | `tests/test_pattern_config.py:61-84` (`_reset_policy` fixture, `_write(tmp_path, text)`), `tests/test_pattern_config.py:571-582` (a standalone function beside the table, asserting substrings of `str(exc_info.value)`), `tests/test_pattern_config.py:418-425` (the existing `unparseable-yaml` row asserts `["PATTERNS_FILE", "parse"]`) | |

### Naming
```python
# SOURCE: app/config.py:287-291
    # Per-message ceiling on the characters any one pattern scan runs over. A
    # longer message is truncated for matching only -- never for the upstream
    # call -- and the pipeline warns with the two lengths, never the content.
    # Consumed by STORY-008's inspect().
    PATTERN_MAX_SCAN_CHARACTERS: int = 1_000_000
```

### Error Handling
```python
# SOURCE: app/config.py:482-497
    @field_validator(
        "CONTEXT_MAX_MESSAGES",
        "CONTEXT_MAX_CHARACTERS",
        "PIPELINE_MAX_WORKERS",
        "PATTERN_MAX_SCAN_CHARACTERS",
        "PII_MAX_CHARACTERS_CODE",
    )
    @classmethod
    def _validate_positive_limit(cls, value: int, info) -> int:
        """Each of these bounds a resource that cannot be 0 or negative (PRD-010, PRD-011, PRD-012)."""
        if value < 1:
            description = _POSITIVE_LIMIT_DESCRIPTIONS[info.field_name]
            raise ValueError(
                f"{info.field_name} must be at least 1, got {value}. It is {description}."
            )
        return value
```
```python
# SOURCE: app/services/pattern_config.py:593-596
    try:
        document = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise PatternConfigError(f"Failed to parse PATTERNS_FILE '{path}': {exc}") from exc
```

### Tests
```python
# SOURCE: tests/test_config.py:517-533
@pytest.mark.parametrize("value", [0, -1, "0"])
def test_a_pattern_max_scan_characters_below_one_is_a_startup_error(value):
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, PATTERN_MAX_SCAN_CHARACTERS=value)

    message = str(exc_info.value)
    assert "PATTERN_MAX_SCAN_CHARACTERS" in message
    assert str(int(value)) in message, "the message must quote the value it rejected"
    assert "per-message ceiling" in message, "the message must say what the field bounds"
```

---

## Verified behaviour (probe run in the scratchpad against PyYAML 6.0.3, the venv's version)

The loader sketched in Task 2 was run against these inputs, and the probe file was then deleted:

| Input | strict loader | `yaml.safe_load` |
|---|---|---|
| `a: 1\na: 2\n` | `ConstructorError ... found duplicate key 'a' (first defined on line 1) ... line 2, column 1` | `{'a': 2}` |
| `x:\n  b: 1\n  b: 2\n` (nested) | `found duplicate key 'b'` ... `line 3` | `{'x': {'b': 2}}` |
| `- {c: 1, c: 2}` (flow, in a list) | `found duplicate key 'c'` | `[{'c': 2}]` |
| `base: &b {k: 1}\nd:\n  <<: *b\n  k: 2\n` (merge override) | `{'base': {'k': 1}, 'd': {'k': 2}}`, the same as safe_load | same |
| `1: a\n1.0: b\n` | duplicate (Python `1 == 1.0`, so safe_load would drop one silently) | `{1: 'b'}` |
| `!!python/object:os.system {}` | `ConstructorError could not determine a constructor for the tag ...` | same error |
| `? [1]\n: x` (unhashable key) | super's own `found unhashable key` | same error |

`str(ConstructorError)` carries both marks ("line N, column M"), so `PatternConfigError`'s `{exc}` interpolation names the key and the line with no change to `pattern_config`'s error arm.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | UPDATE | Three fields in a new PRD-016 block after `V1_SSE_KEEPALIVE_SECONDS` (line 368), the last field (see Task 1); add `ACTION_MAX_ARGUMENT_CHARACTERS` to `_POSITIVE_LIMIT_DESCRIPTIONS` and to `_validate_positive_limit`'s name list |
| `app/services/strict_yaml.py` | CREATE | `_StrictSafeLoader(yaml.SafeLoader)` with duplicate-key `construct_mapping`; `safe_load(text: str) -> Any` |
| `app/services/pattern_config.py` | UPDATE | `yaml.safe_load` -> `strict_yaml.safe_load` (line 594); keep `import yaml` for the `except yaml.YAMLError` arm; replace docstring lines 561-569 |
| `tests/test_strict_yaml.py` | CREATE | ACs 2 and 3 |
| `tests/test_config.py` | UPDATE | New PRD-016 STORY-005 block (append after the PRD-015 blocks at the file end, line 1335), the way each PRD adds its own block |
| `tests/test_pattern_config.py` | UPDATE | One new standalone test function for AC 4, with a comment citing PRD-016 D13. No existing assertion is touched. |

No `.env.example`, README, `requirements.txt` or `app/main.py` changes (STORY-020 and STORY-007).

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Declare the three settings

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**:
  - Place the fields **after `V1_SSE_KEEPALIVE_SECONDS` (line 368)**, the last field. Each PRD's block is appended in PRD order (PRD-010 -> 011 -> 012 -> 013 -> 015), and STORY-020's `.env.example` field-order test will read `Settings.model_fields` order.
  - Block comment, in the style of `app/config.py:256-260` / `358-360`: `# Action policy (PRD-016 Section 9.3). Nothing reads these yet -- each field names the story that becomes its consumer.`
  - `ACTION_POLICY_FILE: str = ""`. Comment: path to the action policy YAML. Empty means the built-in policy and no file is read (the `RBAC_ROLES_FILE` / `PATTERNS_FILE` shape). Sections a file provides replace the built-in wholesale, except `rules:`, which merges per rule id (PRD-016 Section 6.6). Parsed through `strict_yaml`, so a duplicate key is a startup error (D13). Consumed by STORY-006/007's `action_config.load()`.
  - `ACTION_MAX_ARGUMENT_CHARACTERS: int = 100_000` (underscore literal, as `CONTEXT_MAX_CHARACTERS: int = 200_000` at line 250). Comment: the ceiling on a tool call's `arguments` string. A longer one is `tool.malformed` (deny) and is never `json.loads`ed (T12). It reaches `action_adapters.map_tool_call(..., max_argument_characters)` as a parameter, because the adapter is pure. Consumed by STORY-006's `action_config` and STORY-014's `action_policy.evaluate()`.
  - `ACTION_SQL_DIALECT: str = ""`. Comment: the sqlglot dialect for SQL parsing; empty is sqlglot's generic dialect. Here it is only a string. Whether sqlglot knows the name is checked in `action_config.load()` by STORY-008, where `sqlglot` is installed, the way `PATTERN_PROFILE_DEFAULT`'s membership check lives in `pattern_config.load()` (lines 268-277). Consumed by STORY-008.
  - Add `"ACTION_MAX_ARGUMENT_CHARACTERS"` to the `@field_validator(...)` list at lines 482-488, and update the docstring parenthetical to `(PRD-010, PRD-011, PRD-012, PRD-016)`.
  - Add a `_POSITIVE_LIMIT_DESCRIPTIONS` entry, and extend the comment at lines 19-23 ("... and PRD-012 the fifth" -> "..., PRD-012 the fifth and PRD-016 the sixth"). The description must also say **what to set instead** (AC 1), in the `zero_note` spirit of `app/config.py:131-136`: 0 reads like "no limit" and is not one. Suggested text, which renders as `"... It is {description}."`:
    ```python
    "ACTION_MAX_ARGUMENT_CHARACTERS": (
        "the ceiling on characters in a tool call's arguments string, over which "
        "the call is denied as tool.malformed. 0 does not remove the ceiling -- "
        "there is no unbounded value; set a positive count instead, e.g. "
        "ACTION_MAX_ARGUMENT_CHARACTERS=100000 (the default)"
    ),
    ```
    This keeps the shared validator's message format unchanged, so no existing `CONTEXT_MAX_*` / `PII_MAX_CHARACTERS_CODE` assertion is affected.
  - No validator for `ACTION_POLICY_FILE` or `ACTION_SQL_DIALECT` (story Technical Notes: "here it is only a string").
- **Mirror**: `app/config.py:242-291`, `app/config.py:19-33`, `app/config.py:482-497`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Create `strict_yaml`

- **File**: `app/services/strict_yaml.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring (PRD-016 Section 6.6, D13): it is `yaml.safe_load` plus duplicate-key rejection. Why: PyYAML keeps the last of two keys silently, so a second `lists:` or `rules:` section disappears without an error. It is the shared loader `pattern_config.load()`'s docstring asked for, used by `pattern_config` (this story) and `action_config` (STORY-007). It stays a `SafeLoader` subclass, so the `!!python/...` tags are refused exactly as `yaml.safe_load` refuses them. Pure: no settings, no I/O; the caller reads the file and maps the error to its own exception, which names the file.
  - `_MERGE_TAG = "tag:yaml.org,2002:merge"`, with a comment explaining that `<<` merge keys are skipped: overriding a merged key is YAML's documented merge semantics, not a duplicate, and `SafeConstructor.flatten_mapping` handles it, so the result stays identical to `yaml.safe_load` (AC 2's last clause).
  - `class _StrictSafeLoader(yaml.SafeLoader)` overriding `construct_mapping(self, node, deep=False)`:
    ```python
    if isinstance(node, yaml.MappingNode):
        seen: dict[Any, yaml.Mark] = {}
        for key_node, _ in node.value:
            if key_node.tag == _MERGE_TAG:
                continue
            key = self.construct_object(key_node, deep=deep)
            try:
                hash(key)
            except TypeError:
                continue  # super() raises its own "found unhashable key"
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping", node.start_mark,
                    f"found duplicate key {key!r} (first defined on line {seen[key].line + 1})",
                    key_node.start_mark,
                )
            seen[key] = key_node.start_mark
    return super().construct_mapping(node, deep=deep)
    ```
    The explicit keys are checked **before** `super()` calls `flatten_mapping`, which prepends the merged keys to `node.value`. `construct_object` caches by node, so building the key here and again in `super()` constructs it once. `!!set` also goes through `construct_mapping`, so `!!set {a, a}` is rejected too; that is acceptable, and noted in a comment.
  - `def safe_load(text: str) -> Any:` returns `yaml.load(text, Loader=_StrictSafeLoader)  # noqa: S506` (the loader is a SafeLoader subclass; add the noqa only if the repo's lint flags it). Docstring: raises `yaml.YAMLError` (a `ConstructorError`) on a duplicate key at any depth, with the key and both line numbers in the message; otherwise returns exactly what `yaml.safe_load(text)` returns.
- **Mirror**: `app/services/action_adapters.py:1-35` (docstring voice, "Pure on purpose")
- **Validate**: `.venv/Scripts/python -c "from app.services import strict_yaml; print(strict_yaml.safe_load('a: 1'))"`

### Task 3: `pattern_config` adopts it

- **File**: `app/services/pattern_config.py`
- **Action**: UPDATE
- **Implement**:
  - Add `from app.services import strict_yaml` (in the `app.services.*` import group, lines 45-49). **Keep `import yaml`** (line 41): the `except yaml.YAMLError` arm still needs it.
  - Line 594: `document = strict_yaml.safe_load(raw)`. Lines 595-596 stay unchanged, so the prefix stays `Failed to parse PATTERNS_FILE '{path}': `.
  - Docstring lines 561-564: change "`yaml.safe_load` only, which also refuses the `!!python/...` tags" to "`strict_yaml.safe_load` only -- `yaml.safe_load`'s loader underneath, which also refuses the `!!python/...` tags ...". Keep the T7 sentence.
  - Replace lines 566-569 (the "One documented limit: PyYAML resolves duplicate mapping keys silently ..." paragraph) with a D13 note, e.g.: "A mapping key written twice, at any depth, is a startup error (PRD-016 D13). PyYAML alone keeps the last one silently, so a file with `lists:` written twice used to lose one with no error. `strict_yaml` is the shared strict loader this docstring once asked for, and `action_config` uses it too. A `PATTERNS_FILE` that loaded before because of a hidden duplicate now stops the boot with the key and its line named; that is the one behaviour change PRD-016 makes to PRD-011 (Risk 8)."
- **Mirror**: `app/services/pattern_config.py:548-596`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_pattern_config.py -q -p no:cacheprovider`

### Task 4: `tests/test_strict_yaml.py`

- **File**: `tests/test_strict_yaml.py`
- **Action**: CREATE
- **Implement**: The module docstring cites PRD-016 STORY-005, Section 6.6 and D13. The module is pure, so no env setdefault is needed (it imports nothing from `app.config`). Cases:
  - `test_a_duplicate_top_level_key_is_refused_naming_the_key_and_its_line`: `"a: 1\na: 2\n"` raises `yaml.YAMLError`; the message contains `"duplicate key 'a'"` and `"line 2"` (and `"line 1"` for the first definition).
  - `test_a_nested_duplicate_key_is_refused` (parametrized): block nested (`x:\n  b: 1\n  b: 2\n`), flow mapping inside a sequence (`- {c: 1, c: 2}\n`), and deep nesting (3 levels). Each case asserts the key name.
  - `test_equal_but_differently_spelled_keys_are_duplicates`: `a: 1\n"a": 2\n`, plus `1: x\n1.0: y\n` (both collapse to one Python dict key under `safe_load`, which is the silent loss).
  - `test_without_duplicates_the_result_equals_yaml_safe_load` (parametrized): scalars, `""` (-> `None`), a bare string, nested maps and lists, the same key in two *sibling* mappings (`a: {k: 1}\nb: {k: 2}` is **not** a duplicate), anchors/aliases, a `<<` merge with an override, and the repo's real files: `examples/patterns.yaml`, read with `encoding="utf-8"`. Assert `strict_yaml.safe_load(text) == yaml.safe_load(text)`.
  - `test_python_tags_are_refused_as_safe_load_refuses_them` (parametrized `!!python/object:os.system {}`, `!!python/object/apply:os.system ["echo"]`, `!!python/name:os.system`): both `yaml.safe_load` and `strict_yaml.safe_load` raise `yaml.constructor.ConstructorError`, and the strict message contains the same "could not determine a constructor" text.
  - `test_the_error_is_a_yaml_error_so_callers_keep_their_except_arm`: `issubclass(type(exc), yaml.YAMLError)`.
  - `test_strict_yaml_stays_pure` and `test_importing_strict_yaml_loads_no_settings`: mirror `tests/test_action_adapters.py:604-640`. The source contains no `settings`, `open(`, `Path(` or `os.`; it has no `app` import at all; and a subprocess import shows only `app`, `app.services` and `app.services.strict_yaml` in `sys.modules`. Pure modules import no `settings` and do no I/O (brief).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_strict_yaml.py -q -p no:cacheprovider`

### Task 5: Settings tests

- **File**: `tests/test_config.py`
- **Action**: UPDATE (append a new block at the end of the file)
- **Implement**: Header `# --- PRD-016 STORY-005: action policy settings ---`, with a note that nothing reads them yet and that `.env.example` belongs to STORY-020 and the dialect check to STORY-008.
  - `test_action_settings_available_with_documented_defaults(monkeypatch)`: `delenv` the three vars, then `_settings(DATABASE_URL=_LOCAL_URL)` gives `""`, `100_000`, `""`.
  - `@pytest.mark.parametrize("value", [0, -1, "0"])` `test_an_action_max_argument_characters_below_one_is_a_startup_error`: the message contains `ACTION_MAX_ARGUMENT_CHARACTERS`, `str(int(value))`, `"tool.malformed"` (what it bounds) and `"ACTION_MAX_ARGUMENT_CHARACTERS=100000"` (what to set instead).
  - `test_action_max_argument_characters_accepts_the_boundary_value_of_one`.
  - `test_action_sql_dialect_is_only_a_string_here`: `_settings(..., ACTION_SQL_DIALECT="nosuchdb").ACTION_SQL_DIALECT == "nosuchdb"`, which proves no sqlglot check slipped in (the "assertion with teeth" pattern of `test_pattern_profile_default_is_not_checked_against_any_policy_here`, line 553).
  - `test_action_policy_file_is_not_read_by_settings(tmp_path)`: `ACTION_POLICY_FILE=str(tmp_path / "missing.yaml")` constructs fine.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_config.py -q -p no:cacheprovider`

### Task 6: `pattern_config` duplicate-key test

- **File**: `tests/test_pattern_config.py`
- **Action**: UPDATE (one new function, placed after `test_missing_file_raises_naming_the_path`, line 582; **not** a new `_MALFORMED_CASES` row, so the existing table, its ids and `test_every_malformed_case_names_the_file_path` stay unchanged)
- **Implement**:
  ```python
  # PRD-016 STORY-005 (D13): pattern_config now parses through strict_yaml, so a
  # key written twice -- which PyYAML used to resolve silently, last one
  # winning -- is a startup error naming the file and the key.
  def test_a_duplicate_key_raises_naming_the_file_and_the_key(tmp_path, monkeypatch, _reset_policy):
      body = _VALID_FILE + "lists:\n  other:\n    match: word\n    scope: everywhere\n    patterns: [x]\n"
      path = _write(tmp_path, body)
      monkeypatch.setattr(settings, "PATTERNS_FILE", path)
      with pytest.raises(PatternConfigError) as exc_info:
          load()
      message = str(exc_info.value)
      assert "Failed to parse PATTERNS_FILE" in message
      assert path in message
      assert "duplicate key 'lists'" in message
  ```
  Optionally parametrize a nested duplicate as well (`patterns:` twice inside one list). Also assert that the previous policy stays in force (`get_policy() is BUILT_IN_POLICY`), mirroring `test_a_failed_load_leaves_the_previous_policy_in_force`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_pattern_config.py -q -p no:cacheprovider`

### Task 7: Targeted regression

Run the following in one invocation:
`PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_strict_yaml.py tests/test_config.py tests/test_pattern_config.py tests/test_pattern_profiles.py tests/test_pattern_default_config_regression.py tests/test_untouched_app.py -q -p no:cacheprovider`
`test_pattern_profiles.py` and `test_pattern_default_config_regression.py` load real YAML through `pattern_config.load()`. `test_untouched_app.py` runs because app files change. Full suite: deferred to the orchestrator (user decision).

---

## End-to-End Tests

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` imports cleanly (Settings builds with the three new defaults).
- [ ] `examples/patterns.yaml` still loads through `pattern_config.load()` to the built-in policy (`test_examples_patterns_yaml_loads_to_the_built_in_policy`, `tests/test_pattern_config.py:757`).
- [ ] A scratch `PATTERNS_FILE` with `lists:` twice fails `load()` with the file, `'lists'` and the line in the message (Task 6).

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_strict_yaml.py tests/test_config.py tests/test_pattern_config.py tests/test_pattern_profiles.py tests/test_pattern_default_config_regression.py tests/test_untouched_app.py -q -p no:cacheprovider
```

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| A `<<` merge override is treated as a duplicate, so the result diverges from `yaml.safe_load` | Merge-tagged keys are skipped and explicit keys are checked before `flatten_mapping`. Probed: the merge override yields the same dict as `safe_load`. Covered by the equality test. |
| An existing `PATTERNS_FILE` with a hidden duplicate now fails to boot (PRD Risk 8) | Intended (D13). The message names the key and the line. The README upgrade note is STORY-020's. `examples/patterns.yaml` is asserted duplicate-free by the equality test. |
| The shared positive-limit message reads awkwardly with a multi-sentence description | The suggested text is one clause chain ending without a period (the format adds it). Alternative if review dislikes it: a dedicated `_validate_action_max_argument_characters` in the `_validate_v1_sse_keepalive_seconds` style (lines 613-628). Either satisfies AC 1. |
| `test_config.py`'s `.env.example` field-order tests | They only check their own PRD's vars, so new fields after `V1_*` do not disturb them. STORY-020 adds the `.env.example` lines. |
| An existing test or caller relies on `pattern_config` calling `yaml.safe_load` (monkeypatch) | `grep -rn "safe_load" tests/` before the change. At planning time no test patches it (only `pattern_config.py:594` calls it in `app/`). |

---

## Acceptance Criteria

(Copied from story `STORY-005`)

- [ ] Given `app/config.py`, when `Settings` is built, then `ACTION_POLICY_FILE: str = ""`, `ACTION_MAX_ARGUMENT_CHARACTERS: int = 100000` and `ACTION_SQL_DIALECT: str = ""` exist; `ACTION_MAX_ARGUMENT_CHARACTERS=0` fails validation with a message that says what to set instead. (Tasks 1, 5)
- [ ] Given `strict_yaml.safe_load("a: 1\na: 2\n")`, when called, then it raises `yaml.YAMLError` naming the duplicate key `a` and its line; nested duplicates are caught too; a document without duplicates returns exactly what `yaml.safe_load` returns. (Tasks 2, 4)
- [ ] Given a `!!python/object` tag, when loaded through `strict_yaml`, then it is refused as `yaml.safe_load` refuses it. (Tasks 2, 4)
- [ ] Given `pattern_config.load()` with a `PATTERNS_FILE` containing a duplicate key, when it runs, then it raises `PatternConfigError` naming the file and the key; every other assertion in `tests/test_pattern_config.py` is unchanged and green. (Tasks 3, 6)
- [ ] Given `pattern_config.load()`'s docstring, when read after the story, then its "PyYAML resolves duplicate mapping keys silently" paragraph is replaced by a note citing PRD-016 D13. (Task 3)
- [ ] All tasks completed
- [ ] Backend imports without error
- [ ] Follows existing patterns
