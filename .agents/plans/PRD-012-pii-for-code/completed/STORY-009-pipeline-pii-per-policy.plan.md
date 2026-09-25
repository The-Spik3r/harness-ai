---
story: STORY-009
prd: PRD-012
slug: pipeline-pii-per-policy
title: "Pipeline steps 6 and 8 redact per the resolved policy"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-012-pii-for-code        # all stories commit here, no per-story branch
created: 2026-09-25
---

# Plan: Pipeline steps 6 and 8 redact per the resolved policy

## Summary

This story wires the PII policy into `run_conversation` in `app/services/query_pipeline.py`. It changes two steps and adds nothing else.

- **Step 6.** Resolve the policy once with `get_pii_policy(profile_name)`, using the name step 5 already computes. A message whose role is not in `policy.input_roles` is appended as the **same `Message` object**. Every other message goes through one private helper, `_redact(text, policy)`.
- **Step 8.** Runs only when `policy.output` is on. When it is off, the response is returned unchanged and `output_entities` is `[]`, so the row records `pii_detected_output=0`.

The helper calls the module-level `redact` for a policy without `structure_safe` (`chat`), and `redact_for_policy` for any other policy. That branch is what keeps `chat` byte-identical **and** keeps working the ~20 existing tests that monkeypatch `query_pipeline.redact` (F-1).

The following are unchanged:

- PRD-010 D7's audit semantics
- the redaction-error arms
- `_validate_conversation`
- every `log_query` call

STORY-010 adds the size arm at the head of step 6. STORY-011 adds `profile` to every audit arm.

## User Story

As an integrating developer
I want `run_conversation(profile="code")` to apply the `code` PII policy on input and to leave the model's output unmasked
So that my agent's context is protected without placeholders being written into my files

## Story Reference

