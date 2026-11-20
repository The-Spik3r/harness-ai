"""The native Anthropic adapter, whole answers (PRD-022 6.5, D2, D4, D14).

`build_request`, `dropped_params` and `map_response` are pure: no settings, no
registry, no network, no client. The one I/O is `AnthropicAdapter.complete()`,
which builds an SDK client per call (`_open_sdk_client`), calls
`messages.create` and maps the SDK's exceptions. The key goes only into the
client; no message, log line or exception here carries request text, answer
text, reasoning text or the key (T10). Streaming arrives with STORY-007.
"""

import dataclasses
import json
from typing import Any, Iterator, Optional

import anthropic

from app.models.messages import Message, ToolCallSpec
from app.services.provider_registry import Provider
from app.services.upstream.types import (
    UpstreamError,
    UpstreamEvent,
    UpstreamRequest,
    UpstreamResult,
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


def build_request(request: UpstreamRequest, model: Any, *, provider: Provider) -> dict[str, Any]:
    """The `messages.create` keyword arguments for `request` (PRD-022 6.5), or `incompatible`.

    Raises before any network call when the request cannot be carried: tool-call
    arguments that are not a JSON object, a forced `tool_choice` on a model that
    does not claim it, or a forced `tool_choice` together with extended thinking
    (the API rejects that pair). Keys are within `ANTHROPIC_REQUEST_KEYS`.
    """
    if model is None:
        raise _incompatible(provider, "no catalogued model for this request")
    capabilities = model.capabilities
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
            if capabilities.reasoning:
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
    if capabilities.reasoning:
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
            arguments = json.dumps(block.input, ensure_ascii=False, separators=(",", ":"))
            calls.append(ToolCallSpec(block.id, block.name, arguments))
        elif kind in ("thinking", "redacted_thinking"):
            reasoning_blocks += 1  # counted only: reasoning text never enters the answer
    finish = _FINISH_REASONS.get(message.stop_reason)
    if finish is None:
        raise _shape(provider, "unsupported stop reason")
    usage = message.usage
    if usage is None:
        raise _shape(provider, "no usage")
    text = "".join(texts)
    # A refusal is an answer, never a fault (PRD-022 6.2, T4): an empty one is still
    # `content_filter`, not a `shape` error a chain could treat as a provider fault.
    if not text and not calls and finish != "content_filter":
        raise _shape(provider, "no text and no tool call")
    cache_write = _count(getattr(usage, "cache_creation_input_tokens", None))
    cache_read = _count(getattr(usage, "cache_read_input_tokens", None))
    # Anthropic's input_tokens excludes the cached portions; the harness's prompt count includes them.
    prompt = _count(usage.input_tokens) + cache_write + cache_read
    completion = _count(usage.output_tokens)
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


def _sdk_error(exc: anthropic.APIError, provider: Provider) -> UpstreamError:
    """An SDK exception as an `UpstreamError`. Never `str(exc)`: the SDK's text can quote the body (T10)."""
    label, name = provider.label, provider.name
    # Timeout first: APITimeoutError is an APIConnectionError.
    if isinstance(exc, anthropic.APITimeoutError):
        return UpstreamError(
            f"{label} request failed: timed out", retryable=True, provider=name, kind="timeout"
        )
    if isinstance(exc, anthropic.APIConnectionError):
        return UpstreamError(
            f"{label} request failed: connection error", retryable=True, provider=name, kind="transport"
        )
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
        """Plain function, so the refusal is raised at call time like the other adapter's setup errors."""
        raise UpstreamError(
            f"{self._provider.label}: streaming arrives with STORY-007",
            provider=self._provider.name,
            kind="incompatible",
        )
