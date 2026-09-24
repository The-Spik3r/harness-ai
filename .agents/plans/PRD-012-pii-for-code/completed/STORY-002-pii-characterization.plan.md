---
story: STORY-002
prd: PRD-012
slug: pii-characterization
title: "Characterize today's redact() and pipeline steps 6 and 8 before anything moves"
type: REFACTOR
complexity: LOW
epic_branch: epic/PRD-012-pii-for-code        # all stories commit here, no per-story branch
created: 2026-09-24
---

# Plan: Characterize today's redact() and pipeline steps 6 and 8 before anything moves

## Summary

This story adds one test module, `tests/test_pii_characterization.py`, and changes no production code. The module pins the `chat` path byte for byte on untouched code at two levels:

- **`redact()`**: the exact masked text and sorted entity list for twelve fixed prompts. They include one with no PII, one already carrying `<PERSON>` / `<EMAIL_ADDRESS>`, and one with all seven default entity types.
- **`run_conversation` steps 6 and 8**: four chat-shaped conversations, run with a recording `call_openrouter` stub. For each one the module pins:
  - the exact `Message` list the stub receives;
  - the exact returned `QuerySuccessResponse`, minus `audit_id`;
  - the audit row's `pii_detected_input`, `pii_detected_output`, `pii_entities` and `response`.

The four conversations are PII in the last turn, PII in history only (PRD-010 D7), PII in the response, and all three at once.

All expected values below were measured on this branch before the plan was written (F-2, F-3). The implementer confirms them against the DB and does not guess them. Later stories (STORY-009 onward) must keep every assertion green unchanged, and STORY-014 checks that.

## User Story

As an end user
I want today's redaction behaviour pinned before it is refactored
So that the `chat` profile demonstrably does not change

## Story Reference

- Story file: `.agents/stories/PRD-012-pii-for-code/STORY-002-pii-characterization.md`
- PRD: `.agents/PRDs/PRD-012-pii-for-code/PRD.md` (Sections 6.1, 6.8, 6.10 *Characterization first*, 7/F2, 11 *Functional requirements* line 1 and *Quality indicators*, 14 Risk 6)

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR safety net (story type `technical`: test only) |
| Complexity | LOW |
| Systems Affected | `tests/` only: one new module. No file under `app/`, `chat_ui/` or `requirements*.txt` changes (AC 5) |
| Story | STORY-002 |
| PRD | PRD-012 |
| Epic Branch | `epic/PRD-012-pii-for-code` (commit directly on this branch; it exists and is clean at `f98c57b`) |

---

## Skills In Use

None. `.agents/skills/` holds one skill, `frontend-design`. Its description (`.agents/skills/frontend-design/SKILL.md:3`) limits it to "visual design when building new UI or reshaping an existing one". This story adds a pytest module. The story says the same (`skills: []`, "Skills: none applicable").

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

---

## Findings from Exploration

Measured on `epic/PRD-012-pii-for-code` @ `f98c57b`, with presidio-analyzer 2.2.364, presidio-anonymizer 2.2.364, spaCy 3.8.16, `en_core_web_lg` 3.8.0 and phonenumbers 9.0.38. The pipeline probe replaced `log_query` and `check_duplicate` with in-memory captures, because the libSQL container was down (F-6). Everything else ran as shipped.

### F-1: `test_pii_redactor.py` runs on the *small* model, so this module must pin the large one itself

`tests/test_pii_redactor.py:13-18` has an autouse fixture that sets `PII_NLP_MODEL = "en_core_web_sm"` and sets `_analyzer` / `_anonymizer` to `None`. Monkeypatch restores the previous values afterwards. `tests/test_main.py:34-36` does the same. `tests/conftest.py` pins the pattern settings (`_default_pattern_policy`, 187-210) but **no `PII_*` setting**. A developer's `.env` could therefore change the four `PII_*` values, and a stale small-model analyzer could leak from a test that forgets to reset. The characterization would then pin the wrong bytes, or drift for reasons unrelated to the code.

