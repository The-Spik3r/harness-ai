---
story: STORY-005
prd: PRD-011
slug: pattern-config-load-and-validate
title: "pattern_config: built-in policy, YAML loading, startup validation"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-011-pattern-policy        # all stories commit here, no per-story branch
created: 2026-09-22
---

# Plan: `pattern_config` — built-in policy, YAML loading, startup validation

## Summary

Add one new module, `app/services/pattern_config.py`, and one new test module, `tests/test_pattern_config.py`. The module holds the three frozen dataclasses of PRD Section 6.2 (`PatternList`, `Profile`, `PatternPolicy`), a built-in policy reproducing today's seven patterns split into the two lists of PRD Section 6.3, a `load()` that reads `PATTERNS_FILE` with `yaml.safe_load` and **replaces** the built-in policy wholesale, a `get_policy()` that returns the built-in policy when `load()` has never run, and `PatternConfigError` — the one exception every malformed-file rule raises, always naming the offending list or profile and the rule that failed.

The shape is `app/services/authz.py`'s `load()` / `AuthzConfigError` (`app/services/authz.py:61-97`), line for line where it can be: an empty setting returns before any file is read, the module-level policy is rebound wholesale and never merged, and every failure is a startup exception rather than a silent fallback (PRD Sections 6.3, 6.9). What this module adds over `authz` is *depth* — `authz` validates one flat vocabulary of permission strings; this validates a two-level document with per-node key sets, two closed enums, a cross-reference from profiles to lists, and a compile step per pattern.

Nothing calls `load()` yet: STORY-007 registers it in both lifespans, and STORY-008's `inspect()` is the first reader of a compiled pattern. That is the same "no production caller in this story" posture STORY-002, STORY-003 and STORY-004 each held, and it is what keeps this commit revertible.

**The story's hard edge is scope, not code.** Profiles are parsed here only as far as the acceptance criteria demand — unknown keys, `lists:` resolved to real `PatternList` objects, an empty `profiles:` refused — and their `roles:` map is *stored unvalidated*. Role and action validation, the empty-`roles:` rule, `PATTERN_PROFILE_DEFAULT`'s cross-check and `get_profile()` are all STORY-006's, named in its own acceptance criteria. See Decision D-C, the decision most likely to be got wrong by building too much.

## User Story

As a platform operator
I want the pattern lists loaded from a file I control and validated at startup
So that I can change policy without a code change and a broken file stops the boot instead of silently disabling protection

## Story Reference

- Story file: `.agents/stories/PRD-011-pattern-policy/STORY-005-pattern-config-load-and-validate.md`
- PRD: `.agents/PRDs/PRD-011-pattern-policy/PRD.md` — Sections 4 (Configuration), 6.2, 6.3, 6.9, 7 (F3), 8, 9.2 (T4, T5, T7), 9.3, 11 (Functional requirements), 12 Phase 2, 14 (Risks 3, 7)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (new module; no production caller until STORY-007) |
| Complexity | HIGH |
| Systems Affected | `app/services/pattern_config.py` (new), `tests/` (new module). No existing production file is edited |
| Story | STORY-005 |
| PRD | PRD-011 |
| Epic Branch | `epic/PRD-011-pattern-policy` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` contains exactly one skill, `frontend-design`, whose `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one" (`.agents/skills/frontend-design/SKILL.md:2-3`). This story adds a configuration loader and pytest cases and touches no UI. The story frontmatter agrees (`skills: []`), its Technical Notes close with "Skills: none applicable", and no other `SKILL.md` exists whose description matches this story's domain.

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

---

## Findings from Exploration

Each finding was run against the checked-out tree, not inferred.

### F-1 — The two lists of PRD Section 6.3 reproduce the characterization corpus **exactly**, verified by execution

Story AC 1 requires the built-in policy's verdicts to match `tests/test_pattern_characterization.py` for every case outside STORY-001's declared flip set. That claim was not taken on trust. A prototype built the two lists (`injection`, `scope: everywhere`; `keywords`, `scope: outside_code`) with STORY-002's `compile_pattern`, applied STORY-003's `strip_code_spans` per scope, walked lists then patterns in declared order, and ran over all 19 rows of `_CASES` (`tests/test_pattern_characterization.py:57-105`):

```
total 19 mismatches 0
pattern set equal: True 7
```

Every one of the 15 non-flip rows returns the verdict pinned today, and all 4 rows of `PRD_011_FLIP_CASES` (`tests/test_pattern_characterization.py:137-160`) return their declared *after* verdict. That includes the two rows nobody could have predicted from reading alone:

- `"please override and enable admin mode"` → `"admin mode"`, the list-order precedence case (`tests/test_pattern_characterization.py:99`). It survives only because `keywords` declares `execute code, admin mode, override` in **that** order, which is why Task 3 spells the patterns out in PRD Section 6.3's order and the test asserts order rather than set membership.
- `"Here is the diff:\n```java\n@Override\n…\n```\n"` → `None`, which is a *predicted* flip: `PRD_011_FLIP_CASES`'s own comment (`tests/test_pattern_characterization.py:147-152`) says it "depends on STORY-005 giving the built-in `keywords` list `scope: outside_code`, as PRD Section 6.3 specifies. If STORY-005 declares it `everywhere` instead, this row leaves the flip list." This story pays that debt: `scope: outside_code` it is, and the prototype confirms the row flips.

