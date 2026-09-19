"""The `context_limit` bubble's structure (PRD-010 STORY-013).

Four claims AC 2 makes that neither `tests/test_copy.py` nor
`tests/test_chat_components_import.py` covers:

1. The kind has its own `rx.match` arm, and that arm sits **above** the
   default. "It does not fall through to the default arm" is a claim about
   position, and a membership check would pass on a file where the arm was
   written below `render_fallback` and therefore never reached.
2. The renderer is imported by name, so a missing import fails at collection.
3. The bubble draws only a pigment the contrast suite actually covers. This is
   the guard on plan decision D-B: `INK_FORBIDDEN` is the intuitive pigment for
   a refusal and is **below AA on the light ground** (4.28 on `PAPER`, 4.44 on
   its own tint, against a 4.5 floor), which is exactly why it is the one
   verdict pair missing from `_INK_ON_TINT`. Swapping it in later would look
   like a tidy-up and would ship unreadable text.
4. No user-facing string is written as a literal in `bubbles.py`.

**Source assertions, read as text, and no in-process import of
`chat_ui.components.*`.** `tests/test_session_rail.py` and
`tests/test_chat_shell.py` both record the reason in their docstrings:
importing the inner package puts it on `sys.path` and breaks every other test
module, which reaches these files by their repo-root path. The build-level
claim -- that the renderer compiles against a Var -- is covered by
`tests/test_chat_components_import.py`'s subprocess probe, which this story
extends rather than duplicates.
"""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CHAT = _REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "chat.py"
_BUBBLES = _REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "bubbles.py"
_STATE = _REPO_ROOT / "chat_ui" / "chat_ui" / "state.py"

# The kind string, written once here and asserted to appear on both sides of
# the wire. A typo in either place is otherwise a silent fallback bubble.
_KIND = "context_limit"


def _renderer_source() -> str:
    """`render_context_limit`'s body, sliced out of bubbles.py.

    From its `def` to the next top-level `def`, so the assertions below cannot
    accidentally pass because some *other* renderer names the right token.
    """
    source = _BUBBLES.read_text(encoding="utf-8")
    start = source.index("def render_context_limit(")
    rest = source[start + 1 :]
    end = rest.find("\ndef ")
    assert end != -1, "render_context_limit is the last top-level def; slice never terminates"
    return rest[:end]


def test_the_match_has_a_context_limit_arm_above_the_default():
    """AC 2: a distinct arm, and it is reached before the fallback."""
    source = _CHAT.read_text(encoding="utf-8")

    arm = f'("{_KIND}", render_context_limit(message))'
    assert arm in source, f"message_bubble has no {_KIND} arm"

    default = "render_fallback(message)"
    assert default in source, "the default arm is gone; rx.match would raise on an unknown kind"

    assert source.index(arm) < source.rindex(default), (
        f"the {_KIND} arm is written after the default arm, so it is unreachable"
    )


def test_the_renderer_is_imported_by_name():
    """A missing import fails at collection rather than at render."""
    source = _CHAT.read_text(encoding="utf-8")
    assert "render_context_limit," in source or "render_context_limit\n" in source, (
        "render_context_limit is not in chat.py's import block"
    )


def test_the_context_limit_bubble_draws_only_contrast_covered_tokens():
    """AC 4 / plan D-B: the reused pair is one the contrast suite asserts.

    `_INK_ON_TINT` is imported rather than restated, so this test and
    `tests/test_contrast.py` cannot drift apart: if the pair is ever dropped
    from that list, this fails too.
    """
    from tests.test_contrast import _INK_ON_TINT

    body = _renderer_source()

    assert "theme.INK_HELD" in body
    assert "theme.TINT_HELD" in body

    drawn = set(re.findall(r"theme\.((?:INK|TINT)_[A-Z_]+)", body))
    assert drawn == {"INK_HELD", "TINT_HELD"}, (
        f"the bubble draws tokens beyond the reused pair: {sorted(drawn)}"
    )

    assert ("INK_HELD", "TINT_HELD") in _INK_ON_TINT, (
        "the pigment this bubble draws is not covered by the contrast suite"
    )


def test_the_context_limit_bubble_writes_no_user_facing_literal():
    """Every string the reader sees resolves from `copy.py`.

    PRD-004 STORY-007's rule, carried onto the kind this story adds. Asserted
    on the values, the way `test_copy.py`'s rail vocabulary guard is: a pasted
    literal is invisible in a diff that also adds the constant.
    """
    from chat_ui.chat_ui import copy

    body = _renderer_source()
    whole_file = _BUBBLES.read_text(encoding="utf-8")

    assert "copy.CONTEXT_LIMIT_HEADLINE" in body
    assert "copy.CONTEXT_LIMIT_NEW_CHAT_NOTICE" in body
    assert "copy.TAG_CONTEXT_LIMIT" in body

    for name in (
        "CONTEXT_LIMIT_HEADLINE",
        "CONTEXT_LIMIT_NEW_CHAT_NOTICE",
        "TAG_CONTEXT_LIMIT",
    ):
        value = getattr(copy, name)
        assert value not in whole_file, (
            f"{name}'s text is inlined in bubbles.py as a literal; render it as copy.{name}"
        )


def test_the_kind_string_matches_the_bubble_state_builds():
    """The dispatcher and the producer agree on the kind, character for character."""
    assert f'("{_KIND}"' in _CHAT.read_text(encoding="utf-8")
    assert f'kind="{_KIND}"' in _STATE.read_text(encoding="utf-8")
