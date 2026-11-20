"""The native Anthropic adapter, whole answers (PRD-022 6.5, D2, D4, D14).

`build_request`, `dropped_params`, `map_response` and the helpers they share
with the stream path are pure: no settings, no registry, no network, no client.
The I/O is `AnthropicAdapter.complete()` and `.stream()`, which build an SDK
client per call (`_open_sdk_client`), call `messages.create` (`stream=True` for
the raw SSE events, STORY-007) and map the SDK's exceptions. The key goes only
into the client; no message, log line or exception here carries request text,
answer text, reasoning text or the key (T10).
"""

import dataclasses
import json
import types
from typing import Any, Iterator, Optional

import anthropic
import httpx

from app.models.messages import Message, ToolCallSpec
from app.services.provider_registry import Provider
from app.services.upstream.types import (
    Finish,
    ReasoningDelta,
    TextDelta,
    ToolCallDelta,
    UpstreamError,
    UpstreamEvent,
    UpstreamRequest,
    UpstreamResult,
    UsageReport,
)

# PRD-022 T9: the only top-level keys the adapter ever sends. A new key is a deliberate edit here.
ANTHROPIC_REQUEST_KEYS = frozenset(
    {
        "model",
        "messages",
        "max_tokens",
        "system",
        "tools",
        "tool_choice",
        "stop_sequences",
        "temperature",
        "top_p",
        "thinking",
        "cache_control",
    }
)

# PRD-022 6.5: Anthropic `stop_reason` -> the harness's `finish_reason`. Anything else
# (`pause_turn`, None, a future value) is a shape fault, never guessed.
_FINISH_REASONS = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "model_context_window_exceeded": "length",
    "tool_use": "tool_calls",
    "refusal": "content_filter",
}


def _incompatible(provider: Provider, rule: str) -> UpstreamError:
    """A request this provider cannot carry: never sent, never retried (D8). Names the rule only (T10)."""
    return UpstreamError(
        f"{provider.label}: {rule}",
        provider=provider.name,
        kind="incompatible",
        retryable=False,
    )


def _shape(provider: Provider, rule: str) -> UpstreamError:
    return UpstreamError(
        f"{provider.label} returned an unexpected response shape: {rule}",
        provider=provider.name,
        kind="shape",
        retryable=False,
    )


def _tool_use_block(call: ToolCallSpec, provider: Provider) -> dict[str, Any]:
    try:
        parsed = json.loads(call.arguments)
    except ValueError:
        parsed = None
    if not isinstance(parsed, dict):
        raise _incompatible(provider, "tool call arguments are not a JSON object")
    return {"type": "tool_use", "id": call.id, "name": call.name, "input": parsed}


def _map_messages(
    messages: Any, provider: Provider
) -> tuple[Optional[str], list[dict[str, Any]]]:
    """(system, messages) in Anthropic's shape (PRD-022 6.5).

    System turns are hoisted wherever they occur, in order. Consecutive tool turns
    become one user message of `tool_result` blocks; a user turn after them stays a
    separate message (the API combines same-role turns itself).
    """
    system: list[str] = []
    wire: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    def flush() -> None:
        if results:
            wire.append({"role": "user", "content": list(results)})
            results.clear()

    for message in messages:  # type: Message
        if message.role == "tool":
            results.append(
                {"type": "tool_result", "tool_use_id": message.tool_call_id, "content": message.content}
            )
            continue
        flush()
        if message.role == "system":
            system.append(message.content)
        elif message.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if message.content != "":
                blocks.append({"type": "text", "text": message.content})
            blocks.extend(_tool_use_block(c, provider) for c in message.tool_calls)
            wire.append({"role": "assistant", "content": blocks})
        else:
            wire.append({"role": "user", "content": [{"type": "text", "text": message.content}]})
    flush()
    return ("\n\n".join(system) if system else None), wire


def _map_tool(tool: Any, provider: Provider) -> dict[str, Any]:
    function = tool.get("function") if isinstance(tool, dict) else None
    if not isinstance(function, dict) or not isinstance(function.get("name"), str):
        raise _incompatible(provider, "a tool is not an OpenAI function tool")
    mapped: dict[str, Any] = {
        "name": function["name"],
        "input_schema": function.get("parameters") or {"type": "object"},
    }
    if function.get("description") is not None:
        mapped["description"] = function["description"]
    if function.get("strict") is not None:
        mapped["strict"] = function["strict"]
    return mapped