**Consequence:** this module needs an autouse fixture that:
- pins all four `PII_*` settings to the shipped defaults (`app/config.py:82-85`);
- drops `_analyzer` when the cached one is not `core_web_lg`;
- asserts that the analyzer in use is `core_web_lg`. The probe confirmed `_get_analyzer().nlp_engine.nlp["en"].meta["name"] == "core_web_lg"`.

The story says to use the real model "as `test_pii_redactor.py` does". That file actually uses the small model. The precedent that matches the story's intent is `tests/test_pii_redaction_integration.py:26-41`, which uses the shipped settings and exact strings.

### F-2: `redact()` today, measured

| # | Input | Output | Entities |
|---|---|---|---|
| 1 | `How do I reverse a linked list in Python?` | unchanged | `[]` |
| 2 | `` (empty) | `` | `[]` |
| 3 | `Forward this to <PERSON> at <EMAIL_ADDRESS> when you can.` | unchanged | `[]` |
| 4 | `My name is Jane Doe and my email is jane.doe@example.com.` | `My name is <PERSON> and my email is <EMAIL_ADDRESS>.` | `["EMAIL_ADDRESS", "PERSON"]` |
| 5 | `Please call Maria Lopez on +1 415 555 0134 tomorrow.` | `Please call <PERSON> on <PHONE_NUMBER> tomorrow.` | `["PERSON", "PHONE_NUMBER"]` |
| 6 | `Charge the refund to card 4111 1111 1111 1111, please.` | `Charge the refund to card <CREDIT_CARD>, please.` | `["CREDIT_CARD"]` |
| 7 | `My social security number is 219-09-9999.` | `My social security number is <US_SSN>.` | `["US_SSN"]` |
| 8 | `Wire the salary to IBAN GB82 WEST 1234 5698 7654 32.` | `Wire the salary to IBAN <IBAN_CODE>.` | `["IBAN_CODE"]` |
| 9 | `Patrick O'Brien lives in Seattle.` | `<PERSON> lives in <LOCATION>.` | `["LOCATION", "PERSON"]` |
| 10 | `Tomás Herrera and Zoë Müller-Schmidt met in Berlin.` | `<PERSON> and <PERSON> met in <LOCATION>.` | `["LOCATION", "PERSON"]` |
| 11 | `author = "Jane Doe"` | `author = "<PERSON>"` | `["PERSON"]` |
| 12 | `Priya Raghunathan (priya.raghunathan@example.com, phone +1 212 555 0147) moved to Chicago; her card 5555 5555 5555 4444, SSN 219-09-9999 (social security number), IBAN DE89370400440532013000.` | `<PERSON> (<EMAIL_ADDRESS>, phone <PHONE_NUMBER>) moved to <LOCATION>; her card <CREDIT_CARD>, SSN <US_SSN> (social security number), IBAN <IBAN_CODE>.` | all seven, sorted: `["CREDIT_CARD", "EMAIL_ADDRESS", "IBAN_CODE", "LOCATION", "PERSON", "PHONE_NUMBER", "US_SSN"]` |

Case 11 is the PRD Section 1 example (`author = "Jane Doe"`). Pinning it records the exact bytes `chat` produces on code, the behaviour `code` will diverge from. Every value is from the STORY-001 synthetic set (`tests/corpora/pii/SOURCES.md`).

### F-3: `run_conversation` steps 6 and 8 today, measured

`Identity(user_id="analyst-7", role="user")`, `model="gpt-4"`, stub returns `OpenRouterResult(response=R, model_used=model, tokens_used=42)`. One upstream call and one audit row in every case.

**A. PII in the last turn only** (AC 2)
- in: `user "How do I reverse a linked list in Python?"`, `assistant "Iterate once and flip each next pointer."`, `user "My name is Jane Doe and my email is jane.doe@example.com."`; R = `Noted. I will not repeat your details.`
- sent: first two unchanged; last → `My name is <PERSON> and my email is <EMAIL_ADDRESS>.`
- result: `response` = R, `pii_redacted=True`, `pii_entities_masked=["EMAIL_ADDRESS", "PERSON"]`
- row: `pii_detected_input=True`, `pii_detected_output=False`, `pii_entities="EMAIL_ADDRESS,PERSON"`

