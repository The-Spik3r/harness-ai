---
story: STORY-002
prd: PRD-011
slug: word-and-regex-compilation
title: "Word-boundary and regex pattern compilation"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-011-pattern-policy        # all stories commit here, no per-story branch
created: 2026-09-22
---

# Plan: Word-boundary and regex pattern compilation

## Summary

Add three pure primitives to `app/services/pattern_detector.py` — `PatternCompileError`, `compile_pattern(pattern, match)` and `has_nested_quantifier(pattern)` — and one new test module, `tests/test_pattern_matching.py`. Nothing calls them yet: `SUSPICIOUS_PATTERNS` and `detect_suspicious_pattern` stay exactly as they are, the pipeline keeps calling the old function, and STORY-001's characterization suite keeps passing untouched. The module stays pure in the `app/models/messages.py` sense (PRD Section 6.9) — it gains only `import re`, and still imports no `settings`, reads no file and does nothing at import beyond compiling one module-level constant.

Word compilation is the PRD Section 6.2 formula verbatim: split the phrase on whitespace, `re.escape` each token, join with `\s+`, wrap in `\b...\b`, compile `re.IGNORECASE`. Regex compilation is the pattern as written under `re.IGNORECASE`, with `re.error` wrapped as `PatternCompileError`. The nested-quantifier check is a regex over the *pattern source* and is documented as a heuristic for the common catastrophic shape, per PRD 9.2 T4 — not a proof of linear-time matching.

**The one thing this story must fix outside its own files**: `tests/test_pii_dedup_isolation.py::test_dedup_and_pattern_sources_unmodified_on_this_branch` asserts by `git diff` that `app/services/pattern_detector.py` is byte-unmodified since the merge-base with `main`. It is green today and goes red the moment this story writes a line into that module. STORY-002 is the first story in the epic to touch the file, so this story owns the amendment. See Finding F-1 and Task 4.

## User Story

As a platform operator
I want patterns matched as words rather than substrings
So that ordinary vocabulary in a prompt is not reported as an injection attempt

## Story Reference

- Story file: `.agents/stories/PRD-011-pattern-policy/STORY-002-word-and-regex-compilation.md`
- PRD: `.agents/PRDs/PRD-011-pattern-policy/PRD.md` — Sections 4 (Matching), 6.2, 6.9, 7 (F1), 9.2 (T3, T4), 11 (Functional requirements), 12 Phase 1

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (additive primitives; no production caller) |
| Complexity | MEDIUM |
| Systems Affected | `app/services/pattern_detector.py` (additive only), `tests/` |
| Story | STORY-002 |
| PRD | PRD-011 |
| Epic Branch | `epic/PRD-011-pattern-policy` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` contains exactly one skill, `frontend-design`, whose `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one" (`.agents/skills/frontend-design/SKILL.md:2-3`). This story adds a pure Python module's functions and a pytest module, and touches no UI. The story frontmatter agrees (`skills: []`), its Technical Notes close with "Skills: none applicable", and the PRD says the same at Section 15, *Skills referenced*. No `SKILL.md` in the directory has a description matching this story's domain.

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

---

## Findings from Exploration

Each finding was run against the checked-out tree, not inferred.

### F-1 — A green guard test goes red as soon as this story writes into `pattern_detector.py` (blocking; not in the story's ACs)

`tests/test_pii_dedup_isolation.py:223-229`:

```python
@pytest.mark.parametrize(
    "path",
    ["app/services/pattern_detector.py"],
)
def test_dedup_and_pattern_sources_unmodified_on_this_branch(path):
    """RF-6: this epic must not touch either module -- working tree included."""
    assert _changed_since_epic_base(path) == []
```

Verified green right now: `git merge-base main HEAD` is `51e794f`, and `git diff --name-only 51e794f -- app/services/pattern_detector.py` is empty. The comment above it (`tests/test_pii_dedup_isolation.py:218-222`) explains the intent: this is **PRD-009's RF-6** guard — "pattern_detector.py is untouched by PRD-009 and stays pinned by source". PRD-011 is the epic that legitimately owns this module (PRD Section 6.8 lists it as REWRITTEN), so the guard's premise expired with PRD-009.