def _map_tool_choice(choice: Any, parallel: Optional[bool], provider: Provider) -> dict[str, Any]:
    if choice is None:
        mapped: dict[str, Any] = {"type": "auto"}
    elif choice == "none":
        return {"type": "none"}  # the SDK type has no disable_parallel_tool_use here
    elif choice == "auto":
        mapped = {"type": "auto"}
    elif choice == "required":
        mapped = {"type": "any"}
    elif isinstance(choice, dict) and isinstance(choice.get("function"), dict) and isinstance(
        choice["function"].get("name"), str
    ):
        mapped = {"type": "tool", "name": choice["function"]["name"]}
    else:
        raise _incompatible(provider, "tool_choice is not a shape this provider accepts")
    if parallel is False:
        mapped["disable_parallel_tool_use"] = True
    return mapped


def build_request(
    request: UpstreamRequest,
    model: Any,
    *,
    provider: Provider,
    reasoning: Optional[bool] = None,
) -> dict[str, Any]:
    """The `messages.create` keyword arguments for `request` (PRD-022 6.5), or `incompatible`.

    Raises before any network call when the request cannot be carried: tool-call
    arguments that are not a JSON object, a forced `tool_choice` on a model that
    does not claim it, or a forced `tool_choice` together with extended thinking
    (the API rejects that pair). Keys are within `ANTHROPIC_REQUEST_KEYS`.
    `reasoning` (STORY-007, D14) overrides `capabilities.reasoning` for the
    `thinking` key and the forced-choice check: None keeps the capability, which
    is what `complete()` passes; `stream()` passes its own flag.
    """
    if model is None:
        raise _incompatible(provider, "no catalogued model for this request")
    capabilities = model.capabilities
    thinking = capabilities.reasoning if reasoning is None else reasoning
    params = request.params
    tools = request.tools

    system, messages = _map_messages(request.messages, provider)
    body: dict[str, Any] = {
        "model": request.upstream_model,
        "messages": messages,
        "max_tokens": model.default_max_tokens,
    }
    if system is not None:
        body["system"] = system

    if tools is not None:
        body["tools"] = [_map_tool(t, provider) for t in tools.tools]
        tool_choice = _map_tool_choice(tools.tool_choice, tools.parallel_tool_calls, provider)
        if tool_choice["type"] in ("any", "tool"):
            if not capabilities.forced_tool_choice:
                raise _incompatible(provider, "model does not support a forced tool_choice")
            if thinking:
                raise _incompatible(
                    provider, "forced tool_choice cannot be combined with extended thinking"
                )
        body["tool_choice"] = tool_choice

    if params is not None:
        if params.max_tokens is not None:
            body["max_tokens"] = params.max_tokens
        if params.stop is not None:
            body["stop_sequences"] = [params.stop] if isinstance(params.stop, str) else list(params.stop)
        if capabilities.sampling_params:
            if params.temperature is not None:
                body["temperature"] = params.temperature
            if params.top_p is not None:
                body["top_p"] = params.top_p
    if model.prompt_cache == "auto":
        body["cache_control"] = {"type": "ephemeral"}
    if thinking:
        # D14: adaptive, summarized; the summary is counted, never forwarded.
        body["thinking"] = {"type": "adaptive", "display": "summarized"}
    return body


