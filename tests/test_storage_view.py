"""PRD-018 STORY-012 (F8, AC 4): the admin console's Storage view.

Non-`db`: `storage_status()` reads memory only, so `AdminState.load()` needs no
database for this view (the conftest guard would fail any driver call). The
component is not built in-process (importing `chat_ui.components` would put the
inner package on `sys.path`, the note in `tests/test_usage_view.py`); it is
covered by `tests/test_chat_ui_startup_guard.py` (its probe imports
`chat_ui.chat_ui`, which registers the page) and `tests/test_admin_shell.py`
(route, view key and the fifth masthead peer), plus the source checks below.
"""

import asyncio
import ast
import os
import sys
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from app.config import settings
from app.db import database, storage_counters
from app.db.database import JournalView, StorageStatus
from app.services.circuit_breaker import BreakerStatus
from app.db.storage_counters import CounterSnapshot
import chat_ui.chat_ui.admin_state as admin_state_mod
from chat_ui.chat_ui import admin_copy
from chat_ui.chat_ui.admin_formatting import to_storage_view
from chat_ui.chat_ui.admin_state import (
    STORAGE_STATE_FAULT,
    STORAGE_STATE_READY,
    AdminState,
)

_TOKEN = "storage-view-token"
_REPO = Path(__file__).resolve().parents[1]


def _status(state="closed", journal_open=True, held_entries=0, held_files=0, **counters):
    breaker = BreakerStatus(
        state=state,
        since="2026-11-17T10:00:00Z",
        consecutive_failures=5 if state != "closed" else 0,
        last_failure_class="not_sent" if state != "closed" else None,
        retry_after_seconds={"closed": None, "open": 7, "half_open": 1}[state],
    )
    journal = JournalView(
        open=journal_open,
        entries=3 if journal_open else 0,
        bytes=1204 if journal_open else 0,
        max_bytes=67108864,
        headroom_bytes=2097152,
        oldest_timestamp="2026-11-17T09:59:00Z" if journal_open else None,
        draining=False,
        adopted_files=1,
        held_back_entries=held_entries,
        held_back_files=held_files,
    )
    return StorageStatus(
        instance="host:42",
        breaker=breaker,
        journal=journal,
        counters=CounterSnapshot(**counters),
    )


# --- formatting ----------------------------------------------------------------


def test_closed_verdict_and_facts():
    view = to_storage_view(_status("closed"))
    assert view.verdict == admin_copy.STORAGE_VERDICT_CLOSED
    assert view.caption == admin_copy.STORAGE_CAPTION_TEMPLATE.format(instance="host:42")
    facts = {fact.label: fact.value for fact in view.breaker}
    assert facts[admin_copy.STORAGE_LABEL_STATE] == "closed"
    assert facts[admin_copy.STORAGE_LABEL_LAST_CLASS] == "—"  # none yet: the absent mark
    journal = {fact.label: fact.value for fact in view.journal}
    assert journal[admin_copy.STORAGE_LABEL_ENTRIES] == "3"
    assert journal[admin_copy.STORAGE_LABEL_SIZE] == "1,204 of 67,108,864 bytes"
    assert journal[admin_copy.STORAGE_LABEL_DRAINING] == admin_copy.STORAGE_NO


def test_open_and_half_open_verdicts_say_it_in_words():
    opened = to_storage_view(_status("open")).verdict
    assert "open" in opened and "7 s" in opened and "2026-11-17T10:00:00Z" in opened
    probing = to_storage_view(_status("half_open")).verdict
    assert probing == admin_copy.STORAGE_VERDICT_HALF_OPEN_TEMPLATE.format(
        since="2026-11-17T10:00:00Z"
    )


def test_no_journal_says_so_instead_of_showing_zeros():
    view = to_storage_view(_status(journal_open=False))
    assert [fact.value for fact in view.journal] == [admin_copy.STORAGE_NO_JOURNAL]


def test_held_back_sentence_only_when_non_zero():
    assert to_storage_view(_status()).notice == ""
    notice = to_storage_view(_status(held_entries=2, held_files=1)).notice
    assert "2" in notice and "1" in notice and "operator" in notice
    assert to_storage_view(_status(held_files=1)).notice != ""


