"""WCAG AA contrast floor for the chat palette.

The verdict inks are the whole point of the redesign — one pigment per pipeline
outcome — so a tag nobody can read is a broken feature, not a cosmetic nit. The
ochre shipped at 4.38:1 against the paper and had to be darkened; this file
keeps every ink above the line as the palette evolves. PRD-006 adds a second
ground to hold: the admin register's row hover, which every verdict ink is
drawn on when a row is under the cursor.

STORY-018 closes the file with the console's pairings stated as a set — six inks
across three grounds — rather than as a list that has to be remembered when a
component moves an ink. The blocks above stay as they are: they are the chat's
specific pairings, and each one records why it is here.

**The dark ground doubles every claim in this file.** `theme.py` now holds two
palettes, `LIGHT` and `DARK`, and each block below is parametrized over both. The
change is mechanical and deliberately so: every list here went from holding token
*values* to holding token *names*, and the value is resolved out of the palette
under test. Nothing else moved — the pairings, the reasoning attached to each,
and the floor are what they were.

That mechanical change is the whole reason the file is worth extending rather
than duplicating. A `test_contrast_dark.py` would have been a second list of
pairings to keep in step with this one, and the pairing lists are exactly what
STORY-018 and STORY-020 spent their effort making authoritative. Holding names
instead of values means a ground added tomorrow costs one entry in `PALETTES`
and no new pairing at all.

**Two palettes, one instrument.** The dark ground is not held to a lower floor
because it is new: `AA_NORMAL` is the same 4.5 for both, and the same cross
products run against both. It clears with more headroom than the light ground
does — its tightest pairing is `MUTE` on `HOVER` at 6.15:1, against the light
palette's 4.63:1 for `MUTE` on `PAPER` — which is a property of the palette that
was tuned against this file, not a concession made by it.
"""

import sys
from pathlib import Path

# Repo root, not chat_ui/ — putting the inner package on sys.path[0] shadows
# the namespace package every other test module imports through.
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from chat_ui.chat_ui import theme

AA_NORMAL = 4.5

# The grounds every block below runs against. Named, so a failure says which
# palette broke rather than only which pairing.
PALETTES = (
    ("light", theme.LIGHT),
    ("dark", theme.DARK),
)


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


def test_both_palettes_declare_the_same_tokens():
    """The precondition every parametrized block below rests on.

    Each block resolves a token *name* against whichever palette is under test,
    so a name present in `LIGHT` and missing from `DARK` would not fail those
    tests — it would raise `KeyError` inside them, which reads as a broken test
    rather than as the missing colour it is. Worse, a token added to `DARK`
    alone is invisible to every assertion here and ships as a custom property
    that resolves on one ground and not the other.

    Asserting the key sets are equal states the contract `theme.py`'s comment
    claims ("Both dicts carry the same names"), and turns either omission into
    one honest failure with the missing names in the message.
    """
    assert set(theme.LIGHT) == set(theme.DARK), {
        "only in LIGHT": sorted(set(theme.LIGHT) - set(theme.DARK)),
        "only in DARK": sorted(set(theme.DARK) - set(theme.LIGHT)),
    }


@pytest.mark.parametrize("palette_name,palette", PALETTES)
def test_every_palette_value_is_a_hex_triplet(palette_name, palette):
    """The palettes are the last place a real colour is written down.

    Every token in `theme.py`'s module namespace is now a `var(--hx-…)` string,
    so `_luminance` would happily be handed one — `"var(--hx-ink)".lstrip("#")`
    does not raise, it just parses nothing. Pinning the shape here means the
    day someone writes a `var()`, an `rgb()` or a named colour into a palette,
    it fails as a malformed palette instead of as an inscrutable `ValueError`
    six parametrized blocks later.
    """
    for name, value in palette.items():
        assert isinstance(value, str) and len(value) == 7 and value.startswith("#"), (
            f"{palette_name}.{name} is not a #RRGGBB triplet: {value!r}"
        )
        int(value[1:], 16)


def test_ink_self_is_the_same_pigment_as_ink_on_both_grounds():
    """"Your own words — plain ink, no verdict", stated where it is now true.

    `tests/test_render_invariants.py` and `tests/test_session_rail.py` each
    carried `assert theme.INK_SELF == theme.INK` to record why neither file can
    exclude `INK_SELF` by value. That identity moved when the tokens became
    custom property references: `theme.INK_SELF` is now `var(--hx-ink-self)` and
    `theme.INK` is `var(--hx-ink)`, which are different strings naming the same
    pigment.

    So the claim is asserted here, against the palettes, where the pigments
    actually live — and against *both*, because a dark palette that let the two
    drift would break the reasoning in those two files without failing either of
    them.
    """
    for palette_name, palette in PALETTES:
        assert palette["INK_SELF"] == palette["INK"], palette_name


