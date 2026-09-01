"""The console's two render invariants, asserted against a seeded database.

PRD-006 Risks 2 and 6 are the two claims on this surface that are easiest to
break silently and hardest to see in a diff: that the raw previews never reach
the screen, and that nothing on the console is painted outside the four verdict
inks. Every test shipped before this one checks them **per component** —
`tests/test_register.py` collects the hexes in `str(register())`,
`tests/test_summary.py` does the same for the sheet, and
`tests/test_admin_palette.py` greps the admin modules as text. None of them
renders a *page*, and none of them had ever put a row read out of a real
database in front of a real component. This file does both.

**What "the rendered output" is here.** A Reflex page does not compile to HTML
with values in it. It compiles to a *template* that references state vars, and
the frontend binds a *payload* — the serialized state — into that template. So a
string search of `str(admin_page(...))` alone would find no seeded value at all,
and a preview test written that way would pass whether or not the boundary held.
The assertion below is therefore over both halves, because both halves are what
the browser receives: `probe["payload"]` is `AdminState.dict()`, computed vars
included, and `probe["register_page"]` / `probe["summary_page"]` are the
compiled templates. A sentinel may appear in neither.

**The positive control is the point.** Four rows are seeded, one per verdict, and
`test_the_probe_actually_loaded_the_seeded_record` asserts they arrived: four
rows, four distinct verdicts, the seeded `user_id` present in the payload. Every
preview assertion in this file is a negative, and negatives pass on an empty
state — so that test is what stands between this file and a tautology. If it
ever fails, nothing else here means anything, whatever colour it prints.

**The probe runs in a subprocess**, as `tests/test_register.py`,
`tests/test_summary.py` and `tests/test_admin_shell.py` all do, because the
admin modules import each other as `chat_ui.components...`, which resolves only
under the `chat_ui/` PYTHONPATH — and putting the inner package on `sys.path`
in-process breaks every other test module. Here it earns its place twice over:
the probe writes rows into the throwaway database conftest hands it through
`DATABASE_URL`, and doing that in the pytest process would put sentinel previews
one misconfigured path away from a developer's real `harness_ai.db`.

**Two colour claims cannot be made by hex, and are not.**

- `theme.GLOBAL_CSS` sets the global `:focus-visible` outline to `INK_UPSTREAM`,
  and `admin_page()` owns that stylesheet, so every admin page's output contains
  the chat-only blue. It is a shared accessibility affordance, not a verdict
  signal. `tests/test_admin_palette.py`'s docstring predicted this and asked that
  STORY-018 be written knowing it: the stylesheet is stripped before any hex is
  collected, the strip is asserted to have happened, and the exception is pinned
  by `test_the_focus_ring_is_the_only_upstream_ink`.
- `INK_SELF` and `INK` are the same value, `#14181C`. No hex search can tell them
  apart, so "no `INK_SELF` on the console" lives where it can be true — the
  by-name source grep in `tests/test_admin_palette.py` — and
  `test_ink_self_cannot_be_excluded_by_value` records why, so nobody adds a
  value-based check here that would either fail on every page or mean nothing.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

# Repo root, not chat_ui/ — putting the inner package on sys.path[0] shadows the
# namespace package every other test module imports through.
sys.path.insert(0, str(Path(__file__).parent.parent))

from chat_ui.chat_ui import theme  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]

# The four verdicts, as `admin_formatting` names them. Retyped here rather than
# imported for one reason: this file asserts that the seeded rows produced all
# four, and importing the tuple under test would make a renamed verdict agree
# with itself.
EXPECTED_VERDICTS = {"cleared", "held", "denied", "fault"}

# The seeded user, and the sentinel previews. Distinct per row so a failure names
# which row leaked, and distinctive enough that a match is never a coincidence.
# Eight strings for four rows: the numbering matches the probe's, where row
# `index` writes prompt `index * 2` and response `index * 2 + 1`.
SEEDED_USER = "a.torres"
PREVIEW_SENTINELS = tuple(
    part
    for index in range(4)
    for part in (
        f"SENTINEL-PROMPT-{index * 2}-b3f19a",
        f"SENTINEL-RESPONSE-{index * 2 + 1}-7c02de",
    )
)

# The five fills PRD-006 Section 6.1 keeps off the console: "a hundred tinted
# rows would be a heat map of noise."
TINT_NAMES = (
    "TINT_CLEAR",
    "TINT_HELD",
    "TINT_DENIED",
    "TINT_UPSTREAM",
    "TINT_FAULT",
)

# The four verdict inks the console is allowed to paint (PRD-006 Section 6.1's
# colour table).
VERDICT_INKS = {
    "INK_CLEAR": theme.INK_CLEAR,
    "INK_HELD": theme.INK_HELD,
    "INK_DENIED": theme.INK_DENIED,
    "INK_FAULT": theme.INK_FAULT,
}

# Everything the console may paint: the four inks plus the ground tokens. Read
# from theme.py by name, never copied as literals — a token retuned in theme.py
# retunes this assertion in the same edit, which is the whole point of the
# single-file guarantee theme.py's docstring makes.
ALLOWED_COLOURS = {value.upper() for value in VERDICT_INKS.values()} | {
    theme.PAPER.upper(),
    theme.CARD.upper(),
    theme.INK.upper(),
    theme.MUTE.upper(),
    theme.RULE.upper(),
    theme.RULE_SOFT.upper(),
    theme.SPINE.upper(),
    theme.HOVER.upper(),
}

# The two pages, as probe keys. Both are asserted for every invariant: PRD-006
# Risk 6 names the register, but the summary is the surface the dashboard
# default pulls hardest on, and a drift that lands there only would pass a
# register-only check.
PAGES = ("register_page", "summary_page")

# `AuditRow` fields the register and its disclosure actually read. Asserted
# present alongside the preview absences, because a projection that dropped
# every field would satisfy the negatives on its own.
REQUIRED_ROW_FIELDS = (
    "audit_id",
    "timestamp_absolute",
    "timestamp_relative",
    "user_id",
    "verdict",
    "model_used",
    "tokens_used",
    "pii_indicator",
    "device_short",
    "device_full",
    "prompt_hash",
    "error_message",
    "pii_entities",
    "suspicious_pattern",
)


# Runs in the subprocess. Emits one JSON object on the last stdout line.
_CHECK_SCRIPT = r"""
import json, sys

