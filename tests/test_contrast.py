"""WCAG AA contrast floor for the chat palette.

The verdict inks are the whole point of the redesign — one pigment per pipeline
outcome — so a tag nobody can read is a broken feature, not a cosmetic nit. The
ochre shipped at 4.38:1 against the paper and had to be darkened; this file
keeps every ink above the line as the palette evolves. PRD-006 adds a second
ground to hold: the admin register's row hover, which every verdict ink is
drawn on when a row is under the cursor.
"""

import sys
from pathlib import Path

# Repo root, not chat_ui/ — putting the inner package on sys.path[0] shadows
# the namespace package every other test module imports through.
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from chat_ui.chat_ui import theme

AA_NORMAL = 4.5


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    channels = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    channels = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def test_contrast_helper_matches_known_values():
    """Guards the maths itself, so a wrong helper cannot silently pass everything."""
    assert contrast("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.01)
    assert contrast("#FFFFFF", "#FFFFFF") == pytest.approx(1.0, abs=0.01)


# Each verdict ink with the two grounds it is actually drawn on: the rail tag
# sits on the paper, the panel text on that outcome's tint.
_INK_ON_TINT = [
    ("INK_CLEAR", theme.INK_CLEAR, theme.TINT_CLEAR),
    ("INK_HELD", theme.INK_HELD, theme.TINT_HELD),
    ("INK_DENIED", theme.INK_DENIED, theme.TINT_DENIED),
    ("INK_UPSTREAM", theme.INK_UPSTREAM, theme.TINT_UPSTREAM),
    ("INK_FAULT", theme.INK_FAULT, theme.TINT_FAULT),
]


@pytest.mark.parametrize("name,ink,tint", _INK_ON_TINT)
def test_verdict_ink_is_readable_on_the_paper(name, ink, tint):
    """The tag is small text on the transcript ground."""
    assert contrast(ink, theme.PAPER) >= AA_NORMAL, name


@pytest.mark.parametrize("name,ink,tint", _INK_ON_TINT)
def test_verdict_ink_is_readable_on_its_own_tint(name, ink, tint):
    assert contrast(ink, tint) >= AA_NORMAL, name


# The register draws every verdict ink on the row hover ground, so the hover is
# a fifth ground the inks have to clear — not a decoration. Four entries, not
# six: INK_UPSTREAM and INK_SELF are chat-only (PRD-006 Section 6.1), and
# asserting them here would imply the console draws them.
_INK_ON_HOVER = [
    ("INK_CLEAR", theme.INK_CLEAR),
    ("INK_HELD", theme.INK_HELD),
    ("INK_DENIED", theme.INK_DENIED),
    ("INK_FAULT", theme.INK_FAULT),
]


@pytest.mark.parametrize("name,ink", _INK_ON_HOVER)
def test_verdict_ink_is_readable_on_the_row_hover(name, ink):
    """A hovered row is still a row being read."""
    assert contrast(ink, theme.HOVER) >= AA_NORMAL, name


@pytest.mark.parametrize(
    "name,fg,bg",
    [
        ("body ink on paper", theme.INK, theme.PAPER),
        ("body ink on card", theme.INK, theme.CARD),
        ("muted text on paper", theme.MUTE, theme.PAPER),
        ("muted text on card", theme.MUTE, theme.CARD),
        ("inverted button label", theme.PAPER, theme.INK),
        ("body ink on row hover", theme.INK, theme.HOVER),
        ("muted text on row hover", theme.MUTE, theme.HOVER),
        # RULE is deliberately absent: it is a hairline, not text, and measures
        # 1.37:1 on the hover ground. AA is a text criterion, so asserting it
        # here would either fail honestly or force the floor down for everyone.
    ],
)
def test_neutral_pairs_are_readable(name, fg, bg):
    assert contrast(fg, bg) >= AA_NORMAL, name