- Story file: `.agents/stories/PRD-012-pii-for-code/STORY-009-pipeline-pii-per-policy.md`
- PRD: `.agents/PRDs/PRD-012-pii-for-code/PRD.md`: Sections 6.1, 6.3, 6.8, 7 (F8), 10, 11 (Functional requirements)
- Handoffs consumed:
  - **STORY-002 report.** Import `CONVERSATION_CASES` for `chat`; do not copy it. The characterization pipeline cases already run under `profile=None` and `profile="chat"`, and both must pass unchanged.
  - **STORY-007 report.** Call `get_pii_policy(profile_name)` once per request. It never raises and never logs. A test that patches a `PII_*` setting calls `pii_policy.load()`, and the `_default_pii_policy` fixture in `tests/conftest.py:215-225` restores the policies afterwards.
  - **STORY-008 report.** `redact_for_policy` returns a `RedactionResult`, which unpacks like `redact()`. Its `PiiRedactorError` messages carry no content. This plan **deviates** from "call `redact_for_policy` for every policy" for the `chat` branch. See F-1 and D-1.

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/services/query_pipeline.py`, `tests/test_query_pipeline_pii_profiles.py` (new) |
| Story | STORY-009 |
| PRD | PRD-012 |
| Epic Branch | `epic/PRD-012-pii-for-code` (commit directly on this branch) |
| Depends on | STORY-002 ✅ (`5e93b18`), STORY-007 ✅ (`50ef312`), STORY-008 ✅ (`df74e9b`) |
| Blocks | STORY-010, STORY-012, STORY-013 |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | None. The story's `skills: []` and "Skills: none applicable" hold. `.agents/skills/` contains only `frontend-design` (visual UI design), and this story changes no UI. | — |

---

## Findings (measured before planning)

| # | Finding | Evidence | Consequence |
|---|---------|----------|-------------|
| F-1 | **About 20 existing tests replace `query_pipeline.redact` with `monkeypatch.setattr`.** They spy on its call order, fail on the first or second call, or raise from it. `redact_for_policy` calls `pii_redactor.redact`, a different binding, so routing `chat` through it would skip every one of those patches. | `tests/test_pii_dedup_isolation.py:265, 292-331` (asserts the call sequence `[..., "redact", "redact"]`); `test_chat_outcomes_regression.py:56, 164, 206`; `test_duplicate_scope.py:525-572, 784-789`; `test_duplicate_checker.py:395-419`; `test_duplicate_characterization.py:172-182`; `test_query_pipeline_patterns.py:180` | The `chat` branch must call `redact` **by its `query_pipeline` name** (D-1). AC 1's "step 6 calls `redact()` for every message" is then literally true. |
| F-2 | Step 5 already computes `profile_name` (`profile` or `settings.PATTERN_PROFILE_DEFAULT`). An unknown name raises `PatternConfigError` in `get_profile` before step 6 runs. | `query_pipeline.py:252-254` | Reuse `profile_name`; do not re-derive it. With the built-in patterns, the `chat` fallback in `get_pii_policy` is reached only through a patterns file that defines a profile with no PII policy. |
| F-3 | Step 6 builds a **new** `Message(message.role, redacted_content)` for every message, even when nothing changed. | `query_pipeline.py:334` | A role outside `input_roles` must append `message` itself (Technical Notes). Covered roles keep today's construction, so `chat` is unchanged. |
| F-4 | The step-8 error arm logs `pii_detected_input` / `pii_entities` from `input_entities`. The success arm unions input and output entities. | `query_pipeline.py:365-399` | With output off, `output_entities = []` and `redacted_response = openrouter_result.response`. The success arm then needs no other change, and D7 holds (AC 4). |
| F-5 | The `code` policy's default entity list has no NER type, so `_get_analyzer(policy.entities)` returns the tokenizer-only analyzer (`spacy.blank("en")`). No model download is needed, and `PII_NLP_MODEL` is irrelevant on the `code` path. | `pii_redactor.py:40-52, 102-131`; `tests/test_pii_structure_safe.py:88-97` (`_Tripwire`) | `code` pipeline tests use the real pattern analyzer, which is fast and deterministic for emails. A `_Tripwire` on `_analyzer` can prove `en_core_web_lg` is never touched on a `code` request (PRD Section 11). |
| F-6 | `_validate_conversation` refuses `tool` turns. `tests/test_query_pipeline_patterns.py:359-383` has a test-only `_admit_tool_turns` bypass. | `query_pipeline.py:57-63` | Not used here: the story keeps the `tool` cell at STORY-008's direct-call level. Production step 0 is untouched. |

---

## Patterns to Follow

### Step comments cite the PRD and explain the position
```python
# SOURCE: app/services/query_pipeline.py:312-316
# Step 6: redact every message (D5) -- history must never leave the
# process unmasked, whatever its source. Only the last user turn's
# entities count toward the audit's PII fields (D7): re-redacting
# history that already passed once is not a new PII event, or every
# later row of a session would misreport one (PRD Section 6.7).
```

### Error handling: log the arm, then re-raise
```python
# SOURCE: app/services/query_pipeline.py:321-333
try:
    redacted_content, entities = redact(message.content)
except PiiRedactorError as exc:
    log_query(
        user_id=identity.user_id, prompt=prompt, device=device,
        success=False, error_message=str(exc),
        session_id=session_id, dedup_key=key,
    )
    raise
```

### Collaborators patched by module name, not captured
```python
# SOURCE: tests/test_pii_dedup_isolation.py:292-314
real_redact = query_pipeline.redact
def _spy_redact(text):
    calls.append(("redact", text))
    return real_redact(text)
monkeypatch.setattr(query_pipeline, "redact", _spy_redact)
```

### Tests: run helper, recording upstream stub, audit readers
```python
# SOURCE: tests/test_query_pipeline_patterns.py:81-101, 386-400
def _fail_if_called(*args, **kwargs):
    raise AssertionError("this collaborator should not have been called")

class _Upstream:
    def __init__(self) -> None:
        self.calls: list = []
    def __call__(self, messages, model="gpt-4", api_key=None):
        self.calls.append(list(messages))
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

def _run(messages, call_openrouter=_fail_if_called, **kwargs):
    kwargs.setdefault("identity", _JUAN)
    return query_pipeline.run_conversation(
        messages=messages, device=None, model="gpt-4", openrouter_api_key=None,
        call_openrouter=call_openrouter, **kwargs,
    )
