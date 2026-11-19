"""ChatState consumes the pipeline's delivery events (PRD-021 STORY-011).

The pipeline here is a plain function that drives a `QueueSink` from the
executor thread, as the real one does; the real `run_in_pipeline`, the real
`ChatState._do_send` and the real database run around it. What is proved: one
sink reaches both branches, events fold into the live vars in windows of at most
10 per second (D19), the final bubble replaces the live entry in one delta, and
a mid-stream fault shows today's `upstream_error` bubble with no partial text
(D16, D8). The real pipeline through a real sink is STORY-014/015's.

Its own helpers rather than imports from `tests/test_chat_state.py`.
"""

import asyncio
import os
import time

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.config import settings
from app.db.database import insert_user
from app.db.models import User
from app.models.schemas import QuerySuccessResponse
from app.services import chat_sessions
from app.services.delivery import (
    CommittedEvent,
    ContentEvent,
    PhaseEvent,
    QueueSink,
    ReasoningEvent,
    StageEvent,
)
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import OpenRouterError

import chat_ui.chat_ui.state as chat_state_mod
from chat_ui.chat_ui.live_batch import END, batches, fold
from chat_ui.chat_ui.state import ChatState

_AUDIT_REF = "0" * 32
_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_ANSWER = "The final answer."

_LIVE_DEFAULTS = {
    "progress_stage": "",
    "progress_phase": "",
    "progress_action": "",
    "progress_since": 0.0,
    "progress_sent_at": 0.0,
    "live_text": "",
    "live_reasoning": "",
}


@pytest.fixture
def temp_db(temp_db):
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return temp_db


def _make_state() -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = _AUTH_USER_ID
    state._token = _AUTH_TOKEN
    return state


async def _send(state: ChatState, text: str) -> None:
    state.input_text = text
    handler = type(state).event_handlers["send"]
    await handler.fn(state)


def _live(state: ChatState) -> dict:
    return {name: getattr(state, name) for name in _LIVE_DEFAULTS}


def _success() -> QuerySuccessResponse:
    return QuerySuccessResponse(
        response=_ANSWER, audit_id=1, audit_ref=_AUDIT_REF, model_used="gpt-4", tokens_used=1
    )


def _install(monkeypatch, script, seen=None):
    """`script(sink)` runs on the executor thread for either entry point; its
    return value (or None -> a success) is the pipeline's result. `seen` records
    (entry point, sink) per call. Both fakes accept `sink`."""

    def _make(name):
        def _fake(*args, sink=None, **kwargs):
            if seen is not None:
                seen.append((name, sink))
            if sink is not None:
                script(sink)
            return _success()

        return _fake

    monkeypatch.setattr(chat_state_mod, "run_query", _make("run_query"))
    monkeypatch.setattr(chat_state_mod, "run_conversation", _make("run_conversation"))


def _record_batches(monkeypatch):
    """Wraps `_apply_batch`, calling through; records (monotonic time, events,
    state snapshot) per window."""
    record = []
    original = ChatState._apply_batch

    async def _spy(self, batch):
        await original(self, batch)
        record.append((time.monotonic(), list(batch), _live(self)))

    monkeypatch.setattr(ChatState, "_apply_batch", _spy)
    return record


def _scripted_phases(sink):
    sink.stage("checking_permissions")
    time.sleep(0.15)
    sink.phase("waiting")
    time.sleep(0.15)
    sink.phase("thinking")
    time.sleep(0.15)
    sink.phase("writing")
    time.sleep(0.15)


# (a) ----------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("two_sends", [False, True], ids=["run_query", "run_conversation"])
async def test_stage_and_phase_words_arrive_in_order_through_both_branches(
    temp_db, monkeypatch, two_sends
):
    seen = []
    _install(monkeypatch, _scripted_phases, seen)
    record = _record_batches(monkeypatch)

    state = _make_state()
    await _send(state, "first")
    if two_sends:
        record.clear()
        seen.clear()
        await _send(state, "second")

    assert [name for name, _ in seen] == [
        "run_conversation" if two_sends else "run_query"
    ]
    assert all(isinstance(sink, QueueSink) for _, sink in seen)

    phases = [
        event.name
        for _, batch, _ in record
        for event in batch
        if isinstance(event, PhaseEvent)
    ]
    assert phases == ["waiting", "thinking", "writing"]
    snapshots = [snap["progress_phase"] for _, _, snap in record if snap["progress_phase"]]
    assert snapshots[0] == "waiting" and snapshots[-1] == "writing"
    assert all(not snap["live_text"] and not snap["live_reasoning"] for _, _, snap in record)


