"""Folds the pipeline's delivery events into per-window state updates (PRD-021 D19).

`ChatState._do_send` hands one `QueueSink` to the pipeline and drains its queue
here: `batches()` groups whatever arrived into windows of at most
`WINDOW_SECONDS`, and `fold()` turns one window into the dict of state vars it
changes. The state applies each window under a single `async with self`, which
Reflex flushes as one delta (`reflex/istate/proxy.py`, the outermost
`StateProxy.__aexit__`; PRD-021 Risk 5), so the browser sees at most ten updates
a second whatever the token rate.

No Reflex import and no I/O: asyncio and the delivery events only, so the
batching is testable without a running app. Tool-call fragments never reach the
sink (D6), so nothing here can carry them; reasoning is folded into a live var
that is never persisted (D8).
"""

import asyncio
from typing import Any, AsyncIterator, Iterable, List

from app.services.delivery import (
    ContentEvent,
    DeliveryEvent,
    PhaseEvent,
    ReasoningEvent,
    StageEvent,
)

# PRD-021 D19: one state update per 100 ms window, at most.
WINDOW_SECONDS = 0.1

# Put on the queue when the pipeline task finishes, after every event it emitted.
END: Any = object()


async def batches(
    queue: "asyncio.Queue[Any]", window_s: float = WINDOW_SECONDS
) -> AsyncIterator[List[DeliveryEvent]]:
    """Yields lists of events, at most one per window, until `END` arrives.

    Blocks on the first event of a window (no spin), then collects until the
    window, measured from that first event, expires or `END` arrives. Events
    still queued after `END` are yielded as one last batch.
    """
    loop = asyncio.get_running_loop()
    done = False
    while not done:
        first = await queue.get()
        if first is END:
            break
        batch: List[DeliveryEvent] = [first]
        deadline = loop.time() + window_s
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                item = await asyncio.wait_for(queue.get(), remaining)
            except asyncio.TimeoutError:
                break
            if item is END:
                done = True
                break
            batch.append(item)
        yield batch
    leftovers: List[DeliveryEvent] = []
    while True:
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if item is not END:
            leftovers.append(item)
    if leftovers:
        yield leftovers


def fold(
    events: Iterable[DeliveryEvent], *, stage: str, phase: str, now: float
) -> dict:
    """Pure. The state vars one window changes (empty when it changes none).

    `stage` and `phase` are the current values: `progress_since` moves to `now`
    only when the window changes one of them, so a repeated word does not
    restart the clock the 300 ms no-flicker rule reads. Within a window the
    last stage/phase wins and texts concatenate in order. `CommittedEvent` is
    ignored (the chat needs no commit signal).
    """
    new_stage, new_phase, new_action = stage, phase, None
    text: List[str] = []
    reasoning: List[str] = []
    for event in events:
        if isinstance(event, StageEvent):
            new_stage = event.name
        elif isinstance(event, PhaseEvent):
            new_phase = event.name
            new_action = event.action_kind or ""
        elif isinstance(event, ContentEvent):
            text.append(event.text)
        elif isinstance(event, ReasoningEvent):
            reasoning.append(event.text)
    out: dict = {}
    if new_stage != stage:
        out["progress_stage"] = new_stage
    if new_phase != phase:
        out["progress_phase"] = new_phase
    if new_action is not None:
        out["progress_action"] = new_action
    if "progress_stage" in out or "progress_phase" in out:
        out["progress_since"] = now
    if text:
        out["live_text"] = "".join(text)
    if reasoning:
        out["live_reasoning"] = "".join(reasoning)
    return out
