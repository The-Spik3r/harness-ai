---
story: STORY-007
prd: PRD-016
slug: action-policy-file-load-and-validation
title: "action_config, part 2: ACTION_POLICY_FILE load, per-id rule merge, wholesale sections, validation, sample file"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-016-action-policy-rules
created: 2026-11-15
---

# Plan: action_config, part 2: ACTION_POLICY_FILE load, per-id rule merge, wholesale sections, validation, sample file

## Summary

Replace STORY-006's interim fail-closed branch in `action_config.load()` with a real loader. It reads `ACTION_POLICY_FILE` as UTF-8, parses it with `strict_yaml.safe_load` (duplicate keys are refused, D13), and checks the document and each section's keys. It merges `rules:` per rule id over `_BUILT_IN_RULES` (D12). It builds every `tools:` entry through `ToolMapping(...)`, wrapping `ToolMappingError` as `ActionConfigError` with the file and the `tools: '<name>'` node. A present section replaces the built-in section wholesale, and an absent one keeps it. The result is a STORY-006 `_validate` spec. `_validate(source, spec)` gains the content checks that apply to any policy, the built-in one included (F8): absolute `workspace.roots`, `network.allow` entry syntax (exact host, `*.` wildcard host, or IP literal via `ipaddress`), and `shell.allow` entries that are empty or contain a shell operator. `_policy` is rebound only as the last statement of `load()`, so a failing file leaves the previous policy and its digest in force. A new `examples/action_policy.yaml` reproduces PRD Section 6.6, with comments on the `rules:` merge exception (Risk 7). `tests/test_action_config.py` gains one test function per Section 9.3 rule, plus the merge, wholesale, keep-previous-policy and sample-file tests.

## User Story

As a platform operator
I want to set my workspace, allowlists and rollout modes in a file that is validated at startup
So that I can configure the policy without a code change and a typo stops the boot instead of reopening anything

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-007-action-policy-file-load-and-validation.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md`: 6.5 (260-270; host/wildcard/IP entry shapes), 6.6 (272-326: the sample, the two replacement rules, "empty means empty", strict YAML), F8 (502-503), 9.2 T5/T7/T13 (547, 549, 555), 9.3 (557-566: the validation list), 11 Configuration criteria (650-655), 14 Risk 7 (709), 15 D12/D13 (732-733)
- Previous plan: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-006-action-config-loader.plan.md`, design decisions 2, 3, 4 and 8 (lines 123-129)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/services/action_config.py`, `examples/action_policy.yaml` (new), `tests/test_action_config.py` |
| Story | STORY-007 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch) |

Dependencies STORY-005 (`f7824a1`) and STORY-006 (`8648e3a`) are both `status: done`.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI aesthetics; description read). This story has no UI, and its frontmatter has `skills: []`. | — |

---

## Patterns to Follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| LOAD SHAPE | `app/services/pattern_config.py:583-613` | `global _policy`; `path = settings.X`; empty means return; `Path(path).read_text(encoding="utf-8")` under `except OSError`; `strict_yaml.safe_load` under `except yaml.YAMLError`; `isinstance(document, Mapping)` check; `_check_keys`; section parsers; `_policy = ...` as the **last** statement |
| KEY CHECKS | `app/services/pattern_config.py:320-343` | `_check_keys(path, where, body, allowed, required)`: unknown reported first (`unknown[0]`, `_allowed(allowed)`), then missing |
| MESSAGE HELPERS | `app/services/action_config.py:338-343` | `_fail(source, *parts)` -> `"<source>: a: b"`, `_allowed(values)` (already present, reuse) |
| COMPILE SEAM | `app/services/pattern_config.py:365-373` | `try: ... except PatternCompileError as exc: raise _fail(path, where, str(exc)) from exc`, the same shape for `ToolMappingError` |
| BARE-STRING SLIP | `app/services/pattern_config.py:346-351` | A bare string where a list belongs is refused by name (`extra_targets: pattern`) |
| THE VALIDATOR | `app/services/action_config.py:489-574` | `_validate_strings(source, node, values)`; `_validate` node names already in YAML-path form (`shell.allow`, `network.allow`, `workspace.roots`, `secrets.env`, `secrets.files`, `rules: '<id>'`, `tools: '<name>'`) |
| BUILT-IN RULES | `app/services/action_config.py:254-283` | `_BUILT_IN_RULES` holds `(default, grant)` pairs and is the merge base |
| TOOL MAPPING | `app/services/action_adapters.py:75-76, 89-98, 177-227` | `TARGET_FORMATS`; `ToolMappingError`; `ToolMapping(kind, target, default=None, format="text", extra_targets=())`, where `extra_targets` must be a **tuple** (`:210-213`) |
| STRICT YAML | `app/services/strict_yaml.py:62-72` | `safe_load(text)` raises `yaml.constructor.ConstructorError` (a `yaml.YAMLError`) naming the key and both lines |
| TEST FILE WRITER | `tests/test_pattern_config.py:81-84` | `_write(tmp_path, text) -> str` |
| KEEP-PREVIOUS TEST | `tests/test_pattern_config.py:220-230` | load a bad file, assert `pytest.raises`, assert the previous policy is still in force |
| SAMPLE-FILE TEST | `tests/test_pattern_config.py:797-822` | `_SAMPLE_FILE = Path(__file__).resolve().parents[1] / "examples" / ...`; `policy is not BUILT_IN_POLICY` guard |
| EXPECT HELPER | `tests/test_action_config.py:387-394` | `_expect(spec, *fragments)` asserting prefix + fragments |
| POLICY RESET | `tests/conftest.py` `_default_action_policy` (STORY-006 Task 4) | Autouse: pins `ACTION_POLICY_FILE=""` and restores `action_config._policy`, so the new tests need no local reset fixture |

### Naming
```python
# SOURCE: app/services/action_config.py:338-343
def _fail(source: str, *parts: str) -> ActionConfigError:
    return ActionConfigError(f"{source}: " + ": ".join(parts))