def test_counters_and_keyed_rows():
    view = to_storage_view(
        _status(
            retries={"b_op:not_sent": 2, "a_op:dead_stream": 1},
            exhausted={"admit_usage:outcome_unknown": 1},
            breaker_opens=4,
            journal_appended=1200,
        )
    )
    counters = {fact.label: fact.value for fact in view.counters}
    assert counters[admin_copy.STORAGE_LABEL_BREAKER_OPENS] == "4"
    assert counters[admin_copy.STORAGE_LABEL_APPENDED] == "1,200"
    assert [(r.operation, r.failure_class, r.count) for r in view.retries] == [
        ("a_op", "dead_stream", "1"),
        ("b_op", "not_sent", "2"),
    ]
    assert [(r.operation, r.failure_class) for r in view.exhausted] == [
        ("admit_usage", "outcome_unknown")
    ]


# --- state: load() ---------------------------------------------------------------


def _signed_in() -> AdminState:
    state = AdminState(_reflex_internal_init=True)
    state.token_input = _TOKEN
    type(state).event_handlers["authenticate"].fn(state)
    assert state.authenticated
    return state


def _load(state: AdminState) -> None:
    asyncio.run(type(state).event_handlers["load"].fn(state))


@pytest.fixture
def console(monkeypatch):
    """Every read `load()` makes except the Storage one, stubbed empty."""
    monkeypatch.setattr(settings, "ADMIN_TOKEN", _TOKEN)
    monkeypatch.setattr(admin_state_mod, "usage_snapshot", lambda: [])
    monkeypatch.setattr(admin_state_mod, "list_action_decisions", lambda **_kw: [])
    monkeypatch.setattr(
        admin_state_mod, "count_action_decisions", lambda: {"allow": 0, "flag": 0, "deny": 0}
    )
    calls = {"summary_raises": None}

    def summary(row_limit, ranked_limit):
        if calls["summary_raises"] is not None:
            raise calls["summary_raises"]
        figures = {name: 0 for name in database.SUMMARY_FIGURES}
        figures.update(
            rows=[], top_models=[], top_users=[], top_pii_entities=[]
        )
        return database.SummarySnapshot(figures=figures, errors={})

    monkeypatch.setattr(admin_state_mod, "summary_snapshot", summary)
    return calls


def test_load_fills_the_storage_view_from_storage_status(console):
    storage_counters.retry("op", "not_sent")
    state = _signed_in()
    _load(state)
    assert state.storage_error == "" and state.storage_state == STORAGE_STATE_READY
    assert state.storage_verdict == admin_copy.STORAGE_VERDICT_CLOSED
    assert state.storage_caption.startswith("This process: ")
    assert [(r.operation, r.count) for r in state.storage_retries] == [("op", "1")]


def test_a_failed_summary_read_still_refreshes_storage(console):
    console["summary_raises"] = RuntimeError("summary down")
    state = _signed_in()
    _load(state)
    assert state.error  # the summary's own fault
    assert state.storage_error == "" and state.storage_verdict


def test_a_failing_storage_read_sets_only_storage_error(console, monkeypatch):
    def broken():
        raise RuntimeError("no status")

    monkeypatch.setattr(admin_state_mod, "storage_status", broken)
    state = _signed_in()
    _load(state)
    assert admin_copy.READ_LABEL_STORAGE in state.storage_error
    assert state.storage_state == STORAGE_STATE_FAULT
    assert state.error == "" and state.usage_error == ""


def test_sign_out_clears_the_storage_view(console):
    state = _signed_in()
    _load(state)
    assert state.storage_verdict
    type(state).event_handlers["sign_out"].fn(state)
    assert state.storage_verdict == "" and state.storage_breaker == []
    assert state.storage_retries == [] and state.storage_error == ""


# --- read-only by construction -------------------------------------------------------


def test_the_console_reaches_no_journal_drainer_or_counters_module():
    import chat_ui.chat_ui.admin_formatting as admin_formatting_mod

    for module in (admin_state_mod, admin_formatting_mod):
        for name in (
            "insert_audit_log", "audit_journal", "journal_drainer", "storage_counters",
            "drain_journal_entry",
        ):
            assert not hasattr(module, name), (module.__name__, name)


def test_the_component_imports_only_what_a_view_may():
    source = (_REPO / "chat_ui" / "chat_ui" / "components" / "storage.py").read_text(
        encoding="utf-8"
    )
    modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module)
    assert modules == {
        "reflex", "chat_ui", "chat_ui.admin_state", "chat_ui.components.admin_shell",
    }
