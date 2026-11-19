"""Progress line, live answer and reasoning block in the chat UI (PRD-021 STORY-012).

Copy vocabulary (T4), the pure word rule, the browser tick script (run under
node when it is on PATH), the reasoning block's in-memory-only life (D8), and a
render probe of the pending entry. The state tests use their own pipeline
stand-ins, in the style of `tests/test_chat_state_streaming.py`.
"""

import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import get_args

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.db.database import insert_user
from app.db.models import User
from app.models.schemas import QuerySuccessResponse
from app.services import chat_sessions
from app.services.action_classifiers import OperationKind
from app.services.delivery import PHASE_NAMES, STAGE_NAMES
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import OpenRouterError

import chat_ui.chat_ui.state as chat_state_mod
from chat_ui.chat_ui import copy, progress
from chat_ui.chat_ui.models import ChatMessage
from chat_ui.chat_ui.progress import PROGRESS_TICK_JS, progress_word
from chat_ui.chat_ui.state import ChatState, _to_chat_message, _to_stored_message

REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]


# --- Copy (T4) -------------------------------------------------------------


def test_every_stage_and_phase_has_a_word():
    # PRD-021 T4: an event name with no copy fails here, not on a user's screen.
    assert set(copy.PROGRESS_STAGE_WORDS) == set(STAGE_NAMES)
    # `preparing_action` is a template over the closed kind set, below.
    assert set(copy.PROGRESS_PHASE_WORDS) == set(PHASE_NAMES) - {"preparing_action"}
    for word in (*copy.PROGRESS_STAGE_WORDS.values(), *copy.PROGRESS_PHASE_WORDS.values()):
        assert word


def test_every_operation_kind_has_a_word():
    kinds = get_args(OperationKind)
    assert set(copy.PROGRESS_KIND_WORDS) == set(kinds)
    for kind in kinds:
        assert progress_word("", "preparing_action", kind) == (
            copy.PROGRESS_PREPARING_TEMPLATE.format(kind=copy.PROGRESS_KIND_WORDS[kind])
        )


def test_waiting_reuses_the_pending_indicator_text():
    assert copy.PROGRESS_PHASE_WORDS["waiting"] is copy.PENDING_INDICATOR_TEXT
    assert progress_word("", "", "") == copy.PENDING_INDICATOR_TEXT


def test_the_words_of_the_prd_table_render_exactly():
    # PRD-021 7.1.
    assert progress_word("checking_permissions", "", "") == "Checking permissions"
    assert progress_word("", "waiting", "") == "Waiting on the model"
    assert progress_word("", "thinking", "") == "Thinking"
    assert progress_word("", "writing", "") == "Writing"
    assert progress_word("", "preparing_action", "shell") == "Preparing an action: run a command"
    assert progress_word("masking_output", "", "") == "Masking personal data in the answer"
    assert progress_word("masking_input", "", "") == "Masking personal data"


def test_an_unknown_kind_falls_back_and_a_raw_tool_name_never_shows():
    word = progress_word("", "preparing_action", "bogus_tool_name")
    assert word == "Preparing an action: use a tool"
    assert "bogus_tool_name" not in word


def test_word_precedence():
    # A late stage beats a stale model phase.
    assert progress_word("masking_output", "writing", "") == copy.PROGRESS_STAGE_WORDS["masking_output"]
    assert (
        progress_word("evaluating_actions", "preparing_action", "sql")
        == copy.PROGRESS_STAGE_WORDS["evaluating_actions"]
    )
    # Otherwise the phase beats an early stage (step 7 emits `waiting` on entry).
    assert progress_word("checking_usage", "thinking", "") == "Thinking"
    # Otherwise the stage, then waiting.
    assert progress_word("checking_usage", "", "") == copy.PROGRESS_STAGE_WORDS["checking_usage"]
    assert progress_word("nonsense", "nonsense", "") == copy.PENDING_INDICATOR_TEXT


