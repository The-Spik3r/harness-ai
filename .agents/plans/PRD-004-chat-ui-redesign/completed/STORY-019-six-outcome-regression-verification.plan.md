---
story: STORY-019
prd: PRD-004
slug: six-outcome-regression-verification
title: "Six-outcome walkthrough and full-suite regression verification"
type: REFACTOR
complexity: MEDIUM
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-25
---

# Plan: Six-outcome walkthrough and full-suite regression verification

## Summary

Verify the completed chat UI redesign against all MVP success criteria, ensuring zero changes under `app/`, 100% passing test suites with only `tests/test_chat_state.py` modified across the epic, and conducting the 6-outcome validation walkthrough.

## User Story

As an integrating developer, I want the finished redesign verified against every MVP success criterion and proved to be confined to `chat_ui/`, so that the epic closes on evidence rather than on assumption (PRD Section 11, User Story 8).

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-019-six-outcome-regression-verification.md`
- PRD: `.agents/PRDs/PRD-004-chat-ui-redesign/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui`, `tests` |
| Story | STORY-019 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `reflex-process-management` | Reflex app process management & verification walkthrough | Tasks 1, 2, 3 |

---

## Patterns to Follow

### Naming
```
// SOURCE: tests/test_chat_state.py:1-15
@pytest.mark.asyncio
```

### Error Handling
```
// SOURCE: chat_ui/chat_ui/state.py:97-140
except OpenRouterError as exc:
except PiiRedactorError as exc:
except Exception as exc:
```

### Tests
```
// SOURCE: tests/test_chat_state.py:174-210
async def test_chat_state_send_success_appends_user_then_assistant_bubble(temp_db, monkeypatch):
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `.agents/reports/PRD-004-chat-ui-redesign/STORY-019-six-outcome-regression-verification.report.md` | CREATE | Record verification results and quality metrics walkthrough evidence |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Verify Zero Application (`app/`) Modifications
- **File**: `app/` directory
- **Action**: INSPECT / VERIFY
- **Implement**: Run `git diff main...epic/PRD-004-chat-ui-redesign -- app/` to verify zero files modified under `app/`.
- **Mirror**: PRD Section 11 & Section 12 quality table requirements.
- **Validate**: Command output is completely empty.

### Task 2: Verify Full Test Suite Regression & Test File Diff Isolation
- **File**: `tests/` directory
- **Action**: RUN TESTS
- **Implement**: Run `pytest` across the entire test suite including `tests/test_chat_state.py` and `tests/test_route_reservations.py`. Check `git status` / `git diff --name-only main...epic/PRD-004-chat-ui-redesign` to confirm `tests/test_chat_state.py` is the only test file modified across the epic.
- **Mirror**: PRD Section 9 & Section 11 requirements (`tests/test_route_reservations.py` passes, only `tests/test_chat_state.py` modified).
- **Validate**: 100% test pass rate.

### Task 3: Execute 6-Outcome Walkthrough and Error Handling Verification
- **File**: `chat_ui/` / `tests/`
- **Action**: VERIFY
- **Implement**: Verify each of the 6 pipeline outcomes via tests/walkthrough:
  1. Success (normal query response)
  2. Seeded duplicate (`duplicate` kind)
  3. Prompt containing `override` (`suspicious` kind)
  4. Prompt containing email address (PII badge / redactor signal)
  5. Unset `OPENROUTER_API_KEY` (`upstream_error`)
  6. Bogus `PII_NLP_MODEL` (`internal_error` / `PiiRedactorError`)
  7. Forced arbitrary exception (catch-all error handler)
- **Mirror**: PRD Section 12 Phase 3 validation table.
- **Validate**: All 6 outcomes render distinct structured treatments correctly.

### Task 4: Generate Story Report
- **File**: `.agents/reports/PRD-004-chat-ui-redesign/STORY-019-six-outcome-regression-verification.report.md`
- **Action**: CREATE
- **Implement**: Record all walkthrough evidence, quality indicators verbatim, and confirmation of MVP definition of done checkboxes.
- **Validate**: Report file created successfully.

---

## Validation

```bash
pytest
git diff main...epic/PRD-004-chat-ui-redesign -- app/
git diff --name-only main...epic/PRD-004-chat-ui-redesign
```

---

## Acceptance Criteria

- [ ] Given the six pipeline outcomes, when each is exercised end to end, then each renders its own distinct treatment.
- [ ] Given the full repo test suite, when it runs, then it passes and `tests/test_chat_state.py` is the only test file whose diff is non-empty across the epic.
- [ ] Given `git diff main...epic/PRD-004-chat-ui-redesign -- app/`, when run, then it is empty — zero files modified under `app/`.
- [ ] Given a chat-originated audit row from the walkthrough, when inspected, then `device` is non-null and `model_used` matches the model selected in the UI.
- [ ] Given each MVP "definition of done" checkbox in PRD Section 11, when the walkthrough concludes, then each is confirmed and recorded in the story report.
- [ ] All tasks completed.
