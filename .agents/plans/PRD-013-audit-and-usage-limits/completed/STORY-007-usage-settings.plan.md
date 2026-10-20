---
story: STORY-007
prd: PRD-013
slug: usage-settings
title: "Limit and break-glass settings with startup validators"
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-013-audit-and-usage-limits        # all stories commit here, no per-story branch
created: 2026-10-18
---

# Plan: Limit and break-glass settings with startup validators

## Summary

`app/config.py` gains four fields in a new PRD-013 group after the PRD-012 block: `USAGE_LIMITS_ENABLED: bool = True`, `USAGE_DAILY_TOKEN_BUDGET: str = "*=1000000"`, `USAGE_REQUESTS_PER_MINUTE: str = "*=60"` and `BREAK_GLASS_INGRESSES: str = "query,chat"`. It also gains two validators and three parsed properties. The two limit maps are parsed by one module-level helper, `_parse_limit_map(setting, value)`. The field validator calls it so a bad value stops `Settings()`, and each property calls it again to return `dict[str, Optional[int]]`. `BREAK_GLASS_INGRESSES` is checked against `{"query", "chat"}`, with a dedicated message for `v1`, and exposed as `frozenset[str]`. Nothing in production reads any of the four yet: STORY-010, -011, -012 and -013 are the consumers. Tests go in a new block at the end of `tests/test_config.py`.

### Decisions

1. **Validate in the field validator, return the raw string, parse again in the property.** This mirrors `PII_ENTITIES_CODE`: `_validate_pii_entities_code` returns `value` unchanged and `pii_entities_code_list` does the parsing (`app/config.py:351-382`, `404-406`). Keeping the field a `str` means `monkeypatch.setattr(settings, "USAGE_...", "...")` keeps working for consumer tests, the way `test_config.py:32` patches `MODEL_ALLOWLIST`. F6's "parsed once" is read as "one parser, one shape". A map of a few entries is re-parsed on each property read, which costs microseconds. Caching it in a `PrivateAttr` would go stale under the monkeypatch idiom the suite relies on. Recorded for the report.
2. **One parser for both maps, with a per-setting example.** `_LIMIT_MAP_EXAMPLES = {"USAGE_DAILY_TOKEN_BUDGET": "*=1000000,admin=unlimited", "USAGE_REQUESTS_PER_MINUTE": "*=60,admin=120"}` follows the `_POSITIVE_LIMIT_DESCRIPTIONS` shape (`app/config.py:20-29`), so each message "shows a valid example" for its own setting.
3. **Value grammar is strict.** A value is `unlimited` (exact, lowercase) or matches `^[0-9]+$` and is `≥ 1`. The regex is there because a bare `int()` would accept `+5`, `1_000` and ` 7 `. `-5`, `1.5`, `abc` and `Unlimited` all get the "integer ≥ 1 or 'unlimited'" message. `0` gets a message that says 0 is not "off", and names the real switch, `USAGE_LIMITS_ENABLED=false`, the way `CHAT_SESSION_LIMIT`'s message names `CHAT_HISTORY_ENABLED` (`app/config.py:290-296`).
4. **Error order inside one map.** Each entry is checked left to right: no `=` or empty role, then a bad value, then a duplicate role. The missing `*` check runs last, after every entry parses. So `""` and `" , "` (no entries) report a missing `*`. Whitespace around a role or value is stripped (`_split_comma_list`, then `.strip()` on each side of the first `=`). Role names are not checked against RBAC (PRD Section 6.6).
5. **`BREAK_GLASS_INGRESSES`: `v1` is checked before unknown names.** So `"query,v1"` reports the `/v1` rule, not "unknown name". Names are case-sensitive, as `Ingress = Literal["query", "chat", "v1"]` is. `""` gives `frozenset()`. Duplicates such as `"chat,chat"` are accepted, since a set loses nothing. A test pins that.
6. **`.env.example` is not touched.** STORY-018 owns ".env docs", as PRD-012 left its `.env.example` to a later story (`tests/test_config.py:668`). The existing `.env.example` order tests only look at their own variables, so none goes red.
7. **No test asserts "no production code reads them".** That AC point is checked by review (End-to-End check 3). A grep test would have to be deleted by STORY-010.