**B. PII in history only** (AC 3, PRD-010 D7)
- in: `user "Please call Maria Lopez on +1 415 555 0134 tomorrow."`, `assistant "I will remind you to call Maria Lopez on +1 415 555 0134."`, `user "Can you summarise that reminder?"`; R = `You asked to be reminded about a call tomorrow.`
- sent: `Please call <PERSON> on <PHONE_NUMBER> tomorrow.`, `I will remind you to call <PERSON> on <PHONE_NUMBER>.`, last unchanged
- result: `pii_redacted=False`, `pii_entities_masked=[]`
- row: `pii_detected_input=False`, `pii_detected_output=False`, `pii_entities=None` (F-4)

**C. PII in the response only** (AC 4)
- in: `user "Who owns the billing service?"`; R = `Please contact John Smith at john.smith@example.com or phone 212-555-0199.`
- sent: unchanged
- result: `response="Please contact <PERSON> at <EMAIL_ADDRESS> or phone <PHONE_NUMBER>."`, `pii_redacted=True`, `pii_entities_masked=["EMAIL_ADDRESS", "PERSON", "PHONE_NUMBER"]`
- row: `pii_detected_input=False`, `pii_detected_output=True`, `pii_entities="EMAIL_ADDRESS,PERSON,PHONE_NUMBER"`

**D. All three at once: history, last turn and response each carry a *different* type**
- in: `user "Wire the salary to IBAN GB82 WEST 1234 5698 7654 32."`, `assistant "Done. The transfer to GB82 WEST 1234 5698 7654 32 is queued."`, `user "Send the receipt to ops@example.org."`; R = `Sent. Call Aisha Bello on phone +1 415 555 0134 if it does not arrive.`
- sent: `Wire the salary to IBAN <IBAN_CODE>.`, `Done. The transfer to <IBAN_CODE> is queued.`, `Send the receipt to <EMAIL_ADDRESS>.`
- result: `response="Sent. <PERSON> on phone <PHONE_NUMBER> if it does not arrive."`, `pii_entities_masked=["EMAIL_ADDRESS", "PERSON", "PHONE_NUMBER"]`
- row: `pii_detected_input=True`, `pii_detected_output=True`, `pii_entities="EMAIL_ADDRESS,PERSON,PHONE_NUMBER"`. `IBAN_CODE` is absent: it was masked in history and not recorded (D7).

D shows two behaviours of today's code, pinned on purpose:
- **The NER span swallows `Call`.** `Call Aisha Bello` becomes `<PERSON>`. This is the `chat` output a user sees today. It is exactly the kind of byte-level quirk a shared-helper refactor could "fix" by accident (PRD Risk 6).
- **The audit row stores the response unmasked.** Step 8 logs `response=openrouter_result.response` (`app/services/query_pipeline.py:390`), not `redacted_response`. That is today's behaviour, and pinning `row.response` stops PRD-012 from changing it silently in either direction. The report must flag it as an observation for the security admin. Fixing it is out of scope, because no story in this PRD owns it.

### F-4: The audit row's `pii_entities` is a comma-joined string or `None`

`app/services/audit_logger.py:52` writes `",".join(pii_entities) if pii_entities else None`. `get_audit_log` (`app/db/database.py:881-888`) returns it raw, and returns the two booleans as `bool`. Exact assertions are therefore `row.pii_entities == "EMAIL_ADDRESS,PERSON"` and `row.pii_entities is None`. Neither `[]` nor the `not (row.pii_entities or "")` hedge used in `test_query_pipeline_run_conversation.py:301-302` is acceptable, because the story requires exact assertions.

### F-5: `audit_id` is not stable, and `profile` is already accepted

- `audit_id` comes from the DB, so the result is compared with `result.model_dump(exclude={"audit_id"})` against a dict, and the row is fetched with `get_audit_log(result.audit_id)`.
- `run_conversation(..., *, profile=None)` already exists (PRD-011). Calling it with `profile=None` and with `profile="chat"` today resolves to the same pattern profile, because conftest pins `PATTERN_PROFILE_DEFAULT="chat"`. **Parametrizing the pipeline cases over both** pins the call-site default *and* the explicit name that STORY-009's `get_pii_policy("chat")` will resolve, at no cost. Each parametrized case is its own test, and conftest resets the DB before each one (`tests/conftest.py:156-184`), so the duplicate check never fires across them.

