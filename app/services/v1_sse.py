"""The buffered `/v1` stream (PRD-015 Sections 6.4, 7.6).

A streamed request is answered as SSE only once the upstream call has started
(D8): every verdict is decided before step 7, so the router waits for the
first of "the pipeline finished" and "the upstream was called"
(`wait_for_commit`) and sends an ordinary JSON response in the first case.
After commit, `stream` sends nothing but `: keep-alive` comments until the
pipeline's outcome exists (T8), then the events the router renders from it:
one role/content chunk, one chunk per released tool call (PRD-017), one finish
chunk, the usage chunk on request and `[DONE]` (D6), or a single `error` event and no `[DONE]`.

The pipeline is never cancelled here. It runs on its executor thread to
completion whatever the client does (Section 7.6), so the row is written and
the tokens charged after a disconnect; `detach` keeps the outcome from being
reported as unretrieved. This module reads no settings: the router passes the
keep-alive interval, so it is read per request.
"""

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Callable, List, Optional, Set, Tuple, Union

from pydantic import BaseModel

from app.models.v1_schemas import (
    ChatCompletion,
    ChatCompletionChunk,
    ChunkChoice,
    ChunkDelta,
    ChunkToolCall,
    ErrorResponse,
)
from app.services.delivery import (
    CommittedEvent,
    ContentEvent,
    DeliveryEvent,
    ReasoningEvent,
)

KEEPALIVE = ": keep-alive\n\n"
DONE = "data: [DONE]\n\n"

# Pipelines whose stream may be gone: held until they finish, because the
# event loop keeps only weak references to tasks.
_RUNNING: Set[asyncio.Future] = set()


def data_event(payload: BaseModel) -> str:
    """One `data:` event. `model_dump_json`, never `exclude_none` (v1_schemas)."""
    return f"data: {payload.model_dump_json()}\n\n"


def completion_events(completion: ChatCompletion, include_usage: bool) -> List[str]:
    """A completion as Section 7.6's chunk sequence, `[DONE]` included.

    Built from `translate_result`'s `ChatCompletion`, so `finish_reason`, the
    usage split and the id follow one rule streamed and not. Every chunk takes
    the completion's `id`, `created` and `model`.

    PRD-017 Section 6.6: the released calls (step 7c's release, which
    `translate_result` put on the message, never the upstream's, T1) follow the
    role chunk, one chunk each with its whole `arguments`. `tool_calls` absent
    (text-only) or `None` (every call denied) renders none, so those streams are
    PRD-015's. The finish chunk stays the last delta: OpenCode errors on a
    delta after a `finish_reason`, and a usage chunk after it is fine.
    """
    choice = completion.choices[0]

    def chunk(**fields) -> ChatCompletionChunk:
        return ChatCompletionChunk(
            id=completion.id, created=completion.created, model=completion.model, **fields
        )

    role_fields = {}
    if choice.message.reasoning_content is not None:
        # PRD-021 D9: buffered SSE can still carry reasoning (`reasoning.view`
        # without `stream.realtime`). Absent otherwise: the chunk is PRD-015's.
        role_fields["reasoning_content"] = choice.message.reasoning_content
    events = [
        data_event(chunk(choices=[ChunkChoice(
            delta=ChunkDelta(role="assistant", content=choice.message.content, **role_fields)
        )])),
    ]
    for index, call in enumerate(choice.message.tool_calls or []):
        events.append(data_event(chunk(choices=[ChunkChoice(
            delta=ChunkDelta(tool_calls=[
                ChunkToolCall(index=index, id=call.id, function=call.function)
            ])
        )])))
    events.append(data_event(chunk(choices=[ChunkChoice(
        delta=ChunkDelta(), finish_reason=choice.finish_reason
    )])))
    if include_usage:
        events.append(data_event(chunk(choices=[], usage=completion.usage)))
    events.append(DONE)
    return events


