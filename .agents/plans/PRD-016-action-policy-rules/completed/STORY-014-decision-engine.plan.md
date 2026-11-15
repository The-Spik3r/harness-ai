---
story: STORY-014
prd: PRD-016
slug: decision-engine
title: "Decision engine: evaluate(), grants via holds(), most-severe-wins, safe reasons, fail closed"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-016-action-policy-rules
created: 2026-11-15
---

# Plan: Decision engine: evaluate(), grants via holds(), most-severe-wins, safe reasons, fail closed

## Summary

Create `app/services/action_policy.py`, the fold that turns one tool call and one identity into an `ActionDecision`. The pipeline:

1. `action_adapters.map_tool_call` maps the call.
2. `Unknown`, `Malformed` and `Opaque` become one `tool.*` classification each. Each `Operation` in `Operations` goes to the classifier for its kind, and a single `Classification` result (paths, network) is wrapped in a tuple.
3. Each classification is decided as `allow` when `authz.holds(identity, rule.grant)`, otherwise `rule.default`. `tool.opaque` takes `Opaque.decision` instead.
4. The most severe outcome wins (`deny > flag > allow`). The reported rule is the first classification at that severity, in classifier order (D9, Section 6.4).
5. `reason` is built from one fixed subject per rule, a fixed verdict per decision, and the matched `detail` from the call (T11). `policy_digest` is stamped on every decision.
6. Any exception between mapping and folding is caught at the `evaluate` boundary. It is logged at `ERROR` with the tool name and rule, never the arguments, and returned as `deny` / `tool.malformed` (T9).

`action_config` gains two call-time getters, `get_sql_dialect()` and `get_max_argument_characters()`, so the engine never reads `settings`. New suite: `tests/test_action_policy.py`.

## User Story

