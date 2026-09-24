"""PRD-012 STORY-004: `strip_fenced_blocks`, the fence pass of PRD-011's parser, on its own.

PRD-012 Section 6.5 (D2): PII skipping under the `code` profile skips fenced
blocks and *only* fenced blocks -- an inline span is where a person points at
an address, and it must still be masked. So the fence pass of
`strip_code_spans` was extracted as a public pure function, and
`strip_code_spans` rebuilt as the inline pass over it (F3).

This module covers the new function and the rebuild. It is a new file rather
than more cases in `tests/test_pattern_matching.py` because the story's AC 4
is that PRD-011's pattern suites pass *unmodified*: they are the proof that
`strip_code_spans` did not change, and editing them would spend that proof.
Purity (no `app` import, no settings, no I/O) is already asserted over the
whole module by `test_pattern_detector_stays_a_pure_module` there, which
covers `strip_fenced_blocks` without a second copy here.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import inspect
from pathlib import Path

import pytest

import app.services.pattern_detector as pattern_detector
from app.services.pattern_detector import strip_code_spans, strip_fenced_blocks

#: Every checked-in corpus -- PII, injections, code, agent prompts. Real
#: markdown, real source and real unterminated fences, discovered from disk so
#: a new sample is covered with no test edit.
_CORPORA = Path(__file__).resolve().parent / "corpora"

_CORPUS_FILES = sorted(path for path in _CORPORA.rglob("*") if path.is_file())

_CORPUS_IDS = [path.relative_to(_CORPORA).as_posix() for path in _CORPUS_FILES]


def _read(path: Path) -> str:
    # No newline normalisation: the function sees the bytes a client would send.
    return path.read_text(encoding="utf-8")


def _assert_blanked_in_place(original: str, result: str) -> None:
    """Same length, and every character that changed became a newline.

    A copy of the helper in `tests/test_pattern_matching.py`: together the two
    conditions are what make an offset in the result an offset in the
    original, which is the property STORY-008's redactor depends on.
    """
    assert len(result) == len(original)
    for index, (before, after) in enumerate(zip(original, result)):
        assert before == after or after == "\n", (
            f"character {index}: {before!r} became {after!r}, not a newline"
        )


def _newline_offsets(text: str) -> set[int]:
    return {index for index, char in enumerate(text) if char == "\n"}


# --- AC 1: public, pure, and blanks fences ----------------------------------


def test_strip_fenced_blocks_is_public_and_pure():
    """AC 1. Public means importable by name with no leading underscore (there
    is no `__all__` in `app/`); pure means the same input gives the same
    output. The no-`app`-import half of purity is
    `test_pattern_detector_stays_a_pure_module`'s, over the whole module.
    """
    text = "prose\n```\njane@example.com\n```\nmore prose\n"

    first = strip_fenced_blocks(text)
    second = strip_fenced_blocks(text)

    assert callable(pattern_detector.strip_fenced_blocks)
    assert strip_fenced_blocks.__doc__
    assert first == second


#: Each has `before` prose, a block holding `marker`, then `after` prose --
#: except the unterminated fence, which has no after.
_FENCE_CASES = [
    "before\n```python\nmarker = 1\n```\nafter\n",
    "before\n~~~\nmarker\n~~~\nafter\n",
    "before\n   ```\nmarker\n   ```\nafter\n",
    "before\n```\nmarker\n`````\nafter\n",
    "before\n`````\nmarker\n```\nstill marker\n`````\nafter\n",
    "before\n~~~\nmarker\n```\nstill marker\n~~~\nafter\n",
    "before\n```\nmarker\nmore marker\n",
]

_FENCE_IDS = [
    "backtick-fence-with-info-string",
    "tilde-fence",
    "three-space-indented-opener",
    "longer-run-closes",
    "shorter-run-does-not-close",
    "other-character-does-not-close",
    "unterminated-runs-to-the-end",
]


@pytest.mark.parametrize("text", _FENCE_CASES, ids=_FENCE_IDS)
def test_a_fenced_block_is_blanked(text):
    """AC 1: ``` and `~~~` fences, a same-character closer at least as long,
    an unterminated fence to the end of the text -- PRD-011's rules, now owned
    by `strip_fenced_blocks`. The info string goes with the opening line.
    """
    result = strip_fenced_blocks(text)

    assert "marker" not in result
    assert "python" not in result
    assert result.startswith("before\n")
    if text.endswith("after\n"):
        assert result.endswith("\nafter\n")
    _assert_blanked_in_place(text, result)


# --- AC 1 and AC 5: inline spans are not this function's business -----------


def test_an_inline_span_outside_any_fence_is_left_intact():
    """AC 5, the story's own case, and PRD-012 Section 6.5's reason for the
    split: "send it to `ops@corp.com`" must still reach the analyzer under
    `code`, while `outside_code` pattern lists keep not seeing it.
    """
    text = "send it to `ops@corp.com` please\n"

    fenced_only = strip_fenced_blocks(text)
    both_passes = strip_code_spans(text)

    assert fenced_only == text
    assert "ops@corp.com" in fenced_only
    assert "ops@corp.com" not in both_passes
    _assert_blanked_in_place(text, both_passes)


def test_inline_spans_survive_beside_a_fence():
    """AC 1: only the fence goes. The inline spans either side keep their text
    at their original offsets, and a backtick inside the fence is blanked with
    the rest of it -- the fence pass runs first, so it can never open a span.
    """
    text = (
        "mail `ops@corp.com` first\n"
        "```java\n"
        'new User("Jane Doe", "jane@example.com"); // `tick`\n'
        "```\n"
        "then ``billing@corp.com`` too\n"
    )

    result = strip_fenced_blocks(text)

    assert "jane@example.com" not in result
    assert "tick" not in result
    for span in ("`ops@corp.com`", "``billing@corp.com``"):
        assert result.index(span) == text.index(span)
    _assert_blanked_in_place(text, result)


