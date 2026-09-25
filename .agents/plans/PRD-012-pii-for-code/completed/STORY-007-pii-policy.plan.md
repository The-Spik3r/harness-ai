---
story: STORY-007
prd: PRD-012
slug: pii-policy
title: "pii_policy: built-in chat and code policies, profile fallback, load() in both lifespans"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-012-pii-for-code        # all stories commit here, no per-story branch
created: 2026-09-25
---

# Plan: pii_policy: built-in chat and code policies, profile fallback, load() in both lifespans

## Summary

This story adds a new module, `app/services/pii_policy.py`. It holds:

- `PiiPolicy`, a frozen dataclass with the eight fields of PRD Section 6.2;
- `PiiConfigError`;
- two built-in policies, `chat` and `code`, built from `settings`;
- `get_pii_policy(name)`, which falls back to `chat` for any name it does not know;
- `load()`, which rebuilds both policies from `settings`, checks them for consistency, logs one INFO line for each pattern profile with no PII policy, and rebinds module state as its last statement.

It follows `pattern_config`'s get/load split:

- the policies are built once at import, so `get_pii_policy()` works before `load()` has run (every pipeline test that never boots an app depends on this);
- `load()` rebinds a private `_policies` mapping;
- a failed `load()` leaves the previous policies in force.

`load()` is registered in both lifespans directly after `pattern_config.load()`, because it reads the loaded pattern policy's profile names.

Nothing on the request path reads the new module yet. STORY-008 (`redact_for_policy`) and STORY-009 (pipeline) are its consumers.

## User Story

As a security admin
I want PII behaviour chosen by the same server-selected profile that chooses the pattern policy, falling back to the strictest policy for any unknown name
So that the permissive `code` behaviour is reachable only where the server intends it

## Story Reference

- Story file: `.agents/stories/PRD-012-pii-for-code/STORY-007-pii-policy.md`
- PRD: `.agents/PRDs/PRD-012-pii-for-code/PRD.md`: Sections 6.2 (D8), 6.3 (D1, D3), 6.10, 7/F5, 10
- Handoffs consumed: STORY-005 report ("read the six settings from `settings`; `pii_entities_code_list` is the parsed entity list; `PII_REDACTION_ENABLED` stays the master switch") and STORY-006 report ("nothing extra to build at startup; `pii_redactor.load()` already builds what `PII_ENTITIES_CODE` selects")

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/services/pii_policy.py` (new), `app/main.py`, `chat_ui/chat_ui/chat_ui.py`, `tests/conftest.py`, `tests/test_pii_policy.py` (new), `tests/test_main.py`, `tests/test_chat_ui_startup_guard.py` |
| Story | STORY-007 |
| PRD | PRD-012 |
| Epic Branch | `epic/PRD-012-pii-for-code` (commit directly on this branch) |
| Depends on | STORY-005 ✅ done (`ae97fc8`) |
| Blocks | STORY-008, STORY-009 |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | None. The story's `skills: []` and "Skills: none applicable" hold. `.agents/skills/` contains only `frontend-design`, which covers visual UI design. This story changes no UI. | — |

---

## Findings (measured before planning)

| # | Finding | Evidence | Consequence |
|---|---------|----------|-------------|
| F-1 | `pattern_config` has **no logger and no log calls**. There is no INFO format to copy. | `app/services/pattern_config.py` (no `logging` import) | Use the repo's logger idiom, `logger = logging.getLogger(__name__)` (`query_pipeline.py:43`, `reports.py:53`), with %-style arguments (`query_pipeline.py:259-260`). |
| F-2 | Profile names come from `pattern_config.get_policy().profiles`, a `Mapping` keyed by name. There is no dedicated accessor. | `pattern_config.py:150-160`, `255-262` | `load()` computes `sorted(set(get_policy().profiles) - set(_policies))`. |
| F-3 | The built-in pattern policy defines exactly `chat` and `code`, so under the default configuration **no** fallback line is logged. | `pattern_config.py:227-240` | The log test must install a pattern policy with an extra profile name. The default case asserts zero records. |
| F-4 | `pii_redactor.load()` already prebuilds both analyzers and runs first in both lifespans. | `pii_redactor.py:123-134`; `main.py:14`; `chat_ui.py:195` | `pii_policy.load()` builds no analyzer. `pii_policy` must **not** import `pii_redactor`, because STORY-008's `pii_redactor` will import `PiiPolicy` from here, and the reverse import would create a cycle. |
| F-5 | Reflex keeps lifespan tasks in an insertion-ordered dict and calls sync tasks inline, so registration order is run order and a raise stops startup. | `.venv/Lib/site-packages/reflex/app_mixins/lifespan.py:48, 95-106` | Registering `pii_policy.load` directly after `pattern_config.load` satisfies "runs after". The existing adjacency assertion (`pattern_config.load` right after `authz.load`, `test_chat_ui_startup_guard.py:62-68`) stays true. |
| F-6 | `conftest._default_pattern_policy` saves and restores `pattern_config._policy` directly, not through `monkeypatch`. | `tests/conftest.py:186-210` | Add a sibling autouse fixture for `pii_policy._policies`. A test that patches settings and calls `load()` must not leak its policies into the next test. |
| F-7 | Both entity settings are comma strings. The parsed forms are `list[str]` properties. | `config.py:125, 216, 400-406` | Policies store `tuple(settings.pii_entities_list)` and `tuple(settings.pii_entities_code_list)`, which keeps declared order. |
| F-8 | The "PRD-011 unknown-field schema test" is `test_no_route_accepts_messages_params_or_system`. It forbids `profile` on every request body. | `tests/test_query_pipeline_multiturn.py:602, 663-688` | No schema changes. The existing test is the proof, and it is run unchanged. |
| F-9 | `test_main.py`'s `_pattern_startup` fixture boots the FastAPI lifespan with RBAC and PII off and restores the pattern policy. | `tests/test_main.py:218-234` | Reuse it for the FastAPI lifespan tests. |

---

## Patterns to Follow

### Module shape: private state, public accessor, rebind-last load

```python
# SOURCE: app/services/pattern_config.py:244-262
#: The policy in force. Private, and read through `get_policy()`: a public name
#: would be captured by `from app.services.pattern_config import POLICY` at
#: import time and never see the loaded file (PRD-011 Section 7/F3).
_policy = BUILT_IN_POLICY


