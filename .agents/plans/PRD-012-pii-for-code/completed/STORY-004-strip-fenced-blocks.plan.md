---
story: STORY-004
prd: PRD-012
slug: strip-fenced-blocks
title: "Extract strip_fenced_blocks; rebuild strip_code_spans on it"
type: REFACTOR
complexity: LOW
epic_branch: epic/PRD-012-pii-for-code        # all stories commit here, no per-story branch
created: 2026-09-24
---

# Plan: Extract strip_fenced_blocks; rebuild strip_code_spans on it

## Summary

This is a pure extraction inside `app/services/pattern_detector.py`, plus one new test module.

- The fence loop in `strip_code_spans` (`app/services/pattern_detector.py:196-212`) moves verbatim into a new public, pure function, `strip_fenced_blocks(text: str) -> str`. The new function returns `"".join(out)`.
- `strip_code_spans` keeps its signature and docstring. Its body becomes the inline pass (`:214-216`) applied to `strip_fenced_blocks(text)`.
- `_FENCE_OPEN`, the closer regex, `_INLINE_SPAN` and `_blank` are not touched.
- `inspect()` keeps calling `strip_code_spans` by its module-global name.

`pii_redactor` imports `strip_fenced_blocks` in STORY-008, not in this story. The new test module, `tests/test_pattern_fenced_blocks.py`, pins four things:

- `strip_fenced_blocks` blanks fences and leaves inline spans alone. This includes AC 5's `ops@corp.com` case.
- Blanking preserves length and newline offsets, over every checked-in corpus file.
- `strip_code_spans` really is built from the new function.
- The PRD-011 suites stay green with no changes.

The equivalence was measured before this plan was written (F-1). A scratchpad copy of the extracted loop, followed by the inline pass, is byte-identical to today's `strip_code_spans` on all 36 files under `tests/corpora/`.

## User Story

As the implementer of PII fence skipping
I want the fence pass of PRD-011's code-span parser as its own pure function
So that PII can skip fenced blocks without also skipping inline spans

## Story Reference

- Story file: `.agents/stories/PRD-012-pii-for-code/STORY-004-strip-fenced-blocks.md`
- PRD: `.agents/PRDs/PRD-012-pii-for-code/PRD.md` (Sections 6.5 *Fenced-block skipping* / D2, 6.9, 7/F3, 10 *Internal API*, 11 *Functional requirements* "`strip_code_spans` behaviour unchanged")

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (story type `technical`: extraction, no behaviour change) |
| Complexity | LOW |
| Systems Affected | `app/services/pattern_detector.py` (one function split in two, module docstring); `tests/` (one new module). No other file under `app/`, `chat_ui/`, `scripts/` or `requirements*.txt` changes |
| Story | STORY-004 |
| PRD | PRD-012 |
| Epic Branch | `epic/PRD-012-pii-for-code` (commit directly on this branch; clean at `0c841cf`) |

---

## Skills In Use

None apply. `.agents/skills/` holds one skill, `frontend-design`. Its description (`.agents/skills/frontend-design/SKILL.md:3`) limits it to "visual design when building new UI or reshaping an existing one", and this story only touches a pure backend module. The story agrees (`skills: []`, "Skills: none applicable").

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

---

## Findings (measured before planning)

- **F-1: the equivalence holds on real inputs.** A scratchpad prototype copied lines 196-212 into `strip_fenced_blocks` and applied `_INLINE_SPAN.sub(...)` to its result. On all 36 files under `tests/corpora/`, 4 of which contain fences, it produced output byte-identical to `strip_code_spans`. On every file, `strip_fenced_blocks` also:
  - kept the length;
  - changed characters only to `"\n"`;
  - kept every newline at its offset;
  - returned the same text when run again on its own output.

  On `"send it to \`ops@corp.com\` please\n"`, `strip_fenced_blocks` returned the input unchanged, and `strip_code_spans` removed the address.
- **F-2: baseline suites on the untouched branch.**
  - The four suites AC 4 names, `test_pattern_matching.py`, `test_pattern_corpus.py`, `test_pattern_profiles.py` and `test_query_pipeline_patterns.py`: **195 passed**.
  - The other modules that import from or patch `pattern_detector`, `test_pattern_detector.py`, `test_pattern_config.py`, `test_pii_corpus_files.py`, `test_pattern_characterization.py` and `test_pattern_default_config_regression.py`: **142 passed**.