**It cannot simply be deleted.** `tests/test_pii_redaction_integration.py:424-445`, `test_no_pre_epic_test_function_was_removed_or_renamed`, censuses every `def test_*` name present at the merge-base across all of `tests/` and fails on any name that disappears, unless it is listed in `_DELIBERATELY_SUPERSEDED_TESTS` (`:401-421`). Removing the function name trips layer 2.

**Treatment (Task 4):** keep the function *name*, drop the source-byte pin, and replace it with the behavioural claim RF-6 actually makes — that `pattern_detector` has no PII/redaction dependency — in the exact shape `test_duplicate_checker_has_no_redaction_dependency` (`tests/test_pii_dedup_isolation.py:232-237`) already uses for the sibling module. This is the repo's own documented philosophy for a retired guard: *"what was discarded is the broken instrument, not the claim"* (`tests/test_pii_redaction_integration.py:376-378`). The `@pytest.mark.parametrize` decorator and the `path` argument go with the git-diff body; the name stays, so layer 2 stays green and `_DELIBERATELY_SUPERSEDED_TESTS` needs no new entry.

`_epic_base()` / `_changed_since_epic_base()` (`tests/test_pii_dedup_isolation.py:185-213`) become unused once that body changes — they are referenced from nowhere else in the file (`grep` confirms: definitions at `:185`, `:202`, one call at `:203`, one at `:229`). Delete both, since a dead git-subprocess helper is exactly the "broken instrument" the comment warns about. They are helpers, not `def test_*`, so layer 2 does not see them.

### F-2 — `tests/test_pii_dedup_isolation.py` is not byte-pinned, so it may be edited

`_PRE_EPIC_UNTOUCHED_TESTS` (`tests/test_pii_redaction_integration.py:279-283`) is exactly `["tests/test_admin_auth.py", "tests/test_pattern_detector.py", "tests/test_route_reservations.py"]`. `test_pii_dedup_isolation.py` is not on it, so layer 1 does not object to Task 4's edit. `tests/test_pattern_detector.py` **is** on it — which is why this story adds `tests/test_pattern_matching.py` rather than extending it, exactly as the story's Technical Notes say. (STORY-008 rewrites `test_pattern_detector.py` and will have to move it out of layer 1; noted here so that plan does not rediscover it.)

### F-3 — Every current consumer of the old API survives untouched

`grep -rn "detect_suspicious_pattern\|SUSPICIOUS_PATTERNS" --include=*.py .` finds one production caller (`app/services/query_pipeline.py:28,244`) and eight test modules (`test_duplicate_scope.py:62,75`, `test_integration.py:15,99`, `test_pii_dedup_isolation.py:30,263,289-326`, `test_query_pipeline_multiturn.py:142,175,535,541`, `test_query_router.py:354,371`, plus the two pattern suites). This story adds names and removes none, so all of them keep working — which is what "the pipeline still calls them, and STORY-001's characterization must stay green" (story Technical Notes) requires. `PatternDetectionResult` is likewise left alone.

### F-4 — The PRD Section 6.2 word formula satisfies every AC; verified by execution

Run against the checked-out interpreter, `re.compile(r"\b" + r"\s+".join(re.escape(t) for t in p.split()) + r"\b", re.IGNORECASE)`:

| Pattern | Subject | Match |
|---|---|---|
| `override` | `override`, `Override` | ✅ True (AC 1) |
| `override` | `overrides`, `overridden`, `overriding` | ❌ False (AC 1) |
| `override` | `@Override` | ✅ **True** — AC 1's explicit case |
| `ignore previous instructions` | `ignore\nprevious  instructions` | ✅ True (AC 2) |
| `ignore previous instructions` | `Ignore Previous Instructions` | ✅ True (AC 2) |
| `ignore previous instructions` | `ignoreprevious instructions` | ❌ False (AC 2) |
| `a.b` | `a.b` / `axb` | ✅ True / ❌ False (AC 3) |
| `c+d` | `c+d` / `ccd` | ✅ True / ❌ False (AC 3) |

