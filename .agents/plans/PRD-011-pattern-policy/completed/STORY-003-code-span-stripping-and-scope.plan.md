---
story: STORY-003
prd: PRD-011
slug: code-span-stripping-and-scope
title: "Code-span stripping and the outside_code scope"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-011-pattern-policy        # all stories commit here, no per-story branch
created: 2026-09-22
---

# Plan: Code-span stripping and the `outside_code` scope

## Summary

Add one public pure function to `app/services/pattern_detector.py` — `strip_code_spans(text) -> str` — plus the two module-level regexes and the one private blanking helper it needs, and extend `tests/test_pattern_matching.py` with the five ACs. Nothing calls it yet: `pattern_config.load()` (STORY-005) is what reads a list's `scope`, and `inspect()` (STORY-008) is what decides which of a message's two text variants each list sees. The module stays pure in the `app/models/messages.py` sense (PRD Section 6.9) — it gains no import at all, since `re` arrived with STORY-002.

The algorithm is PRD Section 6.5 verbatim, in two passes. **Pass 1, fences:** scan line-anchored for an opener of three or more backticks or tildes with up to three leading spaces, find the first closer that is a run of the *same* character at least as long, and blank the whole region from the start of the opening line through the end of the closing line — or to end of text when there is no closer. **Pass 2, inline spans:** over the already-fenced-out text, blank one-, two- or three-backtick spans that open and close within a single line. "Blank" means `re.sub(r"[^\n]", "\n", span)`: same length, every non-newline character becomes a newline. That is what keeps a match offset in the stripped text pointing at the same character of the original, and what stops the lines either side of a stripped block from fusing into one phrase.

**The one thing this story must not do** is grow an API for applying a scope. AC 5 is phrased in terms of a `scope: outside_code` list, but `PatternList` does not exist until STORY-005 and `inspect()` does not exist until STORY-008. The story's own Technical Notes settle it: *"the natural shape is for `inspect()` to compute at most two variants of a message's content — raw and stripped — and hand the right one to each list."* So AC 5 is proved in the test module with a small local helper that does exactly what `inspect()` will later do, and the production module gains `strip_code_spans` and nothing else. See Decision D-A.

## User Story

As an integrating developer
I want keyword patterns not to fire on text inside code fences
So that pasting a diff into a prompt is not read as an attack

## Story Reference

- Story file: `.agents/stories/PRD-011-pattern-policy/STORY-003-code-span-stripping-and-scope.md`
- PRD: `.agents/PRDs/PRD-011-pattern-policy/PRD.md` — Sections 4 (Matching), 6.2, 6.5 (D3), 6.9, 7 (F2), 9.2 (T6), 11 (Functional requirements), 14 (Risk 8), 12 Phase 1

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (additive pure function; no production caller) |
| Complexity | MEDIUM |
| Systems Affected | `app/services/pattern_detector.py` (additive only), `tests/` |
| Story | STORY-003 |
| PRD | PRD-011 |
| Epic Branch | `epic/PRD-011-pattern-policy` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` contains exactly one skill, `frontend-design`, whose `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one" (`.agents/skills/frontend-design/SKILL.md:2-3`). This story adds one pure function and pytest cases, and touches no UI. The story frontmatter agrees (`skills: []`), its Technical Notes close with "Skills: none applicable", and the PRD says the same at Section 15, *Skills referenced*. No `SKILL.md` in the directory has a description matching this story's domain.

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

---

## Findings from Exploration

Each finding was run against the checked-out tree, not inferred.

### F-1 — STORY-002 already cleared the way; `pattern_detector.py` is freely editable

`tests/test_pii_dedup_isolation.py:207-215` is the retired PRD-009 byte pin. It now reads `source = inspect.getsource(pattern_detector).lower()` and asserts only that `"pii"`, `"redact"` and `"presidio"` are absent. So this story may edit the module without touching that test — **provided the new code and its docstrings contain none of those three substrings.** That is a live constraint, not a formality: a docstring sentence like "this does not redact anything" would turn the guard red. Prefer **strip** and **blank** throughout.