- **F-3: constraints that existing tests place on the refactor.**
  - `tests/test_pattern_matching.py:609-631`: the `strip_code_spans` docstring must still contain "heuristic", "unfenced source gets no protection", "@Override", "not once per pattern" and "T6". The check runs on whitespace-collapsed text, so rewrapping lines is safe but deleting sentences is not.
  - `tests/test_pattern_matching.py:303-323`: the module must stay free of `settings`, `open(`, `Path(` and any `app` import. The check reads the whole module source, so the new function is covered automatically.
  - `tests/test_pattern_detector.py:209-217`: the test patches `pattern_detector.strip_code_spans` and counts one call per message. `inspect()` (`:330`) must keep calling `strip_code_spans` by name. Do not rewrite it to call `strip_fenced_blocks`.
  - `tests/test_pii_corpus_files.py:116-117`: a comment names `_FENCE_OPEN`. The regex keeps its name, so the comment stays correct.

---

## Patterns to Follow

### Naming: section banner, `#:` constants, public = no underscore
```python
# SOURCE: app/services/pattern_detector.py:130-153
# --- PRD-011 STORY-003: code-span stripping --------------------------------

#: An opening code fence: up to three leading spaces (CommonMark's tolerance
#: ...
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})[^\n]*$", re.MULTILINE)
...
def _blank(text: str) -> str:
    """`text` with every non-newline character replaced by a newline: same
    length, same newline positions, no surviving words."""
```
There is no `__all__` anywhere in `app/`. A function is public when its name has no leading underscore. Docstrings open with a one-sentence statement of what the function returns, cite the PRD section and story, and state their limits in **bold** (`has_nested_quantifier`, `:107-127`).

### The code being moved (verbatim; nothing inside it changes)
```python
# SOURCE: app/services/pattern_detector.py:196-216
    out = []
    pos = 0
    while True:
        opening = _FENCE_OPEN.search(text, pos)
        if opening is None:
            out.append(text[pos:])
            break
        out.append(text[pos:opening.start()])
        delimiter = opening.group(1)
        closer = re.compile(
            r"^ {0,3}" + re.escape(delimiter[0]) + r"{%d,}[ \t]*$" % len(delimiter),
            re.MULTILINE,
        )
        closing = closer.search(text, opening.end())
        end = closing.end() if closing else len(text)
        out.append(_blank(text[opening.start():end]))
        pos = end

    # Second, and only now: a backtick inside a fenced block has already
    # become a newline, so it cannot open a span across unrelated text.
    return _INLINE_SPAN.sub(lambda span: _blank(span.group(0)), "".join(out))
```

### Error handling
This refactor has none. The function is total over `str`: `""` returns `""`, and an unterminated fence runs to the end of the text. There is nothing to raise, which matches the current `strip_code_spans`. Do not add input validation.

### Tests
```python
# SOURCE: tests/test_pattern_matching.py:18-34, 340-351, 404-422
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
...
def _assert_blanked_in_place(original: str, result: str) -> None:
    """AC 2 as a property of every stripping case, not one test. ..."""
    assert len(result) == len(original)
    for index, (before, after) in enumerate(zip(original, result)):
        assert before == after or after == "\n", (
            f"character {index}: {before!r} became {after!r}, not a newline"
        )
...
def test_stripping_preserves_offsets_and_does_not_fuse_the_lines_either_side():
    text = "before\n```java\n@Override\n```\nafter\n"

    result = strip_code_spans(text)

    assert len(result) == len(text)
    assert result.index("after") == text.index("after")
```
Corpus discovery from disk, as used in `tests/test_pii_corpus_files.py:47-67`: `Path(__file__).resolve().parent / "corpora"`, sorted, `read_text(encoding="utf-8")` with no newline normalisation, `ids=[path.name ...]`.