def get_policy() -> PatternPolicy:
    """The policy in force -- the built-in one until `load()` replaces it.

    Returns rather than raises when `load()` has never run. ...
    """
    return _policy
```

```python
# SOURCE: app/services/pattern_config.py:568-599
    global _policy
    ...
    _check_default_profile(profiles, f"PATTERNS_FILE '{path}'")

    _policy = PatternPolicy(lists=lists, profiles=profiles)
```

### Frozen dataclass with a PRD-citing docstring; Role from messages

```python
# SOURCE: app/services/pattern_config.py:83-86, 117-147
#: The role vocabulary is `app.models.messages.Role` and nothing else -- this
#: module introduces no second role literal (PRD-011 Section 6.2).
_ROLES = get_args(Role)

@dataclass(frozen=True)
class Profile:
    """A named set of lists plus the roles it inspects (PRD-011 Sections 6.2, 6.4).
    ...
    """
    name: str
    lists: tuple[PatternList, ...]
    roles: Mapping[Role, Action]
```

### Error handling: config error class with a docstring that lists what raises it

```python
# SOURCE: app/services/pattern_config.py:52-62
class PatternConfigError(Exception):
    """Raised by load() for every way PATTERNS_FILE can be wrong: ...

    Startup fails. There is no silent fallback to the built-in policy -- ...
    """
```

### Settings read at call time, never at import-captured values

```python
# SOURCE: app/services/pattern_config.py:522-535
    """... Read at call time, never at
    import, so a test's `monkeypatch.setattr(settings, ...)` is seen.
    """
    default = settings.PATTERN_PROFILE_DEFAULT
```

### Logging

```python
# SOURCE: app/services/query_pipeline.py:43, 259-260
logger = logging.getLogger(__name__)
...
    "pattern scan truncated: user_id=%s message_index=%d length=%d scanned=%d"
```

### Tests: autouse restore fixture

```python
# SOURCE: tests/conftest.py:186-210
@pytest.fixture(autouse=True)
def _default_pattern_policy(monkeypatch):
    """..."""
    monkeypatch.setattr(settings, "PATTERNS_FILE", "")
    monkeypatch.setattr(settings, "PATTERN_PROFILE_DEFAULT", "chat")
    original = pattern_config._policy
    yield
    pattern_config._policy = original
```

### Tests: caplog filtered by logger name

```python
# SOURCE: tests/test_query_pipeline_patterns.py:297-309
    with caplog.at_level(logging.WARNING, logger="app.services.query_pipeline"):
        result = _run([Message("user", _LONG)], call_openrouter=_Upstream())
    ...
    records = [r for r in caplog.records if r.name == "app.services.query_pipeline"]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
```

### Tests: FastAPI lifespan failure stops boot, previous state intact

```python
# SOURCE: tests/test_main.py:237-251
    with pytest.raises(PatternConfigError) as excinfo:
        with TestClient(app):
            pass
    ...
    assert pattern_config.get_policy() is BUILT_IN_POLICY
