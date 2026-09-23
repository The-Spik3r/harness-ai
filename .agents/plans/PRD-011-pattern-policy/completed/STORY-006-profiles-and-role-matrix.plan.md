---
story: STORY-006
prd: PRD-011
slug: profiles-and-role-matrix
title: Profiles and the role inspection matrix
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-011-pattern-policy        # all stories commit here, no per-story branch
created: 2026-09-22
---

# Plan: Profiles and the role inspection matrix

## Summary

STORY-005 left `pattern_config` able to parse profiles but not to judge them. `Profile` exists as a frozen dataclass whose `roles` is typed `Mapping[str, str]` and stored unvalidated (`app/services/pattern_config.py:100-124`, `:432-436`). There is no `get_profile()`, and `load()` never looks at `PATTERN_PROFILE_DEFAULT`. This story closes all three gaps **inside the existing module**, extending STORY-005's check order rather than rewriting it:

1. `Profile.roles` is narrowed to `Mapping[Role, Literal["block", "flag"]]`, with `Role` imported from `app/models/messages.py`.
2. `roles:` becomes a required profile key. It is validated for shape (a non-empty mapping), for role vocabulary (`get_args(Role)`) and for action vocabulary (`block | flag`).
3. `load()` cross-checks `PATTERN_PROFILE_DEFAULT` against the profiles it is about to install, **on both paths**: the file path, and the empty-`PATTERNS_FILE` path, where the check runs against `BUILT_IN_POLICY` and still reads no file.
4. `get_profile(name)` is added and raises `PatternConfigError` for an unknown name.

The Section 6.4 matrix is asserted cell by cell in a new `tests/test_pattern_profiles.py`, and `tests/test_pattern_config.py`'s STORY-005 boundary tests are updated in place with a comment citing PRD-011.

## User Story

As a security admin
I want each profile to declare which message roles it inspects and what happens on a hit
So that the scope of prompt inspection is a document I can review rather than behaviour I have to infer from code

## Story Reference