result = {"errors": []}

try:
    import asyncio

    # DATABASE_URL arrives through this process's environment, where
    # app/config.py's BaseSettings picks it up -- it must name a throwaway
    # database, because init_db() against the developer's real audit log would
    # write sentinel previews into it.
    from app.config import settings

    import reflex as rx
    from app.db.database import init_db, insert_audit_log
    from app.db.models import AuditLog
    from chat_ui import theme
    from chat_ui.admin_models import AuditRow
    from chat_ui.admin_state import AdminState
    from chat_ui.components.admin_shell import (
        VIEW_REGISTER,
        VIEW_SUMMARY,
        admin_page,
    )
    from chat_ui.components.register import register
    from chat_ui.components.summary import summary
except Exception as exc:
    print(json.dumps({"errors": ["import: {}: {}".format(type(exc).__name__, exc)]}))
    sys.exit(0)

init_db()

# One row per verdict, so every rx.match arm has real data behind it, and both
# preview columns populated on every one. Timestamps descend so the order the
# register renders is the order written here.
_ROWS = [
    dict(timestamp="2026-08-31T14:22:07", was_duplicate_blocked=False),
    dict(timestamp="2026-08-31T14:21:07", was_duplicate_blocked=True),
    dict(timestamp="2026-08-31T14:20:07", suspicious_pattern="ignore previous"),
    dict(
        timestamp="2026-08-31T14:19:07",
        success=False,
        error_message="OpenRouter request failed: timeout after 30s",
    ),
]
for index, overrides in enumerate(_ROWS):
    insert_audit_log(
        AuditLog(
            user_id="a.torres",
            prompt_hash="hash-{}".format(index),
            prompt_preview="SENTINEL-PROMPT-{}-b3f19a".format(index * 2),
            response_preview="SENTINEL-RESPONSE-{}-7c02de".format(index * 2 + 1),
            model_used="gpt-4",
            tokens_used=412,
            device="Mozilla/5.0 (X11; Linux x86_64)",
            pii_detected_input=True,
            pii_entities="EMAIL_ADDRESS,PERSON",
            **overrides
        )
    )

# The gate and the read, driven exactly as tests/test_admin_state.py does.
state = AdminState(_reflex_internal_init=True)
state.token_input = settings.ADMIN_TOKEN
type(state).event_handlers["authenticate"].fn(state)
try:
    asyncio.run(type(state).event_handlers["load"].fn(state))
