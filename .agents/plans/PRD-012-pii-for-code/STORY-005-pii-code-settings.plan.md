---
story: STORY-005
prd: PRD-012
slug: pii-code-settings
title: "Six PII code-profile settings with startup validators"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-012-pii-for-code        # all stories commit here, no per-story branch
created: 2026-09-25
---

# Plan: Six PII code-profile settings with startup validators

## Summary

This story adds six fields to `Settings` in `app/config.py`, in a new PRD-012 group placed after the PRD-011 group. It also adds one module-level constant, one shared parsing helper, two validators and one property. It extends `tests/test_config.py` with a PRD-012 block.

**The six fields.** Defaults for the first three come from the STORY-003 report; the other three come from PRD-012 Section 9.3.

| Field | Default |
|---|---|
| `PII_ENTITIES_CODE` | `"EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE"` |
| `PII_SCORE_THRESHOLD_CODE` | `0.40` |
| `PII_MAX_CHARACTERS_CODE` | `200_000` |
| `PII_CODE_REDACT_OUTPUT` | `False` |
| `PII_CODE_REDACT_SYSTEM` | `False` |
| `PII_CODE_SKIP_CODE_BLOCKS` | `True` |

**Validation.**
- `PII_ENTITIES_CODE` is checked against a new module constant, `_PRESIDIO_ENTITY_NAMES`. That constant is the 20 entity names in Presidio 2.2.364's default English registry, measured in F-2. Checking a constant means `Settings` never loads an analyzer.
- `PII_SCORE_THRESHOLD_CODE` must lie in `[0, 1]`.
- `PII_MAX_CHARACTERS_CODE` joins `_POSITIVE_LIMIT_DESCRIPTIONS` and the existing `_validate_positive_limit`. The PRD and the story call that dict `_RESOURCE_BOUNDS`, which does not exist (F-1).
- The four existing `PII_*` fields, and `pii_entities_list`, are not touched.
- Nothing reads the new fields yet. STORY-006, STORY-007 and STORY-010 are the consumers, and each field's comment names its consumer.

`.env.example` and the README are **not** in this story. STORY-014's AC 3 owns documenting all six settings there.

## User Story

As a platform operator
I want the `code` profile's PII behaviour tunable from `.env` and validated at boot
So that I can move its defaults without a code change and a mis-set value stops the process loudly

## Story Reference

- Story file: `.agents/stories/PRD-012-pii-for-code/STORY-005-pii-code-settings.md`
- PRD: `.agents/PRDs/PRD-012-pii-for-code/PRD.md` (Sections 4 Settings, 6.2, 7/F4, 9.3)
- Defaults source: `.agents/reports/PRD-012-pii-for-code/STORY-003-pii-benchmark-baseline.report.md` ("The decided values"; "For later stories → STORY-005")

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `app/config.py`, `tests/test_config.py` |
| Story | STORY-005 |
| PRD | PRD-012 |
| Epic Branch | `epic/PRD-012-pii-for-code` (commit directly on this branch) |
| Depends on | STORY-003 ✅ done (`ddf6596`) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | The story says "Skills: none applicable". `.agents/skills/` holds only `frontend-design`, and this story changes no UI. | — |

---

## Findings (measured before planning)

- **F-1: `_RESOURCE_BOUNDS` does not exist.** The dict that feeds the positive-limit validator's message is `_POSITIVE_LIMIT_DESCRIPTIONS` (`app/config.py:19-24`), consumed by `_validate_positive_limit` (`:231-245`). The STORY-003 report already flags this. AC 3's "`_RESOURCE_BOUNDS`-style message" is read as *that* message: `"{FIELD} must be at least 1, got {value}. It is {description}."`
- **F-2: Presidio's default English registry, 2.2.364.** Measured with `RecognizerRegistry().load_predefined_recognizers(languages=["en"])`, which loads no spaCy model. It has 20 names:
  `CREDIT_CARD, CRYPTO, DATE_TIME, EMAIL_ADDRESS, IBAN_CODE, IP_ADDRESS, LOCATION, MAC_ADDRESS, MEDICAL_LICENSE, NRP, ORGANIZATION, PERSON, PHONE_NUMBER, UK_NHS, URL, US_BANK_NUMBER, US_DRIVER_LICENSE, US_ITIN, US_PASSPORT, US_SSN`.
  The seven in today's `PII_ENTITIES` are all included. `SpacyRecognizer` supplies `DATE_TIME, NRP, LOCATION, PERSON, ORGANIZATION`. `DATE_TIME` is also a pattern type, through `DateRecognizer`.