- Story file: `.agents/stories/PRD-011-pattern-policy/STORY-006-profiles-and-role-matrix.md`
- PRD: `.agents/PRDs/PRD-011-pattern-policy/PRD.md`, Sections 4 (Profiles), 6.2, 6.4 (D1), 6.6 (D2), 7 (F4), 9.2 (T1, T5), 9.3, 10, 11
- Predecessor plan: `.agents/plans/PRD-011-pattern-policy/completed/STORY-005-pattern-config-load-and-validate.plan.md`. Decision D-C there hands this story role and action validation, the empty-`roles:` rule, the default cross-check and `get_profile()`.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/services/pattern_config.py`, `tests/test_pattern_config.py`, `tests/test_pattern_profiles.py` (new) |
| Story | STORY-006 |
| PRD | PRD-011 |
| Epic Branch | `epic/PRD-011-pattern-policy` (commit directly on this branch) |

---

## Design Decisions

| # | Decision | Why |
|---|----------|-----|
| D-A | **Extend `pattern_config.py`, do not add a module.** `Profile`, `_parse_profiles` and `load()` already exist. STORY-005 left docstring markers at `:27-32`, `:115-119`, `:393-396`, `:432-435` and `:464-465` naming exactly this work. | The STORY-005 plan's Risk R-1 and its Technical Notes say "extends rather than rewrites". A second module would split the policy model. |
| D-B | **The role vocabulary is `get_args(Role)`, taken from `app.models.messages`.** Add `from app.models.messages import Role` and `_ROLES = get_args(Role)` (a tuple, so declared order survives into nothing that matters, and `_allowed()` sorts anyway). Do **not** import `messages._ROLES`, because it is private. | AC 5: "this story introduces no second role literal". `messages.py` is pure ("no I/O, no settings, no pydantic, no `app` import", `app/models/messages.py:5-6`), so the import adds no cycle. |
| D-C | **Actions: `_ACTIONS = ("block", "flag")` next to `_MATCH_MODES` / `_SCOPES`, plus a public alias `Action = Literal["block", "flag"]`.** | This mirrors how `_MATCH_MODES` sits beside the `Literal` on `PatternList.match` (`:72-73`, `:94`). The alias names the type `Profile.roles` uses. STORY-008's `PatternHit.action` can reuse it. That story must note that `pattern_detector` cannot import from `pattern_config`, because `pattern_config` already imports `pattern_detector`. See Risk R-3. |
| D-D | **`roles` becomes a required profile key.** `_check_keys(path, where, body, _PROFILE_KEYS, {"lists"})` becomes `..., _PROFILE_KEYS, _PROFILE_KEYS)`, the same shape as the top-level `_check_keys(..., _TOP_LEVEL_KEYS, _TOP_LEVEL_KEYS)` at `:489`. | T5: a profile that inspects nothing must be written out, never arrived at. An absent key would otherwise be an empty map by another name. STORY-005's `_check_keys` docstring (`:271-274`) makes the same argument for `scope`. The inline comment at `:433-435` says "it becomes one there". |
| D-E | **`roles: ~` (YAML null, which is what a bare `roles:` line parses to) is reported as `roles is empty`, not as a type error.** Any other non-mapping (a list or a string) reports `roles must be a mapping of role to action`. | A bare `roles:` with the entries forgotten is the natural operator slip. "empty" is the true diagnosis, and it matches `lists is empty` / `patterns is empty`. |
| D-F | **Check order inside a profile: keys → `lists` shape → `lists` resolution → `roles` shape → `roles` empty → each role → each action.** Roles are checked in declared order and the first offender is reported. | "The order of the checks below is the order STORY-006 extends, not replaces" (`:395-396`). Reporting the first offender matches `_check_keys`'s `unknown[0]`. |
| D-G | **`PATTERN_PROFILE_DEFAULT` is cross-checked inside `load()` by a helper `_check_default_profile(profiles, source)`, called (a) before the early return on the empty-setting path, against `BUILT_IN_POLICY.profiles`, and (b) after `_parse_profiles` and **before** `_policy` is rebound on the file path.** | (a) If the check sat after the early return, `PATTERN_PROFILE_DEFAULT=nope` with no file would boot cleanly and fail on the first request, which is exactly the request-time failure Section 2 forbids. It still reads no file, so `test_load_is_noop_when_patterns_file_unset` holds. (b) This keeps "`_policy` is assigned as the last statement, so a failed file leaves the previous policy intact" (`:446-449`). |
| D-H | **Message shapes.** Profile rules go through `_fail(path, f"profile {name!r}", ...)` and so carry the file path, like every STORY-005 rule. The default cross-check is a whole-policy rule and is **not** under a profile heading. File path: `PATTERN_PROFILE_DEFAULT 'nope' names a profile PATTERNS_FILE '<path>' does not define (defined profiles: chat, code)`. Built-in path: `PATTERN_PROFILE_DEFAULT 'nope' names a profile the built-in policy does not define (defined profiles: chat, code); PATTERNS_FILE is unset`. `get_profile`: `unknown pattern profile 'nope' (defined profiles: chat, code)`. | AC 4 asks for the setting, the missing profile and the profiles that exist, and `app/config.py:136-145` promises the same. Tests assert substrings, never whole messages (`tests/test_pattern_config.py:394-396`), so the wording stays editable. |
| D-I | **`get_profile(name)` reads `_policy`, not `BUILT_IN_POLICY`**, and does no I/O. It takes `str` only. Resolving `None` to the default is `run_conversation`'s job in STORY-008 (PRD Section 6.6). | It sits on the request path from STORY-008, under the same rule `get_policy()` follows (`tests/test_pattern_config.py:663-682`). |
| D-J | **The built-in maps are not re-validated at import.** `_build_built_in()` stays as written. A test asserts that every built-in role and action is inside the vocabulary. | Running the file validator over a Python literal would mean inventing a second input format. A test catches drift just as well, at no import-time cost. |
| D-K | **No route, no request field and no per-endpoint setting** for `code`. | Story Technical Notes; PRD Sections 4 Out of Scope, 6.6, 9.2 T1. The existing unknown-field schema test already covers T1. This story touches no router and no schema. |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | None applicable. `.agents/skills/` holds only `frontend-design`, which covers visual UI design. This story is backend config validation and tests and touches no UI. The story's `skills: []` and the PRD's "Skills referenced: none" agree. | — |

---

## Patterns to Follow

### Naming: vocabularies next to their `Literal`s
```python
# SOURCE: app/services/pattern_config.py:72-77
_MATCH_MODES = ("word", "regex")
_SCOPES = ("everywhere", "outside_code")