def _allowed(values) -> str:
    return ", ".join(sorted(values))
```

### Error Handling
```python
# SOURCE: app/services/pattern_config.py:592-607
try:
    raw = Path(path).read_text(encoding="utf-8")
except OSError as exc:
    raise PatternConfigError(f"Failed to read PATTERNS_FILE '{path}': {exc}") from exc

try:
    document = strict_yaml.safe_load(raw)
except yaml.YAMLError as exc:
    raise PatternConfigError(f"Failed to parse PATTERNS_FILE '{path}': {exc}") from exc

if not isinstance(document, Mapping):
    raise _fail(path, "document", "must be a mapping with 'lists' and 'profiles' sections")
```

### Tests
```python
# SOURCE: tests/test_pattern_config.py:220-230
def test_a_failed_load_leaves_the_previous_policy_in_force(tmp_path, monkeypatch, _reset_policy):
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, "lists: {}\nprofiles: {}\n"))
    with pytest.raises(PatternConfigError):
        load()
    assert get_policy() is BUILT_IN_POLICY
```

---

## Design decisions (for the implementer and the orchestrator)

1. **Two layers: a file parser that produces a spec, then `_validate`.** A new `_parse_document(source, document) -> dict` does everything that only a file can get wrong: the document type, the top-level and section keys, the per-id `rules:` merge, building `ToolMapping`s from YAML, and the wholesale/absent choice per section. It returns a spec with exactly `_SPEC_KEYS`. The content checks that hold for *any* policy go into `_validate`, so the built-in policy passes through them too (F8): absolute roots, network entry syntax, and `shell.allow` operators. The built-in lists are empty, so they cannot fail there. `_validate` keeps its existing checks unchanged; it is still the backstop for decisions, grants, T5, T7, the opaque/tools overlap and globs.
2. **Every message starts with `source = f"ACTION_POLICY_FILE '{path}'"`**, read and parse failures included: `ACTION_POLICY_FILE '<p>': file: cannot be read: <exc>` and `ACTION_POLICY_FILE '<p>': file: is not valid YAML: <exc>`. This drops pattern_config's `"Failed to read ..."` wording so that every `ActionConfigError` from a file has one prefix and one test helper. The existing STORY-006 tests (`tests/test_action_config.py:140-152`, `tests/test_main.py:440-454`, `tests/test_chat_ui_startup_guard.py:306-310`) assert only the type, the path and `"ACTION_POLICY_FILE"`. All three still hold for a missing file, so no assertion changes. Read errors catch `(OSError, UnicodeDecodeError)`: `read_text(encoding="utf-8")` on a non-UTF-8 file raises `UnicodeDecodeError`, a `ValueError`, which pattern_config's `except OSError` would let escape as a non-`ActionConfigError`. The duplicate-key error is a `yaml.YAMLError` from `strict_yaml`, so it arrives through the parse arm, and its text names the key and both lines (the node and the rule for AC 3).
3. **The document shape.** An empty file (parses to `None`), a list or a scalar is refused: `document: must be a mapping of sections (allowed: network, opaque_tools, rules, secrets, shell, tools, workspace)`. It does not fall back to the built-in policy, because an empty file named by a setting is a mistake and not an intent. The top-level keys are `workspace`, `network`, `shell`, `rules`, `tools`, `opaque_tools` and `secrets`, all optional. Any other key is `unknown key` with the allowed list. That includes `protected_paths`, which is built-in only (STORY-006 decision 4 and the orchestrator decision on this story), and the test pins it.
4. **Sections and their keys.** A present section must be a mapping where one is expected, and states every key it owns. `workspace: {roots}`, `network: {allow}`, `shell: {allow}` and `secrets: {env, files}` all require their keys, through `_check_keys(..., allowed, required=allowed)`. The story makes every *section* optional. Inside a present one, an absent key is refused rather than defaulted. If it were defaulted to the built-in value, `secrets: {env: [...]}` would quietly keep the built-in `files`, and that is not wholesale replacement. If it were defaulted to empty, the same file would quietly drop every secret-file glob. Either way the operator could not read the policy off the file (`pattern_config._check_keys`'s reason, `pattern_config.py:323-327`). `[]` is still valid and means empty (PRD 6.6 "empty means empty"). A bare `allow:` line parses to `None` and is refused by `_validate_strings` as "must be a list, got NoneType".
5. **`rules:` merge semantics: field-level, per the story text. This deviates from the PRD wording and is flagged.** PRD 6.6 (line 322) says "a present one replaces both fields". The story's Technical Notes say "inside a rule both `default` and `grant` are optional (an absent one keeps the built-in value)". The plan follows the story. The base for each id is `_BUILT_IN_RULES[rule_id]`, which is always the built-in table and never the previously loaded file. A `default` or `grant` key that is present replaces that field. An explicit `grant: null` (or a bare `grant:`) removes the grant, so a rule can still be made un-liftable. A `default: null` reaches `_validate` and fails as "not a decision". Each entry must be a mapping with only `default` and/or `grant`, and must set at least one. `shell.unlisted: flag` (the shorthand slip) and `shell.unlisted: {}` (a no-op in a file whose `rules:` is meant to list deviations) are both errors. AC 1 holds under either reading. The difference is that `shell.unlisted: {default: flag}` keeps `grant: action:shell:exec` under the plan's reading, where the PRD's reading would drop it.
6. **`rules:` entry checks done in the parser, before the merge.** An unknown rule id produces `rules: '<id>': unknown rule (allowed: ...)`, the same text `_validate_rules` produces (`action_config.py:364-371`). A `tool.opaque` entry is refused outright, with `rules: 'tool.opaque': not configurable here: its decision is each opaque_tools entry's (PRD-016 Section 6.3)` (orchestrator decision, STORY-006 plan decision 3). `_validate` would also catch a `default` on it after the merge. Refusing the entry by name in the parser is clearer, and it also catches `tool.opaque: {grant: null}`, which the merge alone would let through as a no-op.
7. **`tools:` building.** A present `tools:` must be a mapping, and `tools: {}` passes through to `_validate`'s T7 check (`tools: must not be empty (PRD-016 T7)`). For each entry, the name must be a non-empty string and the body a mapping. `_check_keys(source, f"tools: {name!r}", body, {"kind","target","default","format","extra_targets"}, {"kind","target"})`. `extra_targets` must be a YAML list, which becomes a `tuple`. A bare string is refused by name (`extra_targets must be a list of target expressions`), not left to `ToolMapping`'s "must be a tuple", which a YAML author cannot act on. Then `ToolMapping(**fields)` under `except ToolMappingError as exc: raise _fail(source, "tools", f"{name!r}", str(exc)) from exc`. An unknown `kind`, an unknown `format`, a bad target expression and a bad `default` all surface this way, already naming the field and the vocabulary (`action_adapters.py:198-227`). When `tools:` is absent, the spec gets `BUILT_IN_TOOLS` itself, which `_validate_tools` keeps by identity (`action_config.py:455-456`).
8. **`opaque_tools:` and `secrets:` values** go into the spec unchanged. `_validate` already checks that each opaque decision is a `DECISIONS` member and does not overlap `tools`, and that the globs translate. An absent `opaque_tools` keeps the built-in `{}`. An absent `secrets` keeps `_BUILT_IN_SECRET_ENV`/`_BUILT_IN_SECRET_FILES`.
9. **`workspace.roots`: absolute, checked the same way on every OS.** `_check_workspace_root(source, root)` in `_validate` replaces `\` with `/` and then accepts only a POSIX absolute path (`/...`) or a drive-absolute Windows path (`^[A-Za-z]:/`). It refuses: empty, relative (`projects`, `./x`), `~` (`~/x`, which PRD 6.5 line 264 says no root contains), and drive-relative (`C:x`, `C:`). It deliberately does not use `os.path.isabs`, because the result would then depend on the OS running the tests and the gateway, while the agent's OS is a third, unrelated machine. A UNC path (`\\srv\share`) becomes `//srv/share` and is accepted as absolute. Roots are stored as written: normalization for containment is STORY-011's `normalize_path`, which runs on both sides. The digest stays over source values (STORY-006 decision 7).
10. **`network.allow` entries.** `_check_network_entry(source, entry)` in `_validate` accepts exactly three shapes. (a) An IP literal: `ipaddress.ip_address(entry)` succeeds, so `169.254.169.254` and `::1` are accepted (bare, with no brackets). (b) An exact host: an RFC 1123 hostname, with labels `[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?` joined by `.`, total length 253 or less, no trailing dot, and a last label that is not all digits, so that `999.1.1.1` and `127.1` are refused instead of being read as hostnames. `localhost` is accepted. (c) A wildcard host: `*.` followed by a valid (b). Anything else is refused, with `network.allow: '<entry>': not a host, a '*.' wildcard host or an IP literal`. That covers a scheme (`https://pypi.org`), a port (`pypi.org:443`), a path, userinfo (`u@h`), `*`, `*pypi.org`, `a.*.com`, a CIDR (`10.0.0.0/8`), a bracketed IPv6 (`[::1]`), a wildcard over IP-shaped labels (`*.10.0.0.1`), empty, whitespace and an underscore. Case is accepted as written: matching is STORY-012's and is case-insensitive there. A wildcard over a single label (`*.com`) is accepted. PRD 6.5 does not restrict it, and it is an operator-visible choice. This is listed as an open question.
11. **`shell.allow` entries.** `_check_shell_entry(source, entry)` in `_validate` refuses an empty or whitespace-only entry, and any entry containing a character of `; & | $ \` < > ( )` or a line break (`\n`, `\r`). The story lists `; & | $` and the backtick. PRD 9.3 says "a shell operator", and POSIX defines `< > ( )` and newline as operators too (newline is a command separator equivalent to `;`). Refusing them is fail-closed and matches the PRD's wording. The message is `shell.allow: '<entry>': contains the shell operator '<c>' (an entry is a command head of one or more words)`. Multi-token entries (`npm test`) are accepted as written. How heads are tokenized and matched is STORY-010's.
12. **`load()` order and atomicity.** The order is: read the setting (empty means return, reading nothing, as now), read the file, parse, check the document, `_parse_document`, then `_validate`. `_policy = policy` is the last statement. `policy_digest()` is computed from `_policy` on each call (STORY-006 decision 7), so "the previous digest is still in force" (AC 4) follows from `_policy` not being rebound. The `ACTION_SQL_DIALECT` cross-check is STORY-008's and is not planned here. The docstring names it as STORY-008's.
13. **The sample file follows PRD 6.6 as written, with one addition, which is flagged.** `examples/action_policy.yaml` reproduces the 6.6 YAML: the same sections, values and order, `apply_patch` with `format: patch`, and `opaque_tools: todowrite: allow`. It adds a header comment block (how to use it, that sections replace wholesale, that `rules:` merges per id and why (Risk 7), what `grant: null` does, that an invalid file stops startup and never falls back, and that `protected_paths` is not configurable). **Addition:** `secrets.env` also lists `"OPENROUTER_*"`. The sample replaces `secrets` wholesale, so a deployment copying 6.6 verbatim would stop treating the gateway's own key variable as a secret, which the built-in policy covers (STORY-006 decision 5). The alternative is to keep the PRD's six and add a comment only. Orchestrator: say if you prefer that. AC 5 holds either way.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/action_config.py` | UPDATE | Imports (`ipaddress`, `Path`, `yaml`, `strict_yaml`, `ToolMappingError`); `_check_keys`; `_parse_document` and its section helpers; content checks in `_validate`; real `load()`; updated module, `ActionConfigError`, `_validate` and `load` docstrings |
| `examples/action_policy.yaml` | CREATE | PRD 6.6 sample, with comments (decision 13) |
| `tests/test_action_config.py` | UPDATE | Module docstring; STORY-006 docstrings that said "STORY-007 adds it" (comment-cited); new STORY-007 block of tests |

No change to `app/main.py`, `chat_ui/`, `tests/conftest.py`, `tests/test_main.py` or `tests/test_chat_ui_startup_guard.py`: both lifespans already call `load()`, and their missing-file tests stay valid (decision 2). No README or `.env.example` change: STORY-020 owns both.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: `_validate` content checks (any policy)

- **File**: `app/services/action_config.py`
- **Action**: UPDATE
- **Implement**:
  - `import ipaddress`. Add a module constant `_HOST_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")`, `_SHELL_OPERATORS = frozenset(";&|$`<>()\n\r")` (written so the backtick and line breaks are readable, e.g. a tuple of literals), and `_DRIVE_ABSOLUTE = re.compile(r"[A-Za-z]:/")`.
  - `_is_hostname(value: str) -> bool` implements decision 10(b). `_check_network_entry(source, entry)` implements decision 10: try `ipaddress.ip_address` under `except ValueError`, then a hostname, then `*.` + hostname. Otherwise `raise _fail(source, "network.allow", f"{entry!r}", "not a host, a '*.' wildcard host or an IP literal")`.
  - `_check_workspace_root(source, root)` implements decision 9, with the message `workspace.roots: '<root>': must be an absolute path ('/...' or a drive letter 'C:/...'); a relative or '~' root contains nothing`.
  - `_check_shell_entry(source, entry)` implements decision 11. Report the first offending character in entry order, with `repr` so a newline is visible.
  - In `_validate` (`action_config.py:554-556`), after each `_validate_strings` call, loop the entries through the matching checker. Update `_validate`'s docstring (`:509-540`): move absolute roots, network syntax and shell operators from "Added by STORY-007" into "Checked here". Reword the remainder to say that the file-only checks live in `_parse_document`, and that the dialect check is STORY-008's.