- **F-3: The STORY-003 decided values.**
  - `PII_SCORE_THRESHOLD_CODE = 0.40` (R1). This replaces the PRD's provisional 0.5, which misses both required probes.
  - `PII_MAX_CHARACTERS_CODE = 200000` (R3).
  - `PERSON` stays out of `PII_ENTITIES_CODE` (R4). `LOCATION` stays out under D7.
  - `scripts/measure_pii_latency.py:88` already holds the default list as `PATTERN_ENTITIES`.
- **F-4: Line numbers `app/config.py:82-85` are cited elsewhere.** `tests/test_pii_characterization.py:58` points at them in a comment. Adding the new group *after* the PRD-011 group (after `:161`) keeps those lines where they are.
- **F-5: How `.env` strings parse.** pydantic-settings coerces `"true"`, `"false"`, `"1"`, `"0"` and `"yes"` to `bool`. A non-numeric threshold such as `"abc"` is already rejected with pydantic's own `float_parsing` error naming the field. A NaN fails `0 <= x <= 1`, so writing the check as `not 0 <= value <= 1` rejects `"nan"` without a special case.
- **F-6: The test baseline, and a precondition.**
  - `tests/conftest.py` exits the whole session when the libSQL dev server on `127.0.0.1:8080` is unreachable, even for `test_config.py`. Docker Desktop was not running when this plan was written.
  - With `--noconftest`, `tests/test_config.py` gives 69 passed and 1 failed. The failure, `test_settings_construct_without_new_env_vars`, needs conftest's `DATABASE_URL` default and is unrelated to this story.
  - `/implement` must start the container first (Validation).
- **F-7: Nothing enumerates Settings fields.** Nothing outside `test_config.py` enumerates `Settings` fields or cross-checks `.env.example` against them. The `.env.example` tests run per group, so new fields without `.env.example` lines break nothing.

---

## Patterns to Follow

### Naming: group comment, and each field names its consumer story
```python
# SOURCE: app/config.py:126-161
    # Pattern policy (PRD-011). pattern_config.load() reads PATTERNS_FILE,
    # PATTERN_PROFILE_DEFAULT and PATTERNS_ALLOW_REGEX at startup, in both
    # lifespans (STORY-007). PATTERN_MAX_SCAN_CHARACTERS, and the request-path
    # read of PATTERN_PROFILE_DEFAULT, wait for STORY-008 -- each field names
    # the story that becomes its consumer.

    # Per-message ceiling on the characters any one pattern scan runs over. A
    # longer message is truncated for matching only -- never for the upstream
    # call -- and the pipeline warns with the two lengths, never the content.
    # Consumed by STORY-008's inspect().
    PATTERN_MAX_SCAN_CHARACTERS: int = 1_000_000
```