The conventions to copy:
- Module docstring naming the PRD and story.
- Act/assert layout.
- Test docstrings that cite the AC.
- Parametrized case lists with `_IDS`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/pattern_detector.py` | UPDATE | Add public `strip_fenced_blocks` holding the moved fence loop. Rebuild `strip_code_spans` as the inline pass over it. Adjust its "Two passes" paragraph and the module docstring to name the new function |
| `tests/test_pattern_fenced_blocks.py` | CREATE | AC 1, 2, 3 and 5. A new file because AC 4 forbids modifying `test_pattern_matching.py` and the other PRD-011 suites |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Extract `strip_fenced_blocks` and rebuild `strip_code_spans` on it

- **File**: `app/services/pattern_detector.py`
- **Action**: UPDATE
- **Implement**:
  1. Directly above `strip_code_spans` (after `_blank`, `:150-153`), add `def strip_fenced_blocks(text: str) -> str:`. Its body is lines `:196-212` moved **verbatim**, followed by `return "".join(out)`. Leave `_FENCE_OPEN` (`:139`) and the `closer` regex expression exactly as they are (story Technical Notes).
  2. Give it a docstring in this file's style:
     - First line: "`text` with fenced blocks blanked out and everything else, inline backtick spans included, left as it is (PRD-012 Section 6.5, D2; F3)."
     - The fence rules, moved here from `strip_code_spans`: ``` or `~~~` at the start of a line, with up to three leading spaces; the closer is the same character, at least as long, alone on its line; an unterminated fence runs to the end of the text; the opening line and its info string belong to the block.
     - The blanking invariant: `len(result) == len(text)`, newlines stay at their offsets, and only newlines are substituted.
     - Its callers: `strip_code_spans` (below) and, from PRD-012 STORY-008, `pii_redactor`. The redactor analyzes the blanked text and replaces spans in the original, which is why offsets must hold. The dependency runs one way, `pii_redactor` → here, and this module still imports nothing from `app`.
     - Its limit, in bold: **the same heuristic as `strip_code_spans`**, so indented code blocks and unfenced source are not recognised.
     - Why inline spans are left alone: an inline span is where a person points at an address ("send it to `ops@corp.com`"), so skipping it would hide real PII (PRD-012 Section 6.5).
  3. Replace the body of `strip_code_spans` with the existing two-line comment (`:214-215`) and `return _INLINE_SPAN.sub(lambda span: _blank(span.group(0)), strip_fenced_blocks(text))`.
  4. In the `strip_code_spans` docstring, edit only the "Two passes" paragraph (`:160-166`) so it reads: "Two passes. Fences first, by `strip_fenced_blocks()` …". Keep the closer rule and unterminated-fence sentences there, or a one-line summary with a pointer, so the docstring still **describes both passes** (AC 3). Keep every other paragraph word for word, because F-3 lists five phrases that `test_strip_code_spans_documents_itself_as_a_heuristic` asserts. "Its one caller is `inspect()`" remains true and stays.
  5. Module docstring (`:3-8`): add `strip_fenced_blocks` next to `strip_code_spans`. Name it as the fence pass, public for PRD-012's PII fence skipping. Rename the section banner at `:130` to `# --- PRD-011 STORY-003 / PRD-012 STORY-004: code-span stripping ---` and keep its dash padding to the same width.
  6. Do **not** touch `inspect()` (`:330`). It must keep calling `strip_code_spans` by its global name (F-3, `test_pattern_detector.py:209-217`).
