"""PRD-022 STORY-016 (F8, F9, AC 1, 3, 4): the admin console's Providers view.

Non-`db`: `health.providers_status()` reads memory only, so `AdminState.load()`
needs no database for this view. The component is not built in-process (the
note in `tests/test_usage_view.py`); it is covered by
`tests/test_chat_ui_startup_guard.py` (the probe imports `chat_ui.chat_ui`,
which registers the page) and `tests/test_admin_shell.py` (route, view key and
the sixth masthead peer), plus the source checks below. The Register's attempt
column and request-id search are in `tests/test_register.py`.
"""

import ast
import os
import sys
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from app.db import database
from app.services.circuit_breaker import BreakerStatus
from app.services.upstream import health
from app.services.upstream.health import ProviderCounters, ProvidersStatus
from app.services.upstream.types import UpstreamError
import chat_ui.chat_ui.admin_state as admin_state_mod
from chat_ui.chat_ui import admin_copy
from chat_ui.chat_ui.admin_formatting import to_providers_view
from chat_ui.chat_ui.admin_state import (
    PROVIDERS_STATE_FAULT,
    PROVIDERS_STATE_READY,
    AdminState,
)
from tests._providers import provider_file  # noqa: F401  (fixture)
from tests.test_storage_view import _load, _signed_in, console  # noqa: F401

_REPO = Path(__file__).resolve().parents[1]
_SINCE = "2026-11-20T10:00:00Z"

_YAML = """
version: 1
default_model: a/m
providers:
  - name: alpha
    label: Alpha
    type: openai_compatible
    base_url: http://127.0.0.1:9/v1
    insecure_http: true
    key_env: PROVIDERS_VIEW_KEY
    byok: false
    usage_missing: estimate
    models:
      - id: a/m
        upstream: up-a
        capabilities: {tools: true, streaming: true, reasoning: true}
  - name: beta
    label: Beta
    type: openai_compatible
    base_url: http://127.0.0.1:9/v1
    insecure_http: true
    key_env: PROVIDERS_VIEW_KEY
    byok: false
    usage_missing: estimate
    models:
      - id: b/m
        upstream: up-b
        capabilities: {tools: true, streaming: true, reasoning: true}
"""


def _reading(state="closed", failures=0, last=None, retry=None):
    return BreakerStatus(
        state=state,
        since=_SINCE,
        consecutive_failures=failures,
        last_failure_class=last,
        retry_after_seconds=retry,
    )


def _status(readings, **counters):
    base = dict(attempts_failed={}, fallback_answers=0, skipped={}, breaker_opens=0)
    base.update(counters)
    return ProvidersStatus(
        instance="host:42", providers=readings, counters=ProviderCounters(**base)
    )


# --- formatting ----------------------------------------------------------------


def test_all_closed_verdict_and_card_facts():
    view = to_providers_view(_status({"alpha": _reading(), "beta": _reading()}))
    assert view.verdict == admin_copy.PROVIDERS_VERDICT_ALL_CLOSED
    assert view.caption == admin_copy.PROVIDERS_CAPTION_TEMPLATE.format(instance="host:42")
    assert [card.name for card in view.cards] == ["alpha", "beta"]
    facts = {fact.label: fact.value for fact in view.cards[0].facts}
    assert facts[admin_copy.PROVIDERS_LABEL_STATE] == "closed"
    assert facts[admin_copy.PROVIDERS_LABEL_SINCE] == _SINCE
    assert facts[admin_copy.PROVIDERS_LABEL_FAILURES] == "0"
    # Null last failure and null retry-after read as the absent mark.
    assert facts[admin_copy.PROVIDERS_LABEL_LAST_FAILURE] == "—"
    assert facts[admin_copy.PROVIDERS_LABEL_RETRY_AFTER] == "—"


@pytest.mark.parametrize("state", ["open", "half_open"])
def test_the_verdict_names_a_provider_that_is_not_closed(state):
    view = to_providers_view(
        _status(
            {
                "alpha": _reading(state, failures=5, last="timeout", retry=7),
                "beta": _reading(),
            }
        )
    )
    assert view.verdict == admin_copy.PROVIDERS_VERDICT_NOT_CLOSED_TEMPLATE.format(
        names="alpha"
    )
    facts = {fact.label: fact.value for fact in view.cards[0].facts}
    assert facts[admin_copy.PROVIDERS_LABEL_STATE] == state
    assert facts[admin_copy.PROVIDERS_LABEL_LAST_FAILURE] == "timeout"
    assert facts[admin_copy.PROVIDERS_LABEL_RETRY_AFTER] == "7 s"


def test_no_provider_says_so():
    assert (
        to_providers_view(_status({})).verdict == admin_copy.PROVIDERS_VERDICT_NONE
    )