# (b) ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_off_still_shows_stage_words_and_the_same_bubble(
    temp_db, monkeypatch
):
    monkeypatch.setattr(settings, "STREAMING_ENABLED", False)

    def _stages_only(sink):
        sink.stage("checking_permissions")
        time.sleep(0.12)
        sink.stage("masking_output")

    _install(monkeypatch, _stages_only)
    record = _record_batches(monkeypatch)
    state = _make_state()
    await _send(state, "hello")
    stages = [e.name for _, b, _ in record for e in b if isinstance(e, StageEvent)]
    assert stages == ["checking_permissions", "masking_output"]
    with_sink = state.messages[-1]

    # A pipeline that ignores the sink produces today's bubble.
    def _ignores_sink(*args, **kwargs):
        return _success()

    monkeypatch.setattr(chat_state_mod, "run_query", _ignores_sink)
    other = _make_state()
    await _send(other, "hello")
    assert other.messages[-1].kind == with_sink.kind
    assert other.messages[-1].content == with_sink.content == _ANSWER


@pytest.mark.asyncio
async def test_a_pipeline_that_ignores_the_sink_emits_no_deltas(temp_db, monkeypatch):
    monkeypatch.setattr(chat_state_mod, "run_query", lambda *a, **k: _success())
    record = _record_batches(monkeypatch)
    state = _make_state()
    await _send(state, "hello")
    assert record == []
    assert state.messages[-1].content == _ANSWER


# (c) ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_hundred_tokens_a_second_makes_at_most_ten_updates_a_second(
    temp_db, monkeypatch
):
    emitted = []

    def _flood(sink):
        end = time.monotonic() + 1.5
        i = 0
        while time.monotonic() < end:
            token = f"t{i} "
            emitted.append(token)
            sink.content(token)
            i += 1
            time.sleep(0.005)

    _install(monkeypatch, _flood)
    record = _record_batches(monkeypatch)
    state = _make_state()
    started = time.monotonic()
    await _send(state, "go")
    elapsed = time.monotonic() - started

    assert len(record) >= 5
    assert len(record) <= elapsed / 0.1 + 2
    span = record[-1][0] - record[0][0]
    assert (len(record) - 1) / max(span, 0.001) <= 12
    text = "".join(e.text for _, b, _ in record for e in b if isinstance(e, ContentEvent))
    assert text == "".join(emitted)


# (d) ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_mid_stream_fault_shows_the_upstream_error_bubble_and_no_partial_text(
    temp_db, monkeypatch
):
    partial = "PARTIAL-TEXT-SECRET"

    def _faulty(sink):
        sink.content(partial)
        sink.reasoning("PARTIAL-REASONING-SECRET")
        time.sleep(0.25)
        raise OpenRouterError("boom")

    monkeypatch.setattr(chat_state_mod, "run_query", lambda *a, sink=None, **k: _faulty(sink))
    record = _record_batches(monkeypatch)
    state = _make_state()
    await _send(state, "hello")

    assert any(snap["live_text"] == partial for _, _, snap in record)
    last = state.messages[-1]
    assert last.kind == "upstream_error"
    assert last.detail == "boom"
    for message in state.messages:
        for value in vars(message).values():
            assert "PARTIAL" not in str(value)
    identity = Identity(user_id=_AUTH_USER_ID, role="user")
    rows = chat_sessions.messages_for(identity, state.active_session_id)
    assert rows
    for row in rows:
        assert "PARTIAL" not in repr(row)
    assert _live(state) == _LIVE_DEFAULTS
    assert state.pending is False