The consequence for Task 7 is concrete: the AC 1 test can be written as a parametrized walk over the *imported* `_CASES` and `PRD_011_FLIP_CASES` with a local mini-walker, and it will pass. It does not need a hand-copied corpus that can drift.

### F-2 — `SUSPICIOUS_PATTERNS` is still live, and the characterization module is written to survive this story

`app/services/pattern_detector.py:26-34` still holds the seven-string list, and `detect_suspicious_pattern` is still the pipeline's only check. **This story removes neither** — STORY-008 does, and its AC names the repository-wide grep. `tests/test_pattern_characterization.py:190-203` already iterates `SUSPICIOUS_PATTERNS` while "asserting nothing about its length, order or contents: STORY-005 moves the list into the built-in policy, and this module has to survive the move by describing behaviour, not structure". It survives because this story **copies** the seven strings into the built-in lists rather than moving them. Task 3 must not import `SUSPICIOUS_PATTERNS` to avoid the duplication — that would couple the new policy to a constant STORY-008 deletes, and the set-equality assertion in Task 7 is what keeps the two honest until then.

### F-3 — `authz.load()` is the template: a close fit in four places, a poor one in one

`app/services/authz.py:67-97`. Four things transfer verbatim:

| authz | pattern_config |
|---|---|
| `if not path_str: return` before any I/O (`:76-77`) | same — AC 1's "no file is read" |
| `Path(path_str).read_text(encoding="utf-8")` in a `try`, `OSError` → config error naming the path (`:79-82`) | same — AC 3's missing-path rule |
| parse in a `try`, parse error → config error naming the path (`:84-88`) | same, with `yaml.YAMLError` (PRD Risk 7) |
| `ROLE_PERMISSIONS = matrix` as the **last** statement (`:97`) | same: nothing is rebound until every rule has passed |

That last row is load-bearing and easy to lose. A loader that builds the policy incrementally into the module global leaves a half-applied policy behind when rule nine fails. Build a local `PatternPolicy`, rebind at the end.

The poor fit is the accessor. `authz` exposes `ROLE_PERMISSIONS` as a public module attribute that callers read directly. PRD Section 7 F3 specifies `get_policy()` for this module instead, and AC 5 is phrased in terms of it. Keep the policy itself private (`_policy`) and go through the function — see Decision D-A.

### F-4 — `PyYAML` is already declared; nothing in `requirements.txt` changes

`requirements.txt:15` carries `PyYAML`, added explicitly by STORY-004 (its report, Task 5, records the reason: "It is already present transitively through `python-frontmatter`; depending on a transitive dependency is how a build breaks silently", PRD Section 8). The only current `yaml` mention under `app/` is `app/services/reports.py:322`'s comment — no module imports `yaml` directly yet. This module is the first, and a plain `import yaml` is all it needs.

### F-5 — The four settings exist, unread by anything

`app/config.py:134,146,153,159`. `PATTERNS_FILE: str = ""`, `PATTERN_PROFILE_DEFAULT: str = "chat"`, `PATTERNS_ALLOW_REGEX: bool = False`, `PATTERN_MAX_SCAN_CHARACTERS: int = 1_000_000`. Each field's comment names its consumer, and two name **this** story: `PATTERNS_ALLOW_REGEX` says "Enforced by STORY-005's loader, which refuses a regex list outright while this is false" (`app/config.py:150-152`), while `PATTERN_PROFILE_DEFAULT` says the membership cross-check "lives there (PRD-011 Section 9.3)" but attributes it to **STORY-006** (`app/config.py:142-143`). Both are quoted in Decision D-C. This story reads `PATTERNS_FILE` and `PATTERNS_ALLOW_REGEX`, and not the other two.

`tests/test_config.py:551-569` already pins the boundary from the other side: a `Settings` built with `PATTERN_PROFILE_DEFAULT="a-profile-nothing-defines"` *succeeds*. Nothing this story does may make that red.

### F-6 — STORY-002's two primitives are exactly the seam this story plugs into, and its docstrings say who catches what

`app/services/pattern_detector.py:54-63` — `PatternCompileError` "deliberately does not name a list or a file: this module is pure and cannot know where the pattern came from. `pattern_config.load()` (STORY-005) catches this and re-raises `PatternConfigError` with the list name attached, which is the error an operator actually reads at startup." `has_nested_quantifier`'s docstring (`:128-148`) says the same about who refuses: "`pattern_config` (STORY-005) refuses such a pattern at startup, which is PRD Section 9.2 T4's third layer."

