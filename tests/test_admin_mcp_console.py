"""PRD-023 STORY-018 (F11): the admin console's gateway share.

With `MCP_ENABLED=true` the Actions view gains a surface filter, an "Unlinked
gateway calls" toggle and four columns, and a Skills view exists; with it off
none of that is built (D20). Components are compiled in a subprocess with
`MCP_ENABLED` in its environment (the setting is read at build time, as
`tests/test_actions_view.py` probes do); state and formatting run in-process.
No database: every read is replaced.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import chat_ui.chat_ui.admin_state as admin_state_mod  # noqa: E402
from app.config import settings  # noqa: E402
from app.db.models import ActionDecisionRow  # noqa: E402
from chat_ui.chat_ui import admin_copy  # noqa: E402
from chat_ui.chat_ui.admin_formatting import VALUE_ABSENT, to_action_rows, to_skills_view  # noqa: E402
from chat_ui.chat_ui.admin_state import AdminState, read_actions  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
_TOKEN = "mcp-console-token"


def _stored(**overrides) -> ActionDecisionRow:
    base = dict(
        timestamp="2026-11-23T10:00:00+00:00",
        audit_id=1,
        session_id=None,
        user_id="ana",
        role="user",
        tool_call_id="c1",
        tool_name="github.create_pr",
        operation_kind="exec",
        target_preview="repo",
        arguments_hash="h",
        arguments_preview=None,
        decision="allow",
        rule="mcp.default",
        reason="ok",
        granted_by=None,
        classifications="[]",
        policy_digest="d",
        id=7,
    )
    base.update(overrides)
    return ActionDecisionRow(**base)


# --- formatting ---------------------------------------------------------------


def test_gateway_row_projects_server_skills_outcome_and_link():
    (row,) = to_action_rows(
        [
            _stored(
                surface="mcp",
                mcp_server="github",
                skills='["pr", "review"]',
                outcome="forwarded",
                linked_decision_id=4,
            )
        ]
    )
    assert (row.row_id, row.mcp_server, row.skills, row.outcome) == (
        "7",
        "github",
        "pr, review",
        "forwarded",
    )
    assert (row.linked, row.linked_id) == ("#4", "4")


def test_unlinked_gateway_row_says_unlinked_and_v1_row_the_absent_mark():
    gateway, v1 = to_action_rows([_stored(surface="mcp"), _stored(id=8)])
    assert (gateway.linked, gateway.linked_id) == (admin_copy.ACTIONS_LINKED_NONE, "")
    assert (v1.linked, v1.linked_id) == (VALUE_ABSENT, "")
    assert (v1.mcp_server, v1.skills, v1.outcome) == (VALUE_ABSENT,) * 3


# --- state --------------------------------------------------------------------


class _Reads:
    def __init__(self, monkeypatch):
        self.asked: list[dict] = []
        monkeypatch.setattr(settings, "ADMIN_TOKEN", _TOKEN)
        monkeypatch.setattr(admin_state_mod, "list_action_decisions", self._list)
        monkeypatch.setattr(admin_state_mod, "count_action_decisions", lambda: {})

    def _list(self, **kwargs):
        self.asked.append(kwargs)
        return []


def _signed_in() -> AdminState:
    state = AdminState(_reflex_internal_init=True)
    state.token_input = _TOKEN
    type(state).event_handlers["authenticate"].fn(state)
    return state


def _event(state, name, *args):
    return type(state).event_handlers[name].fn(state, *args)


def _load_actions(state):
    asyncio.run(type(state).event_handlers["load_actions"].fn(state))


def test_read_actions_adds_kwargs_only_when_set(monkeypatch):
    reads = _Reads(monkeypatch)
    read_actions("deny")
    read_actions("all", surface="mcp")
    read_actions("all", unlinked=True)
    assert reads.asked == [
        {"limit": 500, "decision": "deny"},
        {"limit": 500, "decision": None, "surface": "mcp"},
        {"limit": 500, "decision": None, "linked": False},
    ]


def test_surface_chip_reads_with_the_surface(monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    reads = _Reads(monkeypatch)
    state = _signed_in()
    assert _event(state, "choose_actions_surface", "mcp") is not None
    _load_actions(state)
    assert reads.asked == [{"limit": 500, "decision": "deny", "surface": "mcp"}]
    assert state.actions_scope.endswith("gateway calls")  # no whole-table total


def test_unlinked_toggle_reads_linked_false(monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    reads = _Reads(monkeypatch)
    state = _signed_in()
    _event(state, "toggle_actions_unlinked")
    _load_actions(state)
    # The default Denied chip would hide an allowed gateway call: widened to all.
    assert state.actions_filter == "all"
    assert reads.asked == [{"limit": 500, "decision": None, "linked": False}]
    assert "unlinked gateway calls" in state.actions_scope
    _event(state, "toggle_actions_unlinked")
    assert state.actions_unlinked is False


def test_unknown_surface_changes_nothing(monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    state = _signed_in()
    assert _event(state, "choose_actions_surface", "nonsense") is None
    assert state.actions_surface == ""


def test_with_mcp_off_both_events_are_no_ops(monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", False)
    reads = _Reads(monkeypatch)
    state = _signed_in()
    assert _event(state, "choose_actions_surface", "mcp") is None
    assert _event(state, "toggle_actions_unlinked") is None
    assert (state.actions_surface, state.actions_unlinked) == ("", False)
    assert state.actions_filter == ""
    _load_actions(state)
    assert reads.asked == [{"limit": 500, "decision": "deny"}]


# --- skills -------------------------------------------------------------------


def _skill(sid, **kw):
    base = dict(
        id=sid,
        version="1",
        description="d " + sid,
        instructions="never shown",
        tools=("github.create_pr", "github.list"),
        requires=("github",),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_skills_list_from_config():
    view = to_skills_view(
        [_skill("pr"), _skill("empty", tools=(), requires=())],
        lambda perm: ("dba",) if perm == "skill:pr" else (),
        "sha256:abc",
    )
    pr, empty = view.skills
    assert (pr.tools, pr.requires, pr.roles) == (
        "github.create_pr, github.list",
        "github",
        "dba",
    )
    assert (empty.tools, empty.requires, empty.roles) == (VALUE_ABSENT,) * 3
    assert "sha256:abc" in view.caption
    assert "never shown" not in view.model_dump_json()


def test_skills_state_empty_rows_and_fault():
    state = AdminState(_reflex_internal_init=True)
    assert state.skills_state == admin_state_mod.SKILLS_STATE_EMPTY
    state.skills_rows = to_skills_view([_skill("pr")], lambda p: (), None).skills
    assert state.skills_state == admin_state_mod.SKILLS_STATE_ROWS
    state.skills_error = "boom"
    assert state.skills_state == admin_state_mod.SKILLS_STATE_FAULT


def test_load_reads_skills_only_with_mcp_on(monkeypatch):
    from app.services import mcp_config

    reads = _Reads(monkeypatch)
    del reads
    monkeypatch.setattr(admin_state_mod, "usage_snapshot", lambda: [])
    monkeypatch.setattr(
        admin_state_mod,
        "summary_snapshot",
        lambda row_limit, ranked_limit: admin_state_mod.SummarySnapshot(
            figures={
                **{n: 0 for n in admin_state_mod.SUMMARY_FIGURES},
                "rows": [],
                "top_models": [],
                "top_users": [],
                "top_pii_entities": [],
            },
            errors={},
        ),
    )
    cfg = SimpleNamespace(skills=(_skill("pr"),))
    monkeypatch.setattr(mcp_config, "get_config", lambda: cfg)
    monkeypatch.setattr(mcp_config, "mcp_config_digest", lambda: "sha256:x")
    monkeypatch.setattr(admin_state_mod.authz, "roles_holding", lambda p: ("dba",))

    monkeypatch.setattr(settings, "MCP_ENABLED", False)
    off = _signed_in()
    asyncio.run(type(off).event_handlers["load"].fn(off))
    assert off.skills_rows == [] and off.skills_error == ""

    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    on = _signed_in()
    asyncio.run(type(on).event_handlers["load"].fn(on))
    assert [s.id for s in on.skills_rows] == ["pr"]
    assert on.skills_rows[0].roles == "dba"


# --- components (subprocess; MCP_ENABLED is read at build time) ---------------

_PROBE = r"""
import json, sys
import reflex as rx
from chat_ui.admin_state import AdminState
from chat_ui.components.actions import actions
from chat_ui.components.admin_shell import admin_masthead, VIEW_REGISTER
from chat_ui.components.skills import skills
out = {
    "actions": str(actions()),
    "masthead": str(admin_masthead(VIEW_REGISTER)),
    "skills": str(skills()),
}
print(json.dumps(out))
"""


def _probe(mcp: bool) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(REPO_ROOT / "chat_ui"),
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join([str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]),
            "ADMIN_TOKEN": os.environ.get("ADMIN_TOKEN", "test-token"),
            "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "test-key"),
            "MCP_ENABLED": "true" if mcp else "false",
        },
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"console probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def on():
    return _probe(True)


@pytest.fixture(scope="module")
def off():
    return _probe(False)


_MCP_STRINGS = (
    admin_copy.COLUMN_SERVER,
    admin_copy.COLUMN_OUTCOME,
    admin_copy.COLUMN_LINKED,
    admin_copy.ACTIONS_SURFACE_MCP_LABEL,
    admin_copy.ACTIONS_UNLINKED_LABEL,
    "action-",
)


def test_mcp_on_actions_view_has_filters_and_columns(on):
    for text in _MCP_STRINGS:
        assert text in on["actions"], text
    assert admin_copy.VIEW_SKILLS_LABEL in on["masthead"]
    assert "/admin/skills" in on["masthead"]


def test_mcp_off_view_is_unchanged(off):
    for text in _MCP_STRINGS:
        assert text not in off["actions"], text
    assert "101rem" not in off["actions"]
    assert "73rem" in off["actions"]
    assert "/admin/skills" not in off["masthead"]


def test_mcp_table_scrolls_inside_its_container(on):
    assert "101rem" in on["actions"]
    assert "hx-scroll" in on["actions"]
    assert "overflow" in on["actions"]
    # Skills are stacked blocks: no fixed minimum width to scroll against.
    assert not re.search(r'"minWidth"\] : "[1-9]', on["skills"])  # fault panel's is 0


def test_skills_empty_state(on):
    assert admin_copy.EMPTY_SKILLS_TITLE in on["skills"]
    assert "MCP_CONFIG_FILE" in on["skills"]


def test_skills_page_is_registered_only_with_mcp_on():
    source = (REPO_ROOT / "chat_ui" / "chat_ui" / "chat_ui.py").read_text(encoding="utf-8")
    guard = source.index("if settings.MCP_ENABLED:\n    app.add_page(\n        admin_skills_page")
    assert guard > source.index("route=ROUTE_PROVIDERS")