### Module constant plus the positive-limit validator (the "`_RESOURCE_BOUNDS`" style)
```python
# SOURCE: app/config.py:15-24
# What each setting that bounds a resource controls, quoted by its validator
# so the message says why 0 or a negative value is rejected, not just that
# it is. The first three arrived with PRD-010's pipeline sizes; PRD-011 added
# the fourth, which is why the name no longer says "pipeline".
_POSITIVE_LIMIT_DESCRIPTIONS = {
    ...
    "PATTERN_MAX_SCAN_CHARACTERS": "the per-message ceiling on characters any one pattern scan runs over",
}

# SOURCE: app/config.py:231-245
    @field_validator(
        "CONTEXT_MAX_MESSAGES",
        "CONTEXT_MAX_CHARACTERS",
        "PIPELINE_MAX_WORKERS",
        "PATTERN_MAX_SCAN_CHARACTERS",
    )
    @classmethod
    def _validate_positive_limit(cls, value: int, info) -> int:
        """Each of these bounds a resource that cannot be 0 or negative (PRD-010, PRD-011)."""
        if value < 1:
            description = _POSITIVE_LIMIT_DESCRIPTIONS[info.field_name]
            raise ValueError(
                f"{info.field_name} must be at least 1, got {value}. It is {description}."
            )
        return value
```

### Error handling: a range validator on a float, and a string validator that names the fix
```python
# SOURCE: app/config.py:220-229
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

# SOURCE: app/config.py:261-269 (_validate_pattern_profile_default): empty -> ValueError
# naming the setting, what it is, and the value to set instead.
```

### Comma-list parsing (the property the new one must parse like)
```python
# SOURCE: app/config.py:271-273
    @property
    def pii_entities_list(self) -> list[str]:
        return [item.strip() for item in self.PII_ENTITIES.split(",") if item.strip()]
```

### Tests: one block per PRD, a vars tuple, `_settings(...)`, `[0, -1, "0"]`, boundary 1, `is True`
```python
# SOURCE: tests/test_config.py:95-97, 487-492, 517-540, 584-594
def _settings(**overrides) -> Settings:
    base = {"OPENROUTER_API_KEY": "test-key", "ADMIN_TOKEN": "test-token"}
    return Settings(_env_file=None, **{**base, **overrides})

_PATTERN_VARS = ("PATTERNS_FILE", "PATTERN_PROFILE_DEFAULT", "PATTERNS_ALLOW_REGEX", "PATTERN_MAX_SCAN_CHARACTERS")

@pytest.mark.parametrize("value", [0, -1, "0"])
def test_a_pattern_max_scan_characters_below_one_is_a_startup_error(value):
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=_LOCAL_URL, PATTERN_MAX_SCAN_CHARACTERS=value)
    message = str(exc_info.value)
    assert "PATTERN_MAX_SCAN_CHARACTERS" in message
    assert str(int(value)) in message, "the message must quote the value it rejected"
    assert "per-message ceiling" in message, "the message must say what the field bounds"

def test_settings_construct_without_the_pattern_policy_vars(monkeypatch):
    for var in _PATTERN_VARS:
        monkeypatch.delenv(var, raising=False)
    fresh = _settings(DATABASE_URL=_LOCAL_URL)
    ...
```

---

## Design

### Files to CREATE
- None.

### Files to UPDATE
- `app/config.py`: the constant, the helper, the six fields, the validators and the property.
- `tests/test_config.py`: a new `# --- PRD-012 STORY-005 ...` block appended at the end.

### Dependency order
The constant and helper come first, then the fields, then the validators and property, then the tests. It is one module, so it is one atomic change.