_TOP_LEVEL_KEYS = frozenset({"lists", "profiles"})
_LIST_KEYS = frozenset({"match", "scope", "patterns"})
_PROFILE_KEYS = frozenset({"lists", "roles"})
```

### Role vocabulary: the one definition
```python
# SOURCE: app/models/messages.py:12-18
from typing import Any, Literal, Mapping, Sequence, get_args

# `tool` is valid on purpose, so PRD-016 does not have to widen the type. The
# pipeline refuses it structurally (STORY-007), as `dedup_key` already does.
Role = Literal["system", "user", "assistant", "tool"]

_ROLES = frozenset(get_args(Role))
```

### Error handling: path-prefixed, offender named, allowed values listed
```python
# SOURCE: app/services/pattern_config.py:260-265, 418-426
def _fail(path: str, *parts: str) -> PatternConfigError:
    return PatternConfigError(f"PATTERNS_FILE '{path}': " + ": ".join(parts))

def _allowed(values) -> str:
    return ", ".join(sorted(values))
...
            if list_name not in lists:
                raise _fail(
                    path,
                    where,
                    f"names undefined list {list_name!r} (defined lists: {_allowed(lists)})",
                )
```

### Wholesale replacement, rebound last
```python
# SOURCE: app/services/pattern_config.py:470-493
    path = settings.PATTERNS_FILE
    if not path:
        return
    ...
    lists = _parse_lists(path, document["lists"])
    profiles = _parse_profiles(path, document["profiles"], lists)

    _policy = PatternPolicy(lists=lists, profiles=profiles)
```

### Tests: local reset fixture, `_write`, substring assertions on the raised message
```python
# SOURCE: tests/test_pattern_config.py:59-74, 488-505
@pytest.fixture
def _reset_policy():
    original = pattern_config._policy
    yield
    pattern_config._policy = original


def _write(tmp_path, text: str) -> str:
    path = tmp_path / "patterns.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)
...
    monkeypatch.setattr(settings, "PATTERNS_FILE", _write(tmp_path, body))

    with pytest.raises(PatternConfigError) as exc_info:
        load()

    message = str(exc_info.value)
    for expected in expected_substrings:
        assert expected in message, f"{expected!r} missing from: {message}"
