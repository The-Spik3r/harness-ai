"""A parsed non-stream reply body as an UpstreamResult (PRD-020 6.4, 6.7, F6, T7).

Pure: no HTTP client, no settings, no registry import at runtime (`Provider` is
imported for annotations only). `complete()` hands it `resp.json()`; `collect()`
hands it the reply it assembled from a stream, so both paths share one set of
rules and one set of message texts (PRD-020 D11).
"""

from typing import TYPE_CHECKING, Any, Mapping, Optional

from app.models.messages import ToolCallSpec
from app.services.upstream.types import UpstreamError, UpstreamRequest, UpstreamResult
from app.services.usage_estimate import estimate_tokens

if TYPE_CHECKING:  # annotations only: the registry imports settings
    from app.services.provider_registry import Provider


def _token_count(value: Any) -> Optional[int]:
    """A provider-reported token count, or None when it is not usable (PRD-013 F3)."""
    # bool is a subclass of int: True/False must not be recorded as 1/0.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _parse_tool_calls(raw: Any, label: str) -> tuple[ToolCallSpec, ...]:
    """choices[0].message.tool_calls as ToolCallSpecs (PRD-017 Section 4, D13).

    Used only when the request sent tools= (D18). Every failure is a
    non-retryable shape error naming the field, never a value. `type` is lenient
    when absent or null (some providers omit it) and strict when wrong; the
    client-edge normalizer is stricter because OpenAI's spec requires the key
    there. arguments must already be a string: coercing an object would invent
    bytes the model never wrote (D13), so it is refused, never serialized.
    """
    prefix = f"{label} returned an unexpected response shape: "
    if not isinstance(raw, list):
        raise UpstreamError(f"{prefix}choices[0].message.tool_calls is not a list")
    calls: list[ToolCallSpec] = []
    seen: set[str] = set()
    for index, call in enumerate(raw):
        where = f"choices[0].message.tool_calls[{index}]"
        if not isinstance(call, Mapping):
            raise UpstreamError(f"{prefix}{where} is not an object")
        call_id = call.get("id")
        if not isinstance(call_id, str) or not call_id:
            raise UpstreamError(f"{prefix}{where}.id must be a non-empty string")
        call_type = call.get("type")
        if call_type is not None and call_type != "function":
            raise UpstreamError(f'{prefix}{where}.type must be "function"')
        function = call.get("function")
        if not isinstance(function, Mapping):
            raise UpstreamError(f"{prefix}{where}.function is not an object")
        name = function.get("name")
        if not isinstance(name, str) or not name:
            raise UpstreamError(f"{prefix}{where}.function.name must be a non-empty string")
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            raise UpstreamError(f"{prefix}{where}.function.arguments must be a string")
        if call_id in seen:
            raise UpstreamError(f"{prefix}{where}.id repeats an earlier id in this response")
        seen.add(call_id)
        calls.append(ToolCallSpec(id=call_id, name=name, arguments=arguments))
    return tuple(calls)


def _resolve_usage(
    provider: "Provider",
    label: str,
    data: Any,
    content: str,
    calls: tuple[ToolCallSpec, ...],
    request: UpstreamRequest,
) -> tuple[int, Optional[int], Optional[int], bool]:
    """(tokens_used, input_tokens, output_tokens, usage_estimated) per PRD-020 D8.

    `usage_missing: error` (legacy) keeps today's behaviour and message texts: a
    missing `usage` or `total_tokens` is an unexpected-shape error, and a present
    total is taken raw. A `null` or non-object usage raises the same message
    naming 'usage' (it was a bare TypeError). `estimate` never fails a call that
    answered: a usable total (and splits) win; two usable splits without a total
    sum to one; anything else is an estimate with the split left None (a lone
    split is discarded), flagged `usage_estimated`.
    """
    usage = data.get("usage") if isinstance(data, Mapping) else None
    has_usage = isinstance(usage, Mapping)
    if provider.usage_missing == "error":
        if not has_usage:
            raise UpstreamError(f"{label} returned an unexpected response shape: 'usage'")
        if "total_tokens" not in usage:
            raise UpstreamError(f"{label} returned an unexpected response shape: 'total_tokens'")
        # PRD-013 F3: optional, and never a reason to fail a call that answered.
        return (
            usage["total_tokens"],
            _token_count(usage.get("prompt_tokens")),
            _token_count(usage.get("completion_tokens")),
            False,
        )
    if has_usage:
        total = _token_count(usage.get("total_tokens"))
        prompt = _token_count(usage.get("prompt_tokens"))
        completion = _token_count(usage.get("completion_tokens"))
        if total is not None:
            return total, prompt, completion, False
        if prompt is not None and completion is not None:
            return prompt + completion, prompt, completion, False
    tools = request.tools
    estimate = estimate_tokens(
        request.messages,
        (content, calls),
        provider.estimate_chars_per_token,
        tools=tools.tools if tools is not None else None,
    )
    return estimate, None, None, True


def result_from_reply(
    provider: "Provider", request: UpstreamRequest, data: Any
) -> UpstreamResult:
    """The reply body `data` as an UpstreamResult: everything `complete()` does after `json()`.

    Shape errors are non-retryable `UpstreamError`s naming the field (T7);
    `model_used` is the upstream id the request carried (the caller maps it back
    to the requested id, D13).
    """
    label = provider.label
    tools = request.tools
    try:
        choice = data["choices"][0]
        message = choice["message"]
        content = message["content"]
    except (KeyError, IndexError, ValueError) as exc:
        raise UpstreamError(f"{label} returned an unexpected response shape: {exc}") from exc

    calls: tuple[ToolCallSpec, ...] = ()
    if tools is not None:
        # PRD-017: parsed only when tools= was sent. Absent, null and [] are no calls.
        raw_calls = message.get("tool_calls")
        if raw_calls is not None:
            calls = _parse_tool_calls(raw_calls, label)
    if content is None and calls:
        content = ""  # content: null beside calls (PRD-017 Section 4)
    if content is None:
        # Unchanged under D18. Note a null content plus tool_calls: [] sent
        # with tools= still gets the note below: its condition is kept as is.
        finish_reason = choice.get("finish_reason")
        error_message = f"{label} returned no text content (finish_reason={finish_reason})"
        if message.get("tool_calls") is not None:
            error_message += "; tool calls are not supported (PRD-017)"
        raise UpstreamError(error_message)

    raw_finish_reason = choice.get("finish_reason")
    finish_reason = raw_finish_reason if isinstance(raw_finish_reason, str) else None

    tokens_used, input_tokens, output_tokens, usage_estimated = _resolve_usage(
        provider, label, data, content, calls, request
    )
    return UpstreamResult(
        response=content,
        model_used=request.upstream_model,
        tokens_used=tokens_used,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        finish_reason=finish_reason,
        tool_calls=calls,
        usage_estimated=usage_estimated,
    )