```

### Tests: Reflex lifespan probe (subprocess), registration and adjacency

```python
# SOURCE: tests/test_chat_ui_startup_guard.py:59-74
load = chat_ui_module.pattern_config.load
result["patterns_load_registered"] = load in tasks
result["patterns_load_adjacent"] = (
    load in tasks
    and chat_ui_module.authz.load in tasks
    and tasks.index(load) == tasks.index(chat_ui_module.authz.load) + 1
)
try:
    load()
    result["patterns_raised"] = None
except Exception as exc:
    result["patterns_raised"] = type(exc).__name__
```

### Lifespan registration comment style

```python
# SOURCE: chat_ui/chat_ui/chat_ui.py:200-205
# Same bypass (PRD-011 STORY-007): without this the chat UI would inspect
# prompts with the built-in pattern policy while the API enforces
# PATTERNS_FILE -- ...
app.register_lifespan_task(pattern_config.load)
```

---

## Design

### Files to CREATE
- `app/services/pii_policy.py`
- `tests/test_pii_policy.py`

### Files to UPDATE
- `app/main.py`: import and call `pii_policy.load()` after `pattern_config.load()`
- `chat_ui/chat_ui/chat_ui.py`: import and register `pii_policy.load` after `pattern_config.load`
- `tests/conftest.py`: autouse `_default_pii_policy` restore fixture
- `tests/test_main.py`: FastAPI lifespan order plus `PiiConfigError` stops boot
- `tests/test_chat_ui_startup_guard.py`: Reflex registration and order, no-op load, `PiiConfigError` raised

### Dependency order
1. `pii_policy.py`, which everything else imports
2. conftest fixture, before any test calls `load()`
3. unit tests
4. lifespan wiring in both apps
5. lifespan tests
6. full regression

### Decisions made here

| # | Decision | Why |
|---|----------|-----|
| P1 | `_policies: Mapping[str, PiiPolicy]` is built at **import** from the current `settings` (`_policies = _build_policies()`) and rebound by `load()`. There is no public `BUILT_IN_*` constant. | STORY-009's pipeline tests call `run_conversation` without booting an app, as `pattern_config.get_policy()` allows (F-2). A public constant would freeze import-time settings, and the story says tests that patch settings must call `load()` again, which this preserves. |
| P2 | `get_pii_policy(name: str) -> PiiPolicy` returns `_policies.get(name, _policies[FALLBACK_POLICY_NAME])`. It never raises and never logs. `FALLBACK_POLICY_NAME = "chat"` is a module constant with a comment citing D8. | It is on the request path (STORY-009), so it must not log per request. The PRD says the fallback is logged "once at startup per name". The constant makes "falls back to chat, not code" readable in one place, and the test pins its value. |
| P3 | `load()` order: build both → `_check_consistent(policy)` for each → compute fallback names → log → `_policies = built` **last**. A `PiiConfigError` leaves the previous mapping intact and logs nothing. | Same as `pattern_config.load()`: nothing is rebound until every rule has passed. |
| P4 | Fallback log: one `logger.info` per name, sorted: `"pii policy: pattern profile %r has no PII policy; it resolves to %r"`, with `(name, FALLBACK_POLICY_NAME)`. | AC 4: "naming it and saying it resolves to `chat`". Sorting makes the order deterministic for the test and for operators. The profile name is operator configuration, not request content, so logging it is fine (the same reasoning `pattern_config.py:291-296` gives for pattern text). |
| P5 | `_check_consistent(policy)` raises `PiiConfigError` for exactly one combination: `skip_fenced_blocks and not structure_safe`. The message names the policy and both fields. | PRD F5 names this combination. The story says to "define it and test the one combination `load()` checks". With built-ins, `code` always has `structure_safe=True`, so it is unreachable today. The test forces it by monkeypatching the private `_build_code_policy`. |
| P6 | Builders are split: `_build_chat_policy()`, `_build_code_policy()`, `_build_policies() -> dict[str, PiiPolicy]` keyed by `policy.name`. | This gives the test in P5 a seam without adding a public parameter. It also reads like `pattern_config._build_built_in()`. |
| P7 | `chat.input_roles = frozenset(get_args(Role))`. `code.input_roles = frozenset({"user", "assistant", "tool"})`, with `"system"` added when `PII_CODE_REDACT_SYSTEM`. | This uses PRD-010's `Role` vocabulary and nothing else. `chat` lists every role, so a future role added to `Role` is redacted under `chat` by default, the strict direction. A test pins `chat.input_roles == {"system", "user", "assistant", "tool"}` literally, so that widening is noticed. |
| P8 | `entities` are tuples from the settings properties (F-7). `threshold` is a float from the setting. `chat.max_characters = None`. `code.max_characters = settings.PII_MAX_CHARACTERS_CODE`. `chat.structure_safe = False`. `code.structure_safe = True`, which is **not** a setting. | These are the PRD Section 6.2 table cells exactly. The PRD's six settings do not include `structure_safe`, so it is fixed per built-in. |
| P9 | `PII_REDACTION_ENABLED` is **not** encoded in the policy. `load()` builds and logs regardless of it. | STORY-005's handoff says it stays the master switch, which is applied where redaction runs (`redact()` today, `redact_for_policy` in STORY-008). A policy is a description, and turning redaction off does not change which policy a profile maps to. |
| P10 | `pii_policy` imports `app.config.settings`, `app.models.messages.Role` and `app.services.pattern_config`. It does **not** import `pii_redactor` (F-4). | This avoids a cycle when STORY-008 imports `PiiPolicy` into `pii_redactor`. |
| P11 | Lifespan order in `main.py`: `init_db → pii_redactor.load → authz.load → pattern_config.load → pii_policy.load → authz.check_bootstrap`. Reflex uses the same order. | AC 5 requires "after `pattern_config.load()`". It sits beside the other pure configuration loads, before the bootstrap DB read (the comment at `chat_ui.py:200-204` names this group). |

### Risks

| Risk | Mitigation |
|------|------------|
| A developer's `.env` sets `PII_CODE_*` and a "default settings" test fails for a reason unrelated to the code. | The defaults test monkeypatches all six settings to `Settings.model_fields[name].default` before `load()`. It reads the defaults from the class, not from hard-coded literals, and a second assert pins the PRD literals. |
| A test that calls `load()` leaks its patched policies into later tests (pipeline suites in STORY-009). | Autouse `_default_pii_policy` in conftest restores `_policies` directly (F-6). |
| The lifespan order test becomes brittle if it patches the whole lifespan. | Record calls by wrapping the two module attributes (`pattern_config.load`, `pii_policy.load`) with `monkeypatch.setattr`. `main.py` calls them through the module (`pattern_config.load()`), so the wrapper is seen. |
| The Reflex probe cannot use monkeypatch (subprocess). | The probe assigns `chat_ui_module.pii_policy._build_code_policy = <inconsistent builder>` inside the child process before a second `load()` call. That process exits right after, so nothing leaks. |
| Import cycle `pattern_config ↔ pii_policy`. | `pattern_config` does not import `pii_policy`, and the dependency is one-way. |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/pii_policy.py` | CREATE | `PiiPolicy`, `PiiConfigError`, `FALLBACK_POLICY_NAME`, built-in builders, `get_pii_policy`, `load` |
| `tests/test_pii_policy.py` | CREATE | AC 1–4 unit tests |
| `tests/conftest.py` | UPDATE | Autouse `_default_pii_policy` restore fixture |
| `app/main.py` | UPDATE | `pii_policy.load()` after `pattern_config.load()` |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | Register `pii_policy.load` after `pattern_config.load` |
| `tests/test_main.py` | UPDATE | AC 5, FastAPI path |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | AC 5, Reflex path |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create `app/services/pii_policy.py`

