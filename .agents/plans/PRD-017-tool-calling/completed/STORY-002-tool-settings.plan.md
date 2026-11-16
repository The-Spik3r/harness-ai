---
story: STORY-002
prd: PRD-017
slug: tool-settings
title: V1_TOOLS_ENABLED and V1_TOOL_MODELS settings with startup validation
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-017-tool-calling        # all stories commit here, no per-story branch
created: 2026-11-15
---

# Plan: V1_TOOLS_ENABLED and V1_TOOL_MODELS settings with startup validation

## Summary

Add two fields to `Settings` in `app/config.py`, directly after `V1_SSE_KEEPALIVE_SECONDS`:

- `V1_TOOLS_ENABLED: bool = False`
- `V1_TOOL_MODELS: str = ""`

Also add a `v1_tool_models_list` property and one cross-field `model_validator(mode="after")`. The validator rejects any `V1_TOOL_MODELS` entry that is not in `MODEL_ALLOWLIST`. Its error message names the setting, the offending entries and an example. Nothing reads the settings yet: STORY-008 and STORY-010 will read them per request. `.env.example` is not touched (STORY-018 owns it). Tests go in a new block at the end of `tests/test_config.py`.

## User Story

As a platform operator
I want one switch that turns tool calling on, and an optional list of the models allowed to receive tools
So that upgrading changes nothing until I opt in, and agents get a clear refusal for a model that cannot call tools

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-002-tool-settings.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md` (Section 4 lines 50-51, 6.7 line 262, 9.3 lines 373-374, D3/D10/D16 lines 512, 519, 525)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | `app/config.py`, `tests/test_config.py` |
| Story | STORY-002 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| none | The only skill is `.agents/skills/frontend-design`, which covers UI. This story has no UI (story `skills: []`). | none |

---

## Decision settled here: `admin` and a non-empty `V1_TOOL_MODELS`

`authorize_model` lets the `admin` role send any model (`app/services/authz.py:76-78`, `:188-203`). It lets every role through when `RBAC_ENABLED=false` (`authz.py:194`). PRD-017 Section 4 (line 51) says an empty `V1_TOOL_MODELS` "means every model the caller may already use". Section 9.3 (line 374) says "empty = no extra restriction".

**The rule:**

- **`V1_TOOL_MODELS` is a capability list, not an authorization list.** It says which models can take `tools` (D3). A caller's role does not change what a model can do.
- **Empty: no extra check.** A `tools` request passes for any model the caller may already use. That includes any model for `admin`, and any model when `RBAC_ENABLED=false`.
- **Non-empty: one check for everybody.** A `tools` request must name a model in the list, whatever the role, `admin` included, and with RBAC off too. Otherwise it gets 400 `tools_not_supported`, `param: "tools"` (D16).
- **Consequence of the startup validator.** Every entry must also be in `MODEL_ALLOWLIST`, so with a non-empty list an `admin` cannot send `tools` to a model outside `MODEL_ALLOWLIST`. To allow that, the operator adds the model to both lists. That is the intended reading: the list is the operator's statement of which models can call tools.
- **Who enforces it.** This story only states the rule, in the field comment and in the validator docstring. The request-time check (`model in settings.v1_tool_models_list` when the list is non-empty, with no look at `identity.role`) belongs to STORY-008. Flag this to STORY-008's planner.

---

## Patterns to Follow

### Naming / field comment block
```
// SOURCE: app/config.py:364-374
    # OpenAI-compatible ingress (PRD-015 Section 9.3). Nothing reads these yet --
    # each field names the story that becomes its consumer. ...
    # Mount /v1 at all. Off: the routes are not included and /v1/* is 404.
    # Consumed by STORY-009's router mount.
    V1_ENABLED: bool = True
    # Seconds between `: keep-alive` comment lines on a buffered /v1 stream,
    # > 0 and <= 60. Consumed by STORY-013.
    V1_SSE_KEEPALIVE_SECONDS: float = 10.0
