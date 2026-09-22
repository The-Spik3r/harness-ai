---
story: STORY-004
prd: PRD-011
slug: pattern-settings
title: "Four pattern-policy settings with startup validators"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-011-pattern-policy        # all stories commit here, no per-story branch
created: 2026-09-22
---

# Plan: Four pattern-policy settings with startup validators

## Summary

Add PRD-011's four knobs to `app/config.py` — `PATTERNS_FILE: str = ""`, `PATTERN_PROFILE_DEFAULT: str = "chat"`, `PATTERNS_ALLOW_REGEX: bool = False`, `PATTERN_MAX_SCAN_CHARACTERS: int = 1_000_000` — document all four in `.env.example`, declare `PyYAML` explicitly in `requirements.txt`, and extend `tests/test_config.py` with the defaults, the validators and the `.env.example` coverage checks. **Nothing reads any of the four in this commit.** That is the point: it mirrors PRD-010 STORY-002, which landed four settings one commit ahead of their consumers so that a settings change and a behaviour change never share a revert.

The one design call worth stating up front is how `PATTERN_MAX_SCAN_CHARACTERS` gets its `>= 1` validator. `app/config.py` already has exactly the machinery: a module-level description mapping (`_PIPELINE_LIMIT_DESCRIPTIONS`) read by one shared `field_validator` (`_validate_positive_pipeline_setting`) that composes `"{field} must be at least 1, got {value}. It is {description}."` from `info.field_name`. The story asks to reuse that mapping pattern rather than inline prose in the `raise`. Reuse here means **joining** the existing mapping and validator, not copying them into a one-entry twin — so both are renamed to drop the PRD-010-specific word "pipeline" (`_POSITIVE_LIMIT_DESCRIPTIONS`, `_validate_positive_limit`) and `PATTERN_MAX_SCAN_CHARACTERS` becomes the fourth field in the decorator's list. Both names are private, neither is referenced anywhere outside `app/config.py` (verified: the only other hit in the repository is prose in `.agents/reports/PRD-010-multi-turn-pipeline/STORY-002-*.report.md`), and no test asserts on either name — the PRD-010 tests assert on the *field* name appearing in the message, which the rename does not touch.