## User Story

As a platform operator
I want the limits and the break-glass policy set in `.env` and checked at startup
So that a mistyped value stops the boot with a message naming it instead of silently disabling a limit

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-007-usage-settings.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md` (Sections 6.6, 6.8, 7 F6, 9.3)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (story type `technical`) |
| Complexity | LOW (story `small`) |
| Systems Affected | `app/config.py`, `tests/test_config.py` |
| Story | STORY-007 |
| PRD | PRD-013 |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch; it is checked out, HEAD `53f8ca1`) |
| Depends on | none |
| Blocks | STORY-010, STORY-013 |

---

## Skills In Use

None. `.agents/skills/` holds one skill, `frontend-design`. The story sets `skills: []` and says "No UI surface changes in this story".

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

---

## Patterns to Follow

### Naming / field group comment
```python
# SOURCE: app/config.py:204-208
    # PII for code (PRD-012). The `code` profile's PII policy is built from
    # these six. ... Nothing reads these yet -- each field names the story that
    # becomes its consumer.
```

### Error handling (validator returns the raw value; message names the setting, the bad input and the fix)
```python
# SOURCE: app/config.py:351-382
    @field_validator("PII_ENTITIES_CODE")
    @classmethod
    def _validate_pii_entities_code(cls, value: str) -> str:
        accepted = ", ".join(sorted(_PRESIDIO_ENTITY_NAMES))
        names = _split_comma_list(value)
        ...
        unknown = [name for name in names if name not in _PRESIDIO_ENTITY_NAMES]
        if unknown:
            raise ValueError(
                f"PII_ENTITIES_CODE names unknown Presidio entity type(s) "
                f"{', '.join(unknown)} (in {value!r}). Names are case-sensitive. "
                f"Accepted names: {accepted}."
            )
        return value
```

### Shared validator over several fields
```python
# SOURCE: app/config.py:310-325
    @field_validator("CONTEXT_MAX_MESSAGES", ..., "PII_MAX_CHARACTERS_CODE")
    @classmethod
    def _validate_positive_limit(cls, value: int, info) -> int:
        ...  info.field_name ...
```

### Tests
```python
# SOURCE: tests/test_config.py:95-97, 736-745
def _settings(**overrides) -> Settings:
    base = {"OPENROUTER_API_KEY": "test-key", "ADMIN_TOKEN": "test-token"}
    return Settings(_env_file=None, **{**base, **overrides})

@pytest.mark.parametrize("value", ["", "   ", " , ,"])
def test_an_empty_pii_entities_code_is_a_startup_error(value):
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, PII_ENTITIES_CODE=value)

    message = str(exc_info.value)
    assert "PII_ENTITIES_CODE" in message
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | UPDATE | Four fields, constants, `_parse_limit_map`, two validators, three properties |
| `tests/test_config.py` | UPDATE | New `PRD-013 STORY-007` block appended at the end; no existing test edited |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Baseline

- **Action**: none
- **Implement**: Record the pass count of `python -m pytest -q` and of `python -m pytest tests/test_config.py -q`.
- **Validate**: `python -m pytest -q`. A failure with `StorageError ... tcp connect error` in a test that passes alone is the known libSQL flakiness. On mass fixture errors, restart the `harness-libsql-dev` container before looking at code.