```

### Tests: settings patched, then the policy rebuilt
```python
# SOURCE: .agents/reports/PRD-012-pii-for-code/STORY-007-pii-policy.report.md:128-130; tests/conftest.py:215-225
monkeypatch.setattr(settings, "PII_CODE_REDACT_OUTPUT", True)
pii_policy.load()          # conftest's _default_pii_policy restores _policies afterwards
```

### Tests: stub analyzer and tripwire
```python
# SOURCE: tests/test_pii_structure_safe.py:63-97
class _StubAnalyzer: ...           # returns fixed RecognizerResult spans
monkeypatch.setattr(pii_redactor, "_get_analyzer", lambda entities=None: stub)
class _Tripwire: ...               # any attribute access on the full analyzer fails
```

---

## Design

### Files to CREATE
- `tests/test_query_pipeline_pii_profiles.py`: step 6 and step 8 per profile, D7, and the error arm. The upstream is an injected `call_openrouter` stub and never the network.

### Files to UPDATE
- `app/services/query_pipeline.py`:
  - imports
  - the `_redact` helper
  - step 6: policy resolved once; role gate; same-object pass-through
  - step 8: gated on `policy.output`

### Dependency order
1. Update the imports and add the `_redact` helper (Task 1).
2. Step 6 (Task 2).
3. Step 8 (Task 3).
4. Test module (Tasks 4 and 5).
5. Regression sweep (Task 6).

### Decisions made here

| # | Decision | Why |
|---|----------|-----|
| D-1 | `_redact(text, policy)` returns `redact(text)` when `not policy.structure_safe`, and `redact_for_policy(text, policy)` otherwise. | For `chat` both give the same value (STORY-008 AC 5). Only `redact` by its `query_pipeline` name keeps F-1's patches effective, and AC 1 requires that "no assertion changed". Branching on `structure_safe` mirrors the branch inside `redact_for_policy` (`pii_redactor.py:468-469`), so the two cannot disagree about which path `chat` takes. |
| D-2 | Resolve the policy at the **head of step 6**, not at step 5. | PRD Section 6.1 places it there. STORY-010's size check goes directly after it and needs `policy`. It still runs once per request, from the `profile_name` step 5 computed (F-2). |
| D-3 | A skipped role appends `message` itself. A covered role keeps `Message(message.role, redacted_content)` even when nothing changed. | This is the Technical Note. Keeping today's construction for covered roles means `chat`'s upstream list does not change, even on identity. |
| D-4 | `input_entities` is still taken only from `index == last_index`. The last message is always a `user` turn (step 0), and `user` is in both policies' `input_roles`, so D7 is unaffected. | AC 4. Setting `PII_CODE_REDACT_SYSTEM` cannot move the recorded entities, because `system` is never last. |
| D-5 | Output off: `redacted_response = openrouter_result.response` and `output_entities = []`. There is no `try` block, because nothing can raise. | AC 3. The success arm and `QuerySuccessResponse` are unchanged. With output off, `pii_redacted` / `pii_entities_masked` reflect input entities only. |
| D-6 | The `PII_REDACTION_ENABLED` master switch is not checked in the pipeline. | Both `redact` and `redact_for_policy` already honour it. |

### Risks

| Risk | Mitigation |
|------|------------|
| A `chat` byte drift, from constructing messages differently or from a different redact binding | D-1 and D-3. Task 6 runs the characterization, integration and both outcome regressions, and every test file listed in F-1, with no assertion edited. |
| A `code` test depends on NER or on the large model | `code` uses the tokenizer-only analyzer (F-5). The tests pin `PII_ENTITIES_CODE` to the default and assert with a `_Tripwire` that the full analyzer is never reached. |
| An email recognizer score under `PII_SCORE_THRESHOLD_CODE` | Presidio's `EmailRecognizer` scores 1.0, above any threshold in `[0, 1)`. The tests also pin the threshold to its shipped value. |
| STORY-010 and STORY-011 conflict with this edit | This story touches only steps 6 and 8, and adds no `log_query` keyword. STORY-010 inserts its arm between the policy line and the loop (D-2). |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/query_pipeline.py` | UPDATE | Resolve the policy once. Step 6 is role-gated through `_redact`, and step 8 is gated on `policy.output`. |
| `tests/test_query_pipeline_pii_profiles.py` | CREATE | ACs 1–5 per profile, with an injected upstream stub. |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Imports and the `_redact` helper

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  - Change the imports:
    - `from app.services.pii_policy import PiiPolicy, get_pii_policy`
    - `from app.services.pii_redactor import PiiRedactorError, redact, redact_for_policy`
  - Add a module-level `_redact(text: str, policy: PiiPolicy) -> Tuple[str, list[str]]` beside `_context_limit_exceeded`. It uses the existing `typing` imports; `RedactionResult` is a `NamedTuple`, so it satisfies that type.
  - Its body is `if not policy.structure_safe: return redact(text)`, then `return redact_for_policy(text, policy)`.
  - Its docstring should say:
    - the `chat` branch is `redact()` by this module's name, byte for byte (PRD-012 Section 2);
    - tests patch `query_pipeline.redact`, so the name is load-bearing (F-1);
    - `redact_for_policy` would return the same value for `chat`, so this is a binding choice, not a behaviour choice.
