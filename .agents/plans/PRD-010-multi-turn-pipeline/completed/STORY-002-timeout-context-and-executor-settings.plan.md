---
story: STORY-002
prd: PRD-010
slug: timeout-context-and-executor-settings
title: "Settings: upstream timeout, context limits and pipeline executor size"
type: NEW_CAPABILITY
complexity: SMALL
epic_branch: epic/PRD-010-multi-turn-pipeline        # all stories commit here, no per-story branch
created: 2026-09-17
---

# Plan: Settings: upstream timeout, context limits and pipeline executor size

## Summary

Add four new fields to `Settings` in `app/config.py`: `OPENROUTER_TIMEOUT_SECONDS: float = 120.0`, `CONTEXT_MAX_MESSAGES: int = 100`, `CONTEXT_MAX_CHARACTERS: int = 200_000`, `PIPELINE_MAX_WORKERS: int = 32`, grouped under one `# Multi-turn pipeline (PRD-010)` comment block, with each field's own comment naming the story that will consume it (STORY-005, STORY-008, STORY-006). Two validators enforce safe values at startup: one for the timeout (`> 0`, since `0` or negative would hang or fail every call instantly) and one shared `field_validator` over the three integer fields (`≥ 1`), following `_validate_chat_session_limit`'s message shape — naming the setting, the value received, and what it controls. `tests/test_config.py` gets a defaults test and parametrized invalid-value tests for all four fields, using the file's existing `_settings(**overrides)` helper. No production code reads these settings yet, and `.env.example` is left untouched (STORY-018's job). This is purely additive: every existing `Settings()`/`_settings()` call in the suite keeps working because all four fields have defaults.

## User Story

As a platform operator
I want the upstream timeout, the context limits and the pipeline executor size to be settings with safe defaults and startup validation
So that I can tune them per deployment and a bad value fails at boot rather than in production

## Story Reference

- Story file: `.agents/stories/PRD-010-multi-turn-pipeline/STORY-002-timeout-context-and-executor-settings.md`
- PRD: `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md` — sections 4 (Settings), 7 (F2), 9.3

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | SMALL |
| Systems Affected | `app/config.py`, `tests/test_config.py` |
| Story | STORY-002 |
| PRD | PRD-010 |
| Epic Branch | `epic/PRD-010-multi-turn-pipeline` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | The only skill in `.agents/skills/` is `frontend-design`, which covers UI and copy. This story is backend settings with no UI surface; the story's `skills: []` field and Technical Notes agree ("Skills: none applicable"). | — |

---

## Patterns to Follow

### Instructive `field_validator` naming the setting, value and consequence
```python
// SOURCE: app/config.py:132-148
@field_validator("CHAT_SESSION_LIMIT")
@classmethod
def _validate_chat_session_limit(cls, value: int) -> int:
    """At least one session listed, or a startup error (PRD-008).

    A limit of 0 renders an empty rail on a user who has sessions, which is
    a silent lie rather than a small list -- so it fails at startup the way
    a bad DATABASE_URL does, rather than being defaulted away.
    """
    if value < 1:
        raise ValueError(
            f"CHAT_SESSION_LIMIT must be at least 1, got {value}. It is the "
            "number of sessions the rail lists per user; 0 would render an "
            "empty rail for a user who has sessions. To turn transcript "
            "persistence off, set CHAT_HISTORY_ENABLED=false instead."
        )
    return value
```

### Grouped settings with a section comment naming the owning PRD/story
```python
// SOURCE: app/config.py:76-85
# Chat sessions (PRD-008). CHAT_HISTORY_ENABLED is the master switch for
# transcript persistence: false means no chat_sessions or chat_messages row
# is written, none is read, no rail is shown, and the chat behaves exactly
# as it did before this PRD (PRD-008 Section 9, Risk 1) -- the supported
# configuration for a deployment that must not hold prompt text at rest.
# CHAT_SESSION_LIMIT caps how many sessions the rail lists per user.
# Nothing reads either setting yet: app/services/chat_sessions.py, added by
# STORY-006, is the only consumer.
CHAT_HISTORY_ENABLED: bool = True
CHAT_SESSION_LIMIT: int = 50
```