# (e) ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_clears_the_live_vars_and_persists_one_assistant_row(
    temp_db, monkeypatch
):
    def _script(sink):
        sink.phase("thinking")
        sink.reasoning("secret reasoning")
        sink.content("Hel")
        time.sleep(0.15)
        sink.content("lo")
        time.sleep(0.15)

    _install(monkeypatch, _script)
    record = _record_batches(monkeypatch)
    state = _make_state()
    await _send(state, "hi")

    # Non-zero during the stream (set in the claim block, survives the user bubble).
    assert record and all(snap["progress_sent_at"] > 0 for _, _, snap in record)
    assert any(snap["live_reasoning"] == "secret reasoning" for _, _, snap in record)
    assert _live(state) == _LIVE_DEFAULTS
    assert state.messages[-1].content == _ANSWER
    identity = Identity(user_id=_AUTH_USER_ID, role="user")
    rows = chat_sessions.messages_for(identity, state.active_session_id)
    assistants = [r for r in rows if r.content == _ANSWER]
    assert len(assistants) == 1
    assert all("secret reasoning" not in repr(r) for r in rows)


@pytest.mark.asyncio
async def test_progress_sent_at_survives_the_users_own_bubble(temp_db, monkeypatch):
    original = ChatState._append_and_persist
    seen = {}

    async def _spy(self, bubble, identity, session_id):
        await original(self, bubble, identity, session_id)
        seen.setdefault(bubble.kind, self.progress_sent_at)

    monkeypatch.setattr(ChatState, "_append_and_persist", _spy)
    _install(monkeypatch, lambda sink: None)
    state = _make_state()
    before = time.time()
    await _send(state, "hi")
    assert seen["user"] >= before  # the clear did not run for the user bubble
    assert state.progress_sent_at == 0.0


@pytest.mark.asyncio
async def test_clear_live_resets_all_seven_vars(temp_db):
    state = _make_state()
    state.progress_stage = "x"
    state.progress_phase = "writing"
    state.progress_action = "k"
    state.progress_since = 1.0
    state.progress_sent_at = 2.0
    state.live_text = "t"
    state.live_reasoning = "r"
    state._clear_live()
    assert _live(state) == _LIVE_DEFAULTS


# pure ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batches_ends_promptly_with_no_events():
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    loop.call_later(0.05, queue.put_nowait, END)
    started = time.monotonic()
    got = [b async for b in batches(queue, window_s=1.0)]
    assert got == []
    assert time.monotonic() - started < 0.5


@pytest.mark.asyncio
async def test_batches_ends_the_window_early_on_end_and_yields_leftovers():
    queue = asyncio.Queue()
    queue.put_nowait(ContentEvent("a"))
    queue.put_nowait(END)
    queue.put_nowait(ContentEvent("late"))
    started = time.monotonic()
    got = [b async for b in batches(queue, window_s=1.0)]
    assert time.monotonic() - started < 0.5
    assert got == [[ContentEvent("a")], [ContentEvent("late")]]


@pytest.mark.asyncio
async def test_batches_groups_a_burst_into_one_window():
    queue = asyncio.Queue()
    for i in range(5):
        queue.put_nowait(ContentEvent(str(i)))
    loop = asyncio.get_running_loop()
    loop.call_later(0.05, queue.put_nowait, END)
    got = [b async for b in batches(queue, window_s=0.2)]
    assert len(got) == 1 and len(got[0]) == 5


def test_fold_keeps_progress_since_on_a_repeated_stage_and_ignores_committed():
    out = fold(
        [StageEvent("checking_usage"), CommittedEvent("c1")],
        stage="checking_usage",
        phase="",
        now=5.0,
    )
    assert out == {}
    out = fold(
        [
            StageEvent("masking_output"),
            PhaseEvent("preparing_action", "send_email"),
            ContentEvent("a"),
            ContentEvent("b"),
            ReasoningEvent("r"),
        ],
        stage="checking_usage",
        phase="",
        now=7.0,
    )
    assert out == {
        "progress_stage": "masking_output",
        "progress_phase": "preparing_action",
        "progress_action": "send_email",
        "progress_since": 7.0,
        "live_text": "ab",
        "live_reasoning": "r",
    }