- **Mirror**: `query_pipeline.py:66-93` (a private helper with a docstring explaining why settings are read per call)
- **Validate**: `python -c "import app.services.query_pipeline"` (no import cycle: `pii_policy` does not import `pii_redactor` or `query_pipeline`)

### Task 2: Step 6 per policy

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  - At the head of step 6, add `policy = get_pii_policy(profile_name)`, with a comment: resolved once per request from step 5's name (PRD-012 Section 6.1, F8). STORY-010's size arm goes directly below.
  - In the loop, when `message.role not in policy.input_roles`, call `redacted_messages.append(message)` and `continue`. The comment should say: same object, byte-identical upstream (`code` `system`, D3). A `tool` turn cannot reach this point (step 0, PRD-016).
  - Otherwise call `redacted_content, entities = _redact(message.content, policy)` inside the **existing** `try/except PiiRedactorError` arm, unchanged.
  - Rewrite the step-6 comment to describe the role map. Keep the D5/D7 rationale, and note that under `code` history is still masked (T7).
- **Mirror**: `query_pipeline.py:312-336`
- **Validate**: `pytest tests/test_pii_characterization.py tests/test_pii_dedup_isolation.py -q`

### Task 3: Step 8 gated on `policy.output`

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  - If `policy.output` is on, run the existing `try: redacted_response, output_entities = _redact(openrouter_result.response, policy)`, followed by the unchanged error arm.
  - Else set `redacted_response = openrouter_result.response` and `output_entities: list[str] = []`.
  - Add a comment citing D1: the reader of a coding agent's output is the file system. `pii_detected_output` is `0` because the output was not analyzed, and STORY-011's `profile` column is what tells the reader so.
  - Leave the success `log_query` and `QuerySuccessResponse` untouched.
- **Mirror**: `query_pipeline.py:364-408`
- **Validate**: `pytest tests/test_query_outcomes_regression.py tests/test_pii_redaction_integration.py -q`

### Task 4: Test module scaffold

- **File**: `tests/test_query_pipeline_pii_profiles.py`
- **Action**: CREATE
- **Implement**:
  - A module docstring listing:
    - PRD-012 STORY-009 and the ACs;
    - "upstream is an injected stub, never the network";
    - the libSQL dev-container note (restart it on mass fixture errors).
  - `os.environ.setdefault` for `OPENROUTER_API_KEY` / `ADMIN_TOKEN`.
  - Helpers copied in shape from `test_query_pipeline_patterns.py`: `_JUAN`, `_fail_if_called`, a recording `_Upstream(response=...)`, `_run`, `_last_audit_entry`, `_count_audit_rows`.
  - An autouse fixture that pins, then calls `pii_policy.load()`:
    - `PII_REDACTION_ENABLED=True`
    - `PII_ENTITIES_CODE` to the default five
    - `PII_SCORE_THRESHOLD_CODE` to its shipped value
    - `PII_CODE_REDACT_OUTPUT=False`
    - `PII_CODE_REDACT_SYSTEM=False`
    - `PII_CODE_SKIP_CODE_BLOCKS=True`
  - A `_redact_output(monkeypatch)` helper that sets `PII_CODE_REDACT_OUTPUT=True` and calls `pii_policy.load()`.
  - `chat` cases import `CONVERSATION_CASES` from `tests.test_pii_characterization` and use that module's `_shipped_pii_settings` values by import, not by copy. Only `chat` tests load `en_core_web_lg`.