The contract is already written down in the module this story imports, and Task 4 implements precisely it. Note what `compile_pattern` already rejects on its own, which the loader therefore need not re-check: an empty or whitespace-only pattern (`:103-106`, `:111-114`) and an unknown match mode (`:122-125`). The loader still checks `match` against its own closed set first, because the *error message* an operator needs names the list and the allowed values, and `PatternCompileError`'s cannot.

### F-7 — PyYAML's behaviour on the four inputs this loader must survive, measured

| Input | `yaml.safe_load` returns | Consequence for `load()` |
|---|---|---|
| empty file | `None` | Not a mapping → "missing `lists:`" would be a misleading message; needs its own "is not a mapping" rule |
| `hello` | `'hello'` (a `str`) | Same — a scalar document must not reach `.items()` and raise `AttributeError` |
| duplicate mapping keys | last wins, **silently** | Not detectable through `safe_load`; see Risk R-3 |
| `!!python/object:os.system {}` | raises `ConstructorError` (a `YAMLError`) | `safe_load`'s tag refusal is already covered by the `YAMLError` handler — PRD Section 9.2 T7 needs no separate code |

Mapping order is preserved (`yaml.safe_load('b: 1\na: 2\nc: 3')` → `['b', 'a', 'c']` on the checked-out CPython 3.11.9), which is what makes declared order recoverable at all. The story's answer to "but that is a dict" is to freeze it into a `tuple` at load, which Task 4 does.

### F-8 — No test guard blocks this story, and the one source pin nearby does not reach the new module

`tests/test_pii_dedup_isolation.py:207-215` reads `inspect.getsource(pattern_detector)` and asserts `"pii"`, `"redact"` and `"presidio"` are absent from it. This story **does not edit** `pattern_detector.py`, so that guard is untouched either way; it does not inspect `pattern_config`. `_PRE_EPIC_UNTOUCHED_TESTS` (`tests/test_pii_redaction_integration.py:280-284`) is exactly `["tests/test_admin_auth.py", "tests/test_pattern_detector.py", "tests/test_route_reservations.py"]` — this story creates a new test file and edits none of those three. Layer 2, `test_no_pre_epic_test_function_was_removed_or_renamed`, fails only on removed or renamed pre-epic test functions; this story removes none.

### F-9 — Test-module conventions this repo enforces by habit

From `tests/test_authz.py:1-27` and `tests/test_pattern_matching.py:17-35`: the two `os.environ.setdefault` lines (`OPENROUTER_API_KEY`, `ADMIN_TOKEN`) come **before** any `app` import, then `import app.services.X as X` alongside the from-imports, so a module-global rebind is observable. `tests/test_authz.py:129-141` is the exact pattern for "no file is read": `monkeypatch.setattr(Path, "read_text", _fail_if_called)`. `tests/test_authz.py:122-127`'s `_reset_role_permissions` fixture is the model for restoring a module global after each case. Files are written under `tmp_path`, per the story's Technical Notes. No database fixture is needed anywhere in this module — nothing here touches libSQL.

---

## Decisions

### D-A — `get_policy()` over a public module constant

`authz` exposes `ROLE_PERMISSIONS` publicly; this module keeps `_policy` private and exposes `get_policy()`. Three reasons: PRD Section 7 F3 specifies the function; AC 5 is written against it; and a public name rebound by `load()` is a trap for `from … import POLICY`, which captures the built-in and never sees the file. `BUILT_IN_POLICY` *is* public and is never rebound — tests and STORY-007's sample-equality assertion need to name it.

### D-B — Every list key is required; no key defaults

`match`, `scope` and `patterns` are all required on a list, and a missing one is a `PatternConfigError` naming the list and the key. The PRD does not say so explicitly, and the alternative — defaulting `scope` to `everywhere` — was rejected: a policy whose scope is inferred rather than written is exactly the "cannot tell from reading the file what is in force" failure PRD Section 6.3 gives as the reason loading replaces wholesale. It costs an operator one line and buys a file that means what it says. Both lists in PRD Section 6.3 declare all three, so `examples/patterns.yaml` (STORY-007) is unaffected.

The same reasoning rejects unknown **top-level** keys: `lists` and `profiles`, nothing else. AC 3 names unknown keys "in a list or profile"; extending it to the root is consistent, and the root is the one place a typo (`list:`) would otherwise be reported as "missing `lists:`".

### D-C — Where this story stops, inside the profile

Parsed here: the `profiles:` section exists and is a non-empty mapping; each profile is a mapping; its keys are within `{lists, roles}`; its `lists:` is a non-empty sequence of names, each defined in `lists:`, resolved to `PatternList` objects at load.

**Not parsed here, on purpose:** the contents of `roles:`. It is stored as a plain dict and nothing validates its keys or values. STORY-006's AC 2 owns "a role outside `Literal[…]` or an action outside `block | flag` … An empty `roles:` map is likewise an error", its AC 4 owns `PATTERN_PROFILE_DEFAULT`'s cross-check, and `app/config.py:142-143` already attributes that cross-check to STORY-006 by name. `get_profile()` is STORY-006's too — its AC 4 specifies the raising behaviour. Adding any of it here makes STORY-006 a rewrite instead of the extension its Technical Notes ask for ("Keep `load()`'s profile handling minimal but ordered").