```

### Tests: the environment prologue every pattern test module carries
```python
# SOURCE: tests/test_pattern_config.py:23-26
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/pattern_config.py` | UPDATE | Import `Role`; add `_ROLES`, `_ACTIONS`, `Action`; narrow `Profile.roles`; validate `roles:`; add `_check_default_profile`; add `get_profile()`; update the five STORY-006 docstring markers |
| `tests/test_pattern_profiles.py` | CREATE | AC 1–5: the matrix cell by cell, roles validation, resolved lists, default cross-check, `get_profile`, `Role` reuse |
| `tests/test_pattern_config.py` | UPDATE | Adapt the fixtures that the new rules invalidate, rewrite the STORY-005 boundary test in place, and pin `PATTERN_PROFILE_DEFAULT`. Every change carries a `PRD-011 STORY-006` comment |

No change to `app/config.py`. Its comment at `:136-145` already describes what this story implements, and `tests/test_config.py:551-569` (Settings accepts an undefined profile name) must stay green, unchanged.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Role and action vocabulary; narrow `Profile.roles`

- **File**: `app/services/pattern_config.py`
- **Action**: UPDATE
- **Implement**:
  - Imports: `from typing import Literal, Mapping, get_args` and `from app.models.messages import Role`. Put it in the first-party block above `from app.config import settings`, following the existing isort grouping.
  - Beside `_MATCH_MODES` / `_SCOPES` (`:72-73`), with a short comment in the style of `:68-71`:
    ```python
    #: The role vocabulary is `app.models.messages.Role` and nothing else -- this
    #: module introduces no second role literal (PRD-011 Section 6.2).
    _ROLES = get_args(Role)
    _ACTIONS = ("block", "flag")
    ```
  - Public alias after the vocabularies: `Action = Literal["block", "flag"]`.
  - `Profile.roles: Mapping[Role, Action]`.
  - Rewrite the `Profile` docstring's last paragraph (`:115-119`). Remove "typed `Mapping[str, str]` only because this story does not validate it". Say instead that `roles` is validated at load against `Role` and `block | flag`, that an empty map is a startup error (T5), and that the map is a plain `dict`: `frozen=True` stops it being reassigned, not mutated (Technical Notes). **Keep** the existing "a role absent from `roles` is not inspected ... opposite default from `authz.py`" paragraph (`:104-109`) verbatim. AC and Technical Notes require it, and it is already correct.
  - Add one sentence to the `Profile` docstring so the `system` cell is easy to find from the type (Technical Notes): *"Under the built-in `code` profile `system` is not inspected on purpose: it is the client's own prompt, and the richest source of false positives (STORY-011 demonstrates it). PRD-014 is where that cell may change. See the comment on `_build_built_in()`'s `code` profile."*
- **Mirror**: `app/services/pattern_config.py:72-77` for the vocabularies; `:80-97` (`PatternList.match` typed with a `Literal` whose values are also a tuple).
- **Validate**: `python -c "import app.services.pattern_config as p; print(p._ROLES, p._ACTIONS, p.BUILT_IN_POLICY.profiles['code'].roles)"`. Expect `('system', 'user', 'assistant', 'tool') ('block', 'flag') {'user': 'block', 'tool': 'flag'}`.

### Task 2: Validate `roles:` in `_parse_profiles`

- **File**: `app/services/pattern_config.py`
- **Action**: UPDATE
- **Implement**, in `_parse_profiles` (`:385-438`), per D-D, D-E and D-F:
  - `_check_keys(path, where, body, _PROFILE_KEYS, _PROFILE_KEYS)`. `roles` is now required.
  - After list resolution, add a helper `_parse_roles(path, where, raw) -> dict[Role, Action]` (or inline it, whichever keeps `_parse_profiles` readable; the list parser uses helpers) that:
    1. `raw is None` or `raw == {}`: `_fail(path, where, "roles is empty (a profile must inspect at least one role; a role absent from roles is not inspected)")`. Comment: `# PRD-011 Section 9.2, T5: a profile that inspects nothing must be written out, not arrived at.`
    2. `not isinstance(raw, Mapping)`: `_fail(path, where, "roles must be a mapping of role to action")`
    3. For each `role, action` in declared order:
       - `role not in _ROLES`: `_fail(path, where, f"roles: unknown role {role!r} (expected one of: {_allowed(_ROLES)})")`
       - `action not in _ACTIONS`: `_fail(path, where, f"roles: role {role!r} has unknown action {action!r} (expected one of: {_allowed(_ACTIONS)})")`
    4. Return `dict(raw)`, which preserves declared order.
  - Use `roles=_parse_roles(path, where, body["roles"])` in place of `roles=dict(body.get("roles") or {})`, and delete the "Stored, not validated" comment (`:432-435`).
  - Rewrite the `_parse_profiles` docstring's "**Not checked here:**" paragraph (`:393-396`) to list the roles checks, in order, as checked here. The default cross-check lives in `load()` because it spans the whole policy, not one profile.
- **Mirror**: `_parse_lists`'s per-key checks (`:340-380`, e.g. `unknown match {match!r} (expected one of: ...)` at `:355`).
- **Gotcha**: a YAML key like `1: block` or `yes: block` arrives as an `int` or `bool`, not a `str`. `role not in _ROLES` still rejects it, and `{role!r}` shows the parsed value. Nothing extra is needed. Do not `.lower()` roles or actions: the vocabulary is exact, as `match` and `scope` are.
- **Validate**: `python -m pytest tests/test_pattern_config.py -q`. This is **expected to go red** in the fixtures listed in Task 5 and nowhere else. Note which ones fail and confirm they match Task 5's list before continuing.

### Task 3: `PATTERN_PROFILE_DEFAULT` cross-check in `load()`

