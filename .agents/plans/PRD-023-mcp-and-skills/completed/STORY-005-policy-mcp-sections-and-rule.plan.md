---
story: STORY-005
prd: PRD-023
slug: policy-mcp-sections-and-rule
title: "Action policy: `mcp_tools` / `mcp_opaque_tools` sections and the `tool.not_in_skill` rule"
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-22
---

# Plan: mcp_tools / mcp_opaque_tools sections and `tool.not_in_skill`

## Summary

Add two per-server mapping tables to `ActionPolicy` (file sections `mcp_tools`, `mcp_opaque_tools`), validated by the existing `_validate_tools` / `_validate_opaque_tools` once per server, and one new non-grantable deny rule `tool.not_in_skill`. The digest includes the tables only when non-empty. `evaluate()` and adapters are untouched (STORY-006).

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-005-policy-mcp-sections-and-rule.md`
- PRD sections used: Section 4 (MCP bullets), 6.4, 9.3 (ACTION_POLICY_FILE additions), D4, D7
- Systems affected: `action_config`, `action_classifiers` vocabulary, one dict entry in `action_policy` (`_SUBJECTS`), tests

## Design Decisions

Orchestrator points (binding): `ActionPolicy` gains frozen `mcp_tools` / `mcp_opaque_tools`, `MappingProxyType` outer and inner, empty in `BUILT_IN_POLICY`; each server's inner mapping goes through the existing validators with a node path naming the server (`mcp_tools.<server>`); errors (`ActionConfigError`, file + node): section not a mapping, server id failing `fullmatch [a-z0-9][a-z0-9-]{0,31}`, empty server mapping (PRD-016 T7), same tool under the same server in both sections. A name in `mcp_tools.<s>` and top-level `tools:` is not an error (D4). No MCP_CONFIG_FILE check (STORY-007), no `MCP_ENABLED` read. Digest keys only when non-empty. `tool.not_in_skill`: deny, grant None, subject `"a tool outside the caller's skills"`, non-grantable (26 / 11).

Findings from the code that shape the implementation:

- **Fields**: add after `secrets` in `ActionPolicy` (`app/services/action_config.py:175-209`) with `field(default_factory=lambda: MappingProxyType({}))`. The only constructor is `_validate` (`:703`); no test calls `ActionPolicy(` (grep), only `dataclasses.replace`.
- **Spec keys optional.** `_validate` demands `set(spec) == _SPEC_KEYS` (`:368`, `:673-681`). Making the two new keys required breaks the `_spec()` helper (`tests/test_action_config.py:107`) and every PRD-016 test built on it. Add `_OPTIONAL_SPEC_KEYS`; the check becomes `_SPEC_KEYS <= keys <= _SPEC_KEYS | optional`, same message; read with `spec.get(key, {})`. PRD-016 tests stay unmodified (brief rule: never edit them to pass).
- **Node kwargs, not copies.** `_validate_tools` (`:457`) and `_validate_opaque_tools` (`:482`) hardcode `"tools"` / `"opaque_tools"` in each `_fail`. Add keyword params whose defaults reproduce today's text exactly: `_validate_tools(source, tools, *, node="tools")`; `_validate_opaque_tools(source, opaque, tools, *, node="opaque_tools", tools_node="tools")` with the overlap message `f"also mapped under {tools_node}; a tool is either mapped or opaque, not both"`. Server calls pass `node=f"mcp_tools.{server}"` etc., giving `ACTION_POLICY_FILE '<p>': mcp_tools.github: 'x': ...`.
- **New helpers** `_validate_mcp_tools(source, raw)` and `_validate_mcp_opaque_tools(source, raw, mcp_tools)` next to the validators, plus constant `_MCP_SERVER_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")` (`re` already imported). Each: section is a `Mapping` else `_fail(source, section, "must be a mapping, got X")`; server id is `str` and `fullmatch`; the server body is non-empty (`_validate_opaque_tools` accepts empty, so the emptiness check lives in the helper, for both sections: "must not be empty (PRD-016 T7)"); then delegate per server. Opaque overlap receives `mcp_tools.get(server, {})`. Return `MappingProxyType({server: MappingProxyType(dict)})` copies. An empty top-level section (`mcp_tools: {}`) is valid and means empty.
- **File parsing**: `_FILE_SECTIONS` (`:834`) gains both names (they also appear in "allowed" lists). `_parse_tools` (`:923`) hardcodes `"tools"` / `f"tools: {name!r}"`: add `node="tools"` kwarg. New `_parse_mcp_tools(source, raw)`: `_mapping` the section, per server check id + mapping, then `_parse_tools(source, body, node=f"mcp_tools.{server}")`; an empty `{}` passes through and is refused by the validator. `_parse_document` (`:971-1016`) returns both keys (absent -> `{}`); `mcp_opaque_tools` passes raw through like `opaque_tools` (`:1008`).
- **Digest** (`_canonical`, `:782-801`): build the dict, then add `out["mcp_tools"] = {srv: {n: asdict(m)}}` / `out["mcp_opaque_tools"] = {srv: dict(...)}` only when non-empty. Ordering is by `json.dumps(sort_keys=True)`.
- **Digest caveat (orchestrator should confirm)**: adding `tool.not_in_skill` to `rules` changes `_canonical()["rules"]`, so EVERY policy's digest changes once, MCP sections or not. "Unchanged digest" can only hold for the MCP keys. The continuity test therefore compares `policy_digest()` against sha256 of a pre-change-shaped canonical dict (the eight old keys, rules table with the new rule included, no MCP keys), and separately asserts `_canonical(BUILT_IN_POLICY)` has no `mcp_*` keys.
- **Rule**: `RuleId` (`app/services/action_classifiers/__init__.py:50-78`) appends `"tool.not_in_skill"` after `tool.malformed` (earlier positions and `RULE_IDS` order stay); `NON_GRANTABLE_RULES` (`:96-107`) gains it, comment "ten" -> "eleven" citing PRD-023 D7. `_BUILT_IN_RULES` (`action_config.py:276-305`) gains `"tool.not_in_skill": ("deny", None)` last; fix the "ten non-grantable" count in its comment.
- **`_SUBJECTS` must be extended**: `app/services/action_policy.py:130-157` needs `"tool.not_in_skill": "a tool outside the caller's skills"` (`evaluate` indexes it, `:256`; `tests/test_action_policy.py:410` asserts `set(_SUBJECTS) == set(RULE_IDS)`). Data entry only; `evaluate()` untouched. Not listed in the story's Technical Notes.
- **File `rules:` needs no code**: `_parse_rules` (`:877`) and `_validate_rules` (`:383-455`) iterate `RULE_IDS` / `NON_GRANTABLE_RULES`, so `rules: {tool.not_in_skill: {grant: ...}}` is refused like the other ten ("not allowed on a non-grantable rule"); its `default` can still be changed. Prove with a test.
- No rule inventory elsewhere in `app/` (grep `sql.unparsed` hits only classifiers, config, policy). `docs/features.md:726-728` and `docs/roadmap.md:93` still say 25 / ten: left to STORY-021, flag it.

## Skills In Use

None (`.agents/skills/` holds only `frontend-design`; story `skills: []`).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Errors | `action_config.py:360-361` `_fail` | file, node path, rule |
| Vocabulary iteration | `action_config.py:877-920` | iterate `RULE_IDS`, no copy of the list |
| Immutability | `action_config.py:455`, `:508` | `MappingProxyType(dict(...))` copies |
| File-refusal tests | `tests/test_action_config.py:529-543` `_expect_file`, `:913-921` | one failing-file test each |
| Spec-refusal tests | `tests/test_action_config.py:399-406` `_expect`, `_spec` `:107` | `_spec(mcp_tools=...)` works (optional keys) |
| Digest tests | `tests/test_action_config.py:360-396` | key-order insensitivity via `_validate` |
| Rule tables | `tests/test_action_vocabulary.py:30-70`, `tests/test_action_config.py:62` | pinned PRD tables |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/action_classifiers/__init__.py` | UPDATE | `RuleId`, `NON_GRANTABLE_RULES`, comments |
| `app/services/action_policy.py` | UPDATE | one `_SUBJECTS` entry |
| `app/services/action_config.py` | UPDATE | fields, spec keys, validators, parser, digest, built-in rule |
| `tests/test_action_vocabulary.py` | UPDATE | counts, id tuples |
| `tests/test_action_config.py` | UPDATE | counts, rule table, new MCP tests |
| `examples/action_policy.yaml` | LEAVE | `test_examples_action_policy_yaml_loads` (`:1118`) pins it; MCP example belongs to STORY-007/021 |

## Tasks

### Task 1: Vocabulary
- **File**: `app/services/action_classifiers/__init__.py`: append the rule id, add to `NON_GRANTABLE_RULES`, update the count comments (PRD-023 D7).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -c "from app.services.action_classifiers import RULE_IDS; print(len(RULE_IDS))"` prints 26.

### Task 2: `_SUBJECTS`
- **File**: `app/services/action_policy.py:156`: add the entry after `tool.malformed`.

### Task 3: action_config
- **File**: `app/services/action_config.py`. In order: record the pre-change digests first (see Task 5); `ActionPolicy` fields + docstring (PRD-023 D4); `_BUILT_IN_RULES`; `_OPTIONAL_SPEC_KEYS` and the key check; node kwargs; `_MCP_SERVER_ID` and the two helpers; `_validate` builds both tables and passes them to `ActionPolicy(...)`; `_validate` docstring checklist; `BUILT_IN_POLICY` spec passes `{}` for both explicitly; `_canonical` + `policy_digest` docstring; `_FILE_SECTIONS`; `_parse_tools(node=)`; `_parse_mcp_tools`; `_parse_document`.
- **Mirror**: `_validate_tools` / `_parse_tools` as above.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_action_config.py`

### Task 4: Existing count assertions (each edit gets a comment citing PRD-023 D7)
- `tests/test_action_vocabulary.py`: append `"tool.not_in_skill"` to `_PRD_6_3_RULE_IDS` (`:30`) and `_PRD_T5_NON_GRANTABLE` (`:58`) with a "PRD-023 D7, not in PRD-016's tables" comment; `:77-78` 25 -> 26; `:88-89` class counts `"tool": 3` -> `4`; `:105` 10 -> 11. Do NOT rename the tests (names say "25"/"ten"): renaming needs `_DELIBERATELY_SUPERSEDED_TESTS` in `tests/test_pii_redaction_integration.py`; keep names, explain in the comment.
- `tests/test_action_config.py`: add `"tool.not_in_skill": ("deny", None)` to `_PRD_6_3_RULES` (`:62`); `:171` 25 -> 26; `:179` 10 -> 11. `test_the_ten_non_grantable_rules_have_no_grant` is parametrized over the set and picks the new rule up (it asserts default deny, grant None: holds).

### Task 5: New tests in `tests/test_action_config.py`
- Before Task 1, on the unchanged tree, print `policy_digest()` of the built-in policy and of the policy loaded from `examples/action_policy.yaml`; after the change, assert the helper-computed old-shape digest (old canonical minus the new rule) equals those two literals, once, during implementation (report them; do not hard-pin literals in the test since the rule changes them).
- AC1: story example file loads via `_load_text`; `get_policy().mcp_tools["postgres-staging"]["query"]` is a `ToolMapping`; `mcp_opaque_tools["github"]["create_pull_request"] == "flag"`; outer and inner raise `TypeError` on assignment; each section alone changes `policy_digest()`.
- Digest: `_canonical(BUILT_IN_POLICY)` and a non-MCP file policy have no `mcp_*` keys; digest equals sha256 of that dict; adding an MCP mapping changes it; reversed server/tool order via `_validate` does not.
- AC2, one `_expect_file` test each (fragments: node and rule): `mcp_tools: [a]`; server id `GitHub`, `-a`, 33 chars, `a_b`; empty server mapping in `mcp_tools` and in `mcp_opaque_tools`; tool in both for one server (`also mapped under mcp_tools.github`); invalid mapping (unknown kind -> `mcp_tools.github: 'push_files'`; bad decision -> `mcp_opaque_tools.github: 'x'`). `_spec(...)` form for a non-string tool name and for copy-not-share.
- Accepted: same tool name under two servers; same name in `tools:` and `mcp_tools.<s>`; `mcp_opaque_tools` server with no `mcp_tools` entry.
- AC4: `monkeypatch.setattr(settings, "MCP_ENABLED", False)` then load the file; also True.
- Rule: `RULE_IDS` contains it, `Rule("deny", None)`, in `NON_GRANTABLE_RULES`; file with a `grant` refused with "non-grantable"; `default: flag` accepted; `_SUBJECTS["tool.not_in_skill"]` equals the exact subject.

### Task 6: Sweep
- `grep -rn "RULE_IDS\|NON_GRANTABLE\|_SUBJECTS\|== 25\|== 10" tests/*.py` and `grep -n "dataclasses.replace(BUILT_IN_POLICY" tests/*.py`; run each hit file (known: `test_action_policy.py:410`, `test_action_audit.py:102`, `test_action_corpus.py`).

## End-to-End Tests

- [ ] `load()` of a YAML file with both sections and `MCP_ENABLED=false`: `get_policy()` exposes them.
- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` (the built-in policy is validated at import, now with the new rule).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_action_config.py tests/test_action_vocabulary.py tests/test_action_policy.py tests/test_action_audit.py tests/test_action_corpus.py tests/test_untouched_app.py
```
Full suite: GitHub CI.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 validated, exposed, in digest | 3, 5 | new file-load and digest tests |
| AC2 four refusals name file + node | 3, 5 | new `test_file_refuses_*mcp*` set |
| AC3 rule, 26 / 11, subject | 1, 2, 4, 5 | `test_action_vocabulary.py` counts; new rule test |
| AC4 `MCP_ENABLED=false` still validates | 3, 5 | new `test_mcp_sections_validate_with_mcp_disabled` |

## Open risks / questions

1. Digest: the new rule changes every policy's digest once; only the MCP keys are conditional. Confirm this reading of "unchanged digest".
2. `_SUBJECTS` edit is in `action_policy.py` (data only).
3. Spec keys optional so PRD-016 tests stay untouched.
4. Docs still say 25 / ten until STORY-021.