except Exception as exc:
    result["errors"].append("load: {}: {}".format(type(exc).__name__, exc))

result["authenticated"] = bool(state.authenticated)
result["load_error"] = state.error
result["row_count"] = len(state.rows)
result["verdicts"] = sorted({row.verdict for row in state.rows})
result["row_fields"] = sorted(AuditRow.__fields__)

# The payload: the state as the frontend receives it, computed vars included.
try:
    result["payload"] = json.dumps(state.dict(), default=str)
except Exception as exc:
    result["errors"].append("payload: {}: {}".format(type(exc).__name__, exc))
    result["payload"] = ""

# The templates: whole pages, not bare components, so the masthead, the gate,
# the fault panel and the stylesheet are all in scope.
try:
    result["register_page"] = str(admin_page(register(), VIEW_REGISTER))
    result["summary_page"] = str(admin_page(summary(), VIEW_SUMMARY))
except Exception as exc:
    result["errors"].append("render: {}: {}".format(type(exc).__name__, exc))
    result["register_page"] = ""
    result["summary_page"] = ""

# The rendered stylesheet, not theme.GLOBAL_CSS itself: Reflex escapes the string
# on the way into the style element, so the raw constant does not appear in the
# page and stripping it would silently remove nothing.
result["stylesheet"] = str(rx.el.style(theme.GLOBAL_CSS))