- **File**: `app/services/pii_policy.py`
- **Action**: CREATE
- **Implement**:
  1. Module docstring in `pattern_config.py`'s style. It covers:
     - PRD-012 Sections 6.2, 6.3 and 7/F5;
     - the three entry points (`PiiPolicy`, `get_pii_policy`, `load`);
     - that it is loaded in both lifespans after `pattern_config.load()` (the `api_transformer` bypass);
     - that `PII_REDACTION_ENABLED` is applied by the redactor, not here (P9);
     - that the consumers are STORY-008 and STORY-009;
     - that this module never imports `pii_redactor` (P10).
  2. Imports: `logging`, `dataclasses.dataclass`, `typing.Mapping, Optional, get_args`, `from app.config import settings`, `from app.models.messages import Role`, `from app.services import pattern_config`.
  3. `logger = logging.getLogger(__name__)`.
  4. `class PiiConfigError(Exception):` The docstring says:
     - it is raised by `load()` for an inconsistent policy;
     - today's one check is `skip_fenced_blocks` without `structure_safe`;
     - it is essentially unreachable with built-in policies and validated settings, and reserved for a future policy file (PRD Section 13);
     - startup fails, with no fallback.
  5. `FALLBACK_POLICY_NAME = "chat"`, with a `#:` comment: D8. An unknown profile resolves to the strictest policy, never the most permissive one (PRD Sections 2 and 6.2).
  6. `@dataclass(frozen=True) class PiiPolicy` with the fields in PRD 6.2 order and types:
     - `name: str`
     - `input_roles: frozenset[Role]`
     - `output: bool`
     - `skip_fenced_blocks: bool`
     - `entities: tuple[str, ...]`
     - `threshold: float`
     - `max_characters: Optional[int]`
     - `structure_safe: bool`

     Give each field a `#:` comment from the 6.2 code block. The class docstring reproduces the chat/code table in short form and notes that `chat` lists `tool` for completeness (step 0 refuses it) and `system` because every message is redacted today.
  7. `_build_chat_policy()`: build `chat` with:
     - `input_roles=frozenset(get_args(Role))`
     - `output=True`
     - `skip_fenced_blocks=False`
     - `entities=tuple(settings.pii_entities_list)`
     - `threshold=settings.PII_SCORE_THRESHOLD`
     - `max_characters=None` (comment: `CONTEXT_MAX_CHARACTERS` already bounds it)
     - `structure_safe=False` (comment: keeps today's exact output)
  8. `_build_code_policy()`: build `code` with:
     - `roles = {"user", "assistant", "tool"}`, plus `"system"` if `settings.PII_CODE_REDACT_SYSTEM`, with a comment each for D3 and for `assistant` (T7);
     - `output=settings.PII_CODE_REDACT_OUTPUT` (D1)
     - `skip_fenced_blocks=settings.PII_CODE_SKIP_CODE_BLOCKS` (D2)
     - `entities=tuple(settings.pii_entities_code_list)` (D7)
     - `threshold=settings.PII_SCORE_THRESHOLD_CODE` (D6)
     - `max_characters=settings.PII_MAX_CHARACTERS_CODE` (D4)
     - `structure_safe=True`
  9. `_build_policies() -> dict[str, PiiPolicy]` returns `{p.name: p for p in (_build_chat_policy(), _build_code_policy())}`.
  10. `_check_consistent(policy)` raises `PiiConfigError(f"PII policy {policy.name!r}: skip_fenced_blocks requires structure_safe (fenced-block skipping is only defined for structure-safe replacement)")` when `policy.skip_fenced_blocks and not policy.structure_safe` (P5).
  11. `_policies: Mapping[str, PiiPolicy] = _build_policies()`, with a `#:` comment mirroring `pattern_config.py:249-251` (private, read through `get_pii_policy`).
  12. `get_pii_policy(name: str) -> PiiPolicy` (P2). The docstring says: it takes a name, never `None` (resolving the default is `run_conversation`'s job, STORY-009); an unknown name gets `chat`; no I/O, no logging; it works before `load()`.
  13. `load() -> None` (P3/P4): `global _policies`; `built = _build_policies()`; check each; `fallbacks = sorted(set(pattern_config.get_policy().profiles) - set(built))`; `logger.info(...)` per name; `_policies = built`. The docstring says it runs at startup only, after `pattern_config.load()` in both lifespans, rereads `settings` (so tests that patch settings call it again), raises `PiiConfigError`, and leaves the previous policies on failure.
- **Mirror**: `app/services/pattern_config.py:52-62` (error), `97-160` (dataclasses), `244-262` (private state and accessor), `538-599` (rebind-last load)
- **Validate**: `.venv/Scripts/python.exe -c "from app.services import pii_policy as p; print(p.get_pii_policy('chat')); print(p.get_pii_policy('code')); print(p.get_pii_policy('nope').name)"` prints both policies, then `chat`.

### Task 2: Autouse restore fixture in `tests/conftest.py`

- **File**: `tests/conftest.py`
- **Action**: UPDATE
- **Implement**:
  - Add `from app.services import pii_policy` beside the existing `pattern_config` import (line 64).
  - After `_default_pattern_policy`, add `@pytest.fixture(autouse=True) def _default_pii_policy():`. It saves `pii_policy._policies`, yields, and restores it directly.
  - Docstring: PRD-012 STORY-007. `load()` rebinds with a plain assignment, so this restores it for the same reason as `_default_pattern_policy`. A test that patches `PII_*` settings calls `load()` itself.
- **Mirror**: `tests/conftest.py:186-210`
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_pattern_config.py -q` (collection is unaffected, still green)

### Task 3: Unit tests `tests/test_pii_policy.py`

- **File**: `tests/test_pii_policy.py`
- **Action**: CREATE
- **Implement**: module docstring citing PRD-012 STORY-007 and Sections 6.2/6.3/F5. Helper `_defaults(monkeypatch)` sets all six `PII_*_CODE` / `PII_CODE_*` settings, plus `PII_ENTITIES` and `PII_SCORE_THRESHOLD`, to `Settings.model_fields[name].default`. Tests:

  **AC 1: shape**
  - `test_pii_policy_is_a_frozen_dataclass_with_the_section_6_2_fields`: `[f.name for f in dataclasses.fields(PiiPolicy)]` equals the eight names in order. Assigning to `policy.output` raises `dataclasses.FrozenInstanceError`.
  - `test_input_roles_use_the_messages_role_vocabulary`: `chat.input_roles == frozenset(get_args(Role))`, and every role of `code` is in `get_args(Role)`.

  **AC 2: chat**
  - `test_chat_policy_matches_the_section_6_2_table`, after `_defaults` and `load()`:
    - `input_roles == {"system","user","assistant","tool"}`
    - `output is True`
    - `skip_fenced_blocks is False`
    - `entities == tuple(settings.pii_entities_list)`
    - `threshold == settings.PII_SCORE_THRESHOLD`
    - `max_characters is None`
    - `structure_safe is False`
  - `test_chat_policy_reads_pii_entities_and_threshold_at_load`: patch `PII_ENTITIES="EMAIL_ADDRESS"` and `PII_SCORE_THRESHOLD=0.6`, then `load()`. They are reflected, which proves the policy is built at `load()` and not at import.

  **AC 3: code**
  - `test_code_policy_defaults`, after `_defaults` and `load()`:
    - `input_roles == {"user","assistant","tool"}`
    - `output is False`
    - `skip_fenced_blocks is True`
    - `entities == ("EMAIL_ADDRESS","PHONE_NUMBER","CREDIT_CARD","US_SSN","IBAN_CODE")`
    - `threshold == 0.40`
    - `max_characters == 200_000`
    - `structure_safe is True`
  - `test_code_policy_adds_system_when_pii_code_redact_system`: with `True`, `"system" in input_roles` and the other three roles are still present.
  - `@pytest.mark.parametrize` `test_code_policy_maps_output_and_skip_settings`: `PII_CODE_REDACT_OUTPUT` maps to `output` and `PII_CODE_SKIP_CODE_BLOCKS` maps to `skip_fenced_blocks`, for both values each. The asserts use `is`.
  - `test_code_policy_reads_entities_threshold_and_limit_settings`: patch `PII_ENTITIES_CODE="EMAIL_ADDRESS,PERSON"`, `PII_SCORE_THRESHOLD_CODE=0.7` and `PII_MAX_CHARACTERS_CODE=5000`, then `load()`. They are reflected, in declared order.

  **AC 4: fallback and logging**
  - `test_fallback_name_is_chat`: `FALLBACK_POLICY_NAME == "chat"`.
  - `test_unknown_name_resolves_to_chat_not_code`: `get_pii_policy("strict") is get_pii_policy("chat")`, `is not get_pii_policy("code")`, and `.name == "chat"`. The docstring cites D8: the fallback is the most masking policy.
  - `test_get_pii_policy_works_before_load`: without calling `load()`, `get_pii_policy("code").name == "code"`.
  - `test_get_pii_policy_does_not_log`: caplog at INFO around `get_pii_policy("unknown")` gives zero records from `app.services.pii_policy`.
  - `test_load_logs_nothing_for_the_built_in_pattern_policy`: under the default pattern policy (conftest), `load()` emits zero records from `app.services.pii_policy` (F-3).
  - `test_load_logs_one_info_line_per_profile_without_a_pii_policy`:
    - Set `pattern_config._policy = dataclasses.replace(BUILT_IN_POLICY, profiles={**BUILT_IN_POLICY.profiles, "strict": BUILT_IN_POLICY.profiles["chat"], "agent": BUILT_IN_POLICY.profiles["code"]})`. Conftest restores it.
    - `load()` under `caplog.at_level(logging.INFO, logger="app.services.pii_policy")`.
    - Assert exactly 2 records, all `levelno == logging.INFO`, in the order `agent`, `strict`. Each message contains the name's `repr` and `'chat'`. No record mentions `code` as a fallback.

  **PiiConfigError**
  - `test_load_raises_pii_config_error_for_skip_fenced_blocks_without_structure_safe`: monkeypatch `pii_policy._build_code_policy` to return `dataclasses.replace(<real code policy>, skip_fenced_blocks=True, structure_safe=False)`. `pytest.raises(PiiConfigError, match="skip_fenced_blocks")`. After the raise, `get_pii_policy("code")` is the object from before the call, so the previous policies are intact.
  - `test_built_in_policies_pass_the_consistency_check`: `_check_consistent` returns `None` for both built-ins, including `code` with `PII_CODE_SKIP_CODE_BLOCKS=False`.
  - `test_failed_load_logs_no_fallback_lines`: combine the extra pattern profile with the inconsistent builder. Zero INFO records, because the check runs before the log.
- **Mirror**: `tests/test_pattern_config.py:213-231` (before-load, failed load keeps previous); `tests/test_query_pipeline_patterns.py:297-309` (caplog)
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_pii_policy.py -q`

### Task 4: Wire `pii_policy.load()` into the FastAPI lifespan

- **File**: `app/main.py`
- **Action**: UPDATE
- **Implement**: add `pii_policy` to the `from app.services import ...` line (alphabetical: `authz, pattern_config, pii_policy, pii_redactor, pipeline_executor`). Insert `pii_policy.load()` on the line after `pattern_config.load()` and before `authz.check_bootstrap()`.
- **Mirror**: `app/main.py:11-19`
- **Validate**: `.venv/Scripts/python.exe -c "import app.main"`

### Task 5: Register `pii_policy.load` in the Reflex lifespan

- **File**: `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Implement**:
  - Add `pii_policy` to the line-13 import.
  - Directly after `app.register_lifespan_task(pattern_config.load)` (line 205), add a comment:
    ```
    # Same bypass (PRD-012 STORY-007): without this the chat UI would resolve
    # PII policy from import-time settings and never log a profile's fallback
    # to `chat`. After pattern_config.load because it reads the loaded pattern
    # profiles; Reflex runs tasks in registration order.
    ```
  - Then add `app.register_lifespan_task(pii_policy.load)`.
- **Mirror**: `chat_ui/chat_ui/chat_ui.py:200-205`
- **Validate**: the Task 7 probe (the chat UI imports cleanly in the subprocess)

### Task 6: FastAPI lifespan tests in `tests/test_main.py`

- **File**: `tests/test_main.py`
- **Action**: UPDATE
- **Implement**: a PRD-012 STORY-007 section after the PII lifespan tests, reusing `_pattern_startup` (F-9). Import `pii_policy` and `PiiConfigError`.
  - `test_lifespan_runs_pii_policy_load_after_pattern_config_load`:
    - `calls = []`;
    - wrap `pattern_config.load` and `pii_policy.load` with `monkeypatch.setattr(module, "load", recorder(original))`, where each recorder appends its module name and calls the original;
    - `with TestClient(app): pass`;
    - assert `calls == ["pattern_config", "pii_policy"]`.
  - `test_lifespan_fails_when_pii_policy_is_inconsistent`:
    - monkeypatch `pii_policy._build_code_policy` to the inconsistent builder (as in Task 3);
    - `with pytest.raises(PiiConfigError): with TestClient(app): pass`;
    - assert `get_pii_policy("code")` is unchanged.
  - `test_lifespan_pii_policy_reflects_settings`: patch `PII_CODE_REDACT_OUTPUT=True`, boot, and assert `get_pii_policy("code").output is True` inside the `with`. This proves `load()` really ran.
- **Mirror**: `tests/test_main.py:218-265`
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_main.py -q`

### Task 7: Reflex lifespan probe in `tests/test_chat_ui_startup_guard.py`

- **File**: `tests/test_chat_ui_startup_guard.py`
- **Action**: UPDATE
- **Implement**:
  1. Append to `_CHECK_SCRIPT`, after the pattern block and before `check_bootstrap`:
     ```python
     # PRD-012 STORY-007.
     pii_load = chat_ui_module.pii_policy.load
     result["pii_policy_load_registered"] = pii_load in tasks
     result["pii_policy_load_after_patterns"] = (
         pii_load in tasks and load in tasks
         and tasks.index(pii_load) == tasks.index(load) + 1
     )
     try:
         pii_load()
         result["pii_policy_raised"] = None
     except Exception as exc:
         result["pii_policy_raised"] = type(exc).__name__
     # Force the one inconsistent combination load() checks.
     import dataclasses
     _pp = chat_ui_module.pii_policy
     _real = _pp._build_code_policy()
     _pp._build_code_policy = lambda: dataclasses.replace(_real, skip_fenced_blocks=True, structure_safe=False)
     try:
         pii_load()
         result["pii_policy_forced_raised"] = None
     except Exception as exc:
         result["pii_policy_forced_raised"] = type(exc).__name__
     ```
  2. Tests:
     - `test_pii_policy_load_registered_after_pattern_config_load` asserts registered and after-patterns.
     - `test_pii_policy_load_is_a_noop_by_default` asserts `pii_policy_raised is None`.
     - `test_pii_policy_config_error_fails_chat_ui_startup` asserts registered and `pii_policy_forced_raised == "PiiConfigError"`. Its docstring repeats the file's "registration plus raise is a claim about startup" reasoning.
  3. The existing `patterns_load_adjacent` assertion is untouched and stays true (F-5).
- **Mirror**: `tests/test_chat_ui_startup_guard.py:59-74, 166-196`
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_chat_ui_startup_guard.py -q`

### Task 8: Regression sweep

- **Implement**: no code. Run the unchanged suites that pin the behaviour this story must not move:
  - `test_pattern_config.py`, `test_pattern_profiles.py`: pattern loading unchanged;
  - `test_query_pipeline_multiturn.py`: no request body accepts `profile` (F-8);
  - `test_pii_redactor.py`, `test_pii_characterization.py`, `test_pii_pattern_analyzer.py`: redactor untouched;
  - then the full suite.
- **Validate**: see the Validation section.

---

## End-to-End Tests

- [ ] `python -c "from app.services.pii_policy import get_pii_policy as g; assert g('chat').output and not g('code').output and g('anything') is g('chat')"` succeeds
- [ ] Boot the FastAPI app (`uvicorn app.main:app`, with the libSQL dev server and a valid `.env`). Startup completes and `/health` returns 200. With the built-in pattern policy, no `pii policy:` INFO line is logged.
- [ ] Boot with `PATTERNS_FILE=` a copy of `examples/patterns.yaml` that adds a third profile (for example `strict`). Exactly one INFO line names `'strict'` and `'chat'`.
- [ ] Chat UI probe (`tests/test_chat_ui_startup_guard.py`): `pii_policy.load` is registered directly after `pattern_config.load`, and a forced inconsistency raises `PiiConfigError`.
- [ ] `/query` behaviour is unchanged: `test_query_outcomes_regression.py` and `test_pii_redaction_integration.py` pass with no assertion changed (nothing on the request path reads `pii_policy` yet).

---

## Validation

```bash
# Precondition: the libSQL dev server the conftest requires
docker start harness-libsql-dev   # or the `docker run` line in README "Running Tests"

.venv/Scripts/python.exe -c "import app.main"                          # backend imports (server-start smoke)
.venv/Scripts/python.exe -m pytest tests/test_pii_policy.py -q
.venv/Scripts/python.exe -m pytest tests/test_main.py tests/test_chat_ui_startup_guard.py -q
.venv/Scripts/python.exe -m pytest tests/test_pattern_config.py tests/test_pattern_profiles.py tests/test_query_pipeline_multiturn.py tests/test_pii_redactor.py tests/test_pii_characterization.py tests/test_pii_pattern_analyzer.py -q
git diff --exit-code HEAD -- tests/test_pii_redactor.py tests/test_pii_characterization.py tests/test_pii_redaction_integration.py tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py tests/test_query_pipeline_multiturn.py
.venv/Scripts/python.exe -m pytest -q                                   # full suite
```

The repo has no linter configured and no npm frontend, and this story changes no UI, so there is no frontend lint step. If there are mass fixture errors, restart the libSQL container rather than bisecting code (PRD Section 11).

---

## Handoff (for later stories)

- **STORY-008 (`redact_for_policy`)**: `from app.services.pii_policy import PiiPolicy`. Read `policy.entities`, `policy.threshold`, `policy.skip_fenced_blocks` and `policy.structure_safe`. `pii_policy` never imports `pii_redactor`, so that import direction is safe. Apply `PII_REDACTION_ENABLED` inside `redact_for_policy`, because the policy does not carry it.
- **STORY-009 (pipeline)**: `get_pii_policy(profile_name)` once per request, with the name step 5 already resolved. It never raises and never logs. Tests that patch `PII_*` settings must call `pii_policy.load()`, and conftest restores the policies.
- **STORY-010**: `policy.max_characters` is `None` for `chat` and `PII_MAX_CHARACTERS_CODE` for `code`.

---

## Acceptance Criteria

(Copied from story `STORY-007`)

- [ ] Given `app/services/pii_policy.py`, when it is read, then the frozen `PiiPolicy` dataclass has the fields of PRD Section 6.2 (`name`, `input_roles`, `output`, `skip_fenced_blocks`, `entities`, `threshold`, `max_characters`, `structure_safe`), using PRD-010's `Role` type.
- [ ] Given the built-in `chat` policy, when it is built, then it matches the Section 6.2 table exactly: every role, output on, no fence skipping, `PII_ENTITIES`, `PII_SCORE_THRESHOLD`, `max_characters=None`, `structure_safe=False`.
- [ ] Given the built-in `code` policy, when it is built with default settings, then `input_roles` is `{user, assistant, tool}`, output off, fence skipping on, `PII_ENTITIES_CODE`, `PII_SCORE_THRESHOLD_CODE`, `PII_MAX_CHARACTERS_CODE`, `structure_safe=True`; with `PII_CODE_REDACT_SYSTEM=true` it adds `system`, and the other two booleans map as named.
- [ ] Given `get_pii_policy(name)` with a name that is neither `chat` nor `code`, when it is called, then it returns `chat`. Given `load()` at startup, then it logs one INFO line per profile name in the loaded pattern policy that has no PII policy, naming it and saying it resolves to `chat`.
- [ ] Given `app/main.py` and `chat_ui/chat_ui/chat_ui.py`, when each lifespan starts, then `pii_policy.load()` runs after `pattern_config.load()`, and a `PiiConfigError` stops the boot.
- [ ] All tasks completed
- [ ] Backend imports and the FastAPI app starts without error
- [ ] Full test suite green; no assertion changed in the PRD Section 11 protected files
- [ ] Follows existing patterns (`pattern_config` get/load split, conftest restore fixture, lifespan probe)