def dropped_params(request: UpstreamRequest, model: Any) -> tuple[str, ...]:
    """Sampling params the request set and the model does not accept (PRD-022 6.5), bare names."""
    params = request.params
    if params is None or model is None or model.capabilities.sampling_params:
        return ()
    return tuple(name for name in ("temperature", "top_p") if getattr(params, name) is not None)


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _canonical_arguments(value: Any) -> str:
    """A tool input as the compact JSON string the harness carries (shared by `complete()` and `stream()`)."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _finish_reason(stop_reason: Any, provider: Provider) -> str:
    finish = _FINISH_REASONS.get(stop_reason)
    if finish is None:
        raise _shape(provider, "unsupported stop reason")
    return finish


def _check_answer(has_text: bool, has_calls: bool, finish: str, provider: Provider) -> None:
    """A refusal is an answer, never a fault (PRD-022 6.2, T4): an empty one is still
    `content_filter`, not a `shape` error a chain could treat as a provider fault."""
    if not has_text and not has_calls and finish != "content_filter":
        raise _shape(provider, "no text and no tool call")


def _usage_counts(usage: Any) -> tuple[int, int, int, int]:
    """(prompt, completion, cache_write, cache_read). Anthropic's input_tokens excludes the
    cached portions; the harness's prompt count includes them."""
    cache_write = _count(getattr(usage, "cache_creation_input_tokens", None))
    cache_read = _count(getattr(usage, "cache_read_input_tokens", None))
    prompt = _count(usage.input_tokens) + cache_write + cache_read
    return prompt, _count(usage.output_tokens), cache_write, cache_read


def map_response(message: Any, provider: Provider) -> UpstreamResult:
    """An SDK `Message` as an `UpstreamResult` (PRD-022 6.5); a malformed one is a `shape` error."""
    texts: list[str] = []
    calls: list[ToolCallSpec] = []
    reasoning_blocks = 0
    for block in message.content or ():
        kind = getattr(block, "type", None)
        if kind == "text":
            texts.append(block.text)
        elif kind == "tool_use":
            arguments = _canonical_arguments(block.input)
            calls.append(ToolCallSpec(block.id, block.name, arguments))
        elif kind in ("thinking", "redacted_thinking"):
            reasoning_blocks += 1  # counted only: reasoning text never enters the answer
    finish = _finish_reason(message.stop_reason, provider)
    usage = message.usage
    if usage is None:
        raise _shape(provider, "no usage")
    text = "".join(texts)
    _check_answer(bool(text), bool(calls), finish, provider)
    prompt, completion, cache_write, cache_read = _usage_counts(usage)
    return UpstreamResult(
        response=text,
        model_used=message.model,
        tokens_used=prompt + completion,
        input_tokens=prompt,
        output_tokens=completion,
        finish_reason=finish,
        tool_calls=tuple(calls),
        usage_estimated=False,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        reasoning_blocks=reasoning_blocks,
    )


def _retry_after_seconds(exc: anthropic.APIStatusError) -> Optional[int]:
    """A 429's integer `Retry-After`, at least 1; a date, junk or no header is None (PRD-022 6.2)."""
    value = exc.response.headers.get("retry-after", "").strip()
    return max(1, int(value)) if value.isdigit() else None


def _timeout_error(provider: Provider) -> UpstreamError:
    return UpstreamError(
        f"{provider.label} request failed: timed out", retryable=True, provider=provider.name, kind="timeout"
    )


def _transport_error(provider: Provider) -> UpstreamError:
    return UpstreamError(
        f"{provider.label} request failed: connection error",
        retryable=True,
        provider=provider.name,
        kind="transport",
    )


def _sdk_error(exc: anthropic.APIError, provider: Provider) -> UpstreamError:
    """An SDK exception as an `UpstreamError`. Never `str(exc)`: the SDK's text can quote the body (T10)."""
    label, name = provider.label, provider.name
    # Timeout first: APITimeoutError is an APIConnectionError.
    if isinstance(exc, anthropic.APITimeoutError):
        return _timeout_error(provider)
    if isinstance(exc, anthropic.APIConnectionError):
        return _transport_error(provider)
    if isinstance(exc, anthropic.APIStatusError):
        status = exc.status_code
        message = f"{label} request failed: HTTP {status}"
        if isinstance(exc, anthropic.AuthenticationError):
            return UpstreamError(
                message, upstream_status=status, retryable=False, provider=name, kind="misconfigured"
            )
        if isinstance(exc, anthropic.RateLimitError):
            return UpstreamError(
                message,
                upstream_status=status,
                retryable=True,
                provider=name,
                kind="status",
                retry_after_seconds=_retry_after_seconds(exc),
            )
        # InternalServerError covers 5xx, 529 included; every other status (3xx too) is final.
        return UpstreamError(
            message,
            upstream_status=status,
            retryable=isinstance(exc, anthropic.InternalServerError),
            provider=name,
            kind="status",
        )
    return _shape(provider, "the SDK rejected the reply")


_USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")

# PRD-022 6.2: an SSE `event: error` under HTTP 200, by the event's `error.type`.
# (kind, status the chain sees, retryable). Never the event's text (T10).
_IN_STREAM_ERRORS = {
    "overloaded_error": ("status", 529, True),
    "api_error": ("status", 500, True),
    "rate_limit_error": ("status", 429, True),  # no Retry-After header is available mid-stream
    "authentication_error": ("misconfigured", 401, False),
    "permission_error": ("misconfigured", 403, False),
}


def _in_stream_error(exc: anthropic.APIStatusError, provider: Provider) -> UpstreamError:
    """An SSE `error` event (an `APIStatusError` with status 200) mapped by its `error.type`.

    An unknown type or an unparseable body is a final `status` 502: the provider
    broke mid-stream in a way this adapter cannot classify.
    """
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error")
    error_type = error.get("type") if isinstance(error, dict) else None
    kind, status, retryable = _IN_STREAM_ERRORS.get(error_type, ("status", 502, False))
    return UpstreamError(
        f"{provider.label} request failed: HTTP {status}",
        upstream_status=status,
        retryable=retryable,
        provider=provider.name,
        kind=kind,
    )


def _map_events(sdk_events: Any, provider: Provider, reasoning: bool) -> Iterator[UpstreamEvent]:
    """The SDK's raw Messages events as `UpstreamEvent`s (PRD-022 6.6).

    Tool input is buffered per block and emitted once, canonical, at its
    `content_block_stop`, as `complete()` carries it. Thinking text is forwarded
    only with `reasoning`; `redacted_thinking` and signatures never. `UsageReport`
    and `Finish` follow `message_delta`, after the same checks as `map_response`.
    Nothing is synthesized but one empty `TextDelta` for an empty refusal, so
    `collect()` returns `""` as `complete()` does (T4, fix 27e0e91). A stream with
    no `message_delta` is a `shape` fault; `message_stop` itself is not required.
    """
    start_usage: dict[str, Any] = {}
    blocks: dict[int, dict[str, Any]] = {}
    tool_ordinal = 0
    has_text = has_calls = finished = False
    for event in sdk_events:
        kind = getattr(event, "type", None)
        if kind == "message_start":
            usage = getattr(getattr(event, "message", None), "usage", None)
            start_usage = {name: getattr(usage, name, None) for name in _USAGE_FIELDS}
        elif kind == "content_block_start":
            block = event.content_block
            if getattr(block, "type", None) == "tool_use":
                blocks[event.index] = {
                    "kind": "tool_use", "id": block.id, "name": block.name,
                    "ordinal": tool_ordinal, "buffer": [],
                }
                tool_ordinal += 1
            else:
                blocks[event.index] = {"kind": getattr(block, "type", None)}
        elif kind == "content_block_delta":
            delta = event.delta
            delta_kind = getattr(delta, "type", None)
            block = blocks.get(event.index, {})
            if delta_kind == "text_delta":
                if delta.text:
                    has_text = True
                    yield TextDelta(delta.text)
            elif delta_kind == "thinking_delta":
                if reasoning and delta.thinking:
                    yield ReasoningDelta(delta.thinking)
            elif delta_kind == "input_json_delta" and block.get("kind") == "tool_use":
                block["buffer"].append(delta.partial_json)
            # signature_delta, citations_delta and unknown deltas carry nothing we forward
        elif kind == "content_block_stop":
            block = blocks.get(event.index, {})
            if block.get("kind") == "tool_use":
                try:
                    parsed = json.loads("".join(block["buffer"]) or "{}")
                except ValueError:
                    parsed = None
                if not isinstance(parsed, dict):
                    raise _shape(provider, "tool input is not a JSON object")
                has_calls = True
                yield ToolCallDelta(block["ordinal"], block["id"], block["name"], _canonical_arguments(parsed))
        elif kind == "message_delta":
            finish = _finish_reason(getattr(event.delta, "stop_reason", None), provider)
            merged = dict(start_usage)
            delta_usage = getattr(event, "usage", None)
            for name in _USAGE_FIELDS:
                value = getattr(delta_usage, name, None)
                if value is not None:
                    merged[name] = value
            if all(value is None for value in merged.values()):
                raise _shape(provider, "no usage")
            _check_answer(has_text, has_calls, finish, provider)
            prompt, completion, cache_write, cache_read = _usage_counts(types.SimpleNamespace(**merged))
            if finish == "content_filter" and not has_text and not has_calls:
                yield TextDelta("")  # an empty refusal still collects to "" (T4)
            # total_tokens is always set: collect() never takes the D8 estimate path, as `usage_estimated=False`
            yield UsageReport(prompt, completion, prompt + completion, cache_read, cache_write)
            yield Finish(finish)
            finished = True
        # message_stop, ping and unknown event types: nothing to do
    if not finished:
        raise _shape(provider, "stream ended without a stop")