def error_event(body: ErrorResponse) -> str:
    """A post-commit failure: the Section 7.5 error object as one `data:` event.

    No `[DONE]` follows it. The OpenAI SDKs raise `APIError` on a `data`
    object with an `error` key (Section 7.6).
    """
    return data_event(body)


async def wait_for_commit(pipeline: asyncio.Future, started: asyncio.Event) -> None:
    """Return once the pipeline has finished or the upstream call has started.

    Which one happened is the caller's to read from the wrapper's own flag,
    not from this wait: a fast upstream can finish the pipeline in the same
    loop iteration that sets `started`. `pipeline` is never cancelled.
    """
    signal = asyncio.ensure_future(started.wait())
    try:
        await asyncio.wait({pipeline, signal}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        if not signal.done():
            signal.cancel()


def _settle(future: asyncio.Future) -> None:
    _RUNNING.discard(future)
    if not future.cancelled():
        # Retrieved, so a stream that disconnected before it was rendered
        # leaves no "exception was never retrieved" in the log.
        future.exception()


def detach(pipeline: asyncio.Future) -> None:
    """Let `pipeline` outlive its stream: held until done, its outcome always retrieved."""
    _RUNNING.add(pipeline)
    pipeline.add_done_callback(_settle)


async def stream(
    pipeline: asyncio.Future,
    render: Callable[[asyncio.Future], List[str]],
    interval: float,
) -> AsyncIterator[str]:
    """Keep-alives every `interval` seconds until `pipeline` is done, then `render(pipeline)`.

    `asyncio.wait`, not `wait_for`: it never cancels what it waits on, so a
    disconnect that cancels or closes this generator leaves the pipeline
    running. The first keep-alive comes one interval after commit.
    """
    while not pipeline.done():
        done, _ = await asyncio.wait({pipeline}, timeout=interval)
        if not done:
            yield KEEPALIVE
    for event in render(pipeline):
        yield event


@dataclass(frozen=True)
class Tail:
    """What the realtime stream sends after the last delta (PRD-021 6.6, T1).

    `completion` is `translate_result`'s body: its tool calls are step 7c's
    release and its finish reason the release's or the upstream's. `notes` are
    the release's denial notes, which belong to the content. Nothing in the tail
    is read from a delivery event.
    """

    completion: ChatCompletion
    notes: Tuple[str, ...]


async def realtime_events(
    queue: "asyncio.Queue[DeliveryEvent]",
    pipeline: asyncio.Future,
    *,
    created: int,
    model: str,
    tail: Callable[[asyncio.Future], Union[Tail, List[str]]],
    include_usage: bool,
    interval: float,
    coalesce_s: float,
    on_close: Callable[[bool], None],
) -> AsyncIterator[str]:
    """The `/v1` real-time stream (PRD-021 6.6): live deltas, then the release.

    The role chunk goes out on `CommittedEvent`, carrying the commit id that
    every later chunk reuses. `ContentEvent` becomes `delta.content` and
    `ReasoningEvent` `delta.reasoning_content` (D9, O5); stage and phase events
    are dropped (T5). Deltas of one kind are coalesced for `coalesce_s` from the
    first pending one (D21; 0 sends each as it comes); a delta of the other kind
    or the end of the stream flushes first. When the pipeline is done the queue
    is drained, then `tail(pipeline)`: a `Tail` is rendered as the released tool
    calls, the denial notes as content, the finish chunk, the usage chunk on
    request and `[DONE]`; a list (an error) is sent as is, without `[DONE]` (D16).

    Tool calls come only from the `Tail`, never from events (T1). The pipeline is
    never cancelled: `asyncio.wait` does not cancel what it waits on, and a
    disconnect only ends this generator, so the row is written and the tokens
    charged (D15). `on_close(completed)` runs last, whatever ended the stream.
    This module reads no settings: the router passes the intervals.
    """
    loop = asyncio.get_running_loop()
    completion_id: Optional[str] = None
    content_sent = False
    pending: Optional[Tuple[str, List[str], float]] = None  # (kind, parts, since)
    last_sent = loop.time()
    getter: Optional[asyncio.Future] = None
    completed = False

    def chunk(delta: ChunkDelta, finish: Optional[str] = None) -> str:
        return data_event(ChatCompletionChunk(
            id=completion_id or "", created=created, model=model,
            choices=[ChunkChoice(delta=delta, finish_reason=finish)],  # type: ignore[arg-type]
        ))

    def flush() -> List[str]:
        nonlocal pending, content_sent
        if pending is None:
            return []
        kind, parts, _ = pending
        pending = None
        text = "".join(parts)
        if kind == "reasoning":
            return [chunk(ChunkDelta(reasoning_content=text))]
        content_sent = True
        return [chunk(ChunkDelta(content=text))]

    def handle(event: DeliveryEvent) -> List[str]:
        nonlocal completion_id, pending
        if isinstance(event, CommittedEvent):
            completion_id = event.completion_id
            return [chunk(ChunkDelta(role="assistant", content=""))]
        if isinstance(event, ContentEvent):
            kind = "content"
        elif isinstance(event, ReasoningEvent):
            kind = "reasoning"
        else:
            return []  # stage / phase: never on the wire (T5)
        out: List[str] = []
        if pending is not None and pending[0] != kind:
            out = flush()
        if coalesce_s <= 0:
            pending = (kind, [event.text], loop.time())
            return out + flush()
        if pending is None:
            pending = (kind, [event.text], loop.time())
        else:
            pending[1].append(event.text)
        return out

    try:
        while not pipeline.done():
            if getter is None:
                getter = asyncio.ensure_future(queue.get())
            deadline = last_sent + interval
            if pending is not None:
                deadline = min(deadline, pending[2] + coalesce_s)
            # Never cancelled mid-wait: the same rule as `stream`.
            await asyncio.wait(
                {getter, pipeline}, timeout=max(0.0, deadline - loop.time()),
                return_when=asyncio.FIRST_COMPLETED,
            )
            out: List[str] = []
            if getter.done():
                event = getter.result()
                getter = None
                out += handle(event)
            if pending is not None and loop.time() - pending[2] >= coalesce_s:
                out += flush()
            if not out and loop.time() - last_sent >= interval:
                out = [KEEPALIVE]
            for item in out:
                yield item
            if out:
                last_sent = loop.time()

        # Done. Every put the pipeline thread made has run by now (its
        # `call_soon_threadsafe` calls precede the executor future's own, and the
        # ready queue is FIFO), so the queue holds the rest of the stream.
        if getter is not None and not getter.done():
            getter.cancel()
        elif getter is not None:
            for item in handle(getter.result()):
                yield item
        getter = None
        await asyncio.sleep(0)
        while True:
            try:
                event = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            for item in handle(event):
                yield item
        for item in flush():
            yield item

        rendered = tail(pipeline)
        if isinstance(rendered, list):
            for item in rendered:
                yield item
        else:
            completion = rendered.completion
            choice = completion.choices[0]
            for index, call in enumerate(choice.message.tool_calls or []):
                yield chunk(ChunkDelta(tool_calls=[
                    ChunkToolCall(index=index, id=call.id, function=call.function)
                ]))
            # The notes are part of the content: sent as deltas so the
            # concatenation equals `tool_release.content_with_notes` (PRD 6.6).
            sent = content_sent
            for note in rendered.notes:
                yield chunk(ChunkDelta(content=("\n\n" + note) if sent else note))
                sent = True
            yield chunk(ChunkDelta(), choice.finish_reason)
            if include_usage:
                yield data_event(ChatCompletionChunk(
                    id=completion_id or completion.id, created=created, model=model,
                    choices=[], usage=completion.usage,
                ))
            yield DONE
        completed = True
    finally:
        if getter is not None and not getter.done():
            getter.cancel()
        on_close(completed)