```

### Cross-field validator (the one existing `model_validator`)
```
// SOURCE: app/config.py:425-438
    @model_validator(mode="after")
    def _require_token_for_remote_endpoint(self) -> "Settings":
        """A remote endpoint without its credential is a startup error, not a retry.

        Both fields are needed, so this cannot be a field validator.
        """
        ...
        return self
```
`model_validator` is already imported (`app/config.py:5`).

### Error message style (setting, offending entries, rule, example)
```
// SOURCE: app/config.py:636-642 (BREAK_GLASS_INGRESSES unknown names) and :655-660 (V1_SSE_KEEPALIVE_SECONDS)
            raise ValueError(
                f"BREAK_GLASS_INGRESSES names unknown ingress(es) {', '.join(unknown)} "
                f"(in {value!r}). Names are case-sensitive. Accepted values: ..."
            )
            ...
                "streamed /v1 response. Example: V1_SSE_KEEPALIVE_SECONDS=10."
```
`hide_input_in_errors=True` (`app/config.py:167-172`) already keeps pydantic from adding `input_value=`. The message lists the offending entries only. It does not quote the whole value or `MODEL_ALLOWLIST`. Model ids are not secrets, but PRD-015 T6/T9 asks messages to name the rule and the location, so the offending entry, which the AC requires, is enough.

### List parsing
```
// SOURCE: app/config.py:110-112, :679-681
def _split_comma_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
...
    def break_glass_ingresses(self) -> frozenset[str]:
        return frozenset(_split_comma_list(self.BREAK_GLASS_INGRESSES))
```
Membership is an exact, case-sensitive match against `model_allowlist_list` (`app/config.py:683-685`), the same rule `/v1/models/{id}` uses (`app/routers/v1.py:387-389`, "Exact match, no aliasing (D4)").

### Tests
```
// SOURCE: tests/test_config.py:95-97, :1245-1253, :1273-1285
def _settings(**overrides) -> Settings:
    base = {"OPENROUTER_API_KEY": "test-key", "ADMIN_TOKEN": "test-token"}
    return Settings(_env_file=None, **{**base, **overrides})

def test_v1_settings_available_with_documented_defaults(monkeypatch):
    for var in _V1_VARS:
        monkeypatch.delenv(var, raising=False)
    result = _settings(DATABASE_URL=_LOCAL_URL)
    ...
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, V1_SSE_KEEPALIVE_SECONDS=value)
    message = str(exc_info.value)
    for fragment in _KEEPALIVE_RULE_FRAGMENTS:
        assert fragment in message, fragment
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | UPDATE | Two fields, one `model_validator`, one property |
| `tests/test_config.py` | UPDATE | New `PRD-017 STORY-002` block at the end (no existing assertion changes) |

Not touched: `.env.example` (AC 4, STORY-018), every reader (STORY-008, STORY-010).

---

## Tasks

### Task 1: Add the two fields

- **File**: `app/config.py`
- **Action**: UPDATE (insert after line 374, `V1_SSE_KEEPALIVE_SECONDS`, before the `# Action policy (PRD-016 ...)` block at 376)
- **Implement**: a group comment, `# Tool calling on /v1 (PRD-017 Section 4, 9.3). Nothing reads these yet -- STORY-008 (translation) and STORY-010 (step 7c) read them per request, the _context_limit_exceeded rule (Section 6.7), so tests flip them with monkeypatch.` Then:
  - `V1_TOOLS_ENABLED: bool = False`. Comment: off means PRD-015 byte for byte, `tools` refused as `tools_not_supported` exactly as today; `functions`/`function_call` are refused whatever the flag (D10).
  - `V1_TOOL_MODELS: str = ""`. Comment: comma list of the models a `tools` request may name, exact match. Empty means no extra restriction: every model the caller may already use, so any model for `admin` (D3, D16). When set, the list applies to every caller, `admin` and RBAC-off included, because it describes a model's capability, not a caller's permission. Each entry must be in `MODEL_ALLOWLIST` (validator below). Read through `v1_tool_models_list`.