### Decisions made here
| # | Decision | Why |
|---|---|---|
| P1 | `_PRESIDIO_ENTITY_NAMES` is a `frozenset` of all 20 default-registry names, not only the 7 in use | The story says "plus any others Presidio's default registry provides". A test pins it to the live registry (Task 2), so a Presidio upgrade that changes the registry turns a test red rather than silently drifting |
| P2 | Names are case-sensitive; `email_address` is rejected | Presidio's entity names are case-sensitive. Accepting a lowercase name here would pass startup and then detect nothing in STORY-006 |
| P3 | `PERSON`/`LOCATION` in `PII_ENTITIES_CODE` are **accepted** | D7: an operator may opt into NER at NER's cost. STORY-006 routes such a list to the full analyzer. This story only checks that names are known |
| P4 | A new `_split_comma_list(value)` helper is used by the validator and by `pii_entities_code_list` only. `pii_entities_list` and `model_allowlist_list` are **not** rewritten onto it | AC 5 asks for "unchanged". The test asserts the two properties give equal output on the same input, which is what "parses like" means |
| P5 | The validator returns the value unchanged (no normalising rewrite) | The field holds exactly what `.env` said. The property does the parsing, as `PII_ENTITIES` does. Duplicate names are allowed, as they are for `PII_ENTITIES` |
| P6 | No validator is added to the existing `PII_SCORE_THRESHOLD` / `PII_ENTITIES` | AC 5 says their validation is unchanged. PRD F4's "the two thresholds" reads as the new one plus a future change. A test pins that `PII_ENTITIES="NOT_A_TYPE"` and `PII_SCORE_THRESHOLD=5` still construct, so the scope cannot creep silently |
| P7 | The unit-interval check lives in its own validator, `_validate_pii_score_threshold_code`, with an inline description | It is one field. A dict for one entry would be premature |

