"""The console's palette is an inheritance, and two inks are not part of it.

PRD-006 Section 6.1 spends the console's design freedom on structure, not on
colour: the register reuses four of `theme.py`'s six verdict inks and adds no
accent of its own. `INK_UPSTREAM` and `INK_SELF` stay chat-only — the register
cannot honestly distinguish an upstream failure from an internal one (Section
6), and there is no "your own words" on an admin surface. That is a claim about
what the admin modules *do not* import, which a diff cannot show, so it is
asserted here.

The four tokens STORY-007 added are pinned here too, `STAMP_X` by identity
rather than by value: PRD Section 6.1 asks for the chat's rail *continued*, and
a hand-copied `"1.875rem"` would satisfy the value while losing the guarantee.

**One deliberate exception, recorded for STORY-018.** `theme.GLOBAL_CSS` sets
the global `:focus-visible` outline to `INK_UPSTREAM`, and the admin pages
inherit that stylesheet. It is not a violation — the rule below is about admin
*modules*, and a focus ring is a shared accessibility affordance rather than a
verdict signal — but a naive grep of rendered admin HTML will find that blue.
STORY-018's render-invariant assertion should be written knowing this, not
discover it as a failure.
"""

import re
import sys
from pathlib import Path

# Repo root, not chat_ui/ — putting the inner package on sys.path[0] shadows
# the namespace package every other test module imports through.
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from chat_ui.chat_ui import theme

REPO_ROOT = Path(__file__).parent.parent

# Chat-only, per PRD-006 Section 6.1.
CHAT_ONLY_INKS = ("INK_UPSTREAM", "INK_SELF")

# Globbed, never hard-coded: STORY-009/011/015 add admin modules and the guard
# has to cover them the day they land, without anyone remembering this file.
ADMIN_MODULE_PATTERNS = (
    "chat_ui/chat_ui/admin_*.py",
    "chat_ui/chat_ui/components/admin_*.py",
    "chat_ui/chat_ui/components/register.py",
    "chat_ui/chat_ui/components/summary.py",
)


def _admin_modules() -> list[Path]:
    found: list[Path] = []
    for pattern in ADMIN_MODULE_PATTERNS:
        found.extend(sorted(REPO_ROOT.glob(pattern)))
    return found


# --- The four STORY-007 tokens -------------------------------------------


def test_register_tokens_exist():
    """The four names PRD Section 12 Phase 2 asks for, in theme.py and nowhere else."""
    for name in ("HOVER", "ROW_H", "STAMP_X", "TEXT_MICRO"):
        assert hasattr(theme, name), name


def test_hover_ground_is_a_hex_colour():
    assert re.fullmatch(r"#[0-9A-F]{6}", theme.HOVER), theme.HOVER


@pytest.mark.parametrize("name", ["ROW_H", "TEXT_MICRO"])
def test_register_sizes_scale_with_the_reader(name):
    """rem, not px — these two ride the reader's type size."""
    assert getattr(theme, name).endswith("rem"), name


def test_stamp_margin_is_the_chat_rail_continued():
    """Identity, not equality: PRD Section 6.1 asks for the rail continued, so
    retuning RAIL_X has to retune the register's margin in the same edit. A
    hand-copied literal would pass an equality check and lose the guarantee."""
    assert theme.STAMP_X is theme.RAIL_X


def test_micro_step_is_below_the_tag_step():
    """The scale block stays ascending; TEXT_MICRO is a new smallest."""
    assert float(theme.TEXT_MICRO.removesuffix("rem")) < float(
        theme.TEXT_TAG.removesuffix("rem")
    )


# --- The two chat-only inks ----------------------------------------------


def test_admin_modules_are_discoverable():
    """A glob that matches nothing would pass every test below vacuously."""
    assert _admin_modules(), ADMIN_MODULE_PATTERNS


@pytest.mark.parametrize("ink", CHAT_ONLY_INKS)
def test_no_admin_module_references_a_chat_only_ink(ink):
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _admin_modules()
        if ink in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"{ink} is chat-only (PRD-006 Section 6.1): {offenders}"


def test_console_adds_no_tint():
    """PRD Section 6.1: "a hundred tinted rows would be a heat map of noise."
    The five TINT_* fills isolate one panel among prose; the register has no
    prose. STORY-018 extends this to the rendered output."""
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _admin_modules()
        if "TINT_" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"the register uses no tint: {offenders}"
