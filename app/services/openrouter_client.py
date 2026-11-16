from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Union

import httpx

from app.config import settings
from app.models.messages import Message, ToolCallSpec

_DEFAULT_MODEL = "gpt-4"

_ALLOWED_GENERATION_PARAMS = frozenset({"temperature", "max_tokens", "top_p", "stop"})
_MAX_STOP_SEQUENCES = 4


class OpenRouterError(Exception):
    """A failed upstream call, and what the client knows about why (PRD-015 D7).

    upstream_status is the HTTP status the upstream answered with, None when
    there was no response. retryable is True only for a transient fault --
    timeout, transport error, upstream 5xx or 429 -- since the same request
    may then succeed; STORY-011 maps it to `/v1`'s retry semantics. The
    message is the only positional argument, so `str(exc)` -- and with it the
    audit row's error_message and /query's 502 detail -- is unchanged.
    """

    def __init__(
        self,
        message: str,
        *,
        upstream_status: Optional[int] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.upstream_status = upstream_status
        self.retryable = retryable


class UnsupportedParameterError(Exception):
    """A generation parameter is outside PRD-010's allowlist or its validated range.

    Raised by GenerationParams construction (direct or via from_mapping), always
    before any HTTP call -- PRD-010 T5: no ingress may widen OpenRouter's
    surface past four allowlisted, range-checked fields.
    """


@dataclass(frozen=True)
class GenerationParams:
    """The only generation parameters call_openrouter may forward (PRD-010 F3, T5).

    Every field defaults to None and is sent only when set. from_mapping is
    PRD-015's entry point (the track's "PRD-014"): v1_translate.translate_request
    is its production caller.
    """

    temperature: Optional[float] = None   # 0.0 <= t <= 2.0
    max_tokens: Optional[int] = None       # >= 1
    top_p: Optional[float] = None          # 0.0 < p <= 1.0
    stop: Optional[Union[str, Sequence[str]]] = None   # <= 4 sequences

    def __post_init__(self) -> None:
        if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
            raise UnsupportedParameterError(
                f"temperature must be between 0.0 and 2.0, got {self.temperature!r}"
            )
        if self.max_tokens is not None:
            # bool is a subclass of int: True/False must not slip past >= 1.
            if isinstance(self.max_tokens, bool) or self.max_tokens < 1:
                raise UnsupportedParameterError(
                    f"max_tokens must be an integer >= 1, got {self.max_tokens!r}"
                )
        if self.top_p is not None and not (0.0 < self.top_p <= 1.0):
            raise UnsupportedParameterError(
                f"top_p must be greater than 0.0 and at most 1.0, got {self.top_p!r}"
            )
        if self.stop is not None:
            if isinstance(self.stop, str):
                pass
            elif isinstance(self.stop, (list, tuple)):
                if len(self.stop) > _MAX_STOP_SEQUENCES:
                    raise UnsupportedParameterError(
                        f"stop must have at most {_MAX_STOP_SEQUENCES} sequences, got {len(self.stop)}"
                    )
                if not all(isinstance(s, str) for s in self.stop):
                    raise UnsupportedParameterError(
                        f"stop sequences must all be strings, got {self.stop!r}"
                    )
            else:
                raise UnsupportedParameterError(
                    f"stop must be a string or a list of up to {_MAX_STOP_SEQUENCES} strings, got {self.stop!r}"
                )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "GenerationParams":
        """PRD-015's entry point (`/v1`). Raises for any key outside the allowlist, sorted."""
        unsupported = sorted(set(raw) - _ALLOWED_GENERATION_PARAMS)
        if unsupported:
            raise UnsupportedParameterError(
                f"unsupported parameter(s): {', '.join(unsupported)}"
            )
        return cls(**{key: raw[key] for key in _ALLOWED_GENERATION_PARAMS if key in raw})


@dataclass(frozen=True)
class ToolParams:
    """The tool request call_openrouter forwards (PRD-017 Section 4, D11).

    Its own keyword, not fields on GenerationParams (PRD-010 T5: from_mapping
    must keep refusing `tools`). Carries values only: shape validation is the
    `/v1` translator's (STORY-008), which is its one builder. Fields are sent
    as given, and a None field is not sent.
    """

    tools: Sequence[Mapping[str, Any]]
    tool_choice: Optional[Union[str, Mapping[str, Any]]] = None
    parallel_tool_calls: Optional[bool] = None


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


def _parse_tool_calls(raw: Any) -> tuple[ToolCallSpec, ...]:
    """choices[0].message.tool_calls as ToolCallSpecs (PRD-017 Section 4, D13).

    Used only when the request sent tools= (D18). Every failure is a
    non-retryable shape error naming the field, never a value. `type` is lenient
    when absent or null (some providers omit it) and strict when wrong; the
    client-edge normalizer is stricter because OpenAI's spec requires the key
    there. arguments must already be a string: coercing an object would invent
    bytes the model never wrote (D13), so it is refused, never serialized.
    """
    prefix = "OpenRouter returned an unexpected response shape: "
    if not isinstance(raw, list):
        raise OpenRouterError(f"{prefix}choices[0].message.tool_calls is not a list")
    calls: list[ToolCallSpec] = []
    seen: set[str] = set()
    for index, call in enumerate(raw):
        where = f"choices[0].message.tool_calls[{index}]"
        if not isinstance(call, Mapping):
            raise OpenRouterError(f"{prefix}{where} is not an object")
        call_id = call.get("id")
        if not isinstance(call_id, str) or not call_id:
            raise OpenRouterError(f"{prefix}{where}.id must be a non-empty string")
        call_type = call.get("type")
        if call_type is not None and call_type != "function":
            raise OpenRouterError(f'{prefix}{where}.type must be "function"')
        function = call.get("function")
        if not isinstance(function, Mapping):
            raise OpenRouterError(f"{prefix}{where}.function is not an object")
        name = function.get("name")
        if not isinstance(name, str) or not name:
            raise OpenRouterError(f"{prefix}{where}.function.name must be a non-empty string")
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            raise OpenRouterError(f"{prefix}{where}.function.arguments must be a string")
        if call_id in seen:
            raise OpenRouterError(f"{prefix}{where}.id repeats an earlier id in this response")
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


@dataclass
class OpenRouterResult:
    response: str
    model_used: str
    tokens_used: int
    # PRD-013 STORY-003: usage.prompt_tokens and usage.completion_tokens, None
    # when the provider omitted or malformed the field. Declared after
    # tokens_used with defaults so three-argument construction keeps working.
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    # PRD-015 STORY-002: choices[0].finish_reason, None when absent or not a
    # string. Declared last with a default for the same reason as the split.
    finish_reason: Optional[str] = None
    # PRD-017 STORY-004: choices[0].message.tool_calls, parsed only when the
    # request sent tools= (D18). Declared last with a default, the PRD-013 /
    # PRD-015 precedent, so three-argument construction keeps working.
    tool_calls: tuple[ToolCallSpec, ...] = ()


def call_openrouter(
    messages: Sequence[Message],
    model: str = _DEFAULT_MODEL,
    api_key: Optional[str] = None,
    params: Optional[GenerationParams] = None,
    client: Optional[httpx.Client] = None,
    *,
    tools: Optional[ToolParams] = None,
) -> OpenRouterResult:
    """tool_calls are parsed only when `tools=` was sent (PRD-017 D18).

    Without it, a null content with tool calls stays today's error.
    """
    if not messages:
        raise OpenRouterError("messages must not be empty")

    resolved_key = api_key or settings.OPENROUTER_API_KEY
    if not resolved_key:
        raise OpenRouterError(
            "OpenRouter API key not configured: pass openrouter_api_key or set OPENROUTER_API_KEY"
        )

    headers = {
        "Authorization": f"Bearer {resolved_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [_wire_message(m) for m in messages],
    }
    if params is not None:
        for field in ("temperature", "max_tokens", "top_p", "stop"):
            value = getattr(params, field)
            if value is not None:
                payload[field] = value
    # PRD-017 D11: forwarded as given, a None field not sent. A separate keyword,
    # passed only when set (params='s rule), so (messages, model, api_key) stubs
    # keep working.
    if tools is not None:
        payload["tools"] = tools.tools
        for field in ("tool_choice", "parallel_tool_calls"):
            value = getattr(tools, field)
            if value is not None:
                payload[field] = value

    owns_client = client is None
    http_client = client or httpx.Client(timeout=settings.OPENROUTER_TIMEOUT_SECONDS)
    try:
        # Read per call, for the reason query_pipeline._context_limit_exceeded gives.
        url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
        try:
            resp = http_client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            upstream_status, retryable = _classify_http_error(exc)
            raise OpenRouterError(
                f"OpenRouter request failed: {exc}",
                upstream_status=upstream_status,
                retryable=retryable,
            ) from exc

        try:
            data = resp.json()
            choice = data["choices"][0]
            message = choice["message"]
            content = message["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise OpenRouterError(
                f"OpenRouter returned an unexpected response shape: {exc}"
            ) from exc

        calls: tuple[ToolCallSpec, ...] = ()
        if tools is not None:
            # PRD-017: parsed only when tools= was sent. Absent, null and [] are no calls.
            raw_calls = message.get("tool_calls")
            if raw_calls is not None:
                calls = _parse_tool_calls(raw_calls)
        if content is None and calls:
            content = ""  # content: null beside calls (PRD-017 Section 4)
        if content is None:
            # Unchanged under D18. Note a null content plus tool_calls: [] sent
            # with tools= still gets the note below: its condition is kept as is.
            finish_reason = choice.get("finish_reason")
            error_message = f"OpenRouter returned no text content (finish_reason={finish_reason})"
            if message.get("tool_calls") is not None:
                error_message += "; tool calls are not supported (PRD-017)"
            raise OpenRouterError(error_message)

        raw_finish_reason = choice.get("finish_reason")
        finish_reason = raw_finish_reason if isinstance(raw_finish_reason, str) else None

        try:
            usage = data["usage"]
            tokens_used = usage["total_tokens"]
        except (KeyError, IndexError, ValueError) as exc:
            raise OpenRouterError(
                f"OpenRouter returned an unexpected response shape: {exc}"
            ) from exc
        # PRD-013 F3: optional, and never a reason to fail a call that answered.
        input_tokens = _token_count(usage.get("prompt_tokens"))
        output_tokens = _token_count(usage.get("completion_tokens"))
    finally:
        if owns_client:
            http_client.close()

    return OpenRouterResult(
        response=content,
        model_used=model,
        tokens_used=tokens_used,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        finish_reason=finish_reason,
        tool_calls=calls,
    )