def _open_sdk_client(provider: Provider, api_key: Optional[str]) -> anthropic.Anthropic:
    """One SDK client for one call (STORY-001): no SDK retries, an explicit timeout, no redirects."""
    return anthropic.Anthropic(
        api_key=api_key,
        base_url=provider.base_url,
        timeout=provider.timeout_seconds,
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(follow_redirects=False),
    )


class AnthropicAdapter:
    """`messages.create` for one `type: anthropic` provider (PRD-022 D4)."""

    def __init__(self, provider: Provider, *, sdk_client: Any = None) -> None:
        self._provider = provider
        self._sdk_client = sdk_client  # an injected client is used as is and never closed

    def complete(self, request: UpstreamRequest, api_key: Optional[str]) -> UpstreamResult:
        provider = self._provider
        body = build_request(request, request.model, provider=provider)  # raises before any network
        dropped = dropped_params(request, request.model)
        owns_client = self._sdk_client is None
        if owns_client and not api_key:
            raise UpstreamError(
                f"{provider.label} API key not configured",
                provider=provider.name,
                kind="misconfigured",
            )
        client = self._sdk_client if not owns_client else _open_sdk_client(provider, api_key)
        try:
            try:
                message = client.messages.create(**body)
            except anthropic.APIError as exc:
                # `from None`: the SDK exception's text can quote the response body (T10).
                raise _sdk_error(exc, provider) from None
            return dataclasses.replace(map_response(message, provider), dropped_params=dropped)
        finally:
            if owns_client:
                client.close()

    def stream(
        self, request: UpstreamRequest, api_key: Optional[str], *, reasoning: bool = False
    ) -> Iterator[UpstreamEvent]:
        """The same answer as events (PRD-022 6.6, D4).

        A plain function, like `stream_upstream`: the request is built (so an
        `incompatible` one, thinking plus a forced `tool_choice` included) and the
        key checked at call time, before any network. The client is opened and the
        request sent on the first `next()` of the returned generator.
        """
        provider = self._provider
        body = build_request(request, request.model, provider=provider, reasoning=reasoning)
        owns_client = self._sdk_client is None
        if owns_client and not api_key:
            raise UpstreamError(
                f"{provider.label} API key not configured",
                provider=provider.name,
                kind="misconfigured",
            )
        return self._events(body, api_key, reasoning, owns_client)

    def _events(
        self, body: dict[str, Any], api_key: Optional[str], reasoning: bool, owns_client: bool
    ) -> Iterator[UpstreamEvent]:
        provider = self._provider
        client = self._sdk_client if not owns_client else _open_sdk_client(provider, api_key)
        sdk_stream = None
        try:
            try:
                sdk_stream = client.messages.create(**body, stream=True)
                yield from _map_events(sdk_stream, provider, reasoning)
            except anthropic.APIStatusError as exc:
                # `from None`: the SDK exception's text quotes the event or body (T10).
                if exc.status_code == 200:  # an SSE `event: error` arrives as a 200 status error
                    raise _in_stream_error(exc, provider) from None
                raise _sdk_error(exc, provider) from None
            except anthropic.APIError as exc:
                raise _sdk_error(exc, provider) from None
            except httpx.TimeoutException:
                # The SDK does not wrap read errors raised while iterating.
                raise _timeout_error(provider) from None
            except httpx.TransportError:
                raise _transport_error(provider) from None
        finally:
            close = getattr(sdk_stream, "close", None)
            if callable(close):
                close()
            if owns_client:
                client.close()
