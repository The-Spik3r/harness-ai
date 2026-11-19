"""PRD-021 STORY-007: the Segmenter (PRD-021 6.5) -- boundaries, forced cut, fences.

No Presidio and no `pii_redactor` import here: the segmenter is pure. The only
other module touched is pattern_detector, whose strip_fenced_blocks() the fence
tracking is pinned to by a differential test.
"""

import ast
import itertools
import pathlib
import re

import pytest

from app.services.pattern_detector import strip_fenced_blocks
from app.services.stream_redaction import Segmenter

_SRC = pathlib.Path(__file__).resolve().parent.parent / "app" / "services" / "stream_redaction.py"


def _run(kind, text, holdback_max=1000, skip_fenced=False, splits=()):
    """Push `text` cut at `splits` (offsets), flush, and return the segments."""
    segmenter = Segmenter(kind, holdback_max, skip_fenced)
    out = []
    previous = 0
    for offset in (*splits, len(text)):
        out.extend(segmenter.push(text[previous:offset]))
        previous = offset
    out.extend(segmenter.flush())
    return out


def _texts(segments):
    return [segment.text for segment in segments]


@pytest.mark.parametrize("terminator", [".", "?", "!", "…"])
def test_chat_cuts_after_terminator_and_whitespace(terminator):
    text = f"One thing{terminator} Another thing{terminator} Last"
    assert _texts(_run("chat", text)) == [f"One thing{terminator} ", f"Another thing{terminator} ", "Last"]


def test_chat_cuts_at_newline():
    assert _texts(_run("chat", "line one\nline two\n\nx")) == ["line one\n", "line two\n", "\n", "x"]


def test_chat_terminator_at_buffer_end_waits():
    segmenter = Segmenter("chat", 1000)
    assert segmenter.push("Hello world.") == []
    assert _texts(segmenter.push(" Next")) == ["Hello world. "]
    assert _texts(segmenter.flush()) == ["Next"]


@pytest.mark.parametrize("text", ["It costs 3.5 euros total", "mail a.b@c.com.au now", "version 1.2.3 is out"])
def test_chat_mid_word_terminators_do_not_cut(text):
    assert _texts(_run("chat", text)) == [text]


def test_chat_ellipsis_cuts_once_at_the_end_of_the_run():
    assert _texts(_run("chat", "Well... maybe so. Okay")) == ["Well... ", "maybe so. ", "Okay"]


_SPLIT_TEXTS = [
    "First one. Second? Third!\nFourth… 5.5 is a number. a.b@c.com. End",
    "line a\nline b\r\nline c",
]


@pytest.mark.parametrize("kind", ["chat", "code"])
def test_every_two_way_and_three_way_split_gives_the_same_segments(kind):
    for text in _SPLIT_TEXTS:
        expected = _run(kind, text)
        offsets = range(len(text) + 1)
        for a in offsets:
            assert _run(kind, text, splits=(a,)) == expected
        for a, b in itertools.combinations(offsets, 2):
            assert _run(kind, text, splits=(a, b)) == expected


@pytest.mark.parametrize("kind", ["chat", "code"])
def test_forced_cut_splits_after_the_last_whitespace(kind):
    text = "aaa bbb ccc ddd eee fff"
    segments = _texts(_run(kind, text, holdback_max=10))
    assert segments[0] == "aaa bbb "
    assert "".join(segments) == text
    assert all(len(s) <= 10 for s in segments)


@pytest.mark.parametrize("kind", ["chat", "code"])
def test_forced_cut_without_whitespace_is_exact(kind):
    text = "x" * 25
    assert _texts(_run(kind, text, holdback_max=10)) == ["x" * 10, "x" * 10, "x" * 5]


def test_forced_cut_loops_over_a_buffer_three_times_the_limit_and_flush_releases_the_rest():
    text = "word " * 60
    segmenter = Segmenter("chat", 100)
    out = segmenter.push(text)
    assert len(out) >= 2 and all(len(s.text) <= 100 for s in out)
    out.extend(segmenter.flush())
    assert "".join(s.text for s in out) == text
    assert segmenter.flush() == []


def test_forced_cut_does_not_depend_on_how_the_deltas_were_split():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"
    expected = _run("chat", text, holdback_max=17)
    for a in range(len(text) + 1):
        assert _run("chat", text, holdback_max=17, splits=(a,)) == expected


def test_a_boundary_beyond_the_limit_is_still_a_forced_cut():
    # The sentence end sits past holdback_max: no segment may exceed it.
    text = "abcdefghij klmnopqrst. tail"
    segments = _texts(_run("chat", text, holdback_max=12))
    assert all(len(s) <= 12 for s in segments) and "".join(segments) == text