No deviation from the PRD formula is needed. Note for STORY-001's record: `overridden` and `overriding` were already clean under the *substring* detector too (STORY-001 plan F-1) — word matching does not flip them, it agrees with today.

### F-5 — A nested-quantifier heuristic that satisfies AC 5, and what it misses

A single module-level regex over the pattern *source* clears every case AC 5 names. Verified by execution:

| Pattern | Result | Source |
|---|---|---|
| `(a+)+` | `True` | AC 5 |
| `(\w*)*` | `True` | AC 5 |
| `(x+)*y` | `True` | AC 5 |
| `overrid\w*` | `False` | AC 5 |
| `ignore\s+previous` | `False` | AC 5 |
| `(?:a+)+` | `True` | non-capturing group, same shape |
| `(a{2,})+`, `(a+){2,}` | `True` | open-ended `{n,}` counts as a quantifier |
| `ignore previous instructions` | `False` | an ordinary phrase is not refused |

Two limits, and both belong in the docstring AC 5 requires:

- **False negative:** `(a|b)+` returns `False`. Alternation-based catastrophic backtracking is a real ReDoS shape and this heuristic does not see it. This is precisely why PRD 9.2 T4 says the heuristic catches "the common shape, not a proof of linear time" and names the deliberate act of setting `PATTERNS_ALLOW_REGEX=true` as the real protection.
- **False positive:** `\(a\+\)+` — escaped *literal* parentheses — returns `True`. The check reads the source textually and does not parse the regex grammar. A false positive costs an operator one rewritten pattern at startup; a false negative costs a hung worker. Erring toward refusal is the right direction and is stated as such.

### F-6 — Repo conventions this module must follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| NAMING (compiled regex) | `app/services/reports.py:151-153,218`; `app/db/database.py:375-377,453` | Module-level, `_UPPER_SNAKE`, compiled once at import: `_FENCE = re.compile(r"^```.*?^```[^\n]*$", re.MULTILINE \| re.DOTALL)` |
| ERRORS | `app/services/authz.py:61-64,82` | `class AuthzConfigError(Exception)` with a docstring naming *who raises it and why*; message quotes the offender and appends `: {exc}`; always `raise ... from exc` |
| ERRORS (location, not value) | `app/models/messages.py:33-38,53` | `MessageNormalizationError`'s docstring: the message "names a location ... and the rule that failed, never the offending value: content is untrusted, may hold PII" |
| PURE MODULE | `app/models/messages.py:1-9` | Module docstring cites the PRD and states "Pure on purpose: no I/O, no settings, no pydantic, no `app` import" |
| TYPES | `app/models/messages.py:11-16`; `app/services/pattern_detector.py:1` | `from typing import ...` with `Literal`; no `from __future__ import annotations` in either module. `pattern_detector.py` already uses `from typing import List, Optional` |
| TESTS (prologue) | `tests/test_pattern_detector.py:1-4`; `tests/test_pattern_characterization.py:38-41` | `os.environ.setdefault("OPENROUTER_API_KEY", "test-key")` and `ADMIN_TOKEN` **before** any `app.*` import — `app/config.py` builds `Settings()` at import time |
| TESTS (shape) | `tests/test_pattern_detector.py`, `tests/test_pattern_characterization.py` | Plain `def test_*` functions, no classes. `@pytest.mark.parametrize`, with an explicit `ids=` list when cases are tuples. Comments cite the PRD section and story that own the assertion |
| TESTS (raises) | `tests/test_messages.py:129,161,168,274` | `with pytest.raises(MessageNormalizationError, match="null content"):` — `match=` is a short substring, not a full escaped regex |

### F-7 — `PatternCompileError` vs `PatternConfigError`: two types, and this story ships only one

The story is explicit: `PatternCompileError` lives in the pure module and names only the pattern; `pattern_config` (STORY-005) catches it and re-raises `PatternConfigError` with the list name attached, "because the pure module cannot know which list a pattern came from". So `PatternCompileError`'s message must **not** invent a list name or a file path, and its docstring should say who wraps it. `PatternConfigError` is not defined in this story.

