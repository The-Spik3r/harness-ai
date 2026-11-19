"""Server-sent-event lines of a chat-completions stream as normalized events (PRD-020 6.4, D11, T7).

Pure: no HTTP client, no settings. `parse_events` takes the response's text lines
(httpx `iter_lines`) and yields `UpstreamEvent`s lazily. Every failure is a
non-retryable `UpstreamError` that names the field and never quotes a payload or
a line (T7), with the same prefix `complete()` uses for a bad body.
"""

import json
from typing import Any, Iterable, Iterator, Mapping

from app.services.upstream.types import (
    Finish,
    ReasoningDelta,
    TextDelta,
    ToolCallDelta,
    UpstreamError,
    UpstreamEvent,
    UsageReport,
)


def parse_events(
    lines: Iterable[str], label: str, *, reasoning: bool = False
) -> Iterator[UpstreamEvent]:
    """Events of one stream, ending at `data: [DONE]`; EOF before it is an error.

    `reasoning` (PRD-021 Risk 3) maps a delta's reasoning text to `ReasoningDelta`;
    off, the reasoning keys are never read and the text is dropped.
    """
    prefix = f"{label} returned an unexpected response shape: "
    seen_calls: set[int] = set()
    for line in lines:
        # Blank lines separate frames; a line starting with ":" is an SSE comment.
        if not line or line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if field != "data":
            continue  # event:, id:, retry: carry nothing this adapter uses
        if value.startswith(" "):
            value = value[1:]
        if value.strip() == "[DONE]":
            return
        try:
            chunk = json.loads(value)
        except ValueError as exc:
            raise UpstreamError(f"{prefix}stream data is not JSON") from exc
        if not isinstance(chunk, Mapping):
            raise UpstreamError(f"{prefix}stream data is not an object")
        yield from _chunk_events(chunk, prefix, seen_calls, reasoning)
    raise UpstreamError(f"{prefix}stream ended without [DONE]")


def _chunk_events(
    chunk: Mapping[str, Any], prefix: str, seen_calls: set[int], reasoning: bool = False
) -> Iterator[UpstreamEvent]:
    choices = chunk.get("choices")
    if choices is not None and not isinstance(choices, list):
        raise UpstreamError(f"{prefix}choices is not a list")
    if choices:
        choice = choices[0]
        if not isinstance(choice, Mapping):
            raise UpstreamError(f"{prefix}choices[0] is not an object")
        delta = choice.get("delta")
        if delta is not None and not isinstance(delta, Mapping):
            raise UpstreamError(f"{prefix}choices[0].delta is not an object")
        if delta:
            if reasoning:
                # One event per delta: OpenRouter sends `reasoning`, DeepSeek-style
                # providers `reasoning_content`. null, "" and non-strings yield none;
                # `reasoning_details` is never read.
                for key in ("reasoning_content", "reasoning"):
                    text = delta.get(key)
                    if isinstance(text, str) and text:
                        yield ReasoningDelta(text)
                        break
            content = delta.get("content")
            if isinstance(content, str):
                yield TextDelta(content)
            raw_calls = delta.get("tool_calls")
            if raw_calls is not None:
                yield from _call_events(raw_calls, prefix, seen_calls)
        finish = choice.get("finish_reason")
        if isinstance(finish, str):
            yield Finish(finish)
    usage = chunk.get("usage")
    if isinstance(usage, Mapping):
        yield UsageReport(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )


def _call_events(raw: Any, prefix: str, seen_calls: set[int]) -> Iterator[ToolCallDelta]:
    if not isinstance(raw, list):
        raise UpstreamError(f"{prefix}delta.tool_calls is not a list")
    for position, call in enumerate(raw):
        where = f"delta.tool_calls[{position}]"
        if not isinstance(call, Mapping):
            raise UpstreamError(f"{prefix}{where} is not an object")
        index = call.get("index")
        if isinstance(index, bool) or not isinstance(index, int):
            raise UpstreamError(f"{prefix}{where}.index must be an integer")
        call_id = call.get("id")
        if call_id is not None and not isinstance(call_id, str):
            raise UpstreamError(f"{prefix}{where}.id must be a string")
        if index not in seen_calls and not call_id:
            # A fragment for a call that never announced itself cannot be assembled.
            raise UpstreamError(f"{prefix}{where}.index has no earlier fragment carrying an id")
        seen_calls.add(index)
        function = call.get("function")
        if function is not None and not isinstance(function, Mapping):
            raise UpstreamError(f"{prefix}{where}.function is not an object")
        name = function.get("name") if function else None
        if name is not None and not isinstance(name, str):
            raise UpstreamError(f"{prefix}{where}.function.name must be a string")
        arguments = function.get("arguments") if function else None
        if arguments is not None and not isinstance(arguments, str):
            raise UpstreamError(f"{prefix}{where}.function.arguments must be a string")
        yield ToolCallDelta(
            index=index,
            id=call_id or None,
            name=name or None,
            arguments=arguments or "",
        )