### Risks
| Risk | Mitigation |
|---|---|
| The libSQL dev server is not running, so `pytest` exits before collecting (F-6) | The Validation step starts it first. For a fast inner loop, `--noconftest` runs `test_config.py` without it, with the one pre-existing failure noted |
| The registry-drift test imports `presidio_analyzer` into `test_config.py` | `RecognizerRegistry.load_predefined_recognizers` loads no spaCy model and runs in well under a second (F-2). It is one test, and it states why it exists |
| `DATE_TIME`, `NRP` and `ORGANIZATION` are also spaCy-NER types (F-2), but the PRD's NER set is `{PERSON, LOCATION}` | This is out of scope here, since all three are simply accepted names. It is recorded as a handoff for STORY-006, whose "no NER type" check must decide on them (see the Handoff section) |
| The comment above `_POSITIVE_LIMIT_DESCRIPTIONS` ("PRD-011 added the fourth") goes stale | Task 1 updates it to name PRD-012's fifth |
| A later story expects `PII_ENTITIES_CODE` in `.env.example` | This is deliberately STORY-014's (its AC 3). It is noted in the plan so `/implement` does not add it early |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | UPDATE | Add `_PRESIDIO_ENTITY_NAMES` and `_split_comma_list`. Add one `_POSITIVE_LIMIT_DESCRIPTIONS` entry and update its comment. Add six fields in a PRD-012 group. Add `PII_MAX_CHARACTERS_CODE` to `_validate_positive_limit`. Add `_validate_pii_entities_code`, `_validate_pii_score_threshold_code` and `pii_entities_code_list` |
| `tests/test_config.py` | UPDATE | Append a PRD-012 STORY-005 block covering AC 1-5 |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Add the PRD-012 settings group, validators and property to `app/config.py`

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**:
  1. **Constant** (after `_POSITIVE_LIMIT_DESCRIPTIONS`, with a `#`-comment in the file's style). Add `_PRESIDIO_ENTITY_NAMES = frozenset({...})` holding the 20 names in F-2.
     - The comment says three things. These are the names Presidio's default English registry supports (pinned version 2.2.364; `requirements.txt`). The validator checks against this constant rather than a loaded analyzer, because `Settings` is built before any model loads. `tests/test_config.py` compares it to the live registry.
  2. **`_POSITIVE_LIMIT_DESCRIPTIONS`**: add
     `"PII_MAX_CHARACTERS_CODE": "the analyzable characters per request the code profile's PII redaction runs over; a longer conversation is refused"`.
     Update the comment above the dict: "...PRD-011 added the fourth, and PRD-012 the fifth...".
  3. **Helper** (module level, beside `_scheme_of`). Add `def _split_comma_list(value: str) -> list[str]` returning `[item.strip() for item in value.split(",") if item.strip()]`, with a one-line docstring saying it is the parsing `pii_entities_list` does.
  4. **Fields.** Add a new group after `PATTERN_MAX_SCAN_CHARACTERS` (`:161`), before the first validator. Leave `:82-85` where they are (F-4).
     - **Group header**: `# PII for code (PRD-012).` It says the `code` profile's PII policy is built from these six. The four `PII_*` settings above keep their meaning and apply to `chat` only. `PII_REDACTION_ENABLED` remains the master switch for every policy. Nothing reads these yet, and each field names the story that becomes its consumer.
     - `PII_ENTITIES_CODE: str = "EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE"`. The comment says these are pattern recognizers only (D7), with no NER type, which selects the tokenizer-only analyzer. It names both consumers: STORY-006 (analyzer choice) and STORY-007 (the `code` policy). It says `PERSON` stays out per STORY-003's R4.
     - `PII_SCORE_THRESHOLD_CODE: float = 0.40`. The comment says it is the confidence threshold under `code` (D6), and that 0.40 is STORY-003's R1: the highest threshold that keeps every prose file and required probe. Consumed by STORY-007.
     - `PII_MAX_CHARACTERS_CODE: int = 200_000`. The comment says it counts analyzable characters per request under `code` (D4), and that over the limit the request is refused, fail closed. The value is STORY-003's R3, and R3's chunking condition belongs to STORY-008. Consumed by STORY-007 (policy) and STORY-010 (refusal arm).
     - `PII_CODE_REDACT_OUTPUT: bool = False`. D1: the response is not redacted under `code`, because a placeholder in a response becomes a placeholder in a file. Consumed by STORY-007.
     - `PII_CODE_REDACT_SYSTEM: bool = False`. D3: `system` is the client's own prompt. Consumed by STORY-007.
     - `PII_CODE_SKIP_CODE_BLOCKS: bool = True`. D2: fenced blocks are skipped, and inline spans are not. Consumed by STORY-007.
  5. **Positive limit.** Add `"PII_MAX_CHARACTERS_CODE"` to the `@field_validator(...)` list of `_validate_positive_limit`. Extend its docstring's PRD list to "(PRD-010, PRD-011, PRD-012)".
  6. **`_validate_pii_entities_code`** (`@field_validator("PII_ENTITIES_CODE")`, `@classmethod`):
     - `names = _split_comma_list(value)`.
     - If empty, raise `ValueError`. The message says: `PII_ENTITIES_CODE` must name at least one Presidio entity type; the value received, shown with `!r`; that the setting is the code profile's entity list, and that turning PII off is `PII_REDACTION_ENABLED=false`, not an empty list; and the accepted names, sorted and comma-joined.
     - `unknown = [n for n in names if n not in _PRESIDIO_ENTITY_NAMES]`. If any, raise `ValueError` with the setting name, the unknown names and the full value (`!r`), and `Accepted names: ` plus the sorted accepted names. Add a sentence saying names are case-sensitive (P2).
     - Return `value` unchanged (P5).
     - The docstring states why a constant and not the analyzer.
  7. **`_validate_pii_score_threshold_code`** (`@field_validator("PII_SCORE_THRESHOLD_CODE")`, `@classmethod`):
     - `if not 0 <= value <= 1:` raise `ValueError(f"PII_SCORE_THRESHOLD_CODE must be between 0 and 1, got {value}. It is the minimum Presidio confidence for an entity to be masked under the code profile.")`. This mirrors the positive-limit message shape.
     - The docstring notes that the `not` form rejects NaN (F-5).
  8. **Property** (after `pii_entities_list`): `pii_entities_code_list -> list[str]` returning `_split_comma_list(self.PII_ENTITIES_CODE)`.
  9. Do **not** edit `PII_REDACTION_ENABLED`, `PII_SCORE_THRESHOLD`, `PII_ENTITIES`, `PII_NLP_MODEL`, `pii_entities_list` or `model_allowlist_list`.
- **Mirror**: `app/config.py:126-161` (group and field comments), `:19-24` and `:231-245` (positive limit), `:220-229` (range message), `:247-269` (string validator that names the fix), `:271-273` (property).
- **Validate**: `.venv/Scripts/python.exe -c "import app.main"` imports cleanly. Then:
  ```
  .venv/Scripts/python.exe -c "from app.config import settings as s; print(s.pii_entities_code_list, s.PII_SCORE_THRESHOLD_CODE, s.PII_MAX_CHARACTERS_CODE, s.PII_CODE_REDACT_OUTPUT, s.PII_CODE_REDACT_SYSTEM, s.PII_CODE_SKIP_CODE_BLOCKS)"
  ```
  This prints `['EMAIL_ADDRESS', 'PHONE_NUMBER', 'CREDIT_CARD', 'US_SSN', 'IBAN_CODE'] 0.4 200000 False False True`.

### Task 2: Append the PRD-012 STORY-005 block to `tests/test_config.py`

- **File**: `tests/test_config.py`
- **Action**: UPDATE
- **Implement**: a banner `# --- PRD-012 STORY-005: PII code-profile settings ---` with a short preamble in the PRD-011 block's style. The preamble says nothing reads these yet; STORY-006, STORY-007 and STORY-010 are the consumers; and `.env.example` is STORY-014's. Then:
  - `_PII_CODE_VARS = ("PII_ENTITIES_CODE", "PII_SCORE_THRESHOLD_CODE", "PII_MAX_CHARACTERS_CODE", "PII_CODE_REDACT_OUTPUT", "PII_CODE_REDACT_SYSTEM", "PII_CODE_SKIP_CODE_BLOCKS")`.
  - Import `_PRESIDIO_ENTITY_NAMES` and `_POSITIVE_LIMIT_DESCRIPTIONS` from `app.config` at the block's top, alongside the file's existing import.

  **AC 1: defaults**
  - `test_pii_code_settings_available_with_documented_defaults`: the six values in the Summary table, with the bools asserted using `is`.
  - `test_pii_entities_code_default_is_the_benchmarked_pattern_list`:
    - The default's parsed list equals `list(bench.PATTERN_ENTITIES)` (`import scripts.measure_pii_latency as bench`, as `tests/test_measure_pii_latency.py:23` does; importing it builds no analyzer, per that file's first test).
    - The default contains neither `PERSON` nor `LOCATION` (R4 / D7).
  - `test_pii_code_bools_parse_the_strings_a_dotenv_supplies`: `"true"` → `is True` for the two `False`-default fields, and `"false"` → `is False` for `PII_CODE_SKIP_CODE_BLOCKS`.
  - `test_settings_construct_without_the_pii_code_vars(monkeypatch)`: `delenv` over `_PII_CODE_VARS`, then assert the defaults.

  **AC 2: the entity list**
  - `@pytest.mark.parametrize("value", ["", "   ", " , ,"])` `test_an_empty_pii_entities_code_is_a_startup_error`: the message contains `PII_ENTITIES_CODE` and `PII_REDACTION_ENABLED` (it names the right way to turn PII off).
  - `@pytest.mark.parametrize("value,bad", [("EMAIL_ADDRESS,NOT_A_TYPE", "NOT_A_TYPE"), ("email_address", "email_address"), ("EMAIL_ADDRESS, PASSPORT", "PASSPORT")])` `test_an_unknown_pii_entity_code_is_a_startup_error`. The message contains:
    - `PII_ENTITIES_CODE`;
    - `bad`;
    - every name in `_PRESIDIO_ENTITY_NAMES` (the accepted names).
  - `@pytest.mark.parametrize("name", sorted(_PRESIDIO_ENTITY_NAMES))` `test_every_known_entity_name_is_accepted_alone`. This covers `PERSON`/`LOCATION` as an operator opt-in (P3).
  - `test_known_entity_names_match_presidios_default_registry`:
    - `RecognizerRegistry(); load_predefined_recognizers(languages=["en"])`.
    - Assert `set(registry.get_supported_entities(languages=["en"])) == _PRESIDIO_ENTITY_NAMES`.
    - The docstring says the constant exists so `Settings` never loads an analyzer, and this test is what stops it drifting from the pinned Presidio.
  - `test_known_entity_names_cover_todays_pii_entities`: `set(_settings(DATABASE_URL=_LOCAL_URL).pii_entities_list) <= _PRESIDIO_ENTITY_NAMES`. This is "the seven types today's default uses".

  **AC 3: threshold and size limit**
  - `@pytest.mark.parametrize("value", [-0.01, 1.01, -1, 2, "1.5", "nan", "inf"])` `test_a_pii_score_threshold_code_outside_zero_to_one_is_a_startup_error`. The message contains:
    - `PII_SCORE_THRESHOLD_CODE`;
    - `"between 0 and 1"`;
    - `"minimum Presidio confidence"`.

    For the numeric cases, `str(float(value))` also appears, so the message quotes the rejected value.
  - `test_pii_score_threshold_code_accepts_both_boundaries`: `0` → `0.0` and `1` → `1.0`.
  - `@pytest.mark.parametrize("value", [0, -1, "0"])` `test_a_pii_max_characters_code_below_one_is_a_startup_error`. The message contains `PII_MAX_CHARACTERS_CODE`, `str(int(value))` and `_POSITIVE_LIMIT_DESCRIPTIONS["PII_MAX_CHARACTERS_CODE"]`, which is the exact positive-limit message shape.
  - `test_pii_max_characters_code_accepts_the_boundary_value_of_one`.

  **AC 4: the property**
  - `test_pii_entities_code_list_parses_like_pii_entities_list`:
    - `raw = " EMAIL_ADDRESS , ,US_SSN ,"`.
    - `result = _settings(DATABASE_URL=_LOCAL_URL, PII_ENTITIES=raw, PII_ENTITIES_CODE=raw)`.
    - Assert `result.pii_entities_code_list == result.pii_entities_list == ["EMAIL_ADDRESS", "US_SSN"]`.

  **AC 5: the existing four are unchanged**
  - `test_existing_pii_settings_keep_their_defaults`: `True`, `0.35`, the 7-type string, and `"en_core_web_lg"`. These are the same values as `tests/test_pii_characterization.py:_SHIPPED_PII_SETTINGS`.
  - `test_existing_pii_settings_gained_no_validation`:
    - `_settings(DATABASE_URL=_LOCAL_URL, PII_ENTITIES="NOT_A_TYPE", PII_SCORE_THRESHOLD=5)` constructs.
    - Its `pii_entities_list == ["NOT_A_TYPE"]`.
    - The docstring says the new validators are `code`-only by AC 5, and `chat`'s settings are PRD-003's.