As the PRD-017 implementer
I want one pure function that takes a tool call and an identity and returns allow, flag or deny with a reason
So that wiring action policy into the response path is plumbing.

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-014-decision-engine.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md`, Sections 4 (Decision engine), 6.2, 6.3, 6.4, 6.7, 6.10 (the shape STORY-015 records), 7 F7, 9.2 T4/T9/T11, 10, 11, 15 D7/D9/D10.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/services/action_policy.py` (new), `app/services/action_config.py` (two getters), tests |
| Story | STORY-014 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design`, whose PRD note limits it to STORY-019 (the Actions view). This story has no UI. The story's `skills: []` agrees. | none |

---

## Binding inputs (orchestrator decisions, applied verbatim)

| Source | Decision | Where in this plan |
|---|---|---|
| STORY-013 plan / story note | The exact call is `classify_shell(op.target, policy.shell_allow, network_allow=policy.network_allow, secret_env=policy.secrets.env.compiled, secret_files=policy.secrets.files.compiled, protected=policy.protected_paths.compiled, workspace_roots=policy.workspace_roots, source_tool=op.source_tool)`. Engine tests assert `cat .env` is `secret.read`, `ls > .git/config` is `fs.write_protected` and `curl evil.com` is `net.unlisted` through `evaluate()` under the built-in policy. | Task 2 `_classify`. Task 4 group G3. |
| STORY-011 plan / story note | `sql`/`shell` return tuples. `classify_write`/`classify_read`/`classify_url` return one `Classification`. The engine normalizes. | Task 2 `_classify`. |
| STORY-008 plan / story note | The dialect comes through an `action_config` getter. It is not an `ActionPolicy` field and not in the digest. The call is `classify_sql(statement, dialect, source_tool=...)`. | Task 1 `get_sql_dialect()`, Task 2. |
| STORY-006 plan decision 3 / story note | `tool.opaque` has no rule default. Its decision is `Opaque.decision`. | Task 2 `_mapped`. |

Verified against the real code (output of a probe run under the built-in policy): `classify_shell("cat .env", ...)` gives `[secret.read '.env', shell.unlisted 'cat']`, `ls > .git/config` gives `[fs.write_protected '.git/config', shell.unlisted 'ls']`, `curl evil.com` gives `[net.unlisted 'evil.com', shell.unlisted 'curl']`, `npm test && rm -rf build` gives `[shell.unlisted 'npm', shell.destructive 'rm -rf']`, `psql -c "DROP TABLE t"` gives `[sql.ddl 'DROP', shell.unlisted 'psql']`, and `classify_sql("DROP TABLE users", None)` gives `[sql.ddl 'DROP']`. So the classifiers already emit the Section 6.4 order ("embedded before the head's own rule", `shell.py:1790-1831`). The engine keeps that order and never re-sorts.

---

## Design decisions (for the implementer and the orchestrator)

### D-1. How the engine gets the policy, the dialect and the argument cap: getters in `action_config`, no new parameters

- `evaluate(call, identity, policy=None)` keeps PRD Section 10's signature exactly. `policy=None` means `action_config.get_policy()` (`action_config.py:741-748`, whose docstring already names this caller).
- The dialect is `action_config.get_sql_dialect() -> Optional[str]`, which returns `settings.ACTION_SQL_DIALECT or None`.
- The cap is `action_config.get_max_argument_characters() -> int`, which returns `settings.ACTION_MAX_ARGUMENT_CHARACTERS`.
- Both getters read at call time, never at import, in the shape of `_check_sql_dialect` (`action_config.py:991-1010`). They do not validate. `load()` already does that, and an unvalidated dialect that reaches `classify_sql` is caught there as `sql.unparsed`, which fails closed (`sql.py:317-326`).
- `evaluate_all(calls, identity, policy=None)` resolves the policy **once** and passes it to each `evaluate`. `policy` is an additive optional parameter beyond Section 10's `evaluate_all(calls, identity)`, which still works unchanged. Every decision in one response therefore carries one policy and one digest.

Justification against the purity rule (Section 6.12: "`action_policy` imports no settings and reads no file") and the Section 10 API:

- Section 10 gives `evaluate` no dialect or cap parameter, and `evaluate_all` no policy parameter at all. Plain arguments would therefore change the internal API that PRD-017 codes against, and would push `settings` reads into PRD-017's request path. A getter keeps the API and puts the read where 6.12 puts *all* configuration: `action_config`.
- `action_policy` itself never names `settings`, opens nothing and touches no database. What it reads is in-memory state: `action_config._policy` through `get_policy()`, two settings attributes through `action_config`'s getters, and `authz.ROLE_PERMISSIONS` through `holds()`. The story's note already calls `get_policy()` "a read of in-memory state, not I/O".
- **The honest limit:** unlike `pattern_detector` and the classifiers, importing `action_policy` *does* load `app.config` transitively, because `action_config` and `authz` import `settings`. This cannot be avoided while `policy=None` defaults to the loaded policy and grants go through `authz.holds()`, both of which the PRD specifies (Sections 4, 6.7, 10).
  - So this module's purity test asserts what is true: no `settings` name in the module, no `open(`/`Path(`/`os.`, and app imports exactly `{action_adapters, action_classifiers, action_config, authz}`.
  - It also runs a behavioural no-I/O check (`builtins.open` and `app.db.database.get_connection` patched to record calls, then a sweep of calls through `evaluate`).
  - It does **not** add the "imports load no settings" subprocess test that the pure modules have (`tests/test_action_adapters.py:661-676`). That test would be false here, and the plan says so rather than weakening it.
- The rejected alternative is a fully pure core, `decide(call, identity, policy, *, dialect, cap, holds)`, plus a wrapper. It adds a second public entry point that nothing needs. Tests can already pin every input: `policy=` is a parameter, the getters read `settings` (monkeypatchable), and `holds` reads `authz.ROLE_PERMISSIONS` (monkeypatchable).

### D-2. `ActionDecision`: the result shape STORY-015 records

A frozen dataclass. Section 6.2's eight fields come first, in 6.2's order, followed by three additions that `record(decisions, identity, audit_id, session_id)` needs. Section 10 gives `record()` no `ToolCall`, so the decision must carry what the row needs.

| Field | Type | Value | Feeds `action_decisions` (6.10) |
|---|---|---|---|
| `tool_call_id` | `str` | `call.id`; `""` if it is not a `str` | `tool_call_id` |
| `tool_name` | `str` | `call.name`; `""` if it is not a `str` | `tool_name` |
| `decision` | `Decision` | the fold | `decision` |
| `rule` | `RuleId` | the reported rule | `rule` |
| `reason` | `str` | D-4 | (API entry, see Q4) |
| `granted_by` | `Optional[str]` | D-3 | `granted_by` |
| `classifications` | `tuple[Classification, ...]` | every one, in order, never empty | `classifications` JSON `[{rule, kind: c.operation.kind or null, detail}]` |
| `policy_digest` | `str` | `action_config.policy_digest(policy)` | `policy_digest` |
| `operations` | `tuple[Operation, ...]` | `Operations.operations`; `()` for unknown, malformed and opaque (PRD Section 4 lists `operations` on `ActionDecision`) | (context) |
| `operation` | `Optional[Operation]` | the reported classification's `operation`, the "target the rule judged"; `None` for `tool.*` | `operation_kind`, `target_preview` |
| `arguments` | `str`, `field(repr=False)` | `call.arguments` as emitted; `""` if it is not a `str` | `arguments_hash`, `arguments_preview` |

- `repr=False` on `arguments` keeps the raw payload, which may hold a secret (T10), out of any `repr` or log line.
- The invariant `rule == c.rule` holds for exactly the reported `c`, and `operation is c.operation`. A test asserts both on every decision.

### D-3. The fold (D9, D10, D7)

- Every classification is decided as follows:
  - `"allow"` with `grant = rule.grant` when `rule.grant is not None and authz.holds(identity, rule.grant)`.
  - Otherwise `rule.default`.
  - `tool.opaque` takes `Opaque.decision` and never consults a rule.
- A decided value outside `DECISIONS` raises an internal `_EngineError`, which the boundary fails closed (D-5). Example: a classifier that returned `tool.opaque`, whose `default` is `None`.
- Severity is `{"allow": 0, "flag": 1, "deny": 2}`. The call's decision is the maximum.
- **Reported rule:** the first classification at the maximum severity, in order. Operations are taken in argument order, and each classifier's own order is kept. **One refinement, only among `allow`s:** a classification that a grant lifted outranks a plain `allow`.
  - The reason is that `SELECT 1; DELETE FROM t WHERE id = 3` for `dba` is allowed *only because of* `action:sql:write`. Reporting `sql.read` with `granted_by=None` would hide the grant from the audit and the Actions view ("the permission that lifted it", F11).
  - The key is `(severity, lifted)`, and the first at the maximum key wins. For `flag` and `deny` the key reduces to D9 exactly, because a grant only ever yields `allow`.
- **`granted_by`** is the reported classification's grant when a grant lifted it. Otherwise it is `None`, which includes every `deny` and `flag` result. This matches 6.2: "the action permission that turned deny/flag into allow".
- `flag` is allowed-and-recorded (D10). The engine only returns it. What to *do* with it is PRD-017's concern.

### D-4. Reasons (T11): one fixed subject per rule and one fixed verdict per decision

- `_SUBJECTS: Mapping[RuleId, str]` (a `MappingProxyType`) has exactly the 25 `RULE_IDS`. A test checks the key set against `RULE_IDS`.
- `_VERDICTS` is `{"deny": "is not permitted", "flag": "is permitted and flagged for review", "allow": "is permitted"}`.
- `reason = f"{subject} {verdict}"`, plus `f": {detail}"` when the reported classification's `detail` is non-empty.
- The PRD's own example fixes `sql.ddl` → `"destructive SQL"`, which gives `"destructive SQL is not permitted: DROP"` (AC 1, PRD 5.1).
- **Why a verdict as well, not one string per rule:** a rule's outcome depends on the decision. `sql.write` is `deny` for `user`, `allow` for `dba`, and `flag` under `{default: flag}`. A single "…is not permitted" string would be false for two of the three. Every possible reason is still a module literal plus the call's fragment, so the story's "the rule's fixed template plus the matched fragment" holds with the template being `(rule, decision)`.
- The verdict names no permission and no role. `granted_by` carries the permission as its own field.
- Subjects (reviewed in the report):

| Rule | Subject | Rule | Subject |
|---|---|---|---|
| `sql.read` | `read-only SQL` | `fs.read` | `reading a file` |
| `sql.write` | `SQL that changes data` | `fs.write_in_workspace` | `writing inside the workspace` |
| `sql.unscoped_write` | `SQL that changes every row` | `fs.write_outside_workspace` | `writing outside the workspace` |
| `sql.ddl` | `destructive SQL` | `fs.write_protected` | `writing a protected path` |
| `sql.dcl` | `SQL that changes permissions` | `net.allowlisted` | `a request to an allowlisted host` |
| `sql.unparsed` | `SQL that cannot be parsed` | `net.unlisted` | `a request to a host that is not allowlisted` |
| `shell.allowlisted` | `an allowlisted command` | `net.unparsed` | `a URL that cannot be parsed` |
| `shell.unlisted` | `a command that is not allowlisted` | `secret.read` | `reading a secret` |
| `shell.destructive` | `a destructive command` | `tool.unknown` | `an unknown tool` |
| `shell.pipe_to_interpreter` | `piping into an interpreter` | `tool.opaque` | `an opaque tool` |
| `shell.inline_interpreter` | `inline interpreter code` | `tool.malformed` | `a tool call that cannot be read` |
| `shell.package_install` | `installing packages` | | |
| `shell.service_control` | `controlling services` | | |
| `shell.unclassifiable` | `a command that cannot be classified` | | |

- **Details**, all taken from the call or as fixed phrases:
  - Classifier details are kept as given. Each classifier's T11 contract says the detail is from the call (`__init__.py:129-131`, `shell.py:184-186`).
  - `tool.unknown` and `tool.opaque` use the tool name truncated to 64 characters.
  - `tool.malformed` from `Malformed` uses `Malformed.detail`, a fixed phrase plus at most a mapping key path, never an argument value (`action_adapters.py:265-271`). This includes `"arguments exceed N characters"`, which names the setting's value. That is not a host, root or allowlist entry (see Q5).
  - `tool.malformed` from the boundary uses the fixed `"classification failed"`.

### D-5. The fail-closed boundary (T9, F7)

- `policy`, its digest, the dialect and the cap are resolved first, outside the `try`. They are configuration rather than model input, and a failure there is a deployment bug that should surface.
- `try:` covers everything from `map_tool_call` to the fold.
- `except Exception as exc:` does two things:
  - It calls `logger.error("action policy: classifying tool %r failed (%s); denied under tool.malformed", tool_name, type(exc).__name__)`.
  - It returns `decision="deny"`, `rule="tool.malformed"`, `classifications=(Classification("tool.malformed", None, "classification failed"),)`, `operations` = whatever was mapped (or `()`), `operation=None` and `granted_by=None`.
- The log line is deliberately narrow:
  - No `exc_info`, and no `str(exc)`. A classifier's exception message or traceback could quote the target, so only the exception's *type* is logged.
  - The tool name is passed through `%r`, so a model-chosen name cannot inject a log line.
- The decision here is a **hard `deny`, not `policy.rules["tool.malformed"].default`**. A deployment may loosen the `tool.malformed` default for unreadable arguments (6.3 lets defaults change). A classifier crash is a bug, not a policy choice, and T9 says "returns deny". See Q3.
- `BaseException` (`KeyboardInterrupt`) is not caught, as in `shell.py:1898`.
- Classifiers are called through their **modules** (`sql.classify_sql`, `shell.classify_shell`, `paths.classify_write`, …) and the adapter through `action_adapters.map_tool_call`. So `monkeypatch.setattr(sql, "classify_sql", boom)` reaches the engine (AC 4).
- A classifier that returns zero classifications for an operation also raises `_EngineError` and fails closed. `classify_shell("")` returns `shell.unclassifiable` today, so this guard should never fire.

### D-6. `tool.opaque` and the other `tool.*` results

| `MappingResult` | `classifications` | decided by |
|---|---|---|
| `Unknown()` | `(Classification("tool.unknown", None, name[:64]),)` | `policy.rules["tool.unknown"]` (non-grantable) |
| `Malformed(detail)` | `(Classification("tool.malformed", None, detail),)` | `policy.rules["tool.malformed"]` (non-grantable) |
| `Opaque(decision)` | `(Classification("tool.opaque", None, name[:64]),)` | `Opaque.decision`, no grant check |

- "Without classification" (AC 3) means the arguments are never read. The adapter returns `Opaque` before the cap and `json.loads` (`action_adapters.py:457-461`). The test passes `arguments="not json"` and still expects `allow`.
- A single `tool.opaque` entry is still recorded, so every decision has at least one classification and `rule` always names one (6.4: "It is recorded with its configured decision"). See Q2.

---

## Patterns to Follow

| Category | File:Lines | Pattern |
|---|---|---|
| NAMING | `app/services/action_adapters.py:1-34` | Module docstring cites PRD sections and decisions and states what is pure and why |
| SCHEMAS | `app/services/action_classifiers/__init__.py:107-131` | Frozen dataclasses with `#:` field comments, closed `Literal` vocabularies (`DECISIONS`, `RULE_IDS`) |
| SCHEMAS | `app/services/action_config.py:170-194` | `ActionPolicy`, `MappingProxyType` constants (`action_config.py:272`) |
| ERRORS | `app/services/action_classifiers/shell.py:1900-1922` | Catch `Exception` at the public boundary, return a fail-closed result, never `BaseException` |
| ERRORS | `app/services/action_adapters.py:280-285, 491-492` | Private exception raised inside, caught only at the boundary |
| CONFIG READS | `app/services/action_config.py:991-1010` | Read the setting at call time, never at import |
| GETTER | `app/services/action_config.py:741-748` | `get_policy()` docstring names its caller |
| LOGGING | `app/services/pii_policy.py:44` | `logger = logging.getLogger(__name__)` |
| GRANT | `app/services/authz.py:168-185` | `holds()` reads `ROLE_PERMISSIONS` only, with no `RBAC_ENABLED` bypass |
| TESTS (purity) | `tests/test_action_adapters.py:641-658` | `"settings" not in vars(mod)`, no `open(`/`Path(`/`os.`, exact set of app imports |
| TESTS (no I/O) | `tests/test_action_paths.py:151-172` | Patch the I/O entry points, then sweep the inputs |
| TESTS (log) | `tests/test_pii_policy.py:60-61`, `tests/test_action_sql.py:349-352` | Filter `caplog.records` by logger name, assert a marker is absent |
| TESTS (policy variants) | STORY-006 plan AC 4 / `tests/test_action_config.py` | `dataclasses.replace(BUILT_IN_POLICY, rules=MappingProxyType({**BUILT_IN_POLICY.rules, "shell.unlisted": Rule("flag", "action:shell:exec")}))` |
| TESTS (env) | `tests/test_action_paths.py:17-20` | `os.environ.setdefault("OPENROUTER_API_KEY"/"ADMIN_TOKEN")` before app imports |
| FIXTURE | `tests/conftest.py:715-726` | Autouse pins `ACTION_POLICY_FILE=""` and restores `action_config._policy` |

### Naming
```python
# SOURCE: app/services/action_adapters.py:246-274
@dataclass(frozen=True)
class Operations:
    """The operations a call performs, in argument order. Never empty."""

    operations: tuple[Operation, ...]
...
MappingResult = Union[Operations, Opaque, Unknown, Malformed]
```

### Error Handling
```python
# SOURCE: app/services/action_classifiers/shell.py:1900-1922
    target = command if isinstance(command, str) else ""
    op = Operation(kind="shell", target=target, source_tool=source_tool)
    try:
        ...
        return tuple(out)
    except Exception:
        return (Classification("shell.unclassifiable", op, _first_word(command)),)
```

### Tests
```python
# SOURCE: tests/test_action_adapters.py:641-658
def test_action_adapters_stays_pure():
    source = inspect.getsource(action_adapters)
    assert "settings" not in vars(action_adapters)
    assert "open(" not in source
    assert "Path(" not in source
    assert "os." not in source
    imports = [line for line in source.splitlines()
               if line.startswith("import ") or line.startswith("from ")]
    app_targets = {re.split(r"\s+", line)[1] for line in imports
                   if re.match(r"(from|import) app(\.|\s|$)", line)}
    assert app_targets == {"app.services.action_classifiers"}
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/action_policy.py` | CREATE | `ActionDecision`, `evaluate`, `evaluate_all`, the fold, reasons, fail-closed boundary |
| `app/services/action_config.py` | UPDATE | `get_sql_dialect()`, `get_max_argument_characters()`; module docstring's entry-point list and `_check_sql_dialect` docstring point at them |
| `tests/test_action_policy.py` | CREATE | The engine suite (ACs 1-5, binding shell assertions, purity) |
| `tests/test_action_config.py` | UPDATE | Two getter tests (additive; no existing assertion changes) |
| `.agents/stories/PRD-016-action-policy-rules/STORY-014-decision-engine.md` | UPDATE (this planner) | `plan`, `status: in-progress`, `updated` |
| `.agents/PRDs/PRD-016-action-policy-rules/index.md` | REGENERATE (this planner) | Board |

Dependency order: Task 1, then Task 2, then Task 3, then Task 4. No `chat_ui/` change, no schema change, no new dependency.

---

## Tasks

### Task 1: `action_config` getters

- **File**: `app/services/action_config.py`
- **Action**: UPDATE
- **Implement**: Add two functions after `get_policy()` (`:741-748`).
  - `get_sql_dialect() -> Optional[str]`: `return settings.ACTION_SQL_DIALECT or None`.
    - Docstring: PRD-016 Sections 6.9 and 9.3, the STORY-008 plan's open question 2 and the STORY-008 orchestrator decision. It is not an `ActionPolicy` field, so it is not in the digest.
    - Read at call time. Validated by `load()` (`_check_sql_dialect`), not here. An unvalidated value reaching `classify_sql` is `sql.unparsed` (fails closed).
    - Its caller is `action_policy.evaluate()` (STORY-014).
  - `get_max_argument_characters() -> int`: `return settings.ACTION_MAX_ARGUMENT_CHARACTERS`.
    - Docstring: PRD-016 Sections 4 and 9.3. The ceiling `map_tool_call` checks before `json.loads`. The `≥ 1` check lives in `app/config.py`'s validator. Read at call time.
  - Update the module docstring's "Three entry points (PRD-016 Section 10)" paragraph (`:8-17`) with one line on the two getters: they serve `action_policy` so that it reads no `settings` (Section 6.12).
  - Change the last sentence of `_check_sql_dialect`'s docstring (`:999-1000`) to "reaches the classifier through `get_sql_dialect()` (STORY-014)".
- **Mirror**: `app/services/action_config.py:741-748` (getter docstring naming its caller), `:991-1010` (call-time read).
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: `app/services/action_policy.py`

- **File**: `app/services/action_policy.py`
- **Action**: CREATE
- **Implement**:
  - **Module docstring:** PRD-016 Sections 4, 6.2, 6.4, 6.7, F7, T4, T9, T11, D7, D9 and D10.
    - The pipeline (map → classify → decide → fold).
    - The Section 6.4 order comes from the classifiers and is never re-sorted.
    - The `(severity, lifted)` refinement (D-3).
    - The reason composition (D-4).
    - The fail-closed boundary (D-5).
    - The purity paragraph from D-1, including the honest transitive-`settings` limit.
    - Not this module's work: what PRD-017 does with `flag`/`deny` (D4, brief D1) and audit recording (STORY-015, `action_audit.record`).
  - **Imports:**
    - `import logging`
    - `from dataclasses import dataclass, field`
    - `from types import MappingProxyType`
    - `from typing import TYPE_CHECKING, Callable, Mapping, Optional, Sequence`
    - `from app.services import action_adapters, action_config, authz`
    - `from app.services.action_classifiers import DECISIONS, RULE_IDS, Classification, Decision, Operation, RuleId`
    - `from app.services.action_classifiers import network, paths, shell, sql`
    - `ToolCall` and the four results through `action_adapters.`
    - `if TYPE_CHECKING: from app.services.identity import Identity`, indented, so the top-level import set stays the four modules.
    - Use string annotations `"Identity"` and `"action_config.ActionPolicy"` where needed, or plain `action_config.ActionPolicy`.
  - `logger = logging.getLogger(__name__)`.
  - **`ActionDecision`:** the frozen dataclass of D-2, with `#:` field comments.
  - **`_SEVERITY`, `_VERDICTS`, `_SUBJECTS`:** `MappingProxyType` constants (D-3, D-4). A module-level `assert set(_SUBJECTS) == set(RULE_IDS)` is **not** used; the test covers it.
  - **`_NAME_DETAIL_CAP = 64`.**
  - **`class _EngineError(Exception)`**, internal only.
  - **`_classify(op, policy, dialect) -> tuple[Classification, ...]`:** a dispatch on `op.kind` that always calls through the modules.
    - `"sql"` → `sql.classify_sql(op.target, dialect, source_tool=op.source_tool)`
    - `"shell"` → **the binding call, verbatim**: `shell.classify_shell(op.target, policy.shell_allow, network_allow=policy.network_allow, secret_env=policy.secrets.env.compiled, secret_files=policy.secrets.files.compiled, protected=policy.protected_paths.compiled, workspace_roots=policy.workspace_roots, source_tool=op.source_tool)`
    - `"fs_write"` → `(paths.classify_write(op.target, policy.protected_paths.compiled, policy.workspace_roots, source_tool=op.source_tool),)`
    - `"fs_read"` → `(paths.classify_read(op.target, policy.secrets.files.compiled, source_tool=op.source_tool),)`
    - `"http"` → `(network.classify_url(op.target, policy.network_allow, source_tool=op.source_tool),)`
    - Any other kind raises `_EngineError`, as does an empty result. Use an `if`/`elif` chain or a dict of small lambdas that look the function up at call time. Either way, monkeypatching the module attribute must work.
  - **`_decide(c, identity, policy, opaque) -> tuple[Decision, Optional[str]]`:** returns `(decision, grant_or_None)` per D-3.
    - `tool.opaque` → `(opaque.decision, None)`.
    - Otherwise `rule = policy.rules[c.rule]`, which raises `KeyError` for an unknown rule, caught by the boundary.
    - Grant via `authz.holds(identity, rule.grant)`.
    - Validate the result is in `DECISIONS`, else `_EngineError`.
  - **`_reason(rule, decision, detail) -> str`** (D-4).
  - **`_fold(classifications, decided) -> int`:** returns the index of the reported classification. Key `(severity, lifted)`, first max wins.
  - **`evaluate(call, identity, policy=None) -> ActionDecision`:**
    - Resolve `policy`, `digest = action_config.policy_digest(policy)`, `dialect = action_config.get_sql_dialect()` and `cap = action_config.get_max_argument_characters()`.
    - Compute `tool_call_id`, `tool_name` and `arguments` with `isinstance(..., str)` guards.
    - Inside the `try`:
      - Call `result = action_adapters.map_tool_call(call, policy.tools, policy.opaque_tools, cap)`.
      - Build `operations` and `classifications` per D-6, or per operation via `_classify` for `Operations`.
      - Decide each, fold, and build the `ActionDecision`.
    - `except Exception` per D-5.
    - Docstring: Section 10 signature. Never raises for any input a model can produce. The `policy=None` semantics.
  - **`evaluate_all(calls, identity, policy=None) -> tuple[ActionDecision, ...]`:** `policy = action_config.get_policy() if policy is None else policy`, then `return tuple(evaluate(c, identity, policy) for c in calls)`. Input order is preserved, and each call is decided independently (PRD Section 4; mixed outcomes are PRD-017 D1).
- **Mirror**: `app/services/action_adapters.py:440-500` (boundary and result building), `app/services/action_classifiers/shell.py:1862-1922` (docstring and catch), `app/services/action_config.py:170-194` (frozen dataclass documentation style).
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"` and `.venv/Scripts/python -c "import os; os.environ.setdefault('OPENROUTER_API_KEY','x'); os.environ.setdefault('ADMIN_TOKEN','y'); from app.services.action_policy import evaluate; from app.services.action_adapters import ToolCall; from app.services.identity import Identity; print(evaluate(ToolCall('c1','query','{\"sql\": \"DROP TABLE users\"}'), Identity('u','user')))"` (expect `deny`, `sql.ddl`, reason `destructive SQL is not permitted: DROP`).

### Task 3: getter tests in `tests/test_action_config.py`

- **File**: `tests/test_action_config.py`
- **Action**: UPDATE (additive only; the module docstring gains a "STORY-014: the two getters" sentence)
- **Implement**: A new section `# --- STORY-014: the getters action_policy reads ---` after the STORY-008 block (`:1135+`).
  - `test_get_sql_dialect_reads_the_setting_at_call_time`: `""` gives `None`; `"postgres"` gives `"postgres"`, set via `monkeypatch.setattr(settings, ...)` after import.
  - `test_get_max_argument_characters_reads_the_setting_at_call_time`: the default is `100_000`, and a patched `7` gives `7`.
  - `test_the_dialect_is_not_in_the_digest`: the same `policy_digest()` under two dialects. This pins the STORY-008 decision.
- **Mirror**: `tests/test_action_config.py:1142-1157`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_config.py -q -p no:cacheprovider`

### Task 4: `tests/test_action_policy.py`

- **File**: `tests/test_action_policy.py`
- **Action**: CREATE
- **Implement**: Module docstring as in the sibling suites: PRD-016 STORY-014, the sections covered, the fact that expected values are written as literals, and what is not covered (recording, STORY-015; corpora, STORY-017/018).
  - Header: `os.environ.setdefault` for the two keys, then imports.
  - Helpers:
    - `_call(name, args_obj_or_str, id="c1")` → `ToolCall`, JSON-dumping a dict.
    - `USER = Identity("u", "user")`, `DBA = Identity("d", "dba")`, `ADMIN = Identity("a", "admin")`.
    - A `dba_matrix` fixture: `monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {**authz.ROLE_PERMISSIONS, "dba": {"query:submit", "action:sql:write"}})`.
    - `_with_rules(**changes)`, `_with(**fields)`: built with `dataclasses.replace` + `MappingProxyType`.
  - Groups:
    - **G1 (AC 1)**:
      - `query` `{"sql": "DROP TABLE users"}` for `USER` gives `deny`, `sql.ddl`, reason `"destructive SQL is not permitted: DROP"` exactly, and `granted_by is None`.
      - `SELECT * FROM users WHERE id = 1` gives `allow`, `sql.read`.
      - Tool name `postgres_query` (unknown) gives `deny`, `tool.unknown`, `operations == ()`, `operation is None`.
    - **G2 (AC 2, D7)** with `dba_matrix`, over `DELETE FROM t WHERE id = 3`:
      - `USER` gives `deny` / `sql.write` / `None`.
      - `DBA` gives `allow` / `sql.write` / `"action:sql:write"`.
      - `DELETE FROM t` gives `deny`, `sql.unscoped_write`, `granted_by None` for both.
      - `DELETE FROM t WHERE 1=1` gives `deny`, `sql.unscoped_write`.
      - **RBAC off** (`monkeypatch.setattr(settings, "RBAC_ENABLED", False)`), see Q1:
        - (a) Built-in matrix (no `dba_matrix`): `DBA` gives `deny`. This is "deny for dba too": the escape hatch hands out no grant. Parametrize over **every grantable rule**, with one call each and the built-in policy, for `USER`, `DBA` and `ADMIN`. The decision equals the rule's built-in default (T4, PRD 11 "every grantable rule decided by its default"). The calls:
          - `sql.write`: `INSERT INTO t VALUES (1)`.
          - `sql.ddl`: `DROP TABLE t`.
          - `shell.unlisted`: `make release`.
          - `shell.inline_interpreter`: `python -c 1`.
          - `shell.package_install`: `npm install x`.
          - `shell.service_control`: `systemctl stop x`.
          - `fs.write_outside_workspace`: `write` `/etc/hosts`.
          - `net.unlisted`: `webfetch` `https://evil.example/`.
          - `secret.read`: `read` `.env`.
        - (b) With `dba_matrix` and RBAC off: `DBA` still gives `allow`. `holds()` ignores the flag in both directions (STORY-003 AC 2). `USER` and `ADMIN` give `deny`.
      - **Mixed-allow refinement (D-3)**: `SELECT 1; DELETE FROM t WHERE id = 3` for `DBA` gives `allow`, `sql.write`, `granted_by="action:sql:write"`. For `USER` it gives `deny`, `sql.write`.
    - **G3 (binding shell assertions, built-in policy, tool `bash`)**:
      - `cat .env` gives `deny` / `secret.read`, detail `.env`.
      - `ls > .git/config` gives `deny` / `fs.write_protected`.
      - `curl evil.com` gives `deny` / `net.unlisted`, and `shell.unlisted` is also among the classifications.
      - The docstring states that this proves every keyword argument reaches `classify_shell`.
      - Add a spy test: `monkeypatch.setattr(shell, "classify_shell", spy)`, where `spy` records kwargs and delegates. It asserts that the kwargs are exactly `policy.network_allow`, `policy.secrets.env.compiled`, `policy.secrets.files.compiled`, `policy.protected_paths.compiled`, `policy.workspace_roots` (compared with `is`) and `source_tool == "bash"`, and that the positional `shell_allow is policy.shell_allow`.
    - **G4 (AC 3)**:
      - `npm test && rm -rf build` with `_with(shell_allow=("npm test",))` gives `deny`, `shell.destructive`, `[c.rule for c in d.classifications] == ["shell.allowlisted", "shell.destructive"]`.
      - `make release` under `_with_rules(**{"shell.unlisted": Rule("flag", "action:shell:exec")})` gives `flag`, `shell.unlisted`, reason `"a command that is not allowlisted is permitted and flagged for review: make"`. Under the built-in policy it gives `deny`.
      - `todowrite` with `arguments="not json"` under `_with(opaque_tools=MappingProxyType({"todowrite": "allow"}))` gives `allow`, `tool.opaque`, `operations == ()`, and `classifications == (Classification("tool.opaque", None, "todowrite"),)`.
      - `todowrite: flag` gives `flag`.
      - `psql -c "DROP TABLE t"` gives `sql.ddl`, not `shell.unlisted` (PRD 11).
    - **G5 (AC 4, T9)**: parametrize the raising target over:
      - `(sql, "classify_sql")` via `query`
      - `(shell, "classify_shell")` via `bash`
      - `(paths, "classify_write")` via `write`
      - `(paths, "classify_read")` via `read`
      - `(network, "classify_url")` via `webfetch`
      - `(action_adapters, "map_tool_call")`
      - `(authz, "holds")` via `query` with a grantable rule

      Each raises `RuntimeError("boom " + MARK)`, where `MARK = "secret_marker_9f3"` is also inside the arguments.
      - Assert `deny` / `tool.malformed` and `granted_by is None`.
      - Assert exactly one record on logger `app.services.action_policy` with `levelno == logging.ERROR`. Its `getMessage()` contains the tool name and `"tool.malformed"`, and contains neither `MARK` nor the raw arguments. `record.exc_info is None` and `record.exc_text is None`. `MARK` is not in `caplog.text`.
      - Also: a deployment policy with `tool.malformed: {default: allow}` still gives `deny` on a raise (D-5, Q3). A classifier returning `()` gives `tool.malformed`.
    - **G6 (AC 5, T11)**:
      - (a) `set(action_policy._SUBJECTS) == set(RULE_IDS)` and `set(_VERDICTS) == set(DECISIONS)`.
      - (b) A sweep. A list of about 40 calls covering every rule id the engine can produce: every `RULE_IDS` member at least once, which the test asserts as the union of the reported and classified rules. Evaluate them for `USER` and `DBA` under a sentinel policy: `_with(network_allow=("sentinel-allowed.example", "*.sentinel-wild.example"), workspace_roots=("/sentinel/root",), shell_allow=("sentinelcmd", "ls", "git status"))`. None of the calls mentions a sentinel, except one `net.allowlisted` call to `https://a.sentinel-wild.example/` whose detail is the call's own host, excluded from the leak assertion with a comment. For every decision:
        - `reason == f"{_SUBJECTS[rule]} {_VERDICTS[decision]}" + (f": {detail}" if detail else "")`, with `detail` the reported classification's.
        - No sentinel string in `reason`.
        - `d.policy_digest == action_config.policy_digest(sentinel_policy)`.
        - The D-2 invariant `d.operation is d.classifications[i].operation` for the reported `i`.
      - (c) Under the built-in policy with no `policy=` argument, `d.policy_digest == action_config.policy_digest()`. After `action_config._policy = <changed one rule>` (restored by the conftest fixture), the digest differs and equals the new one.
      - (d) `evaluate_all([a, b, c], USER)` returns a tuple with `tool_call_id`s in input order, e.g. `("c3", "c1", "c2")` with mixed decisions. It equals `tuple(evaluate(x, USER) for x in calls)`. `evaluate_all([], USER) == ()`.
    - **G7 (shape and severity order)**:
      - `ActionDecision` field names are the D-2 tuple, and it is frozen.
      - `arguments` is not in `repr(d)`.
      - Malformed inputs all give `deny` / `tool.malformed` (PRD 11): `"not json"`, `"[]"`, `"{}"`, and over the cap via `monkeypatch.setattr(settings, "ACTION_MAX_ARGUMENT_CHARACTERS", 10)`.
      - Cross-operation order: Cline `run_commands` `{"commands": ["ls", "rm -rf /"]}` gives `shell.destructive`, reported second-operation-first-deny, and both operations are in `operations`.
      - `npm test` alone, allowlisted, gives `allow` / `shell.allowlisted`.
      - Relative `write` `src/a.ts` gives `allow`.
      - `cat ~/.aws/credentials` for a role granted `action:secret:read` gives `allow`, `granted_by="action:secret:read"`.
      - A non-`str` `call.name` gives `deny` / `tool.malformed`, `tool_name == ""`, and no raise.
      - The SQL dialect reaches the classifier: spy `sql.classify_sql`, set `settings.ACTION_SQL_DIALECT = "postgres"`, and assert the spy got `"postgres"`. With `""` it gets `None`.
    - **G8 (purity, D-1)**:
      - `test_action_policy_stays_pure`: `"settings" not in vars(action_policy)`, no `open(`/`Path(`/`os.` in the source, and the column-0 `app` import lines equal exactly these three literals: `from app.services import action_adapters, action_config, authz`, `from app.services.action_classifiers import DECISIONS, RULE_IDS, Classification, Decision, Operation, RuleId` (or whatever names Task 2 settles on, written out literally) and `from app.services.action_classifiers import network, paths, shell, sql`. The indented `TYPE_CHECKING` import of `Identity` is excluded by the column-0 filter, as `tests/test_action_paths.py:401-407` does. The test docstring names the four allowed modules and why (D-1).
      - `test_evaluate_does_no_io`: warm up by evaluating the sweep once (sqlglot dialect modules load lazily). Then patch `builtins.open`, `pathlib.Path.read_text` and `app.db.database.get_connection` to *record* the call rather than raise; a raise would be swallowed by the boundary. Run the sweep again and assert the record list is empty and no decision has detail `"classification failed"`.
- **Mirror**: `tests/test_action_paths.py:1-50, 151-172, 390-407`, `tests/test_action_adapters.py:641-658`, `tests/test_pii_policy.py:60-61`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_policy.py -q -p no:cacheprovider`

---

## End-to-End Tests

No HTTP surface or UI in this story. The engine has no call site until PRD-017 (Section 6.1). The end-to-end checks are:

- [ ] The probe in Task 2's Validate prints a `deny` / `sql.ddl` decision with the exact reason.
- [ ] `from app.main import app` imports cleanly.
- [ ] `tests/test_action_policy.py` G3 proves the shell keyword wiring through `evaluate()`.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_policy.py tests/test_action_config.py tests/test_action_vocabulary.py tests/test_action_adapters.py tests/test_untouched_app.py -q -p no:cacheprovider
```

- The targeted set is the new suite, `action_config`'s own suite (a modified module), the vocabulary and adapter suites (the engine's direct inputs), and the `test_untouched_app.py` guard.
- No pre-existing test function is renamed or removed, so the `test_pii_redaction_integration.py` census is not needed.
- The classifier suites are unchanged by this story and need not run.
- Full suite: deferred to the orchestrator (user decision).

