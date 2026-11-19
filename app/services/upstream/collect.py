"""Assemble a stream's events into the result `complete()` would have returned (PRD-020 6.4, D8, D11).

Pure: no HTTP client, no settings, no registry import at runtime. The events are
folded into a reply dict shaped like the non-stream body and handed to
`result_from_reply`, so null-content rules, the tools= gate, D13 (arguments are
concatenated, never parsed) and the D8 usage estimate are the same code as in
`complete()`.

A usage field the provider sent as null is treated as absent: the chunk's
non-None fields become the `usage` object. This only matters for `usage_missing:
error` with `total_tokens: null`, where `complete()` returns the raw None and
this raises "'total_tokens'".
"""

from typing import TYPE_CHECKING, Any, Iterable, Optional

from app.services.upstream.reply import _USAGE_MODES, result_from_reply
from app.services.upstream.types import (
    Finish,
    ReasoningDelta,
    TextDelta,
    ToolCallDelta,
    UpstreamEvent,
    UpstreamRequest,
    UpstreamResult,
    UsageReport,
)

if TYPE_CHECKING:  # annotations only: the registry imports settings
    from app.services.provider_registry import Provider


def collect(
    events: Iterable[UpstreamEvent],
    *,
    provider: "Provider",
    request: UpstreamRequest,
    usage_missing: Optional[str] = None,
) -> UpstreamResult:
    """The events as one UpstreamResult; `provider` and `request` carry the D8 estimate and the tools= gate.

    `usage_missing` (PRD-021 D4) overrides the provider's mode for this call only
    (the pipeline passes "estimate" for a stream); None keeps the provider's.
    `ReasoningDelta` events are ignored: reasoning is never part of the result (D8).
    """
    if usage_missing is not None and usage_missing not in _USAGE_MODES:
        raise ValueError(f"usage_missing must be one of {_USAGE_MODES}, got {usage_missing}")
    texts: list[str] = []
    calls: dict[int, dict[str, Any]] = {}
    finish_reason: Optional[str] = None
    usage: Optional[dict[str, int]] = None
    for event in events:
        if isinstance(event, TextDelta):
            texts.append(event.text)
        elif isinstance(event, ToolCallDelta):
            call = calls.setdefault(event.index, {"id": None, "name": None, "arguments": []})
            if call["id"] is None:
                call["id"] = event.id
            if call["name"] is None:
                call["name"] = event.name
            call["arguments"].append(event.arguments)
        elif isinstance(event, Finish):
            if event.reason is not None:
                finish_reason = event.reason
        elif isinstance(event, ReasoningDelta):
            continue
        elif isinstance(event, UsageReport):
            usage = {
                key: value
                for key, value in (
                    ("prompt_tokens", event.prompt_tokens),
                    ("completion_tokens", event.completion_tokens),
                    ("total_tokens", event.total_tokens),
                )
                if value is not None
            }
        else:
            raise TypeError(f"unknown stream event type: {type(event).__name__}")

    message: dict[str, Any] = {"content": "".join(texts) if texts else None}
    if calls:
        message["tool_calls"] = [
            {
                "id": call["id"],
                "type": "function",
                "function": {"name": call["name"], "arguments": "".join(call["arguments"])},
            }
            for _, call in sorted(calls.items())
        ]
    data: dict[str, Any] = {"choices": [{"message": message, "finish_reason": finish_reason}]}
    if usage is not None:
        data["usage"] = usage
    return result_from_reply(provider, request, data, usage_missing=usage_missing)