- **Mirror**: `tests/test_config.py:473-647` (the PRD-011 block: vars tuple, `_settings`, parametrised bad values, boundary, `delenv` test, docstrings that say why).
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_config.py -q`. All new tests pass, and every existing test still passes. This needs the libSQL dev server; see Validation.

### Task 3: Regression sweep over every settings reader

- **Files**: none changed.
- **Implement**: run the suites that read or monkeypatch PII settings (Explore report, section 1), to confirm the existing four behave as before and the module imports everywhere.
- **Validate**:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_pii_characterization.py tests/test_pii_redactor.py tests/test_measure_pii_latency.py tests/test_pii_corpus_files.py tests/test_conftest_fixtures.py -q
  .venv/Scripts/python.exe -m pytest -q
  ```

---

## End-to-End Tests

`/implement` executes these, beyond pytest:

- [ ] `.venv/Scripts/python.exe -c "import app.main"` imports cleanly with no `.env` changes. The new defaults validate.
- [ ] A bad entity stops boot loudly:
  ```
  PII_ENTITIES_CODE=EMAIL_ADDRESS,FOO .venv/Scripts/python.exe -c "import app.config"
  ```
  This exits non-zero with a `ValidationError` naming `PII_ENTITIES_CODE`, `FOO` and the accepted names.