_IDENTITY_CASES = [
    "",
    "plain prose, no code",
    "a\n\nb",
    "only `inline` and ``double`` spans\n",
]

_IDENTITY_IDS = ["empty", "plain-prose", "blank-line", "inline-spans-only"]


@pytest.mark.parametrize("text", _IDENTITY_CASES, ids=_IDENTITY_IDS)
def test_text_with_no_fence_is_returned_unchanged(text):
    """No fence means nothing changes -- including the empty string, which must
    not raise, and a text whose only code is inline."""
    assert strip_fenced_blocks(text) == text


# --- AC 2: length and newline offsets, over every checked-in corpus ---------


@pytest.mark.parametrize("path", _CORPUS_FILES, ids=_CORPUS_IDS)
def test_blanking_preserves_length_and_every_newline_offset(path):
    """AC 2 as a property over real inputs, not a claim about hand-made ones:
    same length, every newline of the original still a newline at the same
    offset, and nothing but newlines substituted.
    """
    text = _read(path)

    result = strip_fenced_blocks(text)

    assert len(result) == len(text)
    assert _newline_offsets(text) <= _newline_offsets(result)
    _assert_blanked_in_place(text, result)


@pytest.mark.parametrize("path", _CORPUS_FILES, ids=_CORPUS_IDS)
def test_blanking_is_idempotent(path):
    """A blanked fence is only newlines, so a second pass has nothing to find."""
    once = strip_fenced_blocks(_read(path))

    assert strip_fenced_blocks(once) == once


def test_the_corpora_include_fenced_samples():
    """Guards the two properties above against passing vacuously: at least one
    corpus file must actually contain a fence the function blanks."""
    assert any(strip_fenced_blocks(_read(path)) != _read(path) for path in _CORPUS_FILES)


# --- AC 3: strip_code_spans is the inline pass over strip_fenced_blocks -----


@pytest.mark.parametrize("path", _CORPUS_FILES, ids=_CORPUS_IDS)
def test_strip_code_spans_is_the_inline_pass_over_strip_fenced_blocks(path):
    """AC 3, behaviourally: on every corpus file, the inline pass applied to
    `strip_fenced_blocks(text)` is exactly `strip_code_spans(text)`."""
    text = _read(path)

    inline_over_fenced = pattern_detector._INLINE_SPAN.sub(
        lambda span: pattern_detector._blank(span.group(0)), strip_fenced_blocks(text)
    )

    assert inline_over_fenced == strip_code_spans(text)


def test_strip_code_spans_is_built_on_strip_fenced_blocks():
    """AC 3, structurally: the fence loop lives in one place. A later copy of
    it back into `strip_code_spans` would pass the behavioural test above and
    quietly fork the parser; this fails it."""
    source = inspect.getsource(strip_code_spans)

    assert "strip_fenced_blocks(text)" in source
    assert "_FENCE_OPEN" not in source


def test_strip_code_spans_docstring_still_describes_both_passes():
    """AC 3: the docstring names both passes and says which runs first. The
    PRD-011 phrases it must also keep are asserted, unmodified, by
    `test_strip_code_spans_documents_itself_as_a_heuristic`."""
    flowed = " ".join(strip_code_spans.__doc__.split())

    assert "strip_fenced_blocks()" in flowed
    assert "fences first" in flowed.lower()
    assert "inline spans second" in flowed.lower()