### F-2 — `tests/test_pattern_matching.py` may be extended; `tests/test_pattern_detector.py` may not

`_PRE_EPIC_UNTOUCHED_TESTS` (`tests/test_pii_redaction_integration.py:279-283`) is exactly `["tests/test_admin_auth.py", "tests/test_pattern_detector.py", "tests/test_route_reservations.py"]`, enforced at `:334-340`. `tests/test_pattern_matching.py` was created by STORY-002 and is on no pin, which is why the story's Technical Notes say "Tests extend `tests/test_pattern_matching.py`". Layer 2 (`test_no_pre_epic_test_function_was_removed_or_renamed`, `tests/test_pii_redaction_integration.py:424-445`) only fails on *removed* names; this story adds names and removes none.

### F-3 — There is an existing `_FENCE` in the repo, and it is the wrong instrument

`app/services/reports.py:218` — `_FENCE = re.compile(r"^```.*?^```[^\n]*$", re.MULTILINE | re.DOTALL)`, used at `:224` as `_FENCE.sub("", section)`. It **deletes** the span rather than blanking it, handles backticks only (no `~~~`), has no three-space tolerance, does not require the closer to be at least as long as the opener, and silently matches nothing when a fence is unterminated — the opposite of AC 4. It is right for its job (dropping fences out of report prose) and wrong for this one. Do not import it, do not generalize it, do not touch `reports.py`. It is cited here only as the **naming precedent**: module-level `_UPPER_SNAKE`, compiled once at import.

### F-4 — Today's detector matches inside a fence, and STORY-001 pinned it

`tests/test_pattern_characterization.py:102-104,126,149` already carries the case `"Here is the diff:\n```java\n@Override\npublic void run() {}\n```\n"` → `"override"`, under the id `fenced-at-override`. That row is the "before" this story writes the "after" for, and it must stay green — this story changes no behaviour of `detect_suspicious_pattern`. Cite it in the new test section so a reader can find the pair.

### F-5 — The two-pass algorithm satisfies every AC; verified by execution

Prototype run against the checked-out interpreter. The invariant `len(result) == len(text)` and "every differing character is a newline" held on every row.

| Input | Result | AC |
|---|---|---|
| ` ```java ` … ` ``` ` between prose | fence blanked, prose either side identical | AC 1 |
| `~~~`-fenced block | blanked | AC 1 |
| Fence opened with three leading spaces | blanked (CommonMark tolerance) | AC 1, Technical Notes |
| ` ```python override ` info string | the opening line, info string and all, is blanked | AC 1, Technical Notes |
| Any of the above | `len(result) == len(text)`, non-newline chars → newline | AC 2 |
| `` `override` `` | blanked | AC 3 |
| ``` ``a `b` c`` ``` | blanked whole, inner single backticks included | AC 3 |
| A triple-backtick span inline on one line | blanked | AC 3 |
| `a lone ` backtick override` | **unchanged**, no exception | AC 3 |
| ` ``` ` opened, never closed | blanked to end of text | AC 4 |
| Opener ` ``` `, closer ` ````` ` (longer) | closes — "at least as long" | Technical Notes |
| Opener ` ````` `, closer ` ``` ` (shorter) | does **not** close; scanning continues | Technical Notes |
| `~~~` opened, ` ``` ` inside | does not close; the backticks are inside the tilde block | Technical Notes |
| A backtick inside a fenced block | never opens an inline span — pass 2 runs on already-blanked text | Technical Notes |
| `""`, `"plain override text"`, `"a\n\nb"` | returned identical | — |

AC 5, by execution, using `\boverride\b` and the helper of Decision D-A:

| Text | `everywhere` first hit | `outside_code` first hit |
|---|---|---|
| `override outside` then a fenced `override inside` | offset 0 (outside) | offset 0 (outside) |
| A fenced `override inside` **then** `override outside` | offset 4 (**inside the fence**) | offset 24 (outside) |