### Task 2: Module-level constants and the map parser

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**:
  - Add `import re` and `from typing import Optional` at the top.
  - After `_PRESIDIO_ENTITY_NAMES`, add a commented constant group (PRD-013):
    - `_UNLIMITED = "unlimited"`
    - `_LIMIT_MAP_EXAMPLES` (Decision 2)
    - `_LIMIT_VALUE_RE = re.compile(r"[0-9]+")`, used with `fullmatch`
    - `_BREAK_GLASS_ACCEPTED = frozenset({"query", "chat"})`, with a comment that `v1` is absent by design (D4)
  - After `_split_comma_list`, add `_parse_limit_map(setting: str, value: str) -> dict[str, Optional[int]]`. Its docstring gives the grammar and says that role names are not checked against RBAC (Section 6.6). It splits with `_split_comma_list` and, per entry, applies Decision 4:
    - no `=` or empty role → `f"{setting} entry {entry!r} is not a role=value pair. Example: {setting}={example}."`
    - bad value → `f"{setting} entry {entry!r} has value {raw!r}; each value must be an integer >= 1 or 'unlimited'. Example: ..."`
    - `0` → as above, plus `"0 does not turn the limit off; set USAGE_LIMITS_ENABLED=false for that."`
    - duplicate → `f"{setting} lists role {role!r} twice (in {value!r}). Each role may appear once. Example: ..."`
    - after the loop, no `*` → `f"{setting} must include a '*' entry, the limit for any role not listed, got {value!r}. Example: ..."`
    - `unlimited` maps to `None`.
- **Mirror**: `_scheme_of` / `_split_comma_list` (`app/config.py:63-80`) for helper placement and docstring tone.
- **Validate**: `python -c "from app.config import _parse_limit_map as p; print(p('USAGE_REQUESTS_PER_MINUTE', '*=60,admin=unlimited,auditor=10'))"` prints `{'*': 60, 'admin': None, 'auditor': 10}`.

### Task 3: Fields, validators, properties

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**:
  - After `PII_CODE_SKIP_CODE_BLOCKS`, add a group comment: "Usage limits and break-glass (PRD-013)". It says the defaults are provisional (PRD Section 9.3, Assumptions), chosen so ordinary use never reaches them, and that nothing reads these yet. Each field then gets its own comment naming its consumer:
    - `USAGE_LIMITS_ENABLED: bool = True` — the master switch for the gate and the charge. It is independent of `RBAC_ENABLED` (Section 6.6). Consumed by STORY-011 (gate) and STORY-012 (charge).
    - `USAGE_DAILY_TOKEN_BUDGET: str = "*=1000000"` — tokens per user per UTC day, by role, with `*` required. Consumed by STORY-010's `limits_for`.
    - `USAGE_REQUESTS_PER_MINUTE: str = "*=60"` — authorized attempts per user per minute, by role. Consumed by STORY-010.
    - `BREAK_GLASS_INGRESSES: str = "query,chat"` — the ingresses on which the `ADMIN_TOKEN` identity may reach the pipeline. It can tighten and never loosen, and `v1` is always refused. Consumed by STORY-013's step 2b.
  - `@field_validator("USAGE_DAILY_TOKEN_BUDGET", "USAGE_REQUESTS_PER_MINUTE")` `_validate_usage_limit_map(cls, value, info)` calls `_parse_limit_map(info.field_name, value)` and returns `value` (Decision 1).
  - `@field_validator("BREAK_GLASS_INGRESSES")` `_validate_break_glass_ingresses` (Decision 5):
    - `"v1"` in the names → `"BREAK_GLASS_INGRESSES may not include 'v1' (in {value!r}): ADMIN_TOKEN is never accepted on /v1, and this setting can only narrow where it is accepted. Accepted values: chat, query (any subset, or empty). Example: BREAK_GLASS_INGRESSES=query,chat."`
    - other unknown names → `"BREAK_GLASS_INGRESSES names unknown ingress(es) {', '.join(unknown)} (in {value!r}). Names are case-sensitive. Accepted values: chat, query (any subset, or empty)."`
    - returns `value`.
  - Properties, placed beside `pii_entities_code_list`:
    - `usage_daily_token_budget_map -> dict[str, Optional[int]]`
    - `usage_requests_per_minute_map -> dict[str, Optional[int]]`
    - `break_glass_ingresses -> frozenset[str]`, which is `frozenset(_split_comma_list(self.BREAK_GLASS_INGRESSES))`