def test_every_progress_string_is_english_copy():
    strings = [
        *copy.PROGRESS_STAGE_WORDS.values(),
        *copy.PROGRESS_PHASE_WORDS.values(),
        *copy.PROGRESS_KIND_WORDS.values(),
        copy.PROGRESS_KIND_FALLBACK,
        copy.PROGRESS_PREPARING_TEMPLATE,
        copy.PROGRESS_ELAPSED_TEMPLATE,
        copy.REASONING_LABEL,
        copy.REASONING_NOT_SAVED,
        copy.REASONING_SHOW,
        copy.REASONING_HIDE,
    ]
    for text in strings:
        assert text
        assert all(ord(c) < 128 or c == "—" for c in text), text
    assert copy.REASONING_LABEL == "Model reasoning — not checked as an answer"
    assert copy.REASONING_NOT_SAVED == "Not saved with the chat"
    # Whatever progress_word can return is a copy.py constant or its template.
    pool = set(copy.PROGRESS_STAGE_WORDS.values()) | set(copy.PROGRESS_PHASE_WORDS.values())
    pool |= {
        copy.PROGRESS_PREPARING_TEMPLATE.format(kind=k)
        for k in [*copy.PROGRESS_KIND_WORDS.values(), copy.PROGRESS_KIND_FALLBACK]
    }
    for stage in ("", *STAGE_NAMES):
        for phase in ("", *PHASE_NAMES):
            for action in ("", "x", *get_args(OperationKind)):
                assert progress_word(stage, phase, action) in pool