The second row is the one that proves both halves of AC 5 at once: `everywhere` reports the first hit in text order, fence or not; `outside_code` reports only the outside one. T6, the same way: a fenced `ignore previous instructions` matches under `everywhere` and not under `outside_code`, which is exactly why the injection list carries `scope: everywhere` (PRD 9.2 T6).

### F-6 — Cost is linear, and the pathological shapes are cheap

Measured on the checked-out interpreter:

| Input | Size | Time |
|---|---|---|
| 100,000 backticks on one line | 100 KB | 0.005 s |
| Unterminated fence over 12,000 lines | 108 KB | 0.005 s |
| Plain prose, no code at all | 101 KB | 0.001 s |
| 1,000 tiny inline spans | 6 KB | 0.001 s |

Both regexes are a simple star with no nested quantifier, so there is no backtracking blowup to guard against. `PATTERN_MAX_SCAN_CHARACTERS` (STORY-004) is a backstop for the *match* pass and is not this function's concern. These numbers are the first input to PRD Section 11's "inspection cost measured at the ceiling" — record them in this story's report so STORY-011 does not have to rediscover them.

### F-7 — A property worth knowing before STORY-008: blanking lets a phrase span a stripped block

`strip_code_spans("ignore previous `x` instructions")` blanks the inline span to newlines, and STORY-002's word formula joins tokens with `\s+`, which newlines satisfy. So the phrase **does** match across the blanked span. The same is true across a whole fenced block.

This is the correct direction and should not be "fixed": it means wrapping the middle word of an injection phrase in backticks is not an evasion, which is the same instinct PRD 9.2 T6 applies to whole phrases. It is recorded here, and asserted in one test, so that a later reader meets it as a decision rather than as a surprise. The alternative — replacing the span with a character that breaks a phrase — would break AC 2's offset invariant and is not on the table.

### F-8 — Repo conventions this function must follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| NAMING (compiled regex) | `app/services/reports.py:151-153,218`; `app/db/database.py:375-377` | Module-level, `_UPPER_SNAKE`, compiled once at import |
| NAMING (private helper) | `app/services/reports.py:205,210,224` | `_plain`, `_section`, `_paragraphs` — leading underscore, one-line docstring |
| PURE MODULE | `app/models/messages.py:1-9`; `app/services/pattern_detector.py:1-21` | Docstring cites the PRD and states "Pure on purpose: no I/O, no settings, no pydantic, no `app` import" |
| DOCSTRING (honest limits) | `app/services/pattern_detector.py:129-155` (`has_nested_quantifier`) | The limits are stated in the docstring **and asserted by a test** — the shape this story's docstring requirement must copy |
| TYPES | `app/services/pattern_detector.py:23` | `from typing import List, Optional`; no `from __future__ import annotations` |
| TESTS (prologue) | `tests/test_pattern_matching.py:17-20` | `os.environ.setdefault("OPENROUTER_API_KEY", ...)` / `ADMIN_TOKEN` before any `app.*` import |
| TESTS (shape) | `tests/test_pattern_matching.py` throughout | Plain `def test_*`, no classes; `@pytest.mark.parametrize` with an explicit `ids=` list; section banner comments `# --- AC N: ... ---`; comments cite the PRD section that owns the assertion |
| TESTS (docstring-as-AC) | `tests/test_pattern_matching.py::test_the_heuristic_documents_itself_as_a_heuristic` | A documentation AC is enforced by asserting on `__doc__`, not assumed |

### F-9 — The suite needs the libSQL dev server even for a pure-unit module

`tests/conftest.py:132-152` declares `_libsql_endpoint` as `scope="session", autouse=True` and calls `pytest.exit(...)` — not `skip` — when the endpoint is unreachable. Start the container (README *Running Tests*, `README.md:615-616`) before Task 4. Per the standing note: mass fixture errors mean restart the container, not bisect the code.

---

## Design Decisions

### D-A — This story ships `strip_code_spans` and no scope-applying API

AC 5 talks about matching "against a `scope: outside_code` list", but a `PatternList` with a `scope` field is STORY-005's and the two-variant choice is STORY-008's. Three options were considered:

