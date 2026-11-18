"""The OpenAI-compatible adapter (PRD-020 6.4, F3, F6, T7).

Today's `call_openrouter` body, parameterized by a `Provider`: base URL, label
and timeout come from the provider; the key arrives only as an argument and
goes only into the request headers (T1, T6). No registry access, no settings.
"""

from typing import Any, Mapping, Optional

import httpx

from app.models.messages import Message, ToolCallSpec
from app.services.provider_registry import Provider
from app.services.upstream.types import UpstreamError, UpstreamRequest, UpstreamResult
from app.services.usage_estimate import estimate_tokens


def _token_count(value: Any) -> Optional[int]:
    """A provider-reported token count, or None when it is not usable (PRD-013 F3)."""
    # bool is a subclass of int: True/False must not be recorded as 1/0.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _wire_message(message: Message) -> dict[str, Any]:
    """One Message as the upstream wire shape (PRD-017 F5).

    Tool-free messages stay exactly {"role", "content"}. arguments is the
    ToolCallSpec's string, never parsed or re-serialized (D13).
    """
    wire: dict[str, Any] = {"role": message.role}
    if message.tool_call_id is not None:
        wire["tool_call_id"] = message.tool_call_id
    # OpenAI's tool-call assistant turn is content: null; the normalizer turned
    # that null into "" (messages.py), so it is restored here.
    wire["content"] = None if message.tool_calls and message.content == "" else message.content
    if message.tool_calls:
        wire["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
            for c in message.tool_calls
        ]
    return wire


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


def _classify_http_error(exc: httpx.HTTPError) -> tuple[Optional[int], bool]:
    """(upstream_status, retryable) for a failed request (PRD-015 Section 7.5)."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status, status >= 500 or status == 429
    # Timeouts, connect errors and the other transport failures: no response,
    # and nothing about the request made it fail.
    if isinstance(exc, httpx.TransportError):
        return None, True
    return None, False



def _resolve_usage(
    provider: Provider,
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


class OpenAICompatibleAdapter:
    """POST {base_url}/chat/completions for one provider (PRD-020 6.4)."""

    def __init__(self, provider: Provider, client: Optional[httpx.Client] = None) -> None:
        self._provider = provider
        self._client = client

    def complete(self, request: UpstreamRequest, api_key: Optional[str]) -> UpstreamResult:
        provider = self._provider
        label = provider.label
        params = request.params
        tools = request.tools

        # No key (a keyless provider) means no Authorization header at all (PRD-020 F3).
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        headers["Content-Type"] = "application/json"
        payload: dict[str, Any] = {
            "model": request.upstream_model,
            "messages": [_wire_message(m) for m in request.messages],
        }
        if params is not None:
            for field in ("temperature", "max_tokens", "top_p", "stop"):
                value = getattr(params, field)
                if value is not None:
                    payload[field] = value
        # PRD-017 D11: forwarded as given, a None field not sent.
        if tools is not None:
            payload["tools"] = tools.tools
            for field in ("tool_choice", "parallel_tool_calls"):
                value = getattr(tools, field)
                if value is not None:
                    payload[field] = value

        owns_client = self._client is None
        # PRD-020 D5/F3: redirects are never followed, so a provider cannot bounce
        # the request (and its Authorization header) to another host.
        http_client = self._client or httpx.Client(
            timeout=provider.timeout_seconds, follow_redirects=False
        )
        try:
            url = f"{provider.base_url.rstrip('/')}/chat/completions"
            try:
                resp = http_client.post(url, headers=headers, json=payload)
                # Checked here, not via raise_for_status: whether httpx treats a 3xx
                # as an error varies by version. The Location is never quoted.
                if 300 <= resp.status_code < 400:
                    raise UpstreamError(
                        f"{label} request failed: unexpected redirect (HTTP {resp.status_code}); "
                        "redirects are not followed",
                        upstream_status=resp.status_code,
                        retryable=False,
                    )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                upstream_status, retryable = _classify_http_error(exc)
                raise UpstreamError(
                    f"{label} request failed: {exc}",
                    upstream_status=upstream_status,
                    retryable=retryable,
                ) from exc

            try:
                data = resp.json()
                choice = data["choices"][0]
                message = choice["message"]
                content = message["content"]
            except (KeyError, IndexError, ValueError) as exc:
                raise UpstreamError(
                    f"{label} returned an unexpected response shape: {exc}"
                ) from exc

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
        finally:
            if owns_client:
                http_client.close()

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
