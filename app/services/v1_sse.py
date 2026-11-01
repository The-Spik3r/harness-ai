"""The buffered `/v1` stream (PRD-015 Sections 6.4, 7.6).

A streamed request is answered as SSE only once the upstream call has started
(D8): every verdict is decided before step 7, so the router waits for the
first of "the pipeline finished" and "the upstream was called"
(`wait_for_commit`) and sends an ordinary JSON response in the first case.
After commit, `stream` sends nothing but `: keep-alive` comments until the
pipeline's outcome exists (T8), then the events the router renders from it:
one content chunk, one finish chunk, the usage chunk on request and
`[DONE]` (D6), or a single `error` event and no `[DONE]`.

The pipeline is never cancelled here. It runs on its executor thread to
completion whatever the client does (Section 7.6), so the row is written and
the tokens charged after a disconnect; `detach` keeps the outcome from being
reported as unretrieved. This module reads no settings: the router passes the
keep-alive interval, so it is read per request.
"""

import asyncio
from typing import AsyncIterator, Callable, List, Set

from pydantic import BaseModel

from app.models.v1_schemas import (
    ChatCompletion,
    ChatCompletionChunk,
    ChunkChoice,
    ChunkDelta,
    ErrorResponse,
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
    """
    choice = completion.choices[0]

    def chunk(**fields) -> ChatCompletionChunk:
        return ChatCompletionChunk(
            id=completion.id, created=completion.created, model=completion.model, **fields
        )

    events = [
        data_event(chunk(choices=[ChunkChoice(
            delta=ChunkDelta(role="assistant", content=choice.message.content)
        )])),
        data_event(chunk(choices=[ChunkChoice(
            delta=ChunkDelta(), finish_reason=choice.finish_reason
        )])),
    ]
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