def test_the_progress_module_has_no_reflex_import():
    source = Path(progress.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+reflex", source, re.M)


def test_the_entry_components_never_name_a_grant():
    # PRD-021 binding: the UI tests the text, never the permission.
    pattern = re.compile(r"authz|\bholds\(|stream:realtime|reasoning:view")
    for name in ("bubbles.py", "chat.py", "progress_line.py"):
        source = (REPO_ROOT / "chat_ui" / "chat_ui" / "components" / name).read_text(encoding="utf-8")
        assert not pattern.search(source), name


def test_no_new_animation_in_the_theme():
    from chat_ui.chat_ui import theme

    keyframes = re.findall(r"@keyframes\s+([\w-]+)", theme.GLOBAL_CSS)
    # PRD-021 STORY-012: the existing pulse is reused; nothing is added.
    assert sorted(keyframes) == ["hx-enter", "hx-pulse"]


# --- The tick script (node) -------------------------------------------------

_NODE = shutil.which("node")

_DRIVER = r"""
function mkEl(word) {
  const attrs = {'data-sent-at': '1', 'data-since': '1', 'data-word': word};
  const w = {_t: word, writes: 0, get textContent() { return this._t; },
             set textContent(v) { this._t = v; this.writes++; }};
  const s = {_t: '', get textContent() { return this._t; }, set textContent(v) { this._t = v; }};
  const el = {getAttribute: (k) => attrs[k], set: (k, v) => { attrs[k] = v; },
              querySelector: (sel) => sel === '[data-hx-word]' ? w : sel === '[data-hx-secs]' ? s : null};
  const root = {present: true, querySelector: (sel) => root.present ? el : null};
  return {el, w, s, root};
}
"""


def _node(scenario: str):
    if _NODE is None:
        pytest.skip("node is not on PATH")
    script = PROGRESS_TICK_JS + _DRIVER + scenario
    proc = subprocess.run([_NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_tick_a_flickering_word_is_never_shown():
    out = _node(
        """
        const m = mkEl('Waiting on the model');
        hxProgressTick(0, m.root);
        m.el.set('data-word', 'Checking permissions'); m.el.set('data-since', '2');
        hxProgressTick(10, m.root);
        m.el.set('data-word', 'Waiting on the model'); m.el.set('data-since', '3');
        hxProgressTick(200, m.root);
        hxProgressTick(600, m.root);
        console.log(JSON.stringify({text: m.w.textContent, writes: m.w.writes}));
        """
    )
    assert out == {"text": "Waiting on the model", "writes": 0}


def test_tick_a_word_stable_for_300ms_is_shown_and_a_moving_target_restarts_it():
    out = _node(
        """
        const m = mkEl('Waiting on the model');
        hxProgressTick(0, m.root);
        m.el.set('data-word', 'Thinking'); m.el.set('data-since', '2');
        hxProgressTick(100, m.root);
        hxProgressTick(399, m.root);
        const early = m.w.textContent;
        hxProgressTick(400, m.root);
        const shown = m.w.textContent;
        m.el.set('data-word', 'Writing'); m.el.set('data-since', '3');
        hxProgressTick(500, m.root);
        m.el.set('data-word', 'Preparing'); m.el.set('data-since', '4');
        hxProgressTick(700, m.root);
        hxProgressTick(900, m.root);
        const mid = m.w.textContent;
        hxProgressTick(1000, m.root);
        console.log(JSON.stringify({early, shown, mid, last: m.w.textContent}));
        """
    )
    assert out == {
        "early": "Waiting on the model",
        "shown": "Thinking",
        "mid": "Thinking",
        "last": "Preparing",
    }


def test_tick_seconds_go_0_1_2_and_a_new_send_resets_them():
    out = _node(
        """
        const m = mkEl('Waiting on the model');
        const seen = [];
        for (const t of [5000, 5500, 6000, 6900, 7000]) {
          hxProgressTick(t, m.root); seen.push(m.s.textContent);
        }
        m.el.set('data-sent-at', '2');
        hxProgressTick(9000, m.root); seen.push(m.s.textContent);
        hxProgressTick(10000, m.root); seen.push(m.s.textContent);
        console.log(JSON.stringify(seen));
        """
    )
    assert out == [f" · {n} s" for n in (0, 0, 1, 1, 2, 0, 1)]


def test_tick_is_a_no_op_without_the_entry_and_the_word_node_is_written_only_on_a_word_change():
    out = _node(
        """
        const m = mkEl('Waiting on the model');
        m.root.present = false;
        hxProgressTick(0, m.root);
        m.root.present = true;
        for (let t = 0; t <= 3000; t += 100) hxProgressTick(t, m.root);
        console.log(JSON.stringify({writes: m.w.writes, secs: m.s.textContent}));
        """
    )
    # The seconds ticked; the aria-live word node was never written.
    assert out == {"writes": 0, "secs": " · 3 s"}


# --- Render probe ------------------------------------------------------------

_PROBE = r"""
import json
from chat_ui.components import bubbles
from chat_ui.components.chat import message_bubble
from chat_ui.state import ChatState

pending = str(bubbles.render_pending_indicator().render())
bubble = str(message_bubble(ChatState.messages[0], 0).render())
no_index = str(message_bubble(ChatState.messages[0]).render())
print(json.dumps({"pending": pending, "bubble": bubble, "no_index": no_index}))
"""


@pytest.fixture(scope="module")
def probe():
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(REPO_ROOT / "chat_ui"),
        env={**os.environ, "PYTHONPATH": os.pathsep.join(_PYTHONPATH)},
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"render probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_pending_entry_keeps_its_tag_and_slot(probe):
    assert '"SENDING"' in probe["pending"]
    assert "hx-entry" in probe["pending"]


def test_aria_live_wraps_the_word_and_the_seconds_are_a_hidden_sibling(probe):
    pending = probe["pending"]
    assert len(re.findall(r"aria-?[lL]ive", pending)) == 1
    assert "data-hx-word" in pending and "data-hx-secs" in pending
    secs_at = pending.find("data-hx-secs")
    around = pending[max(0, secs_at - 300) : secs_at + 300]
    assert re.search(r"aria-?[hH]idden", around)
    assert pending.find("data-hx-word") < secs_at


def test_live_text_uses_the_prose_face_and_the_pulse_is_the_only_motion(probe):
    pending = probe["pending"]
    assert "live_text" in pending and "live_reasoning" in pending
    assert '"whiteSpace"] : "pre-wrap"' in pending
    assert "animation" not in pending and "keyframes" not in pending
    assert pending.count("hx-pulse") == 2  # the rail glyph and the word


def test_the_reasoning_block_is_a_real_button_with_aria(probe):
    bubble = probe["bubble"]
    assert "reasoning_open" in bubble
    assert re.search(r"aria-?[eE]xpanded", bubble)
    assert "hx-reasoning-" in bubble
    assert "toggle_reasoning" in bubble
    # Without an index there is nothing to toggle, so no control is offered.
    assert "toggle_reasoning" not in probe["no_index"]


def test_the_page_hook_installs_one_interval_and_cleans_up():
    source = (REPO_ROOT / "chat_ui/chat_ui/components/progress_line.py").read_text(encoding="utf-8")
    assert "clearInterval" in source and "hxProgressTick(performance.now()" in source
    assert "def add_hooks" in source and "def add_custom_code" in source


# --- Reasoning in memory only (D8) -------------------------------------------

_USER = "juan@empresa.com"
_TOKEN = "test-user-token"
_SECRET = "secret thought"
_ANSWER = "The final answer."


@pytest.fixture
def seeded(temp_db):
    insert_user(User(user_id=_USER, role="user", token_hash=hash_token(_TOKEN)))
    return temp_db


def _state() -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = _USER
    state._token = _TOKEN
    return state


async def _send(state: ChatState, text: str) -> None:
    state.input_text = text
    await type(state).event_handlers["send"].fn(state)


def _install(monkeypatch, script, fault=None):
    def _fake(*args, sink=None, **kwargs):
        if sink is not None:
            script(sink)
        if fault is not None:
            raise fault
        return QuerySuccessResponse(
            response=_ANSWER, audit_id=1, audit_ref="0" * 32, model_used="gpt-4", tokens_used=1
        )

    monkeypatch.setattr(chat_state_mod, "run_query", _fake)
    monkeypatch.setattr(chat_state_mod, "run_conversation", _fake)


def _think(sink):
    sink.phase("thinking")
    sink.reasoning(_SECRET)
    time.sleep(0.15)
    sink.content("Hel")
    time.sleep(0.15)


@pytest.mark.asyncio
async def test_reasoning_rides_the_final_bubble_in_memory_and_is_never_stored(seeded, monkeypatch):
    _install(monkeypatch, _think)
    state = _state()
    await _send(state, "hi")

    bubble = state.messages[-1]
    assert bubble.kind == "assistant"
    assert bubble.reasoning == _SECRET
    assert bubble.reasoning_open is False  # collapsed by default
    assert state.live_reasoning == "" and state.live_text == ""

    identity = Identity(user_id=_USER, role="user")
    rows = chat_sessions.messages_for(identity, state.active_session_id)
    assert rows
    assert all(_SECRET not in repr(dataclasses.asdict(r)) for r in rows)

    from app.db.database import get_connection

    conn = get_connection()
    try:
        raw = repr(conn.execute("SELECT * FROM chat_messages").fetchall())
    finally:
        conn.close()
    assert _SECRET not in raw

    stored = _to_stored_message(bubble, "s1")
    assert "reasoning" not in dataclasses.asdict(stored)
    assert _SECRET not in repr(stored)
    # A restored transcript shows no reasoning.
    assert all(_to_chat_message(r).reasoning == "" for r in rows)


@pytest.mark.asyncio
async def test_a_fault_bubble_never_carries_reasoning(seeded, monkeypatch):
    _install(monkeypatch, _think, fault=OpenRouterError("boom"))
    state = _state()
    await _send(state, "hi")
    bubble = state.messages[-1]
    assert bubble.kind == "upstream_error"
    assert bubble.reasoning == ""
    assert state.live_reasoning == ""


def test_toggle_reasoning_flips_the_block_and_marks_messages_dirty():
    state = _state()
    state.messages = [ChatMessage(kind="assistant", content="a", reasoning="r")]
    state.dirty_vars.clear()
    handler = type(state).event_handlers["toggle_reasoning"]
    handler.fn(state, 0)
    assert state.messages[0].reasoning_open is True
    # reflex 0.9.6.post1 istate/proxy.py: the item is a MutableProxy, so an
    # attribute set marks the list dirty (no model_copy needed).
    assert "messages" in state.dirty_vars
    handler.fn(state, 0)
    assert state.messages[0].reasoning_open is False
    handler.fn(state, 7)  # out of range: ignored
    handler.fn(state, -1)


def test_the_progress_word_var_follows_the_three_vars():
    state = _state()
    state.progress_phase = "thinking"
    assert state.progress_word == "Thinking"
    state.progress_stage = "masking_output"
    assert state.progress_word == copy.PROGRESS_STAGE_WORDS["masking_output"]