`PATTERN_PROFILE_DEFAULT` deliberately gets no membership validator. Whether `chat` names a profile that exists is a cross-check between a setting and a file, and the file is not read when `Settings` is constructed — `pattern_config.load()` owns that check (PRD Section 9.3; the error text itself is STORY-006's AC). What lands here is a non-empty check plus a field comment saying where the real validation lives, so the next reader does not "fix" the apparent omission.

## User Story

As a platform operator
I want the pattern policy's four knobs to exist with safe defaults and instructive startup errors
So that a misconfiguration stops the boot with a message telling me what to set instead

## Story Reference

- Story file: `.agents/stories/PRD-011-pattern-policy/STORY-004-pattern-settings.md`
- PRD: `.agents/PRDs/PRD-011-pattern-policy/PRD.md` — sections 4 (Settings), 6.6, 6.9, 8, 9.3

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (configuration surface, no behaviour) |
| Complexity | LOW |
| Systems Affected | `app/config.py`, `.env.example`, `requirements.txt`, `tests/test_config.py` |
| Story | STORY-004 |
| PRD | PRD-011 |
| Epic Branch | `epic/PRD-011-pattern-policy` (commit directly on this branch) |

---

## Skills In Use

`.agents/skills/` holds exactly one skill, `frontend-design` (visual design for new or reshaped UI). This story touches no UI — four settings, one `.env.example` block, one requirements line and a test module. Its `description` does not match the story domain, so nothing is carried into the tasks below. This agrees with the story's `skills: []`.

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | None. `frontend-design` is the only skill present and is out of domain. | — |

---

## Patterns to Follow

### Settings group with a comment naming the not-yet-existing consumer

```python
# SOURCE: app/config.py:102-122
    # Multi-turn pipeline (PRD-010). Defaults and startup validation land now;
    # no production code reads these yet -- each field names the story that
    # becomes its consumer.

    # Upstream request timeout in seconds, replacing the hard-coded 30.0.
    # Consumed by STORY-005's call_openrouter.
    OPENROUTER_TIMEOUT_SECONDS: float = 120.0

    # Max messages a conversation may carry into the pipeline. Consumed by
    # STORY-008's context-limit refusal.
    CONTEXT_MAX_MESSAGES: int = 100
```

This is the exact shape AC 1 asks for: a group header naming the PRD and stating that nothing reads the group yet, then one comment per field naming the story that becomes its consumer.

### Description mapping + one shared validator

```python
# SOURCE: app/config.py:15-22
# What each PRD-010 pipeline-size setting controls, quoted by its validator
# so the message says why 0 or a negative value is rejected, not just that
# it is.
_PIPELINE_LIMIT_DESCRIPTIONS = {
    "CONTEXT_MAX_MESSAGES": "the maximum number of messages a conversation may carry into the pipeline",
    ...
}

# SOURCE: app/config.py:192-201
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

### Error message that says what to set instead

```python
# SOURCE: app/config.py:163-179
        if value < 1:
            raise ValueError(
                f"CHAT_SESSION_LIMIT must be at least 1, got {value}. It is the "
                "number of sessions the rail lists per user; 0 would render an "
                "empty rail for a user who has sessions. To turn transcript "
                "persistence off, set CHAT_HISTORY_ENABLED=false instead."
            )
```

Field name, rejected value, what the field bounds, and the alternative setting to reach for. AC 2 asks for the first three; the fourth is what makes the `CHAT_SESSION_LIMIT` message the one the story names.

### `.env.example` block

```bash
# SOURCE: .env.example:66-82
# Multi-turn pipeline (PRD-010)

# Seconds to wait for the upstream provider before giving up; must be > 0.
# Replaces the old hard-coded 30s, too short for a long conversation
OPENROUTER_TIMEOUT_SECONDS=120.0

# Most messages one conversation may send to the pipeline, new turn included;
# checked first, and the only limit named when both are exceeded (min 1)
CONTEXT_MAX_MESSAGES=100
```

A bare group header line, then one or two comment lines per variable, then `NAME=value` with the same default the field carries. AC 4 names the `CONTEXT_MAX_*` block; this is it.

### Tests: defaults, rejection, boundary, absence, and `.env.example`

```python
# SOURCE: tests/test_config.py:373-391, 408-418, 452-461
def test_multiturn_pipeline_settings_available_with_documented_defaults():
    result = _settings(DATABASE_URL=_LOCAL_URL)
    assert result.OPENROUTER_TIMEOUT_SECONDS == 120.0
    ...

@pytest.mark.parametrize("field,value", [("CONTEXT_MAX_MESSAGES", 0), ..., ("PIPELINE_MAX_WORKERS", "0")])
def test_a_pipeline_size_setting_below_one_is_a_startup_error(field, value):
    """`"0"` sits alongside the ints ... the environment supplies strings, and
    pydantic coerces before the validator runs."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, **{field: value})
    assert field in str(exc_info.value)

def test_env_example_documents_every_multiturn_pipeline_var_with_a_comment():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for var in (...):
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing ..."
```

Every settings story in this file follows the same five-test shape. `_settings(**overrides)` (`tests/test_config.py:95-97`) is the constructor helper — `_env_file=None` so a developer's real `.env` never decides whether these pass — and `_LOCAL_URL` (`tests/test_config.py:92`) is the endpoint that satisfies the `DATABASE_URL` / `TURSO_AUTH_TOKEN` pair without a token.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | UPDATE | Four PRD-011 fields; generalize the positive-int mapping/validator to cover `PATTERN_MAX_SCAN_CHARACTERS`; non-empty validator for `PATTERN_PROFILE_DEFAULT` |
| `.env.example` | UPDATE | A PRD-011 block documenting all four with the same defaults |
| `requirements.txt` | UPDATE | Declare `PyYAML` explicitly instead of relying on `python-frontmatter`'s transitive pull |
| `tests/test_config.py` | UPDATE | Defaults, both validators, boundary values, absence-of-env, `.env.example` coverage and order, and the `requirements.txt` declaration |

No file is created. No production module gains a reader of the new settings.

---

## Tasks

Execute in order. Tasks 1–3 are one file and can be written in one pass; they are separated because each answers a different AC.

### Task 1: Generalize the positive-integer limit mapping and its validator

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**:
  - Rename `_PIPELINE_LIMIT_DESCRIPTIONS` to `_POSITIVE_LIMIT_DESCRIPTIONS` and widen its comment: it is no longer PRD-010-only, so say "what each setting that bounds a resource controls, quoted by its validator so the message says why 0 or a negative value is rejected, not just that it is." Keep the three existing entries verbatim.
  - Add the fourth entry: `"PATTERN_MAX_SCAN_CHARACTERS": "the per-message ceiling on characters any one pattern scan runs over"` — phrased from PRD Section 9.3's Purpose column, so the message reads `"... It is the per-message ceiling on characters any one pattern scan runs over."`
  - Rename `_validate_positive_pipeline_setting` to `_validate_positive_limit`, add `"PATTERN_MAX_SCAN_CHARACTERS"` to its `@field_validator(...)` argument list, and update its docstring to cite both PRDs (`PRD-010, PRD-011`).
- **Mirror**: `app/config.py:15-22` and `app/config.py:192-201` — the constant and validator being widened.
- **Why a rename and not a second mapping**: a one-entry twin mapping plus a near-identical second validator would duplicate the message format, which is the thing the mapping exists to keep in one place. Both names are private and unreferenced outside this module.
- **Validate**: `grep -rn "_PIPELINE_LIMIT_DESCRIPTIONS\|_validate_positive_pipeline_setting" --include=*.py .` returns nothing (documentation under `.agents/` is historical prose and stays as written).

### Task 2: Declare the four PRD-011 fields

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**: after the PRD-010 block (which ends at `PIPELINE_MAX_WORKERS`) and before the first `@field_validator`, add a group in the PRD-010 group's shape:
  - A header comment: `# Pattern policy (PRD-011). Defaults and startup validation land now; no production code reads these yet -- each field names the story that becomes its consumer.`
  - `PATTERNS_FILE: str = ""` — comment: path to the YAML pattern-list file; empty means the built-in policy and **no file is read**, the `RBAC_ROLES_FILE` shape. Consumed by STORY-005's `pattern_config.load()`.
  - `PATTERN_PROFILE_DEFAULT: str = "chat"` — comment: the profile any call site that passes none gets (`/query`, the chat UI). **State that whether it names a profile the policy defines is checked in `pattern_config.load()` (STORY-006), not here, because the file is not read when `Settings` is constructed** (AC 3 requires this comment; PRD Section 9.3 is the source). Read by STORY-008's `run_conversation`.
  - `PATTERNS_ALLOW_REGEX: bool = False` — comment: whether `match: regex` lists are permitted at all; off by default is the first of PRD Section 9.2 T4's four ReDoS layers. Enforced by STORY-005's loader.
  - `PATTERN_MAX_SCAN_CHARACTERS: int = 1_000_000` — comment: per-message ceiling on the characters any one pattern scan runs over; a longer message is truncated for matching only. Consumed by STORY-008's `inspect()`.
  - Use `1_000_000` with the underscore, matching `CONTEXT_MAX_CHARACTERS: int = 200_000` at `app/config.py:118`.
- **Mirror**: `app/config.py:102-122`.
- **Validate**: `python -c "from app.config import Settings; f=Settings.model_fields; print({k: f[k].default for k in ('PATTERNS_FILE','PATTERN_PROFILE_DEFAULT','PATTERNS_ALLOW_REGEX','PATTERN_MAX_SCAN_CHARACTERS')})"` prints `{'PATTERNS_FILE': '', 'PATTERN_PROFILE_DEFAULT': 'chat', 'PATTERNS_ALLOW_REGEX': False, 'PATTERN_MAX_SCAN_CHARACTERS': 1000000}`.

### Task 3: Non-empty validator for `PATTERN_PROFILE_DEFAULT`

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**: a `@field_validator("PATTERN_PROFILE_DEFAULT")` that strips the value and raises when the result is empty. The message names the field, says what it is, and points at the built-in default — e.g. `"PATTERN_PROFILE_DEFAULT must name a profile, got an empty value. It is the profile any call site that does not pass one uses; set it to 'chat' (the built-in default) or to a profile your PATTERNS_FILE defines."` Return the stripped value — the same "a trailing newline in a `.env` value must not become part of the value" reasoning `_validate_database_url` uses at `app/config.py:128`. The docstring states the boundary explicitly: this is the *only* check that belongs here; membership is `pattern_config.load()`'s, per PRD Section 9.3.
- **Mirror**: `app/config.py:163-179` (`_validate_chat_session_limit`) for the message shape; `app/config.py:128` for the strip.
- **Validate**: `python -c "from app.config import Settings; Settings(_env_file=None, PATTERN_PROFILE_DEFAULT='  ')"` raises, and the message contains `PATTERN_PROFILE_DEFAULT`.

### Task 4: Document all four in `.env.example`

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: append a block at the end of the file (after the `REPORTS_*` pair), in the `CONTEXT_MAX_*` style:
  - Header line: `# Pattern policy (PRD-011)`
  - `PATTERNS_FILE=` — "Optional path to a YAML file of pattern lists and profiles; empty uses the built-in policy and reads no file. The file replaces the built-in policy wholesale - it is not merged". Ships **empty**, like `RBAC_ROLES_FILE=` at `.env.example:37`.
  - `PATTERN_PROFILE_DEFAULT=chat` — "Profile used by any call site that does not pass one - /query and the chat UI. Must name a profile the loaded policy defines, checked at startup when the policy loads".
  - `PATTERNS_ALLOW_REGEX=false` — "Whether match: regex lists are permitted at all (true/false). Off by default: a regex list fails startup until this is true".
  - `PATTERN_MAX_SCAN_CHARACTERS=1000000` — "Most characters of any one message a single pattern scan runs over; a longer message is truncated for matching only, never for the upstream call (min 1)".
  - Write the number as `1000000`, not `1_000_000` — a `.env` value is a string pydantic coerces, and the underscore form is a Python literal, not an environment one.
  - Keep the four in the same relative order as the `Settings` declarations, so the field-order test in Task 6 holds.
- **Mirror**: `.env.example:66-82`.
- **Validate**: `grep -c "^PATTERN" .env.example` prints `4`.

### Task 5: Declare `PyYAML` in `requirements.txt`

- **File**: `requirements.txt`
- **Action**: UPDATE
- **Implement**: append `PyYAML` as a new last line, unpinned — the file pins only `reflex` and `libsql`, which had compatibility reasons; everything else floats. PRD Section 8 is the rationale: it is already present transitively through `python-frontmatter` (`yaml 6.0.3` in the active environment), and depending on a transitive dependency is how a build breaks silently. Spell it `PyYAML`, the name on PyPI.
- **Mirror**: `requirements.txt:14` (`python-frontmatter`) — one bare name per line.
- **Validate**: `python -c "import yaml; print(yaml.__version__)"` prints a version, and `grep -n "PyYAML" requirements.txt` finds it.

### Task 6: Tests for the four settings

- **File**: `tests/test_config.py`
- **Action**: UPDATE
- **Implement**: append a section, headed by the comment block every settings story in this file opens with — `# --- PRD-011 STORY-004: pattern policy settings ---` plus two or three lines saying nothing reads these yet and what is therefore being asserted. Use the existing `_settings(**overrides)` helper and `_LOCAL_URL`. Tests:
  1. `test_pattern_policy_settings_available_with_documented_defaults` — all four equal PRD Section 9.3's defaults. Assert `PATTERNS_ALLOW_REGEX is False`, not `not ...`, for the reason `test_chat_history_can_be_turned_off_with_the_string_false` (`tests/test_config.py:291-299`) gives.
  2. `test_patterns_allow_regex_can_be_turned_on_with_the_string_true` — `PATTERNS_ALLOW_REGEX="true"` yields `is True`; the environment supplies strings.
  3. `test_a_pattern_max_scan_characters_below_one_is_a_startup_error` — parametrized over `[0, -1, "0"]`, asserting the field name, the rejected value and the description substring `"per-message ceiling"` all appear in the message. AC 2 asks for all three, so assert all three rather than only the field name.
  4. `test_pattern_max_scan_characters_accepts_the_boundary_value_of_one` — `1` constructs, so a `<= 1` typo fails here and not in STORY-008.
  5. `test_an_empty_pattern_profile_default_is_a_startup_error` — parametrized over `["", "   "]`, message names the field.
  6. `test_pattern_profile_default_is_not_checked_against_any_policy_here` — `PATTERN_PROFILE_DEFAULT="a-profile-nothing-defines"` **constructs successfully**. This is AC 3's real assertion: the cross-check belongs to `pattern_config.load()`, and a future field validator that reached for a file would turn this red. The docstring says so and names STORY-006.
  7. `test_pattern_profile_default_strips_surrounding_whitespace` — mirrors `test_surrounding_whitespace_is_stripped_not_rejected` (`tests/test_config.py:214-218`).
  8. `test_settings_construct_without_the_pattern_policy_vars` — `monkeypatch.delenv` for all four, then the defaults, so they are the module's and not a developer's exported environment.
  9. `test_env_example_documents_every_pattern_policy_var_with_a_comment` — the `(?m)^#.+\n{var}=` regex, over all four.
  10. `test_env_example_pattern_policy_vars_appear_in_settings_field_order` — positions sorted.
  11. `test_env_example_pattern_defaults_match_the_settings_defaults` — parse `PATTERN_PROFILE_DEFAULT=`, `PATTERNS_ALLOW_REGEX=` and `PATTERN_MAX_SCAN_CHARACTERS=` out of `.env.example` and compare against the `Settings` defaults, and assert `PATTERNS_FILE=` is present and empty (the `test_env_example_ships_no_token_value` shape at `tests/test_config.py:247-251`). AC 4 says "the same defaults", and a hand-written example drifts from the code silently otherwise.
  12. `test_requirements_declares_pyyaml_explicitly` — `requirements.txt` contains a line matching `(?mi)^PyYAML\b`, with a docstring carrying PRD Section 8's reason. AC 5 asks for the declaration; this is what keeps a later dependency tidy-up from deleting it as "already installed".
- **Mirror**: `tests/test_config.py:366-475` — the PRD-010 STORY-002 section, test for test.
- **Validate**: `python -m pytest tests/test_config.py -q` — all pass.

### Task 7: Full suite green

- **File**: —
- **Action**: verify
- **Implement**: run the whole suite. AC 5 requires it green with no production consumer of the new settings. Nothing outside `tests/test_config.py` should move; if another module fails, it is the Task 1 rename and the fix is there.
- **Note**: the suite needs the local libSQL dev server (`tests/conftest.py`'s `_libsql_endpoint` exits the run with instructions if it is unreachable). Start it first: `docker start harness-libsql-dev`. If the run produces mass fixture errors across unrelated modules, restart that container rather than bisecting this diff.
- **Validate**: `python -m pytest -q` — green.

---

## End-to-End Tests

- [ ] `python -c "from app.config import settings; print(settings.PATTERNS_FILE, settings.PATTERN_PROFILE_DEFAULT, settings.PATTERNS_ALLOW_REGEX, settings.PATTERN_MAX_SCAN_CHARACTERS)"` — the module still constructs its singleton at import against the developer's real `.env`, printing the four defaults.
- [ ] `PATTERN_MAX_SCAN_CHARACTERS=0 python -c "import app.config"` — fails at import with a message naming the field, `0`, and what the field bounds.
- [ ] `PATTERN_PROFILE_DEFAULT= python -c "import app.config"` — fails at import naming the field.
- [ ] `PATTERN_PROFILE_DEFAULT=not-a-profile python -c "import app.config"` — **succeeds**. The cross-check is STORY-006's, and this is the command that proves it was not smuggled in here.
- [ ] `python -m pytest tests/test_config.py -q` — green.
- [ ] `python -m pytest -q` — green, no production consumer of the new settings.
- [ ] `git diff --stat` — exactly four files, none of them under `app/services/` or `app/routers/`.

---

## Validation

```bash
docker start harness-libsql-dev
python -m pytest tests/test_config.py -q
python -m pytest -q
grep -rn "_PIPELINE_LIMIT_DESCRIPTIONS" --include=*.py .   # expect no output
grep -c "^PATTERN" .env.example                            # expect 4
grep -n "PyYAML" requirements.txt
```

---

## Acceptance Criteria

(Copied from story `STORY-004`)

- [ ] Given `app/config.py`, when `Settings` is read, then it declares `PATTERNS_FILE: str = ""`, `PATTERN_PROFILE_DEFAULT: str = "chat"`, `PATTERNS_ALLOW_REGEX: bool = False` and `PATTERN_MAX_SCAN_CHARACTERS: int = 1_000_000`, each with a comment naming the story that becomes its consumer.
- [ ] Given `PATTERN_MAX_SCAN_CHARACTERS=0` or a negative value, when `Settings` is constructed, then it raises with a message naming the field, the rejected value and what the field bounds — the `CHAT_SESSION_LIMIT` / `_PIPELINE_LIMIT_DESCRIPTIONS` style already in the file.
- [ ] Given `PATTERN_PROFILE_DEFAULT`, when `Settings` is constructed, then it is **not** validated here beyond being non-empty: it is a cross-check against the loaded policy and belongs in `pattern_config.load()` (STORY-005), because the file is not read when `Settings` is constructed. A comment in the field says so.
- [ ] Given `.env.example`, when it is read, then all four variables appear with the same defaults and a one- or two-line explanation each, in the style of the `CONTEXT_MAX_*` block.
- [ ] Given `requirements.txt`, when it is read, then `PyYAML` is declared explicitly, and `tests/test_config.py` gains cases for the new fields and their validator. The full suite is green with no production consumer of the new settings yet.
- [ ] All tasks completed
- [ ] Backend imports without error (`python -c "import app.config"`)
- [ ] Follows existing patterns

---

## Risks

| # | Risk | Likelihood / Impact | Mitigation |
|---|------|---------------------|------------|
| 1 | The Task 1 rename breaks a reference outside `app/config.py` | Low / Low | Both names are private and grep-verified to have no other code reference; Task 1's validate step re-runs that grep, and the full suite in Task 7 is the backstop |
| 2 | A PRD-010 message changes shape and turns `tests/test_config.py:383-418` red | Low / Low | The format string is untouched; only the constant and function names move. Those tests assert on the field name in the message, never on the identifiers |
| 3 | `PyYAML` added while nothing imports `yaml` reads as dead weight and gets removed | Medium / Medium | Test 12 in Task 6 pins the declaration with PRD Section 8's reason in its docstring, so deleting it is a red test rather than a tidy-up |
| 4 | `.env.example` drifts from the field defaults later | Medium / Low | Test 11 in Task 6 compares the example's values against `Settings.model_fields` defaults rather than against a hard-coded copy |
| 5 | A later reader adds the profile-membership check to a pydantic validator, where the file is not loaded | Medium / High (a boot that cannot succeed, or a silent skip) | The field comment (Task 2) and test 6 in Task 6 both exist to make that attempt fail loudly and explain why |
| 6 | The suite reports mass fixture errors unrelated to this change | Medium / Low | The libSQL dev server degrades under repeated suite runs; restart the container rather than bisecting the diff (Task 7's note) |