- **Mirror**: `_validate_pii_entities_code` (`app/config.py:351-382`); `_validate_positive_limit`'s `info.field_name` (`app/config.py:310-325`); `pii_entities_code_list` (`app/config.py:404-406`).
- **Validate**: `python -c "from app.config import settings as s; print(s.USAGE_LIMITS_ENABLED, s.usage_daily_token_budget_map, s.usage_requests_per_minute_map, s.break_glass_ingresses)"` prints `True {'*': 1000000} {'*': 60} frozenset({...'query', 'chat'...})`. It must not raise against the developer's real `.env`, which sets none of the four.

### Task 4: Tests

- **File**: `tests/test_config.py`
- **Action**: UPDATE (append only)
- **Implement**: Add a block header `# --- PRD-013 STORY-007: usage-limit and break-glass settings ---`. Its comment says nothing reads the four yet, the consumers are STORY-010/011/012/013, and `.env.example` is STORY-018's. Define `_USAGE_VARS = (...)` with the four names. Every test builds with `_settings(DATABASE_URL=_LOCAL_URL, ...)`. Cases, mapped to the ACs:
  - **AC 1**: `test_usage_settings_available_with_documented_defaults`, with `monkeypatch.delenv` over `_USAGE_VARS`. It asserts `USAGE_LIMITS_ENABLED is True` and the three string defaults exactly. It also asserts the three parsed defaults: `{"*": 1000000}`, `{"*": 60}`, `frozenset({"query", "chat"})`.
  - `test_usage_limits_enabled_parses_the_string_false`: `"false"` → `is False`.
  - **AC 2**: `test_requests_per_minute_map_parses_roles_and_unlimited`. `"*=60,admin=unlimited,auditor=10"` → `== {"*": 60, "admin": None, "auditor": 10}`. Also parametrize the same over `USAGE_DAILY_TOKEN_BUDGET` → `usage_daily_token_budget_map`, since one parser serves both.
  - `test_limit_map_strips_whitespace_and_accepts_unlimited_star`: `" * = 5 , admin=unlimited ,"` → `{"*": 5, "admin": None}`, and `"*=unlimited"` → `{"*": None}`.
  - **AC 3**: `test_an_invalid_limit_map_is_a_startup_error`, parametrized over both settings × these `(value, offending)` cases:
    - `("admin=10", "admin=10")` — no `*` (the message quotes the whole value)
    - `("", "")` — empty, so no `*`
    - `("*=0", "*=0")`
    - `("*=-5", "*=-5")`
    - `("*=abc", "*=abc")`
    - `("*=1.5", "*=1.5")`
    - `("*=60,admin=Unlimited", "admin=Unlimited")`
    - `("*=60,admin=1,admin=2", "admin")` — role twice
    - `("*=60,admin", "admin")` — no `=`
    - `("*=60,=5", "=5")` — empty role

    Each asserts that the setting name and `offending` are in `str(exc_info.value)`, and that the setting's own `_LIMIT_MAP_EXAMPLES` entry is in the message (the "valid example").
  - `test_a_zero_limit_names_the_real_off_switch`: `"*=0"` → the message contains `USAGE_LIMITS_ENABLED`.
  - `test_limit_map_role_names_are_not_checked_against_rbac`: `"*=1,no-such-role=2"` is accepted (Section 6.6).
  - **AC 4, accepted**: parametrize `""`, `"chat"`, `"query"`, `"query,chat"`, `"chat,chat"` → constructs, and `break_glass_ingresses` equals the expected frozenset (`""` → `frozenset()`).
  - **AC 4, v1**: parametrize `"v1"`, `"query,v1"` → raises; the message contains `BREAK_GLASS_INGRESSES`, `ADMIN_TOKEN` and `/v1`.
  - **AC 4, unknown**: parametrize `"admin"`, `"Chat"`, `"query,console"` → raises; the message contains the setting, the bad name, `chat` and `query`, and does not contain `/v1`, so the two messages stay distinct.