| Option | Verdict |
|---|---|
| Ship `strip_code_spans` only; prove AC 5 in the test module with a local helper that picks raw-or-stripped text | **Chosen.** It is exactly what PRD Section 10's internal API lists for this module (`strip_code_spans(text) -> str`, nothing else), and it is what the story's Technical Notes describe as "the natural shape" |
| Also ship a public `text_for_scope(text, scope)` | Rejected: a second public name with no caller, which STORY-008 would then have to either adopt or delete. PRD Section 10 does not list it |
| Also ship a memoizing per-message cache ("once per scope, not once per pattern", PRD Risk 8) | Rejected: the cache belongs where the message walk is, which is `inspect()` in STORY-008. Caching here would need state in a module the PRD requires to be pure |

The test helper is deliberately four lines and named so its successor is obvious — `_scoped_text(text, scope)` with a comment pointing at STORY-008. **PRD Risk 8's "once per message per scope" is a constraint this story hands forward, not one it can satisfy** — recorded in Task 2's docstring and in this story's report so STORY-008's plan inherits it rather than rediscovering it.

### D-B — Blank the delimiters too, not just the contents

AC 3 says "their contents are stripped". The prototype blanks the entire matched span, delimiters included. Both satisfy the letter of the AC and both preserve length; blanking the whole span is chosen because leaving the backticks behind would leave stray backtick characters in the stripped text where a later reader of a debug dump would have to work out why. Nothing in the ACs, the PRD or STORY-008 depends on the delimiters surviving.

### D-C — Indented code blocks (four spaces, no fence) are not stripped

CommonMark's other code construct is the four-space-indented block. It is **not** handled: the story defines fence detection as three-or-more backticks or tildes with up to three leading spaces. A four-space-indented block keeps its text, and `override` inside one is still a hit under `outside_code`. This is the same limit as the story's "unfenced source gets no protection" sentence and belongs in the same docstring sentence — it is not a defect to fix here. (Incidental, verified: on a four-space-indented line of three backticks, pass 2 pairs the first two backticks as a degenerate empty inline span and blanks them. Length is preserved, no exception is raised, and no match is created or destroyed. Not worth code to prevent; worth not being surprised by.)

---

## Patterns to Follow

### Naming — module-level compiled regex

```python
# SOURCE: app/services/reports.py:218
_FENCE = re.compile(r"^```.*?^```[^\n]*$", re.MULTILINE | re.DOTALL)
```

### Docstring — an honest limit, stated and then asserted

```python
# SOURCE: app/services/pattern_detector.py:129-142 (has_nested_quantifier)
    """...
    **A heuristic for the common shape, not a proof of linear-time matching.**
    It reads the pattern as text and does not parse the regex grammar, so:
    ...
    Both directions are deliberate. A false positive costs an operator one
    rewritten pattern at startup; a false negative costs a hung worker, so the
    check errs toward refusal."""
```

### Tests — prologue, parametrize with ids, PRD-citing comments

```python
# SOURCE: tests/test_pattern_matching.py:17-33
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.services.pattern_detector import (
    compile_pattern,
    ...
)
```

```python
# SOURCE: tests/test_pattern_matching.py (the AC-1 block)
_OVERRIDE_IDS = [f"{subject}-{'match' if hit else 'clean'}" for subject, hit in _OVERRIDE_CASES]


@pytest.mark.parametrize("subject,expected", _OVERRIDE_CASES, ids=_OVERRIDE_IDS)
def test_word_match_is_case_insensitive_and_suffix_safe(subject, expected):
```

### Tests — the guard this module must not trip