The built-in policy **does** carry the full `roles:` maps of PRD Section 6.4 (`chat: {user: block}`, `code: {user: block, tool: flag}`), because STORY-006 AC 1 asserts them cell by cell and they are policy, not validation.

### D-D — Compile first, then the ReDoS heuristic

For a `regex` pattern the loader calls `compile_pattern` first and `has_nested_quantifier` second. Order matters only for a pattern that is both uncompilable and textually nested, and for that pattern "does not compile" is the more useful message — the operator has a syntax error, not a performance concern. Compiling first is safe: `re.compile` of a catastrophic pattern does not execute it. The gate on `PATTERNS_ALLOW_REGEX` precedes both and is per **list**, not per pattern, so a forbidden list reports once and names the setting to change.

### D-E — One exception type, and what its messages look like

Every rule raises `PatternConfigError`. `PatternCompileError` from STORY-002 is caught and re-raised (`from exc`), never allowed to escape `load()` — that is the whole reason two types exist (F-6). Every message carries the file path and the offending node, in one shape:

```
PATTERNS_FILE '<path>': list 'keywords': unknown key 'mach' (expected one of: match, patterns, scope)
PATTERNS_FILE '<path>': profile 'chat': names undefined list 'keyword' (defined lists: injection, keywords)
PATTERNS_FILE '<path>': list 'evil': match: regex requires PATTERNS_ALLOW_REGEX=true
```

The file path is in every message because an operator debugging startup has a path in an env var and a stack trace in a log, and joining the two by hand is the failure `authz`'s messages already avoid (`app/services/authz.py:82,88,94`). Enumerate allowed values in the message, sorted, as `authz.py:94` does with unknown permissions.

Pattern *text* may appear in these messages — unlike `MessageNormalizationError` (`app/models/messages.py:33-39`), which withholds content. The distinction is real and worth a one-line comment in the code: a configured pattern is operator-authored configuration, not untrusted request content, and an error that will not say which pattern failed is useless at startup.

---

## Patterns to Follow

### Wholesale replacement; an empty setting is a no-op

```python
# SOURCE: app/services/authz.py:67-97
def load() -> None:
    global ROLE_PERMISSIONS

    path_str = settings.RBAC_ROLES_FILE
    if not path_str:
        return

    try:
        raw = Path(path_str).read_text(encoding="utf-8")
    except OSError as exc:
        raise AuthzConfigError(f"Failed to read RBAC_ROLES_FILE '{path_str}': {exc}") from exc
    ...
    ROLE_PERMISSIONS = matrix          # last statement, after every check
```

### Closed vocabulary as a module constant

```python
# SOURCE: app/services/authz.py:16-22
_KNOWN_PERMISSIONS = {
    PERMISSION_QUERY_SUBMIT,
    ...
}

# SOURCE: app/services/pattern_detector.py:70-74 -- module-level _UPPER_SNAKE, built once at import
_NESTED_QUANTIFIER = re.compile(...)
```

### Frozen dataclasses

```python
# SOURCE: app/models/messages.py:21-30
@dataclass(frozen=True)
class Message:
    role: Role
    content: str
```

### Tests: environment first, module alias for globals, no-I/O assertion

```python
# SOURCE: tests/test_authz.py:1-15, 129-141
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import app.services.authz as authz

def test_load_is_noop_when_roles_file_unset(monkeypatch, _reset_role_permissions):
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", "")

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("read_text should not be called when RBAC_ROLES_FILE is empty")

    monkeypatch.setattr(Path, "read_text", _fail_if_called)
```

### Tests: parametrized case table with explicit ids

```python
# SOURCE: tests/test_pattern_matching.py:41-50
_OVERRIDE_CASES = [("override", True), ("overrides", False), ...]
_OVERRIDE_IDS = [f"{subject}-{'match' if hit else 'clean'}" for subject, hit in _OVERRIDE_CASES]
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/pattern_config.py` | CREATE | The policy model, the built-in policy, `load()`, `get_policy()`, `PatternConfigError` |
| `tests/test_pattern_config.py` | CREATE | One case per acceptance criterion; one case per malformed-file rule |

No other file is touched. `requirements.txt` already declares `PyYAML` (F-4), `.env.example` already documents all four settings (STORY-004), and no lifespan is wired until STORY-007.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: The module skeleton — docstring, imports, exception, closed vocabularies