def test_counters_split_on_the_first_colon_and_keep_a_stable_order():
    view = to_providers_view(
        _status(
            {"alpha": _reading()},
            attempts_failed={"beta:timeout": 2, "alpha:status": 1200},
            skipped={"alpha:circuit_open": 3},
            fallback_answers=4,
            breaker_opens=2,
        )
    )
    counters = {fact.label: fact.value for fact in view.counters}
    assert counters[admin_copy.PROVIDERS_LABEL_BREAKER_OPENS] == "2"
    assert counters[admin_copy.PROVIDERS_LABEL_FALLBACK_ANSWERS] == "4"
    assert [(r.provider, r.reason, r.count) for r in view.failed] == [
        ("alpha", "status", "1,200"),
        ("beta", "timeout", "2"),
    ]
    assert [(r.provider, r.reason) for r in view.skipped] == [("alpha", "circuit_open")]


def test_the_view_carries_no_error_text():
    """T10: a failure kind reaches the view, the message does not."""
    health.reset()
    health.record(
        "alpha",
        UpstreamError("secret prompt text sk-leak", kind="timeout", provider="alpha"),
    )
    try:
        view = to_providers_view(health.providers_status(["alpha"]))
    finally:
        health.reset()
    assert "secret" not in view.model_dump_json() and "sk-leak" not in view.model_dump_json()
    assert [(r.provider, r.reason) for r in view.failed] == [("alpha", "timeout")]


# --- state: load() ---------------------------------------------------------------


def test_load_fills_the_providers_view_from_providers_status(console, monkeypatch):
    seen = {}

    def status(names):
        seen["names"] = list(names)
        return _status({"alpha": _reading("open", 5, "timeout", 9)})

    monkeypatch.setattr(admin_state_mod.health, "providers_status", status)
    state = _signed_in()
    _load(state)
    assert state.providers_error == "" and state.providers_state == PROVIDERS_STATE_READY
    assert state.providers_verdict.startswith("Not closed: alpha")
    assert [card.name for card in state.providers_cards] == ["alpha"]
    assert seen["names"]  # the registry's names, as GET /providers/status passes them


def test_load_against_the_real_health_shows_an_open_provider(
    console, provider_file, monkeypatch  # noqa: F811
):
    """E2E: two registry providers, one opened by repeated recorded failures."""
    monkeypatch.setenv("PROVIDERS_VIEW_KEY", "sk-view-key")
    provider_file(_YAML)
    health.reset()
    try:
        for _ in range(20):
            health.record("alpha", UpstreamError("x", kind="timeout", provider="alpha", retryable=True))
        state = _signed_in()
        _load(state)
    finally:
        counters = health.providers_status([]).counters
        health.reset()
    assert [card.name for card in state.providers_cards] == ["alpha", "beta"]
    alpha = {f.label: f.value for f in state.providers_cards[0].facts}
    assert alpha[admin_copy.PROVIDERS_LABEL_STATE] == "open"
    assert alpha[admin_copy.PROVIDERS_LABEL_RETRY_AFTER].endswith(" s")
    assert "alpha" in state.providers_verdict
    assert counters.breaker_opens >= 1


def test_a_failed_summary_read_still_refreshes_providers(console):
    console["summary_raises"] = RuntimeError("summary down")
    state = _signed_in()
    _load(state)
    assert state.error  # the summary's own fault
    assert state.providers_error == "" and state.providers_verdict


def test_a_failing_providers_read_sets_only_providers_error(console, monkeypatch):
    def broken(names):
        raise RuntimeError("no status")

    monkeypatch.setattr(admin_state_mod.health, "providers_status", broken)
    state = _signed_in()
    _load(state)
    assert admin_copy.READ_LABEL_PROVIDERS in state.providers_error
    assert state.providers_state == PROVIDERS_STATE_FAULT
    assert state.error == "" and state.usage_error == "" and state.storage_error == ""
    assert state.storage_verdict  # Storage is unaffected


def test_sign_out_clears_the_providers_view(console):
    state = _signed_in()
    _load(state)
    assert state.providers_verdict
    type(state).event_handlers["sign_out"].fn(state)
    assert state.providers_verdict == "" and state.providers_cards == []
    assert state.providers_failed == [] and state.providers_error == ""


def test_an_unauthenticated_load_leaves_the_providers_view_empty(console):
    """AC 4: gated exactly like Storage -- the admin-token gate, then `load()`."""
    state = AdminState(_reflex_internal_init=True)
    _load(state)
    assert not state.authenticated
    assert state.providers_verdict == "" and state.providers_cards == []
    assert state.providers_caption == "" and state.providers_error == ""


# --- read-only and /stats-free by construction ------------------------------------


def test_the_console_reads_none_of_the_three_stats_only_figures():
    """The fallback figures that need SQL stay `/stats`-only (STORY-015)."""
    for name in ("fallback_answers", "failed_attempts", "answers_by_provider"):
        assert name not in {read[0] for read in admin_state_mod._READS}, name
    assert len(database.SUMMARY_FIGURES) == 16


def test_the_component_imports_only_what_a_view_may():
    source = (_REPO / "chat_ui" / "chat_ui" / "components" / "providers.py").read_text(
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
    assert "httpx" not in source and "app.routers" not in source
