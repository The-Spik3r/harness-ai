---
story: STORY-003
prd: PRD-015
slug: v1-settings
title: "V1_ENABLED and V1_SSE_KEEPALIVE_SECONDS settings with startup validators"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-22
---

# Plan: V1_ENABLED and V1_SSE_KEEPALIVE_SECONDS settings with startup validators

## Summary

This story adds two fields to `Settings` in `app/config.py`, declared after `BREAK_GLASS_INGRESSES` as a PRD-015 block. `V1_ENABLED: bool = True` is a plain pydantic bool, so `"false"` parses to `False`, and it needs no validator. `V1_SSE_KEEPALIVE_SECONDS: float = 10.0` gets a `@field_validator` modelled on `_validate_openrouter_timeout_seconds`. Its check is written as `not 0 < value <= 60`, in the `_validate_pii_score_threshold_code` style, so NaN and `inf` are rejected as well. The error message names the setting, the value received, the accepted range (`> 0` and `<= 60`) and an example. The field is a float so that `0.5` is accepted. Nothing reads either field yet: STORY-009 mounts the router from `V1_ENABLED`, and STORY-013 reads the keep-alive interval. Tests go in a new `# --- PRD-015 STORY-003` block at the end of `tests/test_config.py`, use the existing `_settings(...)` helper and need no DB. Nothing is added to `.env.example`, because STORY-019 writes those entries, and no setting chooses the `/v1` profile (PRD Section 9.3).

## User Story

As a platform operator
I want a switch for the `/v1` ingress and a bounded keep-alive interval, both validated at startup
So that I can turn the door off and a mis-set value stops the boot with a message naming it

## Story Reference

- Story file: `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-003-v1-settings.md`
- PRD: `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` (Section 9.3)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `app/config.py`, `tests/test_config.py` |
| Story | STORY-003 |
| PRD | PRD-015 |
| Epic Branch | `epic/PRD-015-openai-compatible-endpoint` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | The only skill in `.agents/skills/` is `frontend-design`, which does not apply to a backend config change. The story lists `skills: []`. | — |

---