- **Mirror**: `_validate_globs` (`action_config.py:498-506`) for the per-entry loop and the `_fail(source, node, repr(value), rule)` message shape
- **Validate**: `.venv/Scripts/python -c "from app.services import action_config as c; print(c.policy_digest())"` prints the **same digest as before the change**. The built-in policy is untouched, and the implementer should record the digest before Task 1.

### Task 2: The file parser

- **File**: `app/services/action_config.py`
- **Action**: UPDATE
- **Implement** (new block `# --- The policy file ---` between `_validate` and `BUILT_IN_POLICY`, or after `policy_digest` and before `load`; the parser needs `_BUILT_IN_*` constants, which are defined above `_validate`, so either placement works):
  - Imports: `from pathlib import Path`, `import yaml`, `from app.services import strict_yaml`, and add `ToolMappingError` to the `action_adapters` import.
  - `_check_keys(source, where, body, allowed, required)`: a copy in shape of `pattern_config.py:320-343` (unknown first, then missing). Do not import pattern_config's private helper. The two modules each own their errors.
  - Vocabulary constants: `_FILE_SECTIONS = ("workspace", "network", "shell", "rules", "tools", "opaque_tools", "secrets")`, `_RULE_KEYS = frozenset({"default", "grant"})`, `_TOOL_KEYS` (5) and `_TOOL_REQUIRED` (2).
  - `_mapping(source, node, value)` raises `_fail(source, node, f"must be a mapping, got {type(value).__name__}")` unless `isinstance(value, Mapping)`.
  - `_parse_rules(source, raw) -> dict` implements decisions 5 and 6. It starts from `dict(_BUILT_IN_RULES)`. Per entry, in file order: the id must be in `RULE_IDS` (with `_allowed(RULE_IDS)` listed), it must not be `tool.opaque`, the body must be a mapping, `_check_keys(source, f"rules: {rule_id!r}", body, _RULE_KEYS, ())`, and it must not be empty (`must set default and/or grant`). Then `merged[rule_id] = (body.get("default", base_default), body["grant"] if "grant" in body else base_grant)`. Comment the D12 reason (PRD 6.6 line 322), the field-level deviation, and the meaning of `grant: null`.
  - `_parse_tools(source, raw) -> dict[str, ToolMapping]` implements decision 7.
  - `_parse_document(source, document) -> dict` implements decisions 3, 4 and 8. It refuses a non-mapping document and runs `_check_keys(source, "document", document, _FILE_SECTIONS, ())`. For `workspace`, `network`, `shell` and `secrets`, it calls `_mapping` then `_check_keys(..., allowed=required=...)`. Each spec key is set from the file when the section is present, and otherwise from the built-in value (`_BUILT_IN_RULES` when `rules` is absent, `BUILT_IN_TOOLS`, `{}`, `()`, `()`, `()`, `_BUILT_IN_SECRET_ENV`, `_BUILT_IN_SECRET_FILES`). `protected_paths` is always `_BUILT_IN_PROTECTED_PATHS`. The docstring lists the order of checks and the two replacement rules, citing D12 and PRD 6.6.