def test_holdback_max_must_be_positive():
    with pytest.raises(ValueError):
        Segmenter("chat", 0)


def test_code_cuts_only_at_newlines():
    text = "def f():\n    return 1.\n\nx = 'a. b'\n"
    assert _texts(_run("code", text)) == ["def f():\n", "    return 1.\n", "\n", "x = 'a. b'\n"]


# --- fences --------------------------------------------------------------------


def _fenced_lines(text, **kwargs):
    return [(s.text, s.fenced) for s in _run("code", text, skip_fenced=True, **kwargs)]


def _blanked(segments):
    return "".join(re.sub(r"[^\n]", "\n", s.text) if s.fenced else s.text for s in segments)


@pytest.mark.parametrize("fence", ["```", "~~~", "````", "   ```", "```py"])
def test_an_opener_split_across_deltas_at_every_offset_is_seen_whole(fence):
    closer = fence.strip()[:3] + ("`" if fence.strip().startswith("````") else "")
    text = f"prose\n{fence}\ninside\n{closer}\nafter\n"
    expected = _fenced_lines(text)
    assert [fenced for _, fenced in expected] == [False, True, True, True, False]
    for offset in range(len(text) + 1):
        assert [(s.text, s.fenced) for s in _run("code", text, skip_fenced=True, splits=(offset,))] == expected


def test_a_closer_must_match_the_character_and_at_least_the_length():
    text = "````\n```\nstill inside\n~~~\n`````\nout\n"
    assert [fenced for _, fenced in _fenced_lines(text)] == [True, True, True, True, True, False]
    # ``` does not close ~~~ either.
    assert [fenced for _, fenced in _fenced_lines("~~~\n```\nx\n~~~\ny\n")] == [True, True, True, True, False]


def test_an_unterminated_fence_runs_to_the_end():
    assert [fenced for _, fenced in _fenced_lines("a\n```\nb\nc")] == [False, True, True, True]


def test_inline_backticks_are_not_fenced():
    assert [fenced for _, fenced in _fenced_lines("see `a` and ``b`` here\nuse `x@y.com` please\n")] == [False, False]


def test_a_final_line_without_newline_can_be_a_closer():
    assert [fenced for _, fenced in _fenced_lines("```\ncode\n```")] == [True, True, True]


def test_a_force_cut_line_keeps_its_classification_for_the_rest():
    body = "y" * 30
    text = f"```\n{body}\n```\nprose {body}\n"
    segments = _run("code", text, holdback_max=10, skip_fenced=True)
    assert "".join(s.text for s in segments) == text
    fences = [i for i, s in enumerate(segments) if s.text == "```\n"]
    assert len(fences) == 2
    inside = segments[fences[0] + 1 : fences[1]]
    assert len(inside) == 4 and all(s.fenced for s in inside)  # 30 characters cut in three, then the newline
    after_fence = segments[fences[1] + 1 :]
    assert [s.fenced for s in after_fence] == [False] * len(after_fence)


def test_fence_differential_against_strip_fenced_blocks_on_generated_texts():
    pieces = ["```", "~~~", "````", "```py", "  ```", "text a@b.com", "", "`inline`", "    ~~~", "`````", "x"]
    checked = 0
    for count in (1, 2, 3, 4):
        for combo in itertools.product(pieces, repeat=count):
            for ending in ("", "\n"):
                text = "\n".join(combo) + ending
                segments = _run("code", text, skip_fenced=True)
                assert "".join(s.text for s in segments) == text
                assert _blanked(segments) == strip_fenced_blocks(text), repr(text)
                checked += 1
    assert checked > 10000


def test_fence_differential_on_hand_written_texts():
    for text in (
        "Intro with `ops@corp.com`.\n```python\nx = 'a@b.com'\n```\nOutside again.\n~~~\nraw\n~~~\n",
        "````\n```\nnested\n```\n````\ntrail",
    ):
        segments = _run("code", text, skip_fenced=True)
        assert _blanked(segments) == strip_fenced_blocks(text)


# --- purity ---------------------------------------------------------------------


def _imports(tree):
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module)
            imported.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    return imported


def test_stream_redaction_reads_no_settings_and_does_no_logging():
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))
    imported = _imports(tree)
    assert not {name for name in imported if name and (name.startswith("app.config") or name == "logging")}
    assert not any("settings" in (name or "").split(".")[-1] for name in imported)


def test_the_segmenter_names_no_pii_redactor():
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))
    segmenter = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "Segmenter")
    names = {n.id for n in ast.walk(segmenter) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(segmenter) if isinstance(n, ast.Attribute)
    }
    assert "pii_redactor" not in names