- **Mirror**: `tests/test_config.py:660-775` (PRD-012 block: docstrings citing the AC, `_settings(DATABASE_URL=_LOCAL_URL, ...)`, `str(exc_info.value)` substring asserts).
- **Validate**: `python -m pytest tests/test_config.py -q`, all pass.

### Task 5: Full suite

- **Validate**: `python -m pytest -q` passes with the Task 1 figure plus the new tests. No existing test was edited.

---

## End-to-End Tests

- [ ] `python -m pytest tests/test_config.py -q` passes
- [ ] Boot check: with a `.env` that sets none of the four, `python -c "import app.config"` succeeds. With `USAGE_REQUESTS_PER_MINUTE=admin=10` exported, it fails with a message naming the setting, quoting `'admin=10'` and showing `*=60,admin=120`. With `BREAK_GLASS_INGRESSES=v1`, it fails saying `ADMIN_TOKEN` is never accepted on `/v1`.
- [ ] Review check (AC 5): `git grep -nE "USAGE_LIMITS_ENABLED|USAGE_DAILY_TOKEN_BUDGET|USAGE_REQUESTS_PER_MINUTE|BREAK_GLASS_INGRESSES|usage_daily_token_budget_map|usage_requests_per_minute_map|break_glass_ingresses" -- app chat_ui scripts app.py` matches only `app/config.py`
- [ ] Full suite green

---

## Validation

```bash
python -m pytest tests/test_config.py -q
python -m pytest -q
git grep -nE "USAGE_|BREAK_GLASS|break_glass_ingresses" -- app chat_ui scripts app.py
```

---

## Risks

| Risk | Mitigation |
|------|-----------|
| A developer's real `.env` or exported environment sets one of the four badly and `import app.config` fails for the whole suite | No `.env` sets them today (`git grep` over `.env.example` is empty). Tests use `_env_file=None` and `delenv` |
| Strict grammar (`Unlimited`, `1_000`) refuses a value an operator considers obviously fine | Intended: the story's point is that a typo stops the boot. The message shows a valid example |
| "Parsed once" read differently by the reviewer | Decision 1 records why the property re-parses; flagged for the report |
| STORY-008's `Identity` fields or STORY-010 need a different map shape | The shape is fixed by the story (`dict[str, Optional[int]]`, `None` = unlimited), matching PRD Section 6.6's `UsageLimits` |

---

## Acceptance Criteria

(Copied from story `STORY-007`)

- [ ] Given no new variables set, when `Settings()` is built, then `USAGE_LIMITS_ENABLED` is `True`, `USAGE_DAILY_TOKEN_BUDGET` is `"*=1000000"`, `USAGE_REQUESTS_PER_MINUTE` is `"*=60"` and `BREAK_GLASS_INGRESSES` is `"query,chat"`.
- [ ] Given `USAGE_REQUESTS_PER_MINUTE="*=60,admin=unlimited,auditor=10"`, when the parsed property is read, then it is `{"*": 60, "admin": None, "auditor": 10}`.
- [ ] Given a limit map with no `*` entry, a value of `0`, a negative or non-numeric value, a role listed twice, or an entry with no `=`, when `Settings()` is built, then it raises with a message that names the setting, quotes the offending entry and shows a valid example.
- [ ] Given `BREAK_GLASS_INGRESSES` set to `""`, `"chat"` or `"query"`, when `Settings()` is built, then it is accepted; given `"v1"` or `"query,v1"`, then it raises with a message saying `ADMIN_TOKEN` is never accepted on `/v1`; given an unknown name, then it raises naming the accepted values.
- [ ] Given the story's diff, when it is reviewed, then no production code reads the four settings yet, and `tests/test_config.py` covers every case above.
- [ ] All tasks completed
- [ ] Full test suite passes
- [ ] Follows existing patterns