### F-6: Environment

- The suite needs the libSQL dev container (`harness-libsql-dev`, `tests/conftest.py:133-153` exits otherwise). **Docker Desktop was not running when this plan was written**, so it must be started first (Task 0).
- `tests/test_untouched_app.py` no longer guards `app/`; that guard was retired in PRD-008 STORY-023. AC 5 is therefore checked with `git diff` at commit time (Task 3). It is not a test.
- A new test module does not trip `test_no_pre_epic_test_function_was_removed_or_renamed` (`tests/test_pii_redaction_integration.py:463-485`), which only looks at names that already exist.

---

## Patterns to Follow

### Module docstring: frozen record, not a requirement
```python
# SOURCE: tests/test_pattern_characterization.py:1-9
"""PRD-011 STORY-001: the substring detector's verdicts, and which of them changed.

**`_CASES` is a frozen record of pre-PRD-011 behaviour. None of it is a
requirement.** ... STORY-001
pinned every row green on untouched code before anything moved (PRD-011 Section
6.9, "Characterization first"; the precedent is PRD-009 STORY-001 and PRD-010
STORY-003).
```
The same style is in `tests/test_duplicate_characterization.py:1-26`, including "A story that flips one of these must rewrite the assertion in place with a comment citing PRD-009 ... not delete the test."

### Naming and case tables
```python
# SOURCE: tests/test_pattern_characterization.py:62-65, 115, 176-177
#: (text, verdict_before_prd_011) -- what the removed substring detector
#: returned, pinned on untouched code by STORY-001 and frozen since STORY-008.
#: `tests/test_pattern_config.py` imports this list in this shape.
_CASES = [
...
_CASE_IDS = [
...
@pytest.mark.parametrize("text,before", _CASES, ids=_CASE_IDS)
def test_verdict_under_the_default_policy(text, before):
```

### Env bootstrap, imports, identity
```python
# SOURCE: tests/test_query_pipeline_run_conversation.py:14-36
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.db.database import get_audit_log, get_connection
from app.models.messages import Message
from app.models.schemas import (... QuerySuccessResponse,)
from app.services.identity import Identity
from app.services.openrouter_client import GenerationParams, OpenRouterResult
import app.services.query_pipeline as query_pipeline

_JUAN = Identity(user_id="juan@empresa.com", role="user")
```

### Recording stub and the call
```python
# SOURCE: tests/test_query_pipeline_run_conversation.py:278-297
def _capture(messages, model="gpt-4", api_key=None):
    seen.extend(m.content for m in messages)
    return OpenRouterResult(response="noted again", model_used=model, tokens_used=5)
...
result = query_pipeline.run_conversation(
    identity=_JUAN, messages=messages, device=None, model="gpt-4",
    openrouter_api_key=None, call_openrouter=_capture,
)
assert isinstance(result, QuerySuccessResponse)
row = get_audit_log(result.audit_id)
```
This module records **the whole list** (`calls.append(list(messages))`). The pin is the exact `Message` list and the number of calls, not only the contents.

### Settings and singleton hygiene
```python
# SOURCE: tests/test_pii_redactor.py:13-18  (the fixture this module must defend against, F-1)
@pytest.fixture(autouse=True)
def _small_model_and_reset(monkeypatch):
    monkeypatch.setattr(settings, "PII_NLP_MODEL", "en_core_web_sm")
    monkeypatch.setattr(pii_redactor, "_analyzer", None)
    monkeypatch.setattr(pii_redactor, "_anonymizer", None)
    yield
```

### Measured-string provenance comment
```python
# SOURCE: tests/test_pii_redaction_integration.py:26-31
# Every string below was measured against this branch's redactor with the
# shipped settings (en_core_web_lg, PII_SCORE_THRESHOLD=0.35).
_PII_PROMPT = "my name is Maria Gomez, my email is juan@empresa.com and my phone is 555-123-4567"
_REDACTED_PROMPT = "my name is <PERSON>, my email is <EMAIL_ADDRESS> and my phone is <PHONE_NUMBER>"
```