```python
# SOURCE: tests/test_pii_dedup_isolation.py:207-215
def test_dedup_and_pattern_sources_unmodified_on_this_branch():
    source = inspect.getsource(pattern_detector).lower()

    assert "pii" not in source
    assert "redact" not in source
    assert "presidio" not in source
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/pattern_detector.py` | UPDATE | Add `_FENCE_OPEN`, `_INLINE_SPAN`, `_blank`, `strip_code_spans`. Additive only — `SUSPICIOUS_PATTERNS`, `PatternDetectionResult`, `detect_suspicious_pattern`, `PatternCompileError`, `compile_pattern` and `has_nested_quantifier` are not edited |
| `tests/test_pattern_matching.py` | UPDATE | Append the five ACs as a new section; the STORY-002 sections above are not touched, beyond one import line and the module docstring's opening line |

No settings, no dependency, no schema, no database column, no README change, no new test module. `requirements.txt` untouched (`re` is stdlib). `app/services/reports.py` untouched (F-3).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add the two regexes and `_blank`

- **File**: `app/services/pattern_detector.py`
- **Action**: UPDATE
- **Implement**: a new section below STORY-002's, opened with a banner comment in the file's existing style, e.g. `# --- PRD-011 STORY-003: code-span stripping ---`.
  - `_FENCE_OPEN` — the opening fence: `re.MULTILINE`, `^`, up to three leading spaces, then a captured run of three-or-more backticks **or** three-or-more tildes, then the rest of the line. The trailing `[^\n]*` swallows the info string so the whole opening line belongs to the span. A comment must say why the info string is included (story Technical Notes) and why this is `re.MULTILINE` and not `re.DOTALL` — the scan is line-based.
  - `_INLINE_SPAN` — one, two or three backticks opening and closing within a single line: a captured delimiter run, then a body of non-newline characters that does not itself start with the delimiter run, then the same run again. The "does not start with the delimiter" lookahead is what lets a double-backtick span keep its inner single backticks in the body; the non-newline body class is what stops a span crossing a line. Comment both.
  - `def _blank(text: str) -> str:` → `return re.sub(r"[^\n]", "\n", text)`, one-line docstring: same length, every non-newline character becomes a newline.
  - Do **not** add a module-level closer regex: the closer depends on the opener's character and length and is built per fence inside `strip_code_spans` (Task 2). `re.compile` consults `re`'s own cache, so the repeated build is not a per-call compile.
- **Mirror**: `app/services/reports.py:218` (module-level `_UPPER_SNAKE`), `app/services/reports.py:205-210` (`_plain` shape)
- **Do not**: import or reuse `reports._FENCE` (F-3); use the words `pii`, `redact` or `presidio` anywhere in the new code or comments (F-1).
- **Validate**: `python -c "import app.services.pattern_detector as m; print(repr(m._blank('ab\ncd')))"` → `'\n\n\n\n\n'` (length 5, the original newline in place).

### Task 2: Implement `strip_code_spans(text)`

- **File**: `app/services/pattern_detector.py`
- **Action**: UPDATE
- **Implement**: `def strip_code_spans(text: str) -> str:`
  - **Pass 1 — fences.** Walk with `_FENCE_OPEN.search(text, pos)`. For each opener: append `text[pos:match.start()]` unchanged; take the captured delimiter, and build the closer as `re.MULTILINE`, `^`, up to three leading spaces, `re.escape(delim[0])` repeated `{len(delim),}`, then only spaces or tabs to end of line — **same character, at least as long**. Search it from `match.end()`. Append `_blank(text[match.start():end])`, where `end` is the closer's `end()` or `len(text)` when there is no closer (AC 4). Set `pos = end` and continue. When no opener is left, append the remainder and stop.
  - **Pass 2 — inline spans.** `return _INLINE_SPAN.sub(lambda m: _blank(m.group(0)), joined)` over pass 1's output. Running it second is what makes a backtick inside a fenced block unable to open a span (story Technical Notes); a comment must say so, because the ordering is not self-evident and swapping the passes would still pass most of the tests.
  - **Docstring** — it is an acceptance criterion (story Technical Notes: "the docstring must say so"), so write it as carefully as `has_nested_quantifier`'s:
    - what it does: fenced blocks and inline backtick spans are blanked, each non-newline character becoming a newline, so `len` is preserved and a match offset still points at the same character of the original;
    - that it is **a heuristic**, and that **unfenced source gets no protection from it** — which is why the `code` profile's answer to `@Override` is not to rely on stripping but to not load the keyword list at all (PRD Section 6.5). Write that sentence for the reader who is deciding whether `tool` turns are safe, and do not oversell it;
    - the four-space-indented block limit (D-C);
    - that the caller strips **once per message per scope requested, not once per pattern** (PRD 7/F2, PRD Risk 8) — the constraint this story hands to STORY-008 (D-A);
    - that `scope: everywhere` lists are never passed through this at all, which is what stops a fence being an evasion (PRD 9.2 T6).
  - Place the whole section **below** `has_nested_quantifier` so the diff is additive and no existing line moves.
