"""PRD-021 STORY-005: `app/services/delivery.py` -- vocabularies, Visibility, QueueSink.

Sections 6.1, 6.3, 6.4, 7.1; D3, D18, T8. The module is pure (AST test, as
`test_v1_translate_request.py` does), `Visibility.compute` is checked over its
whole input space against an independent restatement of 6.1, and `QueueSink`
runs on a real loop with the producer on a worker thread, as in production.
"""

import ast
import asyncio
import dataclasses
import inspect
import itertools
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import delivery
from app.services.delivery import (
    PHASE_NAMES,
    STAGE_NAMES,
    CommittedEvent,
    ContentEvent,
    PhaseEvent,
    QueueSink,
    ReasoningEvent,
    StageEvent,
    Visibility,
)


def test_is_pure():
    tree = ast.parse(Path(inspect.getsourcefile(delivery)).read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}

    assert modules <= {"asyncio", "dataclasses", "typing", "app.services.action_classifiers"}
    assert not names & {"settings", "open", "httpx", "log_query", "logging", "logger", "query_pipeline"}


def test_vocabularies_are_the_prd_7_1_lists():
    assert STAGE_NAMES == (
        "checking_permissions", "checking_usage", "checking_duplicates",
        "inspecting_prompt", "masking_input", "evaluating_actions", "masking_output",
    )
    assert PHASE_NAMES == ("waiting", "thinking", "writing", "preparing_action")


def _caps(streaming, reasoning):
    return SimpleNamespace(streaming=streaming, reasoning=reasoning)


def _expected(sw, rt, rv, cs, cr, ingress):
    # PRD 6.1, restated.
    realtime = sw and rt and cs
    reasoning = sw and rv and cr
    streamed = sw and cs and (realtime or reasoning or ingress == "chat")
    return (realtime, reasoning, streamed)


def test_visibility_truth_table():
    bools = (False, True)
    for sw, rt, rv, cs, cr, ingress in itertools.product(
        bools, bools, bools, bools, bools, ("chat", "v1", "query", None)
    ):
        got = Visibility.compute(
            streaming_enabled=sw, holds_realtime=rt, holds_reasoning=rv,
            caps=_caps(cs, cr), ingress=ingress,
        )
        assert (got.realtime, got.reasoning, got.upstream_streamed) == _expected(
            sw, rt, rv, cs, cr, ingress
        ), (sw, rt, rv, cs, cr, ingress)


def test_chat_without_grants_streams_upstream_but_shows_nothing():
    v = Visibility.compute(
        streaming_enabled=True, holds_realtime=False, holds_reasoning=False,
        caps=_caps(True, True), ingress="chat",
    )
    assert v == Visibility(realtime=False, reasoning=False, upstream_streamed=True)


@pytest.mark.parametrize("ingress", ["chat", "v1", "query", None])
def test_switch_off_or_no_streaming_capability_never_streams_upstream(ingress):
    off = Visibility.compute(
        streaming_enabled=False, holds_realtime=True, holds_reasoning=True,
        caps=_caps(True, True), ingress=ingress,
    )
    no_cap = Visibility.compute(
        streaming_enabled=True, holds_realtime=True, holds_reasoning=True,
        caps=_caps(False, True), ingress=ingress,
    )
    assert off == Visibility(False, False, False)
    assert no_cap.upstream_streamed is False and no_cap.realtime is False


def test_reasoning_is_independent_of_realtime():
    v = Visibility.compute(
        streaming_enabled=True, holds_realtime=False, holds_reasoning=True,
        caps=_caps(True, True), ingress="v1",
    )
    assert (v.realtime, v.reasoning, v.upstream_streamed) == (False, True, True)


def test_visibility_is_frozen():
    v = Visibility(True, False, True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.realtime = False  # type: ignore[misc]


# --- QueueSink ---------------------------------------------------------------


def _drain(queue):
    out = []
    while not queue.empty():
        out.append(queue.get_nowait())
    return out


def test_queue_sink_delivers_in_order_from_a_worker_thread():
    async def scenario():
        loop = asyncio.get_running_loop()
        sink = QueueSink(loop)

        def produce():
            sink.stage("checking_permissions")
            sink.phase("preparing_action", "shell")
            sink.content("a")
            sink.reasoning("b")
            sink.committed("chatcmpl-1")

        thread = threading.Thread(target=produce)
        thread.start()
        await loop.run_in_executor(None, thread.join)
        await asyncio.sleep(0)  # let the call_soon_threadsafe callbacks run
        return _drain(sink.queue)

    assert asyncio.run(scenario()) == [
        StageEvent("checking_permissions"),
        PhaseEvent("preparing_action", "shell"),
        ContentEvent("a"),
        ReasoningEvent("b"),
        CommittedEvent("chatcmpl-1"),
    ]


def test_queue_sink_drops_puts_after_close():
    async def scenario():
        sink = QueueSink(asyncio.get_running_loop())
        sink.stage("checking_usage")
        sink.close()
        sink.content("late")
        await asyncio.sleep(0)
        return _drain(sink.queue)

    assert asyncio.run(scenario()) == [StageEvent("checking_usage")]


def test_queue_sink_survives_a_closed_loop():
    loop = asyncio.new_event_loop()
    sink = QueueSink(loop)
    loop.close()

    sink.stage("checking_usage")  # must not raise
    sink.content("x")

    assert sink.queue.empty()


# --- PRD-021 STORY-010 (D-A): `streamed=` on the /v1 ingress ---------------------


def test_v1_not_streamed_is_never_realtime_and_follows_into_upstream_streamed():
    # PRD 6.4: `/v1 stream:false` keeps today's buffered body whatever the grants.
    v = Visibility.compute(
        streaming_enabled=True, holds_realtime=True, holds_reasoning=False,
        caps=_caps(True, True), ingress="v1", streamed=False,
    )
    assert v == Visibility(realtime=False, reasoning=False, upstream_streamed=False)
    # Reasoning alone still streams upstream to collect it (rows 3/4 of 6.4).
    v = Visibility.compute(
        streaming_enabled=True, holds_realtime=True, holds_reasoning=True,
        caps=_caps(True, True), ingress="v1", streamed=False,
    )
    assert v == Visibility(realtime=False, reasoning=True, upstream_streamed=True)


@pytest.mark.parametrize("ingress", ["chat", "query", None])
def test_streamed_false_changes_nothing_off_the_v1_ingress(ingress):
    kwargs = dict(
        streaming_enabled=True, holds_realtime=True, holds_reasoning=True,
        caps=_caps(True, True), ingress=ingress,
    )
    assert Visibility.compute(**kwargs, streamed=False) == Visibility.compute(**kwargs)


def test_v1_streamed_true_is_the_default_rule():
    kwargs = dict(
        streaming_enabled=True, holds_realtime=True, holds_reasoning=True,
        caps=_caps(True, True), ingress="v1",
    )
    assert Visibility.compute(**kwargs, streamed=True) == Visibility.compute(**kwargs)
    assert Visibility.compute(**kwargs).realtime is True