### Test helper + parametrized invalid-value tests, string included for env coercion
```python
// SOURCE: tests/test_config.py:95-97, 302-313
def _settings(**overrides) -> Settings:
    base = {"OPENROUTER_API_KEY": "test-key", "ADMIN_TOKEN": "test-token"}
    return Settings(_env_file=None, **{**base, **overrides})


@pytest.mark.parametrize("limit", [0, -1, "0"])
def test_a_chat_session_limit_below_one_is_a_startup_error(limit):
    """AC 2: a limit of 0 renders an empty rail on a user who has sessions.

    `"0"` is parametrized alongside the ints because the environment supplies
    strings and pydantic coerces before the validator runs -- a validator
    written against the raw string would pass the int cases and leak this one.
    """
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, CHAT_SESSION_LIMIT=limit)

    assert "CHAT_SESSION_LIMIT" in str(exc_info.value)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | UPDATE | Add the four PRD-010 settings + two validators (timeout `> 0`; shared `≥ 1` over the three integer fields) |
| `tests/test_config.py` | UPDATE | Defaults test + parametrized invalid-value tests for all four settings |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add the four settings fields, grouped and commented

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**: After the `REPORTS_AGENTS_DIR` / `REPORTS_REPO_URL` block (currently ending at line 91, right before the `_validate_database_url` validator), add:
  ```python
  # Multi-turn pipeline (PRD-010). Defaults and startup validation land now;
  # no production code reads these yet -- each field names the story that
  # becomes its consumer.

  # Upstream request timeout in seconds, replacing the hard-coded 30.0.
  # Consumed by STORY-005's call_openrouter.
  OPENROUTER_TIMEOUT_SECONDS: float = 120.0

  # Max messages a conversation may carry into the pipeline. Consumed by
  # STORY-008's context-limit refusal.
  CONTEXT_MAX_MESSAGES: int = 100

  # Max total characters across message contents in a conversation -- the
  # sum of len(message.content) over all messages. Characters, not tokens,
  # is a documented proxy (PRD-010 Section 4, Out of Scope). Consumed by
  # STORY-008's context-limit refusal.
  CONTEXT_MAX_CHARACTERS: int = 200_000

  # Size of the dedicated pipeline executor thread pool, off the shared
  # anyio/default-executor pools. Consumed by STORY-006.
  PIPELINE_MAX_WORKERS: int = 32
  ```
- **Mirror**: `app/config.py:76-85` (`CHAT_HISTORY_ENABLED` / `CHAT_SESSION_LIMIT` block) — same shape: a section comment naming the owning PRD, a consumer note, then plain typed fields with defaults.
- **Validate**: `python -c "import app.config"` — module still imports (relies on `OPENROUTER_API_KEY`/`ADMIN_TOKEN`/`DATABASE_URL` from the developer's `.env`; if that fails locally for unrelated env reasons, defer to Task 3's test run).

### Task 2: Add startup validators for the four new fields

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**: Add a module-level constant next to the other module constants (near `_REMOTE_SCHEMES` / `_LOCAL_SCHEME`, around line 13), then two validators near the existing `_validate_chat_session_limit` (after it, before the `pii_entities_list` property):
  ```python
  # What each PRD-010 pipeline-size setting controls, quoted by its validator
  # so the message says why 0 or a negative value is rejected, not just that
  # it is.
  _PIPELINE_LIMIT_DESCRIPTIONS = {
      "CONTEXT_MAX_MESSAGES": "the maximum number of messages a conversation may carry into the pipeline",
      "CONTEXT_MAX_CHARACTERS": "the maximum total characters across message contents in a conversation",
      "PIPELINE_MAX_WORKERS": "the number of threads in the dedicated pipeline executor",
  }
  ```
  ```python
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

  @field_validator("CONTEXT_MAX_MESSAGES", "CONTEXT_MAX_CHARACTERS", "PIPELINE_MAX_WORKERS")
  @classmethod
  def _validate_positive_pipeline_setting(cls, value: int, info) -> int:
      """Each of these bounds a resource that cannot be 0 or negative (PRD-010)."""
      if value < 1:
          description = _PIPELINE_LIMIT_DESCRIPTIONS[info.field_name]
          raise ValueError(
              f"{info.field_name} must be at least 1, got {value}. It is {description}."
          )
      return value
  ```
- **Mirror**: `app/config.py:132-148` (`_validate_chat_session_limit`) for message shape; `info.field_name` is the standard pydantic v2 `field_validator` signature for a validator shared across multiple fields (used here because `CONTEXT_MAX_MESSAGES`, `CONTEXT_MAX_CHARACTERS` and `PIPELINE_MAX_WORKERS` share the identical `≥ 1` rule and only their description text differs — one function, not three near-duplicates).
- **Validate**: `cd G:/coding/harness-ai && python -c "from app.config import Settings; Settings(_env_file=None, OPENROUTER_API_KEY='k', ADMIN_TOKEN='t', DATABASE_URL='http://127.0.0.1:8080', OPENROUTER_TIMEOUT_SECONDS=0)"` — must raise `pydantic.ValidationError` mentioning `OPENROUTER_TIMEOUT_SECONDS`.

### Task 3: Tests — defaults and parametrized invalid values

- **File**: `tests/test_config.py`
- **Action**: UPDATE
- **Implement**: Append a new section at the end of the file (after the `CHAT_HISTORY_ENABLED` block, past line 364), headed by a comment block matching the file's existing style:
  ```python
  # --- PRD-010 STORY-002: upstream timeout, context limits, pipeline workers --
  #
  # Nothing reads these settings yet. What is asserted here is that each has
  # the documented default, and that a value of 0 or negative fails at
  # construction with a message naming the setting and what it controls.


  def test_multiturn_pipeline_settings_available_with_documented_defaults():
      """AC 1 / AC 3: all four settings exist with PRD-010 Section 9.3's defaults."""
      result = _settings(DATABASE_URL=_LOCAL_URL)

      assert result.OPENROUTER_TIMEOUT_SECONDS == 120.0
      assert result.CONTEXT_MAX_MESSAGES == 100
      assert result.CONTEXT_MAX_CHARACTERS == 200_000
      assert result.PIPELINE_MAX_WORKERS == 32


  @pytest.mark.parametrize("value", [0, 0.0, -1, "0"])
  def test_openrouter_timeout_seconds_at_or_below_zero_is_a_startup_error(value):
      """AC 2: names the setting, the value received, and its purpose."""
      with pytest.raises(ValidationError) as exc_info:
          _settings(DATABASE_URL=_LOCAL_URL, OPENROUTER_TIMEOUT_SECONDS=value)

      message = str(exc_info.value)
      assert "OPENROUTER_TIMEOUT_SECONDS" in message
      assert "upstream request timeout in seconds" in message


  @pytest.mark.parametrize(
      "field,value",
      [
          ("CONTEXT_MAX_MESSAGES", 0),
          ("CONTEXT_MAX_MESSAGES", -1),
          ("CONTEXT_MAX_MESSAGES", "0"),
          ("CONTEXT_MAX_CHARACTERS", 0),
          ("CONTEXT_MAX_CHARACTERS", -1),
          ("CONTEXT_MAX_CHARACTERS", "0"),
          ("PIPELINE_MAX_WORKERS", 0),
          ("PIPELINE_MAX_WORKERS", -1),
          ("PIPELINE_MAX_WORKERS", "0"),
      ],
  )
  def test_a_pipeline_size_setting_below_one_is_a_startup_error(field, value):
      """AC 3: each of the three integer settings, in the _validate_chat_session_limit style.

      `"0"` sits alongside the ints for the same reason CHAT_SESSION_LIMIT's
      equivalent test does: the environment supplies strings, and pydantic
      coerces before the validator runs.
      """
      with pytest.raises(ValidationError) as exc_info:
          _settings(DATABASE_URL=_LOCAL_URL, **{field: value})

      assert field in str(exc_info.value)


  def test_pipeline_size_settings_accept_the_boundary_value_of_one():
      result = _settings(
          DATABASE_URL=_LOCAL_URL,
          CONTEXT_MAX_MESSAGES=1,
          CONTEXT_MAX_CHARACTERS=1,
          PIPELINE_MAX_WORKERS=1,
      )

      assert result.CONTEXT_MAX_MESSAGES == 1
      assert result.CONTEXT_MAX_CHARACTERS == 1
      assert result.PIPELINE_MAX_WORKERS == 1


  def test_settings_construct_without_the_multiturn_pipeline_vars(monkeypatch):
      """The defaults are the module's, not a developer's exported environment."""
      for var in (
          "OPENROUTER_TIMEOUT_SECONDS",
          "CONTEXT_MAX_MESSAGES",
          "CONTEXT_MAX_CHARACTERS",
          "PIPELINE_MAX_WORKERS",
      ):
          monkeypatch.delenv(var, raising=False)

      fresh = _settings(DATABASE_URL=_LOCAL_URL)

      assert fresh.OPENROUTER_TIMEOUT_SECONDS == 120.0
      assert fresh.CONTEXT_MAX_MESSAGES == 100
      assert fresh.CONTEXT_MAX_CHARACTERS == 200_000
      assert fresh.PIPELINE_MAX_WORKERS == 32
  ```
- **Mirror**: `tests/test_config.py:274-364` (the PRD-008 STORY-001 section) — same section-comment header, same `_settings(**overrides)` helper, same `[0, -1, "0"]` parametrization idiom.
- **Validate**: `cd G:/coding/harness-ai && python -m pytest tests/test_config.py -v`

---

## End-to-End Tests

This story adds settings with no production consumer yet, so there is no user-facing flow to exercise. The checks are the test suite itself:

- [ ] `pytest tests/test_config.py -v` — new tests pass, no existing test in the file regresses
- [ ] `pytest` (full suite) — green; confirms no other module's `Settings()`/`_settings()` call broke now that four required-shaped-but-defaulted fields exist

---

## Validation

```bash
cd G:/coding/harness-ai
python -m pytest tests/test_config.py -v
python -m pytest
```

---

## Acceptance Criteria

(Copied from story `STORY-002`)

- [ ] Given `app/config.py`, when `Settings` is read, then it has `OPENROUTER_TIMEOUT_SECONDS: float = 120.0`, `CONTEXT_MAX_MESSAGES: int = 100`, `CONTEXT_MAX_CHARACTERS: int = 200_000` and `PIPELINE_MAX_WORKERS: int = 32`, grouped under a `# Multi-turn pipeline (PRD-010)` comment.
- [ ] Given `OPENROUTER_TIMEOUT_SECONDS=0` or a negative value, when `Settings()` is constructed, then it raises a validation error naming the setting, the value received, and that it is the upstream request timeout in seconds.
- [ ] Given `CONTEXT_MAX_MESSAGES=0`, `CONTEXT_MAX_CHARACTERS=0` or `PIPELINE_MAX_WORKERS=0` (and negatives), when `Settings()` is constructed, then each raises a validation error naming the setting and what it controls, in the `_validate_chat_session_limit` style. Parametrized tests in `tests/test_config.py` cover each.
- [ ] Given no environment overrides, when `Settings()` is constructed, then the four defaults above hold (test).
- [ ] Given the full test suite, when this story lands, then it is green. No code reads the new settings yet, and each field's comment names the story that consumes it (STORY-005, STORY-006, STORY-008).
- [ ] All tasks completed
- [ ] `.env.example` left untouched (STORY-018's scope)
- [ ] Follows existing patterns (`_validate_chat_session_limit` style, `_settings()` test helper)