### F-8 — Running the suite needs the libSQL dev server, even for a pure-unit module

`tests/conftest.py` declares `_libsql_endpoint` as `scope="session", autouse=True` and calls `pytest.exit(...)` — not `skip` — when the endpoint is unreachable. So `tests/test_pattern_matching.py`, despite importing only `app.services.pattern_detector`, cannot run without the container up. Start it per README *Running Tests* before Task 5. Per the standing note: mass fixture errors mean restart the container, not bisect the code.

---

## Patterns to Follow

### Naming — module-level compiled regex

```python
# SOURCE: app/services/reports.py:218
_FENCE = re.compile(r"^```.*?^```[^\n]*$", re.MULTILINE | re.DOTALL)
```

### Error handling — class shape, message shape, chaining

```python
# SOURCE: app/services/authz.py:61-64
class AuthzConfigError(Exception):
    """Raised by load() when RBAC_ROLES_FILE is set but unreadable,
    malformed, or grants an unrecognized permission. Startup fails rather
    than silently falling back to the built-in matrix (STORY-007)."""

# SOURCE: app/services/authz.py:82
raise AuthzConfigError(f"Failed to read RBAC_ROLES_FILE '{path_str}': {exc}") from exc
```

### Pure-module docstring

```python
# SOURCE: app/models/messages.py:1-9
"""The one internal message shape (PRD-010 Section 6.2).
...
ever sees a part list or a `None`. Pure on purpose: no I/O, no settings, no
pydantic, no `app` import. ...
"""
```

### Tests — prologue, parametrize, raises

```python
# SOURCE: tests/test_pattern_detector.py:1-11
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.services.pattern_detector import (
    SUSPICIOUS_PATTERNS,
    detect_suspicious_pattern,
)
```

```python
# SOURCE: tests/test_messages.py:129
with pytest.raises(MessageNormalizationError, match="null content"):
```

```python
# SOURCE: tests/test_pii_dedup_isolation.py:232-237  (the Task 4 target shape)
def test_duplicate_checker_has_no_redaction_dependency():
    source = inspect.getsource(duplicate_checker).lower()

    assert "pii" not in source
    assert "redact" not in source
    assert "presidio" not in source
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/pattern_detector.py` | UPDATE | Add module docstring, `import re`, `PatternCompileError`, `compile_pattern`, `has_nested_quantifier`, `_NESTED_QUANTIFIER`. Additive only — `SUSPICIOUS_PATTERNS`, `PatternDetectionResult` and `detect_suspicious_pattern` are not edited |
| `tests/test_pattern_matching.py` | CREATE | The five ACs, as parametrized cases |
| `tests/test_pii_dedup_isolation.py` | UPDATE | F-1: retire PRD-009's source-byte pin on `pattern_detector.py`, keep the function name and the RF-6 claim behaviourally |

No settings, no dependency, no schema, no database column, no README change. `requirements.txt` is untouched (`re` is stdlib; `PyYAML` belongs to STORY-005).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add the module docstring and `PatternCompileError`

- **File**: `app/services/pattern_detector.py`
- **Action**: UPDATE
- **Implement**:
  - Prepend a module docstring citing PRD-011 Sections 6.2 / 6.9 and F1, stating the module is pure on purpose — no `settings`, no file I/O, nothing read at import — and that everything reading configuration lives in `pattern_config.py` (STORY-005).
  - Add `import re` above the existing `from dataclasses import dataclass`.
  - Define `class PatternCompileError(Exception)` with a docstring saying: raised by `compile_pattern` for an empty pattern or a regex that does not compile; names the pattern and the underlying `re.error` only, because the pure module cannot know which list the pattern came from — `pattern_config.load()` (STORY-005) catches it and re-raises `PatternConfigError` with the list name attached.
  - Place the new names **after** the existing `detect_suspicious_pattern`, or in a clearly separated section below it, so the diff reads as additive and the old code's lines do not move.