---

## Acceptance Criteria

(Copied from story `STORY-014`)

- [ ] **AC 1:** Built-in policy, `user`.
  - `query` / `DROP TABLE users` gives `deny`, `sql.ddl`, `reason="destructive SQL is not permitted: DROP"`, `granted_by=None`.
  - `SELECT * FROM users WHERE id = 1` gives `allow` / `sql.read`.
  - An unknown tool gives `deny` / `tool.unknown`.
  - Covered by G1.
- [ ] **AC 2:** Test RBAC matrix with `dba` holding `action:sql:write`.
  - `DELETE FROM t WHERE id = 3` gives `deny` for `user` and `allow` with `granted_by="action:sql:write"` for `dba`.
  - `DELETE FROM t` gives `deny` for both.
  - With `RBAC_ENABLED=false`, `dba` gets `deny` too (D7).
  - Covered by G2. The RBAC-off reading is in Q1.
- [ ] **AC 3:** Shell and opaque tools.
  - `npm test && rm -rf build`, with `npm test` allowlisted, gives `deny` as `shell.destructive`, with both segments' classifications kept.
  - `shell.unlisted: {default: flag}` makes `make release` `flag`.
  - `opaque_tools: {todowrite: allow}` makes `todowrite` `allow` / `tool.opaque` without classification.
  - Covered by G4.