- **File**: `app/services/pattern_config.py`
- **Action**: UPDATE
- **Implement**, per D-G and D-H:
  ```python
  def _check_default_profile(profiles: Mapping[str, Profile], source: str) -> None:
      default = settings.PATTERN_PROFILE_DEFAULT
      if default not in profiles:
          raise PatternConfigError(
              f"PATTERN_PROFILE_DEFAULT {default!r} names a profile {source} does not "
              f"define (defined profiles: {_allowed(profiles)})"
          )
  ```
  - Empty-setting path, before `return`: `_check_default_profile(BUILT_IN_POLICY.profiles, "the built-in policy")`. Append `"; PATTERNS_FILE is unset"` to that message, via a `suffix` parameter or by building `source` accordingly, so an operator knows no file was consulted.
  - File path: `_check_default_profile(profiles, f"PATTERNS_FILE '{path}'")` right after `_parse_profiles(...)` and **before** `_policy = PatternPolicy(...)`.
  - Read `settings.PATTERN_PROFILE_DEFAULT` at call time, never at import, so `monkeypatch.setattr(settings, ...)` works (the same reason given at `:42`).
  - Rewrite the `load()` docstring's last paragraph (`:464-465`) to say the default is cross-checked on both paths, and why the empty path checks too (a boot that succeeds and then fails on the first request is the failure Section 2 forbids).
- **Mirror**: `authz.load()`'s rule, "raise rather than fall back" (`app/services/authz.py:67-97`); `load()`'s rebind-last shape (`:441-493`).
- **Validate**: `PATTERN_PROFILE_DEFAULT=nope python -c "import app.services.pattern_config as p; p.load()"` raises `PatternConfigError` naming `'nope'` and `chat, code`. With `PATTERN_PROFILE_DEFAULT=code` it returns `None`. This needs `OPENROUTER_API_KEY` / `ADMIN_TOKEN` set, or a `.env` that already has them.

### Task 4: `get_profile(name)`

