---
story: STORY-006
prd: PRD-016
slug: action-config-loader
title: "action_config, part 1: ActionPolicy model, built-in policy, get_policy(), digest, both lifespans"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-016-action-policy-rules
created: 2026-11-15
---

# Plan: action_config, part 1: ActionPolicy model, built-in policy, get_policy(), digest, both lifespans

## Summary

Create `app/services/action_config.py`, modelled on `app/services/pattern_config.py`. It holds `ActionConfigError`, frozen `Rule`, `Globs`, `Secrets` and `ActionPolicy` dataclasses, and module-level built-in data (the 25 rules of PRD Section 6.3, the protected-path globs of 6.3, and the secret env/file globs of 6.3/6.6). It reuses STORY-004's `BUILT_IN_TOOLS` and sets `opaque_tools` to empty (orchestrator decision). One `_validate(source, spec)` function builds and checks every policy. The built-in policy goes through it at import, and STORY-007 will send the file through it too, so the floor cannot drift into a shape a file would be refused for (PRD F8). The module also adds a glob translator of its own (`*`, `?`, `**`), compiled once, case-insensitive (T6). `get_policy()` returns the built-in policy until `load()` rebinds `_policy`. `policy_digest(policy=None)` is a SHA-256 over canonical JSON (sorted keys) of the policy's source values. In this story `load()` handles only the empty setting, which reads no file. Any non-empty `ACTION_POLICY_FILE` fails closed with `ActionConfigError` naming the path; it never falls back to the built-in policy silently. `action_config.load()` is registered in both lifespans after `authz.load()`. A conftest autouse fixture pins `ACTION_POLICY_FILE=""` and restores `_policy`.

## User Story

As a security admin
I want a built-in action policy that denies every dangerous class out of the box and is in force from the first boot
So that a deployment that configures nothing is protected rather than open

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-006-action-config-loader.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md`. Section 4 Configuration (lines 84-91), 6.2 (184-218), 6.3 table (224-252), 6.5 (260-270), 6.6 (272-326, esp. `secrets:` 317-319 and the two replacement rules 322-324), 6.11 (418, 428, 444), 6.12 (468-477), F8 (502-503), 9.2 T5/T6/T7 (547-549), 9.3 (557-566), 10 internal API (611-613)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/services/action_config.py` (new), `app/main.py`, `chat_ui/chat_ui/chat_ui.py`, `tests/conftest.py`, tests |
| Story | STORY-006 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch) |

Dependencies STORY-003, STORY-004 (and STORY-005, for the setting) are all `status: done`.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI aesthetics). This story has no UI, and its frontmatter has `skills: []`. | — |

---

## Patterns to Follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| MODULE DOCSTRING | `app/services/pattern_config.py:1-34` | Names its entry points, the wholesale rule, both lifespans and why, and what it deliberately leaves to other stories |
| ERROR CLASS | `app/services/pattern_config.py:53-70` | A docstring listing every way configuration can be wrong; "Startup fails. There is no silent fallback"; describes the two-exception seam (`PatternCompileError`, here `ToolMappingError`) |
| CLOSED VOCAB | `app/services/pattern_config.py:73-95` | Vocabulary tuples imported, never re-declared (`_ROLES = get_args(Role)`); here `RULE_IDS`, `DECISIONS`, `NON_GRANTABLE_RULES` from `action_classifiers/__init__.py:83-104` and `authz.ACTION_PERMISSIONS` (`app/services/authz.py:29-38`) |
| FROZEN MODELS | `app/services/pattern_config.py:98-162` | `@dataclass(frozen=True)`, source strings and their `compiled` counterparts as parallel tuples (`PatternList.patterns` / `.compiled`) |
| BUILT_IN / _policy / get_policy | `app/services/pattern_config.py:255-273` | `BUILT_IN_POLICY = _build_built_in()` public and never rebound; `_policy = BUILT_IN_POLICY` private; `get_policy()` returns `_policy` and never raises |
| MESSAGE HELPERS | `app/services/pattern_config.py:312-317` | `_fail(path, *parts)` -> `"<SOURCE>: part: part"`; `_allowed(values)` -> sorted, comma-joined |
| LOAD, EMPTY PATH | `app/services/pattern_config.py:583-590` | `path = settings.X; if not path: return` — settings read at call time, never at import |
| IMMUTABLE MAPPING | `app/services/action_adapters.py:488-554` | `MappingProxyType({...})` for built-in data; `BUILT_IN_TOOLS` is placed in the policy as is (`:555-556`) |
| TOOL MAPPING SEAM | `app/services/action_adapters.py:89-98` | `ToolMappingError` is re-raised by `action_config` as `ActionConfigError` naming file + `tools.<name>` (STORY-007 uses it; STORY-006 only type-checks built `ToolMapping`s) |
| FastAPI LIFESPAN | `app/main.py:10`, `app/main.py:13-22` | One import line in `app.services`, calls in order |
| REFLEX LIFESPAN | `chat_ui/chat_ui/chat_ui.py:13`, `:204-229` | `app.register_lifespan_task(module.load)` with a "Same bypass (PRD-xxx STORY-yyy): ..." comment; Reflex runs tasks in registration order |
| CONFTEST RESET | `tests/conftest.py:673-696` | Autouse fixture pins the setting to `""` and saves and restores `_policy` by plain assignment, not monkeypatch |
| LIFESPAN TESTS (FastAPI) | `tests/test_main.py:221-237` (`_pattern_startup`), `:270-285` (no file read when unset), `:358-376` (call-order recording) | |
| LIFESPAN TESTS (Reflex) | `tests/test_chat_ui_startup_guard.py:44-111` (`_CHECK_SCRIPT` probe: registration, index order, call result), `:127-140` (`_empty_rbac_env` pins settings via env), `:194-208` | |
| UNIT TESTS | `tests/test_pattern_config.py:61-71` (`_reset_policy`), `:103-116` (no-file-read assertion via patched `Path.read_text`), `:213-217` (get_policy without load) | |