- **Mirror**: `app/services/pattern_config.py:320-343, 390-434` (section parser shape), `:365-373` (exception seam)
- **Validate**: covered by Task 5. Import check: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 3: The real `load()`

- **File**: `app/services/action_config.py`
- **Action**: UPDATE
- **Implement**: replace the body of `load()` at `:682-689`:
  ```python
  global _policy

  path = settings.ACTION_POLICY_FILE
  if not path:
      return

  source = f"ACTION_POLICY_FILE '{path}'"
  try:
      raw = Path(path).read_text(encoding="utf-8")
  except (OSError, UnicodeDecodeError) as exc:
      raise _fail(source, "file", f"cannot be read: {exc}") from exc
  try:
      document = strict_yaml.safe_load(raw)
  except yaml.YAMLError as exc:
      raise _fail(source, "file", f"is not valid YAML: {exc}") from exc

  policy = _validate(source, _parse_document(source, document))
  _policy = policy
  ```
  Rewrite the docstring in the voice of `pattern_config.py:549-582`. It covers: the empty-setting no-op; every check passes before the rebind; `strict_yaml` (D13), with duplicate keys refused at any depth; sections wholesale and `rules:` per id (D12); the T13 trust boundary (a writable file is the boundary `RBAC_ROLES_FILE`/`PATTERNS_FILE` already sit on, and no new mitigation is claimed); no silent fallback; and the `ACTION_SQL_DIALECT` cross-check as STORY-008's.
  Also update the module docstring (`:29-33`, "What is deliberately not here yet") to name only STORY-008's dialect check. Update the `ActionConfigError` docstring (`:74-78`, "Added by STORY-007") to present tense, listing what the file adds: unreadable or unparseable file, duplicate key, document not a mapping, unknown key at any level, missing section key, a `rules: tool.opaque` entry, an empty rule entry, a tool body problem wrapped from `ToolMappingError`, a relative root, a bad network entry and a shell operator. The two-exception-seam paragraph (`:84-88`) becomes present tense.