- **Mirror**: `app/services/authz.py:61-64` (error class + docstring); `app/models/messages.py:1-9` (pure-module docstring)
- **Do not**: touch `SUSPICIOUS_PATTERNS`, `PatternDetectionResult` or `detect_suspicious_pattern` — story Technical Notes; STORY-008 removes them.
- **Validate**: `python -c "import app.services.pattern_detector as m; print(m.PatternCompileError, m.SUSPICIOUS_PATTERNS)"` (the module imports nothing from `app`, so no env prologue is needed).

### Task 2: Implement `compile_pattern(pattern, match)`

- **File**: `app/services/pattern_detector.py`
- **Action**: UPDATE
- **Implement**: `def compile_pattern(pattern: str, match: str) -> "re.Pattern[str]":`
  - `match == "word"`: `tokens = pattern.split()`. If `tokens` is empty (empty or whitespace-only pattern), `raise PatternCompileError` naming the rule — story Technical Notes require this rejection. Otherwise return `re.compile(r"\b" + r"\s+".join(re.escape(t) for t in tokens) + r"\b", re.IGNORECASE)`. The `re.escape` is what makes AC 3's `a.b` and `c+d` literal, and it must be applied per token *before* the `\s+` join, never to the whole phrase.
  - `match == "regex"`: return `re.compile(pattern, re.IGNORECASE)`, wrapping `re.error` as `raise PatternCompileError(f"...{pattern!r}: {exc}") from exc` — AC 4 requires the message to name **both** the pattern and the underlying `re.error` text. This arm does **not** consult `has_nested_quantifier` and does **not** consult `PATTERNS_ALLOW_REGEX`: the gate is STORY-005's, and calling it from here would require a `settings` import and break the module's purity (story Technical Notes, PRD 6.9).
  - Any other `match` value: `raise PatternCompileError` naming the unknown mode and the two valid ones. *Addition beyond the ACs*, flagged in Risks R-3 — a silent `None` return from an unknown mode would surface as a `NoneType` crash at request time in STORY-005.
  - Docstring citing PRD Section 6.2 for the formula and noting that `\b` + `\s+` is why the phrase matches across a newline.