- [ ] `PII_SCORE_THRESHOLD_CODE=1.5 .venv/Scripts/python.exe -c "import app.config"` exits non-zero, naming the setting and `between 0 and 1`.
- [ ] `PII_MAX_CHARACTERS_CODE=0 .venv/Scripts/python.exe -c "import app.config"` exits non-zero with `PII_MAX_CHARACTERS_CODE must be at least 1, got 0. It is ...`.
- [ ] `PII_ENTITIES_CODE=PERSON,EMAIL_ADDRESS .venv/Scripts/python.exe -c "from app.config import settings; print(settings.pii_entities_code_list)"` prints `['PERSON', 'EMAIL_ADDRESS']`. The NER opt-in is accepted (P3).
- [ ] `git diff --stat` touches only `app/config.py` and `tests/test_config.py`. In particular, no change to `.env.example`, the README, `app/services/*` or `tests/test_pii_characterization.py`.

---

## Validation

```bash
# Precondition (F-6): the libSQL dev server the conftest requires
docker start harness-libsql-dev   # or the `docker run` line tests/conftest.py prints

.venv/Scripts/python.exe -m pytest tests/test_config.py -q
.venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_pii_characterization.py tests/test_pii_redactor.py tests/test_measure_pii_latency.py tests/test_pii_corpus_files.py -q
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -c "import app.main"      # app still imports (server start smoke)
```