- **Mirror**: `app/services/pattern_config.py:583-613`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_config.py -q -p no:cacheprovider`. The existing STORY-006 tests must still pass unmodified, including `test_load_with_a_policy_file_set_fails_closed`.

### Task 4: `examples/action_policy.yaml`

- **File**: `examples/action_policy.yaml`
- **Action**: CREATE
- **Implement**: a header comment block in the voice of `examples/patterns.yaml:1-19` (usage `ACTION_POLICY_FILE=examples/action_policy.yaml`; edit a copy; an invalid file stops startup naming the node and never falls back; settings that interact: `ACTION_MAX_ARGUMENT_CHARACTERS`, `ACTION_SQL_DIALECT`). It explains the two replacement rules: every present section replaces the built-in one wholesale, so an entry deleted here is gone. `rules:` is the exception, merged per rule id: an omitted rule keeps its built-in default and grant, and a listed field replaces only that field (`grant: null` removes a grant). The block states why (Risk 7: the catalogue is the floor; this section lists deviations from it) and adds that ten rules never take a grant (T5), that `tool.opaque` is configured through `opaque_tools`, and that protected paths are built in. Then the YAML of PRD 6.6 (lines 274-320), keeping its inline comments, plus `"OPENROUTER_*"` in `secrets.env` with a one-line comment (decision 13). The `tools:` comment says it replaces the built-in list, which also covers OpenCode `glob`/`grep`/`lsp` and the Cline tools, and that a tool missing here is `tool.unknown` (deny).
- **Validate**: Task 5's sample-file test.

### Task 5: Tests

- **File**: `tests/test_action_config.py`
- **Action**: UPDATE
- **Implement**:
  - Module docstring: retitle to "PRD-016 STORY-006 and STORY-007". Replace the "deliberately does not cover" paragraph: STORY-007 now covers reading `ACTION_POLICY_FILE`, the merge, the wholesale sections, and one test per Section 9.3 rule. What remains uncovered is the `ACTION_SQL_DIALECT` cross-check (STORY-008) and how a classifier uses globs and lists (STORY-010 to STORY-013).
  - STORY-006 docstrings that reference STORY-007 in the future tense. `test_load_reads_no_file_when_action_policy_file_unset` (`:122-125`) currently says "the module has no `Path` yet (STORY-007 adds it)". Reword it to say that `action_config.Path` is `pathlib.Path`, so the class-level patches cover the loader's read too, and also patch `action_config.Path` with `_no_read`. `test_load_with_a_policy_file_set_fails_closed` (`:140-143`): reword to "a missing file is unreadable (STORY-007)". Both docstrings get a `# PRD-016 STORY-007:` note. No assertion changes. Per the brief, the added `action_config.Path` patch is an addition, not a modified assertion, and it is commented.
  - Imports: add `textwrap`, plus `_BUILT_IN_RULES` if needed. Constants `_SAMPLE_FILE = REPO_ROOT / "examples" / "action_policy.yaml"`.
  - Helpers:
    - `_load_text(tmp_path, monkeypatch, text) -> str`: writes `textwrap.dedent(text)` to `tmp_path / "action_policy.yaml"` (UTF-8), sets the setting, calls `load()`, and returns the path.
    - `_expect_file(tmp_path, monkeypatch, text, *fragments) -> str`: like `_load_text` but expects `ActionConfigError`. It asserts the message starts with `f"ACTION_POLICY_FILE '{path}': "`, that every fragment is in it, and that `get_policy() is BUILT_IN_POLICY` afterwards.
  - **AC 1, merge**:
    - `test_rules_merge_per_id_keeping_every_other_rule`: `rules: {shell.unlisted: {default: flag}}`. Assert `shell.unlisted == Rule("flag", "action:shell:exec")`, every other id equals `BUILT_IN_POLICY.rules[id]`, and `tuple(policy.rules) == RULE_IDS`.
    - `test_a_rule_grant_alone_keeps_the_built_in_default` (`fs.read: {grant: action:fs:write}`; `fs.read` is grantable, since it is not in `NON_GRANTABLE_RULES`) gives `Rule("allow", "action:fs:write")`.
    - `test_grant_null_removes_a_grant` (`sql.write: {grant: null}`) gives `Rule("deny", None)`.
    - `test_the_merge_base_is_the_built_in_table_not_the_previous_file`: load A with a `shell.unlisted` deviation, then B with `{}` rules. B's `shell.unlisted` is built-in.
  - **AC 2, wholesale**: `test_a_present_section_replaces_the_built_in_one`, parametrized over five cases: `tools: {bash: {kind: shell, target: command}}` gives `set(policy.tools) == {"bash"}`; `shell: {allow: [ls]}` gives `("ls",)`; `network: {allow: [pypi.org]}`; `secrets: {env: [X_*], files: [a.txt]}` gives env `("X_*",)` and files `("a.txt",)`, with built-in `.env*` no longer present; and `workspace: {roots: [/srv/app]}`. Also:
    - `test_an_absent_section_keeps_the_built_in_one`: a file with only `rules: {}` gives `policy is not BUILT_IN_POLICY`, `policy == BUILT_IN_POLICY`, `policy.tools is BUILT_IN_TOOLS` and an equal digest.
    - `test_an_empty_list_means_empty`: `shell: {allow: []}` gives `()` (PRD 6.6).
    - `test_a_tool_mapping_accepts_default_format_and_extra_targets`: `glob: {kind: fs_read, target: path, default: ".", extra_targets: [pattern]}` and `apply_patch: {..., format: patch}` equal the `ToolMapping(...)` literals.
  - **AC 3, one function per rule** (each through `_expect_file`, asserting node + rule fragments):
    - `test_file_refuses_an_unknown_top_level_key` is parametrized over `rule`, `tool`, `protected_paths`, `workspaces` and asserts `"document"`, `"unknown key"`, the key, and `"workspace"` (the allowed list).
    - `test_file_refuses_an_unknown_section_key` (`workspace: {root: [/a]}`, `network: {allowed: []}`, `shell: {allowlist: []}`, `secrets: {envs: [], files: []}`).
    - `test_file_refuses_a_missing_section_key` (`secrets: {env: []}` names `files`).
    - `test_file_refuses_a_section_of_the_wrong_type` (`tools: [bash]`, `rules: null`, `workspace: /a`).
    - `test_file_refuses_a_document_that_is_not_a_mapping` (empty file, `- a`, `just text`).
    - `test_file_refuses_an_unreadable_file` (a directory as the path, or invalid UTF-8 bytes written with `write_bytes(b"\xff\xfe")`; asserts `"file"`, `"cannot be read"`).
    - `test_file_refuses_invalid_yaml` (`rules: [`).
    - `test_file_refuses_an_unknown_rule_id` (`sql.nuke`; message lists `sql.read`).
    - `test_file_refuses_an_unknown_rule_key` (`{defualt: deny}`).
    - `test_file_refuses_a_rule_that_is_not_a_mapping` (`shell.unlisted: flag`).
    - `test_file_refuses_an_empty_rule_entry`.
    - `test_file_refuses_a_tool_opaque_rule_entry` (parametrized: `{default: allow}`, `{grant: null}`).
    - `test_file_refuses_a_bad_decision` (`default: block`; asserts `rules: 'sql.read'`, `'block'`, `allow, deny, flag`).
    - `test_file_refuses_an_unknown_permission`.
    - `test_file_refuses_a_grant_on_a_non_grantable_rule`, parametrized over `sorted(NON_GRANTABLE_RULES)` with an assert of 10 ids (T5).
    - `test_file_refuses_empty_tools` (T7).
    - `test_file_refuses_an_unknown_kind` (`kind: shel`; asserts `tools: 'bash'`, `unknown operation kind`).
    - `test_file_refuses_a_missing_target` (and `kind`, parametrized).
    - `test_file_refuses_an_unknown_tool_key` (`targets:`).
    - `test_file_refuses_a_tool_mapping_the_adapter_rejects`, parametrized over `format: diff`, `target: "files["`, `default: "."` with `format: patch`, and `extra_targets: pattern` (the bare-string slip). Each names `tools: '<name>'`.
    - `test_file_refuses_a_tool_both_mapped_and_opaque`.
    - `test_file_refuses_an_opaque_tool_value_that_is_not_a_decision`.
    - `test_file_refuses_a_relative_workspace_root` (`projects`, `./x`, `~/x`, `C:x`, `""`).
    - `test_file_accepts_absolute_workspace_roots` (`/home/dev/projects`, `C:/Repo`, `C:\\Repo`, `d:/x`).
    - `test_file_refuses_a_bad_glob` (`secrets: files: ["a[b"]`).
    - `test_file_refuses_a_bad_network_entry`, parametrized over decision 10's refusals.
    - `test_file_accepts_each_network_entry_shape` (`registry.npmjs.org`, `*.githubusercontent.com`, `localhost`, `169.254.169.254`, `::1`).
    - `test_file_refuses_a_shell_allow_entry_with_an_operator`, parametrized over `ls; rm`, `a && b`, `a | b`, `echo $HOME`, a backtick case, `a > f`, `a\nb`.
    - `test_file_refuses_an_empty_shell_allow_entry` (`""`, `"  "`).
    - `test_file_accepts_a_multi_token_shell_allow_entry` (`npm test`).
    - `test_file_refuses_a_duplicate_key`, parametrized over a top-level `rules:` twice, a rule id twice, and a tool name twice. It asserts `"duplicate key"` and the key name (D13).
  - **AC 4**: `test_a_failed_load_keeps_the_previous_file_policy_and_digest`. Load a valid file (`rules: {shell.unlisted: {default: flag}}`) and capture `policy = get_policy()` and `digest = policy_digest()`, asserting `digest != policy_digest(BUILT_IN_POLICY)`. Overwrite with a file that fails late (a valid `rules:` and `tools:`, then `network: {allow: ["https://x"]}`, so the failure comes in `_validate` after the parse succeeded), expect `ActionConfigError`, and assert `get_policy() is policy` and `policy_digest() == digest`.
  - **AC 5**: `test_examples_action_policy_yaml_loads`. Set the setting to `str(_SAMPLE_FILE)` and load. Assert `policy is not BUILT_IN_POLICY`, `policy_digest() != policy_digest(BUILT_IN_POLICY)`, `rules["shell.unlisted"] == Rule("flag", "action:shell:exec")`, `tools["apply_patch"] == ToolMapping("fs_write", "patchText", format="patch")`, `dict(opaque_tools) == {"todowrite": "allow"}`, `workspace_roots == ("/home/dev/projects",)`, `"npm test" in shell_allow`, and `"*.githubusercontent.com" in network_allow`. The docstring cites PRD 11 "`examples/action_policy.yaml` loads in a test" (line 654).
  - `test_load_ignores_comments_and_key_order_in_the_digest` (optional, cheap): two files with the same content in a different key order and with comments give equal digests (PRD 4 / STORY-006 decision 7).