- **Mirror**: `app/config.py:364-374`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Add the cross-field validator

- **File**: `app/config.py`
- **Action**: UPDATE (insert after `_validate_v1_sse_keepalive_seconds`, i.e. after line 661)
- **Implement**: `@model_validator(mode="after") def _validate_v1_tool_models(self) -> "Settings":`
  - `unknown = [m for m in _split_comma_list(self.V1_TOOL_MODELS) if m not in self.model_allowlist_list]`
  - If `unknown`: `raise ValueError(f"V1_TOOL_MODELS names model(s) not in MODEL_ALLOWLIST: {', '.join(unknown)}. Each entry must also be listed in MODEL_ALLOWLIST (exact, case-sensitive match); leave V1_TOOL_MODELS empty for no extra restriction. Example: V1_TOOL_MODELS=openai/gpt-4o,anthropic/claude-3.5-sonnet.")`
  - `return self`
  - Docstring: "Every entry in MODEL_ALLOWLIST, or a startup error (PRD-017 Section 9.3, D3, D16). Both fields are needed, so this cannot be a field validator, the way `_require_token_for_remote_endpoint` is not." Then state the admin rule from the section above: the list is a capability list that, when non-empty, applies to every role, `admin` included. Because of this check, `admin`'s any-model allowance (`authz.MODEL_ALLOWLIST_WILDCARD_ROLES`) does not reach `tools` requests once the list is set. The request-time check is STORY-008's. Empty or whitespace-only parses to `[]` and passes. Duplicate entries are allowed: they change nothing.
  - The value is not rewritten. The property does the parsing, as `pii_entities_code_list` does.
- **Mirror**: `app/config.py:425-438` (shape), `:636-642` and `:655-660` (message)
- **Validate**: same import check

### Task 3: Add the property

- **File**: `app/config.py`
- **Action**: UPDATE (after `model_allowlist_list`, line 683-685)
- **Implement**: `@property def v1_tool_models_list(self) -> list[str]: return _split_comma_list(self.V1_TOOL_MODELS)`
- **Mirror**: `app/config.py:667-669` (`pii_entities_code_list`)

### Task 4: Tests