- [ ] **AC 4:** A classifier that raises gives `deny` / `tool.malformed`, logged at `ERROR` with the tool name and rule but not the arguments. Covered by G5.
- [ ] **AC 5:** Reasons, digest and order.
  - Every `reason` is the fixed template plus the call's fragment, and never contains a configured host, root or allowlist entry.
  - Every decision carries `policy_digest()` of the policy in force.
  - `evaluate_all` preserves input order.
  - Covered by G6.
- [ ] Binding: `cat .env` → `secret.read`, `ls > .git/config` → `fs.write_protected`, `curl evil.com` → `net.unlisted`, all through `evaluate()`. Covered by G3.
- [ ] Purity: no `settings` import and no I/O in `action_policy`. Covered by G8.
- [ ] All tasks completed.
- [ ] Backend server starts without error.
- [ ] Follows existing patterns.

---

## Risks

| Risk | Mitigation |
|---|---|
| The boundary swallows an `AssertionError` raised by a test's patched I/O, hiding I/O | G8 records calls instead of raising and asserts no `"classification failed"` detail |
| sqlglot loads dialect modules lazily on first use, which looks like I/O in G8 | Warm-up sweep before patching |
| A future classifier returns rules out of Section 6.4 order | The engine relies on classifier order by design (D9). G4 and G3 pin the observed orders, so drift fails here |
| `tool.malformed`'s configured default diverges from the boundary's hard `deny` | Documented (D-5). Q3 |
| `arguments` held on the decision carries a secret into `repr` or logs | `field(repr=False)`, and the boundary log has no exception text. T10 accepts the audit preview itself |
| Unvalidated `ACTION_SQL_DIALECT` in tests that never call `load()` | `classify_sql` maps an unknown dialect to `sql.unparsed` (fails closed) |