### Naming
```python
# SOURCE: app/services/pattern_config.py:255-273
#: The policy in force when nothing is configured. Public and never rebound --
#: `load()` rebinds `_policy`, not this -- so a test, and STORY-007's assertion
#: that `examples/patterns.yaml` parses to the same thing, can name it.
BUILT_IN_POLICY = _build_built_in()

_policy = BUILT_IN_POLICY

def get_policy() -> PatternPolicy:
    return _policy
```

### Error Handling
```python
# SOURCE: app/services/pattern_config.py:312-317
def _fail(path: str, *parts: str) -> PatternConfigError:
    return PatternConfigError(f"PATTERNS_FILE '{path}': " + ": ".join(parts))

def _allowed(values) -> str:
    return ", ".join(sorted(values))
```

### Tests
```python
# SOURCE: tests/test_main.py:270-285
def test_lifespan_reads_no_patterns_file_when_unset(_pattern_startup, monkeypatch):
    monkeypatch.setattr(settings, "PATTERNS_FILE", "")
    def _no_path(*args, **kwargs):
        raise AssertionError("pattern_config built a Path while PATTERNS_FILE is unset")
    monkeypatch.setattr(pattern_config, "Path", _no_path)
    with TestClient(app) as test_client:
        assert pattern_config.get_policy() is BUILT_IN_POLICY
```
```python
# SOURCE: tests/test_chat_ui_startup_guard.py:62-74
load = chat_ui_module.pattern_config.load
result["patterns_load_registered"] = load in tasks
result["patterns_load_adjacent"] = (
    load in tasks
    and chat_ui_module.authz.load in tasks
    and tasks.index(load) == tasks.index(chat_ui_module.authz.load) + 1
)
```

---

## Design decisions (for the implementer and the orchestrator)