## Patterns to Follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| FIELD BLOCK | `app/config.py:331-356` | A section comment naming the PRD and the consuming stories, then one comment per field that ends with "Consumed by STORY-NNN" |
| VALIDATOR | `app/config.py:415-424` | `@field_validator("X")` + `@classmethod`, a one-line docstring with the PRD tag, and a `ValueError` naming the setting, `got {value}` and its purpose |
| NaN-SAFE RANGE | `app/config.py:544-558` | `if not 0 <= value <= 1:`, with a docstring explaining why NaN is rejected |
| EXAMPLE IN MESSAGE | `app/config.py:582-588` | The message ends with `Example: SETTING=value.` |
| DESCRIPTION MAP | `app/config.py:24-34` | `_POSITIVE_LIMIT_DESCRIPTIONS` lists only the integer `>= 1` settings, not every setting, so the new fields are **not** added to it (the story's condition, "if it lists every setting", is false) |
| TEST HELPER | `tests/test_config.py:95-97` | `_settings(DATABASE_URL=_LOCAL_URL, **overrides)` with `_env_file=None` |
| TEST BLOCK | `tests/test_config.py:941-984` | Section header comment, a `_VARS` tuple, a defaults test that `monkeypatch.delenv`s each var, and a bool switch asserted with `is False` from the string `"false"` |
| ERROR TEST | `tests/test_config.py:383-391` | `pytest.raises(ValidationError)`, then fragments asserted in `str(exc_info.value)` |

### Validator
```python
# SOURCE: app/config.py:415-424
@field_validator("OPENROUTER_TIMEOUT_SECONDS")
@classmethod
def _validate_openrouter_timeout_seconds(cls, value: float) -> float:
    """A non-positive timeout would hang forever or fail every call instantly (PRD-010)."""
    if value <= 0:
        raise ValueError(
            f"OPENROUTER_TIMEOUT_SECONDS must be greater than 0, got {value}. "
            "It is the upstream request timeout in seconds."
        )
    return value
```

### Tests
```python
# SOURCE: tests/test_config.py:383-391
@pytest.mark.parametrize("value", [0, 0.0, -1, "0"])
def test_openrouter_timeout_seconds_at_or_below_zero_is_a_startup_error(value):
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, OPENROUTER_TIMEOUT_SECONDS=value)
    message = str(exc_info.value)
    assert "OPENROUTER_TIMEOUT_SECONDS" in message
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | UPDATE | Add the two fields after `BREAK_GLASS_INGRESSES`, plus `_validate_v1_sse_keepalive_seconds` after `_validate_break_glass_ingresses` |
| `tests/test_config.py` | UPDATE | Add a `PRD-015 STORY-003` test block at the end of the file |

---

## Tasks

### Task 1: Add the two settings

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**: Place this directly after `BREAK_GLASS_INGRESSES: str = "query,chat"`:
  ```python
  # OpenAI-compatible ingress (PRD-015 Section 9.3). Nothing reads these yet --
  # each field names the story that becomes its consumer. No setting chooses
  # the /v1 profile: it is the literal "code" at the call site (PRD-011 D2).

  # Mount /v1 at all. Off: the routes are not included and /v1/* is 404.
  # Consumed by STORY-009's router mount.
  V1_ENABLED: bool = True

  # Seconds between `: keep-alive` comment lines on a buffered /v1 stream,
  # > 0 and <= 60. Consumed by STORY-013.
  V1_SSE_KEEPALIVE_SECONDS: float = 10.0
  ```
- **Mirror**: `app/config.py:331-356`
- **Validate**: `python -c "from app.config import Settings"` (imports cleanly)

### Task 2: Add the keep-alive validator

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**: Place this after `_validate_break_glass_ingresses`, before the `@property` block:
  ```python
  @field_validator("V1_SSE_KEEPALIVE_SECONDS")
  @classmethod
  def _validate_v1_sse_keepalive_seconds(cls, value: float) -> float:
      """Within (0, 60], or a startup error (PRD-015 Section 9.3).

      0 or less would spin or never fire; above 60 outlasts common proxy idle
      timeouts, which the keep-alive exists to beat. Written as
      `not 0 < value <= 60` so that NaN is rejected too, as
      _validate_pii_score_threshold_code does.
      """
      if not 0 < value <= 60:
          raise ValueError(
              f"V1_SSE_KEEPALIVE_SECONDS must be > 0 and <= 60, got {value}. "
              "It is the interval in seconds between keep-alive lines on a "
              "streamed /v1 response. Example: V1_SSE_KEEPALIVE_SECONDS=10."
          )
      return value
  ```
  `hide_input_in_errors=True` (`app/config.py:165-166`) removes pydantic's `input_value=` suffix, but `got {value}` is in our own text, so the value still appears in the message. The value is a number and never a secret.
- **Mirror**: `app/config.py:415-424`, `app/config.py:544-558`
- **Validate**: `python -c "from app.config import Settings"`

### Task 3: Tests

- **File**: `tests/test_config.py`
- **Action**: UPDATE (append at the end; do not edit any existing test, per AC 4)
- **Implement**: Add the block below.
  ```python
  # --- PRD-015 STORY-003: V1_ENABLED and V1_SSE_KEEPALIVE_SECONDS --------------
  #
  # Nothing reads these yet -- STORY-009 mounts /v1 from V1_ENABLED and
  # STORY-013 paces keep-alive lines from V1_SSE_KEEPALIVE_SECONDS.
  # `.env.example` is STORY-019's, not this block's.

  _V1_VARS = ("V1_ENABLED", "V1_SSE_KEEPALIVE_SECONDS")
  _KEEPALIVE_RULE_FRAGMENTS = ("V1_SSE_KEEPALIVE_SECONDS", "> 0", "<= 60", "Example")
  ```
  Tests:
  1. `test_v1_settings_available_with_documented_defaults(monkeypatch)`: `delenv` each var in `_V1_VARS`, then assert `V1_ENABLED is True` and `V1_SSE_KEEPALIVE_SECONDS == 10` (AC 1).
  2. `test_v1_enabled_parses_the_string_false`: `_settings(..., V1_ENABLED="false").V1_ENABLED is False` (AC 3).
  3. `test_v1_sse_keepalive_seconds_out_of_range_is_a_startup_error(value)`, parametrized over `0`, `-1`, `61`, `"0"`, `60.01`, `"nan"` and `"inf"`: assert that every fragment in `_KEEPALIVE_RULE_FRAGMENTS` appears in the message. For the numeric cases, also assert that the `got <value>` text is present, e.g. `"got 61"` (AC 2).
  4. `test_v1_sse_keepalive_seconds_accepts_the_range_bounds(value)`, parametrized over `0.5`, `60` and `"60"`: construction succeeds and the field equals `float(value)` (AC 2).
  5. `test_no_setting_chooses_the_v1_profile`: `not [n for n in Settings.model_fields if n.startswith("V1_") and "PROFILE" in n]`. This guards the story note "Do not add one".
- **Mirror**: `tests/test_config.py:941-984`, `tests/test_config.py:383-391`
- **Validate**: `pytest tests/test_config.py -q` (no DB needed; see the `-m "not db"` memory recipe if Docker is down)

---

## End-to-End Tests

This is a config-only story with no new route, so its E2E check is the boot behaviour:

- [ ] `V1_SSE_KEEPALIVE_SECONDS=0 python -c "import app.config"` exits non-zero with the message naming the setting, `> 0`, `<= 60` and the example
- [ ] `V1_SSE_KEEPALIVE_SECONDS=0.5 python -c "from app.config import settings; print(settings.V1_SSE_KEEPALIVE_SECONDS)"` prints `0.5`
- [ ] `V1_ENABLED=false python -c "from app.config import settings; print(settings.V1_ENABLED)"` prints `False`
- [ ] The app starts unchanged with nothing set (`uvicorn app.main:app`, `/health` 200)

---

## Validation

```bash
pytest tests/test_config.py -q
pytest -m "not db" -q        # full non-DB sweep: no other test changes
```

---

## Risks

| Risk | Mitigation |
|------|-----------|
| A developer's exported `V1_*` env var could change the outcome of the defaults test | The test `delenv`s each var, as the PRD-013 block does |
| pydantic accepts `"nan"`/`"inf"` for a float | The `not 0 < value <= 60` form rejects both, and both are covered by test cases |
| An existing `.env.example` order or coverage test picks up the new fields | Those tests filter on their own `_*_VARS` tuples (`tests/test_config.py:1121`), so new fields that are not in `.env.example` affect none of them |

---

## Acceptance Criteria

(Copied from story `STORY-003`)

- [ ] Given nothing configured, when settings load, then `V1_ENABLED is True` and `V1_SSE_KEEPALIVE_SECONDS == 10`.
- [ ] Given `V1_SSE_KEEPALIVE_SECONDS` of `0`, `-1` or `61`, when settings load, then startup fails with a message naming the setting, the value, the accepted range (`> 0` and `<= 60`) and an example; `0.5` and `60` are accepted.
- [ ] Given `V1_ENABLED=false`, when settings load, then it parses as `False` (the router mount that reads it is STORY-009).
- [ ] Given the existing config tests, when they run, then none changes.
- [ ] All tasks completed
- [ ] Backend imports and starts without error
- [ ] Follows existing patterns