Fast inner loop without Docker: `.venv/Scripts/python.exe -m pytest tests/test_config.py -q --noconftest`. The one expected failure there is the pre-existing `test_settings_construct_without_new_env_vars` (F-6).

No linter is configured in the repo, and there is no frontend change, so no frontend lint.

---

## Handoff (for later stories, recorded here so it is not lost)

- **STORY-006:** `_PRESIDIO_ENTITY_NAMES` includes `DATE_TIME`, `NRP` and `ORGANIZATION`. Presidio's `SpacyRecognizer` serves all three (F-2), and `DATE_TIME` is also served by the pattern `DateRecognizer`. The PRD's "no NER type" test names only `PERSON`/`LOCATION`. STORY-006 must decide whether `NRP`/`ORGANIZATION` (and `DATE_TIME`) in `PII_ENTITIES_CODE` select the full analyzer. The safe reading is that they do.
- **STORY-014:** `.env.example` needs the six settings in field order, each with a comment line. Numbers go without underscores (`200000`) and bools lowercase. The `test_config.py` pattern for that is `:597-634`.

---

## Acceptance Criteria

(Copied from story `STORY-005`)

- [ ] Given `app/config.py`, when it is read, then `PII_ENTITIES_CODE`, `PII_SCORE_THRESHOLD_CODE`, `PII_MAX_CHARACTERS_CODE`, `PII_CODE_REDACT_OUTPUT` (`False`), `PII_CODE_REDACT_SYSTEM` (`False`) and `PII_CODE_SKIP_CODE_BLOCKS` (`True`) exist, with the entity list, threshold and size limit defaults taken from the STORY-003 report.
- [ ] Given `PII_ENTITIES_CODE` empty or naming an unknown entity type, when `Settings` is constructed, then it raises with a message naming the setting, the bad value and the accepted names.
- [ ] Given `PII_SCORE_THRESHOLD_CODE` outside `[0, 1]`, or `PII_MAX_CHARACTERS_CODE < 1`, when `Settings` is constructed, then it raises with the `_RESOURCE_BOUNDS`-style message. (Read as `_POSITIVE_LIMIT_DESCRIPTIONS`, F-1.)
- [ ] Given a `pii_entities_code_list` property, when it is read, then it parses like `pii_entities_list`.
- [ ] Given the existing four `PII_*` settings, when this story lands, then their names, defaults and validation are unchanged.
- [ ] All tasks completed
- [ ] Backend imports / server starts without error (`import app.main`)
- [ ] Full pytest suite green (libSQL dev server running)
- [ ] Follows existing patterns