- **File**: `tests/test_config.py`
- **Action**: UPDATE (append a block `# --- PRD-017 STORY-002: V1_TOOLS_ENABLED and V1_TOOL_MODELS ---`, with a header comment: nothing reads these yet, STORY-008/010 do; `.env.example` is STORY-018's)
- **Implement**:
  1. `test_tool_settings_available_with_documented_defaults(monkeypatch)`: delenv both vars, then `V1_TOOLS_ENABLED is False`, `V1_TOOL_MODELS == ""` and `v1_tool_models_list == []` (AC 1).
  2. `test_v1_tools_enabled_parses_the_string_true`: `"true"` gives `is True` (mirrors `:1256-1258`).
  3. `test_v1_tool_models_list_returns_stripped_names_in_order`: `MODEL_ALLOWLIST="gpt-4,openai/gpt-4o,anthropic/claude-3.5-sonnet"` and `V1_TOOL_MODELS="openai/gpt-4o, anthropic/claude-3.5-sonnet"` give `["openai/gpt-4o", "anthropic/claude-3.5-sonnet"]` (AC 2). Pass `MODEL_ALLOWLIST` explicitly so the developer's environment cannot change the result.
  4. `test_v1_tool_models_entry_outside_model_allowlist_is_a_startup_error`, parametrized:
     - one bad entry among good ones (`"openai/gpt-4o, mistral/x"`, offending `mistral/x`)
     - a case mismatch (`"OpenAI/GPT-4o"`), which proves exact matching
     - a non-empty list against an empty `MODEL_ALLOWLIST=""`

     Assert `ValidationError`, the fragments `"V1_TOOL_MODELS"`, `"MODEL_ALLOWLIST"` and `"Example"` plus the offending entry in the message, and the good entry *not* listed as offending (AC 3).
  5. `test_v1_tool_models_blank_parses_to_no_restriction`, parametrized over `"   "` and `" , ,"`: constructs, and `v1_tool_models_list == []`.
  6. `test_v1_tool_models_is_not_checked_against_any_role`: `MODEL_ALLOWLIST` without `x/y` and `V1_TOOL_MODELS="x/y"` still fail. Docstring: the setting has no admin exemption; `admin`'s wildcard (`authz.MODEL_ALLOWLIST_WILDCARD_ROLES`) is not consulted at startup. Keep this only if it adds something over test 4's empty-allowlist case. Otherwise drop it and leave the rule in the docstrings. The implementer decides; one of the two is enough.
- **Mirror**: `tests/test_config.py:1235-1292`
- **Do not** add a test asserting the vars are *absent* from `.env.example`. STORY-018 would have to delete it. AC 4 is checked with `git diff --stat .env.example` (empty) in the report.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_config.py tests/test_untouched_app.py -q`

---

## End-to-End Tests

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` prints OK with no `.env` change (defaults construct).
- [ ] `V1_TOOL_MODELS=nosuch/model .venv/Scripts/python -c "from app.config import Settings; Settings()"` fails, naming `V1_TOOL_MODELS`, `nosuch/model` and an example. Set this env only for that one command.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_config.py tests/test_untouched_app.py -q
git diff --stat .env.example   # must be empty (AC 4)
```
Full suite: deferred to orchestrator (user decision).

---

## Risks

| Risk | Mitigation |
|------|-----------|
| A developer's `.env` or exported `V1_TOOL_MODELS` breaks other tests at import (`settings = Settings()`, `app/config.py:688`) | The default is empty, and the dev `.env` does not set it (grep found no `V1_TOOL` anywhere in the repo). Tests use `_settings(_env_file=None, ...)` and `delenv`. |
| A later test changes `MODEL_ALLOWLIST` with `monkeypatch.setattr(settings, ...)` so it no longer covers `V1_TOOL_MODELS` | `validate_assignment` is off, so the after-validator runs only at construction. That is expected: it is a startup check, and STORY-008's request-time check reads both per request. |
| The `.env.example` order tests (`tests/test_config.py:1310-1318`) iterate over `_V1_VARS` | `_V1_VARS` lists names explicitly, so the new `V1_TOOL*` fields are not picked up. No existing test changes. |
| The admin rule gets lost before STORY-008 | It is stated in the field comment and the validator docstring, and in this plan's Decision section. The orchestrator should pass it to STORY-008. |

---

## Acceptance Criteria

(Copied from story `STORY-002`)

- [ ] Given no configuration, when settings load, then `V1_TOOLS_ENABLED` is `False` and `V1_TOOL_MODELS` is `""` (an empty parsed list). (Task 1, 3; test 1)
- [ ] Given `V1_TOOL_MODELS="openai/gpt-4o, anthropic/claude-3.5-sonnet"` with both in `MODEL_ALLOWLIST`, when settings load, then a `v1_tool_models_list` property returns the two stripped names in order. (Task 3; test 3)
- [ ] Given `V1_TOOL_MODELS` naming a model that is not in `MODEL_ALLOWLIST`, when settings load, then startup fails with a message naming the setting, the offending entry and an example, in the style of the existing `V1_SSE_KEEPALIVE_SECONDS` validator. (Task 2; test 4)
- [ ] Given `.env.example`, when read, then it is unchanged in this story (STORY-018 documents both settings). (`git diff --stat .env.example` empty)
- [ ] All tasks completed
- [ ] Backend imports without error
- [ ] Follows existing patterns