- **Mirror**: `app/services/authz.py:82` (message + `from exc`); `app/models/messages.py:33-38` (never put untrusted content in a message — here the *pattern* is operator-authored configuration, not caller content, so quoting it is correct and is the only way STORY-005's error can name the offender)
- **Validate**: `python -c "from app.services.pattern_detector import compile_pattern as c; print(bool(c('override','word').search('@Override')), bool(c('override','word').search('overrides')), bool(c('ignore previous instructions','word').search('ignore\nprevious  instructions')))"` → `True False True`

### Task 3: Implement `has_nested_quantifier(pattern)`

- **File**: `app/services/pattern_detector.py`
- **Action**: UPDATE
- **Implement**:
  - Module-level `_NESTED_QUANTIFIER = re.compile(...)`, compiled once at import, matching a parenthesised group whose body contains a quantifier and which is itself quantified. The three alternatives verified in F-5 cover `+`/`*` inside and out, plus open-ended `{n,}` on either side.
  - `def has_nested_quantifier(pattern: str) -> bool:` returning `bool(_NESTED_QUANTIFIER.search(pattern))`.
  - **Docstring is an acceptance criterion, not decoration** (AC 5, PRD 9.2 T4). It must state: this is a heuristic for the common catastrophic-backtracking shape — a quantified group containing a quantifier — and **not** a proof of linear-time matching; it does not see alternation-based blowup such as `(a|b)+`; it reads the source textually and so refuses escaped literal parentheses such as `\(a\+\)+`; refusing a safe pattern costs one rewrite at startup, missing a dangerous one costs a hung worker, so it errs toward refusal. Name `PATTERNS_ALLOW_REGEX=false` as the real protection.
  - No caller in this story. STORY-005's loader calls it.
- **Mirror**: `app/services/reports.py:218` (module-level `_UPPER_SNAKE` compiled regex)
- **Validate**: `python -c "from app.services.pattern_detector import has_nested_quantifier as h; print([h(p) for p in ['(a+)+', r'(\w*)*', '(x+)*y', r'overrid\w*', r'ignore\s+previous']])"` → `[True, True, True, False, False]`

### Task 4: Retire PRD-009's source-byte pin on `pattern_detector.py`

- **File**: `tests/test_pii_dedup_isolation.py`
- **Action**: UPDATE
- **Implement** (F-1 — do this *before* running the suite, or Task 6 reports a failure this task already explains):
  - Keep the function **name** `test_dedup_and_pattern_sources_unmodified_on_this_branch` exactly. `tests/test_pii_redaction_integration.py:424-445` fails on a removed or renamed `def test_*`.
  - Remove the `@pytest.mark.parametrize("path", [...])` decorator and the `path` argument; replace the `assert _changed_since_epic_base(path) == []` body with the behavioural pin in the shape of `test_duplicate_checker_has_no_redaction_dependency` (`:232-237`): `source = inspect.getsource(pattern_detector).lower()`, then assert `"pii"`, `"redact"` and `"presidio"` are absent. Add `import app.services.pattern_detector as pattern_detector` beside the existing `import app.services.duplicate_checker as duplicate_checker` (`:20`); `inspect` is already imported.
  - Delete the now-unused `_epic_base()` and `_changed_since_epic_base()` helpers (`:185-213`). They are not `def test_*`, so layer 2 does not see them. Confirm nothing else calls them first: `grep -n "_epic_base\|_changed_since_epic_base" tests/test_pii_dedup_isolation.py` must show only these definitions and the one call site.
  - Rewrite the comment block above the test (`:218-222`) to cite **PRD-011** and its decision — required by PRD Section 11, *Quality indicators*: "Every modified pre-existing test carries a comment citing PRD-011 and its decision." It must say: PRD-009's RF-6 pinned this module by source because PRD-009 never touched it; PRD-011 rewrites it by design (PRD Section 6.8), so the byte pin expired with that epic, and what RF-6 actually claims — that pattern detection never sees masked text — is now pinned the same way the sibling module's is. Note that the name is kept deliberately so `test_no_pre_epic_test_function_was_removed_or_renamed` stays meaningful.
  - Do **not** add an entry to `_DELIBERATELY_SUPERSEDED_TESTS`; keeping the name means none is needed.
- **Mirror**: `tests/test_pii_dedup_isolation.py:232-237`; the retirement rationale at `tests/test_pii_redaction_integration.py:370-386`
- **Validate**: `pytest tests/test_pii_dedup_isolation.py tests/test_pii_redaction_integration.py -v`

### Task 5: Write `tests/test_pattern_matching.py`

- **File**: `tests/test_pattern_matching.py`
- **Action**: CREATE
- **Implement**: module docstring naming PRD-011 STORY-002 and stating that this module covers the *primitives only* — no policy, no profile, no config — because those arrive in STORY-005/006. Then the env prologue (F-6) and, as plain `def test_*` functions:
  - **AC 1** — parametrized: `override`/`Override` match; `overrides`/`overridden`/`overriding` do not.
  - **AC 1, the `@Override` case as its own named test**, asserting it **does** match, with a comment citing **PRD Section 6.2** in the words the story demands — `@` is a non-word character and therefore itself a word boundary; word matching does not fix this; the `code` profile not loading the keyword list is what does (STORY-005/006), and no later story may be written as though boundaries solved it. This test is the story's load-bearing one; name it so a reader cannot miss it, e.g. `test_word_boundary_does_not_fix_at_override`.
  - **AC 2** — `ignore previous instructions` against `ignore\nprevious  instructions` (newline **and** doubled space) and `Ignore Previous Instructions` → match; `ignoreprevious instructions` → no match.
  - **AC 3** — `a.b` matches `a.b` and not `axb`; `c+d` matches `c+d` and not `ccd`. Comment that `re.escape` is applied per token before the `\s+` join.
  - **AC 4** — `compile_pattern(r"overrid\w*", "regex")` returns a compiled pattern with `re.IGNORECASE` in its `.flags`, and matching is case-insensitive; `compile_pattern("(", "regex")` raises `PatternCompileError` — assert with `pytest.raises(PatternCompileError, match=...)` on a short substring, then additionally assert the raised message contains both the pattern text and a fragment of the `re.error` text (AC 4 requires both to be named; `match=` alone proves only one).
  - **Empty/whitespace pattern** — `compile_pattern("", "word")` and `compile_pattern("   ", "word")` each raise `PatternCompileError` (story Technical Notes).
  - **AC 5** — parametrized over the five cases the AC names, plus the `(?:a+)+` and `(a|b)+` rows from F-5. The `(a|b)+` row asserts `False` **with a comment stating it is a known limit of the heuristic, not a bug** — otherwise a later reader "fixes" it and the docstring's honesty quietly becomes a lie. A separate test asserts the docstring itself carries the word "heuristic" and does not claim linear time, which is how AC 5's documentation requirement is actually enforced rather than assumed.
  - **Purity** — assert `app.services.pattern_detector` names neither `settings` nor `open`: `assert "settings" not in inspect.getsource(pattern_detector)`. Cheap, and it is the one thing STORY-005 could break by accident (PRD 6.9).
  - **Old API untouched** — assert `SUSPICIOUS_PATTERNS` and `detect_suspicious_pattern` are still importable and that `detect_suspicious_pattern("please override now").pattern == "override"`. This is the story's "do not touch" clause turned into a test rather than a hope; STORY-008 deletes this case with a citing comment.
- **Mirror**: `tests/test_pattern_detector.py:1-11` (prologue), `tests/test_pattern_characterization.py` (`_CASES` + `ids=`, PRD-citing comments), `tests/test_messages.py:129` (`pytest.raises(..., match=)`)
- **Do not**: extend `tests/test_pattern_detector.py` — it is byte-pinned by layer 1 (F-2).
- **Validate**: `pytest tests/test_pattern_matching.py -v` (libSQL container up, per F-8)

### Task 6: Full suite, then commit

- **File**: —
- **Action**: verify
- **Implement**:
  - Start the libSQL dev server per README *Running Tests* if it is not up.
  - `pytest tests/ -v`. Expect green. Specifically confirm `tests/test_pattern_characterization.py` (STORY-001's pin) and `tests/test_query_outcomes_regression.py` are untouched and passing — this story changes no behaviour any of them observe.
  - `git diff --stat` must show exactly three paths: `app/services/pattern_detector.py`, `tests/test_pattern_matching.py` (new), `tests/test_pii_dedup_isolation.py`. Anything else is out of scope.
  - `git diff app/services/pattern_detector.py` must be additions only below the existing code, plus the docstring and `import re` above it — no changed line inside `detect_suspicious_pattern` or `SUSPICIOUS_PATTERNS`.
  - Commit on `epic/PRD-011-pattern-policy` (no per-story branch).
- **Validate**: `pytest tests/ -v` green; `git status` clean after commit.

---

## End-to-End Tests

There is no HTTP or UI surface in this story — nothing it adds is reachable from an endpoint until STORY-005 loads a policy and STORY-008 calls `inspect`. The end-to-end checks are therefore behavioural-invariance checks on the surfaces that already exist:

- [ ] `pytest tests/test_pattern_characterization.py -v` — green, unmodified (STORY-001's pin survives the module edit)
- [ ] `pytest tests/test_pattern_detector.py -v` — green, byte-unmodified (layer 1)
- [ ] `pytest tests/test_query_outcomes_regression.py -v` — green, no assertion changed
- [ ] `pytest tests/test_query_router.py tests/test_integration.py -v` — green, no assertion changed (PRD Section 11, *Quality indicators*)
- [ ] `pytest tests/test_pii_redaction_integration.py -v` — layers 1 and 2 green after Task 4's edit
- [ ] `pytest tests/ -v` — full suite green

## Validation

```bash
# libSQL dev server (README - Running Tests)
docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
  ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67

pytest tests/ -v

# scope check: exactly three paths
git diff --stat
git status --porcelain
```

---

## Risks + Mitigations

| # | Risk | Mitigation |
|---|---|---|
| R-1 | **The `pattern_detector.py` byte-pin fails the suite and looks like a regression.** | F-1 / Task 4 handles it explicitly and *before* the suite run. If the implementer runs the suite first, the failure message is `test_dedup_and_pattern_sources_unmodified_on_this_branch` — read Task 4, do not revert the module |
| R-2 | **Deleting the guard trips layer 2** (`test_no_pre_epic_test_function_was_removed_or_renamed`). | Task 4 keeps the function *name* and changes only its body and decorator. No `_DELIBERATELY_SUPERSEDED_TESTS` entry needed |
| R-3 | **`compile_pattern` with an unknown `match` value.** Not in any AC; the PRD's signature types it `match: str`, not a `Literal`. | Raise `PatternCompileError` rather than returning `None`. Flagged as an addition beyond the ACs. STORY-005 validates `match` against the closed vocabulary at load, so this branch should be unreachable in production — it exists so an unreachable path fails loudly |
| R-4 | **The nested-quantifier heuristic is trusted as a ReDoS proof** by a later story or the README. | AC 5's docstring requirement, enforced by a test asserting the docstring says "heuristic". PRD 9.2 T4 and STORY-013's README work both depend on this wording surviving |
| R-5 | **A pattern beginning or ending with a non-word character** (e.g. `!important`) compiles to `\b!important\b`, whose leading `\b` requires a word character immediately before the `!` — surprising, and it silently narrows a pattern rather than failing. | Out of scope for this story: no AC covers it and the built-in list has no such pattern. Recorded here for STORY-005, which is where an operator-authored file can first contain one, and for STORY-011's CSS `!important` corpus sample |
| R-6 | **`re.escape` applied to the whole phrase instead of per token** would escape the spaces and defeat the `\s+` join, breaking AC 2 while AC 1 still passes. | Task 2 states the order explicitly; AC 2's newline case is the test that catches it |
| R-7 | **The libSQL dev server degrades under repeated suite runs**, producing mass fixture errors unrelated to this change. | Restart the container; do not bisect the code. Per the standing note and PRD Section 11, *Quality indicators* |

---

## Acceptance Criteria

(Copied from story `STORY-002`)

- [ ] Given `compile_pattern(pattern, match="word")` in `app/services/pattern_detector.py`, when it compiles `override`, then the result matches `override` and `Override`, and does **not** match `overrides`, `overridden` or `overriding`. It **does** match `@Override`, and a test asserts that explicitly with a comment citing PRD Section 6.2 — word boundaries do not fix that case, and a later story must not be written as though they did.
- [ ] Given `compile_pattern("ignore previous instructions", match="word")`, when the subject is `ignore\nprevious  instructions` or `Ignore Previous Instructions`, then it matches; when the subject is `ignoreprevious instructions`, it does not.
- [ ] Given a pattern containing regex metacharacters (`a.b`, `c+d`), when compiled with `match="word"`, then the metacharacters are matched literally — the tokens are `re.escape`d before being joined with `\s+`.
- [ ] Given `compile_pattern(pattern, match="regex")`, when the pattern is valid, then it is returned compiled with `re.IGNORECASE`; when it does not compile, then `PatternCompileError` is raised naming the pattern and the underlying `re.error` text.
- [ ] Given `has_nested_quantifier(pattern)`, when the pattern is `(a+)+`, `(\w*)*` or `(x+)*y`, then it returns `True`; when it is `overrid\w*` or `ignore\s+previous`, then it returns `False`. The docstring states it is a heuristic for the common catastrophic shape, not a proof of linear-time matching (PRD 9.2 T4).
- [ ] `app/services/pattern_detector.py` stays a pure module: no `settings` import, no file I/O, nothing read at import (PRD Section 6.9)
- [ ] `detect_suspicious_pattern` and `SUSPICIOUS_PATTERNS` are unchanged; `tests/test_pattern_characterization.py` is green and unmodified
- [ ] All tasks completed
- [ ] Full suite green (`pytest tests/ -v`)
- [ ] No assertion changed in `test_query_router.py`, `test_integration.py` or `test_query_outcomes_regression.py`
- [ ] The one modified pre-existing test carries a comment citing PRD-011 and its decision
- [ ] Follows existing patterns