- **Mirror**: `tests/test_pattern_config.py:81-84, 220-230, 797-822`; `tests/test_action_config.py:387-394`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_config.py -q -p no:cacheprovider`

### Task 6: Targeted regression

Run in one invocation:
`PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_config.py tests/test_main.py tests/test_chat_ui_startup_guard.py tests/test_strict_yaml.py tests/test_untouched_app.py -q -p no:cacheprovider`

- `test_main.py` and `test_chat_ui_startup_guard.py` hold the STORY-006 missing-file lifespan tests, which now go through the real read path (decision 2). The chat UI probe needs the libSQL dev server on 8080.
- `test_strict_yaml.py` covers the loader `action_config` now uses.
- `test_untouched_app.py` is the guard for touched app files.
- Full suite: deferred to orchestrator (user decision).

---

## End-to-End Tests

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` prints OK
- [ ] The built-in digest is byte-identical before and after this story (`.venv/Scripts/python -c "from app.services import action_config as c; print(c.policy_digest())"`)
- [ ] `ACTION_POLICY_FILE=examples/action_policy.yaml .venv/Scripts/python -c "from app.services import action_config as c; c.load(); print(c.get_policy().rules['shell.unlisted'], c.policy_digest())"` (Git Bash, from the repo root) prints `Rule(default='flag', grant='action:shell:exec')` and a digest different from the built-in one
- [ ] The same command with a copy of the sample containing a duplicate `rules:` key exits with `ActionConfigError: ACTION_POLICY_FILE '...': file: is not valid YAML: ... found duplicate key 'rules' ...`

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_config.py tests/test_main.py tests/test_chat_ui_startup_guard.py tests/test_strict_yaml.py tests/test_untouched_app.py -q -p no:cacheprovider
```

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| The field-level `rules:` merge (story) contradicts the PRD 6.6 wording "a present one replaces both fields" | The plan follows the story text (decision 5), documents it in the docstring and the sample's comments, and makes `grant: null` the explicit way to drop a grant. Flagged to the orchestrator. If the PRD reading is chosen, only `_parse_rules`' merge line and two tests change |
| New `_validate` checks could change the built-in policy or its digest | They only read lists that are empty in the built-in policy. Task 1 validates that the digest is unchanged |
| The validator refuses an entry an operator reasonably writes (an uppercase host, `C:\Repo`, `*.local`) | Uppercase hosts and both Windows separators are accepted. The refusal list is explicit and tested. Single-label wildcards are accepted (open question) |
| `os.path.isabs` would give OS-dependent answers | A lexical rule, the same on every OS (decision 9) |
| `UnicodeDecodeError` escaping as a non-`ActionConfigError` | Caught with `OSError` (decision 2), and tested |
| Example drift: the sample, the PRD and the tests disagree | AC 5's test pins the sample's distinctive values. The `OPENROUTER_*` addition is the only deliberate difference from PRD 6.6, and it is flagged (decision 13) |
| STORY-006 tests that assumed the interim error | They assert type, path and `ACTION_POLICY_FILE` only, and a missing file still yields that (decision 2). Only docstrings change |
| Shell-operator set wider than the story's five characters | Justified by PRD 9.3's "a shell operator" (decision 11). Fail-closed. Flagged |

---

## Open questions for the orchestrator

1. `rules:` merge: field-level (story text, planned) or both-fields (PRD 6.6 line 322)? (Decision 5.)
2. Sample `secrets.env`: add `"OPENROUTER_*"` (planned) or keep the PRD's six? (Decision 13.)
3. Should `network.allow` refuse a wildcard over a single label (`*.com`)? Not planned; PRD 6.5 is silent.

---

## Acceptance Criteria

(Copied from story `STORY-007`)

- [ ] Given a file whose `rules:` sets only `shell.unlisted: {default: flag}`, when loaded, then that rule is `flag` and every other rule keeps its built-in default and grant (per-id merge, D12). (Tasks 2, 3, 5: `test_rules_merge_per_id_keeping_every_other_rule`)
- [ ] Given a file with a `tools:` section, when loaded, then the built-in tool mappings are replaced wholesale; the same holds for `shell.allow`, `network.allow`, `secrets` and `workspace.roots`; a section absent from the file keeps the built-in one. (Tasks 2, 5: `test_a_present_section_replaces_the_built_in_one`, `test_an_absent_section_keeps_the_built_in_one`)
- [ ] Given a file breaking any one validation rule in PRD Section 9.3, when loaded, then `ActionConfigError` names the file, the node and the rule, with one test per rule, including: an unknown rule id, a bad decision, an unknown permission, a grant on each of the ten non-grantable rules, `tools: {}`, an unknown `kind`, a relative workspace root, a name in both `tools` and `opaque_tools`, a bad network entry, a `shell.allow` entry containing `;`, and a duplicate YAML key. (Tasks 1-3, 5: the `test_file_refuses_*` functions)
- [ ] Given a file that fails validation after a valid one was loaded, when `load()` runs, then the previously loaded policy and its digest are still in force. (Task 3, 5: `test_a_failed_load_keeps_the_previous_file_policy_and_digest`)
- [ ] Given `examples/action_policy.yaml` (PRD Section 6.6), when a test loads it, then it loads, and its digest differs from the built-in digest. (Tasks 4, 5: `test_examples_action_policy_yaml_loads`)
- [ ] All tasks completed
- [ ] Backend imports without error
- [ ] Follows existing patterns