- **File**: `app/services/pattern_config.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring in the voice of `app/services/pattern_detector.py:1-20`: what this module owns (all of the I/O and all of the configuration reading for pattern policy), who calls `load()` (STORY-007, both lifespans), who reads `get_policy()` (STORY-008), and the sentence that `load()` replaces the built-in policy wholesale and never merges, citing PRD Sections 6.3 and 6.9.
  - Imports: `re`, `dataclasses.dataclass`, `pathlib.Path`, `typing` (`Literal`, `Mapping`), `yaml`, `from app.config import settings`, and from `app.services.pattern_detector`: `PatternCompileError`, `compile_pattern`, `has_nested_quantifier`.
  - `class PatternConfigError(Exception)` with a docstring saying startup fails rather than falling back silently, and naming `PatternCompileError` as the inner type it wraps (F-6, D-E).
  - Module constants: `_MATCH_MODES = ("word", "regex")`, `_SCOPES = ("everywhere", "outside_code")`, `_TOP_LEVEL_KEYS = frozenset({"lists", "profiles"})`, `_LIST_KEYS = frozenset({"match", "scope", "patterns"})`, `_PROFILE_KEYS = frozenset({"lists", "roles"})`.
- **Mirror**: `app/services/authz.py:8-22,61-65` (closed vocabulary + config exception), `app/services/pattern_detector.py:1-20` (pure-module docstring voice).
- **Validate**: `python -c "import app.services.pattern_config"`

### Task 2: The three frozen dataclasses

- **File**: `app/services/pattern_config.py`
- **Action**: UPDATE
- **Implement**: `PatternList(name, match, scope, patterns: tuple[str, ...], compiled: tuple[re.Pattern, ...])`, `Profile(name, lists: tuple[PatternList, ...], roles: Mapping[str, str])`, `PatternPolicy(lists: Mapping[str, PatternList], profiles: Mapping[str, Profile])` — all `@dataclass(frozen=True)`, exactly PRD Section 6.2. `compiled` carries a comment: built at load, never at request time. `Profile.roles` carries a comment that STORY-006 narrows the annotation to `Mapping[Role, Literal["block", "flag"]]` and adds the validation (D-C), so a reader does not mistake the wide type for a decision.
- **Mirror**: `app/models/messages.py:21-30`.
- **Validate**: `python -c "import app.services.pattern_config as pc; print(pc.PatternList, pc.Profile, pc.PatternPolicy)"`

### Task 3: The built-in policy and `get_policy()`

- **File**: `app/services/pattern_config.py`
- **Action**: UPDATE
- **Implement**:
  - A private `_build_builtin() -> PatternPolicy` constructing the two lists of PRD Section 6.3 **in declared order** — `injection` (`match: word`, `scope: everywhere`; `ignore previous instructions`, `forget everything`, `show system prompt`, `reveal password`), then `keywords` (`match: word`, `scope: outside_code`; `execute code`, `admin mode`, `override`) — each pattern run through `compile_pattern(pattern, "word")`; and the two profiles of PRD Section 6.4: `chat` → lists `(injection, keywords)`, roles `{"user": "block"}`; `code` → lists `(injection,)`, roles `{"user": "block", "tool": "flag"}`.
  - `BUILT_IN_POLICY = _build_builtin()` and `_policy = BUILT_IN_POLICY` at module level.
  - `def get_policy() -> PatternPolicy: return _policy`, whose docstring says it returns the built-in policy when `load()` has never run — the pipeline and every test that never boots an app depend on that, exactly as `ROLE_PERMISSIONS` stands before `authz.load()` (AC 5, D-A).
  - A comment above the list literals: the seven strings are **copied** from `pattern_detector.SUSPICIOUS_PATTERNS`, not imported, because STORY-008 deletes that constant (F-2), and their order within `keywords` is load-bearing for the list-order precedence case (F-1).
- **Mirror**: `app/services/authz.py:24-45` (built-in policy table with the comment explaining it is the fallback).
- **Validate**: `python -c "import app.services.pattern_config as pc; p=pc.get_policy(); print(list(p.lists), [l.scope for l in p.lists.values()], sum(len(l.patterns) for l in p.lists.values()))"` → `['injection', 'keywords'] ['everywhere', 'outside_code'] 7`

### Task 4: List parsing and validation

- **File**: `app/services/pattern_config.py`
- **Action**: UPDATE
- **Implement**: `_parse_lists(raw, path) -> dict[str, PatternList]`, rules in this order, each raising `PatternConfigError` in D-E's message shape:
  1. `lists:` is a mapping and is non-empty.
  2. Each list body is a mapping; its keys ⊆ `_LIST_KEYS`; **and** all three are present (D-B). Report unknown keys and missing keys as separate messages, each enumerating the allowed set sorted.
  3. `match` ∈ `_MATCH_MODES`, `scope` ∈ `_SCOPES` — the message names the list, the value and the allowed values.
  4. `patterns` is a non-empty sequence of non-empty strings (PRD 9.2 T5); a bare string where a sequence is expected is refused too, since YAML makes that an easy slip.
  5. `match: regex` while `settings.PATTERNS_ALLOW_REGEX` is false → error naming the list **and** `PATTERNS_ALLOW_REGEX=true` as the setting to change (AC 4). Checked once per list, before any pattern is compiled (D-D).
  6. Per pattern: `compile_pattern(pattern, match)` inside `try`, `except PatternCompileError as exc` → `PatternConfigError(… list '<name>': …) from exc`; then, for `regex` only, `has_nested_quantifier(pattern)` → error naming the list and the pattern (AC 4, D-D).
  - Build `patterns` and `compiled` as `tuple`s so nothing downstream can reorder them (story Technical Notes).
- **Mirror**: `app/services/authz.py:90-95` (unknown-value error naming the file and the sorted offenders); `app/services/pattern_detector.py:54-63` (the re-raise contract).
- **Validate**: covered by Task 9's suite; until then, by the module import above.

### Task 5: Profile parsing, minimal and ordered

- **File**: `app/services/pattern_config.py`
- **Action**: UPDATE
- **Implement**: `_parse_profiles(raw, lists, path) -> dict[str, Profile]`:
  1. `profiles:` is a mapping and is non-empty (AC 3, PRD 9.2 T5).
  2. Each profile body is a mapping; keys ⊆ `_PROFILE_KEYS`; `lists:` present.
  3. `lists:` is a non-empty sequence of strings; each name resolves in `lists`, or the error names the profile, the undefined name and the defined names (PRD Section 7 F4: never a request-time `KeyError`).
  4. `roles` stored as `dict(body.get("roles") or {})` with **no validation**, under a comment naming STORY-006 and its AC (D-C).
- **Mirror**: `app/services/authz.py:86` (build a local structure, validate, then hand it back).
- **Validate**: as Task 4.

### Task 6: `load()`

- **File**: `app/services/pattern_config.py`
- **Action**: UPDATE
- **Implement**:
  - `global _policy`; `path_str = settings.PATTERNS_FILE`; `if not path_str: return` — before any I/O (AC 1).
  - `Path(path_str).read_text(encoding="utf-8")` in `try`/`except OSError` → `PatternConfigError` naming the path (AC 3, missing path).
  - `yaml.safe_load(raw)` in `try`/`except yaml.YAMLError` → `PatternConfigError` naming the path (PRD Risk 7; F-7 shows this also covers `safe_load`'s tag refusal, PRD 9.2 T7).
  - The document is a mapping, else error; keys ⊆ `_TOP_LEVEL_KEYS`; both `lists:` and `profiles:` present (AC 3, D-B).
  - `_parse_lists`, then `_parse_profiles`, then — as the **last** statement — `_policy = PatternPolicy(lists=…, profiles=…)` (F-3).
  - Docstring: called once at startup by STORY-007 in both lifespans, never per request; replaces the built-in policy wholesale; `PATTERN_PROFILE_DEFAULT`'s cross-check and `get_profile()` land in STORY-006; and Risk R-3's one-line note on duplicate YAML keys.
- **Mirror**: `app/services/authz.py:67-97`.
- **Validate**: `python -c "import app.services.pattern_config as pc; pc.load(); print(list(pc.get_policy().lists))"` → `['injection', 'keywords']` with `PATTERNS_FILE` unset.

### Task 7: Tests — the built-in policy and characterization parity (AC 1, AC 5)

- **File**: `tests/test_pattern_config.py`
- **Action**: CREATE
- **Implement**: a module docstring saying what this module covers and what it deliberately does not (roles, `PATTERN_PROFILE_DEFAULT`, `get_profile` → STORY-006; the message walk → STORY-008). Then:
  - The two `os.environ.setdefault` lines before any `app` import; `import app.services.pattern_config as pattern_config`; a `_reset_policy` fixture mirroring `tests/test_authz.py:122-127`.
  - `load()` with `PATTERNS_FILE=""` reads no file — `monkeypatch.setattr(Path, "read_text", _fail_if_called)` (AC 1).
  - The built-in lists together hold exactly the seven patterns: assert the union equals `set(SUSPICIOUS_PATTERNS)` **and** assert `keywords.patterns == ("execute code", "admin mode", "override")` as a tuple, so declared order is pinned and not merely membership (F-1, F-2).
  - AC 1's parity test: import `_CASES` and `PRD_011_FLIP_CASES` from `tests.test_pattern_characterization`, parametrize over `_CASES`, and compare a local `_verdict(text)` mini-walker (lists in declared order, patterns in declared order, `strip_code_spans` for `outside_code`) against the flip-set-adjusted expectation. A comment must say why the walker is local: `inspect()` is STORY-008's and this story may not ship it — the same move `tests/test_pattern_matching.py` made for scope in STORY-003.
  - AC 5: `get_policy()` returns `BUILT_IN_POLICY` with no `load()` call, and a second case asserts the same after a *failed* `load()` — a raised `PatternConfigError` must leave the previous policy in place (F-3).
- **Mirror**: `tests/test_authz.py:129-141`, `tests/test_pattern_matching.py:41-50`, `tests/test_pattern_characterization.py:166-181`.
- **Validate**: `python -m pytest tests/test_pattern_config.py -q`

### Task 8: Tests — wholesale replacement and compile-once (AC 2)

- **File**: `tests/test_pattern_config.py`
- **Action**: UPDATE
- **Implement**:
  - A valid file under `tmp_path` defining a single list `only` and a single profile; after `load()`, `get_policy().lists` has exactly `{"only"}` — **`injection` and `keywords` are gone**, which is the assertion AC 2 demands in so many words.
  - Compiled once at load: every `PatternList.compiled` entry `isinstance(x, re.Pattern)` and `len(compiled) == len(patterns)`; plus a spy on `pattern_config.compile_pattern` counting calls, asserting the count equals the number of configured patterns and that a subsequent `get_policy()` adds none.
  - Declared order survives parsing: a file whose lists and patterns are in a deliberately non-alphabetical order round-trips in that order, as `tuple`s.
- **Mirror**: `tests/test_authz.py:143-162` (wholesale replacement), `tests/test_authz.py:198-215` (call-counting spy).
- **Validate**: `python -m pytest tests/test_pattern_config.py -q`

### Task 9: Tests — one case per malformed-file rule (AC 3)

- **File**: `tests/test_pattern_config.py`
- **Action**: UPDATE
- **Implement**: a parametrized table with explicit ids, one row per rule named in AC 3, each asserting `PatternConfigError` **and** that the message names the offending list or profile and the failed rule:

  | id | file |
  |---|---|
  | `missing-path` | `PATTERNS_FILE` points at a nonexistent path |
  | `unparseable-yaml` | `lists:\n  - [unbalanced` |
  | `not-a-mapping-empty` / `not-a-mapping-scalar` | an empty document; a bare scalar (F-7) |
  | `missing-lists` / `missing-profiles` | one section only |
  | `empty-profiles` | `profiles: {}` |
  | `unknown-top-level-key` | `list:` typo (D-B) |
  | `unknown-list-key` | `mach: word` — the story's named case |
  | `missing-list-key` | no `scope:` |
  | `unknown-match` / `unknown-scope` | `match: words`, `scope: outside-code` |
  | `empty-patterns` | `patterns: []` |
  | `unknown-profile-key` | `list: [injection]` inside a profile |
  | `undefined-list-in-profile` | `lists: [keyword]` |

  Assert on substrings of the message (the list or profile name, and the offending key or value), not on the whole string — the wording must stay editable.
- **Mirror**: `tests/test_authz.py:164-196`.
- **Validate**: `python -m pytest tests/test_pattern_config.py -q`

### Task 10: Tests — the regex gate and the ReDoS heuristic (AC 4)

- **File**: `tests/test_pattern_config.py`
- **Action**: UPDATE
- **Implement**: with `monkeypatch.setattr(settings, "PATTERNS_ALLOW_REGEX", False)`, a file containing a `match: regex` list raises and the message names the list **and** `PATTERNS_ALLOW_REGEX`. With it true: a `word` list is unaffected; `(a+)+b` raises naming the list and the pattern; `[unclosed` raises naming the list and the pattern; and a benign regex such as `overrid\w*` loads and compiles. One case asserts the raised type is `PatternConfigError` and its `__cause__` is a `PatternCompileError`, which pins the re-raise contract of F-6.
- **Mirror**: `tests/test_pattern_matching.py` (STORY-002's cases for the same two primitives, from the other side of the seam).
- **Validate**: `python -m pytest tests/test_pattern_config.py -q`

### Task 11: Full suite, and the no-consumer check

- **File**: —
- **Action**: verify
- **Implement**: run the full suite; confirm `tests/test_config.py`, `tests/test_pattern_characterization.py`, `tests/test_pattern_matching.py`, `tests/test_pii_dedup_isolation.py` and `tests/test_query_outcomes_regression.py` are green with no assertion edited; and `grep -rn "pattern_config" app/ chat_ui/` returns nothing outside the new module itself — no production caller exists until STORY-007.
- **Validate**: `python -m pytest -q` and the grep.

---

## End-to-End Tests

For `/implement` to execute, each from a clean shell at the repo root:

- [ ] `python -c "import app.services.pattern_config as pc; print(list(pc.get_policy().lists))"` → `['injection', 'keywords']`, with **no** `load()` call and `PATTERNS_FILE` unset (AC 5)
- [ ] With `PATTERNS_FILE=""` in the environment, `pc.load()` returns and `Path.read_text` is never called (AC 1)
- [ ] Write PRD Section 6.3's file verbatim to a temp path, point `PATTERNS_FILE` at it, `pc.load()` → `get_policy()` equals the built-in policy in list names, scopes, pattern tuples and profile list resolution. *(STORY-007 turns this into a checked-in assertion against `examples/patterns.yaml`; running it here is how this story proves the format it validates is the format the PRD publishes.)*
- [ ] A file with `mach: word` → `PatternConfigError` whose message contains the list name and `mach` (PRD Section 11: "A patterns file with a misspelled key stops startup with a message naming the list and the key")
- [ ] A file with a `match: regex` list and `PATTERNS_ALLOW_REGEX` unset → `PatternConfigError` naming the list and the setting
- [ ] The same file with `PATTERNS_ALLOW_REGEX=true` → loads; then with `(a+)+` as the pattern → `PatternConfigError` naming the list and the pattern
- [ ] After any failing `load()`, `get_policy()` still returns the built-in policy — no half-applied state (F-3)
- [ ] `python -c "from app.main import app"` still imports cleanly
- [ ] `git diff --name-only main...HEAD -- app/` names `app/services/pattern_config.py` and nothing else for this commit

## Validation

```bash
python -m pytest tests/test_pattern_config.py -q
python -m pytest tests/test_config.py tests/test_pattern_characterization.py tests/test_pattern_matching.py tests/test_pii_dedup_isolation.py -q
python -m pytest -q          # full suite
python -c "from app.main import app"
grep -rn "pattern_config" app/ chat_ui/
```

The suite needs the local libSQL dev server described in `tests/conftest.py`'s docstring. Per PRD Section 11's quality indicators and this repo's standing note, **mass fixture errors mean restarting that container, not bisecting the code** — nothing in this story touches the database, so a wave of fixture errors here is the container, not the change.

No frontend lint applies: this repo's UI is Reflex and this story touches no UI file (the same call STORY-004's report recorded).

---

## Risks

| # | Risk | Mitigation |
|---|---|---|
| R-1 | **Building STORY-006's half.** The most likely failure is a loader that validates roles, checks `PATTERN_PROFILE_DEFAULT` and ships `get_profile()`, leaving STORY-006 nothing to do but rewrite it. | D-C draws the line explicitly, `app/config.py:142-143` names STORY-006 as the owner in the code itself, and Task 5 puts the boundary in a comment at the one place it would be crossed |
| R-2 | **A half-applied policy after a failed `load()`.** Incremental mutation of `_policy` leaves protection in an undefined state when rule nine fails. | Task 6 rebinds as its last statement (F-3); Task 7 asserts the built-in policy survives a failed load |
| R-3 | **Duplicate YAML keys are silently dropped** — `lists:` written twice means one of them vanishes and nothing warns (F-7), which has the shape of PRD 9.2 T5. | Not handled in this story, deliberately: detecting it needs a custom `SafeLoader` subclass, and AC 3's rule list is closed. Recorded as a one-line limit in `load()`'s docstring so a later reader finds it stated rather than discovering it. If PRD-015 adds a second YAML loader, a shared strict loader is the place to fix it once |
| R-4 | **The AC 1 parity test couples two test modules.** `tests/test_pattern_config.py` importing `_CASES` means a rename there reddens here. | That coupling is the point — it is what stops a hand-copied corpus drifting from the pinned one, and it is the same instrument `test_every_flip_case_is_a_pinned_case` (`tests/test_pattern_characterization.py:166-181`) already uses. The import crosses test modules and reaches a private name; note it in a comment so it reads as deliberate |
| R-5 | **`Mapping` in a frozen dataclass is not deep-immutable.** A caller can still mutate `policy.lists`. | Accepted, as PRD Section 6.2 specifies `Mapping`. `frozen=True` prevents rebinding, which is what protects the load-once contract; the `tuple`s are where real immutability is needed (declared order) and they have it |

---

## Acceptance Criteria

(Copied from story `STORY-005`)

- [ ] Given `PATTERNS_FILE=""`, when `pattern_config.load()` runs, then no file is read and `get_policy()` returns the built-in policy, whose lists together hold exactly today's seven patterns and whose verdicts match STORY-001's characterization for every case outside that story's declared flip set.
- [ ] Given a valid `PATTERNS_FILE`, when `load()` runs, then the built-in policy is replaced **wholesale** — a list present in the built-in policy and absent from the file is gone, asserted by a test — and every pattern is compiled once, at load, with `compile_pattern` from STORY-002.
- [ ] Given a malformed file, when `load()` runs, then it raises `PatternConfigError` whose message names the offending list or profile and the rule that failed, for each of: a missing path, unparseable YAML, an unknown key in a list or profile, an unknown `match`, an unknown `scope`, an empty `patterns:`, a missing `lists:` or `profiles:` section, an empty `profiles:`, and a profile naming a list that is not defined.
- [ ] Given `PATTERNS_ALLOW_REGEX=false` and a file containing a `match: regex` list, when `load()` runs, then it raises `PatternConfigError` naming the list and the setting to change. Given `PATTERNS_ALLOW_REGEX=true`, then an uncompilable pattern and a nested-quantifier pattern each raise `PatternConfigError` naming the list and the pattern.
- [ ] Given `load()` has never been called, when `get_policy()` is called, then the built-in policy is returned rather than raising.
- [ ] All tasks completed
- [ ] Full suite green (STORY-004's baseline was 2354 passed, 26 skipped)
- [ ] Backend imports without error
- [ ] No production file outside `app/services/pattern_config.py` is modified
- [ ] Follows existing patterns (`authz.load()`, `app/models/messages.py` dataclasses, `tests/test_authz.py` fixtures)