- **Mirror**: `has_nested_quantifier` docstring shape (`app/services/pattern_detector.py:107-127`); `_blank` for placement and a short private helper.
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -m pytest tests/test_pattern_matching.py tests/test_pattern_corpus.py tests/test_pattern_profiles.py tests/test_query_pipeline_patterns.py -q
  ```
  Expected: `195 passed`, the F-2 baseline, with no test file modified.

### Task 2: Add `tests/test_pattern_fenced_blocks.py`

- **File**: `tests/test_pattern_fenced_blocks.py`
- **Action**: CREATE
- **Implement**: a module docstring stating "PRD-012 STORY-004: `strip_fenced_blocks`, the fence pass of PRD-011's parser, on its own", followed by the `os.environ.setdefault` preamble. Import `pytest`, `inspect`, `Path`, `app.services.pattern_detector as pattern_detector` and `strip_fenced_blocks, strip_code_spans`. Add a local `_assert_blanked_in_place` helper, a copy of `test_pattern_matching.py:340-351`. Do not import it from there, because test modules do not import from each other. Tests:
  1. `test_strip_fenced_blocks_is_public_and_pure` (AC 1): the function is importable, `callable`, has a non-empty `__doc__`, and calling it twice on the same input returns the same result without mutating anything. Purity against `app` imports is already enforced module-wide by `test_pattern_detector_stays_a_pure_module`. Do not duplicate that check; name it in the docstring.
  2. `test_a_fenced_block_is_blanked` (AC 1), parametrized with ids:
     - backtick fence with info string;
     - tilde fence;
     - opener indented three spaces;
     - longer run closes;
     - shorter run does not close;
     - other character does not close;
     - unterminated fence runs to the end.

     Each case has `before` / `after` prose and a marker word inside the block. Assert the marker is gone, the prose survives (or, for the unterminated case, `startswith("before\n")`), and `_assert_blanked_in_place`.
  3. `test_an_inline_span_outside_any_fence_is_left_intact` (AC 1, AC 5): `text = "send it to \`ops@corp.com\` please\n"`. Assert `strip_fenced_blocks(text) == text`, `"ops@corp.com" in strip_fenced_blocks(text)`, `"ops@corp.com" not in strip_code_spans(text)`, and `_assert_blanked_in_place(text, strip_code_spans(text))`.
  4. `test_inline_spans_survive_beside_a_fence` (AC 1): prose containing `` `ops@corp.com` ``, then a ```` ``` ```` block containing `jane@example.com`, then another inline span. Assert the fenced address is gone, both inline spans are byte-identical at their original offsets, and a backtick inside the fence became a newline.
  5. `test_blanking_preserves_length_and_every_newline_offset` (AC 2), parametrized over every file under `tests/corpora/` discovered from disk: sorted `rglob("*")`, files only, `ids=` relative paths. This follows `test_pii_corpus_files.py:47-67` and uses the 36 files of F-1. Assert `len(result) == len(text)`, `[i for i, c in enumerate(text) if c == "\n"]` is a subset of the newline offsets in `result`, and `_assert_blanked_in_place`.
  6. `test_blanking_is_idempotent` (AC 2), over the same files: `strip_fenced_blocks(strip_fenced_blocks(t)) == strip_fenced_blocks(t)`.
  7. `test_strip_code_spans_is_the_inline_pass_over_strip_fenced_blocks` (AC 3), over the same files. For every file, the composition matches the current function:
     ```python
     pattern_detector._INLINE_SPAN.sub(
         lambda s: pattern_detector._blank(s.group(0)), strip_fenced_blocks(t)
     ) == strip_code_spans(t)
     ```
     Also assert structurally that `"strip_fenced_blocks(text)" in inspect.getsource(strip_code_spans)`, so a later copy-paste of the loop back into `strip_code_spans` fails.
  8. `test_strip_code_spans_docstring_still_describes_both_passes` (AC 3): collapse whitespace in `strip_code_spans.__doc__`, then assert it contains `strip_fenced_blocks`, "fences first" (case-insensitive) and "inline".
  9. `test_text_with_no_fence_is_returned_unchanged`, parametrized: `""`, plain prose, `"a\n\nb"`, and a text with only inline spans. Assert `strip_fenced_blocks(t) == t`.
- **Mirror**:
  - `tests/test_pattern_matching.py:18-34` for the preamble and imports.
  - `:340-351` for the blanking helper.
  - `:371-401` for the parametrized case list with `_IDS`.
  - `tests/test_pii_corpus_files.py:47-67` for corpus discovery.
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -m pytest tests/test_pattern_fenced_blocks.py -q
  ```
  All tests should pass. As a sanity check, temporarily make the new function return `text` unchanged: tests 2, 4 and 7 should fail. Revert afterwards.

### Task 3: Regression sweep over everything that touches `pattern_detector`

- **File**: none (verification only)
- **Action**: —
- **Implement**: run the F-2 suites, the new module, and the full suite.
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -m pytest tests/test_pattern_detector.py tests/test_pattern_config.py tests/test_pii_corpus_files.py tests/test_pattern_characterization.py tests/test_pattern_default_config_regression.py -q   # expect 142 passed (F-2)
  .venv/Scripts/python.exe -m pytest -q    # full suite; needs the local libSQL dev server on :8080 (tests/conftest.py docstring)
  git diff --stat                          # only the two files in "Files to Change"
  git diff --exit-code -- tests/test_pattern_matching.py tests/test_pattern_corpus.py tests/test_pattern_profiles.py tests/test_query_pipeline_patterns.py   # AC 4: unmodified
  ```