1. **Lifespan position: after `pii_policy.load()`, before `authz.check_bootstrap()`, in both lifespans.** This is "after `authz.load()`" (AC 5, PRD 6.11 line 418). It cannot go directly after `authz.load()`. `tests/test_chat_ui_startup_guard.py:64-68` asserts that `pattern_config.load` is at index `authz.load + 1`, and `:80-84` asserts that `pii_policy.load` is at index `pattern_config.load + 1`. Inserting between them would break two pre-existing assertions for no benefit, because `action_config` reads no other loader's state: it validates grants against the constant `authz.ACTION_PERMISSIONS`, not against `ROLE_PERMISSIONS`. `app/main.py` uses the same slot, so the two lifespans stay in the same order.
2. **`load()` with a non-empty `ACTION_POLICY_FILE` raises `ActionConfigError` in this story.** The message names the setting and the path, and says the built-in policy is used only when it is unset. Reading the file is STORY-007's work. Ignoring the file would be the "silent fallback" that PRD 4 (line 88) and 6.12 forbid. The tests built on this assert only the type and the path, which is also what STORY-007's "unreadable file" error will contain, so no test has to be rewritten in STORY-007.
3. **`Rule.default` is `Optional[Decision]`, and `None` appears only on `tool.opaque`.** PRD 6.3 gives `tool.opaque` the default "(per entry)": its decision is the `opaque_tools` entry's (`action_adapters.Opaque.decision`, `action_adapters.py:240-244`), and no `rules:` value applies to it. `_validate` enforces that `tool.opaque` has `default is None` and `grant is None`, and that every other rule has a `Decision` default. STORY-014's engine never reads `rules["tool.opaque"].default`. STORY-007 should refuse a `rules: tool.opaque:` entry in a file, which follows from the same check after the merge.
4. **`protected_paths` is a field of `ActionPolicy`, which the story's field list omits.** AC 2 needs the protected-path globs in the policy, and STORY-011's classifier needs them as data. PRD 6.6 and 9.3 define no file section for them, so they are built-in-only in this PRD (a file key for them would be an "unknown key" in STORY-007). Recorded as a deviation.
5. **Built-in secret globs.** `secrets.env` uses PRD 6.3's seven patterns, in table order: `*KEY*`, `*SECRET*`, `*TOKEN*`, `*PASSWORD*`, `*CREDENTIAL*`, `AWS_*`, `OPENROUTER_*`. The 6.6 sample shows six because it is a deployment example and omits `OPENROUTER_*`. `secrets.files` uses PRD 6.6's eight, because 6.3 gives no file list: `.env*`, `*.pem`, `*.key`, `id_*`, `.aws/**`, `.ssh/**`, `.npmrc`, `.pypirc`.
6. **Glob semantics (owned here, consumed by STORY-011/013).** The supported syntax is literal characters, `*` (any run within one segment), `?` (one non-`/` character), and `**` as a whole segment (zero or more segments when it is not last, one or more when it is last). The following are refused with a `_GlobError`, which `_validate` wraps as `ActionConfigError` naming the node: an empty glob, an empty segment (`a//b`, a trailing `/`), a leading `/`, `**` mixed into a segment (`a**`), and `[`, `]` or `\`. Character classes would be a second syntax to explain. **Path globs** (protected paths, `secrets.files`) compile to `(?:^|/)` + body + `$` with `re.IGNORECASE`. They are matched with `.search()` against a normalized `/`-separated path, so `.env*` matches `/home/dev/projects/app/.env.local` and `.git/**` matches `.git/config` and `a/.git/x`. **Name globs** (`secrets.env`) compile to `^` + body + `$` with `re.IGNORECASE` and must not contain `/`. Case-insensitivity follows T6 for protected paths. It also applies to secret files and env names (STORY-013 asks for case-insensitive env matching), because matching more only adds denials, so it fails closed. Python is 3.12 (`.venv`), so `glob.translate` (3.13) is not available, and the module translates globs itself, as the story asks.
7. **Digest.** `policy_digest(policy=None)` takes the policy in force when called with no argument, which is the PRD 10 signature (line 613); passing a policy explicitly makes AC 4 testable. It returns `"sha256:" + sha256(json.dumps(_canonical(policy), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()`. `_canonical` holds the source values only: rules as `{id: {"default", "grant"}}`, tools via `dataclasses.asdict(mapping)` (tuples become lists), `opaque_tools`, the three lists, `protected_paths` patterns, and `secrets` `{env, files}` patterns. It never includes the compiled regexes. List order is kept, because declared order is part of the policy; dict key order is not. The digest is computed on every call (about 50 small entries, microseconds). Memoizing is left to STORY-014 if profiling ever shows a need. A second piece of module state would be one more thing that could disagree with `_policy`.
8. **`_validate(source, spec)` is the single builder.** `spec` is a plain `Mapping` with exactly the keys `rules`, `tools`, `opaque_tools`, `shell_allow`, `network_allow`, `workspace_roots`, `protected_paths`, `secret_env` and `secret_files`. `rules` maps an id to a `(default, grant)` pair. `tools` holds already-built `ToolMapping`s. The other values are sequences or mappings of strings. `source` is the message prefix: `"built-in action policy"` now, and `"ACTION_POLICY_FILE '<path>'"` in STORY-007. **Checks in this story** (each an `ActionConfigError` via `_fail(source, node, rule)`): the spec has exactly those keys; the rules are complete and closed (every `RULE_IDS` member present, none unknown; message enumerates with `_allowed`); `default` is in `DECISIONS`; `grant` is `None` or in `authz.ACTION_PERMISSIONS`; no grant on a `NON_GRANTABLE_RULES` member (T5); the `tool.opaque` shape from decision 3; `tools` is a non-empty mapping of non-empty `str` to `ToolMapping` (T7); `opaque_tools` is a mapping of non-empty `str` to a `DECISIONS` member, disjoint from `tools`; every glob translates (decision 6). **Left to STORY-007, named as such in the docstring:** reading and parsing the file, document and section key checks, the per-id `rules:` merge and wholesale sections, building `ToolMapping` from YAML and wrapping `ToolMappingError`, absolute `workspace.roots`, the syntax of `network.allow` entries, `shell.allow` entries with operators, and duplicate keys (`strict_yaml`). The `ACTION_SQL_DIALECT` cross-check belongs to STORY-008. The built-in lists are empty, so none of these deferred checks could fail on the built-in policy.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/action_config.py` | CREATE | Error, models, glob translator, built-in data, `_validate`, `BUILT_IN_POLICY`, `_policy`, `get_policy()`, `policy_digest()`, `load()` (empty setting only) |
| `app/main.py` | UPDATE | Import `action_config` (line 10); call `action_config.load()` after `pii_policy.load()` (line 19), before `authz.check_bootstrap()` |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | Import `action_config` (line 13); `app.register_lifespan_task(action_config.load)` after the `pii_policy.load` registration (line 224), before `authz.check_bootstrap` (line 229), with a "Same bypass (PRD-016 STORY-006)" comment |
| `tests/conftest.py` | UPDATE | Import `action_config` beside `pattern_config` (line 86); new autouse `_default_action_policy` after `_default_pii_policy` (line 699-710): pins `ACTION_POLICY_FILE=""`, saves/restores `action_config._policy` |
| `tests/test_action_config.py` | CREATE | AC 1-4 plus `_validate` floor and glob cases |
| `tests/test_main.py` | UPDATE | New PRD-016 STORY-006 block appended at the end (after line 400): call order, no file read, fail-closed boot |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | Probe gains action_config keys; `_empty_rbac_env` pins `ACTION_POLICY_FILE=""`; module docstring lists the fifth concern; two new tests. No existing assertion changes |

No `.env.example`, README, `examples/` or `requirements.txt` changes (STORY-007/STORY-020).

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create `app/services/action_config.py`

- **File**: `app/services/action_config.py`
- **Action**: CREATE
- **Implement** (top to bottom):
  - **Module docstring**, in the voice of `pattern_config.py:1-34`. The module owns all of the action policy's configuration I/O, and the engine modules stay pure (PRD 6.12, line 473). Entry points: `load()`, `get_policy()`, `policy_digest()` (PRD 10). It is called once at startup in both lifespans, because the Reflex `api_transformer` mount bypasses `app.main`'s lifespan (PRD 6.12, line 471). The built-in policy goes through the same `_validate` as a file (F8). Say what STORY-006 covers (built-in, digest, empty setting) and what STORY-007 adds (file load, `rules:` per-id merge, wholesale sections, full Section 9.3 validation) and STORY-008 (the dialect check).
  - **Imports**: `hashlib`, `json`, `re`, `dataclasses` (`dataclass`, `asdict`), `types.MappingProxyType`, `typing` (`Any`, `Mapping`, `Optional`); `from app.config import settings`; `from app.services.authz import ACTION_PERMISSIONS`; `from app.services.action_adapters import BUILT_IN_TOOLS, ToolMapping`; `from app.services.action_classifiers import DECISIONS, NON_GRANTABLE_RULES, RULE_IDS, Decision, RuleId`. Do not import `Path` or `yaml`; they arrive with STORY-007.
  - **`class ActionConfigError(Exception)`**: the docstring lists every way the policy can be wrong, including the STORY-007 ones, as PRD 9.3 does. Say "Startup fails, never a silent fallback to the built-in policy", and describe the `ToolMappingError` seam (`action_adapters.py:89-98`).
  - **Models** (all `@dataclass(frozen=True)`, each docstring citing PRD sections):
    - `Rule(default: Optional[Decision], grant: Optional[str])`. The docstring covers decision 3 (`None` only on `tool.opaque`) and the "a rule with no grant cannot be lifted by any role" paragraph (PRD 6.3, line 252).
    - `Globs(patterns: tuple[str, ...], compiled: tuple[re.Pattern, ...])`, parallel tuples as in `PatternList` (`pattern_config.py:98-115`). The docstring gives the match contract from decision 6 (path globs: `.search()` on a normalized path; name globs: `.search()`/`.fullmatch()` against a name, since both are anchored).
    - `Secrets(env: Globs, files: Globs)`.
    - `ActionPolicy(rules: Mapping[RuleId, Rule], tools: Mapping[str, ToolMapping], opaque_tools: Mapping[str, Decision], shell_allow: tuple[str, ...], network_allow: tuple[str, ...], workspace_roots: tuple[str, ...], protected_paths: Globs, secrets: Secrets)`. The docstring says that mappings are `MappingProxyType`, so the built-in policy cannot be edited in place, and gives the PRD 6.5 note on why the three tuples are empty in the built-in policy.
  - **Glob translator**: `class _GlobError(ValueError)` (private: only `_validate` sees it). `_translate_glob(glob: str) -> str` returns the regex body, with the exact rules of decision 6. `_compile_path_glob(glob) -> re.Pattern` uses `"(?:^|/)" + body + "$"`, and `_compile_name_glob(glob) -> re.Pattern` uses `"^" + body + "$"` and refuses `/`. Both use `re.IGNORECASE`. Segment construction: a `**` that is not last emits `(?:[^/]+/)*` and swallows its following `/`; a `**` that is last emits `[^/]+(?:/[^/]+)*` after the preceding `/`; `*` becomes `[^/]*`; `?` becomes `[^/]`; everything else goes through `re.escape`. Comment the T6 reason for `IGNORECASE`, and why a pattern without `/` matches at any depth (`.env` inside `app/` is still `.env`).
  - **Built-in data** (module-level, private, in PRD order, each block commented with its PRD source line):
    - `_BUILT_IN_RULES: Mapping[str, tuple[Optional[str], Optional[str]]]` holds the 25 `(default, grant)` pairs of PRD 6.3 lines 226-250, in `RULE_IDS` order. Grants use the `authz.PERMISSION_ACTION_*` constants (no string literals; `authz.py:8-9`). The values: `sql.read` allow/None; `sql.write` deny/`action:sql:write`; `sql.unscoped_write` deny/None; `sql.ddl` deny/`action:sql:ddl`; `sql.dcl` deny/None; `sql.unparsed` deny/None; `shell.allowlisted` allow/None; `shell.unlisted` deny/`action:shell:exec`; `shell.destructive` deny/None; `shell.pipe_to_interpreter` deny/None; `shell.inline_interpreter` deny/`action:shell:exec`; `shell.package_install` deny/`action:shell:exec`; `shell.service_control` deny/`action:shell:exec`; `shell.unclassifiable` deny/None; `fs.read` allow/None; `fs.write_in_workspace` allow/None; `fs.write_outside_workspace` deny/`action:fs:write`; `fs.write_protected` deny/None; `net.allowlisted` allow/None; `net.unlisted` deny/`action:net:egress`; `net.unparsed` deny/None; `secret.read` deny/`action:secret:read`; `tool.unknown` deny/None; `tool.opaque` None/None; `tool.malformed` deny/None. That is 9 granted, 10 non-grantable and 6 with nothing to lift.
    - `_BUILT_IN_PROTECTED_PATHS` holds the 11 globs of PRD 6.3 line 243: `.env*`, `*.pem`, `*.key`, `id_*`, `.aws/**`, `.ssh/**`, `.git/**`, `.github/workflows/**`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/**`.
    - `_BUILT_IN_SECRET_ENV` (7) and `_BUILT_IN_SECRET_FILES` (8), from decision 5.
    - The comment on the opaque-tools entry: built-in `opaque_tools` is **empty** (orchestrator decision, STORY-004 plan). The `none` rows of `tests/corpora/actions/SOURCES.md` (OpenCode `todowrite`, `task`, `question`, `websearch`, ...; Cline `search_codebase`, `ask_question`, ...) are `tool.unknown` (deny) until a deployment names them. That is the D1 floor.
  - **Message helpers**: `_fail(source: str, *parts: str) -> ActionConfigError` returns `ActionConfigError(f"{source}: " + ": ".join(parts))`, and `_allowed(values)`, both in the shape of `pattern_config.py:312-317`. `_BUILT_IN_SOURCE = "built-in action policy"`.
  - **`_SPEC_KEYS`** is a frozenset of the nine spec keys.
  - **`_validate(source: str, spec: Mapping[str, Any]) -> ActionPolicy`** runs the checks of decision 8, in this order: spec keys; rules (completeness first, then per rule in `RULE_IDS` order: unknown id, decision, grant vocabulary, non-grantable, `tool.opaque` shape); tools; opaque_tools; globs (protected, then env, then files). Node names in messages: `rules: 'sql.dcl'`, `tools: 'bash'`, `opaque_tools: 'x'`, `protected_paths: 'a[b]'`, `secrets.env: ...`, `secrets.files: ...`, so they match the YAML node paths STORY-007 will report. Example message: `built-in action policy: rules: 'sql.dcl': grant 'action:sql:write' is not allowed on a non-grantable rule (non-grantable: fs.write_protected, ...)`. It builds `MappingProxyType(dict(...))` for rules/tools/opaque_tools and `tuple(...)` for the lists. The docstring has a bullet list "checked here" and a bullet list "added by STORY-007", taken from decision 8, and says this is the one constructor of `ActionPolicy` outside tests.
  - **`BUILT_IN_POLICY = _validate(_BUILT_IN_SOURCE, {...})`**, with `tools=BUILT_IN_TOOLS` (the same object), `opaque_tools={}`, the three lists `()`, and the globs above. Then `_policy = BUILT_IN_POLICY`. Use the comments from `pattern_config.py:255-263`, adapted.
  - **`get_policy() -> ActionPolicy`** has the `pattern_config.get_policy()` contract: returns `_policy` and never raises before `load()`. It cites the PRD 6.12 line 473 rule ("every test that never boots an app gets the floor") and STORY-014's `evaluate(policy=None)`.
  - **`_canonical(policy) -> dict`** and **`policy_digest(policy: Optional[ActionPolicy] = None) -> str`**, per decision 7. The docstring says the digest is over the effective policy and not over file bytes, so comments and key order do not change it. It is stamped on every `ActionDecision` and audit row (PRD 4 line 90, 6.2).
  - **`load() -> None`**. Read `settings.ACTION_POLICY_FILE` at call time. If it is empty, return, reading no file. Otherwise `raise ActionConfigError(f"ACTION_POLICY_FILE '{path}': loading a policy file is not available in this build (PRD-016 STORY-007); unset ACTION_POLICY_FILE to run the built-in policy")`. The docstring explains decision 2 and the "rebound as the last statement" contract STORY-007 must keep (`pattern_config.py:549-556`).
- **Mirror**: `app/services/pattern_config.py:1-317, 549-590`; `app/services/action_adapters.py:488-556`
- **Validate**: `.venv/Scripts/python -c "from app.services import action_config as c; print(len(c.BUILT_IN_POLICY.rules), c.policy_digest())"` should print `25 sha256:<64 hex>`

### Task 2: Register `load()` in the FastAPI lifespan

- **File**: `app/main.py`
- **Action**: UPDATE
- **Implement**: line 10 becomes `from app.services import action_config, authz, pattern_config, pii_policy, pii_redactor, pipeline_executor`. Insert `action_config.load()` after `pii_policy.load()` (line 19) and before `authz.check_bootstrap()` (line 20). No comment is needed: the existing lifespan has none, and the reasoning lives in the chat_ui comment.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 3: Register `load()` in the Reflex lifespan

- **File**: `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Implement**: line 13 becomes the same import with `action_config` first. After `app.register_lifespan_task(pii_policy.load)` (line 224), add:
  ```python
  # Same bypass (PRD-016 STORY-006): without this the chat UI would hold the
  # built-in action policy while the API holds ACTION_POLICY_FILE's -- and a
  # broken file would stop uvicorn but not the deployment serving traffic.
  # After authz.load (PRD-016 Section 6.11); placed after pii_policy.load so
  # pattern_config and pii_policy keep their adjacency to authz.load.
  app.register_lifespan_task(action_config.load)
  ```
- **Validate**: run the probe test in Task 7. The import check in the brief (`.venv/Scripts/python -c "import chat_ui.chat_ui.chat_ui"`) may not be the right path. The probe in `tests/test_chat_ui_startup_guard.py:114-124` imports `chat_ui.chat_ui` with `cwd=chat_ui/` and `PYTHONPATH=chat_ui;.`. If the brief's command fails, use that and report it.

### Task 4: conftest autouse reset

- **File**: `tests/conftest.py`
- **Action**: UPDATE
- **Implement**: add `from app.services import action_config  # noqa: E402` beside line 86. After `_default_pii_policy` (ends at line 710), add:
  ```python
  @pytest.fixture(autouse=True)
  def _default_action_policy(monkeypatch):
      """Every test starts under the built-in action policy (PRD-016 STORY-006).

      `_default_pattern_policy`'s shape and reason: a developer's `.env` with
      ACTION_POLICY_FILE set must not decide which policy a test runs under,
      and `load()` rebinds `_policy` with a plain assignment, which
      `monkeypatch` would not undo.
      """
      monkeypatch.setattr(settings, "ACTION_POLICY_FILE", "")
      original = action_config._policy
      yield
      action_config._policy = original
  ```
- **Validate**: covered by Task 7.

### Task 5: `tests/test_action_config.py`

- **File**: `tests/test_action_config.py`
- **Action**: CREATE
- **Implement**: The module docstring cites PRD-016 STORY-006 and lists what is deliberately not covered: file loading, the merge, and Section 9.3's file rules (STORY-007). Begin with the `os.environ.setdefault` pair (`tests/test_pattern_config.py:24-27`). Pin the expected values as **literals in the test**, not imported from the module, because these tests are about the PRD table and would prove nothing by comparing the module with itself.
  - `_PRD_6_3_RULES`: a literal dict of the 25 `(default, grant)` pairs, with grant strings written out (`"action:sql:write"` and so on).
  - **AC 1** `test_load_reads_no_file_when_action_policy_file_unset(monkeypatch)`: set `ACTION_POLICY_FILE=""`. Patch `builtins.open`, `pathlib.Path.open`, `pathlib.Path.read_text` and `pathlib.Path.read_bytes` with a function that raises `AssertionError`. Assert `load() is None` and `get_policy() is BUILT_IN_POLICY`. The docstring explains why it patches `pathlib`/`open` and not `action_config.Path`: the module has no `Path` yet, and STORY-007 adds it.
  - `test_load_with_a_policy_file_set_fails_closed(tmp_path, monkeypatch)`: `ACTION_POLICY_FILE=str(tmp_path / "missing.yaml")`. Expect `ActionConfigError` whose message contains the path and `ACTION_POLICY_FILE`, and `get_policy() is BUILT_IN_POLICY` afterwards. The docstring says: no silent fallback (decision 2); the assertion is chosen to hold under STORY-007 too, where a missing file is unreadable.
  - **AC 2**: `test_built_in_rules_are_prd_section_6_3` (dict equality with `_PRD_6_3_RULES`, plus `tuple(BUILT_IN_POLICY.rules) == RULE_IDS` and `len == 25`); `test_the_ten_non_grantable_rules_have_no_grant` (parametrized over `sorted(NON_GRANTABLE_RULES)`, plus `len(NON_GRANTABLE_RULES) == 10`); `test_every_grant_is_an_action_permission`; `test_tool_opaque_has_no_default_of_its_own` (decision 3); `test_built_in_tools_are_story_004s_built_in_tools` (`BUILT_IN_POLICY.tools is BUILT_IN_TOOLS`); `test_built_in_opaque_tools_is_empty`, whose docstring states the orchestrator decision (the `none` tools of SOURCES.md are `tool.unknown`, deny, until a deployment names them, the D1 floor) and which also asserts that `map_tool_call(ToolCall("c1", name, "{}"), policy.tools, policy.opaque_tools, settings.ACTION_MAX_ARGUMENT_CHARACTERS)` is `Unknown()` for `todowrite`, `task`, `question`, `search_codebase` and `ask_question`; `test_built_in_protected_path_globs_are_prd_section_6_3` (the 11-tuple literal); `test_built_in_secret_globs_are_prd_sections_6_3_and_6_6` (env 7-tuple, files 8-tuple; the docstring explains decision 5); `test_built_in_workspace_network_and_shell_lists_are_empty` (PRD 6.5); `test_every_built_in_glob_is_compiled_once` (`len(compiled) == len(patterns)`, every item an `re.Pattern`).
  - **Glob behaviour** (decision 6), parametrized: protected-path matches for `.env`, `./.env`-normalized `.env`, `.ENV.local`, `/home/dev/projects/app/.env.local`, `.github/workflows/ci.yml`, `.git/config`, `a/.git/HEAD`, `id_rsa`, `x.pem`, `C:/Users/u/.ssh/id_ed25519`, `Jenkinsfile`; non-matches for `src/env.ts`, `.gitignore`, `x.pem.txt`, `docs/github/workflows.md`. Env name matches for `AWS_SECRET_ACCESS_KEY`, `openrouter_api_key`, `GITHUB_TOKEN`, `DB_PASSWORD`; non-matches for `PATH`, `HOME`. Secret files match `.npmrc` and `a/.pypirc`. These pin the compiled contract, not a classifier (STORY-011/013 own classification).
  - **AC 3** `test_get_policy_before_load_returns_the_built_in_policy`: in a subprocess (`sys.executable -c`, `cwd=REPO_ROOT`, env with `OPENROUTER_API_KEY`/`ADMIN_TOKEN` setdefaults and `ACTION_POLICY_FILE=""`), import `app.services.action_config` and print `get_policy() is BUILT_IN_POLICY`. A fresh interpreter is the only place where `load()` has provably never run. Also add the in-process check in the shape of `tests/test_pattern_config.py:213-217`.
  - **AC 4**: `test_policy_digest_is_stable` (called twice, same value, matches `^sha256:[0-9a-f]{64}$`, and `policy_digest() == policy_digest(BUILT_IN_POLICY)`); `test_policy_digest_changes_with_one_rule_default` (use `dataclasses.replace(BUILT_IN_POLICY, rules=MappingProxyType({**BUILT_IN_POLICY.rules, "shell.unlisted": Rule("flag", "action:shell:exec")}))` and assert the digests differ; also parametrize over a changed grant and a non-empty `network_allow`); `test_policy_digest_ignores_key_order_and_identity` (build a second policy through `_validate` with the rules dict in reversed order and assert `is not` and an equal digest).
  - **`_validate` floor** (decision 8). Use a `_spec(**overrides)` helper that returns the built-in spec dict. Each case asserts `ActionConfigError`, the source prefix, the node and the rule. Cases: a missing rule; an unknown rule id (`sql.nuke`, message lists allowed ids); default `"block"`; grant `"action:sql:everything"`; a grant on each of the ten non-grantable rules (parametrized); `tool.opaque` with `default="allow"`; `tools={}`; a tool value that is not a `ToolMapping`; `opaque_tools={"x": "maybe"}`; `opaque_tools={"bash": "allow"}` (also in `tools`); a bad glob, parametrized over `a[b]`, `a**`, `/etc/**`, `a//b`, `""`; and an env glob containing `/`. The module docstring says STORY-007 adds the file-level versions of these.
  - `test_built_in_policy_is_immutable`: assigning to `BUILT_IN_POLICY.rules["sql.read"]` raises `TypeError`, and `BUILT_IN_POLICY.shell_allow = ("x",)` raises `dataclasses.FrozenInstanceError`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_config.py -q -p no:cacheprovider`

### Task 6: FastAPI lifespan tests

- **File**: `tests/test_main.py`
- **Action**: UPDATE (append a block after line 400; no existing test is touched)
- **Implement**: add `import app.services.action_config as action_config` and `from app.services.action_config import ActionConfigError` to the imports (lines 18-24). Keep the existing `BUILT_IN_POLICY` name, which is pattern_config's, and refer to `action_config.BUILT_IN_POLICY` in the new block. Under the header `# PRD-016 STORY-006 -- action_config.load() in app.main's lifespan.`, reuse `_pattern_startup` (line 221) because it already pins RBAC off, PII off and temp_db:
  - `test_lifespan_runs_action_config_load_after_authz_load` uses the `_recording` shape of lines 362-376 over `authz.load` and `action_config.load`, and asserts `calls == ["authz", "action_config"]`.
  - `test_lifespan_keeps_the_built_in_action_policy_when_unset`: `ACTION_POLICY_FILE=""`; inside `TestClient(app)`, `action_config.get_policy() is action_config.BUILT_IN_POLICY` and `/health` returns 200.
  - `test_lifespan_fails_when_action_policy_file_cannot_be_loaded(tmp_path)`: `ACTION_POLICY_FILE=str(tmp_path / "missing.yaml")`, expect `pytest.raises(ActionConfigError)` around `with TestClient(app): pass`, the path in the message, and the built-in policy still in force. It is durable across STORY-007 (decision 2).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_main.py -q -p no:cacheprovider`

### Task 7: Reflex lifespan tests

- **File**: `tests/test_chat_ui_startup_guard.py`
- **Action**: UPDATE
- **Implement**:
  - Module docstring (lines 3-23): "Four lifespan concerns" becomes "Five", adding a bullet for PRD-016 STORY-006's `action_config.load()`, and add `action_config.load()` to the duplicated list at line 19. Docstring only; no assertion changes.
  - `_CHECK_SCRIPT`: after the pii_policy block (line 102), add
    ```python
    # PRD-016 STORY-006. After authz.load (PRD Section 6.11), before the
    # bootstrap guard's database read.
    action_load = chat_ui_module.action_config.load
    result["action_load_registered"] = action_load in tasks
    result["action_load_order_ok"] = (
        action_load in tasks
        and tasks.index(chat_ui_module.authz.load) < tasks.index(action_load)
        < tasks.index(chat_ui_module.authz.check_bootstrap)
    )
    try:
        action_load()
        result["action_raised"] = None
    except Exception as exc:
        result["action_raised"] = type(exc).__name__
    ```
  - `_empty_rbac_env` (lines 127-140): add `env["ACTION_POLICY_FILE"] = ""` with a "PRD-016 STORY-006: stated rather than inherited" comment.
  - New block header `# PRD-016 STORY-006 -- action_config.load() as a chat UI lifespan task.`, with `test_action_config_load_registered_after_authz_load_as_chat_ui_lifespan_task` (registered and order ok) and `test_action_config_load_is_a_noop_when_action_policy_file_unset` (`action_raised is None`). Add a third, `test_action_config_load_fails_chat_ui_startup_when_a_file_is_set`, with `{**_empty_rbac_env, "ACTION_POLICY_FILE": str(tmp_path / "missing.yaml")}`, asserting registration and `action_raised == "ActionConfigError"` (the `:211-223` reasoning: registration plus raise is what makes it a startup claim).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_chat_ui_startup_guard.py -q -p no:cacheprovider` (needs the libSQL dev server on 8080)

### Task 8: Targeted regression

Run in one invocation:
`PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_config.py tests/test_main.py tests/test_chat_ui_startup_guard.py tests/test_action_adapters.py tests/test_pattern_config.py tests/test_untouched_app.py -q -p no:cacheprovider`

`test_action_adapters.py` covers the module whose `BUILT_IN_TOOLS` is now imported by `action_config`; its purity subprocess test (`tests/test_action_adapters.py:604-640`) must still show that `action_adapters` loads no settings. `action_config` imports `action_adapters`, never the other way round. `test_pattern_config.py` runs because conftest gains a sibling autouse fixture. `test_untouched_app.py` is the guard for touched app files. Full suite: deferred to orchestrator (user decision).

---

## End-to-End Tests

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` prints OK
- [ ] `.venv/Scripts/python -c "from app.services import action_config as c; print(len(c.BUILT_IN_POLICY.rules), c.policy_digest())"` prints `25 sha256:...`, and the same digest twice across two runs (deterministic across processes: no `id()`, no set ordering in the canonical form)
- [ ] `ACTION_POLICY_FILE=/nonexistent.yaml` makes both lifespans refuse to start with `ActionConfigError` naming the path (Tasks 6 and 7)
- [ ] With the setting unset, `TestClient(app)` boots and `/health` returns 200 (Task 6)

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_config.py tests/test_main.py tests/test_chat_ui_startup_guard.py tests/test_action_adapters.py tests/test_pattern_config.py tests/test_untouched_app.py -q -p no:cacheprovider
```

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Inserting `action_config.load` directly after `authz.load` would break `tests/test_chat_ui_startup_guard.py:64-68` / `:80-84` adjacency assertions | Placed after `pii_policy.load` (decision 1). AC 5 only requires "after `authz.load()`", and the probe asserts exactly that order |
| A developer's `.env` sets `ACTION_POLICY_FILE`, and every lifespan test then fails on the fail-closed `load()` | conftest autouse `_default_action_policy` pins it to `""` in-process, and `_empty_rbac_env` pins it for the subprocess probe |
| The interim fail-closed `load()` could surprise an operator on the epic branch | Nobody sets the variable yet (STORY-005 added it; `.env.example` is STORY-020's). The message names the setting and how to unset it, and STORY-007 replaces the branch before any release |
| Glob semantics decided here constrain STORY-011/013 (e.g. `id_*` also matches `src/id_utils.py`: a deny on a write to that file) | The `id_*` pattern comes from the PRD table and was kept as written. The match contract is written in `Globs`' docstring and pinned by tests, so STORY-011 can see exactly how its patterns match. Over-matching only denies (fails closed) |
| `Optional` default on `Rule` leaks into STORY-014's typing | `None` only on `tool.opaque`, enforced by `_validate`; STORY-014 resolves `tool.opaque` from `Opaque.decision` and never reads that default. Flagged to the orchestrator (decision 3) |
| `action_config` importing `authz` pulls `app.db.database` in at import | `pattern_config` is already imported in the same places, and `authz` is already imported by both lifespans. `action_config` is not a pure module (PRD 6.12), so only the pure modules' import guards matter, and those are unaffected |
| `re.Pattern` equality in `ActionPolicy.__eq__` | Patterns compare equal on the same source and flags, which `pattern_config`'s `policy == BUILT_IN_POLICY` (`tests/test_main.py:265`) already relies on. The digest never depends on it |

---

## Acceptance Criteria

(Copied from story `STORY-006`)

- [ ] Given `ACTION_POLICY_FILE=""`, when `action_config.load()` runs, then no file is opened (asserted with a path that would fail if read) and `get_policy()` returns `BUILT_IN_POLICY`. (Tasks 1, 5: `test_load_reads_no_file_when_action_policy_file_unset`; Task 6 lifespan variant)
- [ ] Given `BUILT_IN_POLICY`, when inspected, then every one of the 25 rules has the default and grant of PRD Section 6.3, the ten non-grantable rules have no grant, the tool mappings are STORY-004's `BUILT_IN_TOOLS`, the protected-path and secret globs are those of Sections 6.3 and 6.6, and `workspace.roots`, `network.allow` and `shell.allow` are empty. (Tasks 1, 5; opaque_tools empty stated in `test_built_in_opaque_tools_is_empty`)
- [ ] Given `get_policy()` called before `load()` has ever run, when called, then it returns `BUILT_IN_POLICY` and does not raise (the `pattern_config.get_policy()` contract). (Task 5, subprocess + in-process)
- [ ] Given `policy_digest()`, when called twice on the same policy, then it returns the same `sha256:<hex>`; given two policies that differ in one rule's default, then the digests differ. (Task 5)
- [ ] Given `app/main.py` and `chat_ui/chat_ui/chat_ui.py`, when the app boots, then `action_config.load()` runs in both lifespans, after `authz.load()`. (Tasks 2, 3, 6, 7)
- [ ] All tasks completed
- [ ] Backend imports without error
- [ ] Follows existing patterns