- **File**: `app/services/pattern_config.py`
- **Action**: UPDATE
- **Implement**, directly after `get_policy()` (`:234`):
  ```python
  def get_profile(name: str) -> Profile:
      """The named profile from the policy in force, or `PatternConfigError`. ..."""
      profiles = _policy.profiles
      if name not in profiles:
          raise PatternConfigError(
              f"unknown pattern profile {name!r} (defined profiles: {_allowed(profiles)})"
          )
      return profiles[name]
  ```
  - Docstring: it reads the loaded policy, not the built-in one; it does no I/O (it is on STORY-008's request path); it raises the same error type as `load()` (AC 4). In practice it only raises for a call-site bug, because `load()` has already proven the default exists and PRD-014's `"code"` is a literal. `None` is not accepted; resolving it to the default is `run_conversation`'s job (PRD Section 6.6).
  - Update the module docstring's "deliberately **not** here yet" paragraph (`:27-32`). Replace it with one sentence saying profiles, the role matrix, the default cross-check and `get_profile()` landed in STORY-006. `inspect()` and the message walk remain STORY-008's.
- **Mirror**: `get_policy()` (`:234-241`).
- **Validate**: `python -c "import app.services.pattern_config as p; print(p.get_profile('code').roles); p.get_profile('nope')"` prints the map, then raises.

### Task 5: Adapt `tests/test_pattern_config.py` to the new rules

- **File**: `tests/test_pattern_config.py`
- **Action**: UPDATE
- **Implement**. Every edited test or fixture gets a comment of the form `# PRD-011 STORY-006: <rule> -- <what changed>` (Section 11 quality indicator):
  1. **Module docstring (`:9-11`)**: replace the "does not cover roles ... STORY-006" bullet with a pointer: roles, the default cross-check and `get_profile()` are covered in `tests/test_pattern_profiles.py`.
  2. **Autouse fixture `_default_profile_is_chat`**: `monkeypatch.setattr(settings, "PATTERN_PROFILE_DEFAULT", "chat")`. Every successful load in this module now depends on the default naming a defined profile, and a developer's `.env` must not decide that.
  3. **`test_load_compiles_every_pattern_once_at_load` (`:272-274`)**: rename profile `p` to `chat` and add `roles: {user: block}`.
  4. **`test_declared_order_survives_parsing` (`:315-317`)**: rename `p` to `chat`, add `roles: {user: block}`, and update `policy.profiles["p"]` to `["chat"]` (`:328`).
  5. **`_REGEX_FILE` (`:548-550`)**: rename `p` to `chat` and add `roles: {user: block}`. The success test `test_regex_list_loads_when_the_setting_is_true` depends on it. The three failure tests fail in `_parse_lists`, before profiles are reached, and are unaffected.
  6. **`_MALFORMED_CASES` "undefined-list-in-profile" (`:477-482`)**: add `roles:\n      user: block\n` to the profile body. Without it, the now-required `roles` key fails first and the case would stop testing what its id says. Check the other rows once: the list-level rows fail in `_parse_lists` first, `unknown-profile-key` reports the unknown key before any missing key, and `profile-missing-lists` still reports `'lists'` as the only missing key. No other row changes.
  7. **`test_roles_are_stored_but_not_validated_here` (`:344-374`)**: rewrite in place as `test_roles_are_validated_at_load`, as its docstring instructs. The same `martian: incinerate` file now raises `PatternConfigError` naming `profile 'p'` and `'martian'`. The comment cites PRD-011 STORY-006 AC 2. Coverage in depth lives in the new module; this one keeps the boundary marker honest.
  8. **`test_the_built_in_profiles_carry_the_section_6_4_matrix` (`:377-389`)**: keep the assertions. Update the docstring to say the cell-by-cell assertion now lives in `tests/test_pattern_profiles.py`.
  9. **New rows in `_MALFORMED_CASES`** (so `test_every_malformed_case_names_the_file_path` covers them for free): `unknown-role` (`roles: {admin: block}` → `["profile 'chat'", "unknown role", "'admin'", "assistant, system, tool, user"]`), `unknown-action` (`roles: {user: deny}` → `["profile 'chat'", "'user'", "unknown action", "'deny'", "block, flag"]`), `empty-roles` (`roles: {}` → `["profile 'chat'", "roles is empty"]`), `null-roles` (`roles:` with no value → `["profile 'chat'", "roles is empty"]`), `roles-not-a-mapping` (`roles: [user]` → `["profile 'chat'", "roles must be a mapping"]`), `missing-roles` (profile with only `lists:` → `["profile 'chat'", "missing key", "'roles'"]`). Each uses a single valid list `k` and a profile `chat` with `lists: [k]`.
- **Mirror**: the existing table rows at `:397-483`.
- **Validate**: `python -m pytest tests/test_pattern_config.py -v`, all green.

### Task 6: Create `tests/test_pattern_profiles.py`

- **File**: `tests/test_pattern_profiles.py`
- **Action**: CREATE
- **Implement**. Module docstring: `PRD-011 STORY-006`, what is covered, and what is not (`inspect()` and the walk are STORY-008's; the chat ingress passing no profile is STORY-008's). Copy the prologue (`os.environ.setdefault(...)`), copy the local `_reset_policy` fixture, not a conftest one, matching `tests/test_authz.py:123-126` and `tests/test_pattern_config.py:59-68`, and copy `_write`. Add the autouse `_default_profile_is_chat`. Tests:
  - **AC 1: the matrix, cell by cell.**
    - `_MATRIX = [("chat","system",None), ("chat","user","block"), ("chat","assistant",None), ("chat","tool",None), ("code","system",None), ("code","user","block"), ("code","assistant",None), ("code","tool","flag")]`, parametrized with ids like `chat-system-not-inspected`. It asserts `BUILT_IN_POLICY.profiles[p].roles.get(role) == expected`, and **for `None` cells additionally** `role not in roles`. A key mapped to a falsy value is not the same as an absent key, and absence is what "not inspected" means.
    - `test_the_matrix_has_no_cells_beyond_section_6_4`: `set(roles) == {…}` exactly for both profiles, and `set(BUILT_IN_POLICY.profiles) == {"chat","code"}`.
    - `test_built_in_profile_lists`: chat lists `["injection","keywords"]`, code lists `["injection"]`, by name and in order.
    - `test_every_built_in_role_and_action_is_in_the_vocabulary` (D-J): each key is in `get_args(Role)` and each value is in `("block","flag")`.
  - **AC 2: roles validation.** Parametrized table in this module's own style: unknown role, unknown action, empty map, null, non-mapping, missing key. Assert the profile name, the offending key and the allowed values appear in the message. Add a **positive** parametrization over every `(role, action)` in `get_args(Role) × ("block","flag")`, each loading cleanly and being stored as written. Add `test_roles_keep_declared_order` (`{tool: flag, user: block}` loads with `list(roles) == ["tool","user"]`).
  - **AC 3: resolved lists.** For both built-in profiles, every element of `profile.lists` is a `PatternList` and `is policy.lists[name]`. A file profile naming an undefined list raises `PatternConfigError` from `load()`: assert the type **and** `not isinstance(exc_info.value, KeyError)`, with a comment on why (startup, never request time).
  - **AC 4: default cross-check and `get_profile`.**
    - File path: a valid file defining only `chat`, with `PATTERN_PROFILE_DEFAULT="nope"`. `load()` raises, and the message contains `PATTERN_PROFILE_DEFAULT`, `'nope'`, `chat` and the file path. Afterwards `get_policy() is BUILT_IN_POLICY` (rebind-last holds).
    - Built-in path: `PATTERNS_FILE=""` and default `"nope"`. `load()` raises naming `'nope'` and `chat, code`, and `Path.read_text` is **never called** (the spy pattern from `test_load_reads_the_file_once_not_per_get_policy`, `tests/test_pattern_config.py:663-682`).
    - Built-in path with default `"code"`: `load()` returns `None`.
    - File path whose only profile is `code`, with default `"code"`: loads.
    - `get_profile("chat") is get_policy().profiles["chat"]`; `get_profile("code")` returns the code profile.
    - `get_profile("nope")` raises `PatternConfigError` naming `'nope'` and `chat, code`.
    - After loading a file whose only profile is `chat`, `get_profile("code")` raises. This proves `get_profile` reads the loaded policy, not the built-in one.
  - **AC 5: `Role` is reused, not redefined.**
    - `test_pattern_config_uses_the_messages_role`: `pattern_config.Role is app.models.messages.Role`, and `get_args(get_type_hints(Profile)["roles"])[0] is Role`.
    - `test_every_role_member_is_an_accepted_roles_key`: parametrized over `get_args(Role)`, so a role added to `messages.py` is automatically accepted here. This is the AC's literal wording.
  - **Technical Notes: the asymmetry is documented.** `test_profile_docstring_states_absent_means_not_inspected`: `Profile.__doc__` contains `not inspected` and `authz`. It is cheap, and it stops the paragraph being "tidied" away.
- **Mirror**: `tests/test_pattern_config.py` throughout. Its sections are split with `# --- AC n: ... ---` banners.
- **Validate**: `python -m pytest tests/test_pattern_profiles.py -v`, all green.

### Task 7: Full regression

- **Action**: run only; no edits.
- **Implement**: run the pattern and config suites, then the full suite. If there are mass fixture errors, restart the libSQL container instead of bisecting (PRD Section 11 quality indicator; known dev-server degradation).
- **Validate**: see *Validation* below.

---

## End-to-End Tests

There is no HTTP surface in this story, and none is to be added (D-K). The end-to-end check is the startup contract, run from the repo root:

- [ ] `PATTERNS_FILE` unset and `PATTERN_PROFILE_DEFAULT` unset: `python -c "import app.services.pattern_config as p; p.load(); print(sorted(p.get_policy().profiles))"` prints `['chat', 'code']`
- [ ] `PATTERNS_FILE` unset and `PATTERN_PROFILE_DEFAULT=nope`: the same command raises `PatternConfigError` naming `PATTERN_PROFILE_DEFAULT`, `'nope'` and `chat, code`
- [ ] A temporary YAML with `roles: {admin: block}`: `load()` raises naming the profile, `'admin'` and `assistant, system, tool, user`
- [ ] A temporary YAML with `roles: {}`: `load()` raises `roles is empty`
- [ ] `git grep -n '"assistant"' app/services/pattern_config.py` returns nothing. There is no second role literal. `Role` is imported (AC 5).
- [ ] `git grep -n "profile" app/routers app/models/schemas.py` shows no new request field (T1, D-K)
- [ ] `uvicorn app.main:app` still starts. `load()` is not registered in the lifespans until STORY-007, so this only proves the import graph (the new `messages` import) is sound

---

## Validation

```bash
# libSQL dev server must be running (tests/conftest.py _libsql_endpoint)
python -m pytest tests/test_pattern_profiles.py tests/test_pattern_config.py -v
python -m pytest tests/test_config.py tests/test_messages.py tests/test_pattern_matching.py tests/test_pattern_characterization.py -v
python -m pytest tests/ -q
```

`tests/test_config.py:551-569` (`Settings` accepts an undefined profile name) must pass **unchanged**. That split of responsibility is the premise of AC 4.

---

## Risks & Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| R-1 | Making `roles` required and adding the default cross-check turns existing successful-load fixtures red. | Enumerated exactly in Task 5 (items 3–6). Task 2's validation step checks that the red set is exactly that list before any fixture is edited. |
| R-2 | A developer's `.env` sets `PATTERN_PROFILE_DEFAULT` to something other than `chat`, and pattern tests fail locally but not in CI. | Autouse `_default_profile_is_chat` in both pattern test modules. Tests that need another default set it explicitly. |
| R-3 | STORY-008 wants `Action` or `Profile` inside `pattern_detector` for `PatternHit` / `inspect()`. It cannot import `pattern_config`, because `pattern_config` imports `pattern_detector`. | Out of scope here. It is recorded in this plan and in the `Action` alias comment so STORY-008 decides deliberately, for example by moving the `Action` literal down into `pattern_detector` or by typing `inspect()`'s `profile` parameter structurally. |
| R-4 | The empty-path cross-check changes `load()`'s no-op contract ("no file is read"). | It reads no file. The new AC 4 test spies `Path.read_text` on that path, and `test_load_is_noop_when_patterns_file_unset` stays green under the pinned `chat` default. |
| R-5 | STORY-007 wires `load()` into both lifespans, and a deployment with a bad default then fails at boot. | This is the intended behaviour (Section 2, "fail at startup"). STORY-007 should mention it in its lifespan test. Nothing to do here. |
| R-6 | Someone later "simplifies" the `None`-cell assertions to `.get(role) is None` and loses the absent-versus-present distinction. | The parametrized AC 1 test asserts `role not in roles` explicitly, with a comment. |

---

## Acceptance Criteria

(Copied from story `STORY-006`)

- [ ] Given the built-in policy, when its profiles are read, then `chat` is `lists: [injection, keywords]`, `roles: {user: block}` and `code` is `lists: [injection]`, `roles: {user: block, tool: flag}`: the matrix in PRD Section 6.4, asserted cell by cell, including the four "not inspected" cells.
- [ ] Given a profile's `roles:` map, when it names a role outside `Literal["system", "user", "assistant", "tool"]` or an action outside `block | flag`, then `load()` raises `PatternConfigError` naming the profile, the key and the allowed values. An empty `roles:` map is likewise an error (PRD 9.2 T5).
- [ ] Given a profile, when it is built, then its `lists` are resolved to `PatternList` objects at load time, so an undefined list name is a startup error and can never surface as a request-time `KeyError`.
- [ ] Given `PATTERN_PROFILE_DEFAULT` naming a profile the loaded policy does not define, when `load()` runs, then it raises `PatternConfigError` naming the setting, the missing profile and the profiles that do exist. Given `get_profile("nope")`, then it raises the same error type.
- [ ] Given `Role` in `app/models/messages.py`, when the role vocabulary is needed, then it is imported from there. This story introduces no second role literal, and a test asserts every member of that `Literal` is an accepted `roles:` key.
- [ ] All tasks completed
- [ ] Backend imports cleanly and `uvicorn app.main:app` starts without error (no frontend in scope, so there is no lint step)
- [ ] Full `pytest tests/` green; `tests/test_config.py` unchanged
- [ ] Follows existing patterns (`_fail` / `_allowed` messages, rebind-last `load()`, local `_reset_policy`, substring assertions)