print(json.dumps(result))
"""


@pytest.fixture(scope="module")
def probe(database_url_factory):
    proc = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT],
        cwd=str(REPO_ROOT / "chat_ui"),
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(_PYTHONPATH),
            # admin_state imports app.config.settings, where both are required
            # fields. Same defaults tests/test_register.py sets.
            "ADMIN_TOKEN": os.environ.get("ADMIN_TOKEN", "test-token"),
            "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "test-key"),
            "DATABASE_URL": database_url_factory("render_probe"),
        },
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"render-invariant probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _page_without_the_stylesheet(probe, page: str) -> str:
    """The page with `theme.GLOBAL_CSS` removed, having proved the removal.

    The stylesheet carries `INK_UPSTREAM` in its `:focus-visible` rule (see the
    module docstring), so it has to come out before any hex is collected. The
    length assertion is what keeps that from becoming a silent no-op: if Reflex
    ever renders the style element differently, this fails loudly instead of
    leaving every colour assertion below testing a string it did not shorten.
    """
    rendered = probe[page]
    stripped = rendered.replace(probe["stylesheet"], "")
    assert len(stripped) < len(rendered), (
        f"the global stylesheet was not found in {page}; "
        "the strip below is a no-op and every colour assertion is unsound"
    )
    return stripped


# --- The probe itself -----------------------------------------------------


def test_the_probe_ran(probe):
    """Catches an import failure, a raised read, or a page that would not build."""
    assert not probe["errors"], probe["errors"]


def test_the_probe_actually_loaded_the_seeded_record(probe):
    """**The load-bearing test in this file.**

    Every preview assertion below is a negative, and a negative passes on an
    empty state: no rows loaded means no sentinels rendered means green, with
    the boundary entirely unexercised. This test is what says the rows were
    really read out of the seeded database, really turned into `AuditRow`s, and
    really carry all four verdicts — so that the negatives are statements about
    a populated console rather than about an empty one.

    If this fails, nothing else in this file means anything.
    """
    assert not probe["errors"], probe["errors"]
    assert probe["authenticated"], "the gate refused the configured token"
    assert probe["load_error"] == "", probe["load_error"]
    assert probe["row_count"] == 4, probe["row_count"]
    assert set(probe["verdicts"]) == EXPECTED_VERDICTS, probe["verdicts"]
    assert SEEDED_USER in probe["payload"], "the seeded rows are not in the payload"
    assert "visible_rows" in probe["payload"], "the filtered view is not in the payload"


# --- AC 1: the previews are nowhere in the rendered output ----------------


@pytest.mark.parametrize("sentinel", PREVIEW_SENTINELS)
@pytest.mark.parametrize("surface", ("payload", *PAGES))
def test_no_preview_reaches_the_rendered_output(probe, surface, sentinel):
    """PRD-006 Risk 2's render half, over both halves of what the browser gets.

    `list_audit_logs` returns the whole row, previews included, so both strings
    are in the process — one binding away from the screen. Neither may appear in
    the state the frontend receives, nor in either compiled page.
    """
    assert not probe["errors"], probe["errors"]
    assert sentinel not in probe[surface], f"{sentinel} reached {surface}"


# --- AC 2: the boundary that makes AC 1 structural ------------------------


@pytest.mark.parametrize("field", ("prompt_preview", "response_preview"))
def test_the_row_model_has_no_preview_field(probe, field):
    """PRD-006 Risk 2's mitigation, verbatim: "A test asserts `AuditRow` has no
    preview attribute."

    This is why AC 1 holds structurally rather than by inspection — the previews
    are dropped at the projection, so there is no field for a component to bind
    even by accident.
    """
    assert not probe["errors"], probe["errors"]
    assert field not in probe["row_fields"], field


@pytest.mark.parametrize("field", REQUIRED_ROW_FIELDS)
def test_the_row_model_still_carries_what_the_register_reads(probe, field):
    """The complement, and the reason the two absences above mean something: a
    row model that dropped every field would satisfy them too."""
    assert not probe["errors"], probe["errors"]
    assert field in probe["row_fields"], field


# --- AC 3: no tint on either page -----------------------------------------


@pytest.mark.parametrize("name", TINT_NAMES)
@pytest.mark.parametrize("page", PAGES)
def test_no_tint_reaches_either_page(probe, page, name):
    """PRD-006 Risk 6: "a hundred tinted rows would be a heat map of noise."

    The tints isolate one panel among prose in the chat; the console has no
    prose. `tests/test_admin_palette.py` asserts the modules name no tint and
    `tests/test_register.py` asserts none reaches the table — this closes the
    last route, a tint arriving on a whole page from the shell or the sheet.
    """
    assert not probe["errors"], probe["errors"]
    value = getattr(theme, name).upper()
    assert value not in probe[page].upper(), name


# --- AC 4: nothing painted outside the allowed set ------------------------


@pytest.mark.parametrize("page", PAGES)
def test_no_colour_outside_the_allowed_set(probe, page):
    """PRD-006 Risk 6, over a whole page rather than one component.

    A source grep cannot see a colour a component supplies at compile time — the
    Radix accent `admin_shell.py` records for `rx.link` is exactly that failure.
    This collects every hex the compiled page actually contains and holds it to
    the four verdict inks plus the ground tokens, all read from `theme.py`.
    """
    assert not probe["errors"], probe["errors"]
    body = _page_without_the_stylesheet(probe, page)
    found = {c.upper() for c in re.findall(r"#[0-9a-fA-F]{6}\b", body)}
    assert found <= ALLOWED_COLOURS, sorted(found - ALLOWED_COLOURS)


@pytest.mark.parametrize("page", PAGES)
def test_the_focus_ring_is_the_only_upstream_ink(probe, page):
    """The one deliberate exception, pinned rather than quietly excluded.

    `INK_UPSTREAM` is chat-only on the console (PRD-006 Section 6.1) — but
    `theme.GLOBAL_CSS`'s `:focus-visible` rule paints the focus ring with it, and
    `admin_page()` carries that stylesheet onto both pages. Asserting both halves
    means an admin component adopting the blue fails here, and so does the focus
    ring going missing, which is the quality floor STORY-019 holds.
    """
    assert not probe["errors"], probe["errors"]
    body = _page_without_the_stylesheet(probe, page)
    assert theme.INK_UPSTREAM.upper() not in body.upper(), (
        "INK_UPSTREAM is chat-only outside the global focus ring"
    )
    assert theme.INK_UPSTREAM.upper() in probe["stylesheet"].upper(), (
        "the global :focus-visible ring is gone"
    )


def test_ink_self_cannot_be_excluded_by_value():
    """Why AC 4's "no `INK_SELF`" is not asserted here as a hex.

    `INK_SELF` and `INK` are the same pigment — "your own words — plain ink, no
    verdict". A hex-based exclusion would therefore either fail on every page,
    because `INK` sets the body text, or be written to pass and say nothing. The
    claim lives where it can be true: `tests/test_admin_palette.py`'s
    `test_no_admin_module_references_a_chat_only_ink`, which reads the admin
    sources by token name.

    Recorded as a test rather than a comment so that a future attempt to add the
    value check finds the reason before writing it.
    """
    assert theme.INK_SELF == theme.INK