- **Mirror**: `app/services/pattern_detector.py:129-155` (a docstring that states its own limits), `app/services/reports.py:224` (fence-aware scanning)
- **Do not**: touch any existing function; add a `scope` parameter or a public `text_for_scope` helper (D-A).
- **Validate**: with the libSQL container not needed (pure module), run a short script asserting: a fenced `@Override` between `before` / `after` comes back with `len` unchanged, `Override` gone, and both prose words intact; `"a lone ` backtick override"` comes back `==` itself; an unterminated fence removes `override`; `strip_code_spans("")` is `""`.

### Task 3: Extend `tests/test_pattern_matching.py` with the five ACs

- **File**: `tests/test_pattern_matching.py`
- **Action**: UPDATE
- **Implement**: append a new section below the STORY-002 sections, opened `# --- PRD-011 STORY-003: code-span stripping ---`, and add `strip_code_spans` to the existing `from app.services.pattern_detector import (...)` block. Amend the module docstring's opening line so it names STORY-002 **and** STORY-003 — it currently reads "PRD-011 STORY-002: the compilation primitives, on their own", which stops being true. Then, as plain `def test_*` functions:
  - **A shared invariant helper**, used by every stripping test: assert `len(result) == len(text)` and that every character that differs from the original is a newline. AC 2 is not one test, it is a property of all of them.
  - **AC 1** — parametrized over fence shapes: backtick-fenced, tilde-fenced, an opener with three leading spaces, and an opener carrying an info string. Each asserts the fenced word is gone and the prose either side is returned byte-identical. `ids=` per F-8.
  - **AC 2** — its own named test on the offset invariant: take a text with a fence, strip it, and assert `len` is equal, that `result.index("after")` equals `text.index("after")`, and that the two lines either side of the block are still separated by newlines and did not fuse. Comment citing PRD Section 6.5.
  - **AC 3** — parametrized over a single-backtick span, a double-backtick span containing single backticks, a triple-backtick inline span, and — the important row — `"a lone ` backtick override"`, which must come back **unchanged** with no exception. Give that row an id that says so, e.g. `lone-backtick-unchanged`.
  - **AC 4** — unterminated fence strips to end of text; plus the two closer-length rows from F-5 (a longer closer closes, a shorter one does not) and the mismatched-character row (backticks do not close a tilde fence), each with a comment citing the story's Technical Notes.
  - **AC 5** — the pair of assertions this story exists for. Define the four-line local helper of D-A:
    ```python
    def _scoped_text(text: str, scope: str) -> str:
        """What inspect() will do per message per scope in STORY-008 (D-A)."""
        return strip_code_spans(text) if scope == "outside_code" else text
    ```
    Then, over a text whose **fenced** `override` comes first and whose outside `override` comes second — so the assertion cannot pass by accident — assert that under `outside_code` the only hit is the outside one at the offset F-5 records, and that under `everywhere` the first hit in text order is the fenced one. Comment that the helper is a stand-in for `inspect()` and name the story that replaces it.
  - **T6, named for the threat** (the story's Technical Notes make this explicit): a test named for the fence-as-evasion threat, e.g. `test_a_fence_is_not_an_evasion_for_the_injection_list`, showing `ignore previous instructions` inside a fence still matching under `everywhere`, with a comment citing PRD 9.2 T6 and PRD 6.3's reason the injection list carries that scope.
  - **F-7's property**, asserted once with its reasoning in the docstring: a phrase matches across a blanked inline span, because blanking leaves whitespace and the word formula joins tokens with `\s+`. State that this is the intended direction, not a leak.
  - **The docstring is an AC** — assert `strip_code_spans.__doc__` contains "heuristic" and says unfenced source gets no protection, in the shape `test_the_heuristic_documents_itself_as_a_heuristic` already uses (F-8). Without this, the story's "the docstring must say so" is a hope.
  - **No-code text is identity** — `""`, plain prose and `"a\n\nb"` come back `==` the input.
  - **STORY-001's pin is referenced, not duplicated**: one comment pointing at `tests/test_pattern_characterization.py:104` (`fenced-at-override`) as the "before" this section is the "after" for. Do not re-assert it here.
- **Mirror**: the STORY-002 sections of `tests/test_pattern_matching.py` throughout; `tests/test_messages.py:129` for any `pytest.raises` shape
- **Do not**: extend `tests/test_pattern_detector.py` (byte-pinned, F-2); create a new test module — the story says extend this one.
- **Validate**: `pytest tests/test_pattern_matching.py -v` (libSQL container up, per F-9)

### Task 4: Full suite, then commit

- **File**: —
- **Action**: verify
- **Implement**:
  - Start the libSQL dev server per README *Running Tests* (`README.md:615-616`) if it is not up.
  - `pytest tests/ -v`. Expect green. Confirm specifically that `tests/test_pattern_characterization.py` (STORY-001's pin, including `fenced-at-override`) and `tests/test_pii_dedup_isolation.py` (F-1's guard) pass untouched.
  - `git diff --stat` must show exactly two paths: `app/services/pattern_detector.py` and `tests/test_pattern_matching.py`. Anything else is out of scope.
  - `git diff app/services/pattern_detector.py` must be additions only, below `has_nested_quantifier` — no changed line in any existing function.
  - `grep -niE "pii|redact|presidio" app/services/pattern_detector.py` must print nothing (F-1).
  - Record F-6's timing numbers in the story's report (PRD Section 11, *Quality indicators*), and carry D-A's forward constraint into it so STORY-008 inherits it.
  - Commit on `epic/PRD-011-pattern-policy` (no per-story branch).
- **Validate**: `pytest tests/ -v` green; `git status` clean after commit.

---

## End-to-End Tests

There is no HTTP or UI surface in this story — `strip_code_spans` is unreachable from an endpoint until STORY-005 loads a policy carrying a `scope` and STORY-008 calls it. The end-to-end checks are therefore behavioural-invariance checks on the surfaces that already exist:

- [ ] `pytest tests/test_pattern_matching.py -v` — green, STORY-002's cases included and unchanged in behaviour
- [ ] `pytest tests/test_pattern_characterization.py -v` — green, unmodified; `fenced-at-override` still reports `override` (this story changes no behaviour of the old detector)
- [ ] `pytest tests/test_pattern_detector.py -v` — green, byte-unmodified (layer 1)
- [ ] `pytest tests/test_pii_dedup_isolation.py tests/test_pii_redaction_integration.py -v` — green; the F-1 guard passes on the edited module
- [ ] `pytest tests/test_query_outcomes_regression.py tests/test_query_router.py tests/test_integration.py -v` — green, no assertion changed
- [ ] `pytest tests/ -v` — full suite green

## Validation

```bash
# libSQL dev server (README - Running Tests)
docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
  ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67

pytest tests/ -v

# the module must still carry no redaction dependency (F-1)
grep -niE "pii|redact|presidio" app/services/pattern_detector.py   # expect no output

# scope check: exactly two paths
git diff --stat
git status --porcelain
```

---

## Risks + Mitigations

| # | Risk | Mitigation |
|---|---|---|
| R-1 | **A docstring sentence trips the F-1 guard.** The retired PRD-009 pin now asserts `"pii"`, `"redact"` and `"presidio"` are absent from the module's *source*, docstrings included. "This does not redact code" would turn it red. | Task 1's *Do not*, and the `grep -niE` line in Validation. Use **strip** and **blank** |
| R-2 | **The two passes get swapped.** Running inline-span stripping first would let a backtick inside a fenced block open a span across unrelated text, and most tests would still pass. | Task 2 requires a comment stating the ordering and why; the F-5 row "a backtick inside a fenced block" is the test that catches it |
| R-3 | **The span is deleted rather than blanked** — the obvious `sub("")`. It passes the "the word is gone" tests and breaks AC 2's offset invariant silently, which only surfaces in STORY-008 when a reported offset points at the wrong character. | The shared length/newline invariant helper in Task 3 runs on every stripping test, not just AC 2's |
| R-4 | **The closer is matched loosely** — any run of three backticks, ignoring the opener's character and length. A tilde fence would then be closed by backticks, and a five-backtick block by a three-backtick line inside it. | Task 2 builds the closer from the opener's character and length; three F-5 rows cover it |
| R-5 | **An unterminated fence is treated as no fence.** `reports._FENCE` does exactly this (F-3), so a reader borrowing it would ship the opposite of AC 4. | F-3 says not to borrow it; AC 4 has its own test |
| R-6 | **Someone adds a `scope` parameter or a public `text_for_scope`**, and STORY-008 inherits an API the PRD does not list. | D-A, Task 2's *Do not*, and the test-local helper that makes the successor obvious |
| R-7 | **F-7's cross-span phrase matching is later read as a leak** and "fixed" with a separator character, breaking AC 2. | F-7 is asserted as a test with its reasoning in the docstring, so the behaviour is met as a decision |
| R-8 | **Stripping ends up called once per pattern** rather than once per message per scope (PRD Risk 8). This story cannot prevent it — it has no message walk. | Stated in the `strip_code_spans` docstring and carried into the report, so STORY-008's plan inherits the constraint (D-A) |
| R-9 | **The libSQL dev server degrades under repeated suite runs**, producing mass fixture errors unrelated to this change. | Restart the container; do not bisect the code. Per the standing note and PRD Section 11, *Quality indicators* |

---

## Acceptance Criteria

(Copied from story `STORY-003`)

- [ ] Given `strip_code_spans(text)` in `app/services/pattern_detector.py`, when the text contains a backtick-fenced or `~~~`-fenced block opening at the start of a line, then that block's content is replaced and the surrounding text is returned unchanged.
- [ ] Given a stripped span, when the result is compared with the input, then `len(result) == len(text)` and every non-newline character of the span has become a newline — so a match offset in the stripped text still points at the same character in the original, and the lines either side of a stripped block cannot fuse into one phrase.
- [ ] Given inline spans, when the text contains a single-, double- or triple-backtick span, then their contents are stripped; given a lone unmatched backtick, then nothing is stripped and no exception is raised.
- [ ] Given an unterminated fence, when the text opens a fence and never closes it, then everything from the fence to the end of the text is stripped.
- [ ] Given `override` inside a fence and `override` outside it in the same text, when matched against a `scope: outside_code` list, then only the outside hit is reported; when matched against a `scope: everywhere` list, then the first hit in text order is reported, fence or not.
- [ ] The `strip_code_spans` docstring states that it is a heuristic and that unfenced source gets no protection from it (story Technical Notes), and a test asserts that wording
- [ ] A test named for PRD 9.2 T6 shows a fenced `ignore previous instructions` still matching under `scope: everywhere`
- [ ] `app/services/pattern_detector.py` stays a pure module: no `settings` import, no file I/O, nothing read at import (PRD Section 6.9)
- [ ] `SUSPICIOUS_PATTERNS`, `detect_suspicious_pattern`, `compile_pattern` and `has_nested_quantifier` are unchanged; `tests/test_pattern_characterization.py` is green and unmodified
- [ ] All tasks completed
- [ ] Full suite green (`pytest tests/ -v`)
- [ ] No assertion changed in `test_query_router.py`, `test_integration.py` or `test_query_outcomes_regression.py`
- [ ] Follows existing patterns