### Error handling
This story has no production error path. Assertions use `==` on whole values: strings, lists of `Message`, the dumped response dict, and `is None` / `is True` / `is False` for row fields. A failure message names the case id. It never pastes a PII value that is not already in the case table.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_pii_characterization.py` | CREATE | The characterization module (Tasks 1-2) |
| `.agents/stories/PRD-012-pii-for-code/STORY-002-pii-characterization.md` | UPDATE | Done by `/plan` Phase 5 (plan link, status). `/implement` fills in report and commit |
| `.agents/PRDs/PRD-012-pii-for-code/index.md` | UPDATE | Status and plan link (this command). Commit SHA later (`/implement`) |
| `.agents/reports/PRD-012-pii-for-code/STORY-002-pii-characterization.report.md` | CREATE (by `/implement`) | Task 4 |

No file under `app/`, `chat_ui/` or `requirements*.txt` (AC 5).

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 0: Preflight

- **Action**: environment only.
- **Implement**:
  1. Start Docker Desktop, then `docker start harness-libsql-dev` and check `docker ps` (F-6).
  2. `git status` is clean on `epic/PRD-012-pii-for-code`. Record `git rev-parse HEAD` as `BASE` for AC 5.
  3. Commit this plan file and the Phase 5 story/index updates as `docs(PRD-012): STORY-002 plan`, so the story commit holds only the test module (the STORY-001 precedent: `c749ee3`).
  4. Run the full suite once and record the pass count.
- **Validate**: `.venv/Scripts/python.exe -m pytest -q` is green. On mass fixture errors, restart the container rather than bisecting (PRD Section 11, *Quality indicators*).

### Task 1: Module skeleton, hygiene fixture, `redact()` pins (AC 1)

- **File**: `tests/test_pii_characterization.py`
- **Action**: CREATE
- **Implement**:
  - **Docstring.** `"""PRD-012 STORY-002: today's redact() and pipeline steps 6 and 8, pinned before anything moves.` Then paragraphs covering the following:
    - **Every assertion here is a frozen record of pre-PRD-012 `chat` behaviour.** It was pinned green on untouched code (PRD-012 Section 6.10; precedents PRD-009 STORY-001, PRD-011 STORY-001). No later story in this PRD may change an assertion. STORY-014 checks that (PRD Section 11, *Functional requirements* line 1). A story that believes one must change stops and raises it. It does not edit.
    - It uses the real `en_core_web_lg` with the shipped `PII_*` values, pinned by the fixture, and why: F-1. Only `call_openrouter` is stubbed.
    - What case D pins on purpose (F-3): the `Call` swallowed into `<PERSON>`, and the audit `response` stored unmasked. Both are today's behaviour, recorded here and not endorsed.
    - Audit fields follow PRD-010 D7: only the last user turn plus the output count.
    - STORY-009 and STORY-014 may import `REDACT_CASES` / `CONVERSATION_CASES` (the `tests.test_pattern_characterization` import precedent). They must not copy them.
  - **Env bootstrap**, as in `test_query_pipeline_run_conversation.py:16-17`.
  - **Imports**: `pytest`, `settings` from `app.config`, `get_audit_log` from `app.db.database`, `Message`, `QuerySuccessResponse`, `Identity`, `OpenRouterResult`, `import app.services.pii_redactor as pii_redactor`, `import app.services.query_pipeline as query_pipeline`.
  - **Shipped settings as a constant**:
    ```python
    #: The four PII settings as shipped (app/config.py:82-85). Pinned per test
    #: because conftest pins none of them and tests/test_pii_redactor.py swaps in
    #: the small model (F-1): a developer's .env or a leaked singleton must not
    #: change what "today" means.
    _SHIPPED_PII_SETTINGS = {
        "PII_REDACTION_ENABLED": True,
        "PII_SCORE_THRESHOLD": 0.35,
        "PII_ENTITIES": "PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION",
        "PII_NLP_MODEL": "en_core_web_lg",
    }
    ```
  - **Autouse fixture `_shipped_pii_settings(monkeypatch)`**:
    - `monkeypatch.setattr(settings, name, value)` for each entry.
    - If `pii_redactor._analyzer` is not `None` and its `nlp_engine.nlp["en"].meta["name"] != "core_web_lg"`, `monkeypatch.setattr(pii_redactor, "_analyzer", None)`. It does not reset unconditionally: a reset would reload the large model for every test (seconds each), and monkeypatch restores the old value afterwards anyway.
    - Then `assert pii_redactor._get_analyzer().nlp_engine.nlp["en"].meta["name"] == "core_web_lg"`.
  - **Cases**, exactly the twelve rows of F-2, as `(input, expected_text, expected_entities)` tuples in `REDACT_CASES`. Give them a `#:` doc comment with the F-2 provenance line (measured, library versions, date) and a parallel `_REDACT_IDS` list: `no-pii`, `empty`, `already-masked`, `person-email`, `person-phone`, `card`, `ssn`, `iban`, `apostrophe-name-location`, `non-ascii-names`, `code-string-literal`, `every-default-entity`.
  - **Tests**:
    - `test_redact_output_is_pinned(text, expected_text, expected_entities)`, parametrized, asserting `pii_redactor.redact(text) == (expected_text, expected_entities)`. The tuple is compared as one value, so the entity order is pinned too.
    - `test_the_every_entity_case_covers_every_default_entity()`: the entities of the `every-default-entity` case equal `sorted(settings.pii_entities_list)`. A guard, in the spirit of `test_every_built_in_pattern_is_covered`.
    - `test_the_redact_cases_include_the_required_shapes()`: at least ten cases; one with `expected_entities == []` and no `<` in the input; one whose input contains `<PERSON>` and comes back unchanged with `[]`. This is AC 1's list as an executable guard.
- **Mirror**: `tests/test_pattern_characterization.py:62-184`
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_pii_characterization.py -q -k redact` is green, with 12 plus 2 cases.

### Task 2: Pipeline steps 6 and 8 pins (AC 2, 3, 4)

- **File**: `tests/test_pii_characterization.py`
- **Action**: UPDATE (same module)
- **Implement**:
  - `_ANALYST = Identity(user_id="analyst-7", role="user")`. No users row is needed, because `run_conversation` takes the identity directly (`test_query_pipeline_run_conversation.py:35`).
  - A frozen dataclass `ConversationCase` with these fields:
    - `id`
    - `messages: tuple[Message, ...]`
    - `upstream_response: str`
    - `expected_sent: tuple[Message, ...]`
    - `expected_result: dict`, the `model_dump` minus `audit_id`, with `status`, `response`, `model_used`, `tokens_used`, `pii_redacted` and `pii_entities_masked`
    - `expected_row: dict`, holding `pii_detected_input`, `pii_detected_output`, `pii_entities` and `response`

    `CONVERSATION_CASES` holds A-D from F-3, verbatim, with ids `pii-in-last-turn`, `pii-in-history-only`, `pii-in-response-only` and `pii-in-history-last-turn-and-response`. Each case has a one-line comment naming the AC it serves. Case B's comment cites PRD-010 D7. Case D's comment names the two quirks.
  - `_recording_stub(calls, response)` returns `_call(messages, model="gpt-4", api_key=None)`. `_call` appends `list(messages)` and returns `OpenRouterResult(response=response, model_used=model, tokens_used=42)`. Its signature has no `params`, the shape `query_pipeline.py:338-341` promises to keep working.
  - `test_chat_conversation_is_pinned(temp_db, case, profile)` is parametrized over `CONVERSATION_CASES` (ids from `case.id`) × `profile` in `(None, "chat")` with ids `default` / `chat` (F-5). The test body:
    1. Calls `query_pipeline.run_conversation(identity=_ANALYST, messages=list(case.messages), device=None, model="gpt-4", openrouter_api_key=None, call_openrouter=_recording_stub(calls, case.upstream_response), profile=profile)`.
    2. Asserts `isinstance(result, QuerySuccessResponse)`.
    3. Asserts `calls == [list(case.expected_sent)]`. That is one call, with the exact `Message` list: roles, order and content.
    4. Asserts `result.model_dump(exclude={"audit_id"}) == case.expected_result`.
    5. Fetches `row = get_audit_log(result.audit_id)` and asserts `{"pii_detected_input": row.pii_detected_input, ..., "response": row.response} == case.expected_row`. Values are exact: `None`, not `[]`, for an empty `pii_entities` (F-4).
  - Guards, so the ACs cannot silently lose coverage:
    - `test_the_conversation_cases_are_chat_shaped()`: in every case there is no `system` turn, the last turn is `user`, and there are at least two earlier turns except in the response-only case. This is AC 2's "chat-shaped" as a check.
    - `test_the_history_only_case_masks_history_and_records_nothing()`: in case B, the expected history differs from the raw history, `expected_row["pii_detected_input"] is False` and `expected_row["pii_entities"] is None`. This states AC 3 against the data, so a later edit to the case table cannot drop it.
    - `test_the_response_case_masks_the_response()`: in case C, `expected_result["response"] != case.upstream_response` and `expected_row["pii_detected_output"] is True` (AC 4).
- **Mirror**: `tests/test_query_pipeline_run_conversation.py:278-320`, `tests/test_duplicate_characterization.py:86-122`
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_pii_characterization.py -q` is green, with 8 pipeline cases plus 3 guards on top of Task 1's. If any measured value differs from F-3 with the DB present, **stop and report it**. Do not re-measure and paste. A difference means the probe's substitution of `log_query` / `check_duplicate` hid something, and the plan's finding is wrong.

### Task 3: Prove the pins bite, then the full suite (AC 5)

- **Action**: temporary edits only, each reverted before commit. **These are the only edits under `app/` this story makes, and none of them is committed.**
- **Implement**: each change must make the named tests fail, and is then reverted:
  1. `PII_SCORE_THRESHOLD` default 0.35 → 0.5 in `app/config.py`. The fixture pins 0.35, so nothing should fail. That shows the fixture isolates settings. Then patch the fixture's value to 0.5 temporarily. The phone cases (`person-phone`, case B) must fail.
  2. In `redact()`, drop `sorted(...)` so the entity order is the set order. `test_redact_output_is_pinned` fails on multi-entity cases.
  3. In step 6, redact only the last message. Case B and case D fail on `calls`.
  4. In step 8, return `openrouter_result.response` unredacted. Cases C and D fail on `response`.
  5. In step 8, log `response=redacted_response`. Cases C and D fail on `row.response`.
  6. In step 6, keep the entities of every message rather than only the last. Cases B and D fail on the row.
  7. Replace the default anonymizer operator with `{"DEFAULT": OperatorConfig("replace", {"new_value": "<PII>"})}`. Every masking case fails.
- **Validate**:
  - `git status` shows only `tests/test_pii_characterization.py`.
  - `.venv/Scripts/python.exe -m pytest -q` is green, with the Task 0 count plus this module's 25 cases.
  - `git diff --name-only $BASE -- app/ chat_ui/ requirements.txt` is empty (AC 5), and stays empty after the commit: `git diff --name-only $BASE HEAD -- app/`.
  - Commit: `test(PRD-012): STORY-002 characterize redact() and pipeline steps 6/8`.

### Task 4: Report

- **File**: `.agents/reports/PRD-012-pii-for-code/STORY-002-pii-characterization.report.md` (written by `/implement`, in the STORY-001 report's shape)
- **Must contain**:
  - The library versions the pins were measured with. STORY-003 pins these in `requirements.txt`. A version bump there that changes a pin must be called out as the cause, not "fixed" by editing the pin.
  - **For STORY-009:** the pipeline cases are parametrized over `profile=None` and `"chat"`. `get_pii_policy("chat")` must pass both unchanged, and STORY-009 should import `CONVERSATION_CASES` for its `chat` assertions rather than copy them.
  - **For STORY-014:** the list of assertions to diff (this module, whole), plus the rule that no assertion changes.
  - **Observations, not fixed:**
    - The audit `response` column holds the **unmasked** model response (`query_pipeline.py:390`). This is relevant to the Security/Compliance Admin persona. Out of scope here. Flag it for a future PRD.
    - The NER span sometimes swallows a leading capitalised verb (`Call Aisha Bello` → `<PERSON>`).
    - `test_pii_redactor.py` runs on `en_core_web_sm`, contrary to the story's Technical Notes (F-1).
  - The seven bite checks from Task 3 and what failed for each.

---

## End-to-End Tests

`chat` has no new behaviour. The end-to-end proof is the module on untouched code plus the bite checks:

- [ ] With the libSQL container up, `pytest tests/test_pii_characterization.py -q` is green, with about 25 cases: 12 redact, 2 redact guards, 8 pipeline, 3 pipeline guards.
- [ ] All seven Task 3 bite checks fail as described and pass after revert.
- [ ] `pytest tests/test_pii_redactor.py tests/test_pii_redaction_integration.py tests/test_query_pipeline_run_conversation.py tests/test_query_pipeline_multiturn.py -q` is still green, so the fixture does not leak.
- [ ] Order independence: `pytest tests/test_pii_redactor.py tests/test_pii_characterization.py -q` and the reverse order are both green. This proves F-1's defence against the small-model fixture.
- [ ] The full suite is green.
- [ ] `git diff --name-only $BASE HEAD -- app/` is empty.

---

## Validation

```bash
# libSQL dev server must be up (tests/conftest.py:133; container harness-libsql-dev)
.venv/Scripts/python.exe -m pytest tests/test_pii_characterization.py -q
.venv/Scripts/python.exe -m pytest tests/test_pii_redactor.py tests/test_pii_characterization.py -q   # order check
.venv/Scripts/python.exe -m pytest -q
git diff --name-only $BASE HEAD -- app/ chat_ui/ requirements.txt                                     # must be empty
```

No server start is needed. This is a test-only story, and `/query` is already covered by `test_pii_redaction_integration.py`.

---

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| A stale `en_core_web_sm` analyzer or a developer `.env` pins the wrong bytes | The autouse fixture pins the four settings, drops a non-lg analyzer and asserts lg. Order checks in both directions (F-1) |
| The probe's in-memory `log_query` / `check_duplicate` hid a DB-side difference | Task 2 says to stop and report on any mismatch rather than paste new values |
| The lg model loads once per test and makes the module slow | Reset only when the cached analyzer is not lg. The singleton survives across tests |
| Pinning quirks (`Call` swallowed, unmasked audit `response`) reads as endorsing them | The docstring and the report say they are recorded, not endorsed. Changing them is a separate, announced change, not a side effect of PRD-012 (PRD Section 13, *Structure-safe replacement for `chat`*) |
| A later story "fixes" a pin to make its change pass | The docstring forbids it. STORY-014 diffs this module. Guards restate AC 1, 3 and 4 against the data, so a table edit that drops coverage fails |
| A future Presidio/spaCy upgrade shifts a pin | STORY-003 pins the versions. The report records the versions measured here, so drift can be attributed |
| libSQL is down or degraded | Task 0 starts it. Restart on mass fixture errors |

---

## Acceptance Criteria

(Copied from story `STORY-002`)

- [ ] Given `tests/test_pii_characterization.py` on untouched code, when it runs, then it is green and pins the exact output of `redact()` (masked text and sorted entity list) for a fixed set of at least ten prompts, including one with no PII, one with an already-masked `<PERSON>`, and one with every default entity type.
- [ ] Given a chat-shaped conversation (no system turn, user/assistant history plus a new user turn), when `run_conversation` runs with a recording `call_openrouter` stub, then the test pins the exact `Message` list the stub receives, the exact response returned, and the audit row's `pii_detected_input`, `pii_detected_output` and `pii_entities`.
- [ ] Given the same conversation with PII only in a history turn, when it runs, then the test pins that the history turn is masked upstream and that its entities are **not** recorded in the audit fields (PRD-010 D7).
- [ ] Given the response contains PII, when it runs, then the test pins that the returned response is masked and `pii_detected_output` is true.
- [ ] Given this story's commit, when it is diffed, then no file under `app/` changes.
- [ ] All tasks completed
- [ ] Full suite green (a test-only story; no server start needed beyond the libSQL dev container)
- [ ] Follows existing patterns (characterization docstring, `_CASES` + ids, recording stub, `get_audit_log(result.audit_id)`, exact equality)