# Each verdict ink with the two grounds it is actually drawn on: the rail tag
# sits on the paper, the panel text on that outcome's tint.
#
# Names rather than values, so the pair resolves against the palette under test.
_INK_ON_TINT = [
    ("INK_CLEAR", "TINT_CLEAR"),
    ("INK_HELD", "TINT_HELD"),
    ("INK_DENIED", "TINT_DENIED"),
    ("INK_UPSTREAM", "TINT_UPSTREAM"),
    ("INK_FAULT", "TINT_FAULT"),
]


@pytest.mark.parametrize("palette_name,palette", PALETTES)
@pytest.mark.parametrize("name,tint", _INK_ON_TINT)
def test_verdict_ink_is_readable_on_the_paper(name, tint, palette_name, palette):
    """The tag is small text on the transcript ground."""
    assert contrast(palette[name], palette["PAPER"]) >= AA_NORMAL, (
        f"{name} on PAPER ({palette_name})"
    )


@pytest.mark.parametrize("palette_name,palette", PALETTES)
@pytest.mark.parametrize("name,tint", _INK_ON_TINT)
def test_verdict_ink_is_readable_on_its_own_tint(name, tint, palette_name, palette):
    assert contrast(palette[name], palette[tint]) >= AA_NORMAL, (
        f"{name} on {tint} ({palette_name})"
    )


# The register draws every verdict ink on the row hover ground, so the hover is
# a fifth ground the inks have to clear — not a decoration. Four entries, not
# six: INK_UPSTREAM and INK_SELF are chat-only (PRD-006 Section 6.1), and
# asserting them here would imply the console draws them.
_INK_ON_HOVER = [
    "INK_CLEAR",
    "INK_HELD",
    "INK_DENIED",
    "INK_FAULT",
]


@pytest.mark.parametrize("palette_name,palette", PALETTES)
@pytest.mark.parametrize("name", _INK_ON_HOVER)
def test_verdict_ink_is_readable_on_the_row_hover(name, palette_name, palette):
    """A hovered row is still a row being read."""
    assert contrast(palette[name], palette["HOVER"]) >= AA_NORMAL, (
        f"{name} on HOVER ({palette_name})"
    )


@pytest.mark.parametrize("palette_name,palette", PALETTES)
@pytest.mark.parametrize(
    "name,fg,bg",
    [
        ("body ink on paper", "INK", "PAPER"),
        ("body ink on card", "INK", "CARD"),
        ("muted text on paper", "MUTE", "PAPER"),
        ("muted text on card", "MUTE", "CARD"),
        ("inverted button label", "PAPER", "INK"),
        # The admin gate's submit on hover (STORY-009). The chat's gate hovers
        # to the upstream blue, which PRD-006 Section 6.1 keeps off the console,
        # so the console's only other dark neutral carries it instead. 4.63:1 on
        # the light ground — the tightest pairing in that palette, and the
        # reason it is asserted.
        ("inverted button label on hover", "PAPER", "MUTE"),
        ("body ink on row hover", "INK", "HOVER"),
        ("muted text on row hover", "MUTE", "HOVER"),
        # RULE is deliberately absent: it is a hairline, not text, and measures
        # 1.37:1 on the hover ground. AA is a text criterion, so asserting it
        # here would either fail honestly or force the floor down for everyone.
    ],
)
def test_neutral_pairs_are_readable(name, fg, bg, palette_name, palette):
    assert contrast(palette[fg], palette[bg]) >= AA_NORMAL, f"{name} ({palette_name})"


# The console's pairings as a set rather than as a list someone remembers to
# extend (STORY-018 AC 6). Six inks, three grounds, and every combination held to
# the floor — on each palette, so eighteen pairings became thirty-six.
_CONSOLE_INKS = (
    "INK",
    "MUTE",
    "INK_CLEAR",
    "INK_HELD",
    "INK_DENIED",
    "INK_FAULT",
)

_CONSOLE_GROUNDS = (
    "PAPER",  # the page, and the fault panel on it
    "CARD",  # the gate panel and the masthead
    "HOVER",  # a register row under the cursor
)


