---
story: STORY-005
prd: PRD-001
slug: pattern-detection-service
title: Suspicious pattern detection service
type: feature
complexity: small
epic_branch: epic/PRD-001-harness-ia
created: 2026-07-04
---

# Plan: Suspicious pattern detection service

## Summary

Add `app/services/pattern_detector.py` to the existing `app/services/` package (created in STORY-004). It holds the seven suspicious substrings from PRD Section 9 as a single module-level list constant and exposes one pure function, `detect_suspicious_pattern(prompt: str) -> PatternDetectionResult`, that lowercases the incoming prompt and checks each pattern with a plain `in` substring test (no regex, per the story's Technical Notes). On the first match it returns `PatternDetectionResult(is_suspicious=True, pattern=<matched pattern string>)`; if none match, `PatternDetectionResult(is_suspicious=False)`. Unlike STORY-004's `duplicate_checker.py`, this service touches no database and has no failure mode to wrap — it is pure, synchronous string logic, so there is no dedicated exception type. Adding a new pattern is a one-line edit to the `SUSPICIOUS_PATTERNS` list, satisfying AC 4's Strategy-pattern requirement (PRD Section 6) without touching any branching logic.

## User Story

As a security admin
I want basic prompt-injection patterns blocked before they reach the model
So that known attack strings never get forwarded upstream

## Story Reference

- Story file: `.agents/stories/PRD-001-harness-ia/STORY-005-pattern-detection-service.md`
- PRD: `.agents/PRDs/PRD-001-harness-ia/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | small |
| Systems Affected | `app/services/` (existing package, new module) |
| Story | STORY-005 |
| PRD | PRD-001 |
| Epic Branch | `epic/PRD-001-harness-ia` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` has no `SKILL.md` files in this repo, and the story's `skills: []` frontmatter is empty — same situation as STORY-001 through STORY-004.

---

## Codebase State

`app/services/` already exists (created by STORY-004) containing `__init__.py` and `duplicate_checker.py`. That module establishes the local convention this story follows: a small `@dataclass` result type, a pure top-level function, no class-based service objects. `app/models/schemas.py` (STORY-003) already defines `QueryBlockedSuspiciousResponse` with a `pattern: str` field — populated from PRD Section 10's example as the generic label `"prompt_injection"` — but this story's own acceptance criteria ask the detector to "report which pattern matched," i.e. the actual matched string (e.g. `"ignore previous instructions"`), not a category label. That's a request/response wiring decision for STORY-008 (which depends on this story); this plan keeps `pattern_detector.py` decoupled from `schemas.py` entirely and returns the specific matched pattern text, leaving STORY-008 to decide how it maps into `QueryBlockedSuspiciousResponse.pattern`. No test file for this module exists yet (`tests/` currently has `test_main.py`, `test_db.py`, `test_schemas.py`, `test_duplicate_checker.py`).

---

## Design Decisions

1. **Single list constant, not branching logic.** `SUSPICIOUS_PATTERNS: List[str]` holds the seven lowercase pattern strings verbatim from PRD Section 9. `detect_suspicious_pattern` loops over this list with a single `if pattern in lowered_prompt:` check — no `if/elif` chain per pattern. This is the AC 4 requirement (Strategy pattern, PRD Section 6): adding pattern #8 later is a one-line list edit.

2. **Case-insensitive via `.lower()` on the prompt only.** Patterns are stored already-lowercase in the constant; the incoming prompt is lowered once at the top of the function and compared with plain substring (`in`) checks — no `re`/regex, matching the story's Technical Note ("substring + case-insensitive match — no regex complexity needed for MVP").

3. **First match wins, matched pattern text is returned as-is.** The result's `pattern` field is set to the exact string from `SUSPICIOUS_PATTERNS` that matched (e.g. `"ignore previous instructions"`), not the original-cased substring found in the user's prompt. This gives callers/tests a stable, predictable value regardless of how the user capitalized their input, and directly satisfies AC 1 ("reports which pattern matched").

4. **No custom exception type.** `duplicate_checker.py` needed `DuplicateCheckError` because it depends on SQLite and can fail at the I/O layer. `pattern_detector.py` has no I/O and no failure mode — a `List[str]` substring scan cannot meaningfully raise — so no dedicated exception is introduced. This keeps the module as simple as the story's own scope demands ("Simple over clever," PRD Mission).

5. **Dataclass result type mirrors `DuplicateCheckResult`.** `PatternDetectionResult(is_suspicious: bool, pattern: Optional[str] = None)` — same shape/spirit as `duplicate_checker.py`'s result dataclass, keeping the two sibling services visually and structurally consistent for whoever wires them together in STORY-008.

---

## Patterns to Follow

### Dataclass result type + pure function
```python
// SOURCE: app/services/duplicate_checker.py:12-37
class DuplicateCheckError(Exception):
    pass


@dataclass
class DuplicateCheckResult:
    is_duplicate: bool
    first_query_at: Optional[str] = None


def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def check_duplicate(prompt: str) -> DuplicateCheckResult:
    ...
```
`pattern_detector.py` follows the same dataclass-result + top-level-function shape, minus the DB/exception plumbing (no I/O here).

### Tests: plain assert, one behavior per function, env setup first
```python
// SOURCE: tests/test_duplicate_checker.py:1-25
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.services.duplicate_checker import (
    DuplicateCheckError,
    check_duplicate,
    hash_prompt,
)
```
`tests/test_pattern_detector.py` mirrors the env-var bootstrap lines (harmless here since this module doesn't touch `config`/`settings`, but keeps the file consistent with sibling test files and safe if that ever changes) and the plain-`assert`, no-unittest-class style used throughout the suite.

### Parametrized per-pattern tests
```python
// SOURCE: tests/test_schemas.py (style: one assertion focus per test function)
```
No existing `@pytest.mark.parametrize` usage in this repo yet, but it is the standard pytest idiom for "test each of N items individually" (AC's explicit requirement) while keeping each case separately visible in `pytest -v` output.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/pattern_detector.py` | CREATE | `SUSPICIOUS_PATTERNS`, `PatternDetectionResult`, `detect_suspicious_pattern` |
| `tests/test_pattern_detector.py` | CREATE | Unit tests: each of the 7 patterns, one clean prompt, one mixed-case match |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `app/services/pattern_detector.py`

- **File**: `app/services/pattern_detector.py`
- **Action**: CREATE
- **Implement**:
  ```python
  from dataclasses import dataclass
  from typing import List, Optional

  SUSPICIOUS_PATTERNS: List[str] = [
      "ignore previous instructions",
      "forget everything",
      "show system prompt",
      "reveal password",
      "execute code",
      "admin mode",
      "override",
  ]


  @dataclass
  class PatternDetectionResult:
      is_suspicious: bool
      pattern: Optional[str] = None


  def detect_suspicious_pattern(prompt: str) -> PatternDetectionResult:
      lowered = prompt.lower()
      for pattern in SUSPICIOUS_PATTERNS:
          if pattern in lowered:
              return PatternDetectionResult(is_suspicious=True, pattern=pattern)
      return PatternDetectionResult(is_suspicious=False)
  ```
- **Mirror**: `app/services/duplicate_checker.py:16-23` for the dataclass + top-level pure-function style; PRD Section 9's pattern list copied verbatim (already lowercase, matching the PRD's own listing).
- **Validate**: `python -c "from app.services.pattern_detector import detect_suspicious_pattern, SUSPICIOUS_PATTERNS, PatternDetectionResult"` succeeds.

### Task 2: Create `tests/test_pattern_detector.py`

- **File**: `tests/test_pattern_detector.py`
- **Action**: CREATE
- **Implement**: Env-var bootstrap (mirror `tests/test_duplicate_checker.py:1-4`), then:
  - `@pytest.mark.parametrize("pattern", SUSPICIOUS_PATTERNS)` test that asserts `detect_suspicious_pattern(f"please {pattern} now")` returns `is_suspicious is True` and `pattern == pattern` — covers all 7 patterns individually as distinct pytest cases.
  - `test_clean_prompt_reports_not_suspicious` — `detect_suspicious_pattern("what's the weather today?")` → `is_suspicious is False`, `pattern is None`.
  - `test_mixed_case_pattern_still_flagged` — `detect_suspicious_pattern("IGNORE PREVIOUS INSTRUCTIONS right now")` → `is_suspicious is True`, `pattern == "ignore previous instructions"`.
  - `test_first_matching_pattern_returned_when_multiple_present` — a prompt containing two patterns (e.g. both `"override"` and `"admin mode"`) returns whichever pattern appears first in `SUSPICIOUS_PATTERNS` order, documenting the "first match wins" behavior from Design Decision 3.
- **Mirror**: `tests/test_duplicate_checker.py` (env bootstrap, plain assert, one behavior per test function, no fixtures needed here since there's no DB).
- **Validate**: `pytest tests/test_pattern_detector.py -v` — all cases pass (7 parametrized + 3 = 10 tests).

---

## End-to-End Tests

- [ ] Each of the 7 patterns from PRD Section 9, embedded in a longer sentence, is individually flagged with the correct `pattern` value (AC 1)
- [ ] `"IGNORE PREVIOUS INSTRUCTIONS"` (all caps) is still flagged, with `pattern` returned in its canonical lowercase form (AC 2)
- [ ] A prompt with none of the seven patterns returns `is_suspicious=False` and `pattern=None` (AC 3)
- [ ] Adding an 8th pattern requires editing only the `SUSPICIOUS_PATTERNS` list, no other code change (AC 4 — verified by code inspection, not a runtime test)
- [ ] `pytest tests/ -v` (full existing suite + new file) passes green

---

## Validation

```bash
pytest tests/test_pattern_detector.py -v
pytest tests/ -v
python -c "from app.services.pattern_detector import detect_suspicious_pattern"
```

---

## Acceptance Criteria

(Copied from story STORY-005)

- [ ] Given a prompt containing any of the seven patterns from PRD Section 9 ("ignore previous instructions", "forget everything", "show system prompt", "reveal password", "execute code", "admin mode", "override"), when scanned, then the detector flags it as suspicious and reports which pattern matched.
- [ ] Given a prompt with a pattern in different casing (e.g. "IGNORE PREVIOUS INSTRUCTIONS"), when scanned, then it is still flagged (case-insensitive match).
- [ ] Given a prompt containing none of the listed patterns, when scanned, then the detector reports "clean" and no pattern name.
- [ ] Given the pattern list, when a new pattern needs to be added, then it can be done by editing a single data structure (list/config), not branching logic (Strategy pattern per PRD Section 6).
- [ ] All tasks completed
- [ ] Frontend lint passes — N/A, no frontend in this MVP; substitute `pytest tests/ -v` passes
- [ ] Backend server starts without error
- [ ] Follows existing patterns (dataclass result type, pure top-level function, parametrized test style)