- **Mirror**: `tests/test_query_pipeline_patterns.py:1-120`; `tests/test_pii_structure_safe.py:42-51`
- **Validate**: `pytest tests/test_query_pipeline_pii_profiles.py -q --collect-only`

### Task 5: Tests, grouped by AC

- **File**: `tests/test_query_pipeline_pii_profiles.py`
- **Action**: UPDATE
- **Implement**:
  - **AC 1 (`chat`, no profile)**
    - Spy on `query_pipeline.redact` and `query_pipeline.redact_for_policy`. Run one `CONVERSATION_CASES` case with `profile=None`.
    - Assert `redact` saw every message's content, then the response, in that order (`len(messages) + 1` calls).
    - Assert `redact_for_policy` was never called.
    - Parametrize `profile` over `None` and `"chat"`.
  - **Policy resolved once**
    - Spy on `query_pipeline.get_pii_policy`, then run under `None` and `"code"`.
    - Assert it was called exactly once, with `settings.PATTERN_PROFILE_DEFAULT` for `None` and with `"code"` otherwise.
  - **AC 2 (`code` roles)**
    - Send `[system "Contact ops@corp.com for escalations.", user "email maria.lopez@corp.com", assistant "I will write to maria.lopez@corp.com", user "thanks"]`.
    - Assert `upstream.calls[0][0] is messages[0]` and that its content is unchanged.
    - Assert the user and assistant turns reach upstream with `<EMAIL_ADDRESS>`.
    - Spy on `query_pipeline.redact_for_policy` and assert it was called for exactly the three non-system turns, with `policy.name == "code"`.
    - Assert `query_pipeline.redact` was never called.
  - **AC 2 (setting)**: with `PII_CODE_REDACT_SYSTEM=True` and `load()`, the `system` turn is masked.
  - **AC 2 (fences)**: a user turn with an email inside a ```` ``` ```` fence and another in the prose. Upstream gets the fence byte-identical and the prose masked. This is a pipeline-level smoke test; the fence rules are STORY-008's tests.
  - **AC 3 (output off)**
    - The upstream response is `"Use alice@example.com in the fixture."`.
    - Assert `result.response` is unchanged, the row has `pii_detected_output is False`, and `pii_entities is None` (no input PII).
  - **AC 3 (output on)**
    - Call `_redact_output`, then run the same response.
    - Assert `result.response == "Use <EMAIL_ADDRESS> in the fixture."`, `pii_detected_output is True`, and `pii_entities == "EMAIL_ADDRESS"`.
  - **AC 4 (D7), for both profiles**
    - History carries PII and the last user turn does not. Assert `pii_detected_input is False` and `pii_entities is None`, while history is masked upstream.
    - The last user turn carries a phone (`code`: `+1 415 555 0134`) and output is on with an email. Assert `pii_entities` is exactly the sorted union.
    - For `chat`, AC 4 is held by the imported `CONVERSATION_CASES` "pii-in-history-only". Assert it through the same runner rather than re-pinning values.
  - **AC 5 (error arm)**
    - Patch `query_pipeline.redact_for_policy` to raise `PiiRedactorError("PII analysis failed: boom")` on the **assistant** (history) turn.
    - Run with `call_openrouter=_fail_if_called`.
    - Assert `pytest.raises(PiiRedactorError)`, exactly one new row with `success is False` and that `error_message`, and that the upstream was not called.
    - Repeat for `chat` by patching `query_pipeline.redact`.
  - **AC 5 (JSON post-condition)**
    - A user turn with JSON content, and a stub analyzer (the `_StubAnalyzer` shape) whose span is placed so the post-condition must fail.
    - If no natural span can break the post-condition after clipping, patch `pii_redactor.json.loads` for that one call to raise `ValueError`.
    - Assert the same row shape and no upstream call.
  - **PRD Section 11 (no NER on `code`)**: `monkeypatch.setattr(pii_redactor, "_analyzer", _Tripwire(log))`, run a `code` conversation, and assert `log == []`.
- **Mirror**: `tests/test_query_pipeline_patterns.py:122-260, 416-480`; `tests/test_pii_structure_safe.py:63-97`; `tests/test_pii_characterization.py:175-260`
- **Validate**: `pytest tests/test_query_pipeline_pii_profiles.py -v`

### Task 6: Regression sweep

- **File**: none (validation only)
- **Action**: none
- **Implement**:
  - Run the protected suites and every file in F-1.
  - No assertion may change in:
    - `test_pii_characterization.py`
    - `test_pii_redaction_integration.py`
    - `test_query_outcomes_regression.py`
    - `test_chat_outcomes_regression.py`
    - `test_pii_redactor.py`
  - `git diff --stat tests/` must list only the new file.
- **Validate**:
  ```bash
  pytest tests/test_pii_characterization.py tests/test_pii_redaction_integration.py \
         tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py \
         tests/test_pii_redactor.py tests/test_pii_dedup_isolation.py \
         tests/test_duplicate_scope.py tests/test_duplicate_checker.py \
         tests/test_duplicate_characterization.py tests/test_query_pipeline_patterns.py -q
  pytest tests/ -q
  git diff --stat tests/
  ```

---

## End-to-End Tests

- [ ] `POST /query` with a prompt containing `jane.doe@example.com` returns 200, the response is masked, and the audit row matches the characterization values. This is exercised by `test_pii_redaction_integration.py`, which is unchanged.
- [ ] The chat UI send path (`ChatState` → `run_conversation` with no profile) is covered by `test_chat_outcomes_regression.py`, which is unchanged.
- [ ] Direct call to `run_conversation(profile="code")` with a `system` prompt containing an email: the system turn is unchanged upstream, user PII is masked, and the response is unmasked. This is the new module.
- [ ] Full `pytest tests/ -q` is green. If there are mass fixture errors, restart the libSQL dev container rather than bisecting.

---

## Validation

```bash
python -c "import app.services.query_pipeline"
pytest tests/test_query_pipeline_pii_profiles.py -v
pytest tests/ -q
git diff --stat tests/     # only tests/test_query_pipeline_pii_profiles.py added
```

---

## Handoff (for later stories)

- **STORY-010**:
  - Insert the size check directly after `policy = get_pii_policy(profile_name)` and before the loop.
  - Count only messages whose role is in `policy.input_roles`, using `strip_fenced_blocks` when `policy.skip_fenced_blocks` is set.
  - `chat` has `max_characters=None`.
- **STORY-011**:
  - `profile_name` is the value to pass as `profile=` on every `log_query` call.
  - Under `code` with output off, `pii_detected_output=0` is "not analyzed". The column is what disambiguates it.
- **STORY-012**: `run_conversation(profile="code")` is now the real `code` path for the spike's scripted tasks.
- **STORY-013**: the round-trip suite can go through `run_conversation(profile="code")` with an upstream stub. Latency stays measured on `redact_for_policy`.

---

## Acceptance Criteria

(Copied from story `STORY-009`)

- [ ] Given `run_conversation` with no `profile` (the `/query` and chat UI path), when it runs, then step 6 calls `redact()` for every message and step 8 redacts the response, and `test_pii_characterization.py`, `test_pii_redaction_integration.py` and `test_query_outcomes_regression.py` pass with no assertion changed.
- [ ] Given `profile="code"`, when a conversation has `system`, `user` and `assistant` turns, then the `system` turn reaches `call_openrouter` byte-identical, and `user` and `assistant` turns go through `redact_for_policy` with the `code` policy.
- [ ] Given `profile="code"` and a response containing `alice@example.com`, when it runs, then the returned response is unchanged and the audit row has `pii_detected_output=0`; with `PII_CODE_REDACT_OUTPUT=true`, it is masked and `pii_detected_output=1`.
- [ ] Given either profile, when history turns carry PII, then only the last user turn's entities (plus output entities, when output is redacted) are recorded in `pii_detected_input` / `pii_entities` (PRD-010 D7 kept).
- [ ] Given `redact_for_policy` raises `PiiRedactorError` on any message, when step 6 runs, then the existing redaction-error arm writes its row and re-raises, and `call_openrouter` is never called.
- [ ] All tasks completed
- [ ] Full test suite passes; no assertion changed in the protected test files
- [ ] Follows existing patterns