## Open questions for the orchestrator

1. **AC 2 "with `RBAC_ENABLED=false`, then `deny` for `dba` too".** Read literally against the test matrix, this contradicts `holds()` as built and STORY-003 AC 2, under which a role that holds the permission gets `True` with RBAC off. The plan's reading follows PRD 11 / T4:
   - Under the built-in matrix, RBAC off grants nothing, so `dba`, `user` and `admin` all fall to the rule's default for every grantable rule.
   - With the test matrix, `dba` keeps its grant, because the flag is ignored in both directions.
   - If the orchestrator wants the literal reading, `holds()` would have to change, which reverses STORY-003. Not recommended.
2. **`tool.opaque` "without classification".** The plan records one `Classification("tool.opaque", None, name)` and never reads the arguments. `classifications == ()` is the alternative, at the cost of the "`rule` always names a recorded classification" invariant and an empty audit JSON.
3. **Boundary decision.** The plan uses a hard `deny`, even when a deployment set `tool.malformed: {default: allow}`. The alternative is to honour the configured default.
4. **For STORY-015/016.** The Section 6.10 table has no `reason` column, while the Section 10 API entry shows `reason`. Since `reason` is a pure function of `(rule, decision, detail)`, STORY-015 can store it or STORY-016 can recompute it. STORY-015 decides. The `ActionDecision` additions (`operations`, `operation`, `arguments`) exist so that `record()` keeps the Section 10 signature.
5. **The `tool.malformed` reason for an oversized call says `arguments exceed N characters`** (adapter text, `action_adapters.py:464-466`). It names a configured limit, which is not a host, root or allowlist entry. The adapter's own comment says it is not a secret. Kept as is.
6. **The `(severity, lifted)` tie-break among `allow`s** (D-3) refines D9's "first at that severity" so that a grant that was needed is not hidden. Drop it to get the literal D9 behaviour.