@pytest.mark.parametrize("palette_name,palette", PALETTES)
@pytest.mark.parametrize(
    "ink_name,ground_name",
    [(ink, ground) for ink in _CONSOLE_INKS for ground in _CONSOLE_GROUNDS],
)
def test_every_console_pairing_is_readable(
    ink_name, ground_name, palette_name, palette
):
    """Every pairing the admin console introduced, at AA, on every ground.

    A cross product over-asserts — the register never paints `INK_HELD` on the
    gate's card — and that is the point. It is a superset of what ships, so it
    needs no edit when a component moves an ink onto a ground it had not used
    before, which is exactly the drift a hand-maintained list misses. All
    eighteen clear the floor with margin on the light ground; the tightest is
    `MUTE` on `PAPER` at 4.63:1, the same pairing the neutral block above already
    flags as the tightest in this file. On the dark ground all eighteen clear it
    too, the tightest being `MUTE` on `HOVER` at 6.15:1. A failure here is a
    token that moved, not a matrix that is too strict.

    The palette axis is the outer one, so a failure id reads
    `[light-INK_CLEAR-CARD]` and names the ground first.
    """
    assert contrast(palette[ink_name], palette[ground_name]) >= AA_NORMAL, (
        f"{ink_name} on {ground_name} ({palette_name})"
    )


# The rail's pairings as a set, on the console block's pattern (STORY-020 AC 6).
#
# The rail renders exactly two inks on exactly two grounds, and every one of the
# four was already asserted in the neutral block above -- including
# `("body ink on row hover", "INK", "HOVER")`, which is AC 6's specifically named
# case. **No new pairing was needed**, and that is the finding rather than an
# absence of work: STORY-017 declared the rail's tokens adding no ink, STORY-018
# spent none, and the story predicted this outcome ("a new pairing appearing here
# is a signal worth recording, not a routine addition"). Stating the set is what
# makes the result survive a component moving an ink onto a ground it had not
# used before.
#
# The dark ground did not change that either, and by the same mechanism: the rail
# spends no ink of its own, so a second palette gives it a second set of values
# for the same four pairings and no fifth pairing to declare.
#
# The neutral entries above are deliberately not deleted. They record *why each
# specific pairing exists*; this block records *what the surface is allowed to
# do*. The module docstring draws the same distinction for the console block.
_RAIL_INKS = (
    "INK",  # session titles, and the active row's own mark of type
    "MUTE",  # the activity time, and the row's quiet verbs
)

# `SPINE`, `RULE` and `RULE_SOFT` are absent by the same reasoning the neutral
# block records for `RULE`: AA is a text criterion, and a hairline or a solid
# mark is not text. `SPINE` carries no glyph -- it is a nine-pixel bar, and
# PRD-008 Section 6.1 marks the active row with "`INK` type against `HOVER`",
# which is the pairing below and not the mark.
_RAIL_GROUNDS = (
    "PAPER",  # the rail's own ground, against the transcript's CARD
    "HOVER",  # a row under the cursor, and the active row's ground
)


@pytest.mark.parametrize("palette_name,palette", PALETTES)
@pytest.mark.parametrize(
    "ink_name,ground_name",
    [(ink, ground) for ink in _RAIL_INKS for ground in _RAIL_GROUNDS],
)
def test_every_rail_pairing_is_readable(ink_name, ground_name, palette_name, palette):
    """Every pairing the session rail actually uses, at AA.

    PRD-008 Section 11's quality bar: "every rail string resolves from `copy.py`;
    every colour and size from `theme.py`; `tests/test_contrast.py` covers any
    new pairing." This is the covering half.

    A cross product, for the reason the console block gives: it is a superset of
    what ships, so it needs no edit when the rail moves `MUTE` onto `HOVER` or
    `INK` onto `PAPER` in some future row treatment. All four clear the floor on
    the light ground at 15.45:1, 16.04:1, 4.63:1 and 4.80:1 -- the tightest being
    `MUTE` on `PAPER`, which is the same pairing the neutral block above already
    flags as the tightest in this file, and the reason the rail's activity time
    is the one piece of rail type worth watching. On the dark ground the same
    four clear it at 14.87:1, 12.48:1, 7.33:1 and 6.15:1. A failure here is a
    token that moved in `theme.py`, not a matrix that is too strict.
    """
    assert contrast(palette[ink_name], palette[ground_name]) >= AA_NORMAL, (
        f"{ink_name} on {ground_name} ({palette_name})"
    )