---

## End-to-End Tests

This story has no endpoint or UI surface: the PRD's Section 10 says there is no change on any endpoint, and `inspect()` behaviour is unchanged. The end-to-end checks for `/implement` are therefore:

- [ ] `test_query_pipeline_patterns.py` passes unchanged. It drives `run_conversation` through step 5 with `outside_code` lists, so the pipeline's view of stripping is unchanged end to end.
- [ ] `test_pattern_corpus.py` passes unchanged. It runs the real injection corpus, including `direct-fenced-evasion.md`, through `inspect()`.
- [ ] A one-off REPL check, then discard it:
  ```python
  from app.services.pattern_detector import strip_fenced_blocks, strip_code_spans
  t = "mail `ops@corp.com`\n```\njane@example.com\n```\n"
  assert "ops@corp.com" in strip_fenced_blocks(t) and "jane@" not in strip_fenced_blocks(t)
  assert "ops@corp.com" not in strip_code_spans(t)
  ```

---

## Validation

```bash
.venv/Scripts/python.exe -m pytest tests/test_pattern_matching.py tests/test_pattern_corpus.py tests/test_pattern_profiles.py tests/test_query_pipeline_patterns.py -q   # 195 passed, unmodified
.venv/Scripts/python.exe -m pytest tests/test_pattern_fenced_blocks.py -q
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -c "import app.main"      # app still imports (server start smoke)
```

No linter is configured in the repo: no ruff, flake8 or pyproject config. There is no frontend change, so no frontend lint.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Behaviour drifts while moving the loop, for example `"".join` placed differently or the closer regex "tidied" | Move the lines verbatim. F-1 measured equivalence on 36 files. Task 2 test 7 re-asserts it on every build, and the 195 PRD-011 tests pin the edge cases |
| The `strip_code_spans` docstring gets trimmed and the heuristic-docstring test fails | Edit only the "Two passes" paragraph (F-3 lists the five asserted phrases) |
| `inspect()` switched to call the new function, breaking the once-per-message counting test | Task 1 step 6: `inspect()` is not touched |
| Someone reads `strip_fenced_blocks` as "safe for code" | Its docstring states the same **heuristic** limit in bold, and PRD-012 T2 / Risk 1 remain the record |

---

## Acceptance Criteria

(Copied from story `STORY-004`)

- [ ] Given `app/services/pattern_detector.py`, when it is read, then `strip_fenced_blocks(text: str) -> str` is public and pure, blanks fenced blocks (```` ``` ```` and `~~~`, same-character closer at least as long, unterminated to end of text) with newlines, and leaves inline backtick spans untouched.
- [ ] Given any text, when `strip_fenced_blocks` runs, then `len(result) == len(text)` and every newline stays at its original offset.
- [ ] Given `strip_code_spans`, when it is read, then it is the inline pass applied to `strip_fenced_blocks(text)`, and its docstring still describes both passes.
- [ ] Given PRD-011's `test_pattern_matching.py`, `test_pattern_corpus.py`, `test_pattern_profiles.py` and `test_query_pipeline_patterns.py`, when the suite runs, then they pass with no modification.
- [ ] Given a new test, when an inline span holding `ops@corp.com` sits outside any fence, then `strip_fenced_blocks` leaves it intact and `strip_code_spans` blanks it.
- [ ] All tasks completed
- [ ] Full test suite passes
- [ ] App imports without error (`python -c "import app.main"`)
- [ ] Follows existing patterns (`pattern_detector.py` docstring and banner style, `test_pattern_matching.py` test style)
